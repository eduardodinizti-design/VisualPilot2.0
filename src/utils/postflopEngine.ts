export type Street = 'flop' | 'turn' | 'river';
export type HeroPosition = 'IP' | 'OOP';
export type BoardTexture = 'dry_high' | 'paired' | 'wet_connected' | 'monotone';
export type HandCategory =
  | 'nut_value'
  | 'strong_value'
  | 'medium_showdown'
  | 'combo_draw'
  | 'nut_draw'
  | 'weak_draw'
  | 'air';
export type VillainAction =
  | 'checked_to_hero'
  | 'facing_small_bet'
  | 'facing_large_bet'
  | 'facing_overbet'
  | 'facing_shove';
export type VillainLine =
  | 'uncapped'
  | 'capped_check_back'
  | 'passive_turned_aggressive';
export type BlockerType = 'none' | 'blocks_nuts_value' | 'blocks_bluffs';
export type AggressionProfile = 'tight' | 'balanced' | 'loose';
export type PreflopInitiative = 'hero_pfr' | 'villain_pfr' | 'three_bet_pot' | 'limped_pot';
export type TurnRiverCard =
  | 'brick'
  | 'overcard'
  | 'flush_completes'
  | 'straight_completes'
  | 'board_pairs';

export interface PostflopInput {
  street: Street;
  potBB: number;
  effectiveStackBB: number;
  heroPosition: HeroPosition;
  playersInPot: 2 | 3 | 4;
  preflopInitiative: PreflopInitiative;
  boardTexture: BoardTexture;
  turnRiverCard: TurnRiverCard;
  handCategory: HandCategory;
  drawOuts: number;
  villainAction: VillainAction;
  villainLine: VillainLine;
  blockerType: BlockerType;
  aggressionProfile: AggressionProfile;
  bountyCoverBB: number;
  hudSampleHands: number;
  hudFoldToCbet: number;
  useMixedRng: boolean;
  rngRoll: number;
}

export interface DiagnosticRule {
  tag: string;
  status: 'positive' | 'warning' | 'neutral';
  message: string;
}

export interface PostflopDecision {
  action: 'BET / VALUE' | 'C-BET BLEFE' | 'DONK BET' | 'CHECK' | 'RAISE / SHOVE' | 'CALL' | 'FOLD';
  sizingLabel: string;
  sizingBB: number;
  geometricPotPct: number;
  spr: number;
  sprZone: 'LOW (Compromisso)' | 'MEDIUM (Geométrico)' | 'HIGH (Deep / Pot Control)';
  potCommitted: boolean;
  eqrFactor: number;
  rawEquityPct: number;
  outsEquityPct: number | null;
  effectiveEquityPct: number;
  requiredEquityPct: number;
  mdfPct: number;
  poolAdjustedMdfPct: number;
  rangeAdvantage: 'Hero' | 'Vilão' | 'Neutro';
  nutAdvantage: 'Hero' | 'Vilão' | 'Neutro';
  cbetEquityThresholdPct: number;
  raiseEquityThresholdPct: number;
  hudFoldThresholdPct: number;
  hudExploitActive: boolean;
  frequencies: { primary: number; secondary: number; secondaryLabel: string };
  rngExecutedLine: string;
  diagnostics: DiagnosticRule[];
  streetPlan: { street: string; potBefore: number; betPct: number; betBB: number }[];
}

const BASE_EQUITY_BY_HAND: Record<HandCategory, number> = {
  nut_value: 88,
  strong_value: 71,
  medium_showdown: 50,
  combo_draw: 48,
  nut_draw: 36,
  weak_draw: 21,
  air: 10,
};

const AGGRESSION_CONFIG: Record<
  AggressionProfile,
  {
    label: string;
    cbetMinEquityPct: number;
    raiseMinEquityPct: number;
    hudCbetFoldPct: number;
    hudRaiseFoldPct: number;
    callMarginOffset: number;
    raiseSprCap: number;
  }
> = {
  tight: {
    label: 'Tight (Conservador)',
    cbetMinEquityPct: 48,
    raiseMinEquityPct: 62,
    hudCbetFoldPct: 68,
    hudRaiseFoldPct: 75,
    callMarginOffset: 5,
    raiseSprCap: 1.6,
  },
  balanced: {
    label: 'Balanced (GTO Padrão)',
    cbetMinEquityPct: 34,
    raiseMinEquityPct: 46,
    hudCbetFoldPct: 55,
    hudRaiseFoldPct: 62,
    callMarginOffset: 0,
    raiseSprCap: 2.5,
  },
  loose: {
    label: 'Loose (Agressivo / Exploit)',
    cbetMinEquityPct: 20,
    raiseMinEquityPct: 34,
    hudCbetFoldPct: 45,
    hudRaiseFoldPct: 52,
    callMarginOffset: -4,
    raiseSprCap: 3.4,
  },
};

export function calculateGeometricBetPct(spr: number, remainingStreets: number): number {
  if (spr <= 0 || remainingStreets <= 0) return 0;
  const s = (Math.pow(1 + 2 * spr, 1 / remainingStreets) - 1) / 2;
  return Math.round(Math.min(Math.max(s * 100, 20), 250));
}

export function calculateExactOutsEquityPct(
  outs: number,
  street: Street,
  boardTexture: BoardTexture
): number | null {
  if (street === 'river' || outs <= 0) return null;
  const clampedOuts = Math.min(20, Math.max(1, outs));
  // Dirty-out discount on paired or monotone textures (sets/two pair/flushes can beat our draw)
  const dirtyDiscount = boardTexture === 'paired' || boardTexture === 'monotone' ? 0.85 : 1.0;
  const effectiveOuts = clampedOuts * dirtyDiscount;

  if (street === 'flop') {
    const missFlopTurn = (47 - effectiveOuts) / 47;
    const missTurnRiver = (46 - effectiveOuts) / 46;
    return Math.round((1 - missFlopTurn * missTurnRiver) * 100);
  }
  // Turn -> 1 card to come
  return Math.round((effectiveOuts / 46) * 100);
}

function evaluateRangeAndNutAdvantage(
  initiative: PreflopInitiative,
  texture: BoardTexture,
  street: Street,
  card: TurnRiverCard
): { rangeAdvantage: 'Hero' | 'Vilão' | 'Neutro'; nutAdvantage: 'Hero' | 'Vilão' | 'Neutro' } {
  let rangeAdvantage: 'Hero' | 'Vilão' | 'Neutro' = 'Neutro';
  let nutAdvantage: 'Hero' | 'Vilão' | 'Neutro' = 'Neutro';

  if (initiative === 'hero_pfr' || initiative === 'three_bet_pot') {
    if (texture === 'dry_high' || texture === 'paired') {
      rangeAdvantage = 'Hero';
      nutAdvantage = 'Hero';
    } else if (texture === 'wet_connected') {
      rangeAdvantage = initiative === 'three_bet_pot' ? 'Hero' : 'Neutro';
      nutAdvantage = initiative === 'three_bet_pot' ? 'Neutro' : 'Vilão';
    } else {
      rangeAdvantage = 'Neutro';
      nutAdvantage = 'Neutro';
    }
  } else if (initiative === 'villain_pfr') {
    if (texture === 'dry_high' || texture === 'paired') {
      rangeAdvantage = 'Vilão';
      nutAdvantage = 'Vilão';
    } else if (texture === 'wet_connected') {
      rangeAdvantage = 'Neutro';
      nutAdvantage = 'Hero'; // BB / caller hits sets, 2-pair and straights heavily on low/connected boards
    } else {
      rangeAdvantage = 'Vilão';
      nutAdvantage = 'Neutro';
    }
  } else {
    // limped_pot
    rangeAdvantage = 'Neutro';
    nutAdvantage = 'Neutro';
  }

  // Turn/River card shift
  if (street !== 'flop') {
    if (card === 'overcard') {
      if (initiative === 'hero_pfr' || initiative === 'three_bet_pot') {
        rangeAdvantage = 'Hero';
      } else if (initiative === 'villain_pfr') {
        rangeAdvantage = 'Vilão';
      }
    } else if (card === 'flush_completes' || card === 'straight_completes') {
      if (initiative === 'villain_pfr') {
        nutAdvantage = 'Hero';
      }
    }
  }

  return { rangeAdvantage, nutAdvantage };
}

export function evaluatePostflopSpot(input: PostflopInput): PostflopDecision {
  const safePot = Math.max(input.potBB, 1);
  const safeStack = Math.max(input.effectiveStackBB, 0);
  const spr = Number((safeStack / safePot).toFixed(2));

  const sprZone: PostflopDecision['sprZone'] =
    spr <= 2.5
      ? 'LOW (Compromisso)'
      : spr <= 6
      ? 'MEDIUM (Geométrico)'
      : 'HIGH (Deep / Pot Control)';
  const potCommitted = spr < 1.5 && safeStack > 0;

  const remainingStreets = input.street === 'flop' ? 3 : input.street === 'turn' ? 2 : 1;
  const geometricPotPct = calculateGeometricBetPct(spr, remainingStreets);

  // Equity Realization (EQR) + Multi-way penalty + 3-bet pot EQR stability
  let eqrFactor = input.heroPosition === 'IP' ? 1.08 : 0.78;
  if (input.preflopInitiative === 'three_bet_pot' && input.heroPosition === 'IP') {
    eqrFactor = 1.12;
  }
  const extraPlayers = input.playersInPot - 2;
  if (extraPlayers > 0) {
    eqrFactor = Number((eqrFactor * Math.pow(0.86, extraPlayers)).toFixed(2));
  } else {
    eqrFactor = Number(eqrFactor.toFixed(2));
  }

  const outsEquityPct = calculateExactOutsEquityPct(input.drawOuts, input.street, input.boardTexture);
  let rawEquityPct = BASE_EQUITY_BY_HAND[input.handCategory];

  // Blend or override draw equity when real outs are provided
  if (
    outsEquityPct !== null &&
    (input.handCategory === 'combo_draw' ||
      input.handCategory === 'nut_draw' ||
      input.handCategory === 'weak_draw')
  ) {
    rawEquityPct = Math.min(82, Math.max(rawEquityPct, outsEquityPct + 6));
  }

  // Board vulnerability & scare card penalty on Turn/River
  let scareCardPenalty = 0;
  if (input.street !== 'flop') {
    if (input.turnRiverCard === 'flush_completes' && input.handCategory === 'strong_value') {
      scareCardPenalty = input.blockerType === 'blocks_nuts_value' ? 4 : 11;
    } else if (input.turnRiverCard === 'straight_completes' && input.handCategory === 'strong_value') {
      scareCardPenalty = 10;
    } else if (input.turnRiverCard === 'board_pairs' && input.handCategory === 'strong_value') {
      scareCardPenalty = 8;
    } else if (input.turnRiverCard === 'overcard' && input.handCategory === 'medium_showdown') {
      scareCardPenalty = 9;
    }
  } else if (
    (input.boardTexture === 'wet_connected' || input.boardTexture === 'monotone') &&
    input.handCategory === 'strong_value'
  ) {
    scareCardPenalty = 5;
  }

  rawEquityPct = Math.max(5, rawEquityPct - scareCardPenalty);
  const effectiveEquityPct = Math.min(98, Math.round(rawEquityPct * eqrFactor));

  const agg = AGGRESSION_CONFIG[input.aggressionProfile];
  const cbetEquityThresholdPct = agg.cbetMinEquityPct;
  const raiseEquityThresholdPct = agg.raiseMinEquityPct;
  const hudFoldThresholdPct = agg.hudCbetFoldPct;

  const { rangeAdvantage, nutAdvantage } = evaluateRangeAndNutAdvantage(
    input.preflopInitiative,
    input.boardTexture,
    input.street,
    input.turnRiverCard
  );

  // Facing bet pot odds + MDF + PKO bounty discount
  const facingBetPct =
    input.villainAction === 'facing_small_bet'
      ? 0.33
      : input.villainAction === 'facing_large_bet'
      ? 0.75
      : input.villainAction === 'facing_overbet'
      ? 1.35
      : input.villainAction === 'facing_shove'
      ? Math.max(0.5, spr)
      : 0;

  const facingBetBB = Math.min(safeStack, safePot * facingBetPct);
  const pkoBountyEquivalentBB = input.bountyCoverBB > 0 ? input.bountyCoverBB * 0.45 : 0;

  const requiredEquityPct =
    facingBetBB > 0
      ? Math.round((facingBetBB / (safePot + facingBetBB * 2 + pkoBountyEquivalentBB)) * 100)
      : 0;

  const mdfPct = facingBetPct > 0 ? Math.round((1 / (1 + facingBetPct)) * 100) : 0;
  const poolUnderbluffFactor =
    input.villainLine === 'passive_turned_aggressive' || input.villainAction === 'facing_overbet'
      ? 0.75
      : 1.0;
  const poolAdjustedMdfPct = Math.round(mdfPct * poolUnderbluffFactor);

  const hudExploitActive = input.hudSampleHands >= 30;
  const isMultiWay = input.playersInPot > 2;

  const diagnostics: DiagnosticRule[] = [];

  diagnostics.push({
    tag: 'Range & Nut Advantage',
    status: rangeAdvantage === 'Hero' || nutAdvantage === 'Hero' ? 'positive' : rangeAdvantage === 'Vilão' ? 'warning' : 'neutral',
    message: `Iniciativa (${input.preflopInitiative}) em board ${input.boardTexture}: Vantagem de Range = ${rangeAdvantage} | Vantagem de Nuts = ${nutAdvantage}.`,
  });

  if (input.street !== 'flop') {
    diagnostics.push({
      tag: 'Scare Card (Turn/River)',
      status: scareCardPenalty > 0 ? 'warning' : 'neutral',
      message:
        scareCardPenalty > 0
          ? `Carta "${input.turnRiverCard}" reduziu a equidade efetiva em -${scareCardPenalty}% por vulnerabilidade contra draws completados.`
          : `Carta "${input.turnRiverCard}" preserva a estabilidade do range sem penalidade adicional.`,
    });
  }

  if (outsEquityPct !== null) {
    diagnostics.push({
      tag: 'Calculadora de Outs',
      status: 'positive',
      message: `${input.drawOuts} out(s) na street ${input.street.toUpperCase()} geram ~${outsEquityPct}% de equidade combinatória${
        input.boardTexture === 'paired' || input.boardTexture === 'monotone' ? ' (com desconto de outs sujos 0.85x).' : '.'
      }`,
    });
  }

  if (mdfPct > 0) {
    diagnostics.push({
      tag: 'MDF & Overbet',
      status: input.villainAction === 'facing_overbet' ? 'warning' : 'neutral',
      message: `Aposta de ${Math.round(facingBetPct * 100)}% exige MDF teórico de ${mdfPct}% (ajustado para ${poolAdjustedMdfPct}% no pool da Evolution).`,
    });
  }

  diagnostics.push({
    tag: 'Perfil Agressividade',
    status: input.aggressionProfile === 'balanced' ? 'neutral' : 'positive',
    message: `Perfil ${agg.label}: C-Bet ≥ ${cbetEquityThresholdPct}% | Raise ≥ ${raiseEquityThresholdPct}% | HUD Fold ≥ ${hudFoldThresholdPct}%.`,
  });

  diagnostics.push({
    tag: 'SPR & EQR',
    status: isMultiWay ? 'warning' : 'positive',
    message: `SPR ${spr} (${sprZone}) · EQR ${eqrFactor}x (${input.playersInPot}-way ${input.heroPosition}).`,
  });

  if (potCommitted) {
    diagnostics.push({
      tag: 'Pot Commit (SPR < 1.5)',
      status: 'warning',
      message: `SPR ${spr} < 1.5: compromisso iminente com o pote. Apostas fracionadas destroem fold equity futura — priorizando All-In direto (${safeStack.toFixed(1)} BB).`,
    });
  }

  if (input.hudSampleHands > 0) {
    diagnostics.push({
      tag: 'HUD Gate',
      status: hudExploitActive ? 'positive' : 'warning',
      message: hudExploitActive
        ? `Amostra válida (${input.hudSampleHands} mãos ≥ 30): Fold to C-Bet ${input.hudFoldToCbet}% vs piso ${hudFoldThresholdPct}%.`
        : `Amostra insuficiente (${input.hudSampleHands} mãos < 30): exploit de HUD bloqueado; linha base GTO ativa.`,
    });
  }

  if (input.bountyCoverBB > 0) {
    diagnostics.push({
      tag: 'PKO Overlay',
      status: 'positive',
      message: `Hero cobre bounty de ${input.bountyCoverBB} BB (+${pkoBountyEquivalentBB.toFixed(1)} BB efetivos no pote).`,
    });
  }

  // Decision Logic v2
  let action: PostflopDecision['action'] = 'CHECK';
  let betPct = 0;
  let frequencies = { primary: 80, secondary: 20, secondaryLabel: 'Check' };

  if (input.villainAction === 'checked_to_hero') {
    // Donk-Bet opportunity when Villain was PFR, Hero is OOP (BB defender) with Nut Advantage on wet/connected board
    const donkOpportunity =
      input.preflopInitiative === 'villain_pfr' &&
      input.heroPosition === 'OOP' &&
      nutAdvantage === 'Hero' &&
      !isMultiWay &&
      (input.handCategory === 'nut_value' || input.handCategory === 'combo_draw');

    if (donkOpportunity) {
      action = 'DONK BET';
      betPct = input.boardTexture === 'wet_connected' ? 50 : 33;
      frequencies = { primary: 65, secondary: 35, secondaryLabel: 'Check-Raise' };
    } else if (input.handCategory === 'nut_value' || input.handCategory === 'strong_value') {
      const scareSlowdown =
        input.street !== 'flop' &&
        (input.turnRiverCard === 'flush_completes' || input.turnRiverCard === 'straight_completes') &&
        input.handCategory === 'strong_value' &&
        input.blockerType !== 'blocks_nuts_value';

      if (scareSlowdown && input.heroPosition === 'OOP') {
        action = 'CHECK';
        frequencies = { primary: 70, secondary: 30, secondaryLabel: 'Block Bet 33%' };
      } else if (effectiveEquityPct >= cbetEquityThresholdPct) {
        action = 'BET / VALUE';
        if (input.boardTexture === 'dry_high' || input.boardTexture === 'paired') {
          betPct = spr <= 2.5 ? Math.min(geometricPotPct, 65) : rangeAdvantage === 'Hero' ? 33 : 50;
          frequencies = { primary: rangeAdvantage === 'Hero' ? 90 : 75, secondary: rangeAdvantage === 'Hero' ? 10 : 25, secondaryLabel: 'Check Trap' };
        } else {
          betPct = Math.min(geometricPotPct, 75);
          frequencies = { primary: 80, secondary: 20, secondaryLabel: 'Check' };
        }
        if (spr <= 1.3 && input.handCategory === 'nut_value') {
          action = 'RAISE / SHOVE';
          betPct = Math.round(spr * 100);
        }
      } else {
        action = 'CHECK';
        frequencies = { primary: 65, secondary: 35, secondaryLabel: 'Bet Valor' };
      }
    } else if (input.handCategory === 'combo_draw' || input.handCategory === 'nut_draw') {
      if (effectiveEquityPct >= raiseEquityThresholdPct && spr <= agg.raiseSprCap && !isMultiWay) {
        action = 'BET / VALUE';
        betPct = Math.min(geometricPotPct, 75);
        frequencies = { primary: 80, secondary: 20, secondaryLabel: 'Check-Call' };
      } else if (effectiveEquityPct >= cbetEquityThresholdPct && (input.heroPosition === 'IP' || !isMultiWay)) {
        action = 'C-BET BLEFE';
        betPct = input.boardTexture === 'dry_high' ? 33 : 66;
        frequencies = { primary: 70, secondary: 30, secondaryLabel: 'Check' };
      } else {
        action = 'CHECK';
        frequencies = { primary: 70, secondary: 30, secondaryLabel: 'Bet 50%' };
      }
    } else if (input.handCategory === 'medium_showdown') {
      const canThinValue =
        effectiveEquityPct >= cbetEquityThresholdPct &&
        !isMultiWay &&
        input.heroPosition === 'IP' &&
        (input.boardTexture === 'dry_high' || input.boardTexture === 'paired') &&
        (input.villainLine === 'capped_check_back' || input.aggressionProfile === 'loose') &&
        scareCardPenalty === 0;

      if (canThinValue) {
        action = 'BET / VALUE';
        betPct = 33;
        frequencies = { primary: input.aggressionProfile === 'loose' ? 70 : 60, secondary: input.aggressionProfile === 'loose' ? 30 : 40, secondaryLabel: 'Check' };
      } else {
        action = 'CHECK';
        frequencies = { primary: 85, secondary: 15, secondaryLabel: 'Bet 33%' };
      }
    } else {
      const canHudBluff = hudExploitActive && input.hudFoldToCbet >= agg.hudCbetFoldPct && !isMultiWay;
      const goodBlockerBluff =
        input.blockerType === 'blocks_nuts_value' &&
        !isMultiWay &&
        rangeAdvantage !== 'Vilão' &&
        (input.aggressionProfile !== 'tight' || input.street !== 'flop');
      const cappedAttack =
        input.villainLine === 'capped_check_back' &&
        !isMultiWay &&
        input.heroPosition === 'IP' &&
        input.aggressionProfile !== 'tight';
      const looseIpCbet =
        input.aggressionProfile === 'loose' &&
        !isMultiWay &&
        input.heroPosition === 'IP' &&
        rangeAdvantage === 'Hero' &&
        effectiveEquityPct >= cbetEquityThresholdPct - 10;

      if (canHudBluff || goodBlockerBluff || cappedAttack || looseIpCbet) {
        action = 'C-BET BLEFE';
        betPct = input.boardTexture === 'dry_high' && input.street === 'flop' ? 33 : 66;
        frequencies = { primary: input.aggressionProfile === 'loose' ? 75 : 65, secondary: input.aggressionProfile === 'loose' ? 25 : 35, secondaryLabel: 'Check / Give Up' };
      } else {
        action = 'CHECK';
        frequencies = { primary: 95, secondary: 5, secondaryLabel: 'Blefe 33%' };
      }
    }
  } else {
    // Facing a bet, overbet, or shove
    if (input.handCategory === 'nut_value') {
      if (input.villainAction === 'facing_shove') {
        action = 'CALL';
        frequencies = { primary: 100, secondary: 0, secondaryLabel: 'Fold' };
      } else {
        action = 'RAISE / SHOVE';
        betPct = spr <= 2.5 ? Math.round(spr * 100) : 100;
        frequencies = { primary: 85, secondary: 15, secondaryLabel: 'Slowplay Call' };
      }
    } else if (input.handCategory === 'strong_value') {
      const facingOverbetOrPassiveRiver =
        input.villainAction === 'facing_overbet' ||
        (input.villainLine === 'passive_turned_aggressive' && input.street === 'river' && input.villainAction === 'facing_large_bet');

      if (facingOverbetOrPassiveRiver) {
        const extraRequired = input.villainAction === 'facing_overbet' ? 14 : 12;
        const blockerSave = input.blockerType === 'blocks_nuts_value' ? 5 : 0;
        action =
          effectiveEquityPct >= requiredEquityPct + extraRequired - blockerSave + agg.callMarginOffset
            ? 'CALL'
            : 'FOLD';
        frequencies = { primary: 60, secondary: 40, secondaryLabel: action === 'CALL' ? 'Fold' : 'Call' };
      } else if (
        spr <= agg.raiseSprCap &&
        effectiveEquityPct >= raiseEquityThresholdPct &&
        input.villainAction !== 'facing_shove'
      ) {
        action = 'RAISE / SHOVE';
        betPct = Math.round(spr * 100);
        frequencies = { primary: 75, secondary: 25, secondaryLabel: 'Call' };
      } else {
        action = 'CALL';
        frequencies = { primary: 90, secondary: 10, secondaryLabel: 'Raise' };
      }
    } else if (input.handCategory === 'combo_draw' || input.handCategory === 'nut_draw') {
      if (
        input.street !== 'river' &&
        spr <= agg.raiseSprCap &&
        effectiveEquityPct >= raiseEquityThresholdPct &&
        (input.bountyCoverBB > 0 || input.aggressionProfile === 'loose') &&
        input.villainAction !== 'facing_shove' &&
        input.villainAction !== 'facing_overbet'
      ) {
        action = 'RAISE / SHOVE';
        betPct = Math.round(spr * 100);
        frequencies = { primary: 70, secondary: 30, secondaryLabel: 'Call' };
      } else if (effectiveEquityPct >= requiredEquityPct + agg.callMarginOffset) {
        action = 'CALL';
        frequencies = { primary: 85, secondary: 15, secondaryLabel: 'Fold' };
      } else {
        action = 'FOLD';
        frequencies = { primary: 80, secondary: 20, secondaryLabel: 'Call Marginal' };
      }
    } else if (input.handCategory === 'medium_showdown') {
      const underbluffDanger =
        input.villainLine === 'passive_turned_aggressive' || input.villainAction === 'facing_overbet';
      const blocksBluffPenalty = input.blockerType === 'blocks_bluffs';
      if (
        input.villainAction === 'facing_small_bet' &&
        !underbluffDanger &&
        !blocksBluffPenalty &&
        effectiveEquityPct >= requiredEquityPct + agg.callMarginOffset
      ) {
        action = 'CALL';
        frequencies = { primary: 75, secondary: 25, secondaryLabel: 'Fold' };
      } else if (
        input.villainAction === 'facing_large_bet' &&
        !underbluffDanger &&
        !blocksBluffPenalty &&
        effectiveEquityPct >= requiredEquityPct + 6 + agg.callMarginOffset &&
        !isMultiWay
      ) {
        action = 'CALL';
        frequencies = { primary: 55, secondary: 45, secondaryLabel: 'Fold' };
      } else {
        action = 'FOLD';
        frequencies = { primary: 90, secondary: 10, secondaryLabel: 'Hero Call' };
      }
    } else {
      if (
        input.handCategory === 'weak_draw' &&
        input.villainAction === 'facing_small_bet' &&
        effectiveEquityPct >= requiredEquityPct + agg.callMarginOffset &&
        input.street === 'flop' &&
        !isMultiWay
      ) {
        action = 'CALL';
        frequencies = { primary: 60, secondary: 40, secondaryLabel: 'Fold' };
      } else if (
        input.blockerType === 'blocks_nuts_value' &&
        input.villainAction === 'facing_small_bet' &&
        hudExploitActive &&
        input.hudFoldToCbet >= agg.hudRaiseFoldPct &&
        !isMultiWay
      ) {
        action = 'RAISE / SHOVE';
        betPct = 85;
        frequencies = { primary: 55, secondary: 45, secondaryLabel: 'Fold' };
      } else {
        action = 'FOLD';
        frequencies = { primary: 95, secondary: 5, secondaryLabel: 'Call' };
      }
    }
  }

  // Pot Commit verification (SPR < 1.5): prioritize direct All-In over fractional bets
  if (
    potCommitted &&
    (action === 'BET / VALUE' ||
      action === 'DONK BET' ||
      action === 'C-BET BLEFE' ||
      action === 'RAISE / SHOVE')
  ) {
    action = 'RAISE / SHOVE';
    betPct = Math.max(20, Math.round(spr * 100));
  }

  const rngExecutedLine = !input.useMixedRng
    ? `100% Linha Primária (${action})`
    : input.rngRoll < frequencies.primary
    ? `Roll ${input.rngRoll} < ${frequencies.primary}% → Executa ${action}`
    : `Roll ${input.rngRoll} ≥ ${frequencies.primary}% → Mixa p/ ${frequencies.secondaryLabel}`;

  const isDirectAllIn = potCommitted && action === 'RAISE / SHOVE';
  const sizingBB = isDirectAllIn
    ? Number(safeStack.toFixed(1))
    : betPct > 0
    ? Number(Math.min(safeStack, (safePot * betPct) / 100).toFixed(1))
    : 0;
  const sizingLabel =
    action === 'CHECK' || action === 'CALL' || action === 'FOLD'
      ? action === 'CALL' && facingBetBB > 0
        ? `Pagar ${facingBetBB.toFixed(1)} BB`
        : 'Sem aposta'
      : sizingBB >= safeStack && safeStack > 0
      ? `ALL-IN (${safeStack.toFixed(1)} BB)`
      : `${betPct}% do Pote (${sizingBB} BB)`;

  const streetNames =
    input.street === 'flop' ? ['Flop', 'Turn', 'River'] : input.street === 'turn' ? ['Turn', 'River'] : ['River'];
  let simPot = safePot;
  let simStack = safeStack;
  const streetPlan = streetNames.map((st, idx) => {
    const betAmount =
      potCommitted && idx === 0
        ? Number(simStack.toFixed(1))
        : Math.min(simStack, Number(((simPot * geometricPotPct) / 100).toFixed(1)));
    const effectivePct =
      potCommitted && idx === 0 && simPot > 0
        ? Math.round((betAmount / simPot) * 100)
        : geometricPotPct;
    const row = {
      street: st,
      potBefore: Number(simPot.toFixed(1)),
      betPct: betAmount > 0 ? effectivePct : 0,
      betBB: betAmount,
    };
    simPot += betAmount * 2;
    simStack = Math.max(0, simStack - betAmount);
    return row;
  });

  return {
    action,
    sizingLabel,
    sizingBB,
    geometricPotPct,
    spr,
    sprZone,
    potCommitted,
    eqrFactor,
    rawEquityPct,
    outsEquityPct,
    effectiveEquityPct,
    requiredEquityPct,
    mdfPct,
    poolAdjustedMdfPct,
    rangeAdvantage,
    nutAdvantage,
    cbetEquityThresholdPct,
    raiseEquityThresholdPct,
    hudFoldThresholdPct,
    hudExploitActive,
    frequencies,
    rngExecutedLine,
    diagnostics,
    streetPlan,
  };
}

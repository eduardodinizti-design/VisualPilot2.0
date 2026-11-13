export type PreflopPosition = 'UTG' | 'MP' | 'CO' | 'BTN' | 'SB' | 'BB';
export type PreflopScenario = 'rfi' | 'vs_limpers' | 'vs_open' | 'vs_3bet' | 'vs_shove';
export type IcmStage = 'chip_ev' | 'near_bubble' | 'bubble' | 'final_table';
export type PreflopAggression = 'tight' | 'balanced' | 'loose';

export type MatrixCellAction = 'raise_value' | 'raise_bluff' | 'shove' | 'call' | 'fold';

export interface PreflopInput {
  heroHand: string;
  heroPosition: PreflopPosition;
  effectiveStackBB: number;
  scenario: PreflopScenario;
  limpersCount: 1 | 2 | 3;
  openerPosition: Exclude<PreflopPosition, 'BB'>;
  openSizeBB: number;
  icmStage: IcmStage;
  bountyCoverBB: number;
  aggressionProfile: PreflopAggression;
  hudSampleHands: number;
  hudFoldTo3Bet: number;
}

export interface PreflopDiagnostic {
  tag: string;
  status: 'positive' | 'warning' | 'neutral';
  message: string;
}

export interface PreflopDecision {
  action:
    | 'OPEN RAISE'
    | 'ISO-RAISE'
    | '3-BET VALOR'
    | '3-BET BLEFE'
    | '4-BET / SHOVE'
    | 'ALL-IN (PUSH)'
    | 'CALL'
    | 'CHECK / LIMP'
    | 'FOLD';
  matrixAction: MatrixCellAction;
  sizingLabel: string;
  sizingBB: number;
  stackMode: 'DEEP (≥ 40 BB)' | 'MID-STACK (20–39 BB)' | 'SHORT / RE-SHOVE (14–19 BB)' | 'PUSH / FOLD (< 14 BB)';
  bubbleFactor: number;
  pkoBountyBonusBB: number;
  handScore: number;
  handEquityVsRangePct: number;
  requiredEquityPct: number;
  hudExploitActive: boolean;
  rangeStats: {
    totalCombosPct: number;
    raiseOrPushPct: number;
    bluffPct: number;
    callPct: number;
    foldPct: number;
  };
  matrixActions: Record<string, MatrixCellAction>;
  diagnostics: PreflopDiagnostic[];
}

export const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const;

const RANK_INDEX: Record<string, number> = {
  A: 14,
  K: 13,
  Q: 12,
  J: 11,
  T: 10,
  '9': 9,
  '8': 8,
  '7': 7,
  '6': 6,
  '5': 5,
  '4': 4,
  '3': 3,
  '2': 2,
};

const CHEN_BASE: Record<number, number> = {
  14: 10,
  13: 8,
  12: 7,
  11: 6,
  10: 5,
  9: 4.5,
  8: 4,
  7: 3.5,
  6: 3,
  5: 2.5,
  4: 2,
  3: 1.5,
  2: 1,
};

const BUBBLE_FACTOR_BY_STAGE: Record<IcmStage, { factor: number; label: string }> = {
  chip_ev: { factor: 1.0, label: 'ChipEV (Início / Pós-Bolha)' },
  near_bubble: { factor: 1.25, label: 'Pré-Bolha (Pressão Moderada)' },
  bubble: { factor: 1.55, label: 'Bolha do ITM (Alto Risco ICM)' },
  final_table: { factor: 1.45, label: 'Mesa Final (Payjumps)' },
};

const POSITION_LOOSENESS_BONUS: Record<PreflopPosition, number> = {
  UTG: -9,
  MP: -4,
  CO: 3,
  BTN: 11,
  SB: 6,
  BB: 8,
};

const AGGRESSION_MODIFIER: Record<PreflopAggression, { thresholdShift: number; bluffBonus: number; label: string }> = {
  tight: { thresholdShift: 5, bluffBonus: -6, label: 'Tight (Conservador)' },
  balanced: { thresholdShift: 0, bluffBonus: 0, label: 'Balanced (GTO MTT)' },
  loose: { thresholdShift: -5, bluffBonus: 7, label: 'Loose (Exploit / Pressão)' },
};

export function getHandLabel(row: number, col: number): string {
  const r1 = RANKS[row];
  const r2 = RANKS[col];
  if (row === col) return `${r1}${r2}`;
  if (row < col) return `${r1}${r2}s`;
  return `${r2}${r1}o`;
}

export function getHandCombos(hand: string): number {
  if (hand.length === 2) return 6;
  return hand.endsWith('s') ? 4 : 12;
}

/**
 * Evaluates canonical hand strength (0-100) + suited/blocker playability traits
 */
export function evaluateCanonicalHand(hand: string): {
  score: number;
  pushFoldScore: number;
  isPair: boolean;
  isSuited: boolean;
  isConnected: boolean;
  hasAceOrKingBlocker: boolean;
  is3BetBluffCandidate: boolean;
  rawEquityVsTightRange: number;
} {
  const c1 = RANK_INDEX[hand[0]] ?? 10;
  const c2 = RANK_INDEX[hand[1]] ?? 10;
  const high = Math.max(c1, c2);
  const low = Math.min(c1, c2);
  const isPair = hand.length === 2 || c1 === c2;
  const isSuited = hand.endsWith('s');
  const gap = high - low;
  const isConnected = !isPair && gap <= 2;

  let chen = CHEN_BASE[high] ?? 1;
  if (isPair) {
    chen = Math.max(5, chen * 2);
  }
  if (isSuited) chen += 2;
  if (!isPair) {
    if (gap === 1) chen += 0.5;
    else if (gap === 2) chen -= 1;
    else if (gap === 3) chen -= 2;
    else if (gap === 4) chen -= 4;
    else if (gap >= 5) chen -= 5;

    if (high < 12 && gap <= 1) chen += 1;
  }

  // Normalize Chen (~ -1 to 20) into 0-100 MTT strategic scale
  let score = Math.round(Math.min(100, Math.max(8, ((chen + 1) / 21) * 100)));

  // Extra precision adjustments for poker realism
  if (hand === 'AA') score = 100;
  else if (hand === 'KK') score = 97;
  else if (hand === 'QQ') score = 93;
  else if (hand === 'AKs') score = 91;
  else if (hand === 'JJ') score = 88;
  else if (hand === 'AKo') score = 86;
  else if (hand === 'AQs') score = 84;
  else if (hand === 'TT') score = 82;
  else if (hand === 'AJs' || hand === 'KQs') score = 78;

  // High-card shove power for <15bb Nash Push/Fold (offsuit Ax/Kx out-perform low suited connectors all-in)
  let pushFoldScore = score;
  if (!isPair && high === 14) {
    pushFoldScore = Math.min(96, pushFoldScore + 9);
  } else if (!isPair && high === 13 && low >= 9) {
    pushFoldScore = Math.min(90, pushFoldScore + 5);
  } else if (isPair) {
    pushFoldScore = Math.min(100, pushFoldScore + 7);
  } else if (!isPair && high <= 9 && isSuited) {
    pushFoldScore = Math.max(12, pushFoldScore - 5);
  }

  const hasAceOrKingBlocker = high === 14 || high === 13;
  const is3BetBluffCandidate =
    !isPair &&
    isSuited &&
    ((high === 14 && low >= 2 && low <= 5) ||
      (high === 13 && low >= 5 && low <= 9) ||
      (high >= 7 && high <= 10 && gap === 1));

  // Approximate all-in equity against a ~15% tight opening/calling range
  const rawEquityVsTightRange = Number(
    Math.min(85, Math.max(24, 23 + pushFoldScore * 0.56)).toFixed(1)
  );

  return {
    score,
    pushFoldScore,
    isPair,
    isSuited,
    isConnected,
    hasAceOrKingBlocker,
    is3BetBluffCandidate,
    rawEquityVsTightRange,
  };
}

function classifyCellForScenario(hand: string, input: PreflopInput): MatrixCellAction {
  const h = evaluateCanonicalHand(hand);
  const stack = Math.max(1, input.effectiveStackBB);
  const icm = BUBBLE_FACTOR_BY_STAGE[input.icmStage].factor;
  const agg = AGGRESSION_MODIFIER[input.aggressionProfile];
  const posBonus = POSITION_LOOSENESS_BONUS[input.heroPosition];
  const hudExploitActive = input.hudSampleHands >= 30;
  const hud3BetBonus = hudExploitActive && input.hudFoldTo3Bet >= 62 ? 5 : 0;
  const pkoFactor = input.bountyCoverBB > 0 ? Math.min(10, input.bountyCoverBB * 0.55) : 0;

  // ICM penalty tightens calling & raises, except when covering short bounties or pushing with fold equity
  const icmCallPenalty = (icm - 1) * 18;
  const icmRaisePenalty = (icm - 1) * 8;

  // 1. RFI (Open / Push)
  if (input.scenario === 'rfi') {
    if (input.heroPosition === 'BB') {
      // BB is already last to act in RFI preview -> show walk/check
      return h.score >= 55 ? 'raise_value' : 'call';
    }
    if (stack < 14) {
      const pushThreshold =
        54 - posBonus * 1.15 - (14 - stack) * 1.1 + agg.thresholdShift + icmRaisePenalty * 0.7 - pkoFactor * 0.4;
      return h.pushFoldScore >= pushThreshold ? 'shove' : 'fold';
    }
    const openThreshold = 61 - posBonus * 1.2 + agg.thresholdShift + icmRaisePenalty;
    if (h.score >= openThreshold) return 'raise_value';
    if (
      h.is3BetBluffCandidate &&
      (input.heroPosition === 'CO' || input.heroPosition === 'BTN' || input.heroPosition === 'SB') &&
      h.score >= openThreshold - 8 + agg.bluffBonus * -0.5
    ) {
      return 'raise_bluff';
    }
    return 'fold';
  }

  // 2. Facing Limpers (Iso-Raise)
  if (input.scenario === 'vs_limpers') {
    const limperPenalty = (input.limpersCount - 1) * 4;
    if (stack < 15) {
      const shoveBar = 58 - posBonus * 0.8 + limperPenalty + agg.thresholdShift + icmRaisePenalty - pkoFactor * 0.5;
      return h.pushFoldScore >= shoveBar ? 'shove' : 'fold';
    }
    const isoBar = 63 - posBonus * 0.85 + limperPenalty + agg.thresholdShift + icmRaisePenalty;
    if (h.score >= isoBar) return 'raise_value';
    // Over-limp only with speculative pairs/suited connectors in late position or SB/BB
    if (
      (h.isPair || (h.isSuited && h.isConnected)) &&
      h.score >= 40 &&
      (input.heroPosition === 'BTN' || input.heroPosition === 'CO' || input.heroPosition === 'SB')
    ) {
      return 'call';
    }
    return 'fold';
  }

  // 3. Facing Open Raise
  if (input.scenario === 'vs_open') {
    const openerTightness: Record<Exclude<PreflopPosition, 'BB'>, number> = {
      UTG: 9,
      MP: 5,
      CO: 1,
      BTN: -4,
      SB: -5,
    };
    const openerAdj = openerTightness[input.openerPosition];

    // Re-shove zone (14–22 BB)
    if (stack <= 22) {
      const reshoveBar = 69 + openerAdj * 0.8 - posBonus * 0.35 + agg.thresholdShift + icmRaisePenalty - pkoFactor * 0.6;
      if (h.pushFoldScore >= reshoveBar) return 'shove';
      const flatBar = 62 + openerAdj * 0.6 + icmCallPenalty * 0.4 - (input.heroPosition === 'BB' ? 12 : 0);
      if (h.score >= flatBar && stack >= 14) return 'call';
      return 'fold';
    }

    const threeBetValueBar = 77 + openerAdj * 0.7 + agg.thresholdShift + icmRaisePenalty * 0.8;
    if (h.score >= threeBetValueBar) return 'raise_value';

    const threeBetBluffBar = 46 + openerAdj * 0.6 - hud3BetBonus - agg.bluffBonus + icmRaisePenalty;
    if (h.is3BetBluffCandidate && h.score >= threeBetBluffBar) {
      return 'raise_bluff';
    }

    const bbDiscount = input.heroPosition === 'BB' ? 14 : input.heroPosition === 'BTN' ? 5 : 0;
    const callBar = 64 + openerAdj * 0.8 - bbDiscount + agg.thresholdShift * 0.5 + icmCallPenalty * 0.5 - pkoFactor * 0.35;
    if (h.score >= callBar || (h.isPair && stack >= 35 && h.score >= 44 && input.heroPosition !== 'SB')) {
      return 'call';
    }
    return 'fold';
  }

  // 4. Facing 3-Bet
  if (input.scenario === 'vs_3bet') {
    if (stack <= 26) {
      const fourBetShoveBar = 78 + agg.thresholdShift + icmRaisePenalty - pkoFactor * 0.5;
      if (h.pushFoldScore >= fourBetShoveBar) return 'shove';
      if (h.score >= 70 + icmCallPenalty * 0.4) return 'call';
      return 'fold';
    }
    if (h.score >= 87 + agg.thresholdShift * 0.5) return 'raise_value';
    if (h.is3BetBluffCandidate && h.hasAceOrKingBlocker && h.score >= 54 - hud3BetBonus - agg.bluffBonus && input.icmStage === 'chip_ev') {
      return 'raise_bluff';
    }
    const call3BetBar = 71 + agg.thresholdShift * 0.5 + icmCallPenalty * 0.45 - (input.heroPosition === 'BTN' || input.heroPosition === 'CO' ? 4 : 0);
    if (h.score >= call3BetBar) return 'call';
    return 'fold';
  }

  // 5. Facing All-In Shove
  const callShoveBar =
    72 +
    (stack > 20 ? (stack - 20) * 0.3 : -(20 - stack) * 0.7) +
    icmCallPenalty * 0.85 -
    pkoFactor * 1.15 +
    agg.thresholdShift * 0.6;
  return h.pushFoldScore >= callShoveBar ? 'call' : 'fold';
}

export function evaluatePreflopSpot(input: PreflopInput): PreflopDecision {
  const stack = Math.max(1, input.effectiveStackBB);
  const stackMode: PreflopDecision['stackMode'] =
    stack >= 40
      ? 'DEEP (≥ 40 BB)'
      : stack >= 20
      ? 'MID-STACK (20–39 BB)'
      : stack >= 14
      ? 'SHORT / RE-SHOVE (14–19 BB)'
      : 'PUSH / FOLD (< 14 BB)';

  const icmInfo = BUBBLE_FACTOR_BY_STAGE[input.icmStage];
  const bubbleFactor = icmInfo.factor;
  const pkoBountyBonusBB = input.bountyCoverBB > 0 ? Number((input.bountyCoverBB * 0.45).toFixed(1)) : 0;
  const hudExploitActive = input.hudSampleHands >= 30;

  // Build full 169-hand matrix for the selected spot
  const matrixActions: Record<string, MatrixCellAction> = {};
  let raiseOrPushCombos = 0;
  let bluffCombos = 0;
  let callCombos = 0;
  let foldCombos = 0;
  const totalPossibleCombos = 1326;

  for (let r = 0; r < RANKS.length; r++) {
    for (let c = 0; c < RANKS.length; c++) {
      const hand = getHandLabel(r, c);
      const cellAction = classifyCellForScenario(hand, input);
      matrixActions[hand] = cellAction;
      const combos = getHandCombos(hand);
      if (cellAction === 'raise_value' || cellAction === 'shove') raiseOrPushCombos += combos;
      else if (cellAction === 'raise_bluff') bluffCombos += combos;
      else if (cellAction === 'call') callCombos += combos;
      else foldCombos += combos;
    }
  }

  const normalizedHand = input.heroHand in matrixActions ? input.heroHand : 'AKs';
  const matrixAction = matrixActions[normalizedHand];
  const handEval = evaluateCanonicalHand(normalizedHand);

  // Determine exact action & sizing
  let action: PreflopDecision['action'] = 'FOLD';
  let sizingBB = 0;
  let sizingLabel = 'Sem aposta';

  if (matrixAction === 'shove') {
    action = input.scenario === 'vs_3bet' ? '4-BET / SHOVE' : 'ALL-IN (PUSH)';
    sizingBB = stack;
    sizingLabel = `ALL-IN (${stack.toFixed(1)} BB)`;
  } else if (matrixAction === 'raise_value') {
    if (input.scenario === 'rfi') {
      if (input.heroPosition === 'BB') {
        action = 'CHECK / LIMP';
        sizingBB = 0;
        sizingLabel = 'Walk / Check BB';
      } else {
        action = 'OPEN RAISE';
        sizingBB = input.heroPosition === 'SB' ? 3.0 : stack >= 40 ? 2.3 : 2.1;
        sizingLabel = `${sizingBB.toFixed(1)} BB`;
      }
    } else if (input.scenario === 'vs_limpers') {
      action = 'ISO-RAISE';
      const oopPenalty = input.heroPosition === 'SB' || input.heroPosition === 'BB' ? 0.5 : 0;
      sizingBB = Number((3.5 + input.limpersCount * 1.0 + oopPenalty).toFixed(1));
      sizingLabel = `${sizingBB.toFixed(1)} BB (3.5x + ${input.limpersCount} limper${input.limpersCount > 1 ? 's' : ''})`;
    } else if (input.scenario === 'vs_open') {
      action = '3-BET VALOR';
      const mult = input.heroPosition === 'SB' || input.heroPosition === 'BB' ? 4.0 : 3.0;
      sizingBB = Number(Math.min(stack, input.openSizeBB * mult).toFixed(1));
      sizingLabel = sizingBB >= stack * 0.45 ? `ALL-IN (${stack.toFixed(1)} BB)` : `${sizingBB.toFixed(1)} BB (${mult}x)`;
    } else if (input.scenario === 'vs_3bet') {
      action = '4-BET / SHOVE';
      sizingBB = stack <= 35 ? stack : Number((input.openSizeBB * 7.2).toFixed(1));
      sizingLabel = sizingBB >= stack * 0.5 ? `ALL-IN (${stack.toFixed(1)} BB)` : `${sizingBB.toFixed(1)} BB`;
    } else {
      action = 'CALL';
      sizingBB = stack;
      sizingLabel = `Pagar All-In (${stack.toFixed(1)} BB)`;
    }
  } else if (matrixAction === 'raise_bluff') {
    if (input.scenario === 'rfi') {
      action = 'OPEN RAISE';
      sizingBB = input.heroPosition === 'SB' ? 2.8 : 2.2;
      sizingLabel = `${sizingBB.toFixed(1)} BB (Steal)`;
    } else if (input.scenario === 'vs_3bet') {
      action = '4-BET / SHOVE';
      sizingBB = Number(Math.min(stack, input.openSizeBB * 7.0).toFixed(1));
      sizingLabel = `${sizingBB.toFixed(1)} BB (4-Bet Blocker)`;
    } else {
      action = '3-BET BLEFE';
      const mult = input.heroPosition === 'SB' || input.heroPosition === 'BB' ? 4.0 : 3.0;
      sizingBB = Number(Math.min(stack, input.openSizeBB * mult).toFixed(1));
      sizingLabel = `${sizingBB.toFixed(1)} BB (Light Polarizado)`;
    }
  } else if (matrixAction === 'call') {
    if (input.scenario === 'vs_limpers') {
      action = 'CHECK / LIMP';
      sizingBB = input.heroPosition === 'BB' ? 0 : 1.0;
      sizingLabel = input.heroPosition === 'BB' ? 'Check BB' : 'Over-Limp 1.0 BB';
    } else if (input.scenario === 'vs_shove') {
      action = 'CALL';
      sizingBB = stack;
      sizingLabel = `Pagar All-In (${stack.toFixed(1)} BB)`;
    } else if (input.scenario === 'vs_3bet') {
      action = 'CALL';
      sizingBB = Number((input.openSizeBB * 2.2).toFixed(1));
      sizingLabel = `Pagar 3-Bet (~${sizingBB.toFixed(1)} BB)`;
    } else {
      action = 'CALL';
      sizingBB = input.heroPosition === 'BB' ? Math.max(0, input.openSizeBB - 1) : input.openSizeBB;
      sizingLabel = `Pagar ${sizingBB.toFixed(1)} BB`;
    }
  }

  // Pot odds + ICM Bubble Factor + PKO required equity calculation
  let requiredEquityPct = 0;
  if (input.scenario === 'vs_shove') {
    const potBeforeCall = 1.5 + stack + pkoBountyBonusBB;
    const rawPotOdds = stack / (potBeforeCall + stack);
    const icmAdjusted = (rawPotOdds * bubbleFactor) / (1 + rawPotOdds * (bubbleFactor - 1));
    requiredEquityPct = Math.round(Math.min(82, Math.max(18, icmAdjusted * 100)));
  } else if (input.scenario === 'vs_open') {
    const toCall = input.heroPosition === 'BB' ? Math.max(0.5, input.openSizeBB - 1) : input.openSizeBB;
    const totalPot = input.openSizeBB + 1.5 + toCall + pkoBountyBonusBB * 0.35;
    requiredEquityPct = Math.round(Math.min(60, Math.max(15, (toCall / totalPot) * 100 * (1 + (bubbleFactor - 1) * 0.35))));
  } else if (input.scenario === 'vs_3bet') {
    const threeBetSize = input.openSizeBB * 3.1;
    const toCall = Math.max(1, threeBetSize - input.openSizeBB);
    const totalPot = threeBetSize + input.openSizeBB + 1.5;
    requiredEquityPct = Math.round(Math.min(65, Math.max(20, (toCall / totalPot) * 100 * (1 + (bubbleFactor - 1) * 0.4))));
  }

  const diagnostics: PreflopDiagnostic[] = [
    {
      tag: 'Stack Depth',
      status: stack < 14 ? 'warning' : 'positive',
      message:
        stack < 14
          ? `Stack efetivo de ${stack} BB entra na zona Push/Fold (Nash): elimina flats fracos e maximiza fold equity.`
          : stack < 20
          ? `Zona Re-Shove (${stack} BB): priorize 3-Bet All-In com pares médios e Ax bloqueadores contra opens tardios.`
          : `Stack de ${stack} BB (${stackMode}) permite jogo pós-flop com suited connectors e set-mining controlado.`,
    },
    {
      tag: 'ICM & Bubble Factor',
      status: bubbleFactor > 1.2 ? 'warning' : 'neutral',
      message: `${icmInfo.label} aplica Bubble Factor ${bubbleFactor.toFixed(2)}x, exigindo margem extra para pagar shoves e aumentando pressão sobre stacks médios.`,
    },
  ];

  if (input.bountyCoverBB > 0) {
    diagnostics.push({
      tag: 'PKO Bounty Power',
      status: 'positive',
      message: `Hero cobre bounty equivalente a ${input.bountyCoverBB} BB (+${pkoBountyBonusBB} BB reais no pote), alargando calls de shove e iso-raises.`,
    });
  }

  if (input.scenario === 'vs_limpers') {
    diagnostics.push({
      tag: 'Exploit Limpers',
      status: 'positive',
      message: `Contra ${input.limpersCount} limper(s) na Evolution, o Iso-Raise padronizado em 3.5x + 1x/limper pune ranges capados em posição.`,
    });
  }

  if (input.hudSampleHands > 0) {
    diagnostics.push({
      tag: 'HUD Gate',
      status: hudExploitActive ? 'positive' : 'warning',
      message: hudExploitActive
        ? `Amostra válida (${input.hudSampleHands} mãos ≥ 30): Fold to 3-Bet de ${input.hudFoldTo3Bet}% ${input.hudFoldTo3Bet >= 62 ? 'libera 3-bet light com blockers Ax/Kx.' : 'restringe blefes pré-flop.'}`
        : `Amostra insuficiente (${input.hudSampleHands} mãos < 30): exploits de 3-bet light bloqueados pelo Sample Size Gate.`,
    });
  }

  const raiseOrPushPct = Number((((raiseOrPushCombos + bluffCombos) / totalPossibleCombos) * 100).toFixed(1));

  return {
    action,
    matrixAction,
    sizingLabel,
    sizingBB,
    stackMode,
    bubbleFactor,
    pkoBountyBonusBB,
    handScore: handEval.score,
    handEquityVsRangePct: handEval.rawEquityVsTightRange,
    requiredEquityPct,
    hudExploitActive,
    rangeStats: {
      totalCombosPct: Number((((raiseOrPushCombos + bluffCombos + callCombos) / totalPossibleCombos) * 100).toFixed(1)),
      raiseOrPushPct,
      bluffPct: Number(((bluffCombos / totalPossibleCombos) * 100).toFixed(1)),
      callPct: Number(((callCombos / totalPossibleCombos) * 100).toFixed(1)),
      foldPct: Number(((foldCombos / totalPossibleCombos) * 100).toFixed(1)),
    },
    matrixActions,
    diagnostics,
  };
}

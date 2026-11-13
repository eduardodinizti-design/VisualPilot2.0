export interface ParsedPlayer {
  seat: number;
  name: string;
  initialStack: number;
  bounty?: string;
  isHero: boolean;
}

export interface PlayerStepState {
  stack: number;
  streetBet: number;
  lastAction: string;
  folded: boolean;
  allIn: boolean;
  shownCards?: string[];
}

export interface ReplayerStep {
  index: number;
  street: 'Preflop' | 'Flop' | 'Turn' | 'River' | 'Showdown';
  actor: string;
  description: string;
  pot: number;
  visibleBoard: string[];
  playerStates: Record<string, PlayerStepState>;
}

export interface ParsedHand {
  id: string;
  rawHeader: string;
  tableName: string;
  blindsLabel: string;
  buttonSeat: number | null;
  heroName: string;
  heroCards: string[];
  players: ParsedPlayer[];
  board: {
    flop: string[];
    turn: string | null;
    river: string | null;
  };
  hasPostflop: boolean;
  steps: ReplayerStep[];
  resultSummary: string;
}

function parseCardsBracket(str: string): string[] {
  const matches = str.match(/\[([^\]]+)\]/g);
  if (!matches) return [];
  const cards: string[] = [];
  for (const m of matches) {
    const inner = m.slice(1, -1).trim();
    const parts = inner.split(/\s+/).filter((c) => /^[2-9TJQKA][shdc]$/i.test(c));
    for (const p of parts) {
      cards.push(p[0].toUpperCase() + p[1].toLowerCase());
    }
  }
  return cards;
}

function parseAmount(str: string): number {
  const cleaned = str.replace(/,/g, '').replace(/[^\d.]/g, '');
  const val = parseFloat(cleaned);
  return Number.isFinite(val) ? val : 0;
}

function cloneStates(states: Record<string, PlayerStepState>): Record<string, PlayerStepState> {
  const copy: Record<string, PlayerStepState> = {};
  for (const [k, v] of Object.entries(states)) {
    copy[k] = { ...v, shownCards: v.shownCards ? [...v.shownCards] : undefined };
  }
  return copy;
}

function resetStreetBets(states: Record<string, PlayerStepState>) {
  for (const state of Object.values(states)) {
    state.streetBet = 0;
    if (!state.folded && !state.allIn) {
      state.lastAction = '';
    }
  }
}

export function parseHandHistories(rawText: string, preferredHeroName?: string): ParsedHand[] {
  const trimmed = rawText.trim();
  if (!trimmed) return [];

  // Split by common PPPoker / PokerStars hand header markers
  const blocks = trimmed
    .split(/(?=(?:PPPoker Hand #|Hand #|Mão #|PokerStars Hand #|Game #))/i)
    .map((b) => b.trim())
    .filter((b) => b.length > 20);

  const parsedHands: ParsedHand[] = [];

  for (let idx = 0; idx < blocks.length; idx++) {
    const block = blocks[idx];
    const lines = block.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (lines.length < 3) continue;

    const headerLine = lines[0];
    const idMatch = headerLine.match(/#(\d+)/);
    const id = idMatch ? `#${idMatch[1]}` : `#${idx + 1}`;
    const blindsMatch = headerLine.match(/\(([^)]+)\)/);
    const blindsLabel = blindsMatch ? blindsMatch[1] : 'Torneio / Cash';

    let tableName = 'Mesa PPPoker';
    let buttonSeat: number | null = null;
    const players: ParsedPlayer[] = [];
    let detectedHero = preferredHeroName?.trim() || '';
    let heroCards: string[] = [];

    const flop: string[] = [];
    let turn: string | null = null;
    let river: string | null = null;

    // First pass: extract seats, table, hero cards
    for (const line of lines) {
      const tableMatch = line.match(/Table\s+'([^']+)'/i);
      if (tableMatch) tableName = tableMatch[1];

      const btnMatch = line.match(/Seat\s+#(\d+)\s+is\s+the\s+button/i);
      if (btnMatch) buttonSeat = parseInt(btnMatch[1], 10);

      const seatMatch = line.match(/^Seat\s+(\d+):\s+(.+?)\s+\(([^)]+)\)/i);
      if (seatMatch) {
        const seat = parseInt(seatMatch[1], 10);
        const name = seatMatch[2].trim();
        const parenContent = seatMatch[3];
        const stackMatch = parenContent.match(/([\d,.]+)\s+in\s+chips/i);
        const initialStack = stackMatch ? parseAmount(stackMatch[1]) : parseAmount(parenContent);
        const bountyMatch = parenContent.match(/Bounty\s+([^,)]+)/i);
        players.push({
          seat,
          name,
          initialStack,
          bounty: bountyMatch ? bountyMatch[1].trim() : undefined,
          isHero: false,
        });
      }

      const dealtMatch = line.match(/^Dealt\s+to\s+(.+?)\s+\[([^\]]+)\]/i);
      if (dealtMatch) {
        if (!preferredHeroName?.trim()) {
          detectedHero = dealtMatch[1].trim();
        }
        if (
          dealtMatch[1].trim().toLowerCase() === detectedHero.toLowerCase() ||
          !preferredHeroName?.trim()
        ) {
          detectedHero = dealtMatch[1].trim();
          heroCards = parseCardsBracket(`[${dealtMatch[2]}]`);
        }
      }
    }

    if (!detectedHero && players.length > 0) {
      const heroCandidate = players.find((p) => p.name.toLowerCase() === 'hero');
      detectedHero = heroCandidate ? heroCandidate.name : players[0].name;
    }

    for (const p of players) {
      p.isHero = p.name.toLowerCase() === detectedHero.toLowerCase();
    }

    // Initialize state machine for step-by-step replay
    const playerStates: Record<string, PlayerStepState> = {};
    for (const p of players) {
      playerStates[p.name] = {
        stack: p.initialStack,
        streetBet: 0,
        lastAction: '',
        folded: false,
        allIn: false,
      };
    }

    const steps: ReplayerStep[] = [];
    let currentStreet: ReplayerStep['street'] = 'Preflop';
    let pot = 0;
    let visibleBoard: string[] = [];
    const summaryParts: string[] = [];

    const pushStep = (actor: string, description: string) => {
      steps.push({
        index: steps.length,
        street: currentStreet,
        actor,
        description,
        pot: Number(pot.toFixed(2)),
        visibleBoard: [...visibleBoard],
        playerStates: cloneStates(playerStates),
      });
    };

    for (const line of lines) {
      if (line.startsWith('*** HOLE CARDS ***')) {
        currentStreet = 'Preflop';
        pushStep('Mesa', `Cartas distribuídas${heroCards.length === 2 ? ` · Hero [${heroCards.join(' ')}]` : ''}`);
        continue;
      }

      if (line.startsWith('*** FLOP ***')) {
        currentStreet = 'Flop';
        resetStreetBets(playerStates);
        const cards = parseCardsBracket(line);
        flop.splice(0, flop.length, ...cards.slice(0, 3));
        visibleBoard = [...flop];
        pushStep('Mesa', `Flop: ${flop.join(' ')}`);
        continue;
      }

      if (line.startsWith('*** TURN ***')) {
        currentStreet = 'Turn';
        resetStreetBets(playerStates);
        const cards = parseCardsBracket(line);
        if (cards.length > 0) {
          turn = cards[cards.length - 1];
          visibleBoard = [...flop, turn];
        }
        pushStep('Mesa', `Turn: ${turn ?? ''}`);
        continue;
      }

      if (line.startsWith('*** RIVER ***')) {
        currentStreet = 'River';
        resetStreetBets(playerStates);
        const cards = parseCardsBracket(line);
        if (cards.length > 0) {
          river = cards[cards.length - 1];
          visibleBoard = [...flop, ...(turn ? [turn] : []), river];
        }
        pushStep('Mesa', `River: ${river ?? ''}`);
        continue;
      }

      if (line.startsWith('*** SHOW DOWN ***') || line.startsWith('*** SUMMARY ***')) {
        currentStreet = 'Showdown';
        resetStreetBets(playerStates);
        pushStep('Mesa', 'Showdown');
        continue;
      }

      // Uncalled bet returned
      const uncalledMatch = line.match(/^Uncalled\s+bet\s+\(([\d,.]+)\)\s+returned\s+to\s+(.+)$/i);
      if (uncalledMatch) {
        const retAmt = parseAmount(uncalledMatch[1]);
        const actor = uncalledMatch[2].trim();
        pot = Math.max(0, pot - retAmt);
        if (playerStates[actor]) {
          playerStates[actor].stack = Number((playerStates[actor].stack + retAmt).toFixed(2));
          playerStates[actor].streetBet = Math.max(0, playerStates[actor].streetBet - retAmt);
        }
        pushStep(actor, `Devolução de aposta não paga (${retAmt.toLocaleString()})`);
        continue;
      }

      // Collected pot
      const collectedMatch = line.match(/^(.+?)\s+collected\s+([\d,.]+)\s+from\s+pot/i);
      if (collectedMatch) {
        const actor = collectedMatch[1].trim();
        const wonAmt = parseAmount(collectedMatch[2]);
        if (playerStates[actor]) {
          playerStates[actor].stack = Number((playerStates[actor].stack + wonAmt).toFixed(2));
          playerStates[actor].lastAction = `Venceu ${wonAmt.toLocaleString()}`;
        }
        summaryParts.push(`${actor} venceu ${wonAmt.toLocaleString()}`);
        pushStep(actor, `Coletou ${wonAmt.toLocaleString()} do pote`);
        continue;
      }

      // Player action lines: "Name: action ..."
      const actionLineMatch = line.match(/^(.+?):\s+(.+)$/);
      if (!actionLineMatch) continue;

      const actor = actionLineMatch[1].trim();
      const actionBody = actionLineMatch[2].trim();
      const state = playerStates[actor];
      if (!state) continue;

      if (/^posts\s+small\s+blind\s+/i.test(actionBody) || /^posts\s+big\s+blind\s+/i.test(actionBody) || /^posts\s+the\s+ante\s+/i.test(actionBody)) {
        const amt = parseAmount(actionBody);
        const paid = Math.min(state.stack, amt);
        state.stack = Number((state.stack - paid).toFixed(2));
        if (!/ante/i.test(actionBody)) {
          state.streetBet = Number((state.streetBet + paid).toFixed(2));
        }
        pot += paid;
        const label = /small/i.test(actionBody) ? `SB ${paid}` : /big/i.test(actionBody) ? `BB ${paid}` : `Ante ${paid}`;
        state.lastAction = label;
        continue;
      }

      if (/^folds/i.test(actionBody)) {
        state.folded = true;
        state.lastAction = 'Fold';
        pushStep(actor, 'Fold');
      } else if (/^checks/i.test(actionBody)) {
        state.lastAction = 'Check';
        pushStep(actor, 'Check');
      } else if (/^calls\s+/i.test(actionBody)) {
        const amt = parseAmount(actionBody);
        const paid = Math.min(state.stack, amt);
        state.stack = Number((state.stack - paid).toFixed(2));
        state.streetBet = Number((state.streetBet + paid).toFixed(2));
        pot += paid;
        const isAllIn = /all-in/i.test(actionBody) || state.stack === 0;
        if (isAllIn) state.allIn = true;
        state.lastAction = isAllIn ? `All-In Call ${paid}` : `Call ${paid}`;
        pushStep(actor, isAllIn ? `Call All-In (${paid.toLocaleString()})` : `Call ${paid.toLocaleString()}`);
      } else if (/^bets\s+/i.test(actionBody)) {
        const amt = parseAmount(actionBody);
        const paid = Math.min(state.stack, amt);
        state.stack = Number((state.stack - paid).toFixed(2));
        state.streetBet = Number((state.streetBet + paid).toFixed(2));
        pot += paid;
        const isAllIn = /all-in/i.test(actionBody) || state.stack === 0;
        if (isAllIn) state.allIn = true;
        state.lastAction = isAllIn ? `All-In ${paid}` : `Bet ${paid}`;
        pushStep(actor, isAllIn ? `All-In (${paid.toLocaleString()})` : `Aposta ${paid.toLocaleString()}`);
      } else if (/^raises\s+/i.test(actionBody)) {
        const toMatch = actionBody.match(/to\s+([\d,.]+)/i);
        const targetTotal = toMatch ? parseAmount(toMatch[1]) : parseAmount(actionBody);
        const additional = Math.max(0, targetTotal - state.streetBet);
        const paid = Math.min(state.stack, additional);
        state.stack = Number((state.stack - paid).toFixed(2));
        state.streetBet = Number((state.streetBet + paid).toFixed(2));
        pot += paid;
        const isAllIn = /all-in/i.test(actionBody) || state.stack === 0;
        if (isAllIn) state.allIn = true;
        state.lastAction = isAllIn ? `All-In ${state.streetBet}` : `Raise ${state.streetBet}`;
        pushStep(actor, isAllIn ? `Raise All-In para ${state.streetBet.toLocaleString()}` : `Raise para ${state.streetBet.toLocaleString()}`);
      } else if (/^shows\s+/i.test(actionBody)) {
        const shown = parseCardsBracket(actionBody);
        state.shownCards = shown;
        state.lastAction = `Show [${shown.join(' ')}]`;
        pushStep(actor, `Mostra ${shown.join(' ')}`);
      } else if (/^mucks/i.test(actionBody)) {
        state.lastAction = 'Muck';
        pushStep(actor, 'Muck');
      }
    }

    parsedHands.push({
      id,
      rawHeader: headerLine,
      tableName,
      blindsLabel,
      buttonSeat,
      heroName: detectedHero,
      heroCards,
      players,
      board: { flop, turn, river },
      hasPostflop: flop.length > 0,
      steps,
      resultSummary: summaryParts.join(' · ') || 'Mão concluída',
    });
  }

  return parsedHands;
}

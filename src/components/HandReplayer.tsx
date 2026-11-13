import React, { useEffect, useMemo, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Play,
  Pause,
  Eye,
  Palette,
  Disc,
} from 'lucide-react';
import { parseHandHistories, ParsedHand, ReplayerStep } from '../utils/handParser';

interface HandReplayerProps {
  handHistoryText: string;
  heroName?: string;
}

const SUIT_SYMBOLS: Record<string, string> = {
  s: '♠',
  h: '♥',
  d: '♦',
  c: '♣',
};

function PlayingCard({
  card,
  fourColor,
  size = 'md',
}: {
  card?: string | null;
  fourColor: boolean;
  size?: 'sm' | 'md' | 'lg';
}) {
  const dims =
    size === 'sm'
      ? 'w-7 h-10 text-xs rounded-md'
      : size === 'lg'
      ? 'w-12 h-16 text-base rounded-lg'
      : 'w-10 h-14 text-sm rounded-lg';

  if (!card || card.length < 2) {
    return (
      <div
        className={`${dims} bg-slate-900 border border-slate-700/80 flex items-center justify-center shadow-inner`}
        aria-label="Carta oculta"
      >
        <div className="w-3/5 h-3/5 rounded-sm border border-slate-700/60 bg-slate-800/70" />
      </div>
    );
  }

  const rank = card[0] === 'T' ? '10' : card[0];
  const suit = card[1].toLowerCase();
  const symbol = SUIT_SYMBOLS[suit] ?? suit;

  const colorClass = fourColor
    ? suit === 's'
      ? 'bg-slate-950 text-slate-100 border-slate-600'
      : suit === 'h'
      ? 'bg-rose-950 text-rose-300 border-rose-500/70'
      : suit === 'd'
      ? 'bg-sky-950 text-sky-300 border-sky-500/70'
      : 'bg-emerald-950 text-emerald-300 border-emerald-500/70'
    : suit === 'h' || suit === 'd'
    ? 'bg-white text-rose-600 border-slate-300'
    : 'bg-white text-slate-900 border-slate-300';

  return (
    <div
      className={`${dims} ${colorClass} border font-mono font-bold flex flex-col items-center justify-center leading-none shadow-md select-none tabular-nums`}
    >
      <span>{rank}</span>
      <span className="mt-0.5">{symbol}</span>
    </div>
  );
}

export default function HandReplayer({ handHistoryText, heroName }: HandReplayerProps) {
  const allHands = useMemo(
    () => parseHandHistories(handHistoryText, heroName),
    [handHistoryText, heroName]
  );

  const [onlyPostflop, setOnlyPostflop] = useState<boolean>(false);
  const [fourColorDeck, setFourColorDeck] = useState<boolean>(true);
  const [selectedHandIdx, setSelectedHandIdx] = useState<number>(0);
  const [stepIdx, setStepIdx] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  const hands: ParsedHand[] = useMemo(() => {
    if (!onlyPostflop) return allHands;
    const filtered = allHands.filter((h) => h.hasPostflop);
    return filtered.length > 0 ? filtered : allHands;
  }, [allHands, onlyPostflop]);

  const activeHand = hands[Math.min(selectedHandIdx, Math.max(0, hands.length - 1))] ?? null;

  useEffect(() => {
    setSelectedHandIdx(0);
    setStepIdx(0);
    setIsPlaying(false);
  }, [handHistoryText, onlyPostflop]);

  useEffect(() => {
    setStepIdx(0);
    setIsPlaying(false);
  }, [selectedHandIdx]);

  useEffect(() => {
    if (!isPlaying || !activeHand) return;
    if (stepIdx >= activeHand.steps.length - 1) {
      setIsPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setStepIdx((prev) => Math.min(activeHand.steps.length - 1, prev + 1));
    }, 950);
    return () => window.clearTimeout(timer);
  }, [isPlaying, stepIdx, activeHand]);

  if (!handHistoryText.trim() || hands.length === 0 || !activeHand) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 text-center space-y-2">
        <div className="flex items-center justify-center gap-2 text-sm font-semibold text-slate-300">
          <Eye className="w-4 h-4 text-indigo-400" />
          <span>Hand Replayer Visual</span>
        </div>
        <p className="text-xs text-slate-400">
          Importe um arquivo <code className="text-slate-300">.txt</code> do PPPoker ou clique em{' '}
          <strong className="text-slate-200">Carregar Exemplo PPPoker (.txt)</strong> acima para visualizar as cartas da mesa, do herói e cada ação street a street.
        </p>
      </div>
    );
  }

  const totalSteps = Math.max(1, activeHand.steps.length);
  const clampedStepIdx = Math.min(stepIdx, totalSteps - 1);
  const currentStep: ReplayerStep | undefined = activeHand.steps[clampedStepIdx];
  const visibleBoard = currentStep?.visibleBoard ?? [];

  const jumpToStreet = (targetStreet: ReplayerStep['street']) => {
    setIsPlaying(false);
    const idx = activeHand.steps.findIndex((s) => s.street === targetStreet);
    if (idx !== -1) setStepIdx(idx);
  };

  const streetAvailability = {
    Preflop: activeHand.steps.some((s) => s.street === 'Preflop'),
    Flop: activeHand.steps.some((s) => s.street === 'Flop'),
    Turn: activeHand.steps.some((s) => s.street === 'Turn'),
    River: activeHand.steps.some((s) => s.street === 'River'),
    Showdown: activeHand.steps.some((s) => s.street === 'Showdown'),
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5">
      {/* Top Bar: Hand Selector + Options */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Eye className="w-4 h-4 text-emerald-400" />
            <span>Hand Replayer Visual</span>
          </h3>
          <div className="text-xs text-slate-400 font-mono mt-0.5 flex flex-wrap items-center gap-2">
            <span>{activeHand.id}</span>
            <span aria-hidden="true">·</span>
            <span>{activeHand.tableName}</span>
            <span aria-hidden="true">·</span>
            <span>{activeHand.blindsLabel}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setOnlyPostflop((prev) => !prev)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition whitespace-nowrap ${
              onlyPostflop
                ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500'
                : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200'
            }`}
          >
            Só Pós-Flop ({allHands.filter((h) => h.hasPostflop).length})
          </button>

          <button
            type="button"
            onClick={() => setFourColorDeck((prev) => !prev)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 transition whitespace-nowrap"
          >
            <Palette className="w-3.5 h-3.5 text-amber-400" />
            <span>Baralho {fourColorDeck ? '4 Cores' : '2 Cores'}</span>
          </button>

          <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 rounded-lg p-1">
            <button
              type="button"
              disabled={selectedHandIdx === 0}
              onClick={() => setSelectedHandIdx((prev) => Math.max(0, prev - 1))}
              className="p-1 rounded hover:bg-slate-800 text-slate-300 disabled:opacity-35"
              title="Mão anterior"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <select
              value={selectedHandIdx}
              onChange={(e) => setSelectedHandIdx(Number(e.target.value))}
              className="bg-transparent text-xs font-mono text-white px-2 py-0.5 focus:outline-none tabular-nums"
            >
              {hands.map((h, i) => (
                <option key={`${h.id}-${i}`} value={i} className="bg-slate-900">
                  Mão {i + 1}/{hands.length} · {h.id} {h.heroCards.length === 2 ? `[${h.heroCards.join(' ')}]` : ''}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={selectedHandIdx >= hands.length - 1}
              onClick={() => setSelectedHandIdx((prev) => Math.min(hands.length - 1, prev + 1))}
              className="p-1 rounded hover:bg-slate-800 text-slate-300 disabled:opacity-35"
              title="Próxima mão"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Split: Poker Felt Table (Left 8 cols) + Action History Log (Right 4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* Table Area */}
        <div className="lg:col-span-8 flex flex-col justify-between space-y-4">
          {/* Felt Oval */}
          <div className="relative bg-gradient-to-b from-emerald-950/75 to-slate-950 border border-emerald-800/40 rounded-3xl p-5 sm:p-6 space-y-6">
            {/* Center Pot & Board */}
            <div className="flex flex-col items-center justify-center space-y-3 py-2">
              <div className="text-xs font-mono tabular-nums text-amber-300 bg-slate-950/90 border border-amber-500/30 px-4 py-1 rounded-lg">
                Pote Atual: {(currentStep?.pot ?? 0).toLocaleString()} · {currentStep?.street ?? 'Preflop'}
              </div>

              <div className="flex items-center justify-center gap-2 sm:gap-2.5 py-1">
                {[0, 1, 2, 3, 4].map((slotIdx) => (
                  <PlayingCard
                    key={slotIdx}
                    card={visibleBoard[slotIdx] ?? null}
                    fourColor={fourColorDeck}
                    size="lg"
                  />
                ))}
              </div>

              <div className="text-xs text-slate-300 font-mono text-center min-h-[18px]">
                {currentStep ? (
                  <span>
                    <strong className="text-white">{currentStep.actor}:</strong> {currentStep.description}
                  </span>
                ) : (
                  <span>Início da mão</span>
                )}
              </div>
            </div>

            {/* Players Around Table */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {activeHand.players.map((player) => {
                const state = currentStep?.playerStates[player.name];
                const isActor = currentStep?.actor === player.name;
                const isBtn = activeHand.buttonSeat === player.seat;
                const displayCards = player.isHero
                  ? activeHand.heroCards
                  : state?.shownCards && state.shownCards.length > 0
                  ? state.shownCards
                  : null;

                return (
                  <div
                    key={player.seat}
                    className={`rounded-xl p-3 border transition flex flex-col justify-between gap-2 ${
                      state?.folded
                        ? 'bg-slate-950/50 border-slate-800/60 opacity-50'
                        : isActor
                        ? 'bg-slate-900 border-indigo-400 ring-1 ring-indigo-500/40'
                        : player.isHero
                        ? 'bg-slate-900/90 border-emerald-500/50'
                        : 'bg-slate-950/85 border-slate-800'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-bold text-white truncate">
                            {player.name}
                          </span>
                          {player.isHero && (
                            <span className="text-[10px] font-mono text-emerald-400 shrink-0">(Hero)</span>
                          )}
                          {isBtn && (
                            <span
                              className="inline-flex items-center text-[10px] font-mono font-bold text-amber-300 shrink-0"
                              title="Dealer Button"
                            >
                              <Disc className="w-3 h-3 mr-0.5" />BTN
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] font-mono tabular-nums text-slate-400">
                          Stack: {(state?.stack ?? player.initialStack).toLocaleString()}
                          {player.bounty ? ` · ${player.bounty}` : ''}
                        </div>
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        {displayCards && displayCards.length >= 2 ? (
                          displayCards.map((c, idx) => (
                            <PlayingCard key={idx} card={c} fourColor={fourColorDeck} size="sm" />
                          ))
                        ) : !state?.folded ? (
                          <>
                            <PlayingCard card={null} fourColor={fourColorDeck} size="sm" />
                            <PlayingCard card={null} fourColor={fourColorDeck} size="sm" />
                          </>
                        ) : null}
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-[11px] font-mono border-t border-slate-800/70 pt-1.5 min-h-[22px]">
                      <span className={state?.folded ? 'text-slate-500' : isActor ? 'text-indigo-300 font-semibold' : 'text-slate-300'}>
                        {state?.lastAction || (state?.folded ? 'Fold' : 'Aguardando')}
                      </span>
                      {state && state.streetBet > 0 && (
                        <span className="text-amber-400 tabular-nums">
                          {state.streetBet.toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Playback & Street Scrubber Controls */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            {/* Step buttons */}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setIsPlaying(false);
                  setStepIdx(0);
                }}
                disabled={clampedStepIdx === 0}
                className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 disabled:opacity-35 transition"
                title="Início da mão"
              >
                <ChevronsLeft className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsPlaying(false);
                  setStepIdx((prev) => Math.max(0, prev - 1));
                }}
                disabled={clampedStepIdx === 0}
                className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 disabled:opacity-35 transition"
                title="Ação anterior"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  if (clampedStepIdx >= totalSteps - 1) setStepIdx(0);
                  setIsPlaying((prev) => !prev);
                }}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition whitespace-nowrap"
              >
                {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                <span>{isPlaying ? 'Pausar' : 'Play'}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsPlaying(false);
                  setStepIdx((prev) => Math.min(totalSteps - 1, prev + 1));
                }}
                disabled={clampedStepIdx >= totalSteps - 1}
                className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 disabled:opacity-35 transition"
                title="Próxima ação"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsPlaying(false);
                  setStepIdx(totalSteps - 1);
                }}
                disabled={clampedStepIdx >= totalSteps - 1}
                className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 disabled:opacity-35 transition"
                title="Fim da mão"
              >
                <ChevronsRight className="w-4 h-4" />
              </button>
            </div>

            {/* Street quick jump */}
            <div className="flex flex-wrap items-center gap-1">
              {(['Preflop', 'Flop', 'Turn', 'River', 'Showdown'] as ReplayerStep['street'][]).map((st) => {
                const available = streetAvailability[st];
                const isCurrentStreet = currentStep?.street === st;
                return (
                  <button
                    key={st}
                    type="button"
                    disabled={!available}
                    onClick={() => jumpToStreet(st)}
                    className={`px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-medium transition ${
                      isCurrentStreet
                        ? 'bg-emerald-600/25 text-emerald-300 border border-emerald-500/50'
                        : available
                        ? 'bg-slate-900 text-slate-300 hover:bg-slate-800 border border-slate-800'
                        : 'bg-slate-950 text-slate-600 border border-slate-900 cursor-not-allowed'
                    }`}
                  >
                    {st === 'Preflop' ? 'Pré-Flop' : st}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Step-by-Step Action Timeline */}
        <div className="lg:col-span-4 bg-slate-950 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-semibold text-slate-300">Linha do Tempo da Mão</span>
            <span className="text-[11px] font-mono text-slate-400 tabular-nums">
              Passo {clampedStepIdx + 1}/{totalSteps}
            </span>
          </div>

          <div className="flex-1 max-h-[340px] overflow-y-auto space-y-1.5 pr-1">
            {activeHand.steps.map((step, i) => {
              const active = i === clampedStepIdx;
              const isStreetMarker = step.actor === 'Mesa';
              return (
                <button
                  key={step.index}
                  type="button"
                  onClick={() => {
                    setIsPlaying(false);
                    setStepIdx(i);
                  }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-xs font-mono transition flex items-center justify-between gap-2 border ${
                    active
                      ? 'bg-indigo-600/20 border-indigo-500 text-white'
                      : isStreetMarker
                      ? 'bg-slate-900/90 border-slate-800 text-emerald-300 hover:bg-slate-800/80'
                      : 'bg-slate-900/40 border-transparent text-slate-300 hover:bg-slate-900'
                  }`}
                >
                  <div className="truncate">
                    <span className="text-slate-500 mr-1.5">[{step.street}]</span>
                    {!isStreetMarker && <strong className="text-slate-100">{step.actor}: </strong>}
                    <span>{step.description}</span>
                  </div>
                  <span className="text-[10px] text-amber-400 shrink-0 tabular-nums">
                    {step.pot.toLocaleString()}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="pt-2 border-t border-slate-800 text-[11px] font-mono text-slate-400">
            Resumo: <span className="text-slate-200">{activeHand.resultSummary}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

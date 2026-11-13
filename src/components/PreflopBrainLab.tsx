import React, { useMemo, useState } from 'react';
import {
  Grid3X3,
  ShieldCheck,
  Target,
  CheckCircle2,
  AlertTriangle,
  Info,
  Copy,
  Check,
  Gauge,
  Layers,
} from 'lucide-react';
import {
  evaluatePreflopSpot,
  getHandLabel,
  RANKS,
  PreflopInput,
  PreflopPosition,
  PreflopScenario,
  IcmStage,
  PreflopAggression,
  MatrixCellAction,
} from '../utils/preflopEngine';

const PREFLOP_PRESETS: { name: string; context: string; input: PreflopInput }[] = [
  {
    name: 'Push/Fold 11 BB no CO (Bolha ICM)',
    context: 'Short Stack · Nash + ICM',
    input: {
      heroHand: 'A9o',
      heroPosition: 'CO',
      effectiveStackBB: 11,
      scenario: 'rfi',
      limpersCount: 1,
      openerPosition: 'UTG',
      openSizeBB: 2.2,
      icmStage: 'bubble',
      bountyCoverBB: 0,
      aggressionProfile: 'balanced',
      hudSampleHands: 40,
      hudFoldTo3Bet: 55,
    },
  },
  {
    name: 'Iso-Raise vs 2 Limpers (Evolution)',
    context: '45 BB · Exploit Recreativo',
    input: {
      heroHand: 'KJs',
      heroPosition: 'BTN',
      effectiveStackBB: 45,
      scenario: 'vs_limpers',
      limpersCount: 2,
      openerPosition: 'UTG',
      openSizeBB: 2.2,
      icmStage: 'chip_ev',
      bountyCoverBB: 0,
      aggressionProfile: 'loose',
      hudSampleHands: 50,
      hudFoldTo3Bet: 60,
    },
  },
  {
    name: '3-Bet Light IP vs Open do CO',
    context: '40 BB · Blocker A5s + HUD',
    input: {
      heroHand: 'A5s',
      heroPosition: 'BTN',
      effectiveStackBB: 40,
      scenario: 'vs_open',
      limpersCount: 1,
      openerPosition: 'CO',
      openSizeBB: 2.3,
      icmStage: 'chip_ev',
      bountyCoverBB: 0,
      aggressionProfile: 'balanced',
      hudSampleHands: 54,
      hudFoldTo3Bet: 68,
    },
  },
  {
    name: 'Call All-In PKO Cobrindo Bounty',
    context: '16 BB · Bounty Cover 14 BB',
    input: {
      heroHand: 'KQs',
      heroPosition: 'BB',
      effectiveStackBB: 16,
      scenario: 'vs_shove',
      limpersCount: 1,
      openerPosition: 'SB',
      openSizeBB: 16,
      icmStage: 'chip_ev',
      bountyCoverBB: 14,
      aggressionProfile: 'balanced',
      hudSampleHands: 36,
      hudFoldTo3Bet: 50,
    },
  },
];

const CELL_STYLES: Record<MatrixCellAction, string> = {
  raise_value: 'bg-emerald-600/80 hover:bg-emerald-500 text-white border-emerald-400/40',
  raise_bluff: 'bg-indigo-600/80 hover:bg-indigo-500 text-white border-indigo-400/40',
  shove: 'bg-rose-600/85 hover:bg-rose-500 text-white border-rose-400/50',
  call: 'bg-amber-600/75 hover:bg-amber-500 text-white border-amber-400/40',
  fold: 'bg-slate-950/90 hover:bg-slate-800 text-slate-500 border-slate-800/80',
};

export default function PreflopBrainLab() {
  const [input, setInput] = useState<PreflopInput>(PREFLOP_PRESETS[2].input);
  const [copiedJson, setCopiedJson] = useState(false);

  const decision = useMemo(() => evaluatePreflopSpot(input), [input]);

  const updateField = <K extends keyof PreflopInput>(key: K, value: PreflopInput[K]) => {
    setInput((prev) => ({ ...prev, [key]: value }));
  };

  const actionColor =
    decision.matrixAction === 'raise_value'
      ? 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10'
      : decision.matrixAction === 'raise_bluff'
      ? 'text-indigo-400 border-indigo-500/40 bg-indigo-500/10'
      : decision.matrixAction === 'shove'
      ? 'text-rose-400 border-rose-500/40 bg-rose-500/10'
      : decision.matrixAction === 'call'
      ? 'text-amber-400 border-amber-500/40 bg-amber-500/10'
      : 'text-slate-300 border-slate-700 bg-slate-800/60';

  const handleCopySpec = () => {
    const payload = JSON.stringify({ input, decision }, null, 2);
    navigator.clipboard.writeText(payload);
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header & Presets */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Grid3X3 className="w-5 h-5 text-indigo-400" />
              <span>Motor & Matriz Estratégica Pré-Flop (MTT & PKO)</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Ranges dinâmicos de 169 mãos por profundidade de stack, posição, isolamento contra limpers, Bubble Factor ICM e Bounty Power PKO.
            </p>
          </div>
          <button
            type="button"
            onClick={handleCopySpec}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-200 border border-slate-700 transition whitespace-nowrap shrink-0 self-start md:self-auto"
          >
            {copiedJson ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copiedJson ? 'Range JSON Copiado' : 'Exportar Range JSON'}</span>
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
          {PREFLOP_PRESETS.map((preset) => (
            <button
              key={preset.name}
              type="button"
              onClick={() => setInput(preset.input)}
              className="text-left p-3.5 rounded-xl bg-slate-950 hover:bg-slate-800/80 border border-slate-800 hover:border-indigo-500/50 transition space-y-1"
            >
              <div className="text-[11px] font-mono text-indigo-400">{preset.context}</div>
              <div className="text-xs font-semibold text-white leading-snug">{preset.name}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Main Layout: Controls (Left 5 cols) + Matrix & Output (Right 7 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Preflop Parameters */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              <span>Parâmetros Pré-Flop</span>
            </h3>
            <span className="text-xs font-mono text-indigo-400 tabular-nums">
              Mão: {input.heroHand} · Score {decision.handScore}/100
            </span>
          </div>

          {/* Aggression Profile Selector */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-slate-300 flex items-center gap-1.5">
                <Gauge className="w-4 h-4 text-indigo-400" />
                Perfil de Agressividade
              </span>
              <span className="font-mono text-slate-400 tabular-nums">
                Range Jogável: {decision.rangeStats.totalCombosPct}%
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  { id: 'tight', label: 'Tight', sub: 'Mesa Agressiva' },
                  { id: 'balanced', label: 'Balanced', sub: 'GTO MTT' },
                  { id: 'loose', label: 'Loose', sub: 'Exploit Passivos' },
                ] as { id: PreflopAggression; label: string; sub: string }[]
              ).map((prof) => {
                const isActive = input.aggressionProfile === prof.id;
                return (
                  <button
                    key={prof.id}
                    type="button"
                    onClick={() => updateField('aggressionProfile', prof.id)}
                    className={`p-2 rounded-lg border text-center transition ${
                      isActive
                        ? prof.id === 'tight'
                          ? 'bg-amber-500/15 border-amber-500 text-amber-300'
                          : prof.id === 'loose'
                          ? 'bg-emerald-500/15 border-emerald-500 text-emerald-300'
                          : 'bg-indigo-600/20 border-indigo-500 text-indigo-300'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                    }`}
                  >
                    <div className="text-xs font-bold">{prof.label}</div>
                    <div className="text-[10px] opacity-80 truncate">{prof.sub}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Scenario & Hero Position & Stack */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-medium">Cenário da Mesa</label>
              <select
                value={input.scenario}
                onChange={(e) => updateField('scenario', e.target.value as PreflopScenario)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="rfi">RFI (Fold até o Hero)</option>
                <option value="vs_limpers">Contra Limpers (Iso-Raise)</option>
                <option value="vs_open">Enfrentando Open Raise</option>
                <option value="vs_3bet">Hero Abriu → Enfrenta 3-Bet</option>
                <option value="vs_shove">Enfrentando All-In (Shove)</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-medium">Posição do Hero</label>
              <select
                value={input.heroPosition}
                onChange={(e) => updateField('heroPosition', e.target.value as PreflopPosition)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="UTG">UTG (Early)</option>
                <option value="MP">MP (Middle)</option>
                <option value="CO">CO (Cutoff)</option>
                <option value="BTN">BTN (Button)</option>
                <option value="SB">SB (Small Blind)</option>
                <option value="BB">BB (Big Blind)</option>
              </select>
            </div>
          </div>

          {/* Contextual inputs based on scenario */}
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-medium">Stack Efet. (BB)</label>
              <input
                type="number"
                min={1}
                max={200}
                step={1}
                value={input.effectiveStackBB}
                onChange={(e) => updateField('effectiveStackBB', Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs font-mono tabular-nums text-white"
              />
            </div>

            {input.scenario === 'vs_limpers' ? (
              <div className="space-y-1">
                <label className="text-xs text-slate-400 font-medium">Qtd Limpers</label>
                <select
                  value={input.limpersCount}
                  onChange={(e) => updateField('limpersCount', Number(e.target.value) as 1 | 2 | 3)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
                >
                  <option value={1}>1 Limper</option>
                  <option value={2}>2 Limpers</option>
                  <option value={3}>3+ Limpers</option>
                </select>
              </div>
            ) : input.scenario === 'vs_open' || input.scenario === 'vs_shove' ? (
              <div className="space-y-1">
                <label className="text-xs text-slate-400 font-medium">Posição Vilão</label>
                <select
                  value={input.openerPosition}
                  onChange={(e) =>
                    updateField('openerPosition', e.target.value as Exclude<PreflopPosition, 'BB'>)
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
                >
                  <option value="UTG">UTG</option>
                  <option value="MP">MP</option>
                  <option value="CO">CO</option>
                  <option value="BTN">BTN</option>
                  <option value="SB">SB</option>
                </select>
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-xs text-slate-400 font-medium">Open Padrão (BB)</label>
                <input
                  type="number"
                  min={2}
                  max={6}
                  step={0.1}
                  value={input.openSizeBB}
                  onChange={(e) => updateField('openSizeBB', Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs font-mono tabular-nums text-white"
                />
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-medium">Bounty Cover (BB)</label>
              <input
                type="number"
                min={0}
                step={1}
                value={input.bountyCoverBB}
                onChange={(e) => updateField('bountyCoverBB', Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs font-mono tabular-nums text-white"
              />
            </div>
          </div>

          {/* ICM Stage */}
          <div className="space-y-1">
            <label className="text-xs text-slate-400 font-medium">Fase do Torneio (ICM / Bubble Factor)</label>
            <select
              value={input.icmStage}
              onChange={(e) => updateField('icmStage', e.target.value as IcmStage)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
            >
              <option value="chip_ev">ChipEV (Início / Pós-Bolha — BF 1.00x)</option>
              <option value="near_bubble">Pré-Bolha (BF 1.25x)</option>
              <option value="bubble">Bolha do ITM (BF 1.55x)</option>
              <option value="final_table">Mesa Final / Payjumps (BF 1.45x)</option>
            </select>
          </div>

          {/* HUD Sample Gate */}
          <div className="pt-3 border-t border-slate-800 space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-indigo-400" />
                HUD Sample Gate (Mín. 30 mãos)
              </span>
              <span className={`font-mono ${decision.hudExploitActive ? 'text-emerald-400' : 'text-amber-400'}`}>
                {decision.hudExploitActive ? 'Exploit Liberado' : 'Gate Bloqueado'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-[11px] text-slate-400">Amostra (Mãos)</label>
                <input
                  type="number"
                  min={0}
                  value={input.hudSampleHands}
                  onChange={(e) => updateField('hudSampleHands', Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono tabular-nums text-white"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] text-slate-400">Fold to 3-Bet (%)</label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={input.hudFoldTo3Bet}
                  onChange={(e) => updateField('hudFoldTo3Bet', Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono tabular-nums text-white"
                />
              </div>
            </div>
          </div>

          {/* Diagnostics */}
          <div className="pt-3 border-t border-slate-800 space-y-2.5">
            <h4 className="text-xs font-semibold text-slate-400">Auditoria de Regras Pré-Flop</h4>
            {decision.diagnostics.map((rule, idx) => (
              <div key={idx} className="flex items-start gap-2.5 text-xs text-slate-300">
                {rule.status === 'positive' ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : rule.status === 'warning' ? (
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                ) : (
                  <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                )}
                <p className="leading-relaxed">
                  <strong className="text-slate-100">{rule.tag}:</strong> {rule.message}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Primary Decision + Interactive 13x13 Range Matrix */}
        <div className="lg:col-span-7 space-y-6">
          {/* Decision Banner */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <div className="text-xs text-slate-400 font-medium flex items-center gap-1.5">
                  <Target className="w-4 h-4 text-emerald-400" />
                  <span>Decisão para {input.heroHand} em {input.heroPosition}</span>
                </div>
                <div className="flex flex-wrap items-center gap-3 mt-2">
                  <span className={`text-xl font-extrabold font-mono px-4 py-1.5 rounded-xl border ${actionColor}`}>
                    {decision.action}
                  </span>
                  <span className="text-sm font-mono text-slate-200 font-semibold tabular-nums">
                    {decision.sizingLabel}
                  </span>
                </div>
              </div>

              <div className="text-left sm:text-right space-y-0.5">
                <div className="text-[11px] text-slate-400">Zona de Stack</div>
                <div className="text-sm font-bold font-mono text-indigo-400">{decision.stackMode}</div>
                <div className="text-xs text-slate-400 font-mono tabular-nums">
                  Bubble Factor {decision.bubbleFactor.toFixed(2)}x
                </div>
              </div>
            </div>

            {/* Key Metrics Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-slate-400">Equity vs Range</div>
                <div className="text-base font-bold font-mono tabular-nums text-emerald-400 mt-0.5">
                  {decision.handEquityVsRangePct}%
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-slate-400">Equity Exigida (ICM/PKO)</div>
                <div className="text-base font-bold font-mono tabular-nums text-amber-400 mt-0.5">
                  {decision.requiredEquityPct > 0 ? `${decision.requiredEquityPct}%` : 'Iniciativa'}
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-slate-400">Raise / Push Range</div>
                <div className="text-base font-bold font-mono tabular-nums text-indigo-400 mt-0.5">
                  {decision.rangeStats.raiseOrPushPct}%
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-slate-400">Call / Defesa</div>
                <div className="text-base font-bold font-mono tabular-nums text-slate-200 mt-0.5">
                  {decision.rangeStats.callPct}%
                </div>
              </div>
            </div>
          </div>

          {/* 13x13 Hand Range Matrix */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-white">Matriz Interativa de Ranges (169 Mãos)</h3>
                <p className="text-xs text-slate-400">
                  Clique em qualquer mão na grade para inspecionar a decisão e o sizing exato
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono text-slate-300">
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-emerald-600"></span> Valor/Open
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-indigo-600"></span> 3B Light
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-rose-600"></span> All-In
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-amber-600"></span> Call
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-slate-950 border border-slate-700"></span> Fold
                </span>
              </div>
            </div>

            <div className="grid grid-cols-[repeat(13,minmax(0,1fr))] gap-1 select-none overflow-x-auto pb-1">
              {RANKS.map((_, rowIdx) =>
                RANKS.map((__, colIdx) => {
                  const hand = getHandLabel(rowIdx, colIdx);
                  const cellAct = decision.matrixActions[hand];
                  const isSelected = input.heroHand === hand;
                  return (
                    <button
                      key={hand}
                      type="button"
                      onClick={() => updateField('heroHand', hand)}
                      className={`h-8 min-w-[26px] rounded text-[10px] font-mono font-semibold border transition flex items-center justify-center tabular-nums ${
                        CELL_STYLES[cellAct]
                      } ${isSelected ? 'ring-2 ring-white ring-offset-1 ring-offset-slate-900 scale-105 z-10' : ''}`}
                      title={`${hand}: ${cellAct}`}
                    >
                      {hand}
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

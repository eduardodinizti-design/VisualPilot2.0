import React, { useMemo, useState } from 'react';
import {
  Brain,
  CheckCircle2,
  AlertTriangle,
  Info,
  Layers,
  Target,
  ShieldCheck,
  Zap,
  Copy,
  Check,
  Gauge,
  Shuffle,
} from 'lucide-react';
import {
  evaluatePostflopSpot,
  PostflopInput,
  Street,
  HeroPosition,
  BoardTexture,
  HandCategory,
  VillainAction,
  VillainLine,
  BlockerType,
  AggressionProfile,
  PreflopInitiative,
  TurnRiverCard,
} from '../utils/postflopEngine';

const PRESETS: { name: string; context: string; input: PostflopInput }[] = [
  {
    name: 'Board Seco A-K-4 IP (C-Bet)',
    context: 'Range Advantage · Hero PFR',
    input: {
      street: 'flop',
      potBB: 6.5,
      effectiveStackBB: 32,
      heroPosition: 'IP',
      playersInPot: 2,
      preflopInitiative: 'hero_pfr',
      boardTexture: 'dry_high',
      turnRiverCard: 'brick',
      handCategory: 'air',
      drawOuts: 0,
      villainAction: 'checked_to_hero',
      villainLine: 'capped_check_back',
      blockerType: 'blocks_nuts_value',
      aggressionProfile: 'loose',
      bountyCoverBB: 0,
      hudSampleHands: 48,
      hudFoldToCbet: 62,
      useMixedRng: false,
      rngRoll: 24,
    },
  },
  {
    name: 'BB Donk-Bet 7-6-5 Conectado',
    context: 'Nut Advantage · Vilão PFR',
    input: {
      street: 'flop',
      potBB: 5.5,
      effectiveStackBB: 35,
      heroPosition: 'OOP',
      playersInPot: 2,
      preflopInitiative: 'villain_pfr',
      boardTexture: 'wet_connected',
      turnRiverCard: 'brick',
      handCategory: 'combo_draw',
      drawOuts: 15,
      villainAction: 'checked_to_hero',
      villainLine: 'uncapped',
      blockerType: 'none',
      aggressionProfile: 'balanced',
      bountyCoverBB: 0,
      hudSampleHands: 34,
      hudFoldToCbet: 52,
      useMixedRng: true,
      rngRoll: 41,
    },
  },
  {
    name: 'River vs Overbet 135% (Scare Flush)',
    context: 'MDF & Pool Underbluff',
    input: {
      street: 'river',
      potBB: 24,
      effectiveStackBB: 36,
      heroPosition: 'IP',
      playersInPot: 2,
      preflopInitiative: 'hero_pfr',
      boardTexture: 'wet_connected',
      turnRiverCard: 'flush_completes',
      handCategory: 'strong_value',
      drawOuts: 0,
      villainAction: 'facing_overbet',
      villainLine: 'passive_turned_aggressive',
      blockerType: 'none',
      aggressionProfile: 'balanced',
      bountyCoverBB: 0,
      hudSampleHands: 42,
      hudFoldToCbet: 45,
      useMixedRng: false,
      rngRoll: 18,
    },
  },
  {
    name: 'PKO Pot Commit Combo Draw (15 Outs)',
    context: 'SPR 1.33 · Pot Commit All-In',
    input: {
      street: 'flop',
      potBB: 12,
      effectiveStackBB: 16,
      heroPosition: 'IP',
      playersInPot: 2,
      preflopInitiative: 'three_bet_pot',
      boardTexture: 'wet_connected',
      turnRiverCard: 'brick',
      handCategory: 'combo_draw',
      drawOuts: 15,
      villainAction: 'facing_small_bet',
      villainLine: 'uncapped',
      blockerType: 'none',
      aggressionProfile: 'balanced',
      bountyCoverBB: 12,
      hudSampleHands: 35,
      hudFoldToCbet: 50,
      useMixedRng: false,
      rngRoll: 12,
    },
  },
];

export default function PostflopBrainLab() {
  const [input, setInput] = useState<PostflopInput>(PRESETS[0].input);
  const [copiedJson, setCopiedJson] = useState(false);

  const decision = useMemo(() => evaluatePostflopSpot(input), [input]);

  const updateField = <K extends keyof PostflopInput>(key: K, value: PostflopInput[K]) => {
    setInput((prev) => ({ ...prev, [key]: value }));
  };

  const rollRandomSeed = () => {
    updateField('rngRoll', Math.floor(Math.random() * 100));
  };

  const actionColor =
    decision.action === 'RAISE / SHOVE' || decision.action === 'BET / VALUE' || decision.action === 'DONK BET'
      ? 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10'
      : decision.action === 'C-BET BLEFE'
      ? 'text-indigo-400 border-indigo-500/40 bg-indigo-500/10'
      : decision.action === 'CALL'
      ? 'text-amber-400 border-amber-500/40 bg-amber-500/10'
      : decision.action === 'FOLD'
      ? 'text-rose-400 border-rose-500/40 bg-rose-500/10'
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
              <Brain className="w-6 h-6 text-indigo-400" />
              <span>Simulador & Calibrador do Cérebro Pós-Flop (v2)</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Iniciativa Pré-Flop (Range/Nut Advantage), Scare Cards Turn/River, Overbets & MDF, Outs Reais, SPR Geométrico, EQR Multi-Way, PKO e Mixagem RNG.
            </p>
          </div>
          <button
            type="button"
            onClick={handleCopySpec}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-200 border border-slate-700 transition whitespace-nowrap shrink-0 self-start md:self-auto"
          >
            {copiedJson ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copiedJson ? 'JSON Copiado!' : 'Exportar Regra JSON'}</span>
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
          {PRESETS.map((preset) => (
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

      {/* Main Split: Parameters (Left) + Decision Output (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Controls */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5">
          <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-400" />
            <span>Parâmetros do Spot Pós-Flop</span>
          </h3>

          {/* Aggression Profile Selector */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Gauge className="w-4 h-4 text-indigo-400" />
                Perfil de Agressividade
              </span>
              <span className="text-[11px] font-mono text-indigo-400 tabular-nums">
                C-Bet ≥ {decision.cbetEquityThresholdPct}% · Raise ≥ {decision.raiseEquityThresholdPct}%
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  { id: 'tight', label: 'Tight', sub: 'vs. Calling/Maníaco' },
                  { id: 'balanced', label: 'Balanced', sub: 'GTO Padrão' },
                  { id: 'loose', label: 'Loose', sub: 'vs. Nit/Passivo' },
                ] as { id: AggressionProfile; label: string; sub: string }[]
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

          {/* Street, Position & Players */}
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Street</label>
              <select
                value={input.street}
                onChange={(e) => updateField('street', e.target.value as Street)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="flop">Flop</option>
                <option value="turn">Turn</option>
                <option value="river">River</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Posição</label>
              <select
                value={input.heroPosition}
                onChange={(e) => updateField('heroPosition', e.target.value as HeroPosition)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="IP">IP (Em Posição)</option>
                <option value="OOP">OOP (Fora)</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Jogadores</label>
              <select
                value={input.playersInPot}
                onChange={(e) => updateField('playersInPot', Number(e.target.value) as 2 | 3 | 4)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value={2}>2 (Heads-Up)</option>
                <option value={3}>3 (3-Way)</option>
                <option value={4}>4 (4-Way)</option>
              </select>
            </div>
          </div>

          {/* Preflop Initiative & Turn/River Scare Card */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Iniciativa Pré-Flop</label>
              <select
                value={input.preflopInitiative}
                onChange={(e) => updateField('preflopInitiative', e.target.value as PreflopInitiative)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="hero_pfr">Hero foi PFR (Agressor SRP)</option>
                <option value="villain_pfr">Vilão foi PFR (Hero Defendeu)</option>
                <option value="three_bet_pot">Pote 3-Bet (Range Polarizado)</option>
                <option value="limped_pot">Pote Limped (Multi-Limp)</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">
                Carta do Turn/River {input.street === 'flop' ? '(Inativo no Flop)' : ''}
              </label>
              <select
                value={input.turnRiverCard}
                disabled={input.street === 'flop'}
                onChange={(e) => updateField('turnRiverCard', e.target.value as TurnRiverCard)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white disabled:opacity-45"
              >
                <option value="brick">Brick (Carta Neutra)</option>
                <option value="overcard">Overcard ao Board</option>
                <option value="flush_completes">Completa Flush (3ª do naipe)</option>
                <option value="straight_completes">Completa Sequência</option>
                <option value="board_pairs">Board Dobra</option>
              </select>
            </div>
          </div>

          {/* Pot, Stack & PKO Bounty */}
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Pote (BB)</label>
              <input
                type="number"
                min={1}
                step={0.5}
                value={input.potBB}
                onChange={(e) => updateField('potBB', Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs font-mono tabular-nums text-white"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Stack Efet. (BB)</label>
              <input
                type="number"
                min={0}
                step={1}
                value={input.effectiveStackBB}
                onChange={(e) => updateField('effectiveStackBB', Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs font-mono tabular-nums text-white"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Bounty PKO (BB)</label>
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

          {/* Board Texture, Hand Category & Real Outs */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Textura do Board</label>
              <select
                value={input.boardTexture}
                onChange={(e) => updateField('boardTexture', e.target.value as BoardTexture)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="dry_high">Seco / Alto (A-K-4)</option>
                <option value="paired">Dobrado (Q-Q-5)</option>
                <option value="wet_connected">Conectado (8-7-5)</option>
                <option value="monotone">Monotone (3 naipe)</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Força da Mão</label>
              <select
                value={input.handCategory}
                onChange={(e) => updateField('handCategory', e.target.value as HandCategory)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="nut_value">Valor Nuts (Trinca+)</option>
                <option value="strong_value">Valor Forte (TPTK / OP)</option>
                <option value="medium_showdown">Showdown Médio (2º Par)</option>
                <option value="combo_draw">Combo Draw (FD + OESD)</option>
                <option value="nut_draw">Nut Draw (FD / OESD)</option>
                <option value="weak_draw">Draw Fraco (Gutshot)</option>
                <option value="air">Ar / Sem Par</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Outs Reais (0–20)</label>
              <input
                type="number"
                min={0}
                max={20}
                value={input.drawOuts}
                onChange={(e) => updateField('drawOuts', Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs font-mono tabular-nums text-white"
              />
            </div>
          </div>

          {/* Villain Action & Villain Line */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Situação / Ação do Vilão</label>
              <select
                value={input.villainAction}
                onChange={(e) => updateField('villainAction', e.target.value as VillainAction)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="checked_to_hero">Em Check até o Hero</option>
                <option value="facing_small_bet">Aposta Pequena (33%)</option>
                <option value="facing_large_bet">Aposta Grande (75%)</option>
                <option value="facing_overbet">Overbet Polarizado (135%)</option>
                <option value="facing_shove">All-In (Shove)</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-slate-400 font-medium">Funil de Range (Linha)</label>
              <select
                value={input.villainLine}
                onChange={(e) => updateField('villainLine', e.target.value as VillainLine)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
              >
                <option value="uncapped">Normal / Uncapped</option>
                <option value="capped_check_back">Capado (Check-Back Prévio)</option>
                <option value="passive_turned_aggressive">Passivo → Agressivo River</option>
              </select>
            </div>
          </div>

          {/* Blockers */}
          <div className="space-y-1">
            <label className="text-[11px] text-slate-400 font-medium">Efeito de Blockers (Card Removal)</label>
            <select
              value={input.blockerType}
              onChange={(e) => updateField('blockerType', e.target.value as BlockerType)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white"
            >
              <option value="none">Neutro (Sem bloqueio relevante)</option>
              <option value="blocks_nuts_value">Bloqueia Nuts / Calls Fortes (Bom p/ Blefar)</option>
              <option value="blocks_bluffs">Bloqueia Blefes do Vilão (Ruim p/ Hero Call)</option>
            </select>
          </div>

          {/* HUD Sample Size Gate & Mixed RNG */}
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
                <label className="text-[11px] text-slate-400">Fold to C-Bet (%)</label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={input.hudFoldToCbet}
                  onChange={(e) => updateField('hudFoldToCbet', Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono tabular-nums text-white"
                />
              </div>
            </div>

            {/* Mixed RNG Switch */}
            <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={input.useMixedRng}
                  onChange={(e) => updateField('useMixedRng', e.target.checked)}
                  className="accent-indigo-500 rounded"
                />
                <span>Mixagem Estocástica (RNG)</span>
              </label>

              {input.useMixedRng && (
                <button
                  type="button"
                  onClick={rollRandomSeed}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] font-mono text-indigo-300 border border-slate-700 transition"
                >
                  <Shuffle className="w-3 h-3" />
                  <span>Sortear Roll ({input.rngRoll})</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Right: Output & Diagnostics */}
        <div className="lg:col-span-7 space-y-6">
          {/* Primary Decision Banner */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <div className="text-xs text-slate-400 font-medium flex items-center gap-1.5">
                  <Target className="w-4 h-4 text-emerald-400" />
                  <span>Decisão Recomendada pelo Cérebro Pós-Flop</span>
                </div>
                <div className="flex flex-wrap items-center gap-3 mt-2">
                  <span className={`text-2xl font-extrabold font-mono px-4 py-1.5 rounded-xl border ${actionColor}`}>
                    {decision.action}
                  </span>
                  <span className="text-sm font-mono text-slate-200 font-semibold tabular-nums">
                    {decision.sizingLabel}
                  </span>
                </div>
                <div className="text-[11px] font-mono text-slate-400 mt-2">
                  Execução RNG: <span className="text-slate-200">{decision.rngExecutedLine}</span>
                </div>
              </div>

              <div className="bg-slate-950 px-4 py-3 rounded-xl border border-slate-800 text-left sm:text-right space-y-0.5">
                <div className="text-[11px] text-slate-400">SPR · Range / Nut Adv.</div>
                <div className="text-xl font-bold font-mono tabular-nums text-indigo-400">{decision.spr}</div>
                <div className="text-[11px] text-slate-300 font-mono">
                  Range: {decision.rangeAdvantage} · Nuts: {decision.nutAdvantage}
                </div>
                {decision.potCommitted && (
                  <div className="text-[11px] text-amber-400 font-mono font-semibold">
                    Pot Commit Ativo (SPR &lt; 1.5)
                  </div>
                )}
              </div>
            </div>

            {/* Key Metrics Row */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-[11px] text-slate-400">Equity Bruta</div>
                <div className="text-base font-bold font-mono tabular-nums text-slate-200 mt-0.5">
                  {decision.rawEquityPct}%
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-[11px] text-slate-400">Equity EQR</div>
                <div className="text-base font-bold font-mono tabular-nums text-emerald-400 mt-0.5">
                  {decision.effectiveEquityPct}%
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-[11px] text-slate-400">Outs Eq.</div>
                <div className="text-base font-bold font-mono tabular-nums text-indigo-400 mt-0.5">
                  {decision.outsEquityPct !== null ? `${decision.outsEquityPct}%` : '—'}
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-[11px] text-slate-400">Pot Odds Req.</div>
                <div className="text-base font-bold font-mono tabular-nums text-amber-400 mt-0.5">
                  {decision.requiredEquityPct > 0 ? `${decision.requiredEquityPct}%` : 'N/A'}
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-[11px] text-slate-400">MDF (Pool)</div>
                <div className="text-base font-bold font-mono tabular-nums text-rose-400 mt-0.5">
                  {decision.mdfPct > 0 ? `${decision.mdfPct}% (${decision.poolAdjustedMdfPct}%)` : 'N/A'}
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-[11px] text-slate-400">Geométrico</div>
                <div className="text-base font-bold font-mono tabular-nums text-indigo-400 mt-0.5">
                  {decision.geometricPotPct}%
                </div>
              </div>
            </div>

            {/* Frequency Split Bar */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-mono tabular-nums">
                <span className="text-emerald-400 font-semibold">
                  {decision.action}: {decision.frequencies.primary}%
                </span>
                <span className="text-slate-400">
                  {decision.frequencies.secondaryLabel}: {decision.frequencies.secondary}%
                </span>
              </div>
              <div className="h-2.5 w-full bg-slate-950 rounded-full overflow-hidden flex border border-slate-800">
                <div
                  className="bg-emerald-500 h-full transition-all duration-300"
                  style={{ width: `${decision.frequencies.primary}%` }}
                />
                <div
                  className="bg-slate-700 h-full transition-all duration-300"
                  style={{ width: `${decision.frequencies.secondary}%` }}
                />
              </div>
            </div>
          </div>

          {/* Geometric Street Plan */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
            <h4 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-400" />
              <span>Plano Geométrico por Street (Rumo ao All-In Limpo)</span>
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {decision.streetPlan.map((step, idx) => (
                <div key={step.street} className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-1">
                  <div className="text-xs font-bold text-indigo-400">{step.street}</div>
                  <div className="text-[11px] text-slate-400 font-mono tabular-nums">
                    Pote antes: {step.potBefore} BB
                  </div>
                  <div className="text-sm font-mono font-bold text-white tabular-nums">
                    {step.betBB === 0
                      ? 'Stack já em All-In'
                      : decision.potCommitted && idx === 0
                      ? `All-In Direto (${step.betBB} BB)`
                      : `Apostar ${step.betPct}% (${step.betBB} BB)`}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Rule Audit Diagnostics */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-3">
            <h4 className="text-sm font-semibold text-slate-300">Auditoria de Regras Aplicadas</h4>
            <div className="space-y-2.5">
              {decision.diagnostics.map((rule, idx) => (
                <div
                  key={idx}
                  className="bg-slate-950 border border-slate-800/90 p-3.5 rounded-xl flex items-start gap-3"
                >
                  {rule.status === 'positive' ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  ) : rule.status === 'warning' ? (
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  ) : (
                    <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                  )}
                  <div className="space-y-0.5">
                    <span className="text-[11px] font-mono text-slate-200 font-semibold">{rule.tag}</span>
                    <p className="text-xs text-slate-300 leading-relaxed">{rule.message}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import React, { useMemo, useRef, useState } from 'react';
import {
  FileSearch,
  Upload,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Trash2,
  Download,
  Loader2,
  Target,
  ShieldAlert,
  TrendingDown,
  Sliders
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell
} from 'recharts';
import type { AggressionProfile } from '../utils/postflopEngine';
import HandReplayer from './HandReplayer';

interface MistakeItem {
  category: string;
  occurrences: number;
  frequencyPct: number;
  severity: 'alta' | 'media' | 'baixa' | string;
  affectedStreet: 'Flop' | 'Turn' | 'River' | 'Multi-Street' | string;
  description: string;
  exampleSpot: string;
  recommendedFix: string;
}

interface HandAnalysisReport {
  totalHandsDetected: number;
  postflopHandsReviewed: number;
  totalMistakesFound: number;
  overallGrade: string;
  executiveSummary: string;
  recommendedProfile: string;
  profileAdjustmentReason: string;
  topMistakes: MistakeItem[];
}

const SAMPLE_PPPOKER_HANDS = `PPPoker Hand #9841201: Tournament #55102 (Liga Evolution - Carecas PKO), NL Hold'em (100/200, Ante 25) - 2026/11/12 20:14:08
Table 'Carecas Mesa 4' 8-max Seat #3 is the button
Seat 1: Vilao_Nit (8400 in chips)
Seat 2: Hero (11200 in chips)
Seat 3: Reg_Evolution (9600 in chips)
Seat 5: Recreativo77 (6500 in chips)
Recreativo77: posts small blind 100
Vilao_Nit: posts big blind 200
*** HOLE CARDS ***
Dealt to Hero [Kh 9d]
Hero: raises 420 to 620
Reg_Evolution: calls 620
Recreativo77: calls 520
Vilao_Nit: calls 420
*** FLOP *** [Qc 7s 2d]
Recreativo77: checks
Vilao_Nit: checks
Hero: bets 1850
Reg_Evolution: raises 4800 to 6650
Recreativo77: folds
Vilao_Nit: folds
Hero: folds
Uncalled bet (4800) returned to Reg_Evolution
Reg_Evolution collected 6380 from pot

PPPoker Hand #9841208: Tournament #55102 (Liga Evolution - Carecas PKO), NL Hold'em (150/300, Ante 35) - 2026/11/12 20:22:41
Table 'Carecas Mesa 4' 8-max Seat #6 is the button
Seat 2: Hero (9100 in chips)
Seat 4: Passivo_SP (14500 in chips)
Hero: posts big blind 300
*** HOLE CARDS ***
Dealt to Hero [As Jd]
Passivo_SP: calls 300
Hero: raises 900 to 1200
Passivo_SP: calls 900
*** FLOP *** [Ad 8c 4s]
Hero: bets 850
Passivo_SP: calls 850
*** TURN *** [Ad 8c 4s] [5h]
Hero: checks
Passivo_SP: checks
*** RIVER *** [Ad 8c 4s 5h] [5d]
Hero: bets 1400
Passivo_SP: raises 4800 to 6200
Hero: calls 4800
*** SHOW DOWN ***
Passivo_SP: shows [5c 4c] (a full house, Fives full of Fours)
Hero: mucks hand [As Jd]
Passivo_SP collected 16780 from pot

PPPoker Hand #9841219: Tournament #55102 (Liga Evolution - Carecas PKO), NL Hold'em (200/400, Ante 50) - 2026/11/12 20:35:12
Table 'Carecas Mesa 4' 8-max Seat #1 is the button
Seat 1: ShortBounty (3200 in chips, Bounty R$ 25)
Seat 2: Hero (12400 in chips)
Hero: posts big blind 400
*** HOLE CARDS ***
Dealt to Hero [9h 8h]
ShortBounty: raises 400 to 800
Hero: calls 400
*** FLOP *** [7h 6c 2h]
Hero: checks
ShortBounty: bets 900
Hero: calls 900
*** TURN *** [7h 6c 2h] [Kd]
Hero: checks
ShortBounty: bets 1450 and is all-in
Hero: folds
Uncalled bet (1450) returned to ShortBounty
ShortBounty collected 3500 from pot

PPPoker Hand #9841234: Tournament #55102 (Liga Evolution - Carecas PKO), NL Hold'em (250/500, Ante 60) - 2026/11/12 20:49:05
Table 'Carecas Mesa 4' 8-max Seat #5 is the button
Seat 2: Hero (10800 in chips)
Seat 3: Maniaco_RJ (16200 in chips)
Seat 5: Tight_MG (11500 in chips)
Hero: posts small blind 250
Maniaco_RJ: posts big blind 500
*** HOLE CARDS ***
Dealt to Hero [Td Th]
Tight_MG: folds
Hero: raises 750 to 1250
Maniaco_RJ: calls 750
*** FLOP *** [Jc 9c 4c]
Hero: bets 800
Maniaco_RJ: raises 2600 to 3400
Hero: calls 2600
*** TURN *** [Jc 9c 4c] [Ac]
Hero: checks
Maniaco_RJ: bets 5200
Hero: calls 5200
*** RIVER *** [Jc 9c 4c Ac] [2s]
Hero: checks
Maniaco_RJ: bets 1000 and is all-in
Hero: folds
Uncalled bet (1000) returned to Maniaco_RJ
Maniaco_RJ collected 19860 from pot

PPPoker Hand #9841247: Tournament #55102 (Liga Evolution - Carecas PKO), NL Hold'em (300/600, Ante 75) - 2026/11/12 21:03:29
Table 'Carecas Mesa 4' 8-max Seat #2 is the button
Seat 2: Hero (18500 in chips)
Seat 4: Passivo_SP (15400 in chips)
Seat 6: Reg_Evolution (14100 in chips)
Hero: raises 600 to 1200
Passivo_SP: calls 900
Reg_Evolution: calls 600
*** FLOP *** [Kd Qs 3h]
Passivo_SP: checks
Reg_Evolution: checks
Hero: bets 2900
Passivo_SP: calls 2900
Reg_Evolution: folds
*** TURN *** [Kd Qs 3h] [2c]
Passivo_SP: checks
Hero: checks
*** RIVER *** [Kd Qs 3h 2c] [Jh]
Passivo_SP: bets 6800
Hero: calls 6800
*** SHOW DOWN ***
Passivo_SP: shows [Tc 9c] (a straight, Nine to King)
Hero: shows [Ks 7s] (a pair of Kings)
Passivo_SP collected 23625 from pot`;

export default function HandAnalysisTab() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [fileName, setFileName] = useState<string>('');
  const [handHistoryText, setHandHistoryText] = useState<string>('');
  const [heroName, setHeroName] = useState<string>('Hero');
  const [aggressionProfile, setAggressionProfile] = useState<AggressionProfile>('balanced');
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [report, setReport] = useState<HandAnalysisReport | null>(null);
  const [metaInfo, setMetaInfo] = useState<{ truncated: boolean; analyzedChars: number; originalChars: number } | null>(null);

  const detectedStats = useMemo(() => {
    if (!handHistoryText.trim()) {
      return { lines: 0, estimatedHands: 0, postflopStreets: 0 };
    }
    const lines = handHistoryText.split(/\r?\n/).length;
    const handMatches = handHistoryText.match(/(?:PPPoker Hand|Hand #|Mão #|PokerStars Hand|Game #)/gi);
    const flopMatches = handHistoryText.match(/\*\*\*\s*FLOP\s*\*\*\*/gi);
    return {
      lines,
      estimatedHands: handMatches ? handMatches.length : Math.max(1, flopMatches ? flopMatches.length : 0),
      postflopStreets: flopMatches ? flopMatches.length : 0,
    };
  }, [handHistoryText]);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setErrorMsg(null);
    setFileName(file.name);

    const reader = new FileReader();
    reader.onload = (evt) => {
      const content = typeof evt.target?.result === 'string' ? evt.target.result : '';
      setHandHistoryText(content);
      setReport(null);
      setMetaInfo(null);
    };
    reader.onerror = () => {
      setErrorMsg('Não foi possível ler o arquivo .txt selecionado.');
    };
    reader.readAsText(file, 'UTF-8');
  };

  const loadSampleHands = () => {
    setErrorMsg(null);
    setFileName('exemplo_evolution_carecas_pko.txt');
    setHandHistoryText(SAMPLE_PPPOKER_HANDS);
    setReport(null);
    setMetaInfo(null);
  };

  const clearAll = () => {
    setFileName('');
    setHandHistoryText('');
    setReport(null);
    setMetaInfo(null);
    setErrorMsg(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const runAnalysis = async () => {
    if (!handHistoryText.trim()) {
      setErrorMsg('Importe um arquivo .txt do PPPoker ou cole um histórico de mãos antes de analisar.');
      return;
    }

    setIsAnalyzing(true);
    setErrorMsg(null);

    try {
      const response = await fetch('/api/analyze-hands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          handHistoryText,
          aggressionProfile,
          heroName,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        setErrorMsg(data?.error || 'Erro ao analisar o histórico de mãos.');
        return;
      }

      setReport(data.analysis as HandAnalysisReport);
      setMetaInfo({
        truncated: Boolean(data.truncated),
        analyzedChars: Number(data.analyzedChars ?? 0),
        originalChars: Number(data.originalChars ?? 0),
      });
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? `Falha de comunicação com o servidor: ${err.message}`
          : 'Falha de comunicação com o servidor de análise.'
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  const exportReportJson = () => {
    if (!report) return;
    const blob = new Blob(
      [JSON.stringify({ fileName: fileName || 'manual_input.txt', aggressionProfile, heroName, report }, null, 2)],
      { type: 'application/json' }
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `auditoria_posflop_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const severityBadge = (severity: string) => {
    const normalized = severity.toLowerCase();
    if (normalized === 'alta' || normalized === 'high') {
      return 'bg-rose-500/15 text-rose-400 border-rose-500/30';
    }
    if (normalized === 'media' || normalized === 'média' || normalized === 'medium') {
      return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
    }
    return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
  };

  const barColor = (severity: string) => {
    const normalized = severity.toLowerCase();
    if (normalized === 'alta' || normalized === 'high') return '#f43f5e';
    if (normalized === 'media' || normalized === 'média' || normalized === 'medium') return '#f59e0b';
    return '#10b981';
  };

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono px-2.5 py-0.5 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              Auditoria Pós-Flop via IA
            </span>
            <span className="text-xs font-mono text-slate-400">Formato .txt PPPoker</span>
          </div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <FileSearch className="w-5 h-5 text-indigo-400" />
            <span>Análise de Mãos & Classificação de Leaks Pós-Flop</span>
          </h2>
          <p className="text-xs text-slate-400 max-w-3xl">
            Importe o arquivo <code className="text-slate-300">.txt</code> de histórico de mãos do PPPoker para diagnosticar os erros pós-flop mais recorrentes do bot com base nas regras de EQR, SPR, Blockers, Pool Evolution e PKO.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={loadSampleHands}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition"
          >
            <FileText className="w-4 h-4 text-amber-400" />
            <span>Carregar Exemplo PPPoker (.txt)</span>
          </button>
          {handHistoryText && (
            <button
              type="button"
              onClick={clearAll}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 text-xs font-semibold transition"
            >
              <Trash2 className="w-4 h-4 text-rose-400" />
              <span>Limpar</span>
            </button>
          )}
        </div>
      </div>

      {/* Input & Configuration Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Upload + Audit Settings */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5 shadow-xl">
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
            <Upload className="w-4 h-4 text-indigo-400" />
            <span>1. Importar Arquivo (.txt)</span>
          </h3>

          <label className="block border-2 border-dashed border-slate-700 hover:border-indigo-500/70 bg-slate-950/70 rounded-xl p-5 text-center cursor-pointer transition group">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.log,text/plain"
              onChange={handleFileUpload}
              className="hidden"
            />
            <Upload className="w-7 h-7 text-slate-400 group-hover:text-indigo-400 mx-auto mb-2 transition" />
            <div className="text-xs font-semibold text-slate-200">
              {fileName ? fileName : 'Clique para selecionar arquivo .txt do PPPoker'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1 font-mono">
              Suporta logs UTF-8 até 5 MB
            </div>
          </label>

          {/* Local parser quick counters */}
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-2.5">
              <div className="text-[10px] text-slate-500 uppercase">Mãos</div>
              <div className="text-sm font-bold font-mono text-white">{detectedStats.estimatedHands}</div>
            </div>
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-2.5">
              <div className="text-[10px] text-slate-500 uppercase">Flops</div>
              <div className="text-sm font-bold font-mono text-indigo-400">{detectedStats.postflopStreets}</div>
            </div>
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-2.5">
              <div className="text-[10px] text-slate-500 uppercase">Linhas</div>
              <div className="text-sm font-bold font-mono text-slate-300">{detectedStats.lines}</div>
            </div>
          </div>

          <div className="pt-2 border-t border-slate-800 space-y-4">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Sliders className="w-3.5 h-3.5 text-emerald-400" />
              <span>2. Contexto da Auditoria</span>
            </h4>

            <div className="space-y-1.5">
              <label className="text-xs text-slate-300 font-medium block">
                Nick / Identificador do Bot no .txt
              </label>
              <input
                type="text"
                value={heroName}
                onChange={(e) => setHeroName(e.target.value)}
                placeholder="Ex: Hero ou nick da conta"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-slate-300 font-medium block">
                Perfil de Agressividade Aplicado na Sessão
              </label>
              <div className="grid grid-cols-3 gap-2">
                {(['tight', 'balanced', 'loose'] as AggressionProfile[]).map((profile) => (
                  <button
                    key={profile}
                    type="button"
                    onClick={() => setAggressionProfile(profile)}
                    className={`py-2 px-2 rounded-lg text-xs font-mono font-semibold border transition capitalize ${
                      aggressionProfile === profile
                        ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    {profile}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={runAnalysis}
              disabled={isAnalyzing || !handHistoryText.trim()}
              className={`w-full py-3 rounded-xl font-semibold text-xs transition shadow-lg flex items-center justify-center gap-2 ${
                isAnalyzing || !handHistoryText.trim()
                  ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/25'
              }`}
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Auditando Ações Pós-Flop...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Analisar Erros Pós-Flop com IA</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right: Hand History Preview / Paste */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <FileText className="w-4 h-4 text-emerald-400" />
              <span>Pré-visualização / Cola Direta do Histórico (.txt)</span>
            </h3>
            <span className="text-[11px] font-mono text-slate-500">
              {handHistoryText.length.toLocaleString()} caracteres
            </span>
          </div>
          <textarea
            value={handHistoryText}
            onChange={(e) => setHandHistoryText(e.target.value)}
            placeholder="Importe um arquivo .txt do PPPoker ao lado ou cole aqui o conteúdo do histórico de mãos (PPPoker Hand #...) para auditar os erros pós-flop..."
            className="w-full flex-1 min-h-[300px] bg-slate-950 border border-slate-800 rounded-xl p-4 text-xs text-slate-300 font-mono leading-relaxed focus:outline-none focus:border-indigo-500 resize-y"
          />
        </div>
      </div>

      {/* Visual Hand Replayer */}
      <HandReplayer handHistoryText={handHistoryText} heroName={heroName} />

      {/* Error Alert */}
      {errorMsg && (
        <div className="bg-rose-950/50 border border-rose-500/40 rounded-2xl p-4 flex items-start gap-3 text-xs text-rose-200">
          <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <div className="font-bold text-rose-300">Erro na Auditoria de Mãos</div>
            <p className="mt-0.5 leading-relaxed">{errorMsg}</p>
          </div>
        </div>
      )}

      {/* AI Report Output */}
      {report && (
        <div className="space-y-6">
          {metaInfo?.truncated && (
            <div className="bg-amber-950/40 border border-amber-500/30 rounded-xl p-3 text-xs text-amber-200 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>
                Arquivo extenso: foram analisados os primeiros {metaInfo.analyzedChars.toLocaleString()} de {metaInfo.originalChars.toLocaleString()} caracteres.
              </span>
            </div>
          )}

          {/* KPI Summary Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-1">
              <div className="text-xs text-slate-400">Mãos / Flops Auditados</div>
              <div className="text-2xl font-bold font-mono text-white">
                {report.totalHandsDetected} <span className="text-sm text-indigo-400">({report.postflopHandsReviewed} pós-flop)</span>
              </div>
              <div className="text-[10px] text-slate-500">Processado no histórico enviado</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-1">
              <div className="text-xs text-slate-400">Erros Pós-Flop Detectados</div>
              <div className="text-2xl font-bold font-mono text-rose-400">
                {report.totalMistakesFound}
              </div>
              <div className="text-[10px] text-slate-500">Leaks classificados por street e regra</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-1">
              <div className="text-xs text-slate-400">Nota de Execução Pós-Flop</div>
              <div className="text-2xl font-bold font-mono text-emerald-400">
                {report.overallGrade}
              </div>
              <div className="text-[10px] text-slate-500">Aderência ao Cérebro GTO & Exploits</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-1">
              <div className="text-xs text-slate-400">Perfil Sugerido pela IA</div>
              <div className="text-2xl font-bold font-mono text-amber-400 uppercase">
                {report.recommendedProfile}
              </div>
              <div className="text-[10px] text-slate-500">Atual: {aggressionProfile.toUpperCase()}</div>
            </div>
          </div>

          {/* Executive Summary + Chart */}
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between space-y-4">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                    <Target className="w-4 h-4 text-indigo-400" />
                    <span>Diagnóstico Executivo</span>
                  </h3>
                  <button
                    type="button"
                    onClick={exportReportJson}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 font-medium transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Exportar JSON</span>
                  </button>
                </div>

                <p className="text-xs text-slate-200 leading-relaxed bg-slate-950 border border-slate-800 rounded-xl p-4">
                  {report.executiveSummary}
                </p>

                <div className="bg-indigo-950/30 border border-indigo-500/30 rounded-xl p-4 space-y-1">
                  <div className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Recomendação de Perfil ({report.recommendedProfile.toUpperCase()})</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {report.profileAdjustmentReason}
                  </p>
                </div>
              </div>
            </div>

            <div className="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                  <TrendingDown className="w-4 h-4 text-rose-400" />
                  <span>Frequência dos Erros Pós-Flop (%)</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Distribuição dos leaks identificados por categoria estratégica
                </p>
              </div>

              <div className="h-64 w-full">
                {report.topMistakes?.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={report.topMistakes}
                      layout="vertical"
                      margin={{ top: 5, right: 25, left: 10, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                      <XAxis
                        type="number"
                        stroke="#64748b"
                        tick={{ fill: '#94a3b8', fontSize: 11 }}
                        unit="%"
                      />
                      <YAxis
                        type="category"
                        dataKey="category"
                        width={165}
                        stroke="#64748b"
                        tick={{ fill: '#e2e8f0', fontSize: 11 }}
                      />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload || !payload.length) return null;
                          const item = payload[0].payload as MistakeItem;
                          return (
                            <div className="bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs font-mono space-y-1 shadow-2xl">
                              <div className="font-bold text-white">{item.category}</div>
                              <div className="text-slate-300">Ocorrências: {item.occurrences} ({item.frequencyPct}%)</div>
                              <div className="text-indigo-400">Street: {item.affectedStreet}</div>
                            </div>
                          );
                        }}
                      />
                      <Bar dataKey="frequencyPct" radius={[0, 6, 6, 0]} barSize={22}>
                        {report.topMistakes.map((entry, idx) => (
                          <Cell key={idx} fill={barColor(entry.severity)} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-slate-500 font-mono">
                    Nenhum erro recorrente significativo foi identificado neste arquivo.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Detailed Mistake Classification Cards */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-amber-400" />
              <span>Ranking Detalhado de Erros & Plano de Correção</span>
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {report.topMistakes?.map((mistake, index) => (
                <div
                  key={`${mistake.category}-${index}`}
                  className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3 flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-[11px] font-mono text-slate-500">
                          #{index + 1} • Street: <span className="text-indigo-400 font-semibold">{mistake.affectedStreet}</span>
                        </div>
                        <h4 className="text-base font-bold text-white mt-0.5">{mistake.category}</h4>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-slate-200">
                          {mistake.occurrences}x ({mistake.frequencyPct}%)
                        </span>
                        <span className={`text-[10px] font-mono uppercase px-2 py-1 rounded-lg border ${severityBadge(mistake.severity)}`}>
                          {mistake.severity}
                        </span>
                      </div>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      {mistake.description}
                    </p>

                    <div className="bg-slate-950 border border-slate-800/90 rounded-xl p-3 space-y-1">
                      <div className="text-[10px] font-mono uppercase text-amber-400 font-semibold">
                        Spot de Exemplo Extraído
                      </div>
                      <div className="text-xs font-mono text-slate-300 leading-relaxed">
                        {mistake.exampleSpot}
                      </div>
                    </div>
                  </div>

                  <div className="bg-emerald-950/30 border border-emerald-500/25 rounded-xl p-3 space-y-1">
                    <div className="text-[10px] font-mono uppercase text-emerald-400 font-semibold">
                      Correção Recomendada (Cérebro Pós-Flop)
                    </div>
                    <div className="text-xs text-emerald-100 leading-relaxed">
                      {mistake.recommendedFix}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useMemo, useState } from 'react';
import { 
  Cpu, Terminal, Play, Square,
  Download, Activity, MousePointer, BookOpen, Award, TrendingUp, DollarSign, Plus, Brain, FileSearch, Grid3X3
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend
} from 'recharts';
import PreflopBrainLab from './components/PreflopBrainLab';
import PostflopBrainLab from './components/PostflopBrainLab';
import HandAnalysisTab from './components/HandAnalysisTab';

export default function App() {
  const [activeTab, setActiveTab] = useState<'preflop' | 'brain' | 'hands' | 'bankroll' | 'routine' | 'bible' | 'mouse' | 'control' | 'launcher'>('preflop');
  
  // Bot control state
  const [botRunning, setBotRunning] = useState<boolean>(false);
  const [hwndList] = useState<string>('0x12FA, 0x34BC');
  const [bountyMode] = useState<boolean>(true);
  const [overlayActive] = useState<boolean>(true);
  const [logs, setLogs] = useState<string[]>([
    '[INIT] Bot Control Center iniciado.',
    '[BANKROLL] Módulo de monitoramento e ROI ativo.'
  ]);

  // Anti-cheat mouse settings
  const [bezierCurvature, setBezierCurvature] = useState<number>(0.35);
  const [spatialJitter, setSpatialJitter] = useState<number>(4);

  // Bankroll state
  const [bankrollEntries, setBankrollEntries] = useState<{
    id: number;
    date: string;
    stake: string;
    buyin: number;
    tournaments: number;
    profit: number;
    evProfit: number;
  }[]>([
    { id: 1, date: '2026-11-12', stake: 'R$ 50 PKO', buyin: 500, tournaments: 10, profit: 1450, evProfit: 1320 },
    { id: 2, date: '2026-11-11', stake: 'R$ 25 Turbo', buyin: 250, tournaments: 10, profit: -180, evProfit: -90 },
    { id: 3, date: '2026-11-10', stake: 'R$ 100 High Roller', buyin: 1000, tournaments: 10, profit: 2890, evProfit: 2500 }
  ]);

  const [newDate, setNewDate] = useState(new Date().toISOString().split('T')[0]);
  const [newStake, setNewStake] = useState('R$ 50 PKO');
  const [newBuyin, setNewBuyin] = useState('500');
  const [newTournaments, setNewTournaments] = useState('10');
  const [newProfit, setNewProfit] = useState('');
  const [newEvProfit, setNewEvProfit] = useState('');

  const addBankrollEntry = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProfit) return;
    setBankrollEntries([
      {
        id: Date.now(),
        date: newDate,
        stake: newStake,
        buyin: parseFloat(newBuyin) || 0,
        tournaments: parseInt(newTournaments) || 1,
        profit: parseFloat(newProfit) || 0,
        evProfit: parseFloat(newEvProfit) || parseFloat(newProfit) || 0
      },
      ...bankrollEntries
    ]);
    setNewProfit('');
    setNewEvProfit('');
  };

  // Calculations
  const totalBuyins = bankrollEntries.reduce((acc, e) => acc + e.buyin, 0);
  const totalProfit = bankrollEntries.reduce((acc, e) => acc + e.profit, 0);
  const totalEvProfit = bankrollEntries.reduce((acc, e) => acc + e.evProfit, 0);
  const totalTournaments = bankrollEntries.reduce((acc, e) => acc + e.tournaments, 0);
  const roi = totalBuyins > 0 ? (totalProfit / totalBuyins) * 100 : 0;

  // Stake progression check
  const currentBankroll = 5000 + totalProfit; // Initial Bankroll base R$ 5,000
  const recommendedStakeLimit = currentBankroll > 15000 ? 'R$ 100+ High Roller' : currentBankroll > 8000 ? 'R$ 50 PKO / Turbo' : 'R$ 25 Micro/Mid';

  // Chronological chart data (Saldo vs EV across dates in bankrollEntries)
  const chartData = useMemo(() => {
    const groupedByDate = new Map<string, { profit: number; evProfit: number; tournaments: number }>();

    for (const entry of bankrollEntries) {
      const current = groupedByDate.get(entry.date) ?? { profit: 0, evProfit: 0, tournaments: 0 };
      groupedByDate.set(entry.date, {
        profit: current.profit + entry.profit,
        evProfit: current.evProfit + entry.evProfit,
        tournaments: current.tournaments + entry.tournaments
      });
    }

    const sortedDates = Array.from(groupedByDate.keys()).sort((a, b) => a.localeCompare(b));
    let runningSaldo = 5000;
    let runningEv = 5000;

    return sortedDates.map((date) => {
      const dayStats = groupedByDate.get(date)!;
      runningSaldo += dayStats.profit;
      runningEv += dayStats.evProfit;
      const [, month, day] = date.split('-');
      return {
        date,
        label: day && month ? `${day}/${month}` : date,
        saldo: runningSaldo,
        ev: runningEv,
        dailyProfit: dayStats.profit,
        dailyEv: dayStats.evProfit,
        tournaments: dayStats.tournaments
      };
    });
  }, [bankrollEntries]);

  const toggleBot = async () => {
    try {
      if (!botRunning) {
        const res = await fetch("/api/bot/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hwnd: hwndList, bounty: bountyMode, overlay: overlayActive, mouse: true }),
        });
        const data = await res.json();
        if (data.success) {
          setBotRunning(true);
          setLogs(prev => [`[${new Date().toLocaleTimeString()}] [START] ${data.message}`, ...prev]);
        } else {
          setLogs(prev => [`[${new Date().toLocaleTimeString()}] [ERROR] ${data.error || 'Falha ao iniciar bot.'}`, ...prev]);
        }
      } else {
        const res = await fetch("/api/bot/stop", { method: "POST" });
        const data = await res.json();
        setBotRunning(false);
        setLogs(prev => [`[${new Date().toLocaleTimeString()}] [STOP] ${data.message || 'Sessão encerrada.'}`, ...prev]);
      }
    } catch (err) {
      setLogs(prev => [`[${new Date().toLocaleTimeString()}] [ERROR] Falha de comunicação com a ponte do bot.`, ...prev]);
    }
  };

  const batScriptContent = `@echo off
TITLE VisualPilot 2.0 - Liga Evolution & Clube do Carecas
COLOR 0A
echo ==========================================
echo    VISUALPILOT 2.0 - SESSAO DE TORNEIOS
echo ==========================================
echo [INFO] Clube: Clube do Carecas (Liga Evolution)
echo [INFO] HWNDs: ${hwndList}
echo [INFO] Executando rotina de inscricao e torneios...
python python_bot/tournament_rotina.py
echo [INFO] Iniciando agente de mesas operar_mesa.py...
python python_bot/operar_mesa.py --hwnd ${hwndList} ${bountyMode ? '--bounty-bb' : ''} ${overlayActive ? '--overlay' : ''} --human-mouse
pause
`;

  const downloadBatFile = () => {
    const element = document.createElement('a');
    const file = new Blob([batScriptContent], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = 'INICIAR_SESSAO_EVOLUTION.bat';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Cpu className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                Poker Command & Bankroll Suite
                <span className={`text-xs px-2.5 py-0.5 rounded-full font-mono border ${
                  botRunning 
                    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30 animate-pulse' 
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                }`}>
                  {botRunning ? 'Sessão Ativa' : 'Aguardando Início'}
                </span>
              </h1>
              <p className="text-xs text-slate-400 font-mono">Liga Evolution & Clube do Carecas</p>
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={toggleBot}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-semibold text-xs transition shadow-lg ${
                botRunning
                  ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/20'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/20'
              }`}
            >
              {botRunning ? <Square className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current" />}
              <span>{botRunning ? 'Encerrar Sessão' : 'Iniciar Sessão'}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full space-y-8">
        
        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-800 space-x-2 overflow-x-auto">
          <button
            onClick={() => setActiveTab('preflop')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'preflop'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <Grid3X3 className="w-4 h-4" />
            <span>Cérebro Pré-Flop</span>
          </button>
          <button
            onClick={() => setActiveTab('brain')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'brain'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <Brain className="w-4 h-4" />
            <span>Cérebro Pós-Flop</span>
          </button>
          <button
            onClick={() => setActiveTab('hands')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'hands'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <FileSearch className="w-4 h-4" />
            <span>Análise de Mãos</span>
          </button>
          <button
            onClick={() => setActiveTab('bankroll')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'bankroll'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            <span>Monitoramento de Bankroll & ROI</span>
          </button>
          <button
            onClick={() => setActiveTab('routine')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'routine'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <Award className="w-4 h-4" />
            <span>Rotina & Torneios (Evolution)</span>
          </button>
          <button
            onClick={() => setActiveTab('bible')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'bible'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <BookOpen className="w-4 h-4" />
            <span>Guia de Funcionamento (Bíblia)</span>
          </button>
          <button
            onClick={() => setActiveTab('mouse')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'mouse'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <MousePointer className="w-4 h-4" />
            <span>Anti-Cheat Mouse</span>
          </button>
          <button
            onClick={() => setActiveTab('control')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'control'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <Activity className="w-4 h-4" />
            <span>Painel & Logs</span>
          </button>
          <button
            onClick={() => setActiveTab('launcher')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition whitespace-nowrap ${
              activeTab === 'launcher'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <Terminal className="w-4 h-4" />
            <span>Launcher (.bat)</span>
          </button>
        </div>

        {/* Tab 0: Preflop Brain Lab */}
        {activeTab === 'preflop' && <PreflopBrainLab />}

        {/* Tab 1: Postflop Brain Lab */}
        {activeTab === 'brain' && <PostflopBrainLab />}

        {/* Tab 0.5: Hand History AI Analysis */}
        {activeTab === 'hands' && <HandAnalysisTab />}

        {/* Tab 1: Bankroll Monitoring & ROI */}
        {activeTab === 'bankroll' && (
          <div className="space-y-8">
            {/* Interactive Line Chart: Saldo vs EV Evolution */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-emerald-400" />
                    <span>Evolução do Saldo vs. EV Acumulado</span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    Comparativo cronológico a partir da banca inicial de R$ 5.000
                  </p>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono">
                  <span className="flex items-center gap-1.5 text-emerald-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                    Saldo Real
                  </span>
                  <span className="flex items-center gap-1.5 text-indigo-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-indigo-400"></span>
                    EV Esperado
                  </span>
                </div>
              </div>

              <div className="h-72 w-full">
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        dataKey="label"
                        stroke="#64748b"
                        tick={{ fill: '#94a3b8', fontSize: 12 }}
                        tickLine={{ stroke: '#334155' }}
                      />
                      <YAxis
                        stroke="#64748b"
                        tick={{ fill: '#94a3b8', fontSize: 12 }}
                        tickLine={{ stroke: '#334155' }}
                        tickFormatter={(value: number) => `R$ ${(value / 1000).toFixed(1)}k`}
                        domain={['auto', 'auto']}
                      />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload || payload.length === 0) return null;
                          const data = payload[0].payload as (typeof chartData)[number];
                          const diff = data.saldo - data.ev;
                          return (
                            <div className="bg-slate-950 border border-slate-700 rounded-xl p-3 shadow-2xl text-xs space-y-1.5 font-mono">
                              <div className="text-slate-300 font-bold border-b border-slate-800 pb-1">
                                Data: {data.date} ({data.tournaments} torneios)
                              </div>
                              <div className="flex justify-between gap-4 text-emerald-400">
                                <span>Saldo Real:</span>
                                <span className="font-bold">R$ {data.saldo.toLocaleString()}</span>
                              </div>
                              <div className="flex justify-between gap-4 text-indigo-400">
                                <span>EV Acumulado:</span>
                                <span className="font-bold">R$ {data.ev.toLocaleString()}</span>
                              </div>
                              <div className="flex justify-between gap-4 text-slate-400 pt-1 border-t border-slate-800/80">
                                <span>Resultado Dia:</span>
                                <span className={data.dailyProfit >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                  {data.dailyProfit >= 0 ? `+R$ ${data.dailyProfit.toLocaleString()}` : `-R$ ${Math.abs(data.dailyProfit).toLocaleString()}`}
                                </span>
                              </div>
                              <div className="flex justify-between gap-4 text-slate-400">
                                <span>Run vs. EV:</span>
                                <span className={diff >= 0 ? 'text-emerald-400' : 'text-amber-400'}>
                                  {diff >= 0 ? `+R$ ${diff.toLocaleString()}` : `-R$ ${Math.abs(diff).toLocaleString()}`}
                                </span>
                              </div>
                            </div>
                          );
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }} />
                      <Line
                        type="monotone"
                        dataKey="saldo"
                        name="Saldo Real (R$)"
                        stroke="#10b981"
                        strokeWidth={3}
                        dot={{ r: 4, fill: '#10b981', strokeWidth: 2, stroke: '#020617' }}
                        activeDot={{ r: 6, fill: '#34d399' }}
                      />
                      <Line
                        type="monotone"
                        dataKey="ev"
                        name="EV Esperado (R$)"
                        stroke="#6366f1"
                        strokeWidth={2.5}
                        strokeDasharray="6 4"
                        dot={{ r: 4, fill: '#6366f1', strokeWidth: 2, stroke: '#020617' }}
                        activeDot={{ r: 6, fill: '#818cf8' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-slate-500 font-mono">
                    Adicione sessões para visualizar a curva de evolução.
                  </div>
                )}
              </div>
            </div>

            {/* Top Metrics Summary */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-2 shadow-xl">
                <div className="text-slate-400 text-xs">Bankroll Atual Estimado</div>
                <div className={`text-2xl font-bold font-mono ${currentBankroll >= 5000 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  R$ {currentBankroll.toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-500">Base inicial R$ 5.000 + Lucro Líquido</div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-2 shadow-xl">
                <div className="text-slate-400 text-xs">ROI Acumulado</div>
                <div className={`text-2xl font-bold font-mono ${roi >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {roi.toFixed(1)}%
                </div>
                <div className="text-[10px] text-slate-500">Retorno sobre R$ {totalBuyins.toLocaleString()} investidos</div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-2 shadow-xl">
                <div className="text-slate-400 text-xs">EV Acumulado (Esperado)</div>
                <div className="text-2xl font-bold font-mono text-indigo-400">
                  R$ {totalEvProfit.toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-500">Valor esperado pelo cérebro GTO</div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-2 shadow-xl">
                <div className="text-slate-400 text-xs">Progresso de Limites Recomendado</div>
                <div className="text-lg font-bold font-mono text-amber-400 truncate">
                  {recommendedStakeLimit}
                </div>
                <div className="text-[10px] text-slate-500">Baseado em 100+ buy-ins de margem</div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* Manual Input Form */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
                <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                  <Plus className="w-4 h-4 text-indigo-400" />
                  <span>Input Diário de Resultado</span>
                </h3>
                <form onSubmit={addBankrollEntry} className="space-y-4">
                  <div className="space-y-1">
                    <label className="text-xs text-slate-300 font-medium">Data</label>
                    <input 
                      type="date" 
                      value={newDate}
                      onChange={(e) => setNewDate(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs text-slate-300 font-medium">Stake / Limite</label>
                    <input 
                      type="text" 
                      value={newStake}
                      onChange={(e) => setNewStake(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs text-slate-300 font-medium">Total Buy-ins (R$)</label>
                      <input 
                        type="number" 
                        value={newBuyin}
                        onChange={(e) => setNewBuyin(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-slate-300 font-medium">Qtd Torneios</label>
                      <input 
                        type="number" 
                        value={newTournaments}
                        onChange={(e) => setNewTournaments(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs text-slate-300 font-medium">Lucro Real (R$)</label>
                      <input 
                        type="number" 
                        placeholder="Ex: 850"
                        value={newProfit}
                        onChange={(e) => setNewProfit(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-slate-300 font-medium">Lucro EV (R$)</label>
                      <input 
                        type="number" 
                        placeholder="Ex: 800"
                        value={newEvProfit}
                        onChange={(e) => setNewEvProfit(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono"
                      />
                    </div>
                  </div>

                  <button 
                    type="submit"
                    className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 font-semibold text-white transition shadow-lg shadow-indigo-500/20 text-xs"
                  >
                    Adicionar Registro de Sessão
                  </button>
                </form>
              </div>

              {/* Performance History Table */}
              <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
                <div className="flex justify-between items-center">
                  <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                    <DollarSign className="w-4 h-4 text-emerald-400" />
                    <span>Histórico de Performance & Sessões</span>
                  </h3>
                  <div className="text-xs text-slate-400 font-mono">
                    Total Torneios: {totalTournaments}
                  </div>
                </div>

                <div className="space-y-3 overflow-x-auto">
                  {bankrollEntries.map((e) => {
                    const sessionRoi = e.buyin > 0 ? (e.profit / e.buyin) * 100 : 0;
                    return (
                      <div key={e.id} className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 flex items-center justify-between min-w-[500px]">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-white">{e.stake}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">{e.date}</span>
                          </div>
                          <div className="text-xs text-slate-400 font-mono mt-1">
                            Buy-ins: R$ {e.buyin} • Torneios: {e.tournaments} • EV: R$ {e.evProfit}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className={`text-sm font-mono font-bold ${e.profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {e.profit >= 0 ? `+R$ ${e.profit.toLocaleString()}` : `-R$ ${Math.abs(e.profit).toLocaleString()}`}
                          </div>
                          <div className={`text-[10px] font-mono ${sessionRoi >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                            ROI: {sessionRoi.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Routine */}
        {activeTab === 'routine' && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl">
            <div>
              <span className="text-xs font-mono px-2.5 py-1 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Fluxo Operacional Diário
              </span>
              <h2 className="text-2xl font-bold text-white mt-2">Rotina de Início de Sessão (Liga Evolution & Clube do Carecas)</h2>
              <p className="text-xs text-slate-400 font-mono mt-1">Gerenciamento de Bankroll, Inscrição, Organização e Gameplay</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-2">
                <div className="text-indigo-400 font-semibold text-sm">1. Seleção de Torneios & Horários</div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Programação diária estipulando os torneios, duração da sessão e horário limite de late registration na <strong>Liga da Evolution</strong> e <strong>Clube do Carecas</strong>.
                </p>
              </div>
              <div className="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-2">
                <div className="text-indigo-400 font-semibold text-sm">2. Bankroll & Buy-in Policy</div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Inscrições validadas contra a política de bankroll e progressão de limites de 100+ buy-ins.
                </p>
              </div>
              <div className="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-2">
                <div className="text-indigo-400 font-semibold text-sm">3. Registro, Abertura & Layout</div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Registro automático no lobby, abertura das mesas e organização pelos atalhos nativos de layout do PPPoker.
                </p>
              </div>
              <div className="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-2">
                <div className="text-indigo-400 font-semibold text-sm">4. Assunção do Gameplay (Cérebro GTO)</div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Monitoramento em round-robin com motor pós-flop calibrado (SPR, EQR, Blockers, HUD Gate) e mouse anti-cheat.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Bible */}
        {activeTab === 'bible' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl">
              <div className="border-b border-slate-800 pb-4">
                <span className="text-xs font-mono px-2.5 py-1 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  Documento Oficial + Especificação Técnica
                </span>
                <h2 className="text-2xl font-bold text-white mt-2">Guia de Funcionamento ("A Bíblia do Sistema")</h2>
                <p className="text-xs text-slate-400 font-mono mt-1">Local salvo: /docs/GUIA_FUNCIONAMENTO.md (Sempre atualizado)</p>
              </div>

              <div className="space-y-3 text-xs text-slate-300 leading-relaxed">
                <p>
                  <strong>1. Cérebro Pré-Flop:</strong> Matriz interativa de 169 mãos com zonas de stack (Deep, Mid-Stack, Re-Shove e Push/Fold Nash &lt;14 BB), Bubble Factor ICM (<code>1.00x–1.55x</code>), Bounty Power PKO, Iso-Raise contra limpers (<code>3.5x + 1x/limper</code>) e HUD Gate de Fold to 3-Bet.
                </p>
                <p>
                  <strong>2. Cérebro Pós-Flop (v2):</strong> Motor determinístico com Iniciativa Pré-Flop (Range/Nut Advantage e Donk-Bet), Scare Cards (Turn/River), Overbets (135%) com MDF ajustado ao pool, Calculadora de Outs Reais, SPR, Sizing Geométrico, EQR Multi-Way, Blockers, HUD Sample Gate (≥ 30 mãos), PKO Overlay e Mixagem RNG.
                </p>
                <p>
                  <strong>3. Análise de Mãos (.txt PPPoker + IA + Hand Replayer):</strong> Importação de históricos <code>.txt</code> com <strong>Hand Replayer visual</strong> (mesa, cartas do herói/mesa em 4 ou 2 cores, controles de Play/Pausar e saltos por street) e auditoria por IA no servidor classificando os erros pós-flop por frequência, street e gravidade.
                </p>
                <p>
                  <strong>4. Monitoramento de Bankroll & ROI:</strong> Gráfico interativo Recharts (Saldo Real vs. EV Esperado), cálculo automático de ROI, EV acumulado e recomendação de limites.
                </p>
                <p>
                  <strong>5. Inicialização Segura (.bat):</strong> Execução via interpretador Python nativo sem empacotamento em <code>.exe</code>, preservando invisibilidade contra heurísticas anti-cheat.
                </p>
              </div>

              {/* Section 4 Tables */}
              <div className="pt-4 border-t border-slate-800 space-y-6">
                <h3 className="text-base font-bold text-white">Tabela de Pesos & Regras Formais do Motor Pós-Flop</h3>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Base Equity Table */}
                  <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
                    <div className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                      4.1 Equidade Bruta Base por Categoria
                    </div>
                    <div className="space-y-1.5 text-xs font-mono">
                      {[
                        ['nut_value (Trinca+, Straight+)', '88%'],
                        ['strong_value (TPTK / Overpair)', '71%'],
                        ['medium_showdown (2º Par / TP Fraco)', '50%'],
                        ['combo_draw (FD + OESD)', '48%'],
                        ['nut_draw (Nut FD / OESD)', '36%'],
                        ['weak_draw (Gutshot / Backdoor)', '21%'],
                        ['air (Sem Par / Sem Projeto)', '10%'],
                      ].map(([label, val]) => (
                        <div key={label} className="flex justify-between border-b border-slate-800/70 pb-1">
                          <span className="text-slate-300">{label}</span>
                          <span className="text-emerald-400 font-bold">{val}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* EQR & Multi-way Table */}
                  <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
                    <div className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                      4.2 Fator EQR & Desconto Multi-Way (0.86^(n-2))
                    </div>
                    <div className="space-y-1.5 text-xs font-mono">
                      {[
                        ['Heads-Up (2 Jogadores) — IP', '1.08x'],
                        ['Heads-Up (2 Jogadores) — OOP', '0.78x'],
                        ['3-Way — IP (Blefe ar bloqueado)', '0.93x'],
                        ['3-Way — OOP (Blefe ar bloqueado)', '0.67x'],
                        ['4-Way — IP (Foco estrito valor)', '0.80x'],
                        ['4-Way — OOP (Pot control rigoroso)', '0.58x'],
                      ].map(([label, val]) => (
                        <div key={label} className="flex justify-between border-b border-slate-800/70 pb-1">
                          <span className="text-slate-300">{label}</span>
                          <span className="text-amber-400 font-bold">{val}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* SPR & Formal Rules */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2.5">
                    <div className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                      4.3 Zonas de SPR & Sizing Geométrico
                    </div>
                    <ul className="text-xs text-slate-300 space-y-1.5 leading-relaxed">
                      <li><strong className="text-rose-400">POT COMMIT (SPR &lt; 1.5):</strong> Prioriza All-In direto em vez de apostas fracionadas para evitar perda de <em>fold equity</em>.</li>
                      <li><strong className="text-emerald-400">LOW (SPR ≤ 2.5):</strong> Compromisso rápido com TPTK, Overpairs e Combo Draws.</li>
                      <li><strong className="text-indigo-400">MEDIUM (2.5 &lt; SPR ≤ 6.0):</strong> Fórmula <code>s = ((1 + 2·SPR)^(1/n) - 1) / 2</code> (20%–250% pote).</li>
                      <li><strong className="text-amber-400">HIGH (SPR &gt; 6.0):</strong> Deep / Pot Control; exige dois pares+ ou nut draws p/ pote grande.</li>
                    </ul>
                  </div>

                  <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2.5">
                    <div className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                      4.4 Regras de Pool, Blockers, HUD, PKO & Agressividade
                    </div>
                    <ul className="text-xs text-slate-300 space-y-1.5 leading-relaxed">
                      <li><strong>Iniciativa & Donk-Bet:</strong> Cruza <code>hero_pfr / villain_pfr / 3bet_pot / limped</code> com a textura p/ calcular Vantagem de Range/Nuts e Donk-Bet OOP.</li>
                      <li><strong>Scare Cards & Outs Reais:</strong> Penaliza <code>strong_value</code> quando Turn/River completa flush/straight/dobra e calcula equidade exata por outs (desconto 0.85x em boards pareados/monotone).</li>
                      <li><strong>Overbet (135%) & MDF:</strong> Calcula <code>MDF = 1 / (1 + Bet%)</code> com ajuste de <code>0.75x</code> no pool Evolution underbluff.</li>
                      <li><strong>Perfis (Tight / Balanced / Loose) & RNG:</strong> C-Bet ≥ <code>48% / 34% / 20%</code>, Raise ≥ <code>62% / 46% / 34%</code> e roleta estocástica 0–99 para frequências mistas.</li>
                      <li><strong>HUD Gate & PKO:</strong> Exploit libera com <code>≥ 30 mãos</code>; PKO soma <code>bountyCoverBB * 0.45</code> ao pote efetivo.</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Mouse */}
        {activeTab === 'mouse' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Parâmetros Biomecânicos</h3>
              <div className="space-y-3">
                <label className="text-xs text-slate-300 font-medium block">
                  Curvatura de Bézier ({bezierCurvature})
                </label>
                <input
                  type="range"
                  min="0.1"
                  max="0.8"
                  step="0.05"
                  value={bezierCurvature}
                  onChange={(e) => setBezierCurvature(Number(e.target.value))}
                  className="w-full accent-indigo-600 cursor-pointer"
                />
                <label className="text-xs text-slate-300 font-medium block">
                  Jitter Espacial ({spatialJitter} px)
                </label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  step="1"
                  value={spatialJitter}
                  onChange={(e) => setSpatialJitter(Number(e.target.value))}
                  className="w-full accent-indigo-600 cursor-pointer"
                />
              </div>
            </div>

            <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
              <h3 className="text-lg font-bold text-white">Anti-Cheat Mouse Evasion</h3>
              <p className="text-slate-300 text-sm leading-relaxed">
                O movimento do cursor utiliza curvas de Bézier (curvatura {bezierCurvature}), aceleração natural e desvio espacial gaussiano de ±{spatialJitter}px para impedir qualquer marcação de bot por telemetria mecânica.
              </p>
            </div>
          </div>
        )}

        {/* Tab 5: Control */}
        {activeTab === 'control' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Status Operacional</h3>
              <button
                onClick={toggleBot}
                className={`w-full py-3 rounded-xl font-semibold text-sm transition shadow-lg flex items-center justify-center gap-2 ${
                  botRunning ? 'bg-rose-600 hover:bg-rose-500 text-white' : 'bg-emerald-600 hover:bg-emerald-500 text-white'
                }`}
              >
                {botRunning ? <Square className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current" />}
                <span>{botRunning ? 'Encerrar Sessão' : 'Iniciar Sessão'}</span>
              </button>
            </div>

            <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col space-y-4">
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Logs ao Vivo</h3>
              <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 font-mono text-xs text-slate-300 h-72 overflow-y-auto space-y-1.5">
                {logs.map((log, i) => (
                  <div key={i}>
                    <span className="text-slate-500">&gt; </span>
                    <span>{log}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Tab 6: Launcher */}
        {activeTab === 'launcher' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6 shadow-xl">
              <h3 className="text-lg font-bold text-white">Gerador de Launcher Seguro (.bat)</h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Invoca diretamente o interpretador Python nativo sem empacotamento em <code>.exe</code>, reduzindo o risco de detecção.
              </p>
              <button
                onClick={downloadBatFile}
                className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 font-semibold text-white transition shadow-lg text-sm flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4" />
                <span>Baixar INICIAR_SESSAO_EVOLUTION.bat</span>
              </button>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
              <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 font-mono text-xs text-emerald-400 h-64 overflow-y-auto whitespace-pre">
                {batScriptContent}
              </div>
            </div>
          </div>
        )}

      </main>

      <footer className="border-t border-slate-800 bg-slate-900/40 py-6 text-center text-xs text-slate-500">
        <p>Poker Command & Bankroll Suite • Monitoramento de Bankroll & ROI Ativo</p>
      </footer>
    </div>
  );
}

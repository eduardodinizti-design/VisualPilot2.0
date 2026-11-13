# GUIA DE FUNCIONAMENTO — POLARIS POKER AUTOMATION SUITE ("A BÍBLIA DO PROJETO")

Este documento oficial serve como o manual definitivo de arquitetura, operação, configuração, regras formais do motor estratégico e funcionamento de todo o sistema de automação e GTO. Ele deve ser rigorosamente atualizado a cada nova funcionalidade, botão ou módulo adicionado ao ecossistema.

---

## 1. Visão Geral (Para que Funciona)
O **Polaris Poker Automation Suite** é um ecossistema avançado projetado para:
- **Observação em Tempo Real**: Monitorar mesas de poker (PPPoker / Windows) via captura de tela nativa otimizada (`ReaderCache` a 0.1ms/frame).
- **Tomada de Decisão GTO**: Calcular equidade pós-flop (outs, implied odds reversas, desconto multi-way, SPR, sizing geométrico e blockers) e gerenciar ranges pré-flop com suporte a torneios PKO (Progressive Knockout) e HUD VIP com gate de confiança.
- **Evasão Anti-Cheat Biomecânica**: Executar movimentos de cursor via curvas de Bézier, aceleração natural, latência estocástica e jitter espacial para evitar detecção por telemetria.
- **Segurança de Execução**: Empregar blindagens absolutas (Anti-Fold Premium e Anti-Fold sem leitura) para proteger o bankroll contra falhas visuais.
- **Auditoria Pós-Flop de Mãos (.txt PPPoker + IA)**: Importar históricos de mãos exportados do PPPoker para classificar automaticamente via IA os erros pós-flop mais frequentes do bot e recomendar ajustes de perfil/regras.
- **Monitoramento de Bankroll & ROI**: Acompanhamento rigoroso de resultados diários, cálculo automático de ROI, EV acumulado e diretrizes de progressão de limites.

---

## 2. Rotina de Inicialização e Sessão de Torneios (Liga Evolution & Clube do Carecas)
A rotina operacional diária para iniciar o bot segue o seguinte fluxo validado:

1. **Agendamento da Sessão**:
   - O operador programa a sessão diária estipulando quais torneios serão jogados, a duração estimada da sessão e o horário limite para encerramento do registro tardio (late registration), todos vinculados à **Liga da Evolution** e ao **Clube do Carecas**.
2. **Gerenciamento de Bankroll & Buy-in**:
   - As inscrições respeitam estritamente a política de bankroll e buy-in descrita na aba de Monitoramento de Bankroll.
3. **Fluxo de Registro e Organização**:
   - O bot realiza o registro automático nos torneios selecionados no lobby do clube, abre as janelas e aplica os atalhos de organização de layout do PPPoker.
4. **Assunção de Controle (Gameplay)**:
   - O bot assume o comando das mesas em round-robin, aplicando observação contínua (B09), estado de mão persistente (B06), HUD VIP e mouse anti-cheat.

---

## 3. Guia de Botões e Funcionalidades da Interface Web

### A. Cérebro Pré-Flop (Matriz 169 Mãos · Stack · ICM · PKO)
- **Matriz Interativa 13×13 (169 Mãos)**: Grade clicável exibindo em tempo real todas as combinações (`AA` até `32o`) coloridas por ação estratégica (`Valor/Open`, `3B Light`, `All-In Push`, `Call/Defesa`, `Fold`) e percentual exato de combos do range.
- **Presets de Cenários Pré-Flop**: Botões de 1 clique (*Push/Fold 11 BB no CO (Bolha ICM)*, *Iso-Raise vs 2 Limpers*, *3-Bet Light IP vs Open do CO*, *Call All-In PKO Cobrindo Bounty*).
- **Seletores de Cenário & Posição**: Suporta *RFI (Fold até Hero)*, *Contra Limpers (Iso-Raise)*, *Enfrentando Open Raise*, *Hero Abriu → Enfrenta 3-Bet* e *Enfrentando All-In (Shove)* nas posições `UTG`, `MP`, `CO`, `BTN`, `SB` e `BB`.
- **Controles de Stack, ICM, PKO & Agressividade**: Stack efetivo em BB (ativação automática de Push/Fold Nash `< 14 BB` e Re-Shove `14–19 BB`), fase do torneio (`ChipEV 1.00x`, `Pré-Bolha 1.25x`, `Bolha ITM 1.55x`, `Mesa Final 1.45x`), Bounty Cover (BB), perfil (`Tight / Balanced / Loose`) e HUD Sample Gate (`≥ 30 mãos` para Fold to 3-Bet).
- **Botão `Exportar Range JSON`**: Copia toda a matriz de 169 mãos e a decisão calculada em formato JSON.

### B. Cérebro Pós-Flop (Simulador & Calibrador v2)
- **Seletor de Perfil de Agressividade (`Tight / Balanced / Loose`)**: Ajusta dinamicamente os limiares mínimos de equidade para C-Bet (`48% / 34% / 20%`), Raise/Semi-Blefe (`62% / 46% / 34%`), piso de HUD Fold (`68% / 55% / 45%`) e margem de call contra diferentes perfis de oponentes.
- **Presets de Cenários Reais**: Botões de 1 clique (*Board Seco A-K-4 IP*, *BB Donk-Bet 7-6-5 Conectado*, *River vs Overbet 135% Scare Flush*, *PKO Low SPR Combo Draw 15 Outs*).
- **Parâmetros do Spot v2**: Inclui **Iniciativa Pré-Flop** (`Hero PFR`, `Vilão PFR`, `Pote 3-Bet`, `Limped Pot`), **Carta do Turn/River** (*Brick*, *Overcard*, *Completa Flush*, *Completa Sequência*, *Board Dobra*), **Calculadora de Outs Reais (0–20)**, suporte a **Overbet Polarizado (135%)** na ação do vilão e **Mixagem Estocástica (RNG)** com botão `Sortear Roll`.
- **HUD Sample Size Gate**: Bloqueia automaticamente exploits de HUD caso a amostra registrada do vilão seja inferior a 30 mãos.
- **Saída & Plano Geométrico**: Calcula SPR, Vantagem de Range e de Nuts, Fator EQR, Equidade de Outs, MDF teórico e ajustado ao pool, Pot Odds PKO, plano de apostas geométricas street-a-street, auditoria de regras e botão **Exportar Regra JSON**.

### C. Análise de Mãos (Importação `.txt` PPPoker + Hand Replayer + Auditoria IA)
- **Importar Arquivo (`.txt` / `.log`)**: Área de upload que lê localmente o histórico de mãos do PPPoker via `FileReader`, exibindo pré-contagem imediata de mãos, flops e linhas.
- **Botão `Carregar Exemplo PPPoker (.txt)`**: Carrega um lote realista de mãos da Liga Evolution / Clube do Carecas com leaks pós-flop simulados para testes rápidos sem arquivo local.
- **Botão `Limpar`**: Reseta o arquivo carregado, a pré-visualização e o relatório atual.
- **Hand Replayer Visual (Mesa & Cartas)**: Renderiza visualmente cada mão importada com as cartas do Hero, cartas comunitárias (Flop, Turn e River), botão Dealer (`BTN`), stacks atualizados e pote corrente. Inclui seletor de mão, filtro `Só Pós-Flop`, alternância de baralho (`4 Cores` / `2 Cores`), controles `Início / Anterior / Play / Pausar / Próximo / Fim`, saltos diretos por street (`Pré-Flop`, `Flop`, `Turn`, `River`, `Showdown`) e linha do tempo clicável passo a passo.
- **Contexto da Auditoria (`Nick do Bot` e `Perfil de Agressividade`)**: Permite informar o nick/assento do Hero e o perfil (`tight`, `balanced`, `loose`) utilizado na sessão para comparar as decisões contra os limiares do motor.
- **Botão `Analisar Erros Pós-Flop com IA`**: Envia o histórico para a rota `/api/analyze-hands` no servidor, que usa Gemini para classificar os leaks mais frequentes por categoria, street (`Flop`, `Turn`, `River`, `Multi-Street`), gravidade (`alta`, `media`, `baixa`), spot de exemplo e correção recomendada, exibindo também gráfico de frequência (Recharts) e recomendação de perfil.
- **Botão `Exportar JSON`**: Baixa o relatório estruturado da auditoria pós-flop em formato `.json`.

### D. Monitoramento de Bankroll & Performance
- **Gráfico de Evolução (Saldo vs. EV)**: Gráfico de linha interativo (Recharts) no topo da aba exibindo a curva cronológica do Saldo Real versus o EV Esperado a partir da banca inicial, com tooltip detalhado por data (saldo, EV, resultado do dia e diferença Run vs. EV).
- **Input Manual de Resultados**: Permite cadastrar a data, limite/stake, valor de buy-in, quantidade de torneios e lucro/prejuízo obtido.
- **Cálculo Automático de ROI**: Exibe o Return on Investment acumulado com base nos buy-ins investidos.
- **EV Acumulado**: Compara o lucro real com o Expected Value estimado pelo cérebro GTO.
- **Progresso de Limites**: Recomenda o momento ideal para subida de stake baseado em regras de gestão de banca (ex: 100 buy-ins de margem).

### E. Rotina & Torneios (Evolution)
- Detalha o passo a passo da sessão de torneios para a Liga Evolution e Clube do Carecas.

### F. Guia de Funcionamento (Bíblia)
- Exibe na interface web o resumo vivo das especificações oficiais e tabelas de pesos do motor estratégico.

### G. Evasão Anti-Cheat do Mouse
- Ajustes de curvatura de Bézier (`0.1` a `0.8`) e jitter espacial (`1px` a `10px`).

### H. Painel de Controle (`Bot Control Center`)
- **Iniciar Sessão / Encerrar Sessão**: Controla o loop de observação e execução do bot e exibe os logs em tempo real.

### I. Gerador de Launcher (`.bat`)
- **Baixar INICIAR_SESSAO_EVOLUTION.bat**: Gera o script indetectável em Python nativo.

---

## 4. Especificação Técnica & Tabela de Pesos do Motor Pós-Flop (Guia do Cérebro)

Esta seção define os parâmetros formais utilizados pelo motor `postflopEngine.ts` e que servem de referência direta para calibração do cérebro Python.

### 4.1. Tabela de Equidade Base por Categoria de Mão
| Categoria da Mão (`handCategory`) | Descrição Tática | Equidade Bruta Base |
| :--- | :--- | :---: |
| `nut_value` | Trinca+, Sequência, Flush, Full House+ | **88%** |
| `strong_value` | Top Pair Top Kicker (TPTK) / Overpair | **71%** |
| `medium_showdown` | 2º Par / Top Pair Kicker Fraco | **50%** |
| `combo_draw` | Flush Draw + Open-Ended Straight Draw | **48%** |
| `nut_draw` | Nut Flush Draw ou OESD limpo | **36%** |
| `weak_draw` | Gutshot / Backdoor duplo | **21%** |
| `air` | Sem par e sem projeto relevante | **10%** |

### 4.2. Tabela de Realização de Equidade (EQR) & Desconto Multi-Way
A equidade utilizável pelo cérebro é obtida por: `Equity_Efetiva = min(98%, round(Equity_Bruta * EQR))`.

| Cenário (`heroPosition` + `playersInPot`) | Fator EQR Aplicado | Regra Operacional |
| :--- | :---: | :--- |
| **Heads-Up (2 Jogadores) — IP** | **1.08x** | Realiza acima da equidade bruta por ter controle de posição. |
| **Heads-Up (2 Jogadores) — OOP** | **0.78x** | Desconto de 22% por agir primeiro sem informação. |
| **3-Way — IP** | **0.93x** | `1.08 * 0.86`. Blefes puros bloqueados. |
| **3-Way — OOP** | **0.67x** | `0.78 * 0.86`. Exige valor sólido ou nut draws. |
| **4-Way — IP** | **0.80x** | `1.08 * 0.86²`. Foco estrito em valor e nuts. |
| **4-Way — OOP** | **0.58x** | `0.78 * 0.86²`. Pot control rigoroso; zero blefes. |

### 4.3. Zonas de SPR & Fórmula de Sizing Geométrico
`SPR = Stack_Efetivo_BB / Pote_Atual_BB`

| Zona de SPR | Faixa | Diretriz Estratégica |
| :--- | :---: | :--- |
| **POT COMMIT (All-In Direto)** | `SPR < 1.5` | Prioriza **All-In direto** em qualquer aposta/raise para evitar apostas fracionadas com perda de *fold equity* em potes já comprometidos. |
| **LOW (Compromisso)** | `1.5 ≤ SPR ≤ 2.5` | Zona de stack-off rápido com `strong_value` e `combo_draw` (especialmente em PKO). |
| **MEDIUM (Geométrico)** | `2.5 < SPR ≤ 6.0` | Aplica sizing geométrico constante para distribuir as fichas em `n` streets restantes. |
| **HIGH (Deep / Pot Control)** | `SPR > 6.0` | Exige `nut_value` ou `combo_draw` forte para construir potes grandes; `medium_showdown` faz pot control. |

**Fórmula Geométrica (`calculateGeometricBetPct`):**
$$s = \frac{(1 + 2 \cdot \text{SPR})^{1/n} - 1}{2}$$
Onde `n` é o número de streets restantes (`Flop = 3`, `Turn = 2`, `River = 1`), com resultado limitado entre **20%** e **250%** do pote.

### 4.4. Matriz de Regras Formais (Textura, Range Funil, Blockers, HUD & PKO)
1. **Textura do Board (`boardTexture`)**:
   - `dry_high` / `paired`: Prioriza C-Bet de **33%** do pote em alta frequência (90% para valor, ~65% para blefes qualificados).
   - `wet_connected` / `monotone`: Prioriza sizing polarizado de **66% a 75%** do pote ou check defensivo com mãos médias.
2. **Funil de Range (`villainLine`)**:
   - `capped_check_back`: Autoriza thin value IP com `medium_showdown` (33% pote em board seco HU) e aumenta frequência de blefes IP.
   - `passive_turned_aggressive` *(Pool Exploit Evolution)*: Penaliza *hero calls* no river — `strong_value` passa a exigir `+12%` acima das pot odds para pagar aposta grande, e `medium_showdown` folda automaticamente contra apostas nessa linha.
3. **Blockers (`blockerType`)**:
   - `blocks_nuts_value`: Libera C-Bet blefe em HU e autoriza `RAISE / SHOVE` blefe contra aposta pequena quando combinado com `hudFoldToCbet ≥ 62%` e amostra validada.
   - `blocks_bluffs`: Bloqueia *hero calls* marginais com `medium_showdown` (reduz chance do vilão estar blefando).
4. **HUD Sample Size Gate**:
   - **Piso mínimo:** `hudSampleHands ≥ 30`.
   - Se `< 30` mãos: Gate **BLOQUEADO** — ignora estatísticas de HUD e força linha base GTO.
   - Se `≥ 30` mãos: Gate **LIBERADO** — habilita C-Bet blefe com ar/draw fraco se `hudFoldToCbet ≥ 55%` (em Heads-Up).
5. **Overlay PKO Pós-Flop (`bountyCoverBB`)**:
   - Equivalente em fichas no pote: `PKO_Bonus_BB = bountyCoverBB * 0.45`.
   - Fórmula de Pot Odds ajustada: `Req_Equity = Bet_BB / (Pote_BB + 2 * Bet_BB + PKO_Bonus_BB)`.
6. **Iniciativa Pré-Flop, Range/Nut Advantage & Donk-Bet (`preflopInitiative`)**:
   - Cruza quem foi o agressor pré-flop (`hero_pfr`, `villain_pfr`, `three_bet_pot`, `limped_pot`) com a textura do board. Em `villain_pfr` + board `wet_connected` onde o BB Defender detém Vantagem de Nuts, habilita `DONK BET` OOP (33%–50% pote) com `nut_value` e `combo_draw`.
7. **Scare Cards (Turn/River) & Calculadora de Outs (`turnRiverCard`, `drawOuts`)**:
   - No Turn/River, cartas que completam flush/straight ou dobram o board aplicam penalidade de `-4%` a `-11%` na equidade de `strong_value` e recomendam check/pot control OOP.
   - Outs informados (`1–20`) calculam a probabilidade combinatória exata para Flop e Turn, com fator de *outs sujos* (`0.85x`) em boards pareados ou monotone.
8. **Overbet (135%), MDF & Mixagem Estocástica RNG**:
   - `facing_overbet` aplica `MDF = 1 / (1 + 1.35) ≈ 43%` (reduzido em `0.75x` contra o pool Evolution) e exige `+14%` de equidade extra em `strong_value` sem blockers.
   - O modo `useMixedRng` sorteia um roll `0–99` contra a frequência primária para alternar linhas mistas de forma imprevisível.

### 4.5. Tabela de Limiares Dinâmicos por Perfil de Agressividade (`aggressionProfile`)
| Perfil | Alvo Ideal | Limiar C-Bet (Equity) | Limiar Raise (Equity) | Piso HUD Fold (C-Bet / Raise) | Offset Call | SPR Máx. Raise |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`tight`** | Calling Stations / Maníacos | **≥ 48%** | **≥ 62%** | `68% / 75%` | `+5%` | `1.6` |
| **`balanced`** | GTO Padrão (Default) | **≥ 34%** | **≥ 46%** | `55% / 62%` | `0%` | `2.5` |
| **`loose`** | Nits / Jogadores Passivos | **≥ 20%** | **≥ 34%** | `45% / 52%` | `-4%` | `3.4` |

### 4.6. Regras Formais do Motor Pré-Flop (`preflopEngine.ts`)
1. **Zonas de Stack Efetivo**:
   - **DEEP (`≥ 40 BB`)**: Open padrão `2.1–2.3 BB` (`3.0 BB` do SB), 3-Bet `3x IP / 4x OOP`, *set-mining* com pares baixos e *3-bet light* com `A2s–A5s` e *suited connectors*.
   - **MID-STACK (`20–39 BB`)**: Redução gradual de calls especulativos fora de posição; 4-Bet já compromete stack em faixas menores.
   - **SHORT / RE-SHOVE (`14–19 BB`)**: Substitui 3-Bets tradicionais por **Re-Shove All-In** priorizando força de carta alta e bloqueadores `Ax`/`Kx`.
   - **PUSH / FOLD (`< 14 BB`)**: Modo Nash automático em RFI para maximizar *fold equity*.
2. **Bubble Factor (ICM)**:
   - `ChipEV`: **1.00x** | `Pré-Bolha`: **1.25x** | `Mesa Final`: **1.45x** | `Bolha ITM`: **1.55x**.
   - Ajusta a equidade mínima para pagar all-in via `(PotOdds * BF) / (1 + PotOdds * (BF - 1))`.
3. **Iso-Raise contra Limpers & Bounty Power PKO**:
   - Sizing de isolamento: `3.5 BB + 1.0 BB por limper (+0.5 BB se OOP)`.
   - Quando Hero cobre o bounty (`bountyCoverBB > 0`), soma `bountyCoverBB * 0.45` ao pote efetivo nas pot odds pré-flop.

---

## 5. Protocolo Obrigatório de Atualização
Sempre que uma nova funcionalidade, botão, parâmetro, regra ou peso for adicionado ou calibrado no sistema:
1. Este documento (`/docs/GUIA_FUNCIONAMENTO.md`) **deve ser imediatamente atualizado** nas Seções 3 e 4.
2. A aba correspondente na interface web deve refletir a nova instrução para manter a "Bíblia do Projeto" 100% sincronizada.

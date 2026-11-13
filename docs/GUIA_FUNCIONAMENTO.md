# GUIA DE FUNCIONAMENTO E ARQUITETURA DO VISUALPILOT 2.0
**Liga Evolution & Clube do Carecas (PPPoker Windows Automation Suite)**

---

## 1. Guia Prático: Como Colocar o Bot para Funcionar (Ambiente Windows)

Para iniciar os testes operacionais e de bancada com o VisualPilot 2.0 no Windows, siga rigorosamente o procedimento abaixo:

### Pré-requisitos de Ambiente (Máquina Windows)
1. **Python 3.10 ou superior** instalado no PATH do sistema Windows (certifique-se de marcar "Add Python to PATH" durante a instalação).
2. **Cliente PPPoker Windows** configurado em modo janela padrão (evite redimensionamentos forçados e mantenha a escala de DPI do Windows em 100%).

### Passo 1: Download e Organização dos Arquivos
Certifique-se de possuir a estrutura completa do projeto na máquina:
- O diretório raiz contendo `server.ts`, `src/`, `package.json` e o diretório **`python_bot/`** com todos os módulos de produção (`operar_mesa.py`, `tournament_rotina.py`, pacotes `table_reading/` e `table_discovery/`, módulos de OCR `mss`, controlador de mouse `pyautogui`, etc.).

### Passo 2: Instalação das Dependências Python
Abra o prompt de comando (CMD ou PowerShell) na raiz do projeto e instale as dependências oficiais:
```bash
pip install -r python_bot/requirements.txt
```
*(As dependências incluem `numpy`, `opencv-python`, `mss`, `psutil`, `pyautogui`, `pywin32`, `pillow`, `pytesseract`, `requests`, `dotenv`).*

### Passo 3: Testes de Bancada e Validação Financeira
Antes de abrir mesas reais, valide a integridade do banco de dados SQLite (`bankroll_ledger.db`) e a política financeira executando a rotina de torneios:
```bash
python python_bot/tournament_rotina.py --min-buyins 100 --balance 5000.00 --cost 50.00
```
*Se o saldo for insuficiente ou houver violação de compromissos, o script encerrará com código `1`. Com saldo adequado, prosseguirá com sucesso.*

### Passo 4: Execução do Agente de Mesa (Modo Passivo / Dry-Run / Armado)
Para iniciar o operador na mesa alvo do PPPoker (identificada pelo HWND em hexadecimal, ex: `0x12FA`):
```bash
python python_bot/operar_mesa.py --hwnd 0x12FA --bounty-bb 10.0 --max-tables 6 --arm
```
*   **Modo Padrão (Dry-Run)**: Apenas observa, lê cartas, calcula equidade e registra intenções sem enviar cliques reais.
*   **Modo Armado (`--arm`)**: Utiliza o cursor real com curvas de Bézier e variação espacial natural para interagir com a interface.

---

## 2. Evolução Científica do Cérebro (Pré-Flop & Pós-Flop) — Superando o Empirismo

Para transicionar de heurísticas empíricas para um motor estratégico matematicamente validado (GTO / Nash / ICM / PKO), o VisualPilot 2.0 adota a seguinte arquitetura evolutiva:

### A. Cérebro Pré-Flop: Ranges Validados (HRC / NVT / Nash)
- **Abandono de Fórmulas Cegas**: Substituição gradual de pontuações estáticas por matrizes de 169 mãos baseadas em arquivos JSON de exportação de solvers (HRC / NVT).
- **Abas de Cenários**: O motor consulta diretamente o range específico para RFI, vs_open, vs_3bet, 3-bet, Shove/Fold com factor ICM (<14 BB) e Bônus PKO by Bounty Power.

### B. Cérebro Pós-Flop: Árvores de Decisão Baseadas em Solvers (GTO Wizard / PioSOLVER)
Para evitar que o pós-flop seja baseado em achismos, o motor está estruturado em uma **Árvore de Decisão Paramétrica**:
1. **Classificação de Board & Textura**: Identificação exata de Dry, Wet, Monotone e Paired através do pipeline OCR de naipes e ranks.
2. **Range Advantage & Nut Advantage**: Avaliação matemática da distribuição de combos do range do Herói vs. Vilão com base na agressão pré-flop (Ex: Preflop Aggressor tem vantagem de nuts em boards A-high secos; Caller tem vantagem em boards conectados baixos).
3. **Buckets de Equidade**:
   - *Nut Value / Strong Value*: Decisão orientada por SPR. Se $SPR \le 1.5$, prioriza **All-In direto (Pot Commit)** para maximizar EV e evitar fold equity desperdiçada. Se $SPR > 1.5$, aplica sizing geométrico.
   - *Combo Draws / Nut Draws*: Avaliação de outs reais para apostas por valor de equidade (*semi-bluff*).
   - *Air / Marginais*: Frequência de blefe misturada (*mixed strategy*) indexada por blocos de blockers e frequência de defesa mínima (MDF).
4. **Mixagem e Randomização (RNG)**: Implementação de geradores determinísticos por hash da mão para executar ações mistas (ex: 60% apostar, 40% checar com mãos limítrofes), tornando o bot inexplorável por telemetria e oponentes regulares.

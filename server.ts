import "dotenv/config";
import express from "express";
import path from "path";
import { spawn, ChildProcess } from "child_process";
import { GoogleGenAI, Type } from "@google/genai";

const PORT = 3000;
const MAX_HAND_HISTORY_CHARS = 90000;

let botProcess: ChildProcess | null = null;
const botLogs: string[] = [
  "[INIT] Servidor Express e ponte Python inicializados.",
  "[BRIDGE] Aguardando comando para iniciar operar_mesa.py."
];

interface AnalyzeHandsRequest {
  handHistoryText?: string;
  aggressionProfile?: "tight" | "balanced" | "loose";
  heroName?: string;
}

const aiClient = () =>
  new GoogleGenAI({
    apiKey: process.env.GEMINI_API_KEY,
    httpOptions: {
      headers: {
        "User-Agent": "aistudio-build",
      },
    },
  });

const SYSTEM_INSTRUCTION = `Você é um analista sênior de Poker MTT/PKO (GTO + Exploitative) auditando históricos de mãos exportados do PPPoker (.txt) para o motor estratégico Polaris Poker Automation Suite (Liga Evolution & Clube do Carecas).

Sua missão exclusiva é identificar, classificar e quantificar os ERROS MAIS FREQUENTES DO BOT NAS AÇÕES PÓS-FLOP (Flop, Turn e River).

Use exatamente o framework estratégico do Cérebro Pós-Flop do projeto como referência de auditoria:
1. Fator EQR & Desconto Multi-Way (0.86^(n-2)): Em potes 3-way ou 4-way, especialmente OOP, blefes puros sem equidade/fold equity são erros graves; exija valor sólido ou nut draws.
2. Zonas de SPR & Sizing Geométrico:
   - SPR <= 2.5 (LOW): compromisso rápido com TPTK/Overpair/Combo Draw.
   - 2.5 < SPR <= 6.0 (MEDIUM): sizing geométrico consistente para construir pote em n streets.
   - SPR > 6.0 (HIGH): pot control com mãos médias (2º par / top pair kicker fraco).
3. Perfis de Agressividade e Limiares Dinâmicos:
   - tight: C-Bet >= 48% equity, Raise >= 62%
   - balanced: C-Bet >= 34% equity, Raise >= 46%
   - loose: C-Bet >= 20% equity, Raise >= 34%
4. Exploit do Pool Evolution (Underbluff): Linhas passivas (check-call flop/turn) que viram agressão pesada no river são drasticamente sub-blefadas pelo field. Hero calls marginais com 2º par/showdown médio ou TPTK sem blockers são leaks severos.
5. Textura do Board & Sizing: Boards secos/pareados pedem C-Bet menor (33% pote); boards conectados/monotone pedem sizing polarizado (66%-75%) ou check defensivo.
6. Blockers & PKO Overlay: Avalie se o bot ignorou blockers de nuts para blefar/foldar ou ignorou pot odds ajustadas por bounty PKO em SPR baixo.

Regras de resposta:
- Responda inteiramente em Português (pt-BR), de forma técnica, objetiva e acionável.
- Cite exemplos reais (cartas, board, pote, ação) extraídos do histórico enviado sempre que possível no campo exampleSpot.
- Ordene topMistakes do erro mais frequente/custoso para o menos frequente (entre 3 e 7 categorias distintas, se houver erros no histórico).
- Garanta que frequencyPct represente a participação percentual aproximada daquele erro sobre o total de erros detectados (ou sobre as mãos pós-flop analisadas, de forma coerente).`;

const RESPONSE_SCHEMA = {
  type: Type.OBJECT,
  properties: {
    totalHandsDetected: {
      type: Type.INTEGER,
      description: "Quantidade total de mãos identificadas no arquivo .txt.",
    },
    postflopHandsReviewed: {
      type: Type.INTEGER,
      description: "Quantidade de mãos que chegaram ao flop e foram auditadas.",
    },
    totalMistakesFound: {
      type: Type.INTEGER,
      description: "Total de erros ou leaks pós-flop identificados.",
    },
    overallGrade: {
      type: Type.STRING,
      description: "Nota geral de execução pós-flop (ex: A, B+, B-, C+, C, D).",
    },
    executiveSummary: {
      type: Type.STRING,
      description: "Resumo executivo direto dos principais padrões de erro pós-flop encontrados.",
    },
    recommendedProfile: {
      type: Type.STRING,
      description: "Perfil sugerido para o motor: tight, balanced ou loose.",
    },
    profileAdjustmentReason: {
      type: Type.STRING,
      description: "Explicação do porquê manter ou ajustar o perfil de agressividade do bot.",
    },
    topMistakes: {
      type: Type.ARRAY,
      items: {
        type: Type.OBJECT,
        properties: {
          category: {
            type: Type.STRING,
            description: "Nome curto da categoria do erro (ex: C-Bet Air Multi-Way, Hero Call River Underbluff, Sizing Inadequado em Board Molhado).",
          },
          occurrences: {
            type: Type.INTEGER,
            description: "Número de vezes que este erro ocorreu no histórico.",
          },
          frequencyPct: {
            type: Type.NUMBER,
            description: "Percentual de frequência deste erro (0 a 100).",
          },
          severity: {
            type: Type.STRING,
            description: "Gravidade do leak: alta, media ou baixa.",
          },
          affectedStreet: {
            type: Type.STRING,
            description: "Street principal afetada: Flop, Turn, River ou Multi-Street.",
          },
          description: {
            type: Type.STRING,
            description: "Explicação técnica do erro estratégico cometido.",
          },
          exampleSpot: {
            type: Type.STRING,
            description: "Trecho ou descrição exata de uma mão do histórico que exemplifica o erro.",
          },
          recommendedFix: {
            type: Type.STRING,
            description: "Ajuste concreto nas regras do Cérebro Pós-Flop para corrigir o erro.",
          },
        },
      },
    },
  },
};

async function startServer() {
  const app = express();
  app.use(express.json({ limit: "5mb" }));

  // Python Bot Bridge Endpoints
  app.post("/api/bot/start", (req, res) => {
    if (botProcess && !botProcess.killed) {
      return res.json({ success: true, running: true, message: "O bot python já está em execução." });
    }

    const { hwnd = "0x12FA", bounty = true, bountyMode, overlay = false, mouse = true, reqOverlay, reqHumanMouse } = req.body || {};
    
    // Explicitly reject deprecated flags if requested
    if (overlay || reqOverlay || reqHumanMouse) {
      return res.status(400).json({ success: false, error: "Flags depreciadas (--overlay ou --human-mouse) são rejeitadas explicitamente." });
    }

    const scriptPath = path.resolve(process.cwd(), "python_bot", "operar_mesa.py");
    
    // Strict validation layer for HWNDs: alphanumeric only, stripping commas
    const rawHwnds = String(hwnd).replace(/,/g, " ").trim().split(/\s+/).filter(Boolean);
    const validHwnds: string[] = [];
    for (const h of rawHwnds) {
      const cleanH = h.startsWith("0x") ? h.slice(2) : h;
      if (/^[0-9a-zA-Z]+$/.test(cleanH)) {
        validHwnds.push(h);
      }
    }

    if (validHwnds.length === 0) {
      validHwnds.push("0x12FA");
    }

    const cliArgs = ["--hwnd", ...validHwnds];

    const activeBounty = bountyMode !== undefined ? bountyMode : bounty;
    if (activeBounty) {
      const bountyVal = typeof activeBounty === "number" ? String(activeBounty) : "10";
      cliArgs.push("--bounty-bb", bountyVal);
    }

    if (mouse) {
      cliArgs.push("--arm");
    }
    cliArgs.push("--max-tables", "6");

    botLogs.unshift(`[${new Date().toLocaleTimeString()}] [START] Iniciando python3 operar_mesa.py ${cliArgs.join(" ")}`);

    try {
      botProcess = spawn("python3", [scriptPath, ...cliArgs], { 
        shell: false,
        cwd: path.resolve(process.cwd(), "python_bot"),
        env: { ...process.env, PYTHONPATH: path.resolve(process.cwd(), "python_bot") }
      });

      botProcess.stdout?.on("data", (data) => {
        const text = data.toString().trim();
        if (text) {
          console.log(`[Python OUT] ${text}`);
          botLogs.unshift(`[${new Date().toLocaleTimeString()}] ${text}`);
          if (botLogs.length > 100) botLogs.pop();
        }
      });

      botProcess.stderr?.on("data", (data) => {
        const text = data.toString().trim();
        if (text) {
          console.error(`[Python ERR] ${text}`);
          botLogs.unshift(`[${new Date().toLocaleTimeString()}] [ERR] ${text}`);
          if (botLogs.length > 100) botLogs.pop();
        }
      });

      botProcess.on("close", (code) => {
        botLogs.unshift(`[${new Date().toLocaleTimeString()}] [STOP] Processo python encerrado (código ${code}).`);
        botProcess = null;
      });

      return res.json({ success: true, running: true, message: "Sessão do bot iniciada com sucesso via Python." });
    } catch (err) {
      console.error("Failed to start python bot:", err);
      return res.status(500).json({ success: false, error: "Falha ao iniciar o processo Python operar_mesa.py." });
    }
  });

  app.post("/api/bot/stop", (_req, res) => {
    if (!botProcess) {
      return res.json({ success: true, running: false, message: "O bot já está parado." });
    }

    try {
      botProcess.kill();
      botProcess = null;
      botLogs.unshift(`[${new Date().toLocaleTimeString()}] [STOP] Sessão encerrada manualmente.`);
      return res.json({ success: true, running: false, message: "Sessão encerrada com sucesso." });
    } catch (err) {
      return res.status(500).json({ success: false, error: "Falha ao encerrar processo." });
    }
  });

  app.get("/api/bot/status", (_req, res) => {
    const running = Boolean(botProcess && !botProcess.killed);
    return res.json({ running, logs: botLogs.slice(0, 30) });
  });

  app.post("/api/bot/register-tournaments", (req, res) => {
    const scriptPath = path.resolve(process.cwd(), "python_bot", "tournament_rotina.py");
    const { minBankroll = 100 } = req.body || {};
    const args = [scriptPath, "--min-bankroll", String(minBankroll)];

    botLogs.unshift(`[${new Date().toLocaleTimeString()}] [TOURNAMENT] Iniciando rotina python tournament_rotina.py`);

    try {
      const tourneyProcess = spawn("python", args, { 
        shell: true,
        cwd: path.resolve(process.cwd(), "python_bot"),
        env: { ...process.env, PYTHONPATH: path.resolve(process.cwd(), "python_bot") }
      });
      tourneyProcess.stdout?.on("data", (data) => {
        const text = data.toString().trim();
        if (text) {
          botLogs.unshift(`[${new Date().toLocaleTimeString()}] [Tourney] ${text}`);
          if (botLogs.length > 100) botLogs.pop();
        }
      });
      tourneyProcess.stderr?.on("data", (data) => {
        const text = data.toString().trim();
        if (text) {
          botLogs.unshift(`[${new Date().toLocaleTimeString()}] [Tourney ERR] ${text}`);
          if (botLogs.length > 100) botLogs.pop();
        }
      });
      return res.json({ success: true, message: "Rotina de torneios e bankroll iniciada com sucesso." });
    } catch (err) {
      return res.status(500).json({ success: false, error: "Falha ao executar rotina de torneios." });
    }
  });

  app.post("/api/analyze-hands", async (req, res) => {
    try {
      if (!process.env.GEMINI_API_KEY) {
        return res.status(500).json({
          error:
            "Chave da API Gemini não configurada no ambiente do servidor. Verifique o painel Settings > Secrets.",
        });
      }

      const { handHistoryText, aggressionProfile = "balanced", heroName } =
        (req.body ?? {}) as AnalyzeHandsRequest;

      if (!handHistoryText || typeof handHistoryText !== "string" || handHistoryText.trim().length < 20) {
        return res.status(400).json({
          error: "Envie um histórico de mãos (.txt do PPPoker) válido e com conteúdo suficiente para análise.",
        });
      }

      const trimmedText = handHistoryText.trim();
      const wasTruncated = trimmedText.length > MAX_HAND_HISTORY_CHARS;
      const payloadText = wasTruncated
        ? trimmedText.slice(0, MAX_HAND_HISTORY_CHARS)
        : trimmedText;

      const userPrompt = [
        `Perfil de agressividade configurado atualmente no bot: ${aggressionProfile}`,
        heroName?.trim()
          ? `Identificador/Nick do Hero (bot) nas mãos: ${heroName.trim()}`
          : "Identificador do Hero (bot): detecte automaticamente pelo padrão do histórico (ex: Hero, Dealt to, ou assento marcado).",
        wasTruncated
          ? `Nota: o arquivo original tinha ${trimmedText.length} caracteres e foi limitado aos primeiros ${MAX_HAND_HISTORY_CHARS} caracteres para análise.`
          : "",
        "--- INÍCIO DO HISTÓRICO DE MÃOS (.TXT PPPOKER) ---",
        payloadText,
        "--- FIM DO HISTÓRICO DE MÃOS ---",
      ]
        .filter(Boolean)
        .join("\n\n");

      const ai = aiClient();
      const response = await ai.models.generateContent({
        model: "gemini-4-hydrogen",
        contents: userPrompt,
        config: {
          systemInstruction: SYSTEM_INSTRUCTION,
          responseMimeType: "application/json",
          responseSchema: RESPONSE_SCHEMA,
        },
      });

      const rawJson = (response.text ?? "{}").trim();
      const parsed = JSON.parse(rawJson);

      return res.json({
        analysis: parsed,
        truncated: wasTruncated,
        analyzedChars: payloadText.length,
        originalChars: trimmedText.length,
      });
    } catch (err: unknown) {
      const errorObj = err as { status?: number; message?: string };
      const status = errorObj?.status ?? 500;
      const rawMessage = errorObj?.message ?? "Erro desconhecido ao processar análise de mãos.";

      if (status === 403 || status === 400 || rawMessage.includes("API_KEY_INVALID") || rawMessage.includes("PERMISSION_DENIED")) {
        return res.status(status).json({
          error:
            "Chave da API Gemini inválida ou sem permissão. Verifique e selecione sua chave no painel Settings > Secrets.",
          details: rawMessage,
        });
      }

      if (status === 429 || rawMessage.includes("RESOURCE_EXHAUSTED")) {
        return res.status(429).json({
          error:
            "Limite de requisições da API Gemini atingido (429). Aguarde alguns instantes ou verifique sua cota em Settings > Secrets.",
          details: rawMessage,
        });
      }

      if (status === 404 || rawMessage.includes("NOT_FOUND")) {
        return res.status(404).json({
          error: "Modelo Gemini solicitado não encontrado ou indisponível no momento.",
          details: rawMessage,
        });
      }

      console.error("[POST /api/analyze-hands] Error:", err);
      return res.status(500).json({
        error: "Falha ao analisar o histórico de mãos com a IA. Tente novamente em instantes.",
        details: rawMessage,
      });
    }
  });

  if (process.env.NODE_ENV !== "production") {
    const { createServer: createViteServer } = await import("vite");
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.resolve(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();

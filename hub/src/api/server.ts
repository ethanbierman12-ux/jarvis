/** Hub HTTP API + WebSocket event stream */

import "dotenv/config";
import express from "express";
import cors from "cors";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";
import { hub } from "../hub/orchestrator.js";
import { ephemeral } from "../memory/ephemeral.js";
import { bus } from "../messaging/bus.js";
import { transcribeDeepgram, deepgramBrowserHint } from "../voice/deepgram.js";
import { synthesizeElevenLabs, elevenLabsWidgetConfig } from "../voice/elevenlabs.js";
import { mintLiveKitToken, liveKitConfigured, elevenTurboModel } from "../voice/livekit.js";
import type { HealthSnapshot, SpokeId } from "../types.js";

const HUB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const COMMAND_SEQ_PATH = path.resolve(
  HUB_ROOT,
  "../jarvis/data/command_sequences.json"
);

const started = Date.now();
const PORT = Number(process.env.JARVIS_PORT || 8787);
const HOLOGRAM_URL = process.env.HOLOGRAM_URL || "http://127.0.0.1:3000";

const app = express();
app.use(cors());
app.use(express.json({ limit: "4mb" }));

/** Browser hit on Hub root → send people to the hologram HUD */
app.get("/", (_req, res) => {
  res.redirect(302, HOLOGRAM_URL);
});

app.get("/health", (_req, res) => {
  const snap: HealthSnapshot = {
    ok: true,
    uptimeSec: Math.round((Date.now() - started) / 1000),
    sessions: ephemeral.list().length,
    mockLlm: (process.env.MOCK_LLM || "true").toLowerCase() !== "false",
    spokes: {
      sarah: "idle",
      tom: "idle",
      admin: "idle",
      manager: "idle",
      scholar: "idle",
      stitch: "idle",
      reel: "idle",
      flip: "idle",
      ledger: "idle",
      muse: "idle",
    },
    ts: Date.now(),
  };
  // Reflect latest session statuses if any
  for (const s of ephemeral.list()) {
    for (const r of s.lastResults) {
      snap.spokes[r.spoke as SpokeId] = s.status;
    }
  }
  res.json(snap);
});

/** Primary Hub chat — used by dashboard, n8n, desktop HUD bridge */
app.post("/v1/chat", async (req, res) => {
  try {
    const text = String(req.body?.text || req.body?.message || "");
    const sessionId = req.body?.sessionId as string | undefined;
    const speak = Boolean(req.body?.speak);
    const out = await hub.chat({ text, sessionId });
    let audio: unknown = null;
    if (speak && out.reply) {
      try {
        audio = await synthesizeElevenLabs(out.reply);
      } catch (e) {
        audio = { error: String(e) };
      }
    }
    res.json({ ...out, audio });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

app.post("/v1/halt", (req, res) => {
  const sessionId = String(req.body?.sessionId || "");
  if (!sessionId) return res.status(400).json({ error: "sessionId required" });
  hub.standby(sessionId);
  res.json({ ok: true, halted: true });
});

app.post("/v1/resume", (req, res) => {
  const sessionId = String(req.body?.sessionId || "");
  if (!sessionId) return res.status(400).json({ error: "sessionId required" });
  hub.resume(sessionId);
  res.json({ ok: true, halted: false });
});

app.get("/v1/session/:id", (req, res) => {
  const s = ephemeral.get(req.params.id);
  if (!s) return res.status(404).json({ error: "not found" });
  res.json(s);
});

/** Ethan's learned Jarvis phrases — for hologram command autocomplete */
app.get("/v1/commands", (_req, res) => {
  const counts = new Map<string, number>();
  const bump = (raw: string, n = 1) => {
    const c = raw.trim().replace(/\s+/g, " ");
    if (c.length < 3 || c.length > 120) return;
    const key = c.toLowerCase();
    counts.set(key, (counts.get(key) || 0) + n);
  };
  try {
    if (fs.existsSync(COMMAND_SEQ_PATH)) {
      const data = JSON.parse(fs.readFileSync(COMMAND_SEQ_PATH, "utf8")) as Record<
        string,
        number
      >;
      for (const [seq, n] of Object.entries(data)) {
        const weight = typeof n === "number" ? n : 1;
        for (const part of seq.split(/\u2192|->/)) {
          bump(part, weight);
        }
      }
    }
  } catch {
    /* ignore corrupt file */
  }
  // Always include Hub spoke demos
  for (const demo of [
    "Schedule a meeting with the client who complained in support",
    "Draft a reply to the open support ticket",
    "Investigate the checkout bug and open a PR",
    "Approve and merge the PR",
    "surprise me",
    "standby",
    "hub status",
  ]) {
    bump(demo, 50);
  }
  const commands = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 80)
    .map(([text, score]) => ({ text, score }));
  res.json({ commands, source: COMMAND_SEQ_PATH });
});

app.get("/v1/sessions", (_req, res) => {
  res.json(ephemeral.list().map((s) => ({
    id: s.id,
    status: s.status,
    halted: s.halted,
    updatedAt: s.updatedAt,
    turns: s.turns.length,
  })));
});

/** Deepgram upload STT */
app.post("/v1/stt", express.raw({ type: "*/*", limit: "12mb" }), async (req, res) => {
  try {
    const buf = Buffer.isBuffer(req.body) ? req.body : Buffer.from([]);
    const mime = String(req.headers["content-type"] || "audio/wav");
    const out = await transcribeDeepgram(buf, mime);
    res.json({ ...out, hint: deepgramBrowserHint });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

/** ElevenLabs TTS */
app.post("/v1/tts", async (req, res) => {
  try {
    const text = String(req.body?.text || "");
    const out = await synthesizeElevenLabs(text);
    res.json(out);
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

app.get("/v1/voice/config", (_req, res) => {
  res.json({
    deepgram: deepgramBrowserHint,
    elevenlabs: elevenLabsWidgetConfig(),
    livekit: { configured: liveKitConfigured(), model: elevenTurboModel() },
  });
});

/** LiveKit room token for hologram duplex (<500ms path when infra is up) */
app.post("/v1/livekit/token", async (req, res) => {
  try {
    const identity = String(req.body?.identity || "jarvis-hologram");
    const room = String(req.body?.room || "jarvis-ops");
    const out = await mintLiveKitToken({ identity, room });
    res.status(out.ok ? 200 : 503).json(out);
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

/** Inbound webhook — e.g. Slack slash / n8n → Hub */
app.post("/v1/hooks/inbound", async (req, res) => {
  const text = String(req.body?.text || req.body?.message || req.body?.event?.text || "");
  const sessionId = req.body?.sessionId as string | undefined;
  if (!text) return res.status(400).json({ error: "text required" });
  const out = await hub.chat({ text, sessionId });
  res.json(out);
});

/** Spoke callback webhook (external agents can POST results) */
app.post("/v1/hooks/spoke/:id", (req, res) => {
  const spoke = req.params.id;
  bus.publish("spoke.result", {
    spoke,
    ok: Boolean(req.body?.ok ?? true),
    summary: String(req.body?.summary || "external spoke update"),
    data: req.body?.data,
  });
  res.json({ ok: true });
});

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: "/v1/events" });

wss.on("connection", (ws) => {
  ws.send(JSON.stringify({ type: "hello", ts: Date.now() }));
  const onEvent = (ev: unknown) => {
    if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(ev));
  };
  bus.on("event", onEvent);
  ws.on("close", () => bus.off("event", onEvent));
});

server.on("error", (err: NodeJS.ErrnoException) => {
  if (err.code === "EADDRINUSE") {
    console.error(
      `Port ${PORT} is already in use.\n` +
        `  PowerShell: Get-NetTCPConnection -LocalPort ${PORT} | % { Stop-Process -Id $_.OwningProcess -Force }\n` +
        `  Or set JARVIS_PORT=8788 in .env`
    );
    process.exit(1);
  }
  throw err;
});

server.listen(PORT, () => {
  console.log(`JARVIS Hub listening on http://127.0.0.1:${PORT}`);
  console.log(`  GET  /           → redirect hologram ${HOLOGRAM_URL}`);
  console.log(`  POST /v1/chat   GET /health   WS /v1/events`);
  console.log(`  POST /v1/livekit/token`);
  console.log(`  MOCK_LLM=${process.env.MOCK_LLM ?? "true"}`);
});

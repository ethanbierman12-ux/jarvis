"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chat, halt, health, HUB_URL, type ChatResponse } from "@/lib/api";

type LogLine = { ts: number; text: string };

const EXAMPLES = [
  "Schedule a meeting with the client who complained in support",
  "Draft a reply to the open support ticket",
  "Investigate the checkout bug and open a PR",
  "standby",
];

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [halted, setHalted] = useState(false);
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [hp, setHp] = useState<{
    ok?: boolean;
    uptimeSec?: number;
    sessions?: number;
    mockLlm?: boolean;
  }>({});
  const [lastPlan, setLastPlan] = useState<ChatResponse["plan"] | null>(null);
  const [spokeStats, setSpokeStats] = useState<Record<string, string>>({
    sarah: "idle",
    tom: "idle",
    admin: "idle",
  });
  const recogRef = useRef<SpeechRecognition | null>(null);

  const pushLog = useCallback((text: string) => {
    setLogs((prev) => [{ ts: Date.now(), text }, ...prev].slice(0, 80));
  }, []);

  useEffect(() => {
    const tick = async () => {
      try {
        const h = await health();
        setHp(h);
      } catch {
        setHp({ ok: false });
      }
    };
    tick();
    const id = setInterval(tick, 4000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    try {
      const url = HUB_URL.replace(/^http/, "ws") + "/v1/events";
      ws = new WebSocket(url);
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.type === "hub.log") {
            pushLog(String(data.payload?.line || JSON.stringify(data.payload)));
          } else if (data.type === "spoke.result") {
            const r = data.payload;
            setSpokeStats((s) => ({ ...s, [r.spoke]: r.ok ? "done" : "error" }));
            pushLog(`[${r.spoke}] ${r.summary}`);
            setMessages((m) => [...m, { role: r.spoke, text: r.summary }]);
          } else if (data.type === "hub.halt") {
            setHalted(true);
            pushLog("HALT — agent chain stopped");
          } else if (data.type === "hub.plan") {
            pushLog(`PLAN · ${data.payload?.plan?.reason || "routed"}`);
          }
        } catch {
          /* ignore */
        }
      };
    } catch {
      pushLog("WebSocket unavailable — polling health only");
    }
    return () => ws?.close();
  }, [pushLog]);

  const playAudio = (audio?: ChatResponse["audio"]) => {
    if (!audio?.audioBase64) return;
    const src = `data:${audio.mime || "audio/mpeg"};base64,${audio.audioBase64}`;
    const a = new Audio(src);
    void a.play().catch(() => undefined);
  };

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: t }]);
    setInput("");
    try {
      const out = await chat(t, sessionId, true);
      setSessionId(out.sessionId);
      setHalted(out.halted);
      setLastPlan(out.plan);
      setMessages((m) => [...m, { role: "jarvis", text: out.reply }]);
      for (const r of out.results || []) {
        setSpokeStats((s) => ({ ...s, [r.spoke]: r.needsHitl ? "waiting_hitl" : "done" }));
      }
      playAudio(out.audio);
      pushLog(`JARVIS · ${out.reply.slice(0, 140)}`);
    } catch (e) {
      pushLog(`ERROR · ${String(e)}`);
      setMessages((m) => [
        ...m,
        { role: "jarvis", text: `Hub unreachable at ${HUB_URL}. Start npm run dev:server.` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const startVoice = () => {
    const SR =
      typeof window !== "undefined"
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;
    if (!SR) {
      pushLog("Web Speech API unavailable — use Deepgram key + /v1/stt for production STT");
      return;
    }
    const recog = new SR();
    recog.lang = "en-US";
    recog.interimResults = false;
    recog.onresult = (ev: SpeechRecognitionEvent) => {
      const transcript = ev.results[0][0].transcript;
      void send(transcript);
    };
    recog.onerror = () => pushLog("Voice recognition error");
    recogRef.current = recog;
    recog.start();
    pushLog("Listening (browser STT)…");
  };

  const statusDot = useMemo(() => {
    if (hp.ok === false) return "bad";
    if (halted) return "warn";
    return "ok";
  }, [hp.ok, halted]);

  return (
    <main className="shell">
      <header className="header">
        <div>
          <div className="brand">
            JARVIS
            <span>HUB & SPOKE · MULTI-AGENT OPS</span>
          </div>
        </div>
        <div className="pill">
          <span className={`dot ${statusDot}`} />
          {hp.ok === false ? "HUB OFFLINE" : halted ? "STANDBY" : "SYSTEMS NOMINAL"}
          {hp.mockLlm ? " · MOCK LLM" : " · CLAUDE"}
        </div>
      </header>

      <div className="stats">
        <div className="stat">
          <span>UPTIME</span>
          <b>{hp.uptimeSec ?? "—"}s</b>
        </div>
        <div className="stat">
          <span>SESSIONS</span>
          <b>{hp.sessions ?? 0}</b>
        </div>
        <div className="stat">
          <span>HUB</span>
          <b style={{ fontSize: 14 }}>{HUB_URL.replace("http://", "")}</b>
        </div>
      </div>

      <div className="grid">
        <section className="panel chat">
          <h2>COMMAND DECK</h2>
          <div className="core" aria-hidden />
          <div className="messages">
            {messages.length === 0 && (
              <div className="bubble jarvis">
                Online. Try the multi-agent example: schedule a meeting with the client who
                complained in support. Say <b>standby</b> to halt all spokes.
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`bubble ${
                  m.role === "user" ? "user" : m.role === "jarvis" ? "jarvis" : "spoke"
                }`}
              >
                <strong style={{ opacity: 0.7 }}>{m.role.toUpperCase()} · </strong>
                {m.text}
              </div>
            ))}
          </div>
          <div className="row">
            <input
              value={input}
              placeholder="Speak or type an order…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void send(input)}
              disabled={busy}
            />
            <button type="button" onClick={() => void send(input)} disabled={busy}>
              EXECUTE
            </button>
            <button type="button" className="ghost" onClick={startVoice}>
              MIC
            </button>
            <button
              type="button"
              className="danger"
              onClick={() => {
                if (sessionId) void halt(sessionId);
                setHalted(true);
                void send("standby");
              }}
            >
              STANDBY
            </button>
          </div>
          <div className="hints">
            {EXAMPLES.map((ex) => (
              <div key={ex}>
                →{" "}
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    void send(ex);
                  }}
                >
                  {ex}
                </a>
              </div>
            ))}
          </div>
          {lastPlan && (
            <div className="hints" style={{ marginTop: 12 }}>
              PLAN · {lastPlan.reason}
              {lastPlan.steps?.length
                ? ` → ${lastPlan.steps.map((s) => s.spoke).join(" → ")}`
                : " (hub only)"}
            </div>
          )}
        </section>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <section className="panel">
            <h2>SPOKES</h2>
            <div className="agents">
              {(
                [
                  ["sarah", "Support / Email"],
                  ["tom", "Developer / PRs"],
                  ["admin", "Calendar / Notion"],
                ] as const
              ).map(([id, role]) => (
                <div className="agent" key={id}>
                  <div>
                    <strong>{id.toUpperCase()}</strong>
                    <div>
                      <em>{role}</em>
                    </div>
                  </div>
                  <span className="pill" style={{ textTransform: "uppercase" }}>
                    {spokeStats[id] || "idle"}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel">
            <h2>EVENT STREAM</h2>
            <div className="log">
              {logs.length === 0 && "Waiting for Hub events…"}
              {logs.map((l) => (
                <div key={l.ts + l.text}>
                  [{new Date(l.ts).toLocaleTimeString()}] {l.text}
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  chat,
  fetchCommands,
  halt,
  health,
  resume,
  HUB_URL,
  type ChatResponse,
} from "@/lib/api";

type LogLine = { id: string; ts: number; text: string };

const FALLBACK_COMMANDS = [
  "Schedule a meeting with the client who complained in support",
  "Draft a reply to the open support ticket",
  "Investigate the checkout bug and open a PR",
  "Approve and merge the PR",
  "surprise me",
  "standby",
  "open camera",
  "look at my screen",
  "show stats",
  "hub status",
];

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [halted, setHalted] = useState(false);
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [commands, setCommands] = useState<string[]>(FALLBACK_COMMANDS);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [activeSuggest, setActiveSuggest] = useState(0);
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
  const [waveLive, setWaveLive] = useState(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const recogRef = useRef<SpeechRecognition | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number>(0);
  const phaseRef = useRef(0);
  const logSeq = useRef(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const pushLog = useCallback((text: string) => {
    logSeq.current += 1;
    const id = `${Date.now()}-${logSeq.current}`;
    setLogs((prev) => [{ id, ts: Date.now(), text }, ...prev].slice(0, 80));
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
    void fetchCommands().then((list) => {
      if (list.length) setCommands(list);
    });
  }, []);

  const suggestions = useMemo(() => {
    const q = input.trim().toLowerCase();
    if (!q) return commands.slice(0, 8);
    return commands.filter((c) => c.toLowerCase().includes(q)).slice(0, 8);
  }, [commands, input]);

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
            setSpokeStats((s) => ({
              ...s,
              [r.spoke]: r.needsHitl ? "waiting_hitl" : r.ok ? "done" : "error",
            }));
            // Logs + spoke panel only — chat already gets the JARVIS synthesis
            pushLog(`[${r.spoke}] ${r.summary}`);
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

  // Audio waveform hologram
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      phaseRef.current += waveLive ? 0.18 : 0.05;
      const mid = h / 2;
      ctx.strokeStyle = waveLive ? "rgba(0,240,255,0.9)" : "rgba(0,240,255,0.35)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let x = 0; x < w; x++) {
        const amp = waveLive ? 18 : 8;
        const y =
          mid +
          Math.sin(x * 0.045 + phaseRef.current) * amp +
          Math.sin(x * 0.11 + phaseRef.current * 1.7) * (amp * 0.35);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.strokeStyle = "rgba(255,193,74,0.35)";
      ctx.beginPath();
      for (let x = 0; x < w; x++) {
        const y = mid + Math.cos(x * 0.03 - phaseRef.current) * (waveLive ? 10 : 4);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      rafRef.current = requestAnimationFrame(draw);
    };
    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [waveLive]);

  const playAudio = (audio?: ChatResponse["audio"]) => {
    if (!audio?.audioBase64) return;
    const src = `data:${audio.mime || "audio/mpeg"};base64,${audio.audioBase64}`;
    const a = new Audio(src);
    setWaveLive(true);
    a.onended = () => setWaveLive(false);
    void a.play().catch(() => setWaveLive(false));
  };

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: t }]);
    setInput("");
    const t0 = performance.now();
    try {
      // Clear sticky standby before routing the next real command
      if (halted && sessionId && !/^\s*(standby|abort|exit)\b/i.test(t)) {
        try {
          await resume(sessionId);
          setHalted(false);
        } catch {
          /* hub may auto-resume on chat */
        }
      }
      const out = await chat(t, sessionId, true);
      setLatencyMs(Math.round(performance.now() - t0));
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
      pushLog("Web Speech API unavailable — use LiveKit/Deepgram path for production STT");
      return;
    }
    const recog = new SR();
    recog.lang = "en-GB";
    recog.interimResults = false;
    recog.onresult = (ev: SpeechRecognitionEvent) => {
      const transcript = ev.results[0][0].transcript;
      void send(transcript);
    };
    recog.onerror = () => {
      setWaveLive(false);
      pushLog("Voice recognition error");
    };
    // SpeechRecognition typings omit onend in some lib.dom versions
    (recog as SpeechRecognition & { onend: (() => void) | null }).onend = () =>
      setWaveLive(false);
    recogRef.current = recog;
    recog.start();
    setWaveLive(true);
    pushLog("Listening (hologram mic)…");
  };

  const statusDot = useMemo(() => {
    if (hp.ok === false) return "bad";
    if (halted) return "warn";
    return "ok";
  }, [hp.ok, halted]);

  return (
    <main className="holo-shell">
      <div className="holo-grid" aria-hidden />
      <header className="header">
        <div className="brand">
          JARVIS
          <span>HOLOGRAM HUD · TACTICAL MULTI-AGENT OPS</span>
        </div>
        <div className="pill">
          <span className={`dot ${statusDot}`} />
          {hp.ok === false ? "HUB OFFLINE" : halted ? "STANDBY" : "SYSTEMS NOMINAL"}
          {hp.mockLlm ? " · MOCK LLM" : " · LIVE"}
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
          <span>RTT</span>
          <b>{latencyMs != null ? `${latencyMs}ms` : "—"}</b>
        </div>
        <div className="stat">
          <span>HUB</span>
          <b style={{ fontSize: 13 }}>{HUB_URL.replace("http://", "")}</b>
        </div>
      </div>

      <div className="wave-wrap" aria-hidden>
        <canvas ref={canvasRef} />
      </div>

      <div className="grid">
        <section className="panel chat">
          <h2>COMMAND DECK</h2>
          <div className="core" aria-hidden />
          <div className="messages">
            {messages.length === 0 && (
              <div className="bubble jarvis">
                Hologram online, Sir. UI is{" "}
                <b>http://127.0.0.1:3000</b> — Hub API is{" "}
                <b>http://127.0.0.1:8787</b>. Try a spoke chain, or say <b>surprise me</b>.
                MIC uses browser STT; LiveKit+ElevenLabs turbo when Hub keys are set.
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
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault();
              setSuggestOpen(false);
              void send(input);
            }}
          >
            <div className="row-input-wrap">
              <input
                ref={inputRef}
                value={input}
                placeholder="Type your command — Tab to complete, Enter to run…"
                autoComplete="off"
                disabled={busy}
                onChange={(e) => {
                  setInput(e.target.value);
                  setSuggestOpen(true);
                  setActiveSuggest(0);
                }}
                onFocus={() => setSuggestOpen(true)}
                onBlur={() => {
                  window.setTimeout(() => setSuggestOpen(false), 150);
                }}
                onKeyDown={(e) => {
                  if (!suggestOpen || suggestions.length === 0) return;
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setActiveSuggest((i) => (i + 1) % suggestions.length);
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setActiveSuggest(
                      (i) => (i - 1 + suggestions.length) % suggestions.length
                    );
                  } else if (e.key === "Tab") {
                    e.preventDefault();
                    setInput(suggestions[activeSuggest] || input);
                    setSuggestOpen(false);
                  } else if (e.key === "Escape") {
                    setSuggestOpen(false);
                  }
                }}
              />
              {suggestOpen && suggestions.length > 0 && (
                <ul className="suggest" role="listbox">
                  {suggestions.map((s, i) => (
                    <li key={s} role="option" aria-selected={i === activeSuggest}>
                      <button
                        type="button"
                        className={i === activeSuggest ? "active" : undefined}
                        onMouseDown={(ev) => {
                          ev.preventDefault();
                          setInput(s);
                          setSuggestOpen(false);
                          void send(s);
                        }}
                      >
                        {s}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="row-actions">
              <button type="submit" disabled={busy}>
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
                  setMessages((m) => [
                    ...m,
                    { role: "jarvis", text: "Standing by. All agent operations halted." },
                  ]);
                  pushLog("STANDBY · agents halted");
                }}
              >
                STANDBY
              </button>
              {halted && (
                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    if (sessionId) void resume(sessionId);
                    setHalted(false);
                    pushLog("RESUME · systems online");
                  }}
                >
                  RESUME
                </button>
              )}
            </div>
          </form>
          <div className="livekit-bar">
            <span>
              Voice path:{" "}
              <span className="live">ElevenLabs turbo · optional LiveKit room</span>
            </span>
            {latencyMs != null && latencyMs < 500 && (
              <span className="live">Sub-500ms hub RTT hit</span>
            )}
          </div>
          <div className="hints">
            {commands.slice(0, 6).map((ex) => (
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
                <div key={l.id}>
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

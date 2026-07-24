# Jarvis FAQs

Concise answers for desk ops. Deep dives live in the linked handovers.

---

## Boot / run

**How do I start Jarvis?**  
`run.bat` — watchdog (`runner.py`) keeps the process alive. See [README](../README.md).

**What do exit codes mean?**  
`0` = intentional reload · `99` = offline / closed · other = crash (watchdog recovers ~5s).

**What is the boot sequence?**  
HUD shows INITIATING SYSTEM → loading % → boot sound → main HUD.

---

## Voice / F5 / hotkeys

**How do I wake or soft-reload?**  
**F5** via `install_f5_wake.bat` / `run.bat wake`: launches when closed; soft-reloads when open. HUD-focused F5 also reloads if the wake agent is not armed.

**Why does Jarvis wake / talk on his own?**  
Voice now requires the wake word (**Jarvis**) unless you are in the short “armed” window after he says “Yes?”. Ambient TV/chat is ignored. Say **wake word only** (default) or **always listen** to toggle. Also try **suggestions off** if tips feel like random speech.

**How do I stop or reload by voice?**  
`go offline` / `power down` · `reload core` / `reboot jarvis` · emergency kill `Ctrl+Alt+K`.

**Mic picks up game audio / Voicemeeter?**  
Keep `mic_reject_loopback` true; set `mic_prefer` to a physical device. See [VOICEMEETER.md](VOICEMEETER.md) and rule `jarvis-integrations`.

**British TTS vs ElevenLabs?**  
Default Edge `en-GB-ThomasNeural`. ElevenLabs only if `tts_prefer_elevenlabs` is enabled. [HANDOVER_ROUTER.md](HANDOVER_ROUTER.md)

---

## Phone companion / ntfy

**Command Jarvis from iPhone abroad?**  
Tailscale on PC + phone → say `open phone companion` → Safari → Add to Home Screen (`:8766`). [HANDOVER_COMPANION.md](HANDOVER_COMPANION.md)

**Push alerts to phone without companion?**  
`link my phone` + ntfy app subscribe. Then `text my phone …` / `ping my phone`. [INTEGRATIONS.md](INTEGRATIONS.md)

**Companion zip?**  
Say `companion zip` — export under Desktop / `jarvis/data/exports/`.

---

## Manus

**How do I link Manus?**  
Create key at manus.im → voice `set manus key to …` (DPAPI vault) or `link manus`. Never paste keys into chat. [HANDOVER_MANUS.md](HANDOVER_MANUS.md)

**Ask Manus / review code?**  
`ask manus …` · `manus review` · `manus follow up …` · `manus result`.

---

## Security / intruder / night vision

**False intruder alerts?**  
Re-enroll (`enroll my face`), or `intruder alerts off`. Match uses debounce + cooldown. [HANDOVER_SECURITY.md](HANDOVER_SECURITY.md)

**Night vision turns on in daytime?**  
Auto NV uses `settings.timezone` (not raw PC local). Force: `night vision off` or `night vision auto off`.

**Secure the desk?**  
`secure desk` · `enroll my face` · `security status` · `security off`.

---

## Map / camera / PDTester / spatial

**Maps?**  
`Navigate to …` / map gestures — swipe up/down for map open/close via gesture commander. [HANDOVER_SECURITY.md](HANDOVER_SECURITY.md)

**Second monitor digests?**  
`open pdtester` / `show digests`. [HANDOVER_PDTESTER.md](HANDOVER_PDTESTER.md)

**Spatial gestures?**  
Camera open → pinch/swipe layouts. `spatial gestures on|off`. [HANDOVER_SPATIAL.md](HANDOVER_SPATIAL.md)

---

## Suggestions / quiet mode / desk cmds

**Suggestion cascade after “yes”?**  
Fixed with suppress window; say `suggestions off` / `stop suggesting`. [HANDOVER_ADDITIVE.md](HANDOVER_ADDITIVE.md)

**Quiet / desk ready / full status?**  
`quiet mode` · `loud mode` · `desk ready` · `full status` · `upgrade status`.

**Upgrade check / recent errors?**  
`upgrade check` · `self health` · `health check` — desk readiness blurb.  
`recent errors` · `show errors` · `log errors` — spam-filtered log summary.  
[HANDOVER_UPGRADE.md](HANDOVER_UPGRADE.md)

---

## Hub agents (Sarah / Tom / Admin)

**When does Hub run?**  
Explicit `ask sarah|tom|admin …` or complex hub-marked research. Simple desk intents are **force_local**. [HANDOVER_ROUTER.md](HANDOVER_ROUTER.md)

---

## Integrations (HA / n8n / macros / MCP)

**Silent stop from Stream Deck?**  
`http://127.0.0.1:8765/macro?cmd=stop` — [INTEGRATIONS.md](INTEGRATIONS.md)

**n8n from voice?**  
`trigger n8n <webhook-path>`.

**Cursor MCP (Buffer, Gmail, Stripe, Notion)?**  
Copy `.cursor/mcp.json.example` → `.cursor/mcp.json`, then **Connect** each server in Cursor Settings → Tools & MCP. n8n / Meta Ads / RevenueCat were removed from MCP (Meta DCR block, local n8n hassle, RevenueCat left by choice) — see [HANDOVER_MCP.md](HANDOVER_MCP.md).

---

## Productivity extras

Auto-commit, calendar ICS, news, price watch, voice-to-code, proactive nudges: [HANDOVER_PRODUCTIVITY.md](HANDOVER_PRODUCTIVITY.md)

---

## Cursor subagents (this repo)

| Invoke / name | Path | Use for |
|---------------|------|---------|
| `jarvis-desk-debugger` | `.cursor/agents/jarvis-desk-debugger.md` | Boot, voice, security, NV, router bugs |
| `jarvis-integrations` | `.cursor/agents/jarvis-integrations.md` | MCP, n8n, Manus, HA, companion |
| `jarvis-ui-hud` | `.cursor/agents/jarvis-ui-hud.md` | PyQt HUD, widgets, styles |

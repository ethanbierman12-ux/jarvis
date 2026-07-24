# Handover — Additive Jarvis Upgrade

Safe additive passes. Existing command handlers were **not removed** unless fixing a clear bug.

---

## 2026-07-24 — Performance / smooth HUD

Measurable lag pass: camera paint, waveform/weather timers, log cap, mic stylesheet throttle, folder-watch flush, voice **smooth mode**. See [HANDOVER_PERF.md](HANDOVER_PERF.md).

---

## 2026-07-23 evening — Upgrade / self-health

Logging recursion fix, **upgrade check** / self health, **recent errors**, computer-use `missing_guidance` polish. See [HANDOVER_UPGRADE.md](HANDOVER_UPGRADE.md).

---

## 2026-07-23 — Computer use / browser agent

Additive screenshot→LLM→action loop (`computer_use_agent.py`) with **Ollama free/local** default preference, Anthropic + OpenAI paid fallbacks, optional browser-use (cloud or ChatOllama). Voice: `computer use provider local` · `computer use …` · HITL for long runs · keys via vault. See `docs/HANDOVER_COMPUTER_USE.md`.

---

## 2026-07-23 — Cinematic polish + smart desk

### Night vision timezone fix
- **Root cause:** `_is_night_hours` used PC local hour; desk preference is `timezone: America/New_York` while the machine may be UTC+8 → NV during NY daytime.
- **Fix:** settings-timezone hour + overnight window helpers; `_nv_user_on` / `_nv_user_off`; never auto-enable in day; optional bright-frame skip.
- Voice: `night vision on/off`, `night vision auto on/off`

### Errors checked
- Python 3.13 imports: `brain`, `security_gate`, `manus_*`, `companion_server`, `voice`, `commands` — **OK**
- AST parse of all `jarvis/**/*.py` — **0 syntax errors**
- `jarvis/data/autobug/last_error.txt` — empty
- UI widgets import under `QT_QPA_PLATFORM=offscreen` — **OK**

### UI (refined, not busier)
- Stronger **JARVIS** brand hierarchy; quieter subtitle (`EXECUTIVE SYSTEMS`)
- Glass panels with cyan top edge; softer Ghost/Danger buttons; quieter log
- Tighter margins; panic hint collapsed to `⌃⇧P`; command monitor stays hidden by default
- Clock label shortened to **TIME**

### New voice commands
| Say | Effect |
|-----|--------|
| **quiet mode** / mute alerts / do not disturb | Mute mic + silence intruder alerts |
| **loud mode** / unmute alerts | Restore mic + prior alert setting |
| **desk ready** | Coding lights + mic live (+ exit quiet) |
| **full status** | One-line CPU/RAM · security · companion · Manus · Hub |
| **upgrade status** / feature status | Registry snapshot |
| **summarize my day** | Weather + habits/schedule recap |
| **summarize clipboard** | Soft clipboard digest |
| *(prior)* intruder alerts off · manus review · enroll · ask sarah/tom/admin | unchanged |

Fast-local set includes the new desk cmds so they skip Hub/memory lag.

### Suggestion cascade fix (same day)
- **Root cause:** HUD accept left `pending_cmd` set; `after_command` + sequence hints immediately queued another tip after yes (workspace → playlist → lights…).
- **Fix:** `SuggestionEngine.accept()` clears pending + **5 min suppress**; voice/chip yes set `_skip_suggestion_followups`; ambient speak cooldown 6 min; `after_command` gated by suppress + 120s gap.
- Voice: **`suggestions off`** / **`stop suggesting`** · **`suggestions on`**

---

## 2026-07-19 — Registry / workflows / monitor

| Area | Path | What changed |
|------|------|----------------|
| Feature freeze | `jarvis/core/feature_registry.py` | Registry + freeze during upgrade |
| Workflows | `jarvis/core/workflows.py` | Morning / night / focus / standup / secure |
| Command monitor UI | `jarvis/ui/widgets/command_monitor.py` | Right-rail telemetry |
| Aliases | `jarvis/core/commands.py` | Workflow/registry/disk/lamp/monitor shortcuts |
| Brain wire | `jarvis/brain.py` | Freeze gate, workflows, upgrade freeze/unfreeze |
| HUD | `jarvis/ui/main_window.py` | CommandMonitor + request_ui slots |

### Safety
- New paths wrapped in `try/except`
- Freeze allowlist still permits upgrade/help/status/quiet during upgrade
- No secrets committed

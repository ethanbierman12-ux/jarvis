# Handover — Productivity + Live Context Suite (2026-07-20)

Additive only. Existing `proactive.py` (ReturnBrief / WeatherGuard / SequenceLearner) was briefly overwritten and **restored from git**; new agent lives in `proactive_agent.py`.

## New modules

| Module | Role |
|--------|------|
| `live_context.py` | Exact date/time + weather facts every turn |
| `mood_engine.py` | Energy / patience / banter + 10‑min short-term memory |
| `proactive_agent.py` | High CPU, late-night, 2h stare nudges |
| `github_autocommit.py` | Stage + clean commit message + optional push |
| `smart_calendar.py` | “next Tuesday at 3” → ICS + open |
| `topic_monitor.py` | Tech / gaming / marketing RSS |
| `price_monitor.py` | Watch URLs, alert on drops |
| `media_presence.py` | Pause media when you stand (webcam) |
| `voice_to_code.py` | Dictate → paste into focused editor |
| `voice_waveform.py` | Neon mic amplitude bars on HUD |

## Voice commands (new)

- `auto commit` / `auto commit and push` / `git status`
- `schedule design review next Tuesday at 3`
- `tech news` / `gaming news` / `marketing news`
- `watch price for AirPods at https://…` / `check prices`
- `start voice to code` → speak → `commit code`
- `mood status` / `proactive on|off`
- `what time` / `weather` now include full live date grounding
- Media pause follows presence automatically (toggle: `media pause on stand`)

## Settings

`github_auto_push`, `proactive_enabled`, `media_pause_on_stand` in `config.py` / `settings.json`.

## Safety

- All new paths try/except wrapped
- Git skips `.env` / credential-like paths
- Calendar writes local ICS (Google import) — no OAuth required in this pass

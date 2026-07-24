# Handover — Upgrade / self-health (2026-07-23 evening)

Additive desk health pass. Prefer **local Ollama**. `wake_required` unchanged. `theme_sync_windows` stays **false**. No commit in this pass.

## Logging recursion fix

- `SafeRotatingFileHandler` + `PrintLogger` reentrancy guards in `jarvis/core/logging_setup.py`
- Stops the historical `Message:` / `--- Logging error ---` spam loop when stderr is teed into logging
- Root cause was WinError 32 on log rollover while stderr was teed into logging

## Upgrade check / self health

- Module: `jarvis/core/health_check.py` → `build_upgrade_check`
- Voice: `upgrade check` · `self health` · `health check` · `desk health` · `system health`
- Spoken one-liner: recent log issues · computer-use readiness · cloud links · companion/Manus/Hub/sec · wake

## Recent errors

- `recent_errors_blurb()` — spam-filtered scan of `jarvis.log` + optional autobug note
- Log scan ignores historical recursion spam and only counts ERROR/WARNING from the last 3 calendar days
- Voice: `recent errors` · `show errors` · `show recent errors` · `log errors`
- Fast-local + FREEZE_ALLOW + semantic force_local (facts lane)

## Computer use polish

- `missing_guidance()` surfaces what’s blocking CU
- Richer upgrade-check CU status; setup flow can append a live tip

## How to try

| Say | Expect |
|-----|--------|
| **upgrade check** / **self health** | Full desk health blurb + HUD artifact |
| **recent errors** / **log errors** | Short error summary (or “No recent errors…”) |
| **setup computer use** / **computer use status** | Readiness + missing guidance when blocked |

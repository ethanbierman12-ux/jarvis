# Autonomy pack — Phase 1–4 software (voice cheatsheet)

## Clarify (multi-choice)
Vague: `fix the server` / `deploy it` / `build an app` → HITL option chips.

## Healer
- `healer status`
- `healer kill` / `healer kill top`
- `healer ignore`
Auto-asks when CPU ≥85% or RAM ≥90% (protected processes never killed).

## Git safety
- `safety snapshot` / `git snapshot`
- `revert last snapshot`
- `last snapshot`
Crash runner also calls `scripts/crash_snapshot.py`.

## Memory overnight
3am ET: consolidates logs → Chroma + morning digest.
Manual: `consolidate memory`

## Scaffold
- `scaffold react`
- `scaffold python named mytool`
- `scaffold html`
Projects land in `~/jarvis-projects` (or `scaffold_root`).

## Background research
- `background research <topic>`
Notifies HUD + phone + speaks when done.

## Codesmith
- `run code <request>` / `codesmith <request>`
Sandbox Python with pre-snapshot.

## Whisper
- `whisper mode on` / `whisper mode off`

## Clipboard errors
Copy a traceback → Jarvis offers help.
- `fix clipboard error`

## Companion handoff
`scripts/shutdown_handoff.bat` + POST `/api/handoff`
Set `COMPANION_TOKEN` from settings.

## IoT hooks (hardware later)
- `room kitchen`
- `nfc coffee`
- `mirror listening on`
- `iot status`
ESP32/NFC can POST macros: `/macro?cmd=room+kitchen`

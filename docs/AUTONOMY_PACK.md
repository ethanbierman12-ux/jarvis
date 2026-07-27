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

## Hologram / LiveKit / Pinecone / Anthropic CU
- `open hologram` — Next.js tactical HUD (`hub/dashboard`, port 3000)
- `prefer elevenlabs` / `live voice status` — ElevenLabs turbo + optional LiveKit
- Hub: `POST /v1/livekit/token` when LIVEKIT_* env set
- `pinecone status` · `set pinecone key to …` · `set pinecone host to https://…`
  Memory dual-writes Chroma + Pinecone when configured
- `computer use anthropic` — Claude computer + text_editor + bash tool parity

## Stark intelligence pack
- Roles: `set cognitive role to executive|research|engineering|tactical` + CoT overlay
- Briefings: `good morning` rotates tactical / casual / blind-spot (never same twice)
  - Also: `tactical briefing` · `casual briefing` · `blind spot briefing`
- Protocols: `house party protocol` · `sentry mode` · `veronica protocol` · `run before we walk`
- Lore: `surprise me` · `devil's advocate` · `pitch a project` · `what's shaking the grid` · DUME mode
- Workshop: `register part …` · `workshop stock` · `synergy check` · `source part …`
- Packages: `track package 1Z…` · `where's my package`
- Micro-agents: `cron status` (CPU/horizon/shipments in background)

## Personality forge (Axolotl + TRL DPO)
- `generate personality dataset` — thousands of British / “Sir” chats + DPO pairs
- `personality forge status`
- `harvest rlhf for training` — pull approved mic answers into the dataset
- `train personality` — Axolotl QLoRA instructions
- `start dpo training` — TRL Direct Preference Optimization (Jarvis vs generic)
Artefacts: `jarvis/data/personality_forge/`

## Scaffold
- `scaffold react` → **Pulse Arena** (search, power meters, score sync, Vercel/Netlify configs)
- `scaffold python named mytool`
- `scaffold html` → static Pulse board with local + Jarvis scores
- `publish app` → production `npm run build` + live preview on `:4173`
- `app scores` / `scoreboard` → Jarvis leaderboard (`jarvis/data/app_scores.json`)
- Apps POST telemetry to companion `POST /api/scores` (override with `VITE_JARVIS_SCORE_URL`)
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

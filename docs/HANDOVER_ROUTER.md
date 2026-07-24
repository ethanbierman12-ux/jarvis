# Semantic router handover

## What shipped

Local-first **semantic router** (`jarvis/core/semantic_router.py`):

1. emergency → hotkey → phone → travis → **desk** → facts → media → build → productivity → hub/AI → chitchat  
2. Simple intents (`weather`, `lock`, `enroll`, `night vision`, `show stats`, …) are **force_local** — Hub never runs.  
3. Hub runs for explicit Sarah/Tom/Admin / **ask sarah|tom|admin** **or** complex research/coding the router marks `hub`.  
4. Desk lane handlers run **immediately after Travis** (enroll, NV, security, autobug, auto-lock, router status).

## Control-strip voice

HUD buttons and spoken labels share the same `handle_utterance` path. Aliases in `jarvis/core/commands.py` map short labels (`enroll`, `nv on`, `secure`, `stats`, `router`, `sarah`…) to the exact button cmds in `control_strip.py`.

`is_fast_local_command()` short-circuits memory / emotion / suggestion lag and keeps **one** spoken reply. Fallback lines never say “button …”.

Command monitor is hidden by default (say **show command monitor**).

## Voice (British Jarvis)

- Default TTS: Edge `en-GB-ThomasNeural` (`settings.tts_voice`) with `tts_rate` / `tts_pitch`.
- ElevenLabs is **opt-in** via `tts_prefer_elevenlabs: false` (default) so US Adam voice does not replace Jarvis.

## Voice phrases (agents)

- **ask sarah …** / **sarah** · **ask tom …** / **tom** · **ask admin …** / **admin**
- **ask manus …** / **manus review** (local Manus bridge, not Hub)

## Deferred (from the big brainstorm)

| Idea | Status |
|---|---|
| ChromaDB second brain tighten | later |
| Vision screen/camera → model | partially exists (scan) |
| Autonomous tool writer into tools/ | later |
| Local Llama3 SLM fallback | settings.ollama_* exist; wire later |
| Redis sub-ms cache / Docker sandbox | later |
| Knowledge graph / flashcards / Redis | later |

## Files

- `jarvis/core/semantic_router.py`
- `jarvis/core/commands.py`
- `jarvis/core/voice.py`
- `jarvis/brain.py` — `_route_desk_lane`, hub gate via `allows_hub`

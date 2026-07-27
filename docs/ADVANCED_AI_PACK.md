# Advanced AI Pack

Jarvis already had most of the Stark stack. This pack wires the remaining high-impact pieces: ask-me-anything brain, STM + LTM, sarcastic live-context persona, self-correction, ambience ducking, cinematic morning brief, room presence, guest mode, and energy guard.

## Voice commands

| Say | Effect |
|-----|--------|
| `ask me anything …` / `what do you think …` / `explain …` | LLM brain (Ollama → Anthropic → OpenAI) |
| `remember that my favorite coffee is espresso` | Long-term vector memory |
| `that answer was wrong` / `fix your answer` | RLHF reject + rewrite last reply |
| `cinematic morning brief` / `morning status briefing` | Calendar + weather + traffic hint + quote |
| `roast my tabs` / `what am I watching` | Browser-tab sarcasm |
| `I am in the bedroom` / `set room to kitchen` | Room presence targeting |
| `guest mode on` / `off` | Soft guest profile (no full intruder panic) |
| `energy check` / `set energy limit to 3000` | Power ceiling via HA meter |
| `brain status` / `advanced ai` | Pack + LLM backend status |
| `good morning` | Existing dynamic briefings (still works) |

## LLM backends

1. **Local** — run [Ollama](https://ollama.com) with `llama3` / `mistral` (private, free).
2. **Cloud** — vault `anthropic_api_key` or `openai_api_key`.

Streaming: `llm_client.complete_stream()` uses Ollama token streaming when available.

## Memory

- **Short-term:** last N turns (`chat_memory_turns`, default 8) in `AskAnythingBrain`.
- **Long-term:** Chroma (`VectorMemory`) + optional Pinecone dual-write.
- **Self-correction log:** `jarvis/data/self_corrections.jsonl`.

## Persona

`personality.SYSTEM_PROMPT` is dry, British, sarcastic, anti-repetition. Live context (time, calendar, tabs, room, HA) is injected every ask.

## Ambience ducking

While TTS speaks, Spotify/media volume steps down (`ambient_duck_steps`) and restores after.

## ElevenLabs / Paul Bettany clone

Set in settings (vaulted):

```json
{
  "tts_prefer_elevenlabs": true,
  "elevenlabs_api_key": "…",
  "elevenlabs_voice_id": "<your clone id>",
  "elevenlabs_model": "eleven_turbo_v2_5"
}
```

Clone the voice in the ElevenLabs UI, paste the voice id.

## Room presence (BLE / mmWave)

Manual: `I am in the office`.

Sensor webhook (companion token required):

```http
POST http://<pc>:8766/api/presence
Authorization: Bearer <companion_token>
{"room":"bedroom","source":"mmwave"}
```

## Energy guard

Expose `sensor.house_power` (or similar) in Home Assistant. Configure non-essential entities in `jarvis/data/energy_guard.json`. Say `energy check`.

## Clap → smart plug → BIOS AC recovery

1. BIOS: **Restore AC Power Loss → Power On**.
2. PC PSU into a smart plug (HA entity e.g. `switch.pc_plug`).
3. Settings: `clap_smart_plug_enabled`, `clap_smart_plug_entity`.
4. Existing clap / WOL agent can turn the plug on; motherboard auto-boots.

## Already in repo (use as-is)

Computer use, face enroll, Deepgram duplex, Hub hologram, n8n, Buffer social, Tavily crew search, clap WOL, morning briefings, Pinecone, watchdog (`runner.py`).

## Settings keys

`chat_memory_turns`, `ambient_duck_steps`, `energy_limit_w`, `guest_mode_default`, `clap_smart_plug_entity`, `clap_smart_plug_enabled`.

# JARVIS Hub & Spoke

Voice-activated multi-agent infrastructure. **JARVIS** is the Hub (orchestrator). **Sarah**, **Tom**, and **Admin** are Spokes that report back via a messaging bus (webhooks / Slack).

```
[ User Speech ] ──> Deepgram STT ──> Next.js Dashboard
                                         │
                                  JARVIS Main LLM (Hub)
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
               Agent Sarah          Agent Tom           Agent Admin
              (Support/Email)      (Code/Dev)        (Calendar/Notion)
                    │                    │                    │
                    └────────────────────┼────────────────────┘
                                         ▼
              ElevenLabs TTS <──── Messaging Bus (webhooks / Slack / n8n)
```

## Quick start

```bash
cd hub
cp .env.example .env          # fill API keys
npm install
npm run dev:server            # Hub API → http://127.0.0.1:8787
npm run dev:dashboard         # UI → http://127.0.0.1:3000
```

Optional keys (system still runs in **mock LLM** mode without them):

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude / Fable-class hub reasoning |
| `DEEPGRAM_API_KEY` | Speech-to-text |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | TTS |
| `SLACK_WEBHOOK_URL` | Spoke → Slack reports |
| `GOOGLE_CALENDAR_*` / `NOTION_API_KEY` | Admin agent live APIs |

## Architecture

| Path | Role |
|------|------|
| `src/hub/` | Orchestrator, router node, session halt (`exit` / `standby`) |
| `src/agents/` | Sarah · Tom · Admin spokes + system prompts |
| `src/memory/` | Ephemeral session state + persistent markdown vault |
| `src/messaging/` | Internal bus, webhooks, Slack |
| `src/voice/` | Deepgram + ElevenLabs hooks |
| `src/api/` | HTTP routes for UI / n8n / webhooks |
| `dashboard/` | Next.js holographic ops console |
| `data/memory/` | Obsidian-style persistent notes |
| `simulated/codebase/` | Tom’s mock repo for bug fixes / PRs |

## Example multi-agent flow

> “Schedule a meeting with the client who complained in support.”

1. Router → `sarah` (fetch complainant contact from tickets)
2. Router → `admin` (book Calendar event with that contact)
3. Hub synthesizes reply → ElevenLabs (optional)

## Halt keywords

Any utterance containing **`exit`**, **`standby`**, **`abort`**, or **`stop agents`** immediately cancels the active orchestration chain.

## Desktop HUD bridge

This `hub/` stack is independent of the PyQt Jarvis HUD in the parent repo. Point the HUD or n8n at `POST http://127.0.0.1:8787/v1/chat` to share the same Hub.

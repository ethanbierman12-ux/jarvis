# JARVIS Hub — Installation Guide

## Prerequisites

- Node.js 20+
- npm 10+
- Optional: Anthropic, Deepgram, ElevenLabs, Slack webhook, Google Calendar, Notion

## 1. Install

```bash
cd hub
cp .env.example .env
npm install
cd dashboard && npm install && cd ..
```

## 2. Configure `.env`

Minimum (works offline with mocks):

```
MOCK_LLM=true
JARVIS_PORT=8787
```

Production-ish:

```
MOCK_LLM=false
ANTHROPIC_API_KEY=sk-ant-...
JARVIS_MODEL=claude-sonnet-4-20250514
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
N8N_WEBHOOK_URL=https://your-n8n/webhook/jarvis
```

Dashboard hub URL (optional):

```bash
# dashboard/.env.local
NEXT_PUBLIC_HUB_URL=http://127.0.0.1:8787
```

## 3. Run

Terminal A — Hub API + WebSocket:

```bash
npm run dev:server
```

Terminal B — Next.js console:

```bash
npm run dev:dashboard
```

Open http://127.0.0.1:3000

## 4. Smoke tests

```bash
curl -s http://127.0.0.1:8787/health

curl -s -X POST http://127.0.0.1:8787/v1/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"Schedule a meeting with the client who complained in support\"}"
```

Expected plan: `sarah → admin`.

Halt:

```bash
curl -s -X POST http://127.0.0.1:8787/v1/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"standby\",\"sessionId\":\"YOUR_SESSION\"}"
```

## 5. n8n / Slack mapping

| Layer | Endpoint |
|-------|----------|
| Inbound voice/text from n8n | `POST /v1/hooks/inbound` `{ "text": "..." }` |
| Hub events → n8n | set `N8N_WEBHOOK_URL` (all bus events POSTed) |
| Hub → Slack | set `SLACK_WEBHOOK_URL` |
| External spoke callback | `POST /v1/hooks/spoke/:id` |
| Live event stream | `WS /v1/events` |

## 6. Voice path

```
Mic → Deepgram (/v1/stt or browser Web Speech) → Dashboard → POST /v1/chat
                                                          → ElevenLabs (/v1/tts)
```

Dashboard MIC uses browser Web Speech when Deepgram is unset; wire Deepgram streaming in production with `DEEPGRAM_API_KEY`.

## 7. Persistent memory (Obsidian-style)

Notes live under `hub/data/memory/{preferences,history,goals}`. Point Obsidian at `hub/data/memory` as a vault if desired.

## 8. Desktop PyQt Jarvis bridge

From the parent HUD / brain, POST the same `/v1/chat` URL to reuse this Hub without replacing the Iron Man UI.

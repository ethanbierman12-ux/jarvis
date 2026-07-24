# Integrations — Macro Pad, Home Assistant, Morning Brief, n8n, Manus

## Stream Deck / silent macro gateway

While Jarvis is running:

```
http://127.0.0.1:8765/macro?cmd=stop
http://127.0.0.1:8765/macro?cmd=lock
http://127.0.0.1:8765/macro?cmd=camera
http://127.0.0.1:8765/macro?cmd=brief
http://127.0.0.1:8765/macro?cmd=go offline
```

POST JSON: `{"cmd":"stop"}`. Bind Stream Deck buttons to Open URL / Web Request.

Settings: `macro_gateway_enabled`, `macro_gateway_port` (default `8765`).

## Home Assistant

1. Create a Long-Lived Access Token in HA.
2. Create scenes (examples): `scene.jarvis_build`, `scene.jarvis_fetch`, `scene.jarvis_morning`, `scene.jarvis_coding`, etc.
3. In `config/settings.json`:

```json
{
  "ha_enabled": true,
  "ha_url": "http://127.0.0.1:8123",
  "ha_token": "YOUR_TOKEN"
}
```

Jarvis maps reactor activity (build / fetch / brief / …) to those scenes. Voice: **"HA status"**, **"HA scene jarvis_build"**.

## iPhone 14 link (ntfy)

Push Jarvis alerts to your iPhone without a Mac/Continuity bridge.

1. Say **"link my phone"** — Jarvis creates a private topic and shows it on the HUD.
2. Install free **[ntfy](https://apps.apple.com/app/ntfy/id1624817563)** from the App Store.
3. In ntfy → **Subscribe to topic** → paste the topic Jarvis spoke/showed.
4. Say **"text my phone hello"** or **"ping my phone"**.

Settings keys: `phone_ntfy_topic`, `phone_ntfy_server`, `phone_shortcuts_webhook` (optional).

## iPhone companion — remote chat (Tailscale PWA)

Command Jarvis from abroad on your iPhone 14 (Safari → Add to Home Screen).

1. Install **Tailscale** on the Jarvis PC and the iPhone (same account).
2. Say **"open phone companion"** — HUD shows `http://100.x.y.z:8766/?token=…`
3. Open in Safari → **Share → Add to Home Screen**.
4. Type commands from anywhere on that Tailscale network.

Full walkthrough: [HANDOVER_COMPANION.md](HANDOVER_COMPANION.md).

Settings: `companion_enabled`, `companion_port` (8766), `companion_host`, `companion_token`.

## Alexa lamp (recommended — Echo voice relay)

Works **without** IFTTT or Home Assistant if an Echo can hear your PC speakers.

Voice: **turn on the lamp** · **turn off the lamp** · **lamp to 40** · **lamp status**

What Jarvis does:
1. Briefly switches Windows audio to a room speaker / soundbar (not your WG1 headset)
2. Speaks: `Alexa, turn on the Lamp`
3. Switches playback back to WG1

Requirements: Echo in the same room, speakers unmuted, device named **Lamp** in the Alexa app (change `alexa_lamp_name` if different).

```json
{
  "alexa_lamp_name": "Lamp",
  "alexa_voice_relay": true,
  "alexa_restore_output": "WG1"
}
```

Silent alternatives (optional): IFTTT Maker key or Home Assistant `light.lamp` — see below.

### IFTTT (silent, no speaking to Echo)

1. IFTTT applets: Maker `jarvis_lamp_on` / `jarvis_lamp_off` → Alexa turn lamp on/off  
2. Set `alexa_ifttt_key` in settings — Jarvis will prefer this over voice relay when set.

### Home Assistant

```json
{
  "ha_enabled": true,
  "ha_token": "YOUR_TOKEN",
  "alexa_lamp_entity": "light.lamp"
}
```

## Automated morning standup

Voice: **"good morning"** / **"morning brief"** / **"standup"** → calendar + tasks + weather briefing.

Optional Windows Task Scheduler (6:00 AM precompute):

```bat
.\install_morning_brief.bat
```

Writes `jarvis/data/morning_standup.txt` so the first “good morning” is instant.

## n8n bridge

1. Run n8n locally (`http://127.0.0.1:5678`).
2. Add a **Webhook** node; note the path (e.g. `jarvis-in`).
3. Settings:

```json
{
  "n8n_url": "http://127.0.0.1:5678",
  "n8n_api_key": ""
}
```

Voice: **"trigger n8n jarvis-in"** — fires `POST /webhook/jarvis-in` on a background worker.

Cursor MCP: copy `.cursor/mcp.json.example` → `.cursor/mcp.json` (gitignored). Active set: Buffer, Gmail, Stripe, Notion (OAuth Connect). n8n / Meta Ads / RevenueCat removed from MCP — see [HANDOVER_MCP.md](HANDOVER_MCP.md). Voice `trigger n8n <path>` still uses settings webhooks.

## Cloud integrations (Jarvis voice)

Same four services as Cursor MCP, via vaulted REST keys (OAuth tokens are **not** shared from Cursor):

| Say | Does |
|-----|------|
| **integrations status** | Link state for all four |
| **link stripe** / **set stripe key to sk_…** | Stripe secret key |
| **stripe status** / **stripe payments** | Balance / recent intents |
| **link notion** / **set notion token to …** | Notion integration |
| **notion search …** | Search workspace |
| **link buffer** / **set buffer token to …** | Buffer token |
| **buffer channels** | List profiles |
| **link gmail** / **set gmail token to …** | Gmail OAuth access token |
| **gmail inbox** | Recent subjects |

Module: `jarvis/core/cloud_integrations.py`. Details: [HANDOVER_MCP.md](HANDOVER_MCP.md).

## Manus AI (manus.im)

Delegate long agent tasks to [Manus](https://manus.im) from Jarvis voice.

1. At manus.im → **API Integration** → create a key.
2. Say **"set manus key to YOUR_KEY"** (vaulted; never commit the key).
3. Say **"ask manus research the latest AI news"** — Jarvis calls `api.manus.ai` and opens the task URL.

Voice: **link manus** · **ask manus …** · **manus review** · **manus follow up …** · **manus result**. Full walkthrough: [HANDOVER_MANUS.md](HANDOVER_MANUS.md).

Settings: `manus_enabled`, `manus_api_key` (vault), `manus_agent_profile`, `manus_base_url`, `manus_code_assist`, `manus_code_assist_cooldown_sec`.

## Downloads watchdog

With `watch_enabled: true`, new files in Downloads (or `watch_paths`) flash a HUD alert and queue a light note. Optional deps: `pip install watchdog`.

## Background task queue

Heavy work (n8n, file analysis) uses an in-process worker pool (not Celery). Voice: **"task status"**.

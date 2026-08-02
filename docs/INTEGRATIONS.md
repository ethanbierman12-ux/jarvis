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
  "ha_url": "http://homeassistant.local:8123",
  "ha_token": "YOUR_TOKEN"
}
```

Jarvis maps reactor activity (build / fetch / brief / …) to those scenes. Voice: **"HA status"**, **"HA scene jarvis_build"**.

If `homeassistant.local` does not resolve on Windows, use the HA box LAN IP (`http://192.168.x.x:8123`).

## Ring doorbell (best simple path: Alexa → IFTTT → ntfy → Jarvis)

No Home Assistant and no open ports. IFTTT posts to a private **ntfy** topic; Jarvis listens and announces.

### Your webhook URL

Jarvis creates a private topic on boot. Say **"doorbell setup"** (or check `doorbell_ntfy_topic` in settings). Example shape:

`https://ntfy.sh/jarvis-door-xxxxxxxx`

### IFTTT applet (click-by-click)

1. Create a free account at [ifttt.com](https://ifttt.com).
2. Enable the **Webhooks** service (search “Webhooks” → Connect).
3. **Create** → **If This** — pick one:
   - **Amazon Alexa** → connect Alexa → choose a trigger you can fire from a Routine, **or**
   - **Ring** → “New ding detected” / doorbell pressed (if Ring still offers it on IFTTT).
4. **Then That** → **Webhooks** → **Make a web request**:
   - **URL:** your `https://ntfy.sh/jarvis-door-…` URL  
   - **Method:** `POST`  
   - **Content Type:** `text/plain`  
   - **Body:** `ding` (use `motion` for motion alerts)
5. Save the applet.

### Alexa Routine (if IFTTT trigger is Alexa)

1. Alexa app → **More** → **Routines** → **+**
2. **When** → **Device** / **Doorbell** → Ring doorbell pressed (or motion).
3. **Add action** → **IFTTT** → select the applet you just made  
   (IFTTT Alexa skill must be enabled in Alexa).
4. Save.

### Test

1. Jarvis running (double-tap F3 if needed).
2. Say **"test doorbell"** — he should announce the door.
3. Or from any browser/PC:  
   `curl -d "ding" https://ntfy.sh/YOUR_TOPIC`
4. Then press the real doorbell.

Cooldown default: 45s between announces (`doorbell_cooldown_sec`).

## Ring via Home Assistant (optional / advanced)

Alexa can keep Ring for Echo announcements. For HA, see older notes / `docs/ha_ring_jarvis.yaml` if you install HA later.

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

## Quest / WebXR spatial HUD

Use the same companion token:

```
https://JARVIS-PC.YOUR-TAILNET.ts.net/spatial?token=YOUR_COMPANION_TOKEN
```

First expose the local companion through HTTPS, for example with `tailscale serve --bg http://127.0.0.1:8766`. The bootstrap request exchanges the companion token for a 12-hour HttpOnly session and redirects to a token-free URL.

The page polls the authenticated `/api/state` fallback and offers immersive AR/VR when WebXR is available. Quest Browser requires the HTTPS URL for immersive mode; the flat live HUD also works over local HTTP.

## MQTT state bus

`homeassistant/docker-compose.yml` now starts a non-persistent, loopback-only Mosquitto broker alongside Home Assistant. Run `homeassistant/start_homeassistant.bat`, then enable:

```json
{
  "mqtt_enabled": true,
  "mqtt_host": "127.0.0.1",
  "mqtt_port": 1883,
  "mqtt_topic_prefix": "jarvis"
}
```

Retained JSON topics:

- `jarvis/reactor` — reactor mode
- `jarvis/mic` — throttled microphone level
- `jarvis/speak` — TTS active flag
- `jarvis/state` — combined telemetry snapshot (conversation text is excluded)

Say **“state bus status”** for broker/fallback health. MQTT failure never blocks the PyQt HUD or `/api/state`.

## Isolated execution and edge workers

Generated CODESMITH jobs and plugin validation use `exec_backend`: `auto`, `docker`, `edge`, or `host`. `auto` tries gVisor/Docker, then SSH edge workers. Host fallback is disabled by default because Python `-I` is not a security boundary; set explicit `host` mode only when that risk is acceptable.

For strict isolation, pre-pull `docker_python_image`, configure Docker’s `runsc` runtime, and set:

```json
{
  "exec_backend": "docker",
  "docker_runtime": "runsc",
  "docker_require_gvisor": true,
  "exec_host_fallback": false
}
```

Edge worker objects accept `name`, `host`, `user`, `port`, `key_path`, `python`, and `enabled`. SSH uses batch mode and strict host-key checking. Say **“execution backend status”** for configuration health.

## Audit and privacy

Settings, instruction, vault, and vector-memory writes append payload-redacted SHA-256 records to `jarvis/data/audit/chain.jsonl`. Say **“verify audit chain”** to detect edits, deletion, or reordering.

Memory labels are `personal`, `work`, or `public`. Hub events default to `personal`, which cannot be sent to Slack or n8n. Set `JARVIS_SHARE_MAX_SENSITIVITY=public` in `hub/.env` to block `work` events too.

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

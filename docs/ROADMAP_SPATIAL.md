# Spatial / Edge / Vault roadmap

Garbled mega-spec decoded into a shippable sequence. **Done now** vs later.

## Shipped foundations

| Feature | How |
|--------|-----|
| **Secrets vault** | Windows DPAPI · `jarvis/data/vault/secrets.dpapi.json` · API keys leave `settings.json` |
| **RLHF feedback** | Voice: *approve* / *reject* · Hotkeys: `Ctrl+Shift+Up` / `Ctrl+Shift+Down` |
| **Weekly digester** | `install_rlhf_digest.bat` → Sundays 21:00 → `custom_instructions.md` |
| **MQTT state bus** | `StateBus` publishes retained `jarvis/reactor`, `jarvis/mic`, `jarvis/speak`, and `jarvis/state`; `/api/state` is the authenticated fallback |
| **Spatial HUD** | Dependency-free WebXR panel at companion path `/spatial`; Quest uses HTTP state fallback and enters immersive AR/VR when supported |
| **Execution isolation** | `ExecBackend`: gVisor/Docker → configured SSH edge workers → guarded host fallback according to settings |
| **Edge workers** | Fixed-shape `python3 -I -` jobs over batch-mode SSH; no user-controlled remote shell command |
| **Far-field audio** | ReSpeaker/Seeed scoring plus ranked retries for classic level capture and Deepgram duplex |
| **Audit ledger** | Hash-linked, payload-redacted records at `jarvis/data/audit/chain.jsonl`; Hub keeps its own process-safe chain |
| **Privacy labels** | `personal`, `work`, and `public` memory metadata; personal Hub events cannot fan out to Slack/n8n |

## Operation

### Spatial telemetry (Meta Quest 3 / WebXR)
Open `http://JARVIS-PC:8766/spatial?token=THE_COMPANION_TOKEN`, then press **Enter Spatial HUD**. Immersive WebXR normally requires HTTPS in Quest Browser; the flat HUD remains usable over ordinary HTTP.

### Physical edge sandbox (Pi 5 / Jetson)
Add workers to `edge_workers`:

```json
[{"name":"pi-lab","host":"192.168.1.50","user":"jarvis","key_path":"~/.ssh/jarvis_ed25519","enabled":true}]
```

Set `exec_backend` to `edge` to require an edge target, or `auto` to try Docker first. Set `exec_host_fallback` to `false` when generated code must never run on the main OS.

### ReSpeaker / far-field array
Set `mic_prefer` to the exact Windows device substring, such as `ReSpeaker`. Keep `mic_reject_loopback: true`. Enable onboard AEC in the array firmware utility; Jarvis deliberately does not implement software AEC.

### MQTT state bus
Run `homeassistant/start_homeassistant.bat`, then set `mqtt_enabled: true`. Mosquitto is bound to loopback on ports `1883` (MQTT) and `9001` (WebSocket). The companion API continues serving state if the broker is down.

### Docker + gVisor kernel
Pre-pull `docker_python_image` and install/register `runsc` with Docker. The backend uses a read-only root, no network, dropped capabilities, PID/memory/CPU limits, and `no-new-privileges`. `docker_require_gvisor: true` prevents fallback to Docker’s default runtime.

### Tamper-evident audit ledger
This is a linear SHA-256 hash chain rather than a Merkle tree. It covers settings, instruction, vault, and Chroma writes without storing secret payloads. Say **“verify audit chain”** to validate sequence, previous hashes, and record hashes.

### Privacy context tokens
Chroma and Hub markdown memory carry sensitivity labels. Hub events default to `personal`; personal events are blocked from Slack/n8n. `work` is allowed by default, while `JARVIS_SHARE_MAX_SENSITIVITY=public` restricts external fan-out to public events only.

## Voice cheatsheet

- `approve` / `thumbs up` — log last action as good  
- `reject` / `thumbs down` — log last action as bad  
- `rlhf status` · `run rlhf digest`  
- `state bus status` · `execution backend status`  
- `spatial HUD status` · `verify audit chain`  
- Secrets: automatic on boot — check console for `[vault] moved N secret(s)`

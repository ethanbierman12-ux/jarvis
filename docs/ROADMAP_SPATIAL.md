# Spatial / Edge / Vault roadmap

Garbled mega-spec decoded into a shippable sequence. **Done now** vs later.

## Shipped (this pass)

| Feature | How |
|--------|-----|
| **Secrets vault** | Windows DPAPI · `jarvis/data/vault/secrets.dpapi.json` · API keys leave `settings.json` |
| **RLHF feedback** | Voice: *approve* / *reject* · Hotkeys: `Ctrl+Shift+Up` / `Ctrl+Shift+Down` |
| **Weekly digester** | `install_rlhf_digest.bat` → Sundays 21:00 → `custom_instructions.md` |

## Next foundations (stubs / design)

### Spatial telemetry (Meta Quest 3 / WebXR)
Floating glass HUD beside the monitor via a local WebXR page that subscribes to Jarvis MQTT/state. Not implemented yet — requires Quest browser + HTTPS or localhost tunneling.

### Physical edge sandbox (Pi 5 / Jetson)
SSH exec target for risky agent commands. Planned module: `jarvis/core/edge_cluster.py` with `ssh user@pi` workers. Keep off the main OS until Docker+gVisor lands.

### ReSpeaker / far-field array
Treat as preferred mic in `mic_prefer` / `audio_isolation.py` once the USB array enumerates. Enable onboard AEC in the array’s firmware utility (not soft AEC in Jarvis).

### MQTT state bus
Replace HTTP poll for HUD amp/activity with `paho-mqtt` localhost broker (Mosquitto in Docker). Topics: `jarvis/reactor`, `jarvis/mic`, `jarvis/speak`.

### Docker + gVisor kernel
Sandbox `SandboxCompiler` / vibe agent pip installs inside `docker run --runtime=runsc`.

### Merkle audit ledger
Append-only hash chain of instruction + vault + memory writes. Planned: `jarvis/data/audit/chain.jsonl`.

### Privacy context tokens
Sensitivity labels on memory rows (personal / work / public) before any team channel share.

## Voice cheatsheet

- `approve` / `thumbs up` — log last action as good  
- `reject` / `thumbs down` — log last action as bad  
- `rlhf status` · `run rlhf digest`  
- Secrets: automatic on boot — check console for `[vault] moved N secret(s)`

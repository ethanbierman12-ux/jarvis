# JARVIS 2.0

Clean rebuild — cyberpunk HUD, voice control, Eco-Mode governor, isolated vision process.

## Run

```bat
run.bat
```

Starts the **watchdog** (`runner.py`), which keeps Jarvis alive:

| Exit code | Meaning |
|-----------|---------|
| `0` | Intentional reload — watchdog reboots Jarvis |
| `99` | Offline / window closed — watchdog stops |
| other | Crash — watchdog recovers after 5s |

Voice: **reload core** / **reboot jarvis** → reload · **go offline** / **power down** → stop · **Ctrl+Alt+K** → emergency kill (crash-recover).

**Double-tap F3** (global via `install_f5_wake.bat` / `run.bat wake`): launches Jarvis when closed; soft-reloads when open. A single F3 only focuses an already-open HUD (prevents bed/laptop accidental launches). Crash auto-recover is off by default.

Boot shows **INITIATING SYSTEM 1…** with loading % → 100 and boot sound, then blooms into the main HUD.

### HUD (PyQt6 cyberpunk)

Native high-performance desktop shell — not Streamlit/Electron. Left column: time dial + circular CPU/RAM/disk gauges + **QUICK · RELAYS** toggle grid (lamp / night / quiet / smooth / mini / listen). Center: arc reactor, mission-log terminal, dual-tone waveform. **MINI** collapses to an always-on-top corner widget.

## Voice / commands

| You say | Jarvis does |
|--------|-------------|
| `Play Bruno Mars` | Spotify / YouTube Music |
| `Open camera` / `Camrea` | Full-screen theater (retries if device busy) |
| `Switch camera` | Next camera index |
| `Test microphone` / `Can you hear me` | Mic path + level check |
| `Turn on/off the lamp` | Alexa Echo voice relay |
| `Good morning` / `Standup` | Daily briefing |
| `Screenshot` | Saves under Pictures/Jarvis |
| `Navigate to City Hall` | Google Maps directions |
| `What time is it` / `Weather` | Speaks time / weather |
| `Lock` / `Confirm shutdown` | Locks PC / shuts down |
| `Camera search` / `Scan this online` | Camera ID + Google Lens |
| `Standby for clap` / `Sleep` | Sleeps PC for clap → Wake-on-LAN |
| `Goodnight` | Guardian bedtime (purge media + lock) |
| `Update software` | Typing UI → sandboxed plugin + watchdog reload |
| `Go offline` / `Reload core` | Stop watchdog / reboot via `runner.py` |
| `Note that my camera is on the left monitor` | ChromaDB long-term memory |
| `What do you remember about my camera` | Semantic memory recall |
| `Switch to headphones` / `Set volume to 40` | pycaw audio routing |
| `Click Export` / `Type hello` / `Press ctrl s` | PyAutoGUI desktop automation |

Optional ElevenLabs: set `elevenlabs_api_key` in `config/settings.json` (mirrored to `config/config.json`). Falls back to Edge TTS.

### Upgrade stack

- **ChromaDB** vector memory → `jarvis/data/chroma`
- **Duplex voice**: set `deepgram_api_key` in `config/settings.json` → streaming STT (<300ms finals) + talk-over-Jarvis barge-in; classic STT is the fallback
- **Agent crew**: say `crew <request>` / `crew status` / `crew health` / `crew debates` / `crew debate random` / `crew debate tech` / `crew debate <question>` — eight agents plus a debate chamber with 100+ preset topics (tech, AI, money, career, lifestyle, health, gaming, home, Philly, business)
- **Rotating logs** (5 MB × 3) → `jarvis/data/jarvis.log`
- **Mic hot-plug recovery** in the voice loop
- **Windows Startup**: `install_jarvis_startup.bat`
- **Audio isolation**: rejects Voicemeeter / loopback mics — see `docs/VOICEMEETER.md`
- **Macro pad**: `http://127.0.0.1:8765/macro?cmd=stop` (Stream Deck)
- **Home Assistant / n8n / morning brief / Downloads watch**: `docs/INTEGRATIONS.md`
- **6AM standup precache**: `install_morning_brief.bat`
- **DPAPI secrets vault**: API keys leave `settings.json` → `jarvis/data/vault/`
- **RLHF**: `Ctrl+Shift+Up/Down` or say *approve* / *reject* · `install_rlhf_digest.bat`
- **Spatial / edge roadmap**: `docs/ROADMAP_SPATIAL.md`
- **Live state bus**: retained MQTT topics plus authenticated `/api/state` fallback
- **Quest spatial HUD**: companion URL `/spatial?token=…` with flat + immersive WebXR modes
- **Isolated CODESMITH**: gVisor/Docker → SSH edge → configurable guarded host fallback
- **Tamper-evident writes**: SHA-256 audit chain and `personal` / `work` / `public` memory labels
- **Far-field mics**: ReSpeaker/Seeed preference and ranked hot-plug retries

```powershell
.\run.bat deps
.\run.bat
```

Hotkey input: type in the command bar and press Enter.

## Clap to power on (Wi-Fi + Bluetooth)

The PC cannot hear claps while it is off. Use a **second always-on device** on the same network (or with Bluetooth reach):

1. On **this PC**, run `setup_wol.bat` as Administrator (saves Wi-Fi + Bluetooth MACs, enables wake).
2. In **BIOS**, enable Wake on LAN / Power on by PCI-E (disable ErP / deep sleep if present).
3. On the **second device**:
   ```bat
   pip install numpy sounddevice
   python clap_wol_agent.py
   ```
   - Wi-Fi only: `python clap_wol_agent.py --transport wifi`
   - Bluetooth only: `python clap_wol_agent.py --transport bluetooth`
   - Bluetooth headset mic: `python clap_wol_agent.py --mic bluetooth`
4. On this PC, tell Jarvis: **standby for clap**.
5. **Double-clap** → agent wakes the PC over **Wi-Fi (WOL)** and/or **Bluetooth**.

Config: `config/clap_wol.json` → `"transports": ["wifi", "bluetooth"]`  
Test: `python test_wol.py --transport both`

## Architecture

- **UI** — PyQt6 (GPU / ANGLE), separate from vision
- **Vision** — `multiprocessing` worker (EMEET preferred), Eco-Mode FPS throttle
- **Governor** — CPU > 80% or temp > 75°C → drop vision/UI FPS
- **Voice** — mic thread + 5s thought-stream buffer
- **Plugins** — AST sandbox + `importlib` hot-reload

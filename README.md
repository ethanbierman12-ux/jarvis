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

Boot shows **INITIATING SYSTEM 1…** with loading % → 100 and boot sound, then blooms into the main HUD.

## Voice / commands

| You say | Jarvis does |
|--------|-------------|
| `Play Bruno Mars` | Spotify / YouTube Music |
| `Open Chrome` | Launches installed apps |
| `What time is it` / `Weather` | Speaks time / weather |
| `Lock` / `Confirm shutdown` | Locks PC / shuts down |
| `Standby for clap` / `Sleep` | Sleeps PC for clap → Wake-on-LAN |
| `Goodnight` | Guardian bedtime (purge media + lock) |
| `Update software` | Typing UI → sandboxed plugin hot-load |

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

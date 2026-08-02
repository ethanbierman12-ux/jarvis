# AGENTS.md

## Cursor Cloud specific instructions

This repo contains three independently-runnable products. The dev environment is Linux
(headless) with a live X display on `DISPLAY=:1`. System packages (portaudio, Qt xcb libs,
`python3-tk`, python dev headers, etc.) are already present in the VM image; the startup
update script only refreshes language deps (Python venv + Hub npm installs).

### Services

| Product | Location | Language | How to run (dev) | Ports |
|---------|----------|----------|------------------|-------|
| JARVIS HUD (cyberpunk desktop assistant) | root + `jarvis/` | Python 3.12 / PyQt6 | `DISPLAY=:1 QT_OPENGL=desktop .venv/bin/python main.py` | macro gateway `:8765`, iPhone companion `:8766` |
| JARVIS Hub & Spoke (multi-agent orchestrator + Next.js console) | `hub/` | Node 22 / TS + Next.js | `npm run dev:server` and `npm run dev:dashboard` (from `hub/`) — see `hub/INSTALL.md` | Hub API `:8787`, dashboard `:3000` |
| Clap → Wake-on-LAN utilities | `clap_wol_agent.py`, `test_wol.py` | Python | `.venv/bin/python test_wol.py --transport wifi --mac <MAC>` | UDP WOL `:9` |

Python deps live in the `.venv` virtualenv (activate with `. .venv/bin/activate` or call
`.venv/bin/python`). The Hub is fully cross-platform; the HUD is Windows-oriented but boots
on Linux with the notes below.

### Non-obvious caveats

- HUD boot needs `python3-tk`. Without it, `pyautogui`→`mouseinfo` calls `sys.exit()` during
  `Brain.__init__`, which propagates past the `except Exception` guards and silently kills the
  HUD ~1s after the window paints (exit code 1, no traceback). It is already installed here.
- `jarvis/app.py` defaults `QT_OPENGL=angle` (Windows-only). On Linux export
  `QT_OPENGL=desktop` (the window renders as a raster surface; no GPU needed).
- Windows/hardware-only features degrade gracefully on this headless VM and log expected
  noise: no microphone / "No Default Input Device Available", ALSA "Couldn't open audio
  device", `[vision] no usable camera`, and `[vault] ... module 'ctypes' has no attribute
  'windll'`. These are NOT setup failures — the HUD, its macro gateway (`:8765`) and companion
  server (`:8766`) still come up.
- The many `install_*.bat` / `*.ps1` / `wake_agent.py` scripts are Windows-only (hardcoded
  `C:\Users\...` paths, Win32 hotkeys) and are not runnable here.
- Hub runs in `MOCK_LLM=true` mode by default (`hub/.env`, copied from `hub/.env.example`),
  so no API keys are required to exercise the full sarah/tom/admin orchestration.
- `cd hub && npm run typecheck` reports one pre-existing type error in `src/voice/deepgram.ts`
  (Buffer vs BodyInit). It does not affect `npm run dev:server`, which runs via `tsx`.
- There is no pytest suite. `test_wol.py` is a standalone CLI (not a test module); it sends a
  real WOL magic packet and exits 0.

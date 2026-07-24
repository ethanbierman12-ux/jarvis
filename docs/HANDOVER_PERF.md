# Handover — Performance / Smooth HUD

Additive lag pass (2026-07-24). No product-behavior rewrite; wake_required, theme_sync off, British TTS, computer-use local preference unchanged.

## Root causes found

1. **Camera paint on UI thread** — corner/theater feed ran OpenCV CLAHE + MediaPipe + Qt `SmoothTransformation` every ~33ms.
2. **Always-on 33ms widgets** — voice waveform + rain FX repainted even when quiet/clear.
3. **Unbounded HUD log** — `QTextEdit.append` with no block cap → long-session slowdown.
4. **Mic pill `setStyleSheet` every level sample** — stylesheet reparse on main thread ~8 Hz.
5. **Busy background flush** — folder watch settled every 0.5s; F5 reload poll every 400ms.

## What changed

| Area | Change |
|------|--------|
| Camera / theater | ~15–20 FPS paint; cheap night boost; gestures every 3rd frame @ 320px; OpenCV resize before Qt |
| Arc reactor | Skip every other paint when fully idle |
| Voice waveform | Idle 120ms / active 50ms; eco slows further |
| Weather FX | 66ms + fewer drops |
| Clock dial | Redraw on second change only |
| HUD log | `maximumBlockCount(280)` |
| Mic glow | Banded stylesheet updates |
| Reload poll | 1s (F5 shortcut still instant) |
| Folder watch | Flush settle loop 1.0s |
| Mic level sampler | Quieter sleep when not speaking |
| **Smooth mode** | Voice + governor + persisted `performance_mode` |

## How to feel it

1. **F5** reload Jarvis.
2. Idle HUD should feel calmer (reactor + waveform quieter).
3. Say **Jarvis, smooth mode** — status shows `● SMOOTH MODE`; camera/reactor throttle harder.
4. Say **Jarvis, smooth mode off** (or **full fidelity**) to restore.
5. Open camera — live feed still works; less hitching while speaking over it.
6. Optional: leave smooth mode on (saved in `settings.json` as `performance_mode`).

## Remaining limits

- **Map / WebEngine** and full-screen camera theater still cost CPU when open — expected.
- MediaPipe gestures are lighter but still non-zero when camera + gestures are on.
- Thermal eco (governor) still engages under high CPU/RAM independently of smooth mode.


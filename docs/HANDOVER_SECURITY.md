# Security / gesture / autobug handover

## In scope (shipped)

| Feature | Module | Voice |
|---|---|---|
| Face enroll + sit greet + step-away secure | `jarvis/core/security_gate.py` | `enroll my face`, `security status`, `secure desk` |
| Intruder alert (mismatch vs enrolled) | same | HUD + phone ping; **streak + 12 min cooldown** |
| Silence alerts | same | `intruder alerts off` / `intruder alerts on` |
| Gesture → commands | `jarvis/core/gesture_commander.py` | swipe L=complete, R=news, U=map, D=close map, fist=secure |
| Voice hotkeys | `jarvis/core/voice_hotkeys.py` | `hit copy`, `hit paste`, `hit save`, … |
| Autobug triage | `jarvis/core/autobug.py` | `fix this error: …`, `open last error` |
| Nightly self-audit (HITL only) | `jarvis/core/self_audit.py` | `self audit` — **never auto-mutates live code** |

## False-positive hardening (2026-07)

HSV-only face match was flaky under desk lighting → sit-down scores < 0.52 fired **“Intruder alert — face does not match enrolled biometrics”** every ~90s.

Now:
- Owner accept ≥ **0.36**; clear intruder only ≤ **0.22**
- Ambiguous band stays quiet (optional hourly re-enroll nudge)
- **3 consecutive** clear mismatches before alert
- Spoken alert cooldown **720s** (`intruder_alert_cooldown_sec`)
- Hist uses CLAHE gray + HSV; enroll crop is CLAHE-stabilized

**Re-enroll:** face the cam → `enroll my face` (or Enroll button). Does not delete until new enroll overwrites.

**Silence:** `intruder alerts off` (or `security off` to disarm all face security).

## Night vision auto (2026-07-23)

**Bug:** Auto NV engaged during daytime when the PC clock timezone differed from `settings.timezone` (`America/New_York`). `_is_night_hours` used `datetime.now().hour` (machine local) while the HUD clock / calendar used East Coast.

**Fix:** Evaluate the dusk window in `settings.timezone` via `zoneinfo` (`_now_in_timezone` / `is_night_hour_window`). Overnight window `19→6` = `hour >= 19 or hour < 6`. Day start auto-disables only auto-engaged NV (`_night_vision_auto_on`); manual on sets `_nv_user_on` and is left alone. Manual off sets `_nv_user_off` until dawn. Optional camera luminance gate skips auto-on when the frame is clearly bright.

**Force off:** say `night vision off` (blocks auto until day window) or `night vision auto off` (disables the loop entirely). Settings: `night_vision_auto`, `night_vision_start_hour`, `night_vision_end_hour`, `timezone`.

## Settings

- `security_enabled` (default true)
- `intruder_alert` (default true — keep on; gate debounce prevents spam)
- `intruder_alert_cooldown_sec` (default 720)

## Wiring notes

- Presence path: `Brain._on_vision` → `SecurityGate.on_presence` → `_handle_security_event`
- Gestures: `CameraTheater.gesture` / `gesture_swipe` → `MainWindow` → `Brain.handle_gesture`
- Nightly audit: `_proactive_loop` calls `SelfAudit.maybe_nightly()` around 3am America/New_York
- Registry keys: `security_gate`, `autobug`, `self_audit` (frozen during upgrade)

## Out of scope (do not implement next unless asked)

IPFS backups, autonomous self-mutation of live code, social-media posting, drones, brainwave, quantum, hive-mind cloud coordination.

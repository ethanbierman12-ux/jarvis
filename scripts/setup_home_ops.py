"""One-shot home-ops setup: settings, dirs, LAN trust baseline, first backup."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from jarvis.config import Settings, DATA_DIR
    from jarvis.core.net_watch import NetWatch, STATE_PATH as NET_STATE
    from jarvis.core.secure_backup import SecureBackup, BACKUP_DIR
    from jarvis.core.deadman import DeadmanSwitch, STATE_PATH as DEAD_STATE
    from jarvis.core.process_harden import ProcessHarden
    from jarvis.core.space_weather import SpaceWeather
    from jarvis.core.edge_node import edge_status
    from jarvis.core.slang_translate import translate_casual

    print("[home-ops] loading settingsâ€¦")
    s = Settings.load()
    s.net_watch_enabled = True
    s.net_watch_poll_sec = float(getattr(s, "net_watch_poll_sec", 45) or 45)
    # Deadman stays off until you say "arm deadman" (avoids surprise lockdown)
    s.deadman_enabled = bool(getattr(s, "deadman_enabled", False))
    if not (getattr(s, "deadman_phrase", "") or "").strip():
        s.deadman_phrase = "jarvis clear"
    s.deadman_hours = float(getattr(s, "deadman_hours", 24) or 24)
    s.auto_backup_hours = float(getattr(s, "auto_backup_hours", 24) or 24)
    s.save()
    print(
        f"[home-ops] settings: net_watch={s.net_watch_enabled} "
        f"deadman={s.deadman_enabled} phrase={s.deadman_phrase!r} "
        f"phone_ntfy={'yes' if (s.phone_ntfy_topic or '').strip() else 'no'}"
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[home-ops] data={DATA_DIR}")
    print(f"[home-ops] backups={BACKUP_DIR}")

    print("[home-ops] trusting current LAN devices (baseline)â€¦")
    nw = NetWatch(enabled=True, poll_sec=s.net_watch_poll_sec)
    trust_msg = nw.trust_all_current()
    print(f"[home-ops] {trust_msg}")
    print(f"[home-ops] {nw.status()} â†’ {NET_STATE}")

    print("[home-ops] first encrypted backupâ€¦")
    bak = SecureBackup()
    print(f"[home-ops] {bak.run(label='setup')}")
    print(f"[home-ops] {bak.status()}")

    dm = DeadmanSwitch(
        enabled=s.deadman_enabled,
        phrase=s.deadman_phrase,
        interval_sec=s.deadman_hours * 3600.0,
    )
    dm.save()
    print(f"[home-ops] {dm.status()} â†’ {DEAD_STATE}")

    print("[home-ops] process scanâ€¦")
    print(f"[home-ops] {ProcessHarden().speak_scan()}")

    print("[home-ops] space weather probeâ€¦")
    try:
        print(f"[home-ops] {SpaceWeather().speak_brief()}")
    except Exception as e:
        print(f"[home-ops] space weather skip: {e}")

    print(f"[home-ops] translate check: {translate_casual('hello', to='es')}")
    print(f"[home-ops] {edge_status()}")
    print("[home-ops] DONE â€” say 'home ops' in Jarvis, or run: python -m jarvis.edge_daemon")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

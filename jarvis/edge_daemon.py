"""Headless edge daemon — net watch, backups tick, deadman, space weather."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from jarvis.config import Settings
    from jarvis.core.net_watch import NetWatch
    from jarvis.core.deadman import DeadmanSwitch
    from jarvis.core.space_weather import SpaceWeather
    from jarvis.core.secure_backup import SecureBackup
    from jarvis.core.phone_bridge import PhoneBridge
    from jarvis.core.instance import is_jarvis_running

    settings = Settings.load()
    phone = None
    try:
        topic = getattr(settings, "phone_ntfy_topic", "") or ""
        if topic:
            phone = PhoneBridge(
                topic=topic,
                server=getattr(settings, "phone_ntfy_server", "") or "https://ntfy.sh",
            )
    except Exception as e:
        print(f"[edge] phone: {e}")

    def alert(msg: str) -> None:
        print(f"[edge] ALERT {msg}")
        try:
            if phone:
                phone.notify(msg, title="JARVIS EDGE")
        except Exception:
            pass

    # When the desk HUD is live it owns net-watch — avoid double ARP + double alerts.
    hud_owns_net = is_jarvis_running()
    net_enabled = bool(getattr(settings, "net_watch_enabled", True)) and not hud_owns_net
    net = NetWatch(
        enabled=net_enabled,
        poll_sec=float(getattr(settings, "net_watch_poll_sec", 60) or 60),
        on_alert=lambda msg, _d: alert(msg),
    )
    if hud_owns_net:
        print("[edge] HUD online — skipping net watch (HUD owns LAN alerts)")
    dead = DeadmanSwitch(
        enabled=bool(getattr(settings, "deadman_enabled", False)),
        phrase=str(getattr(settings, "deadman_phrase", "jarvis clear") or "jarvis clear"),
        interval_sec=float(getattr(settings, "deadman_hours", 24) or 24) * 3600.0,
        on_miss=lambda msg: alert(msg),
    )
    backup = SecureBackup()
    space = SpaceWeather(
        on_severe=lambda msg: (alert(msg), backup.run(label="solar")),
    )

    if net_enabled:
        net.start()
    print("[edge] daemon online — backups · deadman · space weather"
          + (" · net watch" if net_enabled else ""))
    last_backup = time.time()
    last_space = 0.0
    last_hud_check = 0.0
    backup_hours = float(getattr(settings, "auto_backup_hours", 12) or 12)
    backup_sec = max(3600.0, backup_hours * 3600.0)
    while True:
        try:
            # Re-check HUD ownership so edge picks up net watch when PC HUD exits
            if time.time() - last_hud_check > 90:
                last_hud_check = time.time()
                want_net = bool(getattr(settings, "net_watch_enabled", True)) and not is_jarvis_running()
                if want_net and not net.enabled:
                    net.enabled = True
                    net.start()
                    print("[edge] HUD offline — net watch armed")
                elif not want_net and net.enabled:
                    net.enabled = False
                    net.stop()
                    print("[edge] HUD online — net watch released")
            miss = dead.tick()
            if miss:
                # on_miss already alerted; don't double-print unless no callback
                pass
            if time.time() - last_space > 600:
                last_space = time.time()
                space.poll_severe()
            if time.time() - last_backup > backup_sec:
                last_backup = time.time()
                alert(backup.run(label="edge"))
        except Exception as e:
            print(f"[edge] tick: {e}")
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())

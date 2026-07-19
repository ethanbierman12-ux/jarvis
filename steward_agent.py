"""
Offline steward agent — works while Jarvis HUD is closed.

Runs queued away-jobs: weather cache, system pulse, brief prep,
spend digest, chrome digest, wake reminders.

Install: install_steward.bat  (Startup folder alongside F5 wake agent)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCK = ROOT / "jarvis" / "data" / "steward_agent.lock"
TICK_SEC = 20  # faster for realtime mail while away
TICK_IDLE = 45


def _already_locked() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            old = int(LOCK.read_text(encoding="utf-8").strip() or "0")
            import psutil

            if old and psutil.pid_exists(old):
                try:
                    p = psutil.Process(old)
                    cmd = " ".join(p.cmdline()).lower()
                    if "steward_agent" in cmd:
                        return True
                except Exception:
                    pass
        except Exception:
            pass
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return False


def _jarvis_ui_running() -> bool:
    try:
        import psutil
    except Exception:
        return False
    me = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == me:
                continue
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            name = (p.info.get("name") or "").lower()
            if "python" not in name and "pythonw" not in name:
                continue
            if "steward_agent" in cmd or "wake_agent" in cmd:
                continue
            if "main.py" in cmd and ("jarvis" in cmd.replace("\\", "/") or str(ROOT).lower().replace("\\", "/") in cmd.replace("\\", "/")):
                return True
            if "-m jarvis" in cmd:
                return True
        except Exception:
            continue
    return False


def main() -> int:
    if _already_locked():
        print("[steward] already running — exit")
        return 0

    print("[steward] offline ops armed — working while Jarvis HUD is closed")
    print(f"[steward] project: {ROOT}")
    try:
        from jarvis.core.away_steward import AwaySteward

        steward = AwaySteward()
        # Seed a quiet heartbeat so first wake has something
        steward.enqueue("heartbeat", label="Steward online")
        while True:
            try:
                status_path = ROOT / "jarvis" / "data" / "steward_status.json"
                away = False
                try:
                    import json

                    st = json.loads(status_path.read_text(encoding="utf-8"))
                    away = bool(st.get("away_mode")) and bool(st.get("mail_watch", True))
                except Exception:
                    away = False
                lines = steward.tick_offline()
                for line in lines:
                    print(f"[steward] {line}")
            except Exception as e:
                print(f"[steward] tick error: {e}")
            time.sleep(TICK_SEC if away else TICK_IDLE)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[steward] fatal: {e}")
        return 1
    finally:
        try:
            if LOCK.exists() and LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
                LOCK.unlink(missing_ok=True)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

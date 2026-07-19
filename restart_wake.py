"""Restart F5 wake agent with the latest wake_agent.py."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT = ROOT / "wake_agent.py"
PY = Path(r"C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe")
PYW = Path(r"C:\Users\ethan\AppData\Local\Programs\Python\Python313\pythonw.exe")
VBS = (
    Path(os.environ["APPDATA"])
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / "Startup"
    / "JarvisF5Wake.vbs"
)


def main() -> None:
    try:
        import psutil

        for p in psutil.process_iter(["pid", "cmdline"]):
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if "wake_agent.py" in cmd:
                try:
                    p.kill()
                    print("killed", p.pid)
                except Exception as e:
                    print("kill fail", e)
    except Exception as e:
        print("scan fail", e)

    time.sleep(0.8)
    VBS.parent.mkdir(parents=True, exist_ok=True)
    launcher = str(PYW if PYW.exists() else PY if PY.exists() else "pythonw")
    # Prefer console python for wake agent so RegisterHotKey message loop is solid;
    # still launch hidden via pythonw if available — Win32 hotkey works either way.
    VBS.write_text(
        "Set sh = CreateObject(\"WScript.Shell\")\n"
        f"sh.CurrentDirectory = \"{ROOT}\"\n"
        f"sh.Run chr(34) & \"{launcher}\" & chr(34) & \" \" & chr(34) & \"{AGENT}\" & chr(34), 0, False\n",
        encoding="utf-8",
    )
    # Also start immediately
    creation = 0x08000000  # CREATE_NO_WINDOW
    exe = str(PY if PY.exists() else launcher)
    subprocess.Popen(
        [exe, str(AGENT)],
        cwd=str(ROOT),
        creationflags=creation if sys_platform_win() else 0,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("wake agent restarted with", exe)
    print("vbs:", VBS)


def sys_platform_win() -> bool:
    import sys

    return sys.platform == "win32"


if __name__ == "__main__":
    main()

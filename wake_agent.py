"""
Always-on F5 wake agent.

Press F5 anywhere on Windows:
  - If Jarvis is not running → launch it
  - If Jarvis is already running → focus its window

Uses Win32 RegisterHotKey (reliable) with keyboard-lib fallback.
Install: install_f5_wake.bat
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCK = ROOT / "jarvis" / "data" / "wake_agent.lock"
LOG = ROOT / "jarvis" / "data" / "wake_agent.log"
MAIN = ROOT / "main.py"
PY = Path(r"C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe")
PYW = Path(r"C:\Users\ethan\AppData\Local\Programs\Python\Python313\pythonw.exe")

_last_f5 = 0.0
HOTKEY_ID = 0x4A46  # "JF"


def _log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(f"[wake] {msg}")
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _python() -> str:
    # Prefer python.exe so launch failures can be diagnosed; hide console via flags
    if PY.exists():
        return str(PY)
    if PYW.exists():
        return str(PYW)
    return sys.executable


def _fast_running() -> bool:
    try:
        sys.path.insert(0, str(ROOT))
        from jarvis.core.instance import is_jarvis_running, is_launching

        if is_jarvis_running():
            return True
        if is_launching(max_age_sec=12.0):
            return True
        return False
    except Exception:
        return False


def _scan_running() -> bool:
    try:
        import psutil
    except Exception:
        return False
    me = os.getpid()
    root_l = str(ROOT).lower().replace("\\", "/")
    main_l = str(MAIN).lower().replace("\\", "/")
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == me:
                continue
            name = (p.info.get("name") or "").lower()
            if "python" not in name and "pythonw" not in name:
                continue
            cmd = " ".join(p.info.get("cmdline") or []).lower().replace("\\", "/")
            if "wake_agent" in cmd:
                continue
            # Strict: must be THIS project's main.py
            if main_l in cmd:
                return True
            if cmd.endswith("main.py") and root_l in cmd:
                return True
            if "-m jarvis" in cmd and root_l in cmd:
                return True
        except Exception:
            continue
    return False


def _jarvis_running() -> bool:
    if _fast_running():
        return True
    return _scan_running()


def _launch_jarvis() -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from jarvis.core.instance import mark_launching

        mark_launching()
    except Exception:
        pass

    creation = 0
    if sys.platform == "win32":
        # CREATE_NO_WINDOW | DETACHED_PROCESS | NEW_PROCESS_GROUP
        creation = 0x08000000 | 0x00000008 | 0x00000200

    log_out = open(LOG, "a", encoding="utf-8")
    try:
        log_out.write(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} LAUNCH {_python()} {MAIN}\n")
        log_out.flush()
    except Exception:
        pass

    subprocess.Popen(
        [_python(), str(MAIN)],
        cwd=str(ROOT),
        stdout=log_out,
        stderr=log_out,
        stdin=subprocess.DEVNULL,
        creationflags=creation,
        close_fds=False,
    )
    _log("launching Jarvis…")


def _focus() -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from jarvis.core.instance import focus_existing_window

        if focus_existing_window():
            _log("focused existing Jarvis window")
        else:
            _log("Jarvis running but window not found — relaunch")
            _launch_jarvis()
    except Exception as e:
        _log(f"focus failed: {e}")


def _on_f5() -> None:
    global _last_f5
    try:
        now = time.time()
        if now - _last_f5 < 0.7:
            return
        _last_f5 = now
        _log("F5 pressed")

        if _jarvis_running():
            _focus()
            return
        _launch_jarvis()
    except Exception as e:
        _log(f"F5 failed: {e}")


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
                    if "wake_agent" in cmd:
                        return True
                except Exception:
                    pass
        except Exception:
            pass
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return False


def _run_win32_hotkey() -> None:
    """Reliable global F5 via RegisterHotKey (no admin required)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    MOD_NOREPEAT = 0x4000
    VK_F5 = 0x74
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_F5):
        err = kernel32.GetLastError()
        raise OSError(f"RegisterHotKey(F5) failed error={err}")

    _log("Win32 F5 hotkey registered")
    try:
        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                _on_f5()
            else:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)


def _run_keyboard_fallback() -> None:
    import keyboard

    keyboard.add_hotkey("f5", _on_f5, suppress=False)
    _log("keyboard-lib F5 hotkey registered (fallback)")
    keyboard.wait()


def main() -> int:
    if _already_locked():
        _log("already running — exit")
        return 0

    _log(f"armed — project={ROOT}")
    try:
        if sys.platform == "win32":
            try:
                _run_win32_hotkey()
            except Exception as e:
                _log(f"Win32 hotkey failed ({e}) — trying keyboard lib")
                _run_keyboard_fallback()
        else:
            _run_keyboard_fallback()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        _log(f"fatal: {e}")
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

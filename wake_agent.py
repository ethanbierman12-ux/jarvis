"""
Always-on F3 wake agent — the global START button.

Press F3 anywhere on Windows:
  - If Jarvis is not running → launch it
  - If Jarvis is already running → soft-reload core (exit 0) and ensure relaunch

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
RUNNER = ROOT / "runner.py"
PY = Path(r"C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe")
PYW = Path(r"C:\Users\ethan\AppData\Local\Programs\Python\Python313\pythonw.exe")

_last_wake = 0.0
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


def _scan_python_cmd(match: str) -> bool:
    try:
        import psutil
    except Exception:
        return False
    me = os.getpid()
    needle = match.lower().replace("\\", "/")
    root_l = str(ROOT).lower().replace("\\", "/")
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
            if needle in cmd and root_l in cmd:
                return True
        except Exception:
            continue
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


def _watchdog_running() -> bool:
    return _scan_python_cmd("runner.py")


def _creation_flags() -> int:
    if sys.platform == "win32":
        # CREATE_NO_WINDOW | DETACHED_PROCESS | NEW_PROCESS_GROUP
        return 0x08000000 | 0x00000008 | 0x00000200
    return 0


def _launch_jarvis(*, prefer_watchdog: bool = True) -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from jarvis.core.instance import mark_launching

        mark_launching()
    except Exception:
        pass

    target = RUNNER if prefer_watchdog and RUNNER.exists() else MAIN
    # Avoid stacking watchdogs — if runner already alive, start HUD only
    if target == RUNNER and _watchdog_running():
        target = MAIN

    log_out = open(LOG, "a", encoding="utf-8")
    try:
        log_out.write(
            f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} LAUNCH {_python()} {target}\n"
        )
        log_out.flush()
    except Exception:
        pass

    subprocess.Popen(
        [_python(), str(target)],
        cwd=str(ROOT),
        stdout=log_out,
        stderr=log_out,
        stdin=subprocess.DEVNULL,
        creationflags=_creation_flags(),
        close_fds=False,
    )
    _log(f"launching Jarvis via {target.name}…")


def _focus() -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from jarvis.core.instance import focus_existing_window

        if focus_existing_window():
            _log("focused existing Jarvis window")
            return True
        _log("Jarvis running but window not found")
        return False
    except Exception as e:
        _log(f"focus failed: {e}")
        return False


def _force_kill_jarvis() -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from jarvis.core.instance import jarvis_pid, release_instance
        import psutil

        pid = jarvis_pid()
        if pid and psutil.pid_exists(pid):
            _log(f"force-stopping Jarvis pid={pid}")
            try:
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(timeout=2.5)
                except Exception:
                    p.kill()
            except Exception as e:
                _log(f"terminate failed: {e}")
        # Also scan for orphaned main.py in this project
        root_l = str(ROOT).lower().replace("\\", "/")
        main_l = str(MAIN).lower().replace("\\", "/")
        me = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == me:
                    continue
                name = (proc.info.get("name") or "").lower()
                if "python" not in name and "pythonw" not in name:
                    continue
                cmd = " ".join(proc.info.get("cmdline") or []).lower().replace("\\", "/")
                if "wake_agent" in cmd or "runner.py" in cmd:
                    continue
                if main_l in cmd or ("-m jarvis" in cmd and root_l in cmd):
                    psutil.Process(proc.info["pid"]).terminate()
            except Exception:
                continue
        try:
            release_instance()
        except Exception:
            pass
    except Exception as e:
        _log(f"force kill error: {e}")


def _request_hud_reload() -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from jarvis.core.instance import request_reload

        request_reload()
        _log("reload.request written")
    except Exception as e:
        _log(f"reload request failed: {e}")


def _ensure_relaunch_after_exit(*, had_watchdog: bool) -> None:
    """After HUD exits for reload, make sure something brings it back."""
    # Watchdog sleeps ~2s before relaunch — give it room
    wait_s = 4.0 if had_watchdog else 0.6
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _jarvis_running():
            _log("Jarvis back online")
            return
        time.sleep(0.25)
    if _jarvis_running():
        return
    _log("relaunching after reload")
    _launch_jarvis(prefer_watchdog=not had_watchdog)


def _on_wake() -> None:
    global _last_wake
    try:
        now = time.time()
        if now - _last_wake < 0.7:
            return
        _last_wake = now
        _log("F3 pressed")

        if _jarvis_running():
            had_watchdog = _watchdog_running()
            _focus()
            _request_hud_reload()
            # Wait for soft exit (HUD polls reload.request)
            soft_deadline = time.time() + 5.0
            while time.time() < soft_deadline and _jarvis_running():
                time.sleep(0.2)
            if _jarvis_running():
                _log("soft reload timed out — force stop")
                _force_kill_jarvis()
                time.sleep(0.4)
            if not _jarvis_running():
                _ensure_relaunch_after_exit(had_watchdog=had_watchdog)
            else:
                _log("Jarvis still running after F3 — focused only")
            return

        _launch_jarvis(prefer_watchdog=True)
    except Exception as e:
        _log(f"F3 failed: {e}")


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
            # Stale lock (dead PID or non-wake process) — reclaim
            _log(f"clearing stale wake lock pid={old}")
        except Exception:
            pass
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return False


def _run_win32_hotkey() -> None:
    """Reliable global F3 via RegisterHotKey (no admin required)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    MOD_NOREPEAT = 0x4000
    VK_F3 = 0x72
    WM_HOTKEY = 0x0312

    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_F3):
        err = kernel32.GetLastError()
        raise OSError(f"RegisterHotKey(F3) failed error={err}")

    _log("Win32 F3 hotkey registered")
    try:
        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                _on_wake()
            else:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)


def _run_keyboard_fallback() -> None:
    import keyboard

    keyboard.add_hotkey("f3", _on_wake, suppress=False)
    _log("keyboard-lib F3 hotkey registered (fallback)")
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

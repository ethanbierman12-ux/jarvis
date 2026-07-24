"""Single-instance PID lock — instant F5 checks without scanning every process."""

from __future__ import annotations

import atexit
import os
import sys
import time
from pathlib import Path

from jarvis.config import DATA_DIR

PID_FILE = DATA_DIR / "jarvis.pid"
LAUNCH_LOCK = DATA_DIR / "jarvis.launching"
RELOAD_REQUEST = DATA_DIR / "reload.request"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil

        if not psutil.pid_exists(pid):
            return False
        p = psutil.Process(pid)
        if not p.is_running():
            return False
        # Reject zombies / other users' dead handles
        try:
            _ = p.status()
        except Exception:
            return False
        return True
    except Exception:
        # Fallback: signal 0 on POSIX; on Windows os.kill is limited — try OpenProcess via psutil only
        if sys.platform == "win32":
            return False
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False


def is_jarvis_running() -> bool:
    """True if a live Jarvis HUD owns the PID file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return False
    if not _pid_alive(pid):
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        return False
    return True


def is_launching(max_age_sec: float = 8.0) -> bool:
    """True if a launch was kicked off recently (debounce double-F5)."""
    if not LAUNCH_LOCK.exists():
        return False
    try:
        age = time.time() - LAUNCH_LOCK.stat().st_mtime
        if age > max_age_sec:
            LAUNCH_LOCK.unlink(missing_ok=True)
            return False
        return True
    except Exception:
        return False


def mark_launching() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCH_LOCK.write_text(str(time.time()), encoding="utf-8")


def clear_launching() -> None:
    try:
        LAUNCH_LOCK.unlink(missing_ok=True)
    except Exception:
        pass


def request_reload() -> None:
    """Ask the running HUD to exit with code 0 (watchdog / wake-agent relaunch)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RELOAD_REQUEST.write_text(str(time.time()), encoding="utf-8")


def consume_reload_request() -> bool:
    """True once if a reload was requested (clears the flag)."""
    if not RELOAD_REQUEST.exists():
        return False
    try:
        RELOAD_REQUEST.unlink(missing_ok=True)
    except Exception:
        try:
            RELOAD_REQUEST.unlink()
        except Exception:
            return False
    return True


def jarvis_pid() -> int:
    """PID from the lock file, or 0 if missing/invalid."""
    if not PID_FILE.exists():
        return 0
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def claim_instance() -> bool:
    """
    Claim this process as the Jarvis HUD.
    Returns False if another live instance already owns the lock.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if is_jarvis_running():
        try:
            existing = int(PID_FILE.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            existing = 0
        if existing and existing != os.getpid():
            return False
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    clear_launching()
    atexit.register(release_instance)
    return True


def release_instance() -> None:
    try:
        if PID_FILE.exists():
            cur = PID_FILE.read_text(encoding="utf-8").strip()
            if cur == str(os.getpid()):
                PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    clear_launching()


def focus_existing_window() -> bool:
    """Bring an already-running Jarvis window to the foreground (Windows)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _enum(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length < 4:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.lower()
            if "jarvis" in title:
                found.append(hwnd)
            return True

        user32.EnumWindows(_enum, 0)
        if not found:
            return False
        hwnd = found[0]
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False

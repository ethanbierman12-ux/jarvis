"""Windows subprocess helpers — never flash a console window."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def no_window_flags() -> int:
    """CREATE_NO_WINDOW on Windows; 0 elsewhere."""
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))


def run_hidden(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    kwargs.setdefault("creationflags", no_window_flags())
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(args, **kwargs)


def check_output_hidden(args: list[str], **kwargs: Any) -> bytes | str:
    kwargs.setdefault("creationflags", no_window_flags())
    kwargs.setdefault("stderr", subprocess.DEVNULL)
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.check_output(args, **kwargs)


def powershell_hidden(command: str, **kwargs: Any) -> bytes | str:
    """Run a PowerShell -Command script with no visible window (steward/mail/etc.)."""
    args = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle",
        "Hidden",
        "-Command",
        command,
    ]
    flags = no_window_flags()
    # Also hide any console that PowerShell might still allocate
    si = None
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
    kwargs.setdefault("creationflags", flags)
    kwargs.setdefault("stderr", subprocess.DEVNULL)
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    kwargs.setdefault("startupinfo", si)
    return subprocess.check_output(args, **kwargs)

#!/usr/bin/env python3
"""Watchdog — keeps Jarvis alive and reboots after intentional core reloads."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"

# Exit codes understood by this watchdog (set by the Jarvis process).
EXIT_RELOAD = 0  # graceful reload after software update / reboot core
EXIT_OFFLINE = 99  # intentional full shutdown of the watchdog shell


def run_watchdog() -> int:
    """Launch main.py in a loop until offline (99) or the user stops the shell."""
    print("[Watchdog Engine]: Initializing J.A.R.V.I.S. architecture monitoring core...")

    while True:
        process = subprocess.Popen(
            [sys.executable, str(MAIN)],
            cwd=str(ROOT),
        )
        process.wait()
        code = process.returncode if process.returncode is not None else 1

        if code == EXIT_RELOAD:
            print(
                "\n[Watchdog Engine]: J.A.R.V.I.S. closed gracefully for software updates. "
                "Re-booting core files..."
            )
            time.sleep(2)
            continue

        if code == EXIT_OFFLINE:
            print(
                "\n[Watchdog Engine]: Manual system shutdown command received. "
                "Terminating watchdog shell."
            )
            return 0

        print(
            "\n[Watchdog Engine]: J.A.R.V.I.S. encountered an unplanned terminal crash. "
            "Initiating standard recovery loop..."
        )
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(run_watchdog())

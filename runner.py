#!/usr/bin/env python3
"""Watchdog — keeps Jarvis alive and reboots after intentional core reloads."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
CRASH_LOG = ROOT / "jarvis" / "data" / "last_crash.txt"

# Exit codes understood by this watchdog (set by the Jarvis process).
EXIT_RELOAD = 0  # graceful reload after software update / reboot core
EXIT_OFFLINE = 99  # intentional full shutdown of the watchdog shell

# Rapid-crash protection — crashes closer together than this stretch the
# recovery delay, so a boot-loop can't relaunch the HUD forever.
RAPID_CRASH_SEC = 60.0
BACKOFF_STEPS = (5.0, 15.0, 30.0, 60.0)
GIVE_UP_STREAK = 6  # consecutive rapid crashes before the watchdog stands down


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _record_crash(code: int, streak: int) -> None:
    """Persist crash forensics so 'unplanned crash' is diagnosable later."""
    try:
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{_stamp()} exit_code={code} rapid_streak={streak}\n")
    except Exception:
        pass


def run_watchdog() -> int:
    """Launch main.py in a loop until offline (99) or the user stops the shell."""
    print("[Watchdog Engine]: Initializing J.A.R.V.I.S. architecture monitoring core...")

    crash_streak = 0
    last_crash_at = 0.0

    while True:
        started = time.time()
        process = subprocess.Popen(
            [sys.executable, str(MAIN)],
            cwd=str(ROOT),
        )
        process.wait()
        code = process.returncode if process.returncode is not None else 1

        if code == EXIT_RELOAD:
            crash_streak = 0
            print(
                f"\n[Watchdog Engine] {_stamp()}: J.A.R.V.I.S. closed gracefully for "
                "software updates. Re-booting core files..."
            )
            time.sleep(2)
            continue

        if code == EXIT_OFFLINE:
            print(
                f"\n[Watchdog Engine] {_stamp()}: Manual system shutdown command "
                "received. Terminating watchdog shell."
            )
            return 0

        # Unplanned exit — track whether we're in a boot-loop
        now = time.time()
        ran_for = now - started
        if now - last_crash_at < RAPID_CRASH_SEC or ran_for < RAPID_CRASH_SEC:
            crash_streak += 1
        else:
            crash_streak = 1
        last_crash_at = now
        _record_crash(code, crash_streak)

        # Negative codes on Windows are native faults (e.g. -1073741819 =
        # 0xC0000005 access violation) — worth calling out explicitly.
        kind = "native fault" if code < 0 else "python exit"
        print(
            f"\n[Watchdog Engine] {_stamp()}: J.A.R.V.I.S. encountered an unplanned "
            f"terminal crash (exit={code}, {kind}, ran {ran_for:.0f}s). "
            "Initiating standard recovery loop..."
        )

        if crash_streak >= GIVE_UP_STREAK:
            print(
                f"[Watchdog Engine] {_stamp()}: {crash_streak} rapid crashes in a row "
                f"— standing down to avoid a relaunch storm. See {CRASH_LOG} and "
                "jarvis/data/jarvis.log, then press F3 to relaunch."
            )
            return 1

        delay = BACKOFF_STEPS[min(crash_streak - 1, len(BACKOFF_STEPS) - 1)]
        print(f"[Watchdog Engine]: recovery in {delay:.0f}s (streak {crash_streak})")
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(run_watchdog())

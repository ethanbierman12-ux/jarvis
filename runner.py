#!/usr/bin/env python3
"""Watchdog — keeps Jarvis alive for intentional reloads only.

By default does NOT auto-recover from crashes — crash loops looked like
Jarvis starting himself (especially after an accidental F3 in bed).
Set JARVIS_RECOVER_CRASH=1 to restore the old recovery behaviour.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
CRASH_LOG = ROOT / "jarvis" / "data" / "last_crash.txt"

EXIT_RELOAD = 0  # graceful reload after software update / reboot core
EXIT_OFFLINE = 99  # intentional full shutdown of the watchdog shell

# Opt-in crash recovery (off by default — prevents phantom relaunches)
RECOVER_ON_CRASH = os.environ.get("JARVIS_RECOVER_CRASH", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
RAPID_CRASH_SEC = 60.0
BACKOFF_STEPS = (5.0, 15.0, 30.0, 60.0)
GIVE_UP_STREAK = 3


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _record_crash(code: int, streak: int) -> None:
    try:
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{_stamp()} exit_code={code} rapid_streak={streak}\n")
    except Exception:
        pass


def run_watchdog() -> int:
    print("[Watchdog Engine]: Initializing J.A.R.V.I.S. architecture monitoring core...")
    if not RECOVER_ON_CRASH:
        print(
            "[Watchdog Engine]: crash auto-recover OFF "
            "(set JARVIS_RECOVER_CRASH=1 to enable)"
        )

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

        # Safety git snapshot on crash (best-effort, never blocks forever)
        try:
            snap_script = ROOT / "scripts" / "crash_snapshot.py"
            if snap_script.exists():
                subprocess.run(
                    [sys.executable, str(snap_script)],
                    cwd=str(ROOT),
                    timeout=25,
                    capture_output=True,
                )
        except Exception:
            pass

        now = time.time()
        ran_for = now - started
        if now - last_crash_at < RAPID_CRASH_SEC or ran_for < RAPID_CRASH_SEC:
            crash_streak += 1
        else:
            crash_streak = 1
        last_crash_at = now
        _record_crash(code, crash_streak)

        kind = "native fault" if code < 0 or code > 100000 else "python exit"
        print(
            f"\n[Watchdog Engine] {_stamp()}: J.A.R.V.I.S. encountered an unplanned "
            f"terminal crash (exit={code}, {kind}, ran {ran_for:.0f}s)."
        )

        if not RECOVER_ON_CRASH:
            print(
                f"[Watchdog Engine] {_stamp()}: standing down (no crash recover). "
                f"See {CRASH_LOG}. Double-tap F3 when you want Jarvis again."
            )
            return 1

        print("[Watchdog Engine]: Initiating recovery loop…")
        if crash_streak >= GIVE_UP_STREAK:
            print(
                f"[Watchdog Engine] {_stamp()}: {crash_streak} rapid crashes — "
                f"standing down. See {CRASH_LOG}."
            )
            return 1

        delay = BACKOFF_STEPS[min(crash_streak - 1, len(BACKOFF_STEPS) - 1)]
        print(f"[Watchdog Engine]: recovery in {delay:.0f}s (streak {crash_streak})")
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(run_watchdog())

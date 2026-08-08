"""Deadman switch — daily verbal handshake or local lockdown / wipe-prep alert."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

from jarvis.config import DATA_DIR

STATE_PATH = DATA_DIR / "deadman.json"


class DeadmanSwitch:
    """
    Requires a spoken passphrase within `interval_sec`.
    Missed check-in -> callback (lock / notify) — never silent-wipes without HITL.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        phrase: str = "jarvis clear",
        interval_sec: float = 86400.0,
        on_miss: Callable[[str], None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.phrase = (phrase or "jarvis clear").strip().lower()
        self.interval_sec = max(3600.0, float(interval_sec))
        self.on_miss = on_miss
        self.last_ok = time.time()
        self.last_miss_ts = 0.0
        self._armed_alert = False
        self._load()

    def _load(self) -> None:
        try:
            if STATE_PATH.exists():
                raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                self.enabled = bool(raw.get("enabled", self.enabled))
                self.phrase = str(raw.get("phrase") or self.phrase).lower()
                self.interval_sec = float(raw.get("interval_sec") or self.interval_sec)
                self.last_ok = float(raw.get("last_ok") or time.time())
                self.last_miss_ts = float(raw.get("last_miss_ts") or 0)
                # Already alerted this overdue window (edge + HUD share state)
                if self.last_miss_ts > self.last_ok:
                    self._armed_alert = True
        except Exception:
            pass

    def save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(
                json.dumps(
                    {
                        "enabled": self.enabled,
                        "phrase": self.phrase,
                        "interval_sec": self.interval_sec,
                        "last_ok": self.last_ok,
                        "last_miss_ts": self.last_miss_ts,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def status(self) -> str:
        if not self.enabled:
            return "Deadman switch off. Say arm deadman to require a daily handshake."
        left = max(0, int(self.interval_sec - (time.time() - self.last_ok)))
        hrs = left // 3600
        return (
            f'Deadman armed · phrase "{self.phrase}" · '
            f"next check-in due in {hrs}h ({left // 60}m)."
        )

    def arm(self, phrase: str | None = None, hours: float = 24.0) -> str:
        self.enabled = True
        if phrase:
            self.phrase = phrase.strip().lower()
        self.interval_sec = max(3600.0, hours * 3600.0)
        self.last_ok = time.time()
        self.last_miss_ts = 0.0
        self._armed_alert = False
        self.save()
        return (
            f'Deadman armed. Say "{self.phrase}" within {hours:.0f} hours '
            "or I lock down and alert."
        )

    def disarm(self) -> str:
        self.enabled = False
        self.save()
        return "Deadman switch disarmed."

    def check_in(self, utterance: str) -> str | None:
        if not self.enabled:
            return None
        t = (utterance or "").strip().lower()
        if self.phrase in t or t == self.phrase:
            self.last_ok = time.time()
            self.last_miss_ts = 0.0
            self._armed_alert = False
            self.save()
            return "Deadman check-in received. Timer reset."
        return None

    def tick(self) -> Optional[str]:
        if not self.enabled:
            return None
        overdue = (time.time() - self.last_ok) > self.interval_sec
        if overdue and not self._armed_alert:
            self._armed_alert = True
            self.last_miss_ts = time.time()
            self.save()
            msg = (
                "DEADMAN MISS - no verbal handshake in time. "
                "Locking workstation and notifying phone."
            )
            if self.on_miss:
                try:
                    self.on_miss(msg)
                except Exception:
                    pass
            return msg
        return None

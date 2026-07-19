"""Clipboard guard — wipe secrets after 60s; keyboard cadence for focus stress."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from typing import Callable, Optional

try:
    import pyperclip
except Exception:
    pyperclip = None  # type: ignore


SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*\S{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS-ish
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),  # GitHub PAT
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),  # Slack
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),  # OpenAI-ish
]


class ClipboardGuard:
    def __init__(
        self,
        wipe_after_sec: float = 60.0,
        on_wipe: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.wipe_after = wipe_after_sec
        self.on_wipe = on_wipe
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last = ""
        self._marked_at = 0.0
        self._sensitive = False

    def start(self) -> None:
        if self._running or pyperclip is None:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="jarvis-clipguard"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _is_secret(self, text: str) -> bool:
        if not text or len(text) < 6:
            return False
        if len(text) > 4000:
            return False
        return any(p.search(text) for p in SECRET_PATTERNS)

    def _loop(self) -> None:
        while self._running:
            try:
                cur = pyperclip.paste() or ""
                if cur != self._last:
                    self._last = cur
                    if self._is_secret(cur):
                        self._sensitive = True
                        self._marked_at = time.time()
                        print("[clipguard] sensitive clipboard detected — will wipe")
                    else:
                        self._sensitive = False
                if (
                    self._sensitive
                    and self._marked_at
                    and time.time() - self._marked_at >= self.wipe_after
                ):
                    if (pyperclip.paste() or "") == self._last:
                        pyperclip.copy("")
                        self._sensitive = False
                        self._last = ""
                        if self.on_wipe:
                            self.on_wipe("Clipboard cleared — sensitive data expired.")
                        print("[clipguard] wiped sensitive clipboard")
            except Exception:
                pass
            time.sleep(1.0)


class KeyboardCadence:
    """Estimate typing stress from global key rate (optional keyboard hook)."""

    def __init__(self) -> None:
        self._times: deque[float] = deque(maxlen=200)
        self._ok = False

    def start(self) -> None:
        def _arm() -> None:
            try:
                import keyboard

                def _on(_e) -> None:
                    self._times.append(time.time())

                keyboard.on_press(_on, suppress=False)
                self._ok = True
                print("[cadence] keyboard stress sensor armed")
            except Exception as e:
                print(f"[cadence] unavailable: {e}")

        threading.Thread(target=_arm, daemon=True, name="jarvis-cadence").start()

    def keys_per_minute(self) -> float:
        now = time.time()
        recent = [t for t in self._times if now - t <= 60.0]
        return float(len(recent))

    def is_high_stress(self, threshold_kpm: float = 180.0) -> bool:
        return self.keys_per_minute() >= threshold_kpm

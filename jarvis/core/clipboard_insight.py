"""Clipboard insight daemon — offer help when an error traceback is copied."""

from __future__ import annotations

import re
import threading
import time
from typing import Callable


_ERROR_RE = re.compile(
    r"(Traceback \(most recent call last\)|"
    r"Error:\s+\w+|"
    r"Exception in thread|"
    r"FATAL ERROR|"
    r"npm ERR!|"
    r"ModuleNotFoundError|"
    r"TypeError:|"
    r"ReferenceError:|"
    r"panic:|"
    r"FAILED\s+\d+)",
    re.I,
)


class ClipboardInsight:
    def __init__(
        self,
        *,
        on_error: Callable[[str], None] | None = None,
        enabled: bool = True,
        cooldown_sec: float = 120.0,
    ) -> None:
        self.on_error = on_error
        self.enabled = bool(enabled)
        self.cooldown = float(cooldown_sec)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last = ""
        self._last_fire = 0.0

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="jarvis-clip-insight", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.enabled:
                    self._tick()
            except Exception:
                pass
            self._stop.wait(1.2)

    def _tick(self) -> None:
        try:
            import pyperclip
        except Exception:
            return
        try:
            text = pyperclip.paste() or ""
        except Exception:
            return
        if not text or text == self._last:
            return
        self._last = text
        if len(text) < 24 or len(text) > 12_000:
            return
        if not _ERROR_RE.search(text):
            return
        now = time.time()
        if now - self._last_fire < self.cooldown:
            return
        self._last_fire = now
        snippet = text.strip()[:400]
        if self.on_error:
            self.on_error(snippet)

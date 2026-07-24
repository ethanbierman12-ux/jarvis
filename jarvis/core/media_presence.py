"""Pause Netflix/YouTube media when you stand (webcam absence)."""

from __future__ import annotations

import time
from typing import Callable


class MediaPresenceController:
    """
    When presence drops, send a media pause key (Space / Media Play-Pause).
    When you return within resume_window, send play again.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        pause_after_sec: float = 2.5,
        resume: bool = True,
    ) -> None:
        self.enabled = enabled
        self.pause_after_sec = pause_after_sec
        self.resume = resume
        self._absent_at: float | None = None
        self._paused = False
        self._press: Callable[[], None] | None = None
        try:
            import pyautogui

            def _press() -> None:
                # Media play/pause is more reliable across browsers than space
                try:
                    pyautogui.press("playpause")
                except Exception:
                    pyautogui.press("space")

            self._press = _press
        except Exception:
            self._press = None

    def on_presence(self, present: bool) -> str:
        if not self.enabled or not self._press:
            return ""
        now = time.time()
        if present:
            self._absent_at = None
            if self._paused and self.resume:
                try:
                    self._press()
                    self._paused = False
                    return "Resumed media — welcome back."
                except Exception:
                    self._paused = False
            return ""
        if self._absent_at is None:
            self._absent_at = now
            return ""
        if not self._paused and (now - self._absent_at) >= self.pause_after_sec:
            try:
                self._press()
                self._paused = True
                return "Paused media — you stepped away."
            except Exception:
                return ""
        return ""

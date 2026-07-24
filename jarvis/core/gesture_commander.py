"""Gesture → command mapping for camera / desk control."""

from __future__ import annotations

import time
from typing import Callable


class GestureCommander:
    """
    Maps stable swipe/fist/wave-like events to brain utterances.
    wave / swipe-left → mark complete; fist → lock gestures/panic quiet;
    swipe-up → open map.
    """

    def __init__(self, run: Callable[[str], None]) -> None:
        self._run = run
        self._last = 0.0
        self.enabled = True

    def on_gesture(self, label: str = "", swipe: str = "") -> str:
        if not self.enabled:
            return ""
        now = time.time()
        if now - self._last < 1.2:
            return ""
        cmd = ""
        if swipe == "left" or label in ("wave_left", "thumbs_up"):
            cmd = "mark task complete"
        elif swipe == "right":
            cmd = "pull up the news"
        elif swipe == "up":
            cmd = "open map view"
        elif swipe == "down":
            cmd = "close map"
        elif label == "fist":
            return ""  # fist only locks camera panels — never OS lock
        elif label == "point":
            return ""  # continuous pointer — no fire
        if not cmd:
            return ""
        self._last = now
        try:
            self._run(cmd)
        except Exception:
            return ""
        return cmd

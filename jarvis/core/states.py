"""Jarvis state machine — ACTIVE / IDLE / BEDTIME."""

from __future__ import annotations

from enum import Enum
from typing import Callable


class JarvisState(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    BEDTIME = "bedtime"


class StateMachine:
    def __init__(self) -> None:
        self.state = JarvisState.ACTIVE
        self._listeners: list[Callable[[JarvisState, JarvisState], None]] = []

    def on_change(self, cb: Callable[[JarvisState, JarvisState], None]) -> None:
        self._listeners.append(cb)

    def set(self, new: JarvisState) -> None:
        if new == self.state:
            return
        old = self.state
        self.state = new
        for cb in self._listeners:
            try:
                cb(old, new)
            except Exception:
                pass

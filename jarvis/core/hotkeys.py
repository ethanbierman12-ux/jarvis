"""Hotkeys disabled — F5 only launches Jarvis via wake_agent (no START spam)."""

from __future__ import annotations

from typing import Callable


class HotkeyService:
    """Kept as a no-op stub so older imports do not break."""

    def __init__(self, on_start: Callable[[], None] | None = None) -> None:
        self.on_start = on_start
        self._ok = False

    def start(self) -> None:
        self._ok = False
        print("[hotkeys] disabled (no F5 START inside Jarvis)")

    def stop(self) -> None:
        pass

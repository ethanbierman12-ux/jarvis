"""Hotkeys stub — global F5 is wake_agent; HUD F5 is MainWindow reload shortcut."""

from __future__ import annotations

from typing import Callable


class HotkeyService:
    """Kept as a no-op stub so older imports do not break."""

    def __init__(self, on_start: Callable[[], None] | None = None) -> None:
        self.on_start = on_start
        self._ok = False

    def start(self) -> None:
        self._ok = False
        print("[hotkeys] disabled (F5 = wake launch / HUD reload, not START)")

    def stop(self) -> None:
        pass

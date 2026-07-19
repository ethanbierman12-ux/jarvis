"""Clap detector disabled — was falsely triggering START / 'Starting'."""

from __future__ import annotations

from typing import Callable


class ClapDetector:
    """No-op stub — clap START removed."""

    def __init__(self, on_clap: Callable[[], None] | None = None, cooldown: float = 2.0) -> None:
        self.on_clap = on_clap
        self.cooldown = cooldown

    def start(self) -> None:
        print("[clap] disabled")

    def stop(self) -> None:
        pass

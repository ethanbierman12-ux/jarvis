"""Bedtime / Guardian state — lock, purge media, deep-sleep UI signal."""

from __future__ import annotations

from typing import Callable

from jarvis.core.system import SystemControl


MEDIA_NAMES = ["chrome", "spotify", "vlc", "msedge", "firefox", "discord"]


class BedtimeMode:
    def __init__(self, system: SystemControl, ui: Callable[[dict], None] | None = None) -> None:
        self.system = system
        self.ui = ui
        self.active = False

    def enter(self) -> str:
        self.active = True
        if self.ui:
            self.ui({"active": True})
        # Purge noisy media
        self.system.kill_named(MEDIA_NAMES)
        # Lock workstation
        self.system.lock()
        return "Guardian state engaged. Sleep well."

    def exit(self) -> str:
        self.active = False
        if self.ui:
            self.ui({"active": False})
        return "Guardian state off. Welcome back."

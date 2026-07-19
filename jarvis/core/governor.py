"""Eco-Mode SystemGovernor — throttle vision/UI when CPU or thermal spikes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import psutil


@dataclass
class GovernorSnapshot:
    cpu: float
    memory: float
    temp_c: float | None
    battery: float | None
    disk: float
    vision_fps: int
    ui_fps: int
    eco: bool


class SystemGovernor:
    """If CPU > 80% or temp > 75°C → drop vision FPS until stable."""

    CPU_HOT = 80.0
    TEMP_HOT = 75.0
    VISION_HOT = 5
    VISION_COOL = 15
    UI_HOT = 18
    UI_COOL = 36

    def __init__(self) -> None:
        self._eco = False
        self._listeners: list[Callable[[GovernorSnapshot], None]] = []
        psutil.cpu_percent(interval=None)  # prime

    def on_change(self, cb: Callable[[GovernorSnapshot], None]) -> None:
        self._listeners.append(cb)

    def _read_temp(self) -> float | None:
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None
            vals = [e.current for entries in temps.values() for e in entries if e.current]
            return max(vals) if vals else None
        except Exception:
            return None

    def snapshot(self) -> GovernorSnapshot:
        cpu = float(psutil.cpu_percent(interval=0.05))
        mem = float(psutil.virtual_memory().percent)
        temp = self._read_temp()
        bat = None
        try:
            b = psutil.sensors_battery()
            bat = float(b.percent) if b else None
        except Exception:
            pass
        try:
            disk = float(psutil.disk_usage("C:\\").percent)
        except Exception:
            disk = 0.0

        hot = cpu >= self.CPU_HOT or (temp is not None and temp >= self.TEMP_HOT)
        # hysteresis: leave eco only when clearly cool
        if hot:
            self._eco = True
        elif cpu < self.CPU_HOT - 15 and (temp is None or temp < self.TEMP_HOT - 10):
            self._eco = False

        snap = GovernorSnapshot(
            cpu=cpu,
            memory=mem,
            temp_c=temp,
            battery=bat,
            disk=disk,
            vision_fps=self.VISION_HOT if self._eco else self.VISION_COOL,
            ui_fps=self.UI_HOT if self._eco else self.UI_COOL,
            eco=self._eco,
        )
        return snap

    def tick(self) -> GovernorSnapshot:
        snap = self.snapshot()
        for cb in self._listeners:
            try:
                cb(snap)
            except Exception:
                pass
        return snap

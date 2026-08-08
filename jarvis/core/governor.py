"""Eco-Mode SystemGovernor — throttle vision/UI when CPU, RAM, or thermal spikes."""

from __future__ import annotations

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
    """If CPU/RAM/temp hot → drop vision + UI FPS until stable."""

    CPU_HOT = 70.0
    MEM_HOT = 82.0
    TEMP_HOT = 72.0
    # Lean defaults — presence doesn't need cinematic FPS
    VISION_HOT = 2
    VISION_COOL = 3
    UI_HOT = 10
    UI_COOL = 15

    def __init__(
        self,
        *,
        max_vision_fps: int | None = None,
        performance_mode: bool = False,
    ) -> None:
        self._eco = False
        self._perf = bool(performance_mode)
        self._listeners: list[Callable[[GovernorSnapshot], None]] = []
        self._last_vision = -1
        self._last_ui = -1
        # Cap cool FPS to settings (never raise above user preference)
        cool = int(max_vision_fps) if max_vision_fps else self.VISION_COOL
        self.VISION_COOL = max(1, min(cool, self.VISION_COOL if cool <= 0 else cool))
        if self.VISION_COOL < self.VISION_HOT:
            self.VISION_HOT = max(1, self.VISION_COOL)
        if self._perf:
            self.VISION_COOL = min(self.VISION_COOL, 2)
            self.UI_COOL = 8
            self.UI_HOT = 6
        psutil.cpu_percent(interval=None)  # prime non-blocking

    def set_performance_mode(self, on: bool) -> None:
        """Smooth / eco HUD — lower UI + vision caps without waiting for thermal."""
        self._perf = bool(on)
        if self._perf:
            self.UI_COOL = 8
            self.UI_HOT = 6
            self.VISION_COOL = min(self.VISION_COOL, 2)
        else:
            self.UI_COOL = 15
            self.UI_HOT = 10
            # vision cool restored by next tick via max from constructor — keep current cap
            self.VISION_COOL = max(self.VISION_COOL, 2)

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
        # Non-blocking — never sleep the UI/telemetry thread
        cpu = float(psutil.cpu_percent(interval=None))
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

        hot = (
            cpu >= self.CPU_HOT
            or mem >= self.MEM_HOT
            or (temp is not None and temp >= self.TEMP_HOT)
            or self._perf  # smooth mode stays lean
        )
        # hysteresis: leave eco only when clearly cool (and not in smooth mode)
        if hot:
            self._eco = True
        elif self._perf:
            self._eco = True
        elif (
            cpu < self.CPU_HOT - 15
            and mem < self.MEM_HOT - 10
            and (temp is None or temp < self.TEMP_HOT - 8)
        ):
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
        changed = (
            snap.vision_fps != self._last_vision
            or snap.ui_fps != self._last_ui
            or snap.eco
        )
        self._last_vision = snap.vision_fps
        self._last_ui = snap.ui_fps
        if not changed and not snap.eco:
            # Still notify for telemetry HUD, but listeners can no-op fps sets
            pass
        for cb in self._listeners:
            try:
                cb(snap)
            except Exception:
                pass
        return snap

"""Gaze workspace — look-up / look-left dwell → multi-monitor actions.

Uses face position in the primary webcam (Haar / existing Biometrics path).
Not true iris tracking — head/face FOV proxy that works with MediaPipe hands already loaded.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


@dataclass
class GazeEvent:
    zone: str  # center | up | left | right | down | away
    dwell_sec: float
    face_present: bool


class GazeWorkspace:
    """
    Dwell rules (defaults):
      · look UP ≥ 3s  → open/focus command deck (top monitor) + detail mode
      · look LEFT ≥ 2s → nudge tools console scroll
      · look CENTER → release deck detail latch after short settle
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        up_dwell_sec: float = 3.0,
        left_dwell_sec: float = 2.0,
        on_look_up: Callable[[], None] | None = None,
        on_look_left_scroll: Callable[[], None] | None = None,
        on_look_center: Callable[[], None] | None = None,
        on_zone: Callable[[GazeEvent], None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.up_dwell_sec = max(1.0, float(up_dwell_sec))
        self.left_dwell_sec = max(0.8, float(left_dwell_sec))
        self.on_look_up = on_look_up
        self.on_look_left_scroll = on_look_left_scroll
        self.on_look_center = on_look_center
        self.on_zone = on_zone
        self._zone = "away"
        self._zone_since = time.time()
        self._fired_up = False
        self._fired_center = False
        self._last_left_scroll = 0.0
        self._last_zone_emit = 0.0
        self._last_event = GazeEvent("away", 0.0, False)

    def status(self) -> str:
        e = "ON" if self.enabled else "OFF"
        return (
            f"Gaze workspace {e} | zone {self._zone} | "
            f"up>={self.up_dwell_sec:.0f}s deck | left>={self.left_dwell_sec:.0f}s scroll"
        )

    def set_enabled(self, on: bool) -> str:
        self.enabled = bool(on)
        return self.status()

    def tick(self, snap) -> GazeEvent:
        """snap: BioSnapshot (needs face_present + optional gaze_zone)."""
        now = time.time()
        if not self.enabled:
            return self._last_event
        face = bool(getattr(snap, "face_present", False))
        zone = str(getattr(snap, "gaze_zone", "") or "")
        if not zone:
            zone = "center" if getattr(snap, "looking_at_screen", False) else "away"
        if not face:
            zone = "away"

        if zone != self._zone:
            self._zone = zone
            self._zone_since = now
            if zone != "up":
                self._fired_up = False
            if zone != "center":
                self._fired_center = False

        dwell = now - self._zone_since
        ev = GazeEvent(zone=zone, dwell_sec=dwell, face_present=face)
        zone_changed = ev.zone != self._last_event.zone
        self._last_event = ev
        if self.on_zone and (zone_changed or now - self._last_zone_emit >= 1.0):
            self._last_zone_emit = now
            try:
                self.on_zone(ev)
            except Exception:
                pass

        if zone == "up" and dwell >= self.up_dwell_sec and not self._fired_up:
            self._fired_up = True
            if self.on_look_up:
                try:
                    self.on_look_up()
                except Exception:
                    pass
        elif zone == "left" and dwell >= self.left_dwell_sec:
            if now - self._last_left_scroll >= 1.1:
                self._last_left_scroll = now
                if self.on_look_left_scroll:
                    try:
                        self.on_look_left_scroll()
                    except Exception:
                        pass
        elif zone == "center" and dwell >= 1.2 and not self._fired_center:
            self._fired_center = True
            if self.on_look_center:
                try:
                    self.on_look_center()
                except Exception:
                    pass
        return ev


def move_foreground_to_monitor(prefer: str = "top") -> str:
    """Throw the foreground window onto tools/deck/primary via Win32."""
    try:
        from jarvis.core.displays import displays

        screen = displays.resolve(prefer)
    except Exception as e:
        return f"Display resolve failed: {e}"
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "No foreground window."
        # Don't move Jarvis HUD itself if somehow focused
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = (buf.value or "").lower()
        if "jarvis" in title and "tools" not in title and "command deck" not in title:
            # Still allow moving other apps; skip if it's the main HUD title exactly
            pass
        SWP_SHOWWINDOW = 0x0040
        margin = 16
        x = screen.x + margin
        y = screen.y + margin
        w = max(800, screen.width - margin * 2)
        h = max(600, screen.height - margin * 2)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetWindowPos(hwnd, 0, x, y, w, h, SWP_SHOWWINDOW)
        return f"Moved window to {prefer} ({screen.width}x{screen.height})."
    except Exception as e:
        return f"Could not move window: {e}"

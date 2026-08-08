"""Spatial gesture workspace — pinch to monitor edges + swipe to move panels.

Desktop-only (no AR glasses). Uses normalized camera cursor 0..1.
"""

from __future__ import annotations

import time
from typing import Any, Callable


class SpatialWorkspace:
    """
    Pinch-drag past left/right screen edge → place HUD or PDTester.
    Swipe while spatial mode is on → send boards between monitors.
    """

    def __init__(
        self,
        *,
        place_hud: Callable[[str], None],
        place_ops: Callable[[str], None],
        on_note: Callable[[str], None] | None = None,
    ) -> None:
        self._place_hud = place_hud
        self._place_ops = place_ops
        self._note = on_note or (lambda _s: None)
        self.enabled = True
        self._edge_side: str | None = None
        self._edge_since = 0.0
        self._last_fire = 0.0
        self._last_swipe = 0.0
        self._pinch_active = False

    def set_enabled(self, on: bool) -> str:
        self.enabled = bool(on)
        return "Spatial gestures on." if self.enabled else "Spatial gestures off."

    def on_pinch_drag(self, nx: float, ny: float, *, pinch: bool) -> str:
        """Call on each drag sample. Fires after ~0.55s dwell in an edge band."""
        if not self.enabled:
            return ""
        self._pinch_active = bool(pinch)
        if not pinch:
            self._edge_side = None
            self._edge_since = 0.0
            return ""

        now = time.time()
        side = None
        try:
            x = float(nx)
        except Exception:
            return ""
        if x >= 0.88:
            side = "secondary"
        elif x <= 0.12:
            side = "primary"

        if side is None:
            self._edge_side = None
            self._edge_since = 0.0
            return ""

        if side != self._edge_side:
            self._edge_side = side
            self._edge_since = now
            return ""

        if now - self._edge_since < 0.55:
            return ""
        if now - self._last_fire < 1.4:
            return ""

        self._last_fire = now
        self._edge_since = now  # reset dwell
        return self._fire_edge(side)

    def on_swipe(self, direction: str) -> str:
        """Swipe sends boards between monitors (spatial mode only)."""
        if not self.enabled:
            return ""
        d = (direction or "").lower().strip()
        if d not in ("left", "right", "up", "down"):
            return ""
        now = time.time()
        if now - self._last_swipe < 1.1:
            return ""
        self._last_swipe = now

        if d == "right":
            # Throw work surface to the other monitor
            try:
                self._place_ops("secondary")
            except Exception:
                pass
            self._note("Spatial › PDTester → secondary")
            return "PDTester sent to your other monitor."

        if d == "left":
            try:
                self._place_hud("primary")
            except Exception:
                pass
            self._note("Spatial › HUD → primary")
            return "Main HUD on primary."

        if d == "up":
            # Throw foreground app to top command deck + dual board layout
            try:
                from jarvis.core.gaze_workspace import move_foreground_to_monitor

                move_foreground_to_monitor("top")
            except Exception:
                pass
            try:
                self._place_ops("secondary")
                self._place_hud("primary")
            except Exception:
                pass
            self._note("Spatial › throw-up → top deck")
            return "Thrown to the top command deck."

        if d == "down":
            # Bring everything home to primary
            try:
                self._place_ops("primary")
                self._place_hud("primary")
            except Exception:
                pass
            self._note("Spatial › all boards → primary")
            return "Boards pulled to primary."

        return ""

    def _fire_edge(self, side: str) -> str:
        if side == "secondary":
            try:
                self._place_ops("secondary")
            except Exception:
                pass
            self._note("Spatial › edge → PDTester secondary")
            return "Thrown to secondary monitor."
        try:
            self._place_hud("primary")
        except Exception:
            pass
        self._note("Spatial › edge → HUD primary")
        return "Anchored to primary monitor."

    def status(self) -> str:
        return (
            f"Spatial gestures {'on' if self.enabled else 'off'} · "
            "pinch to edges · swipe right=PDTester · left=HUD home · up=dual · down=stack."
        )

"""Night-vision HUD badge + green phosphor look helpers."""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QGraphicsOpacityEffect


def apply_night_vision(frame_bgr: np.ndarray) -> np.ndarray:
    """Convert a BGR frame to green phosphor night-vision look."""
    try:
        import cv2
    except Exception:
        return frame_bgr
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    # Lift shadows so a dark room is still readable
    gray = cv2.convertScaleAbs(gray, alpha=1.85, beta=28)
    try:
        clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    except Exception:
        pass
    # Slight grain
    noise = np.random.randint(0, 18, gray.shape, dtype=np.uint8)
    gray = cv2.add(gray, noise)
    # Classic NVG: green channel dominant
    zeros = np.zeros_like(gray)
    green = cv2.merge([zeros, gray, (gray.astype(np.uint16) * 40 // 255).astype(np.uint8)])
    # Soft vignette
    h, w = gray.shape
    yy, xx = np.ogrid[:h, :w]
    cy, cx = h / 2.0, w / 2.0
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    vignette = np.clip(1.15 - r / (0.75 * max(cx, cy)), 0.35, 1.0).astype(np.float32)
    out = green.astype(np.float32)
    out *= vignette[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


class NightVisionBadge(QFrame):
    """Corner badge that appears when night vision engages."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NightVisionBadge")
        self.setStyleSheet(
            "QFrame#NightVisionBadge {"
            " background: rgba(0, 28, 12, 210);"
            " border: 1px solid rgba(40, 255, 90, 180);"
            " border-radius: 4px;"
            "}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.title = QLabel("NIGHT VISION")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(
            "color:#39ff7a; font-family:Consolas; font-size:15px;"
            " letter-spacing:3px; font-weight:700;"
        )
        self.sub = QLabel("ONLINE")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setStyleSheet(
            "color:#9dffb8; font-family:Consolas; font-size:11px; letter-spacing:2px;"
        )
        lay.addWidget(self.title)
        lay.addWidget(self.sub)
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(0.0)
        self._anim: QPropertyAnimation | None = None
        self.hide()
        self._on = False

    def set_active(self, on: bool) -> None:
        on = bool(on)
        if on == self._on and (self.isVisible() == on):
            return
        self._on = on
        if on:
            self.show()
            self.raise_()
            self._fade(0.0, 1.0)
        else:
            self._fade(self._fx.opacity(), 0.0, hide_after=True)

    def _fade(self, start: float, end: float, hide_after: bool = False) -> None:
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(520)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if hide_after:
            anim.finished.connect(self.hide)
        anim.start()
        self._anim = anim

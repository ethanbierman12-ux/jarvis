"""Night-vision HUD badge + green phosphor look helpers."""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QGraphicsOpacityEffect

# Cached vignette masks keyed by (h, w) — avoids per-frame ogrid math
_VIGNETTE_CACHE: dict[tuple[int, int], np.ndarray] = {}
_GRAIN_TICK = 0
_FX_MAX_W = 640


def _downscale_for_fx(frame_bgr: np.ndarray, max_w: int = _FX_MAX_W) -> np.ndarray:
    try:
        import cv2
    except Exception:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    if w <= max_w:
        return frame_bgr
    scale = max_w / float(w)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    return cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_AREA)


def _vignette(h: int, w: int) -> np.ndarray:
    key = (h, w)
    hit = _VIGNETTE_CACHE.get(key)
    if hit is not None:
        return hit
    yy, xx = np.ogrid[:h, :w]
    cy, cx = h / 2.0, w / 2.0
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    vignette = np.clip(1.15 - r / (0.75 * max(cx, cy)), 0.35, 1.0).astype(np.float32)
    if len(_VIGNETTE_CACHE) > 8:
        _VIGNETTE_CACHE.clear()
    _VIGNETTE_CACHE[key] = vignette
    return vignette


def apply_night_vision(frame_bgr: np.ndarray) -> np.ndarray:
    """Convert a BGR frame to green phosphor night-vision look (cheap path)."""
    try:
        import cv2
    except Exception:
        return frame_bgr
    src = _downscale_for_fx(frame_bgr)
    gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
    gray = cv2.convertScaleAbs(gray, alpha=1.85, beta=28)
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        gray = clahe.apply(gray)
    except Exception:
        pass
    global _GRAIN_TICK
    _GRAIN_TICK = (_GRAIN_TICK + 1) % 4
    if _GRAIN_TICK == 0:
        noise = np.random.randint(0, 14, gray.shape, dtype=np.uint8)
        gray = cv2.add(gray, noise)
    zeros = np.zeros_like(gray)
    green = cv2.merge(
        [zeros, gray, (gray.astype(np.uint16) * 40 // 255).astype(np.uint8)]
    )
    h, w = gray.shape
    vignette = _vignette(h, w)
    out = green.astype(np.float32)
    out *= vignette[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_thermal_assist(frame_bgr: np.ndarray) -> np.ndarray:
    """Software false-color heatmap from luminance — assist only, not real FLIR.

    For the owner's own webcam feeds. OpenCV COLORMAP_INFERNO when available.
    """
    try:
        import cv2
    except Exception:
        return frame_bgr
    try:
        src = _downscale_for_fx(frame_bgr)
        gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
        gray = cv2.convertScaleAbs(gray, alpha=1.35, beta=12)
        try:
            clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(4, 4))
            gray = clahe.apply(gray)
        except Exception:
            pass
        cmap = getattr(cv2, "COLORMAP_INFERNO", None)
        if cmap is None:
            cmap = getattr(cv2, "COLORMAP_JET", 2)
        return cv2.applyColorMap(gray, cmap)
    except Exception:
        return frame_bgr


class NightVisionBadge(QFrame):
    """Corner badge that appears when night vision / thermal assist engages."""

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
        self._mode = "nv"

    def set_mode(self, mode: str = "nv") -> None:
        """mode: 'nv' | 'thermal' — updates badge copy without breaking callers."""
        mode = (mode or "nv").strip().lower()
        if mode in ("thermal", "heat", "thermal_assist"):
            self._mode = "thermal"
            self.title.setText("THERMAL ASSIST")
            self.sub.setText("SOFTWARE · NOT FLIR")
            self.setStyleSheet(
                "QFrame#NightVisionBadge {"
                " background: rgba(28, 8, 4, 210);"
                " border: 1px solid rgba(255, 120, 40, 180);"
                " border-radius: 4px;"
                "}"
            )
            self.title.setStyleSheet(
                "color:#ff9a4a; font-family:Consolas; font-size:15px;"
                " letter-spacing:3px; font-weight:700;"
            )
            self.sub.setStyleSheet(
                "color:#ffc9a0; font-family:Consolas; font-size:11px; letter-spacing:2px;"
            )
        else:
            self._mode = "nv"
            self.title.setText("NIGHT VISION")
            self.sub.setText("ONLINE")
            self.setStyleSheet(
                "QFrame#NightVisionBadge {"
                " background: rgba(0, 28, 12, 210);"
                " border: 1px solid rgba(40, 255, 90, 180);"
                " border-radius: 4px;"
                "}"
            )
            self.title.setStyleSheet(
                "color:#39ff7a; font-family:Consolas; font-size:15px;"
                " letter-spacing:3px; font-weight:700;"
            )
            self.sub.setStyleSheet(
                "color:#9dffb8; font-family:Consolas; font-size:11px; letter-spacing:2px;"
            )

    def set_active(self, on: bool, mode: str | None = None) -> None:
        on = bool(on)
        if mode is not None:
            self.set_mode(mode)
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

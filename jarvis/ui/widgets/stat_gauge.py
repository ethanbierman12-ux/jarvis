"""Circular system gauges — cyberpunk segmented rings (CPU / RAM / NET)."""

from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QRadialGradient, QBrush
from PyQt6.QtWidgets import QWidget


class StatGauge(QWidget):
    """Segmented circular % gauge matching dense HUD mockups."""

    def __init__(
        self,
        label: str = "CPU",
        *,
        accent: str = "#00e5ff",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(92, 92)
        self._label = (label or "CPU").upper()
        self._value = 0.0
        self._accent = QColor(accent)
        if not self._accent.isValid():
            self._accent = QColor(0, 229, 255)

    def set_value(self, pct: float) -> None:
        self._value = max(0.0, min(100.0, float(pct)))
        self.update()

    def set_accent(self, hex_color: str) -> None:
        c = QColor(hex_color)
        if c.isValid():
            self._accent = c
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 6
        a = self._accent

        # Soft bloom
        bloom = QRadialGradient(cx, cy, r * 1.4)
        bloom.setColorAt(0.0, QColor(a.red(), a.green(), a.blue(), 35))
        bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bloom))
        p.drawEllipse(QPointF(cx, cy), r * 1.15, r * 1.15)

        # Track ring
        track = QPen(QColor(a.red(), a.green(), a.blue(), 40), 7)
        track.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(track)
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.drawArc(rect, 0, 360 * 16)

        # Segmented progress (gap every few degrees)
        span = int(self._value / 100.0 * 360)
        # Start at 12 o'clock, clockwise
        start = 90 * 16
        seg = 12  # degrees per segment
        gap = 3
        drawn = 0
        while drawn < span:
            chunk = min(seg, span - drawn)
            pen = QPen(QColor(a.red(), a.green(), a.blue(), 230), 7)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            # Qt arcs: positive = counter-clockwise from 3 o'clock; we want clockwise from 12
            p.drawArc(rect, start - drawn * 16, -chunk * 16)
            drawn += chunk + gap

        # Inner tick ring
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 55), 1))
        p.drawEllipse(QPointF(cx, cy), r - 12, r - 12)

        # Value
        p.setPen(QColor(232, 244, 255))
        p.setFont(QFont("Bahnschrift", 14, QFont.Weight.Bold))
        txt = f"{int(self._value)}"
        tw = p.fontMetrics().horizontalAdvance(txt)
        p.drawText(int(cx - tw / 2), int(cy + 2), txt)

        # Label
        p.setPen(QColor(a.red(), a.green(), a.blue(), 200))
        p.setFont(QFont("Cascadia Mono", 8))
        lw = p.fontMetrics().horizontalAdvance(self._label)
        p.drawText(int(cx - lw / 2), int(cy + 18), self._label)

        # Unit tick
        p.setPen(QColor(120, 160, 180, 160))
        p.setFont(QFont("Cascadia Mono", 7))
        u = "%"
        uw = p.fontMetrics().horizontalAdvance(u)
        p.drawText(int(cx - uw / 2 + 18), int(cy - 6), u)
        p.end()

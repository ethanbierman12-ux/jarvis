"""Subtle rain streak overlay for rainy weather mood."""

from __future__ import annotations

import random

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import QWidget


class WeatherAtmosphere(QWidget):
    """Full-window translucent weather FX (rain streaks / storm flashes)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._mood = "clear"
        self._drops: list[list[float]] = []
        self._flash = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def set_mood(self, mood: str) -> None:
        mood = (mood or "clear").lower()
        if mood == self._mood:
            return
        self._mood = mood
        if mood in ("rain", "storm"):
            self._spawn_drops(80 if mood == "rain" else 120)
            self.show()
            self.raise_()
            if not self._timer.isActive():
                self._timer.start(33)
        else:
            self._timer.stop()
            self._drops.clear()
            self.hide()
        self.update()

    def _spawn_drops(self, n: int) -> None:
        w = max(100, self.width())
        h = max(100, self.height())
        self._drops = [
            [
                random.uniform(0, w),
                random.uniform(-h, h),
                random.uniform(10, 22),
                random.uniform(4, 9),
            ]
            for _ in range(n)
        ]

    def _tick(self) -> None:
        h = max(1, self.height())
        w = max(1, self.width())
        for d in self._drops:
            d[1] += d[3]
            if d[1] > h + 20:
                d[0] = random.uniform(0, w)
                d[1] = random.uniform(-80, -10)
        if self._mood == "storm" and random.random() < 0.02:
            self._flash = 1.0
        self._flash = max(0.0, self._flash - 0.08)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._mood in ("rain", "storm") and self._drops:
            self._spawn_drops(len(self._drops))

    def paintEvent(self, event) -> None:
        if self._mood not in ("rain", "storm"):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._flash > 0:
            p.fillRect(self.rect(), QColor(180, 200, 255, int(40 * self._flash)))
        # Cool blue wash
        wash = QColor(20, 60, 110, 35 if self._mood == "rain" else 50)
        p.fillRect(self.rect(), wash)
        pen = QPen(QColor(160, 210, 255, 90 if self._mood == "rain" else 120))
        pen.setWidth(1)
        p.setPen(pen)
        for x, y, length, _spd in self._drops:
            p.drawLine(int(x), int(y), int(x - 2), int(y + length))
        p.end()

"""Voice waveform HUD — dense dual-tone canvas (cyan + amber), pauses when quiet."""

from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QLinearGradient, QBrush
from PyQt6.QtWidgets import QWidget


class VoiceWaveform(QWidget):
    """Animated multi-trace waveform + bar field for speak/listen feedback."""

    _ACTIVE_MS = 40
    _IDLE_MS = 140

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(64)
        self.setMinimumHeight(48)
        self._amp = 0.0
        self._speaking = False
        self._levels = [0.08] * 40
        self._trace_a = [0.0] * 80
        self._trace_b = [0.0] * 80
        self._phase = 0
        self._eco = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._IDLE_MS)

    def set_amplitude(self, amp: float) -> None:
        self._amp = max(0.0, min(1.0, float(amp)))
        if self._amp > 0.06 and self._timer.interval() > self._ACTIVE_MS:
            self._timer.setInterval(self._ACTIVE_MS if not self._eco else 80)

    def set_speaking(self, on: bool) -> None:
        """While Jarvis speaks, keep the wave lively even if mic is muted."""
        self._speaking = bool(on)
        if self._speaking:
            self._timer.setInterval(self._ACTIVE_MS if not self._eco else 80)

    def set_eco(self, on: bool) -> None:
        self._eco = bool(on)
        if self._eco:
            self._timer.setInterval(max(self._IDLE_MS, 100))
        elif self._amp > 0.06 or self._speaking:
            self._timer.setInterval(self._ACTIVE_MS)

    def _tick(self) -> None:
        self._phase = (self._phase + 1) % 10000
        base = 0.10 + self._amp * 0.85
        if self._speaking and self._amp < 0.2:
            base = 0.35 + 0.25 * abs(math.sin(self._phase * 0.12))
        quiet = True

        for i in range(len(self._levels)):
            wiggle = 0.5 + 0.5 * math.sin((self._phase + i * 5) * 0.22)
            goal = base * (0.4 + 0.6 * wiggle)
            self._levels[i] += (goal - self._levels[i]) * 0.38
            if self._levels[i] > 0.12:
                quiet = False

        # Scroll traces
        self._trace_a = self._trace_a[1:] + [
            base * (0.55 + 0.45 * math.sin(self._phase * 0.31))
        ]
        self._trace_b = self._trace_b[1:] + [
            base * (0.4 + 0.6 * math.sin(self._phase * 0.19 + 1.7))
        ]

        if quiet and self._amp < 0.04 and not self._speaking:
            want = self._IDLE_MS if not self._eco else 160
            if self._timer.interval() != want:
                self._timer.setInterval(want)
            # Keep decaying paint until bars settle — early return froze the last peak
            if max(self._levels) < 0.10 and max(self._trace_a + self._trace_b) < 0.12:
                if getattr(self, "_idle_painted", False):
                    return
                self._idle_painted = True
            else:
                self._idle_painted = False
        else:
            self._idle_painted = False
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Panel fill with top/bottom bracket lines
        p.fillRect(0, 0, w, h, QColor(2, 10, 18, 160))
        p.setPen(QPen(QColor(0, 229, 255, 70), 1))
        p.drawLine(8, 1, w - 8, 1)
        p.drawLine(8, h - 2, w - 8, h - 2)
        # Corner ticks
        for x0, y0, dx, dy in (
            (4, 4, 10, 0),
            (4, 4, 0, 8),
            (w - 14, 4, 10, 0),
            (w - 4, 4, 0, 8),
            (4, h - 4, 10, 0),
            (4, h - 12, 0, 8),
            (w - 14, h - 4, 10, 0),
            (w - 4, h - 12, 0, 8),
        ):
            p.drawLine(x0, y0, x0 + dx, y0 + dy)

        mid = h / 2
        # Dual traces — cyan + teal when speaking (secure boot)
        cyan = QColor(0, 240, 255, 210 if self._speaking else 180)
        teal = QColor(0, 180, 210, 190 if self._speaking else 140)
        self._draw_trace(p, self._trace_a, cyan, mid, h * 0.34)
        self._draw_trace(p, self._trace_b, teal, mid, h * 0.24)

        # Concentric mini-rings on the left (voice core echo)
        if self._speaking or self._amp > 0.08:
            rx, ry = 22, mid
            for i, sc in enumerate((6, 11, 16)):
                r = sc * (1.0 + 0.35 * self._amp + (0.2 if self._speaking else 0))
                col = QColor(0, 240, 255, 120 - i * 25)
                if i == 1:
                    col = QColor(0, 180, 210, 100)
                p.setPen(QPen(col, 1.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(rx, ry), r, r)

        # Bar field along the bottom third
        n = len(self._levels)
        gap = 2
        bar_w = max(2, (w - gap * (n + 1)) // n)
        x = gap
        base_y = h - 6
        for lvl in self._levels:
            bh = max(1, int((h * 0.42) * lvl))
            color = QColor(0, 240, 255, 180)
            if self._speaking and lvl > 0.4:
                color = QColor(0, 210, 230, 200)
            if lvl > 0.65:
                color = QColor(61, 255, 154, 210)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRect(x, base_y - bh, bar_w, bh)
            x += bar_w + gap

        # Label
        p.setPen(QColor(0, 229, 255, 140))
        p.setFont(p.font())
        from PyQt6.QtGui import QFont

        p.setFont(QFont("Cascadia Mono", 8))
        tag = "AUDIO · LIVE" if (self._amp > 0.08 or self._speaking) else "AUDIO · STANDBY"
        p.drawText(10, 14, tag)
        p.end()

    def _draw_trace(self, p: QPainter, data: list[float], color: QColor, mid: float, amp_h: float) -> None:
        if len(data) < 2:
            return
        pen = QPen(color, 1.4)
        pen.setCosmetic(True)
        p.setPen(pen)
        w = self.width()
        step = w / max(1, len(data) - 1)
        prev = QPointF(0, mid - data[0] * amp_h)
        for i, v in enumerate(data[1:], 1):
            pt = QPointF(i * step, mid - v * amp_h)
            p.drawLine(prev, pt)
            prev = pt

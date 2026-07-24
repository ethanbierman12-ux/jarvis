"""Voice waveform HUD — neon bars driven by mic amplitude (UI thread only)."""



from __future__ import annotations



import math



from PyQt6.QtCore import Qt, QTimer

from PyQt6.QtGui import QPainter, QColor, QPen

from PyQt6.QtWidgets import QWidget





class VoiceWaveform(QWidget):

    """Simple translucent audio bars for speak/listen feedback."""



    _ACTIVE_MS = 50  # ~20 FPS while speaking / hot mic

    _IDLE_MS = 120  # chill when quiet — was always 33ms



    def __init__(self, parent=None) -> None:

        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.setFixedHeight(36)

        self._amp = 0.0

        self._levels = [0.08] * 24

        self._phase = 0

        self._eco = False

        self._timer = QTimer(self)

        self._timer.timeout.connect(self._tick)

        self._timer.start(self._IDLE_MS)



    def set_amplitude(self, amp: float) -> None:

        self._amp = max(0.0, min(1.0, float(amp)))

        # Snap to active rate when voice energy arrives

        if self._amp > 0.06 and self._timer.interval() > self._ACTIVE_MS:

            self._timer.setInterval(self._ACTIVE_MS if not self._eco else 80)



    def set_eco(self, on: bool) -> None:

        self._eco = bool(on)

        if self._eco:

            self._timer.setInterval(max(self._IDLE_MS, 100))

        elif self._amp > 0.06:

            self._timer.setInterval(self._ACTIVE_MS)



    def _tick(self) -> None:

        self._phase = (self._phase + 1) % 1000

        target = 0.12 + self._amp * 0.88

        quiet = True

        for i in range(len(self._levels)):

            wiggle = 0.5 + 0.5 * math.sin((self._phase + i * 7) * 0.18)

            goal = target * (0.45 + 0.55 * wiggle)

            self._levels[i] += (goal - self._levels[i]) * 0.35

            if self._levels[i] > 0.14:

                quiet = False

        # Drop back to idle cadence when settled

        if quiet and self._amp < 0.04:

            want = self._IDLE_MS if not self._eco else 150

            if self._timer.interval() != want:

                self._timer.setInterval(want)

            # Skip paint when fully flat — saves compositor work

            if max(self._levels) < 0.10:

                return

        self.update()



    def paintEvent(self, _event) -> None:

        p = QPainter(self)

        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(2, 8, 14, 120))

        n = len(self._levels)

        gap = 3

        bar_w = max(2, (w - gap * (n + 1)) // n)

        x = gap

        for lvl in self._levels:

            bh = max(2, int((h - 8) * lvl))

            y = (h - bh) // 2

            color = QColor(0, 232, 255, 200)

            if lvl > 0.7:

                color = QColor(0, 255, 160, 220)

            p.setPen(Qt.PenStyle.NoPen)

            p.setBrush(color)

            p.drawRoundedRect(x, y, bar_w, bh, 1, 1)

            p.setPen(QPen(QColor(0, 232, 255, 60), 1))

            p.setBrush(Qt.BrushStyle.NoBrush)

            p.drawRoundedRect(x, y, bar_w, bh, 1, 1)

            x += bar_w + gap

        p.end()



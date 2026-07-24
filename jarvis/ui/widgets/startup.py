"""Boot HUD — cinematic loading with smooth % climb, SFX, and Loading TTS."""

from __future__ import annotations

import math
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, QLinearGradient
from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect

from jarvis.ui.boot_sound import play_boot_sound, stop_boot_sound, speak_boot_line


class StartupOverlay(QWidget):
    finished = pyqtSignal()
    # Spoken cue when loading begins (UI log / optional external hook)
    loading_announced = pyqtSignal()

    # Tunables — cinematic + smooth, still snappy on F5
    BOOT_SEC = 2.8
    FADE_MS = 520
    TICK_MS = 16

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background:#000;")
        self._ms = 0
        self._t = 0.0
        self._done = False
        self._typed = ""
        self._target = "LOADING SYSTEMS"
        self._phase_online = False
        self._dots = ""
        self._pct = 0
        self._line = 0.0
        self._scan = 0.0
        self._log: list[str] = []
        self._connected = ""
        self._cursor = True
        self._said_loading = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(1.0)
        self._fade = None

    def start(self) -> None:
        self._ms = 0
        self._t = 0.0
        self._done = False
        self._typed = ""
        self._target = "LOADING SYSTEMS"
        self._phase_online = False
        self._dots = ""
        self._pct = 0
        self._line = 0.0
        self._scan = 0.0
        self._log = []
        self._said_loading = False
        self._connected = datetime.now().strftime("%H:%M:%S")
        self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(self.TICK_MS)
        play_boot_sound()
        # Speak "Loading" almost immediately
        QTimer.singleShot(180, self._announce_loading)

    def _announce_loading(self) -> None:
        if self._said_loading:
            return
        self._said_loading = True
        speak_boot_line("Loading")
        try:
            self.loading_announced.emit()
        except Exception:
            pass

    def _tick(self) -> None:
        self._ms += self.TICK_MS
        sec = self._ms / 1000.0
        self._t += 0.055
        self._cursor = (int(self._t * 5) % 2) == 0
        self._scan = (self._scan + 3.8) % max(1, self.height())
        self._line = min(1.0, sec / 0.55)

        raw = min(1.0, sec / self.BOOT_SEC)
        # Smoothstep + slight top linger (feels more mechanical)
        s = raw * raw * (3.0 - 2.0 * raw)
        eased = s * 0.92 + (s * s) * 0.08
        self._pct = int(min(100.0, eased * 100.0))

        # Switch to ONLINE near the end
        if self._pct >= 92 and not self._phase_online:
            self._phase_online = True
            self._target = "J.A.R.V.I.S ONLINE"
            self._typed = ""

        if sec >= 0.28:
            n = int((sec - 0.28) * 26)
            self._typed = self._target[: min(len(self._target), max(0, n))]
            if len(self._typed) >= len(self._target):
                self._dots = "." * (1 + int((sec * 3.5) % 4))
            else:
                self._dots = ""
        else:
            self._typed = ""
            self._dots = ""

        if sec >= 0.12 and not self._log:
            self._log = ["INITIATING"]
        if sec >= 0.45 and len(self._log) < 2:
            self._log = ["INITIATING", f"LINKED {self._connected}"]
        if sec >= 0.75:
            pct_line = f"{self._pct:02d}%" if self._pct < 100 else "100%"
            self._log = [
                "INITIATING",
                f"LINKED {self._connected}",
                "CORE · NOMINAL",
                pct_line,
            ]

        if self._pct >= 100 and sec >= self.BOOT_SEC + 0.2 and not self._done:
            self._done = True
            self._fade_out()
        self.update()

    def _fade_out(self) -> None:
        self._timer.stop()
        stop_boot_sound()
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(self.FADE_MS)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.finished.connect(self._complete)
        anim.start()
        self._fade = anim

    def _complete(self) -> None:
        self.hide()
        self.finished.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        ease = 1.0 - (1.0 - self._line) ** 3
        breath = 1.0 + 0.028 * math.sin(self._t)

        p.fillRect(self.rect(), QColor(0, 0, 0))

        # Subtle vignette for depth
        vig = QRadialGradient(cx, cy, min(w, h) * 0.72)
        vig.setColorAt(0.0, QColor(4, 10, 16, 255))
        vig.setColorAt(0.55, QColor(0, 0, 0, 255))
        vig.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(vig))
        p.drawRect(self.rect())

        bloom = QRadialGradient(cx, cy, min(w, h) * 0.42 * breath)
        bloom.setColorAt(0.0, QColor(0, 70, 100, 70))
        bloom.setColorAt(0.4, QColor(0, 30, 50, 28))
        bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(bloom))
        p.drawRect(self.rect())

        g = QLinearGradient(0, self._scan - 12, 0, self._scan + 12)
        g.setColorAt(0, QColor(0, 240, 255, 0))
        g.setColorAt(0.5, QColor(0, 240, 255, 22))
        g.setColorAt(1, QColor(0, 240, 255, 0))
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(0, self._scan - 12, w, 24))

        self._frames(p, cx, cy, ease * breath)

        if ease > 0.18:
            alpha = int(255 * min(1.0, (ease - 0.18) / 0.45))
            font = QFont("Bahnschrift", max(17, int(min(w, h) * 0.034)))
            font.setBold(True)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6)
            p.setFont(font)
            display = self._typed + self._dots + ("▌" if self._cursor else "")
            full_w = p.fontMetrics().horizontalAdvance(self._target + ".... ")
            x = int(cx - full_w / 2)
            y = int(cy + p.fontMetrics().ascent() / 2 - 2)

            for dx in (-2, 2, 0):
                p.setPen(QColor(0, 240, 255, alpha // 3 if dx else 0))
                if dx:
                    p.drawText(x + dx, y, display)
            p.setPen(QColor(236, 248, 255, alpha))
            p.drawText(x, y, display)

            rail = full_w * 0.98
            rx, ry = cx - rail / 2, cy + 42
            p.setPen(QPen(QColor(0, 240, 255, 35), 1))
            p.drawLine(QPointF(rx, ry), QPointF(rx + rail, ry))
            # Soft progress glow
            p.setPen(QPen(QColor(0, 240, 255, 90), 4))
            p.drawLine(QPointF(rx, ry), QPointF(rx + rail * (self._pct / 100.0), ry))
            p.setPen(QPen(QColor(0, 240, 255, 230), 2))
            p.drawLine(QPointF(rx, ry), QPointF(rx + rail * (self._pct / 100.0), ry))

            p.setPen(QColor(0, 230, 255, 170))
            p.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
            pct = f"{self._pct}%"
            pw = p.fontMetrics().horizontalAdvance(pct)
            p.drawText(int(cx - pw / 2), int(cy + 64), pct)

        if ease > 0.12:
            p.setFont(QFont("Consolas", 10))
            lx = 36
            ly = int(cy - 28)
            for i, line in enumerate(self._log):
                if i == 0:
                    p.setPen(QColor(100, 130, 150, int(170 * ease)))
                elif i == 1:
                    p.setPen(QColor(230, 245, 255, int(220 * ease)))
                else:
                    p.setPen(QColor(0, 220, 255, int(150 * ease)))
                p.drawText(lx, ly + i * 16, line)

        tick = QColor(0, 240, 255, int(130 * ease))
        p.setPen(QPen(tick, 1))
        for ox, oy in ((18, 18), (w - 18, 18), (18, h - 18), (w - 18, h - 18)):
            p.drawLine(ox - 10, oy, ox + 10, oy)
            p.drawLine(ox, oy - 10, ox, oy + 10)
        p.end()

    def _frames(self, p: QPainter, cx: float, cy: float, ease: float) -> None:
        span = min(self.width() * 0.5, 620) * ease
        half = span / 2
        y_top, y_bot = cy - 56, cy + 56
        step, inset = 16, 44
        cyan = QColor(0, 240, 255, int(210 * ease))
        glow = QColor(0, 200, 255, int(55 * ease))

        def rail(y: float, invert: bool) -> None:
            sign = -1 if invert else 1
            left, right = cx - half, cx + half
            gap = 10
            pts_l = [
                QPointF(left, y),
                QPointF(cx - inset - gap, y),
                QPointF(cx - inset + 8, y + sign * step),
                QPointF(cx - gap, y + sign * step),
            ]
            pts_r = [
                QPointF(cx + gap, y + sign * step),
                QPointF(cx + inset - 8, y + sign * step),
                QPointF(cx + inset + gap, y),
                QPointF(right, y),
            ]
            for pen in (QPen(glow, 4), QPen(cyan, 1.7)):
                p.setPen(pen)
                for pts in (pts_l, pts_r):
                    for i in range(len(pts) - 1):
                        p.drawLine(pts[i], pts[i + 1])
            p.setPen(QPen(cyan, 1.5))
            p.drawLine(QPointF(left, y - 8), QPointF(left, y + 8))
            p.drawLine(QPointF(right, y - 8), QPointF(right, y + 8))

        rail(y_top, False)
        rail(y_bot, True)

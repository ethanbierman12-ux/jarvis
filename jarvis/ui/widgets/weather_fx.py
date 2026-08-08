"""Arwes-style HUD atmosphere — hologram film FX over the PyQt HUD.

Stark projection layer: CRT scanlines, vignette, chromatic aberration,
volumetric cyan bloom, dust, mouse parallax, and short digital glitch tears.
"""

from __future__ import annotations

import math
import random
import time

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QLinearGradient, QRadialGradient, QCursor
from PyQt6.QtWidgets import QWidget


class WeatherAtmosphere(QWidget):
    """Full-window translucent HUD chrome — glass lab / hologram film feel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._mood = "clear"
        self._drops: list[list[float]] = []
        self._dust: list[list[float]] = []
        self._flash = 0.0
        self._scan_y = 0.0
        self._pulse = 0.0
        self._parallax = (0.0, 0.0)
        self._cpu = 0.0
        self._glitch_until = 0.0
        self._glitch_bands: list[tuple[int, int, int]] = []
        self._spawn_dust(36)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(90)  # ~11 FPS — grid + scan, lighter on CPU
        self.show()

    def set_mood(self, mood: str) -> None:
        mood = (mood or "clear").lower()
        if mood == self._mood:
            return
        self._mood = mood
        parent = self.parentWidget()
        cam = getattr(parent, "camera", None) if parent is not None else None
        if cam is not None and cam.isVisible():
            self.hide()
            return
        if mood in ("rain", "storm"):
            self._spawn_drops(48 if mood == "rain" else 72)
        else:
            self._drops.clear()
        self.show()
        # Raise film above HUD body only — MainWindow._stack_overlays()
        # puts HITL / artifact / theaters above this layer.
        self.raise_()
        if not self._timer.isActive():
            self._timer.start(90)
        self.update()

    def set_cpu_load(self, pct: float) -> None:
        """Drive film intensity from live CPU — spikes can auto-trigger glitch."""
        prev = self._cpu
        self._cpu = max(0.0, min(100.0, float(pct)))
        # Rising edge past ~82% → brief holographic tear
        if prev < 82.0 and self._cpu >= 82.0:
            self.trigger_glitch(0.15)
        elif self._cpu >= 92.0 and random.random() < 0.08:
            self.trigger_glitch(0.12)

    def trigger_glitch(self, seconds: float = 0.15) -> None:
        """0.15s horizontal tear + RGB split (compile fail / CPU spike)."""
        now = time.monotonic()
        self._glitch_until = max(self._glitch_until, now + max(0.05, float(seconds)))
        h = max(100, self.height())
        self._glitch_bands = []
        for _ in range(random.randint(3, 6)):
            y = random.randint(0, max(1, h - 12))
            thick = random.randint(2, 10)
            shift = random.randint(-18, 18)
            self._glitch_bands.append((y, thick, shift))
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

    def _spawn_dust(self, n: int) -> None:
        w = max(100, self.width() or 800)
        h = max(100, self.height() or 600)
        self._dust = [
            [
                random.uniform(0, w),
                random.uniform(0, h),
                random.uniform(0.6, 1.8),
                random.uniform(0.15, 0.55),
            ]
            for _ in range(n)
        ]

    def _tick(self) -> None:
        h = max(1, self.height())
        w = max(1, self.width())
        self._scan_y = (self._scan_y + 2.5 + self._cpu * 0.04) % (h + 40)
        # ~4.5s ambient breath
        self._pulse = (self._pulse + 0.125) % 6.28318

        # Soft mouse parallax (opposite of cursor)
        try:
            gp = QCursor.pos()
            local = self.mapFromGlobal(gp)
            nx = (local.x() / max(1, w)) * 2 - 1
            ny = (local.y() / max(1, h)) * 2 - 1
            tx, ty = -nx * 10.0, -ny * 7.0
            px, py = self._parallax
            self._parallax = (px + (tx - px) * 0.08, py + (ty - py) * 0.08)
        except Exception:
            pass

        for d in self._drops:
            d[1] += d[3]
            if d[1] > h + 20:
                d[0] = random.uniform(0, w)
                d[1] = random.uniform(-80, -10)

        ox, oy = self._parallax
        for pt in self._dust:
            pt[1] -= pt[3]
            pt[0] += math.sin(self._pulse + pt[0] * 0.01) * 0.15
            pt[0] += ox * 0.002
            pt[1] += oy * 0.002
            if pt[1] < -4:
                pt[0] = random.uniform(0, w)
                pt[1] = h + 4

        if self._mood == "storm" and random.random() < 0.02:
            self._flash = 1.0
        self._flash = max(0.0, self._flash - 0.08)

        # Calm clear sky: paint every other tick — glow still breathes, less lag
        calm = self._mood in ("clear", "cloudy", "clouds", "") and self._cpu < 55 and self._flash < 0.05
        if calm:
            self._idle_skip = getattr(self, "_idle_skip", 0) + 1
            if self._idle_skip % 2:
                return
        else:
            self._idle_skip = 0
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._mood in ("rain", "storm") and self._drops:
            self._spawn_drops(len(self._drops))
        if len(self._dust) < 20:
            self._spawn_dust(36)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            p.end()
            return

        ox, oy = self._parallax
        cpu_n = self._cpu / 100.0
        glitching = time.monotonic() < self._glitch_until

        # Radial vignette — darken edges, keep center clear
        vig = QRadialGradient(w * 0.5 + ox * 0.3, h * 0.48 + oy * 0.3, max(w, h) * 0.72)
        vig.setColorAt(0.0, QColor(0, 0, 0, 0))
        vig.setColorAt(0.55, QColor(0, 0, 0, 0))
        vig.setColorAt(0.82, QColor(2, 8, 19, 55))
        vig.setColorAt(1.0, QColor(2, 8, 19, 120))
        p.fillRect(self.rect(), vig)

        # Volumetric bloom — cyan light bleeding into dark corners
        bloom_a = 18 + int(22 * cpu_n) + int(10 * (0.5 + 0.5 * math.sin(self._pulse)))
        for cx, cy, rad in (
            (w * 0.12, h * 0.18, max(w, h) * 0.28),
            (w * 0.88, h * 0.22, max(w, h) * 0.24),
            (w * 0.5, h * 0.92, max(w, h) * 0.32),
        ):
            bloom = QRadialGradient(cx + ox * 0.4, cy + oy * 0.3, rad)
            bloom.setColorAt(0.0, QColor(0, 229, 255, bloom_a))
            bloom.setColorAt(0.45, QColor(0, 180, 210, bloom_a // 3))
            bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), bloom)

        # Chromatic aberration — RGB channel split at outer edges
        edge_w = max(18, int(w * 0.045))
        shift = 2 + int(3 * cpu_n) + (6 if glitching else 0)
        # Left edge: red bias shifted out
        left = QLinearGradient(0, 0, edge_w, 0)
        left.setColorAt(0.0, QColor(255, 40, 48, 28 + int(20 * cpu_n)))
        left.setColorAt(1.0, QColor(255, 40, 48, 0))
        p.fillRect(0, 0, edge_w + shift, h, left)
        # Right edge: cyan/blue bias
        right = QLinearGradient(w, 0, w - edge_w, 0)
        right.setColorAt(0.0, QColor(0, 229, 255, 32 + int(18 * cpu_n)))
        right.setColorAt(1.0, QColor(0, 229, 255, 0))
        p.fillRect(w - edge_w - shift, 0, edge_w + shift, h, right)
        # Thin green mid-edge fringe
        p.fillRect(shift, 0, 2, h, QColor(40, 255, 120, 14))
        p.fillRect(w - shift - 2, 0, 2, h, QColor(40, 255, 120, 14))

        # Top/bottom cyan wash (lab glass)
        edge = QLinearGradient(0, 0, 0, h)
        edge.setColorAt(0, QColor(0, 229, 255, 16))
        edge.setColorAt(0.12, QColor(0, 0, 0, 0))
        edge.setColorAt(0.88, QColor(0, 0, 0, 0))
        edge.setColorAt(1, QColor(0, 180, 210, 14))
        p.fillRect(self.rect(), edge)

        # CRT scanlines (faint holographic monitor)
        scan_a = 10 + int(4 * (0.5 + 0.5 * math.sin(self._pulse))) + int(6 * cpu_n)
        p.setPen(QPen(QColor(0, 229, 255, scan_a), 1))
        for y in range(0, h, 3):
            p.drawLine(0, y, w, y)

        # Futuristic grid (parallax-shifted)
        grid = QPen(QColor(0, 229, 255, 16 + int(10 * cpu_n)))
        grid.setWidth(1)
        p.setPen(grid)
        step = 48
        gx = int(ox * 0.35) % step
        gy = int(oy * 0.35) % step
        for x in range(-step + gx, w + step, step):
            p.drawLine(x, 0, x, h)
        for y in range(-step + gy, h + step, step):
            p.drawLine(0, y, w, y)

        major = QPen(QColor(0, 229, 255, 28))
        major.setWidth(1)
        p.setPen(major)
        for x in range(-step * 4 + gx, w + step * 4, step * 4):
            p.drawLine(x, 0, x, h)
        for y in range(-step * 4 + gy, h + step * 4, step * 4):
            p.drawLine(0, y, w, y)

        # Horizontal scanline sweep
        sy = int(self._scan_y)
        scan = QLinearGradient(0, sy - 12, 0, sy + 12)
        scan.setColorAt(0, QColor(0, 229, 255, 0))
        scan.setColorAt(0.5, QColor(0, 229, 255, 38 + int(20 * cpu_n)))
        scan.setColorAt(1, QColor(0, 180, 210, 0))
        p.fillRect(0, sy - 12, w, 24, scan)

        # Ambient dust / particle field
        for dx, dy, sz, _spd in self._dust:
            a = 40 + int(50 * (0.5 + 0.5 * math.sin(self._pulse + dx)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 229, 255, a))
            p.drawEllipse(QPoint(int(dx), int(dy)), int(sz), int(sz))

        # Digital glitch — horizontal tears + RGB split bands
        if glitching:
            for y, thick, shift in self._glitch_bands:
                p.fillRect(0, y, w, thick, QColor(0, 8, 19, 90))
                p.fillRect(shift, y, w, max(1, thick // 2), QColor(255, 40, 48, 55))
                p.fillRect(-shift, y + 1, w, max(1, thick // 2), QColor(0, 229, 255, 55))
                p.fillRect(shift // 2, y + thick // 3, w, 1, QColor(40, 255, 120, 80))
            # Full-frame chromatic flash
            p.fillRect(0, 0, w, h, QColor(255, 40, 48, 12))
            p.fillRect(3, 0, w, h, QColor(0, 229, 255, 10))

        # Corner brackets + micro crop marks
        pulse_a = 95 + int(45 * (0.5 + 0.5 * math.sin(self._pulse)))
        bracket = QPen(QColor(0, 229, 255, pulse_a), 2)
        p.setPen(bracket)
        arm = 28
        p.drawLine(8, 8, 8 + arm, 8)
        p.drawLine(8, 8, 8, 8 + arm)
        p.drawLine(w - 8, 8, w - 8 - arm, 8)
        p.drawLine(w - 8, 8, w - 8, 8 + arm)
        p.drawLine(8, h - 8, 8 + arm, h - 8)
        p.drawLine(8, h - 8, 8, h - 8 - arm)
        p.setPen(QPen(QColor(0, 180, 210, pulse_a), 2))
        p.drawLine(w - 8, h - 8, w - 8 - arm, h - 8)
        p.drawLine(w - 8, h - 8, w - 8, h - 8 - arm)

        # Micro serial / tracking marks
        p.setPen(QColor(112, 128, 144, 110))
        p.drawText(14, 22, "JS-9082 · HOLO-FRAME")
        p.drawText(w - 150, 22, f"CPU {self._cpu:.0f}% · FILM")
        p.drawText(14, h - 12, "VOID · #020813 · ABERRATION ON")

        if self._mood in ("rain", "storm"):
            if self._flash > 0:
                p.fillRect(self.rect(), QColor(180, 200, 255, int(40 * self._flash)))
            wash = QColor(20, 60, 110, 35 if self._mood == "rain" else 50)
            p.fillRect(self.rect(), wash)
            pen = QPen(QColor(160, 210, 255, 90 if self._mood == "rain" else 120))
            pen.setWidth(1)
            p.setPen(pen)
            for x, y, length, _spd in self._drops:
                p.drawLine(int(x), int(y), int(x - 2), int(y + length))

        p.end()

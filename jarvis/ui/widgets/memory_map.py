"""Living RAM memory map — organic block fabric + carve packets while building."""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QRadialGradient, QBrush
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QLabel


class MemoryMap(QFrame):
    """
    Sentient stack visualizer: block grid mirrors RAM pressure.
    While vibe/build is active, glowing packets "carve" along neural paths.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setMinimumHeight(148)
        self.setMaximumHeight(180)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        title = QLabel("MEMORY MAP · NEURAL FABRIC")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        self._canvas = _MemoryCanvas()
        lay.addWidget(self._canvas, 1)
        self._meta = QLabel("JS-RAM · STANDING BY")
        self._meta.setObjectName("MicroLabel")
        self._meta.setStyleSheet("color:#708090; font-size:9px; letter-spacing:2px;")
        lay.addWidget(self._meta)

    def set_ram(self, percent: float, *, used_gb: float = 0.0, total_gb: float = 0.0) -> None:
        self._canvas.set_pressure(percent)
        if total_gb > 0:
            self._meta.setText(
                f"JS-RAM · {used_gb:.1f}/{total_gb:.1f} GB · {percent:.0f}%"
            )
        else:
            self._meta.setText(f"JS-RAM · PRESSURE {percent:.0f}%")

    def set_carving(self, on: bool, *, label: str = "") -> None:
        self._canvas.set_carving(bool(on))
        if on:
            self._meta.setText(
                f"JS-RAM · CARVING · {(label or 'ALLOC').upper()[:28]}"
            )


class _MemoryCanvas(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(96)
        self._cols = 16
        self._rows = 6
        self._pressure = 32.0
        self._carving = False
        self._t = 0.0
        self._packets: list[dict] = []
        self._phase = [random.uniform(0, math.tau) for _ in range(self._cols * self._rows)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(70)

    def set_pressure(self, pct: float) -> None:
        self._pressure = max(0.0, min(100.0, float(pct)))
        self.update()

    def set_carving(self, on: bool) -> None:
        self._carving = on
        if on and len(self._packets) < 5:
            for _ in range(5 - len(self._packets)):
                self._packets.append(self._new_packet())
        if not on:
            self._packets.clear()
        self.update()

    def _new_packet(self) -> dict:
        return {
            "c": random.uniform(0, self._cols - 1),
            "r": random.uniform(0, self._rows - 1),
            "vx": random.choice((-1, 1)) * random.uniform(0.08, 0.22),
            "vy": random.choice((-1, 1)) * random.uniform(0.05, 0.16),
            "life": random.uniform(0.4, 1.0),
        }

    def _tick(self) -> None:
        self._t = (self._t + 0.09) % (math.tau * 4)
        if self._carving:
            for p in self._packets:
                p["c"] += p["vx"]
                p["r"] += p["vy"]
                if p["c"] < 0 or p["c"] > self._cols - 1:
                    p["vx"] *= -1
                    p["c"] = max(0, min(self._cols - 1, p["c"]))
                if p["r"] < 0 or p["r"] > self._rows - 1:
                    p["vy"] *= -1
                    p["r"] = max(0, min(self._rows - 1, p["r"]))
                p["life"] = 0.45 + 0.55 * abs(math.sin(self._t * 2 + p["c"]))
            if random.random() < 0.08 and len(self._packets) < 8:
                self._packets.append(self._new_packet())
        # Idle organic shimmer still paints every other tick
        if not self._carving:
            self._idle_skip = getattr(self, "_idle_skip", 0) + 1
            if self._idle_skip % 3:
                return
        else:
            self._idle_skip = 0
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w < 20 or h < 20:
            p.end()
            return

        margin = 2
        gap = 2
        cw = (w - margin * 2 - gap * (self._cols - 1)) / self._cols
        rh = (h - margin * 2 - gap * (self._rows - 1)) / self._rows
        filled = int((self._pressure / 100.0) * self._cols * self._rows)

        # Soft void underlay
        p.fillRect(self.rect(), QColor(2, 8, 19, 40))

        idx = 0
        for r in range(self._rows):
            for c in range(self._cols):
                x = margin + c * (cw + gap)
                y = margin + r * (rh + gap)
                # Organic wobble
                wob = 0.55 + 0.45 * math.sin(self._t + self._phase[idx])
                used = idx < filled
                if used:
                    heat = idx / max(1, filled)
                    # Cold cyan → warm amber under heavy load
                    if self._pressure > 85:
                        col = QColor(255, 59, 48, int(90 + 100 * wob))
                    elif self._pressure > 70:
                        col = QColor(255, 149, 0, int(80 + 90 * wob))
                    else:
                        col = QColor(0, 229, 255, int(70 + 110 * wob * (0.5 + 0.5 * heat)))
                else:
                    col = QColor(0, 229, 255, int(12 + 18 * wob))
                # Carve highlight near packets
                if self._carving:
                    for pk in self._packets:
                        if abs(pk["c"] - c) < 1.2 and abs(pk["r"] - r) < 1.2:
                            col = QColor(0, 240, 255, int(160 + 70 * pk["life"]))
                            break
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                # Slightly rounded organic blocks
                p.drawRoundedRect(int(x), int(y), max(2, int(cw)), max(2, int(rh)), 2, 2)
                idx += 1

        # Neural pathways (faint links)
        p.setPen(QPen(QColor(0, 229, 255, 28), 1))
        mid_y = h * 0.5
        p.drawLine(margin, int(mid_y), w - margin, int(mid_y))
        p.drawLine(int(w * 0.5), margin, int(w * 0.5), h - margin)

        # Glowing carve packets
        for pk in self._packets:
            px = margin + pk["c"] * (cw + gap) + cw * 0.5
            py = margin + pk["r"] * (rh + gap) + rh * 0.5
            bloom = QRadialGradient(QPointF(px, py), 14)
            bloom.setColorAt(0.0, QColor(0, 240, 255, int(200 * pk["life"])))
            bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(bloom))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(px, py), 10, 10)
            p.setBrush(QColor(232, 244, 255, 230))
            p.drawEllipse(QPointF(px, py), 2.2, 2.2)

        # Readout
        p.setPen(QColor(112, 128, 144, 180))
        p.setFont(QFont("Cascadia Mono", 8))
        tag = "CARVE" if self._carving else "IDLE"
        p.drawText(6, h - 4, f"{tag} · BLOCKS {filled}/{self._cols * self._rows}")
        p.end()

"""Date / time dial + circular vitals — left HUD chronometer."""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QRadialGradient, QBrush
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget, QHBoxLayout

from jarvis.ui.widgets.stat_gauge import StatGauge


def _local_now(tz_name: str = "America/New_York") -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_name or "America/New_York"))
    except Exception:
        return datetime.now()


class DateDial(QWidget):
    def __init__(self, parent=None, *, timezone: str = "America/New_York") -> None:
        super().__init__(parent)
        self.setFixedSize(176, 176)
        self.timezone = timezone or "America/New_York"
        self._now = _local_now(self.timezone)
        self._t = 0.0
        self._accent = QColor(0, 232, 255)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)

    def set_timezone(self, tz: str) -> None:
        self.timezone = tz or "America/New_York"

    def set_accent(self, hex_color: str) -> None:
        c = QColor(hex_color)
        if c.isValid():
            self._accent = c
            self.update()

    def _tick(self) -> None:
        self._now = _local_now(self.timezone)
        self._t += 0.08
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        cx, cy, r = self.width() / 2, self.height() / 2, 74
        a = self._accent

        bloom = QRadialGradient(cx, cy, r * 1.35)
        bloom.setColorAt(0.0, QColor(a.red(), a.green(), a.blue(), 28))
        bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bloom))
        p.drawEllipse(QPointF(cx, cy), r * 1.25, r * 1.25)

        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 55), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 25), 1))
        p.drawEllipse(QPointF(cx, cy), r - 8, r - 8)

        for i in range(60):
            ang = math.radians(i * 6 - 90)
            major = i % 5 == 0
            inner = r - (11 if major else 5)
            p.setPen(
                QPen(
                    QColor(a.red(), a.green(), a.blue(), 170 if major else 40),
                    1.6 if major else 1,
                )
            )
            p.drawLine(
                QPointF(cx + math.cos(ang) * inner, cy + math.sin(ang) * inner),
                QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r),
            )

        sec = self._now.second + self._now.microsecond / 1e6
        pen = QPen(QColor(a.red(), a.green(), a.blue(), 230), 3.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        rect = QRectF(cx - r + 5, cy - r + 5, (r - 5) * 2, (r - 5) * 2)
        p.drawArc(rect, 90 * 16, int(-sec / 60 * 360 * 16))

        g = QRadialGradient(cx, cy, 48)
        g.setColorAt(0.0, QColor(a.red() // 4, a.green() // 3, a.blue() // 2, 180))
        g.setColorAt(1.0, QColor(0, 8, 16, 220))
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 60), 1))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), 46, 46)

        p.setPen(a)
        font = QFont("Bahnschrift", 12, QFont.Weight.Bold)
        p.setFont(font)
        month = self._now.strftime("%B %d").upper()
        tw = p.fontMetrics().horizontalAdvance(month)
        p.drawText(int(cx - tw / 2), int(cy - 2), month)

        p.setPen(QColor(180, 220, 240, 200))
        p.setFont(QFont("Cascadia Mono", 9))
        day = self._now.strftime("%A").upper()
        tw = p.fontMetrics().horizontalAdvance(day)
        p.drawText(int(cx - tw / 2), int(cy + 16), day)

        p.setPen(QColor(232, 244, 255))
        p.setFont(QFont("Cascadia Mono", 11, QFont.Weight.Bold))
        tstr = self._now.strftime("%I:%M:%S %p").lstrip("0")
        tw = p.fontMetrics().horizontalAdvance(tstr)
        p.drawText(int(cx - tw / 2), 18, tstr)
        p.end()


class ClockPanel(QFrame):
    def __init__(self, parent=None, *, timezone: str = "America/New_York") -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        head = QLabel("TIME  ·  VITALS")
        head.setObjectName("SectionTitle")
        lay.addWidget(head)

        self.dial = DateDial(timezone=timezone or "America/New_York")
        lay.addWidget(self.dial, 0, Qt.AlignmentFlag.AlignHCenter)

        # Circular gauges row (mockup-style)
        gauges = QHBoxLayout()
        gauges.setSpacing(4)
        self.cpu_gauge = StatGauge("CPU", accent="#00e5ff")
        self.ram_gauge = StatGauge("RAM", accent="#ff9a3c")
        self.net_gauge = StatGauge("DSK", accent="#3dff9a")
        gauges.addWidget(self.cpu_gauge)
        gauges.addWidget(self.ram_gauge)
        gauges.addWidget(self.net_gauge)
        lay.addLayout(gauges)

        self.storage = QLabel("STORAGE —")
        self.storage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.storage.setStyleSheet(
            "color:#7a9ab0; font-family:'Cascadia Mono', Consolas; font-size:10px;"
        )
        lay.addWidget(self.storage)

        self.power = QLabel("POWER  —")
        self.power.setStyleSheet(
            "color:#00e8ff; font-family:'Cascadia Mono', Consolas; font-size:11px; letter-spacing:1px;"
        )
        self.power.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.power)

    def set_timezone(self, tz: str) -> None:
        try:
            self.dial.set_timezone(tz)
        except Exception:
            pass

    def set_accent(self, hex_color: str) -> None:
        self.dial.set_accent(hex_color)
        self.cpu_gauge.set_accent(hex_color)
        self.power.setStyleSheet(
            f"color:{hex_color}; font-family:'Cascadia Mono', Consolas; font-size:11px; letter-spacing:1px;"
        )

    def set_vitals(self, cpu: float, ram: float, battery=None, total_g=0.0, free_g=0.0) -> None:
        self.cpu_gauge.set_value(cpu)
        self.ram_gauge.set_value(ram)
        # Disk used % into the third ring
        if total_g > 0:
            used_pct = max(0.0, min(100.0, (1.0 - free_g / total_g) * 100.0))
            self.net_gauge.set_value(used_pct)
            self.storage.setText(
                f"CAPACITY  {total_g:.0f} G    FREE  {free_g:.0f} G"
            )
        if battery is None:
            self.power.setText("POWER  AC MAINS")
        else:
            self.power.setText(f"POWER  {battery:.0f}% RESERVE")

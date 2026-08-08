"""Ops globe — lightweight owner-site map overlay for camera theater.

Equirectangular / procedural dark globe. Pins are owner sites + home security
event dots only. No Cesium / no external map tiles required.
"""

from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF, QTimer
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QRadialGradient,
    QFont,
    QPainterPath,
)
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QSizePolicy,
)


_KIND_COLORS = {
    "home": QColor(0, 232, 255),
    "edge": QColor(120, 200, 255),
    "alert": QColor(255, 90, 60),
}


class OpsGlobePanel(QFrame):
    """Draggable dark globe panel showing owner pins + security event dots."""

    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("OpsGlobePanel")
        self.setFixedSize(380, 320)
        self.setStyleSheet(
            "QFrame#OpsGlobePanel {"
            " background: rgba(2,10,18,235);"
            " border: 1px solid rgba(0,232,255,140);"
            "}"
        )
        self._pins: list[dict[str, Any]] = []
        self._drag_origin = None
        self._drag_start = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)

        head = QHBoxLayout()
        title = QLabel("OPS HUD · OWNER MAP")
        title.setObjectName("SectionTitle")
        title.setStyleSheet("color:#00e8ff; font-size:11px; font-weight:600;")
        tip = QLabel("owner sites only · drag")
        tip.setStyleSheet("color:#6a9aaa; font-size:9px;")
        close = QPushButton("✕")
        close.setFixedSize(28, 24)
        close.setStyleSheet(
            "QPushButton { color:#8aa4b8; background:transparent; border:none; }"
            "QPushButton:hover { color:#00e8ff; }"
        )
        close.clicked.connect(self._close)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(tip)
        head.addWidget(close)
        lay.addLayout(head)

        self.canvas = _GlobeCanvas(self)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay.addWidget(self.canvas, 1)

        self.status = QLabel("No owner pins yet — set home_lat / home_lon")
        self.status.setStyleSheet("color:#8aa4b8; font-size:10px;")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        # Soft pulse ≤5 Hz when visible — never tied to camera paint
        self._pulse = QTimer(self)
        self._pulse.setInterval(250)  # 4 Hz
        self._pulse.timeout.connect(self.canvas.update)

    def set_pins(self, pins: list[dict[str, Any]] | None) -> None:
        self._pins = list(pins or [])
        self.canvas.set_pins(self._pins)
        n_sites = sum(1 for p in self._pins if p.get("kind") != "alert")
        n_alerts = sum(1 for p in self._pins if p.get("kind") == "alert")
        if not self._pins:
            self.status.setText("No owner pins yet — set home_lat / home_lon")
        else:
            self.status.setText(
                f"{n_sites} site(s) · {n_alerts} security event pin(s)"
            )
        self.canvas.update()

    def open_panel(self) -> None:
        self.show()
        self.raise_()
        if hasattr(self, "_pulse") and not self._pulse.isActive():
            self._pulse.start()
            self.canvas.update()

    def close_panel(self) -> None:
        if hasattr(self, "_pulse"):
            self._pulse.stop()
        self.hide()
        self.closed.emit()

    def _close(self) -> None:
        self.close_panel()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = e.globalPosition().toPoint()
            self._drag_start = self.pos()
            self.raise_()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._drag_origin is not None and self._drag_start is not None:
            delta = e.globalPosition().toPoint() - self._drag_origin
            np_ = self._drag_start + delta
            parent = self.parentWidget()
            if parent is not None:
                x = max(0, min(parent.width() - self.width(), np_.x()))
                y = max(0, min(parent.height() - self.height(), np_.y()))
                self.move(x, y)
            else:
                self.move(np_)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._drag_origin = None
        self._drag_start = None
        super().mouseReleaseEvent(e)


class _GlobeCanvas(QWidget):
    """Procedural dark sphere + equirectangular lat/lon pin projection."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pins: list[dict[str, Any]] = []
        self.setMinimumHeight(200)

    def set_pins(self, pins: list[dict[str, Any]]) -> None:
        self._pins = list(pins or [])

    @staticmethod
    def _latlon_to_xy(
        lat: float, lon: float, cx: float, cy: float, r: float
    ) -> QPointF | None:
        """Orthographic-ish projection centered near home / first pin."""
        # Convert to radians; project onto a circle (front hemisphere)
        # Use simple equirectangular mapped into circle for readability
        x = cx + (lon / 180.0) * r * 0.92
        y = cy - (lat / 90.0) * r * 0.72
        dx, dy = x - cx, y - cy
        if dx * dx + dy * dy > r * r:
            # Clamp to rim (still show off-hemisphere as edge ping)
            scale = r / math.sqrt(dx * dx + dy * dy)
            x = cx + dx * scale * 0.98
            y = cy + dy * scale * 0.98
        return QPointF(x, y)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) * 0.42

        # Void
        p.fillRect(self.rect(), QColor(2, 8, 14))

        # Soft radial glow
        grad = QRadialGradient(QPointF(cx - r * 0.2, cy - r * 0.25), r * 1.4)
        grad.setColorAt(0.0, QColor(0, 40, 55, 180))
        grad.setColorAt(0.55, QColor(0, 18, 28, 220))
        grad.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(0, 180, 210, 90), 1.5))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Latitude / longitude grid
        p.setPen(QPen(QColor(0, 120, 140, 50), 1))
        for lat in (-60, -30, 0, 30, 60):
            # ellipse bands
            ry = r * math.cos(math.radians(lat)) * 0.72
            yy = cy - (lat / 90.0) * r * 0.72
            p.drawEllipse(QPointF(cx, yy), r * 0.92, max(4.0, abs(ry) * 0.35))
        for lon in (-120, -60, 0, 60, 120):
            path = QPainterPath()
            first = True
            for lat in range(-90, 91, 6):
                pt = self._latlon_to_xy(float(lat), float(lon), cx, cy, r)
                if pt is None:
                    continue
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
            p.drawPath(path)

        # Continent hint — abstract silhouette arcs (not real geography)
        p.setPen(QPen(QColor(0, 160, 180, 40), 2))
        for a0, a1 in ((-40, 20), (40, 100), (-100, -40)):
            path = QPainterPath()
            path.moveTo(self._latlon_to_xy(20, a0, cx, cy, r) or QPointF(cx, cy))
            path.quadTo(
                self._latlon_to_xy(5, (a0 + a1) / 2, cx, cy, r) or QPointF(cx, cy),
                self._latlon_to_xy(-10, a1, cx, cy, r) or QPointF(cx, cy),
            )
            p.drawPath(path)

        # Pins
        font = QFont()
        font.setPointSize(8)
        p.setFont(font)
        for pin in self._pins:
            try:
                lat = float(pin.get("lat"))
                lon = float(pin.get("lon"))
            except Exception:
                continue
            kind = str(pin.get("kind") or "edge")
            color = _KIND_COLORS.get(kind, _KIND_COLORS["edge"])
            pt = self._latlon_to_xy(lat, lon, cx, cy, r)
            if pt is None:
                continue
            size = 5.0 if kind == "alert" else 7.0
            # Glow
            glow = QRadialGradient(pt, size * 3)
            gc = QColor(color)
            gc.setAlpha(90)
            glow.setColorAt(0.0, gc)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(pt, size * 3, size * 3)
            # Core
            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor(255, 255, 255, 160), 1))
            p.drawEllipse(pt, size, size)
            name = str(pin.get("name") or "")[:28]
            if name and kind != "alert":
                p.setPen(QPen(QColor(200, 240, 255, 200)))
                p.drawText(QRectF(pt.x() + 8, pt.y() - 8, 140, 16), name)

        # Rim label
        p.setPen(QPen(QColor(106, 154, 170, 160)))
        p.drawText(
            QRectF(8, h - 18, w - 16, 14),
            Qt.AlignmentFlag.AlignLeft,
            "OWNER SITES ONLY",
        )
        p.end()

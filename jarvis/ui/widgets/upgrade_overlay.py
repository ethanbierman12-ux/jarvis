"""Full-screen upgrade loading HUD — progress locks at 100%."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QFrame,
    QGraphicsOpacityEffect,
)


class UpgradeOverlay(QWidget):
    """Big centered loading card while Jarvis hot-upgrades scripts and files."""

    finished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("UpgradeOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(2, 8, 14, 230))
        self.setPalette(pal)
        self.setStyleSheet(
            "QWidget#UpgradeOverlay {"
            "  background-color: rgba(2, 8, 14, 235);"
            "}"
        )
        self._target = 0
        self._display = 0
        self._done = False
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._pulse)
        self._auto_close: QTimer | None = None
        self._fade: QPropertyAnimation | None = None

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setContentsMargins(24, 24, 24, 24)

        panel = QFrame()
        panel.setObjectName("UpgradePanel")
        panel.setFixedSize(580, 280)
        panel.setStyleSheet(
            "QFrame#UpgradePanel {"
            "  background-color: rgba(6, 18, 28, 255);"
            "  border: 2px solid #00e8ff;"
            "  border-radius: 4px;"
            "}"
        )
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(32, 28, 32, 28)
        pl.setSpacing(16)

        self.head = QLabel("SYSTEM UPGRADE")
        self.head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.head.setStyleSheet(
            "color:#00e8ff; font-family:Bahnschrift, Segoe UI; font-size:16px;"
            " letter-spacing:6px; font-weight:800; border:none; background:transparent;"
        )
        pl.addWidget(self.head)

        self.sub = QLabel("Compiling environment layers…")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setWordWrap(True)
        self.sub.setStyleSheet(
            "color:#c8e6f5; font-family:Consolas, monospace; font-size:13px;"
            " border:none; background:transparent;"
        )
        pl.addWidget(self.sub)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(22)
        self.bar.setStyleSheet(
            "QProgressBar {"
            "  background:#021018; border:1px solid #00e8ff;"
            "  border-radius:0px;"
            "}"
            "QProgressBar::chunk {"
            "  background-color:#00e8ff;"
            "  margin:1px;"
            "}"
        )
        pl.addWidget(self.bar)

        row = QHBoxLayout()
        self.pct = QLabel("0%")
        self.pct.setStyleSheet(
            "color:#ffffff; font-family:Consolas; font-size:36px; font-weight:700;"
            " border:none; background:transparent;"
        )
        self.phase = QLabel("INIT")
        self.phase.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.phase.setStyleSheet(
            "color:#00ff88; font-family:Consolas; font-size:13px; letter-spacing:3px;"
            " border:none; background:transparent;"
        )
        row.addWidget(self.pct)
        row.addWidget(self.phase, 1)
        pl.addLayout(row)

        self.log = QLabel("Standing by…")
        self.log.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.log.setWordWrap(True)
        self.log.setStyleSheet(
            "color:#7a9aab; font-family:Consolas; font-size:11px;"
            " border:none; background:transparent;"
        )
        pl.addWidget(self.log)

        lay.addWidget(panel)
        self.hide()

    def _fit_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())

    def open_upgrade(self) -> None:
        if self._auto_close is not None:
            self._auto_close.stop()
            self._auto_close = None
        self._done = False
        self._target = 0
        self._display = 0
        self.bar.setValue(0)
        self.pct.setText("0%")
        self.phase.setText("INIT")
        self.sub.setText("Compiling environment layers…")
        self.log.setText("Standing by…")
        self.head.setText("SYSTEM UPGRADE")
        self.setGraphicsEffect(None)
        self._fit_parent()
        self.show()
        self.raise_()
        # Soft fade-in (start partially visible so it never looks broken)
        fx = QGraphicsOpacityEffect(self)
        fx.setOpacity(1.0)
        self.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.4)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._fade = anim
        if not self._tick.isActive():
            self._tick.start(50)

    def set_progress(self, pct: int, *, phase: str = "", detail: str = "") -> None:
        """Drive the bar. Caps at 100 and stops when complete."""
        if not self.isVisible():
            self.open_upgrade()
        else:
            self.raise_()
        pct = max(0, min(100, int(pct)))
        self._target = max(self._target, pct)
        if phase:
            self.phase.setText(str(phase).upper()[:28])
        if detail:
            self.sub.setText(detail)
            self.log.setText(detail[:140])
        if pct >= 100 and self._display >= 96 and not self._done:
            self._finish()

    def _pulse(self) -> None:
        if self._done:
            return
        if self._display < self._target:
            gap = self._target - self._display
            step = 1 if gap < 8 else max(1, gap // 8)
            self._display = min(self._target, self._display + step)
        self.bar.setValue(int(self._display))
        self.pct.setText(f"{int(self._display)}%")
        if self._target >= 100 and self._display >= 100:
            self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._display = 100
        self._target = 100
        self.bar.setValue(100)
        self.pct.setText("100%")
        self.phase.setText("COMPLETE")
        self.sub.setText("Upgrade complete. All scripts and files refreshed.")
        self.log.setText("Locked at 100% · environment layers online")
        self.head.setText("UPGRADE COMPLETE")
        self._tick.stop()
        self.finished.emit()
        self._auto_close = QTimer(self)
        self._auto_close.setSingleShot(True)
        self._auto_close.timeout.connect(self.close_panel)
        self._auto_close.start(3200)

    def close_panel(self) -> None:
        self._tick.stop()
        if self._auto_close is not None:
            self._auto_close.stop()
            self._auto_close = None
        self.hide()
        self.setGraphicsEffect(None)

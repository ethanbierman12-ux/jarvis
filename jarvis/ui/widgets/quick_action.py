"""Corner quick-action chip + HUD alert banner — animated accept/dismiss."""

from __future__ import annotations

from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QGraphicsOpacityEffect,
)

from jarvis.ui.widgets.cmd_button import CmdButton


class QuickActionChip(QFrame):
    accepted = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setFixedWidth(340)
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(0,10,18,240);"
            " border: 1px solid rgba(0,232,255,140);"
            " border-left: 3px solid #00e8ff; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        tip = QLabel("SUGGESTION")
        tip.setStyleSheet(
            "color:#00e8ff; font-size:9px; letter-spacing:2px; font-weight:700;"
        )
        self.label = QLabel("Shall I set up your morning workspace?")
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color:#eaf6ff; font-size:13px;")
        row = QHBoxLayout()
        yes = CmdButton("Proceed", "proceed", kind="ghost")
        no = CmdButton("Dismiss", "dismiss", kind="ghost")
        yes.fired.connect(lambda _: self._yes())
        no.fired.connect(lambda _: self._no())
        row.addWidget(yes)
        row.addWidget(no)
        lay.addWidget(tip)
        lay.addWidget(self.label)
        lay.addLayout(row)

        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(1.0)
        self.hide()

    def offer(self, text: str) -> None:
        self.label.setText(text)
        self._fx.setOpacity(0.0)
        self.show()
        self.raise_()
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._in_anim = anim
        QTimer.singleShot(45000, self.hide)

    def _yes(self) -> None:
        self.hide()
        self.accepted.emit()

    def _no(self) -> None:
        self.hide()
        self.dismissed.emit()


class AlertBanner(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(20,12,0,235);"
            " border: 1px solid rgba(255,140,60,150);"
            " border-left: 3px solid #ff8c3c; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color:#ffd7a8; font-size:13px;")
        lay.addWidget(self.label)

        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(1.0)
        self.hide()

    def show_alert(self, text: str, ms: int = 20000) -> None:
        self.label.setText(text)
        self._fx.setOpacity(0.0)
        self.show()
        self.raise_()
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(260)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._in_anim = anim
        QTimer.singleShot(ms, self.hide)

"""HITL permission / clarification gate — pauses agents before deploy or big structure."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGraphicsOpacityEffect,
    QTextEdit,
)

from jarvis.ui.widgets.cmd_button import CmdButton


class HitlGate(QFrame):
    """Fullscreen-ish card: Approve / Deny (+ optional clarify answer)."""

    decided = pyqtSignal(str, bool, str)  # request_id, approve, answer

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setFixedWidth(420)
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(8,6,2,245);"
            " border: 1px solid rgba(255,176,32,160);"
            " border-left: 4px solid #ffb020; }"
        )
        self._req_id = ""
        self._kind = "permission"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        tip = QLabel("HITL · HUMAN IN THE LOOP")
        tip.setStyleSheet(
            "color:#ffb020; font-size:9px; letter-spacing:2px; font-weight:800;"
        )
        self.title = QLabel("Permission required")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("color:#ffe8c0; font-size:14px; font-weight:700;")
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("color:#c8b898; font-size:12px;")

        self.answer = QTextEdit()
        self.answer.setPlaceholderText("Clarification / notes (optional)…")
        self.answer.setFixedHeight(56)
        self.answer.setStyleSheet(
            "background:#120e08; color:#e8f4ff; border:1px solid rgba(255,176,32,80);"
            " font-size:12px; padding:6px;"
        )
        self.answer.hide()

        row = QHBoxLayout()
        self.yes = CmdButton("Approve", "approve", kind="start")
        self.no = CmdButton("Deny", "deny", kind="danger")
        self.yes.fired.connect(lambda _: self._go(True))
        self.no.fired.connect(lambda _: self._go(False))
        row.addWidget(self.yes)
        row.addWidget(self.no)

        self.hint = QLabel('Voice: say "approve" or "deny"')
        self.hint.setStyleSheet("color:#6a5a40; font-size:10px;")

        lay.addWidget(tip)
        lay.addWidget(self.title)
        lay.addWidget(self.detail)
        lay.addWidget(self.answer)
        lay.addLayout(row)
        lay.addWidget(self.hint)

        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(1.0)
        self.hide()

    def offer(self, payload: dict) -> None:
        self._req_id = str(payload.get("id") or "")
        self._kind = str(payload.get("kind") or "permission")
        self.title.setText(str(payload.get("title") or "Permission required"))
        self.detail.setText(str(payload.get("detail") or ""))
        clarify = self._kind == "clarify"
        self.answer.setVisible(clarify)
        self.yes.setText("Submit" if clarify else "Approve")
        self.no.setText("Skip" if clarify else "Deny")
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

    def hide_gate(self) -> None:
        self.hide()
        self.answer.clear()

    def _go(self, approve: bool) -> None:
        ans = self.answer.toPlainText().strip() if self.answer.isVisible() else ""
        rid = self._req_id
        self.hide_gate()
        self.decided.emit(rid, approve, ans)

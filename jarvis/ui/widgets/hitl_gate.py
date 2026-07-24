"""HITL / multi-choice clarify gate — Approve/Deny or option chips."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGraphicsOpacityEffect,
    QTextEdit,
    QWidget,
    QPushButton,
    QSizePolicy,
)

from jarvis.ui.widgets.cmd_button import CmdButton


class HitlGate(QFrame):
    """Floating card: Approve / Deny, or multi-choice option chips."""

    decided = pyqtSignal(str, bool, str)  # request_id, approve, answer

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setFixedWidth(460)
        self.setMinimumHeight(160)
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(8,6,2,250);"
            " border: 2px solid rgba(255,176,32,200);"
            " border-left: 5px solid #ffb020; }"
        )
        self._req_id = ""
        self._kind = "permission"
        self._option_btns: list[QPushButton] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        tip = QLabel("HITL · CHOOSE AN OPTION")
        tip.setStyleSheet(
            "color:#ffb020; font-size:10px; letter-spacing:2px; font-weight:800;"
        )
        self.title = QLabel("Permission required")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("color:#ffe8c0; font-size:16px; font-weight:700;")
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

        self.options_wrap = QWidget()
        self.options_lay = QVBoxLayout(self.options_wrap)
        self.options_lay.setContentsMargins(0, 4, 0, 4)
        self.options_lay.setSpacing(8)
        self.options_wrap.hide()

        row = QHBoxLayout()
        self.yes = CmdButton("Approve", "approve", kind="start")
        self.no = CmdButton("Deny", "deny", kind="danger")
        self.yes.fired.connect(lambda _: self._go(True))
        self.no.fired.connect(lambda _: self._go(False))
        row.addWidget(self.yes)
        row.addWidget(self.no)

        self.hint = QLabel('Click an option, or type its name and press Enter')
        self.hint.setStyleSheet("color:#8a7a60; font-size:11px;")

        lay.addWidget(tip)
        lay.addWidget(self.title)
        lay.addWidget(self.detail)
        lay.addWidget(self.answer)
        lay.addWidget(self.options_wrap)
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
        clarify = self._kind in ("clarify", "choice")
        options = [str(o) for o in (payload.get("options") or []) if str(o).strip()]
        self.answer.setVisible(clarify and not options)
        self.yes.setVisible(not options)
        self.yes.setText("Submit" if clarify else "Approve")
        self.no.setText("Skip / Cancel" if clarify or options else "Deny")
        self._rebuild_options(options)
        self.adjustSize()
        self._fx.setOpacity(1.0)
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            anim = QPropertyAnimation(self._fx, b"opacity", self)
            anim.setDuration(180)
            anim.setStartValue(0.15)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            self._in_anim = anim
        except Exception:
            pass

    def _rebuild_options(self, options: list[str]) -> None:
        while self.options_lay.count():
            item = self.options_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._option_btns.clear()
        if not options:
            self.options_wrap.hide()
            return
        for i, opt in enumerate(options[:6], start=1):
            btn = QPushButton(f"{i}.  {opt}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(40)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            btn.setStyleSheet(
                "QPushButton {"
                " background: rgba(255,176,32,28); color:#ffe8c0;"
                " border: 1px solid rgba(255,176,32,140);"
                " font-size:13px; font-weight:700; text-align:left; padding:8px 12px;"
                "}"
                "QPushButton:hover {"
                " background: rgba(255,176,32,70); border-color:#ffb020;"
                "}"
                "QPushButton:pressed { background: rgba(255,176,32,110); }"
            )
            btn.clicked.connect(lambda _checked=False, label=opt: self._pick(label))
            self.options_lay.addWidget(btn)
            self._option_btns.append(btn)
        self.options_wrap.show()

    def hide_gate(self) -> None:
        self.hide()
        self.answer.clear()

    def _pick(self, label: str) -> None:
        rid = self._req_id
        self.hide_gate()
        self.decided.emit(rid, True, label)

    def _go(self, approve: bool) -> None:
        ans = self.answer.toPlainText().strip() if self.answer.isVisible() else ""
        rid = self._req_id
        self.hide_gate()
        self.decided.emit(rid, approve, ans)

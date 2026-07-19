"""Update Software typing overlay — cyberpunk glass terminal."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QHBoxLayout, QPushButton,
    QGraphicsOpacityEffect,
)


class TypingOverlay(QWidget):
    submitted = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0,0,0,180);")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        panel = QWidget()
        panel.setFixedSize(560, 280)
        panel.setStyleSheet(
            "background: rgba(4,12,20,230);"
            "border: 1px solid #00ff88;"
            "border-radius: 4px;"
        )
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(18, 16, 18, 16)
        head = QLabel("UPDATE SOFTWARE  ·  SANDBOX COMPILER")
        head.setStyleSheet(
            "color:#00ff88; font-family:Consolas; font-size:12px; letter-spacing:2px; border:none;"
        )
        pl.addWidget(head)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Describe the feature to add…")
        self.editor.setStyleSheet(
            "background:#02080c; color:#b8ffd0; border:1px solid #00aa66;"
            "font-family:Consolas; font-size:13px; border-radius:2px;"
        )
        pl.addWidget(self.editor, 1)
        row = QHBoxLayout()
        cancel = QPushButton("CANCEL")
        cancel.setObjectName("GhostBtn")
        cancel.clicked.connect(self._cancel)
        ok = QPushButton("EXECUTE")
        ok.setObjectName("GhostBtn")
        ok.clicked.connect(self._submit)
        row.addWidget(cancel)
        row.addStretch(1)
        row.addWidget(ok)
        pl.addLayout(row)
        lay.addWidget(panel)
        self.hide()

    def open(self) -> None:
        self.editor.clear()
        self.show()
        self.raise_()
        fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim
        self.editor.setFocus()

    def close_panel(self) -> None:
        self.hide()
        self.setGraphicsEffect(None)

    def _submit(self) -> None:
        text = self.editor.toPlainText().strip()
        self.close_panel()
        if text:
            self.submitted.emit(text)

    def _cancel(self) -> None:
        self.close_panel()
        self.cancelled.emit()

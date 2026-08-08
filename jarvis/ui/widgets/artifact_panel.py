"""Slide-out artifact companion — scan / code / vision results without freezing the HUD."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QSizePolicy,
)


class ArtifactPanel(QFrame):
    """Glass companion window for scan photos, spoken results, and agent artifacts."""

    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ArtifactPanel")
        self.setStyleSheet(
            "QFrame#ArtifactPanel {"
            " background: rgba(4, 12, 20, 235);"
            " border: 1px solid rgba(0, 240, 255, 140);"
            " border-left: 3px solid #00f0ff;"
            "}"
        )
        self.setFixedWidth(380)
        self.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.title = QLabel("ARTIFACT  ·  COMPANION")
        self.title.setStyleSheet(
            "color:#00f0ff; font-family:Consolas; font-size:11px;"
            " letter-spacing:2px; font-weight:700;"
        )
        close = QPushButton("✕")
        close.setFixedSize(28, 24)
        close.setObjectName("GhostBtn")
        close.clicked.connect(self.hide_panel)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(close)
        lay.addLayout(head)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumHeight(160)
        self.image.setMaximumHeight(220)
        self.image.setStyleSheet(
            "background:#02080e; border:1px solid rgba(0,240,255,60); color:#4a6070;"
        )
        self.image.setText("No capture yet")
        self.image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(self.image)

        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setStyleSheet(
            "background:#02080c; color:#e8f4ff; border:1px solid rgba(0,240,255,50);"
            " font-family:Consolas; font-size:12px;"
        )
        lay.addWidget(self.body, 1)

        self.meta = QLabel("")
        self.meta.setStyleSheet("color:#4a6070; font-size:10px; font-family:Consolas;")
        self.meta.setWordWrap(True)
        lay.addWidget(self.meta)

        self._anim: QPropertyAnimation | None = None

    def show_artifact(
        self,
        *,
        title: str = "ARTIFACT",
        text: str = "",
        image_path: str = "",
        image_bgr=None,
        meta: str = "",
    ) -> None:
        self.title.setText(f"ARTIFACT  ·  {title.upper()[:28]}")
        self.body.setPlainText(text or "")
        self.meta.setText(meta or "")
        self._set_image(image_path=image_path, image_bgr=image_bgr)
        self._slide_in()

    def _set_image(self, image_path: str = "", image_bgr=None) -> None:
        pix = QPixmap()
        if image_bgr is not None:
            try:
                import cv2
                import numpy as np

                rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
                pix = QPixmap.fromImage(qimg)
            except Exception:
                pix = QPixmap()
        elif image_path:
            pix = QPixmap(image_path)
        if pix.isNull():
            self.image.setPixmap(QPixmap())
            self.image.setText("No capture yet")
            return
        scaled = pix.scaled(
            self.image.width() or 340,
            200,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image.setPixmap(scaled)
        self.image.setText("")

    def _slide_in(self) -> None:
        from PyQt6.QtCore import QRect

        parent = self.parentWidget()
        if parent is None:
            self.show()
            return
        w = self.width()
        h = max(320, parent.height() - 96)
        start = QRect(parent.width(), 48, w, h)
        end = QRect(parent.width() - w - 16, 48, w, h)
        self.setGeometry(start)
        self.show()
        self.raise_()
        # Stop prior slide so rapid artifacts don't leave geometry mid-tween
        if self._anim is not None:
            try:
                self._anim.stop()
            except Exception:
                pass
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(320)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self.setGeometry(end))
        anim.start()
        self._anim = anim

    def hide_panel(self) -> None:
        self.hide()
        self.closed.emit()

    def reposition(self) -> None:
        if not self.isVisible():
            return
        parent = self.parentWidget()
        if parent is None:
            return
        from PyQt6.QtCore import QRect

        w = self.width()
        self.setGeometry(QRect(parent.width() - w - 16, 48, w, max(320, parent.height() - 96)))

"""Animated HUD command buttons — press flash, hover lift, success pulse."""

from __future__ import annotations

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    pyqtSignal,
    pyqtProperty,
)
from PyQt6.QtWidgets import QPushButton, QGraphicsOpacityEffect, QSizePolicy


class CmdButton(QPushButton):
    """
    Command button with cinematic press feedback.
    Emits `fired(cmd)` after a short flash so the UI feels alive before routing.
    """

    fired = pyqtSignal(str)

    def __init__(
        self,
        label: str,
        cmd: str = "",
        *,
        kind: str = "ghost",
        compact: bool = False,
        parent=None,
    ) -> None:
        super().__init__(label, parent)
        self._cmd = cmd or label.lower()
        self._kind = kind  # ghost | start | talk | danger | media
        self._flash = 0.0
        self._busy = False

        if kind == "talk":
            self.setObjectName("TalkBtn")
        elif kind == "start":
            self.setObjectName("StartBtn")
        elif kind == "danger":
            self.setObjectName("DangerBtn")
        elif kind == "media":
            self.setObjectName("MediaBtn")
        else:
            self.setObjectName("GhostBtn")

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if compact:
            self.setMinimumHeight(30)
            self.setMaximumHeight(34)
        elif kind == "talk":
            self.setMinimumHeight(38)
        else:
            self.setMinimumHeight(34 if kind != "media" else 30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(self._cmd)

        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)

        self.clicked.connect(self._on_click)

    @pyqtProperty(float)
    def flash(self) -> float:
        return self._flash

    @flash.setter
    def flash(self, value: float) -> None:
        self._flash = float(value)
        self._apply_flash_style()

    def set_command(self, cmd: str) -> None:
        self._cmd = cmd
        self.setToolTip(cmd)

    def _on_click(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            from jarvis.ui.hud_sfx import play_click

            play_click()
        except Exception:
            pass
        self._run_flash(peak=1.0, ms=180)
        # Fire after the press lands so animation is visible
        QTimer.singleShot(70, lambda: self.fired.emit(self._cmd))
        QTimer.singleShot(220, self._clear_busy)

    def pulse_success(self) -> None:
        """Short cyan confirmation after a command lands."""
        try:
            from jarvis.ui.hud_sfx import play_confirm

            play_confirm()
        except Exception:
            pass
        self._run_flash(peak=1.0, ms=320)

    def _clear_busy(self) -> None:
        self._busy = False

    def _run_flash(self, peak: float = 1.0, ms: int = 200) -> None:
        anim = QPropertyAnimation(self, b"flash", self)
        anim.setDuration(ms)
        anim.setStartValue(peak)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._flash_anim = anim

        # Soft opacity dip then recover
        fade = QPropertyAnimation(self._fx, b"opacity", self)
        fade.setDuration(ms)
        fade.setKeyValueAt(0.0, 1.0)
        fade.setKeyValueAt(0.35, 0.72)
        fade.setKeyValueAt(1.0, 1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutQuad)
        fade.start()
        self._fade_anim = fade

    def _apply_flash_style(self) -> None:
        f = max(0.0, min(1.0, self._flash))
        if f < 0.02:
            self.setStyleSheet("")
            return
        if self._kind == "danger":
            bg = f"rgba(255, 90, 50, {int(40 + 90 * f)})"
            border = "#ff6b35"
            color = "#ffe8dc"
        elif self._kind in ("start", "talk"):
            bg = f"rgba(0, 240, 255, {int(70 + 100 * f)})"
            border = "#00e5ff"
            color = "#041018" if self._kind == "talk" else "#ffffff"
        else:
            bg = f"rgba(0, 232, 255, {int(35 + 110 * f)})"
            border = "#00e8ff"
            color = "#f2ffff"
        self.setStyleSheet(
            f"QPushButton {{"
            f" background: {bg};"
            f" border: 1px solid {border};"
            f" color: {color};"
            f" font-weight: 700;"
            f"}}"
        )


class CmdButtonGrid:
    """Helper — not a widget; builds a list of CmdButtons for a section."""

    @staticmethod
    def wire(buttons: list[CmdButton], sink) -> None:
        for b in buttons:
            b.fired.connect(sink)

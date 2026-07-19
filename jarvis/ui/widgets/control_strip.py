"""Left control strip — curated command grid (clean sections, no clutter)."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QSizePolicy,
)

from jarvis.ui.widgets.cmd_button import CmdButton


_PANEL = "#071018"
_SCROLL_CSS = f"""
QScrollArea {{ background: {_PANEL}; border: none; }}
QScrollArea > QWidget > QWidget {{ background: {_PANEL}; }}
QScrollBar:vertical {{ width: 5px; background: transparent; margin: 0; }}
QScrollBar::handle:vertical {{
    background: rgba(0,232,255,70); min-height: 28px; border-radius: 2px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


class ControlStrip(QFrame):
    action = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(260)
        self._force_dark(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(_SCROLL_CSS)
        self._force_dark(scroll)
        if scroll.viewport():
            self._force_dark(scroll.viewport())
        outer.addWidget(scroll)

        inner = QFrame()
        inner.setObjectName("GlassPanel")
        self._force_dark(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 10, 8, 10)
        lay.setSpacing(12)
        self._buttons: list[CmdButton] = []

        # Curated — one job per button, no duplicates
        sections = (
            (
                "CORE",
                (
                    ("Camera", "open camera", "ghost"),
                    ("Screen", "look at my screen", "ghost"),
                    ("Music", "play music", "ghost"),
                    ("Mail", "check email", "ghost"),
                    ("Map", "open map view", "ghost"),
                    ("News", "pull up the news", "ghost"),
                    ("Stats", "show stats", "ghost"),
                    ("Away", "away mode", "ghost"),
                ),
            ),
            (
                "BUILD",
                (
                    ("Site", "build a site", "ghost"),
                    ("Vibe", "start vibe coding", "ghost"),
                    ("Find biz", "find biz", "ghost"),
                    ("Search", "search the web for latest AI news", "ghost"),
                ),
            ),
            (
                "HUB AGENTS",
                (
                    ("Sarah", "sarah triage support tickets", "ghost"),
                    ("Tom", "investigate the checkout bug and open a PR", "ghost"),
                    ("Admin", "schedule a meeting with the client who complained in support", "ghost"),
                    ("Standby", "hub standby", "ghost"),
                ),
            ),
            (
                "EMERGENCY",
                (
                    ("Lock", "lock", "danger"),
                    ("Sleep", "sleep", "danger"),
                    ("Panic", "panic", "danger"),
                    ("Status", "status", "ghost"),
                ),
            ),
        )

        for title, items in sections:
            head = QLabel(title)
            head.setObjectName("SectionTitle")
            lay.addWidget(head)
            grid = QGridLayout()
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            grid.setContentsMargins(0, 0, 0, 2)
            for i, (label, cmd, kind) in enumerate(items):
                b = CmdButton(label, cmd, kind=kind, compact=True)
                b.fired.connect(self._fire)
                self._buttons.append(b)
                grid.addWidget(b, i // 2, i % 2)
            lay.addLayout(grid)

        tip = QLabel("Tip: type site · vibe · sarah · screen")
        tip.setObjectName("Dim")
        tip.setStyleSheet("font-size:9px; letter-spacing:0.5px; color:#4a6070;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lay.addStretch(1)
        scroll.setWidget(inner)

    @staticmethod
    def _force_dark(w: QWidget) -> None:
        pal = w.palette()
        dark = QColor(_PANEL)
        pal.setColor(QPalette.ColorRole.Window, dark)
        pal.setColor(QPalette.ColorRole.Base, dark)
        pal.setColor(QPalette.ColorRole.Button, dark)
        w.setPalette(pal)
        w.setAutoFillBackground(True)

    def _fire(self, cmd: str) -> None:
        self.action.emit(cmd)

    def pulse_command(self, cmd: str) -> None:
        c = (cmd or "").lower().strip()
        for b in self._buttons:
            if b._cmd.lower() == c or c.startswith(b._cmd.lower()[:12]):
                b.pulse_success()
                break

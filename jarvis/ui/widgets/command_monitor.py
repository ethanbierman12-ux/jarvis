"""Live command monitor — telemetry strip for heard / routed / frozen commands."""

from __future__ import annotations

from collections import deque
from time import strftime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
)


class CommandMonitor(QFrame):
    """Compact additive HUD showing recent command traffic."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setMinimumHeight(160)
        self._history: deque[str] = deque(maxlen=40)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("CMDS")
        title.setObjectName("SectionTitle")
        title.setStyleSheet(
            "font-size:9px; letter-spacing:2px; color:#3d5568; border:none;"
        )
        self.badge = QLabel("● IDLE")
        self.badge.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px; font-weight:700;"
        )
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.badge)
        lay.addLayout(head)

        self.stats = QLabel("0 routed · registry open")
        self.stats.setStyleSheet(
            "color:#5a7388; font-size:10px; font-family:Consolas, monospace;"
        )
        lay.addWidget(self.stats)

        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget { background:transparent; border:none; color:#c8e6f5;"
            " font-family:Consolas, monospace; font-size:11px; outline:none; }"
            "QListWidget::item { padding:4px 2px; border-bottom:1px solid rgba(0,232,255,25); }"
        )
        lay.addWidget(self.list, 1)

        self._routed = 0
        self._blocked = 0

    def set_registry_state(self, frozen: bool) -> None:
        if frozen:
            self.badge.setText("● FROZEN")
            self.badge.setStyleSheet(
                "color:#ff6b35; font-size:9px; letter-spacing:2px; font-weight:700;"
            )
        else:
            self.badge.setText("● LIVE")
            self.badge.setStyleSheet(
                "color:#00ff88; font-size:9px; letter-spacing:2px; font-weight:700;"
            )
        self._refresh_stats()

    def note(
        self,
        text: str,
        *,
        kind: str = "route",
        detail: str = "",
    ) -> None:
        """kind: hear | route | block | upgrade | workflow"""
        stamp = strftime("%H:%M:%S")
        tag = {
            "hear": "HEAR",
            "route": "RUN",
            "block": "HOLD",
            "upgrade": "UPG",
            "workflow": "FLOW",
        }.get(kind, "EVT")
        line = f"{stamp}  [{tag}]  {(text or '')[:72]}"
        if detail:
            line += f"  · {detail[:40]}"
        self._history.appendleft(line)
        if kind == "route":
            self._routed += 1
        elif kind == "block":
            self._blocked += 1
        item = QListWidgetItem(line)
        if kind == "block":
            item.setForeground(Qt.GlobalColor.red)
        elif kind == "upgrade":
            item.setForeground(Qt.GlobalColor.cyan)
        elif kind == "workflow":
            item.setForeground(Qt.GlobalColor.yellow)
        self.list.insertItem(0, item)
        while self.list.count() > 40:
            self.list.takeItem(self.list.count() - 1)
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        state = "frozen" if "FROZEN" in self.badge.text() else "open"
        self.stats.setText(
            f"{self._routed} routed · {self._blocked} held · registry {state}"
        )

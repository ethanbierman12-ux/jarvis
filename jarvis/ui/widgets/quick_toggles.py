"""Quick toggle grid — smart-home / night / quiet / smooth / mini HUD."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout, QSizePolicy


class _ToggleCell(QPushButton):
    def __init__(self, key: str, label: str, parent=None) -> None:
        super().__init__(label, parent)
        self.key = key
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(0, 34)
        self.setMaximumHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName("QuickToggle")
        self._refresh()
        self.toggled.connect(lambda _=False: self._refresh())

    def _refresh(self) -> None:
        on = self.isChecked()
        self.setProperty("on", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class QuickToggleGrid(QFrame):
    """Dense hatch-grid of system toggles (mockup-style)."""

    toggled = pyqtSignal(str, bool)  # key, on

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMaximumHeight(128)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        head = QLabel("QUICK  ·  RELAYS")
        head.setObjectName("SectionTitle")
        lay.addWidget(head)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        self._cells: dict[str, _ToggleCell] = {}
        specs = (
            ("lamp", "LAMP"),
            ("night", "NIGHT"),
            ("quiet", "QUIET"),
            ("smooth", "SMOOTH"),
            ("mini", "MINI"),
            ("listen", "LISTEN"),
        )
        for i, (key, label) in enumerate(specs):
            cell = _ToggleCell(key, label)
            cell.toggled.connect(lambda on, k=key: self.toggled.emit(k, bool(on)))
            self._cells[key] = cell
            grid.addWidget(cell, i // 3, i % 3)
        lay.addLayout(grid)

    def set_state(self, key: str, on: bool) -> None:
        cell = self._cells.get(key)
        if cell is None:
            return
        cell.blockSignals(True)
        cell.setChecked(bool(on))
        cell.blockSignals(False)
        cell._refresh()

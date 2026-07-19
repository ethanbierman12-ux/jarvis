"""Right-side atmospheric analysis HUD."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout


class WeatherPanel(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("ATMOSPHERE")
        title.setObjectName("SectionTitle")
        self.badge = QLabel("CLEAR")
        self.badge.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px; font-weight:700;"
        )
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.badge)
        lay.addLayout(head)

        self.temp = QLabel("—°")
        self.temp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.temp.setStyleSheet(
            "color:#00e8ff; font-size:48px; font-weight:700; letter-spacing:2px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        lay.addWidget(self.temp)

        self.condition = QLabel("Syncing sensors…")
        self.condition.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.condition.setObjectName("Dim")
        lay.addWidget(self.condition)

        self.city = QLabel("")
        self.city.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.city.setStyleSheet(
            "color:#eaf6ff; font-size:12px; letter-spacing:2px; font-weight:600;"
        )
        lay.addWidget(self.city)

        div = QLabel("·  ·  ·")
        div.setAlignment(Qt.AlignmentFlag.AlignCenter)
        div.setStyleSheet("color:#3a5060; font-size:10px;")
        lay.addWidget(div)

        self.forecast = QLabel("")
        self.forecast.setObjectName("Dim")
        self.forecast.setWordWrap(True)
        self.forecast.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.forecast.setStyleSheet(
            "color:#8aa4b8; font-family:'Cascadia Mono', Consolas; font-size:11px;"
            " line-height: 1.35;"
        )
        lay.addWidget(self.forecast)
        lay.addStretch(1)

    def set_context(self, data: dict) -> None:
        if data.get("temp_c") is not None:
            self.temp.setText(f"{data['temp_c']:.0f}°")
        self.condition.setText((data.get("condition") or "—").title())
        self.city.setText((data.get("city") or "").upper())
        lines = []
        for day in data.get("forecast") or []:
            lines.append(
                f"{day.get('date', '')[-5:]}  "
                f"{day.get('min', '—')}–{day.get('max', '—')}°  "
                f"{(day.get('desc') or '')[:18]}"
            )
        self.forecast.setText("\n".join(lines[:5]) if lines else "Forecast standing by.")

    def set_mood(self, mood: str, accent: str = "#00e8ff") -> None:
        self.temp.setStyleSheet(
            f"color:{accent}; font-size:48px; font-weight:700; letter-spacing:2px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        label = mood.upper()
        self.badge.setText(label)
        self.badge.setStyleSheet(
            f"color:{accent}; font-size:9px; letter-spacing:2px; font-weight:700;"
        )
        if mood in ("rain", "storm"):
            self.condition.setStyleSheet(f"color:{accent}; font-size:12px;")
        else:
            self.condition.setObjectName("Dim")
            self.condition.setStyleSheet("")

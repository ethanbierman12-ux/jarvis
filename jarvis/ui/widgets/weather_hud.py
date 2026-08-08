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
            "color:#00f0ff; font-size:48px; font-weight:700; letter-spacing:2px;"
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

        self.orbital = QLabel("SAT · syncing…")
        self.orbital.setWordWrap(True)
        self.orbital.setStyleSheet(
            "color:#7eb6ff; font-family:'Cascadia Mono', Consolas; font-size:10px;"
            " letter-spacing:0.5px;"
        )
        lay.addWidget(self.orbital)
        lay.addStretch(1)

    def set_context(self, data: dict) -> None:
        # Prefer Fahrenheit display for US cities
        temp = data.get("temp_display")
        if temp is None:
            if data.get("temp_f") is not None:
                temp = data["temp_f"]
            elif data.get("temp_c") is not None:
                temp = float(data["temp_c"]) * 9.0 / 5.0 + 32.0
        unit = (data.get("unit_label") or ("F" if (data.get("units") or "f") == "f" else "C"))
        if temp is not None:
            self.temp.setText(f"{float(temp):.0f}°{unit}")
        date = data.get("date") or ""
        cond = (data.get("condition") or "—").title()
        if date:
            self.condition.setText(f"{date} · {cond}")
        else:
            self.condition.setText(cond)
        self.city.setText((data.get("city") or "").upper())
        lines = []
        for day in data.get("forecast") or []:
            unit_sym = "°F" if (data.get("units") or "f") == "f" else "°C"
            lines.append(
                f"{day.get('date', '')[-5:]}  "
                f"{day.get('min', '—')}–{day.get('max', '—')}{unit_sym}  "
                f"{(day.get('desc') or '')[:18]}"
            )
        self.forecast.setText("\n".join(lines[:4]) if lines else "Forecast standing by.")
        if data.get("orbital"):
            self.set_orbital(str(data["orbital"]))

    def set_orbital(self, summary: str) -> None:
        text = (summary or "").strip() or "SAT · standing by"
        self.orbital.setText(f"SAT · {text}" if not text.upper().startswith("ISS") else text)

    def set_mood(self, mood: str, accent: str = "#00f0ff") -> None:
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

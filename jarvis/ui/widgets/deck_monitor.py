"""Top-monitor command deck — holographic canvas (Screen 3)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QGridLayout,
    QScrollArea,
)


class DeckMonitorWindow(QMainWindow):
    """High-visibility command deck for the top / large monitor."""

    def __init__(self, settings=None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("JARVIS · COMMAND DECK · SCREEN 3")
        self.setMinimumSize(1100, 700)
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("COMMAND DECK")
        title.setStyleSheet(
            "color:#00e8ff; font-size:18px; letter-spacing:5px; font-weight:700;"
        )
        self.live = QLabel("● LIVE")
        self.live.setStyleSheet(
            "color:#3dff9a; font-size:11px; letter-spacing:2px; font-weight:700;"
        )
        self.badge = QLabel("SCREEN 3 · TOP CANVAS")
        self.badge.setStyleSheet("color:#5a7388; font-size:10px; letter-spacing:2px;")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.live)
        head.addWidget(self.badge)
        lay.addLayout(head)

        sub = QLabel(
            "VISION · SPACE · HOME · ENVIRONMENT · MEDIA CANVAS"
        )
        sub.setStyleSheet("color:#4a6070; font-size:10px; letter-spacing:3px;")
        lay.addWidget(sub)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.kpi_ha = self._card("HOME ASSISTANT", "—")
        self.kpi_space = self._card("SPACE WEATHER", "—")
        self.kpi_iss = self._card("ISS / ORBIT", "—")
        self.kpi_vision = self._card("VISION / CAM", "Standby")
        self.kpi_brain = self._card("AGENT LOAD", "Idle")
        self.kpi_media = self._card("MEDIA FOCUS", "Desktop")
        grid.addWidget(self.kpi_ha, 0, 0)
        grid.addWidget(self.kpi_space, 0, 1)
        grid.addWidget(self.kpi_iss, 0, 2)
        grid.addWidget(self.kpi_vision, 1, 0)
        grid.addWidget(self.kpi_brain, 1, 1)
        grid.addWidget(self.kpi_media, 1, 2)
        lay.addLayout(grid)

        feed_lab = QLabel("TACTICAL FEED")
        feed_lab.setStyleSheet(
            "color:#5a7388; font-size:10px; letter-spacing:3px; font-weight:600;"
        )
        lay.addWidget(feed_lab)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._feed_host = QWidget()
        self._feed_lay = QVBoxLayout(self._feed_host)
        self._feed_lay.setContentsMargins(0, 0, 0, 0)
        self._feed_lay.setSpacing(6)
        self._feed_lay.addStretch(1)
        self._scroll.setWidget(self._feed_host)
        lay.addWidget(self._scroll, 1)

        self.setStyleSheet(
            "QMainWindow { background:#04080c; }"
            "QWidget { background:#04080c; color:#d0e8f8; }"
            "QScrollArea { background:transparent; border:none; }"
        )
        self._detail = False
        self._detail_panel = QLabel("")
        self._detail_panel.setWordWrap(True)
        self._detail_panel.setVisible(False)
        self._detail_panel.setStyleSheet(
            "color:#c8e8ff; font-size:14px; padding:14px;"
            " background:rgba(0,40,60,200); border:1px solid #00e8ff66;"
        )
        lay.addWidget(self._detail_panel)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_env)
        self._timer.start(45000)
        QTimer.singleShot(1200, self._refresh_env)

    def _card(self, label: str, value: str) -> QFrame:
        f = QFrame()
        f.setMinimumHeight(110)
        f.setStyleSheet(
            "QFrame { background:rgba(8,18,28,230); border:1px solid #1a3a4a;"
            " border-top:2px solid #00e8ff88; }"
        )
        v = QVBoxLayout(f)
        v.setContentsMargins(14, 12, 14, 12)
        cap = QLabel(label)
        cap.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px; border:none;"
        )
        val = QLabel(value)
        val.setWordWrap(True)
        val.setStyleSheet(
            "color:#e8f4ff; font-size:15px; font-weight:600; border:none;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        v.addWidget(cap)
        v.addWidget(val, 1)
        f._val = val  # type: ignore[attr-defined]
        return f

    def _refresh_env(self) -> None:
        # Best-effort HA / space — never block UI
        try:
            from jarvis.config import Settings
            from jarvis.core.home_assistant import HomeAssistant

            s = self.settings or Settings.load()
            if getattr(s, "ha_enabled", False) and getattr(s, "ha_token", ""):
                ha = HomeAssistant(
                    url=getattr(s, "ha_url", "") or "",
                    token=getattr(s, "ha_token", "") or "",
                    enabled=True,
                )
                self.kpi_ha._val.setText(ha.status()[:80])  # type: ignore[attr-defined]
            else:
                self.kpi_ha._val.setText("Offline / no token")  # type: ignore[attr-defined]
        except Exception:
            self.kpi_ha._val.setText("HA link standby")  # type: ignore[attr-defined]
        try:
            from jarvis.core.space_weather import SpaceWeather

            sw = SpaceWeather()
            brief = sw.speak_brief(report_only=True)
            self.kpi_space._val.setText(brief[:90])  # type: ignore[attr-defined]
            self.kpi_iss._val.setText(sw.iss_overhead()[:90])  # type: ignore[attr-defined]
        except Exception:
            pass

    def set_vision(self, text: str) -> None:
        self.kpi_vision._val.setText(text or "Standby")  # type: ignore[attr-defined]

    def set_brain(self, text: str) -> None:
        self.kpi_brain._val.setText(text or "Idle")  # type: ignore[attr-defined]

    def set_media(self, text: str) -> None:
        self.kpi_media._val.setText(text or "Desktop")  # type: ignore[attr-defined]

    def set_feed(self, lines: list[str]) -> None:
        while self._feed_lay.count() > 1:
            item = self._feed_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for line in (lines or [])[-18:]:
            lab = QLabel(str(line))
            lab.setWordWrap(True)
            lab.setStyleSheet(
                "color:#9ec4d8; font-size:13px; padding:6px 8px;"
                " background:rgba(10,20,30,180); border-left:3px solid #00e8ff66;"
            )
            self._feed_lay.insertWidget(self._feed_lay.count() - 1, lab)

    def set_detail_mode(self, on: bool, text: str = "") -> None:
        """Gaze look-up: expand tactical detail on the command deck."""
        self._detail = bool(on)
        self._detail_panel.setVisible(self._detail)
        if self._detail:
            body = text or (
                "GAZE DETAIL · look-up dwell engaged\n"
                "· Home / space / ISS cards refreshed\n"
                "· Throw-up gesture → move foreground app here\n"
                "· Return gaze to center to collapse detail"
            )
            self._detail_panel.setText(body)
            self.live.setText("● DETAIL")
            self.live.setStyleSheet(
                "color:#ffcc66; font-size:11px; letter-spacing:2px; font-weight:700;"
            )
            self._refresh_env()
        else:
            self.live.setText("● LIVE")
            self.live.setStyleSheet(
                "color:#3dff9a; font-size:11px; letter-spacing:2px; font-weight:700;"
            )

    def set_iss_alert(self, text: str) -> None:
        self.kpi_iss._val.setText(text[:120] if text else "—")  # type: ignore[attr-defined]
        self.set_detail_mode(True, text or "ISS overhead — tracking on deck.")

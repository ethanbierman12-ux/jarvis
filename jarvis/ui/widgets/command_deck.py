"""Premium command deck — KPI grid + live intelligence feed."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QGraphicsOpacityEffect,
)


class _Kpi(QFrame):
    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)
        self.value = QLabel("—")
        self.value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.value.setStyleSheet(
            "color:#00e8ff; font-size:20px; font-weight:700; letter-spacing:1px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        self.caption = QLabel(label.upper())
        self.caption.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px; font-weight:600;"
        )
        lay.addWidget(self.value)
        lay.addWidget(self.caption)

    def set_value(self, text: str, accent: str = "#00e8ff") -> None:
        self.value.setText(text)
        self.value.setStyleSheet(
            f"color:{accent}; font-size:20px; font-weight:700; letter-spacing:1px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )


class CommandDeck(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("COMMAND CENTER")
        title.setObjectName("SectionTitle")
        self.live = QLabel("● LIVE")
        self.live.setStyleSheet(
            "color:#00e8ff; font-size:9px; letter-spacing:2px; font-weight:700;"
        )
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.live)
        lay.addLayout(head)

        self.subtitle = QLabel("SPEND · TASKS · AWAY OPS")
        self.subtitle.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px;"
        )
        lay.addWidget(self.subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.kpi_spend = _Kpi("Spent today")
        self.kpi_week = _Kpi("This week")
        self.kpi_tasks = _Kpi("Open tasks")
        self.kpi_steward = _Kpi("Away jobs")
        grid.addWidget(self.kpi_spend, 0, 0)
        grid.addWidget(self.kpi_week, 0, 1)
        grid.addWidget(self.kpi_tasks, 1, 0)
        grid.addWidget(self.kpi_steward, 1, 1)
        lay.addLayout(grid)

        feed_head = QHBoxLayout()
        feed_title = QLabel("DATA FEED")
        feed_title.setObjectName("SectionTitle")
        feed_head.addWidget(feed_title)
        feed_head.addStretch(1)
        lay.addLayout(feed_head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self._feed_host = QWidget()
        self._feed_host.setStyleSheet("background: transparent;")
        self._feed_lay = QVBoxLayout(self._feed_host)
        self._feed_lay.setContentsMargins(0, 0, 0, 0)
        self._feed_lay.setSpacing(5)
        self._feed_lay.addStretch(1)
        self._scroll.setWidget(self._feed_host)
        lay.addWidget(self._scroll, 1)

        self._lines: list[QLabel] = []
        self._accent = "#00e8ff"
        self.set_feed(["Systems warming — feed standing by."])

    def set_stats(self, stats: dict, accent: str = "#00e8ff") -> None:
        self._accent = accent
        cur = stats.get("currency") or "USD"
        today = float(stats.get("spent_today") or 0)
        week = float(stats.get("spent_week") or 0)
        tasks = int(stats.get("open_tasks") or 0)
        done = int(stats.get("steward_done") or 0)
        queued = int(stats.get("steward_queued") or 0)
        self.kpi_spend.set_value(
            f"{cur} {today:.0f}" if today >= 10 else f"{cur} {today:.2f}", accent
        )
        self.kpi_week.set_value(
            f"{cur} {week:.0f}" if week >= 10 else f"{cur} {week:.2f}", accent
        )
        self.kpi_tasks.set_value(str(tasks), accent)
        self.kpi_steward.set_value(f"{done} / {queued}", accent)
        stamp = stats.get("updated") or "—"
        away = " · AWAY MODE" if stats.get("away_mode") else ""
        self.subtitle.setText(f"SYNCED {stamp}{away}")
        self.live.setStyleSheet(
            f"color:{accent}; font-size:9px; letter-spacing:2px; font-weight:700;"
        )

    def set_feed(self, lines: list[str]) -> None:
        while self._feed_lay.count():
            item = self._feed_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._lines.clear()
        for line in lines[:20]:
            self._add_line(str(line), fade=False)
        self._feed_lay.addStretch(1)

    def prepend_feed(self, line: str, accent: str | None = None) -> None:
        accent = accent or self._accent
        # Remove stretch, insert, re-add stretch
        if self._feed_lay.count():
            last = self._feed_lay.itemAt(self._feed_lay.count() - 1)
            if last and last.spacerItem():
                self._feed_lay.takeAt(self._feed_lay.count() - 1)
        lab = self._make_line(line, accent)
        self._feed_lay.insertWidget(0, lab)
        self._lines.insert(0, lab)
        fx = QGraphicsOpacityEffect(lab)
        lab.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", lab)
        anim.setDuration(380)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        lab._fade = anim  # keep ref
        self._feed_lay.addStretch(1)
        while len(self._lines) > 22:
            old = self._lines.pop()
            self._feed_lay.removeWidget(old)
            old.deleteLater()

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        for k in (self.kpi_spend, self.kpi_week, self.kpi_tasks, self.kpi_steward):
            k.value.setStyleSheet(
                f"color:{accent}; font-size:20px; font-weight:700; letter-spacing:1px;"
                " font-family: Bahnschrift, 'Segoe UI';"
            )
        self.live.setStyleSheet(
            f"color:{accent}; font-size:9px; letter-spacing:2px; font-weight:700;"
        )

    def _add_line(self, line: str, fade: bool = True) -> None:
        lab = self._make_line(line, self._accent)
        self._feed_lay.addWidget(lab)
        self._lines.append(lab)

    def _make_line(self, line: str, accent: str) -> QLabel:
        lab = QLabel(line)
        lab.setWordWrap(True)
        lab.setStyleSheet(
            f"color:#d0e6f2; font-size:11px;"
            f" font-family: 'Cascadia Mono', Consolas, monospace;"
            f" padding: 7px 8px; background: rgba(0,14,24,160);"
            f" border-left: 2px solid {accent};"
        )
        return lab

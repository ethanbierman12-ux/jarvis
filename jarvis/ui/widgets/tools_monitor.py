"""Left-monitor tools panel — logs, net, system glance (Screen 2 / XRW)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPlainTextEdit,
    QProgressBar,
)


class ToolsMonitorWindow(QMainWindow):
    """Persistent background tools — glanceable, not the main workspace."""

    def __init__(self, settings=None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("JARVIS · TOOLS · SCREEN 2")
        self.setMinimumSize(720, 640)
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("TOOLS STREAM")
        title.setStyleSheet(
            "color:#00e8ff; font-size:14px; letter-spacing:4px; font-weight:700;"
        )
        self.badge = QLabel("SCREEN 2 · LEFT")
        self.badge.setStyleSheet(
            "color:#5a7388; font-size:10px; letter-spacing:2px;"
        )
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.badge)
        lay.addLayout(head)

        sub = QLabel("NET · SYSTEM · CONSOLE · SCAFFOLD")
        sub.setStyleSheet("color:#4a6070; font-size:9px; letter-spacing:2px;")
        lay.addWidget(sub)

        # KPI strip
        strip = QHBoxLayout()
        self.kpi_cpu = self._kpi("CPU")
        self.kpi_ram = self._kpi("RAM")
        self.kpi_net = self._kpi("NET")
        strip.addWidget(self.kpi_cpu)
        strip.addWidget(self.kpi_ram)
        strip.addWidget(self.kpi_net)
        lay.addLayout(strip)

        self.bar_cpu = QProgressBar()
        self.bar_ram = QProgressBar()
        for b in (self.bar_cpu, self.bar_ram):
            b.setRange(0, 100)
            b.setTextVisible(False)
            b.setFixedHeight(6)
            b.setStyleSheet(
                "QProgressBar { background:#0a1218; border:none; }"
                "QProgressBar::chunk { background:#00e8ff; }"
            )
        lay.addWidget(self.bar_cpu)
        lay.addWidget(self.bar_ram)

        self.net_line = QLabel("Net watch · standing by")
        self.net_line.setStyleSheet("color:#8aa4b8; font-size:12px;")
        self.net_line.setWordWrap(True)
        lay.addWidget(self.net_line)

        # Voice clone waveform + impersonation status (mirrors center HUD wave)
        clone_lab = QLabel("VOICE CLONE · WAVEFORM")
        clone_lab.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px; font-weight:600;"
        )
        lay.addWidget(clone_lab)
        self.clone_line = QLabel("Clone · idle · no active sample")
        self.clone_line.setStyleSheet("color:#9ec4d8; font-size:12px;")
        self.clone_line.setWordWrap(True)
        lay.addWidget(self.clone_line)
        try:
            from jarvis.ui.widgets.voice_waveform import VoiceWaveform

            self.wave = VoiceWaveform()
            self.wave.setFixedHeight(56)
            lay.addWidget(self.wave)
        except Exception:
            self.wave = None

        log_lab = QLabel("LIVE CONSOLE")
        log_lab.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px; font-weight:600;"
        )
        lay.addWidget(log_lab)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(400)
        self.console.setStyleSheet(
            "QPlainTextEdit { background:rgba(4,10,16,240); color:#9ec4d8;"
            " border:1px solid #1a3344; font-family: Consolas, 'Cascadia Mono';"
            " font-size:11px; padding:8px; }"
        )
        lay.addWidget(self.console, 1)

        self.setStyleSheet(
            "QMainWindow { background:#060b10; }"
            "QWidget { background:#060b10; color:#c8e0f0; }"
        )
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._poll_system)
        self._tick.start(2000)

    def _kpi(self, label: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet(
            "QFrame { background:rgba(8,16,24,220); border:1px solid #1a3344;"
            " border-left:3px solid #00e8ff; }"
        )
        v = QVBoxLayout(f)
        v.setContentsMargins(10, 8, 10, 8)
        val = QLabel("—")
        val.setObjectName("kpiVal")
        val.setStyleSheet(
            "color:#00e8ff; font-size:18px; font-weight:700; border:none;"
        )
        cap = QLabel(label)
        cap.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px; border:none;"
        )
        v.addWidget(val)
        v.addWidget(cap)
        f._val = val  # type: ignore[attr-defined]
        return f

    def _poll_system(self) -> None:
        try:
            import psutil

            cpu = float(psutil.cpu_percent(interval=None))
            ram = float(psutil.virtual_memory().percent)
            self.kpi_cpu._val.setText(f"{cpu:.0f}%")  # type: ignore[attr-defined]
            self.kpi_ram._val.setText(f"{ram:.0f}%")  # type: ignore[attr-defined]
            self.bar_cpu.setValue(int(cpu))
            self.bar_ram.setValue(int(ram))
        except Exception:
            pass

    def set_net_status(self, text: str) -> None:
        text = text or "Net watch · standing by"
        self.net_line.setText(text)
        # Keep the NET KPI chip in sync (was stuck on "—")
        short = "—"
        try:
            import re

            m = re.search(r"(\d+)\s*MACs?", text, re.I)
            if m:
                short = m.group(1)
            elif re.search(r"\bOFF\b", text, re.I):
                short = "OFF"
            elif re.search(r"\bON\b", text, re.I):
                short = "ON"
        except Exception:
            short = "ON" if "ON" in text.upper() else "—"
        try:
            self.kpi_net._val.setText(short)  # type: ignore[attr-defined]
        except Exception:
            pass

    def set_clone_status(self, payload) -> None:
        """Show which voice is being impersonated + recording state."""
        if not isinstance(payload, dict):
            self.clone_line.setText(str(payload or "Clone · idle"))
            return
        active = payload.get("active") or "none"
        eng = payload.get("engine") or "auto"
        rec = " · RECORDING" if payload.get("recording") else ""
        msg = payload.get("message") or ""
        n = payload.get("count", 0)
        line = f"Clone · {active} · {eng} · {n} sample(s){rec}"
        if msg:
            line += f" · {msg}"
        self.clone_line.setText(line)
        if self.wave is not None and payload.get("recording"):
            self.wave.set_speaking(True)
        elif self.wave is not None and not payload.get("recording"):
            self.wave.set_speaking(False)

    def set_amplitude(self, amp: float) -> None:
        if self.wave is not None:
            self.wave.set_amplitude(amp)

    def set_speaking(self, on: bool) -> None:
        if self.wave is not None:
            self.wave.set_speaking(on)

    def append_log(self, line: str) -> None:
        if not line:
            return
        self.console.appendPlainText(str(line).rstrip())

    def set_lines(self, lines: list[str]) -> None:
        self.console.setPlainText("\n".join(str(x) for x in (lines or [])[-80:]))

    def scroll_console(self, steps: int = 3) -> None:
        """Gaze look-left: nudge the tools console downward."""
        bar = self.console.verticalScrollBar()
        bar.setValue(bar.value() + max(1, int(steps)) * 28)

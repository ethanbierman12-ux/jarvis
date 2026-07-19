"""Presence-loss lock countdown — fullscreen timer with tick sounds."""

from __future__ import annotations

import math
import struct
import threading
import wave
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

from jarvis.config import ASSETS_DIR

_TICK_WAV = ASSETS_DIR / "countdown_tick.wav"
_WARN_WAV = ASSETS_DIR / "countdown_warn.wav"
_START_WAV = ASSETS_DIR / "countdown_start.wav"


def _write_tone(path: Path, freq: float, dur: float, vol: float = 0.35) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 200:
        return path
    sr = 22050
    n = int(sr * dur)
    frames = bytearray()
    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.01) * max(0.0, 1.0 - t / dur)
        v = vol * env * math.sin(2 * math.pi * freq * t)
        frames += struct.pack("<h", int(max(-1.0, min(1.0, v)) * 28000))
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)
    return path


def _ensure_sfx() -> None:
    _write_tone(_TICK_WAV, 880, 0.045, 0.28)
    _write_tone(_WARN_WAV, 520, 0.12, 0.4)
    _write_tone(_START_WAV, 660, 0.22, 0.38)


def _play_wav(path: Path) -> None:
    def _run() -> None:
        try:
            import winsound

            winsound.PlaySound(
                str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
        except Exception:
            try:
                import winsound

                winsound.Beep(int(880 if "tick" in path.name else 520), 40)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="countdown-sfx").start()


class CountdownOverlay(QWidget):
    finished = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setStyleSheet("background: rgba(0,0,0,235); color:#00f0ff;")
        self._left = 0
        self._total = 35
        self._running = False

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(16)

        title = QLabel("SECURITY  ·  PRESENCE LOST")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color:#ff6b35; font-size:16px; letter-spacing:4px; font-weight:700;"
        )
        lay.addWidget(title)

        self.label = QLabel("0:35")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont("Consolas", 84, QFont.Weight.Bold))
        self.label.setStyleSheet("color:#00f0ff;")
        lay.addWidget(self.label)

        self.sub = QLabel("STEP BACK INTO FRAME TO CANCEL LOCK")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setStyleSheet("letter-spacing:3px; font-size:14px; color:#e8f4ff;")
        lay.addWidget(self.sub)

        self.hint = QLabel("Workstation locks when the timer hits zero")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("color:#4a6070; font-size:12px;")
        lay.addWidget(self.hint)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()
        try:
            _ensure_sfx()
        except Exception:
            pass

    def start(self, seconds: int = 35) -> None:
        if self._running and self.isVisible():
            return
        self._total = max(1, int(seconds))
        self._left = self._total
        self._running = True
        self._render()
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._timer.start(1000)
        try:
            _play_wav(_START_WAV)
        except Exception:
            pass

    def cancel(self) -> None:
        if not self._running and not self.isVisible():
            return
        self._timer.stop()
        was = self._running or self.isVisible()
        self._running = False
        self.hide()
        if was:
            self.cancelled.emit()

    def _render(self) -> None:
        m, s = divmod(max(0, self._left), 60)
        if m >= 60:
            h, m = divmod(m, 60)
            self.label.setText(f"{h}:{m:02d}:{s:02d}")
        else:
            self.label.setText(f"{m}:{s:02d}")
        if self._left <= 10:
            self.label.setStyleSheet("color:#ff6b35;")
            self.sub.setText("LOCKING SOON — RETURN NOW")
        elif self._left <= 20:
            self.label.setStyleSheet("color:#ffb020;")
            self.sub.setText("RETURN TO CANCEL LOCK")
        else:
            self.label.setStyleSheet("color:#00f0ff;")
            self.sub.setText("STEP BACK INTO FRAME TO CANCEL LOCK")

    def _should_beep(self) -> str | None:
        """Return which sfx to play this second, if any."""
        left = self._left
        total = self._total
        if left <= 0:
            return "warn"
        # Short countdown (≤60s): tick every second, warn in last 10
        if total <= 60:
            if left <= 10:
                return "warn"
            return "tick"
        if left <= 15:
            return "warn"
        if left <= 60:
            return "tick"
        if left in (1500, 1200, 900, 600, 300):
            return "warn"
        if left <= 300 and left % 30 == 0:
            return "tick"
        if left % 60 == 0:
            return "tick"
        return None

    def _tick(self) -> None:
        self._left -= 1
        self._render()
        kind = self._should_beep()
        if kind == "warn":
            _play_wav(_WARN_WAV)
        elif kind == "tick":
            _play_wav(_TICK_WAV)
        if self._left <= 0:
            self._timer.stop()
            self._running = False
            self.hide()
            self.finished.emit()

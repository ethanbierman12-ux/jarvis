"""Fullscreen PC power-on — PIN gate + clean AI agent greeting.

Flow: enter PIN → birth → face/codeword → unlock → Jarvis greets → HUD.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPointF,
    QRectF,
    QPropertyAnimation,
    QEasingCurve,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QRadialGradient,
    QLinearGradient,
    QGuiApplication,
    QKeyEvent,
    QImage,
)
from PyQt6.QtWidgets import QApplication, QWidget, QGraphicsOpacityEffect

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Access credentials — set via config/settings.json (pc_boot_pin / birth / codeword)
DEFAULT_PIN = ""
DEFAULT_BIRTH = "01/16/2012"


def _user_name() -> str:
    try:
        from jarvis.config import Settings

        return (Settings.load().user_name or "Sir").strip() or "Sir"
    except Exception:
        return "Sir"


def _boot_pin() -> str:
    try:
        from jarvis.config import Settings

        pin = str(getattr(Settings.load(), "pc_boot_pin", "") or "").strip()
        if len(pin) == 4 and pin.isdigit():
            return pin
    except Exception:
        pass
    # No hardcoded fallback — pin must live in settings.json
    return DEFAULT_PIN or "0000"


def _boot_birth() -> str:
    """Normalized MM/DD/YYYY birth date."""
    raw = DEFAULT_BIRTH
    try:
        from jarvis.config import Settings

        raw = str(getattr(Settings.load(), "pc_boot_birth", "") or raw).strip()
    except Exception:
        pass
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 8:
        return f"{digits[0:2]}/{digits[2:4]}/{digits[4:8]}"
    return DEFAULT_BIRTH


def _format_birth_digits(digits: str) -> str:
    """Format up to 8 digits as MM/DD/YYYY while typing."""
    d = "".join(c for c in digits if c.isdigit())[:8]
    if len(d) <= 2:
        return d
    if len(d) <= 4:
        return f"{d[0:2]}/{d[2:]}"
    return f"{d[0:2]}/{d[2:4]}/{d[4:]}"


def _time_greeting(name: str) -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return f"Good morning, {name}."
    if 12 <= hour < 17:
        return f"Good afternoon, {name}."
    if 17 <= hour < 22:
        return f"Good evening, {name}."
    return f"Welcome back, {name}."


# Phases
PIN = "pin"
BIRTH = "birth"
BIO = "bio"
INTRUSION = "intrusion"  # red alarm + 30s countdown
OWNER_LOCK = "owner_lock"  # owner identity quiz to unlock
UNLOCK = "unlock"
GREET = "greet"
FADE = "fade"


class PCPowerOn(QWidget):
    """PIN → birth → face/codeword → unlock → agent greeting → Jarvis.

    On intrusion: red alarm → 30s countdown → PC lock → owner identity quiz.
    """

    line_ready = pyqtSignal(str)
    greet_advance = pyqtSignal(int)
    greet_done = pyqtSignal()
    bio_update = pyqtSignal(object)  # BioResult on UI thread
    tracks_ready = pyqtSignal(str, str)  # wx, iss — thread-safe HUD update
    cam_open_done = pyqtSignal()  # camera ready on background thread

    FADE_MS = 220  # snappy exit — Jarvis already warming
    TICK_MS = 40  # ~25fps peak; PIN/BIRTH paint less often
    IDLE_TICK_MS = 100  # ~10fps while typing PIN / birth
    UNLOCK_SEC = 0.28  # flash unlock then go
    INTRUSION_COUNTDOWN_SEC = 30
    CAM_MS = 280  # ~3.5 fps preview — less UI-thread CV
    PREVIEW_MAX_W = 240

    def __init__(self, *, launch_jarvis: bool = True, allow_lock: bool = True) -> None:
        super().__init__()
        self._launch_jarvis = launch_jarvis
        self._allow_lock = allow_lock
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setStyleSheet("background:#03070c;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._name = _user_name()
        self._pin_ok = _boot_pin()
        self._birth_ok = _boot_birth()
        self._phase = PIN
        self._ms = 0
        self._t = 0.0
        self._ring = 0.0
        self._lips = 0.0
        self._pct = 0.0
        self._done = False
        self._pin = ""
        self._birth_digits = ""
        self._pin_error = 0.0
        self._pin_ok_flash = 0.0
        self._pin_fails = 0
        self._birth_fails = 0
        self._auth_fail_limit = 3  # wrong tries per step → intrusion
        self._unlock_ms = 0
        self._status = "STEP 1 OF 3"
        self._line = ""
        self._line_full = ""
        self._line_at = 0
        self._clock = datetime.now().strftime("%H:%M")
        self._cursor_on = True
        self._greet_started = False

        # Biometrics
        self._bio = None
        self._bio_mode = "face"  # face | code
        self._bio_status = "Face the camera"
        self._bio_score = -1.0
        self._code_buf = ""
        self._face_attempt = 0
        self._bio_busy = False
        self._preview_frame = None  # last BGR for optional paint hint

        # Intrusion lockdown
        self._intrusion_left = 0.0
        self._intrusion_flash = 0.0
        self._owner_quiz = None
        self._owner_buf = ""
        self._owner_status = ""
        self._locked_workstation = False
        self._intrusion_qimg = None  # live QImage for paint
        self._intrusion_snap_path = ""
        self._intrusion_snap_sent = False
        self._intrusion_snap_at = {0.4, 2.0, 5.0}  # seconds into countdown
        self._intrusion_snaps_done: set[float] = set()
        self._feed_mode = "day"  # day | night
        self._wx_summary = "Weather syncing…"
        self._iss_summary = "Satellite syncing…"
        self._track_busy = False
        self._track_next_at = 0.0
        self._cam_opening = False
        self._cam_tick_armed = False
        self._last_cam_ms = 0

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(1.0)
        self._fade = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._spawned = False
        self._paint_gate = 0

        self.line_ready.connect(self._on_line_ready)
        self.greet_advance.connect(self._on_greet_advance)
        self.greet_done.connect(self._on_greet_done)
        self.bio_update.connect(self._on_bio_update)
        self.tracks_ready.connect(self._on_tracks_ready)
        self.cam_open_done.connect(self._on_cam_open_done)
        self._greet_lines: list[str] = []

    def _on_tracks_ready(self, wx: str, iss: str) -> None:
        self._wx_summary = wx or self._wx_summary
        self._iss_summary = iss or self._iss_summary
        self.update()

    def _on_cam_open_done(self) -> None:
        self._cam_opening = False
        try:
            if self._bio is not None:
                frame = self._bio.grab()
                if frame is not None:
                    self._set_live_preview(frame)
                    self.update()
        except Exception:
            pass
        if not self._cam_tick_armed:
            self._cam_tick_armed = True
            QTimer.singleShot(self.CAM_MS, self._live_cam_tick)

    def start(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())
        else:
            self.showFullScreen()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._timer.start(self.IDLE_TICK_MS)
        # Bed + profile off UI thread so PIN paints immediately
        import threading

        def _boot_bg() -> None:
            try:
                from jarvis.ui.boot_sound import ensure_boot_wav, play_boot_sound

                ensure_boot_wav(force=False)
                play_boot_sound()
            except Exception:
                pass
            try:
                from jarvis.core.owner_identity import ensure_owner_profile

                ensure_owner_profile()
            except Exception:
                pass

        threading.Thread(target=_boot_bg, daemon=True, name="jarvis-boot-bg").start()
        QTimer.singleShot(
            80,
            lambda: self._speak(
                "Three step verification required.",
                show="Three-step verification required.",
                voice=False,
                instant=True,
            ),
        )
        # Weather/ISS once, off the critical PIN path (no early cam — BIO opens it)
        QTimer.singleShot(2500, self._refresh_tactical_tracks)

    def _start_live_feed(self) -> None:
        """Open cam in background — preview only runs on BIO / intrusion."""
        if self._cam_opening or self._done:
            return
        if self._bio is not None and getattr(self._bio, "_cam", None) is not None:
            self.cam_open_done.emit()
            return
        self._cam_opening = True

        def _open() -> None:
            try:
                from jarvis.core.boot_biometrics import BootBiometrics

                if self._bio is None:
                    self._bio = BootBiometrics()
                if self._bio._cam is None:
                    self._bio.open_camera()
                frame = self._bio.grab()
                if frame is not None:
                    self._preview_frame = frame
            except Exception as e:
                print(f"[boot] cam open: {e}")
            self.cam_open_done.emit()

        import threading

        threading.Thread(target=_open, daemon=True, name="jarvis-boot-cam").start()

    def _speak(
        self,
        text: str,
        *,
        show: str | None = None,
        on_done=None,
        voice: bool = True,
        instant: bool = False,
    ) -> None:
        """Show HUD line. voice=False skips Edge TTS (keeps PIN entry snappy)."""
        ui = show if show is not None else text
        if instant:
            self._line_full = ui
            self._line = ui
            self._line_at = self._ms
            self.update()
        else:

            def _ui() -> None:
                self.line_ready.emit(ui)

            QTimer.singleShot(0, _ui)
        if not voice:
            if callable(on_done):
                try:
                    on_done()
                except Exception:
                    pass
            return
        try:
            from jarvis.ui.boot_sound import speak_boot_line

            speak_boot_line(text, on_done=on_done)
        except Exception:
            if callable(on_done):
                on_done()
        self._lips = 1.0

    def _on_line_ready(self, text: str) -> None:
        self._line_full = text
        self._line = ""
        self._line_at = self._ms

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if self._phase == INTRUSION:
            # No input during countdown — force step-away
            return
        if self._phase == OWNER_LOCK:
            self._handle_owner_keys(key, event)
            return
        if self._phase == PIN:
            self._handle_pin_keys(key, event)
            return
        if self._phase == BIRTH:
            self._handle_birth_keys(key, event)
            return
        if self._phase == BIO and self._bio_mode == "code":
            self._handle_code_keys(key, event)
            return

        if key == Qt.Key.Key_Escape and self._phase in (UNLOCK, GREET):
            self._skip_to_end()
        else:
            super().keyPressEvent(event)

    def _handle_pin_keys(self, key: int, event: QKeyEvent) -> None:
        if key == Qt.Key.Key_Escape:
            self._pin = ""
            self.update()
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._pin = self._pin[:-1]
            self.update()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._try_pin()
            return
        text = event.text()
        if text.isdigit() and len(self._pin) < 4:
            self._pin += text
            try:
                from jarvis.ui.hud_sfx import play_click

                play_click()
            except Exception:
                pass
            if len(self._pin) == 4:
                QTimer.singleShot(120, self._try_pin)
            self.update()

    def _handle_birth_keys(self, key: int, event: QKeyEvent) -> None:
        if key == Qt.Key.Key_Escape:
            self._birth_digits = ""
            self.update()
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._birth_digits = self._birth_digits[:-1]
            self.update()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._try_birth()
            return
        text = event.text()
        if text.isdigit() and len(self._birth_digits) < 8:
            self._birth_digits += text
            try:
                from jarvis.ui.hud_sfx import play_click

                play_click()
            except Exception:
                pass
            if len(self._birth_digits) == 8:
                QTimer.singleShot(140, self._try_birth)
            self.update()

    def _try_pin(self) -> None:
        if self._phase != PIN:
            return
        if self._pin == self._pin_ok:
            self._pin_ok_flash = 1.0
            self._phase = BIRTH
            self._status = "STEP 2 OF 3"
            self._line_full = ""
            self._line = ""
            self._birth_digits = ""
            try:
                from jarvis.ui.hud_sfx import play_confirm

                play_confirm()
            except Exception:
                pass
            self._speak(
                "PIN accepted. Enter your date of birth.",
                show="PIN accepted. Enter date of birth.",
            )
            self._timer.setInterval(self.IDLE_TICK_MS)
        else:
            self._pin = ""
            self._pin_error = 1.0
            self._pin_fails += 1
            left = max(0, self._auth_fail_limit - self._pin_fails)
            self._status = "DENIED"
            try:
                from jarvis.ui.hud_sfx import play as play_sfx

                play_sfx("error")
            except Exception:
                pass
            if self._pin_fails >= self._auth_fail_limit:
                self._speak(
                    "Too many incorrect PINs. Starting lockdown.",
                    show="Too many incorrect PINs — LOCKDOWN",
                    voice=True,
                    instant=True,
                )
                self._start_intrusion()
                return
            self._speak(
                f"Access denied. {left} tries left.",
                show=f"Access denied · {left} tries left",
                voice=False,
                instant=True,
            )
            QTimer.singleShot(450, lambda: setattr(self, "_status", "STEP 1 OF 3"))
        self.update()

    def _handle_code_keys(self, key: int, event: QKeyEvent) -> None:
        if key == Qt.Key.Key_Escape:
            self._code_buf = ""
            self.update()
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._code_buf = self._code_buf[:-1]
            self.update()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._submit_codeword()
            return
        ch = event.text()
        if ch and ch.isprintable() and len(self._code_buf) < 24:
            self._code_buf += ch
            self.update()

    def _try_birth(self) -> None:
        if self._phase != BIRTH:
            return
        entered = _format_birth_digits(self._birth_digits)
        if entered == self._birth_ok and len(self._birth_digits) == 8:
            self._pin_ok_flash = 1.0
            self._phase = BIO
            self._status = "STEP 3 OF 3"
            self._bio_mode = "face"
            self._bio_status = "Looking for your face…"
            self._face_attempt = 0
            self._line_full = ""
            self._line = ""
            try:
                from jarvis.ui.hud_sfx import play_confirm

                play_confirm()
            except Exception:
                pass
            self._speak(
                "Date confirmed. Face the camera for biometric check.",
                show="Date confirmed. Face the camera.",
            )
            self._timer.setInterval(self.TICK_MS)
            self._start_live_feed()
            if not self._cam_tick_armed:
                self._cam_tick_armed = True
                QTimer.singleShot(self.CAM_MS, self._live_cam_tick)
            QTimer.singleShot(280, self._start_biometrics)
        else:
            self._birth_digits = ""
            self._pin_error = 1.0
            self._birth_fails += 1
            left = max(0, self._auth_fail_limit - self._birth_fails)
            self._status = "DENIED"
            try:
                from jarvis.ui.hud_sfx import play as play_sfx

                play_sfx("error")
            except Exception:
                pass
            if self._birth_fails >= self._auth_fail_limit:
                self._speak(
                    "Too many incorrect birth dates. Starting lockdown.",
                    show="Too many incorrect dates — LOCKDOWN",
                    voice=True,
                    instant=True,
                )
                self._start_intrusion()
                return
            self._speak(
                f"Date of birth incorrect. {left} tries left.",
                show=f"Date incorrect · {left} tries left",
                voice=False,
                instant=True,
            )
            QTimer.singleShot(450, lambda: setattr(self, "_status", "STEP 2 OF 3"))
        self.update()

    def _start_biometrics(self) -> None:
        if self._phase != BIO:
            return
        try:
            from jarvis.core.boot_biometrics import BootBiometrics

            if self._bio is None:
                self._bio = BootBiometrics()
            # Never open camera on the UI thread — wait for background open
            frame = None
            try:
                frame = self._bio.grab()
            except Exception:
                frame = None
            if frame is None:
                if self._cam_opening or getattr(self._bio, "_cam", None) is None:
                    self._start_live_feed()
                    self._bio_status = "Opening camera…"
                    QTimer.singleShot(220, self._start_biometrics)
                    return
                self._enter_codeword_mode(
                    "Camera unavailable. Type your code word."
                )
                return
            if not self._bio.enrolled:
                self._bio_status = "First-time enroll — hold still"
                self._speak(
                    "No face on file. Hold still while I enroll you as owner.",
                    show="Enrolling owner face…",
                )
            else:
                self._bio_status = "Scanning face and eyes…"
            QTimer.singleShot(200, self._bio_face_tick)
        except Exception as e:
            print(f"[boot] bio init: {e}")
            self._enter_codeword_mode(
                "Biometrics offline. Type your code word."
            )

    def _bio_face_tick(self) -> None:
        if self._phase != BIO or self._bio_mode != "face" or self._bio is None:
            return
        if self._bio_busy:
            return
        self._bio_busy = True

        def _work() -> None:
            try:
                best = None
                for _ in range(2):
                    r = self._bio.verify_once()
                    frame = self._bio.grab()
                    if frame is not None:
                        self._preview_frame = frame
                    if r.ok:
                        best = r
                        break
                    best = r
                    time.sleep(0.08)
                self.bio_update.emit(best)
            except Exception as e:
                from jarvis.core.boot_biometrics import BioResult

                self.bio_update.emit(
                    BioResult(False, "failed", f"Scan error: {e}", should_lock=False)
                )

        import threading

        threading.Thread(target=_work, daemon=True, name="boot-bio-scan").start()

    def _on_bio_update(self, result) -> None:
        self._bio_busy = False
        if self._phase != BIO:
            return
        self._bio_score = float(getattr(result, "score", -1) or -1)
        self._bio_status = str(getattr(result, "message", "") or "")
        if result.ok:
            self._pin_ok_flash = 1.0
            try:
                from jarvis.ui.hud_sfx import play_confirm

                play_confirm()
            except Exception:
                pass
            self._speak(result.message, show=result.message)
            self._finish_bio_ok()
            return

        self._face_attempt += 1
        if self._face_attempt < 3 and "no face" in (result.message or "").lower():
            self._bio_status = f"No face yet · try {self._face_attempt}/3"
            QTimer.singleShot(650, self._bio_face_tick)
            self.update()
            return

        self._enter_codeword_mode(result.message)
        self.update()

    def _enter_codeword_mode(self, reason: str) -> None:
        self._bio_mode = "code"
        self._code_buf = ""
        self._status = "CODE WORD"
        self._bio_status = reason or "Type your code word"
        self._speak(
            "Biometrics unsure. Type your code word.",
            show="Type your code word, then Enter.",
        )
        self.update()

    def _submit_codeword(self) -> None:
        if self._phase != BIO or self._bio_mode != "code":
            return
        if self._bio is None:
            try:
                from jarvis.core.boot_biometrics import BootBiometrics

                self._bio = BootBiometrics()
            except Exception:
                return
        result = self._bio.check_codeword(self._code_buf)
        self._code_buf = ""
        self._bio_status = result.message
        if result.ok:
            self._pin_ok_flash = 1.0
            try:
                from jarvis.ui.hud_sfx import play_confirm

                play_confirm()
            except Exception:
                pass
            self._speak(result.message, show=result.message)
            self._finish_bio_ok()
            return
        try:
            from jarvis.ui.hud_sfx import play as play_sfx

            play_sfx("error")
        except Exception:
            pass
        self._pin_error = 1.0
        self._speak(
            result.message,
            show=result.message,
            voice=bool(result.should_lock),
            instant=True,
        )
        if result.should_lock:
            # Honor settings.pc_boot_lock_on_fail (default True)
            try:
                from jarvis.config import Settings

                if not bool(getattr(Settings.load(), "pc_boot_lock_on_fail", True)):
                    self._allow_lock = False
            except Exception:
                pass
            self._start_intrusion()
            return
        self.update()

    def _start_intrusion(self) -> None:
        """Red alarm → ntfy owner → camera + snaps → 30s countdown → lock → quiz."""
        self._phase = INTRUSION
        self._status = "INTRUSION"
        self._bio_mode = "intrusion"
        self._intrusion_left = float(self.INTRUSION_COUNTDOWN_SEC)
        self._intrusion_flash = 1.0
        self._owner_buf = ""
        self._line_full = ""
        self._line = ""
        self._intrusion_snap_path = ""
        self._intrusion_snap_sent = False
        self._intrusion_snaps_done = set()
        self._intrusion_qimg = None
        # Keep / open camera to show and photograph the intruder
        self._ensure_surveillance_cam()
        try:
            from jarvis.ui.hud_sfx import play as play_sfx

            play_sfx("error")
        except Exception:
            pass
        # Text alert immediately when Jarvis says alerting owner
        try:
            from jarvis.core.owner_identity import notify_intrusion

            notify_intrusion(preview=not self._allow_lock)
        except Exception as e:
            print(f"[boot] intrusion notify: {e}")
        self._speak(
            "Step away now. Alerting owner!",
            show="STEP AWAY NOW — ALERTING OWNER",
        )
        # Grab first frames + snapshot shortly after cam opens
        QTimer.singleShot(350, self._live_cam_tick)
        QTimer.singleShot(500, self._capture_intruder_snap)
        QTimer.singleShot(200, self._refresh_tactical_tracks)
        self.update()

    def _refresh_tactical_tracks(self) -> None:
        """Pull live weather + ISS for verify steps and lockdown."""
        live = (PIN, BIRTH, BIO, INTRUSION, OWNER_LOCK)
        if self._phase not in live or self._track_busy:
            return
        self._track_busy = True

        def _work() -> None:
            wx_s = "Weather offline"
            iss_s = "Satellite offline"
            try:
                from jarvis.config import Settings
                from jarvis.core.satellite_track import (
                    fetch_iss,
                    fetch_weather_brief,
                )

                city = getattr(Settings.load(), "city", "") or "Philadelphia"
                wx = fetch_weather_brief(city)
                wx_s = wx.get("summary") or wx_s
                iss = fetch_iss()
                iss_s = iss.get("summary") or iss_s
            except Exception as e:
                print(f"[boot] tracks: {e}")
                if not wx_s or "failed" in wx_s.lower() or "error" in wx_s.lower():
                    wx_s = "Weather standing by"
                if not iss_s or "failed" in iss_s.lower() or "error" in iss_s.lower():
                    iss_s = "ISS track standing by"
            self._wx_summary = wx_s
            self._iss_summary = iss_s
            self._track_busy = False
            self._track_next_at = time.time() + 45.0
            self.tracks_ready.emit(wx_s, iss_s)

        import threading

        threading.Thread(target=_work, daemon=True, name="jarvis-tactical").start()

    def _ensure_surveillance_cam(self) -> None:
        """Open cam off UI thread during intrusion / lockdown."""
        self._start_live_feed()
        if not self._cam_tick_armed:
            self._cam_tick_armed = True
            QTimer.singleShot(self.CAM_MS, self._live_cam_tick)

    def _set_live_preview(self, frame) -> None:
        """Convert BGR frame to QImage — downscaled for HUD performance."""
        try:
            import cv2
            import numpy as np

            if frame is None:
                return
            h, w = frame.shape[:2]
            if w > self.PREVIEW_MAX_W:
                scale = self.PREVIEW_MAX_W / w
                frame = cv2.resize(
                    frame,
                    (self.PREVIEW_MAX_W, int(h * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb = np.ascontiguousarray(rgb)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
            self._intrusion_qimg = qimg
            self._preview_frame = frame
        except Exception:
            pass

    _set_intrusion_preview = _set_live_preview  # alias

    def _live_cam_tick(self) -> None:
        # Skip heavy CV during PIN/BIRTH typing — cam only for bio + lockdown
        live = (BIO, INTRUSION, OWNER_LOCK)
        if self._phase not in live or self._done:
            self._cam_tick_armed = False
            return
        try:
            if self._bio is not None:
                frame = self._bio.grab()
                if frame is not None:
                    self._set_live_preview(frame)
                    self._feed_mode = getattr(self._bio, "feed_mode", "day") or "day"
                    self._last_cam_ms = self._ms
                    self.update()
        except Exception:
            pass
        if self._phase in live and not self._done:
            QTimer.singleShot(self.CAM_MS, self._live_cam_tick)

    _intrusion_cam_tick = _live_cam_tick  # alias

    def _capture_intruder_snap(self) -> None:
        """Save intruder JPEG + push photo to ntfy."""
        if self._phase not in (INTRUSION, OWNER_LOCK):
            return
        frame = self._preview_frame
        try:
            if self._bio is not None:
                frame = self._bio.grab() or frame
        except Exception:
            pass
        if frame is None:
            return
        try:
            import cv2
            from jarvis.config import DATA_DIR

            out_dir = DATA_DIR / "intrusions"
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = out_dir / f"intruder_{stamp}.jpg"
            # Stamp REC overlay on saved image
            shot = frame.copy()
            cv2.putText(
                shot,
                "JARVIS INTRUDER CAM",
                (16, 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (40, 40, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                shot,
                stamp,
                (16, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (200, 200, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imwrite(str(path), shot, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            self._intrusion_snap_path = str(path)
            self._set_live_preview(frame)
            print(f"[intrusion] snapshot saved: {path}")
            # Only the first clear snap is pushed to ntfy
            if not self._intrusion_snap_sent:
                self._intrusion_snap_sent = True
                from jarvis.core.owner_identity import notify_intrusion

                notify_intrusion(
                    preview=not self._allow_lock,
                    image_path=str(path),
                )
        except Exception as e:
            print(f"[intrusion] snapshot failed: {e}")

    def _finish_intrusion_countdown(self) -> None:
        if self._phase != INTRUSION:
            return
        if self._allow_lock and not self._locked_workstation:
            try:
                import ctypes

                ctypes.windll.user32.LockWorkStation()
                self._locked_workstation = True
            except Exception as e:
                print(f"[boot] LockWorkStation: {e}")
        self._phase = OWNER_LOCK
        self._status = "OWNER LOCK"
        self._launch_jarvis = False
        try:
            from jarvis.core.owner_identity import build_owner_quiz

            self._owner_quiz = build_owner_quiz(count=3)
        except Exception as e:
            print(f"[boot] owner quiz: {e}")
            self._owner_quiz = None
        q = self._owner_quiz.current if self._owner_quiz else None
        self._owner_status = q.prompt if q else "Owner verification required"
        self._owner_buf = ""
        self._speak(
            "Workstation locked. Only the owner can unlock. Prove your identity.",
            show=self._owner_status,
        )
        self.update()

    def _handle_owner_keys(self, key: int, event: QKeyEvent) -> None:
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._owner_buf = self._owner_buf[:-1]
            self.update()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._try_owner_answer()
            return
        if key == Qt.Key.Key_Escape:
            self._owner_buf = ""
            self.update()
            return
        text = event.text()
        if text and text.isprintable() and len(self._owner_buf) < 64:
            self._owner_buf += text
            try:
                from jarvis.ui.hud_sfx import play_click

                play_click()
            except Exception:
                pass
            self.update()

    def _try_owner_answer(self) -> None:
        if self._phase != OWNER_LOCK or self._owner_quiz is None:
            return
        q = self._owner_quiz.current
        if q is None:
            return
        from jarvis.core.owner_identity import check_answer

        ok = check_answer(q.key, self._owner_buf)
        self._owner_buf = ""
        if ok:
            self._owner_quiz.index += 1
            self._pin_ok_flash = 1.0
            try:
                from jarvis.ui.hud_sfx import play_confirm

                play_confirm()
            except Exception:
                pass
            if self._owner_quiz.done:
                self._owner_unlock_ok()
                return
            nq = self._owner_quiz.current
            self._owner_status = nq.prompt if nq else ""
            self._speak(
                "Correct. Next question.",
                show=self._owner_status,
            )
        else:
            self._owner_quiz.fails += 1
            self._pin_error = 1.0
            try:
                from jarvis.ui.hud_sfx import play as play_sfx

                play_sfx("error")
            except Exception:
                pass
            self._owner_status = f"{q.prompt} — try again"
            self._speak("Incorrect. Try again.", show=self._owner_status)
            # Re-alert owner after repeated wrong answers
            if self._owner_quiz.fails in (3, 6):
                try:
                    from jarvis.core.owner_identity import notify_intrusion

                    notify_intrusion(preview=not self._allow_lock)
                except Exception:
                    pass
        self.update()

    def _owner_unlock_ok(self) -> None:
        self._pin_ok_flash = 1.0
        try:
            if self._bio is not None:
                self._bio.close()
        except Exception:
            pass
        try:
            stamp = ROOT / "jarvis" / "data" / "last_secure_unlock"
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(str(time.time()), encoding="utf-8")
        except Exception:
            pass
        self._speak(
            f"Owner confirmed. Welcome back, {self._name}.",
            show="Owner verified — unlocking.",
        )
        # Resume normal boot path for the real owner
        self._launch_jarvis = True
        self._phase = UNLOCK
        self._unlock_ms = 0
        self._status = "VERIFIED"
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._timer.setInterval(self.TICK_MS)
        self._spawn_jarvis_once()
        self.update()

    def _finish_bio_ok(self) -> None:
        try:
            if self._bio is not None:
                self._bio.close()
        except Exception:
            pass
        try:
            stamp = ROOT / "jarvis" / "data" / "last_secure_unlock"
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(str(time.time()), encoding="utf-8")
        except Exception:
            pass
        self._launch_jarvis = True
        self._phase = UNLOCK
        self._unlock_ms = 0
        self._status = "VERIFIED"
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._timer.setInterval(self.TICK_MS)
        # Fire-and-forget — do not gate launch on TTS
        self._speak(
            "Identity verified. System booting.",
            show="Identity verified. System booting.",
        )
        # Warm Jarvis during unlock flash so HUD is ready when fade ends
        self._spawn_jarvis_once()
        self.update()

    def _lock_and_exit(self) -> None:
        try:
            if self._bio is not None:
                self._bio.lock_workstation()
                self._bio.close()
        except Exception:
            pass
        self._done = True
        self._launch_jarvis = False
        self._fade_out()

    def _skip_to_end(self) -> None:
        if self._done:
            return
        try:
            from jarvis.ui.boot_sound import speak_boot_clear

            speak_boot_clear()
        except Exception:
            pass
        try:
            if self._bio is not None:
                self._bio.close()
        except Exception:
            pass
        self._done = True
        self._fade_out()

    def _start_greet(self) -> None:
        """Fast path: skip multi-line TTS gate — fade + launch immediately."""
        if self._greet_started:
            return
        self._greet_started = True
        self._phase = GREET
        self._status = "AGENT ONLINE"
        welcome = _time_greeting(self._name)
        self._speak(f"{welcome} Systems online.", show=f"{welcome} Systems online.")
        self._done = True
        QTimer.singleShot(40, self._fade_out)

    def _on_greet_advance(self, i: int) -> None:
        if self._done or self._phase == FADE:
            return
        if i >= len(self._greet_lines):
            QTimer.singleShot(40, lambda: self.greet_done.emit())
            return
        text = self._greet_lines[i]

        def _next() -> None:
            self.greet_advance.emit(i + 1)

        self._speak(text, show=text, on_done=_next)

    def _on_greet_done(self) -> None:
        if not self._done:
            self._done = True
            self._fade_out()

    def _tick(self) -> None:
        tick = max(1, self._timer.interval())
        self._ms += tick
        self._t += 0.04 * (tick / 40.0)
        self._ring += 0.022 + (0.04 * self._lips)
        self._cursor_on = (int(self._t * 3.2) % 2) == 0
        speaking = False
        try:
            from jarvis.ui.boot_sound import is_boot_speaking

            speaking = is_boot_speaking()
        except Exception:
            speaking = self._lips > 0.05
        if speaking:
            self._lips = min(1.0, self._lips + 0.08)
        else:
            self._lips = max(0.0, self._lips - 0.025)
        if self._pin_error > 0:
            self._pin_error = max(0.0, self._pin_error - 0.035)
        if self._pin_ok_flash > 0:
            self._pin_ok_flash = max(0.0, self._pin_ok_flash - 0.018)
        if self._intrusion_flash > 0:
            self._intrusion_flash = min(1.0, self._intrusion_flash)

        if self._line_full:
            # Snappier typewriter (~72 cps); denials already set instant full line
            n = int((self._ms - self._line_at) / 1000.0 * 72)
            self._line = self._line_full[: min(len(self._line_full), max(0, n))]

        if self._phase == INTRUSION:
            self._intrusion_left = max(0.0, self._intrusion_left - tick / 1000.0)
            elapsed = float(self.INTRUSION_COUNTDOWN_SEC) - self._intrusion_left
            self._pct = 100.0 * (
                1.0 - self._intrusion_left / float(self.INTRUSION_COUNTDOWN_SEC)
            )
            for mark in list(self._intrusion_snap_at):
                if elapsed >= mark and mark not in self._intrusion_snaps_done:
                    self._intrusion_snaps_done.add(mark)
                    self._capture_intruder_snap()
            if time.time() >= self._track_next_at:
                self._refresh_tactical_tracks()
            if self._intrusion_left <= 0:
                self._finish_intrusion_countdown()
        elif self._phase == OWNER_LOCK:
            self._pct = 100.0
            if time.time() >= self._track_next_at:
                self._refresh_tactical_tracks()
        elif self._phase == UNLOCK:
            self._unlock_ms += tick
            u = min(1.0, self._unlock_ms / (self.UNLOCK_SEC * 1000))
            s = u * u * (3 - 2 * u)
            self._pct = 30 + s * 45
            if self._unlock_ms >= int(self.UNLOCK_SEC * 1000):
                self._start_greet()
        elif self._phase == GREET:
            self._pct = min(100.0, self._pct + 0.12)
        elif self._phase == PIN:
            self._pct = min(8.0, self._ms / 900.0)
        elif self._phase == BIRTH:
            self._pct = min(22.0, 10.0 + len(self._birth_digits) * 1.5)
        elif self._phase == BIO:
            self._pct = min(55.0, 28.0 + self._face_attempt * 6)

        feedback = (
            self._lips > 0.05
            or self._pin_error > 0
            or self._pin_ok_flash > 0
            or (self._line_full and len(self._line) < len(self._line_full))
        )
        hot = self._phase in (INTRUSION, OWNER_LOCK, UNLOCK, GREET, FADE, BIO)
        if hot or feedback:
            self.update()
        elif self._phase in (PIN, BIRTH):
            gate = self._ms // 120
            if gate != self._paint_gate:
                self._paint_gate = gate
                self.update()

        if self._phase in (BIO,) and time.time() >= self._track_next_at:
            self._refresh_tactical_tracks()

    def _fade_out(self) -> None:
        self._phase = FADE
        self._timer.stop()
        self._spawn_jarvis_once()
        try:
            from jarvis.ui.boot_sound import stop_boot_sound

            stop_boot_sound()
        except Exception:
            pass
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(self.FADE_MS)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.finished.connect(self._complete)
        anim.start()
        self._fade = anim

    def _complete(self) -> None:
        self.hide()
        if not self._launch_jarvis:
            QApplication.instance().quit()
            return
        self._spawn_jarvis_once()
        QApplication.instance().quit()

    def _spawn_jarvis_once(self) -> None:
        if self._spawned or not self._launch_jarvis:
            return
        self._spawned = True
        self._spawn_jarvis()

    def _spawn_jarvis(self) -> None:
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        pyw = local / "Programs/Python/Python313/pythonw.exe"
        py = local / "Programs/Python/Python313/python.exe"
        launcher = str(pyw if pyw.exists() else py if py.exists() else sys.executable)
        runner = ROOT / "runner.py"
        target = runner if runner.exists() else ROOT / "main.py"
        env = os.environ.copy()
        env["JARVIS_FROM_SECURE_BOOT"] = "1"
        env["JARVIS_FAST_BOOT"] = "1"
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [launcher, str(target)],
                cwd=str(ROOT),
                creationflags=flags,
                env=env,
            )
            print(f"[pc-boot] launched Jarvis via {target.name}")
        except Exception as e:
            print(f"[pc-boot] launch jarvis: {e}")

    # ── paint ───────────────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        cx = w / 2.0
        ease = min(1.0, self._ms / 380.0)
        # Layout zones — never stack PIN and speech
        holo_cy = h * 0.28
        brand_y = holo_cy + min(w, h) * 0.095
        pin_cy = h * 0.64
        speech_cy = h * 0.58
        prog_cy = h * 0.70

        breath = 1.0 + 0.03 * math.sin(self._t * 0.9)
        speak_pulse = 0.55 + 0.45 * self._lips * abs(math.sin(self._t * 6.5))

        p.fillRect(self.rect(), QColor(2, 6, 12))
        if self._phase in (INTRUSION, OWNER_LOCK):
            # Full red lockdown field
            pulse = 0.55 + 0.45 * abs(math.sin(self._t * 3.2))
            p.fillRect(self.rect(), QColor(48, 0, 0))
            vig = QRadialGradient(cx, holo_cy, min(w, h) * 0.85)
            vig.setColorAt(0.0, QColor(140, 10, 10, 255))
            vig.setColorAt(0.45, QColor(70, 0, 0, 255))
            vig.setColorAt(1.0, QColor(10, 0, 0, 255))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(vig))
            p.drawRect(self.rect())
            # Strobe edges
            edge_a = int(90 + 120 * pulse)
            p.setPen(QPen(QColor(255, 40, 40, edge_a), 6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(8, 8, w - 16, h - 16))
            self._paint_intrusion(p, cx, holo_cy, pin_cy, speech_cy, ease, pulse)
            self._meta(p, w, h, ease)
            p.end()
            return

        vig = QRadialGradient(cx, holo_cy, min(w, h) * 0.75)
        vig.setColorAt(0.0, QColor(6, 20, 32, 255))
        vig.setColorAt(0.5, QColor(2, 8, 14, 255))
        vig.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(vig))
        p.drawRect(self.rect())

        # Soft floor haze
        floor = QLinearGradient(0, h * 0.72, 0, h)
        floor.setColorAt(0.0, QColor(0, 0, 0, 0))
        floor.setColorAt(1.0, QColor(0, 40, 55, int(40 * ease)))
        p.setBrush(QBrush(floor))
        p.drawRect(QRectF(0, h * 0.72, w, h * 0.28))

        self._corners(p, w, h, ease)
        self._hologram(p, cx, holo_cy, ease, breath, speak_pulse)
        self._brand(p, cx, brand_y, ease)

        if self._phase == PIN:
            self._paint_pin(p, cx, pin_cy, ease)
        elif self._phase == BIRTH:
            self._paint_birth(p, cx, pin_cy, ease)
        elif self._phase == BIO:
            self._paint_bio(p, cx, pin_cy, ease)
        else:
            if self._phase == UNLOCK:
                self._unlock_ring(p, cx, holo_cy, ease)
            self._message(p, cx, speech_cy, ease)
            self._progress(p, cx, prog_cy, ease)

        if self._phase in (PIN, BIRTH, BIO):
            self._paint_verify_tactical(p, w, h, ease)

        self._meta(p, w, h, ease)
        p.end()

    def _paint_verify_tactical(self, p: QPainter, w: int, h: int, ease: float) -> None:
        """Live cam + weather + satellite on PIN / birth / bio steps."""
        cam_w = min(260, int(w * 0.22))
        cam_h = int(cam_w * 0.72)
        x = w - cam_w - 36
        y = h * 0.14
        pulse = 0.55 + 0.45 * abs(math.sin(self._t * 2.4))

        p.setPen(QPen(QColor(0, 210, 230, int(130 * ease)), 1.6))
        p.setBrush(QColor(4, 14, 24, int(210 * ease)))
        p.drawRoundedRect(QRectF(x, y, cam_w, cam_h), 8, 8)

        if self._intrusion_qimg is not None and not self._intrusion_qimg.isNull():
            img = self._intrusion_qimg
            iw, ih = img.width(), img.height()
            if iw > 0 and ih > 0:
                scale = min((cam_w - 10) / iw, (cam_h - 10) / ih)
                dw, dh = int(iw * scale), int(ih * scale)
                p.drawImage(
                    QRectF(x + (cam_w - dw) / 2, y + (cam_h - dh) / 2, dw, dh),
                    img,
                )
        else:
            p.setFont(QFont("Cascadia Mono", 9))
            p.setPen(QColor(80, 140, 160, int(160 * ease)))
            p.drawText(int(x + 52), int(y + cam_h / 2), "OPTICS WARMING")

        night = self._feed_mode == "night"
        mode = "NIGHT VISION" if night else "DAY FEED"
        mode_col = (
            QColor(57, 255, 122, int(220 * ease))
            if night
            else QColor(0, 230, 255, int(220 * ease))
        )
        p.setFont(QFont("Cascadia Mono", 9, QFont.Weight.Bold))
        p.setPen(mode_col)
        p.drawText(int(x + 10), int(y + 16), mode)
        if night and (int(self._t * 2) % 2) == 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(57, 255, 122, int(180 * pulse * ease)))
            p.drawEllipse(QPointF(x + cam_w - 14, y + 12), 4, 4)

        p.setFont(QFont("Cascadia Mono", 8, QFont.Weight.Bold))
        p.setPen(QColor(0, 200, 220, int(180 * ease)))
        p.drawText(int(x + 10), int(y + cam_h - 10), "LIVE FEED")

        p.setFont(QFont("Cascadia Mono", 8))
        p.setPen(QColor(255, 190, 140, int(190 * ease)))
        p.drawText(int(x), int(y + cam_h + 14), f"WX  {(self._wx_summary or '')[:52]}")
        p.setPen(QColor(140, 200, 255, int(190 * ease)))
        p.drawText(int(x), int(y + cam_h + 30), f"SAT {(self._iss_summary or '')[:52]}")

    def _paint_intrusion(
        self,
        p: QPainter,
        cx: float,
        holo_cy: float,
        pin_cy: float,
        speech_cy: float,
        ease: float,
        pulse: float,
    ) -> None:
        w, h = self.width(), self.height()

        # Header
        p.setFont(QFont("Bahnschrift", 14, QFont.Weight.Bold))
        p.setPen(QColor(255, 200, 200, int(220 * ease)))
        title = "SECURITY BREACH"
        tw = p.fontMetrics().horizontalAdvance(title)
        p.drawText(int(cx - tw / 2), int(h * 0.08), title)

        p.setFont(QFont("Bahnschrift", 26, QFont.Weight.Bold))
        p.setPen(QColor(255, 240, 240, int(250 * ease)))
        warn = "STEP AWAY"
        ww = p.fontMetrics().horizontalAdvance(warn)
        p.drawText(int(cx - ww / 2), int(h * 0.125), warn)

        # Live intruder camera panel
        cam_w = min(520, int(w * 0.46))
        cam_h = int(cam_w * 0.72)
        cam_x = cx - cam_w / 2
        cam_y = h * 0.16
        border = QColor(255, 50, 50, int((160 + 80 * pulse) * ease))
        p.setPen(QPen(border, 3))
        p.setBrush(QColor(20, 0, 0, int(230 * ease)))
        p.drawRoundedRect(QRectF(cam_x, cam_y, cam_w, cam_h), 10, 10)

        if self._intrusion_qimg is not None and not self._intrusion_qimg.isNull():
            # Letterbox the frame inside the panel
            img = self._intrusion_qimg
            iw, ih = img.width(), img.height()
            if iw > 0 and ih > 0:
                scale = min((cam_w - 12) / iw, (cam_h - 12) / ih)
                dw, dh = int(iw * scale), int(ih * scale)
                dx = int(cam_x + (cam_w - dw) / 2)
                dy = int(cam_y + (cam_h - dh) / 2)
                p.drawImage(QRectF(dx, dy, dw, dh), img)
        else:
            p.setFont(QFont("Segoe UI", 12))
            p.setPen(QColor(180, 80, 80, int(200 * ease)))
            miss = "CAMERA OFFLINE"
            mw = p.fontMetrics().horizontalAdvance(miss)
            p.drawText(int(cx - mw / 2), int(cam_y + cam_h / 2), miss)

        # REC + day/night feed badge
        rec_on = (int(self._t * 2) % 2) == 0
        if rec_on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 30, 30, int(230 * ease)))
            p.drawEllipse(QPointF(cam_x + 22, cam_y + 22), 7, 7)
        p.setFont(QFont("Cascadia Mono", 10, QFont.Weight.Bold))
        p.setPen(QColor(255, 80, 80, int(230 * ease)))
        p.drawText(int(cam_x + 36), int(cam_y + 28), "REC  INTRUDER CAM")

        night = self._feed_mode == "night"
        mode_label = "NIGHT VISION" if night else "DAY FEED"
        mode_col = (
            QColor(80, 255, 120, int(220 * ease))
            if night
            else QColor(120, 220, 255, int(220 * ease))
        )
        p.setFont(QFont("Cascadia Mono", 11, QFont.Weight.Bold))
        p.setPen(mode_col)
        mw_mode = p.fontMetrics().horizontalAdvance(mode_label)
        p.drawText(int(cam_x + cam_w - mw_mode - 16), int(cam_y + 28), mode_label)

        # Weather + satellite strips
        p.setFont(QFont("Cascadia Mono", 9))
        p.setPen(QColor(255, 190, 160, int(200 * ease)))
        wx_line = f"WX  {self._wx_summary}"
        p.drawText(int(cam_x), int(cam_y + cam_h + 16), wx_line[:78])
        p.setPen(QColor(160, 210, 255, int(200 * ease)))
        sat_line = f"SAT {self._iss_summary}"
        p.drawText(int(cam_x), int(cam_y + cam_h + 34), sat_line[:78])

        if self._intrusion_snap_path:
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor(255, 180, 180, int(180 * ease)))
            snap_tip = "Snapshot saved + sent to owner"
            sw = p.fontMetrics().horizontalAdvance(snap_tip)
            p.drawText(int(cx - sw / 2), int(cam_y + cam_h + 54), snap_tip)

        if self._phase == INTRUSION:
            secs = max(0, int(math.ceil(self._intrusion_left)))
            p.setFont(QFont("Cascadia Mono", 56, QFont.Weight.Bold))
            p.setPen(QColor(255, 60, 60, int((180 + 75 * pulse) * ease)))
            cd = f"{secs:02d}"
            cw = p.fontMetrics().horizontalAdvance(cd)
            p.drawText(int(cx - cw / 2), int(cam_y + cam_h + 120), cd)
            p.setFont(QFont("Segoe UI", 11))
            p.setPen(QColor(255, 180, 180, int(190 * ease)))
            tip = "Locking in… leave the area"
            tw2 = p.fontMetrics().horizontalAdvance(tip)
            p.drawText(int(cx - tw2 / 2), int(cam_y + cam_h + 152), tip)
        else:
            # Owner recovery quiz under cam
            py = cam_y + cam_h + 70
            p.setFont(QFont("Bahnschrift", 14, QFont.Weight.Bold))
            p.setPen(QColor(255, 220, 220, int(240 * ease)))
            head = "OWNER UNLOCK REQUIRED"
            hw = p.fontMetrics().horizontalAdvance(head)
            p.drawText(int(cx - hw / 2), int(py), head)

            p.setFont(QFont("Segoe UI", 11))
            p.setPen(QColor(255, 190, 190, int(220 * ease)))
            prompt = self._owner_status or "Prove you are the owner"
            pw = p.fontMetrics().horizontalAdvance(prompt)
            p.drawText(int(cx - pw / 2), int(py + 28), prompt)

            field_w, field_h = 360, 48
            fx = cx - field_w / 2
            fy = py + 44
            border2 = (
                QColor(255, 80, 80, int(230 * ease))
                if self._pin_error > 0
                else QColor(255, 180, 180, int(180 * ease))
            )
            p.setPen(QPen(border2, 2))
            p.setBrush(QColor(40, 0, 0, int(220 * ease)))
            p.drawRoundedRect(QRectF(fx, fy, field_w, field_h), 8, 8)
            p.setFont(QFont("Bahnschrift", 15))
            if self._owner_buf:
                p.setPen(QColor(255, 245, 245, int(245 * ease)))
                shown = ("•" * len(self._owner_buf)) + ("▋" if self._cursor_on else "")
            else:
                p.setPen(QColor(160, 80, 80, int(160 * ease)))
                shown = "type answer…"
            dw = p.fontMetrics().horizontalAdvance(shown.replace("▋", " "))
            p.drawText(int(cx - dw / 2), int(fy + 32), shown)

            step = 0
            total = 0
            if self._owner_quiz is not None:
                step = min(self._owner_quiz.index + 1, len(self._owner_quiz.questions))
                total = len(self._owner_quiz.questions)
            p.setFont(QFont("Cascadia Mono", 9))
            p.setPen(QColor(255, 150, 150, int(170 * ease)))
            meta = f"IDENTITY {step}/{total} · Enter to submit"
            mw = p.fontMetrics().horizontalAdvance(meta)
            p.drawText(int(cx - mw / 2), int(fy + field_h + 24), meta)

    def _corners(self, p: QPainter, w: int, h: int, ease: float) -> None:
        inset, arm = 40, 30
        a = int(120 * ease)
        p.setPen(QPen(QColor(0, 210, 230, a), 1.1))
        for x, y, sx, sy in (
            (inset, inset, 1, 1),
            (w - inset, inset, -1, 1),
            (inset, h - inset, 1, -1),
            (w - inset, h - inset, -1, -1),
        ):
            p.drawLine(x, y, x + sx * arm, y)
            p.drawLine(x, y, x, y + sy * arm)

    def _hologram(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        ease: float,
        breath: float,
        speak: float,
    ) -> None:
        """Holographic arc reactor — pulses while speaking."""
        base = min(self.width(), self.height()) * 0.078
        # Pulse scale while talking
        pulse = breath * (1.0 + 0.12 * self._lips * speak)
        r = base * pulse * ease
        if r < 8:
            return

        # Outer hologram glow disc
        glow = QRadialGradient(cx, cy, r * 2.1)
        glow.setColorAt(0.0, QColor(0, 200, 230, int(55 * ease * (0.5 + 0.5 * speak))))
        glow.setColorAt(0.45, QColor(0, 120, 160, int(25 * ease)))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), r * 2.0, r * 2.0)

        # Ghost parallax rings (hologram depth)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, (scale, alpha, thick, spin) in enumerate(
            (
                (1.85, 35, 1.0, -0.4),
                (1.62, 55, 1.1, 0.55),
                (1.38, 90, 1.4, -0.8),
            )
        ):
            rr = r * scale
            p.setPen(QPen(QColor(0, 220, 240, int(alpha * ease)), thick))
            p.drawEllipse(QPointF(cx + math.sin(self._t * spin) * 1.5, cy), rr, rr)

        # Scanning bands across hologram
        scan_y = cy - r * 1.5 + ((self._t * 28) % (r * 3.2))
        band = QLinearGradient(0, scan_y - 8, 0, scan_y + 8)
        band.setColorAt(0.0, QColor(0, 255, 255, 0))
        band.setColorAt(0.5, QColor(140, 255, 255, int(70 * ease)))
        band.setColorAt(1.0, QColor(0, 255, 255, 0))
        p.setClipRect(QRectF(cx - r * 1.7, cy - r * 1.7, r * 3.4, r * 3.4))
        p.setBrush(QBrush(band))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(cx - r * 1.7, scan_y - 8, r * 3.4, 16))
        # Fine hologram lines
        p.setPen(QPen(QColor(0, 230, 255, int(18 * ease)), 1))
        for i in range(-4, 5):
            yy = cy + i * (r * 0.28)
            if abs(yy - cy) < r * 1.4:
                p.drawLine(QPointF(cx - r * 1.2, yy), QPointF(cx + r * 1.2, yy))
        p.setClipping(False)

        # Rotating arc segments
        for i in range(3):
            start = (self._ring * 50 + i * 120) % 360
            span = 42 + int(18 * self._lips)
            p.setPen(QPen(QColor(0, 240, 255, int((160 + 60 * self._lips) * ease)), 2.2))
            p.drawArc(
                QRectF(cx - r * 1.38, cy - r * 1.38, r * 2.76, r * 2.76),
                int(start * 16),
                int(span * 16),
            )

        # Teal accent tick (no pink)
        p.setPen(QPen(QColor(0, 180, 210, int(70 * ease * (0.4 + 0.6 * self._lips))), 1.5))
        p.drawArc(
            QRectF(cx - r * 1.55, cy - r * 1.55, r * 3.1, r * 3.1),
            int((-self._ring * 30) % 360) * 16,
            28 * 16,
        )

        # Core
        core_r = r * (0.85 + 0.2 * self._lips * speak)
        core = QRadialGradient(cx, cy, core_r)
        core.setColorAt(0.0, QColor(230, 255, 255, int(240 * ease)))
        core.setColorAt(0.25, QColor(80, 230, 255, int(180 * ease)))
        core.setColorAt(0.55, QColor(0, 140, 190, int(90 * ease)))
        core.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # Speak pulse ring
        if self._lips > 0.05:
            pr = r * (1.5 + 0.35 * speak)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(0, 245, 255, int(140 * self._lips * speak)), 2))
            p.drawEllipse(QPointF(cx, cy), pr, pr)

        # Voice waveform under hologram only while speaking
        if self._lips > 0.08:
            bars = 16
            span = r * 2.6
            left = cx - span / 2
            base_y = cy + r * 1.85
            for i in range(bars):
                x = left + (i / max(1, bars - 1)) * span
                amp = (
                    0.25
                    + 0.75
                    * abs(math.sin(self._t * 8.5 + i * 0.5))
                    * self._lips
                )
                hh = 3 + amp * (12 + 8 * speak)
                p.setPen(QPen(QColor(0, 230, 245, int(150 * self._lips)), 1.6))
                p.drawLine(QPointF(x, base_y - hh), QPointF(x, base_y + hh))

    def _unlock_ring(self, p: QPainter, cx: float, cy: float, ease: float) -> None:
        u = min(1.0, self._unlock_ms / (self.UNLOCK_SEC * 1000))
        s = u * u * (3 - 2 * u)
        r = min(self.width(), self.height()) * (0.09 + 0.28 * s)
        a = int(170 * (1.0 - s) * ease)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 240, 255, a), 2.2))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor(0, 200, 230, a // 3), 1))
        p.drawEllipse(QPointF(cx, cy), r * 1.08, r * 1.08)

    def _brand(self, p: QPainter, cx: float, y: float, ease: float) -> None:
        p.setFont(QFont("Bahnschrift", 11))
        p.setPen(QColor(0, 210, 230, int(170 * ease)))
        mark = "J.A.R.V.I.S"
        mw = p.fontMetrics().horizontalAdvance(mark)
        p.drawText(int(cx - mw / 2), int(y), mark)
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(110, 145, 160, int(130 * ease)))
        sub = (
            "SECURE ACCESS · 1/3"
            if self._phase == PIN
            else "SECURE ACCESS · 2/3"
            if self._phase == BIRTH
            else "SECURE ACCESS · 3/3"
            if self._phase == BIO
            else "PERSONAL AGENT"
        )
        sw = p.fontMetrics().horizontalAdvance(sub)
        p.drawText(int(cx - sw / 2), int(y + 16), sub)

    def _paint_pin(self, p: QPainter, cx: float, cy: float, ease: float) -> None:
        """PIN card — step 1 of 2."""
        shake = int(math.sin(self._t * 26) * 7 * self._pin_error) if self._pin_error else 0
        card_w, card_h = 340, 220
        px = cx - card_w / 2 + shake
        py = cy - card_h / 2

        p.setPen(QPen(QColor(0, 200, 220, int(70 * ease)), 1.2))
        p.setBrush(QColor(4, 12, 20, int(200 * ease)))
        p.drawRoundedRect(QRectF(px, py, card_w, card_h), 12, 12)
        p.setPen(QPen(QColor(0, 230, 245, int(140 * ease)), 1.5))
        p.drawLine(QPointF(px + 24, py + 2), QPointF(px + card_w - 24, py + 2))

        p.setFont(QFont("Cascadia Mono", 8))
        p.setPen(QColor(0, 200, 220, int(150 * ease)))
        step = "VERIFICATION  ·  STEP 1 OF 3"
        sw0 = p.fontMetrics().horizontalAdvance(step)
        p.drawText(int(cx - sw0 / 2 + shake), int(py + 28), step)

        p.setFont(QFont("Bahnschrift", 11))
        p.setPen(QColor(190, 220, 230, int(210 * ease)))
        title = "ENTER ACCESS CODE"
        tw = p.fontMetrics().horizontalAdvance(title)
        p.drawText(int(cx - tw / 2 + shake), int(py + 50), title)

        if self._line_full and self._phase == PIN:
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(QColor(0, 200, 220, int(150 * ease)))
            whisper = self._line or self._line_full
            if len(whisper) > 42:
                whisper = whisper[:41] + "…"
            ww = p.fontMetrics().horizontalAdvance(whisper)
            p.drawText(int(cx - ww / 2 + shake), int(py + 70), whisper)

        cell, gap = 50, 12
        total = 4 * cell + 3 * gap
        x0 = cx - total / 2 + shake
        y0 = py + 92
        for i in range(4):
            x = x0 + i * (cell + gap)
            filled = i < len(self._pin)
            if self._pin_error > 0:
                border = QColor(220, 70, 90, int(210 * ease))
            elif self._pin_ok_flash > 0:
                border = QColor(0, 240, 200, int(230 * ease))
            else:
                border = QColor(0, 210, 230, int((170 if filled else 75) * ease))
            p.setPen(QPen(border, 1.5))
            p.setBrush(QColor(8, 18, 28, int(210 * ease)))
            p.drawRoundedRect(QRectF(x, y0, cell, cell), 8, 8)
            p.setFont(QFont("Bahnschrift", 17, QFont.Weight.Bold))
            if filled:
                p.setPen(QColor(235, 248, 255, int(245 * ease)))
                ch = "●"
                cw = p.fontMetrics().horizontalAdvance(ch)
                p.drawText(int(x + cell / 2 - cw / 2), int(y0 + 33), ch)
            elif i == len(self._pin) and self._cursor_on:
                p.setPen(QColor(0, 230, 245, int(190 * ease)))
                ch = "│"
                cw = p.fontMetrics().horizontalAdvance(ch)
                p.drawText(int(x + cell / 2 - cw / 2), int(y0 + 33), ch)

        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(110, 140, 155, int(145 * ease)))
        hint = "Enter PIN"
        hw = p.fontMetrics().horizontalAdvance(hint)
        p.drawText(int(cx - hw / 2 + shake), int(y0 + cell + 28), hint)

        p.setFont(QFont("Cascadia Mono", 9))
        col = (
            QColor(220, 80, 90, int(210 * ease))
            if self._status == "DENIED"
            else QColor(0, 210, 230, int(170 * ease))
        )
        p.setPen(col)
        sw = p.fontMetrics().horizontalAdvance(self._status)
        p.drawText(int(cx - sw / 2 + shake), int(y0 + cell + 48), self._status)

    def _paint_birth(self, p: QPainter, cx: float, cy: float, ease: float) -> None:
        """Birth date card — step 2 of 2. Type MMDDYYYY; shows as MM/DD/YYYY."""
        shake = int(math.sin(self._t * 26) * 7 * self._pin_error) if self._pin_error else 0
        card_w, card_h = 380, 220
        px = cx - card_w / 2 + shake
        py = cy - card_h / 2

        p.setPen(QPen(QColor(0, 200, 220, int(70 * ease)), 1.2))
        p.setBrush(QColor(4, 12, 20, int(200 * ease)))
        p.drawRoundedRect(QRectF(px, py, card_w, card_h), 12, 12)
        p.setPen(QPen(QColor(0, 200, 230, int(100 * ease)), 1.5))
        p.drawLine(QPointF(px + 24, py + 2), QPointF(px + card_w - 24, py + 2))

        p.setFont(QFont("Cascadia Mono", 8))
        p.setPen(QColor(0, 200, 220, int(150 * ease)))
        step = "VERIFICATION  ·  STEP 2 OF 3"
        sw0 = p.fontMetrics().horizontalAdvance(step)
        p.drawText(int(cx - sw0 / 2 + shake), int(py + 28), step)

        p.setFont(QFont("Bahnschrift", 11))
        p.setPen(QColor(190, 220, 230, int(210 * ease)))
        title = "ENTER DATE OF BIRTH"
        tw = p.fontMetrics().horizontalAdvance(title)
        p.drawText(int(cx - tw / 2 + shake), int(py + 50), title)

        if self._line_full and self._phase == BIRTH:
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(QColor(0, 200, 220, int(150 * ease)))
            whisper = self._line or self._line_full
            if len(whisper) > 44:
                whisper = whisper[:43] + "…"
            ww = p.fontMetrics().horizontalAdvance(whisper)
            p.drawText(int(cx - ww / 2 + shake), int(py + 70), whisper)

        # Date field
        display = _format_birth_digits(self._birth_digits)
        placeholder = "MM / DD / YYYY"
        field_w, field_h = 260, 52
        fx = cx - field_w / 2 + shake
        fy = py + 92
        if self._pin_error > 0:
            border = QColor(220, 70, 90, int(210 * ease))
        elif self._pin_ok_flash > 0:
            border = QColor(0, 240, 200, int(230 * ease))
        else:
            border = QColor(0, 210, 230, int(140 * ease))
        p.setPen(QPen(border, 1.5))
        p.setBrush(QColor(8, 18, 28, int(210 * ease)))
        p.drawRoundedRect(QRectF(fx, fy, field_w, field_h), 8, 8)

        p.setFont(QFont("Bahnschrift", 18))
        if display:
            p.setPen(QColor(235, 248, 255, int(245 * ease)))
            text = display + ("▋" if self._cursor_on and len(self._birth_digits) < 8 else "")
        else:
            p.setPen(QColor(80, 110, 125, int(160 * ease)))
            text = placeholder
        dw = p.fontMetrics().horizontalAdvance(text.replace("▋", " "))
        p.drawText(int(cx - dw / 2 + shake), int(fy + 34), text)

        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(110, 140, 155, int(145 * ease)))
        hint = "Enter date of birth"
        hw = p.fontMetrics().horizontalAdvance(hint)
        p.drawText(int(cx - hw / 2 + shake), int(fy + field_h + 28), hint)

        p.setFont(QFont("Cascadia Mono", 9))
        col = (
            QColor(220, 80, 90, int(210 * ease))
            if self._status == "DENIED"
            else QColor(0, 210, 230, int(170 * ease))
        )
        p.setPen(col)
        sw = p.fontMetrics().horizontalAdvance(self._status)
        p.drawText(int(cx - sw / 2 + shake), int(fy + field_h + 48), self._status)

    def _paint_bio(self, p: QPainter, cx: float, cy: float, ease: float) -> None:
        """Face / eye scan + code-word fallback card."""
        shake = int(math.sin(self._t * 26) * 7 * self._pin_error) if self._pin_error else 0
        card_w, card_h = 400, 230
        px = cx - card_w / 2 + shake
        py = cy - card_h / 2

        p.setPen(QPen(QColor(0, 200, 220, int(70 * ease)), 1.2))
        p.setBrush(QColor(4, 12, 20, int(200 * ease)))
        p.drawRoundedRect(QRectF(px, py, card_w, card_h), 12, 12)
        p.setPen(QPen(QColor(0, 230, 245, int(140 * ease)), 1.5))
        p.drawLine(QPointF(px + 24, py + 2), QPointF(px + card_w - 24, py + 2))

        p.setFont(QFont("Cascadia Mono", 8))
        p.setPen(QColor(0, 200, 220, int(150 * ease)))
        step = "VERIFICATION  ·  STEP 3 OF 3"
        sw0 = p.fontMetrics().horizontalAdvance(step)
        p.drawText(int(cx - sw0 / 2 + shake), int(py + 28), step)

        p.setFont(QFont("Bahnschrift", 11))
        p.setPen(QColor(190, 220, 230, int(210 * ease)))
        title = (
            "OWNER BIOMETRICS"
            if self._bio_mode == "face"
            else "CODE WORD CHALLENGE"
        )
        tw = p.fontMetrics().horizontalAdvance(title)
        p.drawText(int(cx - tw / 2 + shake), int(py + 50), title)

        # Status / whisper
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(0, 200, 220, int(160 * ease)))
        msg = self._bio_status or (self._line or self._line_full)
        if len(msg) > 48:
            msg = msg[:47] + "…"
        mw = p.fontMetrics().horizontalAdvance(msg)
        p.drawText(int(cx - mw / 2 + shake), int(py + 74), msg)

        if self._bio_mode == "face":
            # Scanning reticle
            rr = 36 + 4 * abs(math.sin(self._t * 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(0, 230, 245, int(160 * ease)), 1.6))
            p.drawEllipse(QPointF(cx + shake, py + 130), rr, rr)
            p.setPen(QPen(QColor(0, 200, 230, int(80 * ease)), 1))
            p.drawEllipse(QPointF(cx + shake, py + 130), rr * 1.2, rr * 1.2)
            if self._bio_score >= 0:
                p.setFont(QFont("Cascadia Mono", 9))
                p.setPen(QColor(140, 180, 190, int(170 * ease)))
                sc = f"MATCH {int(self._bio_score * 100)}%"
                sw = p.fontMetrics().horizontalAdvance(sc)
                p.drawText(int(cx - sw / 2 + shake), int(py + 190), sc)
            else:
                p.setFont(QFont("Segoe UI", 8))
                p.setPen(QColor(110, 140, 155, int(145 * ease)))
                tip = "Hold still · eyes toward camera"
                hw = p.fontMetrics().horizontalAdvance(tip)
                p.drawText(int(cx - hw / 2 + shake), int(py + 190), tip)
        else:
            # Code word field
            field_w, field_h = 280, 48
            fx = cx - field_w / 2 + shake
            fy = py + 100
            border = (
                QColor(220, 70, 90, int(210 * ease))
                if self._pin_error > 0
                else QColor(0, 210, 230, int(140 * ease))
            )
            p.setPen(QPen(border, 1.5))
            p.setBrush(QColor(8, 18, 28, int(210 * ease)))
            p.drawRoundedRect(QRectF(fx, fy, field_w, field_h), 8, 8)
            p.setFont(QFont("Bahnschrift", 16))
            shown = ("•" * len(self._code_buf)) if self._code_buf else "code word"
            if self._code_buf:
                p.setPen(QColor(235, 248, 255, int(245 * ease)))
                shown = ("•" * len(self._code_buf)) + ("▋" if self._cursor_on else "")
            else:
                p.setPen(QColor(80, 110, 125, int(160 * ease)))
            dw = p.fontMetrics().horizontalAdvance(shown.replace("▋", " "))
            p.drawText(int(cx - dw / 2 + shake), int(fy + 32), shown)
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor(110, 140, 155, int(145 * ease)))
            tip = "Enter to confirm"
            hw = p.fontMetrics().horizontalAdvance(tip)
            p.drawText(int(cx - hw / 2 + shake), int(fy + field_h + 28), tip)

    def _message(self, p: QPainter, cx: float, cy: float, ease: float) -> None:
        if not self._line_full:
            return
        display = self._line
        if self._line and len(self._line) < len(self._line_full) and self._cursor_on:
            display += "▋"

        font = QFont(
            "Bahnschrift", max(15, int(min(self.width(), self.height()) * 0.022))
        )
        font.setWeight(QFont.Weight.Light)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        p.setFont(font)

        tw = p.fontMetrics().horizontalAdvance(self._line_full)
        pad = 36
        plate_w = min(max(tw + pad * 2, 300), self.width() * 0.72)
        plate_h = 54
        px = cx - plate_w / 2
        py = cy - plate_h / 2

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(4, 12, 20, int(185 * ease)))
        p.drawRoundedRect(QRectF(px, py, plate_w, plate_h), 8, 8)
        p.setPen(QPen(QColor(0, 210, 230, int(55 * ease)), 1))
        p.drawRoundedRect(QRectF(px, py, plate_w, plate_h), 8, 8)
        # Speak glow edge
        if self._lips > 0.1:
            p.setPen(QPen(QColor(0, 240, 255, int(80 * self._lips)), 1.5))
            p.drawRoundedRect(QRectF(px, py, plate_w, plate_h), 8, 8)

        p.setPen(QColor(232, 244, 250, int(245 * ease)))
        # Ellipsize if needed
        text = display
        while p.fontMetrics().horizontalAdvance(text) > plate_w - 28 and len(text) > 4:
            text = text[:-2] + "…"
        dw = p.fontMetrics().horizontalAdvance(text)
        p.drawText(int(cx - dw / 2), int(cy + p.fontMetrics().ascent() / 2 - 2), text)

    def _progress(self, p: QPainter, cx: float, cy: float, ease: float) -> None:
        rail = min(self.width() * 0.26, 340)
        rx = cx - rail / 2
        fill = rail * (min(100.0, self._pct) / 100.0)
        p.setPen(QPen(QColor(255, 255, 255, int(14 * ease)), 1))
        p.drawLine(QPointF(rx, cy), QPointF(rx + rail, cy))
        grad = QLinearGradient(rx, cy, rx + max(fill, 1), cy)
        grad.setColorAt(0.0, QColor(0, 200, 220, 210))
        grad.setColorAt(1.0, QColor(0, 240, 255, 245))
        p.setPen(QPen(QBrush(grad), 2.2))
        p.drawLine(QPointF(rx, cy), QPointF(rx + fill, cy))

        p.setFont(QFont("Cascadia Mono", 9))
        p.setPen(QColor(130, 165, 175, int(160 * ease)))
        p.drawText(int(rx), int(cy + 22), self._status)
        right = f"{int(min(100, self._pct)):02d}%"
        rw = p.fontMetrics().horizontalAdvance(right)
        p.drawText(int(rx + rail - rw), int(cy + 22), right)

    def _meta(self, p: QPainter, w: int, h: int, ease: float) -> None:
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(100, 130, 145, int(140 * ease)))
        p.drawText(48, h - 40, self._name)
        rw = p.fontMetrics().horizontalAdvance(self._clock)
        p.drawText(w - 48 - rw, h - 40, self._clock)
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(70, 100, 115, int(105 * ease)))
        tip = (
            "INTRUSION — step away"
            if self._phase == INTRUSION
            else "Owner unlock — answer identity questions"
            if self._phase == OWNER_LOCK
            else "Step 1 — enter PIN"
            if self._phase == PIN
            else "Step 2 — enter birth date"
            if self._phase == BIRTH
            else "Step 3 — face or code word"
            if self._phase == BIO
            else "Esc to skip"
        )
        if self._phase in (INTRUSION, OWNER_LOCK):
            p.setPen(QColor(255, 140, 140, int(160 * ease)))
        tw = p.fontMetrics().horizontalAdvance(tip)
        p.drawText(int(w / 2 - tw / 2), h - 40, tip)


def run(
    *,
    launch_jarvis: bool = True,
    allow_lock: bool | None = None,
    start_intrusion: bool = False,
) -> int:
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Jarvis Secure Boot")
    # Preview never locks the workstation
    if allow_lock is None:
        allow_lock = launch_jarvis
    win = PCPowerOn(launch_jarvis=launch_jarvis, allow_lock=bool(allow_lock))
    if start_intrusion:
        QTimer.singleShot(80, win.start)
        QTimer.singleShot(500, win._start_intrusion)
    else:
        QTimer.singleShot(50, win.start)
    return app.exec()


if __name__ == "__main__":
    preview = "--preview" in sys.argv
    intrusion = "--intrusion" in sys.argv or "--show-lockdown" in sys.argv
    launch = "--no-jarvis" not in sys.argv and not preview and not intrusion
    raise SystemExit(
        run(
            launch_jarvis=launch,
            # Preview never locks. Intrusion demo DOES lock unless --preview.
            allow_lock=not preview,
            start_intrusion=intrusion,
        )
    )

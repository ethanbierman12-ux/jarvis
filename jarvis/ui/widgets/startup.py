"""Boot HUD — Arwes cinematic INIT: optics feed, weather, ISS, reactor."""

from __future__ import annotations

import math
import os
import random
import threading
from datetime import datetime

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPointF,
    pyqtSignal,
    QPropertyAnimation,
    QEasingCurve,
    QRectF,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QRadialGradient,
    QLinearGradient,
    QImage,
)
from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect

from jarvis.ui.boot_sound import play_boot_sound, stop_boot_sound, speak_boot_line


# Cyan / teal palette (matches secure boot + styles)
CYAN = QColor(0, 240, 255)
TEAL = QColor(0, 180, 210)
WHITE = QColor(230, 251, 255)
VOID = QColor(2, 6, 12)

_FAST = bool(
    os.environ.get("JARVIS_FAST_BOOT") or os.environ.get("JARVIS_FROM_SECURE_BOOT")
)


class StartupOverlay(QWidget):
    finished = pyqtSignal()
    loading_announced = pyqtSignal()

    BOOT_SEC = 1.1 if _FAST else 3.8
    FADE_MS = 200 if _FAST else 550
    TICK_MS = 40
    CAM_MS = 280
    PREVIEW_MAX_W = 240

    # Phased systems checklist (cinematic, not a dashboard dump)
    SYSTEMS = (
        "NEURAL CORE",
        "VOICE MATRIX",
        "OPTICS LINK",
        "ATMOSPHERE",
        "ORBITAL TRACK",
        "MEMORY VAULT",
        "AGENT CREW",
        "HUD FRAME",
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background:#02060c;")
        self._ms = 0
        self._t = 0.0
        self._done = False
        self._typed = ""
        self._target = "INITIATING PROTOCOL"
        self._phase_online = False
        self._dots = ""
        self._pct = 0
        self._line = 0.0
        self._scan = 0.0
        self._log: list[str] = []
        self._connected = ""
        self._cursor = True
        self._said_loading = False
        self._said_online = False
        self._systems_on = 0
        self._sparks: list[tuple[float, float, float, float]] = []
        self._ring_spin = 0.0
        self._cam = None
        self._cam_qimg: QImage | None = None
        self._feed_mode = "day"
        self._wx_summary = "Atmosphere syncing…"
        self._iss_summary = "Orbital syncing…"
        self._optics_ok = False
        self._cam = None
        self._cam_opening = False
        self._cam_started = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(1.0)
        self._fade = None

    def start(self) -> None:
        self._ms = 0
        self._t = 0.0
        self._done = False
        self._typed = ""
        self._target = "INITIATING PROTOCOL"
        self._phase_online = False
        self._dots = ""
        self._pct = 0
        self._line = 0.0
        self._scan = 0.0
        self._log = []
        self._said_loading = False
        self._said_online = False
        self._systems_on = 0
        self._sparks = []
        self._ring_spin = 0.0
        self._cam_qimg = None
        self._feed_mode = "day"
        self._wx_summary = "Atmosphere syncing…"
        self._iss_summary = "Orbital syncing…"
        self._optics_ok = False
        self._cam_started = False
        self._connected = datetime.now().strftime("%H:%M:%S")
        self._effect.setOpacity(1.0)
        # Seed floating energy sparks
        rng = random.Random(int(datetime.now().timestamp()) % 10_000)
        for _ in range(28):
            self._sparks.append(
                (
                    rng.random(),
                    rng.random(),
                    0.15 + rng.random() * 0.85,
                    0.4 + rng.random() * 1.6,
                )
            )
        self.show()
        self.raise_()
        self._timer.start(self.TICK_MS)
        play_boot_sound()
        try:
            from jarvis.ui.hud_sfx import play_whoosh, ensure_sfx

            ensure_sfx()
            play_whoosh()
        except Exception:
            pass
        QTimer.singleShot(80 if _FAST else 160, self._announce_loading)
        # Skip boot cam when coming from secure boot — already verified optics
        if not _FAST:
            QTimer.singleShot(500, self._boot_open_optics)
        else:
            self._optics_ok = True
            self._feed_mode = "day"
        QTimer.singleShot(200 if _FAST else 300, self._boot_fetch_tracks)

    def _boot_open_optics(self) -> None:
        if self._cam_opening or self._done:
            return
        self._cam_opening = True

        def _open() -> None:
            try:
                import cv2
                from jarvis.config import Settings

                settings = Settings.load()
                idx = int(getattr(settings, "camera_index", 0) or 0)
                order = [idx] + [i for i in range(3) if i != idx]
                for i in order:
                    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap = cv2.VideoCapture(i)
                    if not cap.isOpened():
                        continue
                    for _ in range(2):
                        cap.read()
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        self._cam = cap
                        self._optics_ok = True
                        self._ingest_boot_frame(frame)
                        return
                    cap.release()
            except Exception as e:
                print(f"[boot] optics: {e}")
            finally:
                self._cam_opening = False

        threading.Thread(target=_open, daemon=True, name="jarvis-boot-cam").start()

    def _boot_fetch_tracks(self) -> None:
        def _work() -> None:
            try:
                from jarvis.config import Settings
                from jarvis.core.satellite_track import fetch_iss, fetch_weather_brief

                city = getattr(Settings.load(), "city", "") or "Philadelphia"
                wx = fetch_weather_brief(city)
                self._wx_summary = wx.get("summary") or "Atmosphere online"
                iss = fetch_iss()
                self._iss_summary = iss.get("summary") or "Orbital online"
            except Exception as e:
                self._wx_summary = f"Atmosphere offline ({e})"

        threading.Thread(target=_work, daemon=True, name="jarvis-boot-tracks").start()

    def _ingest_boot_frame(self, frame) -> None:
        try:
            import cv2
            import numpy as np
            from jarvis.core.boot_biometrics import is_night_hours
            from jarvis.ui.widgets.night_vision import apply_night_vision

            draw = frame
            mode = "day"
            if is_night_hours():
                gray_mean = float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))
                if gray_mean < 85:
                    draw = apply_night_vision(frame)
                    mode = "night"
            self._feed_mode = mode
            h, w = draw.shape[:2]
            if w > self.PREVIEW_MAX_W:
                draw = cv2.resize(
                    draw,
                    (self.PREVIEW_MAX_W, int(h * self.PREVIEW_MAX_W / w)),
                    interpolation=cv2.INTER_AREA,
                )
            rgb = cv2.cvtColor(draw, cv2.COLOR_BGR2RGB)
            rgb = np.ascontiguousarray(rgb)
            h, w, ch = rgb.shape
            self._cam_qimg = QImage(
                rgb.data, w, h, ch * w, QImage.Format.Format_RGB888
            ).copy()
        except Exception:
            pass

    def _boot_cam_tick(self) -> None:
        if self._done or not self.isVisible():
            return
        try:
            if self._cam is not None:
                ok, frame = self._cam.read()
                if ok and frame is not None:
                    self._ingest_boot_frame(frame)
        except Exception:
            pass
        if not self._done and self.isVisible():
            QTimer.singleShot(self.CAM_MS, self._boot_cam_tick)

    def _close_optics(self) -> None:
        try:
            if self._cam is not None:
                self._cam.release()
        except Exception:
            pass
        self._cam = None

    def _announce_loading(self) -> None:
        if self._said_loading:
            return
        self._said_loading = True
        speak_boot_line("Loading systems")
        try:
            self.loading_announced.emit()
        except Exception:
            pass

    def _tick(self) -> None:
        self._ms += self.TICK_MS
        sec = self._ms / 1000.0
        self._t += 0.055
        self._ring_spin += 0.035
        self._cursor = (int(self._t * 5) % 2) == 0
        self._scan = (self._scan + 4.2) % max(1, self.height())
        self._line = min(1.0, sec / 0.48)

        raw = min(1.0, sec / self.BOOT_SEC)
        s = raw * raw * (3.0 - 2.0 * raw)
        eased = s * 0.9 + (s * s) * 0.1
        self._pct = int(min(100.0, eased * 100.0))

        # Systems light up in sequence
        want = int(min(len(self.SYSTEMS), (self._pct / 100.0) * (len(self.SYSTEMS) + 0.4)))
        if want > self._systems_on:
            self._systems_on = want
            try:
                from jarvis.ui.hud_sfx import play_click

                if self._systems_on <= len(self.SYSTEMS):
                    play_click()
            except Exception:
                pass

        # Title phases
        if self._pct >= 88 and not self._phase_online:
            self._phase_online = True
            self._target = "J.A.R.V.I.S  ONLINE"
            self._typed = ""
            if not self._said_online:
                self._said_online = True
                try:
                    from jarvis.ui.hud_sfx import play_confirm

                    play_confirm()
                except Exception:
                    pass

        if sec >= 0.22:
            n = int((sec - 0.22) * 28)
            self._typed = self._target[: min(len(self._target), max(0, n))]
            if len(self._typed) >= len(self._target):
                self._dots = "." * (1 + int((sec * 3.2) % 4)) if not self._phase_online else ""
            else:
                self._dots = ""
        else:
            self._typed = ""
            self._dots = ""

        if sec >= 0.1 and not self._log:
            self._log = ["ARWES · BOOT"]
        if sec >= 0.38 and len(self._log) < 2:
            self._log = ["ARWES · BOOT", f"LINK  {self._connected}"]
        if sec >= 0.65:
            feed = "NV" if self._feed_mode == "night" else "DAY"
            optics = "OPTICS · LIVE" if self._optics_ok else "OPTICS · STANDBY"
            self._log = [
                "ARWES · BOOT",
                f"LINK  {self._connected}",
                f"{optics} · {feed}",
                "CORE · NOMINAL",
                f"SYS  {self._systems_on}/{len(self.SYSTEMS)}",
                f"{self._pct:03d}%",
            ]

        if self._pct >= 100 and sec >= self.BOOT_SEC + 0.15 and not self._done:
            self._done = True
            self._fade_out()
        if self._optics_ok and not self._cam_started:
            self._cam_started = True
            self._boot_cam_tick()
        self.update()

    def _fade_out(self) -> None:
        self._timer.stop()
        self._close_optics()
        stop_boot_sound()
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(self.FADE_MS)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.finished.connect(self._complete)
        anim.start()
        self._fade = anim

    def _complete(self) -> None:
        self._close_optics()
        try:
            self._effect.setOpacity(0.0)
        except Exception:
            pass
        self.hide()
        self.finished.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        ease = 1.0 - (1.0 - self._line) ** 3
        breath = 1.0 + 0.032 * math.sin(self._t)
        pulse = 0.55 + 0.45 * abs(math.sin(self._t * 1.4))

        p.fillRect(self.rect(), VOID)

        # Deep void vignette
        vig = QRadialGradient(cx, cy, min(w, h) * 0.78)
        vig.setColorAt(0.0, QColor(6, 18, 28, 255))
        vig.setColorAt(0.45, QColor(2, 8, 14, 255))
        vig.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(vig))
        p.drawRect(self.rect())

        self._paint_grid(p, w, h, ease)
        self._paint_sparks(p, w, h, ease)

        # Cyan bloom core
        bloom = QRadialGradient(cx, cy, min(w, h) * 0.38 * breath)
        bloom.setColorAt(0.0, QColor(0, 90, 120, int(88 * pulse)))
        bloom.setColorAt(0.35, QColor(0, 40, 70, 40))
        bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(bloom))
        p.drawRect(self.rect())

        # Teal accent bloom (secure boot)
        teal_bloom = QRadialGradient(cx + w * 0.18, cy - h * 0.12, min(w, h) * 0.28)
        teal_bloom.setColorAt(0.0, QColor(0, 180, 210, int(28 * ease * pulse)))
        teal_bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(teal_bloom))
        p.drawRect(self.rect())

        # Horizontal scanline
        g = QLinearGradient(0, self._scan - 14, 0, self._scan + 14)
        g.setColorAt(0, QColor(0, 240, 255, 0))
        g.setColorAt(0.5, QColor(0, 240, 255, int(28 * ease)))
        g.setColorAt(1, QColor(0, 240, 255, 0))
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(0, self._scan - 14, w, 28))

        self._paint_reactor(p, cx, cy, ease, breath)
        self._frames(p, cx, cy, ease * breath)
        self._paint_brackets(p, w, h, ease)

        # Hero title
        if ease > 0.14:
            alpha = int(255 * min(1.0, (ease - 0.14) / 0.4))
            font = QFont("Bahnschrift", max(18, int(min(w, h) * 0.036)))
            font.setBold(True)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 7)
            p.setFont(font)
            display = self._typed + self._dots + ("▌" if self._cursor and not self._phase_online else "")
            full_w = p.fontMetrics().horizontalAdvance(self._target + "  ")
            x = int(cx - full_w / 2)
            y = int(cy + p.fontMetrics().ascent() / 2 - 6)

            # Magenta ghost / cyan glow
            p.setPen(QColor(0, 180, 210, alpha // 5))
            p.drawText(x + 2, y + 1, display)
            for dx in (-2, 2):
                p.setPen(QColor(0, 240, 255, alpha // 4))
                p.drawText(x + dx, y, display)
            p.setPen(QColor(236, 248, 255, alpha))
            p.drawText(x, y, display)

            # Progress rail
            rail = full_w * 1.02
            rx, ry = cx - rail / 2, cy + 46
            p.setPen(QPen(QColor(0, 240, 255, 30), 1))
            p.drawLine(QPointF(rx, ry), QPointF(rx + rail, ry))
            fill = rail * (self._pct / 100.0)
            # Magenta tip on progress
            glow = QLinearGradient(rx, ry, rx + fill, ry)
            glow.setColorAt(0.0, QColor(0, 240, 255, 200))
            glow.setColorAt(0.85, QColor(0, 240, 255, 230))
            glow.setColorAt(1.0, QColor(0, 180, 210, 240))
            p.setPen(QPen(QBrush(glow), 3))
            p.drawLine(QPointF(rx, ry), QPointF(rx + fill, ry))
            p.setPen(QPen(QColor(0, 240, 255, 70), 6))
            p.drawLine(QPointF(rx, ry), QPointF(rx + fill, ry))

            p.setPen(QColor(0, 230, 255, 180))
            p.setFont(QFont("Cascadia Mono", 11, QFont.Weight.Bold))
            pct = f"{self._pct:03d}"
            pw = p.fontMetrics().horizontalAdvance(pct)
            p.drawText(int(cx - pw / 2), int(cy + 70), pct)
            p.setPen(QColor(0, 180, 210, 140))
            p.setFont(QFont("Cascadia Mono", 8))
            p.drawText(int(cx + pw / 2 + 6), int(cy + 70), "%")

        # Left status log
        if ease > 0.1:
            p.setFont(QFont("Cascadia Mono", 10))
            lx, ly = 36, int(cy - 36)
            for i, line in enumerate(self._log):
                if i == 0:
                    p.setPen(QColor(0, 180, 210, int(160 * ease)))
                elif i == 1:
                    p.setPen(QColor(230, 245, 255, int(220 * ease)))
                else:
                    p.setPen(QColor(0, 220, 255, int(155 * ease)))
                p.drawText(lx, ly + i * 17, line)

        # Right systems checklist
        if ease > 0.2:
            self._paint_systems(p, w, h, cx, cy, ease)

        if ease > 0.25:
            self._paint_boot_optics(p, w, h, ease, pulse)
            self._paint_boot_tracks(p, w, h, ease)

        # Corner crosshairs
        tick = QColor(0, 240, 255, int(140 * ease))
        p.setPen(QPen(tick, 1.2))
        for ox, oy in ((22, 22), (w - 22, 22), (22, h - 22), (w - 22, h - 22)):
            p.drawLine(ox - 12, oy, ox + 12, oy)
            p.drawLine(ox, oy - 12, ox, oy + 12)
            p.setPen(QPen(QColor(0, 180, 210, int(90 * ease)), 1))
            p.drawLine(ox - 4, oy - 4, ox - 4, oy + 4)
            p.setPen(QPen(tick, 1.2))

        # Brand footer
        if ease > 0.35:
            p.setFont(QFont("Bahnschrift", 9))
            p.setPen(QColor(0, 240, 255, int(90 * ease)))
            foot = "ARWES · HOLOGRAPHIC COMMAND"
            fw = p.fontMetrics().horizontalAdvance(foot)
            p.drawText(int(cx - fw / 2), int(h - 28), foot)

        p.end()

    def _paint_boot_optics(
        self, p: QPainter, w: int, h: int, ease: float, pulse: float
    ) -> None:
        cam_w, cam_h = 220, 148
        x, y = 36, h - cam_h - 56
        p.setPen(QPen(QColor(0, 240, 255, int(140 * ease)), 1.4))
        p.setBrush(QColor(0, 12, 20, int(200 * ease)))
        p.drawRoundedRect(QRectF(x, y, cam_w, cam_h), 6, 6)
        if self._cam_qimg is not None and not self._cam_qimg.isNull():
            img = self._cam_qimg
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
            p.setPen(QColor(0, 160, 180, int(160 * ease)))
            p.drawText(int(x + 48), int(y + cam_h / 2), "OPTICS WARMING")

        night = self._feed_mode == "night"
        label = "NIGHT VISION" if night else "DAY FEED"
        col = (
            QColor(57, 255, 122, int(220 * ease))
            if night
            else QColor(0, 230, 255, int(220 * ease))
        )
        p.setFont(QFont("Cascadia Mono", 9, QFont.Weight.Bold))
        p.setPen(col)
        p.drawText(int(x + 10), int(y + 16), label)
        if night and (int(self._t * 2) % 2) == 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(57, 255, 122, int(200 * pulse * ease)))
            p.drawEllipse(QPointF(x + cam_w - 16, y + 12), 4, 4)

    def _paint_boot_tracks(self, p: QPainter, w: int, h: int, ease: float) -> None:
        p.setFont(QFont("Cascadia Mono", 9))
        x = 36
        y = h - 48
        p.setPen(QColor(255, 180, 120, int(190 * ease)))
        p.drawText(x, y, f"WX  {(self._wx_summary or '')[:64]}")
        p.setPen(QColor(140, 200, 255, int(190 * ease)))
        p.drawText(x, y + 16, f"SAT {(self._iss_summary or '')[:64]}")

    def _paint_grid(self, p: QPainter, w: int, h: int, ease: float) -> None:
        a = int(22 * ease)
        if a < 4:
            return
        p.setPen(QPen(QColor(0, 240, 255, a), 1))
        step = max(28, int(min(w, h) * 0.045))
        # Perspective-ish floor grid (lower third)
        y0 = int(h * 0.55)
        for y in range(y0, h, step):
            fade = 1.0 - (y - y0) / max(1, h - y0)
            p.setPen(QPen(QColor(0, 240, 255, int(a * fade * 0.7)), 1))
            p.drawLine(0, y, w, y)
        for x in range(0, w, step):
            p.setPen(QPen(QColor(0, 240, 255, a // 2), 1))
            p.drawLine(x, y0, int(w / 2 + (x - w / 2) * 0.15), h)

    def _paint_sparks(
        self, p: QPainter, w: int, h: int, ease: float
    ) -> None:
        for sx, sy, speed, size in self._sparks:
            x = ((sx + self._t * 0.02 * speed) % 1.0) * w
            y = ((sy + math.sin(self._t * speed) * 0.02) % 1.0) * h
            a = int(50 * ease * (0.4 + 0.6 * abs(math.sin(self._t * speed + sx))))
            col = TEAL if (sx + sy) % 0.37 > 0.22 else CYAN
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col.red(), col.green(), col.blue(), a))
            r = 1.2 + size * 1.4
            p.drawEllipse(QPointF(x, y), r, r)

    def _paint_reactor(
        self, p: QPainter, cx: float, cy: float, ease: float, breath: float
    ) -> None:
        r = min(self.width(), self.height()) * 0.11 * ease * breath
        if r < 8:
            return
        # Outer ring
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 240, 255, int(90 * ease)), 1.5))
        p.drawEllipse(QPointF(cx, cy - 4), r * 1.55, r * 1.55)
        p.setPen(QPen(QColor(0, 180, 210, int(50 * ease)), 1))
        p.drawEllipse(QPointF(cx, cy - 4), r * 1.72, r * 1.72)

        # Spinning arc segments
        for i in range(3):
            start = (self._ring_spin * 57.3 + i * 120) % 360
            p.setPen(QPen(QColor(0, 240, 255, int(160 * ease)), 2.2))
            p.drawArc(
                QRectF(cx - r * 1.55, cy - 4 - r * 1.55, r * 3.1, r * 3.1),
                int(start * 16),
                int(48 * 16),
            )

        core = QRadialGradient(cx, cy - 4, r)
        core.setColorAt(0.0, QColor(180, 255, 255, int(200 * ease)))
        core.setColorAt(0.35, QColor(0, 200, 255, int(120 * ease)))
        core.setColorAt(1.0, QColor(0, 40, 60, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy - 4), r, r)

    def _paint_brackets(self, p: QPainter, w: int, h: int, ease: float) -> None:
        # Expanding corner frame brackets
        inset = int(40 + (1.0 - ease) * 80)
        arm = int(36 + 28 * ease)
        col = QColor(0, 240, 255, int(180 * ease))
        mag = QColor(0, 180, 210, int(100 * ease))
        for (x, y, sx, sy) in (
            (inset, inset, 1, 1),
            (w - inset, inset, -1, 1),
            (inset, h - inset, 1, -1),
            (w - inset, h - inset, -1, -1),
        ):
            p.setPen(QPen(col, 2))
            p.drawLine(x, y, x + sx * arm, y)
            p.drawLine(x, y, x, y + sy * arm)
            p.setPen(QPen(mag, 1))
            p.drawLine(x + sx * 4, y + sy * 4, x + sx * (arm // 2), y + sy * 4)

    def _paint_systems(
        self, p: QPainter, w: int, h: int, cx: float, cy: float, ease: float
    ) -> None:
        p.setFont(QFont("Cascadia Mono", 9))
        rx = int(w - 220)
        ry = int(cy - 50)
        for i, name in enumerate(self.SYSTEMS):
            on = i < self._systems_on
            y = ry + i * 18
            if on:
                p.setPen(QColor(0, 240, 255, int(200 * ease)))
                mark = "▣"
            else:
                p.setPen(QColor(80, 110, 130, int(120 * ease)))
                mark = "□"
            p.drawText(rx, y, f"{mark}  {name}")
            if on:
                p.setPen(QColor(0, 180, 210, int(140 * ease)))
                p.drawText(rx + 150, y, "OK")

    def _frames(self, p: QPainter, cx: float, cy: float, ease: float) -> None:
        span = min(self.width() * 0.52, 680) * ease
        half = span / 2
        y_top, y_bot = cy - 62, cy + 62
        step, inset = 16, 48
        cyan = QColor(0, 240, 255, int(220 * ease))
        glow = QColor(0, 200, 255, int(60 * ease))
        mag = QColor(0, 180, 210, int(90 * ease))

        def rail(y: float, invert: bool) -> None:
            sign = -1 if invert else 1
            left, right = cx - half, cx + half
            gap = 12
            pts_l = [
                QPointF(left, y),
                QPointF(cx - inset - gap, y),
                QPointF(cx - inset + 8, y + sign * step),
                QPointF(cx - gap, y + sign * step),
            ]
            pts_r = [
                QPointF(cx + gap, y + sign * step),
                QPointF(cx + inset - 8, y + sign * step),
                QPointF(cx + inset + gap, y),
                QPointF(right, y),
            ]
            for pen in (QPen(glow, 5), QPen(cyan, 1.8)):
                p.setPen(pen)
                for pts in (pts_l, pts_r):
                    for i in range(len(pts) - 1):
                        p.drawLine(pts[i], pts[i + 1])
            # Magenta chevron tips
            p.setPen(QPen(mag, 1.5))
            p.drawLine(QPointF(cx - gap, y + sign * step), QPointF(cx - 2, y + sign * (step - 6)))
            p.drawLine(QPointF(cx + gap, y + sign * step), QPointF(cx + 2, y + sign * (step - 6)))
            p.setPen(QPen(cyan, 1.5))
            p.drawLine(QPointF(left, y - 8), QPointF(left, y + 8))
            p.drawLine(QPointF(right, y - 8), QPointF(right, y + 8))

        rail(y_top, False)
        rail(y_bot, True)

"""Cinematic AR overlay — smooth holograms, gestures, audio, webs, biometrics."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QFont,
    QRadialGradient,
    QPainterPath,
    QLinearGradient,
)
from PyQt6.QtWidgets import QWidget, QPushButton

from jarvis.core.aerospatial import AerospatialMapper, SpatialMesh, SETUP_GUIDE, lerp, lerp2
from jarvis.core.gestures import GestureState

CYAN = QColor(0, 229, 255)
AMBER = QColor(255, 180, 40)
GREEN = QColor(57, 255, 120)
RED = QColor(255, 70, 90)


@dataclass
class WebBolt:
    x: float
    y: float
    vx: float
    vy: float
    life: float = 1.0
    hits: list[tuple[float, float]] = field(default_factory=list)


class AerospatialOverlay(QWidget):
    closed = pyqtSignal()
    status = pyqtSignal(str)
    biometric_done = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

        self.mapper = AerospatialMapper()
        self._mesh = SpatialMesh()
        self._gesture = GestureState()
        self._t0 = time.time()
        self._last_tick = time.time()
        self._open = False
        self._pulse = 0.0
        self._webs: list[WebBolt] = []
        self._bio_t = -1.0  # <0 idle; 0..1 scanning
        self._bio_done = False
        self._bio_ok = False
        self._last_web = 0.0
        self._audio_at = 0.0
        self._yaw_vis = 0.0
        self._scale_vis = 1.0
        self._g_cursor = (0.5, 0.5)
        self._g_depth = 0.35
        self._last_frame = None

        self._btn_close = QPushButton("CLOSE AR", self)
        self._btn_scan = QPushButton("LASER SCAN", self)
        self._btn_mode = QPushButton("DEPLOY · DESKTOP", self)
        self._btn_cine = QPushButton("CINEMATIC", self)
        for b in (self._btn_close, self._btn_scan, self._btn_mode, self._btn_cine):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background:rgba(0,30,45,190);color:#9eecff;border:1px solid #00c8e0;"
                "padding:5px 12px;font:600 10px 'Segoe UI';border-radius:2px;}"
                "QPushButton:hover{background:rgba(0,70,95,230);}"
            )
        self._btn_close.clicked.connect(self.close_ar)
        self._btn_scan.clicked.connect(self.start_laser)
        self._btn_mode.clicked.connect(self._cycle_deploy)
        self._btn_cine.clicked.connect(self._toggle_cine)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def is_ar_open(self) -> bool:
        return self._open and self.isVisible()

    def open_ar(self) -> None:
        self._open = True
        self.mapper.state.enabled = True
        self.mapper.apply_pro_profile()
        self.mapper.push_log("AR ENGINE · pro cinematic mesh online")
        self.mapper.save()
        self._bio_t = 0.0 if self.mapper.state.biometric_scan else -1.0
        self._bio_done = False
        self._bio_ok = False
        self._sync_btns()
        self.show()
        self.raise_()
        fps = max(24, int(self.mapper.state.target_fps or 30))
        self._timer.start(int(1000 / fps))
        self.status.emit(self.mapper.status())
        self._play_hum(0.10, pan=0.0)
        self.update()

    def close_ar(self) -> None:
        self._open = False
        self.mapper.state.enabled = False
        self.mapper.state.laser_active = False
        self.mapper.save()
        self._timer.stop()
        self.hide()
        self.closed.emit()
        self.status.emit("Aerospatial offline")

    def start_laser(self) -> None:
        msg = self.mapper.start_laser()
        self.status.emit(msg)
        self._play_sfx("whoosh")
        self.update()

    def set_deploy(self, mode: str) -> str:
        msg = self.mapper.set_deploy(mode)
        self._sync_btns()
        self.status.emit(msg)
        self.update()
        return msg

    def set_cinematic(self, on: bool = True) -> str:
        msg = self.mapper.set_cinematic(on)
        self._sync_btns()
        self.status.emit(msg)
        return msg

    def trigger_biometric(self) -> None:
        self._bio_t = 0.0
        self._bio_done = False
        self.status.emit("Biometric scan — align with reticle")

    def ingest_frame(self, frame_bgr: Any) -> None:
        if not self._open:
            return
        self._last_frame = frame_bgr
        self._mesh = self.mapper.process_frame(frame_bgr)
        # Match timer to camera cadence
        if self.mapper.state.match_camera_fps and self._timer.isActive():
            fps = max(24, int(self._mesh.fps_est or 30))
            ms = int(1000 / fps)
            if abs(self._timer.interval() - ms) > 4:
                self._timer.setInterval(ms)

    def on_gesture(self, state: GestureState) -> None:
        self._gesture = state or GestureState()
        if not state or not state.active:
            return
        # EMA cursor — kills hand twitch feeding the hologram
        self._g_cursor = lerp2(self._g_cursor, state.cursor, 0.22)
        self._g_depth = lerp(self._g_depth, float(state.depth or 0.35), 0.2)
        st = self.mapper.state
        # Pinch = scale hologram
        if state.pinch:
            st.fab_scale = max(0.55, min(1.85, 0.7 + self._g_depth * 1.1))
        # Swipe = rotate
        if state.swipe == "left":
            st.fab_yaw -= 0.35
            self._play_sfx("whoosh")
        elif state.swipe == "right":
            st.fab_yaw += 0.35
            self._play_sfx("whoosh")
        elif state.swipe == "up":
            st.fab_scale = min(1.85, st.fab_scale + 0.08)
        elif state.swipe == "down":
            st.fab_scale = max(0.55, st.fab_scale - 0.08)
        # Fist push → laser
        if state.label == "fist" and self._g_depth > 0.58 and not st.laser_active:
            self.start_laser()
        # Web shooter pose
        if st.web_shooter and state.label == "web_shooter":
            self._fire_web(state)

    def _fire_web(self, state: GestureState) -> None:
        now = time.time()
        if now - self._last_web < 0.45:
            return
        self._last_web = now
        x, y = self._g_cursor
        # Shoot toward desk / mesh center
        tx, ty = self.mapper.fab_smoothed
        vx = (tx - x) * 1.8 + 0.15
        vy = (ty - y) * 1.8 - 0.05
        self._webs.append(WebBolt(x=x, y=y, vx=vx, vy=vy, life=1.0))
        self._play_sfx("zap")
        self.status.emit("Web shooter — projectile locked to room mesh")

    def _cycle_deploy(self) -> None:
        order = ("desktop", "mirror", "phone")
        cur = self.mapper.state.deploy
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "desktop"
        self.set_deploy(nxt)

    def _toggle_cine(self) -> None:
        self.set_cinematic(not self.mapper.state.cinematic)

    def _sync_btns(self) -> None:
        d = (self.mapper.state.deploy or "desktop").upper()
        self._btn_mode.setText(f"DEPLOY · {d}")
        self._btn_cine.setText(
            "CINEMATIC · ON" if self.mapper.state.cinematic else "CINEMATIC · OFF"
        )

    def _verify_owner(self) -> bool:
        """Match live frame against enrolled owner face when available."""
        frame = self._last_frame
        if frame is None:
            return True  # no frame yet — don't block
        try:
            from jarvis.config import DATA_DIR
            from jarvis.core.security_gate import SecurityGate
            import tempfile
            from pathlib import Path
            import cv2

            gate = SecurityGate(DATA_DIR, user_name="Sir")
            if not gate.enroll_path.exists():
                return True
            tmp = Path(tempfile.gettempdir()) / "jarvis_ar_bio.jpg"
            cv2.imwrite(str(tmp), frame)
            score = gate.match_score(str(tmp))
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            if score < 0:
                return True
            return score >= getattr(gate, "OWNER_SCORE", 0.36)
        except Exception:
            return True

    def _play_sfx(self, name: str) -> None:
        try:
            from jarvis.ui import hud_sfx

            fn = {
                "whoosh": getattr(hud_sfx, "play_whoosh", None),
                "zap": getattr(hud_sfx, "play", None),
                "confirm": getattr(hud_sfx, "play_confirm", None),
                "click": getattr(hud_sfx, "play_click", None),
            }.get(name)
            if name == "zap" and callable(fn):
                fn("zap")
            elif callable(fn):
                fn()
        except Exception:
            pass

    def _play_hum(self, vol: float, pan: float = 0.0) -> None:
        if not self.mapper.state.spatial_audio:
            return
        now = time.time()
        if now - self._audio_at < 0.35:
            return
        self._audio_at = now
        try:
            from jarvis.ui.hud_sfx import play_hum

            play_hum(volume=max(0.04, min(0.35, vol)), pan=pan)
        except Exception:
            pass

    def _tick(self) -> None:
        now = time.time()
        dt = max(0.001, min(0.08, now - self._last_tick))
        self._last_tick = now
        self._pulse = (now - self._t0) * 2.0
        self.mapper.tick_fab_lerp(dt)
        self._yaw_vis = lerp(self._yaw_vis, self.mapper.state.fab_yaw, 0.12)
        self._scale_vis = lerp(self._scale_vis, self.mapper.state.fab_scale, 0.14)

        # Web physics
        alive: list[WebBolt] = []
        desk = self._mesh.desk
        for w in self._webs:
            w.x += w.vx * dt
            w.y += w.vy * dt
            w.vy += 0.35 * dt  # gravity toward desk plane
            w.life -= dt * 0.55
            if desk and abs(w.x - desk.cx) < desk.w * 0.6 and abs(w.y - desk.cy) < desk.h * 1.2:
                w.hits.append((w.x, w.y))
                w.vx *= 0.3
                w.vy *= -0.2
            if w.life > 0 and 0.0 <= w.x <= 1.0 and -0.1 <= w.y <= 1.1:
                alive.append(w)
        self._webs = alive[-12:]

        # Biometric scan
        if 0.0 <= self._bio_t < 1.0:
            self._bio_t = min(1.0, self._bio_t + dt * 0.48)
            if self._bio_t >= 1.0 and not self._bio_done:
                self._bio_done = True
                self._bio_ok = self._verify_owner()
                self._play_sfx("confirm" if self._bio_ok else "click")
                if self._bio_ok:
                    self.biometric_done.emit("welcome_back")
                    self.status.emit("Welcome back, boss — AR unlocked")
                else:
                    self.status.emit("Biometrics unsure — face the camera or say enroll my face")

        # Spatial audio — louder near hand, pan with laser
        if self.mapper.state.spatial_audio and self._gesture.active:
            fx, fy = self.mapper.fab_smoothed
            gx, gy = self._g_cursor
            dist = math.hypot(fx - gx, fy - gy)
            vol = 0.06 + 0.18 * max(0.0, 1.0 - dist * 1.6)
            pan = (self.mapper.state.laser_y - 0.5) * 1.6 if self.mapper.state.laser_active else (fx - 0.5) * 1.4
            self._play_hum(vol, pan=pan)

        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._btn_close.move(max(12, self.width() - 118), 12)
        self._btn_scan.move(max(12, self.width() - 248), 12)
        self._btn_cine.move(max(12, self.width() - 400), 12)
        self._btn_mode.move(16, 12)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._open:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        st = self.mapper.state
        mesh = self._mesh

        # Soft vignette
        vig = QRadialGradient(w * 0.5, h * 0.42, max(w, h) * 0.75)
        vig.setColorAt(0.0, QColor(0, 18, 32, 12))
        vig.setColorAt(0.7, QColor(0, 8, 18, 36))
        vig.setColorAt(1.0, QColor(0, 0, 0, 120))
        p.fillRect(0, 0, w, h, vig)

        self._draw_mesh(p, w, h, mesh)
        self._draw_planes(p, w, h, mesh)
        self._draw_floor_shadow(p, w, h, mesh, st)
        self._draw_fabricator(p, w, h, mesh, st)
        if st.laser_active or st.laser_y > 0.02:
            self._draw_laser(p, w, h, mesh, st)
        self._draw_webs(p, w, h)
        if st.pc_gauges:
            self._draw_pc_gauges(p, w, h)
        self._draw_chromatic(p, w, h, st)
        if st.occlusion:
            self._draw_occlusion(p, w, h)
        if 0.0 <= self._bio_t <= 1.0:
            self._draw_biometric(p, w, h)
        self._draw_hud(p, w, h, st, mesh)
        # Tracking assist tip
        if mesh.texture_score < 0.28:
            p.setPen(AMBER)
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            p.drawText(
                16,
                h - 48,
                "LOW TEXTURE — add a patterned mousepad / ArUco marker on the desk",
            )
        p.end()

    def _draw_mesh(self, p: QPainter, w: int, h: int, mesh: SpatialMesh) -> None:
        if not mesh.nodes:
            return
        alpha = int(55 + 35 * abs(math.sin(self._pulse * 0.35)))
        p.setPen(QPen(QColor(0, 210, 240, alpha), 1.1))
        pts = [(n.x * w, n.y * h) for n in mesh.nodes]
        for a, b in mesh.edges:
            if a < len(pts) and b < len(pts):
                p.drawLine(QPointF(*pts[a]), QPointF(*pts[b]))

    def _draw_planes(self, p: QPainter, w: int, h: int, mesh: SpatialMesh) -> None:
        for pl in mesh.planes:
            color = {
                "desk": QColor(0, 255, 200, 40),
                "floor": QColor(70, 140, 255, 28),
                "wall": QColor(255, 70, 190, 28),
                "furniture": QColor(255, 200, 60, 36),
                "marker": QColor(255, 255, 120, 70),
            }.get(pl.kind, QColor(0, 200, 255, 24))
            rect = QRectF(
                (pl.cx - pl.w / 2) * w,
                (pl.cy - pl.h / 2) * h,
                pl.w * w,
                pl.h * h,
            )
            p.fillRect(rect, color)
            p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 150), 1.2))
            p.drawRect(rect)
            if pl.label:
                p.setPen(QColor(220, 250, 255, 170))
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
                p.drawText(rect.adjusted(4, 2, -4, -2), Qt.AlignmentFlag.AlignLeft, pl.label)

    def _draw_floor_shadow(
        self, p: QPainter, w: int, h: int, mesh: SpatialMesh, st: Any
    ) -> None:
        fx, fy = self.mapper.fab_smoothed
        desk = mesh.desk
        sy = (desk.cy if desk else fy + 0.12) * h
        sx = fx * w
        g = QRadialGradient(sx, sy, 90 * self._scale_vis)
        g.setColorAt(0.0, QColor(0, 0, 0, int(90 * st.bloom)))
        g.setColorAt(0.55, QColor(0, 40, 60, int(40 * st.bloom)))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(g)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(sx, sy), 95 * self._scale_vis, 28 * self._scale_vis)

    def _draw_fabricator(
        self, p: QPainter, w: int, h: int, mesh: SpatialMesh, st: Any
    ) -> None:
        fx, fy = self.mapper.fab_smoothed
        cx, cy = fx * w, fy * h
        scale = max(60.0, min(w, h) * 0.16) * self._scale_vis
        yaw = self._yaw_vis

        bloom = st.bloom * (0.75 + 0.25 * mesh.light_lux)
        glow = QRadialGradient(cx, cy, scale * 1.85)
        glow.setColorAt(0.0, QColor(0, 255, 255, int(85 * bloom)))
        glow.setColorAt(0.4, QColor(0, 160, 255, int(45 * bloom)))
        glow.setColorAt(1.0, QColor(0, 40, 80, 0))
        p.setBrush(glow)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), scale * 1.55, scale * 1.05)

        def rot(px: float, py: float) -> QPointF:
            dx, dy = px - cx, py - cy
            c, s = math.cos(yaw), math.sin(yaw)
            return QPointF(cx + dx * c - dy * s, cy + dx * s + dy * c)

        path = QPainterPath()
        pts = [
            (-0.7, 0.35),
            (-0.55, -0.55),
            (0.0, -0.85),
            (0.55, -0.55),
            (0.7, 0.35),
        ]
        path.moveTo(rot(cx + pts[0][0] * scale, cy + pts[0][1] * scale))
        for px, py in pts[1:]:
            path.lineTo(rot(cx + px * scale, cy + py * scale))
        path.closeSubpath()

        pulse = 0.5 + 0.5 * math.sin(self._pulse)
        p.fillPath(path, QColor(0, 229, 255, int(30 + 35 * pulse * bloom)))
        p.setPen(QPen(QColor(0, 255, 255, int(170 + 50 * pulse)), 2.0))
        p.drawPath(path)
        # Chromatic fringes
        p.setPen(QPen(QColor(255, 40, 180, int(70 * st.chromatic)), 1.0))
        p.drawPath(path.translated(2.2, 0))
        p.setPen(QPen(QColor(40, 255, 180, int(60 * st.chromatic)), 1.0))
        p.drawPath(path.translated(-1.8, 0))

        p.setBrush(QColor(180, 255, 255, int(150 + 70 * pulse)))
        p.setPen(QPen(CYAN, 1.4))
        p.drawEllipse(rot(cx, cy - scale * 0.15), scale * 0.11, scale * 0.11)

        p.setPen(QColor(200, 255, 255, 200))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(
            QRectF(cx - scale, cy + scale * 0.42, scale * 2, 20),
            Qt.AlignmentFlag.AlignCenter,
            "JARVIS FABRICATOR",
        )
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor(140, 220, 240, 150))
        lock = "MARKER" if mesh.marker else "DESK"
        p.drawText(
            QRectF(cx - scale, cy + scale * 0.56, scale * 2, 16),
            Qt.AlignmentFlag.AlignCenter,
            f"LERP LOCK · {lock} · SCALE {self._scale_vis:.2f}",
        )

    def _draw_laser(self, p: QPainter, w: int, h: int, mesh: SpatialMesh, st: Any) -> None:
        y = st.laser_y * h
        p.setPen(QPen(QColor(255, 70, 100, 90), 6))
        p.drawLine(QPointF(0, y), QPointF(w, y))
        p.setPen(QPen(QColor(255, 220, 230, 210), 1.8))
        p.drawLine(QPointF(0, y), QPointF(w, y))
        for tx, ty in mesh.laser_targets:
            hx, hy = tx * w, ty * h
            if abs(hy - y) < h * 0.07:
                g = QRadialGradient(hx, hy, 26)
                g.setColorAt(0, QColor(255, 255, 210, 200))
                g.setColorAt(0.45, QColor(255, 90, 50, 100))
                g.setColorAt(1, QColor(255, 0, 0, 0))
                p.setBrush(g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(hx, hy), 20, 12)

    def _draw_webs(self, p: QPainter, w: int, h: int) -> None:
        for bolt in self._webs:
            p.setPen(QPen(QColor(200, 230, 255, int(220 * bolt.life)), 2.2))
            x0, y0 = bolt.x * w, bolt.y * h
            x1 = (bolt.x - bolt.vx * 0.08) * w
            y1 = (bolt.y - bolt.vy * 0.08) * h
            p.drawLine(QPointF(x1, y1), QPointF(x0, y0))
            # Web strands
            for i in range(3):
                ang = self._pulse + i * 2.1
                p.setPen(QPen(QColor(160, 200, 255, int(100 * bolt.life)), 1))
                p.drawLine(
                    QPointF(x0, y0),
                    QPointF(x0 + math.cos(ang) * 18, y0 + math.sin(ang) * 18),
                )

    def _draw_pc_gauges(self, p: QPainter, w: int, h: int) -> None:
        tele = self.mapper.refresh_telemetry()
        items = [
            ("CPU", tele.cpu, CYAN),
            ("RAM", tele.ram, GREEN),
            ("GPU", tele.gpu, AMBER),
            ("TEMP", min(100.0, tele.temp_c), RED),
            ("FAN", tele.fan, QColor(180, 140, 255)),
        ]
        x0, y0 = w - 150, 56
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        for i, (name, val, col) in enumerate(items):
            y = y0 + i * 36
            # Rotating ring
            rect = QRectF(x0, y, 28, 28)
            p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 60), 3))
            p.drawEllipse(rect)
            span = int(max(5, min(270, val * 2.7)))
            p.setPen(QPen(col, 3))
            p.drawArc(rect, int((self._pulse * 40 + i * 30) * 16), -span * 16)
            p.setPen(QColor(200, 240, 255, 200))
            p.drawText(x0 + 36, y + 18, f"{name} {val:.0f}")

    def _draw_chromatic(self, p: QPainter, w: int, h: int, st: Any) -> None:
        a = int(14 * st.chromatic)
        if a < 2:
            return
        p.setPen(QPen(QColor(0, 255, 255, a), 1))
        step = 5
        off = int(self._pulse * 6) % step
        for y in range(off, h, step * 4):
            p.drawLine(0, y, w, y)
        p.setPen(QPen(CYAN, 2))
        m = 16
        for x0, y0, sx, sy in (
            (m, m + 36, 1, 1),
            (w - m, m + 36, -1, 1),
            (m, h - m, 1, -1),
            (w - m, h - m, -1, -1),
        ):
            p.drawLine(x0, y0, x0 + sx * 26, y0)
            p.drawLine(x0, y0, x0, y0 + sy * 26)

    def _draw_occlusion(self, p: QPainter, w: int, h: int) -> None:
        g = self._gesture
        if not g.active:
            return
        cx, cy = self._g_cursor[0] * w, self._g_cursor[1] * h
        depth = float(self._g_depth or 0.35)
        rad = 36 + depth * 85
        oc = QRadialGradient(cx, cy, rad)
        oc.setColorAt(0.0, QColor(0, 0, 0, int(130 * depth)))
        oc.setColorAt(0.55, QColor(0, 0, 0, int(50 * depth)))
        oc.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(oc)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), rad, rad * 1.1)

    def _draw_biometric(self, p: QPainter, w: int, h: int) -> None:
        t = self._bio_t
        cx, cy = w * 0.5, h * 0.38
        rad = 90 + 20 * math.sin(self._pulse)
        p.setPen(QPen(QColor(0, 255, 200, int(180 * (1 - abs(t - 0.5)))), 2))
        p.drawEllipse(QPointF(cx, cy), rad, rad * 1.15)
        # Scan line
        sy = cy - rad + (2 * rad) * t
        grad = QLinearGradient(cx - rad, sy, cx + rad, sy)
        grad.setColorAt(0, QColor(0, 255, 200, 0))
        grad.setColorAt(0.5, QColor(0, 255, 220, 200))
        grad.setColorAt(1, QColor(0, 255, 200, 0))
        p.setPen(QPen(QColor(0, 255, 220, 220), 2))
        p.drawLine(QPointF(cx - rad, sy), QPointF(cx + rad, sy))
        # Eye reticles
        for dx in (-28, 28):
            p.drawRect(QRectF(cx + dx - 10, cy - 8, 20, 14))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.setPen(QColor(180, 255, 240, 220))
        msg = (
            "IDENTITY LOCK"
            if t < 1
            else ("WELCOME BACK, BOSS" if self._bio_ok else "ALIGN FACE · RETRY")
        )
        p.drawText(QRectF(cx - 140, cy + rad + 8, 280, 24), Qt.AlignmentFlag.AlignCenter, msg)

    def _draw_hud(self, p: QPainter, w: int, h: int, st: Any, mesh: SpatialMesh) -> None:
        p.setPen(QColor(180, 240, 255, 220))
        p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        p.drawText(16, 48, "AR AEROSPATIAL · CINEMATIC")
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(140, 200, 220, 180))
        q = int(st.mesh_quality * 100)
        p.drawText(
            16,
            66,
            f"MESH {q}% · LIGHT {mesh.light_lux:.0%} · TEX {mesh.texture_score:.0%} · "
            f"{mesh.fps_est:.0f}fps · LERP α{st.smooth_alpha:.2f} · "
            f"{'AUDIO' if st.spatial_audio else 'MUTE'}",
        )
        hints = {
            "desktop": "Desktop webcam overlay — mount cam firmly, match 30fps",
            "mirror": "Smart mirror — 45° glass · monitor below",
            "phone": "Phone AR Foundation — tap to place fabricator",
        }
        p.drawText(16, h - 14, hints.get(st.deploy, ""))
        p.setPen(GREEN if mesh.desk else AMBER)
        if mesh.desk:
            p.drawText(
                16,
                h - 30,
                f"DESK LOCK {mesh.desk.confidence:.0%} · pinch scale · swipe rotate · "
                f"fist laser · web-shooter flick",
            )


def aerospatial_setup_text() -> str:
    return SETUP_GUIDE

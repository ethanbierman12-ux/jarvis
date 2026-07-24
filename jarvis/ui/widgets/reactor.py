"""Central holographic JARVIS core — amber mesh sphere with command-reactive motion."""

from __future__ import annotations

import math
import random
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QRadialGradient,
    QBrush,
    QFont,
    QPainterPath,
)
from PyQt6.QtWidgets import QWidget


# Amber / gold palette from the reference core
_GOLD = QColor(255, 196, 72)
_AMBER = QColor(255, 158, 42)
_HOT = QColor(255, 230, 140)
_DIM = QColor(120, 70, 22)

# Panic / threat palette
_PANIC_GOLD = QColor(255, 48, 48)
_PANIC_AMBER = QColor(220, 24, 24)
_PANIC_HOT = QColor(255, 120, 100)
_PANIC_DIM = QColor(90, 12, 12)

# Travis persona accents (Park gold / Tactical green / Peer blue)
_TRAVIS_ACCENTS = {
    "park": QColor(255, 200, 72),
    "tactical": QColor(26, 255, 122),
    "peer": QColor(42, 107, 255),
    "peer_review": QColor(42, 107, 255),
}


class ArcReactor(QWidget):
    """
    Living holographic core:
      - multi-layer rotating mesh sphere (amber/gold)
      - HUD frame bars + corner gauge
      - intensifies on speak / build / fetch / away
      - turns crimson in panic mode
    """

    node_activated = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._a = self._a2 = self._a3 = 0.0
        self._pulse = 0.0
        self._speak = 0.0
        self._flare = 0.0
        self._amp = 0.0
        self._activity = "idle"  # idle|listen|speak|build|fetch|away|panic
        self._activity_boost = 0.0
        self._speaking_locked = False
        self._parallax = (0.0, 0.0)
        self._hover: Optional[str] = None
        self._hits: list[tuple[str, QRectF]] = []
        self._fps = 66  # ~15 FPS paint (was 28ms ≈ 36 FPS)
        self._accent = QColor(0, 240, 255)  # spokes / weather tint
        self._panic = False
        self._travis_mode = ""  # park | tactical | peer | ""
        self._seed = random.Random(42)
        self._particles = self._make_particles(64)  # was 220
        self._spikes = self._make_spikes(24)  # was 48
        self._nodes = [
            {"label": "Images", "angle": 200, "cmd": "open pictures", "side": "L"},
            {"label": "Documents", "angle": 225, "cmd": "open documents", "side": "L"},
            {"label": "Downloads", "angle": 250, "cmd": "open downloads", "side": "L"},
            {"label": "Map", "angle": 275, "cmd": "open map view", "side": "L"},
            {"label": "Camera", "angle": 300, "cmd": "open camera", "side": "L"},
            {"label": "Gmail", "angle": -20, "cmd": "open gmail", "side": "R"},
            {"label": "YouTube", "angle": 5, "cmd": "open youtube", "side": "R"},
            {"label": "Spotify", "angle": 30, "cmd": "open spotify", "side": "R"},
            {"label": "Chrome", "angle": 55, "cmd": "open chrome", "side": "R"},
            {"label": "Search", "angle": 80, "cmd": "pull up the news", "side": "R"},
        ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._fps)

    # ── public API ──────────────────────────────────────────────
    def set_target_fps(self, fps: int) -> None:
        # fps = frames/sec → timer interval ms
        self._fps = max(50, min(120, int(1000 / max(8, fps))))
        self._timer.setInterval(self._fps)

    def set_amplitude(self, amp: float) -> None:
        self._amp = max(0.0, min(1.0, float(amp)))

    def set_weather_accent(self, hex_color: str) -> None:
        c = QColor(hex_color)
        if c.isValid():
            if not self._panic and not self._travis_mode:
                self._accent = c
            self.update()

    def set_panic(self, on: bool) -> None:
        """Crimson core for panic / privacy threat mode."""
        on = bool(on)
        if on == self._panic:
            if on:
                self._flare = max(self._flare, 1.0)
                self._activity_boost = max(self._activity_boost, 1.0)
            self.update()
            return
        self._panic = on
        if on:
            self._accent = QColor(255, 40, 40)
            self._flare = 1.0
            self._activity = "panic"
            self._activity_boost = 1.0
        else:
            self._restore_accent()
            if self._activity == "panic":
                self._activity = "idle"
                self._activity_boost = 0.0
        self.update()

    def set_travis_mode(self, mode: str) -> None:
        """Park (gold) / Tactical (green) / Peer Review (blue) persona sync."""
        mode = (mode or "").strip().lower().replace("-", "_")
        if mode in ("peer_review", "review"):
            mode = "peer"
        if mode in ("off", "clear", "none", "jarvis"):
            mode = ""
        self._travis_mode = mode if mode in _TRAVIS_ACCENTS else ""
        if not self._panic:
            self._restore_accent()
        if self._travis_mode:
            self._flare = max(self._flare, 0.55)
            self._activity_boost = max(self._activity_boost, 0.4)
        self.update()

    def _restore_accent(self) -> None:
        if self._travis_mode and self._travis_mode in _TRAVIS_ACCENTS:
            self._accent = QColor(_TRAVIS_ACCENTS[self._travis_mode])
        else:
            self._accent = QColor(0, 240, 255)

    def pulse_speak(self) -> None:
        self._speak = 1.0
        self._flare = max(self._flare, 0.85)
        self.set_activity("speak")

    def set_speaking(self, active: bool) -> None:
        """Lock the core in a talking state for the whole TTS clip."""
        self._speaking_locked = bool(active)
        if active:
            self._speak = 1.0
            self._flare = max(self._flare, 0.9)
            self.set_activity("speak")
            self._amp = max(self._amp, 0.55)
        else:
            self._speak = max(self._speak, 0.35)
        self.update()

    def flare(self, strength: float = 1.0) -> None:
        self._flare = max(self._flare, min(1.0, float(strength)))

    def set_activity(self, mode: str) -> None:
        """idle | listen | speak | build | fetch | away | panic | park | tactical | peer"""
        mode = (mode or "idle").lower()
        if self._panic and mode != "panic":
            # Stay in panic visuals until cleared
            self._activity = "panic"
            self._activity_boost = 1.0
            self.update()
            return
        self._activity = mode
        boosts = {
            "idle": 0.0,
            "listen": 0.25,
            "speak": 0.55,
            "fetch": 0.7,
            "away": 0.65,
            "build": 1.0,
            "vibe": 0.95,
            "site": 1.0,
            "panic": 1.0,
            "park": 0.5,
            "tactical": 0.85,
            "peer": 0.6,
        }
        self._activity_boost = boosts.get(mode, 0.35)
        if mode in ("build", "site", "vibe", "away", "fetch", "panic", "tactical"):
            self._flare = max(self._flare, 0.7)
        self.update()

    def set_parallax(self, x: float, y: float) -> None:
        self._parallax = ((x - 0.5) * 16.0, (y - 0.5) * 12.0)

    def _c(self, r: int, g: int, b: int, a: int = 255) -> QColor:
        """Map amber/gold → crimson while panic; tint toward Travis accent."""
        if self._panic:
            # Keep heat, crush green/blue into red threat tone
            return QColor(
                min(255, max(r, 200) + 20),
                max(0, min(90, g // 4 + 10)),
                max(0, min(70, b // 5)),
                a,
            )
        tm = self._travis_mode
        if tm == "tactical":
            # Pull toward pulsed green
            return QColor(
                max(0, min(120, r // 3)),
                min(255, max(g, 180) + 40),
                max(0, min(140, b // 2 + 40)),
                a,
            )
        if tm == "peer":
            # Arc-vector blue
            return QColor(
                max(0, min(100, r // 3)),
                max(40, min(160, g // 2 + 40)),
                min(255, max(b, 200) + 30),
                a,
            )
        if tm == "park":
            # Warm bright gold (default core, slightly hotter)
            return QColor(
                min(255, max(r, 220)),
                min(255, max(g, 170)),
                max(0, min(90, b // 2)),
                a,
            )
        return QColor(r, g, b, a)

    # ── internals ───────────────────────────────────────────────
    def _make_particles(self, n: int) -> list[tuple]:
        """Spherical particle distribution: x,y,z,layer,size."""
        out = []
        rnd = self._seed
        for i in range(n):
            y = 1.0 - (i / max(1, n - 1)) * 2.0
            radius = math.sqrt(max(0.0, 1.0 - y * y))
            theta = math.pi * (1 + 5**0.5) * i
            x = math.cos(theta) * radius
            z = math.sin(theta) * radius
            x += rnd.uniform(-0.04, 0.04)
            y += rnd.uniform(-0.04, 0.04)
            z += rnd.uniform(-0.04, 0.04)
            layer = rnd.choice((0.72, 0.86, 1.0, 1.12))
            size = rnd.uniform(0.7, 2.2)
            out.append((x, y, z, layer, size))
        return out

    def _make_spikes(self, n: int) -> list[tuple[float, float, float]]:
        rnd = self._seed
        out = []
        for _ in range(n):
            ang = rnd.uniform(0, math.tau)
            elev = rnd.uniform(-0.7, 0.7)
            length = rnd.uniform(0.08, 0.28)
            out.append((ang, elev, length))
        return out

    def _tick(self) -> None:
        boost = 1.0 + self._activity_boost * 1.8 + self._speak * 0.9 + self._flare * 0.6
        if self._speaking_locked:
            boost += 0.85
        self._a = (self._a + 0.42 * boost) % 360
        self._a2 = (self._a2 - 0.28 * boost) % 360
        self._a3 = (self._a3 + 0.18 * boost) % 360
        self._pulse = (self._pulse + 0.045 + 0.03 * self._activity_boost) % (2 * math.pi)
        if self._speaking_locked:
            # Hold speech energy — amp comes from TTS envelope via set_amplitude
            self._speak = max(0.75, self._speak)
            self._flare = max(0.45, self._flare)
            self._activity = "speak"
            self._activity_boost = max(0.7, self._activity_boost)
            if self._amp < 0.25:
                # Fallback pulse if audio envelope hasn't arrived yet
                self._amp = 0.4 + 0.35 * abs(math.sin(self._pulse * 3.2))
        elif self._speak > 0:
            self._speak = max(0.0, self._speak - 0.018)
        if self._flare > 0 and not self._speaking_locked:
            self._flare = max(0.0, self._flare - 0.022)
        # Transient modes ease back once energy drains (panic stays locked)
        if self._panic:
            self._activity = "panic"
            self._activity_boost = max(0.85, self._activity_boost)
            self._flare = max(0.35, self._flare)
        elif self._speaking_locked:
            pass
        elif self._activity in ("speak", "fetch", "listen") and self._speak < 0.05 and self._flare < 0.08:
            self._activity_boost *= 0.96
            if self._activity_boost < 0.04:
                self._activity = "idle"
                self._activity_boost = 0.0
        elif self._activity == "idle":
            self._activity_boost *= 0.985
        # Soften amplitude so waves ease down when quiet
        if self._speaking_locked:
            # Light smoothing only — keep the talk pulse alive
            if self._amp > 0.01:
                self._amp = self._amp * 0.82 + 0.18 * self._amp
        elif self._amp > 0.01:
            self._amp *= 0.92
        else:
            self._amp = 0.0
        # Idle: paint every other tick (~7–8 FPS) — still alive, less GPU thrash
        idle = (
            self._activity == "idle"
            and not self._speaking_locked
            and not self._panic
            and self._amp < 0.03
            and self._flare < 0.08
            and self._activity_boost < 0.05
        )
        if idle:
            self._idle_skip = getattr(self, "_idle_skip", 0) + 1
            if self._idle_skip % 2:
                return
        else:
            self._idle_skip = 0
        self.update()

    def mouseMoveEvent(self, e) -> None:
        pos = e.position()
        hit = next((lab for lab, r in self._hits if r.contains(pos)), None)
        if hit != self._hover:
            self._hover = hit
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor
            )

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position()
        for lab, r in self._hits:
            if r.contains(pos):
                for n in self._nodes:
                    if n["label"] == lab:
                        self.pulse_speak()
                        self._hover = lab
                        self.update()
                        self.node_activated.emit(n["cmd"])
                        return

    # ── paint ───────────────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        cx = w / 2 + self._parallax[0]
        cy = h / 2 + self._parallax[1]
        energy = (
            1.0
            + 0.04 * math.sin(self._pulse)
            + 0.10 * self._amp
            + 0.12 * self._speak
            + 0.14 * self._flare
            + 0.08 * self._activity_boost
        )
        base = min(w, h) * 0.30 * energy

        bloom = QRadialGradient(cx, cy, base * 2.1)
        bloom.setColorAt(0.0, self._c(255, 180, 60, int(55 + 40 * self._flare)))
        bloom.setColorAt(0.25, self._c(255, 140, 30, int(28 + 20 * self._activity_boost)))
        bloom.setColorAt(0.55, self._c(80, 40, 10, 12))
        bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bloom))
        p.drawEllipse(QPointF(cx, cy), base * 2.0, base * 2.0)

        self._draw_hud_frame(p, w, h, cx, cy, base)
        self._draw_mesh_sphere(p, cx, cy, base)
        self._draw_spikes(p, cx, cy, base)
        self._draw_arcs(p, cx, cy, base)
        self._draw_core(p, cx, cy, base)
        self._draw_title(p, cx, cy, base)
        self._draw_spokes(p, cx, cy, base)
        # Mic-reactive mathematical waves (synced to audio level)
        if self._amp > 0.02 or getattr(self, "_panic", False):
            p.setPen(QPen(self._c(255, 190, 70, int(50 + 140 * self._amp)), 1.4))
            path = QPainterPath()
            wave_w = base * 2.2
            x0 = cx - wave_w / 2
            y0 = cy + base * 1.72
            steps = 48
            for i in range(steps + 1):
                t = i / steps
                x = x0 + t * wave_w
                y = y0 + math.sin(t * math.pi * 6 + self._pulse * 3) * (
                    4 + 18 * self._amp
                ) * math.sin(math.pi * t)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.drawPath(path)

        p.end()

    def _draw_hud_frame(
        self, p: QPainter, w: float, h: float, cx: float, cy: float, base: float
    ) -> None:
        gold = self._c(255, 170, 50, 160)
        dim = self._c(255, 140, 40, 70)
        bar_w = min(w * 0.42, base * 2.4)
        for y, fill in (
            (cy - base * 1.55, 0.55 + 0.2 * self._activity_boost),
            (cy + base * 1.55, 0.4 + 0.3 * self._flare),
        ):
            x0 = cx - bar_w / 2
            p.setPen(QPen(dim, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(x0, y - 4, bar_w, 8))
            segs = 18
            seg_w = bar_w / segs
            p.setBrush(self._c(255, 170, 50, int(120 + 80 * fill)))
            p.setPen(Qt.PenStyle.NoPen)
            filled = int(segs * fill)
            for i in range(filled):
                p.drawRect(QRectF(x0 + i * seg_w + 1, y - 2.5, seg_w - 2, 5))

        p.setPen(QPen(gold, 1.2))
        bw, bh = base * 0.22, base * 0.55
        for sx in (cx - base * 1.45, cx + base * 1.45 - bw):
            path = QPainterPath()
            path.moveTo(sx, cy - bh)
            path.lineTo(sx + (bw if sx < cx else 0), cy - bh)
            path.moveTo(sx if sx < cx else sx + bw, cy - bh)
            path.lineTo(sx if sx < cx else sx + bw, cy + bh)
            path.lineTo(sx + (bw if sx < cx else 0), cy + bh)
            p.drawPath(path)

        gx, gy = cx + base * 1.25, cy + base * 1.25
        p.setPen(QPen(self._c(255, 170, 50, 140), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(gx, gy), 14, 14)
        p.setPen(QPen(self._c(255, 200, 80, 200), 2))
        p.drawArc(QRectF(gx - 10, gy - 10, 20, 20), int(self._a * 16), 90 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._c(255, 180, 60, 180))
        p.drawEllipse(QPointF(gx, gy), 3, 3)

        p.setPen(QPen(self._c(255, 150, 40, 50), 1))
        for i in range(36):
            ang = math.radians(i * 10 + self._a3)
            r0, r1 = base * 1.42, base * 1.48
            p.drawLine(
                QPointF(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0),
                QPointF(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
            )

    def _project(
        self, x: float, y: float, z: float, rot_y: float, rot_x: float
    ) -> tuple[float, float, float]:
        cy, sy = math.cos(rot_y), math.sin(rot_y)
        x1 = x * cy + z * sy
        z1 = -x * sy + z * cy
        cx, sx = math.cos(rot_x), math.sin(rot_x)
        y2 = y * cx - z1 * sx
        z2 = y * sx + z1 * cx
        return x1, y2, z2

    def _draw_mesh_sphere(self, p: QPainter, cx: float, cy: float, base: float) -> None:
        rot_y = math.radians(self._a)
        rot_x = math.radians(18 + 8 * math.sin(math.radians(self._a2)))
        rot_y2 = math.radians(self._a2)
        pts = []
        for x, y, z, layer, size in self._particles:
            ry = rot_y if layer >= 1.0 else rot_y2
            px, py, pz = self._project(x, y, z, ry, rot_x * 0.6)
            pts.append((pz, px * layer, py * layer, size, layer))
        pts.sort(key=lambda t: t[0])

        for pz, px, py, size, layer in pts:
            depth = (pz + 1.4) / 2.4
            alpha = int(max(18, min(230, 40 + depth * 190)))
            if self._flare > 0.2:
                alpha = min(255, alpha + int(50 * self._flare))
            r = base * 0.78
            sx = cx + px * r
            sy = cy + py * r
            if pz < -0.15:
                alpha = int(alpha * 0.45)
            sz = size * (0.7 + depth * 0.9) * (1.0 + 0.3 * self._activity_boost)
            color = self._c(255, int(160 + 60 * depth), int(40 + 50 * depth), alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(sx, sy), sz, sz)

        p.setPen(QPen(self._c(255, 170, 50, int(35 + 40 * self._activity_boost)), 0.8))
        bright = [t for t in pts if t[0] > 0.1][-40:]
        for i in range(0, len(bright) - 1, 3):
            _, x1, y1, _, _ = bright[i]
            _, x2, y2, _, _ = bright[min(i + 1, len(bright) - 1)]
            r = base * 0.78
            p.drawLine(
                QPointF(cx + x1 * r, cy + y1 * r),
                QPointF(cx + x2 * r, cy + y2 * r),
            )

        for layer_i, (mul, alpha) in enumerate(((1.05, 55), (0.9, 70), (0.75, 90))):
            p.setPen(QPen(self._c(255, 170, 50, alpha), 1.0 if layer_i else 1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rx = base * mul
            ry = base * mul * (0.55 + 0.1 * math.sin(math.radians(self._a3)))
            p.save()
            p.translate(cx, cy)
            p.rotate(self._a if layer_i % 2 == 0 else self._a2)
            p.drawEllipse(QPointF(0, 0), rx, ry)
            p.rotate(60)
            p.drawEllipse(QPointF(0, 0), rx * 0.92, ry * 1.05)
            p.restore()

    def _draw_spikes(self, p: QPainter, cx: float, cy: float, base: float) -> None:
        energy = 0.15 + 0.25 * self._flare + 0.2 * self._activity_boost
        for ang, elev, length in self._spikes:
            a = ang + math.radians(self._a * 0.4)
            x = math.cos(a) * math.cos(elev)
            y = math.sin(elev)
            if math.cos(a) * 0.3 + 0.2 < -0.3:
                continue
            r0 = base * 0.95
            r1 = base * (0.95 + length * (1.0 + energy))
            c0 = QPointF(cx + x * r0, cy + y * r0 * 0.85)
            c1 = QPointF(cx + x * r1, cy + y * r1 * 0.85)
            p.setPen(QPen(self._c(255, 180, 60, int(50 + 90 * energy)), 1.1))
            p.drawLine(c0, c1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._c(255, 210, 100, int(80 + 100 * energy)))
            p.drawEllipse(c1, 1.4, 1.4)

    def _draw_arcs(self, p: QPainter, cx: float, cy: float, base: float) -> None:
        p.save()
        p.translate(cx, cy)
        p.rotate(self._a)
        pen = QPen(self._c(255, 190, 70, 170), 2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        rect = QRectF(-base * 0.7, -base * 0.7, base * 1.4, base * 1.4)
        for start, span in ((8, 48), (78, 36), (138, 55), (228, 38), (298, 32)):
            p.drawArc(rect, start * 16, span * 16)
        p.restore()

        p.save()
        p.translate(cx, cy)
        p.rotate(self._a2)
        p.setPen(QPen(self._c(255, 150, 40, 110), 1.6))
        rect = QRectF(-base * 0.48, -base * 0.48, base * 0.96, base * 0.96)
        for i in range(20):
            if i % 3 == 0:
                continue
            p.drawArc(rect, int(i * 18 * 16), 10 * 16)
        p.restore()

    def _draw_core(self, p: QPainter, cx: float, cy: float, base: float) -> None:
        cr = base * (0.16 + 0.04 * self._speak + 0.05 * self._flare)
        g0 = QRadialGradient(cx, cy, cr * 3.2)
        g0.setColorAt(0.0, self._c(255, 220, 120, int(90 + 80 * self._flare)))
        g0.setColorAt(0.4, self._c(255, 160, 40, 40))
        g0.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g0))
        p.drawEllipse(QPointF(cx, cy), cr * 2.8, cr * 2.8)

        core = QRadialGradient(cx - cr * 0.25, cy - cr * 0.25, cr)
        if self._panic:
            core.setColorAt(0.0, QColor(255, 240, 230))
            core.setColorAt(0.25, QColor(255, 140, 100))
            core.setColorAt(0.55, QColor(255, 40, 40))
            core.setColorAt(1.0, QColor(120, 0, 0))
        else:
            core.setColorAt(0.0, QColor(255, 255, 240))
            core.setColorAt(0.25, QColor(255, 230, 140))
            core.setColorAt(0.55, QColor(255, 170, 50))
            core.setColorAt(1.0, QColor(180, 80, 10))
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), cr, cr)

        if self._activity_boost > 0.05 or self._speak > 0.05 or self._panic:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(self._c(255, 210, 90, int(100 + 120 * self._activity_boost)), 2))
            pulse_r = cr * (1.55 + 0.15 * math.sin(self._pulse * 2))
            p.drawEllipse(QPointF(cx, cy), pulse_r, pulse_r)

    def _draw_title(self, p: QPainter, cx: float, cy: float, base: float) -> None:
        font = QFont("Bahnschrift", max(11, int(base * 0.1)))
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 5)
        p.setFont(font)
        title = "J.A.R.V.I.S"
        tw = p.fontMetrics().horizontalAdvance(title)
        x = int(cx - tw / 2)
        y = int(cy + p.fontMetrics().ascent() / 2 - 2)
        p.setPen(self._c(255, 160, 40, 70))
        p.drawText(x + 1, y + 1, title)
        p.setPen(self._c(255, 235, 190, 245) if not self._panic else QColor(255, 210, 210, 245))
        p.drawText(x, y, title)

        if self._panic or self._activity != "idle" or self._speak > 0.1:
            mode = "PANIC" if self._panic else (
                self._activity.upper() if self._speak < 0.2 else "SPEAKING"
            )
            if not self._panic and self._flare > 0.5 and self._activity in ("build", "site", "vibe"):
                mode = "PROCESSING"
            p.setFont(QFont("Bahnschrift", max(8, int(base * 0.055))))
            p.setPen(self._c(255, 180, 70, 200))
            mw = p.fontMetrics().horizontalAdvance(mode)
            p.drawText(int(cx - mw / 2), int(cy + base * 0.28), mode)

    def _draw_spokes(self, p: QPainter, cx: float, cy: float, base: float) -> None:
        self._hits.clear()
        orbit = base * 1.22
        a = self._accent if not self._panic else QColor(255, 40, 40)
        spoke = QColor(
            min(255, (a.red() + 255) // 2),
            min(255, (a.green() + 170) // 2),
            min(255, (a.blue() + 50) // 2),
        )
        if self._panic:
            spoke = QColor(255, 60, 60)
        p.setFont(QFont("Bahnschrift", 8, QFont.Weight.DemiBold))
        for node in self._nodes:
            ang = math.radians(node["angle"])
            nx = cx + math.cos(ang) * orbit
            ny = cy + math.sin(ang) * orbit
            hot = self._hover == node["label"]
            p.setPen(QPen(QColor(spoke.red(), spoke.green(), spoke.blue(), 190 if hot else 70), 1))
            p.drawLine(QPointF(cx, cy), QPointF(nx, ny))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._c(255, 180, 60, 230 if hot else 150))
            p.drawEllipse(QPointF(nx, ny), 5.5 if hot else 3.5, 5.5 if hot else 3.5)
            text = node["label"].upper()
            fm = p.fontMetrics()
            lx = nx + (14 if node["side"] == "R" else -14 - fm.horizontalAdvance(text))
            p.setPen(self._c(255, 230, 190, 255 if hot else 170))
            p.drawText(int(lx), int(ny + 3), text)
            self._hits.append(
                (
                    node["label"],
                    QRectF(min(nx, lx) - 6, ny - 12, fm.horizontalAdvance(text) + 28, 24),
                )
            )

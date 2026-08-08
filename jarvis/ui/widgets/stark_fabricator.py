"""Stark Jet fabricator — hand-driven suit design + physical weave build.

Far From Home–style cyan hologram: configure upgrades, assemble modules,
then SLAP / BUILD to run the fabricator print sequence.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPointF, QRect
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QFont,
    QLinearGradient,
    QRadialGradient,
    QPainterPath,
    QMouseEvent,
)
from PyQt6.QtWidgets import QWidget, QPushButton

from jarvis.config import DATA_DIR
from jarvis.core.gestures import GestureState

CYAN = QColor(0, 229, 255)
CYAN_DIM = QColor(0, 169, 255)
AMBER = QColor(255, 149, 0)
RED = QColor(255, 59, 48)
GREEN = QColor(57, 255, 20)
SILVER = QColor(200, 230, 240)

SUIT_PATH = DATA_DIR / "stark_suit.json"

TABS = (
    "GENERAL UPGRADES",
    "STEALTH UPGRADES",
    "WEAPON UPGRADES",
    "SYSTEMS",
    "FABRICATE",
)

# label, key, unit, hint, lo, hi, step
GENERAL_ITEMS = [
    ("ARMOR DENSITY", "armor", "%", "chassis weave density", 0, 100, 3),
    ("LENS FILTER", "lenses", "%", "HUD opacity / night mode", 0, 100, 3),
    ("SERVO POWER", "servos", "%", "joint actuator torque", 0, 100, 3),
    ("KINETIC ABSORB", "kinetic", "%", "impact dispersion gel", 0, 100, 3),
    ("POWER CELL", "power", "%", "arc micro-cell charge", 0, 100, 2),
]

STEALTH_ITEMS = [
    ("OPTICAL CAMOUFLAGE", "camo", "%", "refractive weave", 0, 100, 3),
    ("THERMAL SIGNATURE", "thermal", "%", "IR suppression", 0, 100, 3),
    ("AUDIO DAMPENING", "audio", "%", "footfall null field", 0, 100, 3),
    ("RADAR ABSORB", "radar", "%", "RF scatter coating", 0, 100, 3),
    ("SCENT MASK", "scent", "%", "pheromone scrubbers", 0, 100, 2),
]

WEAPON_ITEMS = [
    ("PHASER WEB", "voltage", "%", "detonation voltage boost", 0, 100, 5),
    ("FLUID COMPRESSION", "fluid", "%", "nozzle chamber pressure", 0, 100, 4),
    ("DISCHARGE", "discharge", "MJ", "taser-web safety ceiling", 0.5, 12.0, 0.2),
    ("POLYMER ADHESIVE", "polymer", "%", "web fluid integrity", 0, 100, 3),
    ("WEB VELOCITY", "web_vel", "%", "projectile exit speed", 0, 100, 4),
    ("RAPPEL WINCH", "winch", "%", "line retract torque", 0, 100, 3),
]

SYSTEMS_ITEMS = [
    ("NEURAL LINK", "neural", "%", "suit ↔ host latency", 0, 100, 2),
    ("AI ASSIST", "ai", "%", "E.D.I.T.H. combat cues", 0, 100, 3),
    ("COMMS ENCRYPT", "comms", "%", "Stark net channel", 0, 100, 2),
    ("DRONE LINK", "drone", "%", "combat drone uplink", 0, 100, 3),
    ("AUTO-REPAIR", "repair", "%", "nanite weave regen", 0, 100, 2),
]

MODULES = [
    ("HELMET", "helmet", "optics · neural crown"),
    ("TORSO", "torso", "chassis · power cell"),
    ("GAUNTLET L", "gauntlet_l", "web-shooter left"),
    ("GAUNTLET R", "gauntlet_r", "web-shooter right"),
    ("BOOTS", "boots", "kinetic · winch mount"),
    ("UTILITY BELT", "belt", "cartridges · tools"),
]

SUIT_PRESETS = {
    "classic": {"name": "CLASSIC RED/BLUE", "tint": "classic"},
    "black": {"name": "STEALTH BLACK", "tint": "black"},
    "upgraded": {"name": "UPGRADED BLACK/RED", "tint": "upgraded"},
    "iron_spider": {"name": "IRON SPIDER", "tint": "iron"},
}


@dataclass
class FabState:
    tab: int = 4  # FABRICATE default so build is obvious
    selected: int = 0
    depth: float = 0.35
    flash_until: float = 0.0
    cursor: tuple[float, float] = (0.55, 0.45)
    pinch: bool = False
    # tunables
    armor: float = 48.0
    lenses: float = 55.0
    servos: float = 60.0
    kinetic: float = 40.0
    power: float = 72.0
    camo: float = 12.0
    thermal: float = 28.0
    audio: float = 55.0
    radar: float = 20.0
    scent: float = 15.0
    voltage: float = 25.0
    fluid: float = 62.0
    discharge: float = 4.2
    polymer: float = 91.0
    web_vel: float = 58.0
    winch: float = 45.0
    neural: float = 70.0
    ai: float = 65.0
    comms: float = 80.0
    drone: float = 35.0
    repair: float = 25.0
    # modules installed flags
    helmet: bool = False
    torso: bool = False
    gauntlet_l: bool = False
    gauntlet_r: bool = False
    boots: bool = False
    belt: bool = False
    # build / weave
    suit_tint: str = "upgraded"
    phase: str = "design"  # design | scanning | weaving | complete
    weave: float = 0.0  # 0..100
    laser_y: float = 0.0
    slap_ready: float = 0.0
    # fx
    particles: list[tuple[float, float, float]] = field(default_factory=list)
    last_swipe_at: float = 0.0
    last_pinch_at: float = 0.0
    last_fist_at: float = 0.0
    glitch_frames: int = 0
    log: list[str] = field(default_factory=list)


def _catalog(tab: int) -> list[tuple]:
    return {
        0: GENERAL_ITEMS,
        1: STEALTH_ITEMS,
        2: WEAPON_ITEMS,
        3: SYSTEMS_ITEMS,
        4: [],
    }.get(tab, [])


class StarkFabricator(QWidget):
    """Fullscreen translucent hologram lab over the camera feed."""

    closed = pyqtSignal()
    status = pyqtSignal(str)
    suit_built = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("StarkFabricator")
        self._st = FabState()
        self._load()
        self._t0 = time.time()
        self._active = False
        self._pinch_was = False
        self._fist_was = False
        self._btn_rects: dict[str, QRect] = {}

        close = QPushButton("✕ CLOSE", self)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(
            "color:#00E5FF; border:1px solid #00E5FF; background:rgba(2,12,20,200);"
            " padding:8px 12px; letter-spacing:2px;"
        )
        close.clicked.connect(self.close_lab)
        self._close_btn = close

        build = QPushButton("⚙ BUILD SUIT", self)
        build.setCursor(Qt.CursorShape.PointingHandCursor)
        build.setStyleSheet(
            "color:#02080e; border:1px solid #00E5FF; background:#00E5FF;"
            " padding:8px 14px; letter-spacing:2px; font-weight:700;"
        )
        build.clicked.connect(self.start_build)
        self._build_btn = build

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.setInterval(33)
        self.hide()

    # ── persist ─────────────────────────────────────────────────
    def _load(self) -> None:
        if not SUIT_PATH.exists():
            return
        try:
            data = json.loads(SUIT_PATH.read_text(encoding="utf-8"))
            for k, v in data.items():
                if hasattr(self._st, k) and k not in ("particles", "log"):
                    setattr(self._st, k, v)
        except Exception:
            pass

    def _save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            d = asdict(self._st)
            d.pop("particles", None)
            d["log"] = list(self._st.log)[-12:]
            SUIT_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── public API ──────────────────────────────────────────────
    def open_lab(self) -> None:
        self._active = True
        if self._st.phase == "complete":
            self._st.phase = "design"
        self._t0 = time.time()
        self._push_log("FABRICATOR ONLINE · STARK_LAB_OS_V4.6.2")
        self.show()
        self.raise_()
        if not self._tick.isActive():
            self._tick.start()
        try:
            from jarvis.ui.hud_sfx import play_whoosh, play

            play_whoosh()
            play("hum")
        except Exception:
            pass
        self.status.emit("STARK LAB · configure modules then BUILD SUIT")

    def close_lab(self) -> None:
        self._save()
        self._active = False
        self._tick.stop()
        self.hide()
        self.closed.emit()
        try:
            from jarvis.ui.hud_sfx import play_click

            play_click()
        except Exception:
            pass

    def is_lab_open(self) -> bool:
        return self._active and self.isVisible()

    def start_build(self) -> None:
        """Slap / button — begin laser scan → weave → complete."""
        st = self._st
        if st.phase in ("scanning", "weaving"):
            return
        # Auto-install any missing modules when user commits to build
        for _label, key, _hint in MODULES:
            setattr(st, key, True)
        st.phase = "scanning"
        st.weave = 0.0
        st.laser_y = 0.0
        st.flash_until = time.time() + 0.2
        st.glitch_frames = 4
        self._push_log("LASER SCAN · converting hologram → solid geometry")
        self.status.emit("FABRICATOR · SCANNING BLUEPRINT")
        try:
            from jarvis.ui.hud_sfx import play_confirm, play

            play_confirm()
            play("whoosh")
        except Exception:
            pass

    def on_gesture(self, state: GestureState) -> None:
        if not self.is_lab_open() or not state.active:
            return
        st = self._st
        st.cursor = state.cursor
        st.pinch = bool(state.pinch)
        depth = float(getattr(state, "depth", 0.35) or 0.35)
        st.depth = max(0.05, min(0.95, 0.72 * st.depth + 0.28 * depth))

        now = time.time()
        # During weave, gestures are mostly cinematic — still allow cancel fist
        if st.phase in ("scanning", "weaving"):
            if state.label == "fist" and not self._fist_was:
                self._push_log("weave locked — wait for print cycle")
            self._fist_was = state.label == "fist"
            self._pinch_was = st.pinch
            return

        if state.swipe and now - st.last_swipe_at > 0.5:
            st.last_swipe_at = now
            if state.swipe == "left":
                st.tab = (st.tab + 1) % len(TABS)
                st.selected = 0
                self._zap()
            elif state.swipe == "right":
                st.tab = (st.tab - 1) % len(TABS)
                st.selected = 0
                self._zap()
            elif state.swipe in ("up", "down"):
                items = self._nav_count()
                if items:
                    if state.swipe == "up":
                        st.selected = max(0, st.selected - 1)
                    else:
                        st.selected = min(items - 1, st.selected + 1)
                    self._zap()

        # Fist + deep palm = SLAP to build (movie move)
        if state.label == "fist" and not self._fist_was and now - st.last_fist_at > 0.8:
            st.last_fist_at = now
            if st.depth > 0.55 or st.tab == 4:
                self.start_build()
            elif st.tab == 4:
                self._toggle_module(st.selected)
            else:
                self._install_hint()
        self._fist_was = state.label == "fist"

        if st.pinch and not self._pinch_was and now - st.last_pinch_at > 0.32:
            st.last_pinch_at = now
            st.flash_until = now + 0.14
            st.glitch_frames = 3
            self._on_select()
            cx, cy = st.cursor
            for i in range(10):
                st.particles.append((cx, cy, i * 0.015))
        self._pinch_was = st.pinch

        if state.label == "point" and not st.pinch and st.tab < 4:
            self._nudge_selected(+0.12)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        for name, rect in self._btn_rects.items():
            if rect.contains(pos):
                self._click_hotspot(name)
                return
        # Click list rows
        for name, rect in list(self._btn_rects.items()):
            if name.startswith("row_") and rect.contains(pos):
                self._click_hotspot(name)
                return

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._close_btn.move(max(12, self.width() - 110), 10)
        self._build_btn.move(max(12, self.width() - 250), 10)

    # ── internals ───────────────────────────────────────────────
    def _nav_count(self) -> int:
        if self._st.tab == 4:
            return len(MODULES) + len(SUIT_PRESETS)
        return len(_catalog(self._st.tab))

    def _push_log(self, msg: str) -> None:
        self._st.log.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        self._st.log = self._st.log[-10:]

    def _zap(self) -> None:
        try:
            from jarvis.ui.hud_sfx import play

            play("zap")
        except Exception:
            pass

    def _on_select(self) -> None:
        st = self._st
        try:
            from jarvis.ui.hud_sfx import play_confirm

            play_confirm()
        except Exception:
            pass
        if st.tab == 4:
            n_mod = len(MODULES)
            if st.selected < n_mod:
                self._toggle_module(st.selected)
            else:
                keys = list(SUIT_PRESETS.keys())
                idx = st.selected - n_mod
                if 0 <= idx < len(keys):
                    st.suit_tint = keys[idx]
                    self._push_log(f"PRESET · {SUIT_PRESETS[keys[idx]]['name']}")
                    self.status.emit(f"SUIT PRESET · {SUIT_PRESETS[keys[idx]]['name']}")
            return
        items = _catalog(st.tab)
        if not items:
            return
        label = items[st.selected][0]
        self._nudge_selected(+1)
        self.status.emit(f"SELECT · {label}")
        self._push_log(f"TUNE · {label}")

    def _toggle_module(self, idx: int) -> None:
        if idx < 0 or idx >= len(MODULES):
            return
        label, key, hint = MODULES[idx]
        cur = bool(getattr(self._st, key, False))
        setattr(self._st, key, not cur)
        state = "INSTALLED" if not cur else "REMOVED"
        self._push_log(f"MODULE · {label} {state}")
        self.status.emit(f"{label} · {state} · {hint}")
        self._st.flash_until = time.time() + 0.12
        try:
            from jarvis.ui.hud_sfx import play_confirm

            play_confirm()
        except Exception:
            pass

    def _install_hint(self) -> None:
        self._push_log("FIST+PUSH on FABRICATE tab to SLAP-build · or press BUILD SUIT")

    def _nudge_selected(self, delta: float) -> None:
        items = _catalog(self._st.tab)
        if not items:
            return
        _label, key, _unit, _hint, lo, hi, step = items[self._st.selected]
        cur = float(getattr(self._st, key, lo) or lo)
        mult = step if abs(delta) >= 1 else step * 0.15
        nxt = max(lo, min(hi, cur + delta * mult))
        setattr(self._st, key, nxt)

    def _value_for(self, key: str) -> float:
        return float(getattr(self._st, key, 0) or 0)

    def _modules_ready(self) -> int:
        return sum(1 for _l, k, _h in MODULES if getattr(self._st, k, False))

    def _click_hotspot(self, name: str) -> None:
        if name == "build":
            self.start_build()
            return
        if name.startswith("tab_"):
            self._st.tab = int(name.split("_")[1])
            self._st.selected = 0
            self._zap()
            return
        if name.startswith("row_"):
            self._st.selected = int(name.split("_")[1])
            self._on_select()
            return
        if name.startswith("mod_"):
            self._toggle_module(int(name.split("_")[1]))
            return
        if name.startswith("preset_"):
            key = name.split("_", 1)[1]
            if key in SUIT_PRESETS:
                self._st.suit_tint = key
                self._push_log(f"PRESET · {SUIT_PRESETS[key]['name']}")
                self._zap()

    def _on_tick(self) -> None:
        st = self._st
        alive = []
        for x, y, age in st.particles:
            age += 0.033
            if age < 0.5:
                alive.append((x + age * 0.03, y - age * 0.1, age))
        st.particles = alive[-50:]
        if st.glitch_frames > 0:
            st.glitch_frames -= 1

        if st.phase == "scanning":
            st.laser_y = min(1.0, st.laser_y + 0.018)
            if st.laser_y >= 1.0:
                st.phase = "weaving"
                st.weave = 0.0
                self._push_log("WEAVE · polymer needles engaged")
                self.status.emit("FABRICATOR · WEAVING SUIT")
                try:
                    from jarvis.ui.hud_sfx import play

                    play("hum")
                except Exception:
                    pass
        elif st.phase == "weaving":
            st.weave = min(100.0, st.weave + 0.85)
            if int(st.weave) % 12 == 0:
                st.particles.append((0.55 + (st.weave % 7) * 0.01, 0.5, 0.0))
            if st.weave >= 100.0:
                st.phase = "complete"
                self._push_log("COMPLETE · UPGRADED SUIT READY")
                self.status.emit("SUIT FABRICATED · READY FOR DEPLOYMENT")
                self._save()
                payload = {
                    "tint": st.suit_tint,
                    "modules": self._modules_ready(),
                    "voltage": st.voltage,
                    "armor": st.armor,
                }
                try:
                    self.suit_built.emit(payload)
                except Exception:
                    pass
                try:
                    from jarvis.ui.hud_sfx import play_confirm, play_whoosh

                    play_confirm()
                    play_whoosh()
                except Exception:
                    pass
        self.update()

    # ── paint ───────────────────────────────────────────────────
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w < 40 or h < 40:
            return
        self._btn_rects = {}
        t = time.time() - self._t0
        st = self._st
        cx, cy = st.cursor[0] * w, st.cursor[1] * h
        flash = time.time() < st.flash_until

        p.fillRect(0, 0, w, h, QColor(0, 35, 55, 70))

        # Matrix
        p.setPen(QPen(QColor(0, 229, 255, 36), 1))
        for x in range(0, w, 40):
            for y in range(0, h, 40):
                p.drawLine(x - 3, y, x + 3, y)
                p.drawLine(x, y - 3, x, y + 3)

        # Header
        tint_name = SUIT_PRESETS.get(st.suit_tint, {}).get("name", st.suit_tint.upper())
        self._txt(p, 20, 26, "STARK_LAB_OS_V4.6.2  ·  DESIGNATION: BFP", 10, QColor(0, 229, 255, 150))
        self._txt(p, 20, 48, f"SPIDER-MAN · {tint_name}  ·  SYSTEM OVERRIDE", 14, CYAN)
        ready = self._modules_ready()
        self._txt(
            p,
            20,
            68,
            f"MODULES {ready}/{len(MODULES)}  ·  PHASE {st.phase.upper()}  ·  WEAVE {st.weave:.0f}%",
            11,
            GREEN if st.phase == "complete" else AMBER if st.phase != "design" else QColor(0, 229, 255, 140),
        )

        # Tabs (clickable)
        tab_x = 20
        for i, name in enumerate(TABS):
            on = i == st.tab
            tw = 8 * len(name) + 16
            rect = QRect(tab_x, 84, tw, 22)
            self._btn_rects[f"tab_{i}"] = rect
            col = CYAN if on else QColor(0, 229, 255, 95)
            self._txt(p, tab_x, 100, name, 11 if on else 10, col)
            if on:
                p.setPen(QPen(CYAN, 1.6))
                p.drawLine(tab_x, 106, tab_x + tw - 16, 106)
            tab_x += tw + 8

        # Left panel content
        if st.tab < 4:
            self._paint_tunables(p, w, h, t, flash)
        else:
            self._paint_fabricate(p, w, h, t, flash)

        # Life-size human hologram — ~78–86% viewport (adult 7.5-head)
        schem_cx = w * (0.56 - st.depth * 0.04)
        body_h = h * (0.78 + st.depth * 0.08)
        if st.phase == "weaving":
            body_h *= 0.94 + 0.06 * (st.weave / 100.0)
        # Anchor figure so crown clears HUD chrome and feet sit on floor plate
        schem_cy = h * 0.12 + body_h * 0.42
        self._draw_suit(p, schem_cx, schem_cy, body_h, t, flash, st)

        # Right telemetry column
        self._paint_telemetry(p, w, h, t)

        # Build progress / laser
        if st.phase == "scanning":
            ly = int(h * 0.22 + st.laser_y * h * 0.55)
            p.setPen(QPen(QColor(255, 255, 255, 220), 2))
            p.drawLine(int(w * 0.35), ly, int(w * 0.85), ly)
            glow = QColor(0, 229, 255, 60)
            p.fillRect(int(w * 0.35), ly - 4, int(w * 0.5), 8, glow)
        if st.phase in ("weaving", "complete"):
            bar = QRectF(w * 0.35, h * 0.86, w * 0.4, 10)
            p.fillRect(bar, QColor(0, 30, 45, 180))
            fw = bar.width() * (st.weave / 100.0)
            g = QLinearGradient(bar.topLeft(), bar.topRight())
            g.setColorAt(0, CYAN_DIM)
            g.setColorAt(1, GREEN if st.phase == "complete" else CYAN)
            p.fillRect(QRectF(bar.x(), bar.y(), fw, 10), g)
            self._txt(
                p,
                int(bar.x()),
                int(bar.y() - 8),
                "WEAVE PROGRESS" if st.phase == "weaving" else "SUIT READY",
                10,
                GREEN if st.phase == "complete" else CYAN,
            )

        # Footer help
        self._txt(
            p,
            20,
            h - 16,
            "PINCH tune/install  ·  SWIPE tabs  ·  FIST+PUSH slap-build  ·  BUILD SUIT button  ·  click rows",
            10,
            QColor(0, 229, 255, 110),
        )

        # Cursor
        p.setPen(QPen(QColor(255, 255, 255, 210) if flash else CYAN, 1.6))
        p.drawEllipse(QPointF(cx, cy), 13, 13)
        p.drawLine(int(cx - 20), int(cy), int(cx - 7), int(cy))
        p.drawLine(int(cx + 7), int(cy), int(cx + 20), int(cy))
        for x, y, age in st.particles:
            a = int(190 * (1.0 - age / 0.5))
            p.setPen(QPen(QColor(0, 229, 255, max(0, a)), 1))
            p.drawPoint(int(x * w), int(y * h))

        # Hand wavelength
        path = QPainterPath()
        path.moveTo(cx - 55, cy + 32)
        for i in range(36):
            path.lineTo(
                cx - 55 + i * 3.2,
                cy + 32 + math.sin(t * 9 + i * 0.45) * (5 + st.depth * 10),
            )
        p.setPen(QPen(QColor(0, 229, 255, 110), 1))
        p.drawPath(path)

        # Hand ring
        ring_r = 55 + st.depth * 50
        p.setPen(QPen(QColor(0, 229, 255, 85), 1.1))
        p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

    def _paint_tunables(self, p: QPainter, w: int, h: int, t: float, flash: bool) -> None:
        st = self._st
        items = _catalog(st.tab)
        base_y = int(h * 0.20)
        for i, (label, key, unit, hint, lo, hi, _step) in enumerate(items):
            y = base_y + i * 52
            sel = i == st.selected
            val = self._value_for(key)
            col = AMBER if (sel and flash) else (CYAN if sel else QColor(0, 229, 255, 135))
            gx = 5 if st.glitch_frames and sel else 0
            row = QRect(28 + gx, y - 14, 300, 46)
            self._btn_rects[f"row_{i}"] = row
            if sel:
                p.fillRect(row, QColor(0, 60, 80, 70))
                p.setPen(QPen(CYAN, 1))
                p.drawRect(row)
            self._txt(p, 36 + gx, y, label, 12 if sel else 11, col)
            disp = f"{val:.1f}{unit}" if unit != "MJ" else f"{val:.1f} MJ"
            self._txt(p, 36 + gx, y + 14, f"{hint}  ·  {disp}", 9, QColor(0, 229, 255, 110))
            bar = QRectF(36 + gx, y + 22, 240, 5)
            p.fillRect(bar, QColor(0, 40, 55, 160))
            span = hi - lo if hi != lo else 1
            fill_w = 240 * ((val - lo) / span)
            g = QLinearGradient(bar.topLeft(), bar.topRight())
            g.setColorAt(0, CYAN_DIM)
            g.setColorAt(1, QColor(255, 255, 255) if flash and sel else CYAN)
            p.fillRect(QRectF(bar.x(), bar.y(), max(0, fill_w), 5), g)
            if sel:
                self._dial(p, 300 + gx, y + 8, 18, (val - lo) / span)

    def _paint_fabricate(self, p: QPainter, w: int, h: int, t: float, flash: bool) -> None:
        st = self._st
        self._txt(p, 28, int(h * 0.18), "SUIT MODULES — pinch/click to install", 11, CYAN)
        base_y = int(h * 0.22)
        for i, (label, key, hint) in enumerate(MODULES):
            y = base_y + i * 36
            on = bool(getattr(st, key, False))
            sel = st.selected == i
            rect = QRect(28, y - 12, 280, 30)
            self._btn_rects[f"mod_{i}"] = rect
            self._btn_rects[f"row_{i}"] = rect
            if sel:
                p.fillRect(rect, QColor(0, 70, 90, 80))
            mark = "▣" if on else "□"
            col = GREEN if on else (CYAN if sel else QColor(0, 229, 255, 120))
            self._txt(p, 36, y + 6, f"{mark}  {label}", 12, col)
            self._txt(p, 170, y + 6, hint, 9, QColor(0, 229, 255, 100))

        # Presets
        py0 = base_y + len(MODULES) * 36 + 24
        self._txt(p, 28, py0, "COLORWAY PRESETS", 11, CYAN)
        for j, (key, meta) in enumerate(SUIT_PRESETS.items()):
            y = py0 + 24 + j * 28
            sel = st.selected == len(MODULES) + j
            on = st.suit_tint == key
            rect = QRect(28, y - 10, 280, 26)
            self._btn_rects[f"preset_{key}"] = rect
            self._btn_rects[f"row_{len(MODULES) + j}"] = rect
            col = AMBER if on else (CYAN if sel else QColor(0, 229, 255, 120))
            mark = "●" if on else "○"
            self._txt(p, 36, y + 6, f"{mark}  {meta['name']}", 11, col)

        # Slap callout
        self._txt(
            p,
            28,
            int(h * 0.82),
            "SLAP COMMAND: fist + push palm  →  laser scan  →  weave print",
            11,
            AMBER if st.phase == "design" else GREEN,
        )

    def _paint_telemetry(self, p: QPainter, w: int, h: int, t: float) -> None:
        st = self._st
        x = w - 210
        self._txt(p, x, 130, "BUFFER ALLOCATION", 9, QColor(0, 229, 255, 130))
        for i in range(8):
            bh = 6 + int(10 * abs(math.sin(t * 3 + i)))
            p.fillRect(x + i * 14, 140 + (18 - bh), 10, bh, QColor(0, 229, 255, 100 + i * 8))
        self._txt(p, x, 175, f"PHASER WEB  {st.voltage:.0f}%", 9, CYAN)
        self._txt(p, x, 192, f"DISCHARGE  {st.discharge:.1f} MJ", 9, CYAN)
        self._txt(p, x, 209, f"POLYMER  {st.polymer:.0f}%", 9, CYAN)
        self._txt(p, x, 226, f"AI ASSIST  {st.ai:.0f}%", 9, QColor(0, 229, 255, 140))
        self._txt(p, x, 250, "EVENT LOG", 9, QColor(0, 229, 255, 130))
        for i, line in enumerate(st.log[-6:]):
            self._txt(p, x, 268 + i * 16, line[-34:], 8, QColor(0, 229, 255, 100))
        # Binary
        p.setPen(QPen(QColor(0, 229, 255, 45), 1))
        font = QFont("Bahnschrift", 8)
        font.setWeight(QFont.Weight.Thin)
        p.setFont(font)
        for i in range(14):
            bit = "10"[(int(t * 35) + i) % 2]
            p.drawText(w - 22, 120 + i * 26, bit * 4)

    def _draw_suit(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        body_h: float,
        t: float,
        flash: bool,
        st: FabState,
    ) -> None:
        """Life-size human silhouette — 7.5-head adult proportions, 1:1 hologram scale."""
        H = max(220.0, body_h)
        head = H / 7.5
        crown = cy - H * 0.42
        floor = crown + H

        tint = st.suit_tint
        line = CYAN
        fill_c = QColor(0, 229, 255, 50)
        accent = RED
        if tint == "black":
            line = QColor(190, 205, 220)
            fill_c = QColor(25, 30, 38, 110)
            accent = QColor(230, 235, 240)
        elif tint == "upgraded":
            line = QColor(255, 255, 255) if flash else CYAN
            fill_c = QColor(8, 8, 12, 120)
            accent = RED
        elif tint == "iron":
            line = AMBER
            fill_c = QColor(70, 45, 8, 95)
            accent = AMBER
        elif tint == "classic":
            line = QColor(0, 150, 255)
            fill_c = QColor(160, 25, 35, 85)
            accent = RED

        show_all = st.phase != "design"
        weave_a = (
            int(min(175, 35 + st.weave * 1.4))
            if st.phase in ("weaving", "complete")
            else 0
        )

        def show(mod: str) -> bool:
            return show_all or bool(getattr(st, mod, False))

        # Floor plate
        p.setPen(QPen(QColor(0, 229, 255, 55), 1))
        p.drawEllipse(QPointF(cx, floor + 6), head * 1.8, head * 0.38)
        self._txt(
            p,
            int(cx - 85),
            int(floor + head * 0.85),
            f"SCALE 1:1  ·  ADULT 7.5-HEAD  ·  {int(H)}px PROJECTION",
            9,
            QColor(0, 229, 255, 120),
        )

        sway = math.sin(t * 1.05) * head * 0.035
        cx = cx + sway

        neck = crown + head * 1.0
        shoulder_y = neck + head * 0.12
        shoulder_w = head * 1.2
        chest_y = crown + head * 2.15
        waist_y = crown + head * 3.45
        hip_y = crown + head * 3.95
        hip_w = head * 0.88
        knee_y = crown + head * 5.45
        ankle_y = floor - head * 0.12
        elbow_y = shoulder_y + head * 1.2
        wrist_y = elbow_y + head * 1.05

        # Torso
        if show("torso") or weave_a:
            torso = QPainterPath()
            torso.moveTo(cx - shoulder_w, shoulder_y)
            torso.cubicTo(
                cx - shoulder_w * 1.08,
                chest_y,
                cx - hip_w * 1.08,
                waist_y,
                cx - hip_w,
                hip_y,
            )
            torso.lineTo(cx + hip_w, hip_y)
            torso.cubicTo(
                cx + hip_w * 1.08,
                waist_y,
                cx + shoulder_w * 1.08,
                chest_y,
                cx + shoulder_w,
                shoulder_y,
            )
            torso.closeSubpath()
            fill = QColor(fill_c)
            if weave_a:
                fill.setAlpha(weave_a)
            p.fillPath(torso, fill)
            p.setPen(QPen(line, 1.7))
            p.drawPath(torso)
            p.setPen(QPen(QColor(line.red(), line.green(), line.blue(), 95), 1.0))
            p.drawLine(QPointF(cx, neck), QPointF(cx, hip_y))
            p.drawLine(
                QPointF(cx - shoulder_w * 0.6, chest_y),
                QPointF(cx + shoulder_w * 0.6, chest_y),
            )
            p.drawLine(
                QPointF(cx - hip_w * 0.95, waist_y),
                QPointF(cx + hip_w * 0.95, waist_y),
            )
            # Chest emblem
            p.setPen(QPen(accent, 1.6))
            p.drawEllipse(QPointF(cx, chest_y), head * 0.32, head * 0.38)
            for a in (-0.85, -0.4, 0.4, 0.85, -1.15, 1.15):
                p.drawLine(
                    QPointF(cx, chest_y),
                    QPointF(
                        cx + math.sin(a) * head * 0.55,
                        chest_y + abs(math.cos(a)) * head * 0.15,
                    ),
                )

        # Head / helmet
        if show("helmet") or weave_a:
            hx, hy = cx, crown + head * 0.55
            head_path = QPainterPath()
            head_path.addEllipse(QPointF(hx, hy), head * 0.5, head * 0.6)
            hf = QColor(fill_c)
            if weave_a:
                hf.setAlpha(min(210, weave_a + 45))
            p.fillPath(head_path, hf)
            p.setPen(QPen(line, 1.8))
            p.drawPath(head_path)
            lens = AMBER if tint in ("upgraded", "iron") else QColor(235, 245, 255)
            p.setBrush(lens)
            p.setPen(QPen(QColor(20, 30, 40, 180), 1))
            for side in (-1, 1):
                lx = hx + side * head * 0.2
                ly = hy
                eye = QRectF(lx - head * 0.2, ly - head * 0.1, head * 0.32, head * 0.18)
                p.drawRoundedRect(eye, head * 0.08, head * 0.08)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(line, 1.4))
            p.drawLine(QPointF(cx - head * 0.2, neck), QPointF(cx + head * 0.2, neck))

        # Arms
        for side, gkey in ((-1, "gauntlet_l"), (1, "gauntlet_r")):
            if not (show(gkey) or weave_a):
                continue
            sx = cx + side * shoulder_w
            sy = shoulder_y
            ex = cx + side * (shoulder_w + head * 0.4)
            ey = elbow_y + math.sin(t * 1.25 + side) * head * 0.05
            wx = cx + side * (shoulder_w + head * 0.65)
            wy = wrist_y
            thick = head * 0.24
            arm = QPainterPath()
            arm.moveTo(sx, sy)
            arm.lineTo(ex + side * thick * 0.25, ey)
            arm.lineTo(wx + side * thick * 0.2, wy)
            arm.lineTo(wx - side * thick * 0.2, wy + head * 0.1)
            arm.lineTo(ex - side * thick * 0.25, ey + head * 0.12)
            arm.lineTo(sx - side * thick * 0.35, sy + head * 0.18)
            arm.closeSubpath()
            af = QColor(fill_c)
            if weave_a:
                af.setAlpha(weave_a)
            p.fillPath(arm, af)
            p.setPen(QPen(line, 1.55))
            p.drawPath(arm)
            p.drawEllipse(QPointF(wx, wy + head * 0.14), head * 0.22, head * 0.3)
            # Wrist web-shooter
            p.setPen(QPen(accent if flash else line, 1.5))
            cuff = QRectF(wx - head * 0.24, wy - head * 0.06, head * 0.48, head * 0.3)
            p.drawRoundedRect(cuff, 4, 4)
            p.drawEllipse(
                QPointF(wx + side * head * 0.14, wy + head * 0.08),
                head * 0.09,
                head * 0.07,
            )
            if st.tab == 2:
                self._txt(p, int(wx - 34), int(wy + head * 0.6), "WEB-SHOOTER", 8, accent)

        # Legs
        if show("boots") or show("torso") or weave_a:
            for side in (-1, 1):
                hx_ = cx + side * hip_w * 0.55
                kx = cx + side * hip_w * 0.48
                ax = cx + side * hip_w * 0.42
                thick = head * 0.3
                leg = QPainterPath()
                leg.moveTo(hx_ - side * thick * 0.15, hip_y)
                leg.lineTo(kx - side * thick * 0.12, knee_y)
                leg.lineTo(ax - side * thick * 0.1, ankle_y)
                leg.lineTo(ax + side * thick * 0.4, ankle_y)
                leg.lineTo(kx + side * thick * 0.45, knee_y)
                leg.lineTo(hx_ + side * thick * 0.5, hip_y)
                leg.closeSubpath()
                lf = QColor(fill_c)
                if weave_a:
                    lf.setAlpha(weave_a)
                p.fillPath(leg, lf)
                p.setPen(QPen(line, 1.55))
                p.drawPath(leg)
                if show("boots") or weave_a:
                    boot = QRectF(
                        ax - head * 0.3, ankle_y - head * 0.04, head * 0.78, head * 0.38
                    )
                    p.drawRoundedRect(boot, 5, 5)

        # Belt
        if show("belt") or weave_a:
            p.setPen(QPen(accent, 2.0))
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 45))
            belt = QRectF(cx - hip_w * 1.08, hip_y - head * 0.16, hip_w * 2.16, head * 0.3)
            p.drawRoundedRect(belt, 3, 3)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(-2, 3):
                p.drawRect(
                    QRectF(
                        cx + i * head * 0.38 - head * 0.1,
                        hip_y - head * 0.1,
                        head * 0.2,
                        head * 0.18,
                    )
                )

        # Ghost guide when empty
        if st.phase == "design" and self._modules_ready() == 0:
            p.setPen(QPen(QColor(0, 229, 255, 60), 1.3, Qt.PenStyle.DashLine))
            p.drawEllipse(QPointF(cx, crown + head * 0.55), head * 0.5, head * 0.6)
            p.drawRect(
                QRectF(cx - shoulder_w, shoulder_y, shoulder_w * 2, hip_y - shoulder_y)
            )
            p.drawLine(QPointF(cx - hip_w * 0.5, hip_y), QPointF(cx - hip_w * 0.4, floor))
            p.drawLine(QPointF(cx + hip_w * 0.5, hip_y), QPointF(cx + hip_w * 0.4, floor))
            self._txt(
                p,
                int(cx - 95),
                int(crown - 10),
                "INSTALL MODULES — LIFE-SIZE GUIDE",
                10,
                QColor(0, 229, 255, 130),
            )

        # Height rails
        p.setPen(QPen(QColor(0, 229, 255, 75), 1))
        rx = cx + shoulder_w + head * 1.35
        p.drawLine(QPointF(rx, crown), QPointF(rx, floor))
        for i in range(8):
            yy = crown + i * head
            p.drawLine(QPointF(rx - 7, yy), QPointF(rx + 7, yy))
            self._txt(p, int(rx + 10), int(yy + 4), f"{i}H", 8, QColor(0, 229, 255, 105))

        glow = QRadialGradient(QPointF(cx, cy), H * 0.55)
        glow.setColorAt(0, QColor(0, 229, 255, 16))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(cx - H * 0.55, cy - H * 0.55, H * 1.1, H * 1.1), glow)

        if st.phase == "complete":
            self._txt(
                p,
                int(cx - 100),
                int(floor + head * 1.15),
                "1:1 HUMAN-SCALE FABRICATION COMPLETE",
                12,
                GREEN,
            )

    def _txt(self, p: QPainter, x: int, y: int, text: str, size: int, col: QColor) -> None:
        font = QFont("Bahnschrift", size)
        font.setWeight(QFont.Weight.Light)
        p.setFont(font)
        p.setPen(col)
        p.drawText(x, y, text)

    def _dial(self, p: QPainter, x: float, y: float, r: float, frac: float) -> None:
        p.setPen(QPen(QColor(0, 229, 255, 75), 1))
        p.drawEllipse(QPointF(x, y), r, r)
        p.setPen(QPen(CYAN, 2))
        span = int(max(8, min(350, frac * 320)) * 16)
        p.drawArc(QRectF(x - r, y - r, r * 2, r * 2), 90 * 16, -span)

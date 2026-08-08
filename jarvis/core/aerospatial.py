"""AR Aerospatial Mapping — smooth cinematic room holograms.

Fixes track drift / jitter with EMA + Vector3.Lerp-style interpolation.
Adds light estimation, marker lock, PC telemetry, and tracking quality cues.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from jarvis.config import DATA_DIR

MAP_PATH = DATA_DIR / "aerospatial_map.json"
DEPLOY_MODES = ("desktop", "mirror", "phone")


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolate — never snap holograms to raw detections."""
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t


def lerp2(
    a: tuple[float, float], b: tuple[float, float], t: float
) -> tuple[float, float]:
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))


@dataclass
class PlaneHit:
    kind: str  # floor | desk | wall | furniture | marker
    cx: float
    cy: float
    w: float
    h: float
    angle: float = 0.0
    confidence: float = 0.5
    label: str = ""


@dataclass
class MeshNode:
    x: float
    y: float
    z: float = 0.35


@dataclass
class SpatialMesh:
    nodes: list[MeshNode] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    planes: list[PlaneHit] = field(default_factory=list)
    laser_targets: list[tuple[float, float]] = field(default_factory=list)
    desk: Optional[PlaneHit] = None
    floor: Optional[PlaneHit] = None
    marker: Optional[PlaneHit] = None
    frame_w: int = 0
    frame_h: int = 0
    ts: float = 0.0
    source: str = "opencv"
    light_lux: float = 0.5  # 0 dark → 1 bright
    light_warmth: float = 0.5
    texture_score: float = 0.5  # corner/texture richness for tracking
    fps_est: float = 30.0


@dataclass
class PCTelemetry:
    cpu: float = 0.0
    ram: float = 0.0
    gpu: float = 0.0
    temp_c: float = 0.0
    fan: float = 0.0
    ts: float = 0.0


@dataclass
class AerospatialState:
    enabled: bool = False
    deploy: str = "desktop"
    mesh_quality: float = 0.0
    bloom: float = 0.72
    chromatic: float = 0.35
    occlusion: bool = True
    laser_active: bool = False
    laser_y: float = 0.0
    fabricator_on_desk: bool = True
    last_scan_at: float = 0.0
    # Cinematic / anti-jitter
    cinematic: bool = True
    smooth_alpha: float = 0.14  # lower = smoother
    match_camera_fps: bool = True
    target_fps: float = 30.0
    light_adapt: bool = True
    marker_assist: bool = True
    spatial_audio: bool = True
    pc_gauges: bool = True
    biometric_scan: bool = True
    web_shooter: bool = True
    hold_lock: bool = True  # freeze pose when track confidence collapses
    deadzone: float = 0.008  # ignore micro desk jitter below this
    contrast_boost: bool = True  # CLAHE before edge detect
    fab_scale: float = 1.0
    fab_yaw: float = 0.0
    log: list[str] = field(default_factory=list)


SETUP_GUIDE = """\
JARVIS · CINEMATIC AR AEROSPATIAL (anti-jitter)
═══════════════════════════════════════════════

GOAL: track without drift · visual blending · professional holograms

HARDWARE (kill physical jitter)
  · Mount webcam / iPhone / iPad / Intel RealSense firmly — no desk vibration
  · Prefer 30fps locked (match overlay render — no 60fps hologram on 30fps cam)
  · Dim harsh light OR add lamps if corners look soft
  · Solid white/black desks track poorly — add a textured mousepad or print an
    ArUco / high-contrast marker on the desk near the camera

SOFTWARE (smooth data)
  · EMA + Vector3.Lerp — hologram slides into new pose (never teleports)
  · Light estimation adapts bloom/shadows to your room
  · Screen-space floor shadow + semi-transparent laser
  · MediaPipe hands: pinch scale · swipe rotate · fist laser · web-shooter flick
  · Spatial hum pans with laser; louder as hand approaches hologram
  · Biometric sit-down scan · PC health gauges · web projectile vs mesh

Voice: open aerospatial · cinematic ar · scan room · aerospatial setup
       web shooter · ar biometric · ar gauges · close aerospatial
"""


class AerospatialMapper:
    """Frame → smoothed SpatialMesh + light / marker / telemetry."""

    def __init__(self) -> None:
        self.state = AerospatialState()
        self._mesh = SpatialMesh()
        self._skip = 0
        self._desk_s: Optional[tuple[float, float, float, float]] = None
        self._desk_v = (0.0, 0.0)  # velocity damping
        self._fab_pos = (0.52, 0.55)
        self._fab_target = (0.52, 0.55)
        self._fab_good = (0.52, 0.55)
        self._light_s = 0.5
        self._tex_s = 0.5
        self._frame_times: list[float] = []
        self._tele = PCTelemetry()
        self._tele_at = 0.0
        self._low_conf_streak = 0
        self._load()

    def _load(self) -> None:
        try:
            if MAP_PATH.exists():
                raw = json.loads(MAP_PATH.read_text(encoding="utf-8"))
                for k, v in raw.items():
                    if hasattr(self.state, k) and k != "log":
                        setattr(self.state, k, v)
                if isinstance(raw.get("log"), list):
                    self.state.log = [str(x) for x in raw["log"][-40:]]
        except Exception:
            pass

    def save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = asdict(self.state)
            payload["log"] = self.state.log[-40:]
            MAP_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def push_log(self, line: str) -> None:
        self.state.log.append(f"{time.strftime('%H:%M:%S')} · {line}")
        self.state.log = self.state.log[-40:]

    @property
    def mesh(self) -> SpatialMesh:
        return self._mesh

    @property
    def fab_smoothed(self) -> tuple[float, float]:
        return self._fab_pos

    @property
    def telemetry(self) -> PCTelemetry:
        return self._tele

    def set_deploy(self, mode: str) -> str:
        m = (mode or "desktop").strip().lower()
        if m not in DEPLOY_MODES:
            return f"Unknown deploy '{mode}'. Use desktop, mirror, or phone."
        self.state.deploy = m
        self.push_log(f"DEPLOY · {m}")
        self.save()
        return f"Aerospatial deploy mode: {m}."

    def set_cinematic(self, on: bool = True) -> str:
        self.state.cinematic = bool(on)
        self.state.smooth_alpha = 0.12 if on else 0.32
        self.state.chromatic = 0.28 if on else 0.55
        self.state.hold_lock = bool(on)
        self.state.contrast_boost = bool(on)
        self.state.match_camera_fps = True
        self.state.light_adapt = True
        self.push_log(f"CINEMATIC · {'on' if on else 'off'}")
        self.save()
        return (
            "Cinematic AR on — lerp, hold-lock, CLAHE, light adapt, matched FPS."
            if on
            else "Cinematic AR off — snappier tracking."
        )

    def apply_pro_profile(self) -> str:
        """One-shot best settings for stable cinematic holograms."""
        self.set_cinematic(True)
        self.state.spatial_audio = True
        self.state.pc_gauges = True
        self.state.web_shooter = True
        self.state.biometric_scan = True
        self.state.marker_assist = True
        self.state.occlusion = True
        self.state.bloom = 0.68
        self.save()
        self.push_log("PRO PROFILE · applied")
        return "AR pro profile applied — cinematic lock, gauges, webs, biometric, audio."

    def start_laser(self) -> str:
        self.state.laser_active = True
        self.state.laser_y = 0.05
        self.state.last_scan_at = time.time()
        self.push_log("LASER SCAN · mapping room geometry")
        self.save()
        return "Laser scan engaged — mapping walls and furniture."

    def setup_message(self) -> str:
        return SETUP_GUIDE

    def status(self) -> str:
        m = self._mesh
        q = int(self.state.mesh_quality * 100)
        return (
            f"Aerospatial {'ONLINE' if self.state.enabled else 'STANDBY'} · "
            f"{'cinematic' if self.state.cinematic else 'raw'} · "
            f"deploy {self.state.deploy} · mesh {q}% · "
            f"light {m.light_lux:.0%} · tex {m.texture_score:.0%} · "
            f"{m.fps_est:.0f}fps · planes {len(m.planes)}"
        )

    def tick_fab_lerp(self, dt: float | None = None) -> tuple[float, float]:
        """Call every paint — slide fabricator toward locked target."""
        alpha = self.state.smooth_alpha
        if dt is not None and dt > 0:
            # Frame-rate independent approximate
            alpha = 1.0 - math.exp(-alpha * 60.0 * dt)
        self._fab_pos = lerp2(self._fab_pos, self._fab_target, alpha)
        return self._fab_pos

    def refresh_telemetry(self) -> PCTelemetry:
        now = time.time()
        if now - self._tele_at < 1.0:
            return self._tele
        self._tele_at = now
        cpu = ram = gpu = temp = fan = 0.0
        try:
            import psutil

            cpu = float(psutil.cpu_percent(interval=None))
            ram = float(psutil.virtual_memory().percent)
        except Exception:
            pass
        try:
            import subprocess

            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,temperature.gpu,fan.speed",
                    "--format=csv,noheader,nounits",
                ],
                stderr=subprocess.DEVNULL,
                timeout=0.8,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
            parts = [p.strip() for p in out.strip().split(",")]
            if len(parts) >= 2:
                gpu = float(parts[0] or 0)
                temp = float(parts[1] or 0)
            if len(parts) >= 3 and parts[2] not in ("[N/A]", "N/A", ""):
                fan = float(parts[2] or 0)
        except Exception:
            gpu = max(0.0, cpu * 0.6)
            temp = 40.0 + cpu * 0.35
            fan = cpu * 0.5
        self._tele = PCTelemetry(
            cpu=cpu, ram=ram, gpu=gpu, temp_c=temp, fan=fan, ts=now
        )
        return self._tele

    def _estimate_light(self, gray: Any) -> tuple[float, float, float]:
        import numpy as np

        mean = float(np.mean(gray)) / 255.0
        # Laplacian variance ≈ texture / corner richness
        try:
            import cv2

            lap = cv2.Laplacian(gray, cv2.CV_64F)
            tex = float(np.var(lap))
            tex_n = max(0.0, min(1.0, tex / 450.0))
        except Exception:
            tex_n = 0.4
        # Warmth proxy from center crop if color available later
        warmth = 0.45 + 0.1 * (mean - 0.5)
        return mean, warmth, tex_n

    def _detect_marker(self, gray: Any, sw: int, sh: int) -> Optional[PlaneHit]:
        """ArUco if available, else high-contrast square blob (mousepad / print)."""
        try:
            import cv2
            import numpy as np
        except Exception:
            return None
        # Try ArUco
        try:
            aruco = cv2.aruco
            dicts = getattr(aruco, "DICT_4X4_50", None)
            if dicts is not None:
                dictionary = aruco.getPredefinedDictionary(dicts)
                params = aruco.DetectorParameters()
                det = aruco.ArucoDetector(dictionary, params)
                corners, ids, _ = det.detectMarkers(gray)
                if ids is not None and len(corners):
                    c = corners[0][0]
                    cx = float(np.mean(c[:, 0]) / sw)
                    cy = float(np.mean(c[:, 1]) / sh)
                    w = float((c[:, 0].max() - c[:, 0].min()) / sw)
                    h = float((c[:, 1].max() - c[:, 1].min()) / sh)
                    return PlaneHit(
                        kind="marker",
                        cx=cx,
                        cy=cy,
                        w=max(0.04, w),
                        h=max(0.04, h),
                        confidence=0.95,
                        label="ARUCO LOCK",
                    )
        except Exception:
            pass
        # High-contrast textured patch in lower desk band
        try:
            import cv2
            import numpy as np

            band = gray[int(sh * 0.45) : int(sh * 0.85), int(sw * 0.15) : int(sw * 0.85)]
            if band.size < 100:
                return None
            edges = cv2.Canny(band, 80, 180)
            cnts, _ = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            best = None
            best_score = 0.0
            for c in cnts:
                area = cv2.contourArea(c)
                if area < 400 or area > band.size * 0.4:
                    continue
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.04 * peri, True)
                if len(approx) < 4:
                    continue
                x, y, bw, bh = cv2.boundingRect(c)
                aspect = bw / max(1, bh)
                if 0.6 < aspect < 1.7:
                    score = area * (1.0 - abs(1.0 - aspect))
                    if score > best_score:
                        best_score = score
                        best = (x, y, bw, bh)
            if best:
                x, y, bw, bh = best
                ox, oy = int(sw * 0.15), int(sh * 0.45)
                return PlaneHit(
                    kind="marker",
                    cx=(ox + x + bw / 2) / sw,
                    cy=(oy + y + bh / 2) / sh,
                    w=bw / sw,
                    h=bh / sh,
                    confidence=0.7,
                    label="TEXTURE LOCK",
                )
        except Exception:
            pass
        return None

    def process_frame(self, frame_bgr: Any, *, force: bool = False) -> SpatialMesh:
        if frame_bgr is None:
            return self._mesh
        now = time.time()
        self._frame_times.append(now)
        self._frame_times = [t for t in self._frame_times if now - t < 1.2]
        fps = len(self._frame_times) / max(0.2, (self._frame_times[-1] - self._frame_times[0]))
        if self.state.match_camera_fps:
            self.state.target_fps = max(24.0, min(60.0, fps if fps > 10 else 30.0))

        self._skip = (self._skip + 1) % 2  # denser updates, still smooth via lerp
        if self._skip and not force and not self.state.laser_active:
            # Still lerp fabricator toward last target on skipped frames
            self.tick_fab_lerp()
            return self._mesh
        try:
            import cv2
            import numpy as np
        except Exception:
            return self._mesh

        try:
            h, w = frame_bgr.shape[:2]
            small = cv2.resize(frame_bgr, (480, int(480 * h / max(1, w))))
            sh, sw = small.shape[:2]
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if self.state.contrast_boost:
                try:
                    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
                    gray = clahe.apply(gray)
                except Exception:
                    pass
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            lux, warmth, tex = self._estimate_light(gray)
            a = self.state.smooth_alpha
            self._light_s = lerp(self._light_s, lux, a)
            self._tex_s = lerp(self._tex_s, tex, a)

            # Dim bloom when texture is weak (hard to lock) — avoid slidey bright ghost
            if self.state.light_adapt:
                if self._tex_s < 0.28:
                    self.state.bloom = lerp(self.state.bloom, 0.45, 0.08)
                else:
                    target_bloom = 0.55 + 0.35 * (1.0 - abs(self._light_s - 0.45))
                    self.state.bloom = lerp(self.state.bloom, target_bloom, 0.1)

            edges = cv2.Canny(gray, 55, 130)
            lines = cv2.HoughLinesP(
                edges, 1, math.pi / 180, threshold=48, minLineLength=36, maxLineGap=14
            )

            planes: list[PlaneHit] = []
            nodes: list[MeshNode] = []
            edges_i: list[tuple[int, int]] = []
            lasers: list[tuple[float, float]] = []

            cols, rows = 8, 6
            for gy in range(rows + 1):
                for gx in range(cols + 1):
                    nx = gx / cols
                    ny = 0.35 + 0.55 * (gy / rows)
                    z = 0.2 + 0.7 * (gy / max(1, rows))
                    mid = 0.5
                    nx = mid + (nx - mid) * (0.55 + 0.45 * z)
                    nodes.append(MeshNode(nx, ny, z))
            for gy in range(rows + 1):
                for gx in range(cols):
                    a_i = gy * (cols + 1) + gx
                    edges_i.append((a_i, a_i + 1))
            for gy in range(rows):
                for gx in range(cols + 1):
                    a_i = gy * (cols + 1) + gx
                    edges_i.append((a_i, a_i + (cols + 1)))

            band = gray[int(sh * 0.55) :, :]
            if band.size:
                _, thr = cv2.threshold(
                    band, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                thr = cv2.morphologyEx(
                    thr, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)
                )
                cnts, _ = cv2.findContours(
                    thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:4]
                for i, c in enumerate(cnts):
                    area = cv2.contourArea(c)
                    if area < 800:
                        continue
                    x, y, bw, bh = cv2.boundingRect(c)
                    cy = (y + bh / 2) / sh * 0.45 + 0.55
                    cx = (x + bw / 2) / sw
                    kind = "floor" if i == 0 and bh > sh * 0.12 else "desk"
                    if i > 0 and bh < sh * 0.18:
                        kind = "furniture"
                    hit = PlaneHit(
                        kind=kind,
                        cx=float(cx),
                        cy=float(cy),
                        w=float(bw / sw),
                        h=float(bh / sh * 0.45),
                        confidence=min(0.95, area / (sw * sh * 0.2)),
                        label=kind.upper(),
                    )
                    planes.append(hit)
                    lasers.append((cx, cy - hit.h * 0.35))

            if lines is not None:
                for ln in lines[:20]:
                    x1, y1, x2, y2 = ln[0]
                    dx, dy = x2 - x1, y2 - y1
                    ang = abs(math.degrees(math.atan2(dy, dx)))
                    if 55 < ang < 125:
                        mx = ((x1 + x2) / 2) / sw
                        my = ((y1 + y2) / 2) / sh
                        planes.append(
                            PlaneHit(
                                kind="wall",
                                cx=float(mx),
                                cy=float(my),
                                w=0.04,
                                h=abs(dy) / sh + 0.08,
                                angle=ang,
                                confidence=0.55,
                                label="WALL",
                            )
                        )
                        lasers.append((mx, my))

            marker = None
            if self.state.marker_assist:
                marker = self._detect_marker(gray, sw, sh)
                if marker:
                    planes.insert(0, marker)

            desk = next((p for p in planes if p.kind == "desk"), None)
            floor = next((p for p in planes if p.kind == "floor"), None)
            if marker and marker.confidence > 0.65:
                # Anchor desk to marker — kills slide on blank desks
                desk = PlaneHit(
                    kind="desk",
                    cx=marker.cx,
                    cy=min(0.78, marker.cy + 0.06),
                    w=max(0.28, marker.w * 3.2),
                    h=0.12,
                    confidence=max(0.75, marker.confidence),
                    label="DESK · MARKER",
                )
            if desk is None and floor is not None:
                desk = PlaneHit(
                    kind="desk",
                    cx=floor.cx,
                    cy=max(0.45, floor.cy - 0.18),
                    w=min(0.55, floor.w * 0.7),
                    h=0.12,
                    confidence=0.4,
                    label="DESK PROXY",
                )
                planes.insert(0, desk)
            if desk is None:
                desk = PlaneHit(
                    kind="desk",
                    cx=0.52,
                    cy=0.62,
                    w=0.42,
                    h=0.14,
                    confidence=0.3,
                    label="DESK FALLBACK",
                )
                planes.insert(0, desk)

            # EMA desk lock — anti-jitter + deadzone + velocity damping
            raw = (desk.cx, desk.cy, desk.w, desk.h)
            if self._desk_s is None:
                self._desk_s = raw
            else:
                sa = self.state.smooth_alpha
                dx = raw[0] - self._desk_s[0]
                dy = raw[1] - self._desk_s[1]
                # Deadzone: ignore micro shake
                if abs(dx) < self.state.deadzone and abs(dy) < self.state.deadzone:
                    raw = (self._desk_s[0], self._desk_s[1], raw[2], raw[3])
                    dx = dy = 0.0
                # Velocity damping — resist sudden jumps
                vx = lerp(self._desk_v[0], dx, 0.35)
                vy = lerp(self._desk_v[1], dy, 0.35)
                self._desk_v = (vx * 0.82, vy * 0.82)
                jump = math.hypot(dx, dy)
                if jump > 0.12:
                    # Big jump = likely bad detect — trust less
                    sa *= 0.35
                    self._low_conf_streak += 1
                else:
                    self._low_conf_streak = max(0, self._low_conf_streak - 1)
                if (
                    self.state.hold_lock
                    and self._low_conf_streak > 4
                    and desk.confidence < 0.45
                ):
                    # Hold last good pose instead of sliding around
                    raw = (
                        self._desk_s[0],
                        self._desk_s[1],
                        self._desk_s[2],
                        self._desk_s[3],
                    )
                self._desk_s = (
                    lerp(self._desk_s[0], raw[0], sa),
                    lerp(self._desk_s[1], raw[1], sa),
                    lerp(self._desk_s[2], raw[2], sa),
                    lerp(self._desk_s[3], raw[3], sa),
                )
            desk = PlaneHit(
                kind="desk",
                cx=self._desk_s[0],
                cy=self._desk_s[1],
                w=self._desk_s[2],
                h=self._desk_s[3],
                confidence=desk.confidence,
                label=desk.label,
            )

            # Fabricator target on desk — lerp separately each paint
            target = (desk.cx, desk.cy - desk.h * 0.55)
            if desk.confidence >= 0.4 or not self.state.hold_lock:
                self._fab_good = target
            self._fab_target = self._fab_good if self.state.hold_lock else target
            self.tick_fab_lerp()

            quality = min(
                1.0,
                0.2 * len([p for p in planes if p.kind == "wall"])
                + 0.25 * (1 if floor else 0)
                + 0.35 * desk.confidence
                + 0.2 * self._tex_s
                + (0.15 if marker else 0.0),
            )
            self.state.mesh_quality = lerp(self.state.mesh_quality, quality, 0.2)

            if self.state.laser_active:
                self.state.laser_y = min(1.0, self.state.laser_y + 0.028)
                if self.state.laser_y >= 1.0:
                    self.state.laser_active = False
                    self.push_log(
                        f"MESH LOCK · {len(planes)} planes · q{int(self.state.mesh_quality * 100)}%"
                    )
                    self.save()

            self._mesh = SpatialMesh(
                nodes=nodes,
                edges=edges_i,
                planes=planes[:18],
                laser_targets=lasers[:12],
                desk=desk,
                floor=floor,
                marker=marker,
                frame_w=w,
                frame_h=h,
                ts=now,
                source="opencv+ema",
                light_lux=self._light_s,
                light_warmth=warmth,
                texture_score=self._tex_s,
                fps_est=float(self.state.target_fps),
            )
            if self.state.pc_gauges:
                self.refresh_telemetry()
        except Exception as e:
            print(f"[aerospatial] process: {e}")
        return self._mesh

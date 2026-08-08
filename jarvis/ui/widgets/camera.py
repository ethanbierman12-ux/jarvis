"""Corner live camera — prefers real EMEET, never OBS/virtual placeholders."""

from __future__ import annotations

import math
import threading
import time
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from jarvis.core.gestures import HandGestureTracker, GestureState, draw_gestures

# Physical EMEET only — never Virtual Camera
PHYSICAL_NAMES = (
    "EMEET SmartCam Nova 4K",
    "EMEET SmartCam Nova",
    "EMEET SmartCam",
    "SmartCam Nova 4K",
)

# Anything matching these is rejected hard
SKIP_TOKENS = (
    "virtual",
    "obs",
    "manycam",
    "snap camera",
    "nvidia broadcast",
    "nvidia",
    "iriun",
    "droidcam",
    "epoccam",
    "ndisource",
    "unity capture",
    "streamfx",
    "microphone",
    "audio",
    "speaker",
    "headset",
    "ir camera",
    "infrared",
    "metadata",
)


def _is_junk_name(name: str) -> bool:
    n = (name or "").lower()
    if not n:
        return True
    return any(tok in n for tok in SKIP_TOKENS)


def list_dshow_devices() -> list[str]:
    """Real USB cameras only (filters virtual/OBS/mics)."""
    names: list[str] = []
    try:
        from jarvis.core.win_process import powershell_hidden

        ps = (
            "Get-CimInstance Win32_PnPEntity | "
            "Where-Object { $_.PNPClass -eq 'Camera' -or $_.Name -match 'Cam|EMEET|Webcam' } | "
            "Select-Object -ExpandProperty Name"
        )
        out = powershell_hidden(ps, text=True, timeout=8)
        for line in out.splitlines():
            n = line.strip()
            if not n or n in names:
                continue
            if _is_junk_name(n):
                continue
            names.append(n)
    except Exception:
        pass
    return names


def list_physical_targets(extra: list[str] | None = None) -> list[str]:
    """Ordered open targets: known physical names, then discovered real cams."""
    ordered: list[str] = []
    for n in PHYSICAL_NAMES:
        if n not in ordered:
            ordered.append(n)
    for n in extra or []:
        if _is_junk_name(n):
            continue
        if n not in ordered:
            ordered.append(n)
    return ordered


class CameraOpener:
    """Headless camera open/score helper — no window, safe for theater probes."""

    def _is_obs_placeholder(self, frame: np.ndarray) -> bool:
        """True for OBS Virtual Camera idle screen (blue geometry + logo)."""
        try:
            import cv2

            small = cv2.resize(frame, (320, 180))
            b, g, r = cv2.split(small)
            blue_dom = float(np.mean(b.astype(np.float32) - np.maximum(r, g)))
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
            blue_sat = float(np.mean((hue > 90) & (hue < 130) & (sat > 40) & (val > 30)))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            cy, cx = 90, 160
            yy, xx = np.ogrid[:180, :320]
            dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
            ring = gray[(dist > 35) & (dist < 55)]
            core = gray[dist < 20]
            ring_vs_core = float(ring.mean() - core.mean()) if ring.size and core.size else 0
            hits = 0
            if blue_dom > 12:
                hits += 1
            if blue_sat > 0.15:
                hits += 2
            if ring_vs_core > 35:
                hits += 2
            # OBS crossed-cam bar sits in lower center — bright-ish gray blob on blue
            lower = gray[140:175, 130:190]
            if lower.size and blue_sat > 0.2 and float(lower.std()) < 25:
                hits += 1
            return hits >= 3
        except Exception:
            return False

    def _frame_score(self, frame: np.ndarray, *, motion: float = 0.0) -> float:
        """Higher = better live USB cam. OBS placeholder always loses."""
        if frame is None or frame.size == 0:
            return -1e9
        h, w = frame.shape[:2]
        if w < 320 or h < 240:
            return -1e9
        if self._is_obs_placeholder(frame):
            return -5000  # hard reject OBS idle screen
        mean = float(np.mean(frame))
        std = float(np.std(frame))
        if mean < 0.5 and std < 0.5:
            return -1000  # pure black
        try:
            import cv2

            small = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            # Live sensors have noise even in the dark; graphics don't
            noise = float(np.std(cv2.Laplacian(gray, cv2.CV_64F)))
            q = (small // 32).astype(np.int32)
            packed = q[:, :, 0] * 64 + q[:, :, 1] * 8 + q[:, :, 2]
            unique = int(np.unique(packed).size)
            # Prefer real motion/noise over bright static graphics
            score = (
                std * 1.5
                + noise * 0.35
                + unique * 0.8
                + motion * 40.0
                + min(mean, 80) * 0.4  # don't reward OBS brightness
                + (w * h) / 100000.0
            )
            # Tiny bonus if it looks like a usable lit scene
            if mean > 25 and std > 15:
                score += 30
            return score
        except Exception:
            return std * 2 + motion * 20 + min(mean, 80) * 0.3

    def _configure_capture(self, cap) -> None:
        """Prefer 720p + auto exposure so dark rooms still show a face."""
        try:
            import cv2

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Auto-exposure: 0.75 / 1 often means auto on DSHOW
            for prop, val in (
                (cv2.CAP_PROP_AUTO_EXPOSURE, 0.75),
                (cv2.CAP_PROP_AUTO_EXPOSURE, 1),
                (cv2.CAP_PROP_EXPOSURE, -5),
                (cv2.CAP_PROP_GAIN, 64),
            ):
                try:
                    cap.set(prop, val)
                except Exception:
                    pass
        except Exception:
            pass

    def _try_open(self, source, api) -> tuple | None:
        try:
            import cv2
        except Exception:
            return None
        try:
            cap = cv2.VideoCapture(source, api)
        except Exception:
            return None
        if not cap.isOpened():
            return None
        self._configure_capture(cap)
        frames: list = []
        for _ in range(5):
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append(frame)
            time.sleep(0.015)
        if len(frames) < 2:
            try:
                cap.release()
            except Exception:
                pass
            return None
        # Temporal motion — OBS placeholder is frozen; live cam moves/noises
        diffs = [
            float(np.mean(cv2.absdiff(a, b)))
            for a, b in zip(frames, frames[1:])
        ]
        motion = float(np.mean(diffs)) if diffs else 0.0
        best_frame = frames[-1]
        best_score = self._frame_score(best_frame, motion=motion)
        # Also score a mid frame
        mid = frames[len(frames) // 2]
        mid_score = self._frame_score(mid, motion=motion)
        if mid_score > best_score:
            best_score, best_frame = mid_score, mid
        if best_score < -1000 or self._is_obs_placeholder(best_frame):
            try:
                cap.release()
            except Exception:
                pass
            return None
        # Allow dark-but-real cameras (score can be modest)
        if best_score < -500 and motion < 0.05:
            try:
                cap.release()
            except Exception:
                pass
            return None
        return cap, best_score, best_frame.shape


class CornerCamera(QFrame, CameraOpener):
    closed = pyqtSignal()
    scan_clicked = pyqtSignal(bool)
    gesture = pyqtSignal(object)
    gesture_drag = pyqtSignal(float, float)
    gesture_swipe = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setFixedSize(440, 340)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(0,8,16,230);"
            " border: 1px solid rgba(0,240,255,140); }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        head = QHBoxLayout()
        self.title = QLabel("CAMERA")
        self.title.setObjectName("SectionTitle")
        close_btn = QPushButton("✕")
        close_btn.setObjectName("GhostBtn")
        close_btn.setFixedSize(28, 24)
        close_btn.clicked.connect(self.hide_feed)
        switch_btn = QPushButton("SWITCH")
        switch_btn.setObjectName("GhostBtn")
        switch_btn.setFixedHeight(24)
        switch_btn.clicked.connect(self._switch)
        scan_btn = QPushButton("SCAN")
        scan_btn.setObjectName("GhostBtn")
        scan_btn.setFixedHeight(24)
        scan_btn.setMinimumWidth(56)
        scan_btn.clicked.connect(lambda: self.scan_clicked.emit(True))
        self.gest_btn = QPushButton("GESTURE ON")
        self.gest_btn.setObjectName("GhostBtn")
        self.gest_btn.setFixedHeight(24)
        self.gest_btn.setCheckable(True)
        self.gest_btn.setChecked(True)
        self.gest_btn.clicked.connect(self._toggle_gestures)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.gest_btn)
        head.addWidget(scan_btn)
        head.addWidget(switch_btn)
        head.addWidget(close_btn)
        lay.addLayout(head)

        self.view = QLabel("Starting camera…")
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setStyleSheet(
            "background:#000; color:#4a6070; font-family:Consolas; font-size:11px;"
        )
        self.view.setMinimumHeight(230)
        lay.addWidget(self.view, 1)

        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setStyleSheet("color:#00f0ff; font-family:Consolas; font-size:10px;")
        self.result.setMaximumHeight(48)
        lay.addWidget(self.result)

        self._cap = None
        self._index = -1
        self._backend = ""
        self._label = ""
        self._frame = None
        self._lock = threading.Lock()
        self._prefer = "EMEET"
        self._preferred_index = 0
        self._device_names: list[str] = []
        self._name_targets: list[str] = []
        self._name_cursor = 0
        self._mirror = True
        self._fail_streak = 0
        self._gestures_on = True
        self._tracker: HandGestureTracker | None = None
        self._last_gesture = GestureState()
        self._gesture_skip = 0
        self._paint_ms = 50  # ~20 FPS — was 33ms; UI-thread CV is expensive
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._paint_frame)
        self.hide()

    def set_paint_interval(self, ms: int) -> None:
        """Throttle live paint (smooth / eco mode)."""
        self._paint_ms = max(40, min(120, int(ms)))
        if self._timer.isActive():
            self._timer.setInterval(self._paint_ms)

    def _toggle_gestures(self) -> None:
        self._gestures_on = self.gest_btn.isChecked()
        self.gest_btn.setText("GESTURE ON" if self._gestures_on else "GESTURE OFF")
        if self._gestures_on and self._tracker is None:
            self._tracker = HandGestureTracker()
        if not self._gestures_on:
            self.result.setText("Gesture control off")

    def set_gestures_enabled(self, on: bool) -> None:
        self.gest_btn.setChecked(on)
        self._toggle_gestures()

    def open_feed(self, preferred_index: int = 0, prefer: str = "EMEET") -> None:
        self._prefer = prefer
        self._preferred_index = preferred_index if preferred_index >= 0 else 0
        self._device_names = list_dshow_devices()
        self._name_targets = list_physical_targets(self._device_names)
        self.view.setText("Opening real EMEET…\n(skipping OBS / virtual)")
        self.result.setText("Looking for SmartCam Nova 4K — not Virtual Camera")
        self.show()
        self.raise_()
        if self.parent():
            pr = self.parent().rect()
            self.move(
                max(12, pr.width() - self.width() - 24),
                max(12, pr.height() - self.height() - 24),
            )
        if self._gestures_on and self._tracker is None:
            self._tracker = HandGestureTracker()
        # Longer delay so presence worker + OBS release the device
        QTimer.singleShot(700, self._open_best)

    def _release_cap(self) -> None:
        self._timer.stop()
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _open_best(self) -> None:
        self._release_cap()
        try:
            import cv2  # noqa: F401
        except Exception as e:
            self.view.setText(f"OpenCV missing: {e}")
            self.show()
            return

        from jarvis.core.camera_io import pick_best_camera, silence_opencv_logs

        with silence_opencv_logs():
            picked = pick_best_camera(
                preferred_index=self._preferred_index if self._preferred_index >= 0 else 0,
                prefer=self._prefer or "EMEET",
                max_index=5,
            )
        if picked is None:
            self.view.setText(
                "No real camera feed.\n"
                "Close OBS Virtual Camera / Zoom / Teams,\n"
                "then press SWITCH.\n"
                "Need: EMEET SmartCam Nova 4K"
            )
            self.result.setText("Blocked virtual/OBS sources")
            self.show()
            print("[camera] no usable physical feed")
            return

        cap, idx, backend, score = picked
        label = f"index {idx}"
        self._use(cap, idx, backend, label)
        print(f"[camera] chose score={score:.1f} idx={idx} {label} via {backend}")

    def _use(self, cap, index: int, backend: str, label: str) -> None:
        self._cap = cap
        self._index = index
        self._backend = backend
        self._label = label
        self._fail_streak = 0
        if "EMEET" in label.upper():
            nice = "EMEET NOVA"
        elif index >= 0:
            nice = f"CAM {index}"
        else:
            nice = "CAMERA"
        gest = " · GESTURE" if self._gestures_on else ""
        self.title.setText(nice + gest)
        self.view.setText("")
        self._timer.start(self._paint_ms)
        self.show()
        self.raise_()
        eng = self._tracker.engine if self._tracker else "off"
        self.result.setText(f"Live · {label[:42]} · gestures:{eng}")
        print(f"[camera] live index={index} backend={backend} label={label}")

    def _open_named(self, name: str) -> bool:
        # Named DSHOW open is unsupported on this OpenCV build — use index probe
        print(f"[camera] named open skipped ({name}) — using index probe")
        from jarvis.core.camera_io import pick_best_camera, silence_opencv_logs

        with silence_opencv_logs():
            picked = pick_best_camera(
                preferred_index=self._preferred_index if self._preferred_index >= 0 else 0,
                prefer=self._prefer or "EMEET",
            )
        if not picked:
            return False
        cap, idx, backend, _score = picked
        label = name if not _is_junk_name(name) else f"index {idx}"
        self._use(cap, idx, backend, label)
        return True

    def _open_index(self, index: int) -> None:
        self._release_cap()
        from jarvis.core.camera_io import open_by_index, silence_opencv_logs

        with silence_opencv_logs():
            got = open_by_index(index, reads=4)
        if not got:
            self.view.setText(f"Index {index} is virtual/black/busy.\nTry SWITCH again.")
            self.show()
            return
        cap, backend = got
        self._use(cap, index, backend, f"index {index}")

    def _switch(self) -> None:
        """Cycle camera indices (named DSHOW open is unavailable)."""
        self._release_cap()
        start = self._index if self._index >= 0 else -1
        for step in range(1, 8):
            nxt = (start + step) % 6
            self.view.setText(f"Switching to index {nxt}…")
            self._open_index(nxt)
            if self._cap is not None:
                return
        self.view.setText(
            "Could not find a real camera.\nClose OBS Virtual Camera and retry."
        )

    def hide_feed(self, emit: bool = True) -> None:
        self._release_cap()
        self.hide()
        if emit:
            self.closed.emit()

    def show_result(self, text: str) -> None:
        self.result.setText(text[:220])

    def current_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def grab_best_frame(self, reads: int = 8) -> Optional[np.ndarray]:
        if self._cap is None:
            return self.current_frame()
        best = None
        best_score = -1.0
        for _ in range(max(3, reads)):
            ok, frame = self._cap.read()
            if not ok or frame is None:
                continue
            sc = self._frame_score(frame)
            if sc > best_score:
                best_score = sc
                best = frame.copy()
        if best is not None:
            with self._lock:
                self._frame = best
            return best
        return self.current_frame()

    def _paint_frame(self) -> None:
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._fail_streak += 1
            if self._fail_streak >= 30:
                self.view.setText("Camera stalled — press SWITCH")
            return
        self._fail_streak = 0
        # If feed mutates into OBS placeholder mid-session, warn
        if self._is_obs_placeholder(frame):
            self._fail_streak += 10
            if self._fail_streak >= 30:
                self.view.setText(
                    "OBS Virtual Camera detected.\n"
                    "Close OBS Virtual Camera, then press SWITCH."
                )
                return

        with self._lock:
            self._frame = frame
        try:
            import cv2

            # Cheap night boost (subsample mean; skip CLAHE — was UI-thread heavy)
            mean = float(np.mean(frame[::8, ::8]))
            if mean < 40:
                draw = cv2.convertScaleAbs(frame, alpha=1.35, beta=22)
            else:
                draw = frame.copy()
            if self._mirror:
                draw = cv2.flip(draw, 1)
            h, w = draw.shape[:2]

            m = int(min(w, h) * 0.38)
            x0, y0 = w // 2 - m, h // 2 - m
            x1, y1 = w // 2 + m, h // 2 + m
            pulse = 120 + int(80 * abs(math.sin(time.time() * 4)))
            cv2.rectangle(draw, (x0, y0), (x1, y1), (0, pulse, 80), 2)
            L = 18
            green = (0, 255, 120)
            for ax, ay in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                sx = 1 if ax == x0 else -1
                sy = 1 if ay == y0 else -1
                cv2.line(draw, (ax, ay), (ax + sx * L, ay), green, 2)
                cv2.line(draw, (ax, ay), (ax, ay + sy * L), green, 2)

            cv2.putText(
                draw,
                "LIVE",
                (16, 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 255, 180),
                2,
                cv2.LINE_AA,
            )

            if self._gestures_on and self._tracker is not None:
                # Every 3rd frame + downscale — MediaPipe on full 4K freezes HUD
                self._gesture_skip = (self._gesture_skip + 1) % 3
                if self._gesture_skip == 0:
                    state = self._tracker.process(
                        frame, mirrored=True, max_width=320
                    )
                    self._last_gesture = state
                    self.gesture.emit(state)
                    if state.pinch and state.active:
                        self.gesture_drag.emit(state.cursor[0], state.cursor[1])
                    if state.swipe:
                        self.gesture_swipe.emit(state.swipe)
                draw = draw_gestures(draw, self._last_gesture)

            # Resize with OpenCV before Qt (SmoothTransformation on full frame = lag)
            tw = max(1, self.view.width())
            th = max(1, self.view.height())
            scale = min(tw / w, th / h)
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            if nw != w or nh != h:
                draw = cv2.resize(draw, (nw, nh), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(draw, cv2.COLOR_BGR2RGB)
            hh, ww, ch = rgb.shape
            img = QImage(rgb.data, ww, hh, ch * ww, QImage.Format.Format_RGB888).copy()
            self.view.setPixmap(QPixmap.fromImage(img))
        except Exception as e:
            self.view.setText(str(e))

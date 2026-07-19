"""Hand gesture tracking — MediaPipe HandLandmarker with OpenCV fallback."""

from __future__ import annotations

import math
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from jarvis.config import ASSETS_DIR

MODEL_PATH = ASSETS_DIR / "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

# Landmark indices
WRIST = 0
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
RING_TIP = 16
PINKY_TIP = 20
INDEX_PIP = 6
MIDDLE_PIP = 10
RING_PIP = 14
PINKY_PIP = 18
THUMB_IP = 3


@dataclass
class GestureState:
    active: bool = False
    label: str = "none"  # open | pinch | fist | point | none
    cursor: tuple[float, float] = (0.5, 0.5)  # normalized 0..1 (mirrored screen space)
    pinch: bool = False
    swipe: str = ""  # left | right | up | down | ""
    landmarks: list[tuple[float, float]] = field(default_factory=list)  # pixel x,y on frame
    engine: str = "none"


def ensure_hand_model(path: Path | None = None) -> Path | None:
    path = path or MODEL_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 100_000:
            return path
        urllib.request.urlretrieve(MODEL_URL, path)
        if path.exists() and path.stat().st_size > 100_000:
            return path
    except Exception as e:
        print(f"[gesture] model download failed: {e}")
    return path if path.exists() else None


class HandGestureTracker:
    """Process BGR frames → gesture state. Safe if MediaPipe is missing."""

    def __init__(self) -> None:
        self._landmarker = None
        self._engine = "none"
        self._ts_ms = 0
        self._pinch_hist: list[bool] = []
        self._cursor_hist: list[tuple[float, float]] = []
        self._last_swipe = 0.0
        self._pending_swipe = ""
        self._init_engine()

    def _init_engine(self) -> None:
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core import base_options

            model = ensure_hand_model()
            if model is None:
                raise RuntimeError("hand model missing")
            options = vision.HandLandmarkerOptions(
                base_options=base_options.BaseOptions(model_asset_path=str(model)),
                num_hands=1,
                min_hand_detection_confidence=0.45,
                min_hand_presence_confidence=0.45,
                min_tracking_confidence=0.45,
                running_mode=vision.RunningMode.VIDEO,
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
            self._mp = mp
            self._engine = "mediapipe"
            print("[gesture] MediaPipe HandLandmarker ready")
        except Exception as e:
            print(f"[gesture] MediaPipe unavailable ({e}) — OpenCV fallback")
            self._landmarker = None
            self._engine = "opencv"

    @property
    def engine(self) -> str:
        return self._engine

    def close(self) -> None:
        try:
            if self._landmarker is not None:
                self._landmarker.close()
        except Exception:
            pass
        self._landmarker = None

    def process(self, bgr: np.ndarray, *, mirrored: bool = True, max_width: int = 0) -> GestureState:
        if bgr is None or bgr.size == 0:
            return GestureState(engine=self._engine)
        scale = 1.0
        work = bgr
        if max_width and bgr.shape[1] > max_width:
            scale = max_width / float(bgr.shape[1])
            try:
                import cv2

                work = cv2.resize(
                    bgr,
                    (max_width, int(bgr.shape[0] * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            except Exception:
                work = bgr
                scale = 1.0
        if self._landmarker is not None:
            state = self._process_mp(work, mirrored=mirrored)
        else:
            state = self._process_cv(work, mirrored=mirrored)
        # Map landmarks back to full-frame coords if we downscaled
        if scale != 1.0 and state.landmarks:
            inv = 1.0 / scale
            state.landmarks = [(x * inv, y * inv) for x, y in state.landmarks]
        return state

    def _process_mp(self, bgr: np.ndarray, *, mirrored: bool) -> GestureState:
        try:
            import cv2

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            if mirrored:
                rgb = cv2.flip(rgb, 1)
            h, w = rgb.shape[:2]
            self._ts_ms += 33
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
            result = self._landmarker.detect_for_video(image, self._ts_ms)
            if not result.hand_landmarks:
                return GestureState(engine="mediapipe")

            lm = result.hand_landmarks[0]
            pts = [(p.x * w, p.y * h) for p in lm]
            norm = [(p.x, p.y) for p in lm]
            return self._classify(pts, norm, engine="mediapipe")
        except Exception as e:
            # One bad frame shouldn't kill the session
            if not getattr(self, "_err_once", False):
                print(f"[gesture] mp frame error: {e}")
                self._err_once = True
            return GestureState(engine="mediapipe")

    def _process_cv(self, bgr: np.ndarray, *, mirrored: bool) -> GestureState:
        """Rough skin-blob tracker — enough for drag when MediaPipe fails."""
        try:
            import cv2

            frame = cv2.flip(bgr, 1) if mirrored else bgr
            h, w = frame.shape[:2]
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (0, 30, 60), (25, 180, 255))
            mask = cv2.medianBlur(mask, 7)
            # Prefer lower-center / right side where hands usually are
            roi = mask[h // 4 : h, w // 6 : 5 * w // 6]
            cnts, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                return GestureState(engine="opencv")
            c = max(cnts, key=cv2.contourArea)
            area = cv2.contourArea(c)
            if area < 1200:
                return GestureState(engine="opencv")
            x, y, bw, bh = cv2.boundingRect(c)
            cx = (x + bw / 2) / max(1, roi.shape[1]) * (5 * w // 6 - w // 6) + w // 6
            cy = (y + bh / 2) / max(1, roi.shape[0]) * (h - h // 4) + h // 4
            nx, ny = cx / w, cy / h
            # Compact blob ≈ pinch/fist; elongated ≈ open
            aspect = bw / max(1, bh)
            pinch = area < 8000 and 0.6 < aspect < 1.6
            label = "pinch" if pinch else "open"
            pts = [(cx, cy)]
            return self._classify(pts, [(nx, ny)], engine="opencv", force_label=label)
        except Exception:
            return GestureState(engine="opencv")

    def _classify(
        self,
        pts: list[tuple[float, float]],
        norm: list[tuple[float, float]],
        *,
        engine: str,
        force_label: str | None = None,
    ) -> GestureState:
        if not norm:
            return GestureState(engine=engine)

        # Cursor = index tip if available else centroid
        if len(norm) > INDEX_TIP:
            cursor = (float(norm[INDEX_TIP][0]), float(norm[INDEX_TIP][1]))
        else:
            cursor = (float(norm[0][0]), float(norm[0][1]))

        pinch = False
        label = force_label or "open"
        if force_label is None and len(norm) > PINKY_TIP:
            # Fist first — used to lock gestures after placing a panel
            if self._is_fist(norm):
                label = "fist"
                pinch = False
            elif self._is_pinch(norm):
                pinch = True
                label = "pinch"
            elif self._is_point(norm):
                label = "point"
            else:
                label = "open"

        self._pinch_hist.append(pinch)
        if len(self._pinch_hist) > 4:
            self._pinch_hist.pop(0)
        # 2 of last 4 — snappier pinch without chatter
        pinch_stable = sum(self._pinch_hist) >= 2

        self._cursor_hist.append(cursor)
        if len(self._cursor_hist) > 6:
            self._cursor_hist.pop(0)

        swipe = ""
        now = time.time()
        if len(self._cursor_hist) >= 5 and now - self._last_swipe > 0.7:
            x0, y0 = self._cursor_hist[0]
            x1, y1 = self._cursor_hist[-1]
            dx, dy = x1 - x0, y1 - y0
            if abs(dx) > 0.18 and abs(dx) > abs(dy) * 1.25:
                swipe = "right" if dx > 0 else "left"
                self._last_swipe = now
            elif abs(dy) > 0.18 and abs(dy) > abs(dx) * 1.25:
                swipe = "down" if dy > 0 else "up"
                self._last_swipe = now

        return GestureState(
            active=True,
            label=label,
            cursor=(max(0.0, min(1.0, cursor[0])), max(0.0, min(1.0, cursor[1]))),
            pinch=pinch_stable,
            swipe=swipe,
            landmarks=pts,
            engine=engine,
        )

    @staticmethod
    def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _is_pinch(self, norm: list[tuple[float, float]]) -> bool:
        d = self._dist(norm[THUMB_TIP], norm[INDEX_TIP])
        return d < 0.085

    def _is_fist(self, norm: list[tuple[float, float]]) -> bool:
        # Tips below their PIPs (folded) relative to wrist
        folded = 0
        for tip, pip in (
            (INDEX_TIP, INDEX_PIP),
            (MIDDLE_TIP, MIDDLE_PIP),
            (RING_TIP, RING_PIP),
            (PINKY_TIP, PINKY_PIP),
        ):
            if norm[tip][1] > norm[pip][1] - 0.02:
                folded += 1
        # Compact hand = fist (even if thumb isn't fully tucked)
        span = self._dist(norm[INDEX_TIP], norm[PINKY_TIP])
        return folded >= 3 and span < 0.22

    def _is_point(self, norm: list[tuple[float, float]]) -> bool:
        index_up = norm[INDEX_TIP][1] < norm[INDEX_PIP][1]
        others = 0
        for tip, pip in (
            (MIDDLE_TIP, MIDDLE_PIP),
            (RING_TIP, RING_PIP),
            (PINKY_TIP, PINKY_PIP),
        ):
            if norm[tip][1] > norm[pip][1]:
                others += 1
        return index_up and others >= 2


def draw_gestures(
    frame_bgr: np.ndarray, state: GestureState, *, clean: bool = True
) -> np.ndarray:
    """Draw a clean gesture cursor (minimal chrome, less lag)."""
    try:
        import cv2
    except Exception:
        return frame_bgr
    if not state.active:
        return frame_bgr
    draw = frame_bgr
    h, w = draw.shape[:2]
    cx, cy = int(state.cursor[0] * w), int(state.cursor[1] * h)
    color = (0, 255, 140) if state.pinch else (0, 210, 255)

    if clean:
        # Soft ring + center — no dense landmark soup
        cv2.circle(draw, (cx, cy), 22 if state.pinch else 16, color, 2, cv2.LINE_AA)
        cv2.circle(draw, (cx, cy), 3, color, -1, cv2.LINE_AA)
        if state.pinch and len(state.landmarks) > INDEX_TIP:
            a = state.landmarks[THUMB_TIP]
            b = state.landmarks[INDEX_TIP]
            cv2.line(
                draw,
                (int(a[0]), int(a[1])),
                (int(b[0]), int(b[1])),
                color,
                2,
                cv2.LINE_AA,
            )
        # Tiny status pill
        tag = "DRAG" if state.pinch else state.label.upper()[:6]
        cv2.putText(
            draw,
            tag,
            (cx + 28, cy + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )
        return draw

    # Legacy denser overlay
    if state.landmarks:
        for i, (x, y) in enumerate(state.landmarks):
            cv2.circle(draw, (int(x), int(y)), 3 if i not in (4, 8) else 6, (0, 255, 200), -1)
    cv2.drawMarker(draw, (cx, cy), color, cv2.MARKER_CROSS, 18, 2)
    return draw

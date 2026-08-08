"""Shared camera open helpers — index-only on Windows (no DSHOW-by-name)."""

from __future__ import annotations

import contextlib
import os
import time
from typing import Any, Iterator, Optional

# Mute OpenCV/FFmpeg device-list noise before cv2 is imported elsewhere
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "error")

import numpy as np

# OpenCV builds on Windows often cannot open "video=Device Name" via CAP_DSHOW.
# Opening by index (DSHOW → MSMF) is the reliable path.


@contextlib.contextmanager
def silence_opencv_logs() -> Iterator[None]:
    """Mute OpenCV WARN spam while probing missing indices / unsupported modes."""
    prev = os.environ.get("OPENCV_LOG_LEVEL")
    os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
    try:
        import cv2

        try:
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        except Exception:
            pass
        yield
    finally:
        if prev is None:
            os.environ.pop("OPENCV_LOG_LEVEL", None)
        else:
            os.environ["OPENCV_LOG_LEVEL"] = prev


def is_obs_placeholder(frame: np.ndarray) -> bool:
    try:
        import cv2

        small = cv2.resize(frame, (320, 180))
        b, g, r = cv2.split(small)
        blue_dom = float(np.mean(b.astype(np.float32) - np.maximum(r, g)))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        blue_sat = float(np.mean((hue > 90) & (hue < 130) & (sat > 40) & (val > 30)))
        return blue_sat > 0.2 and blue_dom > 12
    except Exception:
        return False


def configure_capture(
    cap: Any,
    *,
    max_width: int = 1280,
    max_height: int = 720,
) -> None:
    try:
        import cv2

        w = max(320, min(1920, int(max_width or 1280)))
        h = max(240, min(1080, int(max_height or 720)))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for prop, val in (
            (cv2.CAP_PROP_AUTO_EXPOSURE, 0.75),
            (cv2.CAP_PROP_AUTO_EXPOSURE, 1),
        ):
            try:
                cap.set(prop, val)
            except Exception:
                pass
    except Exception:
        pass


def open_by_index(
    index: int,
    *,
    reads: int = 3,
    max_width: int = 1280,
    max_height: int = 720,
) -> tuple[Any, str] | None:
    """Open a camera by numeric index. Tries DSHOW then MSMF. Never opens by name."""
    try:
        import cv2
    except Exception:
        return None
    if index < 0:
        return None
    # DSHOW first; MSMF only if DSHOW cannot open (avoids ffmpeg dshow list spam)
    backends = (
        (cv2.CAP_DSHOW, "DSHOW"),
        (cv2.CAP_MSMF, "MSMF"),
    )
    with silence_opencv_logs():
        for api, label in backends:
            cap = None
            try:
                cap = cv2.VideoCapture(int(index), api)
            except Exception:
                continue
            if cap is None or not cap.isOpened():
                try:
                    if cap is not None:
                        cap.release()
                except Exception:
                    pass
                continue
            configure_capture(cap, max_width=max_width, max_height=max_height)
            ok_frame = None
            for _ in range(max(1, reads)):
                ok, fr = cap.read()
                if ok and fr is not None:
                    ok_frame = fr
                    break
                time.sleep(0.02)
            if ok_frame is None:
                try:
                    cap.release()
                except Exception:
                    pass
                continue
            return cap, label
    return None


def score_frame(frame: np.ndarray, *, motion: float = 0.0) -> float:
    if frame is None or getattr(frame, "size", 0) == 0:
        return -1e9
    if is_obs_placeholder(frame):
        return -5000.0
    mean = float(np.mean(frame))
    std = float(np.std(frame))
    if mean < 0.5 and std < 0.5:
        return -1000.0
    try:
        import cv2

        small = cv2.resize(frame, (160, 90))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        noise = float(np.std(cv2.Laplacian(gray, cv2.CV_64F)))
        score = (
            std * 2.0
            + noise * 0.35
            + motion * 30.0
            + min(mean, 80) * 0.3
            + (frame.shape[1] * frame.shape[0]) / 100000.0
        )
        return score
    except Exception:
        return std * 2 + motion * 20 + min(mean, 80) * 0.3


def probe_index(index: int) -> tuple[float, Optional[Any], str]:
    """
    Score an index without keeping a long-lived handle unless useful.
    Returns (score, open_cap_or_None, backend). Cap is open only if score is usable.
    """
    got = open_by_index(index, reads=4)
    if not got:
        return -1e9, None, ""
    cap, backend = got
    try:
        import cv2

        frames = []
        for _ in range(3):
            ok, fr = cap.read()
            if ok and fr is not None:
                frames.append(fr)
            time.sleep(0.015)
        if not frames:
            cap.release()
            return -1e9, None, ""
        motion = 0.0
        if len(frames) >= 2:
            motion = float(np.mean(cv2.absdiff(frames[0], frames[-1])))
        sc = score_frame(frames[-1], motion=motion)
        # Accept dim night rooms; only hard-reject OBS placeholder / pure black
        if sc < -500 or is_obs_placeholder(frames[-1]):
            cap.release()
            return sc, None, backend
        return sc, cap, backend
    except Exception:
        try:
            cap.release()
        except Exception:
            pass
        return -1e9, None, ""


def pick_best_camera(
    preferred_index: int = 0,
    prefer: str = "EMEET",
    max_index: int = 8,
) -> tuple[Any, int, str, float] | None:
    """
    Pick the best live USB camera by index only.
    Prefers preferred_index, skips OBS placeholders, returns (cap, index, backend, score).
    """
    order: list[int] = []
    if preferred_index >= 0:
        order.append(int(preferred_index))
    for i in range(max_index + 1):
        if i not in order:
            order.append(i)

    best: tuple[float, Any, int, str] | None = None
    extras: list[Any] = []

    with silence_opencv_logs():
        for idx in order:
            sc, cap, backend = probe_index(idx)
            if cap is None:
                continue
            bonus = 0.0
            if idx == preferred_index:
                bonus += 50.0
            # Mild bias toward early USB indices (common for EMEET)
            if prefer and prefer.upper() in ("EMEET", "SMARTCAM") and idx <= 2:
                bonus += 12.0
            total = sc + bonus
            if best is None or total > best[0]:
                if best is not None:
                    extras.append(best[1])
                best = (total, cap, idx, backend)
            else:
                extras.append(cap)
            if total >= 40 and idx == preferred_index:
                break

    for c in extras:
        try:
            c.release()
        except Exception:
            pass

    if best is None:
        return None
    score, cap, idx, backend = best
    print(f"[camera] using index {idx} via {backend} (score={score:.1f})")
    return cap, idx, backend, score

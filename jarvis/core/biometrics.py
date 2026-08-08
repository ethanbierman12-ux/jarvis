"""Biometrics from webcam — posture heuristics + simple rPPG heart-rate estimate."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

import numpy as np


@dataclass
class BioSnapshot:
    posture_ok: bool = True
    slouch_score: float = 0.0
    heart_rate_bpm: float = 0.0
    looking_at_screen: bool = True
    face_present: bool = False
    gaze_zone: str = "away"  # center | up | left | right | down | away
    face_cx: float = 0.5
    face_cy: float = 0.5
    brightness: float = 0.0  # 0..1 mean face luma


class Biometrics:
    def __init__(self) -> None:
        self._green: Deque[float] = deque(maxlen=150)
        self._times: Deque[float] = deque(maxlen=150)
        self.last = BioSnapshot()
        self._slouch_since: float | None = None
        self._hr_high_since: float | None = None

    def analyze(self, frame: np.ndarray, face_box=None) -> BioSnapshot:
        import time

        import cv2

        h, w = frame.shape[:2]
        looking = True
        face_present = False
        slouch = 0.0
        posture_ok = True

        if face_box is None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            faces = cascade.detectMultiScale(gray, 1.2, 4, minSize=(60, 60))
            if len(faces):
                face_box = max(faces, key=lambda r: r[2] * r[3])

        roi = None
        gaze_zone = "away"
        fcx = fcy = 0.5
        brightness = 0.0
        if face_box is not None:
            face_present = True
            x, y, fw, fh = [int(v) for v in face_box]
            cx = (x + fw / 2) / w
            cy = (y + fh / 2) / h
            fcx, fcy = cx, cy
            # Looking at any of the three monitors (allow higher cy for top-deck glance)
            looking = 0.12 < cx < 0.88 and cy < 0.88 and (fw * fh) / (w * h) > 0.012
            # Webcam on center-monitor bezel:
            # look UP (top deck) → head tilts back → face center drops (higher cy)
            # look DOWN (desk) → chin tucks → face rises (lower cy)
            # look LEFT/RIGHT → face shifts on X (non-mirrored capture)
            face_area = (fw * fh) / float(w * h)
            if not looking:
                gaze_zone = "away"
            elif cy > 0.55 and face_area < 0.14:
                # Looking up at top monitor (face lower + not a close lean-in)
                gaze_zone = "up"
            elif cy < 0.34:
                gaze_zone = "down"
            elif cx < 0.34:
                gaze_zone = "left"
            elif cx > 0.66:
                gaze_zone = "right"
            else:
                gaze_zone = "center"
            # Slouch: lean toward center screen — face low AND large in frame
            if cy > 0.62 and face_area > 0.06:
                slouch = min(1.0, (cy - 0.55) / 0.35)
                posture_ok = slouch < 0.45
            elif cy > 0.70:
                slouch = min(1.0, (cy - 0.55) / 0.35)
                posture_ok = slouch < 0.45
            # Forehead ROI for rPPG + brightness
            fy0 = max(0, y)
            fy1 = max(fy0 + 1, y + int(fh * 0.25))
            fx0 = max(0, x + int(fw * 0.25))
            fx1 = min(w, x + int(fw * 0.75))
            roi = frame[fy0:fy1, fx0:fx1]
            try:
                face_crop = frame[y : y + fh, x : x + fw]
                if face_crop.size:
                    gray_f = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                    brightness = float(np.mean(gray_f)) / 255.0
            except Exception:
                brightness = 0.0
        else:
            looking = False
            gaze_zone = "away"

        hr = 0.0
        now = time.time()
        if roi is not None and roi.size > 0:
            g = float(np.mean(roi[:, :, 1]))
            self._green.append(g)
            self._times.append(now)
            hr = self._estimate_hr()

        snap = BioSnapshot(
            posture_ok=posture_ok,
            slouch_score=slouch,
            heart_rate_bpm=hr,
            looking_at_screen=looking,
            face_present=face_present,
            gaze_zone=gaze_zone,
            face_cx=fcx,
            face_cy=fcy,
            brightness=brightness,
        )
        self.last = snap
        return snap

    def _estimate_hr(self) -> float:
        if len(self._green) < 64:
            return 0.0
        try:
            import time

            y = np.array(self._green, dtype=np.float64)
            y = y - np.mean(y)
            if np.std(y) < 1e-6:
                return 0.0
            # FFT peak in 0.8–2.5 Hz (48–150 bpm)
            t0, t1 = self._times[0], self._times[-1]
            duration = max(1e-3, t1 - t0)
            fps = (len(self._times) - 1) / duration
            spec = np.abs(np.fft.rfft(y))
            freqs = np.fft.rfftfreq(len(y), d=1.0 / max(fps, 1.0))
            mask = (freqs >= 0.8) & (freqs <= 2.5)
            if not np.any(mask):
                return 0.0
            peak = freqs[mask][int(np.argmax(spec[mask]))]
            return float(peak * 60.0)
        except Exception:
            return 0.0

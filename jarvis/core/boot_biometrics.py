"""Boot biometrics — face/eye check + code-word fallback for PC power-on.

Designed to NEVER lock you out on a flaky camera:
  - No enrollment → enroll on first success (setup), never lock
  - Ambiguous / no face → code-word challenge, never lock
  - Clear mismatch → code-word (3 tries), lock only if all fail
  - Preview / --no-lock → never call LockWorkStation
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jarvis.config import DATA_DIR, Settings
from jarvis.core.security_gate import SecurityGate


DEFAULT_CODEWORD = "jarvis"


def is_night_hours(*, tz_name: str = "America/New_York") -> bool:
    """True during local night window (night vision allowed)."""
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.now()
    # Philly-ish: night vision only 8pm–6am
    return now.hour >= 20 or now.hour < 6



@dataclass
class BioResult:
    ok: bool
    kind: str  # enrolled | matched | codeword | failed | skipped
    message: str
    score: float = -1.0
    should_lock: bool = False


def boot_codeword() -> str:
    try:
        w = str(getattr(Settings.load(), "pc_boot_codeword", "") or "").strip().lower()
        if len(w) >= 3:
            return w
    except Exception:
        pass
    return DEFAULT_CODEWORD


def normalize_codeword(text: str) -> str:
    t = " ".join((text or "").lower().split())
    return "".join(c for c in t if c.isalnum() or c.isspace()).strip()


class BootBiometrics:
    """Camera verify against SecurityGate owner enrollment."""

    FACE_TRIES = 3
    CODE_TRIES = 3
    # Night-friendly thresholds (desk cams get noisy in the dark)
    MATCH_OK = 0.32
    MATCH_SOFT = 0.26
    EYE_OK = 0.35  # was 0.5 — eyes often vanish under IR/dark
    EYE_SOFT = 0.20

    def __init__(self) -> None:
        settings = Settings.load()
        self.settings = settings
        self.gate = SecurityGate(DATA_DIR, user_name=settings.user_name or "Sir")
        self.codeword = boot_codeword()
        self._cam = None
        self._last_frame = None
        self._feed_mode = "day"
        self._night_cache_until = 0.0
        self._night_cached = False
        self._grab_n = 0
        self._face_fails = 0
        self._code_fails = 0

    @property
    def enrolled(self) -> bool:
        return self.gate.enroll_path.exists() and self.gate._owner_hist is not None

    def open_camera(self) -> bool:
        try:
            import cv2

            prefer = (getattr(self.settings, "camera_prefer", "") or "").lower()
            idx = int(getattr(self.settings, "camera_index", 0) or 0)
            order = [idx] + [i for i in range(4) if i != idx]
            for i in order:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(i)
                if not cap.isOpened():
                    continue
                # Night / low-light camera hints (best-effort; many cams ignore)
                try:
                    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)  # auto on (DirectShow quirk)
                except Exception:
                    pass
                try:
                    cap.set(cv2.CAP_PROP_EXPOSURE, -4)  # brighter if manual
                except Exception:
                    pass
                try:
                    cap.set(cv2.CAP_PROP_GAIN, 80)
                except Exception:
                    pass
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                for _ in range(3):
                    cap.read()
                ok, frame = cap.read()
                if ok and frame is not None:
                    self._cam = cap
                    processed, mode = self.process_frame(frame)
                    self._last_frame = processed
                    self._feed_mode = mode
                    _ = prefer
                    return True
                cap.release()
            return False
        except Exception as e:
            print(f"[boot-bio] camera: {e}")
            return False

    def close(self) -> None:
        try:
            if self._cam is not None:
                self._cam.release()
        except Exception:
            pass
        self._cam = None

    def grab(self) -> Any | None:
        try:
            if self._cam is None:
                return self._last_frame
            ok, frame = self._cam.read()
            if ok and frame is not None:
                processed, mode = self.process_frame(frame)
                self._last_frame = processed
                self._feed_mode = mode
                return self._last_frame
        except Exception:
            pass
        return self._last_frame

    @property
    def feed_mode(self) -> str:
        return getattr(self, "_feed_mode", "day")

    def process_frame(self, frame) -> tuple[Any, str]:
        """Return (frame, mode) — night vision ONLY at night when scene is dark."""
        if frame is None:
            return None, "day"
        now = time.time()
        if now >= self._night_cache_until:
            self._night_cached = is_night_hours()
            self._night_cache_until = now + 30.0
        if not self._night_cached:
            return frame, "day"
        self._grab_n += 1
        dark = self._is_dark(frame) if self._grab_n % 8 == 0 else (
            getattr(self, "_last_dark", False)
        )
        self._last_dark = dark
        if dark:
            return self._night_enhance(frame), "night"
        return frame, "day"

    def _is_dark(self, frame) -> bool:
        try:
            import cv2

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return float(np.mean(gray)) < 70.0
        except Exception:
            return False

    def _night_enhance(self, frame):
        """IR-style night vision boost — call only when is_night_hours + dark."""
        if frame is None:
            return frame
        try:
            import cv2

            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
            l2 = clahe.apply(l)
            out = cv2.cvtColor(cv2.merge([l2, a, b]), cv2.COLOR_LAB2BGR)
            gamma = 0.55
            table = np.array(
                [((i / 255.0) ** gamma) * 255 for i in range(256)]
            ).astype("uint8")
            out = cv2.LUT(out, table)
            out = cv2.bilateralFilter(out, 5, 40, 40)
            blur = cv2.GaussianBlur(out, (0, 0), 1.1)
            out = cv2.addWeighted(out, 1.35, blur, -0.35, 0)
            # Subtle green NV tint so day vs night feed is obvious
            tint = out.astype("float32")
            tint[:, :, 1] = np.clip(tint[:, :, 1] * 1.15, 0, 255)
            tint[:, :, 2] = np.clip(tint[:, :, 2] * 0.75, 0, 255)
            return tint.astype("uint8")
        except Exception:
            return frame

    def _eye_score(self, face_bgr) -> float:
        """0..1 eye visibility — night-tolerant (CLAHE + softer cascade)."""
        try:
            import cv2

            # Enhance face crop again for eyes only at night
            face = face_bgr
            if is_night_hours() and self._is_dark(face_bgr):
                face = self._night_enhance(face_bgr)
            gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
            try:
                clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
                gray = clahe.apply(gray)
            except Exception:
                gray = cv2.equalizeHist(gray)

            cascades = [
                "haarcascade_eye.xml",
                "haarcascade_eye_tree_eyeglasses.xml",
            ]
            best = 0
            for name in cascades:
                eye = cv2.CascadeClassifier(cv2.data.haarcascades + name)
                if eye.empty():
                    continue
                for kw in (
                    dict(scaleFactor=1.08, minNeighbors=2, minSize=(8, 8)),
                    dict(scaleFactor=1.05, minNeighbors=1, minSize=(6, 6)),
                ):
                    eyes = eye.detectMultiScale(gray, **kw)
                    best = max(best, len(eyes))
            if best >= 2:
                return 1.0
            if best == 1:
                return 0.7
            # At night, missing eyes shouldn't kill a strong face match
            return 0.4 if self._is_dark(face_bgr) else 0.2
        except Exception:
            return 0.45

    def match_frame(self, frame) -> tuple[float, float]:
        """Return (face_score, eye_score). face_score -1 = no face."""
        if frame is None:
            return -1.0, 0.0
        if not self.enrolled:
            return -1.0, 0.0
        try:
            import cv2
            import tempfile

            enhanced, mode = self.process_frame(frame)
            # Prefer real face; allow soft center fallback only on night feed
            box = self.gate._find_face_box(
                enhanced, allow_center_fallback=(mode == "night")
            )
            if not box:
                return -1.0, 0.0
            x, y, w, h = box
            crop = enhanced[y : y + h, x : x + w]
            eye = self._eye_score(crop)
            tmp = Path(tempfile.gettempdir()) / "jarvis_boot_face.jpg"
            cv2.imwrite(str(tmp), enhanced)
            score = float(self.gate.match_score(tmp))
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return score, eye
        except Exception as e:
            print(f"[boot-bio] match: {e}")
            return -1.0, 0.0

    def enroll_frame(self, frame) -> BioResult:
        if frame is None:
            return BioResult(False, "failed", "No camera frame — face the cam.")
        enhanced, _mode = self.process_frame(frame)
        msg = self.gate.enroll_from_bgr(enhanced, allow_fallback=True)
        ok = "enrolled" in msg.lower() and "failed" not in msg.lower()
        return BioResult(ok, "enrolled" if ok else "failed", msg, should_lock=False)

    def verify_once(self) -> BioResult:
        """Single capture attempt. Never sets should_lock by itself."""
        frame = self.grab()
        if frame is None:
            return BioResult(
                False, "failed", "Camera not ready.", should_lock=False
            )

        if not self.enrolled:
            return self.enroll_frame(frame)

        score, eye = self.match_frame(frame)
        if score < 0:
            return BioResult(
                False,
                "failed",
                "No face detected — look at the camera.",
                score=score,
                should_lock=False,
            )

        dark = self._is_dark(frame)
        night = self.feed_mode == "night" or (is_night_hours() and dark)
        # Strong match
        if score >= self.MATCH_OK and eye >= self.EYE_OK:
            tag = "night vision" if night else "day feed"
            return BioResult(
                True,
                "matched",
                f"Owner confirmed · {tag} {int(score * 100)}%.",
                score=score,
                should_lock=False,
            )
        # Soft match — night allows weaker eyes
        if score >= self.MATCH_SOFT and eye >= self.EYE_SOFT:
            return BioResult(
                True,
                "matched",
                f"Owner confirmed · soft match {int(score * 100)}%.",
                score=score,
                should_lock=False,
            )
        # Strong face alone at night (eyes often invisible under IR/dark)
        if night and score >= self.MATCH_OK:
            return BioResult(
                True,
                "matched",
                f"Owner confirmed · night face {int(score * 100)}%.",
                score=score,
                should_lock=False,
            )

        self._face_fails += 1
        return BioResult(
            False,
            "failed",
            f"Face not confirmed ({int(max(0, score) * 100)}%). "
            "Type your code word.",
            score=score,
            should_lock=False,
        )

    def check_codeword(self, heard: str) -> BioResult:
        got = normalize_codeword(heard)
        want = normalize_codeword(self.codeword)
        if not got:
            return BioResult(False, "failed", "No code word heard.", should_lock=False)
        # Exact match, or codeword as a whole word in a longer phrase.
        # Never accept substrings (e.g. "j" / "jar" must NOT match "jarvis").
        words = got.split()
        if got == want or want in words:
            self._code_fails = 0
            return BioResult(
                True,
                "codeword",
                "Code word accepted. Identity verified.",
                should_lock=False,
            )
        self._code_fails += 1
        remaining = max(0, self.CODE_TRIES - self._code_fails)
        lock = self._code_fails >= self.CODE_TRIES
        return BioResult(
            False,
            "failed",
            (
                "Code word incorrect. Workstation will lock."
                if lock
                else f"Code word incorrect. {remaining} tries left."
            ),
            should_lock=lock,
        )

    def lock_workstation(self) -> None:
        try:
            import ctypes

            ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            print(f"[boot-bio] lock: {e}")

"""Desk security — enroll face, greet owner, flag intruders, workspace lock."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class SecurityEvent:
    kind: str  # greet | lock | intruder | enroll | status | nudge
    message: str
    snapshot: str = ""


class SecurityGate:
    """
    Lightweight owner recognition using brightness/edges histogram match
    against enrolled face crops (no cloud).

    Matching is intentionally tolerant of desk lighting drift. Intruder
    alerts require a clear mismatch streak + long cooldown so the owner
    is not spammed with false positives.
    """

    # Scores are 0..1 (1 = strong match). Ambiguous band stays quiet.
    OWNER_SCORE = 0.36  # accept as owner (was 0.52 — too strict for HSV)
    INTRUDER_SCORE = 0.22  # clear mismatch only
    INTRUDER_STREAK = 3  # consecutive clear mismatches before alert
    INTRUDER_COOLDOWN_SEC = 720.0  # 12 min between spoken alerts
    WEAK_NUDGE_COOLDOWN_SEC = 3600.0  # re-enroll tip at most hourly

    def __init__(self, data_dir: Path, user_name: str = "Sir") -> None:
        self.dir = Path(data_dir) / "security"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.enroll_path = self.dir / "owner_face.jpg"
        self.meta_path = self.dir / "security.json"
        self.user_name = user_name or "Sir"
        self.enabled = True
        self.intruder_alert = True
        self.greet_on_sit = True
        self.lock_on_leave = True
        self.intruder_cooldown_sec = self.INTRUDER_COOLDOWN_SEC
        self._owner_hist: np.ndarray | None = None
        self._last_present = False
        self._greeted_at = 0.0
        self._intruder_at = 0.0
        self._weak_nudge_at = 0.0
        self._away_logged = False
        self._mismatch_streak = 0
        self._load()

    def _load(self) -> None:
        if self.meta_path.exists():
            try:
                meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
                self.enabled = bool(meta.get("enabled", True))
                self.intruder_alert = bool(meta.get("intruder_alert", True))
                self.greet_on_sit = bool(meta.get("greet_on_sit", True))
                self.lock_on_leave = bool(meta.get("lock_on_leave", True))
                cd = meta.get("intruder_cooldown_sec")
                if cd is not None:
                    self.intruder_cooldown_sec = float(cd)
            except Exception:
                pass
        if self.enroll_path.exists():
            self._owner_hist = self._hist_from_path(self.enroll_path)

    def _save_meta(self) -> None:
        self.meta_path.write_text(
            json.dumps(
                {
                    "enabled": self.enabled,
                    "intruder_alert": self.intruder_alert,
                    "greet_on_sit": self.greet_on_sit,
                    "lock_on_leave": self.lock_on_leave,
                    "intruder_cooldown_sec": self.intruder_cooldown_sec,
                    "enrolled": self.enroll_path.exists(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def status(self) -> str:
        enrolled = "enrolled" if self.enroll_path.exists() else "not enrolled"
        return (
            f"Security {('armed' if self.enabled else 'off')} · face {enrolled} · "
            f"greet={'on' if self.greet_on_sit else 'off'} · "
            f"intruder={'on' if self.intruder_alert else 'off'} · "
            f"cooldown={int(self.intruder_cooldown_sec)}s."
        )

    def set_intruder_alert(self, on: bool) -> str:
        self.intruder_alert = bool(on)
        self._mismatch_streak = 0
        try:
            self._save_meta()
        except Exception:
            pass
        return (
            "Intruder alerts on."
            if self.intruder_alert
            else "Intruder alerts off. Face greet still works if armed."
        )

    def _find_face_box(
        self, img, *, allow_center_fallback: bool = False
    ) -> tuple[int, int, int, int] | None:
        """Return largest (x,y,w,h) face; tolerant of dark / close-up desk cams."""
        try:
            import cv2

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            try:
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                gray = clahe.apply(gray)
            except Exception:
                gray = cv2.equalizeHist(gray)

            cascades = [
                "haarcascade_frontalface_default.xml",
                "haarcascade_frontalface_alt2.xml",
                "haarcascade_profileface.xml",
            ]
            params = [
                dict(scaleFactor=1.08, minNeighbors=3, minSize=(40, 40)),
                dict(scaleFactor=1.05, minNeighbors=2, minSize=(32, 32)),
                dict(scaleFactor=1.12, minNeighbors=4, minSize=(48, 48)),
            ]
            best = None
            best_area = 0
            for name in cascades:
                path = cv2.data.haarcascades + name
                cascade = cv2.CascadeClassifier(path)
                if cascade.empty():
                    continue
                for kw in params:
                    faces = cascade.detectMultiScale(gray, **kw)
                    for x, y, w, h in faces:
                        area = int(w) * int(h)
                        if area > best_area:
                            best_area = area
                            best = (int(x), int(y), int(w), int(h))
            if best:
                return best

            if not allow_center_fallback:
                return None

            h, w = gray.shape[:2]
            if h < 40 or w < 40:
                return None
            cx0, cy0 = int(w * 0.2), int(h * 0.08)
            cx1, cy1 = int(w * 0.8), int(h * 0.72)
            return (cx0, cy0, cx1 - cx0, cy1 - cy0)
        except Exception:
            return None

    def enroll_from_bgr(self, img, *, allow_fallback: bool = True) -> str:
        """Enroll from an in-memory BGR frame (preferred — freshest)."""
        if img is None:
            return "No camera frame yet — face the cam and say enroll my face again."
        try:
            import cv2

            box = self._find_face_box(img, allow_center_fallback=allow_fallback)
            if not box:
                return "No face found to enroll. Face the camera and try again."
            x, y, w, h = box
            pad = int(min(w, h) * 0.18)
            H, W = img.shape[:2]
            x0 = max(0, x - pad)
            y0 = max(0, y - pad)
            x1 = min(W, x + w + pad)
            y1 = min(H, y + h + pad)
            crop = img[y0:y1, x0:x1]
            if crop.size == 0:
                return "Could not crop a face — try again."
            # Stabilize enrollment under uneven desk light
            try:
                lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                l2 = clahe.apply(l)
                crop = cv2.cvtColor(cv2.merge([l2, a, b]), cv2.COLOR_LAB2BGR)
            except Exception:
                pass
            cv2.imwrite(str(self.enroll_path), crop)
            self._owner_hist = self._hist_from_bgr(crop)
            self._mismatch_streak = 0
            self._save_meta()
            return f"Face enrolled for {self.user_name}. I'll greet you when you sit down."
        except Exception as e:
            return f"Enroll failed: {e}"

    def enroll_from_image(self, image_path: str | Path) -> str:
        src = Path(image_path)
        if not src.exists():
            return "No camera snapshot available — sit in view and say enroll my face again."
        try:
            import cv2

            img = cv2.imread(str(src))
            if img is None:
                return "Could not read the vision snapshot."
            return self.enroll_from_bgr(img, allow_fallback=False)
        except Exception as e:
            return f"Enroll failed: {e}"

    def enroll_from_candidates(
        self, frames: list[Any], paths: list[str | Path] | None = None
    ) -> str:
        """Try multiple live frames / files until cascade finds a real face."""
        tried = 0
        last = "No face found to enroll. Face the camera and try again."
        for img in frames:
            if img is None:
                continue
            tried += 1
            msg = self.enroll_from_bgr(img, allow_fallback=True)
            if "enrolled" in msg.lower() and "failed" not in msg.lower():
                return msg
            last = msg
        for p in paths or []:
            path = Path(p)
            if not path.exists():
                continue
            tried += 1
            msg = self.enroll_from_image(path)
            if (
                "enrolled" in msg.lower()
                and "failed" not in msg.lower()
                and "no face" not in msg.lower()
            ):
                return msg
            last = msg
        if tried == 0:
            return (
                "No camera snapshot available — open the camera, face it, "
                "and say enroll my face."
            )
        return last

    def _hist_from_path(self, path: Path) -> np.ndarray | None:
        try:
            import cv2

            img = cv2.imread(str(path))
            if img is None:
                return None
            return self._hist_from_bgr(img)
        except Exception:
            return None

    def _hist_from_bgr(self, img) -> np.ndarray | None:
        """HSV + CLAHE-gray hist concatenated for stabler desk lighting."""
        try:
            import cv2

            small = cv2.resize(img, (64, 64))
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            hist_hsv = cv2.calcHist([hsv], [0, 1], None, [12, 12], [0, 180, 0, 256])
            cv2.normalize(hist_hsv, hist_hsv)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            try:
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                gray = clahe.apply(gray)
            except Exception:
                gray = cv2.equalizeHist(gray)
            hist_g = cv2.calcHist([gray], [0], None, [32], [0, 256])
            cv2.normalize(hist_g, hist_g)
            return np.concatenate(
                [hist_hsv.flatten(), hist_g.flatten()]
            ).astype(np.float32)
        except Exception:
            return None

    def _compare_hists(self, a: np.ndarray, b: np.ndarray) -> float:
        try:
            import cv2

            # Split HSV block vs gray block if both full-size
            if a.shape == b.shape and a.size >= 12 * 12 + 32:
                hsv_n = 12 * 12
                s1 = float(
                    cv2.compareHist(
                        a[:hsv_n].reshape(12, 12),
                        b[:hsv_n].reshape(12, 12),
                        cv2.HISTCMP_CORREL,
                    )
                )
                s2 = float(
                    cv2.compareHist(
                        a[hsv_n:].reshape(-1, 1),
                        b[hsv_n:].reshape(-1, 1),
                        cv2.HISTCMP_CORREL,
                    )
                )
                # Prefer gray/CLAHE under changing desk light
                score = 0.45 * s1 + 0.55 * s2
            else:
                h1 = a.astype(np.float32)
                h2 = b.astype(np.float32)
                score = float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
            return max(0.0, min(1.0, (score + 1.0) / 2.0))
        except Exception:
            return 0.0

    def match_score(self, image_path: str | Path) -> float:
        """0..1 similarity to enrolled owner (1 = strong match). Crops face first."""
        if self._owner_hist is None:
            return 0.0
        try:
            import cv2

            img = cv2.imread(str(image_path))
            if img is None:
                return -1.0  # unreadable / missing — never treat as intruder
            # Prefer cascade; allow mild center crop so owner isn't "unknown"
            # when Haar flakes — still requires a crop for scoring.
            box = self._find_face_box(img, allow_center_fallback=True)
            if box is None:
                return -1.0  # no usable crop → never treat as intruder
            x, y, w, h = box
            crop = img[y : y + h, x : x + w]
            other = self._hist_from_bgr(crop)
            if other is None:
                return 0.0
            # Recompute owner hist if enrollment used older format length
            if self._owner_hist.shape != other.shape:
                refreshed = self._hist_from_path(self.enroll_path)
                if refreshed is not None:
                    self._owner_hist = refreshed
                if self._owner_hist is None or self._owner_hist.shape != other.shape:
                    return -1.0  # can't compare — stay quiet
            return self._compare_hists(self._owner_hist, other)
        except Exception:
            return 0.0

    def _maybe_intruder(self, now: float, snapshot_path: str, score: float) -> SecurityEvent | None:
        """Require clear mismatch streak + long cooldown before alerting."""
        if not self.intruder_alert:
            self._mismatch_streak = 0
            return None
        if score < 0:
            # No face / unscored — reset streak, stay quiet
            self._mismatch_streak = 0
            return None
        if score >= self.OWNER_SCORE:
            self._mismatch_streak = 0
            return None
        if score >= self.INTRUDER_SCORE:
            # Ambiguous — not owner-clear, not intruder-clear
            self._mismatch_streak = 0
            return None

        self._mismatch_streak += 1
        if self._mismatch_streak < self.INTRUDER_STREAK:
            return None
        if now - self._intruder_at < self.intruder_cooldown_sec:
            return None

        self._intruder_at = now
        self._mismatch_streak = 0
        return SecurityEvent(
            "intruder",
            "Intruder alert — face does not match enrolled biometrics.",
            snapshot_path,
        )

    def on_presence(
        self,
        present: bool,
        *,
        snapshot_path: str = "",
        motion: float = 0.0,
    ) -> SecurityEvent | None:
        if not self.enabled:
            self._last_present = present
            self._mismatch_streak = 0
            return None

        now = time.time()
        # Sit down → greet if owner
        if present and not self._last_present:
            self._last_present = True
            self._away_logged = False
            self._mismatch_streak = 0
            if not self.greet_on_sit:
                return None
            if now - self._greeted_at < 90:
                return None
            enrolled = self.enroll_path.exists() and self._owner_hist is not None
            if not enrolled:
                self._greeted_at = now
                return SecurityEvent(
                    "greet",
                    f"Welcome back, {self.user_name}. Say enroll my face to lock biometrics.",
                    snapshot_path,
                )
            score = self.match_score(snapshot_path) if snapshot_path else -1.0
            if score < 0:
                # Present by motion but no usable face yet — wait, don't intruder
                return None
            if score >= self.OWNER_SCORE:
                self._greeted_at = now
                return SecurityEvent(
                    "greet",
                    f"Welcome back, {self.user_name}. Workspace unlocked.",
                    snapshot_path,
                )
            # Clear mismatch on sit-down: still don't spam intruder — soft nudge only
            if (
                score < self.INTRUDER_SCORE
                and now - self._weak_nudge_at > self.WEAK_NUDGE_COOLDOWN_SEC
            ):
                self._weak_nudge_at = now
                self._greeted_at = now
                return SecurityEvent(
                    "nudge",
                    f"Biometrics unsure, {self.user_name}. "
                    "Face the camera and say enroll my face.",
                    snapshot_path,
                )
            # Ambiguous desk lighting — stay quiet (was false intruder spam)
            return None

        # Step away
        if not present and self._last_present:
            self._last_present = False
            self._mismatch_streak = 0
            if self.lock_on_leave and not self._away_logged:
                self._away_logged = True
                return SecurityEvent(
                    "lock",
                    "You stepped away — securing the desk.",
                    snapshot_path,
                )
            return None

        # Mid-session check — only clear mismatches, streaked + cooled down
        if (
            present
            and self.intruder_alert
            and self.enroll_path.exists()
            and snapshot_path
            and motion > 0.22
            and now - self._greeted_at > 120
        ):
            score = self.match_score(snapshot_path)
            ev = self._maybe_intruder(now, snapshot_path, score)
            if ev:
                return ev

        self._last_present = present
        return None

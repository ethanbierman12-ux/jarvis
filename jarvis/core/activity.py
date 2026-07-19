"""Describe what the user appears to be doing from a camera frame."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from jarvis.config import DATA_DIR


class ActivityObserver:
    """Lightweight scene observer — OpenCV cues + optional Ollama vision."""

    def __init__(self) -> None:
        self._prev_gray: np.ndarray | None = None
        self.last_summary = "I have not looked yet."
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def describe(self, frame: np.ndarray | None) -> str:
        if frame is None:
            path = DATA_DIR / "last_vision.jpg"
            if path.exists():
                try:
                    import cv2

                    frame = cv2.imread(str(path))
                except Exception:
                    frame = None
        if frame is None:
            return "I cannot see you right now — the camera is busy or offline."

        # Prefer a real vision model if Ollama is running locally
        smart = self._ollama_describe(frame)
        if smart:
            self.last_summary = smart
            return smart

        cues = self._opencv_cues(frame)
        line = self._cues_to_english(cues)
        self.last_summary = line
        return line

    def identify_item(self, frame: np.ndarray | None, ocr_text: str = "") -> str:
        """Identify an object held up for scan — spoken answer, not a browser tab."""
        if frame is None:
            return ""

        smart = self._ollama_identify(frame, ocr_text)
        if smart:
            return smart

        # Heuristic fallback when no local vision model is running
        cues = self._opencv_cues(frame)
        color = self._dominant_color_name(frame)
        bits: list[str] = []
        if ocr_text:
            bits.append(f"I can read '{ocr_text[:80]}' on it")
        if color:
            bits.append(f"it looks mostly {color}")
        edges = float(cues.get("edge_density") or 0)
        bright = float(cues.get("bright_ratio") or 0)
        if bright > 0.12:
            bits.append("it may be a screen or glossy packaging")
        elif edges > 0.1:
            bits.append("it has a clear shape — likely a packaged product or small device")
        else:
            bits.append("I see an object in the viewfinder")
        if not bits:
            return "I captured the item, but I need a local vision model to name it."
        return ". ".join(bits).capitalize() + "."

    def note_frame(self, frame: np.ndarray) -> None:
        """Update rolling awareness without speaking (called from vision)."""
        try:
            cues = self._opencv_cues(frame)
            self.last_summary = self._cues_to_english(cues)
        except Exception:
            pass

    def _opencv_cues(self, frame: np.ndarray) -> dict[str, Any]:
        import cv2

        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(gray, 1.15, 4, minSize=(40, 40))
        face = None
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
            face = {
                "x": (x + fw / 2) / w,
                "y": (y + fh / 2) / h,
                "size": (fw * fh) / (w * h),
                "w": fw / w,
                "h": fh / h,
            }

        motion = 0.0
        if self._prev_gray is not None:
            small = cv2.resize(gray, (160, 90))
            prev = cv2.resize(self._prev_gray, (160, 90))
            diff = cv2.absdiff(small, prev)
            motion = float(np.mean(diff)) / 255.0
        self._prev_gray = gray

        # Skin / hand-ish blobs in lower-center (holding something toward cam)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        skin = cv2.inRange(hsv, (0, 30, 60), (25, 180, 255))
        skin |= cv2.inRange(hsv, (160, 30, 60), (180, 180, 255))
        cy0, cy1 = int(h * 0.35), int(h * 0.95)
        cx0, cx1 = int(w * 0.2), int(w * 0.8)
        roi = skin[cy0:cy1, cx0:cx1]
        skin_ratio = float(np.count_nonzero(roi)) / max(1, roi.size)

        # Bright rectangular glow (phone / tablet screen facing camera)
        bright = cv2.inRange(hsv, (0, 0, 200), (180, 60, 255))
        bright_roi = bright[int(h * 0.2) : int(h * 0.85), int(w * 0.15) : int(w * 0.85)]
        bright_ratio = float(np.count_nonzero(bright_roi)) / max(1, bright_roi.size)

        mean_lum = float(np.mean(gray)) / 255.0

        # Object-ish contours in center (item held up)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 140)
        center = edges[int(h * 0.25) : int(h * 0.75), int(w * 0.25) : int(w * 0.75)]
        edge_density = float(np.count_nonzero(center)) / max(1, center.size)

        return {
            "face": face,
            "faces": len(faces),
            "motion": motion,
            "skin_ratio": skin_ratio,
            "bright_ratio": bright_ratio,
            "mean_lum": mean_lum,
            "edge_density": edge_density,
        }

    def _cues_to_english(self, c: dict[str, Any]) -> str:
        face = c.get("face")
        motion = float(c.get("motion") or 0)
        skin = float(c.get("skin_ratio") or 0)
        bright = float(c.get("bright_ratio") or 0)
        edges = float(c.get("edge_density") or 0)
        lum = float(c.get("mean_lum") or 0)

        # Nearly blank / covered lens
        if edges < 0.01 and lum < 0.08:
            return "The camera looks dark or covered — I cannot see what you are doing."
        if edges < 0.01 and lum > 0.85:
            return "The camera looks washed out or pointed at a bright light."

        if face and bright > 0.12:
            return "It looks like you are looking at a phone or screen while facing the camera."
        if face and skin > 0.18 and edges > 0.08:
            return "It looks like you are holding something up to show me."
        if face and motion > 0.08:
            return "You look like you are moving around in front of the desk — I can see your face."
        if face and motion < 0.03:
            return "You look like you are sitting still at the computer, facing me."
        if face:
            return "I can see you in front of the camera."
        if not face and skin > 0.15:
            return "I mostly see hands or an object — maybe you are showing me something."
        if motion > 0.08:
            return "There is movement in front of the camera, but I cannot lock onto your face clearly."
        if edges > 0.08:
            return "I can see the room and some objects, but not a clear face right now."
        return "I am watching through the camera. Ask again if you move into view."

    def _ollama_describe(self, frame: np.ndarray) -> str | None:
        """If Ollama is running with a vision model, ask it what the user is doing."""
        return self._ollama_vision(
            frame,
            (
                "In one short sentence, what is the person in this webcam photo doing right now? "
                "Be specific and casual. Do not mention that it is a photo."
            ),
            num_predict=60,
        )

    def _ollama_identify(self, frame: np.ndarray, ocr_text: str = "") -> str | None:
        hint = f" Visible text on the item: {ocr_text[:100]}." if ocr_text else ""
        return self._ollama_vision(
            frame,
            (
                "You are identifying a product or object held up to a webcam. "
                "In 1-2 short sentences: name what it is, brand if visible, and what it is used for. "
                "Be concrete. Do not say you are an AI or that this is a photo."
                + hint
            ),
            num_predict=90,
            timeout=25,
        )

    def _ollama_vision(
        self,
        frame: np.ndarray,
        prompt: str,
        *,
        num_predict: int = 60,
        timeout: float = 12,
    ) -> str | None:
        try:
            import base64
            import cv2

            small = frame
            h, w = frame.shape[:2]
            if max(h, w) > 768:
                scale = 768 / max(h, w)
                small = cv2.resize(frame, None, fx=scale, fy=scale)
            ok, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return None
            b64 = base64.b64encode(buf.tobytes()).decode("ascii")

            models = self._ollama_vision_models()
            if not models:
                return None
            model = models[0]
            payload = {
                "model": model,
                "prompt": prompt,
                "images": [b64],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": num_predict},
            }
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = (data.get("response") or "").strip()
            if len(text) > 8:
                return " ".join(text.replace("\n", " ").split())[:280]
        except Exception:
            return None
        return None

    def _dominant_color_name(self, frame: np.ndarray) -> str:
        try:
            import cv2

            small = cv2.resize(frame, (64, 64))
            mean = small.reshape(-1, 3).mean(axis=0)  # BGR
            b, g, r = float(mean[0]), float(mean[1]), float(mean[2])
            if max(r, g, b) < 40:
                return "dark / black"
            if min(r, g, b) > 200:
                return "white or light"
            if r > g + 30 and r > b + 30:
                return "red or orange"
            if g > r + 20 and g > b + 20:
                return "green"
            if b > r + 20 and b > g + 20:
                return "blue"
            if r > 150 and g > 120 and b < 100:
                return "yellow or gold"
            if r > 100 and b > 100 and g < 90:
                return "purple or pink"
            if abs(r - g) < 25 and abs(g - b) < 25:
                return "gray"
            return "multicolored"
        except Exception:
            return ""

    def _ollama_vision_models(self) -> list[str]:
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names = [m.get("name", "") for m in data.get("models", [])]
            visionish = [
                n
                for n in names
                if any(
                    k in n.lower()
                    for k in ("llava", "moondream", "bakllava", "minicpm-v", "vision", "gemma3")
                )
            ]
            return visionish or []
        except Exception:
            return []


def grab_camera_frame(camera_index: int = 1, prefer: str = "EMEET") -> np.ndarray | None:
    """One-shot capture for activity questions when preview is closed."""
    try:
        import cv2
    except Exception:
        return None

    # Prefer last vision snapshot (no camera fight)
    path = DATA_DIR / "last_vision.jpg"
    if path.exists():
        try:
            age_ok = True
            import time

            age_ok = (time.time() - path.stat().st_mtime) < 8.0
            if age_ok:
                img = cv2.imread(str(path))
                if img is not None:
                    return img
        except Exception:
            pass

    for idx in (camera_index, 1, 0, 2):
        if idx < 0:
            continue
        from jarvis.core.camera_io import open_by_index, silence_opencv_logs

        with silence_opencv_logs():
            got = open_by_index(int(idx), reads=3)
        if not got:
            continue
        cap, _backend = got
        frame = None
        for _ in range(4):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        cap.release()
        if frame is not None:
            return frame
    return None

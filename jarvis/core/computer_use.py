"""Light vision computer-use — screenshot → find text → click like a human."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from jarvis.core.screen_context import ScreenContext


@dataclass
class ClickHit:
    x: int
    y: int
    label: str
    score: float


class ComputerUse:
    """
    Best-effort desktop navigation without a cloud computer-use API.
    Uses screenshot + OCR (pytesseract if installed) + pyautogui.
    """

    def __init__(self) -> None:
        self.screen = ScreenContext()

    def screenshot(self):
        try:
            import pyautogui
            import numpy as np

            shot = pyautogui.screenshot()
            return np.array(shot)[:, :, ::-1].copy()
        except Exception as e:
            print(f"[computer-use] screenshot failed: {e}")
            return None

    def see(self, *, ocr: bool = True) -> str:
        return self.screen.describe(ocr=ocr)

    def help_with(self, task: str = "") -> str:
        return self.screen.help_with(task)

    def find_text(self, needle: str, frame=None) -> Optional[ClickHit]:
        needle = (needle or "").strip().lower()
        if not needle:
            return None
        if frame is None:
            frame = self.screenshot()
        if frame is None:
            return None
        try:
            import cv2
            import pytesseract
            from pytesseract import Output
        except Exception:
            return self._fallback_center(needle)

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            data = pytesseract.image_to_data(rgb, output_type=Output.DICT)
        except Exception as e:
            print(f"[computer-use] OCR failed: {e}")
            return self._fallback_center(needle)

        best: Optional[ClickHit] = None
        n = len(data.get("text") or [])
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            conf = float(data.get("conf", [0])[i] or 0)
            if conf < 40:
                continue
            low = txt.lower()
            if needle in low or low in needle:
                x = int(data["left"][i] + data["width"][i] / 2)
                y = int(data["top"][i] + data["height"][i] / 2)
                score = conf + (20 if needle == low else 0)
                if best is None or score > best.score:
                    best = ClickHit(x=x, y=y, label=txt, score=score)
        return best

    def _fallback_center(self, needle: str) -> Optional[ClickHit]:
        try:
            import pyautogui

            w, h = pyautogui.size()
            return ClickHit(x=w // 2, y=h // 2, label=needle, score=1.0)
        except Exception:
            return None

    def click_text(self, label: str) -> str:
        hit = self.find_text(label)
        if hit is None:
            return f"I couldn't find “{label}” on screen. Is the window visible?"
        if hit.score <= 1.5:
            return (
                f"I couldn't confidently find “{label}” on screen. "
                "Bring that UI forward and try again, or install Tesseract OCR."
            )
        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.moveTo(hit.x, hit.y, duration=0.22)
            time.sleep(0.05)
            pyautogui.click()
            return f"Clicked “{hit.label}” on screen."
        except Exception as e:
            return f"Click failed: {e}"

    def type_text(self, text: str) -> str:
        try:
            import pyautogui

            pyautogui.typewrite(text, interval=0.02)
            return "Typed that for you."
        except Exception as e:
            return f"Typing failed: {e}"

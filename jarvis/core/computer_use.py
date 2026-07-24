"""Light vision computer-use — screenshot → find text → click like a human.

For the autonomous screenshot→LLM→action loop (Anthropic / OpenAI / browser-use),
see jarvis.core.computer_use_agent.ComputerUseAgent.
"""

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

    Autonomous multi-step agents live in computer_use_agent.py.
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

    def hotkey(self, *keys: str) -> str:
        keys = tuple(k.strip().lower() for k in keys if k and str(k).strip())
        if not keys:
            return "No hotkey specified."
        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.hotkey(*keys)
            return f"Pressed {'+'.join(keys)}."
        except Exception as e:
            return f"Hotkey failed: {e}"

    def scroll(self, clicks: int = -3) -> str:
        try:
            import pyautogui

            pyautogui.scroll(int(clicks))
            direction = "up" if clicks > 0 else "down"
            return f"Scrolled {direction}."
        except Exception as e:
            return f"Scroll failed: {e}"

    def move_click(self, x: int, y: int, *, clicks: int = 1) -> str:
        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.moveTo(int(x), int(y), duration=0.2)
            pyautogui.click(clicks=max(1, int(clicks)))
            return f"Clicked at {x},{y}."
        except Exception as e:
            return f"Click failed: {e}"

    def run_macro(self, steps: list[dict]) -> str:
        """
        Execute a list of action dicts, e.g.
        [{"click": "Export"}, {"hotkey": ["ctrl", "s"]}, {"scroll": -4}, {"type": "hello"}]
        """
        notes: list[str] = []
        for step in steps or []:
            if not isinstance(step, dict):
                continue
            if "click" in step:
                notes.append(self.click_text(str(step["click"])))
            elif "type" in step:
                notes.append(self.type_text(str(step["type"])))
            elif "hotkey" in step:
                keys = step["hotkey"]
                if isinstance(keys, str):
                    keys = keys.replace("-", "+").split("+")
                notes.append(self.hotkey(*[str(k) for k in keys]))
            elif "scroll" in step:
                notes.append(self.scroll(int(step["scroll"])))
            elif "wait" in step:
                time.sleep(float(step["wait"]))
                notes.append(f"Waited {step['wait']}s.")
            else:
                notes.append(f"Skipped unknown step: {step}")
            time.sleep(0.15)
        return " ".join(notes) if notes else "Macro was empty."

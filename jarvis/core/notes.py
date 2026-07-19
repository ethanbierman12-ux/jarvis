"""Voice-activated note-taking — spoken notes, screen OCR, audio memos."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from jarvis.config import DATA_DIR

NOTES_DIR = DATA_DIR / "notes"
NOTES_LOG = NOTES_DIR / "notes.md"
AUDIO_DIR = NOTES_DIR / "audio"


class NoteTaker:
    def __init__(self) -> None:
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        if not NOTES_LOG.exists():
            NOTES_LOG.write_text("# Jarvis Notes\n\n", encoding="utf-8")

    def take(self, spoken: str = "", *, from_screen: bool = False, audio: bool = False) -> str:
        """
        Log a note. Priority:
        1) spoken text after the command
        2) OCR of current screen (when 'about this' / from_screen)
        3) clipboard fallback
        Optionally also records a short audio memo.
        """
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        body = (spoken or "").strip()
        source = "voice"

        if from_screen or not body or body.lower() in ("this", "that", "it", "about this", "about that"):
            screen_text = self._screen_text()
            if screen_text:
                body = screen_text
                source = "screen"
            else:
                clip = self._clipboard()
                if clip:
                    body = clip
                    source = "clipboard"
                elif not body or body.lower() in ("this", "that", "it", "about this", "about that"):
                    body = "(no screen text or clipboard — empty note)"
                    source = "empty"

        entry = f"## {stamp} [{source}]\n{body}\n\n"
        with NOTES_LOG.open("a", encoding="utf-8") as f:
            f.write(entry)

        bits = [f"Saved note from {source} to {NOTES_LOG.name}."]
        if audio or from_screen:
            path = self._record_audio_async()
            if path:
                bits.append("Recording a short audio memo in the background.")

        preview = body.replace("\n", " ")[:120]
        bits.append(f"Preview: {preview}")
        return " ".join(bits)

    def list_recent(self, n: int = 5) -> str:
        try:
            text = NOTES_LOG.read_text(encoding="utf-8")
        except Exception:
            return "No notes file yet."
        blocks = [b.strip() for b in text.split("## ") if b.strip() and not b.startswith("# Jarvis")]
        if not blocks:
            return "Your notes log is empty."
        recent = blocks[-n:]
        lines = []
        for b in recent:
            first = b.splitlines()[0][:80]
            lines.append(first)
        return "Recent notes: " + " | ".join(lines)

    def open_log(self) -> str:
        try:
            import os

            os.startfile(str(NOTES_LOG))  # type: ignore[attr-defined]
            return f"Opened {NOTES_LOG}."
        except Exception as e:
            return f"Could not open notes: {e}"

    def _clipboard(self) -> str:
        try:
            import pyperclip

            return (pyperclip.paste() or "").strip()
        except Exception:
            return ""

    def _screen_text(self) -> str:
        try:
            import pyautogui
            import pytesseract
            from pathlib import Path as P

            for tip in (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ):
                if P(tip).exists():
                    pytesseract.pytesseract.tesseract_cmd = tip
                    break

            img = pyautogui.screenshot()
            text = pytesseract.image_to_string(img) or ""
            text = " ".join(text.split())
            return text[:2000] if len(text) >= 8 else ""
        except Exception:
            return ""

    def _record_audio_async(self, seconds: float = 6.0) -> Path | None:
        path = AUDIO_DIR / f"memo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

        def _rec() -> None:
            try:
                import sounddevice as sd
                import soundfile as sf

                sr = 16000
                frames = int(seconds * sr)
                audio = sd.rec(frames, samplerate=sr, channels=1, dtype="float32")
                sd.wait()
                sf.write(str(path), audio, sr)
                with NOTES_LOG.open("a", encoding="utf-8") as f:
                    f.write(f"- audio memo: {path.name}\n\n")
            except Exception as e:
                print(f"[notes] audio memo failed: {e}")

        threading.Thread(target=_rec, daemon=True, name="jarvis-note-audio").start()
        return path

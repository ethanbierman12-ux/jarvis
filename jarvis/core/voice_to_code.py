"""Voice-to-code — dictation buffer typed into the focused editor."""

from __future__ import annotations

import re
import time


class VoiceToCode:
    def __init__(self) -> None:
        self.active = False
        self._buf: list[str] = []
        self._started = 0.0

    def start(self, lang: str = "javascript") -> str:
        self.active = True
        self._buf = []
        self._started = time.time()
        return (
            f"Voice-to-code armed for {lang}. Speak your thoughts — "
            "say 'commit code' to type it, or 'cancel code' to abort."
        )

    def cancel(self) -> str:
        self.active = False
        self._buf = []
        return "Voice-to-code cancelled."

    def ingest(self, text: str) -> str | None:
        """Return a spoken ack, or None if not handling."""
        if not self.active:
            return None
        t = (text or "").strip()
        if re.search(r"\b(cancel code|stop dictation|abort code)\b", t, re.I):
            return self.cancel()
        if re.search(r"\b(commit code|type (it|that)|insert code|flush code)\b", t, re.I):
            return self.flush()
        if re.search(r"\b(done coding|end code)\b", t, re.I):
            return self.flush()
        # strip wake leftovers
        t = re.sub(r"^(hey )?jarvis[,:]?\s*", "", t, flags=re.I).strip()
        if t:
            self._buf.append(t)
            return "Noted."
        return "Listening for code."

    def flush(self) -> str:
        body = " ".join(self._buf).strip()
        self.active = False
        self._buf = []
        if not body:
            return "Nothing to type."
        # Light punctuation cleanup for code-ish dictation
        body = body.replace(" open brace ", " { ").replace(" close brace ", " } ")
        body = body.replace(" open paren ", " ( ").replace(" close paren ", " ) ")
        body = body.replace(" semicolon", ";")
        try:
            import pyautogui
            import pyperclip

            pyperclip.copy(body)
            pyautogui.hotkey("ctrl", "v")
            return f"Typed {len(body.split())} words into the focused editor."
        except Exception as e:
            return f"Could not type into editor: {e}. Buffer was: {body[:120]}"

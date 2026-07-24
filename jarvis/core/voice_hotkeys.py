"""Voice-activated hotkeys — map spoken Mac/Windows shortcuts to pyautogui."""

from __future__ import annotations

import re
from typing import Callable


# Spoken phrase → key combo (Windows-first; Ctrl mirrors Cmd)
_HOTKEYS: list[tuple[str, tuple[str, ...] | str, str]] = [
    (r"^(copy|hit copy|copy that|copy selection)$", ("ctrl", "c"), "Copied"),
    (r"^(paste|hit paste|paste that)$", ("ctrl", "v"), "Pasted"),
    (r"^(cut|hit cut|cut that)$", ("ctrl", "x"), "Cut"),
    (r"^(undo|hit undo|undo that)$", ("ctrl", "z"), "Undone"),
    (r"^(redo|hit redo|redo that)$", ("ctrl", "y"), "Redone"),
    (r"^(save|hit save|save (the )?(file|document))$", ("ctrl", "s"), "Saved"),
    (r"^(select all|hit select all)$", ("ctrl", "a"), "Selected all"),
    (r"^(new tab)$", ("ctrl", "t"), "New tab"),
    (r"^(close tab)$", ("ctrl", "w"), "Closed tab"),
    (r"^(reopen tab)$", ("ctrl", "shift", "t"), "Reopened tab"),
    (r"^(find|hit find|find in (page|file))$", ("ctrl", "f"), "Find opened"),
    (r"^(desktop|show desktop)$", ("win", "d"), "Desktop"),
    (r"^(task view|mission control)$", ("win", "tab"), "Task view"),
    (r"^(lock (the )?(screen|workstation) now)$", "lock", "Lock"),
    (r"^(screenshot region|snip(ping)? tool)$", ("win", "shift", "s"), "Snipping tool"),
]


class VoiceHotkeys:
    def __init__(self, lock_fn: Callable[[], str] | None = None) -> None:
        self._lock = lock_fn

    def try_run(self, text: str) -> str | None:
        t = (text or "").lower().strip(" .!?")
        if not t:
            return None
        for pattern, keys, label in _HOTKEYS:
            if not re.fullmatch(pattern, t, flags=re.I):
                continue
            if keys == "lock":
                if self._lock:
                    return self._lock()
                return "Lock requested."
            try:
                import pyautogui

                if isinstance(keys, tuple):
                    pyautogui.hotkey(*keys)
                else:
                    pyautogui.press(keys)
                return f"{label}."
            except Exception as e:
                return f"Hotkey failed: {e}"
        return None

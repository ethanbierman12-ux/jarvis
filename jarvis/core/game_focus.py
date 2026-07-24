"""Game focus, app prefetch, ghost mode helpers."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from jarvis.config import DATA_DIR, ROOT

PREFETCH_PATH = DATA_DIR / "prefetch.json"
HEAVY = (
    "unity.exe",
    "unrealeditor.exe",
    "premiere pro.exe",
    "adobe premiere pro.exe",
    "afterfx.exe",
    "blender.exe",
    "davinci resolve.exe",
    "steam.exe",
    "epicgameslauncher.exe",
    "valorant.exe",
    "league of legends.exe",
    "cs2.exe",
    "fortniteclient-win64-shipping.exe",
    "gta5.exe",
    "r5apex.exe",
)
# Editors (Cursor / VS Code / devenv) intentionally excluded — focusing them
# must NOT mute the mic or open Windows Focus Assist.


class GameFocusWatch:
    """When a game/heavy app is foreground, mute mic + quiet notifications."""

    def __init__(
        self,
        on_enter: Optional[Callable[[str], None]] = None,
        on_leave: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_enter = on_enter
        self.on_leave = on_leave
        self._running = False
        self._active = False
        self._name = ""

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="jarvis-gamefocus").start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            name = self._foreground_exe()
            # Only treat actual games / known heavy apps — never IDEs
            heavy = name in HEAVY or (
                name.endswith(".exe")
                and any(g in name for g in ("-win64-shipping", "gameoverlay"))
            )
            if heavy and not self._active:
                self._active = True
                self._name = name
                if self.on_enter:
                    self.on_enter(name)
            elif not heavy and self._active:
                self._active = False
                if self.on_leave:
                    self.on_leave()
            time.sleep(2.5)

    def _foreground_exe(self) -> str:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            import psutil

            p = psutil.Process(int(pid.value))
            return (p.name() or "").lower()
        except Exception:
            return ""


class Prefetcher:
    """Warm apps at habitual hours (e.g. IDE at 9am)."""

    def __init__(self, apps_launcher=None) -> None:
        self.apps = apps_launcher
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not PREFETCH_PATH.exists():
            PREFETCH_PATH.write_text(
                json.dumps(
                    {
                        "slots": [
                            {"hour": 9, "minute": 0, "apps": ["code", "chrome"]},
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        self._fired_day = ""
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="jarvis-prefetch").start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            try:
                now = datetime.now()
                day = now.strftime("%Y-%m-%d")
                raw = json.loads(PREFETCH_PATH.read_text(encoding="utf-8"))
                for slot in raw.get("slots") or []:
                    key = f"{day}-{slot.get('hour')}-{slot.get('minute')}"
                    if self._fired_day == key:
                        continue
                    if now.hour == int(slot.get("hour", -1)) and now.minute == int(
                        slot.get("minute", -1)
                    ):
                        self._fired_day = key
                        for app in slot.get("apps") or []:
                            try:
                                if self.apps:
                                    self.apps.open(app)
                            except Exception:
                                pass
                        print(f"[prefetch] warmed {slot.get('apps')}")
            except Exception:
                pass
            time.sleep(20)

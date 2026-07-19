"""Multi-monitor placement — put HUD, ops board, and opened apps on the right screen."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ScreenInfo:
    index: int
    name: str
    x: int
    y: int
    width: int
    height: int
    is_primary: bool

    @property
    def origin(self) -> tuple[int, int]:
        return (self.x, self.y)


class DisplayManager:
    """Resolve primary / secondary screens and move windows onto them."""

    def __init__(self) -> None:
        self._cache: list[ScreenInfo] = []

    def refresh(self) -> list[ScreenInfo]:
        screens: list[ScreenInfo] = []
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                primary = app.primaryScreen()
                for i, s in enumerate(app.screens()):
                    g = s.availableGeometry()
                    screens.append(
                        ScreenInfo(
                            index=i,
                            name=s.name() or f"Display {i}",
                            x=g.x(),
                            y=g.y(),
                            width=g.width(),
                            height=g.height(),
                            is_primary=(s is primary),
                        )
                    )
        except Exception:
            pass
        if not screens:
            screens = [
                ScreenInfo(0, "Primary", 0, 0, 1920, 1080, True),
            ]
        self._cache = screens
        return screens

    def screens(self) -> list[ScreenInfo]:
        return self._cache or self.refresh()

    def primary(self) -> ScreenInfo:
        for s in self.screens():
            if s.is_primary:
                return s
        return self.screens()[0]

    def secondary(self) -> Optional[ScreenInfo]:
        all_s = self.screens()
        others = [s for s in all_s if not s.is_primary]
        if others:
            # Prefer the largest non-primary
            return max(others, key=lambda s: s.width * s.height)
        if len(all_s) >= 2:
            return all_s[1]
        return None

    def resolve(self, prefer: str | int = "secondary") -> ScreenInfo:
        """
        prefer: 'primary' | 'secondary' | 'other' | int index
        """
        self.refresh()
        if isinstance(prefer, int):
            all_s = self.screens()
            return all_s[prefer % len(all_s)]
        key = str(prefer or "secondary").lower().strip()
        if key in ("primary", "main", "0"):
            return self.primary()
        if key in ("secondary", "other", "second", "1"):
            return self.secondary() or self.primary()
        try:
            return self.resolve(int(key))
        except Exception:
            return self.secondary() or self.primary()

    def describe(self) -> str:
        bits = []
        for s in self.refresh():
            tag = "PRIMARY" if s.is_primary else "OTHER"
            bits.append(f"{s.index}:{s.name} {s.width}x{s.height} @({s.x},{s.y}) [{tag}]")
        return "Displays: " + "; ".join(bits)

    def place_widget(self, widget, prefer: str | int = "secondary", *, maximize: bool = False) -> str:
        """Move a Qt window onto the chosen monitor."""
        screen = self.resolve(prefer)
        margin = 24
        if maximize:
            widget.show()
            try:
                # Frame geometry then expand into available area
                widget.setGeometry(
                    screen.x + 8,
                    screen.y + 8,
                    max(800, screen.width - 16),
                    max(600, screen.height - 16),
                )
                widget.showMaximized()
            except Exception:
                widget.setGeometry(screen.x, screen.y, screen.width, screen.height)
        else:
            w = min(max(widget.width(), 1100), screen.width - margin * 2)
            h = min(max(widget.height(), 720), screen.height - margin * 2)
            x = screen.x + (screen.width - w) // 2
            y = screen.y + (screen.height - h) // 2
            widget.setGeometry(x, y, w, h)
            widget.show()
        try:
            widget.raise_()
            widget.activateWindow()
        except Exception:
            pass
        tag = "primary" if screen.is_primary else "other"
        return f"Placed on {tag} monitor ({screen.width}x{screen.height})."

    def open_url_on(self, url: str, prefer: str | int = "secondary") -> str:
        """Open Chrome (or default browser) positioned on the target monitor."""
        screen = self.resolve(prefer)
        chrome = _chrome_path()
        x, y = screen.x + 40, screen.y + 40
        w, h = max(1000, screen.width - 80), max(700, screen.height - 100)
        if chrome:
            try:
                subprocess.Popen(
                    [
                        chrome,
                        f"--window-position={x},{y}",
                        f"--window-size={w},{h}",
                        "--new-window",
                        url,
                    ],
                    shell=False,
                )
                return f"Opened on other monitor: {url}"
            except Exception:
                pass
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass
        # Best-effort move after launch
        time.sleep(0.8)
        self.move_recent_windows_to(prefer, titles=("chrome", "edge", "firefox"))
        return f"Opened {url} (moving to target display)."

    def open_app_on(self, exe_or_path: str, prefer: str | int = "secondary", args: list[str] | None = None) -> str:
        screen = self.resolve(prefer)
        cmd = [exe_or_path, *(args or [])]
        try:
            subprocess.Popen(cmd, shell=False)
        except Exception as e:
            return f"Could not launch: {e}"
        time.sleep(1.0)
        self.move_recent_windows_to(
            prefer,
            titles=(Path_stem(exe_or_path), "chrome", "code", "cursor", "spotify"),
        )
        return f"Launched on monitor {screen.index} ({'primary' if screen.is_primary else 'other'})."

    def move_recent_windows_to(
        self,
        prefer: str | int = "secondary",
        *,
        titles: tuple[str, ...] = (),
    ) -> int:
        """Move matching top-level windows onto the target screen (Win32)."""
        screen = self.resolve(prefer)
        moved = 0
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            EnumWindows = user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
            )
            IsWindowVisible = user32.IsWindowVisible
            GetWindowTextW = user32.GetWindowTextW
            GetWindowTextLengthW = user32.GetWindowTextLengthW
            GetWindowRect = user32.GetWindowRect
            SetWindowPos = user32.SetWindowPos
            GetClassNameW = user32.GetClassNameW

            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_SHOWWINDOW = 0x0040

            targets = [t.lower() for t in titles if t]

            @EnumWindowsProc
            def _cb(hwnd, _lparam):
                nonlocal moved
                if not IsWindowVisible(hwnd):
                    return True
                length = GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").lower()
                cls = ctypes.create_unicode_buffer(256)
                GetClassNameW(hwnd, cls, 256)
                class_name = (cls.value or "").lower()
                blob = title + " " + class_name
                if targets and not any(t in blob for t in targets):
                    return True
                # Skip tiny / tool windows
                rect = wintypes.RECT()
                if not GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True
                w = abs(rect.right - rect.left)
                h = abs(rect.bottom - rect.top)
                if w < 200 or h < 120:
                    return True
                # Already mostly on target?
                if abs(rect.left - screen.x) < 80 and abs(rect.top - screen.y) < 80:
                    return True
                x = screen.x + 30
                y = screen.y + 30
                SetWindowPos(
                    hwnd,
                    0,
                    x,
                    y,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW,
                )
                # Then try maximize on that monitor via ShowWindow
                try:
                    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                except Exception:
                    pass
                moved += 1
                return True

            EnumWindows(_cb, 0)
        except Exception:
            pass
        return moved


def Path_stem(path: str) -> str:
    try:
        from pathlib import Path

        return Path(path).stem.lower()
    except Exception:
        return path.lower()


def _chrome_path() -> str | None:
    from pathlib import Path
    import os

    for p in (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / r"Google\Chrome\Application\chrome.exe",
    ):
        if p.exists():
            return str(p)
    return None


# Singleton for brain / apps
displays = DisplayManager()

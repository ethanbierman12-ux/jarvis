"""Theme sync, performance boost, panic hide, emotion, Chrome history."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class ThemeSync:
    """Optional Windows light/dark sync. Off by default — was flipping the taskbar white at boot."""

    def __init__(self, *, windows_enabled: bool = False) -> None:
        self.windows_enabled = bool(windows_enabled)

    def apply_for_hour(self, hour: Optional[int] = None, ambient_bright: float | None = None) -> str:
        if not self.windows_enabled:
            return "Windows theme sync is off — Jarvis will not change your taskbar or system colors."
        hour = datetime.now().hour if hour is None else hour
        # ambient_bright 0..1 from webcam mean luminance if provided
        if ambient_bright is not None:
            dark = ambient_bright < 0.28
        else:
            dark = hour >= 19 or hour < 7
        return self.set_dark(dark)

    def set_dark(self, dark: bool) -> str:
        if not self.windows_enabled:
            return (
                "Windows theme sync is off. Say enable windows theme sync if you want "
                "Jarvis to change system light/dark mode."
            )
        # Windows AppsUseLightTheme: 0 = dark, 1 = light
        val = 0 if dark else 1
        try:
            subprocess.run(
                [
                    "reg",
                    "add",
                    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "/v",
                    "AppsUseLightTheme",
                    "/t",
                    "REG_DWORD",
                    "/d",
                    str(val),
                    "/f",
                ],
                capture_output=True,
                timeout=5,
            )
            subprocess.run(
                [
                    "reg",
                    "add",
                    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "/v",
                    "SystemUsesLightTheme",
                    "/t",
                    "REG_DWORD",
                    "/d",
                    str(val),
                    "/f",
                ],
                capture_output=True,
                timeout=5,
            )
            return "Dark mode on." if dark else "Light mode on."
        except Exception as e:
            return f"Theme switch failed: {e}"

    def restore_dark_taskbar(self) -> str:
        """One-shot repair if a prior build forced light system theme."""
        # Temporarily allow write
        prev = self.windows_enabled
        self.windows_enabled = True
        try:
            return self.set_dark(True)
        finally:
            self.windows_enabled = prev


class PerformanceBoost:
    SKIP = {
        "explorer.exe",
        "python.exe",
        "pythonw.exe",
        "code.exe",
        "cursor.exe",
        "chrome.exe",
        "dwm.exe",
        "csrss.exe",
        "winlogon.exe",
        "services.exe",
        "lsass.exe",
        "system",
        "registry",
        "jarvis",
    }

    def boost(self) -> str:
        try:
            import psutil
        except Exception as e:
            return f"Boost unavailable: {e}"
        suspended = 0
        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = (p.info.get("name") or "").lower()
                if not name or name in self.SKIP:
                    continue
                # Light touch: only known background gobblers
                if name in (
                    "onedrive.exe",
                    "teams.exe",
                    "ms-teams.exe",
                    "searchindexer.exe",
                    "yourphoneserver.exe",
                    "adobe_licensing_helper.exe",
                    "ccxprocess.exe",
                    "steam.exe",
                    "epicgameslauncher.exe",
                ):
                    p.suspend()
                    suspended += 1
            except Exception:
                continue
        return f"Boost mode — suspended {suspended} background processes."

    def restore(self) -> str:
        try:
            import psutil
        except Exception as e:
            return f"Restore unavailable: {e}"
        n = 0
        for p in psutil.process_iter(["name"]):
            try:
                name = (p.info.get("name") or "").lower()
                if name in (
                    "onedrive.exe",
                    "teams.exe",
                    "ms-teams.exe",
                    "steam.exe",
                    "epicgameslauncher.exe",
                ):
                    p.resume()
                    n += 1
            except Exception:
                continue
        return f"Restored {n} processes."


class PanicSwitch:
    def trigger(self) -> str:
        bits = []
        # Mute mic + media
        try:
            import ctypes

            VK_MUTE = 0xAD
            ctypes.windll.user32.keybd_event(VK_MUTE, 0, 1, 0)
            ctypes.windll.user32.keybd_event(VK_MUTE, 0, 1 | 2, 0)
            bits.append("muted")
        except Exception:
            pass
        # Minimize all windows (Win+M)
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.keybd_event(0x5B, 0, 0, 0)  # LWIN
            user32.keybd_event(ord("M"), 0, 0, 0)
            user32.keybd_event(ord("M"), 0, 2, 0)
            user32.keybd_event(0x5B, 0, 2, 0)
            bits.append("desktop cleared")
        except Exception:
            pass
        return "Panic — " + (", ".join(bits) if bits else "triggered") + "."


class EmotionMirror:
    STRESS = re.compile(
        r"\b(frustrated|annoying|hate|stupid|broken|why won'?t|damn|argh|ugh|stressed|anxious)\b",
        re.I,
    )
    POSITIVE = re.compile(r"\b(thanks|great|awesome|love|perfect|nice|yes)\b", re.I)

    def analyze(self, text: str) -> str:
        t = text or ""
        if self.STRESS.search(t):
            return "stressed"
        if self.POSITIVE.search(t):
            return "positive"
        return "neutral"

    def support_line(self, name: str = "Sir") -> str:
        return (
            f"I hear you, {name}. Take a slow breath with me — "
            "in for four, out for six. Want calm audio or a short break?"
        )


class ChromeHistory:
    def recent(self, hours: int = 24, limit: int = 8) -> str:
        # Prefer live open tabs when available
        try:
            from jarvis.core.screen_context import ScreenContext

            sc = ScreenContext()
            tabs = sc.chrome_open_tabs() or []
            wins = sc.browser_window_titles()
            if tabs:
                names = [t.get("title") or t.get("url") or "" for t in tabs[:limit]]
                names = [n for n in names if n]
                if names:
                    return "Open tabs right now: " + "; ".join(names)
            if wins:
                return "Browser windows: " + "; ".join(wins[:limit])
        except Exception:
            pass

        roots = [
            Path(os.environ.get("LOCALAPPDATA", ""))
            / r"Google\Chrome\User Data\Default\History",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / r"Microsoft\Edge\User Data\Default\History",
        ]
        db = next((p for p in roots if p.exists()), None)
        if not db:
            return "No Chrome/Edge history database found."
        try:
            # Chrome locks the DB — copy it
            tmp = Path(tempfile.gettempdir()) / "jarvis_chrome_history"
            tmp.write_bytes(db.read_bytes())
            con = sqlite3.connect(str(tmp))
            cur = con.cursor()
            # Chrome time: microseconds since 1601
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            # Convert approx
            epoch = int((cutoff.timestamp() + 11644473600) * 1_000_000)
            cur.execute(
                "SELECT title, url, last_visit_time FROM urls "
                "WHERE last_visit_time > ? ORDER BY last_visit_time DESC LIMIT ?",
                (epoch, limit),
            )
            rows = cur.fetchall()
            con.close()
            if not rows:
                return "No recent browser visits in that window."
            lines = []
            for title, url, _ in rows:
                title = (title or url or "")[:60]
                lines.append(title)
            return "You were looking at: " + "; ".join(lines)
        except Exception as e:
            return f"Could not read browser history (is Chrome open?): {e}"

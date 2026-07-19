"""Screen + browser awareness — so Jarvis can help with what you're actually doing.

Combines:
  - Active window title
  - Visible Chrome/Edge window titles (active tabs per window)
  - Optional Chrome DevTools open-tab list (if debugging port is on)
  - Recent browser history
  - Screenshot OCR digest
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import threading
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class ScreenSnapshot:
    active_window: str = ""
    browser_windows: list[str] = field(default_factory=list)
    open_tabs: list[dict[str, str]] = field(default_factory=list)
    recent_history: list[str] = field(default_factory=list)
    ocr_text: str = ""
    summary: str = ""
    help: str = ""


class ScreenContext:
    """Read the user's desktop context without requiring cloud APIs."""

    CDP_PORTS = (9222, 9229, 9333)

    def snapshot(self, *, ocr: bool = True, history_limit: int = 8) -> ScreenSnapshot:
        snap = ScreenSnapshot()
        snap.active_window = self.active_window_title()
        snap.browser_windows = self.browser_window_titles()
        snap.open_tabs = self.chrome_open_tabs()
        snap.recent_history = self.recent_history_titles(limit=history_limit)
        if ocr:
            # Prefer focused window text — more relevant for "look at this"
            snap.ocr_text = self.ocr_active_window(max_chars=1200) or self.ocr_screen(
                max_chars=1200
            )
        snap.summary = self._summarize(snap)
        snap.help = self._help_line(snap)
        return snap

    def describe(self, *, ocr: bool = True) -> str:
        s = self.snapshot(ocr=ocr)
        parts = [s.summary]
        if s.help:
            parts.append(s.help)
        return " ".join(p for p in parts if p).strip()

    def help_with(self, task: str = "") -> str:
        """Task-oriented answer grounded in current screen/tabs."""
        s = self.snapshot(ocr=True)
        task = (task or "").strip()
        base = s.summary
        tips = s.help
        if not task:
            return f"{base} {tips}".strip()

        low = task.lower()
        ocr_l = (s.ocr_text or "").lower()
        tabs = " | ".join(
            (t.get("title") or t.get("url") or "") for t in s.open_tabs[:6]
        ).lower()
        win = " | ".join(s.browser_windows[:6]).lower()
        blob = f"{ocr_l} {tabs} {win} {s.active_window.lower()}"

        # Lightweight grounded tips
        if any(k in low for k in ("code", "bug", "error", "fix", "debug")):
            if "error" in blob or "exception" in blob or "traceback" in blob:
                return (
                    f"{base} I can see error text on screen. "
                    "Paste the traceback here or say 'scan' with the panel focused — "
                    "I'll help fix it step by step."
                )
            return (
                f"{base} Open the failing file or terminal so I can read it, "
                "then say 'look at my screen' again."
            )
        if any(k in low for k in ("email", "mail", "reply", "inbox")):
            if "mail" in blob or "outlook" in blob or "gmail" in blob:
                return (
                    f"{base} You're in mail. Tell me to draft a reply, or say "
                    "'away mode' if you want me to handle inbox while you're out."
                )
        if any(k in low for k in ("write", "essay", "doc", "document")):
            return (
                f"{base} I can see your document context. Tell me the goal "
                "(tone, length, audience) and I'll draft the next section."
            )
        if any(k in low for k in ("shop", "buy", "price", "amazon")):
            return (
                f"{base} I can see shopping/browser context. Say what you're comparing "
                "and constraints (budget, specs) — I'll help decide."
            )
        return (
            f"{base} For “{task[:80]}”: {tips} "
            "Or describe the exact step you're stuck on."
        )

    # ── collectors ──────────────────────────────────────────────
    def active_window_title(self) -> str:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return (buf.value or "").strip()
        except Exception:
            return ""

    def browser_window_titles(self) -> list[str]:
        titles: list[str] = []
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            EnumWindows = user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
            )
            IsWindowVisible = user32.IsWindowVisible
            GetWindowTextLengthW = user32.GetWindowTextLengthW
            GetWindowTextW = user32.GetWindowTextW

            markers = (
                "google chrome",
                "microsoft edge",
                "brave",
                "firefox",
                "opera",
                "arc",
            )

            def _cb(hwnd, _lp):
                if not IsWindowVisible(hwnd):
                    return True
                n = GetWindowTextLengthW(hwnd)
                if n < 3:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                GetWindowTextW(hwnd, buf, n + 1)
                title = (buf.value or "").strip()
                low = title.lower()
                if any(m in low for m in markers):
                    # Strip browser suffix for cleaner tab name
                    clean = re.sub(
                        r"\s*[-—|]\s*(Google Chrome|Microsoft Edge|Brave|Firefox|Opera|Arc)\s*$",
                        "",
                        title,
                        flags=re.I,
                    ).strip()
                    if clean and clean not in titles:
                        titles.append(clean[:120])
                return True

            EnumWindows(EnumWindowsProc(_cb), 0)
        except Exception:
            pass
        return titles[:12]

    def chrome_open_tabs(self) -> list[dict[str, str]]:
        """Best-effort live tabs via Chrome DevTools HTTP if enabled."""
        tabs: list[dict[str, str]] = []
        for port in self.CDP_PORTS:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json", timeout=0.35
                ) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if not isinstance(data, list):
                    continue
                for item in data:
                    if (item.get("type") or "") != "page":
                        continue
                    url = str(item.get("url") or "")
                    if url.startswith(("chrome://", "edge://", "devtools://", "about:")):
                        continue
                    tabs.append(
                        {
                            "title": str(item.get("title") or "")[:100],
                            "url": url[:200],
                        }
                    )
                if tabs:
                    return tabs[:20]
            except Exception:
                continue
        return tabs

    def recent_history_titles(self, limit: int = 8, hours: int = 12) -> list[str]:
        roots = [
            Path(os.environ.get("LOCALAPPDATA", ""))
            / r"Google\Chrome\User Data\Default\History",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / r"Microsoft\Edge\User Data\Default\History",
        ]
        db = next((p for p in roots if p.exists()), None)
        if not db:
            return []
        try:
            tmp = Path(tempfile.gettempdir()) / "jarvis_chrome_hist_snap"
            tmp.write_bytes(db.read_bytes())
            con = sqlite3.connect(str(tmp))
            cur = con.cursor()
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            epoch = int((cutoff.timestamp() + 11644473600) * 1_000_000)
            cur.execute(
                "SELECT title, url FROM urls WHERE last_visit_time > ? "
                "ORDER BY last_visit_time DESC LIMIT ?",
                (epoch, limit),
            )
            rows = cur.fetchall()
            con.close()
            out = []
            for title, url in rows:
                label = (title or url or "").strip()
                if label:
                    out.append(label[:80])
            return out
        except Exception:
            return []

    def ocr_screen(self, max_chars: int = 1200) -> str:
        """OCR with a hard timeout so the HUD never freezes forever."""
        result: list[str] = [""]
        done = threading.Event()

        def _run() -> None:
            try:
                result[0] = self._ocr_screen_inner(max_chars=max_chars)
            except Exception:
                result[0] = ""
            finally:
                done.set()

        threading.Thread(target=_run, daemon=True, name="ocr-screen").start()
        done.wait(timeout=2.8)
        return result[0]

    def _ocr_screen_inner(self, max_chars: int = 1200) -> str:
        try:
            import pyautogui
            import numpy as np
            import cv2
        except Exception:
            return ""

        try:
            shot = pyautogui.screenshot()
            frame = np.array(shot)[:, :, ::-1].copy()
            h, w = frame.shape[:2]
            scale = min(1.0, 1280 / max(w, 1))
            if scale < 0.99:
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        except Exception:
            return ""

        try:
            import pytesseract
            from pytesseract import Output

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            data = pytesseract.image_to_data(rgb, output_type=Output.DICT)
            words = []
            for i, txt in enumerate(data.get("text") or []):
                t = (txt or "").strip()
                if not t:
                    continue
                try:
                    conf = float(data.get("conf", [0])[i] or 0)
                except Exception:
                    conf = 0
                if conf >= 45:
                    words.append(t)
            text = " ".join(words)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:max_chars]
        except Exception:
            return ""

    def ocr_active_window(self, max_chars: int = 1500) -> str:
        """OCR only the focused window (faster, more relevant)."""
        try:
            import pygetwindow as gw
            import pyautogui
            import pytesseract
        except Exception:
            return self.ocr_screen(max_chars=max_chars)

        try:
            win = gw.getActiveWindow()
            if not win or win.width < 80 or win.height < 80:
                return self.ocr_screen(max_chars=max_chars)
            left, top = max(0, int(win.left)), max(0, int(win.top))
            w, h = int(win.width), int(win.height)
            shot = pyautogui.screenshot(region=(left, top, w, h))
            # Prefer configured tesseract path on Windows
            try:
                pytesseract.pytesseract.tesseract_cmd = (
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                )
            except Exception:
                pass
            text = pytesseract.image_to_string(shot) or ""
            text = re.sub(r"\s+", " ", text).strip()
            return text[:max_chars]
        except Exception:
            return self.ocr_screen(max_chars=max_chars)

    def capture_png(self, path: Path | None = None) -> Path | None:
        try:
            import pyautogui

            folder = Path.home() / "Pictures" / "Jarvis"
            folder.mkdir(parents=True, exist_ok=True)
            path = path or folder / f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            pyautogui.screenshot(str(path))
            return path
        except Exception:
            return None

    # ── language ────────────────────────────────────────────────
    def _summarize(self, s: ScreenSnapshot) -> str:
        bits: list[str] = []
        if s.active_window:
            bits.append(f"You're focused on “{s.active_window[:90]}”.")
        if s.open_tabs:
            names = [t.get("title") or t.get("url", "") for t in s.open_tabs[:5]]
            names = [n for n in names if n]
            if names:
                bits.append("Open tabs: " + "; ".join(names) + ".")
        elif s.browser_windows:
            bits.append(
                "Browser windows: " + "; ".join(s.browser_windows[:4]) + "."
            )
        if s.recent_history and not s.open_tabs:
            bits.append(
                "Recently visited: " + "; ".join(s.recent_history[:4]) + "."
            )
        if s.ocr_text:
            snippet = s.ocr_text[:220].strip()
            if snippet:
                bits.append(f"On-screen text includes: “{snippet}…”.")
        if not bits:
            return (
                "I can see your desktop, but need a moment — "
                "bring the window you care about to the front and ask again."
            )
        return " ".join(bits)

    def _help_line(self, s: ScreenSnapshot) -> str:
        blob = " ".join(
            [
                s.active_window,
                " ".join(s.browser_windows),
                " ".join(t.get("title", "") for t in s.open_tabs),
                s.ocr_text[:400],
            ]
        ).lower()
        if any(k in blob for k in ("stackoverflow", "error", "exception", "traceback", "failed")):
            return "Looks like a debugging moment — say 'help me fix this' and I'll guide you."
        if any(k in blob for k in ("gmail", "outlook", "inbox", "mail")):
            return "Mail is open — I can draft a reply or start away mode."
        if any(k in blob for k in ("github", "pull request", "vscode", "cursor", "code")):
            return "You're in a coding context — ask me to build, review, or vibe-code the next piece."
        if any(k in blob for k in ("docs.google", "notion", "word", "document")):
            return "Document open — tell me what to write or improve."
        if any(k in blob for k in ("youtube", "spotify", "netflix")):
            return "Media is up — say play/pause, or ask for focus music."
        return "Say 'help me with this' and tell me the goal — I'll use what I can see."

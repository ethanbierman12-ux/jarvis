"""Snapchat / Phone Link incoming-call watcher — notify + best-effort auto-answer.

Snapchat has no public call API. On Windows we detect:
  1) Phone Link / Your Phone / Snapchat window titles (incoming call UI)
  2) Optional ntfy push from an iOS Shortcut when Snap rings on the phone
Then Jarvis announces, pushes ntfy to you, and can try to click Answer.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable


# Processes that may surface Snap / phone call UI on PC
_PROC_HINTS = (
    "snapchat",
    "phoneexperiencehost",
    "yourphone",
    "phonelink",
    "microsoft.yourphone",
    "link to windows",
)

# Window title / class blobs that suggest an incoming call
_CALL_HINTS = (
    "incoming",
    "is calling",
    "calling you",
    "video chat",
    "video call",
    "audio call",
    "snapchat call",
    "incoming call",
    "wants to call",
    "started a call",
)

_SNAP_HINTS = (
    "snapchat",
    "phone link",
    "your phone",
    "link to windows",
    "calling",
)

_ANSWER_LABELS = (
    "answer",
    "accept",
    "pick up",
    "join",
)


@dataclass
class SnapCallEvent:
    caller: str
    source: str  # window | ntfy | test
    title: str = ""
    hwnd: int = 0


class SnapchatCallBridge:
    """
    Poll Windows for Snapchat / Phone Link incoming calls + optional ntfy hook.

    IFTTT / iOS Shortcuts can POST to the ntfy topic with body:
      snap call
      snap call from Alex
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        auto_answer: bool = True,
        poll_sec: float = 1.25,
        cooldown_sec: float = 25.0,
        ntfy_topic: str = "",
        ntfy_server: str = "https://ntfy.sh",
        on_call: Callable[[SnapCallEvent], None] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.auto_answer = bool(auto_answer)
        self.poll_sec = max(0.4, float(poll_sec or 0.55))
        self.cooldown_sec = max(5.0, float(cooldown_sec or 25.0))
        self.server = (ntfy_server or "https://ntfy.sh").rstrip("/")
        self.topic = (ntfy_topic or "").strip()
        self.on_call = on_call
        self._stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._ntfy_thread: threading.Thread | None = None
        self._until = 0.0
        self._last_fingerprint = ""
        self._answered_fp = ""

    @staticmethod
    def make_topic() -> str:
        return f"jarvis-snap-{secrets.token_hex(4)}"

    def status(self) -> str:
        if not self.enabled:
            return "Snapchat call watcher is off."
        poll = bool(self._poll_thread and self._poll_thread.is_alive())
        ntfy = bool(self._ntfy_thread and self._ntfy_thread.is_alive())
        bits = [
            f"watcher {'on' if poll else 'idle'}",
            f"auto-answer {'on' if self.auto_answer else 'off'}",
        ]
        if self.topic:
            bits.append(
                f"ntfy {'listening' if ntfy else 'topic ready'} "
                f"{self.server}/{self.topic}"
            )
        else:
            bits.append("no phone Shortcut topic yet — say snapchat setup")
        return "Snapchat calls: " + " · ".join(bits)

    def webhook_url(self) -> str:
        if not self.topic:
            return ""
        return f"{self.server}/{self.topic}"

    def start(self) -> None:
        if not self.enabled:
            return
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="jarvis-snap-calls",
            daemon=True,
        )
        self._poll_thread.start()
        if self.topic:
            self._ntfy_thread = threading.Thread(
                target=self._ntfy_loop,
                name="jarvis-snap-ntfy",
                daemon=True,
            )
            self._ntfy_thread.start()
            print(f"[snapchat] listening ntfy {self.webhook_url()}")
        print("[snapchat] call watcher started")

    def stop(self) -> None:
        self._stop.set()

    def inject_test(self, caller: str = "Test") -> SnapCallEvent:
        """Simulate an incoming Snap call (for voice 'test snapchat call')."""
        ev = SnapCallEvent(caller=(caller or "Test").strip() or "Test", source="test")
        self._fire(ev, force=True)
        return ev

    def try_answer_now(self) -> str:
        """Force a best-effort Answer click on any visible Snap/Phone Link call UI."""
        hit = self.scan_once()
        if not hit:
            return "No Snapchat / Phone Link call window found."
        ok = self._answer_call(hit)
        if ok:
            return f"Tried to answer call from {hit.caller}."
        return f"Saw call from {hit.caller} but could not click Answer — check the window."

    # ── detection ───────────────────────────────────────────────

    def scan_once(self) -> SnapCallEvent | None:
        """Return an incoming-call event if a matching window is visible."""
        for title, hwnd, exe in self._enumerate_windows():
            blob = f"{title} {exe}".lower()
            is_snap_family = any(h in blob for h in _SNAP_HINTS) or any(
                h in exe for h in _PROC_HINTS
            )
            is_call = any(h in blob for h in _CALL_HINTS)
            # Phone Link often shows "Incoming call" without "Snapchat" in title
            if is_call and (is_snap_family or "call" in blob):
                # Prefer Snap-ish; still allow generic Phone Link incoming
                if not is_snap_family and "incoming" not in blob and "calling" not in blob:
                    continue
                caller = self._parse_caller(title)
                return SnapCallEvent(
                    caller=caller,
                    source="window",
                    title=title[:160],
                    hwnd=int(hwnd),
                )
        return None

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                hit = self.scan_once()
                if hit:
                    self._fire(hit)
            except Exception as e:
                print(f"[snapchat] poll: {e}")
            self._stop.wait(self.poll_sec)

    def _ntfy_loop(self) -> None:
        if not self.topic:
            return
        url = f"{self.server}/{self.topic}/json"
        backoff = 2.0
        while not self._stop.is_set():
            try:
                import urllib.request

                req = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "application/x-ndjson",
                        "User-Agent": "jarvis-snapchat/1.0",
                    },
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    backoff = 2.0
                    while not self._stop.is_set():
                        line = resp.readline()
                        if not line:
                            break
                        self._handle_ntfy_line(line.decode("utf-8", errors="replace"))
            except Exception as e:
                if self._stop.is_set():
                    break
                print(f"[snapchat] ntfy reconnect in {backoff:.0f}s: {e}")
                time.sleep(backoff)
                backoff = min(60.0, backoff * 1.5)

    def _handle_ntfy_line(self, line: str) -> None:
        raw = (line or "").strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
        except Exception:
            data = {"message": raw}
        ev = str(data.get("event") or "").lower()
        if ev in ("open", "keepalive"):
            return
        msg = str(
            data.get("message") or data.get("title") or data.get("cmd") or ""
        ).strip()
        tags = " ".join(str(t) for t in (data.get("tags") or [])).lower()
        blob = f"{msg} {tags}".lower()
        if not any(
            k in blob
            for k in (
                "snap",
                "snapchat",
                "call",
                "calling",
                "video chat",
                "incoming",
            )
        ):
            return
        caller = self._parse_caller(msg) or "Snapchat"
        self._fire(SnapCallEvent(caller=caller, source="ntfy", title=msg[:160]))

    def _fire(self, ev: SnapCallEvent, *, force: bool = False) -> None:
        now = time.monotonic()
        fp = f"{ev.source}:{ev.caller}:{ev.title}".lower()
        if not force:
            if now < self._until and fp == self._last_fingerprint:
                return
            if now < self._until and ev.source == "window":
                # Still ringing — try answer once if we haven't
                if self.auto_answer and fp != self._answered_fp and ev.hwnd:
                    if self._answer_call(ev):
                        self._answered_fp = fp
                return
        self._until = now + self.cooldown_sec
        self._last_fingerprint = fp
        print(f"[snapchat] incoming from {ev.caller} via {ev.source}")
        if self.on_call:
            try:
                self.on_call(ev)
            except Exception as e:
                print(f"[snapchat] on_call: {e}")
        if self.auto_answer and ev.source != "test":
            # Small delay so UI finishes drawing Answer
            time.sleep(0.15)
            if self._answer_call(ev):
                self._answered_fp = fp

    # ── answer automation ───────────────────────────────────────

    def _answer_call(self, ev: SnapCallEvent) -> bool:
        hwnd = int(ev.hwnd or 0)
        if not hwnd:
            # Re-scan for a live window
            again = self.scan_once()
            if again and again.hwnd:
                hwnd = int(again.hwnd)
                ev = again
        if hwnd:
            self._focus_hwnd(hwnd)
        # Prefer UI Automation "Answer" control
        if hwnd and self._uia_click_answer(hwnd):
            return True
        # pyautogui: click common Answer zones + Enter
        if self._pyautogui_answer(hwnd):
            return True
        return False

    @staticmethod
    def _focus_hwnd(hwnd: int) -> None:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _uia_click_answer(self, hwnd: int) -> bool:
        """Best-effort UI Automation: find a button named Answer/Accept."""
        try:
            from pywinauto import Application  # type: ignore

            app = Application(backend="uia").connect(handle=hwnd, timeout=2)
            win = app.window(handle=hwnd)
            for label in _ANSWER_LABELS:
                try:
                    ctrl = win.child_window(
                        title_re=f"(?i).*{label}.*", control_type="Button"
                    )
                    if ctrl.exists(timeout=0.4):
                        ctrl.click_input()
                        return True
                except Exception:
                    continue
            for ctrl in win.descendants(control_type="Button"):
                try:
                    name = (ctrl.window_text() or "").strip().lower()
                    if any(a in name for a in _ANSWER_LABELS):
                        ctrl.click_input()
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return self._soft_key_answer()

    @staticmethod
    def _soft_key_answer() -> bool:
        """Enter / Space — many call UIs bind these to Answer."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            KEYEVENTF_KEYUP = 0x0002
            for vk in (0x0D, 0x20):  # Enter, Space
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.04)
            return True
        except Exception:
            return False

    def _pyautogui_answer(self, hwnd: int) -> bool:
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            # If we have a window rect, click lower-third center (Answer often lives there)
            rect = self._window_rect(hwnd) if hwnd else None
            if rect:
                left, top, right, bottom = rect
                w = max(1, right - left)
                h = max(1, bottom - top)
                # Phone Link / Snap overlays: Answer is usually bottom-center or mid-right
                points = [
                    (left + int(w * 0.50), top + int(h * 0.78)),
                    (left + int(w * 0.62), top + int(h * 0.72)),
                    (left + int(w * 0.38), top + int(h * 0.72)),
                    (left + int(w * 0.50), top + int(h * 0.85)),
                ]
                for x, y in points:
                    try:
                        pyautogui.click(x, y)
                        time.sleep(0.12)
                    except Exception:
                        continue
                try:
                    pyautogui.press("enter")
                except Exception:
                    pass
                return True
            # No hwnd — press Enter globally (last resort)
            pyautogui.press("enter")
            return True
        except Exception as e:
            print(f"[snapchat] pyautogui answer: {e}")
            return False

    @staticmethod
    def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        except Exception:
            return None

    # ── win32 helpers ───────────────────────────────────────────

    def _enumerate_windows(self) -> list[tuple[str, int, str]]:
        out: list[tuple[str, int, str]] = []
        try:
            import ctypes
            from ctypes import wintypes
            from pathlib import Path

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            EnumWindowsProc = ctypes.WINFUNCTYPE(
                ctypes.c_int, wintypes.HWND, wintypes.LPARAM
            )
            exe_cache: dict[int, str] = {}

            def _exe(pid: int) -> str:
                if pid in exe_cache:
                    return exe_cache[pid]
                name = ""
                try:
                    h = kernel32.OpenProcess(0x1000, False, pid)
                    if h:
                        try:
                            buf = ctypes.create_unicode_buffer(260)
                            size = wintypes.DWORD(260)
                            if kernel32.QueryFullProcessImageNameW(
                                h, 0, buf, ctypes.byref(size)
                            ):
                                name = Path(buf.value).name.lower()
                        finally:
                            kernel32.CloseHandle(h)
                except Exception:
                    name = ""
                exe_cache[pid] = name
                return name

            def _cb(hwnd, _lp):
                if not user32.IsWindowVisible(hwnd):
                    return 1
                n = user32.GetWindowTextLengthW(hwnd)
                if n < 1:
                    return 1
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                title = (buf.value or "").strip()
                if not title:
                    return 1
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                exe = _exe(int(pid.value)) if pid.value else ""
                out.append((title, int(hwnd), exe))
                return 1

            user32.EnumWindows(EnumWindowsProc(_cb), 0)
        except Exception as e:
            print(f"[snapchat] enum: {e}")
        return out

    @staticmethod
    def _parse_caller(text: str) -> str:
        t = (text or "").strip()
        if not t:
            return "Someone"
        patterns = (
            r"(?i)(?:incoming\s+call\s+from|call\s+from|is\s+calling|"
            r"calling\s+you[:\s]+|snap\s+call\s+from|from)\s+([A-Za-z0-9_ .\-]{2,40})",
            r"(?i)^([A-Za-z0-9_ .\-]{2,40})\s+is\s+calling",
        )
        for p in patterns:
            m = re.search(p, t)
            if m:
                name = m.group(1).strip(" .,-_")
                if name and name.lower() not in (
                    "snapchat",
                    "phone",
                    "link",
                    "windows",
                    "incoming",
                    "call",
                ):
                    return name[:40]
        # Strip common chrome
        clean = re.sub(
            r"(?i)\b(incoming|call|video|audio|chat|snapchat|phone link|"
            r"your phone|link to windows|from|is calling)\b",
            " ",
            t,
        )
        clean = re.sub(r"\s+", " ", clean).strip(" -–—|:")
        return (clean[:40] if clean else "Someone")

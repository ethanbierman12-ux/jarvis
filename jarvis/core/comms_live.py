"""Live messaging overlay — Snapchat / Instagram / iMessage (Phone Link).

Watches Windows toast history + messaging windows, extracts new text,
translates to English in real time, and notifies Jarvis (HUD / TTS / phone).

No official chat APIs — relies on Phone Link mirroring + Windows notifications
+ optional OCR. Reliability tracks whatever UI Windows exposes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


_APP_MARKERS: dict[str, tuple[str, ...]] = {
    "snapchat": ("snapchat", "snap chat"),
    "instagram": ("instagram", "ig ", "direct ·", "instagram.com"),
    "imessage": (
        "imessage",
        "messages",
        "phone link",
        "your phone",
        "link to windows",
        "iphone",
    ),
}

_CALL_HINTS = (
    "incoming",
    "is calling",
    "calling you",
    "video chat",
    "video call",
    "audio call",
    "missed call",
    "started a call",
)

_SKIP_TOAST = (
    "battery",
    "wifi",
    "bluetooth",
    "windows update",
    "defender",
    "cortana",
)


@dataclass
class CommsEvent:
    app: str  # snapchat | instagram | imessage | unknown
    kind: str  # message | call
    sender: str
    text: str
    translated: str = ""
    lang: str = ""
    source: str = "toast"  # toast | window | ocr | test


class CommsLiveBridge:
    """Poll toasts + Phone Link / IG / Snap windows; fire on_event for new lines."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        translate: bool = True,
        target_lang: str = "en",
        speak_messages: bool = True,
        poll_sec: float = 1.5,
        apps: tuple[str, ...] = ("snapchat", "instagram", "imessage"),
        on_event: Callable[[CommsEvent], None] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.translate = bool(translate)
        self.target_lang = (target_lang or "en").strip().lower() or "en"
        self.speak_messages = bool(speak_messages)
        self.poll_sec = max(0.35, float(poll_sec or 0.55))
        self.apps = tuple(a for a in apps if a in _APP_MARKERS) or (
            "snapchat",
            "instagram",
            "imessage",
        )
        self.on_event = on_event
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen: set[str] = set()
        self._seen_order: list[str] = []
        self._last_window_blob: dict[str, str] = {}
        self._tick = 0
        self._wpn_mtime = 0.0
        self._wpn_cache: list[tuple[str, str, str]] = []
        self._wpndb = (
            Path.home()
            / "AppData"
            / "Local"
            / "Microsoft"
            / "Windows"
            / "Notifications"
            / "wpndatabase.db"
        )

    def status(self) -> str:
        if not self.enabled:
            return "Live comms (Snap/IG/iMessage) is off."
        alive = bool(self._thread and self._thread.is_alive())
        apps = ", ".join(self.apps)
        return (
            f"Live comms {'watching' if alive else 'idle'} · {apps} · "
            f"translate→{self.target_lang} {'on' if self.translate else 'off'}"
        )

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="jarvis-comms-live",
            daemon=True,
        )
        self._thread.start()
        print(f"[comms] live watcher started ({', '.join(self.apps)})")

    def stop(self) -> None:
        self._stop.set()

    def inject_test(
        self,
        *,
        app: str = "imessage",
        text: str = "Hola, ¿cómo estás?",
        sender: str = "Test",
    ) -> CommsEvent:
        ev = CommsEvent(
            app=app if app in _APP_MARKERS else "imessage",
            kind="message",
            sender=sender,
            text=text,
            source="test",
        )
        self._enrich(ev)
        self._fire(ev, force=True)
        return ev

    # ── main loop ───────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick += 1
                for ev in self._scan_toasts():
                    self._enrich(ev)
                    self._fire(ev)
                # UIA window scrape is expensive — every 3rd tick only
                if self._tick % 3 == 0:
                    for ev in self._scan_windows():
                        self._enrich(ev)
                        self._fire(ev)
            except Exception as e:
                print(f"[comms] poll: {e}")
            self._stop.wait(self.poll_sec)

    def _fire(self, ev: CommsEvent, *, force: bool = False) -> None:
        key = self._fingerprint(ev)
        if not force and key in self._seen:
            return
        self._remember(key)
        print(
            f"[comms] {ev.app}/{ev.kind} {ev.sender}: "
            f"{(ev.translated or ev.text)[:80]}"
        )
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception as e:
                print(f"[comms] on_event: {e}")

    def _fingerprint(self, ev: CommsEvent) -> str:
        raw = f"{ev.app}|{ev.kind}|{ev.sender}|{ev.text}".lower().strip()
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()

    def _remember(self, key: str) -> None:
        if key in self._seen:
            return
        self._seen.add(key)
        self._seen_order.append(key)
        while len(self._seen_order) > 400:
            old = self._seen_order.pop(0)
            self._seen.discard(old)

    # ── toast DB ────────────────────────────────────────────────

    def _scan_toasts(self) -> list[CommsEvent]:
        out: list[CommsEvent] = []
        db = self._wpndb
        if not db.is_file():
            return out
        try:
            mtime = db.stat().st_mtime
            # Skip full copy+query when notification DB hasn't changed
            if mtime == self._wpn_mtime and self._wpn_cache is not None:
                rows = self._wpn_cache
            else:
                import shutil
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    shutil.copy2(db, tmp_path)
                    conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
                    conn.row_factory = sqlite3.Row
                    try:
                        rows = self._query_notifications(conn)
                    finally:
                        conn.close()
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                self._wpn_mtime = mtime
                self._wpn_cache = rows
            for title, body, app_id in rows:
                blob = f"{title} {body} {app_id}".lower()
                if any(s in blob for s in _SKIP_TOAST):
                    continue
                app = self._detect_app(blob)
                if not app or app not in self.apps:
                    continue
                text = (body or title or "").strip()
                if not text or len(text) < 2:
                    continue
                kind = "call" if any(h in blob for h in _CALL_HINTS) else "message"
                sender = self._parse_sender(title, body, app)
                out.append(
                    CommsEvent(
                        app=app,
                        kind=kind,
                        sender=sender,
                        text=text[:500],
                        source="toast",
                    )
                )
        except Exception as e:
            # DB lock / schema — silent most ticks
            if int(time.time()) % 30 == 0:
                print(f"[comms] toast db: {e}")
        return out

    @staticmethod
    def _query_notifications(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
        """Return (title, body, app_id) from whatever Notification tables exist."""
        cur = conn.cursor()
        tables = {
            r[0].lower()
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        rows: list[tuple[str, str, str]] = []

        # Modern: Notification + NotificationHandler
        if "notification" in tables:
            cols = {
                r[1].lower()
                for r in cur.execute("PRAGMA table_info(Notification)").fetchall()
            }
            # Payload is often XML/JSON in a blob/text column
            payload_col = next(
                (
                    c
                    for c in (
                        "payload",
                        "content",
                        "notificationdata",
                        "data",
                    )
                    if c in cols
                ),
                None,
            )
            handler_join = "NotificationHandler" in {t.title() for t in tables} or (
                "notificationhandler" in tables
            )
            try:
                if payload_col and handler_join:
                    q = f"""
                        SELECT n.{payload_col} AS payload, h.PrimaryId AS app_id
                        FROM Notification n
                        LEFT JOIN NotificationHandler h ON n.HandlerId = h.RecordId
                        ORDER BY n.ArrivalTime DESC
                        LIMIT 40
                    """
                    for r in cur.execute(q).fetchall():
                        title, body = CommsLiveBridge._parse_payload(r[0])
                        rows.append((title, body, str(r[1] or "")))
                elif payload_col:
                    q = f"""
                        SELECT {payload_col} FROM Notification
                        ORDER BY rowid DESC LIMIT 40
                    """
                    for r in cur.execute(q).fetchall():
                        title, body = CommsLiveBridge._parse_payload(r[0])
                        rows.append((title, body, ""))
            except Exception:
                pass

        # Fallback: scan any text columns for recent-looking rows
        if not rows:
            for table in tables:
                if "notif" not in table and "toast" not in table:
                    continue
                try:
                    info = cur.execute(f"PRAGMA table_info({table})").fetchall()
                    text_cols = [
                        c[1]
                        for c in info
                        if "char" in (c[2] or "").lower()
                        or "text" in (c[2] or "").lower()
                        or "clob" in (c[2] or "").lower()
                    ][:3]
                    if not text_cols:
                        continue
                    sel = ", ".join(text_cols)
                    for r in cur.execute(
                        f"SELECT {sel} FROM {table} ORDER BY rowid DESC LIMIT 20"
                    ).fetchall():
                        joined = " | ".join(str(x or "") for x in r)
                        title, body = CommsLiveBridge._parse_payload(joined)
                        if title or body:
                            rows.append((title, body, table))
                except Exception:
                    continue
        return rows

    @staticmethod
    def _parse_payload(raw) -> tuple[str, str]:
        if raw is None:
            return "", ""
        if isinstance(raw, (bytes, bytearray)):
            try:
                text = raw.decode("utf-8", errors="ignore")
            except Exception:
                text = str(raw)
        else:
            text = str(raw)
        text = text.strip()
        if not text:
            return "", ""
        # Toast XML
        titles = re.findall(
            r"<text[^>]*>([^<]+)</text>", text, flags=re.I
        ) or re.findall(r'"text"\s*:\s*"([^"]+)"', text)
        if titles:
            title = titles[0].strip()
            body = " ".join(t.strip() for t in titles[1:3]).strip()
            return title[:120], (body or title)[:500]
        # Plain
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return "", text[:500]
        return lines[0][:120], (" ".join(lines[1:3]) or lines[0])[:500]

    # ── window / UIA / OCR ──────────────────────────────────────

    def _scan_windows(self) -> list[CommsEvent]:
        out: list[CommsEvent] = []
        for title, hwnd, exe in self._enumerate_windows():
            blob = f"{title} {exe}".lower()
            app = self._detect_app(blob)
            if not app or app not in self.apps:
                continue
            # Read UIA text snippet from the window
            snippet = self._uia_text(hwnd, max_chars=800)
            if not snippet:
                snippet = title
            prev = self._last_window_blob.get(app, "")
            # Diff: only fire when content grows / changes meaningfully
            if snippet and snippet != prev and len(snippet) > 3:
                # Extract newest-looking line
                new_bits = self._diff_lines(prev, snippet)
                self._last_window_blob[app] = snippet
                for line in new_bits[-3:]:
                    if len(line) < 2:
                        continue
                    kind = (
                        "call"
                        if any(h in line.lower() for h in _CALL_HINTS)
                        else "message"
                    )
                    sender = self._parse_sender(title, line, app)
                    out.append(
                        CommsEvent(
                            app=app,
                            kind=kind,
                            sender=sender,
                            text=line[:500],
                            source="window",
                        )
                    )
            elif not prev and snippet:
                self._last_window_blob[app] = snippet
        return out

    @staticmethod
    def _diff_lines(old: str, new: str) -> list[str]:
        old_set = {ln.strip() for ln in (old or "").splitlines() if ln.strip()}
        fresh: list[str] = []
        for ln in (new or "").splitlines():
            s = ln.strip()
            if not s or s in old_set:
                continue
            # Skip UI chrome
            low = s.lower()
            if low in (
                "send",
                "type a message",
                "search",
                "calls",
                "messages",
                "photos",
            ):
                continue
            if len(s) < 2:
                continue
            fresh.append(s)
        return fresh

    def _uia_text(self, hwnd: int, max_chars: int = 800) -> str:
        try:
            from pywinauto import Application  # type: ignore

            app = Application(backend="uia").connect(handle=hwnd, timeout=0.35)
            win = app.window(handle=hwnd)
            chunks: list[str] = []
            for ctrl in win.descendants():
                try:
                    t = (ctrl.window_text() or "").strip()
                    if t and t not in chunks:
                        chunks.append(t)
                    if sum(len(c) for c in chunks) > max_chars:
                        break
                except Exception:
                    continue
            return "\n".join(chunks)[:max_chars]
        except Exception:
            return ""

    def _enumerate_windows(self) -> list[tuple[str, int, str]]:
        out: list[tuple[str, int, str]] = []
        try:
            import ctypes
            from ctypes import wintypes
            from pathlib import Path as P

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
                                name = P(buf.value).name.lower()
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
            print(f"[comms] enum: {e}")
        return out

    # ── translate / parse ───────────────────────────────────────

    def _enrich(self, ev: CommsEvent) -> None:
        text = (ev.text or "").strip()
        if not text:
            return
        if not self.translate:
            ev.translated = text
            return
        # Skip if already mostly target language ASCII short messages... still try
        translated, lang = self._translate(text, self.target_lang)
        ev.translated = translated or text
        ev.lang = lang or ""

    def _translate(self, text: str, target: str) -> tuple[str, str]:
        text = (text or "").strip()
        if not text:
            return "", ""
        # Fast path: Google free endpoint (no key)
        try:
            q = urllib.parse.quote(text[:450])
            url = (
                "https://translate.googleapis.com/translate_a/single"
                f"?client=gtx&sl=auto&tl={urllib.parse.quote(target)}&dt=t&q={q}"
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "jarvis-comms/1.0"}, method="GET"
            )
            with urllib.request.urlopen(req, timeout=2.2) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            # data[0] = [[translated, original, ...], ...] ; data[2] = detected lang
            parts = []
            if isinstance(data, list) and data and isinstance(data[0], list):
                for chunk in data[0]:
                    if isinstance(chunk, list) and chunk and chunk[0]:
                        parts.append(str(chunk[0]))
            lang = ""
            if isinstance(data, list) and len(data) > 2 and isinstance(data[2], str):
                lang = data[2]
            out = "".join(parts).strip()
            if out and out.lower() != text.lower():
                return out, lang
            if out:
                return out, lang or target
        except Exception:
            pass
        # LLM fallback
        try:
            from jarvis.core.llm_client import complete

            prompt = (
                f"Translate to {target}. Reply with ONLY the translation, "
                f"no quotes or notes.\n\n{text[:400]}"
            )
            out = (complete(prompt, max_tokens=200) or "").strip()
            if out and not out.lower().startswith("error"):
                return out, "auto"
        except Exception:
            pass
        return text, ""

    def _detect_app(self, blob: str) -> str:
        b = (blob or "").lower()
        # Prefer specific apps before generic Phone Link → imessage
        for app in ("snapchat", "instagram", "imessage"):
            if app not in self.apps:
                continue
            if any(m in b for m in _APP_MARKERS[app]):
                return app
        return ""

    @staticmethod
    def _parse_sender(title: str, body: str, app: str) -> str:
        for src in (title, body):
            m = re.search(
                r"(?i)^(?:from\s+)?([A-Za-z0-9_ .\-]{2,40})(?:\s*[:\-–—]|\s+says\b)",
                (src or "").strip(),
            )
            if m:
                name = m.group(1).strip(" .")
                if name.lower() not in (
                    "snapchat",
                    "instagram",
                    "imessage",
                    "messages",
                    "phone link",
                    "your phone",
                    "windows",
                ):
                    return name[:40]
        # Title often is the contact on Phone Link
        t = (title or "").strip()
        for junk in (
            "Snapchat",
            "Instagram",
            "Phone Link",
            "Your Phone",
            "Link to Windows",
            "Messages",
            "iMessage",
        ):
            t = t.replace(junk, "").strip(" -–—|:")
        return (t[:40] if t else app.title())

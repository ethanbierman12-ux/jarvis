"""Doorbell inbound bridge — Alexa/IFTTT → ntfy → Jarvis (no open ports)."""

from __future__ import annotations

import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from typing import Callable


class DoorbellBridge:
    """
    Listen on a private ntfy topic. IFTTT / Alexa posts there; Jarvis announces.

    IFTTT Webhooks action:
      URL:    https://ntfy.sh/<topic>
      Method: POST
      Body:   ding   (or motion)
    """

    def __init__(
        self,
        *,
        topic: str = "",
        server: str = "https://ntfy.sh",
        enabled: bool = True,
        on_event: Callable[[str], str] | None = None,
    ) -> None:
        self.server = (server or "https://ntfy.sh").rstrip("/")
        self.topic = (topic or "").strip()
        self.enabled = bool(enabled and self.topic)
        self.on_event = on_event
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def make_topic() -> str:
        return f"jarvis-door-{secrets.token_hex(4)}"

    def status(self) -> str:
        if not self.topic:
            return "Doorbell bridge has no ntfy topic yet."
        if not self.enabled:
            return f"Doorbell topic `{self.topic}` ready — listener off."
        alive = bool(self._thread and self._thread.is_alive())
        return (
            f"Doorbell ntfy `{'listening' if alive else 'stopped'}` — "
            f"POST {self.server}/{self.topic}  body: ding|motion"
        )

    def webhook_url(self) -> str:
        if not self.topic:
            return ""
        return f"{self.server}/{self.topic}"

    def start(self) -> None:
        if not self.enabled or not self.topic:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="jarvis-doorbell-ntfy",
            daemon=True,
        )
        self._thread.start()
        print(f"[doorbell] listening on {self.webhook_url()}")

    def stop(self) -> None:
        self._stop.set()

    def _listen_loop(self) -> None:
        url = f"{self.server}/{self.topic}/json"
        backoff = 2.0
        while not self._stop.is_set():
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "application/x-ndjson",
                        "User-Agent": "jarvis-doorbell/1.0",
                    },
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    backoff = 2.0
                    while not self._stop.is_set():
                        line = resp.readline()
                        if not line:
                            break
                        self._handle_line(line.decode("utf-8", errors="replace"))
            except Exception as e:
                if self._stop.is_set():
                    break
                print(f"[doorbell] ntfy reconnect in {backoff:.0f}s: {e}")
                time.sleep(backoff)
                backoff = min(60.0, backoff * 1.5)

    def _handle_line(self, line: str) -> None:
        raw = (line or "").strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
        except Exception:
            data = {"message": raw}
        # ntfy keepalive / open events
        ev = str(data.get("event") or "").lower()
        if ev in ("open", "keepalive"):
            return
        msg = str(
            data.get("message")
            or data.get("title")
            or data.get("cmd")
            or ""
        ).strip().lower()
        tags = " ".join(str(t) for t in (data.get("tags") or [])).lower()
        blob = f"{msg} {tags} {ev}"
        kind = "ding"
        if any(w in blob for w in ("motion", "move", "detected")):
            kind = "motion"
        elif any(w in blob for w in ("ding", "door", "ring", "press", "someone")):
            kind = "ding"
        elif not msg and not tags:
            return
        if not self.on_event:
            return
        try:
            self.on_event(kind)
        except Exception as e:
            print(f"[doorbell] on_event: {e}")

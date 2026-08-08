"""iPhone / phone bridge — push alerts via ntfy (works on iPhone 14 App Store)."""

from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class PhoneBridge:
    """
    Send Jarvis alerts to an iPhone.

    Recommended setup (iPhone 14):
      1. Install free **ntfy** from the App Store
      2. Subscribe to your private topic (printed on first run / settings)
      3. Say: "text my phone hello" or "notify phone servers are green"
    """

    def __init__(
        self,
        *,
        topic: str = "",
        server: str = "https://ntfy.sh",
        shortcuts_webhook: str = "",
        enabled: bool = True,
    ) -> None:
        self.server = (server or "https://ntfy.sh").rstrip("/")
        self.topic = (topic or "").strip()
        self.shortcuts_webhook = (shortcuts_webhook or "").strip()
        self.enabled = bool(enabled)

    @staticmethod
    def make_topic(user_hint: str = "jarvis") -> str:
        slug = "".join(c for c in (user_hint or "jarvis").lower() if c.isalnum())[:12] or "jarvis"
        return f"{slug}-{secrets.token_hex(3)}"

    def status(self) -> str:
        if not self.enabled:
            return "Phone bridge disabled."
        if not self.topic and not self.shortcuts_webhook:
            return (
                "Phone not linked. Install ntfy on your iPhone, then set phone_ntfy_topic "
                "in settings (or say 'link my phone')."
            )
        bits = []
        if self.topic:
            bits.append(f"ntfy topic `{self.topic}` @ {self.server}")
        if self.shortcuts_webhook:
            bits.append("iOS Shortcuts webhook")
        return "Phone linked via " + " + ".join(bits) + "."

    def subscribe_url(self) -> str:
        if not self.topic:
            return ""
        return f"{self.server}/{self.topic}"

    def ping(self, message: str, *, title: str = "JARVIS") -> str:
        """High-priority alert alias used by security / doorbell paths."""
        return self.notify(message, title=title, priority=5)

    def notify_image(
        self,
        message: str,
        image_path: str,
        *,
        title: str = "JARVIS",
        priority: int = 5,
        filename: str = "intruder.jpg",
    ) -> str:
        """High-priority ntfy push with a JPEG attachment (intruder snapshot)."""
        msg = (message or "").strip()
        if not self.enabled:
            return "Phone bridge is disabled in settings."
        if not self.topic:
            return "No phone topic yet."
        path = Path(image_path)
        if not path.is_file():
            return f"Image missing: {image_path}"
        try:
            self._ntfy_file(
                msg,
                path,
                title=title,
                priority=priority,
                filename=filename or path.name,
            )
            return f"Sent photo to your iPhone: {msg[:100]}"
        except Exception as e:
            return f"Could not send photo ({e})."

    def notify(
        self,
        message: str,
        *,
        title: str = "JARVIS",
        priority: int = 3,
        tags: list[str] | None = None,
    ) -> str:
        msg = (message or "").strip()
        if not msg:
            return "Nothing to send to your phone."
        if not self.enabled:
            return "Phone bridge is disabled in settings."

        errors: list[str] = []
        ok = False

        if self.topic:
            try:
                self._ntfy(msg, title=title, priority=priority, tags=tags)
                ok = True
            except Exception as e:
                errors.append(f"ntfy: {e}")

        if self.shortcuts_webhook:
            try:
                self._post_json(
                    self.shortcuts_webhook,
                    {"title": title, "message": msg, "source": "jarvis"},
                )
                ok = True
            except Exception as e:
                errors.append(f"shortcuts: {e}")

        if ok:
            return f"Sent to your iPhone: {msg[:120]}"
        if not self.topic and not self.shortcuts_webhook:
            return (
                "No phone topic yet. Say 'link my phone', install ntfy, "
                "and subscribe to the topic I give you."
            )
        return f"Could not reach your phone ({'; '.join(errors)})."

    def _ntfy(
        self,
        message: str,
        *,
        title: str,
        priority: int,
        tags: list[str] | None = None,
    ) -> None:
        url = f"{self.server}/{self.topic}"
        tag_list = [str(t) for t in (tags or ["warning", "rotating_light"]) if t]
        if not tag_list:
            tag_list = ["warning", "rotating_light"]
        # JSON publish avoids Windows header encoding issues
        payload = json.dumps(
            {
                "topic": self.topic,
                "title": (title or "JARVIS")[:120],
                "message": message,
                "priority": max(1, min(5, int(priority))),
                "tags": tag_list[:8],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()

    def _ntfy_file(
        self,
        message: str,
        path: Path,
        *,
        title: str,
        priority: int,
        filename: str,
    ) -> None:
        """PUT binary file to ntfy with metadata headers (ASCII-safe)."""
        url = f"{self.server}/{self.topic}"
        data = path.read_bytes()
        # HTTP headers must be latin-1 — keep ASCII
        safe_title = "".join(c if ord(c) < 128 else "-" for c in (title or "JARVIS"))[:120]
        safe_msg = "".join(c if ord(c) < 128 else "-" for c in (message or ""))[:250]
        safe_name = "".join(
            c if (c.isalnum() or c in "._-") else "_" for c in (filename or "intruder.jpg")
        )[:80]
        headers = {
            "Title": safe_title,
            "Message": safe_msg,
            "Priority": str(max(1, min(5, int(priority)))),
            "Tags": "warning,camera,rotating_light",
            "Filename": safe_name,
            "Content-Type": "image/jpeg",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()

    def _post_json(self, url: str, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}") from e

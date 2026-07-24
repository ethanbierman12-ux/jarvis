"""Manus AI bridge — create agent tasks via Manus API v2."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class ManusBridge:
    """
    Talk to Manus (https://manus.im) from Jarvis.

    Setup:
      1. Open Manus → API Integration → Create API key
      2. Put key in settings as manus_api_key (vaulted) or say:
         "set manus key to YOUR_KEY"
      3. Say: "ask manus research the latest AI news"
    """

    BASE = "https://api.manus.ai"

    def __init__(
        self,
        api_key: str = "",
        *,
        enabled: bool = True,
        agent_profile: str = "manus-1.6",
        base_url: str = "",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.enabled = bool(enabled)
        self.agent_profile = (agent_profile or "manus-1.6").strip() or "manus-1.6"
        self.base = (base_url or self.BASE).rstrip("/")
        self.last_task_id: str = ""
        self.last_task_url: str = ""
        self.last_title: str = ""

    @property
    def linked(self) -> bool:
        return bool(self.enabled and self.api_key)

    def status(self) -> str:
        if not self.enabled:
            return "Manus bridge is disabled in settings."
        if not self.api_key:
            return (
                "Manus not linked. Create an API key at manus.im "
                "(API Integration), then say set manus key to YOUR_KEY."
            )
        bits = [f"Manus linked · profile {self.agent_profile}"]
        if self.last_task_id:
            bits.append(f"last task `{self.last_task_id[:16]}…`")
            if self.last_task_url:
                bits.append(self.last_task_url)
        return " — ".join(bits) + "."

    def create_task(
        self,
        prompt: str,
        *,
        title: str = "",
        interactive: bool = False,
        hide_in_list: bool = False,
    ) -> str:
        msg = (prompt or "").strip()
        if not msg:
            return "Nothing to send to Manus."
        if not self.enabled:
            return "Manus bridge is disabled in settings."
        if not self.api_key:
            return (
                "Manus API key missing. Say set manus key to YOUR_KEY "
                "(from manus.im → API Integration)."
            )

        body: dict[str, Any] = {
            "message": {"content": msg},
            "agent_profile": self.agent_profile,
            "interactive_mode": bool(interactive),
            "hide_in_task_list": bool(hide_in_list),
            "share_visibility": "private",
        }
        if title.strip():
            body["title"] = title.strip()[:120]

        try:
            data = self._post("/v2/task.create", body)
        except Exception as e:
            return f"Manus create failed: {e}"

        if not data.get("ok", True) and data.get("error"):
            err = data["error"]
            return f"Manus error: {err.get('code', '?')} — {err.get('message', data)}"

        tid = str(data.get("task_id") or "").strip()
        url = str(data.get("task_url") or "").strip()
        ttitle = str(data.get("task_title") or title or "Manus task").strip()
        if tid:
            self.last_task_id = tid
            self.last_task_url = url
            self.last_title = ttitle
        if tid and url:
            return (
                f"Manus is on it: {ttitle}. "
                f"Task {tid[:12]}… — open {url}. "
                "Say manus status when you want a progress check."
            )
        if tid:
            return (
                f"Manus task started ({ttitle}, id {tid[:16]}…). "
                "Say manus status for progress."
            )
        return f"Manus responded: {json.dumps(data)[:220]}"

    def task_status(self, task_id: str = "") -> str:
        tid = (task_id or self.last_task_id or "").strip()
        if not tid:
            return "No Manus task yet. Say ask manus … to start one."
        if not self.api_key:
            return "Manus API key missing."

        try:
            data = self._get(
                "/v2/task.listMessages",
                {"task_id": tid, "limit": "30", "order": "desc", "verbose": "false"},
            )
        except Exception as e:
            return f"Manus status failed: {e}"

        if not data.get("ok", True) and data.get("error"):
            err = data["error"]
            return f"Manus error: {err.get('code', '?')} — {err.get('message', data)}"

        messages = data.get("messages") or data.get("data") or []
        if not isinstance(messages, list):
            messages = []

        state = "unknown"
        assistant_bits: list[str] = []
        error_bits: list[str] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            kind = str(m.get("type") or m.get("event_type") or "").lower()
            if kind in ("status_update", "status"):
                st = (
                    m.get("status")
                    or (m.get("status_update") or {}).get("status")
                    or m.get("content")
                    or ""
                )
                if st:
                    state = str(st).lower()
            if kind in ("assistant_message", "assistant"):
                text = self._message_text(m)
                if text:
                    assistant_bits.append(text)
            if kind in ("error_message", "error"):
                text = self._message_text(m) or str(m.get("message") or "")
                if text:
                    error_bits.append(text)

        url = self.last_task_url if tid == self.last_task_id else f"https://manus.im/app/{tid}"
        if error_bits:
            return f"Manus task {tid[:12]}… error: {error_bits[0][:180]} ({url})"
        if assistant_bits:
            preview = assistant_bits[0][:220].strip()
            return f"Manus [{state}] {preview} — {url}"
        return f"Manus task {tid[:12]}… status: {state}. {url}"

    def send_followup(self, text: str, task_id: str = "") -> str:
        tid = (task_id or self.last_task_id or "").strip()
        msg = (text or "").strip()
        if not tid:
            return "No Manus task to continue. Say ask manus … first."
        if not msg:
            return "Nothing to send to Manus."
        if not self.api_key:
            return "Manus API key missing."
        try:
            data = self._post(
                "/v2/task.sendMessage",
                {"task_id": tid, "message": {"content": msg}},
            )
        except Exception as e:
            return f"Manus follow-up failed: {e}"
        if not data.get("ok", True) and data.get("error"):
            err = data["error"]
            return f"Manus error: {err.get('code', '?')} — {err.get('message', data)}"
        return f"Sent follow-up to Manus task {tid[:12]}…. Say manus status for progress."

    @staticmethod
    def _message_text(m: dict[str, Any]) -> str:
        content = m.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(str(p.get("text") or ""))
                elif isinstance(p, str):
                    parts.append(p)
            return " ".join(parts).strip()
        for key in ("text", "message", "body"):
            if m.get(key):
                return str(m[key]).strip()
        return ""

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-manus-api-key": self.api_key,
            "Accept": "application/json",
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base}{path}"
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=raw, headers=self._headers(), method="POST")
        return self._read(req)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        qs = urllib.parse.urlencode(params)
        url = f"{self.base}{path}?{qs}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        return self._read(req)

    def _read(self, req: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            try:
                parsed = json.loads(err_body) if err_body else {}
            except Exception:
                parsed = {}
            if isinstance(parsed, dict) and parsed.get("error"):
                return parsed
            raise RuntimeError(f"HTTP {e.code}: {err_body[:200] or e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(str(e.reason or e)) from e
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {"ok": False, "raw": body[:300]}
        return data if isinstance(data, dict) else {"ok": False, "raw": data}

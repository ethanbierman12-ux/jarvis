"""n8n webhook bridge — fire automation workflows as tools."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


class N8nBridge:
    def __init__(self, base_url: str = "", api_key: str = "") -> None:
        self.base = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.base)

    def trigger(self, path: str, payload: dict[str, Any] | None = None) -> str:
        """
        POST to an n8n webhook path, e.g. path='jarvis-in' → /webhook/jarvis-in
        """
        if not self.enabled:
            return "n8n bridge offline — set n8n_url in settings."
        path = (path or "").strip().lstrip("/")
        if path.startswith("webhook/"):
            url = f"{self.base}/{path}"
        else:
            url = f"{self.base}/webhook/{path}"
        data = json.dumps(payload or {}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-N8N-API-KEY"] = self.api_key
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:500]
            return f"n8n workflow '{path}' triggered. {body[:120]}"
        except Exception as e:
            return f"n8n trigger failed: {e}"

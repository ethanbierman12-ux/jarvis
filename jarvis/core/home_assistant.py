"""Home Assistant REST hooks — room lighting / scenes follow Jarvis state."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


# Jarvis activity → optional HA scene / script entity_id suffix map
STATE_SCENES = {
    "coding": "scene.jarvis_coding",
    "build": "scene.jarvis_build",  # deep purple
    "fetch": "scene.jarvis_fetch",  # glow blue
    "away": "scene.jarvis_away",
    "panic": "scene.jarvis_panic",
    "idle": "scene.jarvis_idle",
    "listening": "scene.jarvis_listening",
    "brief": "scene.jarvis_morning",
}


class HomeAssistant:
    def __init__(
        self,
        url: str = "",
        token: str = "",
        *,
        enabled: bool = False,
    ) -> None:
        self.base = (url or "").rstrip("/")
        self.token = (token or "").strip()
        self.enabled = bool(enabled and self.base and self.token)

    def status(self) -> str:
        if not self.enabled:
            return "Home Assistant offline (set ha_url + ha_token in settings)."
        try:
            data = self._get("/api/")
            return f"Home Assistant online — {data.get('message', 'ok')}."
        except Exception as e:
            return f"Home Assistant unreachable: {e}"

    def call_service(self, domain: str, service: str, data: dict[str, Any] | None = None) -> str:
        if not self.enabled:
            return "HA disabled."
        body = data or {}
        self._post(f"/api/services/{domain}/{service}", body)
        return f"HA {domain}.{service} fired."

    def turn_on(self, entity_id: str) -> str:
        domain = entity_id.split(".", 1)[0]
        return self.call_service(domain, "turn_on", {"entity_id": entity_id})

    def turn_off(self, entity_id: str) -> str:
        domain = entity_id.split(".", 1)[0]
        return self.call_service(domain, "turn_off", {"entity_id": entity_id})

    def activate_scene(self, entity_id: str) -> str:
        return self.call_service("scene", "turn_on", {"entity_id": entity_id})

    def on_jarvis_state(self, state: str) -> str:
        """Map brain activity → HA scene (best-effort, never blocks voice)."""
        if not self.enabled:
            return ""
        key = (state or "idle").lower().strip()
        entity = STATE_SCENES.get(key)
        if not entity:
            return ""
        try:
            return self.activate_scene(entity)
        except Exception as e:
            print(f"[ha] scene {entity}: {e}")
            return ""

    def webhook(self, webhook_id: str, payload: dict[str, Any] | None = None) -> str:
        if not self.enabled:
            return "HA disabled."
        # Native HA webhook: /api/webhook/<id>
        self._post(f"/api/webhook/{webhook_id}", payload or {})
        return f"HA webhook {webhook_id} posted."

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> Any:
        req = urllib.request.Request(
            self.base + path, headers=self._headers(), method="GET"
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    def _post(self, path: str, data: dict[str, Any]) -> Any:
        raw = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=raw, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8") or "{}"
                try:
                    return json.loads(body)
                except Exception:
                    return {"raw": body}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:200]}") from e

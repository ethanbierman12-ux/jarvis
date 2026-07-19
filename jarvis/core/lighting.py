"""Smart lighting — Philips Hue / LIFX task modes (coding / reading / late night)."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


# CIE-ish warm/cool targets as Hue XY + bri, or LIFX HSBK
MODES = {
    "coding": {"bri": 220, "ct": 250, "kelvin": 5000, "label": "bright white — coding"},
    "reading": {"bri": 160, "ct": 400, "kelvin": 2700, "label": "warm amber — reading"},
    "late_night": {"bri": 40, "ct": 500, "kelvin": 1800, "label": "dim red — late night"},
    "focus": {"bri": 200, "ct": 280, "kelvin": 4500, "label": "focus white"},
    "calm": {"bri": 90, "ct": 450, "kelvin": 2200, "label": "calm warm"},
}


class SmartLighting:
    def __init__(
        self,
        hue_bridge_ip: str = "",
        hue_username: str = "",
        lifx_token: str = "",
    ) -> None:
        self.hue_ip = (hue_bridge_ip or "").strip()
        self.hue_user = (hue_username or "").strip()
        self.lifx_token = (lifx_token or "").strip()
        self.mode = "coding"

    def set_mode(self, mode: str) -> str:
        key = (mode or "").lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "code": "coding",
            "coding_mode": "coding",
            "read": "reading",
            "reading_mode": "reading",
            "night": "late_night",
            "late": "late_night",
            "latenight": "late_night",
        }
        key = aliases.get(key, key)
        if key not in MODES:
            return f"Unknown lighting mode '{mode}'. Try coding, reading, or late night."
        self.mode = key
        cfg = MODES[key]
        ok = False
        errors: list[str] = []
        if self.hue_ip and self.hue_user:
            try:
                self._hue_apply(cfg)
                ok = True
            except Exception as e:
                errors.append(f"Hue: {e}")
        if self.lifx_token:
            try:
                self._lifx_apply(cfg)
                ok = True
            except Exception as e:
                errors.append(f"LIFX: {e}")
        if ok:
            return f"Lights set to {cfg['label']}."
        if not self.hue_ip and not self.lifx_token:
            return (
                f"Lighting mode '{key}' remembered ({cfg['label']}). "
                "Add hue_bridge_ip + hue_username or lifx_token in settings to control bulbs."
            )
        return f"Could not reach bulbs ({'; '.join(errors)}). Mode '{key}' stored."

    def _hue_apply(self, cfg: dict[str, Any]) -> None:
        url = f"http://{self.hue_ip}/api/{self.hue_user}/groups/0/action"
        body = json.dumps({"on": True, "bri": int(cfg["bri"]), "ct": int(cfg["ct"])}).encode()
        req = urllib.request.Request(
            url, data=body, method="PUT", headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            resp.read()

    def _lifx_apply(self, cfg: dict[str, Any]) -> None:
        # LIFX HTTP API — set all lights
        payload = json.dumps(
            {
                "power": "on",
                "brightness": min(1.0, int(cfg["bri"]) / 254.0),
                "color": f"kelvin:{int(cfg['kelvin'])}",
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.lifx.com/v1/lights/all/state",
            data=payload,
            method="PUT",
            headers={
                "Authorization": f"Bearer {self.lifx_token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            resp.read()

"""Ops HUD — owner-site map registry for the desk command hub.

Pins are ONLY the owner's locations (home, edge nodes, security events at
own sites). No stranger targets, public CCTV, ALPR, or predictive paths.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


_KINDS = frozenset({"home", "edge", "alert"})


class OpsHud:
    """Owner sites + recent home_security events as map pins."""

    def __init__(
        self,
        *,
        data_dir: Path,
        settings: Any = None,
        home_security: Any = None,
        enabled: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.settings = settings
        self.home_security = home_security
        self.enabled = bool(enabled)
        self.path = self.data_dir / "ops_sites.json"
        self._sites: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        sites: list[dict[str, Any]] = []
        # Settings list first
        try:
            raw = getattr(self.settings, "ops_sites", None) if self.settings else None
            if isinstance(raw, list):
                for item in raw:
                    pin = self._normalize(item)
                    if pin:
                        sites.append(pin)
        except Exception:
            pass
        # JSON file under DATA_DIR
        if not sites and self.path.exists():
            try:
                blob = json.loads(self.path.read_text(encoding="utf-8"))
                rows = blob if isinstance(blob, list) else blob.get("sites", [])
                for item in rows or []:
                    pin = self._normalize(item)
                    if pin:
                        sites.append(pin)
            except Exception as e:
                print(f"[ops_hud] load json: {e}")
        # Default Home pin from home_lat / home_lon
        if not sites:
            home = self._home_from_settings()
            if home:
                sites.append(home)
        self._sites = sites

    def _home_from_settings(self) -> dict[str, Any] | None:
        if self.settings is None:
            return None
        try:
            lat = getattr(self.settings, "home_lat", None)
            lon = getattr(self.settings, "home_lon", None)
            if lat is None or lon is None:
                return None
            lat_f = float(lat)
            lon_f = float(lon)
            if abs(lat_f) > 90 or abs(lon_f) > 180:
                return None
            if lat_f == 0.0 and lon_f == 0.0:
                return None
            return {
                "name": "Home",
                "lat": lat_f,
                "lon": lon_f,
                "kind": "home",
            }
        except Exception:
            return None

    @staticmethod
    def _normalize(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        try:
            name = str(item.get("name") or "").strip() or "Site"
            lat = float(item.get("lat"))
            lon = float(item.get("lon"))
            kind = str(item.get("kind") or "edge").strip().lower()
            if kind not in _KINDS:
                kind = "edge"
            if abs(lat) > 90 or abs(lon) > 180:
                return None
            return {"name": name[:80], "lat": lat, "lon": lon, "kind": kind}
        except Exception:
            return None

    def save(self) -> bool:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"sites": self._sites}, indent=2),
                encoding="utf-8",
            )
            return True
        except Exception as e:
            print(f"[ops_hud] save: {e}")
            return False

    def list_sites(self) -> list[dict[str, Any]]:
        return [dict(s) for s in self._sites]

    def add_site(
        self,
        name: str,
        lat: float,
        lon: float,
        kind: str = "edge",
    ) -> str:
        pin = self._normalize(
            {"name": name, "lat": lat, "lon": lon, "kind": kind}
        )
        if pin is None:
            return "Invalid site coordinates."
        # Replace same name
        self._sites = [s for s in self._sites if s.get("name") != pin["name"]]
        self._sites.append(pin)
        self.save()
        return f"Added {pin['kind']} site {pin['name']}."

    def events_for_map(self, limit: int = 20) -> list[dict[str, Any]]:
        """Recent home_security events as alert dots at owner's home/site coords.

        Never invents stranger target paths — events pin to owner sites only.
        """
        lim = max(1, min(int(limit or 20), 50))
        out: list[dict[str, Any]] = []
        home = next((s for s in self._sites if s.get("kind") == "home"), None)
        if home is None and self._sites:
            home = self._sites[0]
        if home is None:
            return out
        hs = self.home_security
        rows: list[dict[str, Any]] = []
        if hs is not None:
            try:
                rows = hs.recent(lim)
            except Exception:
                rows = []
        # Spread tiny offsets so stacked events remain visible
        for i, row in enumerate(reversed(rows[-lim:])):
            kind = str(row.get("kind") or "alert")
            msg = str(row.get("message") or "")[:80]
            # Skip non-security chatter if desired — keep greet light
            if kind in ("greet", "enroll") and not msg:
                continue
            jitter = (i % 5) * 0.00015
            out.append(
                {
                    "name": f"{kind}: {msg}"[:60] if msg else kind,
                    "lat": float(home["lat"]) + jitter,
                    "lon": float(home["lon"]) + jitter * 0.7,
                    "kind": "alert",
                    "ts": row.get("ts") or time.time(),
                    "iso": row.get("iso") or "",
                }
            )
        return out

    def pins(self) -> list[dict[str, Any]]:
        """Owner sites + recent security event dots for the UI."""
        pins = self.list_sites()
        pins.extend(self.events_for_map(12))
        return pins

    def status(self) -> str:
        if not self.enabled:
            return "Ops HUD disabled."
        n = len(self._sites)
        if n == 0:
            return (
                "Ops HUD online · no owner sites yet. "
                "Set home_lat / home_lon in settings, or add ops_sites."
            )
        names = ", ".join(s.get("name", "?") for s in self._sites[:5])
        ev = len(self.events_for_map(12))
        return f"Ops HUD · {n} owner site(s): {names} · {ev} recent security pin(s)."

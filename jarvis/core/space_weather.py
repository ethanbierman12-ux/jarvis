"""NOAA / space weather + ISS pass alerts."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

import requests

from jarvis.core.satellite_track import HOME_LAT, HOME_LON, fetch_iss


class SpaceWeather:
    """SWPC scales + optional G-storm backup hook."""

    def __init__(
        self,
        *,
        on_severe: Callable[[str], None] | None = None,
        poll_sec: float = 600.0,
    ) -> None:
        self.on_severe = on_severe
        self.poll_sec = poll_sec
        self._last: dict[str, Any] = {}
        self._last_alert = 0.0

    def fetch(self) -> dict[str, Any]:
        data: dict[str, Any] = {"ok": False, "scales": {}, "raw": ""}
        try:
            r = requests.get(
                "https://services.swpc.noaa.gov/products/noaa-scales.json",
                timeout=8,
            )
            r.raise_for_status()
            j = r.json()
            scales = {}
            if isinstance(j, dict):
                for k in ("R", "S", "G", "0"):
                    block = j.get(k) or j.get(str(k))
                    if isinstance(block, dict):
                        scales[k if k != "0" else "now"] = block
                    elif block is not None:
                        scales[str(k)] = block
                if not scales and "0" in j:
                    scales = j.get("0") or {}
            data = {"ok": True, "scales": scales or j, "raw": str(j)[:400]}
            self._last = data
        except Exception as e:
            data["error"] = str(e)
        return data

    def _geomagnetic_scale(self, scales: Any) -> str:
        g = None
        try:
            if isinstance(scales, dict):
                for key in ("G", "geomagnetic", "0"):
                    block = scales.get(key) or scales.get("G")
                    if isinstance(block, dict):
                        g = block.get("Scale") or block.get("scale") or block.get("Text")
                        if g is not None:
                            break
                    if isinstance(block, (int, float, str)):
                        g = block
                        break
                now = scales.get("now") or scales.get("0")
                if g is None and isinstance(now, dict):
                    g = (
                        (now.get("G") or {}).get("Scale")
                        if isinstance(now.get("G"), dict)
                        else now.get("G")
                    )
        except Exception:
            g = None
        return str(g if g is not None else "?")

    def _is_severe(self, g_s: str, scales: Any) -> bool:
        try:
            return int(str(g_s).lstrip("G").strip() or "0") >= 4
        except Exception:
            u = str(g_s).upper()
            return "G4" in u or "G5" in u or "SEVERE" in str(scales).upper()

    def poll_severe(self) -> str | None:
        """Background poll — fires on_severe at most once per hour for G4/G5."""
        d = self.fetch()
        if not d.get("ok"):
            return None
        scales = d.get("scales") or {}
        g_s = self._geomagnetic_scale(scales)
        if not self._is_severe(g_s, scales):
            return None
        if time.time() - self._last_alert <= 3600:
            return None
        self._last_alert = time.time()
        msg = f"Severe geomagnetic activity (G={g_s}). Running secure backup."
        if self.on_severe:
            try:
                self.on_severe(msg)
            except Exception:
                pass
        return msg

    def speak_brief(self, *, report_only: bool = True) -> str:
        """Spoken/status brief. Default report_only avoids double-alert with poll_severe."""
        d = self.fetch()
        if not d.get("ok"):
            return f"Space weather feed offline: {d.get('error', 'unknown')}."
        scales = d.get("scales") or {}
        g_s = self._geomagnetic_scale(scales)
        if (
            not report_only
            and self._is_severe(g_s, scales)
            and self.on_severe
            and time.time() - self._last_alert > 3600
        ):
            self._last_alert = time.time()
            try:
                self.on_severe(
                    f"Severe geomagnetic activity (G={g_s}). Running secure backup."
                )
            except Exception:
                pass
        iss = ""
        try:
            track = fetch_iss(home_lat=HOME_LAT, home_lon=HOME_LON)
            if track.get("ok"):
                iss = " " + str(track.get("summary") or "")
                if track.get("over_home"):
                    iss += " - ISS near overhead!"
        except Exception:
            pass
        return f"Space weather: geomagnetic scale about {g_s}.{iss}"

    def iss_overhead(self) -> str:
        try:
            track = fetch_iss(home_lat=HOME_LAT, home_lon=HOME_LON)
            return str(track.get("summary") or "ISS track standing by.")
        except Exception as e:
            return f"ISS tracker offline: {e}"

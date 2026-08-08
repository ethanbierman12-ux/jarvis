"""Orbital / satellite tracking helpers (ISS — HTTPS, no API key)."""

from __future__ import annotations

import math
import time
from typing import Any

import requests

# Philadelphia / Ethan default
HOME_LAT = 39.9816
HOME_LON = -75.1280
HOME_LABEL = "Philly"

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 45.0


def _cached(key: str, factory) -> dict[str, Any]:
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    data = factory()
    _CACHE[key] = (now, data)
    return data


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _iss_from_wheretheiss() -> tuple[float, float] | None:
    r = requests.get(
        "https://api.wheretheiss.at/v1/satellites/25544",
        timeout=8,
        headers={"User-Agent": "Jarvis/1.0"},
    )
    r.raise_for_status()
    j = r.json()
    return float(j["latitude"]), float(j["longitude"])


def _iss_from_open_notify() -> tuple[float, float] | None:
    r = requests.get(
        "http://api.open-notify.org/iss-now.json",
        timeout=6,
        headers={"User-Agent": "Jarvis/1.0"},
    )
    r.raise_for_status()
    pos = r.json().get("iss_position") or {}
    return float(pos["latitude"]), float(pos["longitude"])


def fetch_iss(*, home_lat: float = HOME_LAT, home_lon: float = HOME_LON) -> dict[str, Any]:
    """Live ISS position + distance from home."""

    def _load() -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": False,
            "name": "ISS",
            "lat": None,
            "lon": None,
            "altitude_km": 420,
            "speed_kms": 7.66,
            "distance_km": None,
            "over_home": False,
            "updated": time.time(),
            "summary": "ISS track standing by",
        }
        lat_lon = None
        for fetch in (_iss_from_wheretheiss, _iss_from_open_notify):
            try:
                lat_lon = fetch()
                if lat_lon:
                    break
            except Exception:
                continue
        if not lat_lon:
            return out
        lat, lon = lat_lon
        dist = _haversine_km(lat, lon, home_lat, home_lon)
        over = dist < 1500
        out.update(
            {
                "ok": True,
                "lat": lat,
                "lon": lon,
                "distance_km": dist,
                "over_home": over,
                "summary": (
                    f"ISS {lat:+.2f}, {lon:+.2f}  |  {dist:.0f} km from {HOME_LABEL}"
                    + ("  |  OVERHEAD" if over else "")
                ),
            }
        )
        return out

    return _cached("iss", _load)


def fetch_weather_brief(city: str = "Philadelphia") -> dict[str, Any]:
    """Quick weather snapshot for HUD overlays."""

    def _load() -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": False,
            "city": city or "Philadelphia",
            "temp": None,
            "condition": "",
            "humidity": None,
            "summary": "Weather standing by",
            "updated": time.time(),
        }
        try:
            from jarvis.core.weather import Weather

            wx = Weather(city=city or "Philadelphia", units="f")
            block = wx.context_block()
            temp = block.get("temp_display") or block.get("temp_f") or block.get("temp_c")
            cond = (block.get("condition") or "").strip()
            hum = block.get("humidity")
            out.update(
                {
                    "ok": True,
                    "temp": temp,
                    "condition": cond,
                    "humidity": hum,
                    "summary": f"{out['city']}  {temp}  |  {cond}"
                    + (f"  |  {hum}% RH" if hum is not None else ""),
                }
            )
        except Exception:
            pass
        return out

    return _cached(f"wx:{city or 'Philadelphia'}", _load)

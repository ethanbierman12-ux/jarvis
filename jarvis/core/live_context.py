"""Live world context — exact datetime + weather, refreshed every turn."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


class LiveContext:
    """Attaches non-hallucinated time/date/weather facts for memory + prompts."""

    def __init__(self, weather, *, timezone: str = "America/New_York") -> None:
        self.weather = weather
        self.timezone = timezone or getattr(weather, "timezone", None) or "America/New_York"
        self._last: dict[str, Any] = {}

    def _now(self) -> datetime:
        try:
            return datetime.now(ZoneInfo(self.timezone))
        except Exception:
            return datetime.now()

    def snapshot(self, *, force_weather: bool = False) -> dict[str, Any]:
        now = self._now()
        wx: dict[str, Any] = {}
        try:
            cache = getattr(self.weather, "_cache", None) or {}
            if force_weather or cache.get("temp_c") is None:
                wx = self.weather.context_block()
            else:
                wx = dict(cache)
                wx["date"] = now.strftime("%A, %B %d, %Y")
                wx["time"] = now.strftime("%H:%M:%S")
                wx["time_12"] = now.strftime("%I:%M %p").lstrip("0")
        except Exception:
            wx = {
                "city": getattr(self.weather, "city", "") or "Local",
                "temp_c": None,
                "temp_f": None,
                "temp_display": None,
                "units": "f",
                "condition": "unavailable",
            }
        units = (wx.get("units") or getattr(self.weather, "units", "f") or "f").lower()
        temp_disp = wx.get("temp_display")
        if temp_disp is None:
            if units == "f":
                temp_disp = wx.get("temp_f")
            else:
                temp_disp = wx.get("temp_c")
        data = {
            "iso": now.isoformat(timespec="seconds"),
            "date": now.strftime("%A, %B %d, %Y"),
            "time_12": now.strftime("%I:%M %p").lstrip("0"),
            "time_24": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
            "year": now.year,
            "timezone": self.timezone,
            "city": wx.get("city") or getattr(self.weather, "city", "") or "Local",
            "temp_c": wx.get("temp_c"),
            "temp_f": wx.get("temp_f"),
            "temp_display": temp_disp,
            "units": units,
            "condition": wx.get("condition") or "",
            "humidity": wx.get("humidity"),
        }
        self._last = data
        return data

    def memory_line(self) -> str:
        d = self._last or self.snapshot()
        if d.get("temp_display") is not None:
            unit = "F" if d.get("units") == "f" else "C"
            temp = f"{d['temp_display']:.0f}{unit} {d.get('condition', '')}".strip()
        else:
            temp = d.get("condition") or "weather offline"
        return (
            f"Live fact — {d['date']} · {d['time_12']} ({d.get('timezone')}) · "
            f"{d.get('city')} · {temp}."
        )

    def briefing_prefix(self) -> str:
        d = self.snapshot(force_weather=True)
        if d.get("temp_display") is not None:
            unit = "Fahrenheit" if d.get("units") == "f" else "Celsius"
            temp = f"{d['temp_display']:.0f} degrees {unit}, {d.get('condition', '')}".strip(", ")
        else:
            temp = "weather unavailable"
        return (
            f"It is {d['time_12']} on {d['date']}. "
            f"{d.get('city')}: {temp}."
        )

    def prompt_block(self) -> str:
        return (
            "REAL-TIME GROUND TRUTH (do not invent dates or weather):\n"
            f"- {self.memory_line()}"
        )

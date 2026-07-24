"""Local weather via wttr.in (no key required) + OpenWeather if configured."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests


def _now_tz(tz_name: str = "America/New_York") -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()


def c_to_f(c: float | None) -> float | None:
    if c is None:
        return None
    return float(c) * 9.0 / 5.0 + 32.0


class Weather:
    def __init__(
        self,
        city: str = "",
        api_key: str = "",
        *,
        units: str = "f",
        timezone: str = "America/New_York",
    ) -> None:
        self.city = city
        self.api_key = api_key
        self.units = (units or "f").lower()  # f | c
        self.timezone = timezone or "America/New_York"
        self._cache: dict[str, Any] = {}

    def context_block(self) -> dict[str, Any]:
        now = _now_tz(self.timezone)
        data: dict[str, Any] = {
            "city": self.city or "Local",
            "date": now.strftime("%A, %B %d, %Y"),
            "time": now.strftime("%H:%M:%S"),
            "time_12": now.strftime("%I:%M %p").lstrip("0"),
            "weekday": now.strftime("%A"),
            "temp_c": None,
            "temp_f": None,
            "temp_display": None,
            "units": self.units,
            "condition": "",
            "humidity": None,
            "feels_like": None,
            "feels_like_f": None,
            "forecast": [],
            "timezone": self.timezone,
        }
        try:
            if self.api_key and self.city:
                r = requests.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": self.city, "appid": self.api_key, "units": "metric"},
                    timeout=6,
                )
                j = r.json()
                data["temp_c"] = float(j["main"]["temp"])
                data["feels_like"] = float(j["main"].get("feels_like") or data["temp_c"])
                data["humidity"] = j["main"].get("humidity")
                data["condition"] = j["weather"][0]["description"]
            else:
                city = self.city or ""
                # Prefer Philadelphia / configured city — wttr returns F too
                r = requests.get(f"https://wttr.in/{city}?format=j1", timeout=8)
                j = r.json()
                cur = j["current_condition"][0]
                data["temp_c"] = float(cur["temp_C"])
                data["humidity"] = int(cur["humidity"])
                data["condition"] = cur["weatherDesc"][0]["value"]
                data["feels_like"] = float(cur.get("FeelsLikeC", data["temp_c"]))
                # Prefer wttr's own Fahrenheit when present (avoids rounding drift)
                if cur.get("temp_F") is not None:
                    data["temp_f"] = float(cur["temp_F"])
                if cur.get("FeelsLikeF") is not None:
                    data["feels_like_f"] = float(cur["FeelsLikeF"])
                if not self.city:
                    data["city"] = (
                        j.get("nearest_area", [{}])[0]
                        .get("areaName", [{}])[0]
                        .get("value", "Local")
                    )
                    self.city = data["city"]
                for day in j.get("weather", [])[:5]:
                    max_c = day.get("maxtempC")
                    min_c = day.get("mintempC")
                    max_f = day.get("maxtempF")
                    min_f = day.get("mintempF")
                    data["forecast"].append(
                        {
                            "date": day.get("date", ""),
                            "max_c": max_c,
                            "min_c": min_c,
                            "max_f": max_f,
                            "min_f": min_f,
                            "max": max_f if self.units == "f" and max_f is not None else max_c,
                            "min": min_f if self.units == "f" and min_f is not None else min_c,
                            "desc": day.get("hourly", [{}])[4]
                            .get("weatherDesc", [{}])[0]
                            .get("value", ""),
                        }
                    )
        except Exception as e:
            data["condition"] = f"offline ({e.__class__.__name__})"

        if data.get("temp_f") is None and data.get("temp_c") is not None:
            data["temp_f"] = c_to_f(data["temp_c"])
        if data.get("feels_like_f") is None and data.get("feels_like") is not None:
            data["feels_like_f"] = c_to_f(float(data["feels_like"]))

        if self.units == "f":
            data["temp_display"] = data.get("temp_f")
            data["unit_label"] = "F"
        else:
            data["temp_display"] = data.get("temp_c")
            data["unit_label"] = "C"

        self._cache = data
        return data

    def speak_brief(self) -> str:
        d = self.context_block()
        temp = d.get("temp_display")
        if temp is None:
            return f"I couldn't reach weather for {d.get('city')}."
        unit = "Fahrenheit" if d.get("units") == "f" else "Celsius"
        return (
            f"It's {temp:.0f} degrees {unit} in {d['city']} on {d.get('date')}, "
            f"{d.get('condition', '').lower()}."
        )

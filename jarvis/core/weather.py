"""Local weather via wttr.in (no key required) + OpenWeather if configured."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests


class Weather:
    def __init__(self, city: str = "", api_key: str = "") -> None:
        self.city = city
        self.api_key = api_key
        self._cache: dict[str, Any] = {}

    def context_block(self) -> dict[str, Any]:
        now = datetime.now()
        data = {
            "city": self.city or "Local",
            "date": now.strftime("%A, %B %d"),
            "time": now.strftime("%H:%M:%S"),
            "temp_c": None,
            "condition": "",
            "humidity": None,
            "feels_like": None,
            "forecast": [],
        }
        try:
            if self.api_key and self.city:
                r = requests.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": self.city, "appid": self.api_key, "units": "metric"},
                    timeout=6,
                )
                j = r.json()
                data["temp_c"] = j["main"]["temp"]
                data["feels_like"] = j["main"].get("feels_like")
                data["humidity"] = j["main"].get("humidity")
                data["condition"] = j["weather"][0]["description"]
            else:
                city = self.city or ""
                r = requests.get(f"https://wttr.in/{city}?format=j1", timeout=6)
                j = r.json()
                cur = j["current_condition"][0]
                data["temp_c"] = float(cur["temp_C"])
                data["humidity"] = int(cur["humidity"])
                data["condition"] = cur["weatherDesc"][0]["value"]
                data["feels_like"] = float(cur.get("FeelsLikeC", data["temp_c"]))
                if not self.city:
                    data["city"] = j.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", "Local")
                    self.city = data["city"]
                # 3-day forecast strip
                for day in j.get("weather", [])[:5]:
                    data["forecast"].append(
                        {
                            "date": day.get("date", ""),
                            "max": day.get("maxtempC"),
                            "min": day.get("mintempC"),
                            "desc": day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", ""),
                        }
                    )
        except Exception as e:
            data["condition"] = f"offline ({e.__class__.__name__})"
        self._cache = data
        return data

    def speak_brief(self) -> str:
        d = self.context_block()
        if d.get("temp_c") is None:
            return f"I couldn't reach weather for {d.get('city')}."
        return (
            f"It's {d['temp_c']:.0f} degrees in {d['city']}, "
            f"{d.get('condition', '').lower()}."
        )

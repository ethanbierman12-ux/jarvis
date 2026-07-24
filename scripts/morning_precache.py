"""Precompute morning standup text for 6AM Task Scheduler."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.config import Settings
from jarvis.core.daily_brief import DailyBrief
from jarvis.core.weather import Weather


def main() -> int:
    settings = Settings.load()
    brief = DailyBrief()
    wx = ""
    try:
        wx = Weather(city=settings.city, api_key=settings.openweather_api_key).speak_brief()
    except Exception:
        pass
    weather_line = f"Weather: {wx}." if wx else ""
    text = brief.morning_standup(weather_line=weather_line, open_inbox=False)
    out = ROOT / "jarvis" / "data" / "morning_standup.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"[morning] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

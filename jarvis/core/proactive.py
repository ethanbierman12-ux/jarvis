"""Return-to-desk brief + weather umbrella nudge + sequence suggestions."""

from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Deque, Optional

from jarvis.config import DATA_DIR

SEQ_PATH = DATA_DIR / "command_sequences.json"


class ReturnBrief:
    """Build a 'what did I miss' summary when user returns."""

    def __init__(self, brief=None, weather=None) -> None:
        self.brief = brief
        self.weather = weather
        self._away_since: float | None = None
        self._last_return_brief = 0.0

    def mark_away(self) -> None:
        if self._away_since is None:
            self._away_since = time.time()

    def mark_present(self) -> Optional[str]:
        if self._away_since is None:
            return None
        away = time.time() - self._away_since
        self._away_since = None
        if away < 90:  # ignore brief glances
            return None
        if time.time() - self._last_return_brief < 120:
            return None
        self._last_return_brief = time.time()
        mins = int(away / 60)
        parts = [f"Welcome back — you were away about {mins} minute{'s' if mins != 1 else ''}."]
        if self.brief:
            try:
                parts.append(self.brief.schedule_only())
            except Exception:
                pass
            try:
                tasks = self.brief._tasks_line()
                if tasks:
                    parts.append(tasks)
            except Exception:
                pass
        parts.append("I opened nothing noisy — say 'check email' if you want the inbox.")
        return " ".join(parts)


class WeatherGuard:
    def __init__(self, weather) -> None:
        self.weather = weather
        self._warned_day = ""

    def morning_check(self) -> Optional[str]:
        day = datetime.now().strftime("%Y-%m-%d")
        if self._warned_day == day:
            return None
        hour = datetime.now().hour
        if hour < 5 or hour > 11:
            return None
        try:
            ctx = self.weather.context_block()
        except Exception:
            return None
        text = json.dumps(ctx).lower()
        desc = str(ctx.get("condition") or ctx.get("description") or ctx.get("summary") or "").lower()
        rainy = any(
            k in text or k in desc
            for k in ("rain", "storm", "drizzle", "thunder", "precip")
        )
        if rainy:
            self._warned_day = day
            return (
                "Sir, rain is expected — take the umbrella, and leave about ten minutes earlier. "
                "If any windows are open, close them before the house becomes a terrarium."
            )
        # Mild heat / stale-air nudge (no open-window sensor required)
        try:
            temp = ctx.get("temp") or ctx.get("temperature") or ctx.get("feels_like")
            if temp is not None and float(temp) >= 82 and hour >= 7:
                self._warned_day = day
                return (
                    "It's already warm out, Sir. Crack a window now, or enjoy the sauna you call an office."
                )
        except Exception:
            pass
        return None


class SequenceLearner:
    """Learn repeated 3–4 command chains → suggest quick action."""

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._recent: Deque[tuple[float, str]] = deque(maxlen=12)
        self._counts: dict[str, int] = {}
        self._load()
        self.pending_suggestion: Optional[str] = None

    def _load(self) -> None:
        if SEQ_PATH.exists():
            try:
                self._counts = json.loads(SEQ_PATH.read_text(encoding="utf-8"))
            except Exception:
                self._counts = {}

    def _save(self) -> None:
        SEQ_PATH.write_text(json.dumps(self._counts, indent=2), encoding="utf-8")

    def observe(self, cmd: str) -> Optional[str]:
        cmd = (cmd or "").strip().lower()[:60]
        if not cmd:
            return None
        now = time.time()
        self._recent.append((now, cmd))
        # Window of last 4 cmds within 3 minutes
        window = [c for t, c in self._recent if now - t < 180]
        if len(window) >= 3:
            key = " → ".join(window[-4:])
            self._counts[key] = self._counts.get(key, 0) + 1
            self._save()
            if self._counts[key] >= 3 and "work" not in key:
                self.pending_suggestion = key
                return key
        return None

    def best_workspace_hint(self) -> Optional[str]:
        if not self._counts:
            return "open chrome → open code → play music"
        return max(self._counts.items(), key=lambda kv: kv[1])[0]

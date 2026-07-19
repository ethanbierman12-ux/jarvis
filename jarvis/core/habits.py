"""Habits + day prioritization from logged work patterns."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

HABITS_PATH = DATA_DIR / "habits.json"
TASKS_PATH = DATA_DIR / "tasks.json"


class HabitEngine:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not HABITS_PATH.exists():
            HABITS_PATH.write_text(
                json.dumps({"events": [], "priorities": []}, indent=2),
                encoding="utf-8",
            )

    def log(self, kind: str, detail: str = "") -> None:
        data = self._load()
        data.setdefault("events", []).append(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "hour": datetime.now().hour,
                "weekday": datetime.now().strftime("%A"),
                "kind": kind,
                "detail": detail[:120],
            }
        )
        # Keep last 500
        data["events"] = data["events"][-500:]
        self._save(data)

    def tell_me_about_my_day(self, daily_brief_text: str = "") -> str:
        data = self._load()
        events = data.get("events") or []
        hour = datetime.now().hour
        weekday = datetime.now().strftime("%A")

        # Hour-of-day habits
        same_day = [e for e in events if e.get("weekday") == weekday]
        kinds = Counter(e.get("kind", "other") for e in same_day[-80:])
        hour_kinds = Counter(
            e.get("kind", "other") for e in events if int(e.get("hour", -1)) == hour
        )

        tasks = self._open_tasks()
        parts: list[str] = [
            f"Here is your day read for {weekday}."
        ]

        if daily_brief_text:
            parts.append(daily_brief_text)

        if tasks:
            # Prioritize: unfinished tasks first, then habit-based suggestion
            top = tasks[:3]
            parts.append("Priority stack: " + "; ".join(top) + ".")
        else:
            parts.append("No open tasks on file — add some with 'add task …'.")

        if hour_kinds:
            usual = hour_kinds.most_common(1)[0][0]
            parts.append(
                f"Around this hour you usually lean toward {usual.replace('_', ' ')}."
            )
        elif kinds:
            usual = kinds.most_common(1)[0][0]
            parts.append(
                f"On {weekday}s your pattern skews toward {usual.replace('_', ' ')}."
            )

        suggestion = self._suggest(hour, tasks, hour_kinds)
        if suggestion:
            parts.append(suggestion)

        return " ".join(parts)

    def _suggest(self, hour: int, tasks: list[str], hour_kinds: Counter) -> str:
        if hour < 11 and tasks:
            return f"Suggested focus now: {tasks[0]}."
        if 11 <= hour < 14:
            return "Suggested: clear mail and a short lunch break before the afternoon block."
        if 14 <= hour < 18 and tasks:
            idx = min(1, len(tasks) - 1)
            return f"Afternoon push — tackle: {tasks[idx]}."
        if hour >= 18:
            return "Evening — wrap unfinished tasks or switch to lighter review work."
        if hour_kinds:
            k = hour_kinds.most_common(1)[0][0]
            return f"Based on your pattern, start with {k.replace('_', ' ')}."
        return "Start with your hardest task while energy is high."

    def _open_tasks(self) -> list[str]:
        try:
            raw = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
            return list(raw.get("open") or [])
        except Exception:
            return []

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(HABITS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"events": [], "priorities": []}

    def _save(self, data: dict[str, Any]) -> None:
        HABITS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

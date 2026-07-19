"""Proactive suggestions — HUD chip + spoken tips based on context."""

from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Any, Optional


class SuggestionEngine:
    def __init__(self, settings, brief=None, habits=None, sequences=None, weather=None) -> None:
        self.settings = settings
        self.brief = brief
        self.habits = habits
        self.sequences = sequences
        self.weather = weather
        self._last_offer = 0.0
        self._last_spoken = 0.0
        self._cooldown = 90.0  # seconds between HUD offers
        self.pending_cmd: str = ""
        self._pending_at: float = 0.0

    def pending_fresh(self, max_age: float = 25.0) -> bool:
        if not self.pending_cmd:
            return False
        return (time.time() - self._pending_at) <= max_age

    def now_suggestion(self, *, force: bool = False) -> Optional[dict[str, str]]:
        """
        Returns {title, detail, cmd} or None.
        title — short chip text
        detail — longer spoken line
        cmd — utterance to run if user says yes / clicks
        """
        now = time.time()
        if not force and now - self._last_offer < self._cooldown:
            return None

        hour = datetime.now().hour
        name = self.settings.user_name or "Sir"
        ideas: list[dict[str, str]] = []

        # Open tasks
        tasks: list[str] = []
        if self.brief:
            try:
                raw = self.brief._load_tasks()
                tasks = list(raw.get("open") or [])
            except Exception:
                tasks = []
        if tasks:
            ideas.append(
                {
                    "title": f"Work on: {tasks[0][:40]}?",
                    "detail": f"{name}, your top open task is '{tasks[0]}'. Want to start work mode?",
                    "cmd": "i'm starting work",
                }
            )

        # Time-of-day
        if 5 <= hour < 10:
            ideas.append(
                {
                    "title": "Set up your morning workspace?",
                    "detail": f"Good morning, {name}. Shall I open your project, IDE, and mail?",
                    "cmd": "set up my morning workspace",
                }
            )
            ideas.append(
                {
                    "title": "Want today's schedule?",
                    "detail": "I can brief your calendar and tasks.",
                    "cmd": "what's my schedule",
                }
            )
        elif 11 <= hour < 14:
            ideas.append(
                {
                    "title": "Clear inbox or take a stretch?",
                    "detail": "Midday check — want me to open mail, or play calm audio for a break?",
                    "cmd": "check email",
                }
            )
        elif 14 <= hour < 18:
            ideas.append(
                {
                    "title": "Afternoon focus playlist?",
                    "detail": "Want your focus playlist while you push through the afternoon?",
                    "cmd": "play my focus playlist",
                }
            )
            ideas.append(
                {
                    "title": "Boost mode for heavy work?",
                    "detail": "I can suspend background apps so your IDE runs smoother.",
                    "cmd": "boost mode",
                }
            )
        elif hour >= 20 or hour < 5:
            ideas.append(
                {
                    "title": "Late night lighting + recap?",
                    "detail": "Dim the lights and do a quick Wins & Growth recap before you stop?",
                    "cmd": "late night mode",
                }
            )
            ideas.append(
                {
                    "title": "Daily recap before bed?",
                    "detail": f"{name}, want a short end-of-day summary?",
                    "cmd": "daily recap",
                }
            )

        # Weather rain
        if self.weather and 5 <= hour <= 11:
            try:
                ctx = self.weather.context_block()
                blob = str(ctx).lower()
                if any(k in blob for k in ("rain", "storm", "drizzle")):
                    ideas.append(
                        {
                            "title": "Rain later — leave earlier?",
                            "detail": "Rain is likely. Don't forget an umbrella — leave about ten minutes early.",
                            "cmd": "what's the weather",
                        }
                    )
            except Exception:
                pass

        # Learned sequence
        if self.sequences:
            hint = self.sequences.best_workspace_hint()
            if hint and "→" in hint:
                ideas.append(
                    {
                        "title": "Repeat your usual setup?",
                        "detail": f"You often do: {hint}. Shall I run your morning workspace?",
                        "cmd": "set up my morning workspace",
                    }
                )

        # Always-useful fallbacks
        ideas.extend(
            [
                {
                    "title": "Scan something with the camera?",
                    "detail": "Hold an item in the green box and say scan — I'll identify it.",
                    "cmd": "open camera",
                },
                {
                    "title": "Take a voice note?",
                    "detail": "Say take notes and talk — I'll save it when you say done.",
                    "cmd": "take notes",
                },
                {
                    "title": "What did I miss while away?",
                    "detail": "I can summarize schedule and tasks from your absence.",
                    "cmd": "what did i miss",
                },
            ]
        )

        pick = random.choice(ideas)
        self._last_offer = now
        self.pending_cmd = pick["cmd"]
        self._pending_at = now
        return pick

    def after_command(self, command: str, reply: str) -> Optional[dict[str, str]]:
        """Light follow-up suggestion after certain actions."""
        t = (command or "").lower()
        now = time.time()
        if now - self._last_offer < 45:
            return None

        follow: dict[str, str] | None = None
        if "scan" in t or "search for this" in t:
            follow = {
                "title": "Save this to visual memory?",
                "detail": "Want me to remember this object? Say remember this as …",
                "cmd": "remember this as item",
            }
        elif "starting work" in t or "workspace" in t:
            follow = {
                "title": "Focus playlist while you work?",
                "detail": "Shall I play your focus playlist?",
                "cmd": "play my focus playlist",
            }
        elif "schedule" in t or "brief" in t:
            follow = {
                "title": "Start work mode now?",
                "detail": "Want me to open your project and IDE?",
                "cmd": "i'm starting work",
            }
        elif "play" in t and "music" in t:
            follow = {
                "title": "Coding lights?",
                "detail": "I can switch to coding-mode lighting.",
                "cmd": "coding mode",
            }
        elif "note" in t:
            follow = {
                "title": "Add a task from that note?",
                "detail": "Say add task … if you want it on your list.",
                "cmd": "show notes",
            }
        elif "weather" in t:
            follow = {
                "title": "Check today's schedule?",
                "detail": "Want your calendar next?",
                "cmd": "what's my schedule",
            }

        if follow:
            self._last_offer = now
            self.pending_cmd = follow["cmd"]
            self._pending_at = now
        return follow

    def speak_ok(self) -> bool:
        """Don't verbally spam — at most every 4 minutes unless asked."""
        now = time.time()
        if now - self._last_spoken < 240:
            return False
        self._last_spoken = now
        return True

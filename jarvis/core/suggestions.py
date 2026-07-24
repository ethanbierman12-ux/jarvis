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
        self._cooldown = 180.0  # seconds between ambient HUD offers
        self._post_accept_cooldown = 300.0  # 5 min calm after yes/accept
        self._suppress_until = 0.0
        self._last_tip_cmd = ""
        self.pending_cmd: str = ""
        self._pending_at: float = 0.0

    @property
    def enabled(self) -> bool:
        try:
            if hasattr(self.settings, "suggestions_enabled"):
                return bool(getattr(self.settings, "suggestions_enabled", True))
        except Exception:
            pass
        try:
            return bool(getattr(self.settings, "proactive_enabled", True))
        except Exception:
            return True

    def set_enabled(self, on: bool) -> str:
        on = bool(on)
        try:
            self.settings.suggestions_enabled = on
            if hasattr(self.settings, "save"):
                self.settings.save()
        except Exception:
            pass
        if not on:
            self.clear_pending()
            self._suppress_until = time.time() + 86400.0
        else:
            self._suppress_until = 0.0
        return "Suggestions on." if on else "Suggestions off. Say suggestions on to restore."

    def clear_pending(self) -> None:
        self.pending_cmd = ""
        self._pending_at = 0.0

    def pending_fresh(self, max_age: float = 45.0) -> bool:
        if not self.pending_cmd:
            return False
        return (time.time() - self._pending_at) <= max_age

    def suppressed(self) -> bool:
        return time.time() < self._suppress_until

    def accept(self) -> str:
        """
        Clear pending and start post-accept cooldown.
        Returns the command to run (empty if nothing pending).
        """
        cmd = (self.pending_cmd or "").strip()
        self.clear_pending()
        now = time.time()
        self._suppress_until = now + self._post_accept_cooldown
        self._last_offer = now  # also blocks ambient offers
        if cmd:
            self._last_tip_cmd = cmd.lower()
        return cmd

    def can_offer(self, *, force: bool = False) -> bool:
        if not self.enabled:
            return False
        if self.suppressed() and not force:
            return False
        now = time.time()
        if not force and now - self._last_offer < self._cooldown:
            return False
        return True

    def now_suggestion(self, *, force: bool = False) -> Optional[dict[str, str]]:
        """
        Returns {title, detail, cmd} or None.
        title — short chip text
        detail — longer spoken line
        cmd — utterance to run if user says yes / clicks
        """
        if not self.can_offer(force=force):
            return None

        now = time.time()
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

        # Dedupe: don't re-offer the same cmd we just ran/accepted
        last = (self._last_tip_cmd or "").lower()
        filtered = [i for i in ideas if (i.get("cmd") or "").lower() != last]
        if not filtered:
            filtered = ideas

        pick = random.choice(filtered)
        self._last_offer = now
        self.pending_cmd = pick["cmd"]
        self._pending_at = now
        self._last_tip_cmd = (pick["cmd"] or "").lower()
        return pick

    def after_command(self, command: str, reply: str) -> Optional[dict[str, str]]:
        """Light follow-up — never chains immediately after accept / during suppress."""
        if not self.enabled or self.suppressed():
            return None
        t = (command or "").lower()
        now = time.time()
        # Longer gap after any offer (incl. ambient) — was 45s, felt like a cascade
        if now - self._last_offer < 120:
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
            cmd = (follow.get("cmd") or "").lower()
            if cmd and cmd == (self._last_tip_cmd or ""):
                return None
            self._last_offer = now
            self.pending_cmd = follow["cmd"]
            self._pending_at = now
            self._last_tip_cmd = cmd
        return follow

    def speak_ok(self) -> bool:
        """Don't verbally spam — at most every 6 minutes unless asked."""
        if not self.enabled or self.suppressed():
            return False
        now = time.time()
        if now - self._last_spoken < 360:
            return False
        self._last_spoken = now
        return True

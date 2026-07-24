"""Proactive interventions — CPU, late night, idle stare heuristics."""

from __future__ import annotations

import time
from typing import Callable


class ProactiveAgent:
    """
    Speaks up occasionally from system triggers (never spams).
    on_say(text) must be thread-safe or scheduled onto UI/voice.
    """

    def __init__(
        self,
        *,
        telemetry_fn: Callable[[], object],
        on_say: Callable[[str], None],
        on_alert: Callable[[str], None] | None = None,
        mood=None,
    ) -> None:
        self._telemetry = telemetry_fn
        self._say = on_say
        self._alert = on_alert or (lambda _t: None)
        self.mood = mood
        self._last: dict[str, float] = {}
        self._enabled = True
        self._idle_since = time.time()

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)

    def note_activity(self) -> None:
        self._idle_since = time.time()

    def _cooldown(self, key: str, sec: float) -> bool:
        now = time.time()
        if now - self._last.get(key, 0) < sec:
            return False
        self._last[key] = now
        return True

    def tick(self) -> None:
        if not self._enabled:
            return
        try:
            tel = self._telemetry()
            cpu = float(getattr(tel, "cpu", 0) or 0)
            if self.mood:
                try:
                    self.mood.observe_cpu(cpu)
                except Exception:
                    pass
            hour = time.localtime().tm_hour

            if cpu >= 90 and self._cooldown("cpu", 900):
                msg = (
                    "Sir, CPU is pinned above ninety percent. "
                    "Shall I kill background chrome, or leave it?"
                )
                self._alert("Proactive · high CPU")
                self._say(msg)
                return

            if hour >= 1 and hour < 5 and self._cooldown("late", 3600):
                msg = (
                    "Rather late for heroics. Hydration and a save wouldn't go amiss."
                )
                self._alert("Proactive · late night")
                self._say(msg)
                return

            idle = time.time() - self._idle_since
            if idle >= 7200 and self._cooldown("stare", 1800):
                msg = (
                    "You've been heads-down for about two hours. "
                    "I suggest a stretch — or I can queue a brief status."
                )
                self._alert("Proactive · long session")
                self._say(msg)
                return

            if self.mood and self._cooldown("followup", 2400):
                hint = self.mood.follow_up_hint()
                if hint:
                    self._alert("Proactive · follow-up")
                    self._say(hint)
        except Exception:
            pass

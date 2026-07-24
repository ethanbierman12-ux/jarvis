"""Proactive interventions — CPU healer, late night, writing check-ins."""

from __future__ import annotations

import time
from typing import Callable


class ProactiveAgent:
    """
    Speaks up occasionally from system triggers (never spams).
    on_say(text) must be thread-safe or scheduled onto UI/voice.
    on_healer(hog) optional — PC healer multi-choice path.
    """

    def __init__(
        self,
        *,
        telemetry_fn: Callable[[], object],
        on_say: Callable[[str], None],
        on_alert: Callable[[str], None] | None = None,
        on_healer: Callable[[object], None] | None = None,
        on_writing_break: Callable[[], None] | None = None,
        mood=None,
        healer=None,
    ) -> None:
        self._telemetry = telemetry_fn
        self._say = on_say
        self._alert = on_alert or (lambda _t: None)
        self._on_healer = on_healer
        self._on_writing = on_writing_break
        self.mood = mood
        self.healer = healer
        self._last: dict[str, float] = {}
        self._enabled = True
        self._idle_since = time.time()
        self._writing_since = 0.0
        self._in_writing = False

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)

    def note_activity(self) -> None:
        self._idle_since = time.time()

    def note_writing(self, active: bool = True) -> None:
        """Call when active window looks like docs / IDE writing."""
        if active:
            if not self._in_writing:
                self._writing_since = time.time()
            self._in_writing = True
            self.note_activity()
        else:
            self._in_writing = False
            self._writing_since = 0.0

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
            mem = float(getattr(tel, "memory", 0) or 0)
            if self.mood:
                try:
                    self.mood.observe_cpu(cpu)
                except Exception:
                    pass
            hour = time.localtime().tm_hour

            # PC healer — structured intervene
            if self.healer and (cpu >= 85 or mem >= 90) and self._cooldown("healer", 600):
                hog = self.healer.should_intervene(system_cpu=cpu, system_mem=mem)
                if hog is not None:
                    self._alert(f"Healer · {hog.name} {hog.cpu:.0f}%")
                    if self._on_healer:
                        self._on_healer(hog)
                    else:
                        self._say(
                            f"Sir, {hog.name} is using {hog.cpu:.0f} percent CPU. "
                            "Say healer kill to terminate it, or healer ignore."
                        )
                    return

            if cpu >= 90 and self._cooldown("cpu", 900):
                msg = (
                    "Sir, CPU is pinned above ninety percent. "
                    "Say healer status to inspect, or healer kill top process."
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

            # Conceptual check-in: long writing session
            if (
                self._in_writing
                and self._writing_since
                and (time.time() - self._writing_since) >= 5400
                and self._cooldown("writing", 1800)
            ):
                self._alert("Proactive · writing break")
                if self._on_writing:
                    self._on_writing()
                else:
                    self._say(
                        "You've been writing for a while. "
                        "Should I summarize your progress, or fetch a coffee update?"
                    )
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

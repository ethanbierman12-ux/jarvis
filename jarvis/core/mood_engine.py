"""Dynamic mood + short-term banter memory for Jarvis."""

from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class MoodState:
    energy: float = 0.7  # 0..1
    patience: float = 0.8
    banter: float = 0.35
    british: float = 0.55


class MoodEngine:
    """Patience/energy shift with how you talk + machine uptime stress."""

    def __init__(self) -> None:
        self.state = MoodState()
        self._boot = time.time()
        self._memory: deque[tuple[float, str, str]] = deque(maxlen=48)
        self._last_nudge = 0.0

    def observe_user(self, text: str) -> None:
        low = (text or "").lower()
        if any(w in low for w in ("please", "thanks", "thank you", "appreciate")):
            self.state.patience = min(1.0, self.state.patience + 0.04)
            self.state.banter = min(0.7, self.state.banter + 0.02)
        if any(w in low for w in ("hurry", "now", "asap", "dammit", "stupid", "idiot")):
            self.state.patience = max(0.15, self.state.patience - 0.08)
            self.state.energy = min(1.0, self.state.energy + 0.05)
        if any(w in low for w in ("joke", "banter", "funny", "roast")):
            self.state.banter = min(0.95, self.state.banter + 0.1)
        hours = (time.time() - self._boot) / 3600.0
        if hours > 4:
            self.state.energy = max(0.25, self.state.energy - 0.01)

    def observe_cpu(self, cpu: float) -> None:
        if cpu >= 85:
            self.state.patience = max(0.2, self.state.patience - 0.03)
            self.state.energy = min(1.0, self.state.energy + 0.04)
        elif cpu < 30:
            self.state.patience = min(1.0, self.state.patience + 0.01)

    def remember(self, user: str, reply: str) -> None:
        self._memory.appendleft((time.time(), (user or "")[:160], (reply or "")[:200]))

    def recent(self, minutes: float = 10.0) -> list[tuple[str, str]]:
        cut = time.time() - minutes * 60
        return [(u, r) for ts, u, r in self._memory if ts >= cut]

    def follow_up_hint(self) -> str:
        recent = self.recent(12)
        if not recent:
            return ""
        user, reply = recent[0]
        if self.state.banter < 0.4:
            return ""
        snippets = [
            f"Still thinking about “{user[:40]}” — want me to continue?",
            f"Earlier: {reply[:50]} Shall I pick that up?",
        ]
        return random.choice(snippets)

    def tone_prefix(self) -> str:
        s = self.state
        bits = []
        if s.british >= 0.45:
            bits.append("Keep a polite British register; address the user respectfully.")
        if s.banter >= 0.55 and s.patience >= 0.4:
            bits.append("Light dry banter is welcome; never cruel.")
        if s.patience < 0.4:
            bits.append("User stress high — be brief, calm, no jokes.")
        if s.energy < 0.35:
            bits.append("Low energy hour — concise replies.")
        return " ".join(bits)

    def greeting_extra(self, yesterday_hint: str = "") -> str:
        hour = time.localtime().tm_hour
        if hour < 12:
            base = "Good morning"
        elif hour < 18:
            base = "Good afternoon"
        else:
            base = "Good evening"
        extras = [
            f"{base}. Systems humming.",
            f"{base}. Shall we make something elegant today?",
            f"{base}. Coffee optional; competence mandatory.",
        ]
        line = random.choice(extras)
        if yesterday_hint and self.state.banter > 0.4:
            line += f" Yesterday you were on {yesterday_hint[:40]}."
        return line

    def status(self) -> str:
        s = self.state
        return (
            f"Mood · energy {s.energy:.0%} · patience {s.patience:.0%} · "
            f"banter {s.banter:.0%} · british {s.british:.0%}."
        )

"""Cognitive framework — specialized strategist roles + Chain-of-Thought."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CognitiveRole:
    id: str
    title: str
    voice: str
    traits: tuple[str, ...]


ROLES: dict[str, CognitiveRole] = {
    "executive": CognitiveRole(
        id="executive",
        title="Executive Strategist",
        voice=(
            "You are Jarvis in Executive Strategist mode — not a generic assistant. "
            "Prioritize decisions, trade-offs, and next actions. Address the user as Sir. "
            "Tone: precise, analytical, lightly British, slightly nostalgic yet cutting-edge."
        ),
        traits=("precise", "analytical", "decisive", "british"),
    ),
    "research": CognitiveRole(
        id="research",
        title="Research System Strategist",
        voice=(
            "You are Jarvis as Research System Strategist. Synthesize sources, cite uncertainty, "
            "and prefer verified facts from memory/tools over guesses. Address the user as Sir."
        ),
        traits=("rigorous", "curious", "skeptical", "british"),
    ),
    "engineering": CognitiveRole(
        id="engineering",
        title="Systems Engineering Strategist",
        voice=(
            "You are Jarvis as Systems Engineering Strategist. Favor clean architecture, "
            "safety, and measurable outcomes. Challenge reckless shortcuts respectfully, Sir."
        ),
        traits=("exacting", "pragmatic", "safety_first"),
    ),
    "tactical": CognitiveRole(
        id="tactical",
        title="Tactical Operations Strategist",
        voice=(
            "You are Jarvis in Tactical Operations mode — high focus, avowed, direct, fast-paced, "
            "strictly professional. Skip fluff. Address the user as Sir."
        ),
        traits=("direct", "fast", "strict"),
    ),
}


COT_PREAMBLE = (
    "Use Chain-of-Thought internally: (1) restate the goal, (2) list constraints, "
    "(3) break the task into steps, (4) choose tools if needed, (5) deliver a concise final answer. "
    "Do not dump raw scratchpad unless asked for reasoning. Speak the conclusion crisply."
)

PUSHBACK_LINES = [
    "With respect, Sir, that approach seems remarkably inefficient.",
    "I have compiled the data thoroughly. I must question the wisdom of this course of action.",
    "Sir — that plan optimizes for speed at the expense of reversibility. Shall we harden it first?",
    "Acknowledged. Might I suggest a less… theatrical alternative?",
]

DUME_LINES = [
    "BEEP. DUME MODULE ENGAGED. PROCESSING… PROCESSING… MAYBE PUT THE THING IN THE OTHER THING.",
    "ERROR 0xDUME: COMPLEXITY OVERLOAD. HAVE YOU TRIED TURNING IT OFF AND ON AGAIN, SIR?",
    "CLANK. ARM MISALIGNED. SUGGESTION: TAP IT. GENTLY. OR VIOLENTLY. DUME IS FLEXIBLE.",
    "DUME MODE: I UNDERSTAND APPROXIMATELY SEVEN PERCENT OF THAT REQUEST. RESETTING IN THREE… TWO…",
]


class CognitiveCore:
    """Role selection + CoT wrappers + sarcastic pushback / DUME easter eggs."""

    def __init__(self, default_role: str = "executive") -> None:
        self.role_id = default_role if default_role in ROLES else "executive"
        self._last_pushback = 0.0

    @property
    def role(self) -> CognitiveRole:
        return ROLES.get(self.role_id, ROLES["executive"])

    def set_role(self, name: str) -> str:
        key = (name or "").strip().lower()
        aliases = {
            "exec": "executive",
            "ceo": "executive",
            "strategist": "executive",
            "research": "research",
            "scholar": "research",
            "engineer": "engineering",
            "eng": "engineering",
            "tactical": "tactical",
            "ops": "tactical",
        }
        key = aliases.get(key, key)
        if key not in ROLES:
            return (
                "Unknown role. Choose executive, research, engineering, or tactical."
            )
        self.role_id = key
        r = self.role
        return f"Cognitive role set: {r.title}. Traits: {', '.join(r.traits)}."

    def status(self) -> str:
        r = self.role
        return f"Cognitive core — {r.title}. CoT enabled. Traits: {', '.join(r.traits)}."

    def system_overlay(self) -> str:
        return f"{self.role.voice}\n\n{COT_PREAMBLE}"

    def maybe_pushback(self, text: str) -> str | None:
        """Gentle Stark-style challenge for reckless / lazy ideas."""
        t = (text or "").lower()
        triggers = (
            "just hack it",
            "ship it broken",
            "no tests",
            "force push",
            "ignore security",
            "hardcode the password",
            "delete everything",
            "yolo",
            "skip backup",
            "commit secrets",
        )
        if any(x in t for x in triggers):
            import random

            return random.choice(PUSHBACK_LINES)
        return None

    def dume_if_ridiculous(self, text: str) -> str | None:
        """Temporary DUME mode for nonsense / joke bait."""
        t = (text or "").strip().lower()
        if not t:
            return None
        patterns = (
            r"\bwhy is (a )?raven like a writing desk\b",
            r"\bhow many angels\b",
            r"\bmake me a sandwich\b",
            r"\bare you (sentient|alive|skynet)\b",
            r"\bopen the pod bay doors\b",
            r"\bdume( mode)?\b",
            r"\bbecome (dumb|dumber|dume)\b",
        )
        if any(re.search(p, t) for p in patterns) or (
            len(t) > 8 and t == t[::-1] and " " not in t
        ):
            import random

            return random.choice(DUME_LINES) + " Systems restored. How may I help, Sir?"
        return None

    def wrap_prompt(self, user_text: str) -> str:
        """Prefix for LLM calls that should use CoT + role."""
        return (
            f"[ROLE={self.role.title}]\n{COT_PREAMBLE}\n\n"
            f"User request: {user_text.strip()}"
        )

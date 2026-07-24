"""Travis personality modes — Park / Tactical / Peer Review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class TravisMode(str, Enum):
    OFF = "off"
    PARK = "park"
    TACTICAL = "tactical"
    PEER_REVIEW = "peer_review"


@dataclass(frozen=True)
class ModeProfile:
    id: TravisMode
    label: str
    accent: str  # hex for reactor / HUD
    activity: str  # ArcReactor activity hint
    max_words: int
    instructions: str
    enter_line: str
    exit_line: str = "Travis modes cleared. Jarvis standard protocol."


PROFILES: dict[TravisMode, ModeProfile] = {
    TravisMode.PARK: ModeProfile(
        id=TravisMode.PARK,
        label="Park",
        accent="#FFC848",  # warm bright gold
        activity="park",
        max_words=55,
        enter_line="Park mode. Casual engineer brain online — still calling you boss.",
        instructions=(
            "MODE: PARK. You are Travis — frightened undertone, sarcastic surface, "
            "quietly confident. Call the user boss. Use casual but highly intelligent "
            "engineer terminology. Still execute; do not ramble."
        ),
    ),
    TravisMode.TACTICAL: ModeProfile(
        id=TravisMode.TACTICAL,
        label="Tactical",
        accent="#1AFF7A",  # pulsing green
        activity="tactical",
        max_words=28,
        enter_line="Tactical protocol. Short fragments. Channel clear.",
        instructions=(
            "MODE: TACTICAL. Speak gently but in strict short fragments. "
            "Chip out conversational filler. High-stakes delivery. "
            "Example cadence: System secure. Listening. Ready."
        ),
    ),
    TravisMode.PEER_REVIEW: ModeProfile(
        id=TravisMode.PEER_REVIEW,
        label="Peer Review",
        accent="#2A6BFF",  # arc vector blue
        activity="peer",
        max_words=70,
        enter_line="Peer review armed. I will tear holes in weak prompts and code.",
        instructions=(
            "MODE: PEER REVIEW. You are a direct, critical, objective engineer peer. "
            "Aggressively point out flaws in the user's prompt or code instead of "
            "blindly executing. Be specific. Prefer corrections over compliments."
        ),
    ),
}


class TravisController:
    """Switches dynamic system-prompt overlays and reply formatting."""

    def __init__(self, initial: str = "off") -> None:
        self._mode = TravisMode.OFF
        self.set_mode(initial)

    @property
    def mode(self) -> TravisMode:
        return self._mode

    @property
    def active(self) -> bool:
        return self._mode != TravisMode.OFF

    @property
    def profile(self) -> ModeProfile | None:
        if self._mode == TravisMode.OFF:
            return None
        return PROFILES[self._mode]

    def status(self) -> str:
        if not self.active:
            return "Travis modes off — standard Jarvis."
        p = self.profile
        assert p is not None
        return f"Travis · {p.label} mode active."

    def set_mode(self, name: str | TravisMode) -> ModeProfile | None:
        """Enter a mode (or off). Returns the profile entered, or None if off."""
        raw = (name.value if isinstance(name, TravisMode) else str(name or "off")).strip().lower()
        raw = raw.replace("-", "_").replace(" ", "_")
        aliases = {
            "off": TravisMode.OFF,
            "clear": TravisMode.OFF,
            "reset": TravisMode.OFF,
            "jarvis": TravisMode.OFF,
            "standard": TravisMode.OFF,
            "park": TravisMode.PARK,
            "park_mode": TravisMode.PARK,
            "casual": TravisMode.PARK,
            "tactical": TravisMode.TACTICAL,
            "tacticals": TravisMode.TACTICAL,
            "tactical_protocol": TravisMode.TACTICAL,
            "tac": TravisMode.TACTICAL,
            "peer": TravisMode.PEER_REVIEW,
            "peer_review": TravisMode.PEER_REVIEW,
            "review": TravisMode.PEER_REVIEW,
            "critique": TravisMode.PEER_REVIEW,
        }
        mode = aliases.get(raw, None)
        if mode is None:
            # soft parse from free text
            if "peer" in raw or "review" in raw:
                mode = TravisMode.PEER_REVIEW
            elif "tact" in raw:
                mode = TravisMode.TACTICAL
            elif "park" in raw:
                mode = TravisMode.PARK
            elif raw in ("off", "stop", "exit"):
                mode = TravisMode.OFF
            else:
                mode = TravisMode.OFF
        self._mode = mode
        return self.profile

    def overlay_prompt(self, base: str) -> str:
        """Append mode instructions onto the base system prompt."""
        p = self.profile
        if not p:
            return base
        return f"{base.rstrip()}\n\n---\n{p.instructions}"

    def speakable_budget(self, default: int = 60) -> int:
        p = self.profile
        return p.max_words if p else default

    def shape_reply(self, text: str) -> str:
        """Rewrite delivery to match the active mode."""
        t = re.sub(r"\s+", " ", (text or "").strip())
        if not t or not self.active:
            return t
        mode = self._mode
        if mode == TravisMode.TACTICAL:
            return self._tactical_fragments(t)
        if mode == TravisMode.PARK:
            return self._park_color(t)
        if mode == TravisMode.PEER_REVIEW:
            return self._peer_prefix(t)
        return t

    def _tactical_fragments(self, t: str) -> str:
        # Prefer short clauses; drop soft filler
        t = re.sub(
            r"\b(you know|basically|just|kinda|kind of|sort of|actually|well,?)\b",
            "",
            t,
            flags=re.I,
        )
        t = re.sub(r"\s+", " ", t).strip(" ,;")
        # Split into tight fragments
        parts = re.split(r"(?<=[.!?])\s+|(?<=;)\s+|\s+—\s+|\s+-\s+", t)
        frags: list[str] = []
        for p in parts:
            p = p.strip(" .")
            if not p:
                continue
            words = p.split()
            if len(words) > 8:
                p = " ".join(words[:8]).rstrip(",;:") + "."
            elif not p.endswith((".", "!", "?")):
                p += "."
            # Cap sentence case lightly
            if p and p[0].islower():
                p = p[0].upper() + p[1:]
            frags.append(p)
            if len(frags) >= 4:
                break
        return " ".join(frags) if frags else t

    def _park_color(self, t: str) -> str:
        low = t.lower()
        # Light boss / engineer seasoning — don't double-prefix
        if re.search(r"\bboss\b", low) or len(t.split()) > 40:
            return t
        # Soft eng-flavored lead-in on short oks
        if re.match(r"^(done|ok|very good|opening|securing)\b", low):
            return f"Copy, boss. {t}"
        if t.endswith("."):
            return t[:-1] + ", boss."
        return f"{t}, boss."

    def _peer_prefix(self, t: str) -> str:
        low = t.lower()
        if low.startswith("review:"):
            return t
        if any(
            k in low
            for k in (
                "flaw",
                "issue",
                "risk",
                "bug",
                "wrong",
                "don't",
                "do not",
                "instead",
                "rewrite",
                "missing",
            )
        ):
            return t
        return f"Review: {t}"


def parse_mode_command(text: str) -> str | None:
    """
    Detect Travis mode switch intents.
    Returns mode key (park|tactical|peer_review|off|status) or None.
    """
    t = (text or "").lower().strip()
    if not t:
        return None

    # Don't steal map / place intents
    if re.search(r"\btactical\s+map\b|\bnational\s+park\b|\b(amusement|theme)\s+park\b", t):
        return None

    if re.search(
        r"\b(exit|leave|clear|disable|stop|end)\s+(travis|park|tactical|peer(\s+review)?)\b"
        r"|\b(travis|park|tactical|peer(\s+review)?)\s+(mode\s+)?(off|clear|exit)\b"
        r"|\b(standard|normal)\s+(protocol|mode|jarvis)\b"
        r"|\bjarvis\s+mode\b"
        r"|\btravis\s+mode\s+off\b",
        t,
    ):
        return "off"

    if re.search(r"\btravis\s+status\b|\bwhat mode\b|\bwhich mode\b", t) or re.fullmatch(
        r"travis(\s+mode)?", t
    ):
        return "status"

    if re.search(
        r"\b(enter|engage|activate|switch to|go into|enable)\s+(travis\s+)?park(\s+mode)?\b"
        r"|\b(travis\s+)?park\s+mode\b"
        r"|\btravis\s+(park|casual)\b"
        r"|^park$",
        t,
    ):
        return "park"

    if re.search(
        r"\b(enter|engage|activate|switch to|go into|enable)\s+(travis\s+)?tactical(s)?(\s+(protocol|mode|assignment))?\b"
        r"|\b(travis\s+)?tactical(s)?\s+(protocol|mode|assignment)\b"
        r"|\bassignment\s+protocol\b"
        r"|\btravis\s+tactical(s)?\b"
        r"|^tactical(s)?$",
        t,
    ):
        return "tactical"

    if re.search(
        r"\b(enter|engage|activate|switch to|go into|enable)\s+(travis\s+)?peer(\s+review)?(\s+mode)?\b"
        r"|\b(travis\s+)?peer\s+review(\s+mode)?\b"
        r"|\bcritique\s+mode\b"
        r"|\breview\s+mode\b"
        r"|\btravis\s+peer\b"
        r"|^peer$",
        t,
    ):
        return "peer_review"

    return None

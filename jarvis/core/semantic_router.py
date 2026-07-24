"""Semantic router — priority lanes + local-first vs hub/AI complexity gate.

Simple utterances (weather, lock, hotkeys) stay on fast local Python.
Only high-complexity / agent asks reach the Hub LLM spoke.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Lane(str, Enum):
    EMERGENCY = "emergency"  # lock, panic, sleep
    HOTKEY = "hotkey"  # copy/paste/save
    DESK = "desk"  # security, NV, enroll, auto-lock
    TRAVIS = "travis"
    PHONE = "phone"
    FACTS = "facts"  # time, weather, status, help
    MEDIA = "media"  # music, camera, news, map
    BUILD = "build"  # site, vibe, search
    PRODUCTIVITY = "productivity"  # git, calendar, workflows
    HUB = "hub"  # Sarah/Tom/Admin / open-ended AI
    CHITCHAT = "chitchat"
    UNKNOWN = "unknown"


class Complexity(str, Enum):
    LOCAL = "local"  # hard-coded router → Python
    HUB = "hub"  # multi-agent / LLM
    EITHER = "either"


@dataclass(frozen=True)
class RouteDecision:
    lane: Lane
    complexity: Complexity
    reason: str = ""
    # If True, brain must NOT call Hub even if wants_hub matches
    force_local: bool = False


# Priority order (first match wins) — keep aligned with brain._route comment block
_LANE_RULES: list[tuple[Lane, Complexity, str, re.Pattern[str]]] = [
    (
        Lane.EMERGENCY,
        Complexity.LOCAL,
        "emergency",
        re.compile(
            r"\b(panic|lock( the screen)?|sleep|shutdown|secure (the )?desk|"
            r"unlock (my )?(pc|computer|workstation)|"
            r"go offline|reload (the )?core)\b",
            re.I,
        ),
    ),
    (
        Lane.HOTKEY,
        Complexity.LOCAL,
        "hotkey",
        re.compile(
            r"\b(hit (copy|paste|save|undo|cut|redo)|"
            r"^(copy|paste|save|undo|cut|select all)$|"
            r"new tab|close tab|show desktop)\b",
            re.I,
        ),
    ),
    (
        Lane.PHONE,
        Complexity.LOCAL,
        "phone",
        re.compile(
            r"\b(phone|iphone|ntfy|text my phone|ping my phone|link my phone|"
            r"phone companion|open phone companion|companion status)\b",
            re.I,
        ),
    ),
    (
        Lane.PHONE,  # Cloud SaaS — force local
        Complexity.LOCAL,
        "cloud",
        re.compile(
            r"\b(integrations?\s+status|cloud\s+status|"
            r"stripe|notion|buffer|gmail|"
            r"link\s+(stripe|notion|buffer|gmail)|"
            r"set\s+(stripe|notion|buffer|gmail)\s+"
            r"(key|token|secret\s+key))\b",
            re.I,
        ),
    ),
    (
        Lane.PHONE,  # Manus — PHONE-adjacent external link; force local
        Complexity.LOCAL,
        "manus",
        re.compile(
            r"\b(manus|ask manus|send to manus|tell manus|"
            r"link manus|connect manus|setup manus|"
            r"set manus (api )?key|manus (status|result|progress|follow.?up|continue|review)|"
            r"review (this )?with manus|manus improve|ask manus to improve|"
            r"check manus|is manus linked)\b",
            re.I,
        ),
    ),
    (
        Lane.TRAVIS,
        Complexity.LOCAL,
        "travis",
        re.compile(
            r"\b(travis|park mode|peer review|tactical mode)\b",
            re.I,
        ),
    ),
    (
        Lane.DESK,
        Complexity.LOCAL,
        "desk",
        re.compile(
            r"\b(enrol+ (my )?face|security status|arm security|disarm security|"
            r"intruder alerts? (on|off)|night vision|nvg|auto lock|presence lock|"
            r"self[- ]?audit|autobug|"
            r"fix this (bug|error)|intruder|router status|secure (the )?desk)\b",
            re.I,
        ),
    ),
    (
        Lane.FACTS,
        Complexity.LOCAL,
        "facts",
        re.compile(
            r"\b(what time|the time|what(?:'s| is) the date|what day|"
            r"weather|forecast|temperature|"
            r"^(status)$|system (status|vitals)|how(?:'s| is) (the )?(cpu|system)|"
            r"full status|upgrade status|upgrade check|self health|health check|desk health|recent errors|"
            r"quiet mode|loud mode|desk ready|"
            r"summarize (my )?day|summarize (the |my )?clipboard|"
            r"suggestions? (on|off)|stop suggesting|"
            r"help|what can you do|list commands|"
            r"feature status|registry status|disk space)\b",
            re.I,
        ),
    ),
    (
        Lane.MEDIA,
        Complexity.LOCAL,
        "media",
        re.compile(
            r"\b(play music|pause|volume|mute|open camera|scan this|"
            r"open map|zoom in to|pull up the news|show stats|open pdtester|"
            r"close (the )?(map|news|camera)|"
            r"switch to (headphones|speakers))\b",
            re.I,
        ),
    ),
    (
        Lane.BUILD,
        Complexity.LOCAL,
        "build",
        re.compile(
            r"\b(build (a )?site|start vibe|find biz|search the web|"
            r"look at my screen|screenshot)\b",
            re.I,
        ),
    ),
    (
        Lane.PRODUCTIVITY,
        Complexity.LOCAL,
        "productivity",
        re.compile(
            r"\b(auto commit|git status|tech news|check prices|"
            r"morning (workflow|routine)|night (workflow|routine)|"
            r"focus (workflow|routine)|proactive (on|off)|"
            r"upgrade|cancel upgrade|work mode|"
            r"schedule (?!a meeting with)\w+)\b",
            re.I,
        ),
    ),
    (
        Lane.HUB,
        Complexity.HUB,
        "hub agents",
        re.compile(
            r"\b(sarah|tom|admin|ask sarah|ask tom|ask admin|"
            r"start hub|hub status|hub standby|"
            r"investigate|triage|open a pr|write (me )?(a )?(long |detailed )|"
            r"plan (how|a)|refactor|architect|explain (in detail|why)|"
            r"complex|research|analyze (this|my)|"
            r"code review|debug (this|my)|implement (a |an )?)\b",
            re.I,
        ),
    ),
    (
        Lane.CHITCHAT,
        Complexity.LOCAL,
        "chitchat",
        re.compile(
            r"\b(thanks|thank you|who are you|how are you|tell me a joke|"
            r"good ?night|good morning|i love you)\b",
            re.I,
        ),
    ),
]

# Patterns that MUST stay local even if HubClient.wants_hub is noisy
_FORCE_LOCAL = re.compile(
    r"\b(weather|what time|the time|lock|sleep|panic|copy|paste|save|"
    r"enrol+|enroll|night vision|security status|open camera|play music|"
    r"screenshot|volume|mute|help|status|auto lock|show stats|router status|"
    r"secure desk|open pdtester|look at my screen|check email|open map|"
    r"pull up the news|away mode|self audit|fix this error)\b",
    re.I,
)

# Heuristic: long multi-clause questions → hub-capable
_COMPLEX = re.compile(
    r"\b(why|how (do|can|would|should)|explain|compare|design|architect|"
    r"step by step|walk me through|in detail|pros and cons|"
    r"research|investigate|refactor|implement|debug)\b",
    re.I,
)


class SemanticRouter:
    """Table-driven priority gate — O(rules) regex, no LLM."""

    def decide(self, text: str) -> RouteDecision:
        t = (text or "").strip()
        if not t:
            return RouteDecision(Lane.UNKNOWN, Complexity.LOCAL, "empty", True)

        force_local = bool(_FORCE_LOCAL.search(t))

        for lane, complexity, reason, pat in _LANE_RULES:
            if pat.search(t):
                # Desk/facts/media never escalate unless explicitly HUB lane
                if lane != Lane.HUB and force_local:
                    return RouteDecision(lane, Complexity.LOCAL, reason, True)
                if lane == Lane.HUB and force_local:
                    continue  # prefer local match if somehow both
                return RouteDecision(
                    lane,
                    complexity,
                    reason,
                    force_local=(complexity == Complexity.LOCAL),
                )

        # No lane: short phrases stay local; deep questions may use hub
        words = len(t.split())
        if force_local or words <= 5:
            return RouteDecision(Lane.UNKNOWN, Complexity.LOCAL, "short/local", True)
        if _COMPLEX.search(t) or words >= 10:
            return RouteDecision(Lane.HUB, Complexity.HUB, "complex/open", False)
        return RouteDecision(Lane.UNKNOWN, Complexity.EITHER, "unclassified", False)

    def allows_hub(self, text: str) -> bool:
        d = self.decide(text)
        if d.force_local or d.complexity == Complexity.LOCAL:
            return False
        return d.complexity in (Complexity.HUB, Complexity.EITHER)

    def priority_legend(self) -> str:
        order = [
            "1 emergency",
            "2 hotkey",
            "3 phone",
            "4 travis",
            "5 desk",
            "6 facts",
            "7 media",
            "8 build",
            "9 productivity",
            "10 hub/AI",
            "11 chitchat",
        ]
        return "Router priority: " + " > ".join(order)

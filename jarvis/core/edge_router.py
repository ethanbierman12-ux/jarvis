"""Hybrid edge router — local Ollama for simple OS cmds, cloud/hub for complex."""

from __future__ import annotations

import re


SIMPLE = re.compile(
    r"\b("
    r"lock|sleep|wake|mute|unmute|volume|open |launch |close |kill |"
    r"play |pause|next|previous|weather|time|camera|scan|scroll |"
    r"click |type |press |go offline|reload|reboot|switch to |"
    r"good morning|brief|help"
    r")\b",
    re.I,
)

COMPLEX = re.compile(
    r"\b("
    r"analy[sz]e|refactor|architect|debug|explain (this|the) (code|error|stack)|"
    r"design|implement|migrate|research|compare|write (a |an )?(long |full )?"
    r"(report|essay|proposal)|database schema|pull request|code review"
    r")\b",
    re.I,
)


def route_complexity(text: str) -> str:
    """
    Returns: 'local' | 'cloud' | 'unknown'
    local  → regex / Ollama tiny model / desktop actions
    cloud  → hub spokes / heavy LLM
    """
    t = (text or "").strip()
    if not t:
        return "unknown"
    if COMPLEX.search(t):
        return "cloud"
    if SIMPLE.search(t) or len(t.split()) <= 6:
        return "local"
    if len(t) > 160:
        return "cloud"
    return "local"

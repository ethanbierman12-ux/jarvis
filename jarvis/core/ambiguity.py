"""Ambiguity classifier — vague commands become multi-choice HUD prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ClarifyPrompt:
    title: str
    detail: str
    options: list[str]
    # Maps chosen option label (or index speech) → rewritten utterance
    rewrite: dict[str, str]


# Patterns that are too vague to execute safely without a choice.
_RULES: list[tuple[re.Pattern[str], ClarifyPrompt]] = [
    (
        re.compile(
            r"^\s*(fix|restart|reboot)\s+(the\s+)?(server|api|backend)\s*$",
            re.I,
        ),
        ClarifyPrompt(
            title="Which server?",
            detail="Pick a target for the fix/restart.",
            options=["Port 8080", "Port 3000", "Healer status", "Cancel"],
            rewrite={
                "Port 8080": "healer status",
                "Port 3000": "healer status",
                "Healer status": "healer status",
                "Cancel": "",
            },
        ),
    ),
    (
        re.compile(
            r"^\s*(fix|debug)\s+(it|this|that|the\s+bug|the\s+error)\s*$",
            re.I,
        ),
        ClarifyPrompt(
            title="Fix what?",
            detail="Need a target for the fix.",
            options=[
                "Clipboard error",
                "Healer status",
                "Crew research the error",
                "Cancel",
            ],
            rewrite={
                "Clipboard error": "fix clipboard error",
                "Healer status": "healer status",
                "Crew research the error": "background research common causes of the last error",
                "Cancel": "",
            },
        ),
    ),
    (
        re.compile(
            r"^\s*(deploy|ship|publish)\s*(it|this|that|the\s+app)?\s*$",
            re.I,
        ),
        ClarifyPrompt(
            title="Deploy where?",
            detail="Choose a deploy target.",
            options=["Git commit", "Git commit and push", "Safety snapshot", "Cancel"],
            rewrite={
                "Git commit": "auto commit changes",
                "Git commit and push": "auto commit and push",
                "Safety snapshot": "safety snapshot",
                "Cancel": "",
            },
        ),
    ),
    (
        re.compile(
            r"^\s*(clean|clear)\s+(up\s+)?(the\s+)?(pc|system|computer)\s*$",
            re.I,
        ),
        ClarifyPrompt(
            title="Clean how?",
            detail="System cleanup needs a scope.",
            options=["Kill CPU hogs", "Healer status", "Cancel"],
            rewrite={
                "Kill CPU hogs": "healer kill top",
                "Healer status": "healer status",
                "Cancel": "",
            },
        ),
    ),
    (
        re.compile(
            r"^\s*(build|make|create)\s+(an?\s+)?(app|project|website|site)\s*$",
            re.I,
        ),
        ClarifyPrompt(
            title="What kind of project?",
            detail="Scaffold needs a stack.",
            options=["React + Vite", "Python package", "Static HTML", "Cancel"],
            rewrite={
                "React + Vite": "scaffold react",
                "Python package": "scaffold python",
                "Static HTML": "scaffold html",
                "Cancel": "",
            },
        ),
    ),
]


def classify_ambiguity(text: str) -> ClarifyPrompt | None:
    t = (text or "").strip()
    if not t or len(t) > 120:
        return None
    for pat, prompt in _RULES:
        if pat.search(t):
            return prompt
    return None


def resolve_option(prompt: ClarifyPrompt, answer: str) -> str | None:
    """Map HITL answer / spoken choice to a concrete utterance."""
    ans = (answer or "").strip()
    if not ans:
        return None
    if ans in prompt.rewrite:
        return prompt.rewrite[ans] or None
    low = ans.lower()
    if low in ("cancel", "skip", "never mind", "no", "deny"):
        return None
    for i, opt in enumerate(prompt.options, start=1):
        if low == str(i) or low == f"option {i}" or low == opt.lower():
            return prompt.rewrite.get(opt) or None
        if low in opt.lower() or opt.lower() in low:
            return prompt.rewrite.get(opt) or None
    return None

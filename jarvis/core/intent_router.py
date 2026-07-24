"""Local Ollama JSON intent router — fuzzy phrases → structured OS actions."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any


ALLOWED = {
    "LAUNCH_APP",
    "SYSTEM_LOCK",
    "SYSTEM_SLEEP",
    "MEDIA_CONTROL",
    "WEB_NAVIGATE",
    "HUB",
    "SCREEN",
    "SCAN",
    "BUILD",
    "AWAY",
    "HELP",
    "UNKNOWN",
}


def route_intent_via_ollama(user_text: str, model: str = "llama3") -> dict[str, Any]:
    """
    Ask a local Ollama model for a structured action.
    Returns {"action": "...", "target": "...", "utterance": "..."}.
    On failure → UNKNOWN (caller falls back to regex router).
    """
    text = (user_text or "").strip()
    if not text:
        return {"action": "UNKNOWN", "target": "", "utterance": ""}

    system = (
        "You are an OS navigation router for JARVIS. Output raw JSON ONLY. "
        "Keys: action, target, utterance. "
        f"action must be one of: {', '.join(sorted(ALLOWED))}. "
        "utterance = a clear English command JARVIS already understands "
        "(e.g. open chrome, lock, play music, look at my screen, build a site). "
        "Example: {\"action\":\"LAUNCH_APP\",\"target\":\"chrome\",\"utterance\":\"open chrome\"}"
    )
    payload = {
        "model": model,
        "prompt": f"{system}\nUser said: {text}",
        "stream": False,
        "format": "json",
    }
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = data.get("response") or "{}"
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        action = str(parsed.get("action") or "UNKNOWN").upper()
        if action not in ALLOWED:
            action = "UNKNOWN"
        target = str(parsed.get("target") or "").strip()
        utterance = str(parsed.get("utterance") or "").strip()
        if not utterance:
            utterance = _fallback_utterance(action, target, text)
        return {"action": action, "target": target, "utterance": utterance}
    except Exception:
        return {"action": "UNKNOWN", "target": "", "utterance": text}


def _fallback_utterance(action: str, target: str, original: str) -> str:
    t = (target or "").lower()
    if action == "LAUNCH_APP":
        return f"open {t or 'chrome'}"
    if action == "SYSTEM_LOCK":
        return "lock"
    if action == "SYSTEM_SLEEP":
        return "sleep"
    if action == "MEDIA_CONTROL":
        return "play music" if "play" in original.lower() else "playpause"
    if action == "WEB_NAVIGATE":
        if t.startswith("http"):
            return f"open {t}"
        dest = t or original
        return f"navigate to {dest}"
    if action == "HUB":
        return original
    if action == "SCREEN":
        return "look at my screen"
    if action == "SCAN":
        return "scan"
    if action == "BUILD":
        return "build a site"
    if action == "AWAY":
        return "away mode"
    if action == "HELP":
        return "help"
    return original


def maybe_rewrite(user_text: str, *, enabled: bool = True, model: str = "llama3") -> str:
    """
    If Ollama is up and the phrase looks fuzzy (no hard alias match), rewrite to a canonical command.
    """
    if not enabled:
        return user_text
    low = (user_text or "").lower().strip()
    # Skip obvious canonical commands
    if re.match(
        r"^(open |lock|sleep|play |build |scan|help|away|hub |look at|start |show )",
        low,
    ):
        return user_text
    # Skip very short aliases handled elsewhere
    if len(low.split()) <= 2 and len(low) < 16:
        return user_text
    out = route_intent_via_ollama(user_text, model=model)
    if out.get("action") == "UNKNOWN":
        return user_text
    utt = (out.get("utterance") or "").strip()
    return utt or user_text

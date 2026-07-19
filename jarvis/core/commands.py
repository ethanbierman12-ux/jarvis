"""Natural-language command aliases — normalize before routing."""

from __future__ import annotations

import re

# Short phrases users type/say → canonical utterances the brain already understands
_ALIASES: list[tuple[str, str]] = [
    (r"^(hi|hello|hey)( jarvis)?$", "how are you"),
    (r"^status$", "status"),
    (r"^(hub|agents?) status$", "hub status"),
    (r"^start( the)? hub$", "start hub"),
    (r"^(stop|halt)( the)? (hub|agents?)$", "hub standby"),
    (r"^standby$", "hub standby"),
    (r"^sarah$", "sarah triage support tickets"),
    (r"^tom$", "investigate the checkout bug and open a PR"),
    (r"^admin$", "schedule a meeting with the client who complained in support"),
    (r"^(see|read )?screen$", "look at my screen"),
    (r"^help me$", "help me with this"),
    (r"^build$", "build a site"),
    (r"^site$", "build a site"),
    (r"^vibe$", "start vibe coding"),
    (r"^map$", "open map view"),
    (r"^news$", "pull up the news"),
    (r"^cam(era)?$", "open camera"),
    (r"^music$", "play music"),
    (r"^playlist$", "play my focus playlist"),
    (r"^mail$", "check email"),
    (r"^ops$", "show ops"),
    (r"^stats$", "show stats"),
    (r"^away$", "away mode"),
    (r"^biz$", "find biz"),
    (r"^search$", "search the web for latest AI news"),
]


def normalize_command(text: str) -> str:
    """Expand short aliases; leave full sentences untouched."""
    raw = (text or "").strip()
    if not raw:
        return raw
    low = raw.lower().strip(" .!?")
    for pattern, canon in _ALIASES:
        if re.fullmatch(pattern, low, re.I):
            return canon
    return raw

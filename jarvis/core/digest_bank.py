"""PDTester digest bank — 6 graphical digests for the secondary monitor.

Updated from the live activity feed on the UI thread; safe to call from feed callbacks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


SLOTS: tuple[str, ...] = ("VOICE", "DESK", "BUILD", "SYSTEM", "HUB", "NET")

_KIND_TO_SLOT: dict[str, str] = {
    "hear": "VOICE",
    "speak": "VOICE",
    "voice": "VOICE",
    "route": "VOICE",
    "security": "DESK",
    "presence": "DESK",
    "optics": "DESK",
    "lock": "DESK",
    "enroll": "DESK",
    "site": "BUILD",
    "vibe": "BUILD",
    "code": "BUILD",
    "biz": "BUILD",
    "upgrade": "SYSTEM",
    "task": "SYSTEM",
    "registry": "SYSTEM",
    "audit": "SYSTEM",
    "hub": "HUB",
    "sarah": "HUB",
    "tom": "HUB",
    "admin": "HUB",
    "net": "NET",
    "mail": "NET",
    "phone": "NET",
    "spend": "NET",
}


@dataclass
class DigestCard:
    slot: str
    title: str
    body: str = "Standing by…"
    accent: str = "#00e8ff"
    updated_at: float = 0.0
    count: int = 0


_ACCENTS = {
    "VOICE": "#00e8ff",
    "DESK": "#3dff9a",
    "BUILD": "#c4a0ff",
    "SYSTEM": "#ffb020",
    "HUB": "#ff6b4a",
    "NET": "#7ec8ff",
}


class DigestBank:
    """Holds exactly six graphical digests for the PDTester board."""

    def __init__(self) -> None:
        self.cards: dict[str, DigestCard] = {
            s: DigestCard(slot=s, title=s, accent=_ACCENTS[s]) for s in SLOTS
        }

    def ingest(self, item: dict[str, Any] | None) -> list[DigestCard]:
        if not item:
            return self.as_list()
        kind = str(item.get("kind") or "info").lower()
        text = str(item.get("text") or "").strip()
        if not text:
            return self.as_list()
        slot = _KIND_TO_SLOT.get(kind, "SYSTEM")
        # Soft keyword override from text
        low = text.lower()
        if any(k in low for k in ("enroll", "night vision", "security", "intruder")):
            slot = "DESK"
        elif any(k in low for k in ("weather", "time", "cpu", "upgrade", "registry")):
            slot = "SYSTEM"
        elif any(k in low for k in ("sarah", "tom", "hub", "agent")):
            slot = "HUB"
        elif any(k in low for k in ("site", "vibe", "build", "code")):
            slot = "BUILD"
        elif any(k in low for k in ("phone", "mail", "http", "search")):
            slot = "NET"

        card = self.cards[slot]
        card.body = text[:160]
        card.updated_at = time.time()
        card.count += 1
        return self.as_list()

    def as_list(self) -> list[DigestCard]:
        return [self.cards[s] for s in SLOTS]

    def as_dicts(self) -> list[dict[str, Any]]:
        out = []
        for c in self.as_list():
            out.append(
                {
                    "slot": c.slot,
                    "title": c.title,
                    "body": c.body,
                    "accent": c.accent,
                    "count": c.count,
                    "updated_at": c.updated_at,
                }
            )
        return out

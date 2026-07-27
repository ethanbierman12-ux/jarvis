"""Dynamic morning briefing protocols — mood, rotation, greetings, topic shuffle."""

from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR

STATE_PATH = DATA_DIR / "briefing_state.json"

GREETINGS = [
    "A splendid morning to you, Sir.",
    "The network is online. Awaiting your command, Sir.",
    "Apologies for the interruption, Sir — briefing ready.",
    "Systems nominal. Shall we begin, Sir?",
    "Good day, Sir. The board is clear for your orders.",
    "Welcome online, Sir. Pulse check complete.",
    "At your service, Sir. Briefing packet assembled.",
    "Sir — chronometer confirms a new cycle. Standing by.",
    "All grids green. Awaiting priorities, Sir.",
    "Boot sequence concluded. How shall we proceed, Sir?",
]

MODES = ("tactical", "casual", "blindspot")


class BriefingProtocols:
    """
    Mood-based briefs that never repeat the same style twice in a row.

    - tactical: high focus — deadlines, conflicts, critical systems only
    - casual: low energy — free time, trivia, tech headlines, dry British wit
    - blindspot: risk mitigation — overdue, unread, overlaps
    """

    def __init__(
        self,
        *,
        brief=None,
        spend=None,
        habits=None,
        news_fn: Callable[[], str] | None = None,
        mail_fn: Callable[[], str] | None = None,
    ) -> None:
        self.brief = brief
        self.spend = spend
        self.habits = habits
        self.news_fn = news_fn
        self.mail_fn = mail_fn

    def compose(self, *, mode: str = "auto", force_mode: str = "") -> str:
        state = self._load()
        chosen = (force_mode or "").strip().lower()
        if chosen not in MODES:
            if mode == "auto":
                chosen = self._pick_mode(state)
            else:
                chosen = mode if mode in MODES else "tactical"
        # Never same mode twice in a row
        if chosen == state.get("last_mode") and not force_mode:
            alts = [m for m in MODES if m != chosen]
            chosen = random.choice(alts)

        greeting = self._greeting(state)
        body = {
            "tactical": self._tactical,
            "casual": self._casual,
            "blindspot": self._blindspot,
        }[chosen]()

        topic = self._topic_shuffle()
        parts = [greeting, f"[{chosen.upper()} BRIEF]", body]
        if topic:
            parts.append(topic)

        state["last_mode"] = chosen
        state["last_greeting"] = greeting
        state["last_day"] = datetime.now().strftime("%Y-%m-%d")
        state["count"] = int(state.get("count") or 0) + 1
        self._save(state)
        return " ".join(p for p in parts if p).strip()

    def status(self) -> str:
        s = self._load()
        return (
            f"Briefing protocols — last mode {s.get('last_mode') or 'none'}, "
            f"briefings delivered {s.get('count') or 0}."
        )

    def _pick_mode(self, state: dict[str, Any]) -> str:
        hour = datetime.now().hour
        # Late night → casual/quiet; morning peak → tactical; midday mix blindspot
        if hour < 6 or hour >= 22:
            return "casual"
        if 6 <= hour < 11:
            return random.choice(["tactical", "tactical", "blindspot"])
        if 11 <= hour < 16:
            return random.choice(["blindspot", "casual", "tactical"])
        return random.choice(["casual", "tactical"])

    def _greeting(self, state: dict[str, Any]) -> str:
        hour = datetime.now().hour
        last = state.get("last_greeting") or ""
        pool = [g for g in GREETINGS if g != last] or list(GREETINGS)
        g = random.choice(pool)
        if hour < 5 or hour >= 23:
            g = "Keeping this brief, Sir — odd hours."
        elif hour >= 18:
            g = random.choice(
                [
                    "Evening brief, Sir.",
                    "As the day winds down, Sir — status packet.",
                ]
            )
        return g

    def _tactical(self) -> str:
        bits: list[str] = []
        # Critical only — skip weather/news fluff
        if self.brief:
            try:
                cal = self.brief.schedule_only()
                if cal and "no" not in cal.lower()[:12]:
                    bits.append(f"Calendar: {cal}")
            except Exception:
                pass
            try:
                tasks = self.brief._load_tasks()
                open_t = list(tasks.get("open") or [])[:4]
                if open_t:
                    bits.append("High-priority tasks: " + "; ".join(open_t) + ".")
            except Exception:
                pass
        if not bits:
            bits.append("No critical deadlines flagged. Board is clear for deep work.")
        return " ".join(bits)

    def _casual(self) -> str:
        bits = [
            "Nothing too luminous, Sir — a lighter pass.",
        ]
        if self.spend:
            try:
                card = self.spend.stats_card()
                bits.append(
                    f"Spend so far today: {card.get('currency','USD')} "
                    f"{float(card.get('today') or 0):.2f}."
                )
            except Exception:
                pass
        # Topic: free time / trivia / tech
        if self.news_fn:
            try:
                n = (self.news_fn() or "").strip()
                if n:
                    bits.append(n[:220])
            except Exception:
                pass
        else:
            trivia = [
                "Trivia: the first computer bug was, quite literally, a moth.",
                "Tech note: LoRA lets us reshape a model’s manners without a castle full of GPUs.",
                "Lightweight update: stretch once before the next deep block — joints appreciate it.",
            ]
            bits.append(random.choice(trivia))
        return " ".join(bits)

    def _blindspot(self) -> str:
        bits = ["Blind-spot sweep."]
        overdue = []
        if self.brief:
            try:
                tasks = self.brief._load_tasks()
                overdue = list(tasks.get("open") or [])[:5]
            except Exception:
                pass
        if overdue:
            bits.append("Possibly neglected: " + "; ".join(overdue) + ".")
        else:
            bits.append("Task list looks tidy — vigilance still advised.")
        if self.mail_fn:
            try:
                m = (self.mail_fn() or "").strip()
                if m and "empty" not in m.lower():
                    bits.append(f"Mail pulse: {m[:180]}")
            except Exception:
                pass
        bits.append("Watch for overlapping calendar blocks and unread high-priority threads.")
        return " ".join(bits)

    def _topic_shuffle(self) -> str:
        """Mon/Wed/Fri global tech; Tue/Thu local/personal goals."""
        wd = datetime.now().weekday()  # 0=Mon
        if wd in (0, 2, 4):
            return "Horizon lane: global tech headlines."
        if wd in (1, 3):
            return "Horizon lane: local updates and personal goals."
        return "Horizon lane: weekend recovery and optional creative sparks."

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

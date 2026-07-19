"""Spend tracker — cash/card outflows Jarvis can report on wake."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from jarvis.config import DATA_DIR

SPEND_PATH = DATA_DIR / "spend.json"


class SpendTracker:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not SPEND_PATH.exists():
            SPEND_PATH.write_text(
                json.dumps({"currency": "USD", "entries": []}, indent=2),
                encoding="utf-8",
            )

    def add(self, amount: float, note: str = "", *, source: str = "voice") -> str:
        if amount <= 0:
            return "Need a positive amount to log."
        data = self._load()
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "day": datetime.now().strftime("%Y-%m-%d"),
            "amount": round(float(amount), 2),
            "note": (note or "expense").strip()[:120],
            "source": source,
        }
        data.setdefault("entries", []).append(entry)
        data["entries"] = data["entries"][-800:]
        self._save(data)
        cur = data.get("currency") or "USD"
        return f"Logged {cur} {entry['amount']:.2f} for {entry['note']}."

    def parse_and_add(self, text: str) -> str | None:
        """
        Match: 'I spent 12 on coffee', 'log expense $4.50 lunch', 'spent 20 dollars uber'
        """
        t = (text or "").strip().lower()
        m = re.search(
            r"\b(?:i\s+)?(?:spent|spend|paid|pay|expense|log(?:ged)?\s+expense)\s+"
            r"\$?\s*(\d+(?:\.\d{1,2})?)\s*"
            r"(?:dollars?|bucks|usd)?\s*"
            r"(?:on|for|at)?\s*(.*)$",
            t,
        )
        if not m:
            m = re.search(
                r"\b(?:add|log)\s+(?:spend|expense|purchase)\s+"
                r"\$?\s*(\d+(?:\.\d{1,2})?)\s+(.+)$",
                t,
            )
        if not m:
            return None
        amount = float(m.group(1))
        note = (m.group(2) or "expense").strip(" .,") or "expense"
        note = re.sub(r"^(dollars?|bucks|usd)\s+", "", note).strip()
        return self.add(amount, note)

    def total_today(self) -> float:
        day = datetime.now().strftime("%Y-%m-%d")
        return round(
            sum(
                float(e.get("amount") or 0)
                for e in self._load().get("entries") or []
                if e.get("day") == day
            ),
            2,
        )

    def total_week(self) -> float:
        from datetime import timedelta

        today = datetime.now().date()
        days = {(today - timedelta(days=i)).isoformat() for i in range(7)}
        return round(
            sum(
                float(e.get("amount") or 0)
                for e in self._load().get("entries") or []
                if e.get("day") in days
            ),
            2,
        )

    def speak_summary(self, *, period: str = "today") -> str:
        data = self._load()
        cur = data.get("currency") or "USD"
        if period == "week":
            total = self.total_week()
            return f"This week you've logged {cur} {total:.2f} in spending."
        total = self.total_today()
        entries = [
            e for e in (data.get("entries") or []) if e.get("day") == datetime.now().strftime("%Y-%m-%d")
        ]
        if not entries:
            return f"No spending logged today — say 'I spent twelve on coffee' to track it."
        top = sorted(entries, key=lambda e: float(e.get("amount") or 0), reverse=True)[:3]
        bits = ", ".join(f"{e.get('note')} {cur} {float(e.get('amount') or 0):.2f}" for e in top)
        return f"Today you've spent {cur} {total:.2f}. Top: {bits}."

    def stats_card(self) -> dict[str, Any]:
        return {
            "today": self.total_today(),
            "week": self.total_week(),
            "currency": self._load().get("currency") or "USD",
            "count_today": sum(
                1
                for e in self._load().get("entries") or []
                if e.get("day") == datetime.now().strftime("%Y-%m-%d")
            ),
        }

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(SPEND_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"currency": "USD", "entries": []}

    def _save(self, data: dict[str, Any]) -> None:
        SPEND_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

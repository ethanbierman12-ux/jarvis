"""Spend tracker — voice + Cash App outflows Jarvis can report on."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Callable

from jarvis.config import DATA_DIR

SPEND_PATH = DATA_DIR / "spend.json"

# Cash App receipt mail (Square)
_CASHAPP_GMAIL_Q = (
    '(from:cash@square.com OR from:cash.app OR from:"Cash App" '
    'OR subject:"You paid" OR subject:"You sent" OR subject:"Cash App")'
)


class SpendTracker:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not SPEND_PATH.exists():
            SPEND_PATH.write_text(
                json.dumps({"currency": "USD", "entries": []}, indent=2),
                encoding="utf-8",
            )

    def add(
        self,
        amount: float,
        note: str = "",
        *,
        source: str = "voice",
        method: str = "",
        external_id: str = "",
        day: str = "",
    ) -> str:
        if amount <= 0:
            return "Need a positive amount to log."
        data = self._load()
        method_n = self._norm_method(method) or self._infer_method(note, source)
        eid = (external_id or "").strip()[:120]
        if eid:
            for e in data.get("entries") or []:
                if e.get("external_id") == eid:
                    return f"Already logged that Cash App payment ({amount:.2f})."
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "day": day or datetime.now().strftime("%Y-%m-%d"),
            "amount": round(float(amount), 2),
            "note": (note or "expense").strip()[:120],
            "source": source,
            "method": method_n,
        }
        if eid:
            entry["external_id"] = eid
        data.setdefault("entries", []).append(entry)
        data["entries"] = data["entries"][-1200:]
        self._save(data)
        cur = data.get("currency") or "USD"
        via = f" via {method_n.replace('_', ' ')}" if method_n else ""
        return f"Logged {cur} {entry['amount']:.2f} for {entry['note']}{via}."

    def parse_and_add(self, text: str) -> str | None:
        """
        Match: 'I spent 12 on coffee', 'spent 20 on Cash App for lunch',
        'Cash App 15 to Mom', 'log expense $4.50 lunch'
        """
        t = (text or "").strip().lower()
        method = ""
        if re.search(r"\bcash\s*app\b|\bcashapp\b", t):
            method = "cash_app"

        # Cash App … $12 to/for …
        m = re.search(
            r"\bcash\s*app\b\s+(?:payment|paid|sent|send|spent)?\s*"
            r"\$?\s*(\d+(?:\.\d{1,2})?)\s*"
            r"(?:dollars?|bucks|usd)?\s*"
            r"(?:on|for|to|at)?\s*(.*)$",
            t,
        )
        if m:
            amount = float(m.group(1))
            note = (m.group(2) or "cash app").strip(" .,") or "cash app"
            note = re.sub(r"^(dollars?|bucks|usd)\s+", "", note).strip()
            return self.add(amount, note, method="cash_app", source="voice")

        m = re.search(
            r"\b(?:i\s+)?(?:spent|spend|paid|pay|expense|log(?:ged)?\s+expense)\s+"
            r"\$?\s*(\d+(?:\.\d{1,2})?)\s*"
            r"(?:dollars?|bucks|usd)?\s*"
            r"(?:on|for|at|via|with)?\s*(.*)$",
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
        # "12 on cash app for coffee" / "12 via cash app coffee"
        if re.search(r"\bcash\s*app\b|\bcashapp\b", note):
            method = "cash_app"
            note = re.sub(r"\bcash\s*app\b|\bcashapp\b", " ", note, flags=re.I)
            note = re.sub(r"\s+", " ", note).strip(" -:,") or "cash app"
        note = re.sub(r"^(on|for|at|via|with|to)\s+", "", note, flags=re.I).strip()
        note = note or ("cash app" if method == "cash_app" else "expense")
        return self.add(amount, note, method=method)

    def total_today(self) -> float:
        return self._sum_days({datetime.now().strftime("%Y-%m-%d")})

    def total_week(self) -> float:
        today = datetime.now().date()
        days = {(today - timedelta(days=i)).isoformat() for i in range(7)}
        return self._sum_days(days)

    def total_month(self) -> float:
        prefix = datetime.now().strftime("%Y-%m")
        return round(
            sum(
                float(e.get("amount") or 0)
                for e in self._load().get("entries") or []
                if str(e.get("day") or "").startswith(prefix)
            ),
            2,
        )

    def total_method(self, method: str, *, period: str = "week") -> float:
        return round(
            sum(float(e.get("amount") or 0) for e in self._entries_for_method(method, period=period)),
            2,
        )

    def by_method(self, *, period: str = "week") -> dict[str, float]:
        days = self._period_days(period)
        month_prefix = datetime.now().strftime("%Y-%m")
        out: dict[str, float] = {}
        for e in self._load().get("entries") or []:
            day = str(e.get("day") or "")
            if period == "month":
                if not day.startswith(month_prefix):
                    continue
            elif days is not None and day not in days:
                continue
            m = self._norm_method(e.get("method") or "") or self._infer_method(
                str(e.get("note") or ""), str(e.get("source") or "")
            )
            key = m or "other"
            out[key] = round(out.get(key, 0) + float(e.get("amount") or 0), 2)
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def speak_summary(self, *, period: str = "today") -> str:
        data = self._load()
        cur = data.get("currency") or "USD"
        if period == "month":
            total = self.total_month()
            methods = self.by_method(period="month")
            if not methods:
                return f"No spending logged this month — say 'I spent twelve on Cash App for lunch'."
            bits = ", ".join(
                f"{k.replace('_', ' ')} {cur} {v:.2f}" for k, v in list(methods.items())[:4]
            )
            return f"This month you've logged {cur} {total:.2f}. By channel: {bits}."
        if period == "week":
            total = self.total_week()
            methods = self.by_method(period="week")
            cash = methods.get("cash_app", 0.0)
            extra = f" Cash App is {cur} {cash:.2f} of that." if cash else ""
            return f"This week you've logged {cur} {total:.2f} in spending.{extra}"
        total = self.total_today()
        day = datetime.now().strftime("%Y-%m-%d")
        entries = [e for e in (data.get("entries") or []) if e.get("day") == day]
        if not entries:
            return (
                f"No spending logged today — say 'I spent twelve on coffee' "
                f"or 'Cash App 20 for gas'."
            )
        top = sorted(entries, key=lambda e: float(e.get("amount") or 0), reverse=True)[:3]
        bits = ", ".join(
            f"{e.get('note')} {cur} {float(e.get('amount') or 0):.2f}" for e in top
        )
        cash = sum(
            float(e.get("amount") or 0)
            for e in entries
            if self._norm_method(e.get("method") or "") == "cash_app"
            or "cash app" in str(e.get("note") or "").lower()
        )
        cash_bit = f" Cash App today: {cur} {cash:.2f}." if cash else ""
        return f"Today you've spent {cur} {total:.2f}. Top: {bits}.{cash_bit}"

    def speak_cash_app(self, *, period: str = "week") -> str:
        cur = self._load().get("currency") or "USD"
        total = self.total_method("cash_app", period=period)
        label = {"today": "today", "week": "this week", "month": "this month"}.get(
            period, period
        )
        entries = self._entries_for_method("cash_app", period=period)
        if not entries and total <= 0:
            return (
                f"No Cash App spend logged {label}. "
                f"Say 'Cash App 15 for lunch' or 'sync cash app' if Gmail is linked."
            )
        top = sorted(entries, key=lambda e: float(e.get("amount") or 0), reverse=True)[:4]
        bits = ", ".join(
            f"{e.get('note')} {cur} {float(e.get('amount') or 0):.2f}" for e in top
        )
        return f"Cash App {label}: {cur} {total:.2f}. Top: {bits}."

    def import_cash_app_messages(
        self,
        msgs: list[dict[str, Any]],
        *,
        source: str = "cash_app_email",
    ) -> tuple[int, int]:
        """Import parsed Cash App emails. Returns (added, skipped)."""
        added = 0
        skipped = 0
        for msg in msgs or []:
            parsed = self._parse_cashapp_email(msg)
            if not parsed:
                skipped += 1
                continue
            before = len(self._load().get("entries") or [])
            self.add(
                parsed["amount"],
                parsed["note"],
                source=source,
                method="cash_app",
                external_id=parsed["external_id"],
                day=parsed.get("day") or "",
            )
            after = len(self._load().get("entries") or [])
            if after > before:
                added += 1
            else:
                skipped += 1
        return added, skipped

    def sync_cash_app_from_gmail(
        self,
        gmail_search: Callable[[str, int], list[dict[str, Any]]],
        *,
        limit: int = 25,
    ) -> str:
        """Import Cash App payments from Gmail search callback."""
        try:
            msgs = gmail_search(_CASHAPP_GMAIL_Q, limit) or []
        except Exception as e:
            return f"Cash App Gmail sync failed: {e}"
        if not msgs:
            return (
                "No Cash App emails in Gmail. If receipts go to iCloud, "
                "link iCloud Mail and say sync cash app."
            )
        added, skipped = self.import_cash_app_messages(msgs, source="cash_app_gmail")
        return self._sync_result("Gmail", added, skipped)

    def sync_cash_app_from_icloud(
        self,
        fetch_msgs: Callable[[int], list[dict[str, Any]]],
        *,
        limit: int = 40,
    ) -> str:
        """Import Cash App payments from iCloud IMAP fetch callback."""
        try:
            msgs = fetch_msgs(limit) or []
        except Exception as e:
            return f"Cash App iCloud sync failed: {e}"
        if not msgs:
            return (
                "No Cash App emails found in iCloud Mail. "
                "Confirm receipts are enabled in Cash App for this Apple ID."
            )
        added, skipped = self.import_cash_app_messages(msgs, source="cash_app_icloud")
        return self._sync_result("iCloud", added, skipped)

    def _sync_result(self, source_label: str, added: int, skipped: int) -> str:
        week = self.total_method("cash_app", period="week")
        cur = self._load().get("currency") or "USD"
        return (
            f"Cash App sync via {source_label}: imported {added} new payment"
            f"{'s' if added != 1 else ''} "
            f"({skipped} skipped). This week on Cash App: {cur} {week:.2f}."
        )

    def stats_card(self) -> dict[str, Any]:
        methods_week = self.by_method(period="week")
        return {
            "today": self.total_today(),
            "week": self.total_week(),
            "month": self.total_month(),
            "cash_app_week": methods_week.get("cash_app", 0.0),
            "cash_app_today": self.total_method("cash_app", period="today"),
            "currency": self._load().get("currency") or "USD",
            "count_today": sum(
                1
                for e in self._load().get("entries") or []
                if e.get("day") == datetime.now().strftime("%Y-%m-%d")
            ),
            "by_method_week": methods_week,
        }

    # --- internals ---

    def _sum_days(self, days: set[str]) -> float:
        return round(
            sum(
                float(e.get("amount") or 0)
                for e in self._load().get("entries") or []
                if e.get("day") in days
            ),
            2,
        )

    def _period_days(self, period: str) -> set[str] | None:
        today = datetime.now().date()
        if period == "today":
            return {today.isoformat()}
        if period == "week":
            return {(today - timedelta(days=i)).isoformat() for i in range(7)}
        if period == "month":
            return None  # use prefix check
        return {today.isoformat()}

    def _entries_for_method(self, method: str, *, period: str) -> list[dict[str, Any]]:
        method_n = self._norm_method(method)
        days = self._period_days(period)
        month_prefix = datetime.now().strftime("%Y-%m")
        out = []
        for e in self._load().get("entries") or []:
            m = self._norm_method(e.get("method") or "")
            if m != method_n:
                blob = f"{e.get('note','')} {e.get('source','')}".lower()
                cashish = (
                    "cash app" in blob
                    or "cashapp" in blob
                    or "cash_app" in blob
                    or "cash_app_email" in blob
                )
                if method_n != "cash_app" or not cashish:
                    continue
            day = str(e.get("day") or "")
            if period == "month":
                if not day.startswith(month_prefix):
                    continue
            elif days is not None and day not in days:
                continue
            out.append(e)
        return out

    @staticmethod
    def _norm_method(method: str) -> str:
        m = (method or "").strip().lower().replace(" ", "_").replace("-", "_")
        if m in ("cashapp", "cash_app", "cash"):
            if m == "cash":
                return "cash"
            return "cash_app"
        if m in ("card", "debit", "credit", "visa", "mastercard"):
            return "card"
        if m in ("venmo", "zelle", "paypal", "apple_pay", "applepay"):
            return m.replace("applepay", "apple_pay")
        return m

    @staticmethod
    def _infer_method(note: str, source: str = "") -> str:
        blob = f"{note} {source}".lower()
        if "cash app" in blob or "cashapp" in blob or "cash_app" in blob:
            return "cash_app"
        if "venmo" in blob:
            return "venmo"
        if "zelle" in blob:
            return "zelle"
        if "card" in blob or "visa" in blob:
            return "card"
        return ""

    @staticmethod
    def _parse_cashapp_email(msg: dict[str, Any]) -> dict[str, Any] | None:
        subject = str(msg.get("subject") or "")
        snippet = str(msg.get("snippet") or "")
        mid = str(msg.get("id") or "")
        blob = f"{subject} {snippet}"
        # You paid/sent/spent $12.00 to/at Name
        m = re.search(
            r"(?:you\s+(?:paid|sent|spent)|payment\s+of|sent)\s*\$?\s*(\d+(?:\.\d{1,2})?)",
            blob,
            re.I,
        )
        if not m:
            m = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", blob)
        if not m:
            return None
        amount = float(m.group(1))
        if amount <= 0:
            return None
        note = "cash app"
        to_m = re.search(
            r"(?:to|for|at)\s+([A-Za-z0-9 ._'&-]{2,60})",
            subject,
            re.I,
        )
        if to_m:
            note = to_m.group(1).strip(" .,-")[:80] or note
        day = ""
        try:
            ms = int(msg.get("internalDate") or 0)
            if ms:
                day = datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d")
        except Exception:
            day = ""
        return {
            "amount": amount,
            "note": note,
            "external_id": (
                mid
                if mid.startswith(("icloud:", "gmail:", "cashapp:"))
                else (f"gmail:{mid}" if mid else f"cashapp:{subject[:40]}:{amount}")
            ),
            "day": day,
        }

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(SPEND_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"currency": "USD", "entries": []}

    def _save(self, data: dict[str, Any]) -> None:
        SPEND_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

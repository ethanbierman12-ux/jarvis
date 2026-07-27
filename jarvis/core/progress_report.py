"""Unified progress brief — spend, Cash App, tasks, habits, app scores."""

from __future__ import annotations

from typing import Any


class ProgressReport:
    def __init__(
        self,
        *,
        spend=None,
        habits=None,
        brief=None,
        steward=None,
        cloud=None,
    ) -> None:
        self.spend = spend
        self.habits = habits
        self.brief = brief
        self.steward = steward
        self.cloud = cloud

    def speak(self, *, include_day: bool = True) -> str:
        parts: list[str] = ["Here's your progress brief."]

        # Spend + Cash App
        if self.spend:
            try:
                card = self.spend.stats_card()
                cur = card.get("currency") or "USD"
                parts.append(
                    f"Spending — today {cur} {float(card.get('today') or 0):.2f}, "
                    f"week {cur} {float(card.get('week') or 0):.2f}, "
                    f"month {cur} {float(card.get('month') or 0):.2f}."
                )
                cash_w = float(card.get("cash_app_week") or 0)
                cash_t = float(card.get("cash_app_today") or 0)
                if cash_w or cash_t:
                    parts.append(
                        f"Cash App — today {cur} {cash_t:.2f}, "
                        f"this week {cur} {cash_w:.2f}."
                    )
                else:
                    parts.append(
                        "No Cash App spend logged yet — say Cash App 20 for lunch, "
                        "or sync cash app after linking iCloud Mail."
                    )
            except Exception:
                pass

        # Tasks
        open_tasks: list[str] = []
        if self.brief:
            try:
                raw = self.brief._load_tasks()
                open_tasks = list(raw.get("open") or [])
            except Exception:
                open_tasks = []
        if open_tasks:
            top = "; ".join(open_tasks[:3])
            parts.append(f"{len(open_tasks)} open task{'s' if len(open_tasks) != 1 else ''}: {top}.")
        else:
            parts.append("Task list is clear.")

        # Habits / day
        if include_day and self.habits:
            try:
                cal = ""
                if self.brief:
                    try:
                        cal = self.brief.schedule_only()
                    except Exception:
                        cal = ""
                day = self.habits.tell_me_about_my_day(cal)
                # Keep it short — drop the long preamble if already said progress
                if day.startswith("Here is your day read"):
                    day = day.split(".", 1)[-1].strip()
                if day:
                    parts.append(day)
            except Exception:
                pass

        # Steward
        if self.steward:
            try:
                sc = self.steward.stats_card()
                done = int(sc.get("done_today") or 0)
                queued = int(sc.get("queued") or 0)
                if done or queued:
                    parts.append(
                        f"Away steward — {done} done today, {queued} queued."
                    )
            except Exception:
                pass

        # App scores
        try:
            from jarvis.core import app_scores

            board = app_scores.leaderboard(3)
            if board:
                top = board[0]
                parts.append(
                    f"App scoreboard leader: {top['title']} with "
                    f"{top['total_points']} points."
                )
        except Exception:
            pass

        return " ".join(p for p in parts if p).strip()

    def stats_card(self) -> dict[str, Any]:
        card: dict[str, Any] = {}
        if self.spend:
            try:
                card["spend"] = self.spend.stats_card()
            except Exception:
                pass
        return card

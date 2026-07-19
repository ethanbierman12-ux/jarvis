"""Wake / command-center briefing — premium morning & return stats."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


class WakeBrief:
    def __init__(
        self,
        *,
        spend=None,
        steward=None,
        habits=None,
        brief=None,
        feed=None,
        system=None,
    ) -> None:
        self.spend = spend
        self.steward = steward
        self.habits = habits
        self.brief = brief
        self.feed = feed
        self.system = system

    def compose(self, *, mode: str = "wake") -> dict[str, Any]:
        """
        Returns {speak, feed_lines, stats} for HUD + TTS.
        mode: wake | return | stats
        """
        spend_card = self.spend.stats_card() if self.spend else {"today": 0, "week": 0, "currency": "USD"}
        steward_card = self.steward.stats_card() if self.steward else {}
        open_tasks = 0
        if self.brief:
            try:
                raw = self.brief._load_tasks()
                open_tasks = len(raw.get("open") or [])
            except Exception:
                open_tasks = 0

        cpu = ram = None
        if self.system:
            try:
                tel = self.system.telemetry()
                cpu = getattr(tel, "cpu", None)
                ram = getattr(tel, "memory", None)
            except Exception:
                pass

        stats = {
            "spent_today": spend_card.get("today", 0),
            "spent_week": spend_card.get("week", 0),
            "currency": spend_card.get("currency", "USD"),
            "open_tasks": open_tasks,
            "steward_done": steward_card.get("done_today", 0),
            "steward_queued": steward_card.get("queued", 0),
            "away_mode": steward_card.get("away_mode", False),
            "cpu": cpu,
            "ram": ram,
            "updated": datetime.now().strftime("%H:%M"),
        }

        cur = stats["currency"]
        speak_parts: list[str] = []
        if mode == "wake":
            speak_parts.append("All systems are online.")
        elif mode == "return":
            speak_parts.append("Welcome back, Sir. Here is your desk brief.")
        else:
            speak_parts.append("Here is your current status overview.")

        speak_parts.append(
            f"You have spent {cur} {stats['spent_today']:.2f} today, "
            f"and {cur} {stats['spent_week']:.2f} this week."
        )
        if open_tasks:
            speak_parts.append(
                f"There {'are' if open_tasks != 1 else 'is'} {open_tasks} open "
                f"task{'s' if open_tasks != 1 else ''} remaining."
            )
        if stats["steward_done"] or stats["steward_queued"]:
            speak_parts.append(
                f"While away, I completed {stats['steward_done']} job"
                f"{'s' if stats['steward_done'] != 1 else ''}, "
                f"with {stats['steward_queued']} still queued."
            )
        mail_line = ""
        try:
            from jarvis.core.mail_agent import MailAgent

            mail_line = MailAgent(user_name="Sir", mode="ack").speak_summary()
            if mail_line and "No mail activity" not in mail_line:
                speak_parts.append(mail_line)
        except Exception:
            mail_line = ""
        if cpu is not None and ram is not None:
            speak_parts.append(
                f"System load is at {cpu:.0f} percent CPU and {ram:.0f} percent memory."
            )

        feed_lines = [
            f"Spend today · {cur} {stats['spent_today']:.2f}",
            f"Spend week · {cur} {stats['spent_week']:.2f}",
            f"Open tasks · {open_tasks}",
            f"Steward · {stats['steward_done']} done / {stats['steward_queued']} queued",
        ]
        if mail_line and "No mail activity" not in mail_line:
            feed_lines.insert(0, f"Mail · {mail_line[:110]}")
        if self.feed:
            for line in self.feed.lines_for_ui(6):
                feed_lines.append(line)

        return {"speak": " ".join(speak_parts), "feed_lines": feed_lines, "stats": stats}

    def apply_pending_steward(self, payload: dict[str, Any]) -> tuple[list[str], list[str]]:
        """
        Process steward pending_wake items.
        Returns (speak_lines, commands_to_run).
        """
        speak: list[str] = []
        commands: list[str] = []
        for item in payload.get("pending") or []:
            typ = item.get("type")
            if typ == "speak" and item.get("text"):
                speak.append(str(item["text"]))
            elif typ == "command" and item.get("command"):
                commands.append(str(item["command"]))
            elif typ == "feed" and self.feed and item.get("text"):
                self.feed.push(str(item.get("kind") or "steward"), str(item["text"]))
        # Recent result headlines
        for r in (payload.get("results") or [])[-4:]:
            if self.feed and r.get("result"):
                self.feed.push("steward", f"{r.get('label') or r.get('kind')}: {r.get('result')}")
        return speak, commands

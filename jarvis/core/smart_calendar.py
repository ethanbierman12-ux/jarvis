"""Smart calendar — parse spoken slots and write local ICS (Google-ready)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path


class SmartCalendar:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir) / "calendar"
        self.dir.mkdir(parents=True, exist_ok=True)

    def parse_when(self, text: str, *, now: datetime | None = None) -> datetime | None:
        """Parse phrases like 'next Tuesday at 3' / 'tomorrow at 15:00'."""
        now = now or datetime.now()
        t = (text or "").lower()
        # tomorrow
        base = now
        m_tod = re.search(
            r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t
        )
        hour, minute = 9, 0
        if m_tod:
            hour = int(m_tod.group(1))
            minute = int(m_tod.group(2) or 0)
            ap = (m_tod.group(3) or "").lower()
            if ap == "pm" and hour < 12:
                hour += 12
            if ap == "am" and hour == 12:
                hour = 0
            if not ap and hour <= 7:
                # bare "at 3" → 15:00 heuristic for afternoon meetings
                hour += 12

        if "tomorrow" in t:
            base = now + timedelta(days=1)
        else:
            m_next = re.search(
                r"\bnext\s+"
                r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                t,
            )
            if m_next:
                target = [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                ].index(m_next.group(1))
                days = (target - now.weekday() + 7) % 7
                if days == 0:
                    days = 7
                base = now + timedelta(days=days)
            else:
                m_day = re.search(
                    r"\bon\s+"
                    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                    t,
                )
                if m_day:
                    target = [
                        "monday",
                        "tuesday",
                        "wednesday",
                        "thursday",
                        "friday",
                        "saturday",
                        "sunday",
                    ].index(m_day.group(1))
                    days = (target - now.weekday() + 7) % 7
                    if days == 0:
                        days = 7
                    base = now + timedelta(days=days)

        if not m_tod and "tomorrow" not in t and "next" not in t and "on " not in t:
            return None
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def extract_title(self, text: str) -> str:
        t = re.sub(
            r"\b(schedule|add|create|put|book|remind me|set)\b",
            "",
            text,
            flags=re.I,
        )
        t = re.sub(
            r"\b(next|on|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
            r"at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|calendar|meeting|event)\b",
            "",
            t,
            flags=re.I,
        )
        title = re.sub(r"\s+", " ", t).strip(" .,")
        return title[:80] or "Jarvis event"

    def schedule(self, text: str) -> str:
        when = self.parse_when(text)
        if not when:
            return (
                "I couldn't parse a time. Try: schedule design review next Tuesday at 3."
            )
        title = self.extract_title(text)
        end = when + timedelta(hours=1)
        uid = str(uuid.uuid4())
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        ics = (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Jarvis//EN\nBEGIN:VEVENT\n"
            f"UID:{uid}\nDTSTAMP:{stamp}\n"
            f"DTSTART:{when.strftime('%Y%m%dT%H%M%S')}\n"
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}\n"
            f"SUMMARY:{title}\n"
            "DESCRIPTION:Created by Jarvis smart calendar\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        path = self.dir / f"event_{when.strftime('%Y%m%d_%H%M')}.ics"
        path.write_text(ics, encoding="utf-8")
        # Try open with default calendar app on Windows
        try:
            import os

            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception:
            pass
        return (
            f"Scheduled “{title}” for {when.strftime('%A %b %d at %I:%M %p').lstrip('0')}. "
            f"ICS saved — import to Google Calendar if it didn't open."
        )

"""Daily brief — calendar + email + local tasks summary."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

SCHEDULE_PATH = DATA_DIR / "schedule.json"
TASKS_PATH = DATA_DIR / "tasks.json"


def _ensure_defaults() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SCHEDULE_PATH.exists():
        today = datetime.now().strftime("%Y-%m-%d")
        SCHEDULE_PATH.write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "date": today,
                            "time": "09:00",
                            "title": "Morning focus block",
                            "type": "task",
                        },
                        {
                            "date": today,
                            "time": "14:00",
                            "title": "Check email and messages",
                            "type": "email",
                        },
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    if not TASKS_PATH.exists():
        TASKS_PATH.write_text(
            json.dumps(
                {
                    "open": [
                        "Review project priorities",
                        "Clear inbox to zero if possible",
                    ],
                    "done_today": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


class DailyBrief:
    def __init__(self) -> None:
        _ensure_defaults()

    def summarize(self, *, open_inbox: bool = True, weather_line: str = "") -> str:
        """Build a spoken daily brief from Outlook (if any) + local schedule/tasks."""
        now = datetime.now()
        parts: list[str] = [
            f"Daily brief for {now.strftime('%A, %B %d')}."
        ]

        if weather_line:
            parts.append(weather_line)

        outlook = self._outlook_today()
        if outlook:
            parts.append("Calendar: " + outlook)
        else:
            local = self._local_events_today()
            if local:
                parts.append("Calendar: " + local)
            else:
                parts.append("No meetings on the local calendar for today.")

        tasks = self._tasks_line()
        if tasks:
            parts.append(tasks)

        mail = self._mail_hint()
        if mail:
            parts.append(mail)

        if open_inbox:
            self._open_mail_surface()

        return " ".join(parts)

    def morning_standup(
        self,
        *,
        weather_line: str = "",
        extra: list[str] | None = None,
        open_inbox: bool = False,
    ) -> str:
        """Structured 6AM-style briefing for 'good morning'."""
        base = self.summarize(open_inbox=open_inbox, weather_line=weather_line)
        bits = [base]
        if extra:
            bits.extend(extra)
        bits.append("Say 'start work' when you are ready to engage.")
        return " ".join(bits)

    def schedule_only(self) -> str:
        outlook = self._outlook_today()
        if outlook:
            return "Your schedule: " + outlook
        local = self._local_events_today()
        if local:
            return "Your schedule: " + local
        return (
            "I do not see meetings for today. "
            f"Add events in {SCHEDULE_PATH.name}, or connect Outlook."
        )

    def add_task(self, text: str) -> str:
        data = self._load_tasks()
        data.setdefault("open", []).append(text.strip())
        self._save_tasks(data)
        return f"Added task: {text.strip()}"

    def complete_task(self, text: str) -> str:
        data = self._load_tasks()
        open_tasks = data.get("open") or []
        match = None
        low = text.lower()
        for t in list(open_tasks):
            if low in t.lower() or t.lower() in low:
                match = t
                break
        if match:
            open_tasks.remove(match)
            data["open"] = open_tasks
            data.setdefault("done_today", []).append(match)
            self._save_tasks(data)
            return f"Marked done: {match}"
        return f"Could not find task matching '{text}'."

    def _local_events_today(self) -> str:
        try:
            raw = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return ""
        today = datetime.now().strftime("%Y-%m-%d")
        events = [
            e
            for e in raw.get("events", [])
            if str(e.get("date", "")) == today
        ]
        events.sort(key=lambda e: str(e.get("time", "99:99")))
        if not events:
            # also include next 24h window by date tomorrow morning items
            return ""
        bits = [f"{e.get('time', '?')} {e.get('title', 'event')}" for e in events[:6]]
        return "; ".join(bits) + "."

    def _outlook_today(self) -> str:
        """Best-effort Outlook calendar via PowerShell COM (no extra pip deps)."""
        ps = r"""
$ErrorActionPreference = 'Stop'
try {
  $ol = New-Object -ComObject Outlook.Application
  $ns = $ol.GetNamespace('MAPI')
  $cal = $ns.GetDefaultFolder(9)
  $start = (Get-Date).Date
  $end = $start.AddDays(1)
  $filter = "[Start] >= '" + $start.ToString('g') + "' AND [Start] < '" + $end.ToString('g') + "'"
  $items = $cal.Items
  $items.IncludeRecurrences = $true
  $items.Sort('[Start]')
  $restrict = $items.Restrict($filter)
  $out = @()
  foreach ($it in $restrict) {
    if ($null -eq $it.Subject) { continue }
    $out += ($it.Start.ToString('HH:mm') + ' ' + $it.Subject)
    if ($out.Count -ge 6) { break }
  }
  if ($out.Count -eq 0) { '' } else { ($out -join '; ') + '.' }
} catch {
  ''
}
"""
        try:
            from jarvis.core.win_process import powershell_hidden

            out = powershell_hidden(ps, text=True, timeout=12)
            return (out or "").strip()
        except Exception:
            return ""

    def _tasks_line(self) -> str:
        data = self._load_tasks()
        open_tasks = data.get("open") or []
        done = data.get("done_today") or []
        bits = []
        if open_tasks:
            bits.append("Open tasks: " + "; ".join(open_tasks[:5]) + ".")
        if done:
            bits.append(f"Already done today: {len(done)}.")
        return " ".join(bits)

    def _mail_hint(self) -> str:
        # We cannot read Gmail without OAuth; nudge + open
        return "I am opening your mail so you can clear urgent messages."

    def _open_mail_surface(self) -> None:
        # Prefer Outlook if installed, else Gmail
        outlook = Path(r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE")
        alt = Path(os_path_appdata_outlook())
        try:
            if outlook.exists():
                subprocess.Popen([str(outlook)], shell=False)
                return
            if alt.exists():
                subprocess.Popen([str(alt)], shell=False)
                return
        except Exception:
            pass
        try:
            import webbrowser

            webbrowser.open("https://mail.google.com")
        except Exception:
            pass

    def _load_tasks(self) -> dict[str, Any]:
        _ensure_defaults()
        try:
            return json.loads(TASKS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"open": [], "done_today": []}

    def _save_tasks(self, data: dict[str, Any]) -> None:
        TASKS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def os_path_appdata_outlook() -> str:
    import os

    return str(Path(os.environ.get("LOCALAPPDATA", "")) / r"Microsoft\Outlook\OUTLOOK.EXE")

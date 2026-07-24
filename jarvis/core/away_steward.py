"""Away steward — queue work for while you're gone / Jarvis UI is offline."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

QUEUE_PATH = DATA_DIR / "away_queue.json"
RESULTS_PATH = DATA_DIR / "steward_results.json"
STATUS_PATH = DATA_DIR / "steward_status.json"
WEATHER_CACHE = DATA_DIR / "weather_cache.json"


class AwaySteward:
    """
    Persist jobs the offline steward_agent can run without the HUD.
    Results are drained when Jarvis wakes.
    """

    JOB_KINDS = (
        "weather_cache",
        "system_pulse",
        "prep_brief",
        "chrome_digest",
        "spend_digest",
        "speak_on_wake",
        "run_on_wake",
        "heartbeat",
        "mail_watch",
        "calendar_watch",
        "quiet_hours",
        "lock_workstation",
    )

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for path, default in (
            (QUEUE_PATH, {"jobs": []}),
            (RESULTS_PATH, {"results": [], "pending_wake": []}),
            (STATUS_PATH, {"last_tick": None, "online": False}),
        ):
            if not path.exists():
                path.write_text(json.dumps(default, indent=2), encoding="utf-8")

    # ── enqueue (Jarvis online) ─────────────────────────────────
    def enqueue(self, kind: str, payload: dict | None = None, *, label: str = "") -> str:
        kind = (kind or "").strip().lower()
        if kind not in self.JOB_KINDS and kind != "custom":
            return f"Unknown away job '{kind}'."
        data = self._load(QUEUE_PATH)
        # Avoid stacking duplicate identical queued jobs
        for j in data.get("jobs") or []:
            if j.get("status") == "queued" and j.get("kind") == kind and not payload:
                return f"Already queued: {j.get('label') or kind}."
        job = {
            "id": f"j{int(time.time() * 1000)}",
            "kind": kind,
            "label": label or kind.replace("_", " "),
            "payload": payload or {},
            "created": datetime.now().isoformat(timespec="seconds"),
            "status": "queued",
        }
        data.setdefault("jobs", []).append(job)
        data["jobs"] = data["jobs"][-120:]
        self._save(QUEUE_PATH, data)
        return f"Queued while-away job: {job['label']}."

    def enqueue_from_utterance(self, text: str) -> str | None:
        t = (text or "").strip().lower()
        if not re_away(t):
            return None

        queued: list[str] = []
        if any(k in t for k in ("weather", "forecast", "rain")):
            queued.append(self.enqueue("weather_cache", label="Refresh weather cache"))
        if any(k in t for k in ("brief", "schedule", "calendar", "morning")):
            queued.append(self.enqueue("prep_brief", label="Prep morning brief"))
            if "calendar" in t or "meeting" in t:
                queued.append(self.enqueue("calendar_watch", label="Calendar watch"))
        if any(k in t for k in ("chrome", "browser", "history", "tabs")):
            queued.append(self.enqueue("chrome_digest", label="Chrome digest"))
        if any(k in t for k in ("spend", "spending", "money", "expense")):
            queued.append(self.enqueue("spend_digest", label="Spend digest"))
        if any(k in t for k in ("system", "pc status", "vitals", "pulse")):
            queued.append(self.enqueue("system_pulse", label="System pulse"))
        if any(
            k in t
            for k in (
                "email",
                "emails",
                "mail",
                "inbox",
                "reply",
                "answer mail",
                "answer email",
            )
        ):
            mode = "ack"
            if "draft" in t:
                mode = "draft"
            elif "auto" in t or "full" in t:
                mode = "auto"
            self._set_mail_prefs(enabled=True, mode=mode)
            queued.append(
                self.enqueue(
                    "mail_watch",
                    {"mode": mode},
                    label=f"Answer email ({mode})",
                )
            )
        if any(k in t for k in ("quiet", "focus assist", "do not disturb", "dnd")):
            queued.append(self.enqueue("quiet_hours", label="Enable quiet hours"))
        if any(k in t for k in ("lock", "secure")):
            queued.append(self.enqueue("lock_workstation", label="Lock workstation"))

        m = re.search(
            r"(?:remind me(?: when i(?:'m| am)? back)?|tell me(?: when i(?:'m| am)? back)?|"
            r"when i(?:'m| am)? back(?: say| tell me)?)\s+(.+)$",
            t,
        )
        if m:
            msg = m.group(1).strip(" .,")
            queued.append(
                self.enqueue("speak_on_wake", {"text": msg}, label="Wake reminder")
            )

        m2 = re.search(
            r"(?:when i(?:'m| am)? back|on wake|when jarvis (?:is )?online)\s+"
            r"(?:please\s+)?(?:run|do|execute)?\s*(.+)$",
            t,
        )
        if m2 and "remind" not in t:
            cmd = m2.group(1).strip(" .,")
            if cmd and not any(
                k in cmd
                for k in ("weather", "brief", "chrome", "spend", "system", "email", "mail")
            ):
                queued.append(
                    self.enqueue("run_on_wake", {"command": cmd}, label=f"Run: {cmd[:40]}")
                )

        if not queued:
            self._set_mail_prefs(enabled=True, mode="ack")
            queued.append(self.enqueue("weather_cache", label="Refresh weather cache"))
            queued.append(self.enqueue("prep_brief", label="Prep morning brief"))
            queued.append(self.enqueue("system_pulse", label="System pulse"))
            queued.append(self.enqueue("spend_digest", label="Spend digest"))
            queued.append(self.enqueue("mail_watch", {"mode": "ack"}, label="Answer email (ack)"))
            queued.append(self.enqueue("calendar_watch", label="Calendar watch"))
        return " ".join(queued)

    def mark_away_mode(self, active: bool = True, *, mail: bool = True, mail_mode: str = "ack") -> str:
        """Seed a standard away package + real-time mail watch."""
        status = self._load(STATUS_PATH)
        status["away_mode"] = active
        status["away_since"] = datetime.now().isoformat(timespec="seconds") if active else None
        if active and mail:
            status["mail_watch"] = True
            status["mail_mode"] = mail_mode if mail_mode in ("draft", "ack", "auto") else "ack"
        elif not active:
            status["mail_watch"] = False
        self._save(STATUS_PATH, status)
        if active:
            self.enqueue("heartbeat", label="Away heartbeat")
            self.enqueue("quiet_hours", label="Enable quiet hours")
            self.enqueue("weather_cache", label="Refresh weather cache")
            self.enqueue("system_pulse", label="System pulse")
            self.enqueue("prep_brief", label="Prep brief")
            self.enqueue("spend_digest", label="Spend digest")
            self.enqueue("calendar_watch", label="Calendar watch")
            if mail:
                self.enqueue(
                    "mail_watch",
                    {"mode": status.get("mail_mode", "ack")},
                    label=f"Answer email ({status.get('mail_mode', 'ack')})",
                )
            mode = status.get("mail_mode", "ack")
            return (
                f"Away mode on. I will watch your inbox in real time and "
                f"{'draft replies' if mode == 'draft' else 'send acknowledgments' if mode == 'ack' else 'auto-reply'} "
                f"via Outlook, plus weather, calendar, vitals, and spend. "
                f"Say 'away mail draft' or 'away mail auto' to change reply style."
            )
        return "Away mode off. Mail watch stopped."

    def set_mail_mode(self, mode: str) -> str:
        mode = (mode or "ack").lower().strip()
        if mode not in ("draft", "ack", "auto"):
            return "Choose draft, ack, or auto."
        self._set_mail_prefs(enabled=True, mode=mode)
        self.enqueue("mail_watch", {"mode": mode}, label=f"Answer email ({mode})")
        return (
            f"Away mail set to {mode}. "
            + {
                "draft": "I will prepare replies for your review.",
                "ack": "I will send short away acknowledgments.",
                "auto": "I will send fuller routine replies.",
            }[mode]
        )

    def _set_mail_prefs(self, *, enabled: bool, mode: str = "ack") -> None:
        status = self._load(STATUS_PATH)
        status["mail_watch"] = enabled
        status["mail_mode"] = mode
        self._save(STATUS_PATH, status)

    # ── drain on Jarvis wake ────────────────────────────────────
    def drain_wake_payload(self) -> dict[str, Any]:
        data = self._load(RESULTS_PATH)
        pending = list(data.get("pending_wake") or [])
        data["pending_wake"] = []
        self._save(RESULTS_PATH, data)
        status = self._load(STATUS_PATH)
        return {
            "pending": pending,
            "results": list(data.get("results") or [])[-12:],
            "last_tick": status.get("last_tick"),
            "jobs_done": status.get("jobs_done_today", 0),
            "away_mode": bool(status.get("away_mode")),
            "mail_watch": bool(status.get("mail_watch")),
            "mail_mode": status.get("mail_mode", "ack"),
        }

    def stats_card(self) -> dict[str, Any]:
        q = self._load(QUEUE_PATH)
        r = self._load(RESULTS_PATH)
        s = self._load(STATUS_PATH)
        queued = sum(1 for j in (q.get("jobs") or []) if j.get("status") == "queued")
        return {
            "queued": queued,
            "done_today": int(s.get("jobs_done_today") or 0),
            "last_tick": s.get("last_tick"),
            "away_mode": bool(s.get("away_mode")),
            "pending_wake": len(r.get("pending_wake") or []),
            "mail_watch": bool(s.get("mail_watch")),
            "mail_mode": s.get("mail_mode", "ack"),
        }

    def speak_offline_summary(self) -> str:
        card = self.stats_card()
        if not card["last_tick"] and card["done_today"] == 0:
            return "Offline steward has not run yet — install steward_agent for while-away work."
        bits = [
            f"Away steward completed {card['done_today']} job{'s' if card['done_today'] != 1 else ''} today."
        ]
        if card.get("mail_watch"):
            bits.append(f"Inbox watch was on ({card.get('mail_mode', 'ack')}).")
        if card["queued"]:
            bits.append(f"{card['queued']} still queued.")
        if card["last_tick"]:
            bits.append(f"Last offline tick {card['last_tick'][11:16]}.")
        try:
            from jarvis.core.mail_agent import MailAgent

            bits.append(MailAgent().speak_summary())
        except Exception:
            pass
        return " ".join(bits)

    # ── offline runner (called by steward_agent) ────────────────
    def tick_offline(self) -> list[str]:
        """Process queued jobs; while away, keep mail_watch hot every tick."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        status = self._load(STATUS_PATH)
        day = datetime.now().strftime("%Y-%m-%d")
        if status.get("jobs_day") != day:
            status["jobs_day"] = day
            status["jobs_done_today"] = 0

        data = self._load(QUEUE_PATH)
        jobs = data.get("jobs") or []

        # Real-time mail: always inject a mail_watch when away + mail_watch enabled
        if status.get("away_mode") and status.get("mail_watch", True):
            has_mail = any(
                j.get("status") == "queued" and j.get("kind") == "mail_watch" for j in jobs
            )
            if not has_mail:
                jobs.append(
                    {
                        "id": f"mail{int(time.time())}",
                        "kind": "mail_watch",
                        "label": "Realtime mail",
                        "payload": {"mode": status.get("mail_mode", "ack")},
                        "created": datetime.now().isoformat(timespec="seconds"),
                        "status": "queued",
                    }
                )

        if status.get("away_mode") and not any(j.get("status") == "queued" for j in jobs):
            jobs.append(
                {
                    "id": f"auto{int(time.time())}",
                    "kind": "system_pulse",
                    "label": "Auto pulse",
                    "payload": {},
                    "created": datetime.now().isoformat(timespec="seconds"),
                    "status": "queued",
                }
            )

        # Prefer mail_watch first for realtime feel
        jobs.sort(
            key=lambda j: (
                0 if j.get("kind") == "mail_watch" and j.get("status") == "queued" else 1,
                j.get("created") or "",
            )
        )

        done = 0
        for job in jobs:
            if job.get("status") != "queued":
                continue
            if done >= 4:
                break
            result = self._run_job(job)
            job["status"] = "done"
            job["finished"] = datetime.now().isoformat(timespec="seconds")
            job["result"] = result[:280]
            self._push_result(job, result)
            lines.append(f"{job.get('kind')}: {result[:140]}")
            done += 1
            status["jobs_done_today"] = int(status.get("jobs_done_today") or 0) + 1

        data["jobs"] = jobs[-120:]
        self._save(QUEUE_PATH, data)
        status["last_tick"] = datetime.now().isoformat(timespec="seconds")
        status["online"] = False
        self._save(STATUS_PATH, status)
        return lines

    def _run_job(self, job: dict[str, Any]) -> str:
        kind = job.get("kind")
        payload = job.get("payload") or {}
        try:
            if kind == "weather_cache":
                return self._job_weather()
            if kind == "system_pulse":
                return self._job_system()
            if kind == "prep_brief":
                return self._job_brief()
            if kind == "chrome_digest":
                return self._job_chrome()
            if kind == "spend_digest":
                return self._job_spend()
            if kind == "mail_watch":
                return self._job_mail(payload)
            if kind == "calendar_watch":
                return self._job_calendar()
            if kind == "quiet_hours":
                return self._job_quiet_hours()
            if kind == "lock_workstation":
                return self._job_lock()
            if kind == "speak_on_wake":
                text = str(payload.get("text") or "Welcome back.")
                self._pending_wake({"type": "speak", "text": text})
                return f"Wake note armed: {text[:80]}"
            if kind == "run_on_wake":
                cmd = str(payload.get("command") or "")
                self._pending_wake({"type": "command", "command": cmd})
                return f"Wake command armed: {cmd[:80]}"
            if kind == "heartbeat":
                return f"Heartbeat ok at {datetime.now().strftime('%H:%M')}"
            return f"Skipped unknown job {kind}"
        except Exception as e:
            return f"Failed: {e}"

    def _job_mail(self, payload: dict[str, Any]) -> str:
        try:
            from jarvis.core.mail_agent import MailAgent
            from jarvis.config import Settings

            s = Settings.load()
            mode = str(payload.get("mode") or getattr(s, "away_mail_mode", "ack") or "ack")
            agent = MailAgent(
                user_name=getattr(s, "user_name", "Sir"),
                mode=mode,
                max_per_tick=int(getattr(s, "away_mail_max_per_tick", 3) or 3),
            )
            result = agent.process_inbox(force_mode=mode)
            msg = result.get("message") or "Mail watch complete."
            if result.get("handled"):
                self._pending_wake(
                    {
                        "type": "speak",
                        "text": f"While you were away, I handled {result['handled']} email"
                        f"{'s' if result['handled'] != 1 else ''}.",
                    }
                )
            for item in result.get("items") or []:
                self._pending_wake(
                    {
                        "type": "feed",
                        "kind": "mail",
                        "text": f"{item.get('action')}: {item.get('from')} — {item.get('subject')}",
                    }
                )
            return msg
        except Exception as e:
            return f"Mail watch failed: {e}"

    def _job_calendar(self) -> str:
        try:
            from jarvis.core.daily_brief import DailyBrief

            text = DailyBrief().schedule_only()
            self._pending_wake({"type": "feed", "kind": "calendar", "text": text[:200]})
            path = DATA_DIR / "calendar_cache.txt"
            path.write_text(text, encoding="utf-8")
            return text[:180]
        except Exception as e:
            return f"Calendar watch failed: {e}"

    def _job_quiet_hours(self) -> str:
        # Never open ms-settings:quiethours — it steals focus while the user works
        return (
            "Quiet hours: skipped opening Windows Settings. "
            "Set Focus Assist manually if you want it."
        )

    def _job_lock(self) -> str:
        try:
            import ctypes

            ctypes.windll.user32.LockWorkStation()
            return "Workstation locked."
        except Exception as e:
            return f"Lock failed: {e}"

    def _job_weather(self) -> str:
        try:
            from jarvis.core.weather import Weather
            from jarvis.config import Settings

            s = Settings.load()
            wx = Weather(s.city or "Philadelphia", s.openweather_api_key or "")
            ctx = wx.context_block()
            WEATHER_CACHE.write_text(json.dumps(ctx, indent=2), encoding="utf-8")
            cond = ctx.get("condition") or ctx.get("summary") or "updated"
            temp = ctx.get("temp_c")
            if temp is not None:
                return f"Weather cached: {temp:.0f}° {cond}"
            return f"Weather cached: {cond}"
        except Exception as e:
            return f"Weather cache skipped: {e}"

    def _job_system(self) -> str:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0.3)
            ram = psutil.virtual_memory().percent
            bat = None
            try:
                b = psutil.sensors_battery()
                bat = None if b is None else int(b.percent)
            except Exception:
                pass
            snap = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "cpu": cpu,
                "ram": ram,
                "battery": bat,
            }
            path = DATA_DIR / "system_pulses.json"
            hist = []
            if path.exists():
                try:
                    hist = json.loads(path.read_text(encoding="utf-8")).get("pulses") or []
                except Exception:
                    hist = []
            hist.append(snap)
            path.write_text(json.dumps({"pulses": hist[-48:]}, indent=2), encoding="utf-8")
            bat_s = f", battery {bat}%" if bat is not None else ""
            return f"PC pulse CPU {cpu:.0f}% RAM {ram:.0f}%{bat_s}"
        except Exception as e:
            return f"System pulse failed: {e}"

    def _job_brief(self) -> str:
        try:
            from jarvis.core.daily_brief import DailyBrief

            text = DailyBrief().summarize(open_inbox=False)
            path = DATA_DIR / "prepared_brief.txt"
            path.write_text(text, encoding="utf-8")
            self._pending_wake({"type": "speak", "text": f"Prepared brief ready. {text[:180]}"})
            return "Morning brief prepared for wake."
        except Exception as e:
            return f"Brief prep failed: {e}"

    def _job_chrome(self) -> str:
        try:
            from jarvis.core.system_extras import ChromeHistory

            text = ChromeHistory().recent(hours=8)
            self._pending_wake({"type": "feed", "kind": "chrome", "text": text[:200]})
            return text[:160] or "No recent browser visits."
        except Exception as e:
            return f"Chrome digest failed: {e}"

    def _job_spend(self) -> str:
        try:
            from jarvis.core.spend import SpendTracker

            text = SpendTracker().speak_summary(period="today")
            self._pending_wake({"type": "feed", "kind": "spend", "text": text})
            return text
        except Exception as e:
            return f"Spend digest failed: {e}"

    def _pending_wake(self, item: dict[str, Any]) -> None:
        data = self._load(RESULTS_PATH)
        data.setdefault("pending_wake", []).append(
            {**item, "ts": datetime.now().isoformat(timespec="seconds")}
        )
        data["pending_wake"] = data["pending_wake"][-40:]
        self._save(RESULTS_PATH, data)

    def _push_result(self, job: dict[str, Any], result: str) -> None:
        data = self._load(RESULTS_PATH)
        data.setdefault("results", []).append(
            {
                "id": job.get("id"),
                "kind": job.get("kind"),
                "label": job.get("label"),
                "result": result,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
        )
        data["results"] = data["results"][-80:]
        data.setdefault("pending_wake", []).append(
            {
                "type": "feed",
                "kind": job.get("kind") or "steward",
                "text": result[:200],
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
        )
        self._save(RESULTS_PATH, data)

    def _load(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def re_away(t: str) -> bool:
    return bool(
        re.search(
            r"\b(while i(?:'m| am)? (?:away|gone)|when i(?:'m| am)? (?:away|gone)|"
            r"offline(?: mode)?|away mode|do (?:this|stuff) (?:while|when) i(?:'m| am)? away|"
            r"work (?:for me )?while i(?:'m| am)? away|steward|"
            r"answer (?:my )?(?:email|emails|mail)|handle (?:my )?inbox)\b",
            t,
        )
    )

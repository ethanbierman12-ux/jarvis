"""Timed reminders — local or remote timezone (e.g. California / Pacific)."""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR

REMINDERS_PATH = DATA_DIR / "reminders.json"

# Spoken place → IANA zone
_TZ_ALIASES: dict[str, str] = {
    # US West
    "california": "America/Los_Angeles",
    "cali": "America/Los_Angeles",
    "ca": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "l a": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "hollywood angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "sf": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "portland": "America/Los_Angeles",
    "vegas": "America/Los_Angeles",
    "las vegas": "America/Los_Angeles",
    "west coast": "America/Los_Angeles",
    # US Mountain / AZ
    "arizona": "America/Phoenix",
    "phoenix": "America/Phoenix",
    "denver": "America/Denver",
    "colorado": "America/Denver",
    "mountain": "America/Denver",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "utah": "America/Denver",
    "salt lake": "America/Denver",
    # US Central
    "chicago": "America/Chicago",
    "central": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "texas": "America/Chicago",
    "dallas": "America/Chicago",
    "houston": "America/Chicago",
    "austin": "America/Chicago",
    "midwest": "America/Chicago",
    # US East
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "eastern": "America/New_York",
    "east coast": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "philly": "America/New_York",
    "philadelphia": "America/New_York",
    "miami": "America/New_York",
    "florida": "America/New_York",
    "boston": "America/New_York",
    "atlanta": "America/New_York",
    "dc": "America/New_York",
    "washington dc": "America/New_York",
    # Canada
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
    # Europe
    "london": "Europe/London",
    "uk": "Europe/London",
    "britain": "Europe/London",
    "england": "Europe/London",
    "paris": "Europe/Paris",
    "france": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "germany": "Europe/Berlin",
    "rome": "Europe/Rome",
    "italy": "Europe/Rome",
    "madrid": "Europe/Madrid",
    "spain": "Europe/Madrid",
    "amsterdam": "Europe/Amsterdam",
    # Asia / Pacific
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore",
    "dubai": "Asia/Dubai",
    "india": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "australia": "Australia/Sydney",
    "auckland": "Pacific/Auckland",
    "new zealand": "Pacific/Auckland",
    # UTC
    "utc": "UTC",
    "gmt": "Etc/GMT",
    "zulu": "UTC",
}


@dataclass
class Reminder:
    id: str
    message: str
    fire_at: float  # unix epoch (UTC-based instant)
    timezone: str = "America/New_York"
    label_time: str = ""  # human: "10:00 PM Pacific"
    enabled: bool = True
    fired: bool = False
    created: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)


class ReminderService:
    """Background one-shot (and optional daily) reminders with zone support."""

    def __init__(
        self,
        *,
        default_tz: str = "America/New_York",
        on_fire: Callable[[Reminder], None] | None = None,
    ) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.default_tz = (default_tz or "America/New_York").strip()
        self.on_fire = on_fire
        self._items: dict[str, Reminder] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._load()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="jarvis-reminders"
        )
        self._thread.start()
        print(f"[reminders] watcher on ({len(self._items)} saved)")

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> str:
        pending = [r for r in self._items.values() if r.enabled and not r.fired]
        if not pending:
            return "No pending reminders."
        pending.sort(key=lambda r: r.fire_at)
        bits = []
        for r in pending[:8]:
            left = max(0, int(r.fire_at - time.time()))
            mins = left // 60
            bits.append(
                f"`{r.id}` {r.label_time or self._fmt_left(left)} — {r.message[:60]} "
                f"(in {mins}m)"
            )
        return "Reminders: " + "; ".join(bits)

    def list_pending(self) -> list[Reminder]:
        with self._lock:
            return sorted(
                [r for r in self._items.values() if r.enabled and not r.fired],
                key=lambda r: r.fire_at,
            )

    def cancel(self, hint: str = "") -> str:
        h = (hint or "").strip().lower()
        with self._lock:
            pending = [r for r in self._items.values() if r.enabled and not r.fired]
            if not pending:
                return "Nothing to cancel."
            if not h or h in ("all", "everything", "them"):
                for r in pending:
                    r.enabled = False
                self._save()
                return f"Cancelled {len(pending)} reminder(s)."
            # match id or message substring
            hits = [
                r
                for r in pending
                if h == r.id.lower() or h in (r.message or "").lower() or h in (r.label_time or "").lower()
            ]
            if not hits and h.isdigit():
                idx = int(h) - 1
                if 0 <= idx < len(pending):
                    hits = [pending[idx]]
            if not hits:
                return f"No reminder matched `{hint}`."
            for r in hits:
                r.enabled = False
            self._save()
            return f"Cancelled: {hits[0].message[:80]}"

    def add_from_utterance(self, text: str) -> str:
        """Parse voice/text and schedule. Returns spoken confirmation."""
        parsed = parse_reminder_utterance(text, default_tz=self.default_tz)
        if not parsed:
            return (
                "I couldn't parse that time. Try: "
                "remind me at 10 pm California to check on her — "
                "or remind me when it's 8 pm in Cali."
            )
        rem = Reminder(
            id=secrets.token_hex(3),
            message=parsed["message"],
            fire_at=float(parsed["fire_at"]),
            timezone=parsed["timezone"],
            label_time=parsed["label_time"],
            meta={"raw": (text or "")[:200]},
        )
        if rem.fire_at <= time.time() + 5:
            return (
                f"That time ({rem.label_time}) already passed today — "
                "say tomorrow if you meant the next one."
            )
        with self._lock:
            self._items[rem.id] = rem
            self._save()
        left = int(rem.fire_at - time.time())
        return (
            f"Got it. I'll remind you at {rem.label_time} — "
            f"“{rem.message}” — in about {self._fmt_left(left)}."
        )

    def _fmt_left(self, sec: int) -> str:
        if sec < 60:
            return f"{sec}s"
        if sec < 3600:
            return f"{sec // 60} minutes"
        h, m = divmod(sec // 60, 60)
        if m == 0:
            return f"{h} hour{'s' if h != 1 else ''}"
        return f"{h}h {m}m"

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                print(f"[reminders] tick: {e}")
            self._stop.wait(12.0)

    def _tick(self) -> None:
        now = time.time()
        due: list[Reminder] = []
        with self._lock:
            for r in self._items.values():
                if r.enabled and not r.fired and r.fire_at <= now:
                    r.fired = True
                    due.append(r)
            if due:
                self._save()
        for r in due:
            print(f"[reminders] FIRE {r.id}: {r.message}")
            if self.on_fire:
                try:
                    self.on_fire(r)
                except Exception as e:
                    print(f"[reminders] on_fire: {e}")

    def _load(self) -> None:
        try:
            raw = json.loads(REMINDERS_PATH.read_text(encoding="utf-8"))
            for row in raw.get("reminders") or []:
                r = Reminder(
                    id=str(row.get("id") or secrets.token_hex(3)),
                    message=str(row.get("message") or "Reminder"),
                    fire_at=float(row.get("fire_at") or 0),
                    timezone=str(row.get("timezone") or self.default_tz),
                    label_time=str(row.get("label_time") or ""),
                    enabled=bool(row.get("enabled", True)),
                    fired=bool(row.get("fired", False)),
                    created=float(row.get("created") or time.time()),
                    meta=row.get("meta") or {},
                )
                # Drop ancient fired ones
                if r.fired and now_age(r.fire_at) > 86400 * 3:
                    continue
                self._items[r.id] = r
        except Exception:
            self._items = {}

    def _save(self) -> None:
        blob = {"reminders": [asdict(r) for r in self._items.values()]}
        REMINDERS_PATH.write_text(json.dumps(blob, indent=2), encoding="utf-8")


def now_age(ts: float) -> float:
    return abs(time.time() - float(ts or 0))


def _zoneinfo(name: str):
    from zoneinfo import ZoneInfo

    return ZoneInfo(name)


def resolve_timezone(text: str, default_tz: str) -> tuple[str, str]:
    """Return (iana, short_label) from utterance."""
    t = (text or "").lower()
    # Prefer longer aliases first
    for alias in sorted(_TZ_ALIASES.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", t):
            iana = _TZ_ALIASES[alias]
            label = {
                "America/Los_Angeles": "Pacific / California",
                "America/Denver": "Mountain",
                "America/Chicago": "Central",
                "America/New_York": "Eastern",
                "America/Phoenix": "Arizona",
                "America/Toronto": "Toronto",
                "America/Vancouver": "Vancouver",
                "Europe/London": "London",
                "Europe/Paris": "Paris",
                "Europe/Berlin": "Berlin",
                "Europe/Rome": "Rome",
                "Europe/Madrid": "Madrid",
                "Europe/Amsterdam": "Amsterdam",
                "Asia/Tokyo": "Tokyo",
                "Asia/Seoul": "Seoul",
                "Asia/Shanghai": "China",
                "Asia/Hong_Kong": "Hong Kong",
                "Asia/Singapore": "Singapore",
                "Asia/Dubai": "Dubai",
                "Asia/Kolkata": "India",
                "Australia/Sydney": "Sydney",
                "Australia/Melbourne": "Melbourne",
                "Pacific/Auckland": "New Zealand",
                "UTC": "UTC",
                "Etc/GMT": "GMT",
            }.get(iana, alias.title())
            return iana, label
    return (default_tz or "America/New_York"), "local"


def speak_time_in(text: str = "", *, default_tz: str = "America/New_York") -> str:
    """Answer 'what time is it in Cali' style questions."""
    from datetime import datetime

    t = (text or "").lower().strip()
    # Explicit "in <place>" or known alias anywhere in the phrase
    has_elsewhere = bool(
        re.search(r"\b(in|for|over in|out in)\b", t)
        or any(re.search(rf"\b{re.escape(a)}\b", t) for a in _TZ_ALIASES)
    )
    if has_elsewhere:
        iana, label = resolve_timezone(t, default_tz)
        # If they said "in …" but we only got default, still try hard
        if label == "local" and re.search(r"\bin\b", t):
            m = re.search(r"\bin\s+([a-z][a-z\s]{1,40}?)\s*$", t)
            if m:
                iana, label = resolve_timezone(m.group(1), default_tz)
    else:
        iana = (default_tz or "America/New_York").strip() or "America/New_York"
        label = "local"

    try:
        now = datetime.now(_zoneinfo(iana))
    except Exception:
        now = datetime.now(_zoneinfo(default_tz or "America/New_York"))
        iana = default_tz or "America/New_York"
        label = "local"

    clock = now.strftime("%I:%M %p").lstrip("0")
    day = now.strftime("%A, %B %d")
    # Offset vs Eastern for quick compare when remote
    extra = ""
    try:
        if iana not in ("America/New_York", default_tz):
            east = datetime.now(_zoneinfo("America/New_York"))
            # Same "instant" — show East clock too
            extra = f" Back East it's {east.strftime('%I:%M %p').lstrip('0')}."
    except Exception:
        pass
    if label == "local":
        return f"It's {clock} on {day}."
    return f"In {label} it's {clock} on {day}.{extra}"


def parse_hour_minute(text: str) -> tuple[int, int] | None:
    t = (text or "").lower()
    # 10 pm / 10:30pm / 8 p.m. / 20:00
    m = re.search(
        r"\b(?:at\s+|when\s+it(?:'s| is)\s+|when\s+it\s+turns\s+)?"
        r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b",
        t,
    )
    if not m:
        m = re.search(r"\b(\d{1,2})(?::(\d{2}))\b", t)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ap = (m.group(3) or "").lower().replace(".", "") if m.lastindex and m.lastindex >= 3 else ""
    if ap.startswith("p") and hour < 12:
        hour += 12
    if ap.startswith("a") and hour == 12:
        hour = 0
    # Bare "at 8" / "at 10" in evening-reminder context → PM if 1–11
    if not ap and 1 <= hour <= 11 and re.search(
        r"\b(tonight|evening|night|pm|cali|california|pacific)\b", t
    ):
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def extract_message(text: str) -> str:
    t = text or ""
    # "to call her" / "that she's camping"
    m = re.search(
        r"\b(?:to|that|about)\s+(.+)$",
        t,
        flags=re.I,
    )
    if m:
        msg = m.group(1).strip(" .,!")
        # strip trailing timezone crumbs
        msg = re.sub(
            r"\b(in\s+)?(california|cali|pacific|pst|pdt|ca)\b",
            "",
            msg,
            flags=re.I,
        ).strip(" .,!")
        if len(msg) >= 2:
            return msg[:160]
    return "Check in — California time reminder"


def parse_reminder_utterance(
    text: str, *, default_tz: str = "America/New_York"
) -> dict[str, Any] | None:
    """
    Examples:
      remind me at 10 pm California to call her
      remind me when it's 8 pm in Cali
      set a reminder for 10pm pacific that she's camping
      remind me at 8 california time
    """
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    if not re.search(r"\b(remind|reminder|alarm|nudge)\b", low):
        return None
    # Must look like a timed reminder, not "remind me that my password is X"
    if not re.search(
        r"\b(at\s+\d|when\s+it|turns?\s+\d|\d{1,2}\s*(:\d{2})?\s*(a\.?m\.?|p\.?m\.?)|"
        r"california|cali|pacific|tonight)\b",
        low,
    ):
        return None

    tz, tz_label = resolve_timezone(t, default_tz)
    hm = parse_hour_minute(t)
    if not hm:
        return None
    hour, minute = hm
    try:
        z = _zoneinfo(tz)
    except Exception:
        z = _zoneinfo(default_tz)
        tz = default_tz
        tz_label = "local"

    now = datetime.now(z)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "tomorrow" in low:
        target = target + timedelta(days=1)
    elif target <= now + timedelta(seconds=30):
        target = target + timedelta(days=1)

    msg = extract_message(t)
    if msg.lower() in ("check in — california time reminder", "reminder") or len(msg) < 3:
        if "camp" in low:
            msg = "She's camping — check in / call time"
        elif tz_label == "Pacific":
            msg = f"California is {hour % 12 or 12}:{minute:02d} {'PM' if hour >= 12 else 'AM'}"
        else:
            msg = f"Reminder — {tz_label} time"

    ampm = "PM" if hour >= 12 else "AM"
    h12 = hour % 12 or 12
    label = f"{h12}:{minute:02d} {ampm} {tz_label}"
    # Also show user's eastern wall clock for clarity
    try:
        east = target.astimezone(_zoneinfo("America/New_York"))
        eh = east.hour % 12 or 12
        eampm = "PM" if east.hour >= 12 else "AM"
        label = f"{label} (your time {eh}:{east.minute:02d} {eampm} ET)"
    except Exception:
        pass

    return {
        "message": msg,
        "fire_at": target.timestamp(),
        "timezone": tz,
        "label_time": label,
    }

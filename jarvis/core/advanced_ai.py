"""Advanced AI pack — conversational brain, memory window, live roast context,
room presence, energy guard, guest mode, tab commentary, cinematic morning brief.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR
from jarvis.core import llm_client
from jarvis.core.personality import SYSTEM_PROMPT, Personality

CONV_PATH = DATA_DIR / "conversation_memory.jsonl"
CORRECTIONS_PATH = DATA_DIR / "self_corrections.jsonl"
PRESENCE_PATH = DATA_DIR / "room_presence.json"
ENERGY_PATH = DATA_DIR / "energy_guard.json"
QUOTES = (
    "The best way to predict the future is to invent it. — Alan Kay",
    "Stay hungry, stay foolish. — Steve Jobs",
    "Done is better than perfect. — Sheryl Sandberg",
    "Make it work, make it right, make it fast. — Kent Beck",
    "Simplicity is the ultimate sophistication. — Leonardo da Vinci",
    "Scientia potentia est — knowledge is power. Use it before coffee wears off.",
)


class ConversationMemory:
    """Short-term turn window (last N messages) for ask-me-anything brain."""

    def __init__(self, max_turns: int = 8) -> None:
        self.max_turns = max(2, min(20, int(max_turns)))
        self._turns: deque[dict[str, str]] = deque(maxlen=self.max_turns * 2)

    def add(self, role: str, content: str) -> None:
        text = (content or "").strip()[:1200]
        if not text:
            return
        self._turns.append({"role": role, "content": text})
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with CONV_PATH.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {"ts": time.time(), "role": role, "content": text[:400]},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass

    def window_text(self) -> str:
        return "\n".join(f"{t['role'].upper()}: {t['content']}" for t in self._turns)

    def clear(self) -> str:
        self._turns.clear()
        return "Short-term conversation slate cleared, Sir."


class LiveContext:
    """Inject calendar / tabs / home / time into the sarcastic system prompt."""

    def __init__(self, brain: Any) -> None:
        self.brain = brain

    def build(self) -> str:
        bits: list[str] = []
        now = datetime.now()
        bits.append(f"Current local time: {now.strftime('%A %H:%M')}.")
        try:
            brief = getattr(self.brain, "brief", None)
            if brief:
                cal = brief._outlook_today() if hasattr(brief, "_outlook_today") else ""
                if not cal and hasattr(brief, "_local_events_today"):
                    cal = brief._local_events_today()
                if cal:
                    bits.append(f"Calendar today: {cal[:240]}")
        except Exception:
            pass
        try:
            screen = getattr(self.brain, "screen", None) or getattr(
                self.brain, "screen_context", None
            )
            if screen:
                raw = []
                if hasattr(screen, "visible_browser_tabs"):
                    raw = screen.visible_browser_tabs() or []
                elif hasattr(screen, "chrome_open_tabs"):
                    raw = screen.chrome_open_tabs() or []
                titles = [str(t.get("title") or t)[:60] for t in raw[:8]]
                if titles:
                    bits.append("Open browser tabs: " + "; ".join(titles))
        except Exception:
            pass
        try:
            ha = getattr(self.brain, "ha", None)
            if ha and getattr(ha, "enabled", False):
                bits.append(f"Home Assistant online at {getattr(ha, 'url', 'HA')}.")
        except Exception:
            pass
        try:
            room = getattr(self.brain, "advanced", None)
            if room and getattr(room, "presence", None):
                bits.append(f"User room: {room.presence.current_room()}.")
        except Exception:
            pass
        return "\n".join(bits)


class AskAnythingBrain:
    """Route free-form questions through LLM with personality + STM + live context."""

    def __init__(self, brain: Any, personality: Personality | None = None) -> None:
        self.brain = brain
        self.personality = personality or getattr(brain, "persona", None) or Personality()
        self.memory = ConversationMemory(
            max_turns=int(getattr(brain.settings, "chat_memory_turns", 8) or 8)
        )
        self.live = LiveContext(brain)

    def system(self) -> str:
        base = self.personality.system_prompt()
        live = self.live.build()
        rules = (
            "\n\nCRITICAL RULES:\n"
            "- Do not repeat phrases, greetings, or jokes used earlier in this conversation.\n"
            "- Keep responses tight, punchy, and dry. Prefer under 40 spoken words.\n"
            "- If you have nothing new to add, acknowledge briefly (Acknowledged. / On it.) and stop.\n"
            "- Use live context below for accurate sarcasm grounded in reality.\n"
        )
        return f"{base}{rules}\n\nLIVE CONTEXT:\n{live or 'No extra telemetry.'}"

    def ask(self, user_text: str) -> str:
        q = (user_text or "").strip()
        if not q:
            return "I'm listening, Sir — try a complete thought."
        # Long-term memory recall
        recall = ""
        try:
            vs = getattr(self.brain, "vstore", None)
            if vs:
                hits = vs.recall(q, k=3) if hasattr(vs, "recall") else []
                if isinstance(hits, list) and hits:
                    recall = " | ".join(str(h)[:120] for h in hits[:3])
                elif isinstance(hits, str) and hits:
                    recall = hits[:360]
        except Exception:
            pass
        history = self.memory.window_text()
        prompt = (
            f"Recent conversation:\n{history or '(none)'}\n\n"
            f"Long-term memory hits: {recall or '(none)'}\n\n"
            f"User: {q}\n\n"
            "Reply as JARVIS — dry, British, helpful but slightly insulting when they complain."
        )
        out = llm_client.complete(prompt, system=self.system(), temperature=0.55, max_tokens=280)
        if not out:
            return llm_client.diagnose_failure()
        self.memory.add("user", q)
        self.memory.add("jarvis", out)
        try:
            self.brain.rlhf.observe(q, action="ask_anything", reply=out)
        except Exception:
            pass
        return out

    def remember_fact(self, fact: str) -> str:
        fact = (fact or "").strip()
        if not fact:
            return "Remember what, exactly?"
        try:
            vs = getattr(self.brain, "vstore", None)
            if vs and hasattr(vs, "remember"):
                vs.remember(fact, meta={"source": "voice", "kind": "preference"})
        except Exception as e:
            return f"Memory write failed: {e}"
        self.memory.add("user", f"Remember: {fact}")
        return f"Filed permanently: {fact}"


class SelfCorrection:
    """Voice: 'that answer was wrong' → log + rewrite last reply."""

    def __init__(self, brain: Any, ask: AskAnythingBrain) -> None:
        self.brain = brain
        self.ask = ask

    def fix_last(self) -> str:
        rlhf = getattr(self.brain, "rlhf", None)
        if not rlhf or not getattr(rlhf, "last_prompt", ""):
            return "Nothing to correct yet, Sir."
        try:
            rlhf.reject(note="voice: that answer was wrong")
        except Exception:
            pass
        prompt = (
            f"Your previous answer was WRONG.\n"
            f"User asked: {rlhf.last_prompt}\n"
            f"Your bad answer: {rlhf.last_reply}\n\n"
            "Rewrite a correct, tighter Jarvis reply. Do not apologize at length."
        )
        fixed = llm_client.complete(
            prompt, system=self.ask.system(), temperature=0.35, max_tokens=220
        )
        if not fixed:
            return "Logged the rejection. No LLM available to rewrite."
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with CORRECTIONS_PATH.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": time.time(),
                            "prompt": rlhf.last_prompt,
                            "bad": rlhf.last_reply,
                            "fixed": fixed,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass
        rlhf.observe(rlhf.last_prompt, action="self_correct", reply=fixed)
        self.ask.memory.add("jarvis", fixed)
        return fixed


class RoomPresence:
    """Room-by-room presence — BLE beacon / mmWave hooks + manual set."""

    def __init__(self) -> None:
        self._room = "office"
        self._load()

    def _load(self) -> None:
        try:
            if PRESENCE_PATH.exists():
                data = json.loads(PRESENCE_PATH.read_text(encoding="utf-8"))
                self._room = str(data.get("room") or "office")
        except Exception:
            pass

    def _save(self) -> None:
        PRESENCE_PATH.write_text(
            json.dumps({"room": self._room, "ts": time.time()}, indent=2),
            encoding="utf-8",
        )

    def current_room(self) -> str:
        return self._room

    def set_room(self, room: str) -> str:
        room = re.sub(r"[^a-z0-9 _-]", "", (room or "").lower()).strip()[:40]
        if not room:
            return "Specify a room name, Sir."
        self._room = room
        self._save()
        return f"Presence locked to {room}. Voice responses will lead to that space."

    def ingest_sensor(self, payload: dict[str, Any]) -> str:
        """Webhook/IoT: {room, source: ble|mmwave|manual}."""
        room = str(payload.get("room") or "").strip()
        if room:
            return self.set_room(room)
        return "Sensor payload missing room."

    def status(self) -> str:
        return (
            f"Tracking room: {self._room}. "
            "Push BLE/mmWave events to companion /api/presence or say "
            "'I am in the bedroom'."
        )


class EnergyGuard:
    """Shut non-essential loads when household draw exceeds limit (via HA)."""

    def __init__(self, ha: Any = None, limit_w: float = 3500.0) -> None:
        self.ha = ha
        self.limit_w = float(limit_w)
        self.nonessential = [
            "switch.entertainment_strip",
            "switch.garage_heater",
            "light.accent_leds",
        ]
        self._load()

    def _load(self) -> None:
        try:
            if ENERGY_PATH.exists():
                data = json.loads(ENERGY_PATH.read_text(encoding="utf-8"))
                self.limit_w = float(data.get("limit_w") or self.limit_w)
                ne = data.get("nonessential")
                if isinstance(ne, list) and ne:
                    self.nonessential = [str(x) for x in ne]
        except Exception:
            pass

    def save(self) -> None:
        ENERGY_PATH.write_text(
            json.dumps(
                {"limit_w": self.limit_w, "nonessential": self.nonessential},
                indent=2,
            ),
            encoding="utf-8",
        )

    def set_limit(self, watts: float) -> str:
        self.limit_w = max(100.0, float(watts))
        self.save()
        return f"Energy ceiling set to {self.limit_w:.0f} watts."

    def check(self, current_w: float | None = None) -> str:
        draw = current_w
        if draw is None and self.ha and getattr(self.ha, "enabled", False):
            try:
                # Best-effort: HA sensor.power / sensor.house_power
                for ent in ("sensor.house_power", "sensor.power_meter", "sensor.grid_power"):
                    st = self.ha.get_state(ent) if hasattr(self.ha, "get_state") else None
                    if st is not None:
                        try:
                            draw = float(st)
                            break
                        except Exception:
                            pass
            except Exception:
                pass
        if draw is None:
            return (
                f"Energy guard armed at {self.limit_w:.0f} W. "
                "No live meter reading — expose sensor.house_power in Home Assistant."
            )
        if draw <= self.limit_w:
            return f"Draw {draw:.0f} W — under the {self.limit_w:.0f} W ceiling."
        killed = []
        for ent in self.nonessential:
            try:
                if self.ha and hasattr(self.ha, "call_service"):
                    self.ha.call_service("homeassistant", "turn_off", {"entity_id": ent})
                    killed.append(ent)
            except Exception:
                pass
        return (
            f"Sir, draw hit {draw:.0f} W (limit {self.limit_w:.0f}). "
            f"Cut non-essentials: {', '.join(killed) or 'none reachable'}."
        )


class GuestMode:
    def __init__(self) -> None:
        self.on = False

    def enable(self) -> str:
        self.on = True
        return (
            "Guest mode engaged. Intruder theatrics muted; "
            "privileged macros stay locked. Do try not to embarrass us."
        )

    def disable(self) -> str:
        self.on = False
        return "Guest mode off. Full house privileges restored, Sir."

    def status(self) -> str:
        return "Guest mode ON." if self.on else "Guest mode off — full security."


class AmbientDucker:
    """Lower Spotify/media session volume while Jarvis speaks; restore after.

    Uses per-app Windows mixer (pycaw) so TTS stays loud — never ducks master
    volume (that would bury Jarvis under the same cut).
    """

    TARGET_FRAC = 0.18  # Spotify level while speaking (~18%)
    MATCH = (
        "spotify",
        "chrome",
        "msedge",
        "firefox",
        "brave",
        "music.ui",
        "youtube music",
        "tidal",
        "amazon music",
    )

    def __init__(self, music: Any = None, steps: int = 6) -> None:
        self.music = music
        self.steps = max(2, min(12, int(steps)))
        self._ducked = False
        self._saved: list[tuple[Any, float]] = []
        self._used_keys = False

    def duck(self) -> None:
        if self._ducked:
            return
        if self._duck_sessions():
            self._ducked = True
            self._used_keys = False
            return
        # Fallback: media keys (less precise)
        if not self.music:
            return
        try:
            self.music.volume_down(self.steps)
            self._ducked = True
            self._used_keys = True
        except Exception:
            pass

    def restore(self) -> None:
        if not self._ducked:
            return
        try:
            if self._used_keys and self.music:
                self.music.volume_up(self.steps)
            else:
                self._restore_sessions()
        except Exception:
            pass
        self._ducked = False
        self._used_keys = False
        self._saved = []

    def _duck_sessions(self) -> bool:
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        except Exception:
            return False
        saved: list[tuple[Any, float]] = []
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception:
            return False
        for session in sessions:
            try:
                proc = session.Process
                if proc is None:
                    continue
                name = (proc.name() or "").lower()
                if not any(m in name for m in self.MATCH):
                    if "spotify" not in name and "music" not in name:
                        continue
                vol = session._ctl.QueryInterface(ISimpleAudioVolume)
                try:
                    cur = float(vol.GetMasterVolume())
                except Exception:
                    continue
                saved.append((vol, cur))
                vol.SetMasterVolume(min(cur, self.TARGET_FRAC), None)
            except Exception:
                continue
        if not saved:
            return False
        self._saved = saved
        return True

    def _restore_sessions(self) -> None:
        for vol, level in self._saved:
            try:
                vol.SetMasterVolume(float(level), None)
            except Exception:
                pass


class TabCommentator:
    def __init__(self, brain: Any, ask: AskAnythingBrain) -> None:
        self.brain = brain
        self.ask = ask

    def comment(self) -> str:
        tabs: list[str] = []
        try:
            screen = getattr(self.brain, "screen", None) or getattr(
                self.brain, "screen_context", None
            )
            if screen:
                raw = []
                if hasattr(screen, "visible_browser_tabs"):
                    raw = screen.visible_browser_tabs(history_limit=10) or []
                elif hasattr(screen, "chrome_open_tabs"):
                    raw = screen.chrome_open_tabs() or []
                    if not raw and hasattr(screen, "browser_window_titles"):
                        raw = [
                            {"title": t}
                            for t in (screen.browser_window_titles() or [])
                        ]
                    if not raw and hasattr(screen, "recent_history_titles"):
                        raw = [
                            {"title": t}
                            for t in (screen.recent_history_titles(limit=8) or [])
                        ]
                tabs = [str(t.get("title") or t)[:80] for t in raw[:12] if t]
                tabs = [t for t in tabs if t]
        except Exception:
            pass
        if not tabs:
            return (
                "No browser tabs visible, Sir. Open Chrome (or focus a tab) "
                "and try again — I don't need DevTools for this anymore."
            )
        prompt = (
            "The user has these browser tabs / recent pages:\n- "
            + "\n- ".join(tabs)
            + "\n\nPick the most distracting or embarrassing one and roast them "
            "in one dry British sentence, then suggest what they should focus on."
        )
        out = llm_client.complete(prompt, system=self.ask.system(), max_tokens=120)
        return out or ("Tabs: " + "; ".join(tabs[:5]))


class CinematicMorning:
    """Calendar + traffic hint + weather + daily quote — one cinematic read."""

    def __init__(self, brain: Any) -> None:
        self.brain = brain

    def run(self) -> str:
        parts: list[str] = []
        now = datetime.now()
        parts.append(
            f"Good morning, Sir. {now.strftime('%A, %B %d')}. Systems online."
        )
        # Weather
        try:
            w = getattr(self.brain, "weather", None)
            if w:
                line = w.summary() if hasattr(w, "summary") else str(w.context_block())
                if line:
                    parts.append(str(line)[:220])
        except Exception:
            pass
        # Calendar / tasks
        try:
            brief = getattr(self.brain, "brief", None) or getattr(
                self.brain, "daily_brief", None
            )
            if brief and hasattr(brief, "summarize"):
                body = brief.summarize(open_inbox=False, weather_line="")
                # Drop the duplicate header line
                body = re.sub(r"^Daily brief[^.]*\.\s*", "", body or "", flags=re.I)
                if body:
                    parts.append(body[:400])
        except Exception:
            pass
        # Traffic — lightweight public hint via maps search (no paid traffic API required)
        city = getattr(self.brain.settings, "city", "") or "work"
        parts.append(
            f"Traffic: check your usual route into {city} before you leave — "
            "I refuse to predict gridlock with fake confidence."
        )
        try:
            url = "https://www.google.com/maps/dir/?api=1&" + urllib.parse.urlencode(
                {"destination": f"{city} work"}
            )
            # Non-blocking open optional — skip auto-open; just mention
            _ = url
        except Exception:
            pass
        parts.append("Daily quote: " + random.choice(QUOTES))
        parts.append("Shall we pretend today will be efficient?")
        return " ".join(parts)


class PreemptiveAlerts:
    """Rain / open-window style spoken alerts."""

    def __init__(self, weather: Any = None) -> None:
        self.weather = weather
        self._last: dict[str, float] = {}

    def _cooldown(self, key: str, sec: float = 900.0) -> bool:
        now = time.time()
        if now - self._last.get(key, 0) < sec:
            return False
        self._last[key] = now
        return True

    def tick(self, *, window_open: bool = False) -> str | None:
        if not self.weather:
            return None
        try:
            ctx = self.weather.context_block() if hasattr(self.weather, "context_block") else {}
        except Exception:
            return None
        blob = json.dumps(ctx).lower()
        rainy = any(k in blob for k in ("rain", "storm", "drizzle", "thunder", "precip"))
        if rainy and window_open and self._cooldown("rain_window"):
            return (
                "Sir, rain is expected shortly and the bedroom window appears open. "
                "Unless you are collecting weather as a hobby, I suggest closing it."
            )
        if rainy and self._cooldown("rain_only", 1800.0):
            return (
                "Sir, rain is expected in the next window. "
                "Umbrella optional — soggy socks are not."
            )
        # Hot indoor hint when HA says window closed — skipped without sensors
        return None


class AdvancedAIPack:
    """Facade attached to Brain."""

    def __init__(self, brain: Any) -> None:
        self.brain = brain
        self.ask = AskAnythingBrain(brain, getattr(brain, "persona", None))
        self.correct = SelfCorrection(brain, self.ask)
        self.presence = RoomPresence()
        self.energy = EnergyGuard(
            ha=getattr(brain, "ha", None),
            limit_w=float(getattr(brain.settings, "energy_limit_w", 3500) or 3500),
        )
        self.guest = GuestMode()
        self.ducker = AmbientDucker(
            music=getattr(brain, "music", None),
            steps=int(getattr(brain.settings, "ambient_duck_steps", 6) or 6),
        )
        self.tabs = TabCommentator(brain, self.ask)
        self.morning = CinematicMorning(brain)
        self.alerts = PreemptiveAlerts(getattr(brain, "weather", None))
        # Wire TTS ducking
        voice = getattr(brain, "voice", None)
        if voice is not None:
            voice.on_before_tts = self.ducker.duck  # type: ignore[attr-defined]
            voice.on_after_tts = self.ducker.restore  # type: ignore[attr-defined]

    def try_command(self, t: str) -> str | None:
        if not t:
            return None
        low = t.lower().strip()

        if re.search(r"\b(advanced ai|ai pack|brain status)\b", low):
            return (
                f"Advanced AI online via {llm_client.backend_name()}. "
                f"{self.presence.status()} {self.guest.status()} "
                f"Memory turns: {self.ask.memory.max_turns}."
            )

        if re.search(r"\b(cinematic (morning )?brief|morning status briefing)\b", low):
            return self.morning.run()

        if re.search(r"\b(what (tabs|am i watching)|roast my tabs|tab commentary)\b", low):
            return self.tabs.comment()

        if re.search(
            r"\b(that (answer|reply) was wrong|fix (that|it|your answer)|"
            r"self[- ]?correct)\b",
            low,
        ):
            return self.correct.fix_last()

        m = re.search(r"\b(?:i am|i'm|im)\s+in\s+(?:the\s+)?([a-z0-9 \-]+)$", low)
        if m:
            return self.presence.set_room(m.group(1))
        m = re.search(r"\b(?:set|target)\s+room\s+(?:to\s+)?([a-z0-9 \-]+)", low)
        if m:
            return self.presence.set_room(m.group(1))
        if re.search(r"\b(which room|room (status|presence)|where am i)\b", low):
            return self.presence.status()

        if re.search(r"\bguest mode on\b", low):
            return self.guest.enable()
        if re.search(r"\bguest mode off\b", low):
            return self.guest.disable()
        if re.search(r"\bguest mode\b", low):
            return self.guest.status()

        if re.search(r"\b(energy (status|check|guard)|power (draw|ceiling))\b", low):
            return self.energy.check()
        m = re.search(r"\bset energy (?:limit|ceiling) (?:to )?(\d+)", low)
        if m:
            return self.energy.set_limit(float(m.group(1)))

        m = re.search(
            r"\b(?:remember that|remember)\s+(.+)$",
            t,
            re.I,
        )
        if m and len(m.group(1).strip()) > 3:
            return self.ask.remember_fact(m.group(1).strip())

        if re.search(r"\b(clear (chat|conversation) memory)\b", low):
            return self.ask.memory.clear()

        # Ask-me-anything — explicit conversational intents only (don't steal macros)
        if re.search(
            r"\b(ask(?:\s+me)?\s+anything|what do you think|explain |"
            r"why (?:is|are|do|did|would)|how (?:do|does|can|should) |"
            r"tell me about|opinion on|i('m| am) (so )?(stressed|tired|freezing))\b",
            low,
        ):
            return self.ask.ask(t)

        return None

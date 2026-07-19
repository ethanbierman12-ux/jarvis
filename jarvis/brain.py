"""Jarvis brain — intent routing, bonded to UI callbacks."""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from typing import Any, Callable

from jarvis.config import Settings
from jarvis.core.camera_intent import is_camera_query
from jarvis.core.apps import AppLauncher
from jarvis.core.bedtime import BedtimeMode
from jarvis.core.governor import SystemGovernor
from jarvis.core.music import MusicPlayer
from jarvis.core.resources import ResourceManager
from jarvis.core.states import JarvisState, StateMachine
from jarvis.core.system import SystemControl
from jarvis.core.updater import SandboxCompiler
from jarvis.core.vision import VisionEvent, VisionService
from jarvis.core.voice import VoiceEngine
from jarvis.core.weather import Weather
from jarvis.core.scanner import Scanner
from jarvis.core.activity import ActivityObserver, grab_camera_frame
from jarvis.core.notes import NoteTaker
from jarvis.core.daily_brief import DailyBrief
from jarvis.core.work_mode import WorkMode
from jarvis.core.habits import HabitEngine
from jarvis.core.personality import Personality
from jarvis.core.lighting import SmartLighting
from jarvis.core.soundscape import Soundscape
from jarvis.core.diary import Diary, VisualMemory
from jarvis.core.proactive import ReturnBrief, WeatherGuard, SequenceLearner
from jarvis.core.suggestions import SuggestionEngine
from jarvis.core.system_extras import (
    ThemeSync,
    PerformanceBoost,
    PanicSwitch,
    EmotionMirror,
    ChromeHistory,
)
from jarvis.core.context_supervisor import ContextSupervisor
from jarvis.core.game_focus import GameFocusWatch, Prefetcher
from jarvis.core.spend import SpendTracker
from jarvis.core.data_feed import DataFeed
from jarvis.core.away_steward import AwaySteward
from jarvis.core.away_agent import AwayAgent
from jarvis.core.wake_brief import WakeBrief
from jarvis.core.business_finder import BusinessFinder
from jarvis.core.site_builder import SiteBuilder
from jarvis.core.vibe_coder import VibeCoder
from jarvis.core.internet import InternetAgent
from jarvis.core.hitl import HumanInTheLoop, HitlRequest
from jarvis.core.computer_use import ComputerUse
from jarvis.core.instructions import CustomInstructions
from jarvis.core.screen_context import ScreenContext
from jarvis.core.hub_client import HubClient
from jarvis.core.commands import normalize_command
from jarvis.core.intent_router import maybe_rewrite
from jarvis.core.zero_env import ensure_agent_dirs, log_hitl
import urllib.parse
import os
import subprocess
from pathlib import Path

try:
    import pyperclip
except Exception:  # optional
    pyperclip = None  # type: ignore


class Brain:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ui: dict[str, Callable] = {}
        self.system = SystemControl()
        self.apps = AppLauncher(
            open_on_other=bool(getattr(settings, "open_on_other_monitor", True))
        )
        self.music = MusicPlayer(
            focus_playlist=settings.focus_playlist,
            spotify_playlist_id=getattr(settings, "spotify_playlist_id", "")
            or "3hMeaqVid62fywPpTBWWw9",
            spotify_client_id=getattr(settings, "spotify_client_id", "") or "",
            spotify_client_secret=getattr(settings, "spotify_client_secret", "") or "",
            spotify_redirect_uri=getattr(settings, "spotify_redirect_uri", "")
            or "http://127.0.0.1:8888/callback",
        )
        self.computer = ComputerUse()
        self.screen = ScreenContext()
        self.hub = HubClient(
            base_url=getattr(settings, "hub_url", "") or "http://127.0.0.1:8787",
            enabled=bool(getattr(settings, "hub_enabled", True)),
            auto_start=bool(getattr(settings, "hub_auto_start", True)),
            on_log=lambda m: self._emit("heard", f"[hub] {m}"),
        )
        self.instructions = CustomInstructions()
        self.weather = Weather(settings.city, settings.openweather_api_key)
        self.governor = SystemGovernor()
        self.resources = ResourceManager()
        self.states = StateMachine()
        self.updater = SandboxCompiler()
        self.scanner = Scanner(apps=self.apps, system=self.system)
        self.activity = ActivityObserver()
        self.notes = NoteTaker()
        self.brief = DailyBrief()
        self.habits = HabitEngine()
        self.work = WorkMode(
            project_path=settings.work_project_path,
            ide=settings.work_ide,
            apps=settings.work_apps,
            urls=settings.work_urls,
            app_launcher=self.apps,
        )
        self.lights = SmartLighting(
            hue_bridge_ip=settings.hue_bridge_ip,
            hue_username=settings.hue_username,
            lifx_token=settings.lifx_token,
        )
        self.soundscape = Soundscape()
        self.diary = Diary()
        self.vmemory = VisualMemory()
        self.theme_sync = ThemeSync()
        self.boost = PerformanceBoost()
        self.panic = PanicSwitch()
        self.emotion = EmotionMirror()
        self.chrome_hist = ChromeHistory()
        self.sequences = SequenceLearner()
        self.suggestions = SuggestionEngine(
            settings,
            brief=self.brief,
            habits=self.habits,
            sequences=self.sequences,
            weather=self.weather,
        )
        self.return_brief = ReturnBrief(brief=self.brief, weather=self.weather)
        self.weather_guard = WeatherGuard(self.weather)
        self.context = ContextSupervisor(
            settings=settings,
            soundscape=self.soundscape,
            on_say=lambda t: self.say(t),
            on_lock=lambda: self.system.lock(),
            on_alert=lambda t: self._emit("hud_alert", t),
            on_return_brief=lambda t: self._on_return_brief(t),
            diary=self.diary,
        )
        self.game_focus = GameFocusWatch(
            on_enter=self._on_game_focus,
            on_leave=self._on_game_unfocus,
        )
        self.prefetcher = Prefetcher(apps_launcher=self.apps)
        self.spend = SpendTracker()
        self.feed = DataFeed()
        self.steward = AwaySteward()
        self.away_agent = AwayAgent()
        self.wake_brief = WakeBrief(
            spend=self.spend,
            steward=self.steward,
            habits=self.habits,
            brief=self.brief,
            feed=self.feed,
            system=self.system,
        )
        self.biz = BusinessFinder(city=settings.city)
        ensure_agent_dirs()
        self.hitl = HumanInTheLoop(
            enabled=bool(getattr(settings, "hitl_enabled", True)),
            timeout_sec=float(getattr(settings, "hitl_timeout_sec", 300) or 300),
            on_ask=self._on_hitl_ask,
        )
        self.sites = SiteBuilder(hitl=self.hitl)
        self.vibe = VibeCoder(hitl=self.hitl)
        self.net = InternetAgent()
        self._ghost = False
        self._pending_shutdown = False
        self._absent_since: float | None = None
        self._countdown_active = False
        self._presence_paused = False  # True while live camera / scanning
        self._scanning = False
        self._night_vision = False
        self._night_vision_auto_on = False
        self._lock = threading.Lock()
        self._last_frame = None
        self._start_cooldown = 0.0
        self._handling = False
        self._note_mode = False
        self._note_buffer: list[str] = []
        self._persona_support = False
        self._last_reply = ""
        self._last_reply_at = 0.0
        self._panic_active = False
        mic_pref = getattr(settings, "mic_prefer", "") or ""
        self.voice = VoiceEngine(
            on_heard=self.handle_utterance,
            voice=settings.tts_voice,
            rate=settings.tts_rate,
            pitch=getattr(settings, "tts_pitch", "-4Hz"),
            volume=getattr(settings, "tts_volume", "+0%"),
            noise_reduce=settings.noise_reduce,
            mic_prefer=mic_pref,  # empty = system default mic
            on_level=lambda lvl: self._emit("mic_level", lvl),
        )
        self.vision = VisionService(
            camera_index=settings.camera_index,
            prefer=settings.camera_prefer,
            fps=settings.presence_check_fps,
            on_event=self._on_vision,
        )
        self.bedtime = BedtimeMode(self.system, ui=lambda d: self._emit("bedtime", d))
        self.persona = Personality(settings.user_name)

        self.governor.on_change(self._on_governor)
        self.states.on_change(self._on_state)

    # ── lifecycle ───────────────────────────────────────────────
    def start(self) -> None:
        self.resources.for_state("hud")
        self.vision.start()
        self.voice.start()
        self.context.start()
        self.game_focus.start()
        # Prefetcher used to silently open Chrome/Code on a schedule — off by default
        # self.prefetcher.start()
        # One spoken line after boot — avoid greet + brief double-TTS (felt slow after F5)
        greet = self.persona.greet()
        self._emit("speak_ui", greet)
        self._emit("hud_alert", greet)
        self._emit("listening", False)
        threading.Timer(0.4, self._wake_command_center).start()
        threading.Timer(3.2, self._morning_weather_nudge).start()
        threading.Timer(1.4, lambda: self.theme_sync.apply_for_hour()).start()
        # Night vision watch (engages after dusk)
        threading.Timer(2.5, self._night_vision_loop).start()
        # First proactive suggestion shortly after boot
        threading.Timer(6.0, self._offer_suggestion).start()
        # Keep offering contextual tips every few minutes
        self._suggest_timer_start()
        # Refresh command deck periodically
        threading.Timer(8.0, self._stats_pulse_loop).start()
        # Bring Hub & Spoke online in the background
        if getattr(self.settings, "hub_enabled", True):
            threading.Thread(
                target=self._boot_hub, daemon=True, name="hub-boot"
            ).start()

    def _boot_hub(self) -> None:
        try:
            ok = self.hub.ensure_running(wait_sec=12.0)
            if ok:
                self._emit("hud_alert", "Hub & Spoke online — Sarah, Tom, Admin ready.")
                self.feed.push("hub", "Hub API connected", meta={"status": "done"})
            else:
                self._emit(
                    "hud_alert",
                    "Hub offline — say 'start hub' or run npm run dev:server in /hub",
                )
                self.feed.push("hub", "Hub offline", meta={"status": "error"})
        except Exception as e:
            self.feed.push("hub", f"Hub boot error: {e}", meta={"status": "error"})

    def _run_hub(self, text: str) -> str:
        """Delegate to Hub orchestrator; surface spoke results on the HUD."""
        self._emit("fetching", True)
        self._emit("hud_alert", "Hub routing to spokes…")
        self._reactor_safe("fetch")
        low = text.lower().strip()
        if re.search(r"\b(hub standby|stop agents|abort agents)\b", low) or low in (
            "standby agents",
            "agents standby",
        ):
            msg = self.hub.halt()
            self.feed.push("hub", msg, meta={"status": "done"})
            return self._flavor("ok", msg)
        if re.search(r"\b(resume hub|hub resume)\b", low):
            return self._flavor("ok", self.hub.resume())

        out = self.hub.chat(text)
        reply = str(out.get("reply") or "Hub returned an empty reply.")
        fails = 0
        for r in out.get("results") or []:
            spoke = str(r.get("spoke") or "spoke")
            summary = str(r.get("summary") or "")
            ok = bool(r.get("ok"))
            self.feed.push(
                spoke, summary[:160], meta={"status": "done" if ok else "error"}
            )
            self._emit("heard", f"[{spoke}] {summary[:120]}")
            if not ok:
                fails += 1
        plan = out.get("plan") or {}
        steps = plan.get("steps") or []
        if steps:
            chain = " → ".join(s.get("spoke", "?") for s in steps)
            self._emit("hud_alert", f"Hub plan · {chain}")
        # Proactive bottleneck alert — Master Operator directive #3
        if fails >= 1:
            alert = (
                f"Bottleneck: {fails} spoke failure(s). "
                "Recommend: hub status, then retry or hub standby."
            )
            self._emit("hud_alert", alert)
            self.feed.push("alert", alert, meta={"status": "error"})
            if fails >= 2:
                reply = f"{reply} {alert}"
        if out.get("halted"):
            self.feed.push("hub", "Agents halted", meta={"status": "done"})
        # Hub reply is already user-facing; avoid "Done. Done." double wrap
        return reply if reply.lower().startswith("done") else self._flavor("ok", reply)

    def _reactor_safe(self, mode: str) -> None:
        try:
            self._emit("reactor_activity", mode)
        except Exception:
            pass

    def _stats_pulse_loop(self) -> None:
        if getattr(self, "_stopped", False):
            return
        try:
            self._push_stats_ui()
        except Exception:
            pass
        threading.Timer(25.0, self._stats_pulse_loop).start()

    def _is_night_hours(self) -> bool:
        from datetime import datetime

        hour = datetime.now().hour
        start = int(getattr(self.settings, "night_vision_start_hour", 19) or 19)
        end = int(getattr(self.settings, "night_vision_end_hour", 6) or 6)
        if start == end:
            return False
        if start > end:
            # e.g. 19 → 6 spans midnight
            return hour >= start or hour < end
        return start <= hour < end

    def _night_vision_loop(self) -> None:
        if getattr(self, "_stopped", False):
            return
        try:
            auto = bool(getattr(self.settings, "night_vision_auto", True))
            if auto:
                want = self._is_night_hours()
                if want and not self._night_vision:
                    self.set_night_vision(True, announce=True, auto=True)
                elif not want and self._night_vision and self._night_vision_auto_on:
                    self.set_night_vision(False, announce=False, auto=True)
        except Exception:
            pass
        threading.Timer(45.0, self._night_vision_loop).start()

    def set_night_vision(self, on: bool, announce: bool = True, auto: bool = False) -> str:
        on = bool(on)
        was = self._night_vision
        self._night_vision = on
        if on:
            self._night_vision_auto_on = bool(auto)
        else:
            self._night_vision_auto_on = False
        self._emit("night_vision", on)
        if on and not was:
            msg = "Turning on night vision."
            self._emit("speak_ui", msg)
            self._emit("hud_alert", "NIGHT VISION ONLINE")
            self._emit("heard", "[optics] night vision online")
            if announce:
                self.say(msg)
            return msg
        if not on and was:
            msg = "Night vision offline."
            self._emit("speak_ui", msg)
            self._emit("hud_alert", "NIGHT VISION OFF")
            if announce:
                self.say(msg)
            return msg
        return "Night vision already on." if on else "Night vision already off."

    def _wake_command_center(self) -> None:
        """On wake: drain offline steward work, speak spend/stats, fill data feed."""
        try:
            payload = self.steward.drain_wake_payload()
            speak_extra, commands = self.wake_brief.apply_pending_steward(payload)
            packet = self.wake_brief.compose(mode="wake")
            self._emit("stats", packet["stats"])
            self._emit("feed", packet["feed_lines"])
            self.feed.push("wake", packet["speak"][:180])
            # Spoken once: command-center brief (greeting already shown in HUD)
            brief = packet["speak"]
            if speak_extra:
                brief = brief + " " + " ".join(speak_extra[:2])
            self.say(brief)
            self._emit("hud_alert", brief[:220])
            for cmd in commands[:3]:
                try:
                    self.handle_utterance(cmd)
                except Exception:
                    pass
            if payload.get("last_tick"):
                self.feed.push(
                    "steward",
                    self.steward.speak_offline_summary(),
                )
                self._emit("feed", self.feed.lines_for_ui(18))
        except Exception as e:
            print(f"[wake] command center failed: {e}")

    def _push_stats_ui(self) -> None:
        packet = self.wake_brief.compose(mode="stats")
        self._emit("stats", packet["stats"])
        self._emit("feed", self.feed.lines_for_ui(18) or packet["feed_lines"])

    def _suggest_timer_start(self) -> None:
        def _tick():
            if not getattr(self, "_stopped", False):
                self._offer_suggestion(speak=False)
                threading.Timer(180.0, _tick).start()

        threading.Timer(180.0, _tick).start()

    def _offer_suggestion(self, speak: bool = True, force: bool = False) -> None:
        tip = self.suggestions.now_suggestion(force=force)
        if not tip:
            return
        self._emit("quick_action", tip["title"])
        self._emit("hud_alert", tip["detail"])
        self._emit("suggestion", tip)
        if speak and self.suggestions.speak_ok():
            self.say(f"Suggestion: {tip['detail']}")

    def accept_suggestion(self) -> str:
        cmd = self.suggestions.pending_cmd or "set up my morning workspace"
        self._emit("heard", f"[suggestion] {cmd}")
        return self._route(cmd.lower())

    def _run_site_build(self, brief: str = "", index: int | None = None) -> str:
        """Kick off a fully autonomous site build; preview appears when ready."""
        city = getattr(self.settings, "city", None) or "Philadelphia"
        hint = brief.strip() if brief else (f"business #{index}" if index else "new venture")
        self._emit("site_ui", {"building": True, "hint": hint or "new venture"})
        self.feed.push("site", f"Autonomous build started: {hint or 'invented venture'}")

        def _job() -> None:
            try:
                def progress(msg) -> None:
                    self._emit("site_progress", msg)
                    text = msg.get("msg", msg) if isinstance(msg, dict) else str(msg)
                    stage = msg.get("stage") if isinstance(msg, dict) else ""
                    status = "running"
                    if stage in ("live",) and "complete" in str(text).lower():
                        status = "done"
                    elif stage in ("ship",) or "ship" in str(text).lower():
                        status = "shipped"
                    elif stage in ("render", "copy", "prompt"):
                        status = "building"
                    self.feed.push("site", str(text)[:160], meta={"status": status})

                if index is not None:
                    reply = self.sites.build_for_index(
                        index, self.biz, city=city, on_progress=progress, hitl=self.hitl
                    )
                else:
                    reply = self.sites.build(
                        brief or "",
                        open_when_done=True,
                        city=city,
                        on_progress=progress,
                        hitl=self.hitl,
                    )
                path = self.sites.last_site
                payload = {
                    "path": str(path) if path else "",
                    "brand": (self.sites.last_content or {}).get("brand") or "",
                    "prompt": self.sites.last_prompt or "",
                }
                self._emit("site_ui", payload)
                self.feed.push("site", reply[:220])
                try:
                    self._push_stats_ui()
                except Exception:
                    pass
                self.say(reply)
            except Exception as e:
                self._emit("site_ui", False)
                self.say(f"Site build failed: {e}")

        threading.Thread(target=_job, daemon=True, name="site-build").start()
        return (
            "Understood. Opening the agentic coding workbench — "
            "watch the agent plan, write files, run the terminal, and hot-reload the browser."
        )

    def _run_vibe_code(self, brief: str = "") -> str:
        """Kick off autonomous vibe coding / agent development."""
        hint = (brief or "").strip() or "invented app"
        ide = getattr(self.settings, "work_ide", None) or "code"
        self._emit("code_ui", {"building": True, "hint": hint})
        self.feed.push("vibe", f"Autonomous code session: {hint}")

        def _job() -> None:
            try:
                def progress(msg: str) -> None:
                    self._emit("code_progress", msg)
                    self.feed.push("vibe", msg[:160], meta={"status": "building"})

                reply = self.vibe.build(
                    brief or "",
                    open_when_done=True,
                    ide=ide,
                    on_progress=progress,
                    hitl=self.hitl,
                )
                meta = self.vibe.last_meta or {}
                payload = {
                    "path": meta.get("path") or str(self.vibe.last_project or ""),
                    "name": meta.get("name") or "",
                    "engine": meta.get("engine") or "",
                    "files": meta.get("files") or [],
                    "entry": meta.get("entry") or "",
                    "prompt": self.vibe.last_prompt or "",
                }
                self._emit("code_ui", payload)
                self.feed.push("vibe", reply[:220])
                try:
                    self._push_stats_ui()
                except Exception:
                    pass
                self.say(reply)
            except Exception as e:
                self._emit("code_ui", False)
                self.say(f"Vibe coding failed: {e}")

        threading.Thread(target=_job, daemon=True, name="vibe-code").start()
        return (
            "Understood. Starting autonomous AI agent development — "
            "I will invent the product if needed, write the brief, generate the code, "
            "and open the project. Watch the vibe panel."
        )

    def _run_biz_find(self, query: str = "") -> str:
        """Open 3D map immediately, scan, then fill numbered options."""
        city = getattr(self.settings, "city", None) or "Philadelphia"
        q = (query or "businesses near me").strip()
        self._emit(
            "map_ui",
            {
                "place": city,
                "markers": [],
                "options": [],
                "scanning": True,
                "query": q,
                "animate": True,
            },
        )
        self.feed.push("biz", f"Map scan: {q}")

        def _job() -> None:
            try:
                reply = self.biz.find(q, city=city)
                results = list(self.biz.last_results or [])
                markers = []
                options = []
                for i, r in enumerate(results[:8], 1):
                    if r.get("lat") is None or r.get("lon") is None:
                        continue
                    markers.append(
                        {
                            "index": i,
                            "name": r.get("name"),
                            "lat": r.get("lat"),
                            "lon": r.get("lon"),
                            "address": r.get("address"),
                            "category": r.get("category"),
                        }
                    )
                    options.append(
                        {
                            "index": i,
                            "name": r.get("name"),
                            "lat": r.get("lat"),
                            "lon": r.get("lon"),
                            "address": r.get("address"),
                            "category": r.get("category"),
                            "website": r.get("website") or "",
                            "phone": r.get("phone") or "",
                        }
                    )
                self._emit(
                    "map_ui",
                    {
                        "place": city,
                        "markers": markers,
                        "options": options,
                        "scanning": False,
                        "query": q,
                        "animate": False,
                    },
                )
                self.feed.push("biz", reply[:220])
                try:
                    self._push_stats_ui()
                except Exception:
                    pass
                # Short spoken options summary
                if options:
                    tops = "; ".join(
                        f"{o['index']}. {o['name']}" for o in options[:4]
                    )
                    self.say(
                        f"Map locked. {len(options)} options on the board — {tops}. "
                        "Pick one on the map, or say build a website for number 1."
                    )
                else:
                    self.say(reply)
            except Exception as e:
                self._emit("map_ui", {"scanning": False, "place": city})
                self.say(f"Business scan failed: {e}")

        threading.Thread(target=_job, daemon=True, name="biz-find").start()
        return (
            "Pulling up the 3D tactical map and scanning the sector now. "
            "Options will appear on the left when locked."
        )

    def _run_away_agent(self, *, mail_mode: str = "ack") -> str:
        """Visible away ritual: apps, writing, talking, diagnostics + steward queue."""
        self.return_brief.mark_away()
        self._emit("away_ui", {"building": True})
        self.feed.push("steward", "Away agent live session started")

        def _job() -> None:
            try:
                def progress(payload) -> None:
                    self._emit("away_progress", payload)
                    msg = (
                        payload.get("msg", "")
                        if isinstance(payload, dict)
                        else str(payload)
                    )
                    if msg:
                        stage = (
                            payload.get("stage")
                            if isinstance(payload, dict)
                            else ""
                        )
                        status = "done" if stage == "done" else "running"
                        self.feed.push(
                            "away", str(msg)[:160], meta={"status": status}
                        )

                def speak(line: str) -> None:
                    # Speak key lines without blocking the ritual too hard
                    try:
                        self.say(line)
                    except Exception:
                        pass

                summary = self.away_agent.run(
                    user_name=self.settings.user_name,
                    city=getattr(self.settings, "city", None) or "Philadelphia",
                    mail_mode=mail_mode,
                    on_progress=progress,
                    on_speak=speak,
                    steward=self.steward,
                )
                self._emit("away_ui", {"done": True, "summary": summary})
                self.feed.push("steward", summary[:220])
                try:
                    self._push_stats_ui()
                except Exception:
                    pass
            except Exception as e:
                self._emit("away_ui", False)
                self.say(f"Away agent hit a snag: {e}")

        threading.Thread(target=_job, daemon=True, name="away-agent").start()
        return (
            "Away agent engaged. Watch me open Task Manager, run diagnostics, "
            "write your status note, and arm mail watch."
        )

    def stop(self) -> None:
        self._stopped = True
        self.voice.stop()
        self.vision.stop()
        self.context.stop()
        self.game_focus.stop()
        self.prefetcher.stop()

    def _on_game_focus(self, name: str) -> None:
        try:
            self.voice.mute_mic(True)
            self.music.media_key("mute")
        except Exception:
            pass
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", "Start-Process ms-settings:quiethours"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
        self._emit("hud_alert", f"Focus mode — {name} detected, mic muted.")

    def _on_game_unfocus(self) -> None:
        try:
            self.voice.mute_mic(False)
        except Exception:
            pass

    def ghost_mode(self) -> str:
        """Privacy Mode — hide workspace, pause camera/AI listening, lock."""
        self._ghost = True
        self._panic_active = True
        try:
            self.voice.mute_mic(True)
            self.vision.stop()
            self.soundscape.stop()
        except Exception:
            pass
        self._emit("camera_ui", False)
        self._emit("panic_ui", True)
        msg = self.panic.trigger()
        try:
            self.system.lock()
        except Exception:
            pass
        self._emit("hud_alert", "Ghost / Privacy Mode — screen cleared & locked.")
        return f"Privacy Mode on. {msg}"

    def daily_recap(self) -> str:
        week = self.diary.week_report()
        tasks = ""
        try:
            tasks = self.brief._tasks_line()
        except Exception:
            pass
        cal = ""
        try:
            cal = self.brief.schedule_only()
        except Exception:
            pass
        return (
            f"End-of-day Wins & Growth: {week} "
            f"{tasks} {cal} "
            f"Rest well, {self.settings.user_name}."
        ).strip()
    def _morning_weather_nudge(self) -> None:
        msg = self.weather_guard.morning_check()
        if msg:
            self._emit("hud_alert", msg)
            self.say(msg)

    def _on_return_brief(self, text: str) -> None:
        packet = self.wake_brief.compose(mode="return")
        full = f"{text} {packet['speak']}"
        self._emit("hud_alert", full[:240])
        self._emit("stats", packet["stats"])
        self._emit("feed", self.feed.lines_for_ui(18) or packet["feed_lines"])
        self.feed.push("presence", text[:160])
        self.say(full)
        self.diary.log_win("Returned to desk", kind="presence")

    def panic_now(self) -> str:
        self._panic_active = True
        try:
            self.voice.mute_mic(True)
        except Exception:
            pass
        try:
            self.soundscape.stop()
        except Exception:
            pass
        self._emit("panic_ui", True)
        msg = self.panic.trigger()
        self._emit("hud_alert", msg)
        return msg

    def clear_panic(self) -> str:
        self._panic_active = False
        self._emit("panic_ui", False)
        try:
            self.voice.mute_mic(False)
            self.voice.set_busy(False)
        except Exception:
            pass
        self._emit("listening", True)
        self._emit("hud_alert", "Panic off — microphone live again.")
        return "Panic mode off. I'm listening on your mic again."

    def trigger_start(self) -> None:
        """START — HUD button or voice 'start' only (no F5 / clap)."""
        import time

        now = time.time()
        with self._lock:
            if now - self._start_cooldown < 1.2:
                return
            self._start_cooldown = now

        def _do() -> None:
            if self.bedtime.active:
                self.bedtime.exit()
            self.states.set(JarvisState.ACTIVE)
            self.voice.mute_mic(False)
            self.pause_presence_lock(False)
            self._emit("start_pulse", True)
            self._emit("listening", True)
            self._emit("track", "START · playing")
            play_msg = self.music.press_play()
            self.say(self.persona.start_ack())
            self._emit("heard", f"[start] {play_msg}")

            def _settle():
                time.sleep(1.5)
                self._emit("listening", False)

            threading.Thread(target=_settle, daemon=True).start()

        threading.Thread(target=_do, daemon=True, name="jarvis-start").start()

    def say(self, text: str) -> None:
        # HUD gets full text; voice stays punchy (≤20 words)
        self._emit("speak", text)
        spoken = self.persona.speakable(text, max_words=20)
        self.voice.say(spoken)

    def _emit(self, key: str, payload: Any) -> None:
        cb = self.ui.get(key)
        if cb:
            try:
                cb(payload)
            except Exception as e:
                print(f"[ui:{key}] {e}")

    def _on_hitl_ask(self, req: HitlRequest) -> None:
        """Push HITL card to HUD + speak the ask."""
        payload = {
            "id": req.id,
            "kind": req.kind.value if hasattr(req.kind, "value") else str(req.kind),
            "title": req.title,
            "detail": req.detail,
            "action": req.action,
            "agent": req.agent,
            "options": list(req.options),
            "meta": dict(req.meta),
        }
        self._emit("hitl_ask", payload)
        self._emit("hud_alert", f"HITL · {req.title}")
        self.feed.push("hitl", f"{req.action}: {req.title}", meta={"status": "waiting"})
        try:
            log_hitl(
                {
                    "event": "ask",
                    **{k: payload[k] for k in ("id", "kind", "action", "agent")},
                }
            )
        except Exception:
            pass
        try:
            self._emit(
                "speak_ui",
                f"Human in the loop — {req.action} needs your OK. Approve or deny.",
            )
        except Exception:
            pass

    def resolve_hitl(
        self, request_id: str = "", *, approve: bool = True, answer: str = ""
    ) -> str:
        ok = self.hitl.resolve(request_id, approve=approve, answer=answer)
        if not ok:
            return "No HITL gate is waiting."
        try:
            log_hitl(
                {
                    "event": "resolve",
                    "id": request_id,
                    "approve": approve,
                    "answer": (answer or "")[:200],
                }
            )
        except Exception:
            pass
        self._emit("hitl_clear", True)
        return "HITL approved — agent continuing." if approve else "HITL denied."

    # ── governor / vision ───────────────────────────────────────
    def _on_governor(self, snap) -> None:
        self.vision.set_fps(snap.vision_fps)
        self._emit("telemetry", snap)
        if snap.eco:
            self._emit("bond", {"dim": True, "ambient": "conserve", "fps": snap.ui_fps})

    def tick_governor(self):
        return self.governor.tick()

    def _on_vision(self, ev: VisionEvent) -> None:
        import time

        self._emit("presence", ev.present)
        self._emit("parallax", {"x": ev.face_x, "y": ev.face_y})
        if self.settings.camera_index != ev.camera_index and ev.camera_index >= 0:
            self.settings.camera_index = ev.camera_index

        # Contextual biometrics + activity from latest snapshot
        if ev.snapshot_path and not self._presence_paused and not self._scanning:
            try:
                import cv2

                img = cv2.imread(ev.snapshot_path)
                if img is not None:
                    self.activity.note_frame(img)
                    self._last_frame = img
                    self.context.tick_frame(img)
            except Exception:
                pass

        if self.bedtime.active:
            return

        # Don't arm lock while user is scanning / live preview (item can cover face)
        if self._presence_paused:
            return

        if not self.settings.lock_on_absence:
            return

        # Keyboard activity = still at desk (even if face briefly missed)
        typing = False
        try:
            typing = self.context.cadence.keys_per_minute() >= 8
        except Exception:
            pass
        motion_here = float(getattr(ev, "motion", 0) or 0) > 0.03

        still_here = bool(ev.present) or typing or motion_here

        if still_here:
            if self._absent_since is not None and ev.present:
                brief = self.return_brief.mark_present()
                self.context.on_presence(True, brief)
            self._absent_since = None
            if self._countdown_active:
                self._countdown_active = False
                self._emit("countdown_cancel", True)
                self._emit("speak_ui", "Welcome back — lock cancelled.")
            if self.states.state == JarvisState.IDLE:
                self.states.set(JarvisState.ACTIVE)
            return

        # Face / motion gone — short grace, then lock countdown (default 35s)
        self.return_brief.mark_away()
        self.context.on_presence(False)
        now = time.time()
        if self._absent_since is None:
            self._absent_since = now
            return

        gone = now - self._absent_since
        grace = float(getattr(self.settings, "presence_grace_sec", 2) or 2)
        if self._countdown_active or gone < grace:
            return

        self._countdown_active = True
        self.states.set(JarvisState.IDLE)
        if getattr(self.settings, "lock_immediate", False):
            self._emit("heard", f"[security] away {int(gone)}s — locking")
            self.on_countdown_finished()
        else:
            secs = int(self.settings.presence_timeout_sec or 35)
            self._emit("countdown_start", secs)
            self._emit("heard", f"[security] presence lost — {secs}s to lock")
            self._emit("speak_ui", f"Presence lost. Locking in {secs} seconds unless you return.")

    def pause_presence_lock(self, paused: bool) -> None:
        """Call while EMEET preview / scan is open so holding items won't false-lock."""
        self._presence_paused = bool(paused)
        if paused:
            self._absent_since = None
            if self._countdown_active:
                self._countdown_active = False
                self._emit("countdown_cancel", True)

    def on_countdown_finished(self) -> None:
        self._countdown_active = False
        self._absent_since = None
        self.system.lock()
        self.say("Workstation locked.")

    def _on_state(self, old: JarvisState, new: JarvisState) -> None:
        self._emit("state", {"from": old.value, "to": new.value})
        self.resources.for_state(new.value if new != JarvisState.ACTIVE else "hud")

    # ── intents ─────────────────────────────────────────────────
    def handle_utterance(self, text: str) -> None:
        text = normalize_command((text or "").strip())
        if getattr(self.settings, "ollama_router", True):
            try:
                text = maybe_rewrite(
                    text,
                    enabled=True,
                    model=getattr(self.settings, "ollama_model", "llama3") or "llama3",
                )
            except Exception:
                pass
        if not text:
            return

        # One command at a time — stops stacked repeats
        if self._handling:
            return
        self._handling = True
        self.voice.set_busy(True)
        try:
            self._emit("heard", text)
            self._emit("listening", True)

            # HITL voice resolve takes priority while a gate is open
            hitl_msg = self.hitl.resolve_voice(text)
            if hitl_msg:
                self._emit("speak_ui", hitl_msg)
                self._emit("hud_alert", hitl_msg)
                self.say(hitl_msg)
                return

            ww = self.settings.wake_word.lower()
            low = text.lower()
            if low.startswith(ww):
                text = text[len(ww) :].strip(" ,.")
                low = text.lower()

            # Dictation mode — capture everything until "done" / "save note"
            if self._note_mode:
                reply = self._note_dictation(low)
            else:
                # Emotional mirroring
                mood = self.emotion.analyze(low)
                if mood == "stressed" and not self._persona_support:
                    self._persona_support = True
                    self.say(self.emotion.support_line(self.settings.user_name))
                elif mood == "positive":
                    self._persona_support = False

                reply = self._route(low)
                # Learn command sequences → quick action suggestion
                if reply and not self._note_mode:
                    hint = self.sequences.observe(low)
                    if hint and self.sequences._counts.get(hint, 0) >= 3:
                        # Proceed runs the last step of the learned sequence
                        last = hint.split("→")[-1].strip() or "set up my morning workspace"
                        self.suggestions.pending_cmd = last
                        self._emit(
                            "quick_action",
                            f"Shall I run “{last}” again?",
                        )
                    # Follow-up suggestion after useful commands
                    follow = self.suggestions.after_command(low, reply or "")
                    if follow:
                        self._emit("quick_action", follow["title"])
                        self._emit("hud_alert", follow["detail"])
                # Silent diary of meaningful actions
                if reply and any(
                    k in low
                    for k in ("done", "finished", "shipped", "deployed", "complete")
                ):
                    self.diary.log_win(low[:120])
            self._emit("listening", False)
            if reply:
                # Never speak the same reply twice in a short window (stops rephrase loops)
                import time as _time

                now = _time.time()
                norm = " ".join(reply.lower().split())
                if (
                    norm
                    and norm == self._last_reply
                    and now - self._last_reply_at < 10.0
                ):
                    print(f"[brain] skip duplicate reply: {reply[:60]}")
                else:
                    self._last_reply = norm
                    self._last_reply_at = now
                    self.say(reply)
        finally:
            self._handling = False
            # Stay less busy in note mode so next sentences come through quickly
            delay = 0.15 if self._note_mode else 0.35
            threading.Timer(delay, lambda: self.voice.set_busy(False)).start()

    def _note_dictation(self, t: str) -> str:
        """While note mode is on, append spoken lines until user saves."""
        if re.search(
            r"\b(done|i'?m done|that'?s (all|it)|save( the)? note|"
            r"stop (taking )?notes?|end note|finish(ed)? note|cancel note)\b",
            t,
        ):
            self._note_mode = False
            body = " ".join(self._note_buffer).strip()
            self._note_buffer = []
            if re.search(r"\bcancel note\b", t) or not body:
                return "Note cancelled."
            self.habits.log("note")
            return self._flavor(
                "ok",
                self.notes.take(body, from_screen=False, audio=False),
            )

        # Ignore empty / wake leftovers
        if not t or t in ("jarvis", "hey jarvis"):
            return ""
        self._note_buffer.append(t)
        # Quiet ack every few lines so we don't spam TTS over their words
        if len(self._note_buffer) == 1:
            return "Got it — keep talking. Say 'done' when finished."
        if len(self._note_buffer) % 3 == 0:
            return "Still listening."
        return ""  # no spoken ack — keep mic free for more dictation

    def _flavor(self, kind: str, core: str) -> str:
        return self.persona.wrap(kind, core)

    def _route(self, t: str) -> str:
        # Hub & Spoke — Sarah / Tom / Admin multi-agent (before local desktop intents)
        if getattr(self.settings, "hub_enabled", True) and (
            HubClient.wants_hub(t)
            or re.search(r"\b(start hub|restart hub|hub status)\b", t)
        ):
            if re.search(r"\b(start hub|restart hub)\b", t):
                ok = self.hub.ensure_running(wait_sec=14.0)
                return self._flavor(
                    "ok",
                    "Hub is online." if ok else "Could not start Hub — run npm run dev:server in /hub.",
                )
            if re.search(r"\bhub status\b", t):
                h = self.hub.health()
                if not h:
                    return self._flavor("ok", "Hub is offline.")
                return self._flavor(
                    "ok",
                    f"Hub online · uptime {h.get('uptimeSec')}s · sessions {h.get('sessions')} · "
                    f"mock={h.get('mockLlm')}.",
                )
            return self._run_hub(t)

        # Accept pending suggestion — only clear yes/affirm within a short window
        if re.search(
            r"\b(yes|yeah|yep|do it|go ahead|sure|please do|sounds good)\b",
            t,
        ) and self.suggestions.pending_cmd:
            if not self.suggestions.pending_fresh(25.0):
                self.suggestions.pending_cmd = ""
            else:
                cmd = self.suggestions.pending_cmd
                self.suggestions.pending_cmd = ""
                # Avoid accidental workspace/browser spam from a lone "yes"
                if re.search(r"\b(workspace|work mode|starting work|check email)\b", cmd):
                    if not re.search(
                        r"\b(do it|go ahead|please do|yes please|set (it )?up)\b", t
                    ):
                        self.suggestions.pending_cmd = cmd  # keep offer
                        return (
                            "Just to confirm — say 'go ahead' if you want me to open "
                            "apps and tabs for that."
                        )
                return self._route(cmd)

        # Ask for suggestions
        if re.search(
            r"\b(suggest(ion|ions)?|any (ideas|suggestions)|what should i (do|focus on)|"
            r"give me (a )?suggestion|recommend something|what next)\b",
            t,
        ):
            tip = self.suggestions.now_suggestion(force=True)
            if not tip:
                return "No fresh suggestion right now — try again in a minute."
            self._emit("quick_action", tip["title"])
            self._emit("hud_alert", tip["detail"])
            return tip["detail"] + " Say yes if you want me to do that."

        # Personality / chitchat
        if re.search(r"\b(thanks|thank you|cheers)\b", t):
            return self.persona.wrap("thanks", "")
        if re.search(r"\b(who are you|what are you|introduce yourself)\b", t):
            return self.persona.wrap("who", "")
        if re.search(r"\b(how are you|you (ok|okay|good))\b", t):
            return self.persona.wrap("how", "")
        if re.search(r"\b(tell me a joke|joke|make me laugh)\b", t):
            return self.persona.wrap("joke", "")
        if re.search(r"\b(i love you|you('re| are) (the best|amazing))\b", t):
            return f"Flattery noted, {self.settings.user_name}. I shall file it under 'obviously correct'."

        # Bedtime / goodnight (not OS sleep — that is "sleep" / "standby")
        if re.search(r"\b(goodnight|good night|bedtime|i'?m going to bed)\b", t):
            self.states.set(JarvisState.BEDTIME)
            recap = self.daily_recap()
            bed = self.bedtime.enter()
            return f"{recap} {bed}"

        if re.search(r"\b(wake up|i'?m back|good morning)\b", t):
            if self.bedtime.active:
                self.states.set(JarvisState.ACTIVE)
                self.bedtime.exit()
            packet = self.wake_brief.compose(mode="return" if "back" in t else "wake")
            self._emit("stats", packet["stats"])
            self._emit("feed", self.feed.lines_for_ui(18) or packet["feed_lines"])
            self.feed.push("wake", packet["speak"][:160])
            # Drain any steward work that finished while offline
            try:
                payload = self.steward.drain_wake_payload()
                extra, cmds = self.wake_brief.apply_pending_steward(payload)
                if extra:
                    packet["speak"] = packet["speak"] + " " + " ".join(extra[:2])
                for cmd in cmds[:2]:
                    threading.Thread(
                        target=lambda c=cmd: self.handle_utterance(c),
                        daemon=True,
                    ).start()
            except Exception:
                pass
            return self._flavor("ok", packet["speak"])

        # Spend tracking
        spent = self.spend.parse_and_add(t)
        if spent:
            self.habits.log("spend", spent[:40])
            self.feed.push("spend", spent)
            self._push_stats_ui()
            return self._flavor("ok", spent)
        if re.search(
            r"\b(how much (did|have) i spend|how much (have )?i spent|"
            r"(what(?:'s| is)|show) my (spend(ing)?|expenses?)|"
            r"spending (today|this week)|expense (report|summary))\b",
            t,
        ):
            period = "week" if "week" in t else "today"
            line = self.spend.speak_summary(period=period)
            self.feed.push("spend", line)
            self._push_stats_ui()
            return self._flavor("ok", line)

        # Away / offline steward — live agent theater
        if re.search(r"\b(away mode|i(?:'m| am) (heading out|leaving|going out))\b", t):
            mail_mode = getattr(self.settings, "away_mail_mode", "ack") or "ack"
            if "draft" in t:
                mail_mode = "draft"
            elif "auto" in t:
                mail_mode = "auto"
            return self._flavor("ok", self._run_away_agent(mail_mode=mail_mode))
        if re.search(r"\b(end away mode|cancel away mode)\b", t):
            return self._flavor("ok", self.steward.mark_away_mode(False))
        if re.search(
            r"\b(away mail|mail mode|answer (my )?emails? (with )?(draft|ack|auto)|"
            r"email replies? (draft|ack|auto))\b",
            t,
        ):
            mode = "ack"
            if "draft" in t:
                mode = "draft"
            elif "auto" in t:
                mode = "auto"
            msg = self.steward.set_mail_mode(mode)
            try:
                self.settings.away_mail_mode = mode
                self.settings.save()
            except Exception:
                pass
            self.feed.push("mail", msg)
            return self._flavor("ok", msg)
        if re.search(
            r"\b(check (away )?mail|process (my )?inbox|answer (my )?emails? now|"
            r"handle (my )?inbox|mail (status|summary|drafts?))\b",
            t,
        ):
            from jarvis.core.mail_agent import MailAgent

            agent = MailAgent(
                user_name=self.settings.user_name,
                mode=getattr(self.settings, "away_mail_mode", "ack") or "ack",
                max_per_tick=int(getattr(self.settings, "away_mail_max_per_tick", 3) or 3),
            )
            if "draft" in t and "summary" not in t and "status" not in t:
                return self._flavor("ok", agent.list_drafts())
            if "summary" in t or "status" in t:
                line = agent.speak_summary()
                self.feed.push("mail", line)
                return self._flavor("ok", line)
            result = agent.process_inbox()
            self.feed.push("mail", result.get("message", ""))
            self._push_stats_ui()
            return self._flavor("ok", result.get("message", "Mail check complete."))
        away = self.steward.enqueue_from_utterance(t)
        if away:
            self.feed.push("steward", away[:200])
            self._push_stats_ui()
            return self._flavor("ok", away)

        # Business finder — opens 3D map with animated scan + pickable options
        if re.search(
            r"\b(find|search|look up|locate)\b.+\b(near me|nearby|close by|in \w+|"
            r"coffee|cafe|restaurant|pizza|plumber|gym|hotel|bar|salon|dentist|"
            r"pharmacy|bakery|lawyer|shop|store|business|biz)\b",
            t,
        ) or re.search(
            r"\b(find (a |me )?(biz|business|businesses|places|shops)|"
            r"business(es)? near me|what(?:'s| is) nearby|"
            r"find biz)\b",
            t,
        ):
            q = re.sub(r"^(jarvis[,.]?\s*)?(please\s+)?", "", t).strip()
            q = re.sub(r"^(find|search|look up|locate)\s+", "", q).strip()
            if re.fullmatch(r"(a |me )?(biz|business|businesses|places|shops)", q or "", re.I):
                q = "businesses near me"
            self.habits.log("business_find", (q or t)[:40])
            return self._flavor("ok", self._run_biz_find(q or t))

        if re.search(r"\b(open business results|show (the )?business(es)?|business list)\b", t):
            path = self.biz.results_html_path()
            if not path.exists():
                return "No business results yet — say find coffee near me first."
            try:
                from jarvis.core.displays import displays

                displays.open_url_on(path.resolve().as_uri(), "secondary")
            except Exception:
                import webbrowser

                webbrowser.open(path.resolve().as_uri())
            return self._flavor("ok", "Opening the business list on your other monitor.")

        m = re.search(
            r"\bbuild (?:a |me )?(?:website|site|webpage|landing page)(?: for)?\s+(?:number\s+)?(\d+)\b",
            t,
        )
        if m:
            idx = int(m.group(1))
            self.habits.log("site_build", f"#{idx}")
            return self._flavor("ok", self._run_site_build(index=idx))

        # Bare "build a site" OR "build a website for …" — fully autonomous
        if re.search(
            r"\b((build|make|create|generate)\s+(?:(?:a|me|my)\s+)*(?:website|site|webpage|landing page)|"
            r"build (?:me )?one|"
            r"agentic (coding|workflow|build)|"
            r"ai (coding )?agent(ic)? (coding|build|workflow)?|"
            r"start (the )?agentic)\b",
            t,
        ):
            m2 = re.search(
                r"(?:website|site|webpage|landing page)(?: for)?\s+(.+)$", t
            )
            brief = m2.group(1).strip() if m2 else ""
            brief = re.sub(r"^(for\s+)", "", brief).strip()
            if re.search(r"\b(that|this|the) business\b", brief) or brief in (
                "it",
                "them",
                "that",
            ):
                self.habits.log("site_build", "biz#1")
                return self._flavor("ok", self._run_site_build(index=1))
            self.habits.log("site_build", (brief or "autonomous")[:40])
            return self._flavor("ok", self._run_site_build(brief=brief))

        # Autonomous vibe coding / AI agent development
        if re.search(
            r"\b((start |do |run )?(autonomous )?(ai )?agent (development|coding|dev)|"
            r"(start |do |run )?vibe( coding|ing| code)?|"
            r"code vibe|"
            r"(build|make|create|generate|ship)\s+(me )?(an? )?(app|project|game|tool|cli)|"
            r"autonomous (coding|development|dev))\b",
            t,
        ):
            brief = ""
            m3 = re.search(
                r"(?:vibe(?: coding|ing| code)?|agent (?:development|coding|dev)|"
                r"(?:app|project|game|tool|cli))\s+(?:for|called|named)?\s*(.+)$",
                t,
            )
            if m3:
                brief = m3.group(1).strip()
            brief = re.sub(
                r"^(called|named|for|me|a|an|the)\s+", "", brief, flags=re.I
            ).strip()
            # Don't steal "coding mode" lights command — already handled elsewhere
            self.habits.log("vibe_code", (brief or "autonomous")[:40])
            return self._flavor("ok", self._run_vibe_code(brief=brief))

        if re.search(r"\b(open (the |my )?(vibe|project|code) you (built|made)|show (the )?vibe)\b", t):
            path = self.vibe.last_project
            if path and path.exists():
                meta = self.vibe.last_meta or {}
                self._emit(
                    "code_ui",
                    {
                        "path": str(path),
                        "name": meta.get("name") or path.name,
                        "engine": meta.get("engine") or "",
                        "files": meta.get("files") or [],
                        "entry": meta.get("entry") or "",
                        "prompt": self.vibe.last_prompt or "",
                    },
                )
            return self._flavor("ok", self.vibe.open_last())

        if re.search(r"\b(list (vibe )?projects|what (apps|projects) did you (build|make))\b", t):
            return self._flavor("ok", self.vibe.list_projects())

        if re.search(r"\b(close (the )?(vibe|code)( panel| preview)?)\b", t):
            self._emit("code_ui", False)
            return self._flavor("ok", "Closing the vibe panel.")

        if re.search(r"\b(open (the |my )?(website|site) you built|show (the )?website)\b", t):
            path = self.sites.last_site
            if path and path.exists():
                self._emit(
                    "site_ui",
                    {
                        "path": str(path),
                        "brand": (self.sites.last_content or {}).get("brand") or "",
                        "prompt": self.sites.last_prompt or "",
                    },
                )
            return self._flavor("ok", self.sites.open_last())
        if re.search(r"\b(list (my )?sites|what websites did you build)\b", t):
            return self._flavor("ok", self.sites.list_sites())
        if re.search(r"\b(close|hide) (the )?(website|site)( preview)?\b", t):
            self._emit("site_ui", False)
            return self._flavor("ok", "Closing the site preview.")

        # 3D tactical map view
        if re.search(
            r"\b((open|show|launch|bring up|pull up) (a |the )?(3d |three[- ]d )?(view of (the )?|view )?(map|maps)|"
            r"(open|show) (the )?(3d )?map( view)?|"
            r"map (mode|view)|tactical map|satellite (view|map))\b",
            t,
        ):
            place = None
            m = re.search(
                r"\b(?:map|maps|view)\s+(?:of\s+)?(.+)$",
                t,
            )
            if m:
                cand = m.group(1).strip(" .")
                cand = re.sub(
                    r"\b(view|mode|please|for me|3d|three[- ]d)\b",
                    "",
                    cand,
                    flags=re.I,
                ).strip(" .")
                if cand and cand.lower() not in ("map", "maps", "the map"):
                    place = cand
            self.habits.log("map_view", (place or "home")[:40])
            self._emit(
                "map_ui",
                {"place": place or self.settings.city, "markers": None},
            )
            where = place or self.settings.city
            return self._flavor(
                "ok",
                f"Switching to 3D map view — focusing on {where}. "
                f"Say close map when you are done.",
            )
        if re.search(r"\b(close|hide|exit) (the )?(3d )?map( view)?\b", t):
            self._emit("map_ui", False)
            return self._flavor("ok", "Closing the map. Arc reactor restored.")
        if re.search(r"\bfly (?:the )?map to\s+(.+)$", t) or re.search(
            r"\b(?:recenter map|map focus)\s+(?:on\s+)?(.+)$", t
        ):
            m2 = re.search(
                r"\b(?:fly (?:the )?map to|recenter map|map focus)\s+(?:on\s+)?(.+)$",
                t,
            )
            dest = (m2.group(1) if m2 else "").strip(" .")
            self._emit("map_ui", {"place": dest, "markers": None})
            return self._flavor("ok", f"Flying the map to {dest}.")

        # ABC News + gesture HUD (before generic web search)
        if re.search(
            r"\b((pull|bring|put|show|open|launch) (up |on )?(the )?(abc )?news|"
            r"abc news|news (panel|overlay|feed|on camera)|"
            r"show (me )?(the )?news)\b",
            t,
        ):
            self.habits.log("news_abc")
            self._emit("news_ui", True)
            return self._flavor(
                "ok",
                "Pulling up ABC News. Camera gesture control is on — "
                "pinch and drag to move the panel, swipe for the next story.",
            )
        if re.search(r"\b(close|hide) (the )?(abc )?news( panel| overlay| feed)?\b", t):
            self._emit("news_ui", False)
            return self._flavor("ok", "Closing the news panel.")

        if re.search(
            r"\b((show|put|move) (stats|ops|operations|command center) on (the )?(other|second) (monitor|screen|display)|"
            r"ops (board|monitor)|show ops|open ops)\b",
            t,
        ):
            self._emit("show_ops", True)
            self._emit("place_ops", "secondary")
            return self._flavor(
                "ok",
                "Operations board is on your other monitor — live stats and data feed.",
            )
        if re.search(
            r"\b((put|move) (jarvis|hud|yourself) on (the )?(other|second) (monitor|screen|display)|"
            r"jarvis on (the )?other (monitor|screen))\b",
            t,
        ):
            self._emit("place_hud", "secondary")
            try:
                self.settings.hud_monitor = "secondary"
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Moving the main HUD to your other monitor.")
        if re.search(
            r"\b((put|move) (jarvis|hud) on (the )?(main|primary) (monitor|screen|display)|"
            r"jarvis on (the )?main (monitor|screen))\b",
            t,
        ):
            self._emit("place_hud", "primary")
            try:
                self.settings.hud_monitor = "primary"
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Moving the main HUD back to your primary monitor.")
        if re.search(r"\b(list (my )?monitors|what monitors|display (layout|setup))\b", t):
            from jarvis.core.displays import displays

            return self._flavor("ok", displays.describe())
        if re.search(
            r"\b(open (apps|things|windows) on (the )?(other|second) (monitor|screen)|"
            r"use (the )?other monitor)\b",
            t,
        ):
            self.settings.open_on_other_monitor = True
            self.apps.open_on_other = True
            try:
                self.settings.save()
            except Exception:
                pass
            self._emit("show_ops", True)
            return self._flavor(
                "ok",
                "Understood. I will open apps and show the ops board on your other monitor.",
            )

        # Command center / stats / data feed
        if re.search(
            r"\b((show|my) (stats|statistics|command center)|data feed|"
            r"what(?:'s| is) the (status|overview)|ops (brief|status))\b",
            t,
        ):
            packet = self.wake_brief.compose(mode="stats")
            self._emit("stats", packet["stats"])
            self._emit("feed", self.feed.lines_for_ui(18) or packet["feed_lines"])
            self._emit("show_ops", True)
            return self._flavor("ok", packet["speak"])

        # Time / date
        if re.search(r"\b(what time|current time|tell me the time)\b", t):
            return self._flavor("time", datetime.now().strftime("It's %I:%M %p."))
        if re.search(r"\b(what(?:'s| is) the date|today'?s date|what day)\b", t):
            return self._flavor("time", datetime.now().strftime("Today is %A, %B %d, %Y."))

        # Weather
        if re.search(r"\b(weather|temperature|how hot|how cold)\b", t):
            self._emit("weather_ui", True)
            self.habits.log("weather")
            return self._flavor("weather", self.weather.speak_brief())

        # Daily brief / schedule / email
        if re.search(
            r"\b(what(?:'s| is) my schedule|my schedule|daily brief|"
            r"brief me|what(?:'s| is) on (my )?(calendar|agenda)|upcoming meetings)\b",
            t,
        ):
            self.habits.log("schedule")
            return self._flavor("ok", self.brief.summarize(open_inbox=True))
        if re.search(r"\b(check (my )?email|open (my )?(mail|inbox|outlook)|check (my )?gmail)\b", t):
            self.habits.log("email")
            return self._flavor("ok", self.brief.summarize(open_inbox=True))

        # Tell me about my day — habits + priorities
        if re.search(
            r"\b(tell me about my day|how(?:'s| is) my day|what should i (do|prioritize|focus on)|"
            r"my priorities|plan my day)\b",
            t,
        ):
            cal = self.brief.schedule_only()
            self.habits.log("day_review")
            return self._flavor("ok", self.habits.tell_me_about_my_day(cal))

        # Work mode
        if re.search(
            r"\b(i'?m starting work|start(ing)? work|work mode|focus mode|"
            r"time to work|let'?s work)\b",
            t,
        ):
            self.habits.log("work_mode", "start")
            return self._flavor("ok", self.work.start_work())
        if re.search(r"\b(end work|stop work|done (for|working)|finish work mode)\b", t):
            self.habits.log("work_mode", "end")
            return self._flavor("ok", self.work.end_work())

        # Tasks
        m = re.search(r"\b(?:add task|new task|todo)\s+(.+)$", t)
        if m:
            self.habits.log("task_add")
            return self._flavor("ok", self.brief.add_task(m.group(1)))
        m = re.search(r"\b(?:done|finish(?:ed)?|complete)\s+task\s+(.+)$", t)
        if m:
            self.habits.log("task_done")
            return self._flavor("ok", self.brief.complete_task(m.group(1)))

        # Contextual reverse-image / "search for this image"
        if re.search(
            r"\b(search (for )?(this|that) image|reverse( image)? search|"
            r"look up (this|that) (image|photo|object|item)|"
            r"search (for )?(this|that) (object|item|thing))\b",
            t,
        ):
            if self._scanning:
                return "Already scanning — one moment."
            self._scanning = True
            self.habits.log("image_search")
            self._emit("scan_now", True)
            return self._flavor(
                "scan",
                "I'll identify it from the camera — hold it in the green box.",
            )

        # Open Lens only when user asks (scan no longer auto-opens tabs)
        if re.search(
            r"\b(search it online|open (the )?(search|lens|results)|"
            r"google (this|that|it)|look it up online)\b",
            t,
        ):
            # Prefer last web search page if recent; else scanner lens
            if self.net.last_results or (self.net.last_query and "lens" not in t):
                if re.search(r"\b(lens|image)\b", t):
                    return self._flavor("ok", self.scanner.open_last_search())
                return self._flavor("ok", self.net.open_results_page())
            return self._flavor("ok", self.scanner.open_last_search())

        # Open a numbered web result
        m = re.search(r"\bopen (?:search )?result(?:s)?\s*(?:number\s*)?(\d+)\b", t)
        if m:
            return self._flavor("ok", self.net.open_result(int(m.group(1))))
        if re.search(r"\b(open (the )?(first|top) (result|link)|open that link)\b", t):
            return self._flavor("ok", self.net.open_result(1))
        if re.search(r"\b(show search results|open (the )?search (page|brief))\b", t):
            return self._flavor("ok", self.net.open_results_page())

        # Internet search — Jarvis searches & summarizes (not just a Google tab)
        m = re.search(
            r"\b(?:search (?:the )?(?:web|internet|net)(?: for)?|"
            r"google|look up|look it up|browse(?: for)?|"
            r"search online(?: for)?)\s+(.+)$",
            t,
        )
        if not m:
            m = re.search(r"\b(?:search|find online)\s+(.+)$", t)
        if m:
            q = m.group(1).strip()
            # Don't steal image / local business intents
            if re.search(r"^(this|that)\s+(image|photo|object|item|thing)$", q):
                if self._scanning:
                    return "Already scanning — one moment."
                self._scanning = True
                self._emit("scan_now", True)
                return self._flavor("scan", "On it — identifying it from the camera.")
            if re.search(
                r"\b(near me|nearby|coffee|cafe|restaurant|plumber|pizza)\b", q
            ) and not re.search(r"\b(wiki|wikipedia|news|who is|what is)\b", q):
                # Let business finder handle local places (already matched earlier usually)
                pass
            else:
                self.habits.log("web_search", q[:40])
                self._emit("fetching", True)
                self.feed.push("net", f"Searching: {q}")
                reply = self.net.search(q, open_page=True)
                self.feed.push("net", reply[:220])
                self._push_stats_ui()
                return self._flavor("ok", reply)

        # What / who / define — encyclopedic internet answers
        m = re.search(
            r"\b(?:what(?:'s| is)|who(?:'s| is)|define|explain|tell me about)\s+(.+)$",
            t,
        )
        if m:
            topic = m.group(1).strip(" ?.")
            # Skip system/local intents already handled
            if not re.search(
                r"\b(my schedule|the weather|the time|the date|my spend|"
                r"you|jarvis|this|that)\b",
                topic,
                re.I,
            ):
                self.habits.log("web_search", topic[:40])
                self._emit("fetching", True)
                reply = self.net.search(topic, open_page=True)
                self.feed.push("net", reply[:220])
                return self._flavor("ok", reply)

        # Voice note-taking — dictate mode or screen grab
        if re.search(
            r"\b(take notes?|start notes?|dictat(e|ion)|note taking|"
            r"take a note|save (a )?note)\b",
            t,
        ) and not re.search(r"\b(show|list|open)\s+notes?\b", t):
            # "take a note about this" → screen; bare "take notes" → listen
            about = ""
            m = re.search(
                r"(?:take a note|save (?:a )?note|note|memo)(?:\s+about)?\s+(.+)$",
                t,
            )
            if m:
                about = m.group(1).strip()

            if about and about not in ("this", "that", "it") and "note" not in about:
                # Immediate content: "note buy milk"
                if about in ("notes", "note"):
                    pass
                elif not re.search(r"\b(this|that|screen)\b", about):
                    self.habits.log("note")
                    return self._flavor(
                        "ok",
                        self.notes.take(about, from_screen=False, audio=False),
                    )

            if re.search(r"\b(this|that|screen)\b", t):
                self.habits.log("note")
                return self._flavor(
                    "ok",
                    self.notes.take("", from_screen=True, audio=True),
                )

            # Enter listen / dictate mode
            self._note_mode = True
            self._note_buffer = []
            self.habits.log("note_mode")
            self._emit("track", "NOTE · listening")
            return (
                "I'm listening. Talk about whatever you want to note. "
                "Say 'done' when you want me to save it."
            )
        m = re.search(r"\b(?:remember|remind me(?: to)?)\s+(.+)$", t)
        if m and not re.search(r"\bremember (this|that)\b", t):
            note = m.group(1).strip()
            self.habits.log("note")
            return self._flavor(
                "ok", self.notes.take(note, from_screen=False, audio=False)
            )
        if re.search(r"\b(show notes|my notes|list notes|open notes)\b", t):
            if "open" in t:
                return self._flavor("ok", self.notes.open_log())
            return self.notes.list_recent()

        # Clipboard
        if re.search(r"\b(read clipboard|what(?:'s| is) on (my )?clipboard|clipboard)\b", t):
            if pyperclip is None:
                return "Clipboard module not installed."
            try:
                clip = pyperclip.paste()
                if not clip:
                    return "Clipboard is empty."
                return self._flavor("ok", f"Clipboard says: {clip[:200]}")
            except Exception:
                return "Could not read the clipboard."

        # Screenshot
        if re.search(r"\b(screenshot|screen shot|capture screen)\b", t):
            return self._flavor("ok", self._screenshot())

        # Volume — voice media control
        if re.search(r"\b(volume up|turn it up|louder|crank it)\b", t):
            return self._flavor("ok", self.music.volume_up())
        if re.search(r"\b(volume down|turn it down|quieter|lower the volume)\b", t):
            return self._flavor("ok", self.music.volume_down())
        if re.search(r"\b(volume max|max volume|full volume)\b", t):
            for _ in range(15):
                self.music.media_key("volup")
            return self._flavor("ok", "Volume raised.")

        # Settings shortcuts
        if re.search(r"\b(wifi|wi-?fi) settings\b", t):
            os.system("start ms-settings:network-wifi")
            return self._flavor("open", "Opening Wi-Fi settings.")
        if re.search(r"\bbluetooth settings\b", t):
            os.system("start ms-settings:bluetooth")
            return self._flavor("open", "Opening Bluetooth settings.")

        # Calculator / notepad
        if re.search(r"\b(open )?calculator\b", t):
            subprocess.Popen(["calc.exe"], shell=False)
            return self._flavor("open", "Calculator ready.")
        if re.search(r"\b(open )?notepad\b", t):
            return self._flavor("open", self.apps.open("notepad"))

        # Empty recycle / clean downloads hint
        if re.search(r"\b(empty recycle|clear recycle bin)\b", t):
            try:
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                    shell=False,
                )
                return self._flavor("ok", "Recycle Bin cleared.")
            except Exception as e:
                return f"Could not clear recycle bin: {e}"

        # START — bare engage only (never "start chrome" / "start music")
        if re.match(r"^(start|go|systems?( online| start)?)$", t.strip()):
            self.trigger_start()
            return self._flavor("ok", "Engaging systems.")

        # Music — playlists + tracks (never reply with "Pressed Play")
        if t in ("playpause", "toggle playback", "play pause", "toggle play"):
            return self._flavor("music", self.music.media_key("playpause"))
        if re.search(r"^\s*play\s*$", t) or t in (
            "play music",
            "resume music",
            "play some music",
            "start music",
            "put on music",
        ):
            self._emit("fetching", True)
            self._emit("track", "Now playing")
            self.habits.log("music")
            return self._flavor("music", self.music.play_music())
        # Ignore echo of old "press play" phrasing — just start music
        if t in ("press play", "pressed play"):
            return self._flavor("music", self.music.play_music())
        if re.search(r"\b(play (my )?focus( playlist)?|focus playlist)\b", t):
            self._emit("track", "Focus playlist")
            self._emit("fetching", True)
            self.habits.log("music", "focus")
            return self._flavor(
                "music", self.music.play_playlist(self.settings.focus_playlist)
            )
        m = re.search(r"\b(?:play|put on)\s+(.+)$", t)
        if m:
            q = m.group(1)
            self._emit("track", q)
            self._emit("fetching", True)
            self.habits.log("music", q[:40])
            return self._flavor("music", self.music.play(q))
        if re.search(r"\b(pause|stop music)\b", t):
            return self._flavor("music", self.music.media_key("playpause"))
        if re.search(r"\b(next( track)?|skip)\b", t):
            return self._flavor("music", self.music.media_key("next"))
        if re.search(r"\b(previous|last track)\b", t):
            return self._flavor("music", self.music.media_key("previous"))
        if re.search(r"\bmute\b", t):
            return self._flavor("music", self.music.media_key("mute"))

        # What am I doing / what do you see
        if re.search(
            r"\b(what am i doing|what(?:'s| is) (going on|happening)|what do you see|"
            r"look at me|describe (what you see|the (scene|room|me))|"
            r"can you see me|am i (here|visible)|watch me)\b",
            t,
        ):
            self.habits.log("activity")
            return self._describe_activity()

        # Scan item through camera (one-shot — camera closes when done)
        if re.search(
            r"\b(scan|scan (this|that|it|item|object)|what(?:'s| is) this|"
            r"identify|read (the )?text|ocr)\b",
            t,
        ):
            if self._scanning:
                return "Already scanning — one moment."
            self._scanning = True
            self.habits.log("scan")
            self._emit("scan_now", True)
            return self._flavor("scan", "Hold it steady in the green box — I'll tell you what it is.")

        # Camera / EMEET (accepts typos like "camrea") — NEVER shell-open as a file
        if is_camera_query(t) and not re.search(r"\b(close|hide|scan)\b", t):
            try:
                self.vision.stop()
            except Exception:
                pass
            self._emit("camera_ui", True)
            return self._flavor(
                "open",
                "Opening full-screen camera theater. "
                "ABC News Live is top-left — Jarvis is bottom-right and draggable. "
                "Pinch to move panels.",
            )
        if re.search(r"\b(close|hide)\s+(the\s+|my\s+)?(cam|camera|camrea|webcam|emeet)\b|\bcamera\s+off\b", t):
            self._emit("camera_ui", False)
            # UI restarts presence after the device is released — don't race here
            return self._flavor("ok", "Camera closed. Presence lock re-armed.")

        # Open apps / folders / sites
        m = re.search(r"\b(?:open|launch|start)\s+(.+)$", t)
        if m:
            target = m.group(1).strip()
            if is_camera_query(target) or is_camera_query("open " + target):
                try:
                    self.vision.stop()
                except Exception:
                    pass
                self._emit("camera_ui", True)
                return self._flavor("open", "Opening your EMEET USB SmartCam.")
            result = self.apps.open(target)
            if result == "CAMERA_UI":
                try:
                    self.vision.stop()
                except Exception:
                    pass
                self._emit("camera_ui", True)
                return self._flavor("open", "Opening your EMEET USB SmartCam.")
            self.habits.log("open_app", target[:40])
            return self._flavor("open", result)

        # Lock / shutdown / clap wake standby
        if re.search(r"\b(lock( (the )?(pc|computer|workstation))?|lock screen)\b", t):
            return self._flavor("lock", self.system.lock())
        if re.search(
            r"\b(standby for clap|sleep for (clap|wake)|clap (wake|standby)|ready for clap)\b",
            t,
        ):
            return self._flavor("lock", self.system.sleep())
        if re.search(r"\b(sleep|suspend|standby)\b", t) and not re.search(
            r"\b(how|what|did|music|playlist)\b", t
        ):
            return self._flavor("lock", self.system.sleep())
        if re.search(r"\b(wake.?on.?lan|wol status|my mac( address)?|clap wake status)\b", t):
            return self._flavor("ok", self.system.wol_status())
        if re.search(r"\bconfirm shutdown\b", t):
            return self._flavor("lock", self.system.shutdown(confirm=True))
        if re.search(r"\b(shut ?down|power off|turn off (the )?(pc|computer))\b", t):
            self._pending_shutdown = True
            return (
                "Say 'confirm shutdown' to power off, or 'standby for clap' "
                "so a double-clap on your wake device can bring me back, {name}."
            ).format(name=self.settings.user_name)

        # Kill process
        m = re.search(r"\b(?:kill|close|force close)\s+(.+)$", t)
        if m:
            name = m.group(1).strip()
            if is_camera_query(name):
                self._emit("camera_ui", False)
                try:
                    self.vision.start()
                except Exception:
                    pass
                return self._flavor("ok", "Camera closed.")
            return self._flavor("ok", self.system.kill_named([name]))

        # Status
        if re.search(r"\b(status|system (status|vitals)|how(?:'s| is) (the )?(cpu|system))\b", t):
            tel = self.system.telemetry()
            bat = f"{tel.battery:.0f}%" if tel.battery is not None else "AC"
            return self._flavor(
                "ok",
                f"CPU {tel.cpu:.0f} percent, memory {tel.memory:.0f} percent, battery {bat}.",
            )

        # Update software
        if re.search(r"\b(update software|add (a )?feature|hot.?reload|patch system)\b", t):
            self.voice.mute_mic(True)
            self._emit("update_ui", True)
            return "Update panel open. Type your request — I will sandbox it."

        # Watchdog lifecycle — reload core (exit 0) or go fully offline (exit 99)
        if re.search(
            r"\b(reload (the )?core|reboot (jarvis|core)|restart jarvis)\b",
            t,
        ):
            self._emit("app_exit", 0)
            return self._flavor(
                "ok",
                "Reloading environment layers. Watchdog will bring me back momentarily.",
            )
        if re.search(
            r"\b(go offline|power down( jarvis)?|quit jarvis|exit jarvis|shut down jarvis)\b",
            t,
        ):
            self._emit("app_exit", 99)
            return self._flavor(
                "ok",
                "Powering down Jarvis application matrix layers. Goodbye, Sir.",
            )

        # ── Environmental / contextual intelligence ──────────────
        if re.search(r"\b(coding mode|code mode|bright (lights?|white))\b", t):
            return self._flavor("ok", self.lights.set_mode("coding"))
        if re.search(r"\b(reading mode|warm (lights?|amber)|read mode)\b", t):
            return self._flavor("ok", self.lights.set_mode("reading"))
        if re.search(r"\b(late night( mode)?|night mode|dim red)\b", t):
            return self._flavor("ok", self.lights.set_mode("late_night"))
        if re.search(r"\b(night vision( on)?|enable night vision|nvg( on)?)\b", t):
            return self._flavor("ok", self.set_night_vision(True, announce=True))
        if re.search(r"\b(night vision off|disable night vision|nvg off)\b", t):
            return self._flavor("ok", self.set_night_vision(False, announce=True))
        if re.search(r"\b(brown noise|focus noise|soundscape|binaural)\b", t):
            return self._flavor("ok", self.soundscape.play_brown_noise())
        if re.search(r"\b(calm audio|calming audio|play calm)\b", t):
            return self._flavor("ok", self.soundscape.play_calm())
        if re.search(r"\b(stop (the )?(noise|soundscape|ambient))\b", t):
            return self._flavor("ok", self.soundscape.stop())

        # Diary / productivity
        if re.search(
            r"\b(how was my productivity|productivity (this )?week|week(ly)? report|"
            r"how did i do this week)\b",
            t,
        ):
            return self._flavor("ok", self.diary.week_report())
        if re.search(r"\b(log (a )?win|i (finished|shipped|completed))\b", t):
            self.diary.log_win(t)
            return self._flavor("ok", "Logged that win in your encrypted diary.")

        # Visual memory
        m = re.search(
            r"\b(?:remember (this|that)(?: as)?|memorize (this|that)(?: as)?)\s*(.*)$",
            t,
        )
        if m:
            label = (m.group(3) or "object").strip() or "object"
            frame = self._last_frame
            if frame is None:
                frame = grab_camera_frame(
                    self.settings.camera_index, self.settings.camera_prefer
                )
            if frame is None:
                return "I need a camera frame — look at the object and try again."
            return self._flavor("ok", self.vmemory.remember(frame, label=label))
        if re.search(
            r"\b(where did i put|where is (that|the)|what did (that|the) .+ look like|"
            r"recall (the )?|find (that|the) (manual|tool|object))\b",
            t,
        ):
            return self._flavor("ok", self.vmemory.recall(t))

        # What did I miss / return brief
        if re.search(
            r"\b(what did i miss|catch me up|missed (emails?|messages?)|"
            r"summary of (what i )?missed)\b",
            t,
        ):
            self.return_brief._away_since = time.time() - 600
            msg = self.return_brief.mark_present() or self.brief.summarize(open_inbox=False)
            return self._flavor("ok", msg)

        # Theme / boost / panic — OFF patterns first so "panic off" never re-triggers
        if re.search(r"\b(dark mode|night theme)\b", t):
            return self._flavor("ok", self.theme_sync.set_dark(True))
        if re.search(r"\b(light mode|day theme)\b", t):
            return self._flavor("ok", self.theme_sync.set_dark(False))
        if re.search(r"\b(sync theme|adaptive theme)\b", t):
            return self._flavor("ok", self.theme_sync.apply_for_hour())
        if re.search(r"\b(boost( mode)?|performance boost|game mode)\b", t):
            return self._flavor("ok", self.boost.boost())
        if re.search(r"\b(restore processes|end boost)\b", t):
            return self._flavor("ok", self.boost.restore())
        if re.search(
            r"\b("
            r"cancel panic|end panic|panic off|clear panic|stand down|"
            r"turn off panic|stop panic|exit panic|disable panic|"
            r"panic mode off|leave panic"
            r")\b",
            t,
        ):
            return self.clear_panic()
        if re.search(r"\b(unmute( (the )?mic)?|listen( again)?|use my mic|start listening)\b", t):
            try:
                self.voice.mute_mic(False)
                self.voice.set_busy(False)
            except Exception:
                pass
            if self._panic_active:
                return self.clear_panic()
            return "Microphone live. I'm listening."

        # Screen / tabs awareness — help with what the user is doing
        if re.search(
            r"\b(look at (my )?(screen|desktop|monitor)|see (my )?(screen|desktop)|"
            r"what('?s| is) on (my )?(screen|display)|read (my )?screen|"
            r"what (am i|are we) (looking at|doing|working on)|"
            r"what('?s| is) (this|that) (tab|page|window)|"
            r"see my tabs|what tabs (do i have|are open)|my (open )?tabs)\b",
            t,
        ):
            self._emit("fetching", True)
            self._emit("hud_alert", "Reading your screen & tabs…")

            def _job() -> None:
                try:
                    msg = self.screen.describe(ocr=True)
                    self.feed.push("screen", msg[:180], meta={"status": "done"})
                    self.say(self._flavor("ok", msg))
                except Exception as e:
                    self.say(f"I couldn't read the screen cleanly: {e}")

            threading.Thread(target=_job, daemon=True, name="screen-see").start()
            return "Looking at your screen and tabs now."

        if re.search(
            r"\b(help me with (this|that|my (task|work|screen))|"
            r"help (me )?(with|on) (this|that|my .{2,40})|"
            r"can you help( me)?( with (this|that))?|"
            r"what should i do( (next|here))?|"
            r"guide me( through (this|that))?)\b",
            t,
        ):
            self._emit("fetching", True)
            task = re.sub(
                r"^(jarvis[, ]*)?(please )?|"
                r"help me with |help with |can you help( me)?( with)? |"
                r"guide me( through)? ",
                "",
                t,
                flags=re.I,
            ).strip(" ?.")
            if task in ("this", "that", "my task", "my work", "my screen", ""):
                task = ""

            def _help() -> None:
                try:
                    msg = self.screen.help_with(task)
                    self.feed.push("screen", msg[:180], meta={"status": "running"})
                    self.say(self._flavor("ok", msg))
                except Exception as e:
                    self.say(f"Screen help failed: {e}")

            threading.Thread(target=_help, daemon=True, name="screen-help").start()
            return "Reading your screen so I can help…"

        # Computer-use: click on-screen text
        m = re.search(
            r"\b(?:click|press|tap|hit)\s+(?:(?:on|the)\s+)?(.+)$",
            t,
        )
        if m and not re.search(r"\b(play|pause|mute|camera|lock)\b", t):
            label = m.group(1).strip().strip("\"'")
            if 1 < len(label) < 48:
                self._emit("fetching", True)
                return self._flavor("ok", self.computer.click_text(label))

        # Custom autonomous instructions
        if re.search(r"\b(add instruction|add behavior|from now on|always remember)\b", t):
            return self._flavor("ok", self.instructions.append(t))
        if re.search(r"\b(show (my )?instructions|list instructions|custom behaviors)\b", t):
            blob = self.instructions.context_snippet(400) or "No custom instructions yet."
            return self._flavor("ok", blob)
        if re.search(r"\b(clear instructions|reset instructions)\b", t):
            return self._flavor("ok", self.instructions.clear())

        if re.search(r"\b(privacy mode|hide everything|ghost mode)\b", t):
            return self.ghost_mode()
        if re.search(r"\bpanic( mode)?\b", t) and not re.search(
            r"\b(off|cancel|end|clear|stop|exit|disable)\b", t
        ):
            return self.panic_now()

        # Compliments / opinions — "what do you think of this"
        if re.search(
            r"\b(what do you think( of (this|that|it))?|how does (this|that) look|"
            r"opinion( on (this|that))?|thoughts( on (this|that))?|"
            r"rate (this|that)|be honest|tell me what you think)\b",
            t,
        ):
            return self._opinion_on_view()
        if re.search(
            r"\b(compliment me|say something nice|do i look good|"
            r"how do i look|flatter me)\b",
            t,
        ):
            return self.persona.compliment()

        # End-of-day recap
        if re.search(
            r"\b(daily recap|end of (the )?day|wins and growth|how was my day|"
            r"wrap up( my day)?|good ?night recap)\b",
            t,
        ):
            return self._flavor("ok", self.daily_recap())

        # Collaborative memory — browser history
        if re.search(
            r"\b(what was i (looking at|working on)|what did i (look at|browse)|"
            r"what was that thing i was looking at|yesterday'?s (tabs|pages|history)|"
            r"browser history)\b",
            t,
        ):
            hours = 48 if "yesterday" in t else 24
            return self._flavor("ok", self.chrome_hist.recent(hours=hours))

        # Calm down routine
        if re.search(r"\b(calm down|i'?m stressed|help me relax|breathe)\b", t):
            self.soundscape.play_calm(0.14)
            self.lights.set_mode("calm")
            return self.emotion.support_line(self.settings.user_name)

        # Heart / posture status
        if re.search(r"\b(my (heart rate|pulse)|how is my posture)\b", t):
            b = self.context.bio.last
            hr = f"{b.heart_rate_bpm:.0f} bpm" if b.heart_rate_bpm else "still measuring"
            post = "upright" if b.posture_ok else "a bit slumped"
            return self._flavor("ok", f"Heart rate estimate {hr}. Posture looks {post}.")

        # Workspace quick setup (from suggestion chip)
        if re.search(r"\b(set up (my )?(morning )?workspace|morning setup)\b", t):
            return self._flavor("ok", self.work.start_work())

        # Help
        if re.search(r"\b(help|what can you do|commands|list commands)\b", t):
            return (
                f"At your service, {self.settings.user_name}. "
                "Try: open camera, pull up the news, open map view, "
                "build a site, start vibe coding, find biz, "
                "away mode, show stats, play music, sleep, or lock. "
                "Shortcuts: site · vibe · camera · screen · music · sarah · tom · admin. "
                "Say panic off to leave panic mode. "
                "HITL: approve / deny before deploy. "
                "Hub: hub status · hub standby."
            )

        # Contextual "do that" via thought stream
        if re.search(r"\b(do that|actually wait|the other)\b", t):
            recent = self.voice.stream.recent()
            if len(recent) >= 2:
                return self._route(recent[-2])

        return self.persona.fallback()

    def _screenshot(self) -> str:
        try:
            import pyautogui

            folder = Path.home() / "Pictures" / "Jarvis"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            pyautogui.screenshot(str(path))
            return f"Screenshot saved to {path}"
        except Exception as e:
            return f"Screenshot failed: {e}"

    def apply_update_request(self, text: str) -> str:
        self.voice.mute_mic(False)
        self._emit("update_ui", False)
        # Persist as custom behavior + hot-load stub plugin
        note = self.instructions.append(text)
        plugin = self.updater.apply(text)
        return f"{note} {plugin}"

    def _describe_activity(self) -> str:
        """Look through the camera and say what the user appears to be doing."""
        frame = self._last_frame
        if frame is None:
            getter = self.ui.get("get_camera_frame")
            if callable(getter):
                try:
                    frame = getter()
                except Exception:
                    frame = None
        if frame is None:
            frame = grab_camera_frame(
                self.settings.camera_index, self.settings.camera_prefer
            )
        line = self.activity.describe(frame)
        if frame is not None:
            self._last_frame = frame
        return self._flavor("ok", line)

    def _opinion_on_view(self) -> str:
        """Comment / compliment on whatever is in front of the camera — no command echo."""
        frame = self._last_frame
        if frame is None:
            getter = self.ui.get("get_camera_frame")
            if callable(getter):
                try:
                    frame = getter()
                except Exception:
                    frame = None
        if frame is None:
            frame = grab_camera_frame(
                self.settings.camera_index, self.settings.camera_prefer
            )
        if frame is not None:
            self._last_frame = frame
        # Prefer identifying a held item; fall back to scene description
        detail = ""
        try:
            detail = (self.activity.identify_item(frame) or "").strip()
        except Exception:
            detail = ""
        if not detail or len(detail) < 12:
            try:
                detail = (self.activity.describe(frame) or "").strip()
            except Exception:
                detail = ""
        return self.persona.opinion_comment(detail)

    def scan_frame(self, frame, ocr: bool = True) -> str:
        self._scanning = True
        self._last_frame = frame
        try:
            result = self.scanner.scan_frame(
                frame,
                ocr=ocr,
                open_browser=False,
                identify=self.activity.identify_item,
            )
            query = result.get("query") or "unknown item"
            detail = (result.get("description") or result.get("reply") or "").strip()
            spoken = self.persona.scan_line(query)
            full = f"{spoken} {detail}".strip()
            self._emit("scan_result", full)
            self._emit(
                "artifact",
                {
                    "title": "SCAN",
                    "text": full,
                    "meta": f"query · {query}",
                    "frame": frame,
                },
            )
            self._emit("track", f"SCAN · {query}")
            return full
        finally:
            self._scanning = False
            # Stop scanning UI / close camera as soon as the one shot is done
            self._emit("scan_done", True)

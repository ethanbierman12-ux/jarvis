"""Jarvis brain — intent routing, bonded to UI callbacks."""

from __future__ import annotations

import re
import threading
import time
import webbrowser
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
from jarvis.core.alexa_lamp import AlexaLamp
from jarvis.core.phone_bridge import PhoneBridge
from jarvis.core.rlhf import RLHFEngine
from jarvis.core.soundscape import Soundscape
from jarvis.core.diary import Diary, VisualMemory
from jarvis.core.memory import VectorMemory
from jarvis.core.audio_devices import AudioRouter
from jarvis.core.home_assistant import HomeAssistant
from jarvis.core.macro_gateway import MacroGateway
from jarvis.core.companion_server import CompanionServer, make_token
from jarvis.core.companion_pack import build_companion_setup_zip, companion_url
from jarvis.core.task_queue import TaskQueue
from jarvis.core.folder_watch import FolderWatch, is_watch_noise
from jarvis.core.n8n_bridge import N8nBridge
from jarvis.core.manus_bridge import ManusBridge
from jarvis.core.cloud_integrations import CloudIntegrations
from jarvis.core.manus_code_assist import (
    CODE_EXTS,
    ManusCodeAssistOffer,
    build_review_prompt,
    build_snapshot,
    is_code_path,
)
from jarvis.core.edge_router import route_complexity
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
from jarvis.core.computer_use_agent import ComputerUseAgent, looks_like_computer_use_goal
from jarvis.core.instructions import CustomInstructions
from jarvis.core.screen_context import ScreenContext
from jarvis.core.hub_client import HubClient
from jarvis.core.commands import normalize_command, is_fast_local_command
from jarvis.core.intent_router import maybe_rewrite
from jarvis.core.zero_env import ensure_agent_dirs, log_hitl
from jarvis.core.travis import TravisController, parse_mode_command
from jarvis.core.feature_registry import FeatureRegistry
from jarvis.core.workflows import WorkflowEngine
from jarvis.core.live_context import LiveContext
from jarvis.core.mood_engine import MoodEngine
from jarvis.core.proactive_agent import ProactiveAgent
from jarvis.core.github_autocommit import GitHubAutoCommitter
from jarvis.core.smart_calendar import SmartCalendar
from jarvis.core.topic_monitor import TopicMonitor
from jarvis.core.price_monitor import PriceMonitor
from jarvis.core.media_presence import MediaPresenceController
from jarvis.core.voice_to_code import VoiceToCode
from jarvis.core.security_gate import SecurityGate
from jarvis.core.voice_hotkeys import VoiceHotkeys
from jarvis.core.gesture_commander import GestureCommander
from jarvis.core.autobug import AutoBug
from jarvis.core.self_audit import SelfAudit
from jarvis.core.semantic_router import SemanticRouter, Lane
from jarvis.config import DATA_DIR, ROOT
import urllib.parse
import os
import subprocess
from pathlib import Path

try:
    import pyperclip
except Exception:  # optional
    pyperclip = None  # type: ignore


def _now_in_timezone(tz_name: str | None = None) -> datetime:
    """Wall-clock in settings timezone (default America/New_York); safe fallback."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo((tz_name or "America/New_York").strip() or "America/New_York"))
    except Exception:
        return datetime.now()


def is_night_hour_window(hour: int, start: int, end: int) -> bool:
    """Overnight-aware hour window. E.g. 19→6: night if hour>=19 or hour<6."""
    hour = int(hour) % 24
    start = int(start) % 24
    end = int(end) % 24
    if start == end:
        return False
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


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
        try:
            self.cu_agent = ComputerUseAgent()
            self.cu_agent.configure_from_settings(settings)
            self.cu_agent.on_status = self._on_computer_use_status
        except Exception as e:
            print(f"[computer-use] agent init: {e}")
            self.cu_agent = None
        self.screen = ScreenContext()
        self.hub = HubClient(
            base_url=getattr(settings, "hub_url", "") or "http://127.0.0.1:8787",
            enabled=bool(getattr(settings, "hub_enabled", True)),
            auto_start=bool(getattr(settings, "hub_auto_start", True)),
            on_log=lambda m: self._emit("heard", f"[hub] {m}"),
        )
        self.instructions = CustomInstructions()
        self.weather = Weather(
            settings.city,
            settings.openweather_api_key,
            units=getattr(settings, "weather_units", "f") or "f",
            timezone=getattr(settings, "timezone", "America/New_York")
            or "America/New_York",
        )
        self.governor = SystemGovernor(
            max_vision_fps=int(getattr(settings, "presence_check_fps", 3) or 3),
            performance_mode=bool(getattr(settings, "performance_mode", False)),
        )
        self._gov_vision_fps = -1
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
        self.vstore = VectorMemory()
        self.audio = AudioRouter()
        self.tasks = TaskQueue(workers=2)
        self.ha = HomeAssistant(
            url=getattr(settings, "ha_url", "") or "",
            token=getattr(settings, "ha_token", "") or "",
            enabled=bool(getattr(settings, "ha_enabled", False)),
        )
        self.lamp = AlexaLamp(
            device_name=getattr(settings, "alexa_lamp_name", "Lamp") or "Lamp",
            ha=self.ha,
            ha_entity=getattr(settings, "alexa_lamp_entity", "light.lamp")
            or "light.lamp",
            ifttt_key=getattr(settings, "alexa_ifttt_key", "") or "",
            ifttt_on_event=getattr(settings, "alexa_ifttt_on_event", "jarvis_lamp_on")
            or "jarvis_lamp_on",
            ifttt_off_event=getattr(settings, "alexa_ifttt_off_event", "jarvis_lamp_off")
            or "jarvis_lamp_off",
            on_webhook=getattr(settings, "alexa_lamp_on_webhook", "") or "",
            off_webhook=getattr(settings, "alexa_lamp_off_webhook", "") or "",
            voice_relay=bool(getattr(settings, "alexa_voice_relay", True)),
            audio=self.audio,
            say_wait=lambda phrase: self.voice.say_wait(phrase, polish=False),
            restore_output=getattr(settings, "alexa_restore_output", "WG1") or "WG1",
        )
        topic = (getattr(settings, "phone_ntfy_topic", "") or "").strip()
        self.phone = PhoneBridge(
            topic=topic,
            server=getattr(settings, "phone_ntfy_server", "") or "https://ntfy.sh",
            shortcuts_webhook=getattr(settings, "phone_shortcuts_webhook", "") or "",
            enabled=bool(getattr(settings, "phone_enabled", True)),
        )
        self.rlhf = RLHFEngine()
        self.n8n = N8nBridge(
            base_url=getattr(settings, "n8n_url", "") or "",
            api_key=getattr(settings, "n8n_api_key", "") or "",
        )
        try:
            self.cloud = CloudIntegrations(
                stripe_secret_key=getattr(settings, "stripe_secret_key", "") or "",
                notion_token=getattr(settings, "notion_token", "") or "",
                buffer_access_token=getattr(settings, "buffer_access_token", "") or "",
                gmail_access_token=getattr(settings, "gmail_access_token", "") or "",
            )
        except Exception:
            self.cloud = CloudIntegrations()
        try:
            self.manus = ManusBridge(
                api_key=getattr(settings, "manus_api_key", "") or "",
                enabled=bool(getattr(settings, "manus_enabled", True)),
                agent_profile=getattr(settings, "manus_agent_profile", "") or "manus-1.6",
                base_url=getattr(settings, "manus_base_url", "") or "",
            )
        except Exception:
            self.manus = ManusBridge()
        self._manus_code_offer: ManusCodeAssistOffer | None = None
        self.code_watch: FolderWatch | None = None
        try:
            debounce = float(
                getattr(settings, "manus_code_assist_debounce_sec", 45) or 45
            )
            cooldown = float(
                getattr(settings, "manus_code_assist_cooldown_sec", 720) or 720
            )
            self._manus_code_offer = ManusCodeAssistOffer(
                debounce_sec=debounce,
                cooldown_sec=cooldown,
                on_offer=self._offer_manus_code_assist,
            )
        except Exception:
            self._manus_code_offer = None
        self.macro: MacroGateway | None = None
        self.watch: FolderWatch | None = None
        self.theme_sync = ThemeSync(
            windows_enabled=bool(getattr(settings, "theme_sync_windows", False))
        )
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
        # Agent crew — six-agent pipeline (supervisor/research/memory/tools/comms/critic)
        self.crew = None
        if bool(getattr(settings, "crew_enabled", True)):
            try:
                from jarvis.core.agent_crew import AgentCrew

                self.crew = AgentCrew(
                    settings,
                    vstore=self.vstore,
                    internet=self.net,
                    phone=self.phone,
                    n8n=self.n8n,
                    computer_use=self.cu_agent,
                )
            except Exception as e:
                print(f"[crew] init: {e}")
        self._ghost = False
        self._pending_shutdown = False
        self._absent_since: float | None = None
        self._countdown_active = False
        self._presence_paused = False  # True while live camera / scanning
        self._scanning = False
        self._night_vision = False
        self._night_vision_auto_on = False
        self._nv_user_off = False  # manual off — blocks auto re-enable until dawn or "on"
        self._nv_user_on = False  # manual on — survives day auto-disable
        self._lock = threading.Lock()
        self._last_frame = None
        self._start_cooldown = 0.0
        self._handling = False
        self._note_mode = False
        self._note_mode_at = 0.0
        self._armed_until = 0.0
        self._memory_hint = ""
        self._note_buffer: list[str] = []
        self._persona_support = False
        self._last_reply = ""
        self._last_reply_at = 0.0
        self._panic_active = False
        self._quiet_mode = False
        self._quiet_saved_intruder: bool | None = None
        self._skip_suggestion_followups = False
        mic_pref = getattr(settings, "mic_prefer", "") or ""
        self.voice = VoiceEngine(
            on_heard=lambda t: self.handle_utterance(t, from_voice=True),
            voice=settings.tts_voice,
            rate=settings.tts_rate,
            pitch=getattr(settings, "tts_pitch", "-4Hz"),
            volume=getattr(settings, "tts_volume", "+0%"),
            noise_reduce=settings.noise_reduce,
            mic_prefer=mic_pref,
            on_level=lambda lvl: self._emit("mic_level", lvl),
            on_speaking=lambda on: self._emit("speaking", bool(on)),
            elevenlabs_api_key=getattr(settings, "elevenlabs_api_key", "") or "",
            elevenlabs_voice_id=getattr(settings, "elevenlabs_voice_id", "")
            or "pNInz6obpgDQ51uIfY1H",
            elevenlabs_model=getattr(settings, "elevenlabs_model", "")
            or "eleven_monolingual_v1",
            prefer_elevenlabs=bool(
                getattr(settings, "tts_prefer_elevenlabs", False)
            ),
            allow_virtual_mic=not bool(
                getattr(settings, "mic_reject_loopback", True)
            ),
            deepgram_api_key=getattr(settings, "deepgram_api_key", "") or "",
            deepgram_model=getattr(settings, "deepgram_model", "") or "nova-2",
            duplex_enabled=bool(getattr(settings, "duplex_voice", True)),
        )
        self._scan_open_browser = False
        self.vision = VisionService(
            camera_index=settings.camera_index,
            prefer=settings.camera_prefer,
            fps=settings.presence_check_fps,
            on_event=self._on_vision,
        )
        self.bedtime = BedtimeMode(self.system, ui=lambda d: self._emit("bedtime", d))
        self.persona = Personality(settings.user_name)
        self.travis = TravisController(
            getattr(settings, "travis_mode", "off") or "off"
        )
        self.persona.bind_travis(self.travis)
        try:
            self.router = SemanticRouter()
        except Exception:
            self.router = SemanticRouter()
        try:
            self.registry = FeatureRegistry()
        except Exception:
            self.registry = FeatureRegistry()  # infallible ctor
        try:
            self.workflows = WorkflowEngine(
                run_cmd=lambda c: self._route_workflow_step(c)
            )
        except Exception as e:
            print(f"[workflows] init: {e}")
            self.workflows = None  # type: ignore
        try:
            self.live = None
            self.mood = None
            self.gitbot = None
            self.calendar = None
            self.topics = None
            self.prices = None
            self.voice_code = None
            self.media_presence = None
            self.security = None
            self.hotkeys = None
            self.gestures = None
            self.autobug = None
            self.self_audit = None
            self.proactive = None
            # Per-module init — one failure must not wipe the rest
            try:
                self.live = LiveContext(
                    self.weather,
                    timezone=getattr(settings, "timezone", "America/New_York")
                    or "America/New_York",
                )
            except Exception as e:
                print(f"[live] init: {e}")
            try:
                self.mood = MoodEngine()
            except Exception as e:
                print(f"[mood] init: {e}")
            try:
                self.gitbot = GitHubAutoCommitter(
                    getattr(settings, "work_project_path", "") or ROOT,
                    auto_push=bool(getattr(settings, "github_auto_push", False)),
                )
            except Exception as e:
                print(f"[gitbot] init: {e}")
            try:
                self.calendar = SmartCalendar(DATA_DIR)
            except Exception as e:
                print(f"[calendar] init: {e}")
            try:
                self.topics = TopicMonitor()
                self.prices = PriceMonitor(DATA_DIR)
            except Exception as e:
                print(f"[topics/prices] init: {e}")
            try:
                self.voice_code = VoiceToCode()
            except Exception as e:
                print(f"[voice_code] init: {e}")
            try:
                self.media_presence = MediaPresenceController(
                    enabled=bool(getattr(settings, "media_pause_on_stand", True))
                )
            except Exception as e:
                print(f"[media_presence] init: {e}")
            try:
                self.security = SecurityGate(DATA_DIR, user_name=settings.user_name)
                self.security.enabled = bool(getattr(settings, "security_enabled", True))
                self.security.intruder_alert = bool(
                    getattr(settings, "intruder_alert", True)
                )
                try:
                    self.security.intruder_cooldown_sec = float(
                        getattr(settings, "intruder_alert_cooldown_sec", 720) or 720
                    )
                except Exception:
                    self.security.intruder_cooldown_sec = 720.0
                # Never auto OS-lock from camera unless lock_on_absence is on
                self.security.lock_on_leave = bool(
                    getattr(settings, "lock_on_absence", False)
                )
                self.security._save_meta()
            except Exception as e:
                print(f"[security] init: {e}")
            try:
                self.hotkeys = VoiceHotkeys(lock_fn=lambda: self.system.lock())
            except Exception as e:
                print(f"[hotkeys] init: {e}")
            try:
                self.gestures = GestureCommander(
                    run=lambda c: self._run_gesture_cmd(c)
                )
            except Exception as e:
                print(f"[gestures] init: {e}")
            try:
                self.autobug = AutoBug(DATA_DIR)
                self.self_audit = SelfAudit(DATA_DIR, ROOT)
            except Exception as e:
                print(f"[autobug/audit] init: {e}")
            try:
                self.proactive = ProactiveAgent(
                    telemetry_fn=lambda: self.system.telemetry(),
                    on_say=lambda t: self.say(t),
                    on_alert=lambda t: self._emit("hud_alert", t),
                    mood=self.mood,
                )
                self.proactive.set_enabled(
                    bool(getattr(settings, "proactive_enabled", True))
                )
            except Exception as e:
                print(f"[proactive] init: {e}")
            try:
                self.registry.register("live_context", version="1.0", note="Date/weather ground truth")
                self.registry.register("proactive", version="1.0", note="CPU/late/idle nudges")
                self.registry.register("github_autocommit", version="1.0", note="AI-ish commit+push")
                self.registry.register("smart_calendar", version="1.0", note="Spoken schedule → ICS")
                self.registry.register("security_gate", version="1.0", note="Face greet + intruder")
                self.registry.register("autobug", version="1.0", note="Error log triage")
                self.registry.register("self_audit", version="1.0", note="Nightly HITL proposals")
                self.registry.register(
                    "semantic_router",
                    version="1.0",
                    note="Local-first priority lanes → Hub only for complex",
                )
                self.registry.register(
                    "agent_crew",
                    version="1.1",
                    note="8-agent crew + debate: VECTOR/SCHOLAR/ARCHIVE/FORGE/HERALD/SENTINEL/CODESMITH/WARDEN",
                )
                self.registry.register(
                    "computer_use",
                    version="1.0",
                    note="Browser/desktop agent (Anthropic / OpenAI / browser-use)",
                )
            except Exception:
                pass
        except Exception as e:
            print(f"[productivity] init: {e}")

        self.governor.on_change(self._on_governor)
        self.states.on_change(self._on_state)

    # ── lifecycle ───────────────────────────────────────────────
    def start(self) -> None:
        self.resources.for_state("hud")
        self.vision.start()
        self.voice.start()
        self.context.start()
        self.game_focus.start()
        self.tasks.start()
        # Prefetcher used to silently open Chrome/Code on a schedule — off by default
        # self.prefetcher.start()
        # Boot: clean welcome only (loading was already spoken during overlay)
        welcome = "Welcome, Sir."
        try:
            welcome = self.persona.boot_welcome()
        except Exception:
            pass
        self._emit("speak_ui", welcome)
        self._emit("hud_alert", welcome)
        # Short delay so loading TTS + boot SFX can finish cleanly
        threading.Timer(0.55, lambda w=welcome: self.say(w)).start()
        self._emit("listening", False)
        # Discoverability — soft tip so the travel companion isn't a 80% secret
        threading.Timer(5.2, self._maybe_announce_companion).start()
        # Kill any leftover lock countdown from prior session
        try:
            self._countdown_active = False
            self._absent_since = None
            self._emit("countdown_cancel", True)
        except Exception:
            pass
        # Restore Travis visual if a mode was persisted
        if self.travis.active:
            self._emit("travis_ui", self.travis.mode.value)
        # Persist smooth / eco HUD if last session left it on
        try:
            if bool(getattr(self.settings, "performance_mode", False)):
                threading.Timer(
                    0.9, lambda: self._set_performance_mode(True)
                ).start()
        except Exception:
            pass
        threading.Timer(0.4, self._wake_command_center).start()
        threading.Timer(3.2, self._morning_weather_nudge).start()
        # Do NOT auto-apply Windows theme (was turning the taskbar white in daytime).
        # Optional one-shot repair if a prior build forced light system theme.
        try:
            if bool(getattr(self.settings, "theme_repair_dark_once", True)):
                def _repair_theme() -> None:
                    try:
                        msg = self.theme_sync.restore_dark_taskbar()
                        print(f"[theme] repair: {msg}")
                        self.settings.theme_repair_dark_once = False
                        self.settings.save()
                    except Exception as e:
                        print(f"[theme] repair skip: {e}")

                threading.Timer(1.6, _repair_theme).start()
        except Exception:
            pass
        # Night vision watch (engages after dusk)
        threading.Timer(2.5, self._night_vision_loop).start()
        # First proactive suggestion shortly after boot
        threading.Timer(6.0, self._offer_suggestion).start()
        # Keep offering contextual tips every few minutes
        self._suggest_timer_start()
        # Refresh command deck periodically
        threading.Timer(8.0, self._stats_pulse_loop).start()
        # Proactive agent — CPU / late night / long session
        try:
            threading.Timer(45.0, self._proactive_loop).start()
        except Exception:
            pass
        # Silent Stream Deck / macro pad
        if getattr(self.settings, "macro_gateway_enabled", True):
            try:
                self.macro = MacroGateway(
                    self.handle_macro,
                    port=int(getattr(self.settings, "macro_gateway_port", 8765) or 8765),
                )
                self.macro.start()
            except Exception as e:
                print(f"[macro] {e}")
        # iPhone companion PWA (Tailscale)
        if getattr(self.settings, "companion_enabled", True):
            try:
                self._boot_companion()
            except Exception as e:
                print(f"[companion] {e}")
        # Downloads / workspace watcher
        if getattr(self.settings, "watch_enabled", True):
            paths = list(getattr(self.settings, "watch_paths", None) or [])
            if not paths:
                paths = [str(Path.home() / "Downloads")]
            try:
                self.watch = FolderWatch(paths, self._on_new_file, enabled=True)
                self.watch.start()
            except Exception as e:
                print(f"[watch] {e}")
        # Manus code-assist: recursive watch on work project / jarvis (opt-in)
        try:
            self._boot_manus_code_watch()
        except Exception as e:
            print(f"[manus-code] watch: {e}")
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
        try:
            self._reactor_ha(mode)
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
        """Night window in settings.timezone (not PC local clock)."""
        try:
            tz = getattr(self.settings, "timezone", None) or "America/New_York"
            hour = _now_in_timezone(tz).hour
            start = int(getattr(self.settings, "night_vision_start_hour", 19) or 19)
            end = int(getattr(self.settings, "night_vision_end_hour", 6) or 6)
            return is_night_hour_window(hour, start, end)
        except Exception:
            return False

    def _frame_mean_luminance(self) -> float | None:
        """0..1 mean luminance from last camera frame; None if unavailable."""
        try:
            frame = getattr(self, "_last_frame", None)
            if frame is None:
                return None
            import numpy as np

            arr = np.asarray(frame)
            if arr.ndim == 3 and arr.shape[2] >= 3:
                # BGR → approximate luma
                gray = (
                    0.114 * arr[..., 0].astype(np.float32)
                    + 0.587 * arr[..., 1].astype(np.float32)
                    + 0.299 * arr[..., 2].astype(np.float32)
                )
            else:
                gray = arr.astype(np.float32)
            return float(np.mean(gray)) / 255.0
        except Exception:
            return None

    def _ambient_too_bright_for_nv(self) -> bool:
        """Skip auto-NV when the camera clearly sees daytime brightness."""
        try:
            lum = self._frame_mean_luminance()
            if lum is None:
                return False
            return lum >= 0.42
        except Exception:
            return False

    def _night_vision_loop(self) -> None:
        if getattr(self, "_stopped", False):
            return
        try:
            auto = bool(getattr(self.settings, "night_vision_auto", True))
            if auto:
                want = self._is_night_hours()
                # Clear manual-off latch once day window begins (ready for next dusk)
                if not want and getattr(self, "_nv_user_off", False):
                    self._nv_user_off = False
                # Never auto-enable during day; brightness gate blocks false dusk
                if (
                    want
                    and not self._night_vision
                    and not getattr(self, "_nv_user_off", False)
                    and not self._ambient_too_bright_for_nv()
                ):
                    self.set_night_vision(True, announce=True, auto=True)
                elif (
                    not want
                    and self._night_vision
                    and self._night_vision_auto_on
                    and not getattr(self, "_nv_user_on", False)
                ):
                    # Day began — drop auto NV; leave user-forced NV alone
                    self.set_night_vision(False, announce=False, auto=True)
        except Exception:
            pass
        threading.Timer(45.0, self._night_vision_loop).start()

    def set_night_vision(self, on: bool, announce: bool = False, auto: bool = False) -> str:
        """Toggle NV. announce=True only for autonomous path (speaks itself).
        Voice/button routes leave announce=False — handle_utterance speaks once.
        """
        on = bool(on)
        was = self._night_vision
        self._night_vision = on
        if on:
            self._night_vision_auto_on = bool(auto)
            self._nv_user_off = False
            # Manual on survives day auto-disable; auto on does not set user latch
            if not auto:
                self._nv_user_on = True
            else:
                self._nv_user_on = False
        else:
            self._night_vision_auto_on = False
            self._nv_user_on = False
            # Voice / manual off: don't let the nightly auto loop flip it back on
            if not auto:
                self._nv_user_off = True
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
            self._emit("heard", "[optics] night vision offline")
            if announce:
                self.say(msg)
            return msg
        return "Night vision already on." if on else "Night vision already off."

    def _grab_fresh_enroll_frame(self):
        """Best-effort BGR frames already in memory / on disk (no second camera)."""
        frames: list = []
        try:
            box = getattr(self, "_enroll_grab_box", None)
            if box:
                frames.extend([f for f in box if f is not None])
        except Exception:
            pass
        try:
            if self._last_frame is not None:
                frames.append(self._last_frame.copy())
        except Exception:
            pass
        try:
            import cv2

            snap = DATA_DIR / "last_vision.jpg"
            if snap.exists():
                img = cv2.imread(str(snap))
                if img is not None:
                    frames.append(img)
        except Exception:
            pass
        return frames

    def _enroll_face_now(self) -> str:
        """Always take a fresh theater frame — you're at the camera when you say this."""
        if not getattr(self, "security", None):
            return "Security module offline."
        self._enroll_pending_speak = True
        self._enroll_grab_box = []
        try:
            self._emit("hud_alert", "ENROLLING — hold still")
            self._emit("enroll_grab", True)
        except Exception as e:
            print(f"[enroll] emit: {e}")
        # If UI never delivers a frame (cam race), fall back after a few seconds
        try:
            threading.Timer(3.5, self._enroll_timeout_fallback).start()
        except Exception:
            pass
        return ""  # accept_enroll_frame / fallback speaks the real result once

    def _enroll_timeout_fallback(self) -> None:
        if not getattr(self, "_enroll_pending_speak", False):
            return
        self._enroll_pending_speak = False
        try:
            frames = self._grab_fresh_enroll_frame()
            msg = self.security.enroll_from_candidates(
                frames, [DATA_DIR / "last_vision.jpg"]
            )
            self._emit(
                "hud_alert",
                "FACE ENROLLED" if "enrolled" in msg.lower() else "ENROLL FAILED",
            )
            self._emit("heard", f"[security] {msg}")
            self.say(msg)
        except Exception as e:
            self.say(f"Enroll failed: {e}")

    def accept_enroll_frame(self, frame) -> None:
        """Called from UI with a live BGR frame; completes an in-flight enroll."""
        if not getattr(self, "_enroll_pending_speak", False):
            return
        try:
            if frame is not None:
                self._last_frame = frame
                box = getattr(self, "_enroll_grab_box", None)
                if isinstance(box, list):
                    box.append(frame.copy() if hasattr(frame, "copy") else frame)
        except Exception:
            pass
        if not getattr(self, "security", None):
            self._enroll_pending_speak = False
            self.say("Security module offline.")
            return
        if frame is None:
            # Keep pending — timeout fallback will try disk/last frame
            return
        self._enroll_pending_speak = False
        try:
            msg = self.security.enroll_from_bgr(frame, allow_fallback=False)
            if "no face" in msg.lower():
                # Close-up desk cam: allow center crop once on live frame
                msg = self.security.enroll_from_bgr(frame, allow_fallback=True)
            self._emit(
                "hud_alert",
                "FACE ENROLLED" if "enrolled" in msg.lower() else "ENROLL FAILED",
            )
            self._emit("heard", f"[security] {msg}")
            self.say(msg)
        except Exception as e:
            self.say(f"Enroll failed: {e}")

    def _proactive_loop(self) -> None:
        try:
            if getattr(self, "proactive", None):
                self.proactive.tick()
        except Exception as e:
            print(f"[proactive] {e}")
        try:
            if getattr(self, "self_audit", None):
                msg = self.self_audit.maybe_nightly()
                if msg:
                    self._emit("hud_alert", "Self-audit ready")
                    self._emit("heard", f"[audit] {msg}")
                    self.say(msg)
        except Exception:
            pass
        try:
            threading.Timer(60.0, self._proactive_loop).start()
        except Exception:
            pass

    def _handle_security_event(self, ev) -> None:
        kind = getattr(ev, "kind", "")
        msg = getattr(ev, "message", "")
        snap = getattr(ev, "snapshot", "") or ""
        self._emit("heard", f"[security] {kind}: {msg}")
        if kind == "intruder":
            self._emit("hud_alert", "INTRUDER ALERT")
            self._emit("panic_ui", True)
            try:
                if snap:
                    self._emit("artifact", snap)
            except Exception:
                pass
            try:
                self.phone.ping("Intruder alert at your desk")
            except Exception:
                pass
            self.say(msg)
            return
        if kind == "nudge":
            # Soft biometrics tip — HUD + one speak (say() dedupes repeats)
            self._emit("hud_alert", "BIOMETRICS UNSURE")
            self.say(msg)
            return
        if kind == "greet":
            self._emit("hud_alert", f"Welcome · {self.settings.user_name}")
            self._emit("panic_ui", False)
            # Light workspace unlock — restore listening / cancel lock countdown
            try:
                self.pause_presence_lock(False)
                if self._countdown_active:
                    self._countdown_active = False
                    self._emit("countdown_cancel", True)
            except Exception:
                pass
            self.say(msg)
            return
        if kind == "lock":
            # Step-away: HUD only unless lock_on_absence is on
            self._emit("hud_alert", "AWAY")
            self._emit("heard", "[security] stepped away (auto-lock off)")
            try:
                if self.settings.lock_on_absence and not self._countdown_active:
                    secs = int(getattr(self.settings, "presence_timeout_sec", 35) or 35)
                    self._countdown_active = True
                    self._emit("countdown_start", secs)
                    self._emit("heard", f"[security] stepped away — {secs}s to lock")
            except Exception:
                pass
            return

    def handle_gesture(self, label: str = "", swipe: str = "") -> None:
        """Called from camera theater / news gesture path."""
        try:
            if getattr(self, "gestures", None):
                cmd = self.gestures.on_gesture(label=label or "", swipe=swipe or "")
                if cmd:
                    self._emit("hud_alert", f"Gesture · {cmd}")
                    self._emit("command_ui", {"kind": "route", "text": f"gesture:{cmd}"})
        except Exception as e:
            print(f"[gesture] {e}")

    def _run_gesture_cmd(self, cmd: str) -> None:
        """Execute gesture-mapped utterance without the _handling lock drop."""
        try:
            if getattr(self, "registry", None) and not self.registry.allows(cmd):
                self._emit("hud_alert", "Registry frozen")
                return
            reply = self._route((cmd or "").lower().strip())
            if reply:
                self.say(reply)
        except Exception as e:
            print(f"[gesture] cmd: {e}")

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
        try:
            if not getattr(self.suggestions, "enabled", True):
                return
            if self.suggestions.suppressed() and not force:
                return
        except Exception:
            pass
        tip = self.suggestions.now_suggestion(force=force)
        if not tip:
            return
        self._emit("quick_action", tip["title"])
        self._emit("hud_alert", tip["detail"])
        self._emit("suggestion", tip)
        # Spoken ambient tips only when speak_ok (long gap) — never stack "Suggestion:"
        if speak and self.suggestions.speak_ok():
            self.say(tip["detail"] + " Say yes if you want that.")

    def accept_suggestion(self) -> str:
        """HUD chip accept — one command, then suppress follow-up cascade."""
        try:
            cmd = self.suggestions.accept()
        except Exception:
            cmd = self.suggestions.pending_cmd or ""
            self.suggestions.clear_pending()
        if not cmd:
            return "Nothing pending."
        self._emit("heard", f"[suggestion] {cmd}")
        self._skip_suggestion_followups = True
        try:
            return self._route(cmd.lower())
        finally:
            self._skip_suggestion_followups = False

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

    def _extract_map_zoom_place(self, t: str) -> str | None:
        """Parse 'zoom in to Paris' / 'fly map to Japan' / 'go to Japan' style commands."""
        patterns = (
            r"\bzoom\s+(?:in\s+)?(?:in\s+to|into|to|on)\s+(.+)$",
            r"\bfly\s+(?:the\s+)?(?:map\s+)?(?:to|into)\s+(.+)$",
            r"\bmap\s+(?:zoom\s+(?:in\s+)?(?:to|on)|focus\s+on|to)\s+(.+)$",
            r"\brecenter\s+(?:the\s+)?map\s+(?:on\s+)?(.+)$",
            r"\b(?:go|take\s+me)\s+to\s+(.+?)\s+on\s+(?:the\s+)?map\b",
            r"\b(?:show|focus)\s+(?:me\s+)?(.+?)\s+on\s+(?:the\s+)?map\b",
            r"\bfocus\s+(?:the\s+)?map\s+on\s+(.+)$",
            r"\b(?:show|open)\s+(?:me\s+)?(?:the\s+)?map\s+(?:of|for|to)\s+(.+)$",
            # Bare go-to / take-me (filtered against non-geo phrases below)
            r"\b(?:go|take\s+me)\s+to\s+(.+)$",
            r"\b(?:fly|jump)\s+to\s+(.+)$",
        )
        _non_geo = {
            "map",
            "the map",
            "in",
            "out",
            "closer",
            "there",
            "here",
            "sleep",
            "bed",
            "work",
            "bedtime",
            "settings",
            "the bathroom",
            "the store",
            "the office",
            "school",
            "home",  # ambiguous; use city via open map
            "hell",
            "town",
            "the gym",
            "lunch",
            "dinner",
            "meeting",
            "a meeting",
        }
        for pat in patterns:
            m = re.search(pat, t, flags=re.I)
            if not m:
                continue
            dest = (m.group(1) or "").strip(" .,!?")
            dest = re.sub(
                r"\b(on the map|in the map|please|for me|view|mode|3d|the map)\b",
                "",
                dest,
                flags=re.I,
            ).strip(" .,!?")
            low = dest.lower()
            if not dest or low in _non_geo:
                continue
            # Skip obvious non-places: "go to sleep early", "go to the next track"
            if re.match(
                r"^(the\s+)?(next|previous|last|first|my|your)\b",
                low,
            ):
                continue
            if re.search(
                r"\b(sleep|bed|settings|meeting|playlist|email|camera|news)\b",
                low,
            ):
                continue
            return dest
        return None

    def _map_zoom_to(self, place: str) -> str:
        """Geocode place, fly 3D map, speak a short location brief."""
        from jarvis.ui.widgets.map_view import _brief_for, _geocode_detail

        hit = _geocode_detail(place)
        if not hit:
            return self._flavor(
                "ok",
                f"I couldn't locate {place} on the tactical map.",
            )
        brief = _brief_for(hit)
        label = str(hit.get("name") or place)
        self.habits.log("map_zoom", label[:40])
        self._emit(
            "map_ui",
            {
                "place": label,
                "lat": hit["lat"],
                "lon": hit["lon"],
                "zoom": hit.get("zoom"),
                "label": label,
                "brief": brief,
                "markers": [],
                "scanning": False,
                "animate": True,
            },
        )
        self._emit("hud_alert", f"Map · {label}")
        return self._flavor("ok", f"Zooming to {label}. {brief}")

    def _map_zoom_delta(self, delta: float) -> str:
        """Relative zoom in/out; opens map with intro if closed."""
        try:
            self.habits.log("map_zoom", "in" if delta >= 0 else "out")
        except Exception:
            pass
        self._emit(
            "map_ui",
            {
                "zoom_delta": float(delta),
                "markers": [],
                "scanning": False,
                "animate": True,
            },
        )
        if delta >= 0:
            return self._flavor("ok", "Zooming in on the tactical map.")
        return self._flavor("ok", "Pulling back on the tactical map.")

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
        try:
            if self.macro:
                self.macro.stop()
        except Exception:
            pass
        try:
            if self.watch:
                self.watch.stop()
        except Exception:
            pass

    def handle_macro(self, cmd: str) -> str:
        """Silent Stream Deck / HTTP macros — no TTS required for stop."""
        c = (cmd or "").strip().lower()
        aliases = {
            "stop": "panic off",
            "halt": "panic off",
            "kill": "go offline",
            "offline": "go offline",
            "cam": "open camera",
            "camera": "open camera",
            "mute": "mute",
            "lock": "lock",
            "brief": "good morning",
            "standup": "good morning",
            "lamp": "turn on the lamp",
            "lamp on": "turn on the lamp",
            "lamp off": "turn off the lamp",
            "light on": "turn on the lamp",
            "light off": "turn off the lamp",
        }
        utterance = aliases.get(c, c)
        if c in ("stop", "halt", "barge"):
            try:
                self.voice.barge_in()
                self.voice.set_busy(False)
                self._handling = False
            except Exception:
                pass
            self._emit("hud_alert", "Macro STOP")
            return "Stopped speech / cleared busy."
        # Run through normal router on UI-safe thread
        try:
            self.handle_utterance(utterance)
            return f"Macro ran: {utterance}"
        except Exception as e:
            return f"Macro error: {e}"

    def handle_companion(self, text: str) -> str:
        """iPhone PWA chat — same brain router, return spoken reply for the phone UI."""
        msg = (text or "").strip()
        if not msg:
            return "Send a command when you're ready."
        if self._handling:
            return "I'm mid-command — try again in a moment."
        self._last_spoken_shaped = ""
        try:
            self._emit("heard", f"[iPhone] {msg}")
            self._emit("hud_alert", f"iPhone › {msg[:80]}")
        except Exception:
            pass
        try:
            self.handle_utterance(msg)
        except Exception as e:
            return f"Error: {e}"
        out = (getattr(self, "_last_spoken_shaped", "") or "").strip()
        return out or "Done."

    def _ensure_companion_token(self) -> str:
        tok = (getattr(self.settings, "companion_token", "") or "").strip()
        if tok:
            return tok
        tok = make_token()
        self.settings.companion_token = tok
        self.settings.companion_enabled = True
        try:
            self.settings.save()
        except Exception:
            pass
        return tok

    def _boot_companion(self) -> None:
        token = self._ensure_companion_token()
        host = (getattr(self.settings, "companion_host", "") or "0.0.0.0").strip()
        port = int(getattr(self.settings, "companion_port", 8766) or 8766)

        def _status() -> dict:
            return {
                "user": self.settings.user_name,
                "listening": not bool(getattr(self, "_handling", False)),
                "port": port,
            }

        self.companion = CompanionServer(
            self.handle_companion,
            token=token,
            host=host,
            port=port,
            on_status=_status,
        )
        self.companion.start()

    def companion_status_line(self) -> str:
        if not getattr(self.settings, "companion_enabled", True):
            return "Phone companion is disabled in settings."
        port = int(getattr(self.settings, "companion_port", 8766) or 8766)
        live = getattr(self, "companion", None) is not None
        tok = self._ensure_companion_token()
        short = tok[:6] + "…" if len(tok) > 8 else tok
        state = "online" if live else "configured but not running"
        return (
            f"iPhone companion {state} on port {port}. "
            f"Token starts {short}. Say open phone companion for the Tailscale link."
        )

    def companion_link_message(self) -> str:
        token = self._ensure_companion_token()
        port = int(getattr(self.settings, "companion_port", 8766) or 8766)
        url, host = companion_url(token=token, port=port)
        self._emit(
            "artifact",
            {
                "title": "IPHONE COMPANION · Tailscale + zip",
                "text": (
                    "You already have a travel companion built in.\n\n"
                    "Fast path: say **companion zip** — Jarvis builds a setup zip "
                    "(Desktop + exports). AirDrop it to the iPhone, open "
                    "OPEN_IN_SAFARI.html in Safari.\n\n"
                    "1) Install **Tailscale** on this PC and your iPhone 14 — same account.\n"
                    "2) On iPhone: keep Tailscale Connected.\n"
                    f"3) Safari open:\n   {url}\n"
                    "4) Share → **Add to Home Screen** → Jarvis.\n"
                    f"\nHost: `{host}`  Token: `{token}`\n"
                    "\nDoc: docs/HANDOVER_COMPANION.md"
                ),
            },
        )
        try:
            if getattr(self, "phone", None):
                self.phone.notify(
                    f"Companion ready. Or say companion zip on the desk.",
                    title="JARVIS · phone companion",
                )
        except Exception:
            pass
        if host.startswith("100."):
            return (
                "You already have a travel companion. Open the Tailscale link in Safari on "
                "your iPhone, or say companion zip for a setup pack you can AirDrop."
            )
        return (
            "You already have a travel companion. Say companion zip for a Safari setup pack "
            "on your Desktop — install Tailscale on PC and iPhone first."
        )

    def companion_zip_message(self) -> str:
        """Build the iPhone Safari setup zip and point the user at it."""
        token = self._ensure_companion_token()
        port = int(getattr(self.settings, "companion_port", 8766) or 8766)
        try:
            info = build_companion_setup_zip(
                token=token,
                port=port,
                user_name=self.settings.user_name or "Sir",
            )
        except Exception as e:
            return f"Could not build the companion zip: {e}"

        zip_path = info.get("desktop") or info.get("zip") or ""
        url = info.get("url") or ""
        self._emit(
            "artifact",
            {
                "title": "IPHONE COMPANION · setup zip",
                "text": (
                    f"Zip ready:\n  {zip_path}\n\n"
                    "On iPhone:\n"
                    "1) Tailscale Connected (same account)\n"
                    "2) AirDrop / iCloud the zip → Files → unzip\n"
                    "3) Open OPEN_IN_SAFARI.html → Open Jarvis in Safari\n"
                    "4) Share → Add to Home Screen\n\n"
                    f"URL inside the pack:\n  {url}\n"
                ),
            },
        )
        try:
            import os

            folder = str(Path(zip_path).parent) if zip_path else ""
            if folder:
                os.startfile(folder)  # noqa: S606 — Windows Explorer
        except Exception:
            pass
        try:
            if getattr(self, "phone", None):
                self.phone.notify(
                    "Companion setup zip is on your PC Desktop. AirDrop it, open in Safari.",
                    title="JARVIS · companion zip",
                )
        except Exception:
            pass
        where = "Desktop" if info.get("desktop") else "exports folder"
        return (
            f"Companion setup zip is on your {where}. AirDrop it to the iPhone, "
            "open OPEN_IN_SAFARI.html in Safari, then Add to Home Screen."
        )

    def _maybe_announce_companion(self) -> None:
        """Once a day: surface that the iPhone companion exists (discoverability)."""
        if not getattr(self.settings, "companion_enabled", True):
            return
        if getattr(self, "_companion_announced", False):
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if (getattr(self.settings, "companion_intro_day", "") or "") == today:
            return
        self._companion_announced = True
        self.settings.companion_intro_day = today
        try:
            self.settings.save()
        except Exception:
            pass
        tip = (
            f"By the way, {self.settings.user_name} — you already have a travel companion. "
            "Say companion zip for a Safari setup pack, or open phone companion."
        )
        try:
            self._emit("hud_alert", "iPhone companion ready")
            self._emit("quick_action", "Open phone companion?")
            if getattr(self, "suggestions", None):
                self.suggestions.pending_cmd = "open phone companion"
                self.suggestions._pending_at = time.time()
        except Exception:
            pass
        try:
            self.say(tip)
        except Exception:
            pass

    def _boot_manus_code_watch(self) -> None:
        """Recursive code-folder watch for Manus improve offers (never auto-tasks)."""
        if not bool(getattr(self.settings, "manus_code_assist", True)):
            return
        manus = getattr(self, "manus", None)
        if manus is None or not getattr(manus, "linked", False):
            return
        project = Path(
            getattr(self.settings, "work_project_path", "") or ROOT
        ).expanduser()
        roots: list[str] = []
        try:
            proj_res = project.resolve()
            root_res = ROOT.resolve()
        except Exception:
            proj_res = project
            root_res = ROOT

        # Prefer narrow source trees — never the whole jarvis/ package (data/ TTS spam).
        try:
            if str(proj_res) == str(root_res):
                jarvis_pkg = ROOT / "jarvis"
                for sub in ("core", "ui", "web"):
                    p = jarvis_pkg / sub
                    try:
                        if p.is_dir():
                            roots.append(str(p))
                    except Exception:
                        pass
                hub_src = ROOT / "hub" / "src"
                try:
                    if hub_src.is_dir():
                        roots.append(str(hub_src))
                except Exception:
                    pass
            elif project.is_dir():
                # External work project: watch it, but FolderWatch + is_code_path filter noise
                roots.append(str(project))
        except Exception:
            pass
        if not roots:
            return
        self.code_watch = FolderWatch(
            roots,
            self._on_new_file,
            enabled=True,
            settle_sec=2.0,
            recursive=True,
            also_modified=True,
            allow_suffixes=CODE_EXTS,
        )
        self.code_watch.start()

    def _offer_manus_code_assist(self) -> None:
        """HUD quick_action only — user must say yes / click (no auto Manus task)."""
        try:
            if not bool(getattr(self.settings, "manus_code_assist", True)):
                return
            manus = getattr(self, "manus", None)
            if manus is None or not getattr(manus, "linked", False):
                return
            if getattr(self, "suggestions", None):
                self.suggestions.pending_cmd = "manus review"
                self.suggestions._pending_at = time.time()
            self._emit("quick_action", "Ask Manus to improve recent code?")
            self._emit("hud_alert", "Manus code assist — say yes or manus review")
        except Exception as e:
            print(f"[manus-code] offer: {e}")

    def _run_manus_code_review(self, file_path: str = "") -> str:
        """Collect coding snapshot → Manus create_task → open URL + HUD artifact."""
        manus = getattr(self, "manus", None)
        if manus is None:
            return "Manus bridge unavailable."
        if not getattr(manus, "linked", False):
            return (
                "Manus not linked. Say set manus key to YOUR_KEY "
                "(from manus.im → API Integration)."
            )
        project = getattr(self.settings, "work_project_path", "") or str(ROOT)
        try:
            snap = build_snapshot(project_path=project, file_path=file_path or "")
            prompt = build_review_prompt(snapshot=snap)
        except Exception as e:
            return f"Could not build code snapshot: {e}"
        title = "Jarvis code review"
        if file_path:
            title = f"Review {Path(file_path).name}"
        reply = manus.create_task(prompt, title=title)
        url = getattr(manus, "last_task_url", "") or ""
        if url:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        self._emit(
            "artifact",
            {
                "title": "MANUS CODE REVIEW",
                "text": (
                    f"{getattr(manus, 'last_title', '') or title}\n"
                    f"id: {getattr(manus, 'last_task_id', '') or '—'}\n"
                    f"{url or '—'}\n\n"
                    f"Snapshot ~{len(snap)} chars sent.\n{reply}"
                ),
            },
        )
        try:
            if getattr(self, "_manus_code_offer", None):
                self._manus_code_offer.mark_offered()
        except Exception:
            pass
        return reply

    def _on_new_file(self, path: str) -> None:
        # Drop runtime churn early (data_feed, TTS mp3s, locks, logs, …)
        try:
            if is_watch_noise(path):
                return
        except Exception:
            return

        name = Path(path).name

        def _under_code_watch(p: str) -> bool:
            try:
                cw = getattr(self, "code_watch", None)
                if not cw:
                    return False
                roots = [str(r.resolve()) for r in (cw.paths or [])]
                try:
                    resolved = str(Path(p).resolve())
                except Exception:
                    resolved = p
                return any(
                    resolved == r
                    or resolved.startswith(r.rstrip("\\/") + "\\")
                    or resolved.startswith(r.rstrip("\\/") + "/")
                    for r in roots
                )
            except Exception:
                return False

        under_code = _under_code_watch(path)

        # Manus code-assist hook (additive; never auto-create tasks)
        try:
            if (
                bool(getattr(self.settings, "manus_code_assist", True))
                and getattr(self, "manus", None) is not None
                and getattr(self.manus, "linked", False)
                and is_code_path(path)
                and getattr(self, "_manus_code_offer", None) is not None
            ):
                self._manus_code_offer.note_change(path)
        except Exception as e:
            print(f"[manus-code] note: {e}")

        # Quiet path for recursive code_watch (avoid Downloads-style spam)
        if under_code:
            try:
                if is_code_path(path):
                    self._emit("heard", f"[code-watch] {name}")
                # Non-code under code roots: silent drop (no HUD / no task queue)
            except Exception:
                pass
            return

        msg = f"New file in watch folder: {name}"
        self._emit("hud_alert", msg)
        self.feed.push("watch", msg)
        self._emit("heard", f"[watch] {path}")
        # Light-weight analyze for media/csv — queued so voice stays free
        low = path.lower()

        def _job() -> str:
            if low.endswith((".csv", ".json", ".xlsx", ".parquet")):
                return f"Dataset detected ({name}). Say 'analyze downloads' when ready."
            if low.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                return f"Image landed ({name}). Say 'scan this' to identify."
            return f"Noted {name}."

        tid = self.tasks.submit(f"watch:{name[:24]}", _job)
        print(f"[watch] queued {tid} for {name}")

    def _reactor_ha(self, mode: str) -> None:
        try:
            self.ha.on_jarvis_state(mode)
        except Exception:
            pass

    def _on_game_focus(self, name: str) -> None:
        """Mute listen path while a real game is up — never open Windows settings."""
        try:
            self.voice.mute_mic(True)
        except Exception:
            pass
        self._emit("hud_alert", f"Game focus — {name} (mic paused).")

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
        # HUD gets full text; voice speaks complete sentences (not a 20-word chop)
        shaped = text
        try:
            shaped = self.travis.shape_reply(text)
        except Exception:
            shaped = text
        budget = 60
        try:
            budget = self.travis.speakable_budget(60)
        except Exception:
            pass
        spoken = self.persona.speakable(shaped, max_words=budget)
        if not spoken:
            return
        # Brain-level dedupe — stops NV/route double-speak and stacked acks
        import time as _t
        import difflib

        now = _t.time()
        norm = " ".join(spoken.lower().split())
        last = getattr(self, "_last_brain_say", "") or ""
        last_at = float(getattr(self, "_last_brain_say_at", 0) or 0)
        if last and now - last_at < 12.0:
            if norm == last:
                self._emit("speak_ui", shaped)  # log only
                return
            if difflib.SequenceMatcher(None, norm, last).ratio() >= 0.82:
                self._emit("speak_ui", shaped)
                return
            # Same leading phrase ("Turning on night vision…")
            if len(norm) > 18 and len(last) > 18 and (
                norm[:24] == last[:24] or last.startswith(norm[:20]) or norm.startswith(last[:20])
            ):
                self._emit("speak_ui", shaped)
                return
        self._last_brain_say = norm
        self._last_brain_say_at = now
        self._last_spoken_shaped = shaped
        self._emit("speak", shaped)
        self.voice.say(spoken)

    def _apply_travis_mode(self, mode: str) -> str:
        """Enter / exit Travis mode and sync HUD + settings."""
        if mode == "status":
            return self._flavor("ok", self.travis.status())
        prev = self.travis.mode.value
        profile = self.travis.set_mode(mode)
        # Persist
        try:
            self.settings.travis_mode = self.travis.mode.value
            self.settings.save()
        except Exception:
            pass
        # Visual sync
        mid = self.travis.mode.value if self.travis.active else "off"
        self._emit("travis_ui", mid)
        if profile:
            self._reactor_safe(profile.activity)
            self._emit("hud_alert", f"Travis · {profile.label}")
            return self._flavor("ok", profile.enter_line)
        self._reactor_safe("idle")
        self._emit("hud_alert", "Travis · off")
        line = "Travis modes cleared. Standard Jarvis protocol."
        if prev != "off":
            return self._flavor("ok", line)
        return self._flavor("ok", line)

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
        # Only push FPS when it actually changes (avoids queue spam every 2s)
        if snap.vision_fps != getattr(self, "_gov_vision_fps", -1):
            self._gov_vision_fps = snap.vision_fps
            self.vision.set_fps(snap.vision_fps)
        self._emit("telemetry", snap)
        if snap.eco:
            self._emit("bond", {"dim": True, "ambient": "conserve", "fps": snap.ui_fps})

    def tick_governor(self):
        return self.governor.tick()

    def _set_performance_mode(self, on: bool) -> str:
        """Throttle HUD paint / vision for snappier voice (persisted)."""
        on = bool(on)
        try:
            self.settings.performance_mode = on
            self.settings.save()
        except Exception:
            pass
        try:
            self.governor.set_performance_mode(on)
            self.governor.tick()
        except Exception:
            pass
        try:
            self._emit("performance_ui", on)
            if on:
                self._emit(
                    "bond",
                    {"dim": True, "ambient": "conserve", "fps": 10},
                )
            else:
                self._emit("bond", {"fps": 15, "ambient": "normal"})
        except Exception:
            pass
        if on:
            return self._flavor(
                "ok",
                "Smooth mode on — HUD throttled so voice stays snappy.",
            )
        return self._flavor("ok", "Full fidelity HUD restored.")

    def _on_vision(self, ev: VisionEvent) -> None:
        import time

        self._emit("presence", ev.present)
        self._emit("parallax", {"x": ev.face_x, "y": ev.face_y})
        # Smart media: pause Netflix/YouTube when you stand up
        try:
            if getattr(self, "media_presence", None) and not self._presence_paused:
                note = self.media_presence.on_presence(bool(ev.present))
                if note:
                    self._emit("hud_alert", note)
                    self._emit("heard", f"[media] {note}")
        except Exception:
            pass
        # Biometric greet / intruder / step-away secure
        try:
            if getattr(self, "security", None) and not self._presence_paused:
                ev_sec = self.security.on_presence(
                    bool(ev.present),
                    snapshot_path=str(getattr(ev, "snapshot_path", "") or ""),
                    motion=float(getattr(ev, "motion", 0) or 0),
                )
                if ev_sec:
                    self._handle_security_event(ev_sec)
        except Exception as e:
            print(f"[security] {e}")
        if self.settings.camera_index != ev.camera_index and ev.camera_index >= 0:
            self.settings.camera_index = ev.camera_index

        # Contextual biometrics + activity from latest snapshot (throttled)
        if (
            ev.snapshot_path
            and not self._presence_paused
            and not self._scanning
            and (
                getattr(self.settings, "posture_nudge", False)
                or getattr(self.settings, "auto_soundscape", False)
            )
        ):
            try:
                import cv2

                img = cv2.imread(ev.snapshot_path)
                if img is not None:
                    self.activity.note_frame(img)
                    self._last_frame = img
                    self.context.tick_frame(img)
            except Exception:
                pass
        elif ev.snapshot_path and not self._presence_paused:
            # Keep last frame lightly for scan/opinion without full Haar bio path
            try:
                now = time.time()
                if now - getattr(self, "_last_frame_load", 0) > 4.0:
                    import cv2

                    img = cv2.imread(ev.snapshot_path)
                    if img is not None:
                        self._last_frame = img
                        self._last_frame_load = now
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
            # Prefer short countdown
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
    def handle_utterance(self, text: str, *, from_voice: bool = False) -> None:
        text = normalize_command((text or "").strip())
        # Ollama rewrite only when explicitly enabled (adds multi-second latency)
        if getattr(self.settings, "ollama_router", False):
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

        # Wake gate early (voice only) — before HUD "heard" flash
        if from_voice and bool(getattr(self.settings, "wake_required", True)):
            low0, woke0 = self._strip_wake(text.lower())
            armed0 = time.time() < float(getattr(self, "_armed_until", 0) or 0)
            note_or_code0 = bool(getattr(self, "_note_mode", False)) or bool(
                getattr(getattr(self, "voice_code", None), "active", False)
            )
            if not woke0 and not armed0 and not note_or_code0:
                print(f"[brain] ignore (no wake): {text[:60]}")
                return

        # One command at a time — stops stacked repeats
        if self._handling:
            print(f"[brain] busy — queued drop: {text[:60]}")
            return
        self._handling = True
        self.voice.set_busy(True)
        reply = ""
        try:
            try:
                self._emit("heard", text)
                self._emit("listening", True)
                self._emit("command_ui", {"kind": "hear", "text": text})
            except Exception:
                pass

            # HITL voice resolve takes priority while a gate is open
            hitl_msg = self.hitl.resolve_voice(text)
            if hitl_msg:
                self._emit("speak_ui", hitl_msg)
                self._emit("hud_alert", hitl_msg)
                self.say(hitl_msg)
                return

            # Feature freeze during upgrade — additive gate (allowlist only)
            try:
                low_probe = (text or "").lower().strip()
                probe, woke_probe = self._strip_wake(low_probe)
                check = probe if woke_probe else low_probe
                if getattr(self, "registry", None) and not self.registry.allows(
                    check or low_probe
                ):
                    msg = self.registry.block_message()
                    self._emit(
                        "command_ui", {"kind": "block", "text": check or text}
                    )
                    self._emit("hud_alert", "Registry frozen")
                    self.say(msg)
                    return
            except Exception as e:
                print(f"[registry] gate: {e}")

            # Voice-to-code dictation mode (before normal routing)
            try:
                if getattr(self, "voice_code", None) and self.voice_code.active:
                    low_vc, _ = self._strip_wake((text or "").lower())
                    ack = self.voice_code.ingest(low_vc or text)
                    if ack is not None:
                        self.say(ack)
                        return
            except Exception as e:
                print(f"[voice_code] {e}")

            # Expire stuck note/dictation mode after 90s
            if self._note_mode:
                import time as _t

                started = float(getattr(self, "_note_mode_at", 0) or 0)
                if started and _t.time() - started > 90:
                    self._note_mode = False
                    self._note_buffer = []
                    print("[brain] note mode auto-expired")

            low, woke = self._strip_wake(text.lower())
            # Preserve original casing for vaulted secrets (Anthropic/OpenAI keys are case-sensitive).
            # Routing still uses `low`; set-key handlers read `self._cased_cmd`.
            try:
                self._cased_cmd, _ = self._strip_wake_preserve(text)
            except Exception:
                self._cased_cmd = text

            # Bare wake word → short ack, stay ready (don't dump help menu)
            if woke and not low:
                # Cooldown — stop repeated "Yes?" from TV/false STT
                now = time.time()
                last_wake = float(getattr(self, "_last_bare_wake_at", 0) or 0)
                if now - last_wake < 6.0:
                    print("[brain] bare wake cooldown")
                    self._armed_until = now + float(
                        getattr(self.settings, "wake_arm_sec", 8.0) or 8.0
                    )
                    self._emit("listening", False)
                    return
                self._last_bare_wake_at = now
                arm = float(getattr(self.settings, "wake_arm_sec", 8.0) or 8.0)
                reply = f"Yes, {self.settings.user_name}?"
                self._armed_until = now + arm
                self._emit("hud_alert", "Listening…")
                self.say(reply)
                return

            # Command with wake word — refresh arm for a quick follow-up
            if woke and low:
                self._armed_until = time.time() + float(
                    getattr(self.settings, "wake_arm_sec", 8.0) or 8.0
                )

            # Dictation mode — capture everything until "done" / "save note"
            if self._note_mode:
                reply = self._note_dictation(low)
            else:
                # Fast local strip cmds: skip memory/emotion/Hub lag; one spoken reply
                fast = False
                try:
                    fast = is_fast_local_command(low)
                except Exception:
                    fast = False

                support = ""
                if not fast:
                    # Emotional mirroring — prepend once, never speak separately
                    mood = self.emotion.analyze(low)
                    if mood == "stressed" and not self._persona_support:
                        self._persona_support = True
                        support = self.emotion.support_line(self.settings.user_name) + " "
                    elif mood == "positive":
                        self._persona_support = False

                    try:
                        if getattr(self, "mood", None):
                            self.mood.observe_user(low)
                        if getattr(self, "proactive", None):
                            self.proactive.note_activity()
                    except Exception:
                        pass

                    try:
                        self._memory_hint = ""
                        if self._should_query_memory(low):
                            mem_block = self.vstore.context_block(low, n=3)
                            if mem_block:
                                self._emit(
                                    "heard",
                                    f"[memory] {mem_block.splitlines()[1][:100]}",
                                )
                                self._memory_hint = mem_block
                    except Exception:
                        self._memory_hint = ""
                    try:
                        if getattr(self, "live", None):
                            self.live.snapshot(force_weather=False)
                    except Exception:
                        pass
                else:
                    self._memory_hint = ""

                reply = self._route(low)
                if support and reply:
                    reply = (support + reply).strip()
                elif support and not reply:
                    reply = support.strip()
                try:
                    if reply and getattr(self, "mood", None) and not fast:
                        self.mood.remember(low, reply)
                except Exception:
                    pass
                try:
                    if reply:
                        self._emit(
                            "command_ui",
                            {
                                "kind": "route",
                                "text": low,
                                "detail": ("local" if fast else (reply or "")[:80]),
                            },
                        )
                except Exception:
                    pass
                # Learn / follow-ups — never chain after yes/accept
                skip_follow = bool(
                    getattr(self, "_skip_suggestion_followups", False)
                )
                try:
                    if skip_follow or (
                        getattr(self, "suggestions", None)
                        and self.suggestions.suppressed()
                    ):
                        skip_follow = True
                except Exception:
                    pass
                if reply and not self._note_mode and not fast and not skip_follow:
                    hint = self.sequences.observe(low)
                    if hint and self.sequences._counts.get(hint, 0) >= 3:
                        last = hint.split("→")[-1].strip() or "set up my morning workspace"
                        self.suggestions.pending_cmd = last
                        self.suggestions._pending_at = time.time()
                        self._emit(
                            "quick_action",
                            f"Shall I run “{last}” again?",
                        )
                    follow = self.suggestions.after_command(low, reply or "")
                    if follow:
                        self._emit("quick_action", follow["title"])
                        self._emit("hud_alert", follow["detail"])
                self._skip_suggestion_followups = False
                if reply and any(
                    k in low
                    for k in ("done", "finished", "shipped", "deployed", "complete")
                ):
                    self.diary.log_win(low[:120])
            self._emit("listening", False)
            if reply:
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
                    try:
                        if not is_fast_local_command(low or text):
                            self.rlhf.observe(low or text, action=low or text, reply=reply)
                    except Exception:
                        pass
                    self.say(reply)
        finally:
            self._handling = False
            # Free the mic quickly so the next command isn't dropped
            delay = 0.05 if self._note_mode else 0.06
            threading.Timer(delay, lambda: self.voice.set_busy(False)).start()

    def _strip_wake(self, text: str) -> tuple[str, bool]:
        """Remove hey/ok/hi + wake word. Returns (remainder lowercased, woke)."""
        rest, woke = self._strip_wake_preserve(text)
        return rest.lower(), woke

    def _strip_wake_preserve(self, text: str) -> tuple[str, bool]:
        """Like _strip_wake but keeps original casing (API keys are case-sensitive)."""
        raw = (text or "").strip(" .,!?")
        low = raw.lower()
        ww = re.escape((self.settings.wake_word or "jarvis").lower())
        m = re.match(rf"^(?:hey |ok |okay |hi |yo )?{ww}(?:\s*[,:\-]+|\s+|$)", low)
        if m:
            return raw[m.end() :].strip(" .,!?"), True
        return raw, False

    def _capture_secret(self, pattern: str, fallback: str = "") -> str:
        """Extract a secret from case-preserved utterance text when available."""
        from jarvis.core.secrets_vault import sanitize_secret

        src = (getattr(self, "_cased_cmd", None) or "").strip()
        if src:
            m = re.search(pattern, src, re.I)
            if m:
                return sanitize_secret(m.group(1))
        fb = (fallback or "").strip()
        if not fb:
            return ""
        m = re.search(pattern, fb, re.I)
        if m:
            return sanitize_secret(m.group(1))
        # fallback may already be the captured key group (lowercased route path)
        return sanitize_secret(fb)

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

    def _should_query_memory(self, t: str) -> bool:
        """Skip vector search for short / obvious commands."""
        if not t or len(t) < 12:
            return False
        if re.match(
            r"^(open |lock|sleep|play |pause|volume |click |type |press |"
            r"scroll |mute|unmute|weather|time|help|scan|build |away|"
            r"go offline|reload |reboot |update software|hub |"
            r"enroll|night vision|security|show stats|router |secure |"
            r"auto lock|self audit|fix this|status$)",
            t,
        ):
            return False
        return bool(
            re.search(
                r"\b(where|what|remember|recall|about|my |the |mounted|"
                r"camera|monitor|setup|config|prefer)\b",
                t,
            )
        )

    def _with_memory(self, core: str) -> str:
        """Spoken replies stay clean — memory stays in the HUD log only."""
        return core

    def _try_phone_cmd(self, t: str) -> str | None:
        """Return a reply string if this is a phone intent, else None."""
        if not t:
            return None
        # iPhone companion PWA (Tailscale)
        if re.search(
            r"\b((open|show|launch|start)\s+(my\s+)?(phone\s+)?companion|"
            r"phone\s+companion|"
            r"companion\s+(link|url|setup)|"
            r"jarvis\s+on\s+(my\s+)?(phone|iphone)|"
            r"connect\s+jarvis\s+to\s+(my\s+)?(phone|iphone))\b",
            t,
        ):
            return self._flavor("ok", self.companion_link_message())
        if re.search(
            r"\b(companion\s+zip|zip\s+(the\s+)?companion|"
            r"(phone|iphone)\s+companion\s+zip|"
            r"setup\s+zip|"
            r"make\s+(a\s+)?companion\s+zip)\b",
            t,
        ):
            return self._flavor("ok", self.companion_zip_message())
        if re.search(r"\bcompanion\s+status\b", t):
            return self._flavor("ok", self.companion_status_line())
        # Status
        if re.search(r"\b(phone status|iphone status|is my phone linked)\b", t):
            push = self.phone.status()
            comp = self.companion_status_line()
            return self._flavor("ok", f"{push} {comp}")
        # Pair / link
        if re.search(
            r"\b(link|pair|setup|connect)\s+(my\s+)?(phone|iphone)\b|"
            r"\b(link my (phone|iphone)|setup (my )?phone|pair my (phone|iphone))\b",
            t,
        ):
            return self._link_phone()
        # Text / notify with body: "text my phone hello there"
        m = re.search(
            r"\b(?:text|notify|ping|message|alert|sms|send)\s+"
            r"(?:to\s+)?(?:my\s+)?(?:phone|iphone|iphne|fone)\s+(.+)$",
            t,
        )
        if m:
            body = m.group(1).strip(" .,!?")
            if body and body not in ("please", "now", "sir"):
                self._ensure_phone_topic()
                return self._flavor("ok", self.phone.notify(body))
        # Bare ping / text phone
        if re.search(
            r"\b(?:text|notify|ping|message|alert|sms)\s+"
            r"(?:to\s+)?(?:my\s+)?(?:phone|iphone|iphne|fone)\b|"
            r"\b(?:phone|iphone)\s+ping\b|"
            r"\bping(?:\s+my)?\s+(?:phone|iphone)\b|"
            r"\bpink(?:\s+my)?\s+(?:phone|iphone)\b",
            t,
        ):
            self._ensure_phone_topic()
            return self._flavor(
                "ok",
                self.phone.notify("Jarvis ping — systems nominal."),
            )
        return None

    def _try_cloud_cmd(self, t: str) -> str | None:
        """Stripe / Notion / Buffer / Gmail voice intents."""
        if not t:
            return None
        cloud = getattr(self, "cloud", None)
        if cloud is None:
            return None

        if re.search(
            r"\b(integrations?\s+status|cloud\s+status|cloud\s+integrations?)\b",
            t,
        ):
            return self._flavor("ok", cloud.status())

        # --- set tokens (vaulted via settings.save) ---
        m = re.search(r"\bset\s+stripe\s+(?:secret\s+)?key\s+to\s+(\S.+)$", t, re.I)
        if m:
            key = self._capture_secret(
                r"\bset\s+stripe\s+(?:secret\s+)?key\s+to\s+(\S.+)$",
                m.group(1),
            )
            self.settings.stripe_secret_key = key
            cloud.stripe_secret_key = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Stripe key saved to the vault.")

        m = re.search(r"\bset\s+notion\s+token\s+to\s+(\S.+)$", t, re.I)
        if m:
            key = self._capture_secret(
                r"\bset\s+notion\s+token\s+to\s+(\S.+)$",
                m.group(1),
            )
            self.settings.notion_token = key
            cloud.notion_token = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Notion token saved to the vault.")

        m = re.search(r"\bset\s+buffer\s+token\s+to\s+(\S.+)$", t, re.I)
        if m:
            key = self._capture_secret(
                r"\bset\s+buffer\s+token\s+to\s+(\S.+)$",
                m.group(1),
            )
            self.settings.buffer_access_token = key
            cloud.buffer_access_token = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Buffer token saved to the vault.")

        m = re.search(r"\bset\s+gmail\s+token\s+to\s+(\S.+)$", t, re.I)
        if m:
            key = self._capture_secret(
                r"\bset\s+gmail\s+token\s+to\s+(\S.+)$",
                m.group(1),
            )
            self.settings.gmail_access_token = key
            cloud.gmail_access_token = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Gmail token saved to the vault.")

        # --- link / setup guides ---
        if re.search(r"\b(link|connect|setup)\s+stripe\b|\bstripe\s+setup\b", t):
            self._emit(
                "artifact",
                {
                    "title": "STRIPE · LINK",
                    "text": (
                        "1) Open https://dashboard.stripe.com/apikeys\n"
                        "2) Create a **secret** key (sk_…)\n"
                        "3) Say: set stripe key to sk_…\n"
                        "4) Say: stripe status · stripe payments\n"
                    ),
                },
            )
            try:
                webbrowser.open("https://dashboard.stripe.com/apikeys")
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Stripe setup is on screen. Create a secret key, then say set stripe key to …",
            )

        if re.search(r"\b(link|connect|setup)\s+notion\b|\bnotion\s+setup\b", t):
            self._emit(
                "artifact",
                {
                    "title": "NOTION · LINK",
                    "text": (
                        "1) Open https://www.notion.so/my-integrations\n"
                        "2) New integration → copy Internal Integration Secret\n"
                        "3) Share target pages/databases with the integration\n"
                        "4) Say: set notion token to secret_…\n"
                        "5) Say: notion search …\n"
                    ),
                },
            )
            try:
                webbrowser.open("https://www.notion.so/my-integrations")
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Notion setup is on screen. Create an integration secret, then say set notion token to …",
            )

        if re.search(r"\b(link|connect|setup)\s+buffer\b|\bbuffer\s+setup\b", t):
            self._emit(
                "artifact",
                {
                    "title": "BUFFER · LINK",
                    "text": (
                        "1) Buffer developer / account access token\n"
                        "2) Say: set buffer token to YOUR_TOKEN\n"
                        "3) Say: buffer status · buffer channels\n"
                        "Cursor MCP Buffer OAuth is separate — this is for Jarvis voice.\n"
                    ),
                },
            )
            return self._flavor(
                "ok",
                "Buffer setup is on screen. Set an access token, then say buffer status.",
            )

        if re.search(r"\b(link|connect|setup)\s+gmail\b|\bgmail\s+setup\b", t):
            self._emit(
                "artifact",
                {
                    "title": "GMAIL · LINK",
                    "text": (
                        "Preferred: Connect Gmail MCP in Cursor (OAuth).\n"
                        "For Jarvis voice, paste a short-lived OAuth access token:\n"
                        "  set gmail token to ya29.…\n"
                        "Then: gmail inbox · gmail status\n"
                    ),
                },
            )
            try:
                webbrowser.open("https://mail.google.com")
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Gmail setup is on screen. Prefer Cursor OAuth; or set gmail token for Jarvis voice.",
            )

        # --- actions ---
        if re.search(r"\bstripe\s+(status|balance)\b", t):
            return self._flavor("ok", cloud.stripe_status())
        if re.search(r"\b(stripe\s+payments|recent\s+stripe|list\s+stripe)\b", t):
            return self._flavor("ok", cloud.stripe_recent_payments())

        if re.search(r"\bnotion\s+status\b", t):
            return self._flavor("ok", cloud.notion_status())
        m = re.search(r"\bnotion\s+search\s+(.+)$", t, re.I)
        if m:
            return self._flavor("ok", cloud.notion_search(m.group(1).strip(" .,!?")))

        if re.search(r"\bbuffer\s+status\b", t):
            return self._flavor("ok", cloud.buffer_status())
        if re.search(r"\bbuffer\s+(channels|profiles)\b", t):
            return self._flavor("ok", cloud.buffer_channels())

        if re.search(r"\bgmail\s+status\b", t):
            return self._flavor("ok", cloud.gmail_status())
        if re.search(r"\b(gmail\s+inbox|check\s+(my\s+)?(email|inbox|gmail))\b", t):
            return self._flavor("ok", cloud.gmail_inbox())

        return None

    def _try_crew_cmd(self, t: str) -> str | None:
        """Return a reply if this is an agent-crew intent, else None."""
        if not t:
            return None
        crew = getattr(self, "crew", None)
        if crew is None:
            return None

        if re.search(r"\b(crew|agent\s*crew)\s+status\b", t):
            return self._flavor("ok", crew.status())

        if re.search(r"\b(crew|agent\s*crew)\s+(health|diagnostics)\b", t):
            return self._flavor("ok", crew.guardian.report())

        # Soft STT variants: "crude debate", "crew debates", "ask crew to debate"
        m = re.search(
            r"(?:^|\b)(?:ask\s+(?:the\s+)?crew\s+to\s+)?(?:crew|crude)\s+debates?\s+(.+)$",
            t.strip(),
            re.I,
        )
        if not m:
            m = re.search(r"^crew\s+debate\s+(.+)$", t.strip(), re.I)
        if m:
            question = m.group(1).strip(" .,!?")
            if not question:
                return self._flavor("clarify", "What shall the crew debate, sir?")
            # Keep mic armed while the debate runs (can take 30–60s)
            try:
                arm = float(getattr(self.settings, "wake_arm_sec", 8.0) or 8.0)
                self._armed_until = time.time() + max(arm, 90.0)
            except Exception:
                pass

            def _debate_job(q: str = question) -> str:
                try:
                    result = crew.debate(q)
                except Exception as e:
                    result = f"Debate failed: {e}"
                self._emit(
                    "artifact",
                    {"title": "AGENT CREW · DEBATE", "text": result},
                )
                try:
                    verdict = result.rsplit("VERDICT:", 1)[-1].strip()
                    if not verdict or "LLM backend" in result:
                        spoken = "The debate chamber could not reach a verdict, sir."
                    else:
                        # Speak a clear answer, not a truncated fragment
                        if len(verdict) > 480:
                            cut = verdict[:480]
                            spoken = (
                                cut.rsplit(".", 1)[0] + "."
                                if "." in cut
                                else cut
                            )
                            spoken += " The full debate is on screen."
                        else:
                            spoken = f"My verdict: {verdict}"
                    # Protected — do not let speaker bleed cut off the answer
                    self.voice.say_protected(spoken)
                except Exception as e:
                    print(f"[crew] debate speak: {e}")
                return result[:200]

            self.tasks.submit(f"crew-debate:{question[:20]}", _debate_job)
            return self._flavor(
                "ok", "The debate chamber is in session — verdict shortly, sir."
            )

        m = re.search(
            r"^(?:ask\s+the\s+crew|ask\s+crew|crew)\s+(.+)$", t.strip(), re.I
        )
        if not m:
            return None
        request = m.group(1).strip(" .,!?")
        if not request:
            return self._flavor("clarify", "What shall the crew work on, sir?")

        def _job(req: str = request) -> str:
            try:
                result = crew.dispatch(req)
            except Exception as e:
                result = f"Crew run failed: {e}"
            routes = ", ".join((crew.last_run or {}).get("routes", []) or [])
            self._emit(
                "artifact",
                {
                    "title": f"AGENT CREW · {routes.upper() or 'RESULT'}",
                    "text": result,
                },
            )
            try:
                if len(result) <= 420:
                    spoken = result
                else:
                    head = result[:400]
                    spoken = (
                        head.rsplit(".", 1)[0] + ". The full report is on screen."
                        if "." in head
                        else head + "… full report on screen."
                    )
                self.voice.say_protected(spoken)
            except Exception as e:
                print(f"[crew] speak: {e}")
            return result[:200]

        self.tasks.submit(f"crew:{request[:24]}", _job)
        return self._flavor(
            "ok", "The crew is on it — VECTOR is routing your request now."
        )

    def _try_manus_cmd(self, t: str) -> str | None:
        """Return a reply if this is a Manus AI intent, else None."""
        if not t:
            return None
        try:
            manus = getattr(self, "manus", None)
            if manus is None:
                return None

            # Status / linked?
            if re.search(
                r"\b(manus\s+status|is\s+manus\s+linked|manus\s+linked)\b",
                t,
            ):
                return self._flavor("ok", manus.status())

            # Setup / link guide
            if re.search(
                r"\b((link|connect|setup|set\s+up)\s+manus|"
                r"manus\s+(link|setup|connect))\b",
                t,
            ):
                self._emit(
                    "artifact",
                    {
                        "title": "MANUS AI · LINK",
                        "text": (
                            "1) Open https://manus.im and sign in\n"
                            "2) Go to **API Integration** → Create API key\n"
                            "3) Say: set manus key to YOUR_KEY\n"
                            "4) Say: ask manus research the latest AI news\n"
                            "\n"
                            "API: https://api.manus.ai (header x-manus-api-key)\n"
                            "Profile: manus-1.6 (settings.manus_agent_profile)"
                        ),
                    },
                )
                try:
                    webbrowser.open("https://manus.im")
                except Exception:
                    pass
                return self._flavor(
                    "ok",
                    "Manus setup is on screen. Create an API key at manus.im "
                    "under API Integration, then say set manus key to YOUR_KEY.",
                )

            # Set API key
            m = re.search(
                r"\bset\s+manus\s+(?:api\s+)?key\s+to\s+(\S.+)$",
                t,
                re.I,
            )
            if m:
                key = self._capture_secret(
                    r"\bset\s+manus\s+(?:api\s+)?key\s+to\s+(\S.+)$",
                    m.group(1),
                )
                if not key or key.lower() in ("please", "now", "sir"):
                    return self._flavor(
                        "clarify",
                        "Paste in the command bar: set manus key to YOUR_KEY — from manus.im.",
                    )
                self.settings.manus_api_key = key
                self.settings.manus_enabled = True
                try:
                    self.settings.save()
                except Exception:
                    pass
                manus.api_key = key
                manus.enabled = True
                return self._flavor(
                    "ok",
                    "Manus API key saved to the vault. Say ask manus … to start a task.",
                )

            # Follow-up / continue
            m = re.search(
                r"\bmanus\s+(?:follow\s*up|continue|reply)\s+(.+)$",
                t,
                re.I,
            )
            if m:
                body = m.group(1).strip(" .,!?")
                if body:
                    return self._flavor("ok", manus.send_followup(body))

            # Result / progress / check
            if re.search(
                r"\b(manus\s+(result|progress|check)|check\s+manus|"
                r"manus\s+task\s+status)\b",
                t,
            ):
                return self._flavor("ok", manus.task_status())

            # Code review / improve — before generic ask manus
            m = re.search(
                r"\bmanus\s+review\s+file\s+(\S.+)$",
                t,
                re.I,
            )
            if m:
                fpath = m.group(1).strip(" .,!\"'")
                return self._flavor("ok", self._run_manus_code_review(file_path=fpath))

            if re.search(
                r"\b("
                r"manus\s+review|"
                r"review\s+(this\s+)?with\s+manus|"
                r"manus\s+improve(\s+this)?|"
                r"ask\s+manus\s+to\s+improve(\s+this)?|"
                r"improve\s+(this\s+)?with\s+manus"
                r")\b",
                t,
                re.I,
            ):
                return self._flavor("ok", self._run_manus_code_review())

            # Create task: ask manus … / send to manus … / tell manus … / manus …
            m = re.search(
                r"\b(?:ask\s+manus|send\s+to\s+manus|tell\s+manus|"
                r"manus(?:\s+please)?)\s+(.+)$",
                t,
                re.I,
            )
            if m:
                prompt = m.group(1).strip(" .,!?")
                # Avoid colliding with status/setup/review phrases already handled
                if not prompt or re.match(
                    r"^(status|linked|link|setup|connect|result|progress|check|"
                    r"follow\s*up|continue|key|review|improve)\b",
                    prompt,
                    re.I,
                ):
                    return None
                # "ask manus to improve this" already handled; belt-and-suspenders
                if re.match(r"^to\s+improve\b", prompt, re.I):
                    return self._flavor("ok", self._run_manus_code_review())
                reply = manus.create_task(prompt)
                url = getattr(manus, "last_task_url", "") or ""
                if url:
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass
                self._emit(
                    "artifact",
                    {
                        "title": "MANUS TASK",
                        "text": (
                            f"{getattr(manus, 'last_title', '') or prompt[:80]}\n"
                            f"id: {getattr(manus, 'last_task_id', '') or '—'}\n"
                            f"{url or '—'}\n\n{reply}"
                        ),
                    },
                )
                return self._flavor("ok", reply)

            return None
        except Exception as e:
            return self._flavor("error", f"Manus command failed: {e}")

    def _on_computer_use_status(self, status) -> None:
        """HUD/feed updates from the agent thread (cross-thread via _emit)."""
        try:
            step = getattr(status, "step", 0)
            mx = getattr(status, "max_steps", 0)
            action = getattr(status, "last_action", "") or ""
            running = bool(getattr(status, "running", False))
            finished = bool(getattr(status, "finished", False))
            result = getattr(status, "result", "") or ""
            prov = getattr(status, "provider", "") or ""
            if running:
                msg = f"CU {prov} {step}/{mx}: {action}"[:140]
                self._emit("hud_alert", msg)
                self._emit(
                    "command_ui",
                    {"kind": "computer_use", "text": msg, "detail": action[:80]},
                )
                try:
                    self.feed.push(
                        "computer_use",
                        msg,
                        meta={"status": "running", "step": step, "provider": prov},
                    )
                except Exception:
                    pass
            elif finished:
                done = (result or action or "session ended")[:160]
                self._emit("hud_alert", f"Computer use: {done}")
                self._emit("fetching", False)
                try:
                    self.feed.push(
                        "computer_use",
                        done,
                        meta={"status": "done", "provider": prov},
                    )
                except Exception:
                    pass
                # Speak completion once from worker thread via say
                try:
                    self.say(self._flavor("ok", done))
                except Exception:
                    pass
        except Exception as e:
            print(f"[computer-use] status ui: {e}")

    def _start_computer_use_session(
        self,
        goal: str,
        *,
        provider: str = "",
        max_steps: int | None = None,
    ) -> str:
        agent = getattr(self, "cu_agent", None)
        if agent is None:
            return "Computer-use agent failed to initialise."
        try:
            agent.configure_from_settings(self.settings)
        except Exception:
            pass

        steps = int(max_steps if max_steps is not None else agent.max_steps)

        def _run() -> None:
            try:
                # HITL gate for long autonomous runs (never silent spend of API + desktop control)
                if agent.needs_confirm(steps) and getattr(self, "hitl", None):
                    from jarvis.core.hitl import HitlDecision

                    result = self.hitl.ask_permission(
                        title="HITL · Computer use",
                        detail=(
                            f"Allow an autonomous computer-use session?\n\n"
                            f"Goal: {goal[:280]}\n"
                            f"Provider: {provider or agent.provider_name}\n"
                            f"Max steps: {steps}\n\n"
                            "Approve to let Jarvis control mouse/keyboard/browser. "
                            "Deny cancels. Say stop computer use anytime."
                        ),
                        action="computer_use",
                        agent="computer_use",
                        meta={"goal": goal[:200], "steps": steps},
                    )
                    if result.decision not in (
                        HitlDecision.APPROVED,
                        HitlDecision.SKIPPED,
                    ):
                        msg = "Computer use cancelled — permission denied."
                        self._emit("hud_alert", msg)
                        self.say(self._flavor("ok", msg))
                        return

                self._emit("fetching", True)
                self._emit(
                    "artifact",
                    {
                        "title": "COMPUTER USE",
                        "text": (
                            f"Goal: {goal}\n"
                            f"Provider: {provider or agent.provider_name}\n"
                            f"Max steps: {steps}\n"
                            "Say stop computer use to abort."
                        ),
                    },
                )
                reply = agent.start(goal, provider=provider, max_steps=steps)
                self.say(self._flavor("ok", reply))
            except Exception as e:
                self.say(self._flavor("error", f"Computer use failed: {e}"))
            finally:
                # fetching cleared when agent finishes via status callback;
                # also clear if start refused immediately
                try:
                    if not getattr(agent.status, "running", False):
                        self._emit("fetching", False)
                except Exception:
                    self._emit("fetching", False)

        threading.Thread(target=_run, daemon=True, name="computer-use-gate").start()
        if agent.needs_confirm(steps) and getattr(self, "hitl", None) and self.hitl.enabled:
            return self._flavor(
                "ok",
                "I need your approval for this computer-use run — Approve on the HUD, or say yes.",
            )
        # Immediate path: thread will speak the precise provider readiness line
        return ""

    def _try_computer_use_cmd(self, t: str) -> str | None:
        """Return a reply if this is a computer-use / browser-agent intent, else None."""
        if not t:
            return None
        try:
            agent = getattr(self, "cu_agent", None)
            if agent is None:
                # Still allow key-setting prompts to work if init failed partially
                if not re.search(
                    r"\b(computer\s*use|browser\s*agent|operator|"
                    r"anthropic\s+key|openai\s+key)\b",
                    t,
                    re.I,
                ):
                    return None

            # Status
            if re.search(
                r"\b((computer\s*use|browser\s*agent|operator)\s+status|"
                r"is\s+computer\s*use\s+(ready|running|linked)|"
                r"computer\s*use\s+ready)\b",
                t,
                re.I,
            ):
                if agent is None:
                    return self._flavor("error", "Computer-use agent is offline.")
                try:
                    agent.configure_from_settings(self.settings)
                except Exception:
                    pass
                return self._flavor("ok", agent.status_line())

            # Cancel / stop
            if re.search(
                r"\b((stop|cancel|abort|end|kill)\s+(computer\s*use|browser\s*agent|operator)|"
                r"(computer\s*use|browser\s*agent|operator)\s+(stop|cancel|abort))\b",
                t,
                re.I,
            ):
                if agent is None:
                    return self._flavor("ok", "No computer-use session to stop.")
                return self._flavor("ok", agent.cancel())

            # Setup / link guide
            if re.search(
                r"\b((link|connect|setup|set\s+up)\s+(computer\s*use|browser\s*agent|operator)|"
                r"(computer\s*use|browser\s*agent)\s+(setup|link|connect))\b",
                t,
                re.I,
            ):
                self._emit(
                    "artifact",
                    {
                        "title": "COMPUTER USE · SETUP",
                        "text": (
                            "FREE / LOCAL (no API credits):\n"
                            "1) Install Ollama from https://ollama.com/download\n"
                            "2) Start Ollama, then in a terminal:\n"
                            "     ollama pull llava\n"
                            "   (or: llama3.2-vision · qwen2.5vl · minicpm-v)\n"
                            "3) Say: computer use provider local\n"
                            "4) Optional browser window:\n"
                            "     pip install playwright && playwright install chromium\n"
                            "5) Example: computer use: open google maps\n"
                            "\n"
                            "PAID FALLBACK (optional):\n"
                            "  set anthropic key to YOUR_KEY  (Claude computer-use)\n"
                            "  set openai key to YOUR_KEY     (vision + actions)\n"
                            "  Paste keys in the command bar — not voice.\n"
                            "\n"
                            "Settings: computer_use_provider=auto|ollama|local|anthropic|openai|browser_use\n"
                            "computer_use_prefer_local=true → auto picks Ollama first\n"
                            "Keys stay in the DPAPI vault — never commit them."
                        ),
                    },
                )
                live = ""
                try:
                    if agent is not None:
                        agent.configure_from_settings(self.settings)
                        live = " Right now: " + agent.missing_guidance()
                except Exception:
                    live = ""
                return self._flavor(
                    "ok",
                    "Computer-use setup is on screen. For free local control: install Ollama, "
                    "pull llava, say computer use provider local, then computer use followed by your goal. "
                    "Cloud Anthropic/OpenAI keys are optional fallbacks."
                    + live,
                )

            # Set API keys
            m = re.search(
                r"\bset\s+anthropic\s+(?:api\s+)?key\s+to\s+(\S.+)$",
                t,
                re.I,
            )
            if m:
                key = self._capture_secret(
                    r"\bset\s+anthropic\s+(?:api\s+)?key\s+to\s+(\S.+)$",
                    m.group(1),
                )
                if not key or key.lower() in ("please", "now", "sir"):
                    return self._flavor(
                        "clarify",
                        "Paste in the command bar: set anthropic key to YOUR_KEY "
                        "(from console.anthropic.com — starts with sk-ant-). "
                        "Voice often truncates long keys.",
                    )
                if not key.startswith("sk-ant-"):
                    if key.startswith("sk-") or key.startswith("sk_"):
                        return self._flavor(
                            "clarify",
                            "That looks like an OpenAI or Stripe key. "
                            "Anthropic computer-use needs a key starting with sk-ant-.",
                        )
                    return self._flavor(
                        "clarify",
                        "Anthropic keys start with sk-ant-. "
                        "Copy the full key from console.anthropic.com into the command bar.",
                    )
                self.settings.anthropic_api_key = key
                self.settings.computer_use_enabled = True
                try:
                    self.settings.save()
                except Exception:
                    pass
                if agent is not None:
                    agent.anthropic_api_key = key
                    agent.configure_from_settings(self.settings)
                return self._flavor(
                    "ok",
                    "Anthropic key saved to the vault. Say computer use … to start an agent session.",
                )

            m = re.search(
                r"\bset\s+openai\s+(?:api\s+)?key\s+to\s+(\S.+)$",
                t,
                re.I,
            )
            if m:
                key = self._capture_secret(
                    r"\bset\s+openai\s+(?:api\s+)?key\s+to\s+(\S.+)$",
                    m.group(1),
                )
                if not key or key.lower() in ("please", "now", "sir"):
                    return self._flavor(
                        "clarify",
                        "Paste in the command bar: set openai key to YOUR_KEY "
                        "(from platform.openai.com). Voice often truncates long keys.",
                    )
                self.settings.openai_api_key = key
                self.settings.computer_use_enabled = True
                try:
                    self.settings.save()
                except Exception:
                    pass
                if agent is not None:
                    agent.openai_api_key = key
                    agent.configure_from_settings(self.settings)
                return self._flavor(
                    "ok",
                    "OpenAI key saved to the vault. Say computer use … or operator … to start.",
                )

            # Provider switch
            m = re.search(
                r"\b(?:computer\s*use|browser\s*agent)\s+provider\s+(\w+)\b",
                t,
                re.I,
            )
            if m:
                raw_name = m.group(1).strip().lower()
                from jarvis.core.computer_use_agent import normalize_provider_name

                name = normalize_provider_name(raw_name)
                allowed = {
                    "auto",
                    "ollama",
                    "local",
                    "free",
                    "anthropic",
                    "openai",
                    "browser_use",
                    "browseruse",
                    "desktop",
                    "gemini",
                    "skyvern",
                    "openinterpreter",
                }
                if raw_name.replace("-", "_") not in allowed and name not in {
                    "auto",
                    "ollama",
                    "anthropic",
                    "openai",
                    "browser_use",
                    "desktop",
                    "gemini",
                    "skyvern",
                    "openinterpreter",
                }:
                    return self._flavor(
                        "clarify",
                        "Providers: auto, ollama/local/free, anthropic, openai, browser_use, desktop "
                        "(gemini/skyvern/openinterpreter are stubs).",
                    )
                self.settings.computer_use_provider = name
                if name == "ollama":
                    try:
                        self.settings.computer_use_prefer_local = True
                    except Exception:
                        pass
                try:
                    self.settings.save()
                except Exception:
                    pass
                if agent is not None:
                    agent.provider_name = name
                    try:
                        agent.prefer_local = bool(
                            getattr(self.settings, "computer_use_prefer_local", True)
                        )
                    except Exception:
                        pass
                spoken = "ollama (local/free)" if name == "ollama" else name
                return self._flavor("ok", f"Computer-use provider set to {spoken}.")

            # Start session: computer use … / browser agent … / operator …
            m = re.search(
                r"\b(?:computer\s*use|browser\s*agent|operator)\s*:?\s+(.+)$",
                t,
                re.I,
            )
            if m:
                goal = m.group(1).strip(" .,!?")
                if not goal or re.match(
                    r"^(status|ready|stop|cancel|setup|link|provider|key)\b",
                    goal,
                    re.I,
                ):
                    return None
                return self._start_computer_use_session(goal)

            # "build a site for …" → computer-use agent (Maps/Lovable framing)
            if looks_like_computer_use_goal(t) and re.search(
                r"\bbuild\s+(a\s+)?(site|website)\s+for\b",
                t,
                re.I,
            ):
                goal = re.sub(
                    r"^(jarvis[, ]*)?(please )?",
                    "",
                    t,
                    flags=re.I,
                ).strip()
                framed = (
                    f"{goal}. Research on Google Maps if needed, gather business info, "
                    f"then open https://lovable.dev and draft a simple site."
                )
                return self._start_computer_use_session(framed)

            return None
        except Exception as e:
            return self._flavor("error", f"Computer-use command failed: {e}")

    def _ensure_phone_topic(self) -> None:
        if self.phone.topic:
            return
        topic = PhoneBridge.make_topic(self.settings.user_name or "jarvis")
        self.phone.topic = topic
        self.settings.phone_ntfy_topic = topic
        self.settings.phone_enabled = True
        try:
            self.settings.save()
        except Exception:
            pass

    def _link_phone(self) -> str:
        self._ensure_phone_topic()
        url = self.phone.subscribe_url()
        self._emit(
            "artifact",
            {
                "title": "IPHONE LINK · ntfy + companion",
                "text": (
                    "PUSH ALERTS (ntfy):\n"
                    "1) Install free app **ntfy** from the App Store on your iPhone 14.\n"
                    f"2) Open ntfy → Subscribe to topic:\n   {self.phone.topic}\n"
                    f"3) Or open: {url}\n"
                    "4) Say: ping my phone\n"
                    "\nREMOTE CONTROL (Tailscale PWA):\n"
                    "5) Say **open phone companion** for the chat URL.\n"
                    "   Install Tailscale on PC + iPhone (same account).\n"
                ),
            },
        )
        try:
            self.phone.notify(
                "Jarvis linked. You're connected, Sir.",
                title="JARVIS · linked",
            )
        except Exception:
            pass
        return self._flavor(
            "ok",
            f"Install ntfy on your iPhone and subscribe to topic {self.phone.topic}. "
            "I just sent a test ping. For remote control abroad, say open phone companion — "
            "you already have a Tailscale travel companion built in.",
        )

    def _route_desk_lane(self, t: str) -> str | None:
        """High-priority desk/security/NV intents — returns None if not matched."""
        if getattr(self, "security", None) and re.search(
            r"\b(enrol+ (my )?face|face enrol+|set up (face|biometric))\b", t
        ):
            # Single speak: async enroll result only (no "hold still" + result pair)
            return self._enroll_face_now() or ""
        if getattr(self, "security", None) and re.search(
            r"\b(security status|biometric status|intruder status)\b", t
        ):
            return self._flavor("ok", self.security.status())
        if getattr(self, "security", None) and re.search(
            r"\b(arm security|security on|enable (face )?security)\b", t
        ):
            self.security.enabled = True
            self.security._save_meta()
            try:
                self.settings.security_enabled = True
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Security armed.")
        if getattr(self, "security", None) and re.search(
            r"\b(disarm security|security off|disable (face )?security)\b", t
        ):
            self.security.enabled = False
            self.security._save_meta()
            try:
                self.settings.security_enabled = False
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Security disarmed.")
        if getattr(self, "security", None) and re.search(
            r"\b(intruder alerts? off|disable intruder( alerts?)?|"
            r"stop intruder( alerts?)?|quiet (the )?intruder|"
            r"no intruder alerts?)\b",
            t,
        ):
            try:
                self.settings.intruder_alert = False
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", self.security.set_intruder_alert(False))
        if getattr(self, "security", None) and re.search(
            r"\b(intruder alerts? on|enable intruder( alerts?)?|"
            r"arm intruder( alerts?)?)\b",
            t,
        ):
            try:
                self.settings.intruder_alert = True
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", self.security.set_intruder_alert(True))
        if re.search(r"\b(secure (the )?desk|lock (the )?workspace)\b", t):
            self._emit("hud_alert", "DESK SECURE")
            try:
                self.system.lock()
            except Exception:
                pass
            return self._flavor("ok", "Desk secured.")
        if re.search(
            r"\b(auto lock off|disable (auto |presence )?lock|presence lock off|"
            r"don'?t (auto )?lock|stop (auto )?locking)\b",
            t,
        ):
            self.settings.lock_on_absence = False
            try:
                self.settings.save()
            except Exception:
                pass
            try:
                if getattr(self, "security", None):
                    self.security.lock_on_leave = False
                    self.security._save_meta()
            except Exception:
                pass
            self.pause_presence_lock(False)
            if self._countdown_active:
                self._countdown_active = False
                self._emit("countdown_cancel", True)
            return self._flavor(
                "ok",
                "Auto-lock off. I only lock when you say secure desk.",
            )
        if re.search(
            r"\b(auto lock on|enable (auto |presence )?lock|presence lock on)\b",
            t,
        ):
            self.settings.lock_on_absence = True
            try:
                self.settings.save()
            except Exception:
                pass
            try:
                if getattr(self, "security", None):
                    self.security.lock_on_leave = True
                    self.security._save_meta()
            except Exception:
                pass
            return self._flavor("ok", "Auto-lock on. I'll lock after you step away.")
        # Night vision OFF before ON; auto before bare on
        if re.search(
            r"\b(night vision auto off|disable (auto )?night vision auto|"
            r"turn(ing)? off (auto )?night vision auto|auto night vision off)\b",
            t,
        ):
            try:
                self.settings.night_vision_auto = False
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Night vision auto off. Say night vision on if you still want it.")
        if re.search(
            r"\b(night vision auto( on)?|enable (auto )?night vision auto|"
            r"turn(ing)? on (auto )?night vision auto|auto night vision( on)?)\b",
            t,
        ):
            try:
                self.settings.night_vision_auto = True
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Night vision auto on — engages in settings timezone dusk window.",
            )
        if re.search(
            r"\b(night vision off|disable (the )?night vision|turn(ing)? off (the )?night vision|"
            r"turn (the )?night vision off|nvg off|stop (the )?night vision|"
            r"no night vision)\b",
            t,
        ):
            return self._flavor("ok", self.set_night_vision(False, announce=False))
        if re.search(
            r"\b(night vision( on)?|enable (the )?night vision|turn(ing)? on (the )?night vision|"
            r"turn (the )?night vision on|nvg( on)?)\b",
            t,
        ):
            return self._flavor("ok", self.set_night_vision(True, announce=False))
        if getattr(self, "autobug", None) and re.search(
            r"\b(fix (this |the )?(bug|error)|autobug|debug this)\b",
            t,
        ):
            return self._flavor("ok", self.autobug.analyze(t))
        if getattr(self, "autobug", None) and re.search(
            r"\b(open last error|show last (error|bug))\b", t
        ):
            p = self.autobug.last_path()
            if not p.exists():
                return self._flavor("ok", "No saved error yet.")
            try:
                self._emit(
                    "artifact",
                    {"title": "LAST ERROR", "text": p.read_text(encoding="utf-8")[:4000]},
                )
            except Exception:
                pass
            return self._flavor("ok", "Last error is on screen.")
        if getattr(self, "self_audit", None) and re.search(
            r"\b(self[- ]?audit|run (a )?self audit|audit yourself)\b", t
        ):
            return self._flavor("ok", self.self_audit.run(apply=False))
        if re.search(r"\b(router status|semantic router|route priority)\b", t):
            try:
                # Keep ack short — full legend stays in HUD artifact
                legend = self.router.priority_legend()
                self._emit(
                    "artifact",
                    {"title": "ROUTER", "text": legend},
                )
                return self._flavor("ok", "Router is local-first. Legend is on screen.")
            except Exception as e:
                return self._flavor("ok", f"Router offline: {e}")
        if re.search(r"\b(spatial (gestures? )?(on|enable)|enable spatial)\b", t):
            self._emit("spatial_ui", True)
            return self._flavor(
                "ok",
                "Spatial gestures on. Open camera — pinch to edges, swipe between monitors.",
            )
        if re.search(r"\b(spatial (gestures? )?(off|disable)|disable spatial)\b", t):
            self._emit("spatial_ui", False)
            return self._flavor("ok", "Spatial gestures off.")
        if re.search(r"\b(spatial status|gesture spatial)\b", t):
            self._emit("spatial_status", True)
            return self._flavor(
                "ok",
                "Spatial: pinch hold at left/right edge to throw boards; "
                "swipe right PDTester, left HUD home, up dual layout, down stack.",
            )
        return None

    def _route(self, t: str) -> str:
        """
        Priority (semantic router lanes — first match wins):
          emergency → hotkey → phone/manus → travis → desk → facts →
          media → build → productivity → hub/AI → chitchat → fallback

        Simple local intents never call Hub. Complex / agent asks may.
        """
        # Classify once for hub gate + HUD
        decision = None
        try:
            if getattr(self, "router", None):
                decision = self.router.decide(t)
                self._emit(
                    "command_ui",
                    {
                        "kind": "route",
                        "text": t[:80],
                        "detail": f"{decision.lane.value}/{decision.complexity.value}",
                    },
                )
        except Exception:
            decision = None

        # Phone / iPhone — FIRST (must not fall through to Help / Hub)
        phone_reply = self._try_phone_cmd(t)
        if phone_reply is not None:
            return phone_reply

        # Cloud integrations (Stripe / Notion / Buffer / Gmail)
        try:
            cloud_reply = self._try_cloud_cmd(t)
            if cloud_reply is not None:
                return cloud_reply
        except Exception as e:
            print(f"[cloud] {e}")

        # Manus AI agent — local bridge (before Hub)
        try:
            manus_reply = self._try_manus_cmd(t)
            if manus_reply is not None:
                return manus_reply
        except Exception:
            pass

        # Agent crew — six-agent pipeline (before Hub)
        try:
            crew_reply = self._try_crew_cmd(t)
            if crew_reply is not None:
                return crew_reply
        except Exception as e:
            print(f"[crew] route: {e}")

        # Computer-use / browser agent (before Hub)
        try:
            cu_reply = self._try_computer_use_cmd(t)
            if cu_reply is not None:
                return cu_reply
        except Exception as e:
            print(f"[computer-use] route: {e}")

        # Voice hotkeys — copy/paste/save macros (before Travis / Hub)
        try:
            if getattr(self, "hotkeys", None):
                hk = self.hotkeys.try_run(t)
                if hk is not None:
                    return self._flavor("ok", hk)
        except Exception:
            pass

        # Travis personality modes — Park / Tactical / Peer Review
        travis_intent = parse_mode_command(t)
        if travis_intent is not None:
            return self._apply_travis_mode(travis_intent)

        # DESK lane first (security / NV / enroll) — before Hub & long chain
        desk = self._route_desk_lane(t)
        if desk is not None:
            return desk

        # Hub & Spoke — only when router allows (local-first)
        hub_ok = True
        try:
            if decision is not None and getattr(self, "router", None):
                hub_ok = self.router.allows_hub(t)
            elif decision is not None and decision.force_local:
                hub_ok = False
        except Exception:
            hub_ok = True

        explicit_hub = bool(
            re.search(
                r"\b(start hub|restart hub|hub status|hub standby|"
                r"ask (sarah|tom|admin)|agent (sarah|tom|admin))\b",
                t,
            )
            or HubClient.wants_hub(t)
        )
        # Complex / research / coding — prefer Hub when router says hub
        complex_hub = bool(
            decision is not None
            and decision.complexity.value == "hub"
            and not decision.force_local
            and (len(t.split()) >= 5 or explicit_hub)
        )

        # Explicit spoke asks always reach Hub; complex only when router allows
        if getattr(self.settings, "hub_enabled", True) and (
            explicit_hub or (hub_ok and complex_hub)
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

        # Accept pending suggestion — one shot, then suppress cascade
        if re.search(
            r"\b(yes|yeah|yep|do it|go ahead|sure|please do|sounds good)\b",
            t,
        ) and self.suggestions.pending_cmd:
            if not self.suggestions.pending_fresh(45.0):
                self.suggestions.clear_pending()
            else:
                cmd = self.suggestions.pending_cmd
                # Avoid accidental workspace/browser spam from a lone "yes"
                if re.search(r"\b(workspace|work mode|starting work|check email)\b", cmd):
                    if not re.search(
                        r"\b(do it|go ahead|please do|yes please|set (it )?up)\b", t
                    ):
                        return (
                            "Just to confirm — say 'go ahead' if you want me to open "
                            "apps and tabs for that."
                        )
                cmd = self.suggestions.accept()
                if not cmd:
                    return self._flavor("ok", "Nothing pending.")
                self._skip_suggestion_followups = True
                return self._route(cmd)

        # Suggestions on / off
        if re.search(
            r"\b(stop suggesting|suggestions? off|disable suggestions?|"
            r"no more suggestions?|quiet suggestions?)\b",
            t,
        ):
            return self._flavor("ok", self.suggestions.set_enabled(False))
        if re.search(
            r"\b(suggestions? on|enable suggestions?|start suggesting)\b", t
        ):
            return self._flavor("ok", self.suggestions.set_enabled(True))

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
            # Prefer structured daily standup when saying good morning
            if "good morning" in t or re.search(r"\b(morning brief|daily brief|standup)\b", t):
                cache = Path(__file__).resolve().parent / "data" / "morning_standup.txt"
                if cache.exists():
                    try:
                        age = time.time() - cache.stat().st_mtime
                        if age < 14 * 3600:  # same-day-ish precache from Task Scheduler
                            text = cache.read_text(encoding="utf-8").strip()
                            if text:
                                try:
                                    self.ha.on_jarvis_state("brief")
                                except Exception:
                                    pass
                                self._emit("hud_alert", "Morning standup ready")
                                self.feed.push("brief", text[:180])
                                return self._flavor("ok", text)
                    except Exception:
                        pass
                wx = ""
                try:
                    wx = self.weather.speak_brief()
                except Exception:
                    wx = ""
                weather_line = f"Weather: {wx}." if wx else ""
                try:
                    if getattr(self, "live", None):
                        weather_line = self.live.briefing_prefix()
                except Exception:
                    pass
                brief = self.brief.morning_standup(
                    weather_line=weather_line, open_inbox=False
                )
                try:
                    self.ha.on_jarvis_state("brief")
                except Exception:
                    pass
                self._emit("hud_alert", "Morning standup ready")
                self.feed.push("brief", brief[:180])
                return self._flavor("ok", brief)
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

        # Zoom / fly map to a city or country → open (if needed) + cinematic fly
        dest = self._extract_map_zoom_place(t)
        if dest:
            return self._map_zoom_to(dest)

        # Relative zoom (no destination) — still opens map with intro if closed
        if re.search(
            r"\b(zoom\s+in|zoom\s+closer|magnify(\s+map)?|pull\s+in(\s+on\s+the\s+map)?)\b",
            t,
        ):
            return self._map_zoom_delta(2.2)
        if re.search(
            r"\b(zoom\s+out|pull\s+back(\s+on\s+the\s+map)?|pull\s+out(\s+on\s+the\s+map)?)\b",
            t,
        ):
            return self._map_zoom_delta(-2.6)

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
            r"\b((show|put|move) (stats|ops|operations|command center|pdtester|devlog|digests?)"
            r"( on (the )?(other|second) (monitor|screen|display))?|"
            r"ops (board|monitor)|show ops|open ops|show stats|"
            r"open (the )?(ops|pdtester|devlog)|show (pdtester|digests?))\b",
            t,
        ):
            self._emit("show_ops", True)
            self._emit("place_ops", "secondary")
            try:
                self.settings.ops_monitor_enabled = True
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "PDTester is on your other monitor — six digests and the live feed.",
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

        # Time / date — East Coast (Philadelphia) timezone
        if re.search(r"\b(what time|current time|tell me the time)\b", t):
            try:
                if getattr(self, "live", None):
                    d = self.live.snapshot()
                    return self._flavor("time", f"It's {d['time_12']} on {d['date']}.")
            except Exception:
                pass
            from zoneinfo import ZoneInfo

            now = datetime.now(ZoneInfo("America/New_York"))
            return self._flavor(
                "time",
                "It's "
                + now.strftime("%I:%M %p").lstrip("0")
                + now.strftime(" on %A, %B %d, %Y."),
            )
        if re.search(r"\b(what(?:'s| is) the date|today'?s date|what day)\b", t):
            try:
                if getattr(self, "live", None):
                    d = self.live.snapshot()
                    return self._flavor(
                        "time",
                        f"Today is {d['date']}. Local time {d['time_12']}.",
                    )
            except Exception:
                pass
            from zoneinfo import ZoneInfo

            now = datetime.now(ZoneInfo("America/New_York"))
            return self._flavor("time", now.strftime("Today is %A, %B %d, %Y."))

        # Weather
        if re.search(r"\b(weather|temperature|how hot|how cold)\b", t):
            self._emit("weather_ui", True)
            self.habits.log("weather")
            try:
                if getattr(self, "live", None):
                    prefix = self.live.briefing_prefix()
                    return self._flavor("weather", prefix)
            except Exception:
                pass
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
            self._note_mode_at = time.time()
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
            try:
                self.vstore.remember(note, kind="note")
            except Exception:
                pass
            return self._flavor(
                "ok", self.notes.take(note, from_screen=False, audio=False)
            )

        # Durable vector facts — "note that my camera is on the left monitor"
        m = re.search(
            r"\b(?:note that|for the record|remember that|don't forget that)\s+(.+)$",
            t,
        )
        if m:
            fact = m.group(1).strip(" .")
            if fact:
                msg = self.vstore.remember(fact, kind="fact")
                return self._flavor("ok", msg)

        # Possessive durable facts: "my eMeet camera is mounted on my left monitor"
        m = re.search(
            r"^(?:please\s+)?(my|the)\s+(.{3,60}?)\s+"
            r"(is|are|was|sits|mounted|located|plugged|connected|lives)\s+(.+)$",
            t,
        )
        if m and not re.search(
            r"\b(playing|open|running|loading|wrong|broken|down|time|weather|"
            r"password|volume|muted|busy|here|there|ready)\b",
            t,
        ):
            fact = t.strip(" .")
            msg = self.vstore.remember(fact, kind="fact")
            return self._flavor("ok", msg)

        if re.search(r"\b(memory status|how(?:'s| is) (your )?memory)\b", t):
            return self._flavor("ok", self.vstore.status())
        m = re.search(r"\b(?:what do you (know|remember) about|recall)\s+(.+)$", t)
        if m:
            q = m.group(2).strip()
            hits = self.vstore.recall(q, n=5)
            if not hits:
                return self._flavor("ok", f"Nothing stored about {q} yet.")
            return self._flavor("ok", "Here's what I remember: " + "; ".join(hits))
        m = re.search(r"\b(?:forget(?: that)?)\s+(.+)$", t)
        if m:
            return self._flavor("ok", self.vstore.forget(m.group(1).strip()))

        if re.search(r"\b(show notes|my notes|list notes|open notes)\b", t):
            if "open" in t:
                return self._flavor("ok", self.notes.open_log())
            return self.notes.list_recent()

        # Clipboard
        if re.search(
            r"\b(read clipboard|what(?:'s| is) on (my )?clipboard|clipboard|"
            r"summarize (the |my )?clipboard|clipboard summary)\b",
            t,
        ):
            if re.search(r"summar|summary", t):
                return self._flavor("ok", self._summarize_clipboard())
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

        # Audio device routing (pycaw)
        if re.search(r"\b(audio (status|devices)|list (audio |sound )?(devices|outputs))\b", t):
            return self._flavor("ok", self.audio.status())
        m = re.search(
            r"\b(?:switch|set|use|change)\s+(?:(?:to|the)\s+)?"
            r"(headphones?|headset|speakers?|emeet|[\w\s\-]{2,40}?)"
            r"(?:\s+(?:audio|output|sound|device))?\b",
            t,
        )
        if m and re.search(r"\b(switch|headphones?|speakers?|audio output|sound (to|output))\b", t):
            target = m.group(1).strip()
            return self._flavor("ok", self.audio.switch_output(target))
        if re.search(r"\b(use headphones|switch to headphones)\b", t):
            return self._flavor("ok", self.audio.switch_output("headphones"))
        if re.search(r"\b(use speakers|switch to speakers)\b", t):
            return self._flavor("ok", self.audio.switch_output("speakers"))
        m = re.search(r"\b(?:set )?(?:volume|master volume)\s+(?:to\s+)?(\d{1,3})\b", t)
        if m:
            return self._flavor("ok", self.audio.set_volume(int(m.group(1))))
        if re.search(r"\b(mute (audio|sound|volume)|mute output)\b", t):
            return self._flavor("ok", self.audio.mute(True))
        if re.search(r"\b(unmute)\b", t):
            return self._flavor("ok", self.audio.mute(False))
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

        # Google Maps directions (CTK: navigate to …)
        m = re.search(
            r"\b(?:navigate(?:\s+to)?|directions(?:\s+to)?|take me to|drive to|route to)\s+(.+)$",
            t,
        )
        if m:
            dest = m.group(1).strip(" .")
            dest = re.sub(r"\b(please|for me|now)\b", "", dest, flags=re.I).strip(" .")
            if dest:
                url = (
                    "https://www.google.com/maps/dir/?api=1&destination="
                    + urllib.parse.quote_plus(dest)
                )
                try:
                    webbrowser.open(url)
                except Exception:
                    self.apps.open(url)
                self.habits.log("navigate", dest[:40])
                return self._flavor(
                    "ok", f"Plotting transit vectors for {dest}."
                )

        # Scan item through camera (one-shot — camera closes when done)
        if re.search(
            r"\b(scan|scan (this|that|it|item|object)|what(?:'s| is) this|"
            r"identify|read (the )?text|ocr|camera search)\b",
            t,
        ):
            if self._scanning:
                return "Already scanning — one moment."
            self._scanning = True
            # CTK "camera search" / explicit online search → Google Lens
            self._scan_open_browser = bool(
                re.search(
                    r"\b(camera search|search (it |this )?(online|on google|with google)|"
                    r"google (this|that|it)|lens)\b",
                    t,
                )
                or "camera search" in t
            )
            self.habits.log("scan")
            self._emit("scan_now", True)
            if self._scan_open_browser:
                return self._flavor(
                    "scan",
                    "Activating camera array — I'll identify it and open Google Lens.",
                )
            return self._flavor("scan", "Hold it steady in the green box — I'll tell you what it is.")

        # Camera / EMEET (accepts typos like "camrea") — NEVER shell-open as a file
        if is_camera_query(t) and not re.search(r"\b(close|hide|scan)\b", t):
            try:
                self.vision.stop()
            except Exception:
                pass
            self._emit("camera_ui", True)
            self._emit("hud_alert", "Opening camera theater…")
            return self._flavor(
                "open",
                "Opening the camera theater now — one moment.",
            )
        if re.search(r"\b(close|hide)\s+(the\s+|my\s+)?(cam|camera|camrea|webcam|emeet)\b|\bcamera\s+off\b", t):
            self._emit("camera_ui", False)
            # UI restarts presence after the device is released — don't race here
            return self._flavor("ok", "Camera closed. Presence lock re-armed.")
        if re.search(r"\b(switch (the )?cam(era)?|next cam(era)?|change cam(era)?)\b", t):
            try:
                cur = int(getattr(self.settings, "camera_index", 0) or 0)
                nxt = (cur + 1) % 6
                self.settings.camera_index = nxt
                self.settings.save()
                self.vision.stop()
            except Exception:
                nxt = 1
            self._emit("camera_ui", True)
            return self._flavor(
                "ok",
                f"Switching camera to device index {nxt}.",
            )
        if re.search(r"\b(test (the )?mic(rophone)?|mic(rophone)? test|can you hear me)\b", t):
            lvl = 0.0
            try:
                lvl = float(self.voice.level())
            except Exception:
                pass
            prefer = getattr(self.settings, "mic_prefer", "") or "default"
            if lvl < 0.02:
                return self._flavor(
                    "ok",
                    f"Mic path is {prefer}, but I'm barely hearing signal. "
                    "Talk louder, unmute the mic, or say switch to headphones.",
                )
            return self._flavor(
                "ok",
                f"Yes — microphone is live on {prefer}. Level about {int(lvl * 100)} percent.",
            )

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
                return self._flavor("open", "Bringing the camera theater to the front now.")
            result = self.apps.open(target)
            if result == "CAMERA_UI":
                try:
                    self.vision.stop()
                except Exception:
                    pass
                self._emit("camera_ui", True)
                return self._flavor("open", "Bringing the camera theater to the front now.")
            self.habits.log("open_app", target[:40])
            return self._flavor("open", result)

        # Unlock BEFORE lock (else "unlock my pc" matches lock)
        if re.search(
            r"\b(unlock (my )?(pc|computer|workstation|screen)|"
            r"type (my )?pin|sign (me )?in)\b",
            t,
        ):
            self._emit("hud_alert", "UNLOCK")
            return self._flavor("ok", self.system.unlock())
        m_pin = re.search(
            r"\bset (my )?unlock (pin|password|passcode)\s*(?:to|=)?\s*(.+)$",
            t,
            flags=re.I,
        )
        if m_pin:
            from jarvis.core.pc_unlock import store_unlock_pin

            # Never echo the PIN back into TTS / logs
            msg = store_unlock_pin(m_pin.group(3).strip(" .,\"'"))
            self._emit("heard", "[security] unlock PIN updated (redacted)")
            return self._flavor("ok", msg)

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
        if re.search(
            r"\b(upgrade check|self health|health check|desk health|system health)\b",
            t,
        ):
            return self._flavor("ok", self._upgrade_check_line())
        if re.search(r"\b(recent errors|show (recent )?errors|log errors)\b", t):
            return self._flavor("ok", self._recent_errors_line())
        if re.search(
            r"\b(full status|systems? overview|upgrade status|feature status)\b", t
        ):
            if "upgrade status" in t or "feature status" in t or (
                "upgrade" in t and "check" not in t and "full" not in t
            ):
                return self._flavor("ok", self._upgrade_status_line())
            return self._flavor("ok", self._full_status_line())
        if re.search(
            r"\b(quiet mode|mute alerts|silence (the )?desk|do not disturb)\b", t
        ):
            return self._flavor("ok", self._enter_quiet_mode())
        if re.search(
            r"\b(loud mode|exit quiet|unmute alerts|leave quiet mode|end quiet mode)\b",
            t,
        ):
            return self._flavor("ok", self._exit_quiet_mode())
        if re.search(
            r"\b(wake word only|require wake( word)?|listen for wake)\b", t
        ):
            self.settings.wake_required = True
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Wake word required. Say Jarvis first — I will ignore ambient talk.",
            )
        if re.search(
            r"\b(always listen|wake word off|disable wake( word)?)\b", t
        ):
            self.settings.wake_required = False
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Always listening. I will act on commands without hearing Jarvis first.",
            )
        if re.search(r"\b(desk ready|prep (my )?desk|ready (the )?desk)\b", t):
            return self._flavor("ok", self._desk_ready())
        if re.search(
            r"\b(summarize (my )?day|day summary|recap (my )?day)\b", t
        ):
            return self._flavor("ok", self._summarize_my_day())
        if re.search(
            r"\b(summarize (the |my )?clipboard|clipboard summary)\b", t
        ):
            return self._flavor("ok", self._summarize_clipboard())
        if re.search(
            r"\b(system (status|vitals)|how(?:'s| is) (the )?(cpu|system))\b", t
        ) or re.fullmatch(r"status", t.strip()):
            tel = self.system.telemetry()
            bat = f"{tel.battery:.0f}%" if tel.battery is not None else "AC"
            return self._flavor(
                "ok",
                f"CPU {tel.cpu:.0f} percent, memory {tel.memory:.0f} percent, battery {bat}.",
            )

        # Update software (manual patch panel)
        if re.search(r"\b(update software|add (a )?feature|hot.?reload|patch system)\b", t):
            self.voice.mute_mic(True)
            self._emit("update_ui", True)
            return "Update panel open. Type your request — I will sandbox it."

        # Cancel upgrade BEFORE upgrade (else "cancel upgrade" starts one)
        if re.search(r"\b(cancel upgrade|abort upgrade|unfreeze( registry)?)\b", t):
            try:
                if getattr(self, "registry", None):
                    self.registry.unfreeze()
                self._emit("upgrade_ui", {"pct": 100, "done": True, "cancel": True})
                self._emit("registry_ui", {"frozen": False})
                self._emit("hud_alert", "Upgrade cancelled")
            except Exception:
                pass
            return self._flavor("ok", "Upgrade cancelled. Registry live.")

        # Full hot-upgrade with loading UI 0→100%
        if re.search(
            r"\b((run( an)? |system )?upgrade( (jarvis|system|everything|all|core|scripts?|files?)?)?|"
            r"upgrade all)\b",
            t,
        ) and not re.search(r"\b(update software|cancel|abort)\b", t):
            return self._run_hot_upgrade()

        # Feature registry / command monitor (additive)
        if re.search(
            r"\b(feature status|registry status|list features|feature registry)\b", t
        ):
            try:
                return self._flavor("ok", self.registry.status())
            except Exception as e:
                return self._flavor("ok", f"Registry unavailable: {e}")
        if re.search(r"\b(show|open) (the )?command monitor\b", t):
            self._emit("monitor_ui", True)
            return self._flavor("ok", "Command monitor on the right rail.")
        if re.search(r"\b(hide|close) (the )?command monitor\b", t):
            self._emit("monitor_ui", False)
            return self._flavor("ok", "Command monitor hidden.")

        # Automated workflows
        if re.search(r"\b(list workflows?|what workflows|workflow(s)? list)\b", t):
            if self.workflows:
                return self._flavor("ok", self.workflows.list_workflows())
            return self._flavor("ok", "Workflow engine offline.")
        wf = re.search(
            r"\b(?:run|start|execute)\s+(morning|night|focus|standup|secure)"
            r"(?:\s+workflow|\s+routine)?\b",
            t,
        )
        if wf:
            return self._flavor("ok", self._run_workflow(wf.group(1)))
        if re.search(r"\b(morning (workflow|routine)|start my day)\b", t):
            return self._flavor("ok", self._run_workflow("morning"))
        if re.search(r"\b(night (workflow|routine)|wind down)\b", t):
            return self._flavor("ok", self._run_workflow("night"))
        if re.search(r"\b(focus (workflow|routine)|deep work mode)\b", t):
            return self._flavor("ok", self._run_workflow("focus"))

        # Additive system / lamp / ops helpers (existing APIs only)
        if re.search(r"\b(disk space|how much disk|storage (left|free))\b", t):
            try:
                tel = self.system.telemetry()
                used_pct = getattr(tel, "disk", 0)
                total_g, free_g = self.system.disk_capacity()
                return self._flavor(
                    "ok",
                    f"Disk at {used_pct:.0f} percent — {free_g:.0f} gigabytes free of {total_g:.0f}.",
                )
            except Exception as e:
                return self._flavor("ok", f"Disk check failed: {e}")
        if re.search(r"\b(task status|queue status|background tasks)\b", t):
            try:
                line = getattr(self.tasks, "status_line", None)
                return self._flavor(
                    "ok", line() if callable(line) else "Task queue online."
                )
            except Exception:
                return self._flavor("ok", "Task queue status unavailable.")
        if re.search(r"\b(home assistant status|ha status)\b", t):
            try:
                return self._flavor("ok", self.ha.status())
            except Exception as e:
                return self._flavor("ok", f"Home Assistant: {e}")
        if re.search(r"\b(toggle( the)? lamp|lamp toggle)\b", t):
            try:
                # Prefer explicit toggle if present
                tog = getattr(self.lamp, "toggle", None)
                if callable(tog):
                    return self._flavor("ok", tog())
                return self._flavor("ok", self.lamp.turn_on())
            except Exception as e:
                return self._flavor("ok", f"Lamp toggle failed: {e}")
        if re.search(r"\bcoding mode\b", t):
            try:
                return self._flavor("ok", self.lights.set_mode("coding"))
            except Exception:
                return self._flavor("ok", self.lamp.turn_on())
        if re.search(r"\breading mode\b", t):
            try:
                return self._flavor("ok", self.lights.set_mode("reading"))
            except Exception:
                return self._flavor("ok", self.lamp.turn_on())

        # ── Productivity suite (additive) ───────────────────────
        if re.search(r"\b(mood status|how(?:'s| is) your mood)\b", t):
            try:
                return self._flavor("ok", self.mood.status())
            except Exception:
                return self._flavor("ok", "Mood engine offline.")
        if re.search(r"\bproactive (on|enable)\b", t):
            try:
                self.proactive.set_enabled(True)
                self.settings.proactive_enabled = True
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Proactive interventions armed.")
        if re.search(r"\bproactive (off|disable)\b", t):
            try:
                self.proactive.set_enabled(False)
                self.settings.proactive_enabled = False
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "I'll stay quiet unless spoken to.")
        if re.search(r"\b(git status|repo status)\b", t):
            if not getattr(self, "gitbot", None):
                return self._flavor("ok", "Git helper offline.")
            return self._flavor("ok", self.gitbot.status_line())
        if re.search(
            r"\b(auto commit( and push)?|commit (my )?(code|changes)( and push)?|"
            r"push (my )?changes|github (auto )?commit)\b",
            t,
        ):
            if not getattr(self, "gitbot", None):
                return self._flavor("ok", "Git helper offline.")
            push = bool(re.search(r"\bpush\b", t))
            hint = ""
            m = re.search(r"\b(?:message|saying)\s+(.+)$", t)
            if m:
                hint = m.group(1).strip(" .")
            return self._flavor("ok", self.gitbot.commit_all(hint, push=push or None))
        if re.search(
            r"\b(schedule|book|add|create)\b.+\b(calendar|meeting|event)\b|"
            r"\bschedule\b.+\b(next|tomorrow|monday|tuesday|wednesday|thursday|friday)\b|"
            r"\bremind me\b.+\b(at|next|tomorrow)\b",
            t,
        ):
            if not getattr(self, "calendar", None):
                return self._flavor("ok", "Calendar offline.")
            return self._flavor("ok", self.calendar.schedule(t))
        if re.search(r"\b(tech news|technology (news|headlines))\b", t):
            if not getattr(self, "topics", None):
                return self._flavor("ok", "Topic monitor offline.")
            return self._flavor("ok", self.topics.headlines("tech"))
        if re.search(r"\b(gaming news|game (news|headlines)|ign news)\b", t):
            if not getattr(self, "topics", None):
                return self._flavor("ok", "Topic monitor offline.")
            return self._flavor("ok", self.topics.headlines("gaming"))
        if re.search(r"\b(marketing news|marketing (headlines|pulse))\b", t):
            if not getattr(self, "topics", None):
                return self._flavor("ok", "Topic monitor offline.")
            return self._flavor("ok", self.topics.headlines("marketing"))
        if re.search(r"\b(check prices|price (check|alerts?|watch)|any price drops)\b", t):
            if not getattr(self, "prices", None):
                return self._flavor("ok", "Price watch offline.")
            return self._flavor("ok", self.prices.check())
        if re.search(r"\b(price watch status|watchlist)\b", t):
            if not getattr(self, "prices", None):
                return self._flavor("ok", "Price watch offline.")
            return self._flavor("ok", self.prices.status())
        m_price = re.search(
            r"\bwatch(?:\s+price)?(?:\s+for)?\s+(.+?)\s+(?:at|url)\s+(\S+)",
            t,
            flags=re.I,
        )
        if m_price:
            if not getattr(self, "prices", None):
                return self._flavor("ok", "Price watch offline.")
            return self._flavor(
                "ok", self.prices.watch(m_price.group(1).strip(), m_price.group(2).strip())
            )
        if re.search(
            r"\b(start voice( to)? code|dictate code|voice to code|code dictation)\b",
            t,
        ):
            if not getattr(self, "voice_code", None):
                return self._flavor("ok", "Voice-to-code offline.")
            return self._flavor("ok", self.voice_code.start("javascript"))
        if re.search(r"\b(media pause on stand|pause (video|netflix|youtube) when i (stand|leave))\b", t):
            if not getattr(self, "media_presence", None):
                return self._flavor("ok", "Media presence offline.")
            self.media_presence.enabled = True
            try:
                self.settings.media_pause_on_stand = True
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "I'll pause media when you stand up.")
        if re.search(r"\b(media pause off|don'?t pause (media|video))\b", t):
            if getattr(self, "media_presence", None):
                self.media_presence.enabled = False
            return self._flavor("ok", "Media pause on stand disabled.")

        if re.search(r"\b(mark (task |it )?complete|task complete|you('re| are) complete)\b", t):
            try:
                self.feed.push("task", "Marked complete")
            except Exception:
                pass
            self._emit("hud_alert", "TASK COMPLETE")
            return self._flavor("ok", "Marked complete.")

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
        # Alexa / smart lamp
        if re.search(r"\b(lamp status|light status|alexa lamp)\b", t):
            return self._flavor("ok", self.lamp.status())

        # RLHF preference feedback
        if re.search(r"\b(rlhf status|feedback status)\b", t):
            return self._flavor("ok", self.rlhf.status())
        if re.search(
            r"\b(approve( that| this| it)?|that was (good|correct|right)|good job|"
            r"thumbs up|prefer that)\b",
            t,
        ) and not self.hitl.pending:
            return self._flavor("ok", self.rlhf.approve())
        if re.search(
            r"\b(reject( that| this| it)?|that was (wrong|bad|incorrect)|thumbs down|"
            r"don'?t do that|prefer not)\b",
            t,
        ) and not self.hitl.pending:
            return self._flavor("ok", self.rlhf.reject())
        if re.search(r"\b(digest (rlhf|feedback)|run (rlhf )?digest)\b", t):
            return self._flavor("ok", self.rlhf.digest(apply=True))

        if re.search(
            r"\b((turn|switch|put) (the )?(lamp|light|bulb) on|"
            r"(lamp|light|bulb) on|lights? on)\b",
            t,
        ) and not re.search(r"\b(night vision|coding|reading)\b", t):
            self._reactor_safe("fetch")
            return self._flavor("ok", self.lamp.turn_on())
        if re.search(
            r"\b((turn|switch|put) (the )?(lamp|light|bulb) off|"
            r"(lamp|light|bulb) off|lights? off)\b",
            t,
        ):
            self._reactor_safe("fetch")
            return self._flavor("ok", self.lamp.turn_off())
        if re.search(r"\b(toggle (the )?(lamp|light|bulb)|lamp toggle)\b", t):
            self._reactor_safe("fetch")
            return self._flavor("ok", self.lamp.toggle())
        m = re.search(
            r"\b(?:set|dim|brighten)?\s*(?:the )?(?:lamp|light|bulb)\s*"
            r"(?:to\s+)?(\d{1,3})\s*(?:%|percent)?\b",
            t,
        )
        if m and re.search(r"\b(lamp|light|bulb|brightness|dim|bright)\b", t):
            self._reactor_safe("fetch")
            return self._flavor("ok", self.lamp.brightness(int(m.group(1))))

        if re.search(r"\b(coding mode|code mode|bright (lights?|white))\b", t):
            return self._flavor("ok", self.lights.set_mode("coding"))
        if re.search(r"\b(reading mode|warm (lights?|amber)|read mode)\b", t):
            return self._flavor("ok", self.lights.set_mode("reading"))
        if re.search(r"\b(late night( mode)?|night mode|dim red)\b", t):
            return self._flavor("ok", self.lights.set_mode("late_night"))
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
            if not getattr(self.settings, "theme_sync_windows", False):
                return self._flavor(
                    "ok",
                    "Windows theme sync is off so I will not change your taskbar. "
                    "Say enable windows theme sync first, or change Windows settings yourself.",
                )
            return self._flavor("ok", self.theme_sync.set_dark(True))
        if re.search(r"\b(light mode|day theme)\b", t):
            if not getattr(self.settings, "theme_sync_windows", False):
                return self._flavor(
                    "ok",
                    "Windows theme sync is off. Say enable windows theme sync to allow light mode.",
                )
            return self._flavor("ok", self.theme_sync.set_dark(False))
        if re.search(r"\b(enable windows theme sync|windows theme sync on)\b", t):
            self.settings.theme_sync_windows = True
            self.theme_sync.windows_enabled = True
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Windows theme sync enabled. Say dark mode or light mode to change the taskbar.",
            )
        if re.search(r"\b(disable windows theme sync|windows theme sync off)\b", t):
            self.settings.theme_sync_windows = False
            self.theme_sync.windows_enabled = False
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Windows theme sync disabled.")
        if re.search(r"\b(sync theme|adaptive theme)\b", t):
            return self._flavor("ok", self.theme_sync.apply_for_hour())
        if re.search(r"\b(fix( my)? (taskbar|theme)|restore dark( theme)?)\b", t):
            msg = self.theme_sync.restore_dark_taskbar()
            return self._flavor("ok", msg)
        if re.search(r"\b(boost( mode)?|performance boost|game mode)\b", t):
            return self._flavor("ok", self.boost.boost())
        if re.search(r"\b(restore processes|end boost)\b", t):
            return self._flavor("ok", self.boost.restore())
        # Smooth / eco HUD (not process suspend — pairs with governor)
        if re.search(
            r"\b("
            r"smooth mode off|performance mode off|exit smooth|"
            r"full fidelity|end smooth mode"
            r")\b",
            t,
        ):
            return self._set_performance_mode(False)
        if re.search(
            r"\b(smooth mode|performance mode|eco hud|eco mode)\b",
            t,
        ):
            return self._set_performance_mode(True)
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

        # Computer-use: click / type / hotkeys / scroll (pyautogui)
        m = re.search(
            r"\b(?:click|press|tap|hit)\s+(?:(?:on|the)\s+)?(.+)$",
            t,
        )
        if m and not re.search(r"\b(play|pause|mute|camera|lock|ctrl|alt|shift|enter|tab)\b", t):
            label = m.group(1).strip().strip("\"'")
            if 1 < len(label) < 48:
                self._emit("fetching", True)
                return self._flavor("ok", self.computer.click_text(label))

        m = re.search(r"\b(?:type|enter text|type out)\s+(.+)$", t)
        if m:
            return self._flavor("ok", self.computer.type_text(m.group(1).strip()))

        m = re.search(
            r"\b(?:press|hit)\s+((?:ctrl|control|alt|shift|win|cmd)(?:\s*\+\s*|\s+)[\w]+(?:\s*\+\s*[\w]+)?|enter|tab|escape|esc)\b",
            t,
        )
        if m:
            raw = m.group(1).lower().replace("control", "ctrl").replace("escape", "esc")
            keys = re.split(r"\s*\+\s*|\s+", raw)
            keys = [k for k in keys if k]
            return self._flavor("ok", self.computer.hotkey(*keys))

        if re.search(r"\b(scroll down|page down)\b", t):
            return self._flavor("ok", self.computer.scroll(-4))
        if re.search(r"\b(scroll up|page up)\b", t):
            return self._flavor("ok", self.computer.scroll(4))

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
        if re.search(r"\b(task status|background tasks|queue status)\b", t):
            return self._flavor("ok", self.tasks.status_line())
        if re.search(r"\b(home assistant status|ha status)\b", t):
            return self._flavor("ok", self.ha.status())
        m = re.search(r"\b(?:ha|home assistant)\s+(?:scene|activate)\s+(.+)$", t)
        if m:
            ent = m.group(1).strip()
            if not ent.startswith("scene."):
                ent = f"scene.{ent.replace(' ', '_').lower()}"
            return self._flavor("ok", self.ha.activate_scene(ent))
        m = re.search(r"\b(?:trigger|run) n8n\s+(\S+)\b", t)
        if m:
            path = m.group(1).strip()
            tid = self.tasks.submit(
                f"n8n:{path}",
                lambda p=path: self.n8n.trigger(p, {"source": "jarvis", "text": t}),
            )
            return self._flavor(
                "ok",
                f"Queued n8n workflow {path} in the background (task {tid}).",
            )
        if re.search(r"\b(voicemeeter|audio isolation|mic isolation)\b", t):
            from jarvis.core.audio_isolation import VOICEMEETER_SETUP

            self._emit("artifact", {"title": "AUDIO ISOLATION", "text": VOICEMEETER_SETUP})
            return self._flavor(
                "ok",
                "Audio isolation guide is on screen. Use mic_prefer for your headset.",
            )

        if re.search(r"\b(help|what can you do|commands|list commands)\b", t):
            return (
                f"At your service, {self.settings.user_name}. "
                "Smart: quiet mode · smooth mode · desk ready · full status · summarize my day · "
                "wake word only · always listen · suggestions off · upgrade status · upgrade check · recent errors. "
                "Travis: park · tactical · peer review. "
                "Workflows: morning · night · focus · secure. "
                "Security: enroll · intruder alerts off · secure desk. "
                "Phone: companion · ping my phone. "
                "Manus: ask manus · manus review. "
                "Computer use: computer use … · browser agent … · operator … · "
                "stop computer use · set anthropic/openai key. "
                "Cloud: integrations status · stripe status · notion search … · "
                "buffer channels · gmail inbox · link stripe / notion / buffer / gmail. "
                "Agents: ask sarah · ask tom · ask admin · hub status. "
                "Desk: camera · lock · screenshot · music · weather. "
                "Build: site · vibe · map · news · away. "
                "Say upgrade for hot reload. Full list stays punchy — ask for a category."
            )

        # Contextual "do that" via thought stream
        if re.search(r"\b(do that|actually wait|the other)\b", t):
            recent = self.voice.stream.recent()
            if len(recent) >= 2:
                return self._route(recent[-2])

        # Vague ask — only speak recalled facts when user explicitly asks
        if re.search(
            r"\b(what do you remember|from memory|recall( that)?|remind me about)\b",
            t,
        ):
            hint = getattr(self, "_memory_hint", "") or ""
            bullets = [
                ln[2:].strip() for ln in hint.splitlines() if ln.startswith("- ")
            ]
            if not bullets:
                try:
                    bullets = self.vstore.recall(t, n=3)
                except Exception:
                    bullets = []
            if bullets:
                return self._flavor("ok", "; ".join(bullets[:2]))
            return self._flavor("ok", "Nothing stored for that yet.")

        return self.persona.fallback()

    def _full_status_line(self) -> str:
        """One-line systems pack: desk · companion · manus · hub."""
        bits: list[str] = []
        try:
            tel = self.system.telemetry()
            bits.append(
                f"CPU {getattr(tel, 'cpu', 0):.0f}% · RAM {getattr(tel, 'memory', getattr(tel, 'ram', 0)):.0f}%"
            )
        except Exception:
            bits.append("systems nominal")
        try:
            if getattr(self, "security", None):
                bits.append(self.security.status())
        except Exception:
            pass
        try:
            bits.append(self.companion_status_line())
        except Exception:
            try:
                bits.append(self.phone.status())
            except Exception:
                pass
        try:
            manus = getattr(self, "manus", None)
            if manus is not None:
                bits.append(manus.status())
        except Exception:
            pass
        try:
            cu = getattr(self, "cu_agent", None)
            if cu is not None and getattr(cu.status, "running", False):
                bits.append(
                    f"CU {cu.status.provider} {cu.status.step}/{cu.status.max_steps}"
                )
        except Exception:
            pass
        try:
            if getattr(self.settings, "hub_enabled", True):
                h = self.hub.health()
                if h:
                    bits.append(f"Hub online · sessions {h.get('sessions')}")
                else:
                    bits.append("Hub offline")
        except Exception:
            bits.append("Hub unknown")
        if getattr(self, "_quiet_mode", False):
            bits.append("quiet mode on")
        line = " · ".join(b for b in bits if b)
        if len(line) > 420:
            line = line[:400].rsplit("·", 1)[0].strip(" ·") + "."
        return line

    def _summarize_my_day(self) -> str:
        parts: list[str] = []
        try:
            if getattr(self, "live", None):
                parts.append(self.live.briefing_prefix().rstrip("."))
        except Exception:
            pass
        try:
            wx = self.weather.speak_brief()
            if wx:
                parts.append(wx)
        except Exception:
            pass
        try:
            cal = self.brief.schedule_only()
            day = self.habits.tell_me_about_my_day(cal)
            if day:
                parts.append(day)
        except Exception:
            try:
                parts.append(self.brief.summarize(open_inbox=False))
            except Exception:
                pass
        if not parts:
            return "Nothing queued for today yet. Say good morning for a standup."
        return " ".join(parts)[:480]

    def _desk_ready(self) -> str:
        """Light focus prep — coding lights + mic live + short status."""
        notes: list[str] = []
        try:
            if getattr(self, "lights", None):
                notes.append(self.lights.set_mode("coding"))
        except Exception:
            pass
        try:
            self.voice.mute_mic(False)
            self.voice.set_busy(False)
        except Exception:
            pass
        if getattr(self, "_quiet_mode", False):
            try:
                notes.append(self._exit_quiet_mode())
            except Exception:
                pass
        self._emit("hud_alert", "DESK READY")
        core = "Desk ready — coding lights, mic live."
        if notes:
            core += " " + " ".join(str(n) for n in notes if n)[:120]
        return core

    def _enter_quiet_mode(self) -> str:
        self._quiet_mode = True
        try:
            self.voice.mute_mic(True)
        except Exception:
            pass
        try:
            if getattr(self, "security", None):
                self._quiet_saved_intruder = bool(self.security.intruder_alert)
                self.security.set_intruder_alert(False)
        except Exception:
            self._quiet_saved_intruder = None
        self._emit("hud_alert", "QUIET MODE")
        return "Quiet mode on — mic muted, intruder alerts silenced. Say loud mode to restore."

    def _exit_quiet_mode(self) -> str:
        self._quiet_mode = False
        try:
            self.voice.mute_mic(False)
            self.voice.set_busy(False)
        except Exception:
            pass
        try:
            if getattr(self, "security", None) and self._quiet_saved_intruder is not None:
                self.security.set_intruder_alert(bool(self._quiet_saved_intruder))
            self._quiet_saved_intruder = None
        except Exception:
            pass
        self._emit("hud_alert", "LIVE")
        return "Loud mode — mic live, alerts restored."

    def _summarize_clipboard(self) -> str:
        try:
            import pyperclip
        except Exception:
            return "Clipboard module not installed."
        try:
            clip = (pyperclip.paste() or "").strip()
        except Exception:
            return "Could not read the clipboard."
        if not clip:
            return "Clipboard is empty."
        # Soft summarize: first sentence / trim
        one = re.split(r"(?<=[.!?])\s+", clip, maxsplit=1)[0].strip()
        words = clip.split()
        if len(words) <= 28:
            preview = clip
        else:
            preview = " ".join(words[:28]) + "…"
        if one and len(one) < 160 and one != preview:
            return f"Clipboard ({len(words)} words): {one}"
        return f"Clipboard ({len(words)} words): {preview[:220]}"

    def _upgrade_status_line(self) -> str:
        try:
            if getattr(self, "registry", None):
                return self.registry.status()
        except Exception as e:
            return f"Registry unavailable: {e}"
        return "Feature registry offline."

    def _recent_errors_line(self) -> str:
        try:
            from jarvis.core.health_check import recent_errors_blurb

            return recent_errors_blurb()
        except Exception as e:
            return f"Could not read errors: {e}"

    def _upgrade_check_line(self) -> str:
        """Self-health: logs · computer-use readiness · integrations · wake."""
        try:
            from jarvis.core.health_check import build_upgrade_check
        except Exception as e:
            return f"Health check module unavailable: {e}"
        companion = ""
        manus_line = ""
        hub_line = ""
        security_line = ""
        try:
            companion = self.companion_status_line()
        except Exception:
            try:
                companion = self.phone.status()
            except Exception:
                pass
        try:
            manus = getattr(self, "manus", None)
            if manus is not None:
                manus_line = str(manus.status())
        except Exception:
            pass
        try:
            if getattr(self.settings, "hub_enabled", True):
                h = self.hub.health()
                hub_line = (
                    f"Hub online sessions {h.get('sessions')}"
                    if h
                    else "Hub offline"
                )
            else:
                hub_line = "Hub disabled"
        except Exception:
            hub_line = "Hub unknown"
        try:
            if getattr(self, "security", None):
                security_line = str(self.security.status())
        except Exception:
            pass
        cloud = getattr(self, "cloud", None)
        line = build_upgrade_check(
            settings=self.settings,
            cu_agent=getattr(self, "cu_agent", None),
            cloud=cloud,
            companion_line=companion,
            manus_line=manus_line,
            hub_line=hub_line,
            security_line=security_line,
        )
        try:
            self._emit(
                "artifact",
                {
                    "title": "UPGRADE CHECK",
                    "text": line
                    + "\n\nTips: computer use status · setup computer use · "
                    "integrations status · full status · upgrade status",
                },
            )
        except Exception:
            pass
        return line

    def apply_update_request(self, text: str) -> str:
        self.voice.mute_mic(False)
        self._emit("update_ui", False)
        # Persist as custom behavior + hot-load stub plugin
        note = self.instructions.append(text)
        plugin = self.updater.apply(text)
        msg = f"{note} {plugin}"
        if getattr(self.settings, "reload_after_update", True):
            self._emit("app_exit", 0)
            return (
                f"{msg} Compilation successful. Reloading environment layers."
            )
        return msg

    def _run_hot_upgrade(self) -> str:
        """Show upgrade loading UI and hot-refresh plugins + scripts to 100%."""
        try:
            if getattr(self, "registry", None):
                self.registry.freeze("upgrade")
                self._emit("command_ui", {"kind": "upgrade", "text": "registry frozen"})
                self._emit("registry_ui", {"frozen": True})
        except Exception as e:
            print(f"[upgrade] freeze: {e}")
        self._emit("upgrade_ui", "start")
        self._reactor_safe("build")
        try:
            self.habits.log("upgrade")
        except Exception:
            pass

        def _job() -> None:
            time.sleep(0.45)

            def on_progress(pct: int, phase: str, detail: str) -> None:
                self._emit(
                    "upgrade_ui",
                    {"pct": int(pct), "phase": phase, "detail": detail},
                )
                try:
                    self._emit(
                        "command_ui",
                        {
                            "kind": "upgrade",
                            "text": f"{pct}% {phase}",
                            "detail": detail[:60],
                        },
                    )
                except Exception:
                    pass

            try:
                msg = self.updater.hot_upgrade(progress=on_progress)
            except Exception as e:
                msg = f"Upgrade hit turbulence at the last gate: {e}"
                self._emit(
                    "upgrade_ui",
                    {"pct": 100, "phase": "COMPLETE", "detail": str(e)[:120]},
                )
            try:
                import importlib
                from jarvis.core import commands as cmd_mod

                importlib.reload(cmd_mod)
            except Exception:
                pass
            try:
                if getattr(self, "registry", None):
                    self.registry.unfreeze()
                    self._emit("registry_ui", {"frozen": False})
                    self._emit(
                        "command_ui",
                        {"kind": "upgrade", "text": "registry open · 100%"},
                    )
            except Exception as e:
                print(f"[upgrade] unfreeze: {e}")
            self._reactor_safe("idle")
            try:
                self.feed.push("upgrade", msg[:180])
            except Exception:
                pass
            time.sleep(0.8)
            self.say(msg)

        threading.Thread(target=_job, daemon=True, name="jarvis-upgrade").start()
        return "Upgrade sequence engaged. Registry frozen until 100 percent."

    def _route_workflow_step(self, cmd: str) -> str | None:
        """Execute one workflow step without re-entering utterance locks."""
        try:
            c = (cmd or "").lower().strip()
            if getattr(self, "registry", None) and not self.registry.allows(c):
                return self.registry.block_message()
            return self._route(c)
        except Exception as e:
            print(f"[workflow] step: {e}")
            return None

    def _run_workflow(self, name: str) -> str:
        if not getattr(self, "workflows", None):
            return "Workflow engine offline."
        self._emit("hud_alert", f"Workflow · {name}")
        self._reactor_safe("build")

        def _job() -> None:
            def progress(label: str, meta: dict) -> None:
                self._emit(
                    "command_ui",
                    {
                        "kind": "workflow",
                        "text": label,
                        "detail": f"{meta.get('index')}/{meta.get('total')}",
                    },
                )
                self._emit("hud_alert", f"Workflow · {label}")

            try:
                msg = self.workflows.run(name, progress=progress)
            except Exception as e:
                msg = f"Workflow failed: {e}"
            self._reactor_safe("idle")
            self.say(msg)

        threading.Thread(
            target=_job, daemon=True, name=f"workflow-{name}"
        ).start()
        return f"Starting {name} workflow."

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
        open_browser = bool(getattr(self, "_scan_open_browser", False))
        self._scan_open_browser = False
        try:
            result = self.scanner.scan_frame(
                frame,
                ocr=ocr,
                open_browser=open_browser,
                identify=self.activity.identify_item,
            )
            query = result.get("query") or "unknown item"
            detail = (result.get("description") or result.get("reply") or "").strip()
            spoken = self.persona.scan_line(query)
            full = f"{spoken} {detail}".strip()
            if open_browser:
                full = f"{full} Opening Google Lens.".strip()
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

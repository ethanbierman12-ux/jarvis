"""Jarvis brain — intent routing, bonded to UI callbacks."""

from __future__ import annotations

import re
import json
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
from jarvis.core.rgb_peripherals import RgbPeripherals
from jarvis.core.alexa_lamp import AlexaLamp
from jarvis.core.phone_bridge import PhoneBridge
from jarvis.core.rlhf import RLHFEngine
from jarvis.core.soundscape import Soundscape
from jarvis.core.scanner_radio import ScannerRadio
from jarvis.core.danger_watch import DangerWatch
from jarvis.core.local_customizer import LocalCustomizer
from jarvis.core.diary import Diary, VisualMemory
from jarvis.core.memory import VectorMemory
from jarvis.core.pinecone_memory import PineconeMemory
from jarvis.core.live_voice import LiveVoiceBridge
from jarvis.core.audio_devices import AudioRouter
from jarvis.core.home_assistant import HomeAssistant
from jarvis.core.macro_gateway import MacroGateway
from jarvis.core.doorbell_bridge import DoorbellBridge
from jarvis.core.snapchat_calls import SnapchatCallBridge, SnapCallEvent
from jarvis.core.comms_live import CommsLiveBridge, CommsEvent
from jarvis.core.healer import PcHealer
from jarvis.core.scaffolder import ProjectScaffolder
from jarvis.core import app_scores
from jarvis.core.progress_report import ProgressReport
from jarvis.core.personality_forge import PersonalityForge
from jarvis.core.cognitive import CognitiveCore
from jarvis.core.briefing_protocols import BriefingProtocols
from jarvis.core.protocols import ProtocolEngine
from jarvis.core.workshop import WorkshopInventory
from jarvis.core.package_tracker import PackageTracker
from jarvis.core.advanced_ai import AdvancedAIPack
from jarvis.core.cron_jobs import CronRegistry
from jarvis.core.reminders import ReminderService, Reminder
from jarvis.core.memory_consolidate import MemoryConsolidator
from jarvis.core.clipboard_insight import ClipboardInsight
from jarvis.core.iot_bridge import IoTBridge
from jarvis.core.ambiguity import classify_ambiguity, resolve_option
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
from jarvis.core.home_security import HomeSecurity
from jarvis.core.file_hub import FileHub
from jarvis.core.alert_desk import AlertDesk
from jarvis.core.driver_dispatch import DriverDispatch
from jarvis.core.ops_hud import OpsHud
from jarvis.core.traffic_cams import TrafficCams
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
        self.rgb = RgbPeripherals(
            enabled=bool(getattr(settings, "openrgb_enabled", True)),
            host=getattr(settings, "openrgb_host", "") or "127.0.0.1",
            port=int(getattr(settings, "openrgb_port", 6742) or 6742),
            openrgb_path=getattr(settings, "openrgb_path", "") or "",
        )
        self.soundscape = Soundscape()
        self.scanner_radio = ScannerRadio(
            city=getattr(settings, "city", "") or "Philadelphia",
            feed_url=getattr(settings, "scanner_feed_url", "") or "",
            feed_id=getattr(settings, "scanner_feed_id", "") or "",
            rtl_freq=getattr(settings, "scanner_rtl_freq", "") or "",
        )
        self.danger_watch = None
        try:
            self.danger_watch = DangerWatch(
                enabled=bool(getattr(settings, "danger_watch_enabled", False)),
                sensitivity=float(
                    getattr(settings, "danger_watch_sensitivity", 1.0) or 1.0
                ),
                cooldown_sec=float(
                    getattr(settings, "danger_watch_cooldown_sec", 60.0) or 60.0
                ),
                mic_prefer=str(getattr(settings, "mic_prefer", "") or "auto"),
                on_alert=self._on_danger_alert,
            )
            if getattr(settings, "danger_watch_enabled", False):
                try:
                    threading.Timer(2.5, self.danger_watch.start).start()
                except Exception:
                    pass
        except Exception as e:
            print(f"[danger_watch] init: {e}")
            self.danger_watch = None
        self.diary = Diary()
        self.vmemory = VisualMemory()
        self.pinecone = PineconeMemory(
            getattr(settings, "pinecone_api_key", "") or "",
            index_host=getattr(settings, "pinecone_index_host", "") or "",
            namespace=getattr(settings, "pinecone_namespace", "") or "jarvis",
        )
        self.vstore = VectorMemory(pinecone=self.pinecone)
        self.live_voice = LiveVoiceBridge(
            elevenlabs_api_key=getattr(settings, "elevenlabs_api_key", "") or "",
            elevenlabs_voice_id=getattr(settings, "elevenlabs_voice_id", "") or "",
            elevenlabs_model=getattr(settings, "elevenlabs_model", "")
            or "eleven_turbo_v2_5",
            livekit_url=getattr(settings, "livekit_url", "") or "",
            livekit_api_key=getattr(settings, "livekit_api_key", "") or "",
            livekit_api_secret=getattr(settings, "livekit_api_secret", "") or "",
        )
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
        door_topic = (getattr(settings, "doorbell_ntfy_topic", "") or "").strip()
        if not door_topic and bool(getattr(settings, "doorbell_ntfy_enabled", True)):
            door_topic = DoorbellBridge.make_topic()
            try:
                self.settings.doorbell_ntfy_topic = door_topic
                self.settings.save()
            except Exception:
                pass
        self.doorbell = DoorbellBridge(
            topic=door_topic,
            server=getattr(settings, "doorbell_ntfy_server", "") or "https://ntfy.sh",
            enabled=bool(getattr(settings, "doorbell_ntfy_enabled", True)),
            on_event=self.handle_doorbell,
        )
        snap_topic = (getattr(settings, "snapchat_ntfy_topic", "") or "").strip()
        self.snapchat = SnapchatCallBridge(
            enabled=bool(getattr(settings, "snapchat_calls_enabled", True)),
            auto_answer=bool(getattr(settings, "snapchat_auto_answer", True)),
            poll_sec=float(getattr(settings, "snapchat_poll_sec", 1.25) or 1.25),
            cooldown_sec=float(
                getattr(settings, "snapchat_cooldown_sec", 25.0) or 25.0
            ),
            ntfy_topic=snap_topic,
            ntfy_server=getattr(settings, "snapchat_ntfy_server", "") or "https://ntfy.sh",
            on_call=self.handle_snapchat_call,
        )
        apps = tuple(
            str(a).lower()
            for a in (getattr(settings, "comms_live_apps", None) or [])
            if str(a).strip()
        ) or ("snapchat", "instagram", "imessage")
        self.comms_live = CommsLiveBridge(
            enabled=bool(getattr(settings, "comms_live_enabled", True)),
            translate=bool(getattr(settings, "comms_live_translate", True)),
            target_lang=str(getattr(settings, "comms_live_target_lang", "en") or "en"),
            speak_messages=bool(getattr(settings, "comms_live_speak", True)),
            poll_sec=float(getattr(settings, "comms_live_poll_sec", 1.5) or 1.5),
            apps=apps,
            on_event=self.handle_comms_live,
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
                gmail_refresh_token=getattr(settings, "gmail_refresh_token", "") or "",
                gmail_client_id=getattr(settings, "gmail_client_id", "") or "",
                gmail_client_secret=getattr(settings, "gmail_client_secret", "") or "",
            )
        except Exception:
            self.cloud = CloudIntegrations()
        # Vault may hold tokens while settings.json fields are empty — always re-merge
        try:
            self._refresh_cloud_tokens()
        except Exception:
            pass
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
        try:
            from jarvis.core.gaze_workspace import GazeWorkspace

            self.gaze_ws = GazeWorkspace(
                enabled=bool(getattr(settings, "gaze_workspace_enabled", True)),
                up_dwell_sec=float(getattr(settings, "gaze_up_dwell_sec", 3) or 3),
                left_dwell_sec=float(getattr(settings, "gaze_left_dwell_sec", 2) or 2),
                on_look_up=lambda: self._emit("gaze_look_up", True),
                on_look_left_scroll=lambda: self._emit("gaze_scroll_tools", True),
                on_look_center=lambda: self._emit("gaze_look_center", True),
                on_zone=lambda ev: self._emit(
                    "gaze_zone",
                    {"zone": ev.zone, "dwell": round(ev.dwell_sec, 1)},
                ),
            )
            self.context.gaze = self.gaze_ws
        except Exception as e:
            print(f"[gaze] init: {e}")
            self.gaze_ws = None
        self.game_focus = GameFocusWatch(
            on_enter=self._on_game_focus,
            on_leave=self._on_game_unfocus,
        )
        self.prefetcher = Prefetcher(apps_launcher=self.apps)
        self.spend = SpendTracker()
        self.feed = DataFeed()
        self.steward = AwaySteward()
        self.away_agent = AwayAgent()
        self.progress = ProgressReport(
            spend=self.spend,
            habits=self.habits,
            brief=self.brief,
            steward=self.steward,
            cloud=getattr(self, "cloud", None),
        )
        self.forge = PersonalityForge()
        self.cognitive = CognitiveCore("executive")
        self.workshop = WorkshopInventory()
        self.packages = PackageTracker()
        self.protocols = ProtocolEngine(
            settings=settings,
            apps=self.apps,
            lamp=getattr(self, "lamp", None),
            system=self.system,
        )
        self.briefings = BriefingProtocols(
            brief=self.brief,
            spend=self.spend,
            habits=self.habits,
            news_fn=lambda: (
                self.topics.headlines("tech", limit=2)
                if getattr(self, "topics", None)
                else ""
            ),
            mail_fn=lambda: (
                self.cloud.gmail_inbox(3)
                if getattr(self, "cloud", None)
                and getattr(self.cloud, "gmail_access_token", "")
                else ""
            ),
        )
        self.cron = CronRegistry(on_report=self._cron_report)
        self._wire_cron_handlers()
        self.reminders = ReminderService(
            default_tz=getattr(settings, "timezone", "America/New_York")
            or "America/New_York",
            on_fire=self.handle_reminder_fire,
        )
        try:
            from jarvis.core.net_watch import NetWatch
            from jarvis.core.secure_backup import SecureBackup
            from jarvis.core.space_weather import SpaceWeather
            from jarvis.core.deadman import DeadmanSwitch
            from jarvis.core.process_harden import ProcessHarden

            self.backups = SecureBackup()
            self.process_harden = ProcessHarden()
            self.space_weather = SpaceWeather(
                on_severe=lambda msg: self._on_space_severe(msg),
            )
            self.deadman = DeadmanSwitch(
                enabled=bool(getattr(settings, "deadman_enabled", False)),
                phrase=str(getattr(settings, "deadman_phrase", "jarvis clear") or "jarvis clear"),
                interval_sec=float(getattr(settings, "deadman_hours", 24) or 24) * 3600.0,
                on_miss=lambda msg: self._on_deadman_miss(msg),
            )
            self.net_watch = NetWatch(
                enabled=bool(getattr(settings, "net_watch_enabled", True)),
                poll_sec=float(getattr(settings, "net_watch_poll_sec", 45) or 45),
                on_alert=lambda msg, _d: self._on_net_intruder(msg),
            )
        except Exception as e:
            print(f"[home-ops] init: {e}")
            self.backups = None
            self.process_harden = None
            self.space_weather = None
            self.deadman = None
            self.net_watch = None
        try:
            from jarvis.core.software_security import SoftwareSecurity

            self.software_security = SoftwareSecurity(
                enabled=bool(getattr(settings, "software_security_enabled", True)),
                process_harden=getattr(self, "process_harden", None),
                on_alert=lambda msg: self._on_software_security_alert(msg),
            )
        except Exception as e:
            print(f"[software-security] init: {e}")
            self.software_security = None
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
        self.local_code = LocalCustomizer(
            project_path=getattr(settings, "work_project_path", "") or "",
            ide=getattr(settings, "work_ide", "") or "code",
            last_project_fn=lambda: getattr(self.vibe, "last_project", None),
        )
        self.net = InternetAgent()
        # Agent crew — heavy; start deferred so HUD/voice come up first
        self.crew = None
        self.work_crew = None
        self.auto_loop = None
        self.systems_v2 = None
        self._crew_boot_started = False
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
        self._thermal_assist = bool(getattr(settings, "thermal_assist", False))
        self.home_security = None
        self.file_hub = None
        self.alert_desk = None
        self.driver_dispatch = None
        self.ops_hud = None
        self._ops_hud_on = False
        self.traffic_cams = None
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
            pitch=getattr(settings, "tts_pitch", "-2Hz"),
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
            chunk_sentences=bool(getattr(settings, "tts_chunk_sentences", True)),
        )
        try:
            from jarvis.core.voice_clone import VoiceCloneLab

            self.voice_clone = VoiceCloneLab(
                voice_engine=self.voice,
                settings=settings,
                on_status=lambda m: self._emit("heard", f"[clone] {m}"),
                on_ui=lambda d: self._emit("voice_clone_ui", d),
                duck_media=lambda: getattr(self.voice, "on_before_tts", lambda: None)(),
                unduck_media=lambda: getattr(self.voice, "on_after_tts", lambda: None)(),
            )
            eng = str(getattr(settings, "voice_clone_engine", "auto") or "auto")
            if eng and eng != "auto":
                self.voice_clone.set_engine(eng)
        except Exception as e:
            print(f"[voice-clone] init: {e}")
            self.voice_clone = None
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
            self.persona._cognitive = self.cognitive  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self.advanced = AdvancedAIPack(self)
            if bool(getattr(settings, "guest_mode_default", False)):
                self.advanced.guest.enable()
        except Exception as e:
            print(f"[advanced_ai] init: {e}")
            self.advanced = None  # type: ignore[assignment]
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
                self.home_security = HomeSecurity(
                    DATA_DIR,
                    log_enabled=bool(getattr(settings, "home_security_log", True)),
                    phone_photo=bool(
                        getattr(settings, "home_security_phone_photo", True)
                    ),
                )
                self.home_security.thermal_assist = bool(
                    getattr(settings, "thermal_assist", False)
                )
                self._thermal_assist = bool(self.home_security.thermal_assist)
                if self._thermal_assist:
                    try:
                        threading.Timer(
                            3.0, lambda: self._emit("thermal_assist", True)
                        ).start()
                    except Exception:
                        pass
            except Exception as e:
                print(f"[home_security] init: {e}")
                self.home_security = None
            try:
                self.file_hub = FileHub(
                    data_dir=DATA_DIR,
                    project_root=ROOT,
                    enabled=bool(getattr(settings, "file_hub_enabled", True)),
                    extra_roots=list(getattr(settings, "file_hub_roots", None) or []),
                )
            except Exception as e:
                print(f"[file_hub] init: {e}")
                self.file_hub = None
            try:
                self.alert_desk = AlertDesk(
                    data_dir=DATA_DIR,
                    phone=self.phone,
                    home_security=self.home_security,
                    on_hud=lambda t: self._emit("hud_alert", t),
                    guest_check=lambda: bool(
                        getattr(getattr(self, "advanced", None), "guest", None)
                        and getattr(self.advanced.guest, "on", False)
                    ),
                    enabled=bool(getattr(settings, "alert_desk_enabled", True)),
                )
            except Exception as e:
                print(f"[alert_desk] init: {e}")
                self.alert_desk = None
            try:
                self.driver_dispatch = DriverDispatch(
                    phone=self.phone,
                    alert_desk=self.alert_desk,
                    on_hud=lambda t: self._emit("hud_alert", t),
                )
            except Exception as e:
                print(f"[driver_dispatch] init: {e}")
                self.driver_dispatch = None
            try:
                self.ops_hud = OpsHud(
                    data_dir=DATA_DIR,
                    settings=settings,
                    home_security=self.home_security,
                    enabled=bool(getattr(settings, "ops_hud_enabled", True)),
                )
            except Exception as e:
                print(f"[ops_hud] init: {e}")
                self.ops_hud = None
            try:
                self.traffic_cams = TrafficCams(
                    data_dir=DATA_DIR,
                    settings=settings,
                    city=str(
                        getattr(settings, "traffic_cams_city", None)
                        or getattr(settings, "city", None)
                        or "Philadelphia"
                    ),
                    enabled=bool(getattr(settings, "traffic_cams_enabled", True)),
                )
            except Exception as e:
                print(f"[traffic_cams] init: {e}")
                self.traffic_cams = None
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
                self.healer = PcHealer()
                self.scaffolder = ProjectScaffolder(
                    getattr(settings, "scaffold_root", "") or None
                )
                self.memory_night = MemoryConsolidator(self.vstore)
                self.iot = IoTBridge(
                    on_event=lambda kind, data: self._on_iot_event(kind, data),
                    serial_port=getattr(settings, "iot_serial_port", "") or "",
                    serial_baud=int(getattr(settings, "iot_serial_baud", 115200) or 115200),
                )
                self.proactive = ProactiveAgent(
                    telemetry_fn=lambda: self.system.telemetry(),
                    on_say=lambda t: self.say(t),
                    on_alert=lambda t: self._emit("hud_alert", t),
                    on_healer=lambda hog: self._on_healer_prompt(hog),
                    on_writing_break=lambda: self._on_writing_break(),
                    mood=self.mood,
                    healer=self.healer,
                )
                self.proactive.set_enabled(
                    bool(getattr(settings, "proactive_enabled", True))
                )
                if bool(getattr(settings, "clipboard_insight_enabled", True)):
                    self.clip_insight = ClipboardInsight(
                        on_error=lambda snip: self._on_clipboard_error(snip),
                        enabled=True,
                    )
                    self.clip_insight.start()
                else:
                    self.clip_insight = None
            except Exception as e:
                print(f"[proactive] init: {e}")
                self.healer = None
                self.scaffolder = None
                self.memory_night = None
                self.iot = None
                self.clip_insight = None
            try:
                if bool(getattr(settings, "whisper_mode", False)) and getattr(
                    self, "voice", None
                ):
                    self.voice.set_whisper_mode(
                        True,
                        volume=str(
                            getattr(settings, "whisper_volume", "-20%") or "-20%"
                        ),
                    )
            except Exception:
                pass
            try:
                self.registry.register("live_context", version="1.0", note="Date/weather ground truth")
                self.registry.register("proactive", version="1.0", note="CPU/late/idle nudges")
                self.registry.register("healer", version="1.0", note="CPU hog intervene")
                self.registry.register("scaffolder", version="1.0", note="React/Python/HTML scaffolds")
                self.registry.register("ambiguity", version="1.0", note="Multi-choice clarify")
                self.registry.register("iot_bridge", version="1.0", note="Room/NFC/mirror hooks")
                self.registry.register("github_autocommit", version="1.0", note="AI-ish commit+push")
                self.registry.register("smart_calendar", version="1.0", note="Spoken schedule → ICS")
                self.registry.register("security_gate", version="1.0", note="Face greet + intruder")
                self.registry.register(
                    "home_security",
                    version="1.0",
                    note="Home desk: encrypted log, intrusion snaps, thermal assist, phone photo",
                )
                self.registry.register(
                    "file_hub",
                    version="1.0",
                    note="Voice file search/open across Documents/Desktop/Downloads/DATA_DIR",
                )
                self.registry.register(
                    "alert_desk",
                    version="1.0",
                    note="HUD + phone blast / secure+intruder blast / encrypted desk notes",
                )
                self.registry.register(
                    "driver_dispatch",
                    version="1.0",
                    note="Owner ntfy driver notes (not fleet radio)",
                )
                self.registry.register(
                    "ops_hud",
                    version="1.0",
                    note="Owner-site map pins + home security event dots (no stranger targets)",
                )
                self.registry.register(
                    "traffic_cams",
                    version="1.0",
                    note="Public PennDOT/511PA traffic stills for owner city (no private CCTV)",
                )
                self.registry.register(
                    "scanner_radio",
                    version="1.2",
                    note="Broadcastify/LiveATC + NOAA weather/satellite radio (not cam mics)",
                )
                self.registry.register(
                    "danger_watch",
                    version="1.0",
                    note="Opt-in local desk mic impulse/bang watch (not CCTV audio)",
                )
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
                self.registry.register(
                    "net_watch",
                    version="1.1",
                    note="LAN ARP unknown-MAC alerts + owner-LAN cam-port presence",
                )
                self.registry.register(
                    "software_security",
                    version="1.0",
                    note="Defender status / quick scan + process harden (defensive)",
                )
                self.registry.register(
                    "secure_backup",
                    version="1.0",
                    note="Local encrypted zip backups + prune",
                )
                self.registry.register(
                    "deadman",
                    version="1.0",
                    note="Verbal handshake lockdown / backup on miss",
                )
                self.registry.register(
                    "space_weather",
                    version="1.0",
                    note="NOAA SWPC + ISS overhead",
                )
                self.registry.register(
                    "gaze_workspace",
                    version="1.0",
                    note="Look-up deck detail · look-left scroll · throw-up · posture",
                )
                self.registry.register(
                    "voice_clone",
                    version="1.0",
                    note="Room grab · denoise · F5/XTTS/SoVITS/ElevenLabs engines",
                )
                self.registry.register(
                    "process_harden",
                    version="1.0",
                    note="Background process scan + Chris Titus guide (HITL)",
                )
                self.registry.register(
                    "edge_node",
                    version="1.0",
                    note="Jetson / home-server headless daemon",
                )
                self.registry.register(
                    "slang_translate",
                    version="1.0",
                    note="EN↔ES casual + acronym expand",
                )
                self.registry.register(
                    "systems_ai_v2",
                    version="2.0",
                    note="SWE-bench · Cloud Agent · LangGraph · OpenAI Agents sandbox · "
                    "Mistweb/Tick · Pydad · Agno Type-C · LlamaIndex Workflow RAG",
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
        # Iconic boot: Daddy's home → Jarvis speaks → Stark workshop music
        if bool(getattr(self.settings, "stark_arrival_boot", True)):
            self._emit("speak_ui", "Daddy's home.")
            self._emit("hud_alert", "DADDY'S HOME")
            # Wait for voice/duplex to settle — do not block first paint
            threading.Timer(1.8, self._run_stark_arrival).start()
        else:
            welcome = "Welcome home, Sir. All systems are online."
            try:
                welcome = self.persona.boot_welcome()
            except Exception:
                pass
            self._emit("speak_ui", welcome)
            self._emit("hud_alert", welcome)
            threading.Timer(0.05, lambda w=welcome: self.say(w)).start()
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
            if bool(getattr(self.settings, "performance_mode", False)) or bool(
                getattr(self.settings, "zero_latency", True)
            ):
                threading.Timer(
                    0.35, lambda: self._set_performance_mode(True)
                ).start()
                threading.Timer(0.2, self._apply_zero_latency).start()
        except Exception:
            pass
        # Heavy agents after voice is live
        threading.Timer(1.2, self._boot_heavy_agents).start()
        threading.Timer(0.4, self._wake_command_center).start()
        threading.Timer(3.2, self._morning_weather_nudge).start()
        # Background micro-agents (sys monitor / horizon / packages)
        try:
            if getattr(self, "cron", None):
                # Refresh lamp handle if it was created later
                try:
                    self.protocols.lamp = getattr(self, "lamp", None)
                except Exception:
                    pass
                self.cron.start()
        except Exception as e:
            print(f"[cron] {e}")
        try:
            if getattr(self, "reminders", None):
                self.reminders.start()
        except Exception as e:
            print(f"[reminders] {e}")
        try:
            if getattr(self, "net_watch", None):
                self.net_watch.start()
            if getattr(self, "software_security", None):
                try:
                    self.software_security.start()
                except Exception as e:
                    print(f"[software-security] start: {e}")
        except Exception as e:
            print(f"[net-watch] {e}")
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
        # Silent Stream Deck / macro pad (LAN-open for Home Assistant Ring)
        if getattr(self.settings, "macro_gateway_enabled", True):
            try:
                self.macro = MacroGateway(
                    self.handle_macro,
                    host=str(
                        getattr(self.settings, "macro_gateway_host", "0.0.0.0")
                        or "0.0.0.0"
                    ),
                    port=int(getattr(self.settings, "macro_gateway_port", 8765) or 8765),
                    token=str(getattr(self.settings, "macro_gateway_token", "") or ""),
                )
                self.macro.start()
            except Exception as e:
                print(f"[macro] {e}")
        # Alexa / IFTTT doorbell via ntfy (no inbound ports)
        try:
            if getattr(self, "doorbell", None):
                self.doorbell.start()
        except Exception as e:
            print(f"[doorbell] {e}")
        # Snapchat / Phone Link incoming calls
        try:
            if getattr(self, "snapchat", None):
                self.snapchat.start()
        except Exception as e:
            print(f"[snapchat] {e}")
        # Live Snap / IG / iMessage read + translate
        try:
            if getattr(self, "comms_live", None):
                self.comms_live.start()
        except Exception as e:
            print(f"[comms] {e}")
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

    def _run_stark_arrival(self) -> None:
        """Daddy's home → Jarvis → research tabs → Shoot to Thrill + Play → help."""
        from jarvis.core.stark_arrival import run_stark_arrival

        def _sfx() -> None:
            try:
                from jarvis.ui.hud_sfx import play_whoosh

                play_whoosh()
            except Exception:
                pass

        def _say(text: str) -> None:
            try:
                self._emit("speak_ui", text)
                self._emit("speak", text)
            except Exception:
                pass
            try:
                self.voice.say_wait(text, polish=False)
            except Exception:
                try:
                    self.voice.say(text)
                    time.sleep(max(1.2, len(text.split()) * 0.28))
                except Exception as e:
                    print(f"[stark-arrival] speak: {e}")

        def _play() -> str:
            try:
                return self.music.play_shoot_to_thrill()
            except Exception as e:
                print(f"[stark-arrival] music: {e}")
                return f"Shoot to Thrill failed: {e}"

        def _press() -> str:
            # Media Play only — music.press_play() reloads the track and can
            # skip the start; play_shoot_to_thrill already seeks to 0:00.
            try:
                return self.music.press_play_key()
            except Exception as e:
                return str(e)

        # Never run on the Qt main thread — Spotify focus can stall the HUD
        threading.Thread(
            target=lambda: run_stark_arrival(
                say_wait=_say,
                play_music=_play,
                press_play=_press,
                open_research=self._arrival_open_research,
                help_brief=self._arrival_help_brief,
                on_status=lambda m: self.feed.push("arrival", m[:160]),
                on_hud=lambda m: self._emit("hud_alert", m[:80]),
                on_track=lambda t: self._emit("track", t),
                play_sfx=_sfx,
                user_name=getattr(self.settings, "user_name", "Sir") or "Sir",
                play_music_enabled=bool(
                    getattr(self.settings, "stark_arrival_music", True)
                ),
            ),
            daemon=True,
            name="stark-arrival",
        ).start()

    def _arrival_open_research(self) -> str:
        """Open research + work tabs on the tools / secondary screen."""
        urls = [
            "https://www.youtube.com",
            "https://www.perplexity.ai",
            "https://news.google.com",
            "https://scholar.google.com",
            "https://www.google.com/search?q=AI+research+news+today",
        ]
        for u in list(getattr(self.settings, "work_urls", None) or []):
            if u and u not in urls:
                urls.append(u)
        prefer: str | int = "secondary"
        try:
            from jarvis.core.displays import displays

            screens = displays.refresh()
            if len(screens) < 2:
                prefer = "primary"
            elif len(screens) >= 3:
                prefer = "left"
        except Exception:
            prefer = "primary"

        def _job() -> None:
            try:
                from jarvis.core.displays import displays

                msg = displays.open_urls(urls, prefer, activate=True)
                self._emit("hud_alert", "Research tabs ready")
                self.feed.push("arrival", msg[:160])
            except Exception as e:
                print(f"[arrival] research tabs: {e}")

        threading.Thread(target=_job, daemon=True, name="arrival-tabs").start()
        return "Opening research tabs now."

    def _arrival_help_brief(self) -> str:
        """Short helpful brief after arrival music starts."""
        parts: list[str] = []
        try:
            wx = self.weather.speak_brief()
            if wx:
                parts.append(str(wx)[:160])
        except Exception:
            pass
        try:
            if getattr(self, "wake_brief", None):
                packet = self.wake_brief.compose(mode="wake")
                spoken = ""
                if isinstance(packet, dict):
                    spoken = str(packet.get("spoken") or packet.get("text") or "")
                if spoken:
                    parts.append(spoken[:220])
        except Exception:
            pass
        try:
            cal = self.brief.schedule_only()
            day = self.habits.tell_me_about_my_day(cal) if cal else ""
            if day:
                parts.append(str(day)[:180])
        except Exception:
            pass
        if not parts:
            return (
                "I'm ready to help — ask me to research anything, "
                "run a crew task, or open your project."
            )
        return "Here's your brief. " + " ".join(parts)[:360]

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

    def set_thermal_assist(self, on: bool, announce: bool = False) -> str:
        """Toggle software false-color thermal assist (own webcam only — not FLIR)."""
        on = bool(on)
        was = bool(getattr(self, "_thermal_assist", False))
        self._thermal_assist = on
        try:
            if getattr(self, "home_security", None):
                self.home_security.thermal_assist = on
        except Exception:
            pass
        try:
            self.settings.thermal_assist = on
            self.settings.save()
        except Exception:
            pass
        self._emit("thermal_assist", on)
        if on and not was:
            msg = "Thermal assist on — software false-color from your cam, not real FLIR."
            self._emit("speak_ui", msg)
            self._emit("hud_alert", "THERMAL ASSIST ONLINE")
            self._emit("heard", "[optics] thermal assist online")
            if announce:
                self.say(msg)
            return msg
        if not on and was:
            msg = "Thermal assist offline."
            self._emit("speak_ui", msg)
            self._emit("hud_alert", "THERMAL ASSIST OFF")
            self._emit("heard", "[optics] thermal assist offline")
            if announce:
                self.say(msg)
            return msg
        return "Thermal assist already on." if on else "Thermal assist already off."

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
            try:
                if (
                    getattr(self, "home_security", None)
                    and "enrolled" in msg.lower()
                    and "failed" not in msg.lower()
                ):
                    self.home_security.log_event("enroll", msg)
            except Exception:
                pass
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
            try:
                if (
                    getattr(self, "home_security", None)
                    and "enrolled" in msg.lower()
                    and "failed" not in msg.lower()
                ):
                    self.home_security.log_event("enroll", msg)
            except Exception:
                pass
            self.say(msg)
        except Exception as e:
            self.say(f"Enroll failed: {e}")

    def _proactive_loop(self) -> None:
        try:
            # Writing-session detect via active window title
            if getattr(self, "proactive", None) and getattr(self, "screen", None):
                try:
                    title = (self.screen.active_window_title() or "").lower()
                    writing = any(
                        k in title
                        for k in (
                            "word",
                            "docs",
                            "notion",
                            "obsidian",
                            "notepad",
                            "onenote",
                            "google docs",
                            "typora",
                            "cursor",
                            "visual studio code",
                            "code.exe",
                        )
                    )
                    self.proactive.note_writing(writing)
                except Exception:
                    pass
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
            if getattr(self, "memory_night", None) and bool(
                getattr(self.settings, "memory_consolidate_enabled", True)
            ):
                msg = self.memory_night.maybe_nightly()
                if msg:
                    self._emit("hud_alert", "Memory consolidate")
                    self._emit("heard", f"[memory] {msg}")
        except Exception:
            pass
        try:
            dm = getattr(self, "deadman", None)
            if dm is not None:
                dm.tick()  # on_miss handles speak/lock; avoid double HUD spam
        except Exception:
            pass
        try:
            sw = getattr(self, "space_weather", None)
            if sw is not None:
                now = time.time()
                last = float(getattr(self, "_space_poll_ts", 0) or 0)
                if now - last > 600:
                    self._space_poll_ts = now
                    sw.poll_severe()
                # ISS overhead → command deck (every ~3 min)
                last_iss = float(getattr(self, "_iss_poll_ts", 0) or 0)
                if now - last_iss > 180:
                    self._iss_poll_ts = now
                    try:
                        from jarvis.core.satellite_track import fetch_iss

                        track = fetch_iss()
                        if track.get("ok") and track.get("over_home"):
                            fired = float(getattr(self, "_iss_deck_ts", 0) or 0)
                            if now - fired > 1800:
                                self._iss_deck_ts = now
                                self._emit("iss_deck", True)
                                self._emit("hud_alert", "ISS OVERHEAD")
                                summary = str(track.get("summary") or "ISS near overhead")
                                self.say(summary)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            # Quiet auto-backup on the HUD schedule (background thread)
            hours = float(getattr(self.settings, "auto_backup_hours", 0) or 0)
            if hours > 0 and getattr(self, "backups", None):
                now = time.time()
                last = float(getattr(self, "_auto_backup_ts", 0) or 0)
                if last <= 0:
                    self._auto_backup_ts = now
                elif now - last > max(3600.0, hours * 3600.0):
                    self._auto_backup_ts = now
                    self._run_backup_bg(label="auto")
        except Exception:
            pass
        try:
            threading.Timer(60.0, self._proactive_loop).start()
        except Exception:
            pass

    def _run_backup_bg(self, *, label: str = "auto") -> str:
        """Kick secure backup off the voice/UI thread."""
        b = getattr(self, "backups", None)
        if b is None:
            return "Backup module offline."

        def _job() -> None:
            try:
                msg = b.run(label=label)
                self._emit("heard", f"[backup] {msg}")
            except Exception as e:
                print(f"[backup] {e}")

        threading.Thread(target=_job, daemon=True, name=f"jarvis-backup-{label}").start()
        return f"Secure backup started ({label})."

    def _on_healer_prompt(self, hog) -> None:
        name = getattr(hog, "name", "process")
        cpu = float(getattr(hog, "cpu", 0) or 0)
        self._emit("hud_alert", f"HEALER · {name}")
        if not getattr(self, "hitl", None):
            self.say(
                f"{name} is using {cpu:.0f} percent CPU. "
                "Say healer kill or healer ignore."
            )
            return

        def _ask() -> None:
            try:
                res = self.hitl.ask_clarify(
                    title=f"{name} is freezing the system",
                    detail=f"CPU {cpu:.0f}% · pid {getattr(hog, 'pid', '?')}",
                    agent="healer",
                    options=[
                        f"Terminate {name}",
                        "Leave it alone",
                        "Show top processes",
                    ],
                )
                ans = (res.answer or "").strip()
                from jarvis.core.hitl import HitlDecision

                if res.decision in (HitlDecision.DENIED, HitlDecision.TIMEOUT):
                    self.healer.clear_pending()
                    self.say("Leaving it alone.")
                    return
                if ans.startswith("Terminate") or "terminate" in ans.lower():
                    msg = self.healer.kill_hog(hog)
                    self.say(msg)
                elif "Show" in ans or "top" in ans.lower():
                    self.say(self.healer.status())
                else:
                    self.healer.clear_pending()
                    self.say("Leaving it alone.")
            except Exception as e:
                print(f"[healer] hitl: {e}")

        threading.Thread(target=_ask, daemon=True, name="jarvis-healer-hitl").start()
        self.say(
            f"Sir, {name} is using {cpu:.0f} percent CPU. "
            "Choose on the HITL panel — terminate, leave it, or show processes."
        )

    def _on_writing_break(self) -> None:
        if not getattr(self, "hitl", None):
            self.say(
                "You've been writing for a while. "
                "Should I summarize your progress, or fetch a coffee update?"
            )
            return

        def _ask() -> None:
            try:
                res = self.hitl.ask_clarify(
                    title="Writing break?",
                    detail="You've been on documents for a while.",
                    agent="wellness",
                    options=[
                        "Summarize my progress",
                        "Coffee / stretch reminder",
                        "Keep working",
                    ],
                )
                ans = (res.answer or "").lower()
                if "summarize" in ans:
                    self.handle_utterance("summarize my progress")
                elif "coffee" in ans or "stretch" in ans:
                    self.say(
                        "Coffee window — stand, hydrate, five minutes. I'll hold the fort."
                    )
                else:
                    self.say("Very well — staying quiet.")
            except Exception as e:
                print(f"[wellness] {e}")

        threading.Thread(target=_ask, daemon=True, name="jarvis-writing-hitl").start()

    def _on_clipboard_error(self, snippet: str) -> None:
        self._emit("hud_alert", "CLIPBOARD · ERROR DETECTED")
        self._last_clip_error = snippet
        self.say(
            "You copied what looks like an error. "
            "Say fix clipboard error if you want me to diagnose it."
        )

    def _on_iot_event(self, kind: str, data: dict) -> None:
        try:
            self._emit("heard", f"[iot] {kind}: {data}")
            if kind == "room":
                self._emit("hud_alert", f"ROOM · {data.get('room', '')}".upper())
            elif kind == "nfc":
                self._emit("hud_alert", f"NFC · {data.get('tag', '')}".upper())
                msg = data.get("message") or ""
                if msg:
                    self.say(msg)
        except Exception:
            pass

    def _handle_security_event(self, ev) -> None:
        kind = getattr(ev, "kind", "")
        msg = getattr(ev, "message", "")
        snap = getattr(ev, "snapshot", "") or ""
        self._emit("heard", f"[security] {kind}: {msg}")
        hs = getattr(self, "home_security", None)
        if kind == "intruder":
            adv = getattr(self, "advanced", None)
            if adv is not None and getattr(adv.guest, "on", False):
                self._emit("hud_alert", "GUEST MODE · alert suppressed")
                self.say(
                    "Guest detected, Sir. Privileged macros stay locked — "
                    "do try not to let them break anything expensive."
                )
                return
            archived = None
            try:
                if hs is not None:
                    archived = hs.archive_intrusion(snap or None)
                    hs.log_event(
                        "intruder",
                        msg or "Intruder alert at your desk",
                        snapshot_path=str(archived or snap or ""),
                    )
            except Exception as e:
                print(f"[home_security] intruder archive/log: {e}")
            img_for_ui = str(archived) if archived else (snap or "")
            self._emit("hud_alert", "INTRUDER ALERT")
            self._emit("panic_ui", True)
            try:
                if img_for_ui:
                    self._emit("artifact", img_for_ui)
            except Exception:
                pass
            try:
                if hs is not None:
                    hs.notify_intrusion(
                        self.phone,
                        "Intruder alert at your desk",
                        image_path=archived or snap or None,
                    )
                else:
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
            try:
                if hs is not None:
                    hs.log_event("greet", msg or "Owner greeted")
            except Exception:
                pass
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
            try:
                if hs is not None:
                    hs.log_event("lock", msg or "Stepped away")
            except Exception:
                pass
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

    def _cron_report(self, msg: str) -> None:
        """Quiet micro-agent callback — HUD feed, speak only if notable."""
        if not msg:
            return
        try:
            self.feed.push("cron", msg[:200])
            self._emit("feed", self.feed.lines_for_ui(18))
            self._emit("hud_alert", msg[:80])
        except Exception:
            pass

    def _wire_cron_handlers(self) -> None:
        cron = getattr(self, "cron", None)
        if not cron:
            return

        def sys_monitor(job) -> str | None:
            try:
                import psutil

                cpu = psutil.cpu_percent(interval=0.15)
                ram = psutil.virtual_memory().percent
                if cpu >= 88 or ram >= 90:
                    return f"Systems watch: CPU {cpu:.0f}% · RAM {ram:.0f}% — pressure rising, Sir."
            except Exception:
                return None
            return None

        def horizon(job) -> str | None:
            try:
                if getattr(self, "topics", None):
                    return self.topics.latest_blurb()
            except Exception:
                return None
            return None

        def packages(job) -> str | None:
            try:
                pkgs = self.packages._load().get("packages") or []
                active = [p for p in pkgs if p.get("status") != "done"]
                if active:
                    return f"Shipment watch: {len(active)} active package(s) on the ledger."
            except Exception:
                return None
            return None

        cron.register_handler("sys_monitor", sys_monitor)
        cron.register_handler("horizon", horizon)
        cron.register_handler("packages", packages)

    def _icloud_mail(self):
        from jarvis.core.icloud_mail import IcloudMail

        return IcloudMail(
            getattr(self.settings, "icloud_email", "") or "",
            getattr(self.settings, "icloud_app_password", "") or "",
        )

    def _sync_cash_app_spend(self) -> str:
        """Prefer iCloud Mail (where Cash App receipts live), fall back to Gmail."""
        icloud = self._icloud_mail()
        if icloud.configured():
            return self.spend.sync_cash_app_from_icloud(icloud.fetch_cash_app)

        cloud = getattr(self, "cloud", None)
        if cloud and getattr(cloud, "gmail_access_token", ""):
            # Gmail is linked but Cash App is often on iCloud — hint that path
            line = self.spend.sync_cash_app_from_gmail(cloud.gmail_search_messages)
            if "No Cash App emails" in line:
                return (
                    line
                    + " Your Cash App mail is probably on iCloud — say link icloud mail."
                )
            return line

        return (
            "Cash App receipts need iCloud Mail. Say link icloud mail, "
            "set your Apple ID email and app-specific password, then sync cash app."
        )

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
                preview_url = ""
                try:
                    # Serve site folder over HTTP so CSS/JS work in PREVIEW tab
                    site_root = path.parent if path and path.is_file() else path
                    if site_root and getattr(self, "vibe", None):
                        preview_url = self.vibe.ensure_preview_url(site_root) or ""
                except Exception as e:
                    print(f"[site] preview serve: {e}")
                payload = {
                    "path": str(path) if path else "",
                    "brand": (self.sites.last_content or {}).get("brand") or "",
                    "prompt": self.sites.last_prompt or "",
                    "preview_url": preview_url,
                    "url": preview_url,
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
            "Understood. Opening Build Theater — Working, Coding, and Preview tabs live. "
            "Watch the agent plan, write files, run the terminal, and hot-reload the browser."
        )

    def _studio_open(self, url: str, label: str) -> str:
        """Open a creative-suite tool in the browser (or app URI)."""
        try:
            webbrowser.open(url)
        except Exception as e:
            return self._flavor("error", f"Could not open {label}: {e}")
        self.feed.push("studio", f"Opened {label}")
        return self._flavor("ok", f"Opening {label}.")

    def _open_obsidian(self, *, note: str = "") -> str:
        """Launch Obsidian (exe + vault path → URI → folder)."""
        import os
        import subprocess
        from pathlib import Path
        from urllib.parse import quote

        vault = (getattr(self.settings, "obsidian_vault_path", None) or "").strip()
        vault_name = (getattr(self.settings, "obsidian_vault_name", None) or "").strip()
        if vault and not vault_name:
            vault_name = Path(vault).name

        local = os.environ.get("LOCALAPPDATA", "")
        exe_candidates = []
        if local:
            exe_candidates = [
                Path(local) / "Programs" / "Obsidian" / "Obsidian.exe",
                Path(local) / "Programs" / "obsidian" / "Obsidian.exe",
                Path(local) / "Obsidian" / "Obsidian.exe",
            ]
        for exe in exe_candidates:
            if exe.is_file():
                try:
                    args = [str(exe)]
                    if vault and Path(vault).is_dir():
                        args.append(vault)
                    subprocess.Popen(args, shell=False)
                    self.feed.push("studio", "Opened Obsidian")
                    return self._flavor(
                        "ok",
                        f"Launching Obsidian"
                        + (f" — {vault_name}." if vault_name else "."),
                    )
                except Exception as e:
                    print(f"[obsidian] exe launch: {e}")

        # Deep link (works after vault is registered once)
        uri = "obsidian://open"
        if vault_name:
            uri = f"obsidian://open?vault={quote(vault_name)}"
            if note:
                uri += f"&file={quote(note)}"
        try:
            webbrowser.open(uri)
            self.feed.push("studio", "Opened Obsidian")
            if vault:
                return self._flavor(
                    "ok",
                    f"Opening Obsidian — vault {vault_name or vault}.",
                )
            return self._flavor("ok", "Opening Obsidian.")
        except Exception:
            pass

        if vault and Path(vault).is_dir():
            try:
                os.startfile(vault)  # type: ignore[attr-defined]
                return self._flavor("ok", f"Opening vault folder {vault_name or vault}.")
            except Exception:
                pass

        return self._flavor(
            "error",
            "Obsidian not found. Install it, or set obsidian vault to YOUR_PATH.",
        )

    def _obsidian_capture(self, title: str, body: str) -> str:
        """Write a markdown note into the configured Obsidian vault (Jarvis/ folder)."""
        from datetime import datetime
        from pathlib import Path

        vault = (getattr(self.settings, "obsidian_vault_path", None) or "").strip()
        if not vault:
            return ""
        root = Path(vault)
        if not root.is_dir():
            return ""
        dest = root / "Jarvis"
        try:
            dest.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w\s\-]+", "", title).strip()[:60] or "note"
            stamp = datetime.now().strftime("%Y%m%d-%H%M")
            path = dest / f"{stamp} {safe}.md"
            path.write_text(
                f"# {title}\n\n"
                f"_Captured by Jarvis · {datetime.now().isoformat(timespec='seconds')}_\n\n"
                f"{body.strip()}\n",
                encoding="utf-8",
            )
            return str(path)
        except Exception as e:
            print(f"[obsidian] capture failed: {e}")
            return ""

    def _studio_command(self, t: str) -> str | None:
        """STUDIO strip — Written/Claude/Obsidian/Video/Cling/Research/Perplexity/Design/Figma/Audio/11 Labs/Images/Mid-Journey/Automation/N8N."""
        # Exact / near-exact button cmds first
        exact = {
            "start written": "written",
            "open claude": "claude",
            "open clawed": "claude",
            "open obsidian": "obsidian",
            "make a video": "video",
            "open cling": "cling",
            "start research": "research",
            "open perplexity": "perplexity",
            "start design": "design",
            "open figma": "figma",
            "make audio": "audio",
            "open 11 labs": "eleven",
            "open eleven labs": "eleven",
            "make images": "images",
            "open mid journey": "midjourney",
            "open midjourney": "midjourney",
            "start automation": "automation",
            "open n8n": "n8n",
            # Web & desktop / game / asset frameworks
            "open arwes": "arwes",
            "open aui": "arwes",
            "open electron": "electron",
            "open dear pygui": "dearpygui",
            "open pygui": "dearpygui",
            "open godot": "godot",
            "open unreal": "unreal",
            "open unreal engine": "unreal",
            "open rainmeter": "rainmeter",
            "open envato": "envato",
            "open motion array": "motionarray",
        }
        key = exact.get(t.strip().lower())
        if not key:
            # Spoken variants
            if re.search(r"\b(start |open )?(written|writing mode|write for me)\b", t):
                key = "written"
            elif re.search(
                r"\b(open |launch )?(clawed|claude\.?ai|claude)\b", t
            ) and not re.search(r"\b(key|api|set)\b", t):
                key = "claude"
            elif re.search(r"\b(open |launch )?obsidian\b", t):
                key = "obsidian"
            elif re.search(r"\b(open |launch )?(cling|kling)\b", t):
                key = "cling"
            elif re.search(r"\b(open |launch )?perplexity\b", t):
                key = "perplexity"
            elif re.search(r"\b(open |launch )?figma\b", t):
                key = "figma"
            elif re.search(r"\b(open |launch )?(11 labs|eleven ?labs)\b", t):
                key = "eleven"
            elif re.search(r"\b(open |launch )?(mid[- ]?journey)\b", t):
                key = "midjourney"
            elif re.search(r"\b(open |launch )?n8n\b", t) and not re.search(
                r"\b(trigger|run)\b", t
            ):
                key = "n8n"
            elif re.search(r"\b(open |launch )?(arwes|aui)\b", t):
                key = "arwes"
            elif re.search(r"\b(open |launch )?electron\b", t):
                key = "electron"
            elif re.search(r"\b(open |launch )?(dear )?pygui\b", t):
                key = "dearpygui"
            elif re.search(r"\b(open |launch )?godot\b", t):
                key = "godot"
            elif re.search(r"\b(open |launch )?(unreal( engine)?|ue5)\b", t):
                key = "unreal"
            elif re.search(r"\b(open |launch )?rainmeter\b", t):
                key = "rainmeter"
            elif re.search(r"\b(open |launch )?envato\b", t):
                key = "envato"
            elif re.search(r"\b(open |launch )?motion ?array\b", t):
                key = "motionarray"
            elif re.search(r"\b(start |do |open )?research( mode)?\b", t) and re.fullmatch(
                r"(start |do |open )?research( mode)?", t.strip()
            ):
                # bare strip button only — don't steal "research the latest…"
                key = "research"
            elif re.search(r"\b(start |open )?design( mode)?\b", t):
                key = "design"
            elif re.search(r"\b(make|generate|create)\s+(me\s+)?(an?\s+)?audio\b", t):
                key = "audio"
            elif re.search(r"\b(make|generate|create)\s+(me\s+)?(an?\s+)?images?\b", t):
                key = "images"
            elif re.search(r"\b(start |open )?automation\b", t):
                key = "automation"
            else:
                return None

        frameworks = {
            "arwes": (
                "https://arwes.dev/",
                "Arwes UI — sci-fi React framework",
            ),
            "electron": (
                "https://www.electronjs.org/",
                "Electron — wrap web UI as desktop",
            ),
            "dearpygui": (
                "https://dearpygui.readthedocs.io/",
                "Dear PyGui — hardware-accelerated Python GUI",
            ),
            "godot": (
                "https://godotengine.org/",
                "Godot — lightweight 3D holographic engine",
            ),
            "unreal": (
                "https://www.unrealengine.com/en-US/unreal-engine-5",
                "Unreal Engine 5 — UMG / Niagara holograms",
            ),
            "rainmeter": (
                "https://www.rainmeter.net/",
                "Rainmeter — Iron Man / sci-fi desktop skins",
            ),
            "envato": (
                "https://elements.envato.com/search/sci-fi-hud",
                "Envato Elements — Sci-Fi HUD assets",
            ),
            "motionarray": (
                "https://motionarray.com/browse/stock-footage/?q=futuristic%20hud",
                "Motion Array — futuristic UI loops",
            ),
        }
        if key in frameworks:
            url, label = frameworks[key]
            self.habits.log("studio", key)
            return self._studio_open(url, label)
        if key == "written":
            self.habits.log("studio", "written")
            # Prefer Claude web for drafting when available; still open Build Theater editor
            try:
                webbrowser.open("https://claude.ai/new")
            except Exception:
                pass
            return self._flavor(
                "ok",
                self._run_vibe_code(
                    brief="written article editor with outline drafts export and tone controls"
                ),
            )
        if key == "claude":
            self.habits.log("studio", "claude")
            return self._studio_open("https://claude.ai/new", "Claude")
        if key == "obsidian":
            self.habits.log("studio", "obsidian")
            return self._open_obsidian()
        if key == "video":
            self.habits.log("studio", "video")
            return self._flavor(
                "ok",
                self._run_vibe_code(
                    brief="video slideshow reel with captions play pause and export"
                ),
            )
        if key == "cling":
            self.habits.log("studio", "cling")
            return self._studio_open("https://kling.ai/", "Cling · Kling video")
        if key == "research":
            self.habits.log("studio", "research")
            # Kick a live scholar pass on a useful default; voice can override next
            return self._flavor(
                "ok",
                self._start_research_job("latest AI tools for creators 2026"),
            )
        if key == "perplexity":
            self.habits.log("studio", "perplexity")
            return self._studio_open("https://www.perplexity.ai/", "Perplexity")
        if key == "design":
            self.habits.log("studio", "design")
            return self._flavor(
                "ok",
                self._run_vibe_code(
                    brief="design moodboard board with color palette typography and layout mock"
                ),
            )
        if key == "figma":
            self.habits.log("studio", "figma")
            return self._studio_open("https://www.figma.com/", "Figma")
        if key == "audio":
            self.habits.log("studio", "audio")
            try:
                self.settings.tts_prefer_elevenlabs = True
                if hasattr(self, "live_voice") and self.live_voice:
                    self.live_voice.model = getattr(
                        self.settings, "elevenlabs_model", None
                    ) or "eleven_turbo_v2_5"
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Audio mode armed — ElevenLabs preferred. "
                "Say something and I will speak it, or open 11 Labs for the full studio.",
            )
        if key == "eleven":
            self.habits.log("studio", "eleven")
            return self._studio_open("https://elevenlabs.io/app", "11 Labs")
        if key == "images":
            self.habits.log("studio", "images")
            return self._studio_open(
                "https://www.midjourney.com/imagine", "Images · Midjourney Imagine"
            )
        if key == "midjourney":
            self.habits.log("studio", "midjourney")
            return self._studio_open("https://www.midjourney.com/", "Mid-Journey")
        if key == "automation":
            self.habits.log("studio", "automation")
            base = (getattr(self.settings, "n8n_url", None) or "http://127.0.0.1:5678").rstrip(
                "/"
            )
            return self._studio_open(f"{base}/home/workflows", "Automation · n8n")
        if key == "n8n":
            self.habits.log("studio", "n8n")
            base = (getattr(self.settings, "n8n_url", None) or "http://127.0.0.1:5678").rstrip(
                "/"
            )
            return self._studio_open(base, "N8N")
        return None

    def _run_vibe_code(self, brief: str = "") -> str:
        """Kick off autonomous vibe coding / agent development."""
        hint = (brief or "").strip() or "invented app"
        ide = getattr(self.settings, "work_ide", None) or "code"
        self._emit("code_ui", {"building": True, "hint": hint})
        self.feed.push("vibe", f"Autonomous code session: {hint}")

        def _job() -> None:
            try:
                def progress(msg) -> None:
                    self._emit("code_progress", msg)
                    text = (
                        str(msg.get("msg") or "")
                        if isinstance(msg, dict)
                        else str(msg)
                    )
                    if text:
                        self.feed.push(
                            "vibe", text[:160], meta={"status": "building"}
                        )
                    if isinstance(msg, dict) and msg.get("speak"):
                        try:
                            self.say(str(msg["speak"]))
                        except Exception:
                            pass

                reply = self.vibe.build(
                    brief or "",
                    open_when_done=True,
                    ide=ide,
                    on_progress=progress,
                    hitl=self.hitl,
                )
                meta = self.vibe.last_meta or {}
                preview_url = str(meta.get("preview_url") or "").strip()
                app_url = str(meta.get("app_url") or "").strip()
                if not preview_url:
                    try:
                        preview_url = self.vibe.ensure_preview_url() or ""
                        app_url = preview_url or app_url
                    except Exception:
                        pass
                if not preview_url:
                    port = getattr(self.vibe, "_preview_port", None)
                    root = self.vibe.last_project
                    if port and root is not None:
                        entry = self.vibe._preview_entry(root)
                        preview_url = f"http://127.0.0.1:{port}/{entry}"
                        app_url = preview_url
                payload = {
                    "path": meta.get("path") or str(self.vibe.last_project or ""),
                    "name": meta.get("name") or "",
                    "engine": meta.get("engine") or "",
                    "files": meta.get("files") or [],
                    "entry": meta.get("entry") or "",
                    "prompt": self.vibe.last_prompt or "",
                    "preview_url": preview_url,
                    "app_url": app_url,
                    "keep_theater": True,
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
            "Understood. Opening Build Theater — Working, Coding, and Preview tabs. "
            "I will invent the product if needed, write the brief, generate the code, "
            "and open the runnable preview. Watch the vibe panel."
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
        """Parse zoom/fly/find-address / where-is / locate / show-on-map commands."""
        patterns = (
            r"\bfind\s+address\s+(.+)$",
            r"\blocate\s+(?:the\s+)?(?:address\s+(?:of|for)\s+)?(.+)$",
            r"\bwhere\s+is\s+(.+)$",
            r"\bnavigate\s+to\s+(.+)$",
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
            "my keys",
            "my phone",
            "that",
            "this",
            "it",
        }
        for pat in patterns:
            m = re.search(pat, t, flags=re.I)
            if not m:
                continue
            dest = (m.group(1) or "").strip(" .,!?")
            dest = re.sub(
                r"\b(on the map|in the map|please|for me|view|mode|3d|the map|"
                r"address of|address for)\b",
                "",
                dest,
                flags=re.I,
            ).strip(" .,!?")
            low = dest.lower()
            if not dest or low in _non_geo:
                continue
            # Skip inventory / personal-item "where is" (handled elsewhere)
            if re.search(
                r"\b(my|our)\s+(keys?|phone|wallet|bag|laptop|remote|charger)\b",
                low,
            ):
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
        """Geocode place via Nominatim, fly 3D map, speak a short location brief."""
        from jarvis.ui.widgets.map_view import _brief_for, _geocode_detail

        hit = _geocode_detail(place)
        if not hit:
            return self._flavor(
                "ok",
                f"I couldn't find an address or place matching {place}. "
                f"Try a clearer street, landmark, or city name.",
            )
        brief = _brief_for(hit)
        label = str(hit.get("name") or place)
        try:
            self.habits.log("map_zoom", label[:40])
        except Exception:
            pass
        markers = [
            {
                "lat": hit["lat"],
                "lon": hit["lon"],
                "label": label,
                "name": label,
            }
        ]
        self._emit(
            "map_ui",
            {
                "place": label,
                "lat": hit["lat"],
                "lon": hit["lon"],
                "zoom": hit.get("zoom") or 15.5,
                "label": label,
                "brief": brief,
                "markers": markers,
                "scanning": False,
                "animate": True,
            },
        )
        try:
            self._emit("hud_alert", f"Locate · {label}")
        except Exception:
            pass
        return self._flavor(
            "ok",
            f"Found it — {label}. Zooming the tactical map. {brief}",
        )

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
            rem = getattr(self, "reminders", None)
            if rem is not None:
                rem.stop()
        except Exception:
            pass
        try:
            door = getattr(self, "doorbell", None)
            if door is not None:
                door.stop()
        except Exception:
            pass
        try:
            snap = getattr(self, "snapchat", None)
            if snap is not None:
                snap.stop()
        except Exception:
            pass
        try:
            comms = getattr(self, "comms_live", None)
            if comms is not None:
                comms.stop()
        except Exception:
            pass
        try:
            if self.watch:
                self.watch.stop()
        except Exception:
            pass
        try:
            iot = getattr(self, "iot", None)
            if iot is not None:
                iot.close()
        except Exception:
            pass

    def handle_macro(self, cmd: str) -> str:
        """Silent Stream Deck / HTTP macros — no TTS required for stop."""
        c = (cmd or "").strip().lower()
        if c in (
            "doorbell",
            "ding",
            "ring",
            "ring ding",
            "doorbell_ding",
            "doorbell ding",
        ):
            return self.handle_doorbell("ding")
        if c in (
            "doorbell_motion",
            "ring_motion",
            "motion",
            "doorbell motion",
            "ring motion",
        ):
            return self.handle_doorbell("motion")
        if c in (
            "snapchat",
            "snap call",
            "snapchat call",
            "snap_incoming",
            "snap incoming",
        ):
            return self.handle_snapchat_call(
                SnapCallEvent(caller="Someone", source="test", title="macro")
            )
        if c in ("snapchat answer", "answer snap", "answer snapchat"):
            snap = getattr(self, "snapchat", None)
            if snap is None:
                return "Snapchat bridge not loaded."
            return snap.try_answer_now()
        if (
            c.startswith("room ")
            or c.startswith("nfc ")
            or c.startswith("mirror ")
            or c.startswith("ambient ")
            or c.startswith("desk light ")
            or c in ("iot status", "room status", "presence status")
        ):
            if getattr(self, "iot", None):
                return self.iot.handle(c)
        if c in ("healer", "healer status"):
            if getattr(self, "healer", None):
                return self.healer.status()
        if c in ("healer kill", "healer_kill"):
            if getattr(self, "healer", None):
                return self.healer.kill_hog() or self.healer.kill_top()
        if c.startswith("scaffold "):
            parts = c.split(None, 2)
            kind = parts[1] if len(parts) > 1 else "html"
            name = parts[2] if len(parts) > 2 else ""
            if getattr(self, "scaffolder", None):
                return self._scaffold_with_preview(kind, name)
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

    def handle_doorbell(self, event: str = "ding") -> str:
        """Ring / HA doorbell alert — speak, HUD, phone (debounced)."""
        import time as _time

        kind = (event or "ding").strip().lower()
        if kind not in ("ding", "motion"):
            kind = "ding"
        now = _time.monotonic()
        until = float(getattr(self, "_doorbell_until", 0.0) or 0.0)
        cooldown = float(
            getattr(self.settings, "doorbell_cooldown_sec", 45.0) or 45.0
        )
        if now < until:
            left = int(until - now)
            self._emit("heard", f"[doorbell] suppressed ({kind}, {left}s left)")
            return f"Doorbell {kind} suppressed ({left}s cooldown)."
        self._doorbell_until = now + max(5.0, cooldown)

        if kind == "motion":
            line = "Motion at the front door."
            hud = "RING › MOTION"
            phone_msg = "Ring: motion at the front door"
        else:
            line = "Someone is at the front door."
            hud = "RING › DOORBELL"
            phone_msg = "Ring: someone is at the front door"

        try:
            self._emit("hud_alert", hud)
            self._emit("heard", f"[doorbell] {kind}")
        except Exception:
            pass
        try:
            if hasattr(self.voice, "say_protected"):
                self.voice.say_protected(line)
            else:
                self.say(line)
        except Exception as e:
            print(f"[doorbell] speak: {e}")
        try:
            self.phone.notify(phone_msg, title="JARVIS · Door", priority=5)
        except Exception as e:
            print(f"[doorbell] phone: {e}")
        return line

    def handle_snapchat_call(self, event: SnapCallEvent | str | None = None) -> str:
        """Incoming Snapchat / Phone Link call — announce, notify, optional answer."""
        if isinstance(event, str):
            ev = SnapCallEvent(caller=event or "Someone", source="test")
        elif event is None:
            ev = SnapCallEvent(caller="Someone", source="test")
        else:
            ev = event
        caller = (ev.caller or "Someone").strip() or "Someone"
        line = f"Incoming Snapchat call from {caller}."
        hud = f"SNAP › {caller.upper()[:24]}"
        phone_msg = f"Snapchat: {caller} is calling"
        try:
            self._emit("hud_alert", hud)
            self._emit("heard", f"[snapchat] {ev.source}: {caller}")
        except Exception:
            pass
        try:
            if hasattr(self.voice, "say_protected"):
                self.voice.say_protected(line)
            else:
                self.say(line)
        except Exception as e:
            print(f"[snapchat] speak: {e}")
        try:
            self.phone.notify(
                phone_msg,
                title="JARVIS · Snapchat",
                priority=5,
                tags=["telephone_receiver", "rotating_light", "warning"],
            )
        except Exception as e:
            print(f"[snapchat] phone: {e}")
        return line

    def handle_comms_live(self, event: CommsEvent | None = None) -> str:
        """Live Snap / IG / iMessage line — HUD + optional speak + phone push."""
        if event is None:
            return "No message."
        app = (event.app or "message").strip().lower()
        label = {
            "snapchat": "SNAP",
            "instagram": "IG",
            "imessage": "iMSG",
        }.get(app, app.upper()[:6])
        sender = (event.sender or "Someone").strip() or "Someone"
        body = (event.translated or event.text or "").strip()
        original = (event.text or "").strip()
        if event.kind == "call":
            line = f"Incoming {label} call from {sender}."
            hud = f"{label} › CALL · {sender.upper()[:20]}"
            phone_msg = f"{label}: {sender} is calling"
        else:
            show = body
            if (
                event.translated
                and original
                and event.translated.lower() != original.lower()
                and event.lang
                and event.lang != getattr(self.settings, "comms_live_target_lang", "en")
            ):
                show = f"{body}  (orig: {original[:80]})"
            elif (
                event.translated
                and original
                and event.translated.lower() != original.lower()
            ):
                show = f"{body}"
            line = f"{label} from {sender}: {show[:180]}"
            hud = f"{label} › {sender.upper()[:16]}"
            phone_msg = f"{label} {sender}: {body[:160]}"
        try:
            self._emit("hud_alert", hud)
            self._emit(
                "heard",
                f"[comms] {app}/{event.kind}: {sender}: {(body or original)[:100]}",
            )
            self._emit(
                "artifact",
                {
                    "title": f"{label} · LIVE",
                    "text": (
                        f"From: {sender}\nApp: {app}\nKind: {event.kind}\n"
                        f"Text: {original}\n"
                        f"Translated: {event.translated or '—'}\n"
                        f"Lang: {event.lang or '—'}\n"
                        f"Source: {event.source}"
                    ),
                },
            )
        except Exception:
            pass
        # Avoid double-speak when Snap call bridge also fires
        quiet = bool(getattr(self, "_quiet_mode", False))
        speak = bool(getattr(self.settings, "comms_live_speak", True))
        if speak and not quiet and not (
            event.kind == "call" and app == "snapchat"
        ):
            try:
                if hasattr(self.voice, "say_protected"):
                    self.voice.say_protected(line)
                else:
                    self.say(line)
            except Exception as e:
                print(f"[comms] speak: {e}")
        if bool(getattr(self.settings, "comms_live_notify_phone", True)):
            try:
                self.phone.notify(
                    phone_msg,
                    title=f"JARVIS · {label}",
                    priority=5 if event.kind == "call" else 4,
                    tags=["speech_balloon", "globe_with_meridians"],
                )
            except Exception as e:
                print(f"[comms] phone: {e}")
        return line

    def handle_reminder_fire(self, rem: Reminder) -> None:
        """Due reminder — HUD + speak + phone push."""
        msg = (rem.message or "Reminder").strip()
        when = rem.label_time or "now"
        line = f"Reminder: {msg}. That's {when}."
        try:
            self._emit("hud_alert", f"REMIND › {msg[:40]}")
            self._emit("heard", f"[reminder] {msg}")
            self._emit(
                "artifact",
                {
                    "title": "REMINDER",
                    "text": f"{msg}\n\nScheduled for: {when}\nZone: {rem.timezone}",
                },
            )
        except Exception:
            pass
        try:
            if hasattr(self.voice, "say_protected"):
                self.voice.say_protected(line)
            else:
                self.say(line)
        except Exception as e:
            print(f"[reminders] speak: {e}")
        try:
            self.phone.notify(
                f"{msg} ({when})",
                title="JARVIS · Reminder",
                priority=5,
                tags=["alarm_clock", "rotating_light"],
            )
        except Exception as e:
            print(f"[reminders] phone: {e}")

    def _on_net_intruder(self, msg: str) -> None:
        try:
            self._emit("hud_alert", "NET WATCH · UNKNOWN DEVICE")
            self._emit("heard", f"[net] {msg}")
            self.say(msg)
        except Exception:
            pass
        try:
            self.phone.notify(msg, title="JARVIS · Net Watch", priority=5, tags=["warning"])
        except Exception:
            pass

    def _on_software_security_alert(self, msg: str) -> None:
        """HUD + phone when Defender looks disabled (defensive only)."""
        try:
            self._emit("hud_alert", "DEFENDER · CHECK")
            self._emit("heard", f"[software-security] {msg}")
            self.say(msg)
        except Exception:
            pass
        try:
            self.phone.notify(
                msg,
                title="JARVIS · Software Security",
                priority=5,
                tags=["warning", "shield"],
            )
        except Exception:
            pass

    def _on_deadman_miss(self, msg: str) -> None:
        try:
            self._emit("hud_alert", "DEADMAN MISS")
            self.say(msg)
            self.system.lock()
        except Exception:
            pass
        try:
            self.phone.notify(msg, title="JARVIS · Deadman", priority=5, tags=["rotating_light"])
        except Exception:
            pass
        try:
            if getattr(self, "backups", None):
                self._run_backup_bg(label="deadman")
        except Exception:
            pass

    def _on_space_severe(self, msg: str) -> None:
        try:
            self._emit("hud_alert", "SPACE WEATHER")
            self.say(msg)
        except Exception:
            pass
        try:
            if getattr(self, "backups", None):
                self._run_backup_bg(label="solar")
        except Exception:
            pass
        try:
            self.phone.notify(msg, title="JARVIS · Space Weather", priority=4)
        except Exception:
            pass

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
            note = ""
            try:
                note = getattr(self.companion, "handoff_note", "") or ""
                hp = DATA_DIR / "handoff.json"
                if not note and hp.exists():
                    note = json.loads(hp.read_text(encoding="utf-8")).get("note", "")
            except Exception:
                pass
            return {
                "user": self.settings.user_name,
                "listening": not bool(getattr(self, "_handling", False)),
                "port": port,
                "handoff": note,
            }

        self.companion = CompanionServer(
            self.handle_companion,
            token=token,
            host=host,
            port=port,
            on_status=_status,
            on_handoff=self._companion_handoff,
            on_score=lambda data: app_scores.ingest(
                data if isinstance(data, dict) else {}
            ),
            on_presence=self._companion_presence,
        )
        self.companion.start()

    def _companion_presence(self, data: dict) -> dict:
        """BLE / mmWave / phone → room targeting for voice lead."""
        adv = getattr(self, "advanced", None)
        if adv is None:
            return {"reply": "Advanced AI pack offline."}
        msg = adv.presence.ingest_sensor(data if isinstance(data, dict) else {})
        return {"reply": msg, "room": adv.presence.current_room()}

    def _companion_handoff(self, data: dict) -> dict:
        """PC shutdown / sleep → save context for iPad companion."""
        target = str((data or {}).get("target") or "ipad")
        project = str((data or {}).get("project") or getattr(self.settings, "work_project_path", "") or "")
        ctx = str((data or {}).get("context") or "")
        win = ""
        try:
            if getattr(self, "screen", None):
                win = self.screen.active_window_title() or ""
        except Exception:
            pass
        note = (
            f"Main terminal offline. Saved progress"
            + (f" on {Path(project).name}" if project else "")
            + (f" · last window: {win[:80]}" if win else "")
            + ". Shall we proceed from here, sir?"
        )
        if ctx:
            note = f"{ctx.rstrip('.')}. {note}"
        path = DATA_DIR / "handoff.json"
        try:
            path.write_text(
                json.dumps(
                    {
                        "target": target,
                        "project": project,
                        "window": win,
                        "context": ctx,
                        "note": note,
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        if getattr(self, "companion", None):
            self.companion.handoff_note = note
        try:
            if getattr(self, "phone", None):
                self.phone.notify(note, title="JARVIS · handoff", priority=4)
        except Exception:
            pass
        try:
            self.vstore.remember(
                f"Handoff: user left desk; project={project or 'unknown'}; window={win or 'unknown'}",
                kind="handoff",
            )
        except Exception:
            pass
        return {"note": note, "target": target, "window": win}
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
        if not bool(getattr(self.settings, "ambient_light_sync", True)):
            return
        try:
            from jarvis.core.iot_bridge import AMBIENT_RGB

            raw = (mode or "idle").lower().strip()
            if raw in ("thinking", "process", "processing", "fetch"):
                key = "thinking"
            elif raw in ("compiling", "compile", "coding", "build", "vibe", "site", "code"):
                key = "compiling"
            elif raw in ("error", "panic"):
                key = "error"
            else:
                key = "idle"
            if key == getattr(self, "_last_ambient_sync", None):
                return
            self._last_ambient_sync = key
            rgb = AMBIENT_RGB.get(key, AMBIENT_RGB["idle"])
            iot = getattr(self, "iot", None)
            if iot is not None:
                iot.sync_ambient(key)
            try:
                # Prefer keyboard-class devices; never blast DualSense as fallback
                detail = self.rgb.set_color(rgb, target="keyboard")
                if isinstance(detail, str) and detail.lower().startswith("could not"):
                    self.rgb.set_color(rgb, target="all")
            except Exception:
                pass
            light_mode = {
                "idle": "calm",
                "thinking": "focus",
                "compiling": "coding",
                "error": "late_night",
            }.get(key)
            if light_mode:
                try:
                    self.lights.set_mode(light_mode)
                except Exception:
                    pass
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
            if now - self._start_cooldown < 0.4:
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
                time.sleep(0.35)
                self._emit("listening", False)

            threading.Thread(target=_settle, daemon=True).start()

        threading.Thread(target=_do, daemon=True, name="jarvis-start").start()

    def say(self, text: str) -> None:
        if getattr(self, "_stopped", False):
            return
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

    def _screenshot(self) -> str:
        """Capture the desktop to Pictures/Jarvis and report the path."""
        try:
            path = self.screen.capture_png()
            if path is None:
                return "Could not capture the screen."
            self._emit("hud_alert", f"Screenshot saved · {path.name}")
            return f"Screenshot saved to {path}."
        except Exception as e:
            return f"Screenshot failed: {e}"

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
            if req.kind.value == "clarify" if hasattr(req.kind, "value") else str(req.kind) == "clarify":
                opts = ", ".join(str(o) for o in (req.options or [])[:4])
                self._emit(
                    "speak_ui",
                    f"Clarify — {req.title}. Options: {opts}",
                )
            else:
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
            # Stale gate click after voice already resolved — quiet no-op
            try:
                self._emit("hitl_clear", True)
            except Exception:
                pass
            return ""
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
            if on:
                self.settings.zero_latency = True
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
                    {"dim": True, "ambient": "conserve", "fps": 8},
                )
            else:
                self._emit("bond", {"fps": 15, "ambient": "normal"})
        except Exception:
            pass
        if on:
            try:
                self._apply_zero_latency()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Smooth mode on — HUD throttled so voice stays snappy.",
            )
        return self._flavor("ok", "Full fidelity HUD restored.")

    def _boot_heavy_agents(self) -> None:
        """Load crew / work-crew / auto-loop after voice HUD is already live."""
        if getattr(self, "_crew_boot_started", False):
            return
        self._crew_boot_started = True

        def _go() -> None:
            try:
                if bool(getattr(self.settings, "crew_enabled", True)) and self.crew is None:
                    from jarvis.core.agent_crew import AgentCrew

                    self.crew = AgentCrew(
                        self.settings,
                        vstore=self.vstore,
                        internet=self.net,
                        phone=self.phone,
                        n8n=self.n8n,
                        computer_use=self.cu_agent,
                    )
                    print("[crew] deferred boot ready")
            except Exception as e:
                print(f"[crew] deferred init: {e}")
            try:
                if self.work_crew is None:
                    from jarvis.core.work_crew import WorkCrew

                    self.work_crew = WorkCrew(
                        self.settings,
                        research=getattr(self.crew, "research", None)
                        if self.crew
                        else None,
                    )
            except Exception as e:
                print(f"[work-crew] deferred init: {e}")
            try:
                if self.auto_loop is None:
                    from jarvis.core.auto_loop import AutoLoopEngine

                    self.auto_loop = AutoLoopEngine(
                        self.settings,
                        codesmith=getattr(self.crew, "code", None)
                        if self.crew
                        else None,
                        on_progress=lambda m: self.feed.push("loop", m[:160]),
                    )
            except Exception as e:
                print(f"[auto-loop] deferred init: {e}")
            try:
                if (
                    bool(getattr(self.settings, "systems_ai_v2_enabled", True))
                    and self.systems_v2 is None
                ):
                    from jarvis.core.systems_ai_v2 import SystemsAIv2

                    def _llm(prompt: str) -> str:
                        try:
                            from jarvis.core.llm_client import complete

                            return complete(prompt) or ""
                        except Exception:
                            return ""

                    self.systems_v2 = SystemsAIv2(
                        settings=self.settings,
                        vstore=getattr(self, "vstore", None),
                        internet=getattr(self, "net", None),
                        llm_fn=_llm,
                        on_status=lambda m: self.feed.push("systems", m[:160]),
                    )
                    print("[systems-v2] deferred boot ready")
            except Exception as e:
                print(f"[systems-v2] deferred init: {e}")

        threading.Thread(target=_go, daemon=True, name="jarvis-heavy-boot").start()

    def _apply_zero_latency(self) -> None:
        """Tighten watchers + voice-facing settings for lean runtime."""
        try:
            self.settings.zero_latency = True
            self.settings.performance_mode = True
            self.settings.tts_instant_ack = False  # avoid "On it" double-TTS lag
            self.settings.telemetry_interval_ms = min(
                int(getattr(self.settings, "telemetry_interval_ms", 2000) or 2000),
                2000,
            )
            self.settings.snapchat_poll_sec = min(
                float(getattr(self.settings, "snapchat_poll_sec", 0.55) or 0.55),
                0.55,
            )
            self.settings.comms_live_poll_sec = min(
                float(getattr(self.settings, "comms_live_poll_sec", 0.55) or 0.55),
                0.55,
            )
            self.settings.save()
        except Exception:
            pass
        try:
            snap = getattr(self, "snapchat", None)
            if snap is not None:
                snap.poll_sec = max(0.4, float(self.settings.snapchat_poll_sec))
        except Exception:
            pass
        try:
            comms = getattr(self, "comms_live", None)
            if comms is not None:
                comms.poll_sec = max(0.35, float(self.settings.comms_live_poll_sec))
        except Exception:
            pass
        try:
            voice = getattr(self, "voice", None)
            if voice is not None:
                voice.rate = getattr(self.settings, "tts_rate", "+8%") or "+8%"
                voice.chunk_sentences = True
        except Exception:
            pass

    def optimize_jarvis(self) -> str:
        """One-shot lean profile: smooth HUD, fast voice, tight watchers."""
        try:
            self.settings.performance_mode = True
            self.settings.zero_latency = True
            self.settings.tts_rate = "+8%"
            self.settings.tts_instant_ack = False
            self.settings.tts_chunk_sentences = True
            self.settings.telemetry_interval_ms = 2000
            self.settings.presence_check_fps = 2
            self.settings.snapchat_poll_sec = 0.55
            self.settings.comms_live_poll_sec = 0.55
            self.settings.chat_memory_turns = min(
                int(getattr(self.settings, "chat_memory_turns", 8) or 8), 6
            )
            self.settings.noise_reduce = False  # CPU-heavy on mic path
            self.settings.save()
        except Exception as e:
            return f"Could not save optimize settings: {e}"
        try:
            self._set_performance_mode(True)
        except Exception:
            pass
        try:
            self._apply_zero_latency()
        except Exception:
            pass
        try:
            self._emit(
                "artifact",
                {
                    "title": "JARVIS · OPTIMIZED",
                    "text": (
                        "Smooth HUD · zero-latency watchers · snappy TTS\n"
                        "Crew agents boot deferred · chroma stays lazy\n"
                        "Restart once if voice rate still feels old."
                    ),
                },
            )
        except Exception:
            pass
        return (
            "Jarvis optimized — smooth HUD, faster speech, no On-it lag, leaner watchers. "
            "Restart once for a fully clean boot."
        )

    def upgrade_everything(self) -> str:
        """Full polish pass: optimize + cinematic AR pro profile + voice fixes."""
        bits: list[str] = []
        try:
            bits.append(self.optimize_jarvis().split("—")[0].strip() or "Optimized")
        except Exception as e:
            bits.append(f"optimize skipped ({e})")
        try:
            from jarvis.core.aerospatial import AerospatialMapper

            ar = AerospatialMapper()
            bits.append(ar.apply_pro_profile())
        except Exception as e:
            bits.append(f"AR profile skipped ({e})")
        try:
            self.settings.tts_instant_ack = False
            self.settings.zero_latency = True
            self.settings.performance_mode = True
            self.settings.suggestions_enabled = True
            self.settings.save()
        except Exception:
            pass
        try:
            self._emit("aerospatial_cinematic", True)
        except Exception:
            pass
        try:
            self._emit(
                "artifact",
                {
                    "title": "JARVIS · UPGRADE EVERYTHING",
                    "text": (
                        "✓ Zero-latency voice (no On-it double speak)\n"
                        "✓ Smooth / performance HUD\n"
                        "✓ Cinematic AR pro: lerp · hold-lock · CLAHE · light adapt\n"
                        "✓ Web shooter · biometric · PC gauges · spatial audio\n"
                        "Say: open aerospatial · good morning · help"
                    ),
                },
            )
        except Exception:
            pass
        summary = " · ".join(bits[:3])
        return (
            f"Upgrade complete. {summary} "
            "Say open aerospatial for the cinematic hologram lab."
        )

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
                or getattr(self.settings, "gaze_workspace_enabled", True)
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

            # Instant voice ack — skip in zero-latency / fast-local (avoids double TTS delay)
            if from_voice and bool(getattr(self.settings, "tts_instant_ack", True)):
                try:
                    skip_ack = bool(getattr(self.settings, "zero_latency", False))
                    if not skip_ack and not is_fast_local_command((text or "").lower()):
                        self.voice.say_ack("On it.")
                except Exception:
                    pass

            # HITL voice resolve — only yes/no / matching option (never swallow cmds)
            hitl_msg = self.hitl.resolve_voice(text)
            if hitl_msg:
                # If async clarify is pending, prefer that path below after wake strip
                if not getattr(self, "_pending_clarify", None):
                    try:
                        self._emit("hitl_clear", True)
                    except Exception:
                        pass
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

            # Pending multi-choice clarify — typed option name / number
            if getattr(self, "_pending_clarify", None):
                from jarvis.core.ambiguity import resolve_option as _res_opt

                choice = (low or text).strip()
                got = _res_opt(self._pending_clarify, choice)
                if got is not None or choice.lower() in (
                    "cancel",
                    "skip",
                    "1",
                    "2",
                    "3",
                    "4",
                ):
                    msg = self.resolve_clarify_choice(choice)
                    if msg:
                        self._emit("speak_ui", msg)
                    return

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
            # Free the mic immediately so the next command isn't dropped
            delay = 0.02 if self._note_mode else 0.02
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
        # Alert desk blasts — HUD + high-priority ping (before soft notify)
        if re.search(
            r"\b(alert phone|send alert|desk alert|blast alert|secure blast|"
            r"intruder blast|encrypt alert)\b",
            t,
        ):
            hub = self._route_desk_hub(t)
            if hub is not None:
                return hub
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

    def _try_doorbell_cmd(self, t: str) -> str | None:
        """Alexa/IFTTT doorbell setup + test."""
        if not t:
            return None
        if re.search(
            r"\b(doorbell\s+setup|setup\s+(the\s+)?doorbell|"
            r"ring\s+setup|ifttt\s+doorbell|"
            r"doorbell\s+(link|status|url))\b",
            t,
        ):
            return self._flavor("ok", self.doorbell_setup_message())
        if re.search(
            r"\b(test\s+(the\s+)?doorbell|doorbell\s+test|"
            r"simulate\s+(door|ding|doorbell))\b",
            t,
        ):
            return self._flavor("ok", self.handle_doorbell("ding"))
        return None

    def _try_snapchat_cmd(self, t: str) -> str | None:
        """Snapchat call watcher setup / test / answer."""
        if not t:
            return None
        if re.search(
            r"\b(snapchat\s+(setup|link|status|url)|"
            r"setup\s+(snap|snapchat)(\s+calls?)?|"
            r"link\s+(my\s+)?(snap|snapchat)(\s+calls?)?|"
            r"snap\s+call\s+(setup|status|link)|"
            r"link\s+snap)\b",
            t,
        ):
            return self._flavor("ok", self.snapchat_setup_message())
        if re.search(
            r"\b(test\s+(snap|snapchat)(\s+call)?|"
            r"simulate\s+(snap|snapchat)(\s+call)?|"
            r"snapchat\s+test)\b",
            t,
        ):
            import time as _time

            snap = getattr(self, "snapchat", None)
            if snap is not None:
                snap._until = _time.monotonic() + snap.cooldown_sec
                snap._last_fingerprint = "test:test"
            return self._flavor(
                "ok",
                self.handle_snapchat_call(
                    SnapCallEvent(caller="Test", source="test", title="voice test")
                ),
            )
        if re.search(
            r"\b((auto\s+)?answer\s+(the\s+)?(snap|snapchat)(\s+call)?|"
            r"pick\s+up\s+(the\s+)?(snap|snapchat)|"
            r"snapchat\s+answer)\b",
            t,
        ):
            snap = getattr(self, "snapchat", None)
            if snap is None:
                return self._flavor("warn", "Snapchat bridge is not loaded.")
            return self._flavor("ok", snap.try_answer_now())
        if re.search(
            r"\b(enable|turn\s+on)\s+(snap|snapchat)(\s+calls?)?\b|"
            r"\b(snap|snapchat)\s+calls?\s+on\b",
            t,
        ):
            return self._flavor("ok", self._set_snapchat_enabled(True))
        if re.search(
            r"\b(disable|turn\s+off)\s+(snap|snapchat)(\s+calls?)?\b|"
            r"\b(snap|snapchat)\s+calls?\s+off\b",
            t,
        ):
            return self._flavor("ok", self._set_snapchat_enabled(False))
        return None

    def _try_reminder_cmd(self, t: str) -> str | None:
        """Timezone-aware timed reminders (California / Pacific / local)."""
        if not t:
            return None
        rem = getattr(self, "reminders", None)
        if rem is None:
            return None
        if re.search(
            r"\b(list reminders|my reminders|reminder status|what reminders|"
            r"show reminders|pending reminders)\b",
            t,
        ):
            return self._flavor("ok", rem.status())
        if re.search(
            r"\b(cancel (all )?reminders?|clear reminders?|"
            r"delete (all )?reminders?)\b",
            t,
        ):
            m = re.search(
                r"\b(?:cancel|clear|delete)\s+(?:reminder\s+)?(.+)$", t
            )
            hint = (m.group(1) if m else "all").strip()
            if hint in ("reminders", "reminder", "all reminders"):
                hint = "all"
            return self._flavor("ok", rem.cancel(hint))
        # set / remind at time (with or without zone)
        if re.search(
            r"\b("
            r"remind me\b.+\b(at|when|turns?)\b|"
            r"set (a |me a )?reminder\b|"
            r"reminder (for|at)\b|"
            r"nudge me (at|when)\b|"
            r"alarm (for|at)\b"
            r")",
            t,
        ) and re.search(
            r"\b(at\s+\d|when\s+it|turns?\s+\d|\d{1,2}\s*(:\d{2})?\s*(a\.?m\.?|p\.?m\.?)|"
            r"california|cali|pacific|tonight|tomorrow)\b",
            t,
        ):
            return self._flavor("ok", rem.add_from_utterance(t))
        return None

        return None

    def _try_voice_clone_cmd(self, t: str) -> str | None:
        """Room grab / YouTube clone / speak-as / engine select."""
        if not t:
            return None
        lab = getattr(self, "voice_clone", None)
        if lab is None:
            return None

        if re.search(
            r"\b(voice clone status|clone (lab )?status|voice samples? status)\b",
            t,
        ):
            return self._flavor("ok", lab.status())

        if re.search(
            r"\b(list (voice )?clones?|list voice samples|show (voice )?clones?)\b",
            t,
        ):
            return self._flavor("ok", lab.list_samples())

        if re.search(
            r"\b(clear (voice )?clone|stop (impersonating|cloning)|"
            r"use (normal|standard|default) (jarvis )?voice)\b",
            t,
        ):
            return self._flavor("ok", lab.clear_active())

        m_eng = re.search(
            r"\b(?:set |use )?(?:voice )?clone engine(?: to)?\s+"
            r"(auto|f5|f5[- ]?tts|xtts|coqui|gpt[- ]?sovits|sovits|eleven(?:labs)?|edge)\b",
            t,
        )
        if m_eng:
            return self._flavor("ok", lab.set_engine(m_eng.group(1)))

        m_yt = re.search(
            r"\b(?:clone (?:voice )?from youtube|youtube (?:voice )?clone)\b"
            r".*?(https?://\S+|www\.youtube\.com\S+|youtu\.be/\S+)",
            t,
            re.I,
        )
        if m_yt:
            url = m_yt.group(1).rstrip(".,)")
            return self._flavor("ok", lab.clone_from_youtube(url))

        m_use = re.search(
            r"\b(?:talk|speak|use) as (?:clone |voice )?"
            r"['\"]?([a-z0-9_\- ]{2,40})['\"]?\b",
            t,
        )
        if m_use and not re.search(r"\bspeak as clone\b", t):
            name = m_use.group(1).strip()
            if name not in ("clone", "jarvis", "me", "you"):
                # If followed by quoted speech, use then speak
                m_line = re.search(r"\bsay\b[:\s]+(.+)$", t)
                msg = lab.use_clone(name)
                if m_line:
                    return self._flavor("ok", lab.speak_as_clone(m_line.group(1).strip()))
                return self._flavor("ok", msg)

        m_speak = re.search(
            r"\b(?:speak|talk|say) as clone\b[:\s]*(.*)$",
            t,
        )
        if m_speak:
            line = (m_speak.group(1) or "").strip() or "Hello — voice clone online."
            return self._flavor("ok", lab.speak_as_clone(line))

        if re.search(
            r"\b("
            r"grab (voice|clone)|clone (this )?voice|record (a )?voice (sample|clone)|"
            r"voice grab|sample (this )?voice|ten second(s)? (voice )?clone|"
            r"clone (the )?(next )?10 seconds?|listen(ing)? (and )?clone"
            r")\b",
            t,
        ):
            if not bool(getattr(self.settings, "voice_clone_enabled", True)):
                return self._flavor("ok", "Voice clone is disabled in settings.")
            # Optional name: "grab voice as marcus"
            m_name = re.search(r"\bas ([a-z0-9_\-]{2,32})\b", t)
            name = m_name.group(1) if m_name else ""
            sec = float(getattr(self.settings, "voice_clone_seconds", 10) or 10)
            m_sec = re.search(r"\b(\d{1,2})\s*seconds?\b", t)
            if m_sec:
                sec = float(m_sec.group(1))
            self._emit("show_tools", True)
            return self._flavor(
                "ok",
                lab.grab_room_async(
                    seconds=sec,
                    name=name,
                    denoise=bool(getattr(self.settings, "voice_clone_denoise", True)),
                ),
            )

        return None

    def _try_home_ops_cmd(self, t: str) -> str | None:
        """Edge / net watch / backups / deadman / space weather / harden / translate."""
        if not t:
            return None
        # Deadman phrase check-in (any utterance containing the phrase)
        try:
            dm = getattr(self, "deadman", None)
            if dm is not None:
                hit = dm.check_in(t)
                if hit:
                    return self._flavor("ok", hit)
                # Periodic tick when user talks (on_miss already spoke — don't re-say)
                dm.tick()
        except Exception:
            pass

        if re.search(r"\b(edge setup|jetson setup|home server setup)\b", t):
            from jarvis.core.edge_node import edge_setup_message

            guide = edge_setup_message()
            try:
                self._emit("artifact", {"title": "EDGE / JETSON SETUP", "text": guide})
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Edge setup is on screen — Jetson or mini-PC keeps net watch and backups "
                "alive when this PC is off.",
            )
        if re.search(r"\b(edge status|home ops status)\b", t):
            bits = []
            try:
                from jarvis.core.edge_node import edge_status

                bits.append(edge_status())
            except Exception:
                pass
            for attr in ("net_watch", "software_security", "deadman", "backups"):
                obj = getattr(self, attr, None)
                if obj is not None and hasattr(obj, "status"):
                    try:
                        bits.append(obj.status())
                    except Exception:
                        pass
            return self._flavor("ok", " · ".join(bits) if bits else "Home ops offline.")

        if re.search(
            r"\b(net watch status|network watch|lan scan|scan (the )?network|"
            r"scan local network|lan status|network security status|"
            r"unknown (devices|macs)|wifi intruder|list (lan |network )?devices)\b",
            t,
        ):
            nw = getattr(self, "net_watch", None)
            if nw is None:
                return self._flavor("warn", "Net watch not loaded.")
            if "trust" in t:
                return self._flavor("ok", nw.trust_all_current())

            deep = bool(
                re.search(
                    r"\b(scan local network|lan scan|scan (the )?network|"
                    r"network security status)\b",
                    t,
                )
            )
            if deep and hasattr(nw, "speak_local_network_scan"):

                def _lan_scan() -> None:
                    try:
                        msg = nw.speak_local_network_scan()
                        self._emit("heard", f"[lan] {msg}")
                        self.say(msg)
                    except Exception as e:
                        print(f"[lan-scan] {e}")

                threading.Thread(
                    target=_lan_scan, daemon=True, name="jarvis-lan-scan"
                ).start()
                return self._flavor(
                    "ok",
                    "Scanning your local network (owner LAN only) — "
                    "ARP devices plus common IP-cam ports. No exploit.",
                )
            if hasattr(nw, "speak_lan_status"):
                return self._flavor("ok", nw.speak_lan_status())
            found = nw.scan_once()
            return self._flavor(
                "ok",
                f"{nw.status()}. Right now {len(found)} ARP entries. "
                "Say trust network to whitelist current devices.",
            )
        if re.search(r"\b(trust (the )?(network|lan|wifi|devices)|whitelist (lan|network))\b", t):
            nw = getattr(self, "net_watch", None)
            if nw is None:
                return self._flavor("warn", "Net watch not loaded.")
            return self._flavor("ok", nw.trust_all_current())
        if re.search(r"\b(net watch (on|enable)|enable net watch)\b", t):
            nw = getattr(self, "net_watch", None)
            if nw is None:
                return None
            nw.enabled = True
            nw.start()
            self.settings.net_watch_enabled = True
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Net watch on — I'll announce unknown MACs.")
        if re.search(r"\b(net watch (off|disable)|disable net watch)\b", t):
            nw = getattr(self, "net_watch", None)
            if nw is None:
                return None
            nw.enabled = False
            nw.stop()
            self.settings.net_watch_enabled = False
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Net watch off.")

        if re.search(r"\b(run backup|secure backup|backup (now|jarvis|everything)|"
                     r"encrypt(ed)? backup)\b", t):
            b = getattr(self, "backups", None)
            if b is None:
                return self._flavor("warn", "Backup module offline.")
            return self._flavor("ok", self._run_backup_bg(label="voice"))
        if re.search(r"\b(backup status|list backups)\b", t):
            b = getattr(self, "backups", None)
            if b is None:
                return self._flavor("warn", "Backup module offline.")
            return self._flavor("ok", b.status())
        if re.search(r"\b(prune backups)\b", t):
            b = getattr(self, "backups", None)
            if b is None:
                return None
            return self._flavor("ok", b.prune(8))

        if re.search(r"\b(arm deadman|deadman (on|arm)|enable deadman)\b", t):
            dm = getattr(self, "deadman", None)
            if dm is None:
                return None
            hours = float(getattr(self.settings, "deadman_hours", 24) or 24)
            msg = dm.arm(hours=hours)
            self.settings.deadman_enabled = True
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", msg)
        if re.search(r"\b(disarm deadman|deadman (off|disarm)|disable deadman)\b", t):
            dm = getattr(self, "deadman", None)
            if dm is None:
                return None
            self.settings.deadman_enabled = False
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", dm.disarm())
        if re.search(r"\b(deadman status)\b", t):
            dm = getattr(self, "deadman", None)
            if dm is None:
                return None
            return self._flavor("ok", dm.status())

        if re.search(r"\b(space weather|solar (flare|storm)|geomagnetic)\b", t):
            sw = getattr(self, "space_weather", None)
            if sw is None:
                return self._flavor(
                    "ok",
                    "Space weather module offline.",
                )
            return self._flavor("ok", sw.speak_brief())
        if re.search(r"\b(iss (status|overhead|pass)|where('?s| is) the iss)\b", t):
            sw = getattr(self, "space_weather", None)
            if sw is None:
                return None
            return self._flavor("ok", sw.iss_overhead())

        if re.search(
            r"\b(defender status|windows defender status)\b",
            t,
        ):
            ss = getattr(self, "software_security", None)
            if ss is None:
                return self._flavor("warn", "Software security module offline.")
            return self._flavor("ok", ss.defender_status())
        if re.search(
            r"\b((run )?security scan|run (a )?quick (defender )?scan|"
            r"defender (quick )?scan|start defender scan)\b",
            t,
        ):
            ss = getattr(self, "software_security", None)
            if ss is None:
                return self._flavor("warn", "Software security module offline.")

            def _sec_scan() -> None:
                try:
                    # User-initiated only: Defender quick scan + process harden
                    quick = ss.start_quick_scan()
                    status = ss.defender_status()
                    proc = ss.harden_processes()
                    msg = f"{quick} · {status} · {proc}"
                    self._emit("heard", f"[software-security] {msg}")
                    self.say(msg)
                except Exception as e:
                    print(f"[software-security] {e}")

            threading.Thread(
                target=_sec_scan, daemon=True, name="jarvis-sec-scan"
            ).start()
            return self._flavor(
                "ok",
                "Starting defensive security scan (Defender quick scan + process check).",
            )
        if re.search(
            r"\b(harden processes|scan processes|process (harden|scan)|"
            r"check (for )?miners|background process(es)?)\b",
            t,
        ):
            ph = getattr(self, "process_harden", None)
            ss = getattr(self, "software_security", None)
            if ph is None and ss is None:
                return None

            def _scan() -> None:
                try:
                    if ss is not None and "harden processes" in t:
                        msg = ss.harden_processes()
                    elif ph is not None:
                        msg = ph.speak_scan()
                    else:
                        msg = ss.harden_processes()
                    self._emit("heard", f"[harden] {msg}")
                    self.say(msg)
                except Exception as e:
                    print(f"[harden] {e}")

            threading.Thread(target=_scan, daemon=True, name="jarvis-proc-scan").start()
            return self._flavor("ok", "Scanning background processes.")
        if re.search(r"\b(chris titus|winutil|windows harden guide)\b", t):
            ph = getattr(self, "process_harden", None)
            if ph is None:
                return None
            guide = ph.chris_titus_guide()
            try:
                self._emit("artifact", {"title": "WINDOWS HARDEN", "text": guide})
            except Exception:
                pass
            return self._flavor("ok", "Windows harden guide is on screen — review before running anything.")
        m = re.search(r"\b(?:kill|close) process\s+(.+)$", t)
        if m:
            ph = getattr(self, "process_harden", None)
            if ph is None:
                return None
            return self._flavor("ok", ph.kill(m.group(1).strip(" .,!?")))

        m = re.search(
            r"\b(?:translate(?:\s+to)?\s+(spanish|es|english|en)|"
            r"(spanish|english)\s+for)\s+(.+)$",
            t,
            re.I,
        )
        if m:
            from jarvis.core.slang_translate import translate_casual

            lang = (m.group(1) or m.group(2) or "es").lower()
            to = "es" if lang.startswith(("s", "es")) else "en"
            body = (m.group(3) or "").strip(" .,!?\"'")
            return self._flavor("ok", translate_casual(body, to=to))
        m = re.search(r"\b(?:expand|decode)\s+(?:acronyms?\s+)?(.+)$", t)
        if m and re.search(r"\b(acronym|slang|icymi|lmao|expand)\b", t):
            from jarvis.core.slang_translate import expand_acronyms

            return self._flavor("ok", expand_acronyms(m.group(1)))

        return None

    def _try_comms_live_cmd(self, t: str) -> str | None:
        """Live Snap / IG / iMessage translate watcher."""
        if not t:
            return None
        if re.search(
            r"\b((live\s+)?(comms|messages?)\s+(setup|status|link)|"
            r"setup\s+(live\s+)?(comms|messages?|translate)|"
            r"message\s+translate\s+(setup|status)|"
            r"(imessage|instagram|snap)\s+translate\s+(on|setup|status))\b",
            t,
        ):
            return self._flavor("ok", self.comms_live_setup_message())
        if re.search(
            r"\b((setup|open|install|link)\s+(phone\s+link|your\s+phone|link\s+to\s+windows)|"
            r"phone\s+link\s+(setup|install|open)|"
            r"setup\s+phone\s+link|"
            r"link\s+(my\s+)?(iphone|phone)\s+to\s+(windows|pc))\b",
            t,
        ):
            return self._flavor("ok", self.setup_phone_link_now())
        if re.search(
            r"\b(test\s+(live\s+)?(comms|message\s+translate|imessage\s+translate)|"
            r"simulate\s+(imessage|instagram|snap)\s+message)\b",
            t,
        ):
            return self._flavor("ok", self._test_comms_live(t))
        if re.search(
            r"\b((enable|turn\s+on|start)\s+(live\s+)?(comms|message\s+translate)|"
            r"live\s+comms\s+on|"
            r"translate\s+(my\s+)?(messages?|snaps?|texts?)\s+on)\b",
            t,
        ):
            return self._flavor("ok", self._set_comms_live_enabled(True))
        if re.search(
            r"\b((disable|turn\s+off|stop)\s+(live\s+)?(comms|message\s+translate)|"
            r"live\s+comms\s+off|"
            r"translate\s+(my\s+)?(messages?|snaps?|texts?)\s+off)\b",
            t,
        ):
            return self._flavor("ok", self._set_comms_live_enabled(False))
        m = re.search(
            r"\btranslate\s+(messages?|texts?|snaps?)\s+to\s+([a-z]{2})\b",
            t,
        )
        if m:
            return self._flavor("ok", self._set_comms_live_lang(m.group(2)))
        return None

    def _set_comms_live_enabled(self, on: bool) -> str:
        try:
            self.settings.comms_live_enabled = bool(on)
            self.settings.save()
        except Exception:
            pass
        comms = getattr(self, "comms_live", None)
        if comms is None:
            return "Live comms setting saved — restart Jarvis."
        comms.enabled = bool(on)
        if on:
            comms.start()
            return (
                "Live message translate on — Snap, Instagram, and iMessage "
                "(via Phone Link). Keep Phone Link open."
            )
        comms.stop()
        return "Live message translate off."

    def _set_comms_live_lang(self, lang: str) -> str:
        code = (lang or "en").strip().lower()[:8] or "en"
        try:
            self.settings.comms_live_target_lang = code
            self.settings.comms_live_translate = True
            self.settings.save()
        except Exception:
            pass
        comms = getattr(self, "comms_live", None)
        if comms is not None:
            comms.target_lang = code
            comms.translate = True
        return f"I'll translate live messages to `{code}`."

    def _test_comms_live(self, t: str = "") -> str:
        comms = getattr(self, "comms_live", None)
        if comms is None:
            return "Live comms bridge not loaded — restart Jarvis."
        app = "imessage"
        low = (t or "").lower()
        if "instagram" in low or " ig " in f" {low} ":
            app = "instagram"
        elif "snap" in low:
            app = "snapchat"
        samples = {
            "imessage": ("Hola, ¿cómo estás?", "Alex"),
            "instagram": ("Bonjour mon ami", "Sam"),
            "snapchat": ("Wie geht's dir?", "Jordan"),
        }
        text, sender = samples.get(app, samples["imessage"])
        # Don't use inject_test (would double-fire on_event) — enrich + handle once
        from jarvis.core.comms_live import CommsEvent

        ev = CommsEvent(
            app=app, kind="message", sender=sender, text=text, source="test"
        )
        comms._enrich(ev)
        return self.handle_comms_live(ev)

    def setup_phone_link_now(self) -> str:
        """Install/open Phone Link + notification settings + iPhone app page."""
        try:
            from jarvis.core.phone_link_setup import setup_phone_link

            msg = setup_phone_link(ensure_install=True)
        except Exception as e:
            msg = f"Phone Link setup helper failed: {e}"
        try:
            self.settings.comms_live_enabled = True
            self.settings.snapchat_calls_enabled = True
            self.settings.save()
            if getattr(self, "comms_live", None):
                self.comms_live.enabled = True
                self.comms_live.start()
            if getattr(self, "snapchat", None):
                self.snapchat.enabled = True
                self.snapchat.start()
        except Exception:
            pass
        try:
            self._emit(
                "artifact",
                {
                    "title": "PHONE LINK SETUP",
                    "text": (
                        f"{msg}\n\n"
                        "PC checklist:\n"
                        "1) Microsoft Store → Install **Phone Link** if prompted\n"
                        "2) Open Phone Link → Link your iPhone (QR / Microsoft account)\n"
                        "3) Allow notifications from Phone Link in Windows Settings\n\n"
                        "iPhone checklist:\n"
                        "1) Install **Link to Windows**\n"
                        "2) Sign in same Microsoft account · allow notifications\n"
                        "3) Keep Bluetooth/Wi‑Fi on while pairing\n\n"
                        "Then: live comms setup · test live comms · test snapchat call"
                    ),
                },
            )
        except Exception:
            pass
        try:
            self._ensure_phone_topic()
            self.phone.notify(
                "Phone Link setup started on your PC. Finish pairing in Phone Link + "
                "install Link to Windows on iPhone.",
                title="JARVIS · Phone Link",
                priority=4,
                tags=["iphone", "white_check_mark"],
            )
        except Exception:
            pass
        return (
            "I'm setting up Phone Link now — Store, app, and notification settings "
            "should be open. On your iPhone install Link to Windows and finish pairing. "
            f"{msg}"
        )

    def comms_live_setup_message(self) -> str:
        # Also kick Phone Link so one command does both
        try:
            self.setup_phone_link_now()
        except Exception:
            pass
        comms = getattr(self, "comms_live", None)
        status = comms.status() if comms else "not loaded"
        try:
            self._ensure_phone_topic()
        except Exception:
            pass
        try:
            self.settings.comms_live_enabled = True
            self.settings.save()
            if comms is not None:
                comms.enabled = True
                comms.start()
        except Exception:
            pass
        guide = (
            f"{status}\n\n"
            "LIVE TRANSLATE — Snapchat · Instagram · iMessage\n\n"
            "1) Phone Link should be opening — finish iPhone pairing.\n"
            "2) Keep Instagram / Snapchat notifications on.\n"
            "3) Jarvis reads toasts/windows, translates, speaks + HUD + phone.\n"
            "4) Say: test live comms · translate messages to es · live comms off\n\n"
            "iPhone Phone Link is mostly notifications (not full Android-style SMS mirror)."
        )
        try:
            self._emit("artifact", {"title": "LIVE COMMS · TRANSLATE", "text": guide})
        except Exception:
            pass
        return (
            "Live Snap, Instagram, and iMessage translate is on, and Phone Link setup "
            "is open. Finish pairing on the phone, then say test live comms."
        )

    def _set_snapchat_enabled(self, on: bool) -> str:
        snap = getattr(self, "snapchat", None)
        try:
            self.settings.snapchat_calls_enabled = bool(on)
            self.settings.save()
        except Exception:
            pass
        if snap is None:
            return "Snapchat setting saved — restart Jarvis to apply."
        snap.enabled = bool(on)
        if on:
            snap.start()
            return "Snapchat call watcher on. I'll notify you and try to answer."
        snap.stop()
        return "Snapchat call watcher off."

    def snapchat_setup_message(self) -> str:
        snap = getattr(self, "snapchat", None)
        if snap is None:
            return "Snapchat bridge is not loaded — restart Jarvis first."
        # Ensure phone push exists so Snap alerts reach your iPhone
        try:
            self._ensure_phone_topic()
        except Exception:
            pass
        topic = (snap.topic or "").strip()
        if not topic:
            topic = SnapchatCallBridge.make_topic()
            snap.topic = topic
            try:
                self.settings.snapchat_ntfy_topic = topic
                self.settings.snapchat_calls_enabled = True
                self.settings.save()
            except Exception:
                pass
            try:
                snap.stop()
                snap.enabled = True
                snap.start()
            except Exception:
                pass
        else:
            try:
                snap.enabled = True
                self.settings.snapchat_calls_enabled = True
                self.settings.save()
                snap.start()
            except Exception:
                pass
        url = snap.webhook_url()
        phone_topic = (getattr(self.phone, "topic", "") or "").strip()
        guide = (
            "SNAPCHAT CALLS LINKED\n\n"
            f"Status: {snap.status()}\n\n"
            "A) Alerts TO your iPhone (already on):\n"
            f"   ntfy topic `{phone_topic or '—'}` — Jarvis pushes when a Snap call is seen.\n"
            "   Say: test snapchat call\n\n"
            "B) Optional — iPhone tells Jarvis when Snap rings (Shortcut):\n"
            f"   POST {url}\n"
            "   Body text: snap call from Name\n"
            "   (Shortcuts → Automation → when you get a Snapchat notification → Get Contents of URL)\n\n"
            "C) PC auto-answer: keep Phone Link connected so the call UI can show on Windows.\n\n"
            "Commands: test snapchat call · answer snapchat · snapchat status"
        )
        try:
            self._emit(
                "artifact",
                {"title": "SNAPCHAT · PHONE LINK", "text": guide},
            )
        except Exception:
            pass
        # Push the link card to the phone they already subscribed
        try:
            if phone_topic:
                self.phone.notify(
                    f"Snapchat linked. Shortcut POST → {url}  body: snap call from Name. "
                    "Also keep Phone Link on for PC answer.",
                    title="JARVIS · Snapchat linked",
                    priority=4,
                    tags=["telephone_receiver", "white_check_mark"],
                )
        except Exception:
            pass
        return (
            f"Snapchat is linked to your phone. Alerts go to ntfy `{phone_topic}`. "
            f"Optional Shortcut topic `{topic}` — I sent the details to your iPhone. "
            "Say test snapchat call to try it."
        )

    def doorbell_setup_message(self) -> str:
        door = getattr(self, "doorbell", None)
        if door is None:
            return "Doorbell bridge is not loaded."
        topic = (door.topic or "").strip()
        if not topic:
            topic = DoorbellBridge.make_topic()
            door.topic = topic
            door.enabled = True
            try:
                self.settings.doorbell_ntfy_topic = topic
                self.settings.doorbell_ntfy_enabled = True
                self.settings.save()
            except Exception:
                pass
            try:
                door.start()
            except Exception:
                pass
        url = door.webhook_url()
        try:
            self._emit(
                "artifact",
                {
                    "title": "DOORBELL · Alexa / IFTTT",
                    "body": (
                        "1) Create a free IFTTT account and enable Webhooks.\n"
                        "2) New applet → If: Amazon Alexa (or Ring) → "
                        "doorbell pressed / routine.\n"
                        "3) Then: Webhooks → Make a web request\n"
                        f"   URL: {url}\n"
                        "   Method: POST\n"
                        "   Content Type: text/plain\n"
                        "   Body: ding\n"
                        "4) Alexa app → Routines → When doorbell pressed → "
                        "run that IFTTT applet (if using Alexa trigger).\n"
                        "5) Say: test doorbell\n"
                        f"\nStatus: {door.status()}"
                    ),
                },
            )
        except Exception:
            pass
        return (
            f"Doorbell webhook ready. In IFTTT Webhooks, POST to {url} "
            "with body ding. Say test doorbell to try the announce."
        )

    def _maybe_clarify_ambiguous(self, t: str) -> str | None:
        """
        Non-blocking multi-choice: show HUD chips, stash prompt, stop this route.
        Clicking a chip (or typing the option) continues via resolve_clarify_choice.
        """
        prompt = classify_ambiguity(t)
        if prompt is None:
            return None
        self._pending_clarify = prompt
        req_id = f"clarify-{int(time.time() * 1000) % 10_000_000}"
        self._pending_clarify_id = req_id
        payload = {
            "id": req_id,
            "kind": "clarify",
            "title": prompt.title,
            "detail": prompt.detail,
            "action": "clarify",
            "agent": "ambiguity",
            "options": list(prompt.options),
            "meta": {"async_clarify": True},
        }
        self._emit("hitl_ask", payload)
        self._emit("hud_alert", f"CLARIFY · {prompt.title}")
        for i, opt in enumerate(prompt.options, start=1):
            self._emit("heard", f"[clarify] {i}. {opt}")
        opts = "; ".join(f"{i}) {o}" for i, o in enumerate(prompt.options, start=1))
        self.say(f"{prompt.title} Choose on the HUD: {opts}")
        # Stop this route — chip click will run the concrete command
        return ""

    def _scaffold_with_preview(self, kind: str, name: str = "") -> str:
        """Create project, open browser tab + HUD site preview."""
        if not getattr(self, "scaffolder", None):
            return "Scaffolder offline."
        brand = (name or kind or "app").strip()
        try:
            self._emit(
                "site_ui",
                {"building": True, "hint": f"scaffold {kind} {brand}".strip()},
            )
        except Exception:
            pass
        result = self.scaffolder.create_project(kind, name, preview=True)
        url = (result.preview_url or "").strip()
        path = result.path
        try:
            if url:
                self._emit(
                    "site_ui",
                    {
                        "url": url,
                        "brand": brand,
                        "prompt": result.message[:160],
                        "path": str(path) if path else "",
                    },
                )
            elif path and (path / "index.html").exists():
                self._emit(
                    "site_ui",
                    {
                        "path": str(path / "index.html"),
                        "brand": brand,
                        "prompt": result.message[:160],
                    },
                )
            else:
                self._emit("site_ui", False)
        except Exception as e:
            print(f"[scaffold] site_ui: {e}")
        return result.message

    def resolve_clarify_choice(self, answer: str) -> str:
        """HUD chip / typed option → rewrite and run the real command (no busy lock)."""
        prompt = getattr(self, "_pending_clarify", None)
        self._pending_clarify = None
        self._pending_clarify_id = ""
        self._emit("hitl_clear", True)
        if prompt is None:
            return ""
        rewritten = resolve_option(prompt, answer)
        if not rewritten:
            self.say("Cancelled.")
            return "Clarify cancelled."
        self._emit("heard", f"[clarify] → {rewritten}")
        self._emit("hud_alert", f"RUN · {rewritten[:60]}")

        cmd = rewritten.strip()

        def _go() -> None:
            # Bypass handle_utterance busy lock — chip clicks / typed "1"
            # often fire while the parent utterance still holds _handling.
            try:
                self._handling = False
                try:
                    self.voice.set_busy(False)
                except Exception:
                    pass
                reply = self._route(cmd.lower())
                if reply:
                    self.say(reply)
                    self._emit("speak_ui", reply)
                else:
                    self._emit("heard", f"[clarify] done: {cmd}")
            except Exception as e:
                print(f"[clarify] run: {e}")
                try:
                    self.say(f"Could not run that: {e}")
                except Exception:
                    pass

        threading.Thread(
            target=_go, daemon=True, name="jarvis-clarify-run"
        ).start()
        return f"Running: {cmd}"

    def _try_stark_cmd(self, t: str) -> str | None:
        """Cognitive roles, protocols, workshop, packages, briefings, cron."""
        if not t:
            return None

        # Iconic Stark arrival — replay anytime
        if re.search(
            r"\b(daddy'?s\s+home|daddys\s+home|i'?m\s+home|"
            r"tony'?s\s+home|stark\s+arrival|home\s+sequence)\b",
            t,
        ):
            threading.Thread(
                target=self._run_stark_arrival,
                daemon=True,
                name="stark-arrival-cmd",
            ).start()
            return self._flavor(
                "ok",
                "Daddy's home — Jarvis online, then Shoot to Thrill.",
            )

        # DUME / pushback easter eggs (before normal routing)
        cog = getattr(self, "cognitive", None)
        push = None
        if cog:
            dume = cog.dume_if_ridiculous(t)
            if dume:
                return self._flavor("ok", dume)
            push = cog.maybe_pushback(t)

        # Named protocols / lore triggers
        proto = getattr(self, "protocols", None)
        if proto:
            hit = proto.try_handle(t)
            if hit:
                # Late-night quieter flavor
                try:
                    if proto.late_night_style() == "quiet" and len(hit) > 160:
                        hit = hit[:160].rstrip() + "…"
                except Exception:
                    pass
                return self._flavor("ok", hit)

        if cog and re.search(r"\bcognitive (status|role|core)\b", t):
            return self._flavor("ok", cog.status())
        m = re.search(
            r"\b(?:set|use|switch to)\s+(?:cognitive\s+)?role\s+(?:to\s+)?(\w+)",
            t,
        )
        if m and cog:
            return self._flavor("ok", cog.set_role(m.group(1)))
        if cog and push:
            # Soft challenge only — return pushback as the reply for reckless asks
            if re.search(
                r"\b(force push|no tests|skip backup|yolo|hardcode the password|delete everything)\b",
                t,
            ):
                return self._flavor("ok", push)

        if re.search(
            r"\b(tactical briefing|casual briefing|blind\s*spot briefing|"
            r"risk briefing)\b",
            t,
        ):
            mode = "tactical"
            if "casual" in t:
                mode = "casual"
            elif "blind" in t or "risk" in t:
                mode = "blindspot"
            line = self.briefings.compose(force_mode=mode)
            self.feed.push("brief", line[:180])
            return self._flavor("ok", line)
        if re.search(r"\bbriefing (protocol )?status\b", t):
            return self._flavor("ok", self.briefings.status())

        if re.search(r"\b(cron status|micro[- ]?agents?|background agents?)\b", t):
            return self._flavor("ok", self.cron.status())

        # Hologram HUD / LiveKit / Pinecone / Anthropic CU
        if re.search(
            r"\b(open (the )?(stark )?(fabricator|jet lab|suit lab)|"
            r"stark (jet |lab )?(hologram|fabricator)|"
            r"suit (fabricator|customizer|upgrades?)|"
            r"edith (lab|interface)|phaser web)\b",
            t,
        ):
            self._emit("fabricator_ui", True)
            # Workshop ambience on Spotify while the lab is open
            try:
                threading.Thread(
                    target=self.music.play_workshop,
                    daemon=True,
                    name="workshop-music",
                ).start()
                self._emit("track", "Iron Man workshop")
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Stark fabricator online — Iron Man workshop music on Spotify. "
                "Tune upgrades, install modules, then say build the suit.",
            )
        if re.search(
            r"\b((build|fabricate|print|weave) (the |my |a )?(suit|spider[- ]?suit|upgraded suit)|"
            r"slap (to )?build|start (suit )?fabrication)\b",
            t,
        ):
            self._emit("fabricator_ui", True)
            self._emit("fabricator_build", True)
            return self._flavor(
                "ok",
                "Engaging fabricator print cycle — laser scan, then polymer weave.",
            )
        if re.search(
            r"\b(close (the )?(stark )?(fabricator|jet lab|suit lab)|"
            r"close (suit|hologram) lab)\b",
            t,
        ):
            self._emit("fabricator_ui", False)
            return self._flavor("ok", "Fabricator lab closed.")
        if re.search(
            r"\b(open (the )?hologram|hologram (hud|dashboard)|open hub dashboard)\b",
            t,
        ):
            # Prefer in-HUD Stark lab; hub URL remains available via "hub dashboard"
            if "hub" in t or "dashboard" in t:
                url = getattr(self.settings, "hologram_url", "") or "http://127.0.0.1:3000"
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                return self._flavor(
                    "ok",
                    f"Opening hologram HUD at {url}. Run npm run dev in hub/dashboard if offline.",
                )
            self._emit("fabricator_ui", True)
            return self._flavor(
                "ok",
                "Opening Stark hologram lab on camera. Say hub dashboard for the web HUD.",
            )
        # AR Aerospatial Mapping — room mesh + fabricator hologram overlay
        if re.search(
            r"\b(open (the )?(aerospatial|ar map|spatial mesh|ar (lab|overlay|engine))|"
            r"aerospatial (on|online)|start (aerospatial|room mapping)|"
            r"augmented reality (map|overlay|hologram))\b",
            t,
        ):
            self._emit("aerospatial_ui", True)
            self._emit("camera_ui", True)
            return self._flavor(
                "ok",
                "Aerospatial mapping online — scanning room geometry so the Fabricator "
                "can sit on your desk. Say scan room for a laser pass, or aerospatial setup "
                "for desktop, smart-mirror, and phone deploy.",
            )
        if re.search(
            r"\b((laser )?scan (the )?room|map (the )?room|start (laser )?scan|"
            r"aerospatial scan)\b",
            t,
        ):
            self._emit("aerospatial_ui", True)
            self._emit("aerospatial_scan", True)
            return self._flavor(
                "ok",
                "Laser scan engaged — mapping floor, desk, and walls for hologram lock.",
            )
        if re.search(
            r"\b(aerospatial|ar) (deploy )?(desktop|monitor|mirror|smart mirror|phone|mobile)\b",
            t,
        ):
            mode = "desktop"
            if "mirror" in t:
                mode = "mirror"
            elif "phone" in t or "mobile" in t:
                mode = "phone"
            self._emit("aerospatial_ui", True)
            self._emit("aerospatial_deploy", mode)
            hints = {
                "desktop": "Desktop deploy — point the webcam at the room; hologram overlays on the monitor.",
                "mirror": "Smart mirror deploy — one-way glass at 45 degrees; hologram floats mid-air.",
                "phone": "Phone deploy — use a Unity AR Foundation template; tap to place the Fabricator.",
            }
            return self._flavor("ok", hints[mode])
        if re.search(
            r"\b(aerospatial setup|ar setup|how (do i|to) (do )?aerospatial|"
            r"spatial meshing (setup|guide)|ar foundation setup)\b",
            t,
        ):
            from jarvis.core.aerospatial import SETUP_GUIDE

            try:
                self._emit(
                    "artifact",
                    {"title": "AR AEROSPATIAL SETUP", "text": SETUP_GUIDE},
                )
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Aerospatial setup is on screen. Desktop webcam overlay works now; "
                "mirror uses one-way glass; phone uses Unity AR Foundation. "
                "Say open aerospatial to start mapping.",
            )
        if re.search(r"\b(aerospatial status|ar (map )?status|mesh status)\b", t):
            try:
                from jarvis.core.aerospatial import AerospatialMapper

                return self._flavor("ok", AerospatialMapper().status())
            except Exception as e:
                return self._flavor("warn", f"Aerospatial status unavailable: {e}")
        if re.search(
            r"\b(close (the )?(aerospatial|ar map|spatial mesh|ar (lab|overlay))|"
            r"aerospatial (off|offline)|close ar)\b",
            t,
        ):
            self._emit("aerospatial_ui", False)
            return self._flavor("ok", "Aerospatial overlay closed.")
        if re.search(
            r"\b(cinematic (ar|aerospatial|hologram)|smooth (ar|tracking|hologram)|"
            r"fix (ar )?jitter|anti[- ]?jitter)\b",
            t,
        ):
            self._emit("aerospatial_ui", True)
            self._emit("aerospatial_cinematic", True)
            return self._flavor(
                "ok",
                "Cinematic AR on — lerp smoothing, light adapt, matched camera FPS. "
                "Add a textured mousepad if the desk is blank white or black.",
            )
        if re.search(r"\b(raw ar|disable cinematic|cinematic off)\b", t):
            self._emit("aerospatial_cinematic", False)
            return self._flavor("ok", "Cinematic smoothing off.")
        if re.search(
            r"\b(ar biometric|biometric (ar )?scan|welcome scan|sit down scan)\b",
            t,
        ):
            self._emit("aerospatial_ui", True)
            self._emit("aerospatial_biometric", True)
            return self._flavor(
                "ok",
                "Biometric scan overlay armed — look at the camera for identity lock.",
            )
        if re.search(r"\b(ar gauges|pc (health )?hologram|holographic (cpu|gpu|stats))\b", t):
            self._emit("aerospatial_ui", True)
            self._emit("aerospatial_gauges", True)
            return self._flavor("ok", "PC health gauges on the AR overlay.")
        if re.search(r"\b(web shooter|spider[- ]?web|shoot web)\b", t):
            self._emit("aerospatial_ui", True)
            self._emit("aerospatial_web", True)
            return self._flavor(
                "ok",
                "Web shooter armed — tuck middle and ring fingers, extend thumb, "
                "index, and pinky to fire a web at the room mesh.",
            )
        if re.search(r"\b(live ?voice status|livekit status|elevenlabs turbo)\b", t):
            return self._flavor("ok", self.live_voice.status())
        if re.search(r"\b(pinecone status|hybrid memory status)\b", t):
            return self._flavor("ok", self.pinecone.status())
        m = re.search(
            r"\bset\s+pinecone\s+(?:api\s+)?key\s+to\s+(\S.+)$", t, re.I
        )
        if m:
            key = self._capture_secret(
                r"\bset\s+pinecone\s+(?:api\s+)?key\s+to\s+(\S.+)$", m.group(1)
            )
            self.settings.pinecone_api_key = key
            self.pinecone.api_key = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Pinecone API key vaulted.")
        m = re.search(
            r"\bset\s+pinecone\s+(?:index\s+)?host\s+to\s+(\S+)\s*$", t, re.I
        )
        if m:
            host = m.group(1).strip().rstrip(".,")
            self.settings.pinecone_index_host = host
            self.pinecone.index_host = host.rstrip("/")
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", f"Pinecone index host set to {host}.")
        m = re.search(
            r"\bset\s+obsidian\s+vault\s+(?:(?:path|folder)\s+)?(?:to\s+)?(.+)$",
            t,
            re.I,
        )
        if m:
            from pathlib import Path

            path = m.group(1).strip().strip("\"'").rstrip(".,")
            p = Path(path).expanduser()
            if not p.exists():
                return self._flavor(
                    "error",
                    f"That path doesn't exist yet: {p}. Create the vault in Obsidian first.",
                )
            self.settings.obsidian_vault_path = str(p.resolve())
            self.settings.obsidian_vault_name = p.name
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                f"Obsidian vault set to {p.name}. Research notes will land in Jarvis/.",
            )
        if re.search(r"\b(obsidian vault status|which obsidian vault)\b", t):
            vault = (getattr(self.settings, "obsidian_vault_path", None) or "").strip()
            if vault:
                return self._flavor("ok", f"Obsidian vault: {vault}")
            return self._flavor(
                "ok",
                "No Obsidian vault configured — say set obsidian vault to YOUR_PATH.",
            )
        if re.search(
            r"\b(computer use anthropic|use anthropic computer use|"
            r"anthropic computer use)\b",
            t,
        ):
            try:
                self.settings.computer_use_provider = "anthropic"
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Computer-use provider set to Anthropic (computer + editor + bash parity). "
                "Say computer use: <goal> when ready.",
            )
        if re.search(r"\b(enable elevenlabs turbo|prefer elevenlabs)\b", t):
            self.settings.tts_prefer_elevenlabs = True
            self.settings.elevenlabs_model = "eleven_turbo_v2_5"
            try:
                self.settings.save()
            except Exception:
                pass
            self.live_voice.model = "eleven_turbo_v2_5"
            return self._flavor(
                "ok",
                "ElevenLabs turbo preferred for low-latency speech. "
                + self.live_voice.status(),
            )

        # Packages
        if re.search(
            r"\b(where'?s my (package|parcel|tech|order)|package status|"
            r"shipment status|tracking status)\b",
            t,
        ):
            return self._flavor("ok", self.packages.where_is_my_package())
        m = re.search(
            r"\b(?:track(?:ing)?(?:\s+package)?|add package)\s+([A-Za-z0-9]{8,})\b",
            t,
            re.I,
        )
        if m:
            return self._flavor("ok", self.packages.add(m.group(1)))
        parsed = self.packages.parse_and_add(t)
        if parsed and re.search(r"\b(track|package|shipping|ups|fedex|usps|tba)\b", t):
            return self._flavor("ok", parsed)

        # Workshop inventory
        if re.search(
            r"\b(workshop stock|what(?:'s| is) in (the )?workshop|"
            r"what do we have in stock|inventory status)\b",
            t,
        ):
            q = ""
            m = re.search(r"\b(?:stock|inventory)\s+(?:for\s+)?(.+)$", t)
            if m:
                q = m.group(1).strip(" .,!?")
            return self._flavor("ok", self.workshop.stock(q))
        m = re.search(
            r"\b(?:register|log)\s+(?:part|component|item)\s+(.+)$",
            t,
        )
        if m:
            return self._flavor("ok", self.workshop.register(m.group(1).strip(" .,!?")))
        if re.search(r"\b(register (this |the )?scan|log (this )?part|add to workshop)\b", t):
            # Use last vision/scan blurb if any
            note = ""
            try:
                note = getattr(self, "_last_scan_text", "") or ""
            except Exception:
                note = ""
            if not note:
                return self._flavor(
                    "ok",
                    "Show me the part on camera and scan it first, then say register this scan.",
                )
            return self._flavor("ok", self.workshop.register_from_scan(note))
        if re.search(r"\b(synergy check|compatibility check)\b", t):
            msg = self.workshop.synergy_check() or "No conflicting parts in this session yet."
            return self._flavor("ok", msg)
        m = re.search(r"\b(?:source|price|buy)\s+(?:part\s+)?(.+)$", t)
        if m and re.search(r"\b(source|market|buy|price)\b", t):
            return self._flavor("ok", self.workshop.market_hint(m.group(1).strip(" .,!?")))
        if re.search(r"\b(clear workshop session)\b", t):
            return self._flavor("ok", self.workshop.clear_session())

        # Solar / horizon easter injection
        if re.search(r"\b(solar (flare|radiation)|space weather)\b", t):
            return self._flavor(
                "ok",
                "Sir, solar radiation chatter is elevated on the open feeds — "
                "do not be alarmed if local networks experience light latency.",
            )

        return None

    def _try_autonomy_cmd(self, t: str) -> str | None:
        """Healer, scaffold, research jobs, git safety, whisper, IoT, memory."""
        if not t:
            return None

        # Whisper / soft speak
        if re.search(r"\b(whisper mode|soft speak|quiet voice)\s+on\b", t):
            self.settings.whisper_mode = True
            try:
                self.voice.set_whisper_mode(
                    True, volume=str(getattr(self.settings, "whisper_volume", "-20%"))
                )
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Whisper mode on — I'll keep my voice down.")
        if re.search(r"\b(whisper mode|soft speak|quiet voice)\s+off\b", t):
            self.settings.whisper_mode = False
            try:
                self.voice.set_whisper_mode(False)
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Whisper mode off — normal volume.")

        # Healer
        if re.search(r"\bhealer status\b|\b(pc |system )?healer\b", t) and not re.search(
            r"\b(kill|terminate|ignore)\b", t
        ):
            if not getattr(self, "healer", None):
                return self._flavor("ok", "Healer offline.")
            return self._flavor("ok", self.healer.status())
        if re.search(r"\bhealer (kill|terminate)( top)?\b|\bkill top process\b", t):
            if not getattr(self, "healer", None):
                return self._flavor("ok", "Healer offline.")
            if getattr(self, "gitbot", None):
                try:
                    self.gitbot.snapshot("pre-healer-kill")
                except Exception:
                    pass
            return self._flavor("ok", self.healer.kill_top())
        if re.search(r"\bhealer (kill|terminate) pending\b|\bhealer kill\b", t):
            if not getattr(self, "healer", None):
                return self._flavor("ok", "Healer offline.")
            return self._flavor("ok", self.healer.kill_hog())
        if re.search(r"\bhealer ignore\b", t):
            if getattr(self, "healer", None):
                self.healer.clear_pending()
            return self._flavor("ok", "Ignoring the process.")

        # Git safety
        if re.search(r"\b(safety snapshot|git snapshot|snapshot (repo|code))\b", t):
            if not getattr(self, "gitbot", None):
                return self._flavor("ok", "Git bot offline.")
            return self._flavor("ok", self.gitbot.snapshot("manual"))
        if re.search(r"\b(revert (last )?snapshot|rollback snapshot)\b", t):
            if not getattr(self, "gitbot", None):
                return self._flavor("ok", "Git bot offline.")
            return self._flavor("ok", self.gitbot.revert_last_snapshot())
        if re.search(r"\blast (git )?snapshot\b", t):
            if not getattr(self, "gitbot", None):
                return self._flavor("ok", "Git bot offline.")
            return self._flavor("ok", self.gitbot.last_snapshot())

        # Scaffold
        m = re.search(
            r"\bscaffold\s+(react|vite|python|py|html|site|static)"
            r"(?:\s+(?:app|project|package|site))?(?:\s+(?:named|called)\s+(\S+))?",
            t,
        )
        if m and getattr(self, "scaffolder", None):
            kind = m.group(1)
            name = (m.group(2) or "").strip()
            if getattr(self, "gitbot", None):
                try:
                    self.gitbot.snapshot("pre-scaffold")
                except Exception:
                    pass
            return self._flavor("ok", self._scaffold_with_preview(kind, name))
        if re.search(r"\bscaffold status\b", t) and getattr(self, "scaffolder", None):
            return self._flavor("ok", self.scaffolder.status())

        # Publish scaffolded React app (production build + preview)
        m = re.search(
            r"\b(?:publish|ship|deploy)\s+(?:the\s+)?(?:scaffold(?:ed)?\s+)?(?:react\s+)?(?:app|project|site|hub)\b"
            r"(?:\s+(?:named|called)\s+(\S+))?",
            t,
        )
        if m and getattr(self, "scaffolder", None):
            name = (m.group(1) or "").strip()
            return self._flavor("ok", self.scaffolder.publish(name))
        if re.search(r"^\s*(publish|ship)\s+(app|it|this)\s*$", t) and getattr(
            self, "scaffolder", None
        ):
            return self._flavor("ok", self.scaffolder.publish())

        # App scoreboard
        if re.search(
            r"\b(app scores?|scoreboard|leaderboard|pulse scores?|how('?s| is) (my |the )?app(s)? (doing|scoring))\b",
            t,
        ):
            return self._flavor("ok", app_scores.summary())
        m = re.search(r"\b(?:scores? for|app score)\s+(.+)$", t)
        if m:
            return self._flavor("ok", app_scores.app_detail(m.group(1).strip(" .,!?")))

        # Personality forge — synthetic data, Axolotl LoRA, TRL DPO
        forge = getattr(self, "forge", None)
        if forge and re.search(
            r"\b(personality forge status|forge status|training data status)\b", t
        ):
            return self._flavor("ok", forge.status())
        if forge and re.search(
            r"\b(generate personality (data(set)?|training data)|"
            r"forge personality (data|dataset)|build (a )?personality dataset|"
            r"create (synthetic )?training (data|conversations))\b",
            t,
        ):
            # Default 2000; allow "generate personality dataset 5000"
            count = 2000
            mcount = re.search(r"\b(\d{3,5})\b", t)
            if mcount:
                count = int(mcount.group(1))
            line = forge.generate(
                count=count,
                honorific=getattr(self.settings, "user_name", None) or "Sir",
                british=True,
            )
            self.feed.push("forge", line[:200])
            return self._flavor("ok", line)
        if forge and re.search(
            r"\b(harvest (rlhf|feedback)( for training)?|pull rlhf into (the )?forge)\b",
            t,
        ):
            return self._flavor("ok", forge.harvest_from_rlhf())
        if forge and re.search(
            r"\b(export (axolotl|training) config|refresh (axolotl|dpo) config)\b",
            t,
        ):
            return self._flavor("ok", forge.ensure_configs())
        if forge and re.search(
            r"\b(start dpo( training)?|train (with )?dpo|run dpo|trl dpo)\b", t
        ):
            return self._flavor("ok", forge.try_launch_trl())
        if forge and re.search(
            r"\b(train personality|fine[- ]?tune (jarvis|personality)|"
            r"start (lora|axolotl|qlora)( training)?)\b",
            t,
        ):
            return self._flavor("ok", forge.train_hint(backend="axolotl"))

        # Background web research (explicit only)
        m = re.search(r"\bbackground research\s+(.+)$", t)
        if m:
            return self._flavor("ok", self._start_research_job(m.group(1).strip(" .,!?")))
        m = re.search(r"\bresearch in background\s+(.+)$", t)
        if m:
            return self._flavor("ok", self._start_research_job(m.group(1).strip(" .,!?")))
        m = re.search(
            r"\b(?:find|research)\s+(.+?)\s+and (?:notify|tell) me\b",
            t,
        )
        if m:
            return self._flavor("ok", self._start_research_job(m.group(1).strip(" .,!?")))

        # Memory consolidate now
        if re.search(r"\b(consolidate memory|memory consolidate|overnight memory)\b", t):
            if not getattr(self, "memory_night", None):
                return self._flavor("ok", "Memory consolidator offline.")
            return self._flavor("ok", self.memory_night.run())

        # Fix clipboard error
        if re.search(r"\b(fix|diagnose)\s+(the\s+)?clipboard error\b", t):
            snip = getattr(self, "_last_clip_error", "") or ""
            if not snip:
                return self._flavor(
                    "ok", "No recent clipboard error. Copy a traceback first."
                )
            return self._flavor(
                "ok",
                self._start_research_job(f"Explain and fix this error:\n{snip[:800]}"),
            )

        # IoT / desk ambient LEDs
        if (
            re.search(
                r"\b(iot status|room status|presence status|nfc |room |mirror |ambient |desk light )\b",
                t,
            )
            or t.startswith("room ")
            or t.startswith("nfc ")
            or t.startswith("mirror ")
            or t.startswith("ambient ")
            or t.startswith("desk light ")
        ):
            if not getattr(self, "iot", None):
                return self._flavor("ok", "IoT bridge offline.")
            return self._flavor("ok", self.iot.handle(t))

        # Codesmith / run python in sandbox with snapshot
        m = re.search(r"\b(?:run code|codesmith|sandbox run)\s+(.+)$", t)
        if m and getattr(self, "crew", None):
            req = m.group(1).strip()
            if getattr(self, "gitbot", None):
                try:
                    self.gitbot.snapshot("pre-codesmith")
                except Exception:
                    pass
            tid = self.tasks.submit(
                f"codesmith:{req[:40]}",
                lambda r=req: self.crew.code.build_and_run(r),
            )
            return self._flavor(
                "ok",
                f"CODESMITH job {tid} queued. I'll speak when the sandbox finishes.",
            )

        return None

    def _start_research_job(self, topic: str) -> str:
        topic = (topic or "").strip()
        if len(topic) < 4:
            return "What should I research?"
        if not getattr(self, "tasks", None):
            return "Task queue offline."

        def _job() -> str:
            try:
                if getattr(self, "crew", None):
                    out = self.crew.dispatch(f"research: {topic}")
                elif getattr(self, "net", None):
                    out = self.net.answer(topic)
                else:
                    out = "No research backend."
            except Exception as e:
                out = f"Research failed: {e}"
            try:
                self._emit("hud_alert", "RESEARCH DONE")
                self._emit(
                    "artifact",
                    {"title": f"Research · {topic[:60]}", "body": str(out)[:4000]},
                )
            except Exception:
                pass
            try:
                note = self._obsidian_capture(
                    f"Research · {topic[:80]}", str(out)[:8000]
                )
                if note:
                    self.feed.push("studio", f"Obsidian note · {note}")
            except Exception:
                pass
            try:
                if getattr(self, "phone", None):
                    self.phone.notify(
                        f"Research done: {topic[:80]}",
                        title="JARVIS · research",
                        priority=4,
                    )
            except Exception:
                pass
            try:
                if hasattr(self.voice, "say_protected"):
                    self.voice.say_protected(
                        f"Research finished on {topic[:60]}. "
                        f"{str(out)[:280]}"
                    )
                else:
                    self.say(f"Research finished. {str(out)[:200]}")
            except Exception:
                try:
                    self.say(f"Research finished. {str(out)[:200]}")
                except Exception:
                    pass
            return str(out)[:2000]

        tid = self.tasks.submit(f"research:{topic[:40]}", _job)
        return (
            f"Background research job {tid} started on: {topic[:80]}. "
            "I'll notify you when it's done."
        )

    def _refresh_cloud_tokens(self) -> None:
        """Pull vaulted keys into the live CloudIntegrations object (survives mid-session saves)."""
        cloud = getattr(self, "cloud", None)
        if cloud is None:
            return
        try:
            from jarvis.core.secrets_vault import get_vault

            get_vault().merge_into(self.settings)
        except Exception:
            pass
        for attr in (
            "stripe_secret_key",
            "notion_token",
            "buffer_access_token",
            "gmail_access_token",
            "gmail_refresh_token",
            "gmail_client_id",
            "gmail_client_secret",
        ):
            val = (getattr(self.settings, attr, "") or "").strip()
            if val:
                setattr(cloud, attr, val)

    def _try_cloud_cmd(self, t: str) -> str | None:
        """Stripe / Notion / Buffer / Gmail voice intents."""
        if not t:
            return None
        cloud = getattr(self, "cloud", None)
        if cloud is None:
            return None
        self._refresh_cloud_tokens()

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

        m = re.search(r"\bset\s+gmail\s+refresh\s+token\s+to\s+(\S.+)$", t, re.I)
        if m:
            key = self._capture_secret(
                r"\bset\s+gmail\s+refresh\s+token\s+to\s+(\S.+)$",
                m.group(1),
            )
            key = re.sub(r"\s+", "", key)
            self.settings.gmail_refresh_token = key
            cloud.gmail_refresh_token = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", "Gmail refresh token saved to the vault.")

        m = re.search(
            r"\bset\s+gmail\s+client\s+id\s+to\s+(\S.+)$",
            t,
            re.I,
        )
        if m:
            key = self._capture_secret(
                r"\bset\s+gmail\s+client\s+id\s+to\s+(\S.+)$",
                m.group(1),
            )
            key = re.sub(r"\s+", "", key)
            self.settings.gmail_client_id = key
            cloud.gmail_client_id = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Gmail client id saved. Next: set gmail client secret to …, then say link gmail.",
            )

        m = re.search(
            r"\bset\s+gmail\s+client\s+secret\s+to\s+(\S.+)$",
            t,
            re.I,
        )
        if m:
            key = self._capture_secret(
                r"\bset\s+gmail\s+client\s+secret\s+to\s+(\S.+)$",
                m.group(1),
            )
            key = re.sub(r"\s+", "", key)
            self.settings.gmail_client_secret = key
            cloud.gmail_client_secret = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Gmail client secret saved to the vault. Say link gmail to authorize.",
            )

        m = re.search(
            r"\bset\s+gmail\s+(?:e-?mail|address)\s+to\s+(\S+@\S+)\s*$",
            t,
            re.I,
        )
        if m:
            addr = m.group(1).strip().rstrip(".,")
            self.settings.gmail_email = addr
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                f"Gmail email set to {addr}. Next: set gmail app password "
                "(Google App Password if 2FA is on).",
            )

        m = re.search(
            r"\bset\s+gmail\s+(?:app[- ]?)?password\s+to\s+(\S.+)$",
            t,
            re.I,
        )
        if m:
            key = self._capture_secret(
                r"\bset\s+gmail\s+(?:app[- ]?)?password\s+to\s+(\S.+)$",
                m.group(1),
            )
            self.settings.gmail_app_password = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Gmail password saved to the vault. Say clear email to empty the inbox.",
            )

        m = re.search(
            r"\bset\s+icloud\s+(?:mail\s+)?(?:e-?mail|address)\s+to\s+(\S+@\S+)\s*$",
            t,
            re.I,
        )
        if m:
            addr = m.group(1).strip().rstrip(".,")
            self.settings.icloud_email = addr
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                f"iCloud email set to {addr}. Next: set icloud password to your app-specific password.",
            )

        m = re.search(
            r"\bset\s+icloud\s+(?:app[- ]?)?password\s+to\s+(\S.+)$",
            t,
            re.I,
        )
        if m:
            key = self._capture_secret(
                r"\bset\s+icloud\s+(?:app[- ]?)?password\s+to\s+(\S.+)$",
                m.group(1),
            )
            self.settings.icloud_app_password = key
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                "iCloud app password saved to the vault. Say icloud status, then sync cash app.",
            )

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

        if re.search(
            r"\b(link|connect|setup)\s+gmail\b|\bgmail\s+setup\b|\bsetup\s+gmail\s+oauth\b",
            t,
        ):
            from jarvis.core.gmail_oauth import (
                GMAIL_REDIRECT_URI,
                GMAIL_SETUP_STEPS,
                has_gmail_oauth_client,
                run_gmail_oauth_loopback,
            )

            cid = (getattr(cloud, "gmail_client_id", "") or "").strip() or (
                getattr(self.settings, "gmail_client_id", "") or ""
            ).strip()
            secret = (getattr(cloud, "gmail_client_secret", "") or "").strip() or (
                getattr(self.settings, "gmail_client_secret", "") or ""
            ).strip()
            if has_gmail_oauth_client() or (cid and secret):
                self._emit(
                    "artifact",
                    {
                        "title": "GMAIL · OAUTH",
                        "text": (
                            "Opening Google consent in your browser.\n"
                            f"Loopback: {GMAIL_REDIRECT_URI}\n"
                            "Approve gmail.modify — Jarvis will vault tokens automatically.\n"
                        ),
                    },
                )
                try:
                    result = run_gmail_oauth_loopback(cid, secret, timeout_sec=180.0)
                except Exception as e:
                    result = {"ok": False, "error": str(e)[:160]}
                if result.get("ok"):
                    self._refresh_cloud_tokens()
                    try:
                        self.settings.save()
                    except Exception:
                        pass
                    has_rt = "with refresh" if result.get("has_refresh") else "access only"
                    return self._flavor(
                        "ok",
                        f"Gmail linked ({has_rt}). Access token will auto-renew. "
                        "Say gmail status or gmail inbox.",
                    )
                return self._flavor(
                    "error",
                    f"Gmail OAuth failed: {result.get('error') or 'unknown'}. "
                    "Say link gmail again, or check client id/secret.",
                )

            self._emit(
                "artifact",
                {
                    "title": "GMAIL · LINK (OAuth Desktop)",
                    "text": GMAIL_SETUP_STEPS,
                },
            )
            try:
                webbrowser.open("https://console.cloud.google.com/apis/library/gmail.googleapis.com")
            except Exception:
                pass
            return self._flavor(
                "ok",
                "Gmail setup is on screen. Create a Desktop OAuth client, then "
                "set gmail client id and set gmail client secret, then say link gmail again.",
            )

        if re.search(
            r"\b(link|connect|setup)\s+icloud(\s+mail)?\b|\bicloud\s+(mail\s+)?setup\b",
            t,
        ):
            self._emit(
                "artifact",
                {
                    "title": "ICLOUD MAIL · CASH APP",
                    "text": (
                        "Cash App receipts on iCloud need an app-specific password:\n"
                        "1) Open https://appleid.apple.com → Sign-In and Security\n"
                        "2) App-Specific Passwords → Generate (label: Jarvis)\n"
                        "3) Say: set icloud email to you@icloud.com\n"
                        "4) Say: set icloud password to xxxx-xxxx-xxxx-xxxx\n"
                        "5) Say: icloud status · sync cash app\n"
                    ),
                },
            )
            try:
                webbrowser.open("https://appleid.apple.com/account/manage")
            except Exception:
                pass
            return self._flavor(
                "ok",
                "iCloud Mail setup is on screen. You need an Apple app-specific password, then sync cash app.",
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
            cloud_st = cloud.gmail_status()
            try:
                from jarvis.core.gmail_imap import GmailImap

                imap = GmailImap(
                    getattr(self.settings, "gmail_email", "") or "",
                    getattr(self.settings, "gmail_app_password", "") or "",
                )
                if imap.configured():
                    return self._flavor("ok", f"{cloud_st} · {imap.status()}")
            except Exception:
                pass
            return self._flavor("ok", cloud_st)
        if re.search(r"\b(gmail\s+inbox|check\s+(my\s+)?(email|inbox|gmail))\b", t):
            return self._flavor("ok", cloud.gmail_inbox())

        # Clear / empty Gmail inbox — live feed + real archive/trash
        if re.search(
            r"\b(clear\s+(my\s+)?(email|emails|mail|inbox|gmail)|"
            r"empty\s+(my\s+)?(email|emails|mail|inbox|gmail)|"
            r"gmail\s+clear|inbox\s+zero|zero\s+(my\s+)?inbox|"
            r"delete\s+all\s+(my\s+)?(email|emails|mail)|"
            r"trash\s+all\s+(my\s+)?(email|emails|mail|inbox))\b",
            t,
        ):
            has_oauth = bool(getattr(cloud, "gmail_access_token", ""))
            has_imap = bool(
                (getattr(self.settings, "gmail_email", "") or "").strip()
                and (getattr(self.settings, "gmail_app_password", "") or "").strip()
            )
            if not has_oauth and not has_imap:
                return self._flavor(
                    "error",
                    "Gmail not linked for clear. Say link gmail, or: "
                    "set gmail email to you@gmail.com and set gmail app password to …",
                )
            mode = "trash" if re.search(r"\b(trash|delete\s+all)\b", t) else "archive"
            return self._flavor("ok", self._start_gmail_clear(mode=mode))

        return None

    def _start_gmail_clear(self, *, mode: str = "archive") -> str:
        """Run Gmail clear on a worker thread with live HUD / tools feed."""
        cloud = getattr(self, "cloud", None)

        log_lines: list[str] = [
            f"CLEAR EMAIL · mode={mode}",
            "Live feed — watching Jarvis clear your inbox…",
            "",
        ]

        def _paint() -> None:
            body = "\n".join(log_lines[-80:])
            self._emit(
                "artifact",
                {"title": "CLEAR EMAIL · LIVE", "body": body[:6000], "text": body[:6000]},
            )
            try:
                self._emit("feed", self.feed.lines_for_ui(18))
            except Exception:
                pass

        def _on_event(kind: str, text: str, meta: dict | None = None) -> None:
            line = f"[{(kind or 'info').upper()}] {text}"
            log_lines.append(line)
            try:
                self.feed.push("gmail", text[:200], meta={"phase": kind, **(meta or {})})
            except Exception:
                pass
            try:
                self._emit("hud_alert", text[:80])
                self._emit("speak_ui", f"GMAIL › {text[:140]}")
            except Exception:
                pass
            _paint()

        def _job() -> None:
            try:
                try:
                    self._emit("show_tools", True)
                except Exception:
                    pass
                try:
                    self._emit("show_ops", True)
                except Exception:
                    pass
                _on_event("start", "Engaging Gmail clear protocol…")
                # Ensure vaulted OAuth token is on the live cloud object
                try:
                    self._refresh_cloud_tokens()
                except Exception:
                    pass
                result: dict = {}
                # 1) OAuth API when token present
                if cloud and getattr(cloud, "gmail_access_token", ""):
                    try:
                        result = cloud.gmail_clear_inbox(
                            mode=mode, max_total=2000, on_event=_on_event
                        )
                        if result.get("ok") or int(result.get("cleared") or 0) > 0:
                            pass
                        else:
                            raise RuntimeError(result.get("summary") or "OAuth clear incomplete")
                    except Exception as e:
                        _on_event("warn", f"OAuth clear failed — trying IMAP… ({e})"[:160])
                        result = {}
                # 2) IMAP fallback (email + app password)
                if not result.get("ok"):
                    from jarvis.core.gmail_imap import GmailImap

                    imap = GmailImap(
                        getattr(self.settings, "gmail_email", "") or "",
                        getattr(self.settings, "gmail_app_password", "") or "",
                    )
                    if not imap.configured():
                        raise RuntimeError(
                            "No Gmail IMAP credentials. Say set gmail email / "
                            "set gmail app password, then clear email again."
                        )
                    result = imap.clear_inbox(mode=mode, on_event=_on_event)

                summary = result.get("summary") or (
                    f"Cleared {result.get('cleared', 0)} · remaining {result.get('remaining', '?')}"
                )
                self._emit(
                    "artifact",
                    {
                        "title": "CLEAR EMAIL · DONE",
                        "body": "\n".join(log_lines[-100:]) + f"\n\n{summary}",
                    },
                )
                self.say(summary[:280])
            except Exception as e:
                err = str(e)
                _on_event("error", err[:200])
                hint = ""
                if "403" in err or "Insufficient" in err or "insufficient" in err.lower():
                    hint = (
                        " Need gmail.modify OAuth or a Google App Password for IMAP."
                    )
                self.say(f"Clear email failed: {err[:160]}.{hint}")

        threading.Thread(target=_job, daemon=True, name="gmail-clear").start()
        return (
            "Clearing Gmail now — live feed is on screen. "
            + ("Trashing mail." if mode == "trash" else "Archiving out of inbox so Primary is empty.")
        )

    def _try_auto_loop_cmd(self, t: str) -> str | None:
        """Plan/Do/Check autonomous loops — walk away while it works."""
        if not t:
            return None
        engine = getattr(self, "auto_loop", None)

        if re.search(r"\b(loop status|auto loop status|loops status)\b", t):
            if engine is None:
                return self._flavor("error", "Auto-loop engine offline.")
            return self._flavor("ok", engine.status_line())

        if re.search(r"\b(stop (all )?loops?|cancel loop|halt loop)\b", t):
            if engine is None:
                return self._flavor("error", "No loop engine.")
            m = re.search(r"\bstop loop\s+([a-f0-9]{6,10})\b", t)
            lid = m.group(1) if m else ""
            return self._flavor("ok", engine.stop(lid))

        m = re.search(
            r"\bloop limits?\s+(\d+)\s+rounds?\s+(\d+)\s*(?:min|minutes?)?\b",
            t,
        )
        if m:
            self.settings.auto_loop_max_rounds = int(m.group(1))
            self.settings.auto_loop_max_minutes = float(m.group(2))
            try:
                self.settings.save()
            except Exception:
                pass
            return self._flavor(
                "ok",
                f"Loop limits set — {m.group(1)} rounds / {m.group(2)} minutes. "
                "Done still requires verification.",
            )

        m = re.search(
            r"\b(?:start |run |begin )?(?:an? )?(?:auto )?loop\s+(.+)$",
            t,
            re.I,
        )
        if not m:
            m = re.search(
                r"\b(?:work while i sleep|autonomous loop|plan do check)\s*(.*)$",
                t,
                re.I,
            )
        if m is None:
            return None
        # Avoid stealing unrelated "loop" words
        if not re.search(
            r"\b(start loop|run loop|auto loop|begin loop|work while i sleep|"
            r"plan do check|autonomous loop)\b",
            t,
        ) and not t.strip().lower().startswith("loop "):
            return None
        if engine is None:
            return self._flavor("error", "Auto-loop engine offline.")
        goal = (m.group(1) or "").strip(" .,!?")
        if not goal or goal.lower() in ("status", "limits", "stop"):
            return None
        # Strip leading verbs already matched
        goal = re.sub(
            r"^(?:for me\s+|please\s+|that\s+)?", "", goal, flags=re.I
        ).strip()
        msg = engine.start(goal)
        self.feed.push("loop", goal[:100])
        self._emit(
            "artifact",
            {
                "title": "AUTO LOOP ARMED",
                "body": f"{msg}\n\nCycle: PLAN → DO → CHECK → REPEAT\n"
                "Fake 'done' claims are rejected without evidence.",
            },
        )
        return self._flavor("ok", msg)

    def _try_work_crew_cmd(self, t: str) -> str | None:
        """Manager + research + market work agents."""
        if not t:
            return None
        wc = getattr(self, "work_crew", None)

        # Soft refresh — agents + sources + optional HUD reload
        if re.search(
            r"\b(refresh agents|reload agents|refresh (work )?crew|"
            r"refresh sources|agent refresh)\b",
            t,
        ):
            notes: list[str] = []
            crew = getattr(self, "crew", None)
            if crew is not None and hasattr(crew, "refresh"):
                try:
                    notes.append(crew.refresh())
                except Exception as e:
                    notes.append(f"crew: {e}")
            if wc is not None and hasattr(wc, "refresh"):
                try:
                    notes.append(wc.refresh())
                except Exception as e:
                    notes.append(f"work: {e}")
            try:
                from jarvis.config import Settings

                fresh = Settings.load()
                for key in (
                    "tts_rate",
                    "tts_pitch",
                    "tts_volume",
                    "tts_instant_ack",
                    "tts_chunk_sentences",
                    "tts_voice",
                    "auto_loop_max_rounds",
                    "auto_loop_max_minutes",
                    "prefer_claude_cli",
                ):
                    if hasattr(fresh, key):
                        setattr(self.settings, key, getattr(fresh, key))
                self.voice.rate = getattr(self.settings, "tts_rate", "+0%")
                self.voice.pitch = getattr(self.settings, "tts_pitch", "-2Hz")
                self.voice.volume = getattr(self.settings, "tts_volume", "+0%")
                self.voice.voice = getattr(self.settings, "tts_voice", self.voice.voice)
                self.voice.chunk_sentences = bool(
                    getattr(self.settings, "tts_chunk_sentences", True)
                )
                notes.append("settings + voice refreshed")
            except Exception:
                pass
            # Soft-reload HUD so new Python modules load
            if re.search(r"\b(reload|soft.?reload|full refresh)\b", t):
                try:
                    from jarvis.core.instance import request_reload

                    request_reload()
                    notes.append("HUD soft-reload requested")
                except Exception as e:
                    notes.append(f"reload: {e}")
            msg = " · ".join(notes) if notes else "Nothing to refresh."
            self.feed.push("agents", msg[:160])
            return self._flavor("ok", msg)

        if re.search(r"\b(soft.?reload|reload (the )?hud|reload jarvis)\b", t) and not re.search(
            r"\breload (the )?core\b", t
        ):
            try:
                from jarvis.core.instance import request_reload

                request_reload()
            except Exception as e:
                return self._flavor("error", f"Reload failed: {e}")
            return self._flavor("ok", "Soft-reload queued — back in a moment.")

        if re.search(r"\b(open agent ops|open work (crew )?dashboard|agent ops dashboard)\b", t):
            from pathlib import Path
            import webbrowser

            path = Path(__file__).resolve().parent / "data" / "agent_ops_dashboard.html"
            try:
                webbrowser.open(path.resolve().as_uri())
            except Exception as e:
                return self._flavor("error", f"Could not open Agent Ops: {e}")
            return self._flavor("ok", "Opening Agent Ops tile dashboard.")

        if re.search(r"\b(claude cli status|anthropic cli status)\b", t):
            from jarvis.core.anthropic_cli import status as cli_status

            return self._flavor("ok", cli_status())

        if wc is None:
            return None

        if re.search(r"\b(work crew|agent 5|work system)\s+status\b", t) or re.fullmatch(
            r"work crew status", t.strip()
        ):
            return self._flavor("ok", wc.status())

        m = re.search(
            r"\b(?:ask|run)\s+(?:the\s+)?"
            r"(manager|research(?:\s+agent)?|scholar|market(?:\s+agent)?|"
            r"stitch|etsy|reel|tiktok|flip|ebay|ledger|stock|trader|muse|music)"
            r"(?:\s+agent)?\s+(.+)$",
            t,
            re.I,
        )
        if m:
            agent = m.group(1)
            brief = m.group(2).strip()
            self.feed.push("work", f"{agent}: {brief[:80]}")

            def _job(a=agent, b=brief) -> str:
                try:
                    return wc.run_agent(a, b)
                except Exception as e:
                    return f"Work agent failed: {e}"

            tid = self.tasks.submit(f"work:{agent}", _job) if getattr(self, "tasks", None) else None
            if tid:
                # Also run sync for snappy HUD when CLI/LLM is fast — prefer async
                def _done() -> None:
                    try:
                        out = _job()
                        self._emit(
                            "artifact",
                            {"title": f"WORK · {agent.upper()}", "body": out[:5000]},
                        )
                        self.say(out[:280])
                    except Exception as e:
                        self.say(f"Work agent error: {e}")

                threading.Thread(target=_done, daemon=True, name=f"work-{agent}").start()
                return self._flavor(
                    "ok",
                    f"{agent} engaged on background task {tid}. Watch Agent Ops for the outcome stream.",
                )
            out = _job()
            self._emit("artifact", {"title": f"WORK · {agent.upper()}", "body": out[:5000]})
            return self._flavor("ok", out[:900])

        m = re.search(
            r"\b(?:work crew|agent 5|work system)\s+(?:run|go|start)\s+(.+)$",
            t,
            re.I,
        )
        if not m:
            m = re.search(r"\b(?:start work crew|run work crew)\s*(.*)$", t, re.I)
        if m is not None and (
            "work crew" in t or "agent 5" in t or "work system" in t or t.startswith("start work")
        ):
            brief = (m.group(1) or "").strip() or "Invent a profitable creative outcome stream for today."
            self.feed.push("work", f"MANAGER dispatch: {brief[:80]}")

            def _dispatch(b=brief) -> None:
                try:
                    out = wc.dispatch(b)
                    self._emit(
                        "artifact",
                        {"title": "WORK CREW · OUTCOME STREAM", "body": out[:6000]},
                    )
                    self.say(out[:320])
                except Exception as e:
                    self.say(f"Work crew failed: {e}")

            threading.Thread(target=_dispatch, daemon=True, name="work-dispatch").start()
            return self._flavor(
                "ok",
                "Manager is live — Research and market agents spinning up an outcome stream.",
            )
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

        # Debate menu / list (no LLM needed)
        if re.search(
            r"\b(?:crew|crude)\s+debates?\b|"
            r"\b(?:crew|crude)\s+debate\s+(?:list|topics|menu|options|help)\b|"
            r"\bwhat\s+debates?\b|"
            r"\blist\s+debates?\b",
            t,
        ) and not re.search(
            r"\bdebate\s+(?:random|tech|money|ai|career|health|gaming|home|"
            r"business|philly|philadelphia|lifestyle|\d+)",
            t,
        ) and not re.search(r"\bdebate\s+.+\?|\bdebate\s+should\b", t):
            # Bare "crew debates" / "crew debate list" → menu
            if re.search(
                r"\b(?:crew|crude)\s+debates?\s*$|"
                r"\b(?:crew|crude)\s+debate\s+(?:list|topics|menu|options|help)\b|"
                r"\b(?:what|list)\s+debates?\b",
                t,
            ):
                from jarvis.core.debate_topics import list_summary, spoken_menu

                self._emit(
                    "artifact",
                    {"title": "AGENT CREW · DEBATE MENU", "text": list_summary()},
                )
                return self._flavor("ok", spoken_menu())

        # Soft STT variants: "crude debate", "crew debates", "ask crew to debate"
        m = re.search(
            r"(?:^|\b)(?:ask\s+(?:the\s+)?crew\s+to\s+)?(?:crew|crude)\s+debates?\s+(.+)$",
            t.strip(),
            re.I,
        )
        if not m:
            m = re.search(r"^crew\s+debate\s+(.+)$", t.strip(), re.I)
        if not m:
            # Also: "debate random" / "start a debate about tech" when wake-armed
            m = re.search(
                r"^(?:start\s+a\s+)?debates?\s+(?:about\s+|on\s+)?(.+)$",
                t.strip(),
                re.I,
            )
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
                title = "AGENT CREW · DEBATE"
                if result.startswith("TOPIC"):
                    head = result.split("\n", 1)[0][:80]
                    title = f"DEBATE · {head}"
                self._emit(
                    "artifact",
                    {"title": title, "text": result},
                )
                try:
                    # Menu-only replies have no VERDICT
                    if "VERDICT:" not in result:
                        spoken = crew.debate_menu_spoken()
                        self.voice.say_protected(spoken)
                        return result[:200]
                    verdict = result.rsplit("VERDICT:", 1)[-1].strip()
                    topic_line = ""
                    if result.startswith("TOPIC"):
                        topic_line = result.split("\n", 1)[0].strip()
                    if not verdict or "LLM backend" in result:
                        spoken = "The debate chamber could not reach a verdict, sir."
                    else:
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
                        q_low = q.lower().strip()
                        library_pick = q_low in (
                            "random",
                            "surprise",
                            "any",
                            "tech",
                            "money",
                            "ai",
                            "career",
                            "lifestyle",
                            "health",
                            "gaming",
                            "home",
                            "philadelphia",
                            "philly",
                            "business",
                            "finance",
                            "gadgets",
                        ) or q_low.isdigit()
                        if library_pick and topic_line:
                            spoken = f"{topic_line}. {spoken}"
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

    def _try_systems_v2_cmd(self, t: str) -> str | None:
        """AI Systems v2 — coding verify, cloud agents, scrape, RAG."""
        if not t:
            return None
        if not re.search(
            r"\b(systems?(?:\s+v2)?|a\.?i\.?\s*systems?|swe[- ]?bench|"
            r"cloud\s+agent|langgraph|openai\s+agents?|mistweb|pydad|"
            r"agno|type[- ]?c\s+scrape|llama\s*index|tick\s+scrape|"
            r"rag\s+(?:ingest|ask|query)|sandbox\s+exec)\b",
            t,
            re.I,
        ):
            if not re.search(
                r"\b((?:mistweb\s+)?(?:scrape|aggregate)|tick\s+(?:add|list|start|stop)|"
                r"verify\s+(?:this\s+)?(?:code|patch|tests?))\b",
                t,
                re.I,
            ):
                return None

        sysv = getattr(self, "systems_v2", None)
        if sysv is None:
            if re.search(r"\b(systems?(?:\s+v2)?|a\.?i\.?\s*systems?)\b", t, re.I):
                self._boot_heavy_agents()
                return self._flavor(
                    "ok",
                    "AI Systems v2 is booting — say 'systems status' in a moment.",
                )
            return None

        if re.search(
            r"\b(systems?(?:\s+v2)?\s+status|a\.?i\.?\s*systems?\s+status|"
            r"systems?\s+probe)\b",
            t,
            re.I,
        ) or re.fullmatch(r"systems?(?:\s+v2)?", t.strip(), re.I):
            return self._flavor("ok", sysv.status())

        if re.search(
            r"\b(upgrade\s+systems?|systems?\s+upgrade|engage\s+systems?\s+v2|"
            r"enable\s+a\.?i\.?\s*systems?)\b",
            t,
            re.I,
        ):
            return self._flavor("ok", sysv.upgrade_message())

        m = re.search(r"\b(?:mistweb\s+)?(?:scrape|aggregate)\s+(.+)$", t, re.I)
        if m:
            q = m.group(1).strip(" .,!?")
            self.feed.push("mistweb", q[:80])

            def _scrape(query=q) -> None:
                try:
                    out = sysv.mist_scrape(query)
                    self._emit(
                        "artifact",
                        {"title": "MISTWEB AGGREGATION", "body": out[:6000]},
                    )
                    self.say(out[:280])
                except Exception as e:
                    self.say(f"Mistweb failed: {e}")

            threading.Thread(target=_scrape, daemon=True, name="mistweb").start()
            return self._flavor("ok", f"Mistweb scraping: {q[:80]}")

        m = re.search(r"\b(?:agno|type[- ]?c)\s+(?:scrape\s+)?(.+)$", t, re.I)
        if m and not re.search(r"\b(status|workers)\b", t, re.I):
            raw = m.group(1).strip()
            queries = [x.strip() for x in re.split(r"[;|]| and ", raw) if x.strip()]

            def _agno(qs=queries) -> None:
                try:
                    results = sysv.agno.scrape(qs)
                    items = sysv.agno.flatten(results)
                    blob = sysv.mistweb.aggregate_text(items)
                    self._emit(
                        "artifact",
                        {
                            "title": "AGNO TYPE-C SCRAPE",
                            "body": f"{len(results)} workers · {len(items)} items\n\n{blob[:5000]}",
                        },
                    )
                    self.say(f"Type-C scrape done — {len(items)} items.")
                except Exception as e:
                    self.say(f"Agno scrape failed: {e}")

            threading.Thread(target=_agno, daemon=True, name="agno-typec").start()
            return self._flavor(
                "ok",
                f"Agno Type-C workers on {len(queries)} quer{'y' if len(queries) == 1 else 'ies'}.",
            )

        if re.search(r"\btick\s+(?:list|status|jobs)\b", t, re.I):
            jobs = sysv.mistweb.tick_list()
            if not jobs:
                return self._flavor(
                    "ok",
                    "No Tick scrape jobs. Say 'tick add <query> every 60 minutes'.",
                )
            lines = [
                f"{j.job_id}: {j.query} every {int(j.interval_s)}s "
                f"({'on' if j.enabled else 'off'}) last={j.last_count}"
                for j in jobs
            ]
            return self._flavor("ok", "Tick jobs:\n" + "\n".join(lines))

        m = re.search(
            r"\btick\s+add\s+(.+?)(?:\s+every\s+(\d+)\s*(m|min|minutes|h|hr|hours|s|sec|seconds)?)?$",
            t,
            re.I,
        )
        if m:
            q = m.group(1).strip(" .,!?")
            n = int(m.group(2) or 60)
            unit = (m.group(3) or "min").lower()
            mult = 60.0
            if unit.startswith("h"):
                mult = 3600.0
            elif unit.startswith("s"):
                mult = 1.0
            interval = max(60.0, n * mult)
            job = sysv.mistweb.tick_add(q, interval_s=interval)
            return self._flavor(
                "ok",
                f"Tick job {job.job_id} — re-scrape '{q}' every {int(interval)}s.",
            )

        if re.search(r"\btick\s+start\b", t, re.I):
            sysv.mistweb.tick_start()
            return self._flavor("ok", "Tick scrape scheduler started.")
        if re.search(r"\btick\s+stop\b", t, re.I):
            sysv.mistweb.tick_stop()
            return self._flavor("ok", "Tick scrape scheduler stopped.")

        m = re.search(r"\bpydad\s+(?:extract\s+)?(.+)$", t, re.I)
        if m:
            text = m.group(1).strip()
            r = sysv.pydad.extract(text)
            body = (
                f"engine={r.engine}\n{r.summary}\n"
                f"tags: {', '.join(r.tags)}\n"
                f"entities: {len(r.entities)}"
            )
            self._emit("artifact", {"title": "PYDAD EXTRACT", "body": body[:4000]})
            return self._flavor("ok", f"Pydad ({r.engine}): {r.summary[:200]}")

        m = re.search(r"\blanggraph\s+(?:run\s+)?(.+)$", t, re.I)
        if m:
            goal = m.group(1).strip()

            def _graph(g=goal) -> None:
                try:
                    out = sysv.graph_run(g)
                    self._emit("artifact", {"title": "LANGGRAPH", "body": out[:5000]})
                    self.say(out[:280])
                except Exception as e:
                    self.say(f"LangGraph failed: {e}")

            threading.Thread(target=_graph, daemon=True, name="langgraph").start()
            return self._flavor("ok", "LangGraph running.")

        m = re.search(r"\b(?:openai\s+agents?|agents?\s+sdk)\s+(.+)$", t, re.I)
        if m:
            prompt = m.group(1).strip()

            def _oa(p=prompt) -> None:
                try:
                    out = sysv.agents_run(p)
                    self._emit(
                        "artifact",
                        {"title": "OPENAI AGENTS", "body": out[:5000]},
                    )
                    self.say(out[:280])
                except Exception as e:
                    self.say(f"Agents failed: {e}")

            threading.Thread(target=_oa, daemon=True, name="openai-agents").start()
            return self._flavor("ok", "OpenAI Agents engaged.")

        m = re.search(r"\bsandbox\s+exec\s+(.+)$", t, re.I | re.S)
        if m:
            code = m.group(1).strip()
            if code.startswith("```"):
                code = code.strip("`")
                if code.lower().startswith("python"):
                    code = code[6:].lstrip()
            r = sysv.openai_agents.sandbox_exec(code)
            body = r.get("stdout") or r.get("error") or r.get("stderr") or str(r)
            self._emit("artifact", {"title": "SANDBOX EXEC", "body": str(body)[:4000]})
            return self._flavor("ok" if r.get("ok") else "error", str(body)[:400])

        m = re.search(r"\bcloud\s+agent\s+(?:run\s+)?(.+)$", t, re.I)
        if m and not re.search(r"\bstatus\b", t, re.I):
            prompt = m.group(1).strip()

            def _cloud(p=prompt) -> None:
                try:
                    out = sysv.cloud.run(p)
                    msg = out.get("result") or out.get("error") or str(out)
                    self._emit(
                        "artifact",
                        {"title": "CLOUD AGENT", "body": str(msg)[:5000]},
                    )
                    self.say(str(msg)[:280])
                except Exception as e:
                    self.say(f"Cloud agent failed: {e}")

            threading.Thread(target=_cloud, daemon=True, name="cloud-agent").start()
            return self._flavor("ok", "Cloud Agent SDK launching.")

        if re.search(r"\bcloud\s+agent\s+status\b", t, re.I):
            return self._flavor("ok", sysv.cloud.status())

        if re.search(r"\bswe[- ]?bench\s+(?:status|verify\s+status)\b", t, re.I):
            ok, detail = sysv.swe.probe()
            return self._flavor(
                "ok",
                f"SWE-bench Verify: {'ready' if ok else 'off'} — {detail}",
            )

        if re.search(
            r"\b(swe[- ]?bench|verify\s+(?:this\s+)?(?:code|patch|tests?))\b",
            t,
            re.I,
        ):
            m = re.search(
                r"\b(?:swe[- ]?bench\s+)?verify\s+(?:this\s+)?(?:code|patch|tests?)?\s*(.*)$",
                t,
                re.I | re.S,
            )
            payload = (m.group(1) if m else "").strip()
            code, test_code = payload, None
            if "```" in payload:
                blocks = re.findall(r"```(?:python)?\s*([\s\S]*?)```", payload)
                if len(blocks) >= 2:
                    code, test_code = blocks[0], blocks[1]
                elif blocks:
                    code = blocks[0]
            if not code:
                return self._flavor(
                    "clarify",
                    "Give code to verify, or: swe-bench verify with two python fences "
                    "(solution + tests).",
                )

            def _verify(c=code, tc=test_code) -> None:
                try:
                    msg = sysv.swe_verify_code(c, tc)
                    self._emit("artifact", {"title": "SWE-BENCH VERIFY", "body": msg})
                    self.say(msg)
                except Exception as e:
                    self.say(f"Verify failed: {e}")

            threading.Thread(target=_verify, daemon=True, name="swe-verify").start()
            return self._flavor("ok", "SWE-bench verify running in sandbox.")

        m = re.search(r"\brag\s+ingest\s+(.+)$", t, re.I | re.S)
        if m:
            text = m.group(1).strip()
            did = sysv.rag.ingest(text)
            return self._flavor("ok", f"LlamaIndex RAG ingested doc {did}.")

        m = re.search(r"\brag\s+(?:ask|query)\s+(.+)$", t, re.I)
        if m:
            q = m.group(1).strip()

            def _rag(question=q) -> None:
                try:
                    out = sysv.rag_ask(question)
                    self._emit(
                        "artifact",
                        {"title": "LLAMAINDEX RAG", "body": out[:5000]},
                    )
                    self.say(out[:280])
                except Exception as e:
                    self.say(f"RAG failed: {e}")

            threading.Thread(target=_rag, daemon=True, name="llama-rag").start()
            return self._flavor("ok", "Querying data-grounded RAG.")

        if re.search(
            r"\b(llama\s*index|mistweb|pydad|agno|langgraph)\s+status\b",
            t,
            re.I,
        ):
            return self._flavor("ok", sysv.status())

        return None

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

    def set_ops_hud(self, on: bool, announce: bool = False) -> str:
        """Toggle owner-site ops map overlay beside live camera."""
        on = bool(on)
        self._ops_hud_on = on
        pins: list = []
        try:
            oh = getattr(self, "ops_hud", None)
            if oh is not None:
                pins = oh.pins()
        except Exception as e:
            print(f"[ops_hud] pins: {e}")
        try:
            self._emit("ops_hud", on)
            self._emit("ops_pins", pins)
        except Exception:
            pass
        if on:
            msg = "Ops HUD online — owner sites map."
            if announce:
                self._emit("hud_alert", "OPS HUD ONLINE")
            return msg
        msg = "Ops HUD offline."
        if announce:
            self._emit("hud_alert", "OPS HUD OFF")
        return msg

    def set_traffic_cams(self, on: bool = True, announce: bool = False) -> str:
        """Show/hide public traffic stills HUD (official DOT / 511 only)."""
        tc = getattr(self, "traffic_cams", None)
        if tc is None or not getattr(tc, "enabled", True):
            return "Traffic cams offline."
        on = bool(on)
        try:
            self._emit("traffic_cams", on)
        except Exception as e:
            print(f"[traffic_cams] emit: {e}")
        if on:
            msg = (
                f"Traffic live — {getattr(tc, 'city', 'Philadelphia')}. "
                "Opening the official map for moving video, and scanner audio "
                "(camera stills have no sound)."
            )
            if announce:
                self._emit("hud_alert", "TRAFFIC CAMS")
            return msg
        msg = "Traffic cams closed."
        if announce:
            self._emit("hud_alert", "TRAFFIC OFF")
        return msg

    def set_traffic_region(self, region: str, *, open_board: bool = True) -> str:
        """Switch traffic cam region (PHL / Miami / FL / NYC / World)."""
        tc = getattr(self, "traffic_cams", None)
        if tc is None or not getattr(tc, "enabled", True):
            return "Traffic cams offline."
        msg = tc.set_region(region)
        # Keep scanner city in sync with traffic board region when known
        try:
            sr = getattr(self, "scanner_radio", None)
            if sr is not None and hasattr(sr, "follow_traffic_region"):
                r = getattr(tc, "region", region) or region
                if str(r).lower() not in ("world", ""):
                    sr.follow_traffic_region(str(r))
        except Exception as e:
            print(f"[scanner_radio] region sync: {e}")
        try:
            self._emit("traffic_region", getattr(tc, "region", region))
        except Exception as e:
            print(f"[traffic_cams] region emit: {e}")
        if open_board:
            try:
                self._emit("traffic_cams", True)
            except Exception:
                pass
        try:
            self._emit("hud_alert", f"TRAFFIC · {getattr(tc, 'city', region).upper()}")
        except Exception:
            pass
        return msg

    def _on_danger_alert(self, kind: str, message: str, level: str = "warn") -> None:
        """Local mic impulse → HUD + speak + phone ping + home_security log."""
        kind = (kind or "impulse").strip() or "impulse"
        msg = (message or "Sudden bang on desk mic.").strip()
        level = (level or "warn").strip()
        try:
            self._emit("hud_alert", f"DANGER · {kind.upper().replace('_', ' ')}")
        except Exception:
            pass
        try:
            self.say(msg)
        except Exception as e:
            print(f"[danger_watch] say: {e}")
        # Prefer AlertDesk.blast (HUD+phone); fall back to PhoneBridge.ping
        blasted = False
        try:
            desk = getattr(self, "alert_desk", None)
            if desk is not None and getattr(desk, "enabled", True):
                desk.blast(msg, title=f"JARVIS · {kind.upper()}")
                blasted = True
        except Exception as e:
            print(f"[danger_watch] alert_desk: {e}")
        if not blasted:
            try:
                phone = getattr(self, "phone", None)
                if phone is not None:
                    phone.ping(msg, title=f"JARVIS · {kind.upper()}")
            except Exception as e:
                print(f"[danger_watch] phone: {e}")
        try:
            hs = getattr(self, "home_security", None)
            if hs is not None and hasattr(hs, "log_event"):
                hs.log_event(
                    "danger_watch",
                    msg,
                    meta={"kind": kind, "level": level, "source": "local_mic"},
                )
        except Exception as e:
            print(f"[danger_watch] home_security log: {e}")

    def set_danger_watch(self, on: bool = True) -> str:
        dw = getattr(self, "danger_watch", None)
        if dw is None:
            try:
                self.danger_watch = DangerWatch(
                    enabled=bool(on),
                    sensitivity=float(
                        getattr(self.settings, "danger_watch_sensitivity", 1.0) or 1.0
                    ),
                    cooldown_sec=float(
                        getattr(self.settings, "danger_watch_cooldown_sec", 60.0) or 60.0
                    ),
                    mic_prefer=str(getattr(self.settings, "mic_prefer", "") or "auto"),
                    on_alert=self._on_danger_alert,
                )
                dw = self.danger_watch
            except Exception as e:
                return f"Danger watch unavailable: {e}"
        try:
            self.settings.danger_watch_enabled = bool(on)
        except Exception:
            pass
        if on:
            msg = dw.start()
            try:
                self._emit("hud_alert", "DANGER WATCH ON")
            except Exception:
                pass
            return msg
        msg = dw.stop()
        try:
            self._emit("hud_alert", "DANGER WATCH OFF")
        except Exception:
            pass
        return msg

    def danger_watch_status(self) -> str:
        dw = getattr(self, "danger_watch", None)
        if dw is None:
            return "Danger watch offline (not initialized)."
        return dw.status()

    def play_traffic_audio(self) -> str:
        """Live city scanner audio (cams have no mic) + in-HUD player."""
        sr = getattr(self, "scanner_radio", None)
        if sr is None:
            return "Scanner radio offline."
        try:
            if hasattr(sr, "play_traffic_audio"):
                msg = sr.play_traffic_audio()
            else:
                msg = sr.play("dispatch")
            url = ""
            try:
                url = sr.live_audio_url() if hasattr(sr, "live_audio_url") else ""
            except Exception:
                url = getattr(sr, "_last", "") or ""
            try:
                self._emit(
                    "scanner_live",
                    {
                        "url": url,
                        "title": f"LIVE SCANNER · {getattr(sr, 'city', 'CITY')}",
                    },
                )
            except Exception as e:
                print(f"[scanner_live] emit: {e}")
            self._emit("track", "Scanner · live audio")
            return msg
        except Exception as e:
            return f"Traffic audio failed: {e}"

    def play_local_dispatch(self, kind: str = "dispatch") -> str:
        """Open public Broadcastify/LiveATC for current scanner city."""
        sr = getattr(self, "scanner_radio", None)
        if sr is None:
            return "Scanner radio offline."
        k = (kind or "dispatch").strip().lower() or "dispatch"
        try:
            self.habits.log("scanner", k)
        except Exception:
            pass
        try:
            self._emit("track", f"Scanner · {k}")
        except Exception:
            pass
        # Weather / satellite → dedicated path (honest NOAA messaging)
        if k in (
            "weather",
            "satellite",
            "noaa",
            "wx",
            "nwr",
            "satellite radio",
            "satellite audio",
            "weather radio",
            "noaa radio",
        ):
            return self.play_satellite_audio()
        return sr.play(k)

    def play_satellite_audio(self) -> str:
        """NOAA / satellite weather radio companion — not traffic-cam mics."""
        sr = getattr(self, "scanner_radio", None)
        if sr is None:
            return "Scanner radio offline."
        try:
            self.habits.log("scanner", "satellite_weather")
        except Exception:
            pass
        try:
            if hasattr(sr, "play_satellite_audio"):
                msg = sr.play_satellite_audio()
            else:
                msg = sr.play("weather")
            url = ""
            try:
                if hasattr(sr, "live_sat_url"):
                    url = sr.live_sat_url()
                else:
                    url = getattr(sr, "_last", "") or ""
            except Exception:
                url = getattr(sr, "_last", "") or ""
            try:
                self._emit(
                    "scanner_live",
                    {
                        "url": url,
                        "title": f"NOAA / SAT WEATHER · {getattr(sr, 'city', 'CITY')}",
                    },
                )
            except Exception as e:
                print(f"[scanner_live] sat emit: {e}")
            self._emit("track", "Scanner · NOAA / satellite weather (cams silent)")
            return msg
        except Exception as e:
            return f"Satellite / NOAA weather radio failed: {e}"

    def dispatch_driver(self, message: str = "") -> str:
        """Owner ntfy phone ping for own drivers — not fleet/company radio."""
        dd = getattr(self, "driver_dispatch", None)
        if dd is None:
            # Soft recreate if init race
            try:
                self.driver_dispatch = DriverDispatch(
                    phone=getattr(self, "phone", None),
                    alert_desk=getattr(self, "alert_desk", None),
                    on_hud=lambda t: self._emit("hud_alert", t),
                )
                dd = self.driver_dispatch
            except Exception as e:
                return f"Driver dispatch offline: {e}"
        msg = (message or "").strip()
        try:
            self.habits.log("driver_dispatch", msg[:40] if msg else "empty")
        except Exception:
            pass
        try:
            if hasattr(dd, "dispatch_driver"):
                return dd.dispatch_driver(msg)
            return dd.dispatch(msg)
        except Exception as e:
            return f"Driver dispatch failed: {e}"

    def open_traffic_board(self) -> str:
        tc = getattr(self, "traffic_cams", None)
        if tc is None:
            return "Traffic cams offline."
        try:
            self._emit("traffic_board", True)
        except Exception:
            pass
        return tc.open_traffic_board()

    def open_traffic_live_map(self) -> str:
        """Show embedded official 511/DOT interactive map for current region."""
        tc = getattr(self, "traffic_cams", None)
        if tc is None or not getattr(tc, "enabled", True):
            return "Traffic cams offline."
        try:
            self._emit("traffic_live_map", True)
        except Exception as e:
            print(f"[traffic_live_map] emit: {e}")
            return tc.open_traffic_board()
        try:
            self._emit("hud_alert", "LIVE TRAFFIC MAP")
        except Exception:
            pass
        city = getattr(tc, "city", "Philadelphia")
        return f"Live traffic map online — {city} official DOT / 511."

    def next_traffic_cams(self) -> str:
        """Rotate traffic board to the next page of cams."""
        tc = getattr(self, "traffic_cams", None)
        if tc is None or not getattr(tc, "enabled", True):
            return "Traffic cams offline."
        try:
            self._emit("traffic_cams_next", True)
        except Exception as e:
            print(f"[traffic_cams] next emit: {e}")
            return "Could not rotate traffic cams."
        return "Rotating traffic cams."

    def find_address_on_map(self, place: str = "") -> str:
        """Geocode a place/address and fly the tactical map (Nominatim)."""
        q = (place or "").strip()
        if not q:
            # Open map focused on home city — user can voice a place next
            city = getattr(self.settings, "city", None) or "Philadelphia"
            self._emit("map_ui", {"place": city, "markers": None, "animate": True})
            return self._flavor(
                "ok",
                f"Map online — say find address, where is, or locate a place. "
                f"Centered on {city}.",
            )
        return self._map_zoom_to(q)

    def traffic_cams_status(self) -> str:
        tc = getattr(self, "traffic_cams", None)
        if tc is None:
            return "Traffic cams offline."
        return tc.status()

    def _route_desk_hub(self, t: str) -> str | None:
        """File hub / alert desk / ops HUD / traffic cams voice intents."""
        if not t:
            return None
        # Multi-region traffic cams (official DOT / 511 only)
        if re.search(
            r"\b(miami traffic( cams?)?|show miami cams?|miami cams?)\b",
            t,
        ):
            return self._flavor("ok", self.set_traffic_region("miami"))
        if re.search(
            r"\b(florida traffic( cams?)?|fl traffic( cams?)?|show florida cams?)\b",
            t,
        ):
            return self._flavor("ok", self.set_traffic_region("florida"))
        if re.search(
            r"\b(nyc traffic( cams?)?|new york traffic( cams?)?|show nyc cams?)\b",
            t,
        ):
            return self._flavor("ok", self.set_traffic_region("nyc"))
        if re.search(
            r"\b(world traffic( cams?)?|global traffic( cams?)?)\b",
            t,
        ):
            return self._flavor("ok", self.set_traffic_region("world"))
        if re.search(
            r"\b(philly traffic|philadelphia traffic( cams?)?)\b",
            t,
        ):
            return self._flavor("ok", self.set_traffic_region("philadelphia"))
        if re.search(
            r"\b(live traffic map|traffic live map|show live traffic( map)?)\b",
            t,
        ):
            return self._flavor("ok", self.open_traffic_live_map())
        if re.search(
            r"\b(next traffic cams?|next traffic cameras?|rotate traffic cams?)\b",
            t,
        ):
            return self._flavor("ok", self.next_traffic_cams())
        if re.search(
            r"\b(open traffic board|traffic board|511(pa)?( traffic)?|philly traffic board)\b",
            t,
        ):
            return self._flavor("ok", self.open_traffic_board())
        if re.search(
            r"\b(traffic cams? status|traffic camera status)\b",
            t,
        ):
            return self._flavor("ok", self.traffic_cams_status())
        if re.search(
            r"\b(hide traffic cams?|close traffic cams?|traffic cams? off|"
            r"close (live )?traffic map|hide (live )?traffic map)\b",
            t,
        ):
            if re.search(r"\b(live )?traffic map\b", t) and not re.search(
                r"\btraffic cams?\b", t
            ):
                try:
                    self._emit("traffic_live_map", False)
                except Exception:
                    pass
                return self._flavor("ok", "Live traffic map closed.")
            return self._flavor("ok", self.set_traffic_cams(False))
        if re.search(
            r"\b(show traffic cams?|traffic cameras?|"
            r"traffic cams?( on)?)\b",
            t,
        ):
            return self._flavor("ok", self.set_traffic_cams(True))
        # Traffic / dispatch audio via public Broadcastify (DOT cams have no audio)
        if re.search(
            r"\b(listen to traffic|traffic audio|play traffic audio)\b",
            t,
        ):
            return self._flavor("ok", self.play_traffic_audio())
        if re.search(
            r"\b(police dispatch|live dispatch|put on local dispatch)\b",
            t,
        ):
            return self._flavor("ok", self.play_local_dispatch("dispatch"))
        # Truck / DOT / highway scanner (Broadcastify public listen)
        if re.search(
            r"\b((put on |play |listen to )?(truck(er)? (dispatch|radio)|"
            r"truck dispatch)|trucker radio)\b",
            t,
        ):
            return self._flavor("ok", self.play_local_dispatch("truck"))
        if re.search(r"\b(dot radio|d\.?o\.?t\.? radio)\b", t):
            return self._flavor("ok", self.play_local_dispatch("dot"))
        if re.search(r"\b(highway radio)\b", t):
            return self._flavor("ok", self.play_local_dispatch("highway"))
        if re.search(r"\b((put on |play |listen to )?(the )?cb( radio)?)\b", t):
            return self._flavor("ok", self.play_local_dispatch("cb"))
        # Owner phone → driver note (ntfy only)
        m_drv = re.search(
            r"\b(?:dispatch driver|tell the driver|send driver)\s+(.+)$",
            t,
            flags=re.I,
        )
        if m_drv:
            body = m_drv.group(1).strip(" .,!?")
            return self._flavor("ok", self.dispatch_driver(body))
        if re.search(r"\b(driver dispatch status)\b", t):
            dd = getattr(self, "driver_dispatch", None)
            if dd is None:
                return self._flavor("ok", "Driver dispatch offline.")
            return self._flavor("ok", dd.status())
        if re.fullmatch(r"\s*(dispatch driver|tell the driver|send driver)\s*", t):
            return self._flavor("ok", "What should I tell the driver?")
        # Danger / gunshot-like watch (local mic)
        if re.search(
            r"\b((danger|gunshot) watch (off|stop)|stop (danger|gunshot) watch)\b",
            t,
        ):
            return self._flavor("ok", self.set_danger_watch(False))
        if re.search(
            r"\b((danger|gunshot) watch( on)?|start (danger|gunshot) watch)\b",
            t,
        ):
            return self._flavor("ok", self.set_danger_watch(True))
        if re.search(r"\b(danger status|danger watch status)\b", t):
            return self._flavor("ok", self.danger_watch_status())
        # Address find (also caught later by _extract_map_zoom_place; early clear intent)
        m = re.search(
            r"\b(?:find\s+address|locate(?:\s+address)?|where\s+is)\s+(.+)$",
            t,
            flags=re.I,
        )
        if m:
            place = (m.group(1) or "").strip(" .,!?")
            if place and not re.search(
                r"\b(my|our)\s+(keys?|phone|wallet)\b", place, flags=re.I
            ):
                return self.find_address_on_map(place)
        # Ops HUD
        if re.search(r"\b(ops hud off|hide ops (hud|map)|close ops (hud|map))\b", t):
            return self._flavor("ok", self.set_ops_hud(False))
        if re.search(
            r"\b(ops hud( on)?|show ops (hud|map)|show (the )?ops map|"
            r"ops map( on)?)\b",
            t,
        ) or re.fullmatch(r"show map", t.strip()):
            return self._flavor("ok", self.set_ops_hud(True))
        if re.search(r"\b(ops status|ops hud status)\b", t):
            oh = getattr(self, "ops_hud", None)
            if oh is None:
                return self._flavor("ok", "Ops HUD offline.")
            return self._flavor("ok", oh.status())
        # Alert desk blasts
        desk = getattr(self, "alert_desk", None)
        if desk is not None:
            if re.search(r"\b(alert desk status|blast status)\b", t):
                return self._flavor("ok", desk.status())
            if re.search(r"\b(secure blast)\b", t):
                m = re.search(r"\bsecure blast\s+(.+)$", t)
                body = m.group(1).strip(" .,!?") if m else ""
                return self._flavor("ok", desk.secure_blast(body))
            if re.search(r"\b(intruder blast)\b", t):
                m = re.search(r"\bintruder blast\s+(.+)$", t)
                body = m.group(1).strip(" .,!?") if m else ""
                return self._flavor("ok", desk.intruder_blast(body))
            m = re.search(r"\bencrypt alert\s+(.+)$", t)
            if m:
                return self._flavor("ok", desk.encrypt_alert(m.group(1).strip(" .,!?")))
            if re.search(r"\bencrypt alert\b", t):
                return self._flavor("ok", "What should I encrypt and send?")
            m = re.search(
                r"\b(?:alert phone|send alert|desk alert|blast alert)\s+(.+)$",
                t,
            )
            if m:
                body = m.group(1).strip(" .,!?")
                if body:
                    return self._flavor("ok", desk.blast(body))
            if re.search(
                r"\b(?:alert phone|send alert|desk alert|blast alert)\b",
                t,
            ):
                return self._flavor("ok", "What alert should I blast?")
        # File hub
        fh = getattr(self, "file_hub", None)
        if fh is not None:
            if re.search(r"\b(file hub status)\b", t):
                return self._flavor("ok", fh.status())
            try:
                reply = fh.handle_voice(t)
                if reply is not None:
                    return self._flavor("ok", reply)
            except Exception as e:
                print(f"[file_hub] voice: {e}")
        return None

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
            base = self.security.status()
            try:
                hs = getattr(self, "home_security", None)
                if hs is not None:
                    extra = hs.status(
                        night_vision=bool(getattr(self, "_night_vision", False)),
                        thermal=bool(getattr(self, "_thermal_assist", False)),
                    )
                    base = f"{base} · {extra}"
            except Exception:
                pass
            return self._flavor("ok", base)
        if re.search(
            r"\b(security log|show security log|recent security events)\b", t
        ):
            hs = getattr(self, "home_security", None)
            if hs is None:
                return self._flavor("ok", "Home security log offline.")
            return self._flavor("ok", hs.speak_recent(5))
        # --- Advanced desk hub: ops HUD / alert desk / file hub ---
        hub = self._route_desk_hub(t)
        if hub is not None:
            return hub
        if re.search(
            r"\b(thermal assist off|disable (the )?thermal( assist)?|"
            r"turn(ing)? off (the )?thermal( assist)?|heat vision off|"
            r"no (thermal|heat) vision)\b",
            t,
        ):
            return self._flavor("ok", self.set_thermal_assist(False, announce=False))
        if re.search(
            r"\b(thermal assist( on)?|enable (the )?thermal( assist)?|"
            r"turn(ing)? on (the )?thermal( assist)?|heat vision( on)?)\b",
            t,
        ):
            return self._flavor("ok", self.set_thermal_assist(True, announce=False))
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

        try:
            door_reply = self._try_doorbell_cmd(t)
            if door_reply is not None:
                return door_reply
        except Exception as e:
            print(f"[doorbell] route: {e}")

        try:
            snap_reply = self._try_snapchat_cmd(t)
            if snap_reply is not None:
                return snap_reply
        except Exception as e:
            print(f"[snapchat] route: {e}")

        try:
            rem_reply = self._try_reminder_cmd(t)
            if rem_reply is not None:
                return rem_reply
        except Exception as e:
            print(f"[reminders] route: {e}")

        try:
            home_reply = self._try_home_ops_cmd(t)
            if home_reply is not None:
                return home_reply
        except Exception as e:
            print(f"[home-ops] route: {e}")

        try:
            vc_reply = self._try_voice_clone_cmd(t)
            if vc_reply is not None:
                return vc_reply
        except Exception as e:
            print(f"[voice-clone] route: {e}")

        try:
            comms_reply = self._try_comms_live_cmd(t)
            if comms_reply is not None:
                return comms_reply
        except Exception as e:
            print(f"[comms] route: {e}")

        try:
            auto_reply = self._try_autonomy_cmd(t)
            if auto_reply is not None:
                return auto_reply
        except Exception as e:
            print(f"[autonomy] route: {e}")

        try:
            adv = getattr(self, "advanced", None)
            if adv is not None:
                hit = adv.try_command(t)
                if hit is not None:
                    return self._flavor("ok", hit)
        except Exception as e:
            print(f"[advanced_ai] route: {e}")

        try:
            stark = self._try_stark_cmd(t)
            if stark is not None:
                return stark
        except Exception as e:
            print(f"[stark] route: {e}")

        # Vague command → multi-choice HUD chips (non-blocking)
        if bool(getattr(self.settings, "ambiguity_clarify", True)):
            try:
                clarified = self._maybe_clarify_ambiguous(t)
                if clarified is not None:
                    # "" = chips shown, waiting for click — do not speak "Cancelled"
                    if clarified == "":
                        return ""
                    t = clarified
            except Exception as e:
                print(f"[ambiguity] {e}")

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

        # AI Systems v2 — SWE / Cloud / LangGraph / Mistweb / RAG
        try:
            systems_reply = self._try_systems_v2_cmd(t)
            if systems_reply is not None:
                return systems_reply
        except Exception as e:
            print(f"[systems-v2] route: {e}")

        # Work Crew — Manager + Research + market outcome agents
        try:
            work_reply = self._try_work_crew_cmd(t)
            if work_reply is not None:
                return work_reply
        except Exception as e:
            print(f"[work-crew] route: {e}")

        # Autonomous Plan/Do/Check loops
        try:
            loop_reply = self._try_auto_loop_cmd(t)
            if loop_reply is not None:
                return loop_reply
        except Exception as e:
            print(f"[auto-loop] route: {e}")

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
            # Dynamic mood briefings — never the same style twice in a row
            if "good morning" in t or re.search(
                r"\b(morning brief|daily brief|standup|brief me|"
                r"cinematic (morning )?brief|morning status)\b",
                t,
            ):
                # YouTube + research tabs first (non-blocking), then brief
                tabs_note = ""
                try:
                    tabs_note = self._morning_launch_tabs()
                except Exception as e:
                    print(f"[morning] tabs: {e}")
                if re.search(r"\b(cinematic|morning status)\b", t):
                    try:
                        cinematic = getattr(self, "advanced", None)
                        if cinematic is not None:
                            spoken = cinematic.morning.run()
                            self._emit("hud_alert", "Cinematic morning briefing")
                            self.feed.push("brief", spoken[:180])
                            if tabs_note:
                                spoken = f"{spoken} {tabs_note}".strip()
                            return self._flavor("ok", spoken)
                    except Exception as e:
                        print(f"[advanced_ai] morning: {e}")
                force = ""
                if "tactical" in t:
                    force = "tactical"
                elif "casual" in t:
                    force = "casual"
                elif "blind" in t or "risk" in t:
                    force = "blindspot"
                try:
                    spoken = self.briefings.compose(mode="auto", force_mode=force)
                except Exception:
                    spoken = ""
                if not spoken:
                    wx = ""
                    try:
                        wx = self.weather.speak_brief()
                    except Exception:
                        wx = ""
                    weather_line = f"Weather: {wx}." if wx else ""
                    spoken = self.brief.morning_standup(
                        weather_line=weather_line, open_inbox=False
                    )
                greet = f"Good morning, {self.settings.user_name}."
                if spoken and not spoken.lower().startswith("good morning"):
                    spoken = f"{greet} {spoken}"
                elif not spoken:
                    spoken = greet
                if tabs_note:
                    spoken = f"{spoken} {tabs_note}".strip()
                try:
                    self.ha.on_jarvis_state("brief")
                except Exception:
                    pass
                self._emit("hud_alert", "Morning briefing ready")
                self.feed.push("brief", spoken[:180])
                return self._flavor("ok", spoken)
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

        # Spend tracking (+ Cash App)
        spent = self.spend.parse_and_add(t)
        if spent:
            self.habits.log("spend", spent[:40])
            self.feed.push("spend", spent)
            self._push_stats_ui()
            return self._flavor("ok", spent)
        if re.search(
            r"\b(sync cash\s*app|import cash\s*app|cash\s*app (from )?email|"
            r"pull cash\s*app (receipts?|spend(ing)?))\b",
            t,
        ):
            line = self._sync_cash_app_spend()
            self.feed.push("spend", line)
            self._push_stats_ui()
            return self._flavor("ok", line)
        if re.search(r"\bicloud\s+(mail\s+)?status\b", t):
            return self._flavor("ok", self._icloud_mail().status())
        if re.search(
            r"\b(cash\s*app spend(ing)?|how much (on|via|with) cash\s*app|"
            r"what(?:'s| is) my cash\s*app|"
            r"cash\s*app (today|this week|this month|summary|report))\b",
            t,
        ):
            period = "today"
            if "month" in t:
                period = "month"
            elif "week" in t:
                period = "week"
            line = self.spend.speak_cash_app(period=period)
            self.feed.push("spend", line)
            self._push_stats_ui()
            return self._flavor("ok", line)
        if re.search(
            r"\b(how much (did|have) i spend|how much (have )?i spent|"
            r"(what(?:'s| is)|show) my (spend(ing)?|expenses?)|"
            r"spending (today|this week|this month)|expense (report|summary))\b",
            t,
        ):
            period = "today"
            if "month" in t:
                period = "month"
            elif "week" in t:
                period = "week"
            line = self.spend.speak_summary(period=period)
            self.feed.push("spend", line)
            self._push_stats_ui()
            return self._flavor("ok", line)

        # Progress brief (spend + Cash App + tasks + habits + scores)
        if re.search(
            r"\b(summarize my progress|my progress|progress (report|brief|update)|"
            r"how am i doing|status report|give me (a |my )?progress)\b",
            t,
        ):
            line = self.progress.speak()
            self.habits.log("progress")
            self.feed.push("progress", line[:220])
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

        # STUDIO strip — Written / Clawed / Video / Cling / Research / Perplexity /
        # Design / Figma / Audio / 11 Labs / Images / Mid-Journey / Automation / N8N
        studio = self._studio_command(t)
        if studio is not None:
            return studio

        # Autonomous vibe coding / AI agent development
        if re.search(
            r"\b((start |do |run )?(autonomous )?(ai )?agent (development|coding|dev)|"
            r"(start |do |run )?vibe( coding|ing| code)?|"
            r"code vibe|"
            r"(build|make|create|generate|ship)\s+(me )?(an? )?(app|project|game|video|reel|trailer|tool|cli|3d|animation)|"
            r"make (me )?(a )?(game|video|reel|trailer|3d( app)?|animation)|"
            r"(start |make )(a )?3d|"
            r"autonomous (coding|development|dev))\b",
            t,
        ):
            brief = ""
            m3 = re.search(
                r"(?:vibe(?: coding|ing| code)?|agent (?:development|coding|dev)|"
                r"(?:app|project|game|video|reel|trailer|tool|cli|3d|animation))\s+(?:for|called|named)?\s*(.+)$",
                t,
            )
            if m3:
                brief = m3.group(1).strip()
            if re.search(r"\bmake (me )?(a )?game\b", t) and not brief:
                brief = "browser game with score pause restart and difficulty"
            if re.search(r"\bmake (me )?(a )?(video|reel|trailer)\b", t) and not brief:
                brief = "video slideshow reel with captions play pause and export"
            if re.search(r"\b(3d|three\.?js|webgl)\b", t) and not brief:
                brief = "3d three.js orbit scene with lighting particles and hud controls"
            if re.search(r"\b(animation|gsap|motion graphics)\b", t) and not brief:
                brief = "gsap motion graphics timeline with kinetic type and export frame"
            brief = re.sub(
                r"^(called|named|for|me|a|an|the)\s+", "", brief, flags=re.I
            ).strip()
            # Don't steal "coding mode" lights command — already handled elsewhere
            self.habits.log("vibe_code", (brief or "autonomous")[:40])
            return self._flavor("ok", self._run_vibe_code(brief=brief))

        if re.search(r"\b(publish (the )?(vibe|app|project)|ship (the )?vibe|open (the )?vibe in (cursor|ide|code))\b", t):
            path = self.vibe.last_project
            if path and path.exists():
                ide = getattr(self.settings, "work_ide", None) or "code"
                try:
                    if not self.vibe.open_in_ide(path, ide=ide):
                        return self._flavor(
                            "error",
                            "Could not open Cursor/VS Code. Install Cursor or say the path aloud.",
                        )
                except Exception as e:
                    return self._flavor("error", f"Publish failed: {e}")
                preview_url = ""
                try:
                    preview_url = self.vibe.ensure_preview_url(path) or ""
                except Exception:
                    preview_url = str((self.vibe.last_meta or {}).get("preview_url") or "")
                self._emit(
                    "code_ui",
                    {
                        "path": str(path),
                        "name": (self.vibe.last_meta or {}).get("name") or path.name,
                        "engine": (self.vibe.last_meta or {}).get("engine") or "",
                        "files": (self.vibe.last_meta or {}).get("files") or [],
                        "entry": (self.vibe.last_meta or {}).get("entry") or "",
                        "preview_url": preview_url,
                        "app_url": preview_url,
                    },
                )
                return self._flavor(
                    "ok",
                    f"Published — opening {path.name} in {ide}. Preview stays in Build Theater.",
                )
            return self._flavor("error", "No vibe project to publish yet.")

        # Open / show preview tab + reopen last app in Build Theater
        if re.search(
            r"\b("
            r"(open|show|go to|switch to)\s+(the\s+)?(app\s+)?preview(\s+tab)?|"
            r"preview\s+tab|"
            r"(open|show|go to|switch to)\s+(the\s+)?(working|coding|building|preview)\s+tab"
            r")\b",
            t,
        ):
            tab = "building"
            if re.search(r"\bcoding\s+tab\b", t):
                tab = "coding"
            elif re.search(r"\bworking\s+tab\b", t):
                tab = "working"
            preview_url = ""
            path = self.vibe.last_project
            name = ""
            if path and path.exists() and tab == "building":
                try:
                    preview_url = self.vibe.ensure_preview_url(path) or ""
                except Exception:
                    preview_url = str((self.vibe.last_meta or {}).get("preview_url") or "")
                name = (self.vibe.last_meta or {}).get("name") or path.name
                self._emit(
                    "code_ui",
                    {
                        "path": str(path),
                        "name": name,
                        "engine": (self.vibe.last_meta or {}).get("engine") or "",
                        "files": (self.vibe.last_meta or {}).get("files") or [],
                        "entry": (self.vibe.last_meta or {}).get("entry") or "",
                        "prompt": self.vibe.last_prompt or "",
                        "preview_url": preview_url,
                        "app_url": preview_url,
                    },
                )
            self._emit("theater_tab", {"tab": tab, "preview_url": preview_url})
            labels = {
                "working": "Working",
                "coding": "Coding",
                "building": "Preview",
            }
            if tab == "building" and preview_url:
                return self._flavor("ok", f"Opening {labels[tab]} — {preview_url}")
            return self._flavor("ok", f"Switching to the {labels[tab]} tab.")

        if re.search(r"\b(open (the |my )?(vibe|project|code) you (built|made)|show (the )?vibe)\b", t):
            path = self.vibe.last_project
            if path and path.exists():
                meta = self.vibe.last_meta or {}
                preview_url = ""
                try:
                    preview_url = self.vibe.ensure_preview_url(path) or ""
                except Exception:
                    preview_url = str(meta.get("preview_url") or "")
                self._emit(
                    "code_ui",
                    {
                        "path": str(path),
                        "name": meta.get("name") or path.name,
                        "engine": meta.get("engine") or "",
                        "files": meta.get("files") or [],
                        "entry": meta.get("entry") or "",
                        "prompt": self.vibe.last_prompt or "",
                        "preview_url": preview_url,
                        "app_url": preview_url,
                    },
                )
                return self._flavor(
                    "ok",
                    f"Opening {(meta.get('name') or path.name)} in Build Theater Preview."
                    + (f" {preview_url}" if preview_url else ""),
                )
            return self._flavor("error", "No vibe project yet — say start vibe coding.")

        if re.search(r"\b(list (vibe )?projects|what (apps|projects) did you (build|make))\b", t):
            return self._flavor("ok", self.vibe.list_projects())

        if re.search(r"\b(close (the )?(vibe|code)( panel| preview)?)\b", t):
            self._emit("code_ui", False)
            return self._flavor("ok", "Closing the vibe panel.")

        if re.search(r"\b(open (the |my )?(website|site) you built|show (the )?website)\b", t):
            path = self.sites.last_site
            if path and path.exists():
                preview_url = ""
                try:
                    site_root = path.parent if path.is_file() else path
                    preview_url = self.vibe.ensure_preview_url(site_root) or ""
                except Exception:
                    pass
                self._emit(
                    "site_ui",
                    {
                        "path": str(path),
                        "brand": (self.sites.last_content or {}).get("brand") or "",
                        "prompt": self.sites.last_prompt or "",
                        "preview_url": preview_url,
                        "url": preview_url,
                    },
                )
                return self._flavor(
                    "ok",
                    f"Opening site preview in Build Theater."
                    + (f" {preview_url}" if preview_url else ""),
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

        # Local dispatch / scanner (Broadcastify public feeds — listen only)
        if re.search(
            r"\b(stop (the )?(scanner|dispatch|police radio|sdr|rtl|"
            r"weather radio|satellite radio|noaa)|"
            r"stop dispatch)\b",
            t,
        ):
            return self._flavor("ok", self.scanner_radio.stop())
        if re.search(r"\b(scanner status|dispatch status)\b", t):
            return self._flavor("ok", self.scanner_radio.status())
        if re.search(
            r"\b(satellite radio|satellite audio|noaa( weather)? radio|"
            r"weather radio|play satellite|put on (the )?satellite|"
            r"listen to (the )?(satellite|noaa|weather) radio)\b",
            t,
        ):
            self.habits.log("scanner", "satellite_weather")
            return self._flavor("ok", self.play_satellite_audio())
        if re.search(
            r"\b(listen to traffic|traffic audio|play traffic audio|"
            r"hear (the )?traffic|traffic (radio|scanner))\b",
            t,
        ):
            self.habits.log("scanner", "traffic_audio")
            return self._flavor("ok", self.play_traffic_audio())
        if re.search(
            r"\b((put on|play|tune|open|listen to) (the )?(local )?sdr|"
            r"rtl[- ]?sdr|software defined radio)\b",
            t,
        ):
            self.habits.log("scanner", "sdr")
            return self._flavor("ok", self.scanner_radio.play_rtl())
        m_scan = re.search(
            r"\b(?:put on|play|tune|open|listen to|pull up)\s+(?:the\s+)?"
            r"(local\s+dispatch|police\s+radio|police\s+dispatch|live\s+dispatch|"
            r"fire\s+dispatch|ems(?:\s+dispatch)?|"
            r"truck(?:er)?\s+(?:dispatch|radio)|truck\s+dispatch|dot\s+radio|"
            r"highway\s+radio|cb(?:\s+radio)?|"
            r"air\s+traffic(?:\s+control)?|aviation(?:\s+radio)?|scanner|"
            r"weather\s+radio|satellite\s+radio|satellite\s+audio|noaa\s+radio|"
            r"dispatch)\b",
            t,
        )
        if m_scan or re.search(
            r"\b(local dispatch|police radio|police dispatch|live dispatch|"
            r"truck(er)? radio|truck dispatch|dot radio|highway radio|cb radio|"
            r"fire scanner|scanner feed)\b",
            t,
        ):
            phrase = (m_scan.group(1) if m_scan else "dispatch").lower()
            kind = "dispatch"
            if "police" in phrase:
                kind = "police"
            elif "fire" in phrase:
                kind = "fire"
            elif "ems" in phrase:
                kind = "ems"
            elif "truck" in phrase:
                kind = "truck"
            elif "dot" in phrase:
                kind = "dot"
            elif "highway" in phrase:
                kind = "highway"
            elif re.search(r"\bcb\b", phrase):
                kind = "cb"
            elif "air" in phrase or "aviation" in phrase or "atc" in phrase:
                kind = "aviation"
            elif "satellite" in phrase or "noaa" in phrase or "weather" in phrase:
                kind = "weather"
            elif "scanner" in phrase:
                kind = "scanner"
            return self._flavor("ok", self.play_local_dispatch(kind))

        # Owner driver note (ntfy phone) — late catch if early lane missed
        m_drv2 = re.search(
            r"\b(?:dispatch driver|tell the driver|send driver)\s+(.+)$",
            t,
            flags=re.I,
        )
        if m_drv2:
            return self._flavor(
                "ok", self.dispatch_driver(m_drv2.group(1).strip(" .,!?"))
            )

        # Local desk mic danger / gunshot-like bang watch (opt-in)
        if re.search(
            r"\b((danger|gunshot) watch (off|stop)|stop (danger|gunshot) watch)\b",
            t,
        ):
            return self._flavor("ok", self.set_danger_watch(False))
        if re.search(
            r"\b((danger|gunshot) watch( on)?|start (danger|gunshot) watch|"
            r"arm (danger|gunshot) watch)\b",
            t,
        ):
            return self._flavor("ok", self.set_danger_watch(True))
        if re.search(r"\b(danger status|danger watch status|gunshot watch status)\b", t):
            return self._flavor("ok", self.danger_watch_status())

        # Local-only code customize (never remote public sites)
        if re.search(
            r"\b((change|tweak|fix|update|modify) (the )?(layout|design|css|style) "
            r"(of )?(my |the )?(website|site|app|page|project)|"
            r"edit (my |the )?(local )?(website|site|app|html|css)|"
            r"customize (my |the )?(local )?(website|site|app)|"
            r"open (my )?local (project|site|app) in (cursor|code|ide))\b",
            t,
        ):
            brief = t
            brief = re.sub(
                r"^(jarvis[, ]*)?(please\s+)?", "", brief, flags=re.I
            ).strip()
            self.habits.log("local_customize", brief[:40])
            if re.search(r"\bopen (my )?local\b", t):
                return self._flavor("ok", self.local_code.open_ide())

            def _job() -> None:
                try:
                    self._emit("code_ui", {"building": True, "hint": brief[:80]})
                    msg = self.local_code.apply_layout_tweak(brief)
                    self._emit("code_ui", False)
                    self.say(msg)
                except Exception as e:
                    self._emit("code_ui", False)
                    self.say(f"Local customize failed: {e}")

            threading.Thread(target=_job, daemon=True, name="local-customize").start()
            return self._flavor(
                "ok",
                "Understood — editing files on this machine only. "
                "I will not touch live public websites.",
            )

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
            r"\b(engage triple( monitors?)?|triple (monitor |screen )?layout|"
            r"three monitor( layout)?|command deck layout|"
            r"setup (my )?monitors|multi[- ]monitor( layout)?)\b",
            t,
        ):
            self._emit("triple_layout", True)
            return self._flavor(
                "ok",
                "Triple layout: Screen 1 control hub, Screen 2 tools stream, "
                "Screen 3 command deck.",
            )
        if re.search(
            r"\b(gaze (workspace )?(on|enable|start)|enable gaze|"
            r"start (eye|gaze) tracking|look.?up (mode|deck))\b",
            t,
        ):
            gw = getattr(self, "gaze_ws", None)
            if gw is None:
                return self._flavor("ok", "Gaze workspace is not loaded.")
            try:
                self.settings.gaze_workspace_enabled = True
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", gw.set_enabled(True))
        if re.search(
            r"\b(gaze (workspace )?(off|disable|stop)|disable gaze|"
            r"stop (eye|gaze) tracking)\b",
            t,
        ):
            gw = getattr(self, "gaze_ws", None)
            if gw is None:
                return self._flavor("ok", "Gaze workspace is not loaded.")
            try:
                self.settings.gaze_workspace_enabled = False
                self.settings.save()
            except Exception:
                pass
            return self._flavor("ok", gw.set_enabled(False))
        if re.search(r"\b(gaze (workspace )?status|gaze zone)\b", t):
            gw = getattr(self, "gaze_ws", None)
            if gw is None:
                return self._flavor("ok", "Gaze workspace is not loaded.")
            return self._flavor("ok", gw.status())
        if re.search(
            r"\b(throw (up|to (the )?top)|move (window|app) (to )?(the )?top|"
            r"send (to )?(the )?(deck|top (screen|monitor)))\b",
            t,
        ):
            from jarvis.core.gaze_workspace import move_foreground_to_monitor

            return self._flavor("ok", move_foreground_to_monitor("top"))
        if re.search(
            r"\b((show|open|put) (the )?tools?( (panel|stream|monitor))?|"
            r"tools on (the )?left|screen ?2|xrw)\b",
            t,
        ):
            self._emit("show_tools", True)
            self._emit("place_tools", "left")
            return self._flavor("ok", "Tools stream on Screen 2 — left panel.")
        if re.search(
            r"\b((show|open|put) (the )?(command )?deck|"
            r"holographic (dashboard|canvas)|screen ?3|"
            r"deck on (the )?top)\b",
            t,
        ):
            self._emit("show_deck", True)
            self._emit("place_deck", "top")
            return self._flavor("ok", "Command deck on Screen 3 — top canvas.")
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
            r"\b(cast (to )?(the )?(tv|fire ?tv|insignia)|"
            r"project (to )?(the )?(tv|fire ?tv|insignia)|"
            r"mirror (to )?(the )?(tv|fire ?tv)|"
            r"jarvis on (the )?tv|put (jarvis|hud) on (the )?tv|"
            r"fire tv (cast|mirror|project))\b",
            t,
        ):
            return self._flavor("ok", self.system.cast_to_fire_tv())
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

        # Time / date — local (settings tz) or remote ("what time in Cali")
        if re.search(
            r"\b(what time|current time|tell me the time|time is it|"
            r"time in |what's the time|whats the time)\b",
            t,
        ) or re.search(
            r"\btime (in|for|over in)\b",
            t,
        ):
            try:
                from jarvis.core.reminders import speak_time_in

                home = getattr(self.settings, "timezone", None) or "America/New_York"
                line = speak_time_in(t, default_tz=home)
                return self._flavor("time", line)
            except Exception:
                pass
            try:
                if getattr(self, "live", None) and not re.search(
                    r"\b(cali|california|pacific|london|tokyo|in )\b", t
                ):
                    d = self.live.snapshot()
                    return self._flavor("time", f"It's {d['time_12']} on {d['date']}.")
            except Exception:
                pass
            from zoneinfo import ZoneInfo

            home = getattr(self.settings, "timezone", None) or "America/New_York"
            now = datetime.now(ZoneInfo(home))
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

            home = getattr(self.settings, "timezone", None) or "America/New_York"
            now = datetime.now(ZoneInfo(home))
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
            # Timed reminders (California / at 10pm / when it turns 8) take priority
            if re.search(
                r"\b(at\s+\d|when\s+it|turns?\s+\d|\d{1,2}\s*(:\d{2})?\s*(a\.?m\.?|p\.?m\.?)|"
                r"california|cali|pacific|tonight)\b",
                t,
            ):
                rem = getattr(self, "reminders", None)
                if rem is not None:
                    return self._flavor("ok", rem.add_from_utterance(t))
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
                    [
                        "powershell",
                        "-NoProfile",
                        "-WindowStyle",
                        "Hidden",
                        "-Command",
                        "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
                    ],
                    shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
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
            self._emit("track", "Shoot to Thrill · AC/DC")
            self.habits.log("music")
            return self._flavor("music", self.music.press_play())
        # Ignore echo of old "press play" phrasing — just start music
        if t in ("press play", "pressed play"):
            self._emit("track", "Shoot to Thrill · AC/DC")
            return self._flavor("music", self.music.press_play())
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

        # Google Maps directions + tactical map fly (CTK: navigate to …)
        m = re.search(
            r"\b(?:navigate(?:\s+to)?|directions(?:\s+to)?|take me to|drive to|route to)\s+(.+)$",
            t,
        )
        if m:
            dest = m.group(1).strip(" .")
            dest = re.sub(r"\b(please|for me|now)\b", "", dest, flags=re.I).strip(" .")
            if dest:
                # Prefer tactical map pin/fly; also open Google dirs as transit aid
                try:
                    map_msg = self._map_zoom_to(dest)
                except Exception:
                    map_msg = ""
                url = (
                    "https://www.google.com/maps/dir/?api=1&destination="
                    + urllib.parse.quote_plus(dest)
                )
                try:
                    webbrowser.open(url)
                except Exception:
                    try:
                        self.apps.open(url)
                    except Exception:
                        pass
                self.habits.log("navigate", dest[:40])
                if map_msg and "couldn't find" not in map_msg.lower():
                    return map_msg
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
        m = re.search(
            r"\b(?:use|set|prefer)\s+(?:my\s+)?mic(?:rophone)?\s+(?:to\s+|prefer\s+)?(.+)$",
            t,
        )
        if m:
            name = m.group(1).strip(" .,!?")
            name = re.sub(r"^(the|my)\s+", "", name, flags=re.I)
            if name.lower() in ("default", "windows default", "system"):
                name = ""
            self.settings.mic_prefer = name
            try:
                self.settings.save()
            except Exception:
                pass
            try:
                self.voice.mic_prefer = name
            except Exception:
                pass
            label = name or "Windows default"
            return self._flavor(
                "ok",
                f"Microphone preference set to {label}. Restart voice or say mic test, Sir.",
            )
        if re.search(
            r"\b(use my mic|listen on my mic|microphone (preference|status))\b", t
        ):
            prefer = getattr(self.settings, "mic_prefer", "") or "Windows default"
            return self._flavor(
                "ok",
                f"I'm bound to mic prefer “{prefer}”. "
                "Say set mic to EMEET or set mic to default to change it.",
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

        # Keyboard / mouse RGB (OpenRGB)
        if re.search(r"\b(rgb status|openrgb status|keyboard rgb status)\b", t):
            return self._flavor("ok", self.rgb.status())
        if re.search(
            r"\b(rgb off|turn off (keyboard|mouse) (rgb|lights?)|"
            r"(keyboard|mouse) (rgb )?off)\b",
            t,
        ):
            tgt = "keyboard" if "keyboard" in t else ("mouse" if "mouse" in t else "all")
            return self._flavor("ok", self.rgb.off(tgt))
        if re.search(r"\b(sync rgb|rgb sync|rgb jarvis|jarvis rgb)\b", t):
            return self._flavor("ok", self.rgb.sync_jarvis())
        m = re.search(
            r"\b(?:set\s+)?(?:the\s+)?(keyboard|mouse|rgb|peripherals?)\s+"
            r"(?:(?:rgb|lights?|color|colour)\s+)?(?:to\s+)?([#\w][\w,# ]{0,40})$",
            t,
            re.I,
        )
        if m and not re.search(r"\b(shortcut|layout|language)\b", t):
            wh = m.group(1).lower()
            col = m.group(2).strip()
            tgt = "all"
            if wh == "keyboard":
                tgt = "keyboard"
            elif wh == "mouse":
                tgt = "mouse"
            return self._flavor("ok", self.rgb.set_color(col, target=tgt))
        m = re.search(
            r"\b(?:keyboard|mouse)\s+(?:to\s+)?(cyan|jarvis|red|blue|green|magenta|pink|"
            r"purple|orange|gold|amber|white|warm|cool|off|arwes)\b",
            t,
        )
        if m:
            tgt = "keyboard" if "keyboard" in t else "mouse"
            return self._flavor("ok", self.rgb.set_color(m.group(1), target=tgt))
        m = re.search(
            r"\brgb\s+(?:to\s+)?(cyan|jarvis|red|blue|green|magenta|pink|purple|"
            r"orange|gold|amber|white|warm|cool|off|arwes|#[0-9a-fA-F]{6})\b",
            t,
        )
        if m:
            return self._flavor("ok", self.rgb.set_color(m.group(1), target="all"))

        # RLHF preference feedback
        if re.search(r"\b(rlhf status|feedback status)\b", t):
            return self._flavor("ok", self.rlhf.status())
        if re.search(
            r"\b(approve( that| this| it)?|that was (good|correct|right)|good job|"
            r"thumbs up|prefer that)\b",
            t,
        ) and not self.hitl.pending:
            msg = self.rlhf.approve()
            # Feed approved mic/voice turns into personality forge harvest
            try:
                forge = getattr(self, "forge", None)
                if forge and self.rlhf.last_prompt and self.rlhf.last_reply:
                    forge.harvest_turn(
                        self.rlhf.last_prompt,
                        self.rlhf.last_reply,
                        source="mic_rlhf",
                    )
            except Exception:
                pass
            return self._flavor("ok", msg)
        if re.search(
            r"\b(reject( that| this| it)?|that was (wrong|bad|incorrect)|thumbs down|"
            r"don'?t do that|prefer not|fix (that|it|your answer))\b",
            t,
        ) and not self.hitl.pending:
            adv = getattr(self, "advanced", None)
            if adv is not None and re.search(
                r"\b(that was (wrong|bad|incorrect)|fix (that|it|your answer))\b", t
            ):
                return self._flavor("ok", adv.correct.fix_last())
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
            r"\b(optimize\s+jarvis|jarvis\s+optimize|lean\s+mode|"
            r"speed\s+up\s+jarvis|make\s+jarvis\s+faster)\b",
            t,
        ):
            return self._flavor("ok", self.optimize_jarvis())
        if re.search(
            r"\b(upgrade everything|fix everything|make (it |everything )?better|"
            r"upgrade (jarvis|ar|all)|optimize ar|full (upgrade|polish))\b",
            t,
        ):
            return self._flavor("ok", self.upgrade_everything())
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
            try:
                self._morning_launch_tabs()
            except Exception:
                pass
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
                "Morning: good morning — greet + YouTube + research tabs. "
                "AR: open aerospatial · cinematic ar · upgrade everything · scan room · web shooter. "
                "Reminders: remind me at 10 pm California to … · list reminders. "
                "Home ops: net watch · scan local network · lan status · trust network · "
                "run backup · arm deadman · space weather · iss · grab voice · "
                "list voice clones · scan processes · defender status · security scan · "
                "harden processes · edge setup · translate to Spanish …. "
                "Scanner: listen to traffic · satellite radio · weather radio · NOAA radio "
                "(cam tiles stay silent). "
                "Snap / phone: snapchat setup · test snapchat call · live comms setup · "
                "ping my phone · setup phone link. "
                "Smart: quiet mode · desk ready · full status · optimize jarvis · upgrade everything. "
                "Travis: park · tactical · peer review. "
                "Workflows: morning · night · focus · secure. "
                "Security: enroll · intruder alerts off · secure desk. "
                "Cloud: integrations status · stripe · notion · buffer · gmail. "
                "Agents: ask sarah · ask tom · hub status. "
                "Desk: camera · lock · music · weather. "
                "Say upgrade for hot reload."
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
            snap = getattr(self, "snapchat", None)
            if snap is not None:
                bits.append(snap.status())
        except Exception:
            pass
        try:
            comms = getattr(self, "comms_live", None)
            if comms is not None:
                bits.append(comms.status())
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

    def _morning_launch_tabs(self) -> str:
        """Good-morning ritual: YouTube + research tabs, then click/focus them."""
        urls = [
            "https://www.youtube.com",
            "https://www.perplexity.ai",
            "https://news.google.com",
            "https://scholar.google.com",
            "https://www.google.com/search?q=AI+research+news+today",
        ]
        prefer: str | int = "primary"
        try:
            from jarvis.core.displays import displays

            screens = displays.refresh()
            if len(screens) > 1:
                prefer = "secondary"
        except Exception:
            prefer = "primary"

        def _job() -> None:
            try:
                from jarvis.core.displays import displays

                msg = displays.open_urls(urls, prefer, activate=True)
                self._emit("hud_alert", "Morning tabs ready")
                self.feed.push("morning", msg)
            except Exception as e:
                print(f"[morning] launch: {e}")

        threading.Thread(target=_job, daemon=True, name="morning-tabs").start()
        return "Opening YouTube and research tabs now."

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
            try:
                self._last_scan_text = f"{query}. {detail}".strip()
            except Exception:
                pass
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

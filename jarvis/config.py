from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "settings.json"
DATA_DIR = ROOT / "jarvis" / "data"
PLUGINS_DIR = ROOT / "plugins"
ASSETS_DIR = ROOT / "assets"


@dataclass
class Theme:
    cyan: str = "#00f0ff"
    void: str = "#05060a"
    panel: str = "#0a121c"
    white: str = "#e8f4ff"
    dim: str = "#4a6070"
    orange: str = "#ff6b35"


@dataclass
class Settings:
    user_name: str = "Sir"
    wake_word: str = "jarvis"
    tts_voice: str = "en-GB-ThomasNeural"
    tts_rate: str = "-8%"
    tts_pitch: str = "-4Hz"
    tts_volume: str = "+0%"
    presence_timeout_sec: int = 35  # lock countdown after stepping away from camera
    presence_check_fps: int = 5
    telemetry_interval_ms: int = 2000
    camera_index: int = 1
    camera_prefer: str = "EMEET"
    lock_on_absence: bool = True
    noise_reduce: bool = True
    mic_prefer: str = ""  # empty = Windows default mic (not camera name)
    city: str = "Philadelphia"
    openweather_api_key: str = ""
    # Night vision — auto-engage after dusk
    night_vision_auto: bool = True
    night_vision_start_hour: int = 19  # 7 PM local
    night_vision_end_hour: int = 6  # 6 AM local
    # Work mode / media personalization
    work_project_path: str = ""
    work_ide: str = "code"
    work_apps: list[str] = field(default_factory=lambda: ["chrome", "code"])
    work_urls: list[str] = field(
        default_factory=lambda: [
            "https://mail.google.com",
            "https://github.com",
        ]
    )
    focus_playlist: str = "focus"
    spotify_playlist_id: str = "3hMeaqVid62fywPpTBWWw9"
    # Smart home / intelligence
    hue_bridge_ip: str = ""
    hue_username: str = ""
    lifx_token: str = ""
    gaze_lock_minutes: float = 0.0  # 0 = disabled (looking away must not lock)
    clipboard_wipe_sec: float = 60.0
    posture_nudge: bool = True
    auto_soundscape: bool = True
    lock_immediate: bool = False  # never lock on brief face flicker
    presence_grace_sec: float = 2.0  # brief settle before 35s lock countdown starts
    # HITL — human permission before deploy / massive structure
    hitl_enabled: bool = True
    hitl_timeout_sec: float = 300.0  # deny on timeout (safe default)
    # Away mode / mail agent (Outlook COM)
    away_mail_mode: str = "ack"  # draft | ack | auto
    away_mail_max_per_tick: int = 3
    # Multi-monitor
    hud_monitor: str = "primary"  # primary | secondary | 0 | 1
    ops_monitor: str = "secondary"  # where big stats board goes
    ops_monitor_enabled: bool = True
    open_on_other_monitor: bool = True  # apps/URLs Jarvis opens
    # Wake-on-LAN / clap wake (second device uses Wi-Fi and/or Bluetooth)
    wol_mac: str = ""
    wol_broadcast: str = "255.255.255.255"
    bluetooth_mac: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8888/callback"
    # Hub & Spoke (Node multi-agent: Sarah / Tom / Admin)
    hub_enabled: bool = True
    hub_auto_start: bool = True
    hub_url: str = "http://127.0.0.1:8787"
    # Local Ollama fuzzy intent router (optional — falls back to regex)
    ollama_router: bool = True
    ollama_model: str = "llama3"
    theme: Theme = field(default_factory=Theme)

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or CONFIG_PATH
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            s = cls()
            # Default project path to this jarvis repo when unset
            if not s.work_project_path:
                s.work_project_path = str(ROOT)
            s.save(path)
            return s
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8-sig"))
        theme_raw = raw.pop("theme", {}) or {}
        known_theme = {k: v for k, v in theme_raw.items() if k in Theme.__dataclass_fields__}
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__ and k != "theme"}
        s = cls(theme=Theme(**known_theme), **known)
        if not s.work_project_path:
            s.work_project_path = str(ROOT)
        return s

    def save(self, path: Path | None = None) -> None:
        path = path or CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

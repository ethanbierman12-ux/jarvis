from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "settings.json"
CONFIG_JSON = ROOT / "config" / "config.json"  # alias — tokens stay out of source
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
    presence_check_fps: int = 2
    telemetry_interval_ms: int = 4000
    camera_index: int = 1
    camera_prefer: str = "EMEET"
    lock_on_absence: bool = False
    noise_reduce: bool = False
    mic_prefer: str = ""  # empty = Windows default mic (not camera name)
    city: str = "Philadelphia"
    openweather_api_key: str = ""
    weather_units: str = "f"  # f | c — US default Fahrenheit
    timezone: str = "America/New_York"  # calendar day for Philly / East Coast
    # Night vision — auto-engage after dusk (hours evaluated in settings.timezone)
    night_vision_auto: bool = True
    night_vision_start_hour: int = 19  # 7 PM in settings.timezone
    night_vision_end_hour: int = 6  # 6 AM in settings.timezone
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
    # Alexa smart lamp (bulb in the Alexa app)
    alexa_lamp_name: str = "Lamp"
    alexa_lamp_entity: str = "light.lamp"  # Home Assistant entity if exposed
    alexa_ifttt_key: str = ""  # IFTTT Maker key — recommended without a Hue bridge
    alexa_ifttt_on_event: str = "jarvis_lamp_on"
    alexa_ifttt_off_event: str = "jarvis_lamp_off"
    alexa_lamp_on_webhook: str = ""
    alexa_lamp_off_webhook: str = ""
    alexa_voice_relay: bool = True  # best default: talk to nearby Echo via room speakers
    alexa_restore_output: str = "WG1"
    gaze_lock_minutes: float = 0.0  # 0 = disabled (looking away must not lock)
    clipboard_wipe_sec: float = 60.0
    posture_nudge: bool = False
    auto_soundscape: bool = False
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
    ops_monitor_enabled: bool = True  # PDTester digests on secondary monitor
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
    hub_auto_start: bool = False  # start on demand, not every boot
    hub_url: str = "http://127.0.0.1:8787"
    # Local Ollama fuzzy intent router (optional — falls back to regex)
    ollama_router: bool = False
    ollama_model: str = "llama3"
    # ElevenLabs TTS (optional — Edge en-GB-ThomasNeural is the Jarvis default)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "pNInz6obpgDQ51uIfY1H"
    elevenlabs_model: str = "eleven_monolingual_v1"
    tts_prefer_elevenlabs: bool = False  # keep False for classic British Jarvis
    # After "update software" patch, reboot via watchdog (exit 0)
    reload_after_update: bool = True
    # Audio isolation — never STT from desktop loopback / Voicemeeter outs
    mic_reject_loopback: bool = True
    # Stream Deck / silent macro HTTP pad
    macro_gateway_enabled: bool = True
    macro_gateway_port: int = 8765
    # Home Assistant
    ha_enabled: bool = False
    ha_url: str = "http://127.0.0.1:8123"
    ha_token: str = ""
    # n8n automation bridge
    n8n_url: str = "http://127.0.0.1:5678"
    n8n_api_key: str = ""
    # Cloud integrations (mirror Cursor MCP: Stripe / Notion / Buffer / Gmail)
    stripe_secret_key: str = ""
    notion_token: str = ""
    buffer_access_token: str = ""
    gmail_access_token: str = ""
    # Manus AI agent API (https://manus.im / api.manus.ai)
    manus_enabled: bool = True
    manus_api_key: str = ""
    manus_agent_profile: str = "manus-1.6"  # manus-1.6 | manus-1.6-lite | manus-1.6-max
    manus_base_url: str = "https://api.manus.ai"
    # Opt-in HUD offer when new/changed code lands (never auto-create Manus tasks)
    manus_code_assist: bool = True
    manus_code_assist_cooldown_sec: int = 720  # 12 min between offers
    manus_code_assist_debounce_sec: int = 45
    # Computer-use / browser agent (screenshot → LLM → mouse/keyboard)
    computer_use_enabled: bool = True
    # auto|ollama|local|anthropic|openai|browser_use|desktop|gemini|skyvern|openinterpreter
    computer_use_provider: str = "auto"
    computer_use_prefer_local: bool = True  # auto prefers Ollama before paid APIs
    computer_use_ollama_host: str = "http://127.0.0.1:11434"
    computer_use_ollama_model: str = ""  # empty = auto-detect (vision preferred)
    computer_use_max_steps: int = 40
    computer_use_headless: bool = False  # show real browser window
    computer_use_confirm_long_runs: bool = True  # HITL before long autonomous sessions
    computer_use_confirm_steps: int = 8  # ask permission when max_steps >= this
    computer_use_anthropic_model: str = "claude-sonnet-4-5"
    computer_use_openai_model: str = "gpt-4.1"
    anthropic_api_key: str = ""  # vaulted
    openai_api_key: str = ""  # vaulted
    # iPhone / phone push (ntfy App Store app)
    phone_enabled: bool = True
    phone_ntfy_topic: str = ""  # auto-generated on first link
    phone_ntfy_server: str = "https://ntfy.sh"
    phone_shortcuts_webhook: str = ""  # optional iOS Shortcuts URL
    # iPhone companion PWA (Tailscale-reachable chat UI)
    companion_enabled: bool = True
    companion_port: int = 8766
    companion_host: str = "0.0.0.0"  # Tailscale peers need non-loopback bind
    companion_token: str = ""  # auto-generated; kept in DPAPI vault when possible
    companion_intro_day: str = ""  # YYYY-MM-DD — once-a-day discoverability tip
    # Folder watchdog (Downloads etc.)
    watch_enabled: bool = True
    watch_paths: list[str] = field(default_factory=list)
    # Travis personality modes: off | park | tactical | peer_review
    travis_mode: str = "off"
    # Productivity suite
    github_auto_push: bool = False
    proactive_enabled: bool = True
    suggestions_enabled: bool = True  # ambient tips; "suggestions off" disables
    # Voice: only act after wake word (or within short armed window after "Jarvis?")
    wake_required: bool = True
    wake_arm_sec: float = 8.0  # how long after bare wake a follow-up command is accepted
    # Smooth / eco HUD — lower reactor/camera/waveform FPS for snappier voice
    performance_mode: bool = False
    media_pause_on_stand: bool = True
    # Desk security / biometrics
    security_enabled: bool = True
    # Keep alerts on but security_gate enforces long cooldown + mismatch streak
    intruder_alert: bool = True
    intruder_alert_cooldown_sec: int = 720  # 12 min between spoken intruder alerts
    theme: Theme = field(default_factory=Theme)
    # Never touch Windows taskbar/app light-dark unless user opts in
    theme_sync_windows: bool = False
    # One-shot: restore dark taskbar if a prior build flipped it light
    theme_repair_dark_once: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        # Prefer settings.json (user-edited). config.json is a write mirror only.
        path = path or CONFIG_PATH
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists() and CONFIG_JSON.exists():
            path = CONFIG_JSON
        if not path.exists():
            s = cls()
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
        # Harvest any plaintext secrets into DPAPI vault, then hydrate RAM from vault
        try:
            from jarvis.core.secrets_vault import get_vault

            vault = get_vault()
            moved = vault.harvest_from(s)
            vault.merge_into(s)
            if moved:
                s.save(path)  # rewrite settings.json without secrets
                print(f"[vault] moved {moved} secret(s) into DPAPI vault")
        except Exception as e:
            print(f"[vault] skip: {e}")
        return s

    def save(self, path: Path | None = None) -> None:
        path = path or CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from jarvis.core.secrets_vault import SECRET_KEYS, get_vault, sanitize_secret

            vault = get_vault()
            vault.load()
            # Snapshot live secrets → vault, then write redacted JSON
            for key in SECRET_KEYS:
                val = getattr(self, key, "") or ""
                if str(val).strip() and not str(val).startswith("•"):
                    vault._cache[key] = sanitize_secret(str(val))
            vault.save()
            disk = asdict(self)
            for key in SECRET_KEYS:
                disk[key] = ""
            blob = json.dumps(disk, indent=2)
            # Keep RAM hydrated
            vault.merge_into(self)
        except Exception:
            blob = json.dumps(asdict(self), indent=2)
        path.write_text(blob, encoding="utf-8")
        if path.resolve() != CONFIG_JSON.resolve():
            try:
                CONFIG_JSON.write_text(blob, encoding="utf-8")
            except Exception:
                pass

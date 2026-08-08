"""Main Jarvis HUD — clean three-column layout after boot bloom."""

from __future__ import annotations

import json
import os
import threading

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QTextEdit,
    QGraphicsOpacityEffect, QLineEdit, QStackedWidget, QFrame, QScrollArea,
    QSizePolicy,
)

from jarvis.config import Settings
from jarvis.ui.styles import stylesheet, weather_mood, mood_palette
from jarvis.ui.widgets.startup import StartupOverlay
from jarvis.ui.widgets.reactor import ArcReactor
from jarvis.ui.widgets.clock import ClockPanel
from jarvis.ui.widgets.weather_hud import WeatherPanel
from jarvis.ui.widgets.command_deck import CommandDeck
from jarvis.ui.widgets.typing_overlay import TypingOverlay
from jarvis.ui.widgets.upgrade_overlay import UpgradeOverlay
from jarvis.ui.widgets.countdown import CountdownOverlay
from jarvis.ui.widgets.night_vision import NightVisionBadge
from jarvis.ui.widgets.artifact_panel import ArtifactPanel
from jarvis.ui.widgets.camera_theater import CameraTheater
from jarvis.ui.widgets.control_strip import ControlStrip
from jarvis.ui.widgets.memory_map import MemoryMap
from jarvis.ui.widgets.media_panel import MediaPanel
from jarvis.ui.widgets.quick_action import QuickActionChip, AlertBanner
from jarvis.ui.widgets.weather_fx import WeatherAtmosphere
from jarvis.ui.widgets.site_preview import SitePreview
from jarvis.ui.widgets.code_preview import CodePreview
from jarvis.ui.widgets.build_theater import BuildTheater
from jarvis.ui.widgets.away_theater import AwayTheater
from jarvis.ui.widgets.map_view import MapView
from jarvis.ui.widgets.command_monitor import CommandMonitor
from jarvis.ui.widgets.voice_waveform import VoiceWaveform
from jarvis.ui.widgets.news_overlay import NewsOverlay
from jarvis.ui.widgets.cmd_button import CmdButton
from jarvis.ui.widgets.hitl_gate import HitlGate
from jarvis.ui.widgets.quick_toggles import QuickToggleGrid


class MainWindow(QMainWindow):
    """HUD shell. Emits boot_ready when the startup sequence finishes."""

    boot_ready = pyqtSignal()
    # Thread-safe UI slots — voice thread must not call QTimer.singleShot alone
    request_camera = pyqtSignal(bool)
    request_ui = pyqtSignal(str, object)

    def __init__(self, settings: Settings, brain=None) -> None:
        super().__init__()
        self.settings = settings
        self.brain = brain
        self.ops = None  # secondary-monitor ops board (PDTester)
        self.tools = None  # Screen 2 tools panel
        self.deck_win = None  # Screen 3 command deck
        self._tts_active = False
        self._cam_open_retries = 0
        self.setWindowTitle("JARVIS")
        self.resize(1560, 940)
        self.setMinimumSize(1280, 780)

        self.request_camera.connect(self._toggle_camera)
        self.request_ui.connect(self._on_request_ui)

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(settings.theme.void))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(settings.theme.white))
        self.setPalette(pal)
        self.setStyleSheet(stylesheet(settings.theme, mood="clear"))
        self._wx_mood = "clear"

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 10, 18, 14)
        outer.setSpacing(10)

        # Header
        header_frame = QFrame()
        header_frame.setObjectName("HeaderBar")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(2, 2, 2, 8)
        header.setSpacing(10)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(4)
        brand = QLabel("JARVIS")
        brand.setObjectName("Brand")
        brand_sub = QLabel("JS-9082 · SECURE ACCESS · VOID LAB")
        brand_sub.setObjectName("BrandSub")
        brand_col.addWidget(brand)
        brand_col.addWidget(brand_sub)
        header.addLayout(brand_col)
        header.addSpacing(10)

        self.start_btn = CmdButton("START", "start", kind="start")
        self.start_btn.setMinimumWidth(108)
        self.start_btn.setToolTip(
            "Engage systems (voice: start) — double-tap F3 to launch/reload "
            "(single F3 arms only; second tap within 2.5s starts)"
        )
        self.start_btn.fired.connect(lambda _: self._on_start_clicked())
        header.addWidget(self.start_btn)

        hint = QLabel("⌃⇧P")
        hint.setObjectName("Dim")
        hint.setStyleSheet("letter-spacing:1px; font-size:8px; color:#3a5060;")
        hint.setToolTip("Panic — Ctrl+Shift+P")
        header.addWidget(hint)
        self.loc = QLabel("")
        self.loc.setObjectName("Dim")
        header.addWidget(self.loc)
        header.addStretch(1)

        self.listen = QLabel("MIC STANDBY")
        self.listen.setObjectName("MicPill")
        self.listen.setMaximumWidth(160)
        self.status = QLabel("● OPTIMAL")
        self.status.setObjectName("StatusPill")
        self.status.setMaximumWidth(220)
        self.status.setWordWrap(False)
        header.addWidget(self.listen)
        header.addWidget(self.status)
        outer.addWidget(header_frame)

        # Body
        body = QHBoxLayout()
        body.setSpacing(12)

        # Left rail — scroll so dense widgets never crush / paint through each other
        left_inner = QWidget()
        left_inner.setObjectName("LeftRailInner")
        left = QVBoxLayout(left_inner)
        left.setContentsMargins(0, 0, 2, 0)
        left.setSpacing(8)
        self.clock = ClockPanel(
            timezone=getattr(settings, "timezone", "America/New_York")
            or "America/New_York"
        )
        self.memory_map = MemoryMap()
        self.toggles = QuickToggleGrid()
        self.toggles.toggled.connect(self._on_quick_toggle)
        self.controls = ControlStrip()
        self.controls.action.connect(self._cmd)
        self.media = MediaPanel(
            playlist_id=getattr(settings, "spotify_playlist_id", "")
            or "3hMeaqVid62fywPpTBWWw9"
        )
        self.media.action.connect(self._media_action)
        left.addWidget(self.clock, 0)
        left.addWidget(self.memory_map, 0)
        left.addWidget(self.toggles, 0)
        left.addWidget(self.controls, 0)
        left.addWidget(self.media, 0)
        left.addStretch(1)

        left_scroll = QScrollArea()
        left_scroll.setObjectName("LeftRail")
        left_scroll.setWidget(left_inner)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setFixedWidth(300)
        left_scroll.setMinimumWidth(280)
        left_scroll.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        body.addWidget(left_scroll)
        self._left_rail = left_scroll
        self._left_inner = left_inner

        center = QVBoxLayout()
        center.setSpacing(12)

        self._center_stack = QStackedWidget()
        self.reactor = ArcReactor()
        self.reactor.node_activated.connect(self._cmd)
        self.map_view = MapView()
        self.map_view.closed.connect(self._close_map_mode)
        self.map_view.option_selected.connect(self._on_map_option)
        self.map_view.build_requested.connect(self._on_map_build_site)
        self.map_view.hide()
        self._center_stack.addWidget(self.reactor)  # 0
        self._center_stack.addWidget(self.map_view)  # 1
        self._center_stack.setCurrentIndex(0)
        center.addWidget(self._center_stack, 1)

        self.log = QTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setFixedHeight(110)
        self.log.setPlaceholderText("MISSION LOG  ·  terminal feed")
        try:
            # Cap growth — unbounded append() was a long-session lag source
            self.log.document().setMaximumBlockCount(400)
        except Exception:
            pass
        center.addWidget(self.log)

        self.wave = VoiceWaveform()
        center.addWidget(self.wave)

        row = QHBoxLayout()
        row.setSpacing(8)
        talk_frame = QFrame()
        talk_frame.setObjectName("TalkBar")
        talk_row = QHBoxLayout(talk_frame)
        talk_row.setContentsMargins(10, 6, 10, 6)
        talk_row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setObjectName("CmdInput")
        self.input.setPlaceholderText(
            "Say Jarvis…  ·  quiet mode · desk ready · full status · help"
        )
        self.input.returnPressed.connect(self._submit)
        send = CmdButton("TALK TO JARVIS", "execute", kind="talk")
        send.setMinimumWidth(180)
        send.fired.connect(lambda _: self._submit())
        self.exec_btn = send
        talk_row.addWidget(self.input, 1)
        talk_row.addWidget(send)
        row.addWidget(talk_frame, 1)
        center.addLayout(row)
        center_w = QWidget()
        center_w.setLayout(center)
        body.addWidget(center_w, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.deck = CommandDeck()
        self.cmd_monitor = CommandMonitor()
        self.cmd_monitor.setMinimumHeight(100)
        self.cmd_monitor.hide()  # quieter HUD; say "show command monitor" to open
        self.weather = WeatherPanel()
        right.addWidget(self.deck, 3)
        right.addWidget(self.cmd_monitor, 1)
        right.addWidget(self.weather, 2)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setFixedWidth(300)
        body.addWidget(right_w)

        self._hud = QWidget()
        self._hud.setLayout(body)
        outer.addWidget(self._hud, 1)

        # Overlays
        self.typing = TypingOverlay(root)
        self.typing.setGeometry(root.rect())
        self.typing.submitted.connect(self._on_update)
        self.typing.cancelled.connect(lambda: self.brain and self.brain.voice.mute_mic(False))
        self.typing.hide()

        self.upgrade = UpgradeOverlay(root)
        self.upgrade.setGeometry(root.rect())
        self.upgrade.hide()

        self.alert = AlertBanner(root)
        self.quick = QuickActionChip(root)
        self.quick.accepted.connect(self._accept_quick_action)
        self.hitl_gate = HitlGate(root)
        self.hitl_gate.decided.connect(self._on_hitl_decided)
        self.atmosphere = WeatherAtmosphere(root)
        self.atmosphere.setGeometry(root.rect())
        self.atmosphere.raise_()  # subtle overlay above HUD; mouse-transparent

        # Panic: Ctrl+Shift+P
        panic = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        panic.activated.connect(self._panic)
        # RLHF: Ctrl+Shift+Up = approve last action · Ctrl+Shift+Down = reject
        rlhf_up = QShortcut(QKeySequence("Ctrl+Shift+Up"), self)
        rlhf_up.activated.connect(lambda: self._rlhf_verdict(True))
        rlhf_dn = QShortcut(QKeySequence("Ctrl+Shift+Down"), self)
        rlhf_dn.activated.connect(lambda: self._rlhf_verdict(False))
        self.countdown = CountdownOverlay()
        self.countdown.finished.connect(lambda: self.brain and self.brain.on_countdown_finished())
        self.countdown.cancelled.connect(
            lambda: self.append_log("SECURITY › countdown cancelled — welcome back")
        )

        self.camera = CameraTheater(root)
        self.camera.closed.connect(self._on_camera_closed)
        self.camera.scan_clicked.connect(lambda _: self._do_scan(ocr=True))
        self.camera.gesture.connect(self._on_gesture_state)
        self.camera.gesture_drag.connect(self._on_gesture_drag)
        self.camera.gesture_swipe.connect(self._on_gesture_swipe)
        # Camera dock desk pack → traffic / NOAA / LAN / Defender
        try:
            self.camera.desk_traffic.connect(
                lambda: self._dispatch_brain("show traffic cams")
            )
            self.camera.desk_listen.connect(self._traffic_play_listen)
            self.camera.desk_sat.connect(self._traffic_play_sat)
            self.camera.desk_lan.connect(self._camera_desk_lan)
            self.camera.desk_sec.connect(self._camera_desk_sec)
        except Exception as e:
            print(f"[camera] desk pack wire: {e}")

        self._spatial = None
        try:
            from jarvis.core.spatial_gestures import SpatialWorkspace

            self._spatial = SpatialWorkspace(
                place_hud=lambda m: self._place_on_monitor(m, which="hud"),
                place_ops=lambda m: self._place_on_monitor(m, which="ops"),
                on_note=lambda s: self.append_log(s),
            )
        except Exception as e:
            print(f"[spatial] init: {e}")
            self._spatial = None

        self.nv_badge = NightVisionBadge(root)
        self.nv_badge.move(24, 72)
        self.nv_badge.hide()

        self.artifact = ArtifactPanel(root)
        self.artifact.hide()

        self.news = NewsOverlay(root)
        self.news.closed.connect(self._on_news_closed)
        self.news.hide()

        self.site_preview = SitePreview(root)
        self.site_preview.closed.connect(
            lambda: self.append_log("SITE › preview closed")
        )
        self.site_preview.hide()

        self.code_preview = CodePreview(root)
        self.code_preview.closed.connect(
            lambda: self.append_log("VIBE › panel closed")
        )
        self.code_preview.open_ide.connect(self._open_vibe_ide)
        self.code_preview.hide()

        self.build_theater = BuildTheater(root)
        self.build_theater.closed.connect(self._on_build_theater_closed)
        self.build_theater.hide()

        self.away_theater = AwayTheater(root)
        self.away_theater.closed.connect(
            lambda: self.append_log("AWAY › theater closed")
        )
        self.away_theater.hide()

        self.startup = StartupOverlay(root)
        self.startup.setGeometry(root.rect())
        self.startup.finished.connect(self._on_boot_done)
        self._hud.hide()
        self._hud.setEnabled(False)

        self._root = root
        root.installEventFilter(self)

        self._tel = QTimer(self)
        self._tel.timeout.connect(self._refresh)
        self._tel.start(settings.telemetry_interval_ms)

        self._wx = QTimer(self)
        self._wx.timeout.connect(self._weather)
        self._wx.start(90_000)

        self._orb = QTimer(self)
        self._orb.timeout.connect(self._orbital)
        self._orb.start(30_000)

        QTimer.singleShot(30, self.startup.start)

        # F3 = reload core (exit 0). Must NOT trigger START (that caused spam).
        # Global F3 is owned by wake_agent when armed; this shortcut covers HUD
        # focus when the wake agent is not holding RegisterHotKey.
        self._wake_key = QShortcut(QKeySequence(Qt.Key.Key_F3), self)
        self._wake_key.setContext(Qt.ShortcutContext.WindowShortcut)
        self._wake_key.activated.connect(self._on_wake_reload)

        # Esc closes map if open.
        self._esc = QShortcut(QKeySequence("Escape"), self)
        self._esc.setContext(Qt.ShortcutContext.WindowShortcut)
        self._esc.activated.connect(self._on_escape)

        # Emergency override — force-crash exit so watchdog recovers (not offline 99)
        self._kill = QShortcut(QKeySequence("Ctrl+Alt+K"), self)
        self._kill.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._kill.activated.connect(self._emergency_kill)

        # Wake-agent / external F3 writes reload.request — poll quickly
        self._reload_poll = QTimer(self)
        self._reload_poll.setInterval(250)
        self._reload_poll.timeout.connect(self._poll_reload_request)
        self._reload_poll.start()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        if obj is self._root and event.type() == QEvent.Type.Resize:
            self.typing.setGeometry(self._root.rect())
            self.startup.setGeometry(self._root.rect())
            try:
                self.atmosphere.setGeometry(self._root.rect())
            except Exception:
                pass
            try:
                if self.camera.isVisible():
                    self.camera.setGeometry(self._root.rect())
                    self.camera.raise_()
            except Exception:
                pass
            try:
                if getattr(self, "build_theater", None) and self.build_theater.isVisible():
                    self.build_theater.setGeometry(self._root.rect())
                    self.build_theater.raise_()
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _on_boot_done(self) -> None:
        self._hud.show()
        self._hud.setEnabled(True)
        fx = QGraphicsOpacityEffect(self._hud)
        self._hud.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _clear_boot_fx() -> None:
            try:
                self._hud.setGraphicsEffect(None)
            except Exception:
                pass

        anim.finished.connect(_clear_boot_fx)
        # Backup clear — finished can miss if the effect is replaced mid-fade
        QTimer.singleShot(380, _clear_boot_fx)
        anim.start()
        self._boot_anim = anim
        self.status.setText("● OPTIMAL")
        # Brain/stark arrival owns the "Daddy's home" line — avoid triple log spam
        self.append_log("HUD › arc reactor online")
        self.input.setFocus()
        QTimer.singleShot(80, self._weather)
        QTimer.singleShot(200, self._orbital)
        QTimer.singleShot(350, self._boot_optics_auto)
        QTimer.singleShot(300, self._stack_overlays)
        # Tell app.py to start the brain (speaks Welcome)
        self.boot_ready.emit()

    def _on_escape(self) -> None:
        if getattr(self, "build_theater", None) and self.build_theater.isVisible():
            try:
                self.build_theater._close()
            except Exception:
                self.build_theater.hide()
                self._on_build_theater_closed()
            return
        if getattr(self, "camera", None) and self.camera.isVisible():
            self.camera.hide_feed(emit=True)
            return
        if getattr(self, "_center_stack", None) and self._center_stack.currentIndex() == 1:
            self._close_map_mode()

    def _on_wake_reload(self) -> None:
        """HUD F3 — double-tap to soft-reload (matches global wake agent)."""
        if getattr(self, "_reload_armed", False):
            return
        import time as _time

        now = _time.monotonic()
        armed_until = float(getattr(self, "_f3_arm_until", 0.0) or 0.0)
        if now > armed_until:
            self._f3_arm_until = now + 2.5
            self.append_log("CORE › F3 armed — tap again within 2.5s to reload")
            try:
                self.status.setText("● F3 ARMED — TAP AGAIN")
            except Exception:
                pass
            return
        self._f3_arm_until = 0.0
        self._reload_armed = True
        self.append_log("CORE › F3 soft-reload")
        try:
            self.status.setText("● RELOADING…")
        except Exception:
            pass
        self._request_app_exit(0)

    def _poll_reload_request(self) -> None:
        if getattr(self, "_reload_armed", False):
            return
        try:
            from jarvis.core.instance import consume_reload_request

            if consume_reload_request():
                self._reload_armed = True
                self.append_log("CORE › external reload request")
                self._request_app_exit(0)
        except Exception as e:
            print(f"[reload] poll: {e}")

    def _emergency_kill(self) -> None:
        print("\n[CRITICAL]: EMERGENCY OVERRIDE RECEIVED. SHUTTING DOWN FORCEFULLY.")
        try:
            if self.brain:
                self.brain.stop()
        except Exception:
            pass
        os._exit(1)

    def bind_brain(self, brain) -> None:
        self.brain = brain
        brain.ui.update(
            {
                "speak": lambda t: QTimer.singleShot(0, lambda: self._on_speak(t)),
                "speaking": lambda on: QTimer.singleShot(
                    0, lambda: self._on_jarvis_speaking(bool(on))
                ),
                "heard": lambda t: QTimer.singleShot(0, lambda: self.append_log(f"YOU › {t}")),
                "listening": lambda a: QTimer.singleShot(0, lambda: self._set_listen(a)),
                "presence": lambda p: QTimer.singleShot(0, lambda: self._presence(p)),
                "countdown_start": lambda s: QTimer.singleShot(0, lambda: self._start_lock_countdown(int(s))),
                "countdown_cancel": lambda _: QTimer.singleShot(0, self.countdown.cancel),
                "panic_ui": lambda on: QTimer.singleShot(
                    0, lambda: self._set_panic_core(bool(on))
                ),
                "travis_ui": lambda m: QTimer.singleShot(
                    0, lambda: self._set_travis_core(str(m or "off"))
                ),
                "night_vision": lambda on: QTimer.singleShot(
                    0, lambda: self._set_night_vision(bool(on))
                ),
                "thermal_assist": lambda on: QTimer.singleShot(
                    0, lambda: self._set_thermal_assist(bool(on))
                ),
                "ops_hud": lambda on: self.request_ui.emit("ops_hud", bool(on)),
                "traffic_cams": lambda on: self.request_ui.emit("traffic_cams", bool(on)),
                "traffic_board": lambda on: self.request_ui.emit("traffic_board", bool(on)),
                "traffic_live_map": lambda on: self.request_ui.emit(
                    "traffic_live_map", bool(on)
                ),
                "scanner_live": lambda payload: self.request_ui.emit(
                    "scanner_live", payload
                ),
                "traffic_cams_next": lambda _: self.request_ui.emit(
                    "traffic_cams_next", True
                ),
                "traffic_region": lambda r: self.request_ui.emit(
                    "traffic_region", str(r or "")
                ),
                "ops_pins": lambda pins: self.request_ui.emit("ops_pins", pins),
                "spatial_ui": lambda on: QTimer.singleShot(
                    0, lambda: self._set_spatial(bool(on))
                ),
                "spatial_status": lambda _: QTimer.singleShot(
                    0, self._spatial_status
                ),
                "enroll_grab": lambda _: QTimer.singleShot(0, self._enroll_grab_frame),
                "speak_ui": lambda t: QTimer.singleShot(0, lambda: self.append_log(f"JARVIS › {t}")),
                "update_ui": lambda a: QTimer.singleShot(
                    0, lambda: self.typing.open() if a else self.typing.close_panel()
                ),
                # Thread-safe: worker thread must use signal, not lone QTimer
                "upgrade_ui": lambda payload: self.request_ui.emit("upgrade_ui", payload),
                "command_ui": lambda payload: self.request_ui.emit("command_ui", payload),
                "registry_ui": lambda payload: self.request_ui.emit("registry_ui", payload),
                "monitor_ui": lambda payload: self.request_ui.emit("monitor_ui", payload),
                "camera_ui": lambda a: self.request_camera.emit(bool(a)),
                "fabricator_ui": lambda a: self.request_ui.emit("fabricator_ui", a),
                "fabricator_build": lambda _: self.request_ui.emit("fabricator_build", True),
                "aerospatial_ui": lambda a: self.request_ui.emit("aerospatial_ui", a),
                "aerospatial_scan": lambda _: self.request_ui.emit("aerospatial_scan", True),
                "aerospatial_deploy": lambda m: self.request_ui.emit("aerospatial_deploy", m),
                "aerospatial_cinematic": lambda a: self.request_ui.emit(
                    "aerospatial_cinematic", a
                ),
                "aerospatial_biometric": lambda _: self.request_ui.emit(
                    "aerospatial_biometric", True
                ),
                "aerospatial_gauges": lambda _: self.request_ui.emit(
                    "aerospatial_gauges", True
                ),
                "aerospatial_web": lambda _: self.request_ui.emit("aerospatial_web", True),
                # Thread-safe: voice/worker threads must use signals, not QTimer alone
                "map_ui": lambda payload: self.request_ui.emit("map_ui", payload),
                "news_ui": lambda payload: self.request_ui.emit("news_ui", payload),
                "site_ui": lambda payload: self.request_ui.emit("site_ui", payload),
                "site_progress": lambda msg: self.request_ui.emit("site_progress", msg),
                "code_ui": lambda payload: self.request_ui.emit("code_ui", payload),
                "code_progress": lambda msg: self.request_ui.emit("code_progress", msg),
                "theater_tab": lambda payload: self.request_ui.emit("theater_tab", payload),
                "away_ui": lambda payload: self.request_ui.emit("away_ui", payload),
                "away_progress": lambda msg: self.request_ui.emit("away_progress", msg),
                "bond": lambda h: QTimer.singleShot(0, lambda: self._bond(h)),
                "bedtime": lambda d: QTimer.singleShot(0, lambda: self._bedtime(d)),
                "state": lambda s: QTimer.singleShot(0, lambda: self._on_state_ui(s)),
                "weather_ui": lambda _: QTimer.singleShot(0, self._weather),
                "parallax": lambda d: QTimer.singleShot(0, lambda: self._parallax(d)),
                "telemetry": lambda s: QTimer.singleShot(0, lambda: self._apply_tel(s)),
                "track": lambda n: QTimer.singleShot(0, lambda: self._on_track(str(n))),
                "fetching": lambda _: QTimer.singleShot(
                    0, lambda: self._reactor_activity("fetch")
                ),
                "reactor_activity": lambda m: QTimer.singleShot(
                    0, lambda: self._reactor_activity(str(m or "fetch"))
                ),
                "scan_now": lambda _: QTimer.singleShot(0, lambda: self._do_scan(ocr=True)),
                "scan_result": lambda t: QTimer.singleShot(0, lambda: self._on_scan_result(str(t))),
                "artifact": lambda p: QTimer.singleShot(0, lambda: self._show_artifact(p)),
                "mic_level": lambda lvl: QTimer.singleShot(
                    0, lambda: self._on_mic_level(float(lvl))
                ),
                "performance_ui": lambda on: QTimer.singleShot(
                    0, lambda: self._apply_performance_mode(bool(on))
                ),
                "scan_done": lambda _: QTimer.singleShot(0, self._on_scan_done),
                "get_camera_frame": lambda: self.camera.current_frame() if self.camera.isVisible() else None,
                "start_pulse": lambda _: QTimer.singleShot(0, self._on_start_pulse),
                "hud_alert": lambda t: QTimer.singleShot(0, lambda: self._hud_alert(str(t))),
                "quick_action": lambda t: QTimer.singleShot(0, lambda: self._offer_quick(str(t))),
                "hitl_ask": lambda p: self.request_ui.emit("hitl_ask", p),
                "hitl_clear": lambda _: self.request_ui.emit("hitl_clear", None),
                "stats": lambda s: QTimer.singleShot(0, lambda: self._apply_stats(s)),
                "feed": lambda lines: QTimer.singleShot(0, lambda: self._apply_feed(lines)),
                "place_hud": lambda pref: QTimer.singleShot(
                    0, lambda: self._place_on_monitor(str(pref), which="hud")
                ),
                "place_ops": lambda pref: QTimer.singleShot(
                    0, lambda: self._place_on_monitor(str(pref), which="ops")
                ),
                "place_tools": lambda pref: QTimer.singleShot(
                    0, lambda: self._place_on_monitor(str(pref), which="tools")
                ),
                "place_deck": lambda pref: QTimer.singleShot(
                    0, lambda: self._place_on_monitor(str(pref), which="deck")
                ),
                "show_ops": lambda _: QTimer.singleShot(0, self._show_ops),
                "show_tools": lambda _: QTimer.singleShot(0, self._show_tools),
                "show_deck": lambda _: QTimer.singleShot(0, self._show_deck),
                "triple_layout": lambda _: QTimer.singleShot(0, self._engage_triple_layout),
                "gaze_look_up": lambda _: self.request_ui.emit("gaze_look_up", True),
                "gaze_scroll_tools": lambda _: self.request_ui.emit("gaze_scroll_tools", True),
                "gaze_look_center": lambda _: self.request_ui.emit("gaze_look_center", True),
                "gaze_zone": lambda p: self.request_ui.emit("gaze_zone", p),
                "iss_deck": lambda _: self.request_ui.emit("iss_deck", True),
                "voice_clone_ui": lambda p: self.request_ui.emit("voice_clone_ui", p),
                "app_exit": lambda code: QTimer.singleShot(
                    2200, lambda c=int(code): self._request_app_exit(c)
                ),
            }
        )
        # Live secondary-monitor feed — every push streams immediately
        try:
            brain.feed.on_push(
                lambda item: QTimer.singleShot(0, lambda i=item: self._on_live_feed_item(i))
            )
        except Exception:
            pass
        QTimer.singleShot(300, self._refresh_ops_feed)

    def attach_ops_monitor(self, ops) -> None:
        self.ops = ops

    def _ops_stats(self, stats) -> None:
        self._apply_stats(stats)

    def _place_on_monitor(self, prefer: str, *, which: str = "hud") -> None:
        from jarvis.core.displays import displays

        prefer = prefer or "secondary"
        if which == "ops":
            self._show_ops()
            if self.ops:
                msg = displays.place_widget(self.ops, prefer, maximize=True)
                self.append_log(f"DISPLAY › ops {msg}")
            return
        if which == "tools":
            self._show_tools()
            if self.tools:
                msg = displays.place_widget(self.tools, prefer, maximize=True)
                self.append_log(f"DISPLAY › tools {msg}")
            return
        if which == "deck":
            self._show_deck()
            if self.deck_win:
                msg = displays.place_widget(self.deck_win, prefer, maximize=True)
                self.append_log(f"DISPLAY › deck {msg}")
            return
        msg = displays.place_widget(self, prefer, maximize=False)
        self.append_log(f"DISPLAY › hud {msg}")

    def _show_ops(self) -> None:
        from jarvis.core.displays import displays

        if self.ops is None:
            try:
                from jarvis.ui.widgets.ops_monitor import OpsMonitorWindow

                self.ops = OpsMonitorWindow(self.settings)
            except Exception as e:
                self.append_log(f"DISPLAY › could not open ops board: {e}")
                return
        pref = getattr(self.settings, "ops_monitor", "secondary") or "secondary"
        displays.place_widget(self.ops, pref, maximize=True)
        self.ops.show()
        self._refresh_ops_feed()
        self.append_log("DISPLAY › live ops board on other monitor")

    def _show_tools(self) -> None:
        from jarvis.core.displays import displays

        if self.tools is None:
            try:
                from jarvis.ui.widgets.tools_monitor import ToolsMonitorWindow

                self.tools = ToolsMonitorWindow(self.settings)
            except Exception as e:
                self.append_log(f"DISPLAY › tools panel failed: {e}")
                return
        pref = getattr(self.settings, "tools_monitor", "left") or "left"
        displays.place_widget(self.tools, pref, maximize=True)
        self.tools.show()
        try:
            if self.brain and getattr(self.brain, "net_watch", None):
                self.tools.set_net_status(self.brain.net_watch.status())
        except Exception:
            pass
        self.append_log("DISPLAY › tools stream on Screen 2")

    def _show_deck(self) -> None:
        from jarvis.core.displays import displays

        if self.deck_win is None:
            try:
                from jarvis.ui.widgets.deck_monitor import DeckMonitorWindow

                self.deck_win = DeckMonitorWindow(self.settings)
            except Exception as e:
                self.append_log(f"DISPLAY › command deck failed: {e}")
                return
        pref = getattr(self.settings, "deck_monitor", "top") or "top"
        displays.place_widget(self.deck_win, pref, maximize=True)
        self.deck_win.show()
        try:
            if self.brain and getattr(self.brain, "feed", None):
                self.deck_win.set_feed(self.brain.feed.lines_for_ui(18))
        except Exception:
            pass
        self.append_log("DISPLAY › command deck on Screen 3")

    def _engage_triple_layout(self) -> None:
        """Screen 1 control HUD · Screen 2 tools · Screen 3 command deck."""
        from jarvis.core.displays import displays

        displays.refresh()
        self._place_on_monitor(
            getattr(self.settings, "hud_monitor", "primary") or "primary", which="hud"
        )
        self._show_tools()
        self._show_deck()
        try:
            self.settings.triple_layout_enabled = True
            self.settings.tools_monitor = "left"
            self.settings.deck_monitor = "top"
            self.settings.hud_monitor = "primary"
            self.settings.save()
        except Exception:
            pass
        self.append_log("DISPLAY › triple layout engaged (control · tools · deck)")
        try:
            if self.brain:
                self.brain.say(
                    "Triple monitors online. Control hub, tools stream, and command deck."
                )
        except Exception:
            pass

    def _on_gaze_look_up(self) -> None:
        """Look at top screen ≥3s → open deck + detail submenu."""
        self._show_deck()
        if self.deck_win is not None:
            self.deck_win.set_detail_mode(True)
            self.deck_win.set_vision("Gaze · looking UP (deck detail)")
        self.append_log("GAZE › look-up dwell → command deck detail")

    def _on_gaze_scroll_tools(self) -> None:
        """Look left ≥2s → scroll tools console."""
        if self.tools is None or not self.tools.isVisible():
            self._show_tools()
        if self.tools is not None:
            self.tools.scroll_console(4)
            self.tools.append_log("GAZE › look-left scroll")
        self.append_log("GAZE › look-left → tools scroll")

    def _on_gaze_look_center(self) -> None:
        if self.deck_win is not None and getattr(self.deck_win, "_detail", False):
            self.deck_win.set_detail_mode(False)
            self.deck_win.set_vision("Gaze · center")
        self.append_log("GAZE › center — deck detail released")

    def _on_gaze_zone(self, payload) -> None:
        if not isinstance(payload, dict):
            return
        zone = str(payload.get("zone") or "")
        if self.deck_win is not None and self.deck_win.isVisible() and zone:
            dwell = payload.get("dwell", 0)
            self.deck_win.set_vision(f"Gaze · {zone} ({dwell}s)")

    def _on_iss_deck(self) -> None:
        """ISS overhead → force command deck + detail alert."""
        self._show_deck()
        msg = "ISS overhead — tracking map on command deck."
        try:
            from jarvis.core.space_weather import SpaceWeather

            msg = SpaceWeather().iss_overhead() or msg
        except Exception:
            pass
        if self.deck_win is not None:
            self.deck_win.set_iss_alert(msg)
        self.append_log(f"SPACE › {msg}")

    def _on_voice_clone_ui(self, payload) -> None:
        """Left tools monitor — which clone is active + waveform cue."""
        if self.tools is None or not self.tools.isVisible():
            self._show_tools()
        if self.tools is not None:
            self.tools.set_clone_status(payload if isinstance(payload, dict) else {})
            if isinstance(payload, dict) and payload.get("message"):
                self.tools.append_log(f"CLONE › {payload.get('message')}")
        self.append_log(
            f"CLONE › {payload.get('active') if isinstance(payload, dict) else payload}"
        )

    def _refresh_ops_feed(self) -> None:
        if not self.brain or not getattr(self.brain, "feed", None):
            return
        try:
            items = self.brain.feed.items_for_ui(32)
            if self.ops:
                self.ops.set_items(items)
            lines = self.brain.feed.lines_for_ui(18)
            self.deck.set_feed(lines)
        except Exception:
            pass

    def _on_live_feed_item(self, item: dict) -> None:
        """Stream one activity event to the secondary live feed (animated)."""
        try:
            # Only update PDTester if already open — never auto-spawn it
            if self.ops is not None and self.ops.isVisible():
                self.ops.push_live_item(item)
                self.ops.set_now_working(
                    str(item.get("kind") or "info"),
                    str(item.get("text") or ""),
                )
            # Keep HUD deck in sync (string lines)
            if self.brain:
                lines = self.brain.feed.lines_for_ui(14)
                self.deck.set_feed(lines)
                if self.deck_win is not None and self.deck_win.isVisible():
                    self.deck_win.set_feed(lines)
        except Exception:
            pass

    def _apply_feed(self, lines) -> None:
        def _mirror_str_lines(str_lines: list[str]) -> None:
            self.deck.set_feed(str_lines)
            try:
                if self.deck_win is not None and self.deck_win.isVisible():
                    self.deck_win.set_feed(str_lines)
            except Exception:
                pass
            try:
                if self.tools is not None and self.tools.isVisible():
                    self.tools.set_lines(str_lines)
            except Exception:
                pass
            if self.ops:
                try:
                    self.ops.set_feed(str_lines)
                except Exception:
                    pass

        if isinstance(lines, list) and lines:
            # Prefer rich items when available
            if lines and all(isinstance(x, dict) for x in lines):
                if self.ops:
                    try:
                        self.ops.set_items(lines)
                    except Exception:
                        pass
                str_lines = [
                    f"{(x.get('ts') or '')[11:16]}  {(x.get('kind') or '').upper()}  {x.get('text', '')}"
                    for x in lines
                ]
                _mirror_str_lines(str_lines)
                return
            _mirror_str_lines([str(x) for x in lines])
        elif isinstance(lines, str) and lines.strip():
            self.deck.prepend_feed(lines.strip())
            try:
                if self.deck_win is not None and self.deck_win.isVisible():
                    # Refresh from brain when possible; else prepend as single line
                    if self.brain and getattr(self.brain, "feed", None):
                        self.deck_win.set_feed(self.brain.feed.lines_for_ui(18))
            except Exception:
                pass
            try:
                if self.tools is not None and self.tools.isVisible():
                    self.tools.append_log(lines.strip())
            except Exception:
                pass
            if self.ops:
                try:
                    self.ops.set_status(lines.strip()[:160])
                except Exception:
                    pass

    def _apply_stats(self, stats) -> None:
        if not isinstance(stats, dict):
            return
        accent = "#00f0ff"
        try:
            from jarvis.ui.styles import mood_palette

            accent = mood_palette(getattr(self, "_wx_mood", "clear")).get("accent", accent)
        except Exception:
            pass
        self.deck.set_stats(stats, accent=accent)
        if self.ops:
            try:
                self.ops.set_stats(stats, accent=accent)
                self.ops.set_accent(accent)
            except Exception:
                pass

    def _hud_alert(self, text: str) -> None:
        self.append_log(f"ALERT › {text[:200]}")
        self.alert.show_alert(text)
        self.alert.setFixedWidth(min(720, self.width() - 80))
        self.alert.move(40, 56)

    def _offer_quick(self, text: str) -> None:
        self.quick.offer(text)
        self.quick.move(max(20, self.width() - self.quick.width() - 40), 70)

    def _offer_hitl(self, payload) -> None:
        if not isinstance(payload, dict):
            return
        # Always sit above Build Theater / other overlays
        try:
            root = self.centralWidget() or getattr(self, "_root", None)
            if root is not None:
                self.hitl_gate.setParent(root)
        except Exception:
            pass
        self.hitl_gate.offer(payload)
        parent = self.hitl_gate.parentWidget() or self
        pw = parent.width() if hasattr(parent, "width") else self.width()
        ph = parent.height() if hasattr(parent, "height") else self.height()
        self.hitl_gate.move(
            max(20, (pw - self.hitl_gate.width()) // 2),
            max(48, ph // 6),
        )
        self.hitl_gate.show()
        self.hitl_gate.raise_()
        self.hitl_gate.activateWindow()
        self._stack_overlays()
        title = payload.get("title") or "permission"
        self.append_log(f"HITL › {title}")
        for i, opt in enumerate(payload.get("options") or [], start=1):
            self.append_log(f"  {i}. {opt}")
        try:
            self._reactor_activity("fetch")
        except Exception:
            pass
        self.status.setText("● CHOOSE OPTION")

    def _on_hitl_decided(self, request_id: str, approve: bool, answer: str) -> None:
        if not self.brain:
            return
        # Async multi-choice clarify chips
        if getattr(self.brain, "_pending_clarify", None) and (
            answer or not approve
        ):
            msg = self.brain.resolve_clarify_choice(answer if approve else "cancel")
            self.append_log(f"CLARIFY › {msg or 'cancelled'}")
            return
        msg = self.brain.resolve_hitl(request_id, approve=approve, answer=answer)
        if msg:
            self.append_log(f"HITL › {msg}")
            if not answer:
                try:
                    self.brain.say(msg)
                except Exception:
                    pass
        else:
            try:
                self.hitl_gate.hide_gate()
            except Exception:
                pass

    def _accept_quick_action(self) -> None:
        if self.brain:
            reply = self.brain.accept_suggestion()
            if reply:
                self.append_log(f"SUGGEST › {reply[:200]}")
                try:
                    self.brain.say(reply)
                except Exception:
                    pass

    def _rlhf_verdict(self, approve: bool) -> None:
        if not self.brain:
            return
        try:
            msg = self.brain.rlhf.approve() if approve else self.brain.rlhf.reject()
            self.append_log(f"RLHF › {msg}")
            self._hud_alert("RLHF · approve" if approve else "RLHF · reject")
            if self.brain:
                self.brain.say(msg)
        except Exception as e:
            self.append_log(f"RLHF › {e}")

    def _panic(self) -> None:
        if self.brain:
            msg = self.brain.panic_now()
            self.append_log(f"PANIC › {msg}")
            self._hud_alert(msg)

    def _set_panic_core(self, on: bool) -> None:
        try:
            self.reactor.set_panic(on)
        except Exception:
            pass
        if on:
            self.status.setText("● PANIC")
            self.status.setStyleSheet("color:#ff3030; font-size:11px;")
            self.append_log("CORE › crimson — panic mode")
        else:
            self.status.setText("● OPTIMAL")
            self.status.setStyleSheet("color:#00f0ff; font-size:11px;")
            self.append_log("CORE › restored")

    def _set_travis_core(self, mode: str) -> None:
        """Sync ArcReactor palette to Travis Park / Tactical / Peer Review."""
        mode = (mode or "off").strip().lower()
        try:
            self.reactor.set_travis_mode(mode)
        except Exception:
            pass
        labels = {
            "park": ("● TRAVIS · PARK", "#FFC848"),
            "tactical": ("● TRAVIS · TACTICAL", "#1AFF7A"),
            "peer": ("● TRAVIS · PEER", "#2A6BFF"),
            "peer_review": ("● TRAVIS · PEER", "#2A6BFF"),
        }
        if mode in labels:
            text, color = labels[mode]
            self.status.setText(text)
            self.status.setStyleSheet(f"color:{color}; font-size:11px;")
            self.append_log(f"TRAVIS › {mode} mode")
            try:
                self.reactor.set_activity(
                    "park" if mode == "park" else ("peer" if "peer" in mode else "tactical")
                )
            except Exception:
                pass
        else:
            self.status.setText("● OPTIMAL")
            self.status.setStyleSheet("color:#00f0ff; font-size:11px;")
            self.append_log("TRAVIS › modes cleared")

    def _on_start_clicked(self) -> None:
        if self.brain:
            self.brain.trigger_start()
        else:
            self.append_log("START › brain not ready")

    def _stack_overlays(self) -> None:
        """Atmosphere film under interactive overlays (HITL / artifact / theaters)."""
        try:
            cam_up = bool(getattr(self, "camera", None) and self.camera.isVisible())
            upg_up = bool(getattr(self, "upgrade", None) and self.upgrade.isVisible())
            if (
                getattr(self, "atmosphere", None)
                and self.atmosphere.isVisible()
                and not cam_up
                and not upg_up
            ):
                self.atmosphere.raise_()
            for w in (
                getattr(self, "typing", None),
                getattr(self, "upgrade", None),
                getattr(self, "alert", None),
                getattr(self, "quick", None),
                getattr(self, "hitl_gate", None),
                getattr(self, "camera", None),
                getattr(self, "news", None),
                getattr(self, "site_preview", None),
                getattr(self, "code_preview", None),
                getattr(self, "build_theater", None),
                getattr(self, "away_theater", None),
                getattr(self, "countdown", None),
                getattr(self, "artifact", None),
                getattr(self, "nv_badge", None),
            ):
                if w is not None and w.isVisible():
                    w.raise_()
            if getattr(self, "startup", None) and self.startup.isVisible():
                self.startup.raise_()
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        try:
            self.typing.setGeometry(self.centralWidget().rect())
            if hasattr(self, "upgrade") and self.centralWidget() is not None:
                r = self.centralWidget().rect()
                self.upgrade.setGeometry(0, 0, r.width(), r.height())
            if hasattr(self, "atmosphere"):
                self.atmosphere.setGeometry(self.centralWidget().rect())
            try:
                self.artifact.reposition()
            except Exception:
                pass
            if self.alert.isVisible():
                self.alert.move(40, 56)
            if self.quick.isVisible():
                self.quick.move(max(20, self.width() - self.quick.width() - 40), 70)
            if self.hitl_gate.isVisible():
                self.hitl_gate.move(
                    max(20, (self.width() - self.hitl_gate.width()) // 2),
                    max(40, self.height() // 5),
                )
            self._stack_overlays()
        except Exception:
            pass

    def _on_start_pulse(self) -> None:
        self.reactor.pulse_speak()
        try:
            self.start_btn.pulse_success()
        except Exception:
            pass
        self.status.setText("● STARTED")
        # Don't wipe StatusPill QSS with an inline stylesheet
        try:
            self.status.setStyleSheet("")
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
        except Exception:
            pass
        self.append_log("START › ready")
        self.input.setFocus()
        QTimer.singleShot(1600, lambda: self.status.setText("● OPTIMAL"))

    def _on_track(self, name: str) -> None:
        self.media.set_track(name)
        self.append_log(f"MUSIC › {name}")

    def _media_action(self, action: str) -> None:
        if not self.brain:
            return
        # Play always starts music (presses Play) — not a toggle
        mapping = {
            "playpause": "play music",
            "play": "play music",
            "previous": "previous track",
            "next": "next track",
            "mute": "mute",
        }
        self.append_log(f"PLAYER › {action}")
        self._dispatch_brain(mapping.get(action, action))

    def _do_scan(self, ocr: bool = True) -> None:
        if not self.brain:
            return

        # Ensure camera is open (do not mark busy yet — we re-enter after open)
        if not self.camera.isVisible() or self.camera._cap is None:
            self._toggle_camera(True)
            self.append_log("SCAN › opening EMEET — hold item in the green box")
            QTimer.singleShot(1100, lambda: self._do_scan(ocr))
            return

        if getattr(self, "_scan_busy", False):
            return
        self._scan_busy = True

        self.camera.show_result("Hold steady… scanning once")
        self.status.setText("● SCANNING")
        self.append_log("SCAN › capturing one frame…")

        # Grab several fresh frames; pick the best (not blank/white)
        def capture_and_scan():
            frame = None
            try:
                frame = self.camera.grab_best_frame(10)
            except Exception:
                frame = self.camera.current_frame()
            if frame is None:
                try:
                    self.camera._paint_frame()
                except Exception:
                    pass
                frame = self.camera.current_frame()
            if frame is None:
                self._scan_busy = False
                if self.brain:
                    self.brain._scanning = False
                QTimer.singleShot(
                    0,
                    lambda: self._on_scan_result(
                        "No frame yet — wait a second and press SCAN again."
                    ),
                )
                return

            def work():
                reply = self.brain.scan_frame(frame, ocr=ocr)
                QTimer.singleShot(0, lambda: self._on_scan_result(reply))
                try:
                    self.brain.say(reply)
                except Exception:
                    pass

            import threading

            threading.Thread(target=work, daemon=True, name="jarvis-scan").start()

        QTimer.singleShot(500, capture_and_scan)

    def _on_scan_result(self, text: str) -> None:
        self.append_log(f"SCAN › {text[:240]}")
        if self.camera.isVisible():
            self.camera.show_result(text)
        self.status.setText("● OPTIMAL")
        # Companion artifact panel (no freeze — already off camera thread)
        try:
            frame = None
            if self.brain and getattr(self.brain, "_last_frame", None) is not None:
                frame = self.brain._last_frame
            self._show_artifact(
                {"title": "SCAN", "text": text, "meta": "camera capture", "frame": frame}
            )
        except Exception:
            pass

    def _show_artifact(self, payload) -> None:
        if not isinstance(payload, dict):
            payload = {"text": str(payload)}
        try:
            self.artifact.show_artifact(
                title=str(payload.get("title") or "ARTIFACT"),
                text=str(payload.get("text") or payload.get("body") or ""),
                image_path=str(payload.get("image_path") or ""),
                image_bgr=payload.get("frame"),
                meta=str(payload.get("meta") or ""),
            )
            self._stack_overlays()
        except Exception as e:
            self.append_log(f"ARTIFACT › {e}")

    def _on_state_ui(self, s) -> None:
        """Log state transitions without flooding the mission log."""
        if not isinstance(s, dict):
            return
        fr = str(s.get("from") or "")
        to = str(s.get("to") or "")
        if not to or fr == to:
            return
        # Skip noisy micro-transitions
        noisy = {"idle", "listen", "listening", "ready"}
        if fr.lower() in noisy and to.lower() in noisy:
            return
        key = f"{fr}->{to}"
        import time as _t

        now = _t.monotonic()
        if key == getattr(self, "_last_state_ui", "") and (
            now - float(getattr(self, "_last_state_ui_at", 0) or 0)
        ) < 4.0:
            return
        self._last_state_ui = key
        self._last_state_ui_at = now
        self.append_log(f"STATE › {fr} → {to}")

    def _on_mic_level(self, level: float) -> None:
        try:
            self.reactor.set_amplitude(level)
        except Exception:
            pass
        try:
            if getattr(self, "wave", None):
                self.wave.set_amplitude(level)
        except Exception:
            pass
        try:
            if self.tools is not None and self.tools.isVisible():
                self.tools.set_amplitude(level)
        except Exception:
            pass
        # Soft glow on mic pill — throttle setStyleSheet (expensive on main thread)
        try:
            band = 0 if level < 0.08 else (1 if level < 0.35 else 2)
            if band == getattr(self, "_mic_glow_band", -1):
                return
            self._mic_glow_band = band
            if band == 0:
                if self.listen.objectName() == "MicPill":
                    self.listen.setStyleSheet("")
            else:
                glow = 120 if band == 1 else 220
                self.listen.setStyleSheet(
                    f"color: rgb(0,{glow},255); font-size:11px; letter-spacing:1px;"
                )
        except Exception:
            pass

    def _apply_performance_mode(self, on: bool) -> None:
        """Smooth / eco HUD — lower paint rates so voice stays snappy."""
        try:
            self.reactor.set_target_fps(8 if on else 15)
        except Exception:
            pass
        try:
            if getattr(self, "wave", None):
                self.wave.set_eco(on)
        except Exception:
            pass
        try:
            if hasattr(self.camera, "set_paint_interval"):
                self.camera.set_paint_interval(110 if on else 66)
        except Exception:
            pass
        try:
            # Slow background HUD timers in smooth mode
            if getattr(self, "_wx", None):
                self._wx.setInterval(180_000 if on else 90_000)
            if getattr(self, "_orb", None):
                self._orb.setInterval(60_000 if on else 30_000)
            if getattr(self, "_tel", None) and on:
                self._tel.setInterval(
                    max(
                        1500,
                        int(
                            getattr(self.settings, "telemetry_interval_ms", 2000) or 2000
                        ),
                    )
                )
        except Exception:
            pass
        try:
            if on:
                self.status.setText("● SMOOTH MODE")
                self.append_log("CORE › smooth mode — HUD throttled")
            else:
                self.status.setText("● OPTIMAL")
                self.append_log("CORE › full fidelity HUD")
        except Exception:
            pass

    def _on_scan_done(self) -> None:
        """One-shot scan finished — close camera so it stops scanning."""
        self._scan_busy = False
        self.append_log("SCAN › done — camera closing")
        self.status.setText("● SCAN COMPLETE")
        # Brief moment to show result text, then stop the feed
        QTimer.singleShot(900, lambda: self._toggle_camera(False))
        QTimer.singleShot(
            1200,
            lambda: self.status.setText("● OPTIMAL"),
        )

    def append_log(self, text: str) -> None:
        text = str(text or "").rstrip()
        if not text:
            return
        # Dedupe identical consecutive lines (speak + speak_ui, stark arrival, etc.)
        try:
            import time as _t

            now = _t.monotonic()
            if text == getattr(self, "_last_log_line", None) and (
                now - float(getattr(self, "_last_log_at", 0) or 0)
            ) < 2.0:
                return
            self._last_log_line = text
            self._last_log_at = now
        except Exception:
            pass
        self.log.append(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        try:
            if self.tools is not None and self.tools.isVisible():
                self.tools.append_log(text)
        except Exception:
            pass

    def _reactor_activity(self, mode: str) -> None:
        """Drive cyan core intensity + memory-map carve from HUD/brain events."""
        try:
            if mode in ("speak",):
                self.reactor.pulse_speak()
            else:
                self.reactor.set_activity(mode)
                if mode in ("build", "site", "vibe", "away", "fetch"):
                    self.reactor.flare(0.9)
        except Exception:
            pass
        try:
            carving = mode in (
                "build",
                "site",
                "vibe",
                "fetch",
                "thinking",
                "compiling",
                "code",
            )
            self.memory_map.set_carving(carving, label=str(mode or ""))
        except Exception:
            pass
        try:
            if mode in ("panic",):
                self.atmosphere.trigger_glitch(0.18)
        except Exception:
            pass

    def _on_speak(self, text: str) -> None:
        # Mission log (deduped vs speak_ui when both fire for the same line)
        if text:
            self.append_log(f"JARVIS › {text}")
        self._reactor_activity("speak")
        # Speak cue fires from _on_jarvis_speaking when TTS actually starts

    def _on_jarvis_speaking(self, active: bool) -> None:
        """Keep the core alive for the full TTS playback window."""
        try:
            self._tts_active = bool(active)
        except Exception:
            pass
        try:
            if getattr(self, "wave", None):
                self.wave.set_speaking(bool(active))
        except Exception:
            pass
        try:
            if self.tools is not None and self.tools.isVisible():
                self.tools.set_speaking(bool(active))
        except Exception:
            pass
        try:
            if active:
                self.reactor.set_speaking(True)
                self._reactor_activity("speak")
                try:
                    from jarvis.ui.hud_sfx import play_speak_cue

                    play_speak_cue()
                except Exception:
                    pass
            else:
                self.reactor.set_speaking(False)
                try:
                    from jarvis.ui.hud_sfx import play_confirm

                    play_confirm()
                except Exception:
                    pass
                mode = getattr(self.reactor, "_activity", "idle")
                if mode in ("speak", "idle"):
                    self._reactor_activity("idle")
        except Exception:
            pass

    def _on_quick_toggle(self, key: str, on: bool) -> None:
        """QUICK · RELAYS grid — lamp / night / quiet / smooth / mini / listen."""
        key = (key or "").lower()
        try:
            if key == "lamp":
                self._cmd("turn on the lamp" if on else "turn off the lamp")
            elif key == "night":
                self._cmd("night vision on" if on else "night vision off")
            elif key == "quiet":
                self._cmd("quiet mode" if on else "leave quiet mode")
            elif key == "smooth":
                self._cmd("smooth mode" if on else "smooth mode off")
            elif key == "mini":
                self._set_mini_mode(on)
            elif key == "listen":
                # Arm / disarm wake-required loosely via quiet opposite
                if self.brain and hasattr(self.brain.settings, "wake_required"):
                    self.brain.settings.wake_required = not on
                    self.append_log(
                        "VOICE › open listen" if on else "VOICE › wake required"
                    )
            self.append_log(f"RELAY › {key.upper()} {'ON' if on else 'OFF'}")
        except Exception as e:
            self.append_log(f"RELAY › {key} failed: {e}")

    def _set_mini_mode(self, on: bool) -> None:
        """Collapse HUD into a small always-on-top corner widget."""
        try:
            if on:
                if not hasattr(self, "_full_geometry"):
                    self._full_geometry = self.geometry()
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
                rail = getattr(self, "_left_rail", None)
                if rail:
                    rail.hide()
                # Hide right column
                if getattr(self, "_hud", None):
                    lay = self._hud.layout()
                    if lay and lay.count() >= 3:
                        right = lay.itemAt(2).widget()
                        if right:
                            right.hide()
                self.resize(520, 640)
                screen = self.screen()
                if screen:
                    geo = screen.availableGeometry()
                    self.move(geo.right() - self.width() - 16, geo.bottom() - self.height() - 16)
                self.show()
                self.append_log("HUD › mini mode — corner widget")
            else:
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
                rail = getattr(self, "_left_rail", None)
                if rail:
                    rail.show()
                if getattr(self, "_hud", None):
                    lay = self._hud.layout()
                    if lay and lay.count() >= 3:
                        right = lay.itemAt(2).widget()
                        if right:
                            right.show()
                if hasattr(self, "_full_geometry") and self._full_geometry:
                    self.setGeometry(self._full_geometry)
                else:
                    self.resize(1560, 940)
                self.show()
                self.append_log("HUD › full command center")
        except Exception as e:
            self.append_log(f"HUD › mini failed: {e}")

    def _set_listen(self, active: bool) -> None:
        self.listen.setText("● LISTENING" if active else "MIC STANDBY")
        if active:
            self._reactor_activity("listen")
        elif not getattr(self, "_tts_active", False):
            # Don't kill core while Jarvis is still talking
            try:
                mode = getattr(self.reactor, "_activity", "idle")
                if mode in ("listen", "speak", "idle"):
                    self._reactor_activity("idle")
            except Exception:
                pass
        if active:
            self.listen.setObjectName("StatusPill")
            self.listen.setStyleSheet("")
            # Force style refresh
            self.listen.style().unpolish(self.listen)
            self.listen.style().polish(self.listen)
        else:
            self.listen.setObjectName("MicPill")
            self.listen.setStyleSheet("")
            self.listen.style().unpolish(self.listen)
            self.listen.style().polish(self.listen)

    def _start_lock_countdown(self, seconds: int) -> None:
        secs = max(1, int(seconds))
        self.append_log(
            f"SECURITY › presence lost — locking in {secs}s unless you return"
        )
        self.status.setText("● PRESENCE LOST")
        self.status.setStyleSheet("color:#ff6b35; font-size:11px;")
        self.countdown.start(secs)

    def _set_night_vision(self, on: bool) -> None:
        try:
            from jarvis.core.boot_biometrics import is_night_hours

            if on and not is_night_hours():
                self.append_log(
                    "OPTICS › night vision only arms at night (8pm-6am)"
                )
                on = False
        except Exception:
            pass
        try:
            self.nv_badge.set_mode("nv")
            self.nv_badge.set_active(on, mode="nv")
            self.nv_badge.move(24, 72)
            self.nv_badge.raise_()
        except Exception:
            pass
        try:
            self.camera.set_night_vision(on)
        except Exception:
            pass
        if on:
            self.append_log("OPTICS › night vision online")
            self.status.setText("● NIGHT VISION")
            self.status.setStyleSheet("color:#39ff7a; font-size:11px;")
            # Reveal the green feed if theater isn't open yet
            if not self.camera.isVisible():
                self._toggle_camera(True)
        else:
            self.append_log("OPTICS › day feed / night vision offline")
            if not self.countdown.isVisible():
                # Keep thermal status if that is still on
                if getattr(self.camera, "_thermal_assist", False):
                    self.status.setText("● THERMAL ASSIST")
                    self.status.setStyleSheet("color:#ff9a4a; font-size:11px;")
                else:
                    self.status.setText("● OPTIMAL")
                    self.status.setStyleSheet("color:#00f0ff; font-size:11px;")

    def _set_thermal_assist(self, on: bool) -> None:
        on = bool(on)
        try:
            if on:
                self.nv_badge.set_mode("thermal")
                self.nv_badge.set_active(True, mode="thermal")
            else:
                # If night vision still on, restore NV badge; else hide
                nv_on = bool(getattr(self.camera, "_night_vision", False))
                if nv_on:
                    self.nv_badge.set_active(True, mode="nv")
                else:
                    self.nv_badge.set_active(False)
            self.nv_badge.move(24, 72)
            self.nv_badge.raise_()
        except Exception:
            pass
        try:
            self.camera.set_thermal_assist(on)
        except Exception:
            pass
        if on:
            self.append_log("OPTICS › thermal assist online (software · not FLIR)")
            self.status.setText("● THERMAL ASSIST")
            self.status.setStyleSheet("color:#ff9a4a; font-size:11px;")
            if not self.camera.isVisible():
                self._toggle_camera(True)
        else:
            self.append_log("OPTICS › thermal assist offline")
            if not self.countdown.isVisible():
                if getattr(self.camera, "_night_vision", False):
                    self.status.setText("● NIGHT VISION")
                    self.status.setStyleSheet("color:#39ff7a; font-size:11px;")
                else:
                    self.status.setText("● OPTIMAL")
                    self.status.setStyleSheet("color:#00f0ff; font-size:11px;")

    def _boot_optics_auto(self) -> None:
        """After HUD boot: arm night vision automatically only at night."""
        try:
            from jarvis.core.boot_biometrics import is_night_hours

            if is_night_hours():
                self._set_night_vision(True)
                self.append_log("OPTICS › night window — NV armed")
            else:
                self.append_log("OPTICS › day feed standing by")
        except Exception as e:
            self.append_log(f"OPTICS › {e}")

    def _set_spatial(self, on: bool) -> None:
        try:
            if self._spatial:
                msg = self._spatial.set_enabled(on)
                self.append_log(f"SPATIAL › {msg}")
                self.status.setText(f"● {msg}")
                if on and getattr(self, "camera", None) and not self.camera.isVisible():
                    self._toggle_camera(True)
        except Exception as e:
            self.append_log(f"SPATIAL › {e}")

    def _spatial_status(self) -> None:
        try:
            if self._spatial:
                self.append_log(f"SPATIAL › {self._spatial.status()}")
            else:
                self.append_log("SPATIAL › offline")
        except Exception:
            pass

    def _enroll_grab_frame(self) -> None:
        """Live frame from theater — wait for USB open before grabbing."""
        try:
            if self.camera is not None and not self.camera.isVisible():
                self._toggle_camera(True)
                # open_feed is scheduled ~1400ms; grab after that plus warmup
                QTimer.singleShot(2600, lambda: self._enroll_grab_frame_do(retries=4))
                return
        except Exception:
            pass
        self._enroll_grab_frame_do(retries=4)

    def _enroll_grab_frame_do(self, retries: int = 0) -> None:
        frame = None
        try:
            if self.camera is not None:
                if getattr(self.camera, "_cap", None) is None and retries > 0:
                    QTimer.singleShot(
                        500, lambda: self._enroll_grab_frame_do(retries=retries - 1)
                    )
                    return
                frame = self.camera.grab_best_frame(reads=8)
                if frame is None:
                    frame = self.camera.current_frame()
        except Exception as e:
            self.append_log(f"SECURITY › enroll grab failed: {e}")
        try:
            if frame is not None:
                import cv2
                from jarvis.config import DATA_DIR

                cv2.imwrite(str(DATA_DIR / "last_vision.jpg"), frame)
                self.append_log("SECURITY › captured face frame for enroll")
        except Exception:
            pass
        try:
            if self.brain:
                self.brain.accept_enroll_frame(frame)
        except Exception:
            pass
        if frame is None and retries > 0:
            QTimer.singleShot(
                600, lambda: self._enroll_grab_frame_do(retries=retries - 1)
            )

    def _presence(self, present: bool) -> None:
        if present:
            if not self.countdown.isVisible():
                self.status.setText("● OPTIMAL")
                self.status.setStyleSheet("color:#00f0ff; font-size:11px;")
        else:
            self.status.setText("● PRESENCE LOST")
            self.status.setStyleSheet("color:#ff6b35; font-size:11px;")

    def _on_request_ui(self, key: str, payload: object) -> None:
        """Generic queued UI dispatch from worker threads."""
        if key == "camera_ui":
            self._toggle_camera(bool(payload))
        elif key == "fabricator_ui":
            self._toggle_fabricator(bool(payload))
        elif key == "fabricator_build":
            self._fabricator_build()
        elif key == "aerospatial_ui":
            self._toggle_aerospatial(bool(payload))
        elif key == "ops_hud":
            self._toggle_ops_hud(bool(payload))
        elif key == "traffic_cams":
            self._toggle_traffic_cams(bool(payload))
        elif key == "traffic_board":
            self._open_traffic_board_ui()
        elif key == "traffic_live_map":
            self._toggle_traffic_live_map(bool(payload))
        elif key == "scanner_live":
            self._open_scanner_live(payload)
        elif key == "traffic_cams_next":
            self._next_traffic_cams_page()
        elif key == "traffic_region":
            self._set_traffic_region(str(payload or ""))
        elif key == "ops_pins":
            self._set_ops_pins(payload)
        elif key == "aerospatial_scan":
            self._aerospatial_scan()
        elif key == "aerospatial_deploy":
            self._aerospatial_deploy(str(payload or "desktop"))
        elif key == "aerospatial_cinematic":
            self._aerospatial_cinematic(bool(payload))
        elif key == "aerospatial_biometric":
            self._aerospatial_biometric()
        elif key == "aerospatial_gauges":
            self._aerospatial_flag("pc_gauges", True)
        elif key == "aerospatial_web":
            self._aerospatial_flag("web_shooter", True)
        elif key == "upgrade_ui":
            self._upgrade_ui(payload)
        elif key == "command_ui":
            self._command_ui(payload)
        elif key == "registry_ui":
            try:
                frozen = bool((payload or {}).get("frozen")) if isinstance(payload, dict) else bool(payload)
                self.cmd_monitor.set_registry_state(frozen)
            except Exception:
                pass
        elif key == "monitor_ui":
            try:
                show = bool(payload) if payload is not False else False
                self.cmd_monitor.setVisible(show)
                if show:
                    self.cmd_monitor.raise_()
            except Exception:
                pass
        elif key == "map_ui":
            self._toggle_map(payload)
        elif key == "news_ui":
            self._toggle_news(payload)
        elif key == "site_ui":
            self._toggle_site(payload)
        elif key == "site_progress":
            self._site_progress(payload)
        elif key == "code_ui":
            self._toggle_code(payload)
        elif key == "code_progress":
            self._code_progress(payload)
        elif key == "theater_tab":
            self._theater_tab(payload)
        elif key == "away_ui":
            self._toggle_away(payload)
        elif key == "away_progress":
            self._away_progress(payload)
        elif key == "hitl_ask":
            self._offer_hitl(payload)
        elif key == "hitl_clear":
            try:
                self.hitl_gate.hide_gate()
            except Exception:
                pass
        elif key == "gaze_look_up":
            self._on_gaze_look_up()
        elif key == "gaze_scroll_tools":
            self._on_gaze_scroll_tools()
        elif key == "gaze_look_center":
            self._on_gaze_look_center()
        elif key == "gaze_zone":
            self._on_gaze_zone(payload)
        elif key == "iss_deck":
            self._on_iss_deck()
        elif key == "voice_clone_ui":
            self._on_voice_clone_ui(payload)

    def _command_ui(self, payload) -> None:
        try:
            if not isinstance(payload, dict):
                return
            self.cmd_monitor.note(
                str(payload.get("text") or ""),
                kind=str(payload.get("kind") or "route"),
                detail=str(payload.get("detail") or ""),
            )
        except Exception as e:
            print(f"[command_ui] {e}")

    def _toggle_camera(self, open_it: bool) -> None:
        if open_it:
            if self.brain:
                try:
                    self.brain.pause_presence_lock(True)
                    self.brain.vision.stop()
                except Exception:
                    pass
            self.append_log("CAMERA › full-screen theater — news + Jarvis dock")
            self.status.setText("● CAMERA THEATER")
            self._cam_open_retries = 0
            self._cam_live_raised = False

            # Bring Jarvis to the front — otherwise it "opens" behind Chrome/etc.
            try:
                self.show()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass

            def _open():
                idx = self.settings.camera_index if self.settings.camera_index >= 0 else 0
                prefer = getattr(self.settings, "camera_prefer", "") or "EMEET"
                self.camera.set_gestures_enabled(True)
                # Cover the full window root (not just HUD chrome)
                root = self.centralWidget() or self._root
                if root is not None:
                    self.camera.setParent(root)
                    self.camera.setGeometry(root.rect())
                # Hide competing overlays so the feed is actually visible
                for w in (
                    getattr(self, "atmosphere", None),
                    getattr(self, "typing", None),
                    getattr(self, "startup", None),
                    getattr(self, "alert", None),
                    getattr(self, "quick", None),
                ):
                    try:
                        if w is not None:
                            w.hide()
                    except Exception:
                        pass
                try:
                    self._hud.hide()
                except Exception:
                    pass
                # Show theater shell immediately so voice path feels instant
                self.camera.show()
                self.camera.raise_()
                try:
                    self.camera.view.setText("Opening camera theater…")
                except Exception:
                    pass
                self.camera.open_feed(preferred_index=idx, prefer=prefer)
                self.camera.raise_()
                try:
                    if self.brain and getattr(self.brain, "_night_vision", False):
                        self.camera.set_night_vision(True)
                except Exception:
                    pass
                # Soft-load Defender / LAN line onto camera dock
                QTimer.singleShot(2800, self._refresh_camera_desk_sec)
                # Probe can take several seconds — don't fail while still opening
                QTimer.singleShot(4500, self._ensure_camera_visible)
                QTimer.singleShot(5000, self._persist_camera_index)

            # Give the vision worker time to fully release the USB device
            QTimer.singleShot(2200, _open)
        else:
            self.camera.hide_feed(emit=False)
            try:
                self._hud.show()
            except Exception:
                pass
            self.append_log("CAMERA › theater closed — presence lock armed")
            self.status.setText("● OPTIMAL")
            if self.brain:
                self.brain.pause_presence_lock(False)
                QTimer.singleShot(900, self.brain.vision.start)

    def _ensure_camera_visible(self) -> None:
        """After open attempt: keep theater up, or retry, else restore HUD."""
        if not self.camera.isVisible():
            return
        cap = getattr(self.camera, "_cap", None)
        if cap is not None:
            # Coalesce — one raise pass when live; avoid activate storms
            if not getattr(self, "_cam_live_raised", False):
                self._cam_live_raised = True
                try:
                    self.camera.raise_()
                except Exception:
                    pass
            self._cam_open_retries = 0
            self.append_log("CAMERA › live")
            self.status.setText("● CAMERA LIVE")
            return
        # Still probing — wait, don't declare failure yet
        if bool(getattr(self.camera, "_opening", False)):
            self.append_log("CAMERA › still opening…")
            self.status.setText("● CAMERA OPENING")
            QTimer.singleShot(2500, self._ensure_camera_visible)
            return
        # Retry a few times after release windows (USB often busy right after vision.stop)
        retries = int(getattr(self, "_cam_open_retries", 0) or 0)
        if retries < 3:
            self._cam_open_retries = retries + 1
            self.append_log(f"CAMERA › retrying open ({self._cam_open_retries}/3)…")
            self.status.setText("● CAMERA RETRY")
            try:
                if self.brain:
                    self.brain.vision.stop()
            except Exception:
                pass
            idx = self.settings.camera_index if self.settings.camera_index >= 0 else 0
            prefer = getattr(self.settings, "camera_prefer", "") or "EMEET"

            def _retry():
                self.camera.open_feed(preferred_index=idx, prefer=prefer)
                QTimer.singleShot(4000, self._ensure_camera_visible)

            QTimer.singleShot(1200, _retry)
            return
        self._cam_open_retries = 0
        # Failed to grab a device — don't leave a blank overlay
        msg = self.camera.view.text() if hasattr(self.camera, "view") else ""
        self.append_log(f"CAMERA › open failed — {msg[:80]}")
        self.status.setText("● CAMERA FAILED")
        try:
            self.camera.hide_feed(emit=False)
            self._hud.show()
        except Exception:
            pass
        if self.brain:
            try:
                self.brain.say(
                    "I still couldn't open the camera. "
                    "Close Zoom, Teams, or OBS Virtual Camera, then say open camera again."
                )
            except Exception:
                pass
            self.brain.pause_presence_lock(False)
            QTimer.singleShot(900, self.brain.vision.start)

    def _toggle_fabricator(self, open_it: bool) -> None:
        """Stark Jet hologram lab — hand-tracked suit fabricator over camera."""
        if not open_it:
            try:
                self.camera.close_fabricator()
            except Exception:
                pass
            self.append_log("FABRICATOR › lab closed")
            self.status.setText("● OPTIMAL")
            return
        # Open camera theater first, then lab overlay
        if not self.camera.isVisible():
            self._toggle_camera(True)
        try:
            self.camera.open_fabricator()
            fab = getattr(self.camera, "fabricator", None)
            if fab is not None and not getattr(self, "_fab_built_hooked", False):
                fab.suit_built.connect(self._on_suit_built)
                self._fab_built_hooked = True
        except Exception as e:
            self.append_log(f"FABRICATOR › failed: {e}")
            return
        self.append_log("FABRICATOR › Stark lab OS v4.6.2 online")
        self.status.setText("● STARK FABRICATOR")

    def _toggle_aerospatial(self, open_it: bool) -> None:
        """AR aerospatial mapping — room mesh + fabricator hologram on camera."""
        if not open_it:
            try:
                self.camera.close_aerospatial()
            except Exception:
                pass
            self.append_log("AEROSPATIAL › AR offline")
            self.status.setText("● OPTIMAL")
            return
        if not self.camera.isVisible():
            self._toggle_camera(True)
        try:
            self.camera.open_aerospatial()
            ar = getattr(self.camera, "aerospatial", None)
            if ar is not None and not getattr(self, "_ar_bio_hooked", False):
                ar.biometric_done.connect(self._on_ar_biometric)
                self._ar_bio_hooked = True
        except Exception as e:
            self.append_log(f"AEROSPATIAL › failed: {e}")
            return
        self.append_log("AEROSPATIAL › cinematic room mesh online")
        self.status.setText("● AR AEROSPATIAL")

    def _toggle_ops_hud(self, open_it: bool) -> None:
        """Owner-site ops map overlay on live camera theater."""
        if not open_it:
            try:
                self.camera.close_ops_hud()
            except Exception:
                pass
            self.append_log("OPS HUD › map offline")
            self.status.setText("● OPTIMAL")
            return
        if not self.camera.isVisible():
            self._toggle_camera(True)
        pins = None
        try:
            if self.brain and getattr(self.brain, "ops_hud", None):
                pins = self.brain.ops_hud.pins()
        except Exception:
            pins = None
        try:
            self.camera.open_ops_hud(pins)
        except Exception as e:
            self.append_log(f"OPS HUD › failed: {e}")
            return
        self.append_log("OPS HUD › owner map online")
        self.status.setText("● OPS HUD")

    def _set_ops_pins(self, pins) -> None:
        try:
            self.camera.set_ops_pins(list(pins or []))
        except Exception as e:
            print(f"[ops_hud] set pins: {e}")


    def _toggle_traffic_cams(self, open_it: bool) -> None:
        """Public official DOT/511 traffic stills overlay (no private CCTV)."""
        if not open_it:
            try:
                if getattr(self.camera, "close_traffic_board_panel", None):
                    self.camera.close_traffic_board_panel()
            except Exception:
                pass
            panel = getattr(self, "traffic_board", None)
            if panel is not None:
                try:
                    panel.close_panel()
                except Exception:
                    pass
            try:
                self._toggle_traffic_live_map(False)
            except Exception:
                pass
            self.append_log("TRAFFIC › cams closed")
            self.status.setText("● OPTIMAL")
            return
        city = "Philadelphia"
        fetcher = None
        panel_ref: list = [None]
        try:
            tc = getattr(self.brain, "traffic_cams", None) if self.brain else None
            if tc is not None:
                city = getattr(tc, "city", city) or city

                def fetcher():
                    panel = panel_ref[0]
                    off = 0
                    if panel is not None and hasattr(panel, "page_offset"):
                        try:
                            off = int(panel.page_offset())
                        except Exception:
                            off = 0
                    if hasattr(tc, "live_grid"):
                        return tc.live_grid(4, offset=off)
                    return tc.grid(4, offset=off)

        except Exception as e:
            print(f"[traffic_cams] ui: {e}")

        def _wire_panel(panel) -> None:
            panel_ref[0] = panel
            try:
                panel.region_changed.disconnect()
            except Exception:
                pass
            try:
                panel.find_address.disconnect()
            except Exception:
                pass
            try:
                panel.open_live_map.disconnect()
            except Exception:
                pass
            try:
                panel.open_board.disconnect()
            except Exception:
                pass
            try:
                panel.play_dispatch.disconnect()
            except Exception:
                pass
            try:
                panel.play_listen.disconnect()
            except Exception:
                pass
            try:
                panel.play_truck.disconnect()
            except Exception:
                pass
            try:
                panel.play_sat.disconnect()
            except Exception:
                pass
            panel.open_board.connect(self._open_traffic_board_ui)
            panel.open_live_map.connect(lambda: self._toggle_traffic_live_map(True))
            panel.find_address.connect(self._traffic_find_address)
            panel.region_changed.connect(self._set_traffic_region)
            try:
                panel.play_dispatch.connect(self._traffic_play_dispatch)
            except Exception:
                pass
            try:
                panel.play_listen.connect(self._traffic_play_listen)
            except Exception:
                pass
            try:
                panel.play_truck.connect(self._traffic_play_truck)
            except Exception:
                pass
            try:
                panel.play_sat.connect(self._traffic_play_sat)
            except Exception:
                pass
            try:
                tc = getattr(self.brain, "traffic_cams", None) if self.brain else None
                if tc is not None:
                    panel.set_region(getattr(tc, "region", city))
            except Exception:
                panel.set_city(city)

        # Prefer overlay on camera theater if live; else root panel
        opened = False
        try:
            if self.camera.isVisible() and hasattr(self.camera, "open_traffic_board_panel"):
                self.camera.open_traffic_board_panel(fetcher=fetcher, city=city)
                try:
                    panel = getattr(self.camera, "traffic_board", None)
                    if panel is not None:
                        _wire_panel(panel)
                except Exception:
                    pass
                opened = True
        except Exception as e:
            print(f"[traffic_cams] theater: {e}")
        if not opened:
            try:
                from jarvis.ui.widgets.traffic_board import TrafficBoardPanel

                if getattr(self, "traffic_board", None) is None:
                    root = self.centralWidget() or self._root
                    self.traffic_board = TrafficBoardPanel(root)
                    self.traffic_board.hide()
                panel = self.traffic_board
                _wire_panel(panel)
                if fetcher is not None:
                    panel.set_fetcher(fetcher)
                root = panel.parentWidget() or self
                panel.move(max(12, (root.width() - panel.width()) // 2), 40)
                panel.open_panel()
                panel.raise_()
                opened = True
            except Exception as e:
                self.append_log(f"TRAFFIC › failed: {e}")
                self._open_traffic_board_ui()
                return

        self.append_log(f"TRAFFIC › {city} live map + audio")
        self.status.setText("● TRAFFIC LIVE")
        # JPEG stills often don't move (CDN). Official MAP has real video.
        QTimer.singleShot(250, lambda: self._toggle_traffic_live_map(True))
        # Traffic cams have no audio track — start public scanner listen.
        QTimer.singleShot(600, self._traffic_play_listen)
    def _set_traffic_region(self, region: str) -> None:
        """Switch TrafficCams region and refresh open board."""
        region = (region or "").strip()
        if not region:
            return
        try:
            tc = getattr(self.brain, "traffic_cams", None) if self.brain else None
            if tc is not None and hasattr(tc, "set_region"):
                msg = tc.set_region(region)
                self.append_log(f"TRAFFIC › {msg}")
            # Keep scanner city aligned with board region
            try:
                if self.brain and hasattr(self.brain, "set_traffic_region"):
                    # Already set on tc; just sync scanner without re-opening board
                    sr = getattr(self.brain, "scanner_radio", None)
                    if sr is not None and hasattr(sr, "follow_traffic_region"):
                        if region.lower() not in ("world", ""):
                            sr.follow_traffic_region(region)
                elif self.brain:
                    sr = getattr(self.brain, "scanner_radio", None)
                    if sr is not None and hasattr(sr, "follow_traffic_region"):
                        if region.lower() not in ("world", ""):
                            sr.follow_traffic_region(region)
            except Exception as e:
                print(f"[scanner_radio] ui region: {e}")
            for panel in (
                getattr(self.camera, "traffic_board", None) if self.camera else None,
                getattr(self, "traffic_board", None),
            ):
                if panel is not None and hasattr(panel, "set_region"):
                    try:
                        # Avoid re-emitting region_changed loop: set UI only
                        panel.set_region(region)
                        panel._page = 0
                        panel._had_pixmap = [False] * 4
                        panel._busy = False
                        QTimer.singleShot(80, panel._refresh)
                    except Exception:
                        pass
            self.status.setText(f"● TRAFFIC · {region.upper()[:12]}")
        except Exception as e:
            print(f"[traffic_cams] region: {e}")

    def _traffic_play_dispatch(self) -> None:
        """DISPATCH button → public Broadcastify local dispatch."""
        try:
            self.append_log("SCANNER › local dispatch")
            self._dispatch_brain("put on local dispatch")
        except Exception as e:
            print(f"[traffic_dispatch] {e}")

    def _traffic_play_listen(self) -> None:
        """LISTEN → live city scanner audio (not a dead 'traffic' search)."""
        try:
            self.append_log("SCANNER › live city audio")
            self._dispatch_brain("listen to traffic")
        except Exception as e:
            print(f"[traffic_listen] {e}")

    def _open_scanner_live(self, payload=None) -> None:
        """Embed Broadcastify/NOAA player — prefer camera theater when live."""
        url = "https://www.broadcastify.com/listen/ctid/2291"
        title = "LIVE SCANNER AUDIO"
        if isinstance(payload, dict):
            url = (payload.get("url") or url).strip() or url
            title = (payload.get("title") or title).strip() or title
        elif isinstance(payload, str) and payload.startswith("http"):
            url = payload
        try:
            if (
                self.camera is not None
                and self.camera.isVisible()
                and hasattr(self.camera, "open_scanner_audio")
            ):
                self.camera.open_scanner_audio(url, title=title)
                self.append_log(f"SCANNER › camera player {url[:60]}")
                self.status.setText("● LIVE SCANNER · CAM")
                return
        except Exception as e:
            print(f"[scanner_live] theater: {e}")
        try:
            from jarvis.ui.widgets.traffic_board import ScannerAudioPanel

            if getattr(self, "scanner_audio", None) is None:
                root = self.centralWidget() or self._root
                self.scanner_audio = ScannerAudioPanel(root)
                self.scanner_audio.hide()
            panel = self.scanner_audio
            root = panel.parentWidget() or self
            panel.move(
                max(12, root.width() - panel.width() - 24),
                max(40, (root.height() - panel.height()) // 2),
            )
            panel.open_panel(url, title=title)
            panel.raise_()
            self.append_log(f"SCANNER › live player {url[:60]}")
            self.status.setText("● LIVE SCANNER")
        except Exception as e:
            self.append_log(f"SCANNER › player failed: {e}")
            try:
                import webbrowser

                webbrowser.open(url)
            except Exception:
                pass

    def _camera_desk_lan(self) -> None:
        """LAN button on camera dock — owner network scan."""
        try:
            self.append_log("LAN › camera desk scan")
            if self.camera and hasattr(self.camera, "set_desk_sec_line"):
                self.camera.set_desk_sec_line("LAN · scanning owner network…")
            self._dispatch_brain("scan local network")
        except Exception as e:
            print(f"[camera_lan] {e}")

    def _camera_desk_sec(self) -> None:
        """SEC button on camera dock — Defender + process harden."""
        try:
            self.append_log("SEC › camera desk security scan")
            if self.camera and hasattr(self.camera, "set_desk_sec_line"):
                self.camera.set_desk_sec_line("SEC · Defender + process scan…")
            # Status first (fast), then full scan
            if self.brain and getattr(self.brain, "software_security", None):
                try:
                    st = self.brain.software_security.defender_status()
                    if self.camera and hasattr(self.camera, "set_desk_sec_line"):
                        self.camera.set_desk_sec_line(st[:120])
                    self.append_log(f"SEC › {st[:100]}")
                except Exception:
                    pass
            self._dispatch_brain("security scan")
        except Exception as e:
            print(f"[camera_sec] {e}")

    def _refresh_camera_desk_sec(self) -> None:
        """Populate camera dock SEC line with Defender + net watch snapshot."""
        if not self.camera or not self.camera.isVisible():
            return
        bits = []
        try:
            ss = getattr(self.brain, "software_security", None) if self.brain else None
            if ss is not None:
                bits.append(ss.defender_status()[:70])
        except Exception:
            pass
        try:
            nw = getattr(self.brain, "net_watch", None) if self.brain else None
            if nw is not None and hasattr(nw, "status"):
                bits.append(nw.status())
        except Exception:
            pass
        if not bits:
            bits.append("CAMS · LISTEN · SAT · LAN · SEC on dock")
        try:
            self.camera.set_desk_sec_line(" · ".join(bits)[:140])
        except Exception:
            pass

    def _traffic_play_truck(self) -> None:
        """TRUCK button → public Broadcastify truck / DOT listen."""
        try:
            self.append_log("SCANNER › truck radio")
            self._dispatch_brain("truck dispatch")
        except Exception as e:
            print(f"[traffic_truck] {e}")

    def _traffic_play_sat(self) -> None:
        """SAT → NOAA / satellite weather radio (not traffic-cam mics)."""
        try:
            self.append_log("SCANNER › NOAA / satellite weather radio (cams stay silent)")
            self._dispatch_brain("satellite radio")
        except Exception as e:
            print(f"[traffic_sat] {e}")

    def _traffic_find_address(self) -> None:
        """FIND from traffic board → open tactical map for address search."""
        try:
            if self.brain and hasattr(self.brain, "find_address_on_map"):
                msg = self.brain.find_address_on_map("")
                self.append_log(f"MAP › {msg}")
                return
        except Exception as e:
            print(f"[traffic_find] {e}")
        city = "Philadelphia"
        try:
            city = getattr(self.brain.settings, "city", city) if self.brain else city
        except Exception:
            pass
        self.request_ui.emit("map_ui", {"place": city, "markers": None, "animate": True})
        self.append_log("MAP › find address — say locate / where is / find address …")

    def _next_traffic_cams_page(self) -> None:
        """Rotate to next page of cams on the open traffic board."""
        for panel in (
            getattr(self.camera, "traffic_board", None) if self.camera else None,
            getattr(self, "traffic_board", None),
        ):
            if panel is not None and hasattr(panel, "_next_page") and panel.isVisible():
                try:
                    panel._next_page()
                    self.append_log("TRAFFIC › next cams page")
                    return
                except Exception as e:
                    print(f"[traffic_cams] next: {e}")
        self._toggle_traffic_cams(True)
        self.append_log("TRAFFIC › cams opened — say next traffic cams to rotate")

    def _toggle_traffic_live_map(self, open_it: bool) -> None:
        """Embedded official 511/DOT interactive map for current region."""
        if not open_it:
            try:
                if getattr(self.camera, "close_traffic_live_map", None):
                    self.camera.close_traffic_live_map()
            except Exception:
                pass
            panel = getattr(self, "traffic_live_map", None)
            if panel is not None:
                try:
                    panel.close_panel()
                except Exception:
                    pass
            self.append_log("TRAFFIC › live map closed")
            return
        map_url = "https://www.511pa.com/"
        title = "LIVE TRAFFIC MAP"
        try:
            tc = getattr(self.brain, "traffic_cams", None) if self.brain else None
            if tc is not None:
                map_url = tc.map_url() if hasattr(tc, "map_url") else getattr(
                    tc, "board_url", map_url
                )
                title = f"{getattr(tc, 'city', 'TRAFFIC')} · LIVE MAP"
        except Exception:
            pass
        try:
            if self.camera.isVisible() and hasattr(self.camera, "open_traffic_live_map"):
                self.camera.open_traffic_live_map(url=map_url, title=title)
                self.append_log(f"TRAFFIC › live map {map_url}")
                self.status.setText("● LIVE TRAFFIC MAP")
                return
        except Exception as e:
            print(f"[traffic_live_map] theater: {e}")
        try:
            from jarvis.ui.widgets.traffic_board import TrafficLiveMapPanel

            if getattr(self, "traffic_live_map", None) is None:
                root = self.centralWidget() or self._root
                self.traffic_live_map = TrafficLiveMapPanel(root)
                self.traffic_live_map.hide()
            panel = self.traffic_live_map
            panel.set_map_url(map_url, title=title)
            root = panel.parentWidget() or self
            panel.move(max(12, (root.width() - panel.width()) // 2), 30)
            panel.open_panel(map_url)
            panel.raise_()
            self.append_log(f"TRAFFIC › live map {map_url}")
            self.status.setText("● LIVE TRAFFIC MAP")
        except Exception as e:
            self.append_log(f"TRAFFIC › live map failed: {e}")
            self._open_traffic_board_ui()

    def _open_traffic_board_ui(self) -> None:
        try:
            if self.brain and getattr(self.brain, "traffic_cams", None):
                msg = self.brain.traffic_cams.open_traffic_board()
                self.append_log(f"TRAFFIC › {msg}")
                return
        except Exception as e:
            print(f"[traffic_board] {e}")
        try:
            import webbrowser
            from jarvis.core.traffic_cams import TRAFFIC_BOARD_URL

            webbrowser.open(TRAFFIC_BOARD_URL)
            self.append_log("TRAFFIC › opened official map")
        except Exception as e:
            self.append_log(f"TRAFFIC › board failed: {e}")

    def _aerospatial_scan(self) -> None:
        ar = getattr(self.camera, "aerospatial", None)
        if ar is None or not getattr(ar, "is_ar_open", lambda: False)():
            self._toggle_aerospatial(True)
            ar = getattr(self.camera, "aerospatial", None)
        try:
            if ar is not None:
                ar.start_laser()
            self.append_log("AEROSPATIAL › laser scan mapping room")
        except Exception as e:
            self.append_log(f"AEROSPATIAL › scan failed: {e}")

    def _aerospatial_deploy(self, mode: str) -> None:
        ar = getattr(self.camera, "aerospatial", None)
        if ar is None or not getattr(ar, "is_ar_open", lambda: False)():
            self._toggle_aerospatial(True)
            ar = getattr(self.camera, "aerospatial", None)
        try:
            if ar is not None:
                msg = ar.set_deploy(mode)
                self.append_log(f"AEROSPATIAL › {msg}")
        except Exception as e:
            self.append_log(f"AEROSPATIAL › deploy failed: {e}")

    def _aerospatial_cinematic(self, on: bool = True) -> None:
        ar = getattr(self.camera, "aerospatial", None)
        if ar is None or not getattr(ar, "is_ar_open", lambda: False)():
            self._toggle_aerospatial(True)
            ar = getattr(self.camera, "aerospatial", None)
        try:
            if ar is not None:
                msg = ar.set_cinematic(bool(on))
                self.append_log(f"AEROSPATIAL › {msg}")
                self._hud_alert("Cinematic AR" if on else "Raw AR")
        except Exception as e:
            self.append_log(f"AEROSPATIAL › cinematic failed: {e}")

    def _aerospatial_biometric(self) -> None:
        ar = getattr(self.camera, "aerospatial", None)
        if ar is None or not getattr(ar, "is_ar_open", lambda: False)():
            self._toggle_aerospatial(True)
            ar = getattr(self.camera, "aerospatial", None)
        try:
            if ar is not None:
                ar.mapper.state.biometric_scan = True
                ar.trigger_biometric()
            self.append_log("AEROSPATIAL › biometric scan")
        except Exception as e:
            self.append_log(f"AEROSPATIAL › biometric failed: {e}")

    def _aerospatial_flag(self, name: str, on: bool = True) -> None:
        ar = getattr(self.camera, "aerospatial", None)
        if ar is None or not getattr(ar, "is_ar_open", lambda: False)():
            self._toggle_aerospatial(True)
            ar = getattr(self.camera, "aerospatial", None)
        try:
            if ar is not None:
                setattr(ar.mapper.state, name, bool(on))
                ar.mapper.save()
            self.append_log(f"AEROSPATIAL › {name}={'on' if on else 'off'}")
        except Exception as e:
            self.append_log(f"AEROSPATIAL › flag failed: {e}")

    def _on_ar_biometric(self, _payload: object = None) -> None:
        self.append_log("AEROSPATIAL › welcome back, boss")
        self._hud_alert("Welcome back, boss")
        try:
            self.brain.say(
                f"Welcome back, {getattr(self.brain.settings, 'user_name', 'sir')}. "
                "Aerospatial unlocked."
            )
        except Exception:
            pass
        try:
            self.status.setText("● AR UNLOCKED")
        except Exception:
            pass

    def _fabricator_build(self) -> None:
        if not self.camera.isVisible() or not getattr(
            getattr(self.camera, "fabricator", None), "is_lab_open", lambda: False
        )():
            self._toggle_fabricator(True)
        try:
            self.camera.fabricator.start_build()
            self.append_log("FABRICATOR › print cycle engaged")
        except Exception as e:
            self.append_log(f"FABRICATOR › build failed: {e}")

    def _on_suit_built(self, payload: object) -> None:
        meta = payload if isinstance(payload, dict) else {}
        tint = str(meta.get("tint") or "upgraded")
        self.append_log(f"FABRICATOR › suit complete · {tint}")
        self.status.setText("● SUIT READY")
        self._hud_alert(f"Suit fabricated — {tint.replace('_', ' ')}")
        if self.brain:
            try:
                self.brain.say(
                    f"Fabrication complete. {tint.replace('_', ' ')} suit is ready for deployment."
                )
            except Exception:
                pass

    def _toggle_news(self, payload, _retries: int = 0) -> None:
        """Open theater with ABC live news (or standalone overlay)."""
        if payload is False or payload == 0 or payload == "close":
            try:
                if hasattr(self.camera, "news"):
                    self.camera.news.hide()
            except Exception:
                pass
            self.news.hide()
            self.append_log("NEWS › closed")
            self.status.setText("● OPTIMAL")
            return
        # Prefer full theater so news sits top-left on the live camera
        if not self.camera.isVisible() or getattr(self.camera, "_cap", None) is None:
            if _retries >= 4:
                msg = self.news.open_news()
                self.append_log(f"NEWS › {msg}")
                return
            if _retries == 0:
                self._toggle_camera(True)
                self.append_log("NEWS › opening camera theater…")
            QTimer.singleShot(
                1700, lambda: self._toggle_news(payload, _retries + 1)
            )
            return
        try:
            self.camera._show_news_top_left()
            self.camera.dock.raise_()
        except Exception:
            self.news.open_news()
        self.append_log("NEWS › ABC Live top-left on camera")
        self.status.setText("● CAMERA · ABC LIVE")

    def _on_build_theater_closed(self) -> None:
        self.append_log("BUILD › theater closed")
        try:
            self.code_preview.hide()
        except Exception:
            pass
        try:
            self.site_preview.hide()
        except Exception:
            pass
        self.status.setText("● OPTIMAL")
        self._reactor_activity("idle")

    def _on_news_closed(self) -> None:
        self.append_log("NEWS › closed")
        self.status.setText("● OPTIMAL")

    def _toggle_site(self, payload) -> None:
        if payload is False or payload == 0 or payload == "close":
            self.site_preview.hide()
            try:
                self.build_theater.hide()
            except Exception:
                pass
            self.append_log("SITE › preview closed")
            self.status.setText("● OPTIMAL")
            self._reactor_activity("idle")
            return
        if not isinstance(payload, dict):
            return
        try:
            self.site_preview.hide()
        except Exception:
            pass
        if payload.get("building"):
            hint = payload.get("hint") or "new venture"
            try:
                self._open_build_theater(mode="site", hint=str(hint))
            except Exception as e:
                self.append_log(f"SITE › theater failed: {e}")
            self.append_log(f"SITE › agentic coding — {hint}")
            self.status.setText("● AGENTIC CODING")
            self._reactor_activity("build")
            return
        url = str(payload.get("url") or payload.get("preview_url") or "").strip()
        brand = str(payload.get("brand") or "")
        if url:
            try:
                if not self.build_theater.isVisible():
                    self._open_build_theater(mode="site", hint=brand or "scaffold")
                else:
                    self.build_theater.ensure_open()
                self.build_theater.show_done(
                    path=url,
                    name=brand or "scaffold",
                    preview_url=url if url.startswith("http") else "",
                )
                self.build_theater._set_tab("building", force=True)
            except Exception as e:
                self.append_log(f"SITE › theater preview failed: {e}")
            self.append_log(f"SITE › preview tab — {url}")
            self.status.setText("● PREVIEW")
            self._reactor_activity("idle")
            return
        path = payload.get("path") or ""
        if not path:
            self.append_log("SITE › build finished but no path")
            return
        from pathlib import Path

        p = Path(path)
        preview_url = str(payload.get("preview_url") or "").strip()
        try:
            if not self.build_theater.isVisible():
                self._open_build_theater(mode="site", hint=brand or p.parent.name)
            else:
                self.build_theater.ensure_open()
            self.build_theater.show_done(
                path=str(p),
                name=brand or p.parent.name,
                preview_url=preview_url,
            )
            self.build_theater._set_tab("building", force=True)
        except Exception as e:
            self.append_log(f"SITE › theater finish failed: {e}")
        self.append_log(f"SITE › live preview — {brand or p.parent.name}")
        if preview_url:
            self.append_log(f"SITE › preview {preview_url}")
        self.status.setText("● SITE READY")
        self._reactor_activity("idle")

    def _site_progress(self, msg) -> None:
        text = ""
        if isinstance(msg, dict):
            text = str(msg.get("msg") or msg.get("log") or "")
        else:
            text = str(msg)
        if text:
            self.append_log(f"SITE › {text}")
        self._reactor_activity("build")
        try:
            if self.site_preview.isVisible():
                self.site_preview.apply_progress(msg)
        except Exception:
            pass
        try:
            theater = getattr(self, "build_theater", None)
            if theater is not None and (
                theater.isVisible() or getattr(theater, "_active", False)
            ):
                if not theater.isVisible():
                    theater._fill_parent()
                    theater.show()
                    theater.raise_()
                theater.apply_progress(msg)
                # Mirror vibe: force WORKING / CODING / PREVIEW so tabs always paint
                if isinstance(msg, dict):
                    tab = str(msg.get("tab") or "").lower()
                    stage = str(
                        msg.get("agent_stage") or msg.get("stage") or ""
                    ).lower()
                    if msg.get("preview_url") or stage in (
                        "preview",
                        "ship",
                        "live",
                        "browser",
                    ):
                        theater._set_tab("building", force=True)
                    elif (
                        msg.get("file_path")
                        or msg.get("file")
                        or msg.get("code")
                        or tab == "coding"
                        or stage in ("code", "coding", "file", "terminal", "render", "copy")
                    ):
                        theater._set_tab("coding", force=True)
                    elif (
                        tab == "working"
                        or stage in ("research", "plan", "invent", "prompt")
                        or msg.get("keyboard") is not None
                    ):
                        theater._set_tab("working", force=True)
                    elif tab in ("working", "coding", "building"):
                        theater._set_tab(tab, force=True)
        except Exception:
            pass

    def _theater_tab(self, payload) -> None:
        """Voice/HUD: switch Build Theater tab and optionally load preview_url."""
        try:
            theater = getattr(self, "build_theater", None)
            if theater is None:
                return
            tab = "building"
            preview_url = ""
            if isinstance(payload, dict):
                tab = str(payload.get("tab") or "building").lower()
                preview_url = str(
                    payload.get("preview_url") or payload.get("app_url") or ""
                ).strip()
            elif isinstance(payload, str):
                tab = payload.lower().strip()
            if tab in ("preview", "app preview", "building tab"):
                tab = "building"
            if tab not in ("working", "coding", "building"):
                tab = "building"
            if not theater.isVisible():
                self._open_build_theater(mode="vibe", hint="preview")
            else:
                theater.ensure_open()
            if preview_url.startswith("http"):
                theater._load_preview(preview_url)
                theater.show_done(preview_url=preview_url, name="preview")
            theater._set_tab(tab, force=True)
            theater.raise_()
            self.append_log(f"THEATER › tab {tab}" + (f" · {preview_url}" if preview_url else ""))
        except Exception as e:
            self.append_log(f"THEATER › tab failed: {e}")

    def _toggle_code(self, payload) -> None:
        if payload is False or payload == 0 or payload == "close":
            self.code_preview.hide()
            try:
                self.build_theater.hide()
            except Exception:
                pass
            self.append_log("VIBE › panel closed")
            self.status.setText("● OPTIMAL")
            self._reactor_activity("idle")
            return
        if not isinstance(payload, dict):
            return
        if payload.get("building"):
            hint = payload.get("hint") or "new app"
            try:
                self.code_preview.hide()
            except Exception:
                pass
            try:
                self._open_build_theater(mode="vibe", hint=str(hint))
            except Exception as e:
                self.append_log(f"VIBE › theater failed: {e}")
            self.append_log(f"VIBE › autonomous agent — {hint}")
            self.status.setText("● VIBE CODING")
            self._reactor_activity("vibe")
            return
        path = payload.get("path") or ""
        if not path:
            self.append_log("VIBE › build finished but no path")
            return
        from pathlib import Path

        p = Path(path)
        preview_url = str(payload.get("preview_url") or payload.get("app_url") or "").strip()
        # Stay in Build Theater — do not open CodePreview ("Visual Coder")
        try:
            self.code_preview.hide()
        except Exception:
            pass
        try:
            theater = self.build_theater
            if not theater.isVisible():
                self._open_build_theater(
                    mode="vibe", hint=str(payload.get("name") or p.name)
                )
            else:
                theater.ensure_open()
            # Hard switch to PREVIEW once — parks Google WebEngine so it can't cover the app
            if not (
                getattr(theater, "_preview_locked", False)
                and preview_url
                and preview_url == getattr(theater, "_preview_url", "")
            ):
                theater.force_preview(
                    preview_url,
                    path=str(p),
                    name=str(payload.get("name") or p.name),
                )
            if not preview_url.startswith("http"):
                try:
                    if self.brain and getattr(self.brain, "vibe", None):
                        preview_url = self.brain.vibe.ensure_preview_url(p) or ""
                except Exception:
                    pass
                if preview_url.startswith("http"):
                    theater.force_preview(
                        preview_url,
                        path=str(p),
                        name=str(payload.get("name") or p.name),
                    )
            theater.raise_()
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception as e:
            self.append_log(f"VIBE › theater finish failed: {e}")
        self.append_log(f"VIBE › ready — {payload.get('name') or p.name}")
        if preview_url:
            self.append_log(f"VIBE › preview {preview_url}")
        self.status.setText("● VIBE PREVIEW")
        self._reactor_activity("idle")

    def _code_progress(self, msg) -> None:
        text = str(msg.get("msg") or msg) if isinstance(msg, dict) else str(msg)
        if text:
            self.append_log(f"VIBE › {text}")
        self._reactor_activity("vibe")
        try:
            theater = getattr(self, "build_theater", None)
            if theater is None:
                return
            # Don't reset an active session — that was killing tab switches
            if theater.isVisible() or getattr(theater, "_active", False):
                theater.ensure_open()
            else:
                hint = "vibe"
                if isinstance(msg, dict):
                    hint = str(msg.get("hint") or msg.get("msg") or "vibe")[:48]
                self._open_build_theater(mode="vibe", hint=hint)
            theater.apply_progress(msg)
            # Explicit tab pop so WORKING / CODING / PREVIEW always paint
            if isinstance(msg, dict):
                tab = str(msg.get("tab") or "").lower()
                stage = str(msg.get("agent_stage") or "").lower()
                preview_url = str(msg.get("preview_url") or "").strip()
                already = (
                    getattr(theater, "_preview_locked", False)
                    and preview_url
                    and preview_url == getattr(theater, "_preview_url", "")
                )
                if preview_url.startswith("http") or stage in ("preview", "ship", "live"):
                    if already:
                        theater._set_tab("building", force=True)
                    else:
                        theater.force_preview(
                            preview_url,
                            path=str(msg.get("path") or ""),
                            name=str(msg.get("msg") or "preview")[:40],
                        )
                elif getattr(theater, "_preview_locked", False):
                    theater._set_tab("building", force=True)
                elif (
                    msg.get("file_path")
                    or msg.get("file_content")
                    or msg.get("code")
                    or tab == "coding"
                    or stage in ("code", "coding", "file", "terminal")
                ):
                    theater._set_tab("coding", force=True)
                elif (
                    tab == "working"
                    or stage in ("research", "plan", "invent")
                    or msg.get("keyboard") is not None
                    or msg.get("mouse") is not None
                ):
                    theater._set_tab("working", force=True)
                elif tab in ("working", "coding", "building"):
                    theater._set_tab(tab, force=True)
        except Exception as e:
            self.append_log(f"VIBE › theater progress failed: {e}")
        try:
            if self.code_preview.isVisible():
                self.code_preview.hide()
        except Exception:
            pass

    def _open_vibe_ide(self, path: str) -> None:
        from pathlib import Path

        self.append_log(f"VIBE › opening IDE — {path}")
        if self.brain and getattr(self.brain, "vibe", None):
            try:
                ide = getattr(self.settings, "work_ide", None) or "code"
                self.brain.vibe.open_in_ide(Path(path), ide=ide)
            except Exception as e:
                self.append_log(f"VIBE › IDE open failed: {e}")

    def _on_gesture_state(self, state) -> None:
        """Fist / wave labels → GestureCommander (command shortcuts)."""
        try:
            if not self.brain:
                return
            label = getattr(state, "label", "") or ""
            if label in ("fist", "thumbs_up", "wave_left"):
                self.brain.handle_gesture(label=label)
        except Exception:
            pass

    def _on_gesture_drag(self, nx: float, ny: float) -> None:
        """Pinch-drag panels + spatial edge throws between monitors."""
        try:
            if self._spatial and self._spatial.enabled:
                try:
                    pinch = False
                    if getattr(self, "camera", None):
                        st = getattr(self.camera, "_last_gesture", None)
                        pinch = bool(getattr(st, "pinch", False))
                    note = self._spatial.on_pinch_drag(nx, ny, pinch=pinch)
                    if note:
                        self.append_log(f"SPATIAL › {note}")
                        self.status.setText(f"● {note[:42]}")
                except Exception:
                    pass
            if getattr(self, "camera", None) and self.camera.isVisible():
                return
            if self.news.isVisible():
                self.news.move_normalized(nx, ny)
            if getattr(self, "site_preview", None) and self.site_preview.isVisible():
                parent = self.site_preview.parentWidget()
                if parent is not None:
                    pr = parent.rect()
                    x = int(nx * pr.width() - self.site_preview.width() / 2)
                    y = int(ny * pr.height() - self.site_preview.height() / 2)
                    x = max(8, min(pr.width() - self.site_preview.width() - 8, x))
                    y = max(40, min(pr.height() - self.site_preview.height() - 8, y))
                    self.site_preview.move(x, y)
            if getattr(self, "code_preview", None) and self.code_preview.isVisible():
                parent = self.code_preview.parentWidget()
                if parent is not None:
                    pr = parent.rect()
                    x = int(nx * pr.width() - self.code_preview.width() / 2)
                    y = int(ny * pr.height() - self.code_preview.height() / 2)
                    x = max(8, min(pr.width() - self.code_preview.width() - 8, x))
                    y = max(40, min(pr.height() - self.code_preview.height() - 8, y))
                    self.code_preview.move(x, y)
        except Exception:
            pass

    def _on_gesture_swipe(self, direction: str) -> None:
        try:
            if self._spatial and self._spatial.enabled:
                note = self._spatial.on_swipe(direction or "")
                if note:
                    self.append_log(f"SPATIAL › {note}")
                    try:
                        self.status.setText(f"● {note[:42]}")
                    except Exception:
                        pass
                    return
            if self.brain:
                self.brain.handle_gesture(swipe=direction or "")
            if getattr(self, "camera", None) and self.camera.isVisible():
                return
            if not self.news.isVisible():
                return
            if direction == "left":
                self.news.next_story(1)
            elif direction == "right":
                self.news.next_story(-1)
            elif direction == "down":
                self.news.hide()
        except Exception:
            pass

    def _toggle_map(self, payload) -> None:
        """payload: False to close, True/dict to open {place, markers, options, scanning}."""
        if payload is False or payload == 0 or payload == "close":
            self._close_map_mode()
            return
        place = None
        markers = None
        options = None
        scanning = False
        query = ""
        animate = True
        lat = lon = zoom = None
        label = None
        brief = None
        zoom_delta = None
        if isinstance(payload, dict):
            place = payload.get("place")
            markers = payload.get("markers")
            options = payload.get("options")
            scanning = bool(payload.get("scanning"))
            query = str(payload.get("query") or "")
            if "animate" in payload:
                animate = bool(payload.get("animate"))
            if payload.get("lat") is not None and payload.get("lon") is not None:
                try:
                    lat = float(payload["lat"])
                    lon = float(payload["lon"])
                except Exception:
                    lat = lon = None
            if payload.get("zoom") is not None:
                try:
                    zoom = float(payload["zoom"])
                except Exception:
                    zoom = None
            if payload.get("zoom_delta") is not None:
                try:
                    zoom_delta = float(payload["zoom_delta"])
                except Exception:
                    zoom_delta = None
            label = payload.get("label") or None
            brief = payload.get("brief") or None
        city = getattr(self.settings, "city", None) or "Philadelphia"

        # Prefer last business search pins if none provided
        if markers is None and self.brain and getattr(self.brain, "biz", None):
            try:
                markers = [
                    {
                        "index": i,
                        "name": r.get("name"),
                        "lat": r.get("lat"),
                        "lon": r.get("lon"),
                        "address": r.get("address"),
                        "category": r.get("category"),
                    }
                    for i, r in enumerate((self.brain.biz.last_results or [])[:12], 1)
                    if r.get("lat") is not None and r.get("lon") is not None
                ]
            except Exception:
                markers = None

        already_open = self._center_stack.currentIndex() == 1
        self.map_view.show()
        self._center_stack.setCurrentIndex(1)
        target = place or city

        # Relative zoom in / out — open with intro first if closed
        if zoom_delta is not None and not scanning and options is None:
            engine_ok = False
            try:
                engine_ok = bool(self.map_view.engine_ready())
            except Exception:
                engine_ok = getattr(self.map_view, "_web", None) is not None

            # Map panel visible but engine dead (soft-reload) → reopen then zoom
            if not already_open or not engine_ok:
                try:
                    msg = self.map_view.open_map(
                        city=city,
                        place=city,
                        markers=markers if markers else None,
                        scanning=False,
                        animate=True,
                    )
                except Exception as e:
                    msg = f"Map open failed: {e}"
                delay_ms = 1800 if not already_open else 900

                def _zoom_after_open(d=zoom_delta):
                    try:
                        zmsg = self.map_view.zoom_by(d)
                        self.append_log(f"MAP › {zmsg}")
                    except Exception:
                        pass

                QTimer.singleShot(delay_ms, _zoom_after_open)
                self.append_log(f"MAP › {msg} · then zoom")
            else:
                try:
                    msg = self.map_view.zoom_by(zoom_delta)
                except Exception as e:
                    msg = f"Zoom failed: {e}"
                # If zoom still reports offline, force reopen + retry once
                if "offline" in (msg or "").lower():
                    try:
                        self.map_view.open_map(
                            city=city, place=city, scanning=False, animate=False
                        )
                    except Exception:
                        pass

                    def _retry_zoom(d=zoom_delta):
                        try:
                            self.append_log(f"MAP › {self.map_view.zoom_by(d)}")
                        except Exception:
                            pass

                    QTimer.singleShot(1200, _retry_zoom)
                    msg = "Rebooting map engine, then zooming…"
                self.append_log(f"MAP › {msg}")
            self.status.setText(
                "● 3D MAP · ZOOM IN" if zoom_delta >= 0 else "● 3D MAP · ZOOM OUT"
            )
            return

        # If map already open and we're just delivering options, update in place
        if already_open and options is not None and not scanning:
            self.map_view.set_options(options, query=query)
            self.append_log(f"MAP › {len(options or [])} options locked")
            self.status.setText("● 3D MAP · OPTIONS")
            return

        if already_open and scanning:
            self.map_view.set_scanning(True, query)
            self.append_log(f"MAP › scanning — {query or target}")
            self.status.setText("● 3D MAP · SCANNING")
            return

        # Voice zoom / fly — reuse live map when already open
        fly_dest = bool(
            place
            and not scanning
            and options is None
            and lat is not None
            and lon is not None
            and (markers is None or markers == [])
        )
        if fly_dest and already_open:
            msg = self.map_view.fly_to(
                target,
                lat=lat,
                lon=lon,
                zoom=zoom,
                label=label,
                brief=brief,
            )
            self.append_log(f"MAP › {msg}")
            self.status.setText(f"● 3D MAP · {str(label or target).upper()[:28]}")
            return

        if already_open and place and not markers and not scanning:
            msg = self.map_view.fly_to(
                target,
                lat=lat,
                lon=lon,
                zoom=zoom,
                label=label,
                brief=brief,
            )
            self.append_log(f"MAP › {msg}")
            self.status.setText(f"● 3D MAP · {str(label or target).upper()[:28]}")
            return

        # Cold open: play intro on home city, then cinematic fly-to destination
        if fly_dest and not already_open and animate:
            try:
                msg = self.map_view.open_map(
                    city=city,
                    place=city,
                    markers=None,
                    scanning=False,
                    animate=True,
                )
            except Exception as e:
                msg = f"Map open failed: {e}"
            # Intro starts immediately; wait for load + first motion, then dive
            delay_ms = 1700
            dest_label = label or target
            dest_brief = brief
            dest_zoom = zoom

            def _fly_after_open(
                p=target,
                la=lat,
                lo=lon,
                z=dest_zoom,
                lab=dest_label,
                br=dest_brief,
            ):
                try:
                    self.map_view.fly_to(
                        p, lat=la, lon=lo, zoom=z, label=lab, brief=br
                    )
                except Exception:
                    pass

            QTimer.singleShot(delay_ms, _fly_after_open)
            if brief:
                self.map_view.place_lab.setText(str(dest_label).upper())
                self.map_view.options_status.setText(str(brief))
            self.append_log(f"MAP › {msg} · fly to {dest_label}")
            self.status.setText(f"● 3D MAP · {str(dest_label).upper()[:28]}")
            return

        msg = self.map_view.open_map(
            city=city,
            place=target,
            markers=markers,
            scanning=scanning,
            query=query,
            options=options,
            animate=animate,
            lat=lat,
            lon=lon,
            zoom=zoom,
            label=label,
            brief=brief,
        )
        # Snap-open (no intro): late fly once engine is up
        if (
            lat is not None
            and lon is not None
            and self.map_view._web is not None
            and not animate
        ):
            def _fly_after():
                try:
                    self.map_view.fly_to(
                        target,
                        lat=lat,
                        lon=lon,
                        zoom=zoom,
                        label=label,
                        brief=brief,
                    )
                except Exception:
                    pass

            QTimer.singleShot(900, _fly_after)
        elif (
            lat is not None
            and lon is not None
            and self.map_view._web is not None
            and animate
            and brief
        ):
            self.map_view.place_lab.setText(str(label or target).upper())
            self.map_view.options_status.setText(str(brief))
        self.append_log(f"MAP › {msg}")
        self.status.setText(
            "● 3D MAP · SCANNING" if scanning else "● 3D MAP ONLINE"
        )

    def _on_map_option(self, index: int) -> None:
        self.append_log(f"MAP › selected option #{index}")
        self.status.setText(f"● MAP · OPTION {index}")

    def _on_map_build_site(self, index: int) -> None:
        self.append_log(f"MAP › build site for #{index}")
        if self.brain:
            QTimer.singleShot(
                0,
                lambda: self._dispatch_brain(f"build a website for number {index}"),
            )

    def _close_map_mode(self) -> None:
        self._center_stack.setCurrentIndex(0)
        self.map_view.hide()
        self.status.setText("● OPTIMAL")
        self.append_log("MAP › closed — arc reactor restored")

    def _persist_camera_index(self) -> None:
        if getattr(self.camera, "_cap", None) is None:
            self.append_log("CAMERA › failed — close OBS Virtual Camera, press SWITCH on dock")
            self.status.setText("● CAMERA FAILED")
            return
        idx = getattr(self.camera, "_index", -1)
        if idx >= 0:
            self.settings.camera_index = idx
            try:
                self.settings.save()
            except Exception:
                pass
        label = getattr(self.camera, "_label", "")
        self.append_log(f"CAMERA › theater live @ {idx} {label}")
        self.status.setText("● CAMERA THEATER")

    def _on_camera_closed(self) -> None:
        try:
            self._hud.show()
        except Exception:
            pass
        self.status.setText("● OPTIMAL")
        if self.brain:
            self.brain.pause_presence_lock(False)
            QTimer.singleShot(900, self.brain.vision.start)

    def _parallax(self, data: dict) -> None:
        try:
            self.reactor.set_parallax(float(data.get("x", 0.5)), float(data.get("y", 0.5)))
        except Exception:
            pass

    def _bond(self, hint: dict) -> None:
        if not hint:
            return
        fps = hint.get("fps")
        if fps:
            self.reactor.set_target_fps(int(fps))
        if hint.get("ambient") == "conserve":
            if getattr(self.settings, "performance_mode", False):
                self.status.setText("● SMOOTH MODE")
            else:
                self.status.setText("● ECO MODE")

    def _bedtime(self, data: dict) -> None:
        if data and data.get("active"):
            self.status.setText("● GUARDIAN / SLEEP")
            self.status.setStyleSheet("color:#1a6080; font-size:11px;")
            self.reactor.set_target_fps(12)
            self.append_log("GUARDIAN › bedtime mode")
        else:
            self.status.setText("● OPTIMAL")
            self.reactor.set_target_fps(16)

    def _apply_tel(self, snap) -> None:
        total_g, free_g = (0.0, 0.0)
        if self.brain:
            total_g, free_g = self.brain.system.disk_capacity()
        self.clock.set_vitals(snap.cpu, snap.memory, snap.battery, total_g, free_g)
        try:
            import psutil

            vm = psutil.virtual_memory()
            used_gb = (vm.total - vm.available) / (1024**3)
            total_ram = vm.total / (1024**3)
            self.memory_map.set_ram(
                float(snap.memory), used_gb=used_gb, total_gb=total_ram
            )
        except Exception:
            try:
                self.memory_map.set_ram(float(snap.memory))
            except Exception:
                pass
        # Hardware → hologram film + core spin
        try:
            cpu = float(getattr(snap, "cpu", 0) or 0)
            self.reactor.set_cpu_load(cpu)
            self.atmosphere.set_cpu_load(cpu)
        except Exception:
            pass
        # Keep Screen-2 tools net KPI fresh while open
        try:
            if (
                self.tools is not None
                and self.tools.isVisible()
                and self.brain
                and getattr(self.brain, "net_watch", None)
            ):
                self.tools.set_net_status(self.brain.net_watch.status())
        except Exception:
            pass
        if snap.eco:
            if getattr(self.settings, "performance_mode", False):
                self.status.setText("● SMOOTH MODE")
            else:
                self.status.setText("● ECO / THERMAL")

    def _refresh(self) -> None:
        if self.brain:
            self.brain.tick_governor()

    def _weather(self) -> None:
        if not self.brain:
            return

        def _work() -> None:
            ctx = None
            err = None
            try:
                ctx = self.brain.weather.context_block()
            except Exception as e:
                err = e

            def _apply() -> None:
                if err is not None:
                    self.append_log(f"WEATHER › {err}")
                    return
                if not ctx:
                    return
                try:
                    self.weather.set_context(ctx)
                    if ctx.get("city"):
                        self.loc.setText(f"◎ {ctx['city']}")
                    self._apply_weather_mood(ctx.get("condition") or "")
                except Exception as e:
                    self.append_log(f"WEATHER › {e}")

            QTimer.singleShot(0, _apply)

        import threading

        threading.Thread(target=_work, daemon=True, name="jarvis-weather").start()

    def _orbital(self) -> None:
        """Refresh ISS satellite track into the atmosphere panel."""
        def _work() -> None:
            summary = "track offline"
            try:
                from jarvis.core.satellite_track import fetch_iss

                summary = fetch_iss().get("summary") or summary
            except Exception as e:
                summary = str(e)

            def _apply() -> None:
                try:
                    self.weather.set_orbital(summary)
                except Exception:
                    pass

            QTimer.singleShot(0, _apply)

        import threading

        threading.Thread(target=_work, daemon=True, name="jarvis-orbital").start()

    def _apply_weather_mood(self, condition: str) -> None:
        mood = weather_mood(condition)
        if mood == self._wx_mood:
            # Still refresh FX in case window resized while clear
            self.atmosphere.set_mood(mood)
            self._stack_overlays()
            return
        prev = self._wx_mood
        self._wx_mood = mood
        pal = mood_palette(mood)
        self.setStyleSheet(stylesheet(self.settings.theme, mood=mood))
        self.atmosphere.set_mood(mood)
        try:
            self.reactor.set_weather_accent(pal["accent"])
        except Exception:
            pass
        try:
            self.weather.set_mood(mood, pal["accent"])
        except Exception:
            pass
        try:
            self.deck.set_accent(pal["accent"])
        except Exception:
            pass
        try:
            self.clock.set_accent(pal["accent"])
        except Exception:
            pass
        try:
            self.status.setStyleSheet("")
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
        except Exception:
            pass
        self._stack_overlays()
        label = pal.get("label", mood.upper())
        if mood in ("rain", "storm") and prev == "clear":
            self.append_log(f"ATMOSPHERE › {label} — HUD shifted to weather mode")
            self.status.setText(f"● {label} MODE")
        elif mood == "clear" and prev != "clear":
            self.append_log("ATMOSPHERE › CLEAR — HUD restored to normal")
            self.status.setText("● OPTIMAL")
        else:
            self.status.setText(f"● {label}")

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        try:
            self.exec_btn.pulse_success()
        except Exception:
            pass
        self._cmd(text)

    def _cmd(self, text: str) -> None:
        if not text:
            return
        self.append_log(f"CMD › {text}")
        self._reactor_activity("fetch")
        try:
            self.controls.pulse_command(text)
        except Exception:
            pass
        self.status.setText("● EXECUTING")

        low = text.lower().strip()
        # Build site button → agentic coding workbench every time
        if low in (
            "build a site",
            "build site",
            "start agentic coding",
            "start agentic",
            "agentic coding",
            "agentic",
        ):
            self._launch_agentic_site()
            return

        # Vibe button / command → open Build Theater on the GUI thread first
        if (
            low
            in (
                "start vibe coding",
                "start vibe",
                "vibe coding",
                "vibe",
                "start vibe code",
                "do vibe coding",
                "run vibe coding",
            )
            or low.startswith("start vibe coding")
            or low.startswith("vibe coding")
        ):
            self._launch_vibe_coding(brief="")
            return

        # STUDIO strip — theater-backed creative modes (GUI thread first)
        studio_vibe = {
            "start written": "written article editor with outline drafts export and tone controls",
            "make a video": "video slideshow reel with captions play pause and export",
            "start design": "design moodboard board with color palette typography and layout mock",
            "make 3d": "3d three.js orbit product turntable with particles and hud controls",
            "make a 3d app": "3d webgl scene with orbit controls lighting and animation",
            "start 3d": "3d three.js cinematic scene with orbit controls and fx",
            "make animation": "gsap motion graphics timeline with kinetic type and export frame",
            "start animation": "animation app with gsap canvas ribbons and play pause restart",
        }
        if low in studio_vibe:
            self._launch_vibe_coding(brief=studio_vibe[low])
            return

        # Away button → live away agent theater
        if low in (
            "away mode",
            "away",
            "i'm heading out",
            "im heading out",
            "i am heading out",
        ):
            self._launch_away_agent()
            return

        QTimer.singleShot(120, lambda: self.status.setText("● OPTIMAL"))

        if self.brain:
            # Never run the brain on the Qt GUI thread — HITL / network / healer
            # waits would freeze the HUD ("Not Responding").
            threading.Thread(
                target=self.brain.handle_utterance,
                args=(text,),
                daemon=True,
                name="jarvis-hud-cmd",
            ).start()
        else:
            self.append_log("CMD › brain not ready")

    def _dispatch_brain(self, text: str) -> None:
        if not self.brain or not text:
            return
        threading.Thread(
            target=self.brain.handle_utterance,
            args=(text,),
            daemon=True,
            name="jarvis-hud-cmd",
        ).start()

    def _open_build_theater(self, *, mode: str, hint: str) -> None:
        """Force the live Build Theater onto the HUD (GUI thread only)."""
        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        try:
            if getattr(self, "_center_stack", None) and self._center_stack.currentIndex() == 1:
                self._close_map_mode()
        except Exception:
            pass
        for w in (
            getattr(self, "atmosphere", None),
            getattr(self, "typing", None),
            getattr(self, "startup", None),
            getattr(self, "site_preview", None),
            getattr(self, "code_preview", None),
            getattr(self, "away_theater", None),
            getattr(self, "news", None),
            getattr(self, "camera", None),
            getattr(self, "artifact", None),
        ):
            try:
                if w is not None and w.isVisible():
                    w.hide()
            except Exception:
                pass
        root = self.centralWidget() or getattr(self, "_root", None)
        if root is not None:
            self.build_theater.setParent(root)
            self.build_theater.setGeometry(root.rect())
        theater = self.build_theater
        # Fresh session only when idle — never wipe mid-vibe (breaks tabs)
        if getattr(theater, "_active", False) and theater.isVisible():
            theater.ensure_open()
            if hint:
                theater.sub.setText(str(hint)[:60])
            # Keep PREVIEW if already locked
            if getattr(theater, "_preview_locked", False):
                theater._set_tab("building", force=True)
            else:
                theater._set_tab(getattr(theater, "_tab", None) or "working", force=True)
        else:
            theater.show_session(mode=mode, hint=hint)
        theater.raise_()
        try:
            theater.activateWindow()
        except Exception:
            pass
        self.append_log(f"BUILD › theater open · {mode} · {hint}")
        self.status.setText("● BUILD THEATER")

    def _launch_vibe_coding(self, brief: str = "") -> None:
        """Open Build Theater immediately, then run vibe agent on a worker."""
        hint = (brief or "").strip() or "invented app"
        self.append_log(f"VIBE › opening live theater — {hint}")
        self.status.setText("● VIBE CODING")
        self._reactor_activity("vibe")
        try:
            self.code_preview.hide()
        except Exception:
            pass
        try:
            self._open_build_theater(mode="vibe", hint=hint)
        except Exception as e:
            self.append_log(f"VIBE › theater open failed: {e}")

        if not self.brain:
            self.append_log("VIBE › brain not ready")
            return

        def _go() -> None:
            try:
                reply = self.brain._run_vibe_code(brief=brief or "")
                # Opening line already spoken/returned by handle path; avoid double-say
                if reply and "Opening Build Theater" not in reply:
                    self.brain.say(reply)
            except Exception as e:
                self.append_log(f"VIBE › agent failed: {e}")
                try:
                    self.request_ui.emit("code_ui", False)
                except Exception:
                    pass

        threading.Thread(target=_go, daemon=True, name="jarvis-vibe-code").start()

    def _launch_agentic_site(self) -> None:
        """Open the agentic workbench immediately, then run the site agent."""
        self.append_log("SITE › agentic coding workbench")
        self.status.setText("● AGENTIC CODING")
        self._reactor_activity("build")
        try:
            self.site_preview.hide()
        except Exception:
            pass
        try:
            self._open_build_theater(mode="site", hint="agentic build")
        except Exception as e:
            self.append_log(f"SITE › theater open failed: {e}")

        if not self.brain:
            self.append_log("SITE › brain not ready")
            return

        # Kick the autonomous agent on a worker thread (never freeze HUD)
        def _go() -> None:
            try:
                reply = self.brain._run_site_build(brief="")
                if reply and "Opening Build Theater" not in str(reply):
                    self.brain.say(reply)
            except Exception as e:
                self.append_log(f"SITE › agent failed: {e}")
                try:
                    self._dispatch_brain("build a site")
                except Exception:
                    pass

        threading.Thread(target=_go, daemon=True, name="jarvis-site-build").start()

    def _launch_away_agent(self) -> None:
        """Open away theater immediately and run the live away agent."""
        self.append_log("AWAY › agent theater")
        self.status.setText("● AWAY AGENT LIVE")
        self._reactor_activity("away")
        try:
            self.away_theater.show_session()
            self.away_theater.raise_()
        except Exception as e:
            self.append_log(f"AWAY › theater failed: {e}")
        if not self.brain:
            return

        def _go() -> None:
            try:
                mode = getattr(self.settings, "away_mail_mode", "ack") or "ack"
                reply = self.brain._run_away_agent(mail_mode=mode)
                if reply:
                    self.brain.say(reply)
            except Exception as e:
                self.append_log(f"AWAY › agent failed: {e}")
                try:
                    self._dispatch_brain("away mode")
                except Exception:
                    pass

        threading.Thread(target=_go, daemon=True, name="jarvis-away-agent").start()

    def _toggle_away(self, payload) -> None:
        if payload is False or payload == 0 or payload == "close":
            self.away_theater.hide()
            self.append_log("AWAY › theater closed")
            self.status.setText("● OPTIMAL")
            self._reactor_activity("idle")
            return
        if not isinstance(payload, dict):
            return
        if payload.get("building"):
            self.away_theater.show_session()
            self.away_theater.raise_()
            self.append_log("AWAY › live agent session")
            self.status.setText("● AWAY AGENT LIVE")
            self._reactor_activity("away")
            return
        if payload.get("done"):
            summary = str(payload.get("summary") or "Away mode armed")
            self.append_log(f"AWAY › {summary}")
            self.status.setText("● AWAY MODE ON")
            self._reactor_activity("idle")
            try:
                self.away_theater.apply_progress(
                    {"msg": summary, "stage": "done", "speak": summary}
                )
            except Exception:
                pass

    def _away_progress(self, msg) -> None:
        text = ""
        if isinstance(msg, dict):
            text = str(msg.get("msg") or msg.get("action") or "")
        else:
            text = str(msg)
        if text:
            self.append_log(f"AWAY › {text}")
        self._reactor_activity("away")
        try:
            if self.away_theater.isVisible():
                self.away_theater.apply_progress(msg)
        except Exception:
            pass

    def _on_update(self, text: str) -> None:
        if self.brain:
            reply = self.brain.apply_update_request(text)
            self.append_log(f"UPDATE › {reply}")
            self.brain.say(reply)

    def _upgrade_ui(self, payload) -> None:
        """payload: True/'start' to open, False to close, dict with pct/phase/detail."""
        try:
            root = self.centralWidget()
            if root is not None:
                self.upgrade.setParent(root)
                self.upgrade.setGeometry(0, 0, root.width(), root.height())
        except Exception as e:
            print(f"[upgrade_ui] geometry: {e}")
        if payload is False or payload == 0 or payload == "close":
            self.upgrade.close_panel()
            return
        if payload is True or payload == "start" or payload == 1:
            # Keep competing overlays from covering the progress card
            for w in (
                getattr(self, "atmosphere", None),
                getattr(self, "typing", None),
                getattr(self, "alert", None),
                getattr(self, "quick", None),
            ):
                try:
                    if w is not None and w.isVisible() and w is not self.upgrade:
                        if w is self.atmosphere:
                            w.hide()
                except Exception:
                    pass
            self.upgrade.open_upgrade()
            self.upgrade.raise_()
            self.append_log("UPGRADE › loading UI online")
            self.status.setText("● UPGRADING")
            self._reactor_activity("build")
            return
        if isinstance(payload, dict):
            if not self.upgrade.isVisible():
                self.upgrade.open_upgrade()
            self.upgrade.raise_()
            pct = int(payload.get("pct") or payload.get("progress") or 0)
            phase = str(payload.get("phase") or "")
            detail = str(payload.get("detail") or payload.get("msg") or "")
            self.upgrade.set_progress(pct, phase=phase, detail=detail)
            # Only log notable milestones (avoid flooding)
            if detail and (pct in (0, 1, 2, 8, 38, 72, 94, 100) or pct % 20 == 0):
                self.append_log(f"UPGRADE › {pct}% · {detail}")
            if pct >= 100:
                self.status.setText("● UPGRADE COMPLETE")
                self._reactor_activity("idle")
            return

    def _request_app_exit(self, code: int) -> None:
        """Ask QApplication to quit with a watchdog-aware exit code."""
        # Stop voice first so Edge TTS doesn't schedule futures during interpreter teardown
        try:
            if self.brain:
                self.brain.stop()
        except Exception:
            pass
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.setProperty("jarvis_exit_code", int(code))
        self.append_log(f"CORE › exit code {code}")
        self.close()

    def closeEvent(self, event) -> None:
        try:
            self.camera.hide_feed(emit=False)
        except Exception:
            pass
        if self.brain:
            self.brain.stop()
        self.countdown.close()
        try:
            from jarvis.core.instance import release_instance

            release_instance()
        except Exception:
            pass
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and app.property("jarvis_exit_code") is None:
            # Closing the window = offline (99), not a reload (0)
            app.setProperty("jarvis_exit_code", 99)
        super().closeEvent(event)
        if app is not None:
            code = app.property("jarvis_exit_code")
            try:
                app.exit(int(code) if code is not None else 99)
            except (TypeError, ValueError):
                app.exit(99)

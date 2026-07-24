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
from jarvis.ui.widgets.media_panel import MediaPanel
from jarvis.ui.widgets.quick_action import QuickActionChip, AlertBanner
from jarvis.ui.widgets.weather_fx import WeatherAtmosphere
from jarvis.ui.widgets.site_preview import SitePreview
from jarvis.ui.widgets.code_preview import CodePreview
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
        self.ops = None  # secondary-monitor ops board
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
        brand_col.setSpacing(0)
        brand = QLabel("JARVIS")
        brand.setObjectName("Brand")
        brand_sub = QLabel("COMMAND CENTER")
        brand_sub.setObjectName("BrandSub")
        brand_col.addWidget(brand)
        brand_col.addWidget(brand_sub)
        header.addLayout(brand_col)
        header.addSpacing(6)

        self.start_btn = CmdButton("START", "start", kind="start")
        self.start_btn.setMinimumWidth(108)
        self.start_btn.setToolTip(
            "Engage systems (voice: start) — double-tap F3 to launch/reload "
            "(single F3 only focuses when open)"
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
        self.status = QLabel("● OPTIMAL")
        self.status.setObjectName("StatusPill")
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
        center.setSpacing(8)

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

        # Wake-agent / external F3 writes reload.request — poll lightly
        self._reload_poll = QTimer(self)
        self._reload_poll.setInterval(1000)  # was 400ms — F3 still instant via shortcut
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
        return super().eventFilter(obj, event)

    def _on_boot_done(self) -> None:
        self._hud.show()
        self._hud.setEnabled(True)
        fx = QGraphicsOpacityEffect(self._hud)
        self._hud.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", self)
        anim.setDuration(560)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._hud.setGraphicsEffect(None))
        anim.start()
        self._boot_anim = anim
        self.status.setText("● OPTIMAL")
        self.append_log("JARVIS › Welcome, Sir.")
        self.input.setFocus()
        QTimer.singleShot(200, self._weather)
        # Tell app.py to start the brain (speaks Welcome)
        self.boot_ready.emit()

    def _on_escape(self) -> None:
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
            self._f3_arm_until = now + 1.2
            self.append_log("CORE › F3 armed — tap again to reload")
            return
        self._f3_arm_until = 0.0
        self._reload_armed = True
        self.append_log("CORE › F3 reload")
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
                "map_ui": lambda payload: QTimer.singleShot(
                    0, lambda: self._toggle_map(payload)
                ),
                "news_ui": lambda payload: QTimer.singleShot(
                    0, lambda: self._toggle_news(payload)
                ),
                "site_ui": lambda payload: QTimer.singleShot(
                    0, lambda: self._toggle_site(payload)
                ),
                "site_progress": lambda msg: QTimer.singleShot(
                    0, lambda m=msg: self._site_progress(m)
                ),
                "code_ui": lambda payload: QTimer.singleShot(
                    0, lambda: self._toggle_code(payload)
                ),
                "code_progress": lambda msg: QTimer.singleShot(
                    0, lambda m=msg: self._code_progress(m)
                ),
                "away_ui": lambda payload: QTimer.singleShot(
                    0, lambda: self._toggle_away(payload)
                ),
                "away_progress": lambda msg: QTimer.singleShot(
                    0, lambda m=msg: self._away_progress(m)
                ),
                "bond": lambda h: QTimer.singleShot(0, lambda: self._bond(h)),
                "bedtime": lambda d: QTimer.singleShot(0, lambda: self._bedtime(d)),
                "state": lambda s: QTimer.singleShot(
                    0, lambda: self.append_log(f"STATE › {s.get('from')} → {s.get('to')}")
                ),
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
                "hitl_ask": lambda p: QTimer.singleShot(0, lambda: self._offer_hitl(p)),
                "hitl_clear": lambda _: QTimer.singleShot(0, self.hitl_gate.hide_gate),
                "stats": lambda s: QTimer.singleShot(0, lambda: self._apply_stats(s)),
                "feed": lambda lines: QTimer.singleShot(0, lambda: self._apply_feed(lines)),
                "place_hud": lambda pref: QTimer.singleShot(
                    0, lambda: self._place_on_monitor(str(pref), which="hud")
                ),
                "place_ops": lambda pref: QTimer.singleShot(
                    0, lambda: self._place_on_monitor(str(pref), which="ops")
                ),
                "show_ops": lambda _: QTimer.singleShot(0, self._show_ops),
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
            if self.ops is None:
                # Lazily ensure ops exists so live work is always visible
                if getattr(self.settings, "ops_monitor_enabled", True):
                    self._show_ops()
            if self.ops:
                self.ops.push_live_item(item)
                self.ops.set_now_working(
                    str(item.get("kind") or "info"),
                    str(item.get("text") or ""),
                )
            # Keep HUD deck in sync (string lines)
            if self.brain:
                self.deck.set_feed(self.brain.feed.lines_for_ui(14))
        except Exception:
            pass

    def _apply_feed(self, lines) -> None:
        if isinstance(lines, list) and lines:
            # Prefer rich items when available
            if lines and all(isinstance(x, dict) for x in lines):
                if self.ops:
                    try:
                        self.ops.set_items(lines)
                    except Exception:
                        pass
                self.deck.set_feed(
                    [
                        f"{(x.get('ts') or '')[11:16]}  {(x.get('kind') or '').upper()}  {x.get('text', '')}"
                        for x in lines
                    ]
                )
                return
            self.deck.set_feed([str(x) for x in lines])
            if self.ops:
                try:
                    self.ops.set_feed([str(x) for x in lines])
                except Exception:
                    pass
        elif isinstance(lines, str) and lines.strip():
            self.deck.prepend_feed(lines.strip())
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
        self.hitl_gate.offer(payload)
        self.hitl_gate.move(
            max(20, (self.width() - self.hitl_gate.width()) // 2),
            max(48, self.height() // 6),
        )
        self.hitl_gate.raise_()
        self.hitl_gate.activateWindow()
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
        self.append_log(f"HITL › {msg}")
        if not answer:
            try:
                self.brain.say(msg)
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        try:
            self.typing.setGeometry(self.centralWidget().rect())
            if hasattr(self, "upgrade") and self.centralWidget() is not None:
                r = self.centralWidget().rect()
                self.upgrade.setGeometry(0, 0, r.width(), r.height())
                if self.upgrade.isVisible():
                    self.upgrade.raise_()
            if hasattr(self, "atmosphere"):
                self.atmosphere.setGeometry(self.centralWidget().rect())
                if not (hasattr(self, "camera") and self.camera.isVisible()):
                    if self.atmosphere.isVisible() and not (
                        hasattr(self, "upgrade") and self.upgrade.isVisible()
                    ):
                        self.atmosphere.raise_()
            # Keep interactive overlays above rain FX
            for w in (
                self.typing,
                getattr(self, "upgrade", None),
                self.alert,
                self.quick,
                self.hitl_gate,
                self.camera,
                self.news,
                self.site_preview,
                self.code_preview,
                self.away_theater,
                self.countdown,
                self.artifact,
            ):
                if w is not None and w.isVisible():
                    w.raise_()
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
                self.hitl_gate.raise_()
        except Exception:
            pass

    def _on_start_pulse(self) -> None:
        self.reactor.pulse_speak()
        try:
            self.start_btn.pulse_success()
        except Exception:
            pass
        self.status.setText("● STARTED")
        self.status.setStyleSheet("color:#00f0ff; font-size:11px;")
        self.append_log("START › ready")
        self.input.setFocus()

    def _on_track(self, name: str) -> None:
        self.media.set_track(name)
        self.append_log(f"MUSIC › {name}")

    def _media_action(self, action: str) -> None:
        if not self.brain:
            return
        mapping = {
            "playpause": "playpause",
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
                text=str(payload.get("text") or ""),
                image_path=str(payload.get("image_path") or ""),
                image_bgr=payload.get("frame"),
                meta=str(payload.get("meta") or ""),
            )
        except Exception as e:
            self.append_log(f"ARTIFACT › {e}")

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
            self.reactor.set_target_fps(10 if on else 15)
        except Exception:
            pass
        try:
            if getattr(self, "wave", None):
                self.wave.set_eco(on)
        except Exception:
            pass
        try:
            if hasattr(self.camera, "set_paint_interval"):
                self.camera.set_paint_interval(90 if on else 66)
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
        self.log.append(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _reactor_activity(self, mode: str) -> None:
        """Drive amber core intensity from HUD/brain events."""
        try:
            if mode in ("speak",):
                self.reactor.pulse_speak()
            else:
                self.reactor.set_activity(mode)
                if mode in ("build", "site", "vibe", "away", "fetch"):
                    self.reactor.flare(0.9)
        except Exception:
            pass

    def _on_speak(self, text: str) -> None:
        self.append_log(f"JARVIS › {text}")
        self._reactor_activity("speak")

    def _on_jarvis_speaking(self, active: bool) -> None:
        """Keep the amber core alive for the full TTS playback window."""
        try:
            self._tts_active = bool(active)
            try:
                self.wave.set_speaking(bool(active))
            except Exception:
                pass
            if active:
                self.reactor.set_speaking(True)
                self._reactor_activity("speak")
            else:
                self.reactor.set_speaking(False)
                # Only idle if we aren't mid-listen UI
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
            self.nv_badge.set_active(on)
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
            self.append_log("OPTICS › night vision offline")
            if not self.countdown.isVisible():
                self.status.setText("● OPTIMAL")
                self.status.setStyleSheet("color:#00f0ff; font-size:11px;")

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
                # Confirm live feed (or retry) — don't leave a blank black panel
                QTimer.singleShot(2800, self._ensure_camera_visible)
                QTimer.singleShot(3000, self._persist_camera_index)

            # Give the vision worker time to fully release the USB device
            QTimer.singleShot(1400, _open)
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
        """After open attempt: keep theater up, or retry once, else restore HUD."""
        if not self.camera.isVisible():
            return
        cap = getattr(self.camera, "_cap", None)
        if cap is not None:
            self.camera.raise_()
            try:
                self.raise_()
                self.activateWindow()
            except Exception:
                pass
            self._cam_open_retries = 0
            self.append_log("CAMERA › live")
            self.status.setText("● CAMERA LIVE")
            return
        # First failure — retry once after another release window
        retries = int(getattr(self, "_cam_open_retries", 0) or 0)
        if retries < 1:
            self._cam_open_retries = retries + 1
            self.append_log("CAMERA › retrying open…")
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
                QTimer.singleShot(2200, self._ensure_camera_visible)

            QTimer.singleShot(900, _retry)
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

    def _on_news_closed(self) -> None:
        self.append_log("NEWS › closed")
        self.status.setText("● OPTIMAL")

    def _toggle_site(self, payload) -> None:
        if payload is False or payload == 0 or payload == "close":
            self.site_preview.hide()
            self.append_log("SITE › preview closed")
            self.status.setText("● OPTIMAL")
            self._reactor_activity("idle")
            return
        if not isinstance(payload, dict):
            return
        if payload.get("building"):
            hint = payload.get("hint") or "new venture"
            self.site_preview.show_building(str(hint))
            self.site_preview.raise_()
            self.append_log(f"SITE › agentic coding — {hint}")
            self.status.setText("● AGENTIC CODING")
            self._reactor_activity("build")
            return
        url = str(payload.get("url") or "").strip()
        brand = str(payload.get("brand") or "")
        prompt = str(payload.get("prompt") or "")
        if url:
            self.site_preview.show_url(url, brand=brand or "scaffold", prompt=prompt or url)
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
        self.site_preview.show_site(
            p,
            brand=brand,
            prompt=prompt,
        )
        self.append_log(f"SITE › live preview — {brand or p.parent.name}")
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

    def _toggle_code(self, payload) -> None:
        if payload is False or payload == 0 or payload == "close":
            self.code_preview.hide()
            self.append_log("VIBE › panel closed")
            self.status.setText("● OPTIMAL")
            self._reactor_activity("idle")
            return
        if not isinstance(payload, dict):
            return
        if payload.get("building"):
            hint = payload.get("hint") or "new app"
            self.code_preview.show_building(str(hint))
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
        self.code_preview.show_project(
            p,
            name=str(payload.get("name") or ""),
            engine=str(payload.get("engine") or ""),
            files=list(payload.get("files") or []),
            entry=str(payload.get("entry") or ""),
        )
        self.append_log(f"VIBE › ready — {payload.get('name') or p.name}")
        self.status.setText("● VIBE READY")
        self._reactor_activity("idle")

    def _code_progress(self, msg: str) -> None:
        self.append_log(f"VIBE › {msg}")
        self._reactor_activity("vibe")
        try:
            if self.code_preview.isVisible():
                self.code_preview.set_progress(msg)
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
            if not already_open:
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
                delay_ms = 1600

                def _zoom_after_open(d=zoom_delta):
                    try:
                        self.map_view.zoom_by(d)
                    except Exception:
                        pass

                QTimer.singleShot(delay_ms, _zoom_after_open)
                self.append_log(f"MAP › {msg} · then zoom")
            else:
                try:
                    msg = self.map_view.zoom_by(zoom_delta)
                except Exception as e:
                    msg = f"Zoom failed: {e}"
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
            self.reactor.set_target_fps(10)
            self.append_log("GUARDIAN › bedtime mode")
        else:
            self.status.setText("● OPTIMAL")
            self.reactor.set_target_fps(36)

    def _apply_tel(self, snap) -> None:
        total_g, free_g = (0.0, 0.0)
        if self.brain:
            total_g, free_g = self.brain.system.disk_capacity()
        self.clock.set_vitals(snap.cpu, snap.memory, snap.battery, total_g, free_g)
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
        try:
            ctx = self.brain.weather.context_block()
            self.weather.set_context(ctx)
            if ctx.get("city"):
                self.loc.setText(f"◎ {ctx['city']}")
            self._apply_weather_mood(ctx.get("condition") or "")
        except Exception as e:
            self.append_log(f"WEATHER › {e}")

    def _apply_weather_mood(self, condition: str) -> None:
        mood = weather_mood(condition)
        if mood == self._wx_mood:
            # Still refresh FX in case window resized while clear
            self.atmosphere.set_mood(mood)
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
        QTimer.singleShot(900, lambda: self.status.setText("● OPTIMAL"))

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

    def _launch_agentic_site(self) -> None:
        """Open the agentic workbench immediately, then run the site agent."""
        self.append_log("SITE › agentic coding workbench")
        self.status.setText("● AGENTIC CODING")
        self._reactor_activity("build")
        try:
            # Close map so the workbench is visible
            if getattr(self, "_center_stack", None) and self._center_stack.currentIndex() == 1:
                self._close_map_mode()
        except Exception:
            pass
        try:
            self.site_preview.show_building("agentic build")
            self.site_preview.raise_()
            self.site_preview.activateWindow()
        except Exception as e:
            self.append_log(f"SITE › workbench open failed: {e}")

        if not self.brain:
            self.append_log("SITE › brain not ready")
            return

        # Kick the autonomous agent on a worker thread (never freeze HUD)
        def _go() -> None:
            try:
                reply = self.brain._run_site_build(brief="")
                if reply:
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

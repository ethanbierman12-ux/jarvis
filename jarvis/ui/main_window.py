"""Main Jarvis HUD — clean three-column layout after boot bloom."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QTextEdit,
    QGraphicsOpacityEffect, QLineEdit, QStackedWidget, QFrame,
)

from jarvis.config import Settings
from jarvis.ui.styles import stylesheet, weather_mood, mood_palette
from jarvis.ui.widgets.startup import StartupOverlay
from jarvis.ui.widgets.reactor import ArcReactor
from jarvis.ui.widgets.clock import ClockPanel
from jarvis.ui.widgets.weather_hud import WeatherPanel
from jarvis.ui.widgets.command_deck import CommandDeck
from jarvis.ui.widgets.typing_overlay import TypingOverlay
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
from jarvis.ui.widgets.news_overlay import NewsOverlay
from jarvis.ui.widgets.cmd_button import CmdButton
from jarvis.ui.widgets.hitl_gate import HitlGate


class MainWindow(QMainWindow):
    """HUD shell. Emits boot_ready when the startup sequence finishes."""

    boot_ready = pyqtSignal()

    def __init__(self, settings: Settings, brain=None) -> None:
        super().__init__()
        self.settings = settings
        self.brain = brain
        self.ops = None  # secondary-monitor ops board
        self.setWindowTitle("JARVIS")
        self.resize(1560, 940)
        self.setMinimumSize(1280, 780)

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
        header.setContentsMargins(4, 4, 4, 10)
        header.setSpacing(12)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel("JARVIS")
        brand.setObjectName("Brand")
        brand_sub = QLabel("JUST A RATHER VERY INTELLIGENT SYSTEM")
        brand_sub.setObjectName("BrandSub")
        brand_col.addWidget(brand)
        brand_col.addWidget(brand_sub)
        header.addLayout(brand_col)
        header.addSpacing(8)

        self.start_btn = CmdButton("START", "start", kind="start")
        self.start_btn.setMinimumWidth(118)
        self.start_btn.setToolTip("Engage systems (voice: start) — F5 only launches Jarvis")
        self.start_btn.fired.connect(lambda _: self._on_start_clicked())
        header.addWidget(self.start_btn)

        hint = QLabel("CTRL+SHIFT+P PANIC")
        hint.setObjectName("Dim")
        hint.setStyleSheet("letter-spacing:1px; font-size:9px;")
        header.addWidget(hint)
        self.loc = QLabel("")
        self.loc.setObjectName("Dim")
        header.addWidget(self.loc)
        header.addStretch(1)

        self.listen = QLabel("MIC STANDBY")
        self.listen.setObjectName("MicPill")
        self.status = QLabel("● BOOTING")
        self.status.setObjectName("StatusPill")
        header.addWidget(self.listen)
        header.addWidget(self.status)
        outer.addWidget(header_frame)

        # Body
        body = QHBoxLayout()
        body.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(10)
        self.clock = ClockPanel()
        self.controls = ControlStrip()
        self.controls.action.connect(self._cmd)
        self.media = MediaPanel(
            playlist_id=getattr(settings, "spotify_playlist_id", "")
            or "3hMeaqVid62fywPpTBWWw9"
        )
        self.media.action.connect(self._media_action)
        left.addWidget(self.clock, 0)
        left.addWidget(self.controls, 1)  # stretch — scrollable, not squashed
        left.addWidget(self.media, 0)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(318)
        left_w.setMinimumWidth(300)
        body.addWidget(left_w)

        center = QVBoxLayout()
        center.setSpacing(10)

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
        self.log.setFixedHeight(84)
        self.log.setPlaceholderText("Mission log…")
        center.addWidget(self.log)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setObjectName("CmdInput")
        self.input.setPlaceholderText(
            "site · vibe · sarah · screen · music · away · help"
        )
        self.input.returnPressed.connect(self._submit)
        send = CmdButton("GO", "execute", kind="ghost")
        send.setMinimumWidth(72)
        send.fired.connect(lambda _: self._submit())
        self.exec_btn = send
        row.addWidget(self.input, 1)
        row.addWidget(send)
        center.addLayout(row)
        center_w = QWidget()
        center_w.setLayout(center)
        body.addWidget(center_w, 1)

        right = QVBoxLayout()
        right.setSpacing(12)
        self.deck = CommandDeck()
        self.weather = WeatherPanel()
        right.addWidget(self.deck, 3)
        right.addWidget(self.weather, 2)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setFixedWidth(318)
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
        self.countdown = CountdownOverlay()
        self.countdown.finished.connect(lambda: self.brain and self.brain.on_countdown_finished())
        self.countdown.cancelled.connect(
            lambda: self.append_log("SECURITY › countdown cancelled — welcome back")
        )

        self.camera = CameraTheater(root)
        self.camera.closed.connect(self._on_camera_closed)
        self.camera.scan_clicked.connect(lambda _: self._do_scan(ocr=True))
        self.camera.gesture_drag.connect(self._on_gesture_drag)
        self.camera.gesture_swipe.connect(self._on_gesture_swipe)

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

        # F5 must NOT trigger START (that caused spam). Esc closes map if open.
        self._esc = QShortcut(QKeySequence("Escape"), self)
        self._esc.setContext(Qt.ShortcutContext.WindowShortcut)
        self._esc.activated.connect(self._on_escape)

        # Emergency override — force-crash exit so watchdog recovers (not offline 99)
        self._kill = QShortcut(QKeySequence("Ctrl+Alt+K"), self)
        self._kill.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._kill.activated.connect(self._emergency_kill)

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
        anim.setDuration(420)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._hud.setGraphicsEffect(None))
        anim.start()
        self._boot_anim = anim
        self.status.setText("● SYSTEMS NOMINAL")
        self.append_log("JARVIS › All systems are operational. Awaiting your command, Sir.")
        self.input.setFocus()
        QTimer.singleShot(200, self._weather)
        # Tell app.py to start the brain (no fixed 5s wait)
        self.boot_ready.emit()

    def _on_escape(self) -> None:
        if getattr(self, "camera", None) and self.camera.isVisible():
            self.camera.hide_feed(emit=True)
            return
        if getattr(self, "_center_stack", None) and self._center_stack.currentIndex() == 1:
            self._close_map_mode()

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
                "heard": lambda t: QTimer.singleShot(0, lambda: self.append_log(f"YOU › {t}")),
                "listening": lambda a: QTimer.singleShot(0, lambda: self._set_listen(a)),
                "presence": lambda p: QTimer.singleShot(0, lambda: self._presence(p)),
                "countdown_start": lambda s: QTimer.singleShot(0, lambda: self._start_lock_countdown(int(s))),
                "countdown_cancel": lambda _: QTimer.singleShot(0, self.countdown.cancel),
                "panic_ui": lambda on: QTimer.singleShot(
                    0, lambda: self._set_panic_core(bool(on))
                ),
                "night_vision": lambda on: QTimer.singleShot(
                    0, lambda: self._set_night_vision(bool(on))
                ),
                "speak_ui": lambda t: QTimer.singleShot(0, lambda: self.append_log(f"JARVIS › {t}")),
                "update_ui": lambda a: QTimer.singleShot(
                    0, lambda: self.typing.open() if a else self.typing.close_panel()
                ),
                "camera_ui": lambda a: QTimer.singleShot(0, lambda: self._toggle_camera(bool(a))),
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
            max(40, self.height() // 5),
        )
        self.hitl_gate.raise_()
        self.append_log(f"HITL › {payload.get('title') or 'permission'}")
        try:
            self._reactor_activity("fetch")
        except Exception:
            pass

    def _on_hitl_decided(self, request_id: str, approve: bool, answer: str) -> None:
        if not self.brain:
            return
        msg = self.brain.resolve_hitl(request_id, approve=approve, answer=answer)
        self.append_log(f"HITL › {msg}")
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
            self.status.setText("● SYSTEMS NOMINAL")
            self.status.setStyleSheet("color:#00f0ff; font-size:11px;")
            self.append_log("CORE › restored")

    def _on_start_clicked(self) -> None:
        if self.brain:
            self.brain.trigger_start()
        else:
            self.append_log("START › brain not ready")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        try:
            self.typing.setGeometry(self.centralWidget().rect())
            if hasattr(self, "atmosphere"):
                self.atmosphere.setGeometry(self.centralWidget().rect())
                self.atmosphere.raise_()
            # Keep interactive overlays above rain FX
            for w in (
                self.typing,
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
                if w.isVisible():
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
        self.brain.handle_utterance(mapping.get(action, action))

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
        self.status.setText("● SYSTEMS NOMINAL")
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
        # Soft glow on mic pill
        try:
            if level > 0.08:
                glow = min(255, int(80 + level * 160))
                self.listen.setStyleSheet(
                    f"color: rgb(0,{glow},255); font-size:11px; letter-spacing:1px;"
                )
            elif self.listen.objectName() == "MicPill":
                self.listen.setStyleSheet("")
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
            lambda: self.status.setText("● SYSTEMS NOMINAL"),
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

    def _set_listen(self, active: bool) -> None:
        self.listen.setText("● LISTENING" if active else "MIC STANDBY")
        if active:
            self._reactor_activity("listen")
        else:
            # Don't kill build/away intensity when the mic drops
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
                self.status.setText("● SYSTEMS NOMINAL")
                self.status.setStyleSheet("color:#00f0ff; font-size:11px;")

    def _presence(self, present: bool) -> None:
        if present:
            if not self.countdown.isVisible():
                self.status.setText("● SYSTEMS NOMINAL")
                self.status.setStyleSheet("color:#00f0ff; font-size:11px;")
        else:
            self.status.setText("● PRESENCE LOST")
            self.status.setStyleSheet("color:#ff6b35; font-size:11px;")

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

            def _open():
                idx = self.settings.camera_index if self.settings.camera_index >= 0 else 0
                self.camera.set_gestures_enabled(True)
                # Cover entire HUD root
                if self.centralWidget() is not None:
                    self.camera.setGeometry(self.centralWidget().rect())
                try:
                    self._hud.hide()
                except Exception:
                    pass
                self.camera.open_feed(
                    preferred_index=idx, prefer=self.settings.camera_prefer
                )
                self.camera.raise_()
                # Keep night vision filter if already engaged
                try:
                    if self.brain and getattr(self.brain, "_night_vision", False):
                        self.camera.set_night_vision(True)
                except Exception:
                    pass
                QTimer.singleShot(1200, self._persist_camera_index)

            QTimer.singleShot(200, _open)
        else:
            self.camera.hide_feed(emit=False)
            try:
                self._hud.show()
            except Exception:
                pass
            self.append_log("CAMERA › theater closed — presence lock armed")
            self.status.setText("● SYSTEMS NOMINAL")
            if self.brain:
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
            self.status.setText("● SYSTEMS NOMINAL")
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
        self.status.setText("● SYSTEMS NOMINAL")

    def _toggle_site(self, payload) -> None:
        if payload is False or payload == 0 or payload == "close":
            self.site_preview.hide()
            self.append_log("SITE › preview closed")
            self.status.setText("● SYSTEMS NOMINAL")
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
        path = payload.get("path") or ""
        if not path:
            self.append_log("SITE › build finished but no path")
            return
        from pathlib import Path

        p = Path(path)
        self.site_preview.show_site(
            p,
            brand=str(payload.get("brand") or ""),
            prompt=str(payload.get("prompt") or ""),
        )
        self.append_log(f"SITE › live preview — {payload.get('brand') or p.parent.name}")
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
            self.status.setText("● SYSTEMS NOMINAL")
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

    def _on_gesture_drag(self, nx: float, ny: float) -> None:
        """Theater handles its own drag; keep fallback for any legacy panels."""
        try:
            if getattr(self, "camera", None) and self.camera.isVisible():
                # CameraTheater applies drag internally
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
            if getattr(self, "camera", None) and self.camera.isVisible():
                return  # theater handles swipes
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
        if isinstance(payload, dict):
            place = payload.get("place")
            markers = payload.get("markers")
            options = payload.get("options")
            scanning = bool(payload.get("scanning"))
            query = str(payload.get("query") or "")
            if "animate" in payload:
                animate = bool(payload.get("animate"))
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

        if already_open and place and not markers and not scanning:
            msg = self.map_view.fly_to(target)
        else:
            msg = self.map_view.open_map(
                city=city,
                place=target,
                markers=markers,
                scanning=scanning,
                query=query,
                options=options,
                animate=animate,
            )
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
                lambda: self.brain.handle_utterance(
                    f"build a website for number {index}"
                ),
            )

    def _close_map_mode(self) -> None:
        self._center_stack.setCurrentIndex(0)
        self.map_view.hide()
        self.status.setText("● SYSTEMS NOMINAL")
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
        self.status.setText("● SYSTEMS NOMINAL")
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
            self.status.setText("● ECO MODE")

    def _bedtime(self, data: dict) -> None:
        if data and data.get("active"):
            self.status.setText("● GUARDIAN / SLEEP")
            self.status.setStyleSheet("color:#1a6080; font-size:11px;")
            self.reactor.set_target_fps(10)
            self.append_log("GUARDIAN › bedtime mode")
        else:
            self.status.setText("● SYSTEMS NOMINAL")
            self.reactor.set_target_fps(36)

    def _apply_tel(self, snap) -> None:
        total_g, free_g = (0.0, 0.0)
        if self.brain:
            total_g, free_g = self.brain.system.disk_capacity()
        self.clock.set_vitals(snap.cpu, snap.memory, snap.battery, total_g, free_g)
        if snap.eco:
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
            self.status.setText("● SYSTEMS NOMINAL")
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
        QTimer.singleShot(900, lambda: self.status.setText("● SYSTEMS NOMINAL"))

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
            self.brain.handle_utterance(text)
        else:
            self.append_log("CMD › brain not ready")

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

        # Kick the autonomous agent directly (don't rely on voice routing)
        def _go() -> None:
            try:
                reply = self.brain._run_site_build(brief="")
                if reply:
                    self.brain.say(reply)
            except Exception as e:
                self.append_log(f"SITE › agent failed: {e}")
                try:
                    self.brain.handle_utterance("build a site")
                except Exception:
                    pass

        QTimer.singleShot(50, _go)

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
                    self.brain.handle_utterance("away mode")
                except Exception:
                    pass

        QTimer.singleShot(50, _go)

    def _toggle_away(self, payload) -> None:
        if payload is False or payload == 0 or payload == "close":
            self.away_theater.hide()
            self.append_log("AWAY › theater closed")
            self.status.setText("● SYSTEMS NOMINAL")
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

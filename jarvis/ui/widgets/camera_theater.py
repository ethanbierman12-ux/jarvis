"""Full-screen camera theater — live feed, news video corner, draggable Jarvis dock."""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal, QUrl
from PyQt6.QtGui import QImage, QPixmap, QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QSizePolicy,
)

from jarvis.core.gestures import HandGestureTracker, GestureState, draw_gestures
from jarvis.ui.widgets.camera import (
    CameraOpener,
    list_dshow_devices,
    list_physical_targets,
    _is_junk_name,
)


ABC_LIVE_EMBED = (
    "https://www.youtube.com/embed/live_stream?channel=UCBi2mrWuNuyYy4gbM6fU18Q"
    "&autoplay=1&mute=1&controls=1&rel=0"
)
ABC_LIVE_PAGE = "https://abcnews.go.com/Live"


class _DragPanel(QFrame):
    """Glass floating panel that can be mouse-dragged."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self._drag_origin: QPoint | None = None
        self._drag_start: QPoint | None = None

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = e.globalPosition().toPoint()
            self._drag_start = self.pos()
            self.raise_()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_origin is not None and self._drag_start is not None:
            delta = e.globalPosition().toPoint() - self._drag_origin
            np_ = self._drag_start + delta
            parent = self.parentWidget()
            if parent is not None:
                x = max(0, min(parent.width() - self.width(), np_.x()))
                y = max(0, min(parent.height() - self.height(), np_.y()))
                self.move(x, y)
            else:
                self.move(np_)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_origin = None
        self._drag_start = None
        super().mouseReleaseEvent(e)


class NewsVideoCorner(_DragPanel):
    """Top-left ABC News live video interface."""

    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(420, 280)
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(2,10,18,230);"
            " border: 1px solid rgba(0,232,255,150); }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        head = QHBoxLayout()
        title = QLabel("ABC NEWS · LIVE")
        title.setObjectName("SectionTitle")
        tip = QLabel("drag to move")
        tip.setObjectName("Dim")
        tip.setStyleSheet("font-size:9px;")
        close = QPushButton("✕")
        close.setObjectName("GhostBtn")
        close.setFixedSize(28, 24)
        close.clicked.connect(self._close)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(tip)
        head.addWidget(close)
        lay.addLayout(head)

        self._host = QWidget()
        self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._host, 1)
        self._fallback = QLabel("Loading ABC News Live…")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet("color:#8aa4b8; background:#02080e;")
        self._host_lay.addWidget(self._fallback)
        self._web = None
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._web = QWebEngineView(self._host)
            settings = self._web.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
            )
            self._host_lay.addWidget(self._web, 1)
            self._fallback.hide()
        except Exception as e:
            self._fallback.setText(f"WebEngine needed for live news.\n{e}")

    def start_live(self) -> None:
        self.show()
        self.raise_()
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>html,body{{margin:0;background:#02080e;height:100%;overflow:hidden}}
iframe{{border:0;width:100%;height:100%}}</style></head>
<body><iframe src="{ABC_LIVE_EMBED}" allow="autoplay; encrypted-media; picture-in-picture"
allowfullscreen></iframe></body></html>"""
        if self._web is not None:
            self._web.setHtml(html, QUrl("https://www.youtube.com/"))
        else:
            try:
                from jarvis.core.displays import displays

                displays.open_url_on(ABC_LIVE_PAGE, "secondary")
            except Exception:
                pass

    def stop_live(self) -> None:
        """Unload WebEngine to free GPU/CPU when news corner is hidden."""
        try:
            if self._web is not None:
                self._web.setUrl(QUrl("about:blank"))
        except Exception:
            pass
        self.hide()

    def _close(self) -> None:
        self.stop_live()
        self.closed.emit()


class JarvisDock(_DragPanel):
    """Bottom-right Jarvis control chip — cam desk + security pack."""

    close_camera = pyqtSignal()
    toggle_news = pyqtSignal()
    scan = pyqtSignal()
    unlock_gestures = pyqtSignal()
    # Desk pack: traffic cams + NOAA/SAT audio + LAN + Defender (not cam mics)
    open_traffic = pyqtSignal()
    play_listen = pyqtSignal()
    play_sat = pyqtSignal()
    scan_lan = pyqtSignal()
    security_scan = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(340, 228)
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(2,12,20,235);"
            " border: 1px solid rgba(0,232,255,160);"
            " border-left: 3px solid #00e8ff; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)
        brand = QLabel("J.A.R.V.I.S")
        brand.setStyleSheet(
            "color:#00e8ff; font-size:16px; font-weight:800; letter-spacing:4px;"
        )
        self.status = QLabel("CAMERA THEATER · LIVE")
        self.status.setObjectName("Dim")
        self.status.setWordWrap(True)
        self.gesture = QLabel("Gesture: ready")
        self.gesture.setStyleSheet("color:#8aa4b8; font-size:11px;")
        self.sec_line = QLabel("SEC · LAN · SAT ready · cam mic silent on traffic tiles")
        self.sec_line.setStyleSheet("color:#5a7388; font-size:9px; letter-spacing:0.5px;")
        self.sec_line.setWordWrap(True)
        tip = QLabel("Pinch = drag · Fist = lock")
        tip.setStyleSheet("color:#5a7388; font-size:9px; letter-spacing:1px;")
        lay.addWidget(brand)
        lay.addWidget(self.status)
        lay.addWidget(self.gesture)
        lay.addWidget(self.sec_line)
        lay.addWidget(tip)
        row = QHBoxLayout()
        row.setSpacing(4)
        for label, slot in (
            ("NEWS", self.toggle_news.emit),
            ("UNLOCK", self.unlock_gestures.emit),
            ("SCAN", self.scan.emit),
            ("CLOSE", self.close_camera.emit),
        ):
            b = QPushButton(label)
            b.setObjectName("GhostBtn")
            b.setMinimumHeight(26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        desk = QHBoxLayout()
        desk.setSpacing(4)
        for label, tip_txt, slot in (
            ("CAMS", "Public traffic stills + live map", self.open_traffic.emit),
            ("LISTEN", "City scanner audio (cams have no mic)", self.play_listen.emit),
            ("SAT", "NOAA / satellite weather radio", self.play_sat.emit),
            ("LAN", "Owner LAN devices + IP-cam ports", self.scan_lan.emit),
            ("SEC", "Defender status + security scan", self.security_scan.emit),
        ):
            b = QPushButton(label)
            b.setObjectName("GhostBtn")
            b.setMinimumHeight(26)
            b.setToolTip(tip_txt)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            desk.addWidget(b)
        lay.addLayout(desk)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_gesture(self, text: str) -> None:
        self.gesture.setText(text)

    def set_sec_line(self, text: str) -> None:
        self.sec_line.setText((text or "")[:140])


class CameraTheater(QFrame):
    """
    Full-screen camera mode:
      - live feed fills the window
      - ABC News Live video · top-left (draggable)
      - Jarvis dock · bottom-right (draggable) with CAMS/LISTEN/SAT/LAN/SEC
      - clean gesture cursor
    """

    closed = pyqtSignal()
    scan_clicked = pyqtSignal(bool)
    gesture = pyqtSignal(object)
    gesture_drag = pyqtSignal(float, float)
    gesture_swipe = pyqtSignal(str)
    # Desk pack → main_window → brain (traffic / NOAA / LAN / Defender)
    desk_traffic = pyqtSignal()
    desk_listen = pyqtSignal()
    desk_sat = pyqtSignal()
    desk_lan = pyqtSignal()
    desk_sec = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CameraTheater")
        self.setStyleSheet("QFrame#CameraTheater { background:#000; border:none; }")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.view = QLabel(self)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setStyleSheet("background:#000; color:#4a6070;")
        self.view.lower()

        self.news = NewsVideoCorner(self)
        self.news.hide()
        self.dock = JarvisDock(self)
        self.dock.close_camera.connect(lambda: self.hide_feed(emit=True))
        self.dock.toggle_news.connect(self._toggle_news_corner)
        self.dock.scan.connect(lambda: self.scan_clicked.emit(True))
        self.dock.unlock_gestures.connect(self._unlock_gestures)
        self.dock.open_traffic.connect(self.desk_traffic.emit)
        self.dock.play_listen.connect(self.desk_listen.emit)
        self.dock.play_sat.connect(self.desk_sat.emit)
        self.dock.scan_lan.connect(self.desk_lan.emit)
        self.dock.security_scan.connect(self.desk_sec.emit)

        from jarvis.ui.widgets.stark_fabricator import StarkFabricator

        self.fabricator = StarkFabricator(self)
        self.fabricator.hide()
        self.fabricator.closed.connect(lambda: self._set_lab_mode(False))
        self.fabricator.status.connect(lambda s: self.dock.status.setText(s[:80]) if hasattr(self.dock, "status") else None)
        self._lab_mode = False

        from jarvis.ui.widgets.aerospatial_overlay import AerospatialOverlay

        self.aerospatial = AerospatialOverlay(self)
        self.aerospatial.hide()
        self.aerospatial.closed.connect(lambda: self._set_ar_mode(False))
        self.aerospatial.status.connect(
            lambda s: self.dock.status.setText(s[:80]) if hasattr(self.dock, "status") else None
        )
        self._ar_mode = False

        try:
            from jarvis.ui.widgets.ops_globe import OpsGlobePanel

            self.ops_globe = OpsGlobePanel(self)
            self.ops_globe.hide()
            self.ops_globe.closed.connect(lambda: self._set_ops_hud(False))
        except Exception as e:
            print(f"[ops_globe] init: {e}")
            self.ops_globe = None
        self._ops_hud_on = False
        self.traffic_board = None
        self.traffic_live_map = None
        self.scanner_audio = None

        self._cap = None
        self._index = -1
        self._backend = ""
        self._label = ""
        self._frame = None
        self._lock = threading.Lock()
        self._prefer = "EMEET"
        self._preferred_index = 0
        self._opening = False  # True while probing devices — don't treat as failed yet
        self._device_names: list[str] = []
        self._mirror = True
        self._fail_streak = 0
        self._gestures_on = True
        self._gesture_locked = False  # fist locks drag until open hand / UNLOCK
        self._fist_streak = 0
        self._open_streak = 0
        self._tracker: HandGestureTracker | None = None
        self._last_gesture = GestureState()
        self._gesture_skip = 0
        self._smooth_cursor = (0.85, 0.82)
        self._probe = None
        self._night_vision = False
        self._thermal_assist = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._paint_frame)
        self.hide()

        # Compatibility aliases used by main_window
        self.result = self.dock.status

    def set_night_vision(self, on: bool) -> None:
        self._night_vision = bool(on)
        if self._thermal_assist and self.isVisible():
            self.dock.set_status("THERMAL ASSIST · ONLINE")
        elif self._night_vision and self.isVisible():
            self.dock.set_status("NIGHT VISION · ONLINE")
        elif self.isVisible() and self._label:
            self.dock.set_status(f"LIVE · {self._label} · fist locks panels")

    def set_thermal_assist(self, on: bool) -> None:
        self._thermal_assist = bool(on)
        if self._thermal_assist and self.isVisible():
            self.dock.set_status("THERMAL ASSIST · ONLINE")
        elif self._night_vision and self.isVisible():
            self.dock.set_status("NIGHT VISION · ONLINE")
        elif self.isVisible() and self._label:
            self.dock.set_status(f"LIVE · {self._label} · fist locks panels")

    def stop(self) -> None:
        self.hide_feed(emit=True)

    def set_gestures_enabled(self, on: bool) -> None:
        self._gestures_on = on
        if on and self._tracker is None:
            self._tracker = HandGestureTracker()

    def open_feed(self, preferred_index: int = 0, prefer: str = "EMEET") -> None:
        self._prefer = prefer
        self._preferred_index = preferred_index if preferred_index >= 0 else 0
        self._opening = True
        self._device_names = list_dshow_devices()
        self._gesture_locked = False
        self._fist_streak = 0
        self._open_streak = 0
        self.view.setText("Opening full-screen camera…")
        self.dock.set_status("Opening camera theater…")
        self.dock.set_gesture("Gesture: ready · fist locks")
        self._enter_fullscreen()
        # News loads after camera is live (WebEngine was slowing open)
        self.news.hide()
        self._place_corners()
        # Defer MediaPipe so the window paints immediately
        if self._gestures_on and self._tracker is None:
            QTimer.singleShot(400, self._lazy_gestures)
        QTimer.singleShot(50, self._open_best)

    def _lazy_gestures(self) -> None:
        if not self._gestures_on or self._tracker is not None:
            return
        try:
            self._tracker = HandGestureTracker()
        except Exception as e:
            print(f"[theater] gestures offline: {e}")

    def _unlock_gestures(self) -> None:
        self._gesture_locked = False
        self._fist_streak = 0
        self._open_streak = 0
        self.dock.set_gesture("Gesture: unlocked")

    def _show_news_top_left(self) -> None:
        """Pin ABC News Live interface to top-left of the camera theater."""
        self.news.move(18, 18)
        self.news.start_live()
        self.news.raise_()
        self.dock.raise_()

    def hide_feed(self, emit: bool = True) -> None:
        self._timer.stop()
        self._opening = False
        try:
            self.close_aerospatial()
        except Exception:
            pass
        try:
            self.close_fabricator()
        except Exception:
            pass
        try:
            self.close_ops_hud()
        except Exception:
            pass
        try:
            self.close_traffic_board_panel()
        except Exception:
            pass
        try:
            self.close_traffic_live_map()
        except Exception:
            pass
        try:
            self.close_scanner_audio()
        except Exception:
            pass
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        try:
            self.news.stop_live()
        except Exception:
            self.news.hide()
        self.hide()
        if emit:
            self.closed.emit()

    def show_result(self, text: str) -> None:
        self.dock.set_status(text[:180])

    def current_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def grab_best_frame(self, reads: int = 8) -> Optional[np.ndarray]:
        if self._cap is None:
            return self.current_frame()
        best = None
        best_score = -1.0
        for _ in range(max(3, reads)):
            ok, frame = self._cap.read()
            if not ok or frame is None:
                continue
            mean = float(np.mean(frame))
            std = float(np.std(frame))
            if mean < 8 or std < 4:
                continue
            score = std + 0.01 * mean
            if score > best_score:
                best_score = score
                best = frame.copy()
        if best is not None:
            with self._lock:
                self._frame = best
            return best
        return self.current_frame()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.view.setGeometry(self.rect())
        if self.isVisible():
            self._place_corners(keep_positions=True)
            try:
                if getattr(self, "ops_globe", None) is not None and self.ops_globe.isVisible():
                    self._place_ops_globe()
            except Exception:
                pass

    def _enter_fullscreen(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.dock.show()
        self.dock.raise_()
        self.news.raise_()

    def _place_corners(self, keep_positions: bool = False) -> None:
        w, h = self.width(), self.height()
        if not keep_positions or not self.news.isVisible():
            self.news.move(18, 18)
        else:
            self.news.move(
                max(0, min(w - self.news.width(), self.news.x())),
                max(0, min(h - self.news.height(), self.news.y())),
            )
        if not keep_positions:
            self.dock.move(
                max(12, w - self.dock.width() - 20),
                max(12, h - self.dock.height() - 20),
            )
        else:
            self.dock.move(
                max(0, min(w - self.dock.width(), self.dock.x())),
                max(0, min(h - self.dock.height(), self.dock.y())),
            )

    def _toggle_news_corner(self) -> None:
        if self.news.isVisible():
            self.news.hide()
        else:
            self._show_news_top_left()

    def _get_probe(self) -> CameraOpener:
        if self._probe is None:
            self._probe = CameraOpener()
        return self._probe

    def _try_sources(self, sources: list) -> list[tuple[float, object, int, str, str]]:
        """Try camera sources by index — accept dim feeds, reject OBS only."""
        import cv2

        from jarvis.core.camera_io import open_by_index, silence_opencv_logs

        probe = self._get_probe()
        found: list[tuple[float, object, int, str, str]] = []
        seen: set[int] = set()
        with silence_opencv_logs():
            for source in sources:
                if isinstance(source, str):
                    continue
                idx = int(source)
                if idx in seen or idx < 0:
                    continue
                seen.add(idx)
                got = open_by_index(idx, reads=6, max_width=960, max_height=540)
                if not got:
                    continue
                cap, backend = got
                frames = []
                for _ in range(5):
                    ok, fr = cap.read()
                    if ok and fr is not None:
                        frames.append(fr)
                    time.sleep(0.02)
                if len(frames) < 1:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    continue
                motion = 0.0
                if len(frames) >= 2:
                    motion = float(np.mean(cv2.absdiff(frames[0], frames[-1])))
                score = probe._frame_score(frames[-1], motion=motion)
                # Soft reject — dark rooms score low but are still valid EMEET feeds
                if probe._is_obs_placeholder(frames[-1]) or score < -500:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    if probe._is_obs_placeholder(frames[-1]):
                        print(f"[theater] skip OBS placeholder at index {idx}")
                    continue
                if idx == self._preferred_index:
                    score += 40
                prefer_u = (self._prefer or "").upper()
                if prefer_u and prefer_u in ("EMEET", "SMARTCAM") and idx <= 2:
                    score += 12
                label = f"index {idx}"
                found.append((score, cap, idx, backend, label))
                if score >= 25 and idx == self._preferred_index:
                    break
        return found

    def _open_best(self) -> None:
        self._timer.stop()
        self._opening = True
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        try:
            import cv2  # noqa: F401
        except Exception as e:
            self._opening = False
            self.view.setText(f"OpenCV missing: {e}")
            return

        # Fast path: preferred index only (settings.camera_index, usually EMEET @ 1)
        prefer_idx = self._preferred_index if self._preferred_index >= 0 else 0
        try:
            from jarvis.core.camera_io import open_by_index, silence_opencv_logs

            with silence_opencv_logs():
                got = open_by_index(prefer_idx, reads=6, max_width=960, max_height=540)
            if got:
                cap, backend = got
                self._cap = cap
                self._index = prefer_idx
                self._backend = backend
                self._label = f"index {prefer_idx}"
                self._fail_streak = 0
                self._opening = False
                self.dock.set_status(
                    f"LIVE · {self._label} · {backend} · fist locks panels"
                )
                self.view.setText("")
                self._paint_ms = getattr(self, "_paint_ms", 66)
                self._timer.start(self._paint_ms)
                self._place_corners()
                self.dock.raise_()
                # News is lazy — user taps NEWS (no auto WebEngine on open)
                print(f"[theater] fast open idx={prefer_idx} via {backend}")
                return
        except Exception as e:
            print(f"[theater] fast open: {e}")

        # Preferred first, then scan a wider index range (EMEET often not 0)
        sources: list = []
        if self._preferred_index >= 0:
            sources.append(self._preferred_index)
        for i in range(9):
            if i not in sources:
                sources.append(i)

        candidates = self._try_sources(sources)
        if not candidates:
            # Last resort: shared picker with softer gates
            try:
                from jarvis.core.camera_io import pick_best_camera

                picked = pick_best_camera(
                    preferred_index=self._preferred_index,
                    prefer=self._prefer or "EMEET",
                    max_index=8,
                )
            except Exception:
                picked = None
            if not picked:
                self._opening = False
                self.view.setText(
                    "No camera feed.\nClose Zoom / Teams / OBS Virtual Camera,\n"
                    "unplug/replug EMEET, then say open camera again."
                )
                self.dock.set_status("Camera failed — device busy or missing")
                return
            cap, idx, backend, score = picked
            self._cap = cap
            self._index = idx
            self._backend = backend
            self._label = f"index {idx}"
            self._fail_streak = 0
            self._opening = False
            self.dock.set_status(f"LIVE · {self._label} · {backend} · fist locks panels")
            self.view.setText("")
            self._paint_ms = getattr(self, "_paint_ms", 66)
            self._timer.start(self._paint_ms)
            self._place_corners()
            self.dock.raise_()
            # News is lazy — user taps NEWS (no auto WebEngine on open)
            print(f"[theater] fallback pick idx={idx} via {backend} score={score:.1f}")
            return

        candidates.sort(key=lambda c: c[0], reverse=True)
        best = candidates[0]
        for c in candidates[1:]:
            try:
                c[1].release()
            except Exception:
                pass
        score, cap, idx, backend, label = best
        self._cap = cap
        self._index = idx if isinstance(idx, int) else self._preferred_index
        self._backend = backend
        self._label = label
        self._fail_streak = 0
        self._opening = False
        self.dock.set_status(f"LIVE · {label} · {backend} · fist locks panels")
        self.view.setText("")
        self._paint_ms = getattr(self, "_paint_ms", 66)
        self._timer.start(self._paint_ms)
        self._place_corners()
        self.dock.raise_()
        # News is lazy — user taps NEWS (no auto WebEngine on open)
        print(f"[theater] chose idx={self._index} via {backend} score={score:.1f}")

    def set_paint_interval(self, ms: int) -> None:
        self._paint_ms = max(66, min(120, int(ms)))
        if self._timer.isActive():
            self._timer.setInterval(self._paint_ms)

    def _paint_frame(self) -> None:
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._fail_streak += 1
            if self._fail_streak >= 25:
                self.view.setText("Camera stalled")
            return
        self._fail_streak = 0
        with self._lock:
            self._frame = frame

        try:
            import cv2

            use_thermal = bool(getattr(self, "_thermal_assist", False))
            use_nv = bool(self._night_vision)
            night_ok = False
            if use_nv or use_thermal:
                try:
                    from jarvis.core.boot_biometrics import is_night_hours

                    night_ok = is_night_hours()
                except Exception:
                    night_ok = False

            if use_thermal:
                from jarvis.ui.widgets.night_vision import apply_thermal_assist

                draw = apply_thermal_assist(frame)
                cv2.putText(
                    draw,
                    "THERMAL ASSIST",
                    (18, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.85,
                    (40, 180, 255),
                    2,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    draw,
                    "software · not FLIR",
                    (18, 68),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (180, 200, 255),
                    1,
                    cv2.LINE_AA,
                )
            elif use_nv and night_ok:
                from jarvis.ui.widgets.night_vision import apply_night_vision

                draw = apply_night_vision(frame)
                cv2.putText(
                    draw,
                    "NIGHT VISION",
                    (18, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.85,
                    (60, 255, 120),
                    2,
                    cv2.LINE_AA,
                )
            else:
                # Cheap brightness lift only when very dark; else skip full copy
                mean = float(np.mean(frame[::16, ::16]))
                if mean < 28:
                    draw = cv2.convertScaleAbs(frame, alpha=1.28, beta=16)
                else:
                    draw = frame

            if self._mirror:
                draw = cv2.flip(draw, 1)
            elif draw is frame and self._gestures_on and self._tracker is not None:
                # Avoid mutating the live capture buffer when drawing landmarks
                draw = frame.copy()

            if self._gestures_on and self._tracker is not None:
                # Skip harder so MediaPipe never owns every paint
                period = 8 if self._gesture_locked else 6
                self._gesture_skip = (self._gesture_skip + 1) % period
                if self._gesture_skip == 0:
                    state = self._tracker.process(
                        frame, mirrored=True, max_width=240
                    )
                    self._last_gesture = state
                    self._update_gesture_lock(state)
                    try:
                        if state.label in ("fist", "thumbs_up", "wave_left"):
                            self.gesture.emit(state)
                    except Exception:
                        pass
                    if not self._gesture_locked and state.active:
                        sx, sy = self._smooth_cursor
                        cx, cy = state.cursor
                        self._smooth_cursor = (
                            sx * 0.6 + cx * 0.4,
                            sy * 0.6 + cy * 0.4,
                        )
                        if getattr(self, "_lab_mode", False) and getattr(
                            self, "fabricator", None
                        ) is not None and self.fabricator.is_lab_open():
                            self.fabricator.on_gesture(state)
                        elif getattr(self, "_ar_mode", False) and getattr(
                            self, "aerospatial", None
                        ) is not None and self.aerospatial.is_ar_open():
                            self.aerospatial.on_gesture(state)
                        else:
                            if state.pinch:
                                self.gesture_drag.emit(*self._smooth_cursor)
                                self._apply_gesture_drag(*self._smooth_cursor)
                            if state.swipe:
                                self.gesture_swipe.emit(state.swipe)
                                self._apply_swipe(state.swipe)
                    self._refresh_gesture_label(state)

                if not self._gesture_locked and self._last_gesture.active:
                    clean = not (
                        getattr(self, "_lab_mode", False)
                        or getattr(self, "_ar_mode", False)
                    )
                    draw = draw_gestures(draw, self._last_gesture, clean=clean)

            # Downscale to window size before Qt convert (big lag win)
            tw = max(1, self.width())
            th = max(1, self.height())
            h, w = draw.shape[:2]
            scale = max(tw / w, th / h)
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            if nw != w or nh != h:
                draw = cv2.resize(draw, (nw, nh), interpolation=cv2.INTER_LINEAR)
            x0 = max(0, (nw - tw) // 2)
            y0 = max(0, (nh - th) // 2)
            draw = draw[y0 : y0 + th, x0 : x0 + tw]
            if draw.shape[0] != th or draw.shape[1] != tw:
                draw = cv2.resize(draw, (tw, th), interpolation=cv2.INTER_LINEAR)

            rgb = cv2.cvtColor(draw, cv2.COLOR_BGR2RGB)
            hh, ww, ch = rgb.shape
            img = QImage(rgb.data, ww, hh, ch * ww, QImage.Format.Format_RGB888).copy()
            self.view.setPixmap(QPixmap.fromImage(img))
            # No per-frame raise_/lower — stacking only on show/toggle/drag
            if getattr(self, "fabricator", None) is not None and self.fabricator.isVisible():
                self.fabricator.setGeometry(self.rect())
            if getattr(self, "aerospatial", None) is not None and self.aerospatial.isVisible():
                try:
                    self.aerospatial.ingest_frame(frame)
                except Exception:
                    pass
                self.aerospatial.setGeometry(self.rect())
        except Exception as e:
            self.view.setText(str(e))

    def _set_lab_mode(self, on: bool) -> None:
        self._lab_mode = bool(on)
        if not on and getattr(self, "fabricator", None) is not None:
            try:
                if self.fabricator.isVisible():
                    self.fabricator.close_lab()
            except Exception:
                pass

    def _set_ar_mode(self, on: bool) -> None:
        self._ar_mode = bool(on)
        if not on and getattr(self, "aerospatial", None) is not None:
            try:
                if self.aerospatial.isVisible():
                    self.aerospatial.close_ar()
            except Exception:
                pass

    def open_fabricator(self) -> None:
        """Open Stark jet hologram lab over the live camera feed."""
        if not self.isVisible():
            self.open_feed(self._preferred_index, prefer=self._prefer)
        self.set_gestures_enabled(True)
        self._lab_mode = True
        if getattr(self, "fabricator", None) is not None:
            self.fabricator.setGeometry(self.rect())
            self.fabricator.open_lab()
            self.fabricator.raise_()
        self.dock.raise_()

    def close_fabricator(self) -> None:
        self._set_lab_mode(False)

    def open_aerospatial(self) -> None:
        """Open AR aerospatial mapping overlay on the live room camera."""
        if not self.isVisible():
            self.open_feed(self._preferred_index, prefer=self._prefer)
        self.set_gestures_enabled(True)
        self._ar_mode = True
        if getattr(self, "aerospatial", None) is not None:
            self.aerospatial.setGeometry(self.rect())
            self.aerospatial.open_ar()
            self.aerospatial.raise_()
        self.dock.set_status("AR AEROSPATIAL · mapping room")
        self.dock.raise_()

    def close_aerospatial(self) -> None:
        self._set_ar_mode(False)

    def _set_ops_hud(self, on: bool) -> None:
        self._ops_hud_on = bool(on)
        if not on and getattr(self, "ops_globe", None) is not None:
            try:
                if self.ops_globe.isVisible():
                    self.ops_globe.hide()
            except Exception:
                pass

    def open_ops_hud(self, pins: list | None = None) -> None:
        """Show owner-site ops map panel beside live camera feed."""
        if not self.isVisible():
            self.open_feed(self._preferred_index, prefer=self._prefer)
        self._ops_hud_on = True
        globe = getattr(self, "ops_globe", None)
        if globe is not None:
            if pins is not None:
                try:
                    globe.set_pins(pins)
                except Exception:
                    pass
            self._place_ops_globe()
            globe.open_panel()
            globe.raise_()
        self.dock.set_status("OPS HUD · owner map")
        self.dock.raise_()

    def close_ops_hud(self) -> None:
        self._set_ops_hud(False)

    def set_ops_pins(self, pins: list | None) -> None:
        globe = getattr(self, "ops_globe", None)
        if globe is not None:
            try:
                globe.set_pins(pins or [])
            except Exception:
                pass

    def open_traffic_board_panel(self, fetcher=None, city: str = "Philadelphia") -> None:
        """Show public traffic stills overlay (lazy create)."""
        panel = getattr(self, "traffic_board", None)
        if panel is None:
            try:
                from jarvis.ui.widgets.traffic_board import TrafficBoardPanel

                panel = TrafficBoardPanel(self)
                panel.hide()
                panel.closed.connect(lambda: None)
                panel.open_board.connect(self._emit_open_511)
                panel.open_live_map.connect(self.open_traffic_live_map)
                self.traffic_board = panel
            except Exception as e:
                print(f"[traffic_board] init: {e}")
                return
        try:
            panel.set_city(city or "Philadelphia")
            if fetcher is not None:
                panel.set_fetcher(fetcher)
            x = max(12, (self.width() - panel.width()) // 2)
            y = max(40, (self.height() - panel.height()) // 2)
            panel.move(x, y)
            panel.open_panel()
            panel.raise_()
            self.dock.raise_()
        except Exception as e:
            print(f"[traffic_board] open: {e}")

    def close_traffic_board_panel(self) -> None:
        panel = getattr(self, "traffic_board", None)
        if panel is not None:
            try:
                panel.close_panel()
            except Exception:
                pass

    def open_scanner_audio(
        self, url: str = "", title: str = "LIVE SCANNER AUDIO"
    ) -> None:
        """Embed Broadcastify / NOAA player on the camera theater."""
        panel = getattr(self, "scanner_audio", None)
        if panel is None:
            try:
                from jarvis.ui.widgets.traffic_board import ScannerAudioPanel

                panel = ScannerAudioPanel(self)
                panel.hide()
                self.scanner_audio = panel
            except Exception as e:
                print(f"[scanner_audio] init: {e}")
                return
        try:
            u = (url or "").strip() or "https://www.broadcastify.com/listen/ctid/2291"
            panel.move(
                max(12, self.width() - panel.width() - 24),
                max(40, (self.height() - panel.height()) // 2),
            )
            panel.open_panel(u, title=title or "LIVE SCANNER AUDIO")
            panel.raise_()
            self.dock.set_sec_line(
                "LISTEN/SAT · live radio (traffic cam tiles stay silent)"
            )
            self.dock.raise_()
        except Exception as e:
            print(f"[scanner_audio] open: {e}")

    def close_scanner_audio(self) -> None:
        panel = getattr(self, "scanner_audio", None)
        if panel is not None:
            try:
                if hasattr(panel, "close_panel"):
                    panel.close_panel()
                else:
                    panel.hide()
            except Exception:
                pass

    def set_desk_sec_line(self, text: str) -> None:
        try:
            self.dock.set_sec_line(text)
        except Exception:
            pass

    def open_traffic_live_map(self, url: str | None = None, title: str | None = None) -> None:
        """Show embedded official 511/DOT interactive map."""
        panel = getattr(self, "traffic_live_map", None)
        if panel is None:
            try:
                from jarvis.ui.widgets.traffic_board import TrafficLiveMapPanel

                panel = TrafficLiveMapPanel(self)
                panel.hide()
                panel.closed.connect(lambda: None)
                self.traffic_live_map = panel
            except Exception as e:
                print(f"[traffic_live_map] init: {e}")
                self._emit_open_511()
                return
        try:
            if url:
                panel.set_map_url(url, title=title)
            elif title:
                panel.title.setText(title)
            x = max(12, (self.width() - panel.width()) // 2)
            y = max(20, (self.height() - panel.height()) // 2)
            panel.move(x, y)
            panel.open_panel(url)
            panel.raise_()
            self.dock.raise_()
        except Exception as e:
            print(f"[traffic_live_map] open: {e}")
            self._emit_open_511()

    def close_traffic_live_map(self) -> None:
        panel = getattr(self, "traffic_live_map", None)
        if panel is not None:
            try:
                panel.close_panel()
            except Exception:
                pass

    def _emit_open_511(self) -> None:
        try:
            from jarvis.core.traffic_cams import TRAFFIC_BOARD_URL
            import webbrowser

            webbrowser.open(TRAFFIC_BOARD_URL)
        except Exception as e:
            print(f"[traffic_board] 511: {e}")

    def _place_ops_globe(self) -> None:
        globe = getattr(self, "ops_globe", None)
        if globe is None:
            return
        # Top-right, keep clear of news (top-left) and dock (bottom-right)
        x = max(12, self.width() - globe.width() - 20)
        y = 18
        globe.move(x, y)

    def _update_gesture_lock(self, state: GestureState) -> None:
        if not state.active:
            self._fist_streak = 0
            self._open_streak = 0
            return
        if state.label == "fist":
            self._fist_streak += 1
            self._open_streak = 0
            if self._fist_streak >= 2:
                self._gesture_locked = True
        elif state.label == "open" and self._gesture_locked:
            self._open_streak += 1
            self._fist_streak = 0
            if self._open_streak >= 3:
                self._gesture_locked = False
                self._open_streak = 0
        else:
            self._fist_streak = 0
            if state.label != "open":
                self._open_streak = 0

    def _refresh_gesture_label(self, state: GestureState) -> None:
        if self._gesture_locked:
            self.dock.set_gesture("LOCKED · open hand or UNLOCK")
            return
        if not state.active:
            self.dock.set_gesture("Gesture: —")
            return
        extra = " · DRAG" if state.pinch else ""
        self.dock.set_gesture(f"Gesture: {state.label.upper()}{extra}")

    def _apply_gesture_drag(self, nx: float, ny: float) -> None:
        if self._gesture_locked:
            return
        w, h = max(1, self.width()), max(1, self.height())
        if nx < 0.42 and self.news.isVisible():
            target = self.news
        else:
            target = self.dock
        x = int(nx * w - target.width() / 2)
        y = int(ny * h - target.height() / 2)
        x = max(0, min(w - target.width(), x))
        y = max(0, min(h - target.height(), y))
        target.move(x, y)
        target.raise_()

    def _apply_swipe(self, direction: str) -> None:
        if self._gesture_locked:
            return
        if direction == "left" and not self.news.isVisible():
            self._show_news_top_left()
        elif direction == "right" and self.news.isVisible():
            self.news.hide()
        elif direction == "down":
            self.dock.move(
                max(12, self.width() - self.dock.width() - 20),
                max(12, self.height() - self.dock.height() - 20),
            )

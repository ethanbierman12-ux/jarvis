"""Traffic board overlay — multi-region near-live official DOT stills.

Regions: PHL / MIA / NYC / WORLD. Hero + 3 tiles, ~1s near-live refresh.
MAP opens official 511/DOT embed; FIND focuses tactical map address search.
Soft-fails keep last good pixmap. No private CCTV.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QByteArray, QUrl
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGridLayout,
    QSizePolicy,
    QWidget,
)


def _hud_btn(text: str, w: int = 40, *, active: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedSize(w, 24)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    bg = "rgba(0,232,255,55)" if active else "transparent"
    btn.setStyleSheet(
        f"QPushButton {{ color:#00e8ff; background:{bg};"
        " border:1px solid rgba(0,232,255,100); font-size:10px; }"
        "QPushButton:hover { background:rgba(0,232,255,40); }"
    )
    return btn


class TrafficBoardPanel(QFrame):
    """Draggable dark HUD — hero + 3 near-live public traffic stills."""

    closed = pyqtSignal()
    open_board = pyqtSignal()
    open_live_map = pyqtSignal()
    find_address = pyqtSignal()
    play_dispatch = pyqtSignal()
    play_listen = pyqtSignal()
    play_truck = pyqtSignal()
    play_sat = pyqtSignal()
    region_changed = pyqtSignal(str)
    _rows_ready = pyqtSignal(object, str, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TrafficBoardPanel")
        self.setFixedSize(780, 600)
        self.setStyleSheet(
            "QFrame#TrafficBoardPanel {"
            " background: rgba(2,10,18,235);"
            " border: 1px solid rgba(0,232,255,140);"
            "}"
        )
        self._drag_origin = None
        self._drag_start = None
        self._fetch: Callable[[], list] | None = None
        self._city = "Philadelphia"
        self._region = "philadelphia"
        self._page = 0
        self._had_pixmap = [False] * 4
        self._pulse_on = False
        self._region_btns: dict[str, QPushButton] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        self.title = QLabel("TRAFFIC · PHILADELPHIA")
        self.title.setStyleSheet(
            "color:#00e8ff; font-size:12px; font-weight:600; letter-spacing:1px;"
        )
        self.tip = QLabel(
            "MAP = video · LISTEN = city scanner · SAT = NOAA radio · cams stay silent"
        )
        self.tip.setStyleSheet("color:#6a9aaa; font-size:9px;")
        board_btn = _hud_btn("511")
        board_btn.clicked.connect(self.open_board.emit)
        map_btn = _hud_btn("MAP")
        map_btn.clicked.connect(self.open_live_map.emit)
        find_btn = _hud_btn("FIND", 44)
        find_btn.clicked.connect(self.find_address.emit)
        dispatch_btn = _hud_btn("DISPATCH", 64)
        dispatch_btn.setToolTip("Public Broadcastify local dispatch (listen only)")
        dispatch_btn.clicked.connect(self.play_dispatch.emit)
        truck_btn = _hud_btn("TRUCK", 48)
        truck_btn.setToolTip("Public Broadcastify truck / DOT / highway (listen only)")
        truck_btn.clicked.connect(self.play_truck.emit)
        listen_btn = _hud_btn("LISTEN", 52)
        listen_btn.setToolTip(
            "Live city scanner audio — traffic cam tiles have no microphone"
        )
        listen_btn.clicked.connect(self.play_listen.emit)
        sat_btn = _hud_btn("SAT", 40)
        sat_btn.setToolTip(
            "NOAA / satellite weather radio (Broadcastify + optional SDR) — not cam mics"
        )
        sat_btn.clicked.connect(self.play_sat.emit)
        next_btn = _hud_btn("NEXT", 44)
        next_btn.clicked.connect(self._next_page)
        close = QPushButton("✕")
        close.setFixedSize(28, 24)
        close.setStyleSheet(
            "QPushButton { color:#8aa4b8; background:transparent; border:none; }"
            "QPushButton:hover { color:#00e8ff; }"
        )
        close.clicked.connect(self._close)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.tip)
        head.addWidget(board_btn)
        head.addWidget(map_btn)
        head.addWidget(find_btn)
        head.addWidget(dispatch_btn)
        head.addWidget(truck_btn)
        head.addWidget(listen_btn)
        head.addWidget(sat_btn)
        head.addWidget(next_btn)
        head.addWidget(close)
        lay.addLayout(head)

        # Region switcher
        reg = QHBoxLayout()
        reg.setSpacing(4)
        reg_lab = QLabel("REGION")
        reg_lab.setStyleSheet("color:#6a9aaa; font-size:9px;")
        reg.addWidget(reg_lab)
        for key, label in (
            ("philadelphia", "PHL"),
            ("miami", "MIA"),
            ("nyc", "NYC"),
            ("world", "WORLD"),
        ):
            b = _hud_btn(label, 52 if label == "WORLD" else 40, active=(key == "philadelphia"))
            b.clicked.connect(lambda _=False, r=key: self._on_region(r))
            self._region_btns[key] = b
            reg.addWidget(b)
        reg.addStretch(1)
        lay.addLayout(reg)

        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        self._tiles: list[QLabel] = []
        self._captions: list[QLabel] = []
        self._live_badges: list[QLabel] = []
        self._cells: list[QFrame] = []
        for i in range(4):
            cell = QFrame()
            cell.setStyleSheet(
                "QFrame { background:#02080e; border:1px solid rgba(0,232,255,60); }"
            )
            cell_lay = QVBoxLayout(cell)
            cell_lay.setContentsMargins(2, 2, 2, 2)
            cell_lay.setSpacing(2)
            tw, th = (696, 250) if i == 0 else (226, 130)
            img = QLabel("loading")
            img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img.setFixedSize(tw, th)
            img.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            img.setStyleSheet("color:#5a7388; background:#02080e; font-size:10px;")
            img.setScaledContents(True)
            cap_row = QHBoxLayout()
            cap_row.setContentsMargins(2, 0, 2, 0)
            live = QLabel("● LIVE")
            live.setStyleSheet(
                "color:#ff3355; font-size:8px; font-weight:700; letter-spacing:1px;"
            )
            live.setFixedWidth(48)
            cap = QLabel("")
            cap.setStyleSheet("color:#8aa4b8; font-size:9px;")
            cap.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            cap_row.addWidget(live)
            cap_row.addWidget(cap, 1)
            cell_lay.addWidget(img, 0, Qt.AlignmentFlag.AlignCenter)
            cell_lay.addLayout(cap_row)
            self._cells.append(cell)
            self._tiles.append(img)
            self._captions.append(cap)
            self._live_badges.append(live)
        self.grid.addWidget(self._cells[0], 0, 0, 1, 3)
        for i in range(1, 4):
            self.grid.addWidget(self._cells[i], 1, i - 1)
        lay.addLayout(self.grid, 1)

        self.status = QLabel("Loading near-live stills…")
        self.status.setStyleSheet("color:#8aa4b8; font-size:10px;")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)  # near-real-time still refresh
        self._timer.timeout.connect(self._refresh)
        self._pulse = QTimer(self)
        self._pulse.setInterval(500)
        self._pulse.timeout.connect(self._pulse_live)
        self._busy = False
        self._refresh_gen = 0
        self._ticks = 0
        self._last_hashes: list[str] = [""] * 4
        self._rows_ready.connect(self._on_rows_ready)

    def page_offset(self) -> int:
        return max(0, int(self._page) * 4)

    def current_region(self) -> str:
        return self._region

    def _on_region(self, region: str) -> None:
        self._page = 0
        self._had_pixmap = [False] * 4
        self.set_region(region)
        self.region_changed.emit(region)
        self.status.setText(f"Switching region -> {region.upper()}...")
        self._busy = False
        QTimer.singleShot(60, self._refresh)

    def set_region(self, region: str) -> None:
        from jarvis.core.traffic_cams import normalize_region, REGION_LABELS

        self._region = normalize_region(region)
        label = REGION_LABELS.get(self._region, region)
        self._city = label
        self.title.setText(f"TRAFFIC · {label.upper()}")
        tip_map = {
            "philadelphia": (
                "PA stills lag — MAP for motion · LISTEN city scanner · "
                "SAT NOAA radio · cams silent"
            ),
            "miami": (
                "FL stills lag — MAP for video · LISTEN city scanner · "
                "SAT NOAA radio · cams silent"
            ),
            "florida": (
                "FL stills lag — MAP for video · LISTEN city scanner · "
                "SAT NOAA radio · cams silent"
            ),
            "nyc": (
                "NYC stills ~1–3s · LISTEN city scanner · SAT NOAA radio · cams silent"
            ),
            "world": (
                "MAP video · LISTEN city scanner · SAT NOAA radio · cam tiles stay silent"
            ),
        }
        self.tip.setText(
            tip_map.get(
                self._region,
                "MAP = video · LISTEN = city scanner · SAT = NOAA · cams silent",
            )
        )
        # NYC frames actually change — refresh faster; PA/FL CDN stills are sticky
        if self._region == "nyc":
            self._timer.setInterval(700)
        else:
            self._timer.setInterval(1200)
        for key, btn in self._region_btns.items():
            active = key == self._region or (
                self._region == "florida" and key == "miami"
            )
            bg = "rgba(0,232,255,55)" if active else "transparent"
            btn.setStyleSheet(
                f"QPushButton {{ color:#00e8ff; background:{bg};"
                " border:1px solid rgba(0,232,255,100); font-size:10px; }"
                "QPushButton:hover { background:rgba(0,232,255,40); }"
            )

    def _next_page(self) -> None:
        self._page = int(self._page or 0) + 1
        self.status.setText(f"Rotating cams · page {self._page + 1}…")
        self._busy = False
        QTimer.singleShot(40, self._refresh)

    def set_city(self, city: str) -> None:
        self.set_region(city)

    def set_fetcher(self, fn: Callable[[], list] | None) -> None:
        self._fetch = fn

    def open_panel(self) -> None:
        self.show()
        self.raise_()
        self._busy = False
        self._had_pixmap = [False] * 4
        for tile in self._tiles:
            tile.clear()
            tile.setText("loading")
        self.status.setText("Loading near-live stills…")
        if not self._timer.isActive():
            self._timer.start()
        if not self._pulse.isActive():
            self._pulse.start()
        QTimer.singleShot(80, self._refresh)

    def close_panel(self) -> None:
        self._timer.stop()
        self._pulse.stop()
        self._busy = False
        self.hide()
        self.closed.emit()

    def _close(self) -> None:
        self.close_panel()

    def _pulse_live(self) -> None:
        self._pulse_on = not self._pulse_on
        color = "#ff3355" if self._pulse_on else "#00e8ff"
        style = (
            f"color:{color}; font-size:8px; font-weight:700; letter-spacing:1px;"
        )
        for badge in self._live_badges:
            if badge.isVisible():
                badge.setStyleSheet(style)

    def _refresh(self) -> None:
        if not self.isVisible():
            return
        if self._fetch is None:
            self.status.setText("No traffic feed wired — press MAP / 511.")
            for i, tile in enumerate(self._tiles):
                if not self._had_pixmap[i]:
                    tile.clear()
                    tile.setText("no feed")
            return
        # Auto-rotate camera set so the board doesn't freeze on one spot
        self._ticks = int(self._ticks or 0) + 1
        if self._ticks >= 6:
            self._ticks = 0
            self._page = int(self._page or 0) + 1
        # Don't stack workers forever — allow a new gen if previous is stuck
        if self._busy:
            return
        self._busy = True
        self._refresh_gen = int(self._refresh_gen or 0) + 1
        gen = self._refresh_gen

        def _job() -> None:
            rows: list[dict[str, Any]] = []
            err = ""
            try:
                rows = list(self._fetch() or [])
            except Exception as e:
                err = str(e)
            try:
                self._rows_ready.emit(rows, err, gen)
            except TypeError:
                # Older signal arity during hot-reload
                try:
                    self._rows_ready.emit(rows, err)
                except Exception as e:
                    print(f"[traffic_board] emit: {e}")
            except Exception as e:
                print(f"[traffic_board] emit: {e}")

        threading.Thread(target=_job, daemon=True, name="traffic-board").start()
        QTimer.singleShot(8000, lambda: self._unstick_busy(gen))

    def _unstick_busy(self, gen: int | None = None) -> None:
        if gen is not None and gen != self._refresh_gen:
            return
        if self._busy:
            self._busy = False
            if self.isVisible():
                self.status.setText("Catching up…")
                QTimer.singleShot(200, self._refresh)

    def _on_rows_ready(self, rows: object, err: str, gen: int = 0) -> None:
        if gen and gen != self._refresh_gen:
            return  # stale
        self._busy = False
        self._apply_rows(list(rows or []), err or "")

    def _apply_rows(self, rows: list[dict[str, Any]], err: str) -> None:
        if err and not rows:
            self.status.setText(f"Soft-fail · {err[:80]} — try MAP / next region")
            for i, tile in enumerate(self._tiles):
                if not self._had_pixmap[i]:
                    tile.clear()
                    tile.setText("offline")
            return
        ok_n = 0
        changed = 0
        for i, tile in enumerate(self._tiles):
            if i >= len(rows):
                if not self._had_pixmap[i]:
                    tile.clear()
                    tile.setText("—")
                self._captions[i].setText("")
                continue
            row = rows[i]
            name = str(row.get("name") or f"Cam {i + 1}")
            road = str(row.get("road") or "")
            label = name[:42]
            if road and road.lower() not in name.lower():
                label = f"{road} · {name}"[:42]
            self._captions[i].setText(label)
            blob = row.get("bytes")
            if blob:
                try:
                    raw = bytes(blob) if not isinstance(blob, (bytes, bytearray)) else blob
                    h = str(row.get("hash") or "")
                    if not h:
                        import hashlib

                        h = hashlib.md5(raw).hexdigest()[:12]
                    pix = QPixmap()
                    ok = pix.loadFromData(QByteArray(raw))
                    if ok and not pix.isNull():
                        tile.clear()
                        tile.setPixmap(pix)
                        self._had_pixmap[i] = True
                        ok_n += 1
                        if h and h != self._last_hashes[i]:
                            changed += 1
                            self._last_hashes[i] = h
                        continue
                except Exception as e:
                    print(f"[traffic_board] pixmap: {e}")
            if not self._had_pixmap[i]:
                tile.clear()
                tile.setText("no still")
        if ok_n:
            stuck = ok_n - changed
            note = ""
            if stuck >= ok_n and self._region in (
                "philadelphia",
                "miami",
                "florida",
            ):
                note = " · stills frozen — open MAP for moving video"
            self.status.setText(
                f"{ok_n} tiles · {changed} new frames · "
                f"{self._region.upper()} · page {self._page + 1}"
                f"{note} · LISTEN = audio"
            )
        else:
            self.status.setText(
                "No stills — press MAP for live video, LISTEN for scanner audio."
            )

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = e.globalPosition().toPoint()
            self._drag_start = self.pos()
            self.raise_()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
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

    def mouseReleaseEvent(self, e) -> None:
        self._drag_origin = None
        self._drag_start = None
        super().mouseReleaseEvent(e)


class TrafficLiveMapPanel(QFrame):
    """Embedded official 511 / DOT interactive map (live video in their player)."""

    closed = pyqtSignal()

    def __init__(self, parent=None, *, url: str | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TrafficLiveMapPanel")
        self.setFixedSize(900, 620)
        self.setStyleSheet(
            "QFrame#TrafficLiveMapPanel {"
            " background: rgba(2,10,18,240);"
            " border: 1px solid rgba(0,232,255,150);"
            "}"
        )
        self._drag_origin = None
        self._drag_start = None
        self._web = None
        self._url = url or "https://www.511pa.com/"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)

        head = QHBoxLayout()
        self.title = QLabel("LIVE TRAFFIC MAP")
        self.title.setStyleSheet(
            "color:#00e8ff; font-size:12px; font-weight:600; letter-spacing:1px;"
        )
        tip = QLabel("official map · live video in their player")
        tip.setStyleSheet("color:#6a9aaa; font-size:9px;")
        close = QPushButton("✕")
        close.setFixedSize(28, 24)
        close.setStyleSheet(
            "QPushButton { color:#8aa4b8; background:transparent; border:none; }"
            "QPushButton:hover { color:#00e8ff; }"
        )
        close.clicked.connect(self._close)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(tip)
        head.addWidget(close)
        lay.addLayout(head)

        self._host = QWidget(self)
        self._host.setStyleSheet("background:#02080e;")
        self._host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        host_lay = QVBoxLayout(self._host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        self._fallback = QLabel("Loading official traffic map…")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet("color:#5a7388; font-size:11px;")
        host_lay.addWidget(self._fallback)
        lay.addWidget(self._host, 1)

        self.status = QLabel("Official DOT / 511 interactive map")
        self.status.setStyleSheet("color:#8aa4b8; font-size:10px;")
        lay.addWidget(self.status)

    def set_map_url(self, url: str, *, title: str | None = None) -> None:
        self._url = (url or "https://www.511pa.com/").strip()
        if title:
            self.title.setText(title)

    def _ensure_web(self) -> bool:
        if self._web is not None:
            return True
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._fallback.hide()
            self._web = QWebEngineView(self._host)
            s = self._web.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            try:
                s.setAttribute(
                    QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
                )
            except Exception:
                pass
            lay = self._host.layout()
            if lay is not None:
                lay.addWidget(self._web)
            return True
        except Exception as e:
            self._fallback.setText(
                f"WebEngine needed for live map.\n{e}\n"
                "Press 511 to open in browser."
            )
            self._fallback.show()
            return False

    def open_panel(self, url: str | None = None) -> None:
        if url:
            self._url = url
        self.show()
        self.raise_()
        if self._ensure_web() and self._web is not None:
            self.status.setText(f"Loading {self._url}…")
            self._web.load(QUrl(self._url))
            self.status.setText("Official live map · click cams for video")
        else:
            self.status.setText("WebEngine unavailable — use 511 browser button")

    def close_panel(self) -> None:
        try:
            if self._web is not None:
                self._web.load(QUrl("about:blank"))
        except Exception:
            pass
        self.hide()
        self.closed.emit()

    def _close(self) -> None:
        self.close_panel()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = e.globalPosition().toPoint()
            self._drag_start = self.pos()
            self.raise_()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
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

    def mouseReleaseEvent(self, e) -> None:
        self._drag_origin = None
        self._drag_start = None
        super().mouseReleaseEvent(e)


class ScannerAudioPanel(QFrame):
    """In-HUD live Broadcastify player — real scanner audio (not cam mics)."""

    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ScannerAudioPanel")
        self.setFixedSize(520, 420)
        self.setStyleSheet(
            "QFrame#ScannerAudioPanel {"
            " background: rgba(2,10,18,240);"
            " border: 1px solid rgba(0,232,255,150);"
            "}"
        )
        self._drag_origin = None
        self._drag_start = None
        self._web = None
        self._url = "https://www.broadcastify.com/listen/ctid/2291"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)

        head = QHBoxLayout()
        self.title = QLabel("LIVE SCANNER AUDIO")
        self.title.setStyleSheet(
            "color:#00e8ff; font-size:12px; font-weight:600; letter-spacing:1px;"
        )
        tip = QLabel("Broadcastify · click Play on a feed")
        tip.setStyleSheet("color:#6a9aaa; font-size:9px;")
        close = QPushButton("✕")
        close.setFixedSize(28, 24)
        close.setStyleSheet(
            "QPushButton { color:#8aa4b8; background:transparent; border:none; }"
            "QPushButton:hover { color:#00e8ff; }"
        )
        close.clicked.connect(self._close)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(tip)
        head.addWidget(close)
        lay.addLayout(head)

        self._host = QWidget(self)
        self._host.setStyleSheet("background:#02080e;")
        self._host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        host_lay = QVBoxLayout(self._host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        self._fallback = QLabel("Loading live scanner…")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet("color:#5a7388; font-size:11px;")
        host_lay.addWidget(self._fallback)
        lay.addWidget(self._host, 1)

        self.status = QLabel(
            "Traffic cams have no mic — this is live public radio for your city."
        )
        self.status.setStyleSheet("color:#8aa4b8; font-size:10px;")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

    def _ensure_web(self) -> bool:
        if self._web is not None:
            return True
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._fallback.hide()
            self._web = QWebEngineView(self._host)
            s = self._web.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            try:
                s.setAttribute(
                    QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
                )
            except Exception:
                pass
            lay = self._host.layout()
            if lay is not None:
                lay.addWidget(self._web)
            return True
        except Exception as e:
            self._fallback.setText(
                f"WebEngine needed for in-HUD audio.\n{e}\n"
                "Browser tab should still have opened."
            )
            self._fallback.show()
            return False

    def open_panel(self, url: str, *, title: str | None = None) -> None:
        self._url = (url or "").strip() or self._url
        if title:
            self.title.setText(title)
        self.show()
        self.raise_()
        if self._ensure_web() and self._web is not None:
            self.status.setText("Loading live feeds — press Play on one…")
            self._web.load(QUrl(self._url))
            self.status.setText(
                "Live scanner · pick a feed and hit Play · listen only"
            )
        else:
            self.status.setText("Open the browser tab and press Play on a feed.")

    def close_panel(self) -> None:
        try:
            if self._web is not None:
                self._web.load(QUrl("about:blank"))
        except Exception:
            pass
        self.hide()
        self.closed.emit()

    def _close(self) -> None:
        self.close_panel()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = e.globalPosition().toPoint()
            self._drag_start = self.pos()
            self.raise_()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
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

    def mouseReleaseEvent(self, e) -> None:
        self._drag_origin = None
        self._drag_start = None
        super().mouseReleaseEvent(e)

"""Build Theater — live Google research browser + coding stream + app preview."""

from __future__ import annotations

import html as html_lib
import time
from typing import Any

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QSizePolicy,
    QPlainTextEdit,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QProgressBar,
)


def _esc(s: Any) -> str:
    return html_lib.escape(str(s or ""))


class BuildTheater(QFrame):
    """Full-HUD live board: Google search → code stream → runnable app preview."""

    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("BuildTheater")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            """
            QFrame#BuildTheater { background: #02080e; border: none; }
            QLabel#SectionTitle { color:#00f0ff; font-size:14px; letter-spacing:2px; font-weight:700; }
            QLabel#Dim { color:#7f9bb0; font-size:12px; }
            QLabel#StatVal { color:#00f0ff; font-size:18px; font-weight:700; }
            QLabel#StatKey { color:#7f9bb0; font-size:9px; letter-spacing:2px; }
            QPushButton#GhostBtn, QPushButton#TabBtn {
              background: transparent; color:#7f9bb0; border:1px solid rgba(0,240,255,60);
              padding:8px 14px; letter-spacing:2px;
            }
            QPushButton#TabBtn[active="true"] {
              color:#00f0ff; border-color:#00f0ff; background:rgba(0,240,255,28);
            }
            QListWidget, QPlainTextEdit {
              background:#071018; color:#d8ecf8; border:1px solid rgba(0,240,255,50);
              font-family: Consolas, monospace; font-size:12px;
            }
            QProgressBar {
              background:rgba(255,255,255,20); border:none; height:4px;
            }
            QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
              stop:0 #00f0ff, stop:1 #ffc14a); }
            """
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._mode = "site"
        self._title = "SESSION"
        self._tab = "working"
        self._status = "Standing by…"
        self._working: list[str] = []
        self._coding: list[str] = []
        self._building: list[str] = []
        self._files: list[str] = []
        self._code = ""
        self._pct = 5
        self._chars = 0
        self._words = 0
        self._clicks = 0
        self._images: list[dict] = []
        self._research: list[dict] = []
        self._prompts: list[str] = []
        self._preview_url = ""
        self._browser_url = ""
        self._active = False
        self._type_target = ""
        self._type_idx = 0

        self._live = None
        self._preview = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(6)

        head = QHBoxLayout()
        self.header = QLabel("BUILD THEATER")
        self.header.setObjectName("SectionTitle")
        self.sub = QLabel("Live agent workbench")
        self.sub.setObjectName("Dim")
        self.sub.setWordWrap(True)
        close = QPushButton("CLOSE")
        close.setObjectName("GhostBtn")
        close.clicked.connect(self._close)
        head.addWidget(self.header)
        head.addStretch(1)
        head.addWidget(close)
        root.addLayout(head)
        root.addWidget(self.sub)

        stats = QHBoxLayout()
        self._stat_chars = self._mk_stat("CHARS")
        self._stat_words = self._mk_stat("WORDS")
        self._stat_files = self._mk_stat("FILES")
        self._stat_clicks = self._mk_stat("CLICKS")
        for w in (
            self._stat_chars[0],
            self._stat_words[0],
            self._stat_files[0],
            self._stat_clicks[0],
        ):
            stats.addWidget(w)
        stats.addStretch(1)
        root.addLayout(stats)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        self.bar.setValue(5)
        root.addWidget(self.bar)

        tabs = QHBoxLayout()
        self._tab_btns: dict[str, QPushButton] = {}
        for key, label in (
            ("working", "WORKING · GOOGLE"),
            ("coding", "CODING"),
            ("building", "APP PREVIEW"),
        ):
            b = QPushButton(label)
            b.setObjectName("TabBtn")
            b.setProperty("active", "false")
            b.clicked.connect(lambda _=False, k=key: self._set_tab(k))
            self._tab_btns[key] = b
            tabs.addWidget(b)
        tabs.addStretch(1)
        root.addLayout(tabs)

        self.status = QLabel("LIVE · standing by")
        self.status.setObjectName("Dim")
        self.status.setStyleSheet("color:#9adfff; font-size:13px; padding:4px 2px;")
        root.addWidget(self.status)

        self.url_bar = QLabel("jarvis://theater")
        self.url_bar.setStyleSheet(
            "color:#7f9bb0; background:#071018; border:1px solid rgba(0,240,255,40);"
            " padding:6px 10px; font-family:Consolas,monospace; font-size:11px;"
        )
        root.addWidget(self.url_bar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # ── Working: live Google browser + research side ──
        work = QWidget()
        work_l = QHBoxLayout(work)
        work_l.setContentsMargins(0, 0, 0, 0)
        work_l.setSpacing(8)
        self._live_host = QWidget()
        live_lay = QVBoxLayout(self._live_host)
        live_lay.setContentsMargins(0, 0, 0, 0)
        self._live_fallback = QLabel("Live Google browser loading…")
        self._live_fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._live_fallback.setStyleSheet("color:#8aa4b8; background:#040c14;")
        live_lay.addWidget(self._live_fallback)
        work_l.addWidget(self._live_host, 3)

        side = QWidget()
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.addWidget(self._section("SEARCH LOG"))
        self.work_log = QListWidget()
        side_l.addWidget(self.work_log, 1)
        side_l.addWidget(self._section("PROMPTS FOUND"))
        self.prompt_list = QListWidget()
        side_l.addWidget(self.prompt_list, 1)
        work_l.addWidget(side, 1)
        self.stack.addWidget(work)  # 0

        # ── Coding: files + typewriter ──
        code_w = QWidget()
        code_l = QHBoxLayout(code_w)
        code_l.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        left.addWidget(self._section("FILES"))
        self.file_list = QListWidget()
        left.addWidget(self.file_list, 1)
        code_l.addLayout(left, 1)
        right = QVBoxLayout()
        right.addWidget(self._section("LIVE CODE STREAM"))
        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setFont(QFont("Consolas", 11))
        right.addWidget(self.code_view, 1)
        code_l.addLayout(right, 2)
        self.stack.addWidget(code_w)  # 1

        # ── Building: app preview ──
        build = QWidget()
        build_l = QVBoxLayout(build)
        build_l.setContentsMargins(0, 0, 0, 0)
        build_l.addWidget(self._section("RUNNABLE APP PREVIEW · SANDBOX"))
        self._preview_host = QWidget()
        prev_lay = QVBoxLayout(self._preview_host)
        prev_lay.setContentsMargins(0, 0, 0, 0)
        self._preview_fallback = QLabel("App preview appears after files are written…")
        self._preview_fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_fallback.setStyleSheet("color:#8aa4b8; background:#040c14;")
        prev_lay.addWidget(self._preview_fallback)
        build_l.addWidget(self._preview_host, 1)
        self.build_log = QListWidget()
        self.build_log.setMaximumHeight(120)
        build_l.addWidget(self.build_log)
        self.stack.addWidget(build)  # 2

        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._live = QWebEngineView(self._live_host)
            s1 = self._live.settings()
            s1.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s1.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            self._live_fallback.hide()
            live_lay.addWidget(self._live, 1)

            self._preview = QWebEngineView(self._preview_host)
            s2 = self._preview.settings()
            s2.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s2.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            s2.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
            )
            self._preview_fallback.hide()
            prev_lay.addWidget(self._preview, 1)
        except Exception as e:
            self._live_fallback.setText(f"WebEngine unavailable — {e}")
            self._preview_fallback.setText(f"WebEngine unavailable — {e}")

        self._type_timer = QTimer(self)
        self._type_timer.setInterval(16)
        self._type_timer.timeout.connect(self._tick_typewriter)
        self.hide()

    def _mk_stat(self, key: str) -> tuple[QWidget, QLabel]:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 4, 8, 4)
        l.setSpacing(0)
        val = QLabel("0")
        val.setObjectName("StatVal")
        lab = QLabel(key)
        lab.setObjectName("StatKey")
        l.addWidget(val)
        l.addWidget(lab)
        w.setStyleSheet(
            "background:rgba(0,240,255,18); border:1px solid rgba(0,240,255,40);"
        )
        return w, val

    def _section(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(
            "color:#00f0ff; font-size:10px; letter-spacing:2px; padding:4px 0;"
        )
        return lab

    def show_session(self, *, mode: str = "site", hint: str = "") -> None:
        self._active = True
        self._mode = "vibe" if "vibe" in (mode or "").lower() else "site"
        self._title = (hint or ("Vibe app" if self._mode == "vibe" else "Site build"))[:60]
        self._tab = "working"
        self._status = "Opening live Google research…"
        self._working = [f"Session open: {self._title}"]
        self._coding = []
        self._building = []
        self._files = []
        self._code = ""
        self._pct = 8
        self._chars = 0
        self._words = 0
        self._clicks = 0
        self._images = []
        self._research = []
        self._prompts = []
        self._preview_url = ""
        self._browser_url = ""
        self._type_target = ""
        self._type_idx = 0
        self.header.setText(f"BUILD THEATER · {self._mode.upper()}")
        self.sub.setText(self._title)
        self.work_log.clear()
        self.prompt_list.clear()
        self.file_list.clear()
        self.build_log.clear()
        self.code_view.setPlainText("// waiting for code stream…")
        self._refresh_stats()
        self._set_tab("working")
        self._fill_parent()
        # Warm Google so the first search feels instant
        if self._live is not None:
            self._live.load(QUrl("https://www.google.com/"))
            self.url_bar.setText("https://www.google.com/")
        self.show()
        self.raise_()
        self.activateWindow()
        if not self._type_timer.isActive():
            self._type_timer.start()

    def apply_progress(self, payload: Any) -> None:
        if isinstance(payload, str):
            payload = {"msg": payload}
        if not isinstance(payload, dict):
            return
        msg = str(payload.get("msg") or payload.get("log") or "").strip()
        stage = str(payload.get("agent_stage") or payload.get("stage") or "").lower()
        tab = str(payload.get("tab") or "").lower()

        if not tab:
            if stage in ("plan", "invent", "prompt", "copy", "working", "research"):
                tab = "working"
            elif stage in ("code", "terminal", "coding", "file"):
                tab = "coding"
            elif stage in ("browser", "iterate", "ship", "live", "build", "building", "hitl", "preview"):
                tab = "building"
            else:
                tab = self._tab or "working"

        if tab in ("working", "coding", "building"):
            self._set_tab(tab)

        if msg:
            self._status = msg
            self.status.setText(f"LIVE · {msg}")
            bucket = {
                "working": self._working,
                "coding": self._coding,
                "building": self._building,
            }[self._tab]
            if not bucket or bucket[-1] != msg:
                bucket.append(msg)
                del bucket[:-40]
            self._sync_logs()

        # Live Google / browser navigation
        browser_url = str(payload.get("browser_url") or payload.get("url") or "").strip()
        if browser_url.startswith("http"):
            self._navigate_live(browser_url)
            self._clicks += 1

        if payload.get("prompts"):
            pr = payload["prompts"]
            if isinstance(pr, list):
                self._prompts = [str(x) for x in pr][:12]
                self.prompt_list.clear()
                for p in self._prompts:
                    self.prompt_list.addItem(QListWidgetItem(p[:160]))

        if payload.get("research"):
            res = payload["research"]
            if isinstance(res, list):
                self._research = [x for x in res if isinstance(x, dict)][:12]

        if payload.get("images"):
            imgs = payload["images"]
            if isinstance(imgs, list):
                self._images = [x for x in imgs if isinstance(x, dict)][:12]

        fpath = payload.get("file_path") or payload.get("file")
        if fpath:
            rel = str(fpath).replace("\\", "/")
            if rel not in self._files:
                self._files.append(rel)
                self.file_list.addItem(QListWidgetItem(rel))
            self._set_tab("coding")

        if payload.get("file_content") or payload.get("code"):
            self._type_target = str(payload.get("file_content") or payload.get("code"))[:9000]
            self._type_idx = min(self._type_idx, len(self._type_target))
            self._set_tab("coding")

        # App preview — prefer live server URL
        preview_url = str(payload.get("preview_url") or "").strip()
        if preview_url.startswith("http"):
            self._load_preview(preview_url)
            self._set_tab("building")
        elif payload.get("html"):
            html = str(payload.get("html") or "")
            if self._preview is not None and html:
                self._preview.setHtml(html, QUrl("https://jarvis.local/preview/"))
                self.url_bar.setText("jarvis://sandbox/preview")
                self._set_tab("building")

        if payload.get("chars") is not None:
            try:
                self._chars = int(payload["chars"])
            except Exception:
                pass
        if payload.get("words") is not None:
            try:
                self._words = int(payload["words"])
            except Exception:
                pass

        self._pct = min(
            95,
            8 + len(self._files) * 7 + len(self._working) * 2 + min(25, self._chars // 60),
        )
        if stage in ("ship", "live") or "complete" in msg.lower() or "preview ready" in msg.lower():
            if "complete" in msg.lower():
                self._pct = 100
        self.bar.setValue(self._pct)
        self._refresh_stats()

    def show_done(self, *, path: str = "", name: str = "") -> None:
        self._set_tab("building")
        self._pct = 100
        self.bar.setValue(100)
        label = name or path or "project"
        self._status = f"Complete — {label}"
        self.status.setText(f"LIVE · {self._status}")
        self._building.append(self._status)
        self._sync_logs()
        if path and not self._preview_url:
            # file URI fallback for preview.html
            from pathlib import Path

            p = Path(path)
            cand = p / "preview.html" if p.is_dir() else p
            if cand.exists() and self._preview is not None:
                self._preview.load(QUrl.fromLocalFile(str(cand.resolve())))

    def _navigate_live(self, url: str) -> None:
        self._browser_url = url
        self.url_bar.setText(url)
        self.status.setText(f"LIVE · browsing {url[:90]}")
        if self._live is not None:
            self._live.load(QUrl(url))
        self._set_tab("working")

    def _load_preview(self, url: str) -> None:
        self._preview_url = url
        self.url_bar.setText(url)
        if self._preview is not None:
            self._preview.load(QUrl(url))
        self._preview_fallback.setText(f"Preview: {url}")

    def _set_tab(self, tab: str) -> None:
        self._tab = tab
        idx = {"working": 0, "coding": 1, "building": 2}.get(tab, 0)
        self.stack.setCurrentIndex(idx)
        for k, b in self._tab_btns.items():
            b.setProperty("active", "true" if k == tab else "false")
            b.style().unpolish(b)
            b.style().polish(b)

    def _tick_typewriter(self) -> None:
        if not self._active or not self._type_target:
            return
        if self._type_idx >= len(self._type_target):
            return
        step = max(2, len(self._type_target) // 200)
        self._type_idx = min(len(self._type_target), self._type_idx + step)
        chunk = self._type_target[: self._type_idx]
        self.code_view.setPlainText(chunk)
        self.code_view.verticalScrollBar().setValue(
            self.code_view.verticalScrollBar().maximum()
        )
        self._chars = self._type_idx
        self._words = len(chunk.split()) if chunk.strip() else 0
        self._refresh_stats()

    def _sync_logs(self) -> None:
        def fill(widget: QListWidget, lines: list[str]) -> None:
            widget.clear()
            for line in lines[-30:]:
                widget.addItem(QListWidgetItem(line[:180]))
            if widget.count():
                widget.scrollToBottom()

        fill(self.work_log, self._working)
        fill(self.build_log, self._building)

    def _refresh_stats(self) -> None:
        self._stat_chars[1].setText(str(self._chars))
        self._stat_words[1].setText(str(self._words))
        self._stat_files[1].setText(str(len(self._files)))
        self._stat_clicks[1].setText(str(self._clicks))

    def _fill_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self.raise_()

    def _place(self) -> None:
        self._fill_parent()

    def _close(self) -> None:
        self._active = False
        self._type_timer.stop()
        self.hide()
        self.closed.emit()

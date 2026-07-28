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
            QPushButton#GhostBtn {
              background: transparent; color:#7f9bb0; border:1px solid rgba(0,240,255,60);
              padding:8px 14px; letter-spacing:2px;
            }
            QPushButton#TabBtn {
              background: rgba(7,16,24,220); color:#8aa4b8;
              border:1px solid rgba(0,240,255,70);
              padding:10px 18px; letter-spacing:2px; font-weight:700; min-height:34px;
            }
            QPushButton#TabBtn:hover { color:#00f0ff; border-color:#00f0ff; }
            QPushButton#TabBtn[active="true"], QPushButton#TabBtn:checked {
              color:#02080e; border-color:#00f0ff;
              background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #00f0ff, stop:1 #7cf0ff);
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
        self._key_target = ""
        self._key_idx = 0
        self._mouse_nx = 0.5
        self._mouse_ny = 0.42
        self._research_lock = False
        self._last_nav_url = ""
        self._last_nav_at = 0.0

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
        tabs.setSpacing(8)
        self._tab_btns: dict[str, QPushButton] = {}
        for key, label in (
            ("working", "1 · WORKING"),
            ("coding", "2 · CODING"),
            ("building", "3 · PREVIEW"),
        ):
            b = QPushButton(label)
            b.setObjectName("TabBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("active", "false")
            b.clicked.connect(lambda _checked=False, k=key: self._set_tab(k, force=True))
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

        self.key_strip = QLabel("KEYBOARD · idle — watch Jarvis type into Google")
        self.key_strip.setStyleSheet(
            "color:#00f0ff; background:#040c14; border:1px solid rgba(0,240,255,70);"
            " padding:8px 12px; font-family:Consolas,monospace; font-size:13px;"
        )
        root.addWidget(self.key_strip)

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
        self._key_timer = QTimer(self)
        self._key_timer.setInterval(55)
        self._key_timer.timeout.connect(self._tick_keyboard)
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
        self._key_target = ""
        self._key_idx = 0
        self._research_lock = True
        self._last_nav_url = ""
        self._last_nav_at = 0.0
        self.key_strip.setText("KEYBOARD · ready — click search bar, then type slowly")
        self.header.setText(f"BUILD THEATER · {self._mode.upper()}")
        self.sub.setText(self._title)
        self.work_log.clear()
        self.prompt_list.clear()
        self.file_list.clear()
        self.build_log.clear()
        self.code_view.setPlainText("// waiting for code stream…")
        self._refresh_stats()
        self._fill_parent()
        # Warm Google home (empty search bar — typing comes next)
        if self._live is not None:
            self._live.load(QUrl("https://www.google.com/"))
            self.url_bar.setText("https://www.google.com/")
            self._last_nav_url = "https://www.google.com/"
        self.show()
        self.raise_()
        self.activateWindow()
        self._set_tab("working", force=True)
        if not self._type_timer.isActive():
            self._type_timer.start()
        if not self._key_timer.isActive():
            self._key_timer.start()

    def ensure_open(self) -> None:
        """Show theater without wiping an in-progress session."""
        self._active = True
        self._fill_parent()
        self.show()
        self.raise_()
        if not self._type_timer.isActive():
            self._type_timer.start()
        if not self._key_timer.isActive():
            self._key_timer.start()

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
            elif stage in (
                "browser",
                "iterate",
                "ship",
                "live",
                "build",
                "building",
                "hitl",
                "preview",
            ):
                tab = "building"
            else:
                tab = self._tab or "working"

        # Coding / preview always win — never yank back to Google mid-build
        if stage in ("preview", "ship", "live", "building") or tab == "building":
            self._research_lock = False
            tab = "building"
        elif payload.get("preview_url") or payload.get("html"):
            self._research_lock = False
            tab = "building"
        elif (
            stage in ("code", "coding", "file", "terminal")
            or tab == "coding"
            or payload.get("file_path")
            or payload.get("file")
            or payload.get("file_content")
            or payload.get("code")
        ):
            self._research_lock = False
            tab = "coding"
        else:
            # Research inputs only lock WORKING during research stages
            research_event = (
                stage in ("research", "plan", "invent")
                or payload.get("keyboard") is not None
                or payload.get("mouse") is not None
                or payload.get("mouse_x") is not None
                or (
                    str(payload.get("browser_url") or "").startswith("http")
                    and stage in ("research", "plan", "invent", "")
                    and tab in ("", "working")
                )
            )
            if research_event:
                self._research_lock = True
                tab = "working"

        if msg:
            self._status = msg
            self.status.setText(f"LIVE · {msg}")
            bucket = {
                "working": self._working,
                "coding": self._coding,
                "building": self._building,
            }.get(tab, self._working)
            if not bucket or bucket[-1] != msg:
                bucket.append(msg)
                del bucket[:-40]
            self._sync_logs()

        # Slow keyboard into Google search bar (theater + page inject)
        kb = payload.get("keyboard")
        if kb is not None and (self._research_lock or stage in ("research", "plan", "invent")):
            text = str(kb)
            if payload.get("keyboard_reset") or text != self._key_target:
                self._key_target = text
                self._key_idx = 0 if payload.get("keyboard_reset") else min(
                    self._key_idx, len(text)
                )
                if payload.get("keyboard_reset"):
                    self._key_idx = 0
            self.key_strip.setText("KEYBOARD · " + (text[: max(1, self._key_idx)] or "▌"))
            self._inject_google_query(text, submit=bool(payload.get("google_submit")))

        if (payload.get("mouse") or payload.get("mouse_x") is not None) and (
            self._research_lock or stage in ("research", "plan", "invent")
        ):
            try:
                self._mouse_nx = float(payload.get("mouse_x") or self._mouse_nx)
                self._mouse_ny = float(payload.get("mouse_y") or self._mouse_ny)
            except Exception:
                pass
            click = bool(
                payload.get("mouse_click")
                or str(payload.get("mouse") or "").lower()
                in ("click", "submit", "focus-search")
            )
            self.key_strip.setText(
                f"MOUSE · {payload.get('mouse') or 'move'} "
                f"{self._mouse_nx:.2f},{self._mouse_ny:.2f}"
            )
            self._clicks += 1
            self._inject_google_mouse(self._mouse_nx, self._mouse_ny, click=click)
            self._refresh_stats()

        # Live Google / browser navigation (debounced — smoother)
        browser_url = str(payload.get("browser_url") or "").strip()
        if browser_url.startswith("http") and (
            self._research_lock or stage in ("research", "plan", "invent") or tab == "working"
        ):
            skip_nav = (
                self._key_target
                and "search?q=" in browser_url
                and self._key_idx < max(1, len(self._key_target) - 1)
                and not payload.get("google_submit")
            )
            if not skip_nav:
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

        if payload.get("file_content") or payload.get("code"):
            content = str(payload.get("file_content") or payload.get("code"))[:9000]
            if content != self._type_target:
                self._type_target = content
                self._type_idx = 0

        # App preview — prefer live server URL
        preview_url = str(payload.get("preview_url") or "").strip()
        if preview_url.startswith("http"):
            self._load_preview(preview_url)
            tab = "building"
        elif payload.get("html") and not self._preview_url:
            html = str(payload.get("html") or "")
            if self._preview is not None and html:
                self._preview.setHtml(html, QUrl("https://jarvis.local/preview/"))
                self.url_bar.setText("jarvis://sandbox/preview")
                tab = "building"

        # Switch tab last so nothing overrides it
        if tab in ("working", "coding", "building"):
            self._set_tab(tab, force=True)

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
            if "complete" in msg.lower() or "preview ready" in msg.lower():
                self._pct = 100
        self.bar.setValue(self._pct)
        self._refresh_stats()

    def show_done(self, *, path: str = "", name: str = "", preview_url: str = "") -> None:
        self._research_lock = False
        self._pct = 100
        self.bar.setValue(100)
        label = name or path or "project"
        self._status = f"Complete — {label}"
        self.status.setText(f"LIVE · {self._status}")
        self._building.append(self._status)
        self._sync_logs()
        # Prefer live http preview, then path/index.html
        url = (preview_url or self._preview_url or "").strip()
        if url.startswith("http"):
            self._load_preview(url)
        elif path:
            from pathlib import Path

            p = Path(path)
            if path.startswith(("http://", "https://")):
                self._load_preview(path)
            else:
                for name_html in ("index.html", "preview.html"):
                    cand = p / name_html if p.is_dir() else p
                    if cand.exists():
                        if self._preview is not None:
                            self._preview.show()
                            self._preview.load(QUrl.fromLocalFile(str(cand.resolve())))
                            self.url_bar.setText(cand.resolve().as_uri())
                            self._preview_fallback.hide()
                        else:
                            self._preview_fallback.setText(f"Open: {cand}")
                            self._preview_fallback.show()
                        break
        self._set_tab("building", force=True)
        self.ensure_open()

    def _navigate_live(self, url: str) -> None:
        now = time.time()
        # Skip duplicate reloads — keeps Google from flashing / resetting the bar
        if url == self._last_nav_url and (now - self._last_nav_at) < 1.2:
            self.url_bar.setText(url)
            return
        self._browser_url = url
        self._last_nav_url = url
        self._last_nav_at = now
        self.url_bar.setText(url)
        self.status.setText(f"LIVE · browsing {url[:90]}")
        if self._live is not None:
            self._live.load(QUrl(url))

    def _inject_google_query(self, text: str, *, submit: bool = False) -> None:
        """Focus Google search box and type (visible keystrokes)."""
        if self._live is None:
            return
        safe = (
            str(text)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", " ")
            .replace("\r", "")
        )
        sub = "true" if submit else "false"
        js = f"""
        (function() {{
          var q = '{safe}';
          var submit = {sub};
          var inp = document.querySelector(
            "textarea[name=q], input[name=q], form[role=search] textarea, form[action*='search'] input[type=text]"
          );
          if (!inp) {{
            var all = document.querySelectorAll("textarea, input[type=text], input[type=search]");
            if (all && all.length) inp = all[0];
          }}
          if (!inp) return "no-input";
          inp.focus();
          inp.click && inp.click();
          inp.value = q;
          try {{
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
          }} catch (e) {{}}
          if (submit) {{
            var form = inp.form || document.querySelector("form[action*='search'], form");
            if (form) {{ try {{ form.submit(); return "submit"; }} catch (e) {{}} }}
            location.href = "/search?q=" + encodeURIComponent(q) + "&hl=en";
            return "nav";
          }}
          return "typed";
        }})();
        """
        try:
            self._live.page().runJavaScript(js)
        except Exception:
            pass

    def _inject_google_mouse(self, nx: float, ny: float, *, click: bool = False) -> None:
        """Draw a fake cursor overlay on the live page and optionally click."""
        if self._live is None:
            return
        js = f"""
        (function() {{
          var nx = {float(nx):.4f}, ny = {float(ny):.4f}, click = {str(click).lower()};
          var c = document.getElementById('jarvis-cursor');
          if (!c) {{
            c = document.createElement('div');
            c.id = 'jarvis-cursor';
            c.style.cssText = 'position:fixed;z-index:999999;width:18px;height:18px;'
              + 'border-radius:50%;background:#00e8ff;border:2px solid #fff;'
              + 'box-shadow:0 0 14px #00e8ff;pointer-events:none;'
              + 'transition:left .45s ease, top .45s ease;';
            document.body.appendChild(c);
          }}
          c.style.left = (nx * 100) + 'vw';
          c.style.top = (ny * 100) + 'vh';
          if (click) {{
            c.style.transform = 'scale(0.7)';
            setTimeout(function(){{ c.style.transform = 'scale(1)'; }}, 180);
            var el = document.elementFromPoint(nx * innerWidth, ny * innerHeight);
            if (el) {{ try {{ el.click(); }} catch (e) {{}} }}
          }}
          return 'ok';
        }})();
        """
        try:
            self._live.page().runJavaScript(js)
        except Exception:
            pass

    def _load_preview(self, url: str) -> None:
        self._preview_url = url
        self.url_bar.setText(url)
        if self._preview is not None:
            try:
                self._preview.show()
                self._preview_host.show()
                self._preview_fallback.hide()
                self._preview.load(QUrl(url))
            except Exception as e:
                self._preview_fallback.setText(f"Preview failed: {e}\n{url}")
                self._preview_fallback.show()
        else:
            self._preview_fallback.setText(f"Preview: {url}")
            self._preview_fallback.show()

    def _set_tab(self, tab: str, force: bool = False) -> None:
        want = tab if tab in ("working", "coding", "building") else "working"
        if not force and want == self._tab and self.stack.currentIndex() == {
            "working": 0, "coding": 1, "building": 2
        }.get(want, 0):
            return
        self._tab = want
        # Manual / forced switches leave research — don't yank back to WORKING
        if want in ("coding", "building"):
            self._research_lock = False
        idx = {"working": 0, "coding": 1, "building": 2}.get(self._tab, 0)
        self.stack.setCurrentIndex(idx)
        self.stack.show()
        # CRITICAL: hide inactive pages. QWebEngineView uses native windows that
        # stay painted on top of siblings if the page is only "stacked" not hidden.
        for i in range(self.stack.count()):
            w = self.stack.widget(i)
            if w is None:
                continue
            if i == idx:
                w.setVisible(True)
                w.show()
                w.raise_()
            else:
                w.hide()
                w.setVisible(False)
        # Explicitly park the two webviews so only the active tab's is visible
        try:
            if self._live is not None:
                if self._tab == "working":
                    self._live_host.show()
                    self._live.setVisible(True)
                    self._live.show()
                    self._live.raise_()
                    self._live.resize(self._live_host.size())
                else:
                    self._live.hide()
                    self._live.setVisible(False)
            if self._preview is not None:
                if self._tab == "building":
                    self._preview_host.show()
                    self._preview.setVisible(True)
                    self._preview.show()
                    self._preview.raise_()
                    self._preview.resize(self._preview_host.size())
                    # Reload if we already have a URL (webview may have been blank while hidden)
                    if self._preview_url.startswith("http"):
                        try:
                            cur = self._preview.url().toString()
                        except Exception:
                            cur = ""
                        if cur.rstrip("/") != self._preview_url.rstrip("/"):
                            self._preview.load(QUrl(self._preview_url))
                            self.url_bar.setText(self._preview_url)
                else:
                    self._preview.hide()
                    self._preview.setVisible(False)
        except Exception:
            pass
        page = self.stack.currentWidget()
        if page is not None:
            page.setVisible(True)
            page.show()
            page.raise_()
            page.update()
        for k, b in self._tab_btns.items():
            on = k == self._tab
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
            b.setProperty("active", "true" if on else "false")
            b.style().unpolish(b)
            b.style().polish(b)
            b.update()
        labels = {
            "working": "WORKING · Google research",
            "coding": "CODING · writing files",
            "building": "PREVIEW · runnable app",
        }
        if self._status and not str(self._status).startswith("Complete"):
            self.status.setText(f"LIVE · {self._status}")
        else:
            self.status.setText(f"LIVE · {labels.get(self._tab, self._tab)}")
        self.raise_()
        self._fill_parent()

    def _tick_keyboard(self) -> None:
        if not self._active or not self._key_target:
            return
        if self._key_idx >= len(self._key_target):
            return
        self._key_idx = min(len(self._key_target), self._key_idx + 1)
        typed = self._key_target[: self._key_idx]
        self.key_strip.setText(f"KEYBOARD · {typed}▌")
        self._chars = max(self._chars, self._key_idx)
        self._words = len(typed.split()) if typed.strip() else self._words
        self._refresh_stats()
        # Push partial text into Google as it types
        self._inject_google_query(typed, submit=False)

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
        try:
            self._key_timer.stop()
        except Exception:
            pass
        self.hide()
        self.closed.emit()

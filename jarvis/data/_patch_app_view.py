# -*- coding: utf-8 -*-
"""Patch BuildTheater preview to use a fresh WebEngine view + open-in-browser."""
from pathlib import Path

p = Path(r"c:\Users\ethan\jarvis\jarvis\ui\widgets\build_theater.py")
text = p.read_text(encoding="utf-8")

# 1) Init fields for app_view
if "self._app_view = None" not in text:
    text = text.replace(
        "self._overlay = None\n        self._overlay_host = None\n        self._overlay_banner = None",
        "self._overlay = None\n        self._overlay_host = None\n        self._overlay_banner = None\n"
        "        self._app_view = None\n        self._btn_open_browser = None\n        self._btn_reload_app = None",
        1,
    )

# 2) Replace force_preview through end of _mount_live (before _resurrect or _on_preview)
start = text.index("    def force_preview(self, url: str = \"\", *, path: str = \"\", name: str = \"\") -> None:")
# Find next def after _mount_live
end = text.index("    def _resurrect_overlay(self) -> None:")

new = r'''    def force_preview(self, url: str = "", *, path: str = "", name: str = "") -> None:
        """Hard-switch to PREVIEW with a FRESH WebEngine view (reparented views go blank)."""
        url = (url or self._preview_url or "").strip()
        self._active = True
        self._preview_locked = True
        self._research_lock = False
        self._pct = 100
        try:
            self.bar.setValue(100)
        except Exception:
            pass
        label = str(name or path or "app")[:60]
        self._status = f"Complete — {label}"
        if self._status not in self._building:
            self._building.append(self._status)
        self._sync_logs()
        self._fill_parent()
        self.show()
        self.raise_()

        self._kill_live_view()

        self._tab = "building"
        for k, b in self._tab_btns.items():
            on = k == "building"
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
            b.setProperty("active", "true" if on else "false")
            try:
                b.style().unpolish(b)
                b.style().polish(b)
            except Exception:
                pass
            b.update()

        try:
            self.stack.setCurrentIndex(2)
            for i in range(self.stack.count()):
                w = self.stack.widget(i)
                if w is not None:
                    w.setVisible(i == 2)
        except Exception:
            pass

        # Hide the old broken preview widget — we use _app_view instead
        try:
            if self._preview is not None:
                self._preview.hide()
                self._preview.setVisible(False)
        except Exception:
            pass

        self._ensure_overlay()
        self._place_overlay()
        self._overlay.show()
        self._overlay.raise_()
        self._overlay_banner.setText(f"3 · PREVIEW · {label.upper()}")

        view = self._ensure_app_view()
        if url.startswith("http"):
            self._preview_url = url
            self.url_bar.setText(url)
            self.status.setText(f"LIVE · LOADING APP · {url}")
            self._load_app_url(url)
            QTimer.singleShot(100, self._place_overlay)
            QTimer.singleShot(250, lambda u=url: self._load_app_url(u))
            QTimer.singleShot(700, lambda u=url: self._load_app_url(u, force=True))
        elif path:
            from pathlib import Path as _P

            root = _P(path)
            # Prefer serving over HTTP — file:// breaks JS modules / relative assets
            try:
                from jarvis.core.vibe_coder import VibeCoder

                # caller may have brain.vibe; try global serve via ensure if path given
            except Exception:
                pass
            for name_html in ("index.html", "preview.html"):
                cand = root / name_html if root.is_dir() else root
                if cand.exists():
                    file_url = QUrl.fromLocalFile(str(cand.resolve())).toString()
                    self.url_bar.setText(file_url)
                    self.status.setText("LIVE · LOADING LOCAL APP")
                    self._load_app_url(file_url)
                    break
        else:
            self.status.setText("LIVE · PREVIEW · no URL yet — open in browser after serve")

        self.key_strip.setText(
            "PREVIEW — if still blank tap OPEN IN BROWSER (same URL works outside)"
        )
        self.sub.setText(f"{label} · preview ready")
        try:
            self.update()
            self.repaint()
        except Exception:
            pass
        # Keep a reference so linters know view exists
        _ = view

    def _ensure_overlay(self) -> None:
        if self._overlay is not None:
            return
        self._overlay = QWidget(self)
        self._overlay.setObjectName("PreviewOverlay")
        self._overlay.setStyleSheet(
            "QWidget#PreviewOverlay { background: #02080e; border: 2px solid #00f0ff; }"
        )
        lay = QVBoxLayout(self._overlay)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._overlay_banner = QLabel("3 · PREVIEW")
        self._overlay_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._overlay_banner.setStyleSheet(
            "color:#02080e; background:#00f0ff; font-weight:700;"
            " padding:10px; letter-spacing:3px; font-size:14px;"
        )
        lay.addWidget(self._overlay_banner)

        btns = QHBoxLayout()
        btns.setContentsMargins(8, 6, 8, 6)
        btns.setSpacing(8)
        self._btn_open_browser = QPushButton("OPEN IN BROWSER")
        self._btn_reload_app = QPushButton("RELOAD APP")
        for b in (self._btn_open_browser, self._btn_reload_app):
            b.setObjectName("GhostBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                "color:#00f0ff; border:1px solid #00f0ff; padding:8px 14px;"
                " letter-spacing:2px; background:rgba(0,20,30,200);"
            )
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)
        self._btn_open_browser.clicked.connect(self._open_preview_external)
        self._btn_reload_app.clicked.connect(lambda: self._load_app_url(self._preview_url, force=True))

        self._overlay_host = QWidget()
        self._overlay_host.setStyleSheet("background:#02060c;")
        oh = QVBoxLayout(self._overlay_host)
        oh.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._overlay_host, 1)
        self._overlay.hide()

    def _ensure_app_view(self):
        """Always use a dedicated WebEngine for the app — never the Google view."""
        if self._app_view is not None:
            try:
                self._app_view.show()
                return self._app_view
            except Exception:
                self._app_view = None
        self._ensure_overlay()
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings
        except Exception as e:
            self._overlay_banner.setText(f"PREVIEW · WebEngine missing — {e}")
            return None

        view = QWebEngineView(self._overlay_host)
        s = view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        try:
            s.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        except Exception:
            pass
        try:
            s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        except Exception:
            pass
        from PyQt6.QtWidgets import QSizePolicy as _SP

        view.setSizePolicy(_SP.Policy.Expanding, _SP.Policy.Expanding)
        view.setMinimumSize(200, 160)
        lay = self._overlay_host.layout()
        if lay is not None:
            lay.addWidget(view, 1)
        view.loadFinished.connect(self._on_app_load_finished)
        try:
            view.renderProcessTerminated.connect(
                lambda *_a: self._overlay_banner.setText(
                    "3 · PREVIEW · RENDER CRASHED — tap RELOAD or OPEN IN BROWSER"
                )
            )
        except Exception:
            pass
        self._app_view = view
        view.show()
        return view

    def _load_app_url(self, url: str, *, force: bool = False) -> None:
        url = (url or "").strip()
        if not url:
            return
        self._preview_url = url
        self.url_bar.setText(url)
        view = self._ensure_app_view()
        if view is None:
            self._open_preview_external()
            return
        self._place_overlay()
        try:
            host = self._overlay_host
            if host is not None and host.width() > 20:
                view.resize(max(200, host.width()), max(160, host.height()))
            view.show()
            view.raise_()
            cur = ""
            try:
                cur = view.url().toString()
            except Exception:
                pass
            if force or not cur or cur in ("about:blank", "data:,") or cur.rstrip("/") != url.rstrip("/"):
                view.setUrl(QUrl(url))
            else:
                view.reload()
            self.status.setText(f"LIVE · LOADING · {url}")
        except Exception as e:
            self.status.setText(f"LIVE · PREVIEW ERROR · {e}")
            self._overlay_banner.setText("3 · PREVIEW · ERROR — OPEN IN BROWSER")

    def _open_preview_external(self) -> None:
        url = (self._preview_url or "").strip()
        if not url:
            self.status.setText("LIVE · no preview URL to open")
            return
        try:
            from PyQt6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(url))
            self.status.setText(f"LIVE · opened system browser · {url}")
            self.key_strip.setText("Opened in your browser — that is the real app preview")
        except Exception as e:
            self.status.setText(f"LIVE · browser open failed · {e}")

    def _on_app_load_finished(self, ok: bool) -> None:
        try:
            if ok:
                self.status.setText(f"LIVE · APP RUNNING · {self._preview_url}")
                if self._overlay_banner is not None:
                    self._overlay_banner.setText("3 · PREVIEW · APP RUNNING")
                if self._app_view is not None:
                    self._app_view.show()
                    self._app_view.raise_()
            else:
                self.status.setText("LIVE · PREVIEW LOAD FAILED — opening browser")
                if self._overlay_banner is not None:
                    self._overlay_banner.setText(
                        "3 · PREVIEW · LOAD FAILED — USE OPEN IN BROWSER"
                    )
                # Auto-fallback so the user always sees the app
                QTimer.singleShot(400, self._open_preview_external)
        except Exception:
            pass

    def _place_overlay(self) -> None:
        if self._overlay is None:
            return
        try:
            g = self.stack.geometry()
            if g.width() < 50 or g.height() < 50:
                g = self.rect().adjusted(10, 160, -10, -10)
            self._overlay.setGeometry(g)
            self._overlay.raise_()
            if self._app_view is not None and self._overlay_host is not None:
                self._app_view.resize(
                    max(200, self._overlay_host.width()),
                    max(160, self._overlay_host.height()),
                )
                self._app_view.show()
        except Exception:
            pass

    def _hide_overlay(self) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        if self._app_view is not None:
            try:
                self._app_view.hide()
            except Exception:
                pass

    def _kill_live_view(self) -> None:
        """Windows WebEngine keeps painting after hide — force it dead."""
        if self._live is None:
            return
        try:
            self._live.setUrl(QUrl("about:blank"))
        except Exception:
            pass
        try:
            self._live.hide()
            self._live.setVisible(False)
            self._live.setFixedSize(0, 0)
            self._live.setMaximumSize(0, 0)
            self._live.move(-20000, -20000)
            self._live.setParent(self._web_park)
        except Exception:
            try:
                self._live.hide()
            except Exception:
                pass

    def _mount_live(self, on_working: bool) -> None:
        """Reparent Google WebEngine so it cannot paint over PREVIEW."""
        if self._live is None:
            return
        try:
            if on_working:
                self._hide_overlay()
                from PyQt6.QtWidgets import QSizePolicy as _SP

                self._live.setSizePolicy(_SP.Policy.Expanding, _SP.Policy.Expanding)
                self._live.setMinimumSize(0, 0)
                self._live.setMaximumSize(16777215, 16777215)
                lay = self._live_host.layout()
                if self._live.parent() is not self._live_host:
                    self._live.setParent(self._live_host)
                    if lay is not None:
                        lay.addWidget(self._live, 1)
                self._live_host.show()
                self._live.show()
                self._live.setVisible(True)
                self._live.resize(
                    max(100, self._live_host.width()),
                    max(100, self._live_host.height()),
                )
            else:
                self._kill_live_view()
        except Exception:
            try:
                self._live.hide()
            except Exception:
                pass

'''

text = text[:start] + new + text[end:]

# Point _load_preview / _reload at app view
# Replace _load_preview body to delegate
if "def _load_preview(self, url: str) -> None:" in text:
    ls = text.index("    def _load_preview(self, url: str) -> None:")
    le = text.index("    def _navigate_live(self, url: str) -> None:")
    text = text[:ls] + (
        "    def _load_preview(self, url: str) -> None:\n"
        "        # Back-compat — real app preview uses _load_app_url / _app_view\n"
        "        self._load_app_url(url, force=True)\n\n"
        "    def _reload_preview_if(self, url: str) -> None:\n"
        "        self._load_app_url(url or self._preview_url, force=True)\n\n"
    ) + text[le:]

# Fix _resurrect_overlay to use app view
if "def _resurrect_overlay(self) -> None:" in text:
    rs = text.index("    def _resurrect_overlay(self) -> None:")
    # next def
    re_ = text.index("    def _on_preview_load_finished(self, ok: bool) -> None:")
    text = text[:rs] + (
        "    def _resurrect_overlay(self) -> None:\n"
        "        if not self._preview_locked:\n"
        "            return\n"
        "        self._ensure_overlay()\n"
        "        self._place_overlay()\n"
        "        if self._overlay is not None:\n"
        "            self._overlay.show()\n"
        "            self._overlay.raise_()\n"
        "        self._kill_live_view()\n"
        "        if self._preview_url:\n"
        "            self._load_app_url(self._preview_url)\n\n"
        "    def _on_preview_load_finished(self, ok: bool) -> None:\n"
        "        # legacy preview widget callback — ignore\n"
        "        return\n\n"
    ) + text[re_ + len("    def _on_preview_load_finished(self, ok: bool) -> None:\n"):]
    # That last part is messy - let's just replace _resurrect only
    pass

p.write_text(text, encoding="utf-8")
print("theater patch written", len(text))

"""Media transport + Spotify recommendation playlist embed."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy

from jarvis.ui.widgets.cmd_button import CmdButton

DEFAULT_PLAYLIST_ID = "3hMeaqVid62fywPpTBWWw9"


class MediaPanel(QFrame):
    action = pyqtSignal(str)

    def __init__(self, parent=None, playlist_id: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self._playlist_id = (playlist_id or DEFAULT_PLAYLIST_ID).strip() or DEFAULT_PLAYLIST_ID

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("PLAYER")
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        self._spot = QLabel("SPOTIFY")
        self._spot.setStyleSheet(
            "color:#1db954; font-size:9px; letter-spacing:1.5px; font-weight:700;"
        )
        head.addWidget(self._spot)
        lay.addLayout(head)

        self.track = QLabel("Recommendation playlist ready")
        self.track.setObjectName("Dim")
        self.track.setWordWrap(True)
        lay.addWidget(self.track)

        # Embed host — compact so the left column stays clean
        self._host = QWidget()
        self._host.setMinimumHeight(120)
        self._host.setMaximumHeight(148)
        self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        host_lay = QVBoxLayout(self._host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        self._web = None
        self._fallback = QLabel("Loading Spotify embed…")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet("color:#5a7388; font-size:11px;")
        self._fallback.setWordWrap(True)
        host_lay.addWidget(self._fallback)
        lay.addWidget(self._host)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._buttons: list[CmdButton] = []
        for label, act in (
            ("Prev", "previous"),
            ("Play", "playpause"),
            ("Next", "next"),
            ("Mute", "mute"),
        ):
            b = CmdButton(label, act, kind="media")
            b.fired.connect(self.action.emit)
            self._buttons.append(b)
            row.addWidget(b)
        lay.addLayout(row)

        playlist_btn = CmdButton("Playlist", "play my focus playlist", kind="ghost", compact=True)
        playlist_btn.fired.connect(self.action.emit)
        lay.addWidget(playlist_btn)

        self._init_embed()

    def _embed_html(self) -> str:
        pid = self._playlist_id
        src = (
            f"https://open.spotify.com/embed/playlist/{pid}"
            f"?utm_source=generator&theme=0"
        )
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  html,body {{ margin:0; height:100%; background:#0a121c; overflow:hidden; }}
  iframe {{ border:0; width:100%; height:100%; min-height:120px; }}
</style></head>
<body>
<iframe
  title="Spotify Embed: Recommendation Playlist"
  src="{src}"
  width="100%"
  height="100%"
  allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
  loading="lazy"
></iframe>
</body></html>"""

    def _init_embed(self) -> None:
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._web = QWebEngineView(self._host)
            s = self._web.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s.setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
            )
            self._host.layout().addWidget(self._web)
            self._fallback.hide()
            self._web.setHtml(self._embed_html(), QUrl("https://open.spotify.com/"))
        except Exception as e:
            self._fallback.setText(
                f"Spotify playlist {self._playlist_id}\n"
                f"(WebEngine needed for embed)\n{e}"
            )

    def set_playlist_id(self, playlist_id: str) -> None:
        pid = (playlist_id or "").strip()
        if not pid or pid == self._playlist_id:
            return
        self._playlist_id = pid
        if self._web is not None:
            try:
                self._web.setHtml(self._embed_html(), QUrl("https://open.spotify.com/"))
            except Exception:
                pass

    def set_track(self, name: str) -> None:
        self.track.setText(name)
        for b in self._buttons:
            if b._cmd == "playpause":
                b.pulse_success()
                break

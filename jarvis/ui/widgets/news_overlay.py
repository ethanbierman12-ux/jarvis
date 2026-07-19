"""ABC News overlay — WebEngine feed + gesture-draggable HUD panel."""

from __future__ import annotations

import re
import threading
import urllib.request
from xml.etree import ElementTree as ET

from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QWidget,
    QSizePolicy,
)

ABC_HOME = "https://abcnews.go.com/"
ABC_RSS = "https://abcnews.go.com/abcnews/topstories"


def fetch_abc_headlines(limit: int = 10) -> list[dict[str, str]]:
    """Pull ABC top stories from RSS (network)."""
    items: list[dict[str, str]] = []
    try:
        req = urllib.request.Request(
            ABC_RSS,
            headers={"User-Agent": "JarvisNews/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            desc = re.sub(r"<[^>]+>", "", desc)
            if title:
                items.append({"title": title, "link": link or ABC_HOME, "summary": desc[:220]})
    except Exception as e:
        print(f"[news] RSS failed: {e}")
    if not items:
        items = [
            {
                "title": "ABC News — live feed",
                "link": ABC_HOME,
                "summary": "Open the full site below. RSS was unavailable.",
            }
        ]
    return items


class NewsOverlay(QFrame):
    """Floating ABC News panel — pinch-drag with camera gestures."""

    closed = pyqtSignal()
    story_opened = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(2,10,18,245);"
            " border: 1px solid rgba(0,232,255,160); }"
            "QListWidget { background: rgba(0,12,22,220); color:#eaf6ff;"
            " border: 1px solid rgba(0,232,255,50); font-size:12px; }"
            "QListWidget::item:selected { background: rgba(0,200,255,60); }"
        )
        self.setFixedSize(520, 560)
        self._stories: list[dict[str, str]] = []
        self._web = None
        self._drag_armed = False
        self._gesture_hint = "Pinch + move to drag · swipe for next story"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("ABC NEWS · LIVE")
        title.setObjectName("SectionTitle")
        self.hint = QLabel(self._gesture_hint)
        self.hint.setObjectName("Dim")
        self.hint.setWordWrap(True)
        close = QPushButton("CLOSE")
        close.setObjectName("GhostBtn")
        close.setFixedHeight(28)
        close.clicked.connect(self._close)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(close)
        lay.addLayout(head)
        lay.addWidget(self.hint)

        self.status = QLabel("Loading ABC headlines…")
        self.status.setObjectName("Dim")
        lay.addWidget(self.status)

        self.list = QListWidget()
        self.list.setMaximumHeight(150)
        self.list.itemClicked.connect(self._on_pick)
        lay.addWidget(self.list)

        self._host = QWidget()
        self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._host, 1)

        self._fallback = QLabel("Loading ABC News…")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet("color:#8aa4b8; background:#02080e; padding:20px;")
        self._host_lay.addWidget(self._fallback)

        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._web = QWebEngineView(self._host)
            settings = self._web.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            self._host_lay.addWidget(self._web, 1)
            self._fallback.hide()
        except Exception as e:
            self._fallback.setText(f"WebEngine needed for ABC News.\n{e}")

        self.hide()

    def open_news(self, *, url: str = ABC_HOME) -> str:
        self.show()
        self.raise_()
        self._place_default()
        self.status.setText("Fetching ABC top stories…")
        self.list.clear()
        if self._web is not None:
            self._web.load(QUrl(url))
        else:
            try:
                from jarvis.core.displays import displays

                displays.open_url_on(url, "secondary")
            except Exception:
                pass

        def _load():
            stories = fetch_abc_headlines(10)
            QTimer.singleShot(0, lambda: self._apply_stories(stories))

        threading.Thread(target=_load, daemon=True, name="abc-rss").start()
        return "ABC News is on screen. Pinch and drag to move the panel — swipe left or right for the next story."

    def _apply_stories(self, stories: list[dict[str, str]]) -> None:
        self._stories = stories
        self.list.clear()
        for s in stories:
            item = QListWidgetItem(s["title"])
            item.setData(Qt.ItemDataRole.UserRole, s)
            self.list.addItem(item)
        self.status.setText(f"{len(stories)} ABC headlines · gesture control armed")
        if stories and self._web is not None and stories[0].get("link"):
            # Keep homepage unless user picks; optional: load first story
            pass

    def _on_pick(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        link = data.get("link") or ABC_HOME
        if self._web is not None:
            self._web.load(QUrl(link))
        self.story_opened.emit(data.get("title") or link)
        self.status.setText(f"Opened: {(data.get('title') or '')[:60]}")

    def next_story(self, delta: int = 1) -> None:
        if not self._stories:
            return
        row = self.list.currentRow()
        if row < 0:
            row = 0
        row = (row + delta) % len(self._stories)
        self.list.setCurrentRow(row)
        item = self.list.item(row)
        if item:
            self._on_pick(item)

    def _place_default(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            self.move(80, 80)
            return
        pr = parent.rect()
        self.move(
            max(20, (pr.width() - self.width()) // 2 - 40),
            max(60, (pr.height() - self.height()) // 2 - 40),
        )

    def move_normalized(self, nx: float, ny: float) -> None:
        """Place panel so its center tracks normalized cursor (0..1) in parent."""
        parent = self.parentWidget()
        if parent is None:
            return
        pr = parent.rect()
        x = int(nx * pr.width() - self.width() / 2)
        y = int(ny * pr.height() - self.height() / 2)
        x = max(8, min(pr.width() - self.width() - 8, x))
        y = max(40, min(pr.height() - self.height() - 8, y))
        self.move(x, y)

    def set_gesture_hint(self, text: str) -> None:
        self.hint.setText(text)

    def _close(self) -> None:
        self.hide()
        self.closed.emit()

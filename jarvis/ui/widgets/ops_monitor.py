"""Secondary-monitor PDTester — 6 graphical digests + live activity stream."""

from __future__ import annotations

import html as html_lib
from typing import Any

from PyQt6.QtCore import QTimer, QUrl, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QGridLayout,
    QGraphicsOpacityEffect,
)

from jarvis.core.digest_bank import DigestBank, SLOTS


_KIND_COLORS = {
    "site": "#00e8ff",
    "vibe": "#3dff9a",
    "steward": "#ffb020",
    "away": "#ffb020",
    "biz": "#7ec8ff",
    "code": "#3dff9a",
    "net": "#c4a0ff",
    "mail": "#ff6b4a",
    "wake": "#00e8ff",
    "spend": "#ffb020",
    "presence": "#8aa4b8",
    "security": "#3dff9a",
    "info": "#8aa4b8",
}


class _DigestTile(QFrame):
    """One of six graphical digests on the PDTester board."""

    def __init__(self, slot: str, parent=None) -> None:
        super().__init__(parent)
        self.slot = slot
        self.setObjectName("DigestTile")
        self.setMinimumHeight(118)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        self.badge = QLabel(slot)
        self.count = QLabel("0")
        self.count.setStyleSheet(
            "color:#5a7388; font-size:10px; letter-spacing:2px;"
        )
        top = QHBoxLayout()
        top.addWidget(self.badge)
        top.addStretch(1)
        top.addWidget(self.count)
        lay.addLayout(top)
        self.body = QLabel("Standing by…")
        self.body.setWordWrap(True)
        self.body.setStyleSheet(
            "color:#d7ebf6; font-size:14px; line-height:1.35;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        lay.addWidget(self.body, 1)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)
        self._set_accent("#00e8ff")

    def _set_accent(self, accent: str) -> None:
        self.setStyleSheet(
            f"QFrame#DigestTile {{ background: rgba(6,14,22,230);"
            f" border: 1px solid {accent}88; border-left: 4px solid {accent}; }}"
        )
        self.badge.setStyleSheet(
            f"color:{accent}; font-size:11px; letter-spacing:3px; font-weight:700;"
        )

    def set_digest(self, body: str, *, accent: str, count: int = 0) -> None:
        self._set_accent(accent)
        self.body.setText(body or "Standing by…")
        self.count.setText(str(count))
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(380)
        anim.setStartValue(0.4)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim


class _BigKpi(QFrame):
    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(6,14,22,220);"
            " border: 1px solid rgba(0,232,255,70); }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.value = QLabel("—")
        self.value.setStyleSheet(
            "color:#00e8ff; font-size:22px; font-weight:700; letter-spacing:1px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        self.caption = QLabel(caption.upper())
        self.caption.setStyleSheet(
            "color:#5a7388; font-size:9px; letter-spacing:2px; font-weight:600;"
        )
        lay.addWidget(self.value)
        lay.addWidget(self.caption)

    def set_value(self, text: str, accent: str = "#00e8ff") -> None:
        self.value.setText(text)
        self.value.setStyleSheet(
            f"color:{accent}; font-size:22px; font-weight:700; letter-spacing:1px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )


def _feed_document(
    *,
    items: list[dict[str, Any]],
    now: dict[str, Any] | None = None,
    accent: str = "#00e8ff",
) -> str:
    now = now or {}
    now_kind = (now.get("kind") or "info").upper()
    now_text = html_lib.escape(str(now.get("text") or "Standing by…"))
    now_color = _KIND_COLORS.get((now.get("kind") or "info").lower(), accent)

    cards = []
    for i, it in enumerate(items[:18]):
        kind = (it.get("kind") or "info").lower()
        color = _KIND_COLORS.get(kind, accent)
        stamp = html_lib.escape(str(it.get("ts") or "")[11:19] or "--:--:--")
        text = html_lib.escape(str(it.get("text") or ""))
        delay = min(i * 0.03, 0.4)
        cards.append(
            f"""<article class="card" style="animation-delay:{delay:.2f}s; border-left-color:{color}">
  <header>
    <span class="kind" style="color:{color}; border-color:{color}">{kind.upper()}</span>
    <span class="time">{stamp}</span>
  </header>
  <p>{text}</p>
</article>"""
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  :root {{ --cyan:{accent}; --void:#02060c; --panel:rgba(6,14,22,.92);
    --dim:#6a8498; --text:#e8f4ff; }}
  * {{ box-sizing:border-box; }}
  html, body {{
    margin:0; height:100%; background: var(--void); color:var(--text);
    font-family: Bahnschrift, "Segoe UI", sans-serif; overflow:hidden;
  }}
  .shell {{ display:flex; flex-direction:column; height:100%; padding:12px 14px; gap:10px; }}
  .now {{
    background: linear-gradient(105deg, rgba(0,232,255,.12), rgba(6,14,22,.9) 55%);
    border: 1px solid rgba(0,232,255,.2); padding: 12px 14px;
  }}
  .now .label {{ letter-spacing:.22em; font-size:10px; color:{now_color}; margin-bottom:6px; }}
  .now h1 {{ margin:0; font-size:1.15rem; font-weight:700; line-height:1.3; }}
  .stream {{ flex:1; overflow:auto; display:flex; flex-direction:column; gap:8px; }}
  .card {{
    background: var(--panel); border: 1px solid rgba(0,232,255,.1);
    border-left: 3px solid var(--cyan); padding: 10px 12px;
    animation: rise .45s ease both;
  }}
  @keyframes rise {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:none; }} }}
  .card header {{ display:flex; gap:10px; align-items:center; margin-bottom:4px; }}
  .kind {{ font-size:9px; letter-spacing:.14em; padding:2px 6px; border:1px solid; font-weight:700; }}
  .time {{ color:var(--dim); font-family: Consolas, monospace; font-size:10px; }}
  .card p {{ margin:0; font-size:13px; line-height:1.4; color:#d7ebf6; }}
</style></head>
<body>
<div class="shell">
  <section class="now">
    <div class="label">NOW · {html_lib.escape(now_kind)}</div>
    <h1>{now_text}</h1>
  </section>
  <div class="stream">
    {''.join(cards) if cards else '<div style="color:#5a7388;letter-spacing:.2em;margin:auto;">WAITING FOR DIGESTS…</div>'}
  </div>
</div>
</body></html>"""


class OpsMonitorWindow(QMainWindow):
    """PDTester board for monitor 2 — six digests + stream (HUD stays on monitor 1)."""

    def __init__(self, settings=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("JARVIS · PDTESTER / DEVLOG")
        self.setMinimumSize(980, 680)
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#02050a"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#eaf6ff"))
        self.setPalette(pal)

        self.bank = DigestBank()

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(20, 16, 20, 14)
        lay.setSpacing(12)

        head = QHBoxLayout()
        brand = QLabel("JARVIS  ·  PDTESTER")
        brand.setStyleSheet(
            "color:#00e8ff; font-size:24px; font-weight:800; letter-spacing:6px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        self.subtitle = QLabel("MONITOR 2 · 6 DIGESTS")
        self.subtitle.setStyleSheet(
            "color:#5a7388; font-size:11px; letter-spacing:3px;"
        )
        self._live_dot = QLabel("● LIVE")
        self._live_dot.setStyleSheet(
            "color:#00e8ff; font-size:12px; letter-spacing:3px; font-weight:700;"
        )
        head.addWidget(brand)
        head.addStretch(1)
        head.addWidget(self._live_dot)
        head.addSpacing(12)
        head.addWidget(self.subtitle)
        lay.addLayout(head)

        digest_grid = QGridLayout()
        digest_grid.setHorizontalSpacing(10)
        digest_grid.setVerticalSpacing(10)
        self._tiles: dict[str, _DigestTile] = {}
        for i, slot in enumerate(SLOTS):
            tile = _DigestTile(slot)
            self._tiles[slot] = tile
            digest_grid.addWidget(tile, i // 3, i % 3)
        lay.addLayout(digest_grid)

        kpi_row = QHBoxLayout()
        self.kpi_cpu = _BigKpi("CPU")
        self.kpi_ram = _BigKpi("Memory")
        self.kpi_tasks = _BigKpi("Tasks")
        for w in (self.kpi_cpu, self.kpi_ram, self.kpi_tasks):
            kpi_row.addWidget(w)
        lay.addLayout(kpi_row)

        feed_frame = QFrame()
        feed_frame.setObjectName("GlassPanel")
        feed_frame.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(2,8,14,230);"
            " border: 1px solid rgba(0,232,255,80); }"
        )
        feed_lay = QVBoxLayout(feed_frame)
        feed_lay.setContentsMargins(0, 0, 0, 0)
        self._web = None
        self._fallback_host = QWidget()
        self._fallback_lay = QVBoxLayout(self._fallback_host)
        self._fallback_lay.setContentsMargins(14, 12, 14, 12)
        self._fallback = QLabel("Loading live feed…")
        self._fallback.setStyleSheet("color:#8aa4b8; font-size:14px;")
        self._fallback_lay.addWidget(self._fallback)
        feed_lay.addWidget(self._fallback_host, 1)
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._web = QWebEngineView(feed_frame)
            self._web.settings().setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )
            feed_lay.addWidget(self._web, 1)
            self._fallback_host.hide()
        except Exception as e:
            self._fallback.setText(f"Feed engine unavailable — {e}")
        lay.addWidget(feed_frame, 1)

        self.status = QLabel("PDTester ready · digests sync from monitor 1 core…")
        self.status.setStyleSheet(
            "color:#8aa4b8; font-family:Consolas, monospace; font-size:12px;"
        )
        lay.addWidget(self.status)

        self._accent = "#00e8ff"
        self._items: list[dict[str, Any]] = []
        self._now: dict[str, Any] = {"kind": "info", "text": "Standing by…"}
        self._pulse_on = True
        self._pulse = QTimer(self)
        self._pulse.timeout.connect(self._tick_live)
        self._pulse.start(1100)
        self._paint_pending = False
        self._refresh_digest_tiles()
        self._paint_feed()

        if settings is not None:
            try:
                from jarvis.ui.styles import stylesheet

                self.setStyleSheet(stylesheet(settings.theme, mood="clear"))
            except Exception:
                pass

    def _tick_live(self) -> None:
        self._pulse_on = not self._pulse_on
        color = "#00e8ff" if self._pulse_on else "#5a7388"
        self._live_dot.setStyleSheet(
            f"color:{color}; font-size:12px; letter-spacing:3px; font-weight:700;"
        )

    def _refresh_digest_tiles(self) -> None:
        for card in self.bank.as_list():
            tile = self._tiles.get(card.slot)
            if tile:
                tile.set_digest(card.body, accent=card.accent, count=card.count)

    def set_stats(self, stats: dict, accent: str = "#00e8ff") -> None:
        self._accent = accent
        tasks = int(stats.get("open_tasks") or 0)
        cpu = stats.get("cpu")
        ram = stats.get("ram")
        self.kpi_tasks.set_value(str(tasks), accent)
        if cpu is not None:
            self.kpi_cpu.set_value(f"{float(cpu):.0f}%", accent)
        if ram is not None:
            self.kpi_ram.set_value(f"{float(ram):.0f}%", accent)
        stamp = stats.get("updated") or ""
        self.subtitle.setText(f"MONITOR 2 · SYNCED {stamp}")

    # Compatibility for older callers expecting spend/week/steward KPIs
    @property
    def kpi_spend(self):
        return self.kpi_cpu

    @property
    def kpi_week(self):
        return self.kpi_ram

    @property
    def kpi_steward(self):
        return self.kpi_tasks

    def push_live_item(self, item: dict[str, Any]) -> None:
        if not item:
            return
        self.bank.ingest(item)
        self._refresh_digest_tiles()
        self._items = [item] + [x for x in self._items if x is not item][:24]
        self._now = {
            "kind": item.get("kind") or "info",
            "text": item.get("text") or "",
        }
        kind = (item.get("kind") or "info").upper()
        self.status.setText(f"DIGEST › {kind} · {str(item.get('text') or '')[:90]}")
        self._schedule_paint()

    def set_now_working(self, kind: str, text: str) -> None:
        self._now = {"kind": kind or "info", "text": text or ""}
        self.bank.ingest({"kind": kind, "text": text})
        self._refresh_digest_tiles()
        self._schedule_paint()

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self._schedule_paint()

    def set_items(self, items: list[dict[str, Any]]) -> None:
        self._items = list(items or [])[:30]
        for it in reversed(self._items[:12]):
            self.bank.ingest(it)
        self._refresh_digest_tiles()
        if self._items:
            self._now = {
                "kind": self._items[0].get("kind") or "info",
                "text": self._items[0].get("text") or "",
            }
        self._schedule_paint()

    def set_feed(self, lines) -> None:
        items: list[dict[str, Any]] = []
        for line in lines or []:
            if isinstance(line, dict):
                items.append(line)
            else:
                s = str(line)
                parts = s.split("  ", 2)
                if len(parts) >= 3:
                    items.append(
                        {
                            "ts": f"2026-01-01T{parts[0]}:00",
                            "kind": parts[1].lower(),
                            "text": parts[2],
                        }
                    )
                else:
                    items.append({"ts": "", "kind": "info", "text": s})
        self.set_items(items)

    def _schedule_paint(self) -> None:
        if self._paint_pending:
            return
        self._paint_pending = True
        QTimer.singleShot(100, self._flush_paint)

    def _flush_paint(self) -> None:
        self._paint_pending = False
        self._paint_feed()

    def _paint_feed(self) -> None:
        html = _feed_document(
            items=self._items, now=self._now, accent=self._accent
        )
        if self._web is not None:
            self._web.setHtml(html, QUrl("https://jarvis.local/pdtester/"))
        else:
            lines = [
                f"{(it.get('kind') or '').upper()}  {it.get('text')}"
                for it in self._items[:8]
            ]
            self._fallback.setText(
                f"NOW: {self._now.get('text')}\n\n" + "\n".join(lines)
            )

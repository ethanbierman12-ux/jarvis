"""Secondary-monitor ops board — live animated activity feed + vitals."""

from __future__ import annotations

import html as html_lib
import json
from typing import Any

from PyQt6.QtCore import Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve
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
    "info": "#8aa4b8",
}


class _BigKpi(QFrame):
    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(6,14,22,220);"
            " border: 1px solid rgba(0,232,255,70); }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        self.value = QLabel("—")
        self.value.setStyleSheet(
            "color:#00e8ff; font-size:36px; font-weight:700; letter-spacing:2px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        self.caption = QLabel(caption.upper())
        self.caption.setStyleSheet(
            "color:#5a7388; font-size:11px; letter-spacing:3px; font-weight:600;"
        )
        lay.addWidget(self.value)
        lay.addWidget(self.caption)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)

    def set_value(self, text: str, accent: str = "#00e8ff") -> None:
        self.value.setText(text)
        self.value.setStyleSheet(
            f"color:{accent}; font-size:36px; font-weight:700; letter-spacing:2px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(420)
        anim.setStartValue(0.45)
        anim.setKeyValueAt(0.4, 1.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim


def _feed_document(
    *,
    items: list[dict[str, Any]],
    now: dict[str, Any] | None = None,
    accent: str = "#00e8ff",
) -> str:
    now = now or {}
    now_kind = (now.get("kind") or "info").upper()
    now_text = html_lib.escape(str(now.get("text") or "Standing by for agent activity…"))
    now_color = _KIND_COLORS.get((now.get("kind") or "info").lower(), accent)

    cards = []
    for i, it in enumerate(items[:36]):
        kind = (it.get("kind") or "info").lower()
        color = _KIND_COLORS.get(kind, accent)
        stamp = html_lib.escape(str(it.get("ts") or "")[11:19] or "--:--:--")
        text = html_lib.escape(str(it.get("text") or ""))
        status = (it.get("meta") or {}).get("status") or ""
        status_html = (
            f'<span class="status {html_lib.escape(str(status))}">{html_lib.escape(str(status).upper())}</span>'
            if status
            else ""
        )
        delay = min(i * 0.03, 0.45)
        cards.append(
            f"""<article class="card" style="animation-delay:{delay:.2f}s; border-left-color:{color}">
  <header>
    <span class="kind" style="color:{color}; border-color:{color}">{kind.upper()}</span>
    <span class="time">{stamp}</span>
    {status_html}
  </header>
  <p>{text}</p>
</article>"""
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  :root {{
    --cyan: {accent}; --void:#02060c; --panel:rgba(6,14,22,.92);
    --dim:#6a8498; --text:#e8f4ff; --line:rgba(0,232,255,.18);
  }}
  * {{ box-sizing:border-box; }}
  html, body {{
    margin:0; height:100%; background:
      radial-gradient(900px 420px at 10% -10%, rgba(0,232,255,.12), transparent 55%),
      radial-gradient(700px 380px at 100% 100%, rgba(61,255,154,.06), transparent 50%),
      var(--void);
    color: var(--text); font-family: Bahnschrift, "Segoe UI", sans-serif; overflow:hidden;
  }}
  .shell {{ display:flex; flex-direction:column; height:100%; padding:18px 20px 16px; gap:14px; }}
  .now {{
    position:relative; overflow:hidden;
    background: linear-gradient(105deg, rgba(0,232,255,.14), rgba(6,14,22,.9) 55%);
    border: 1px solid var(--line); padding: 16px 18px;
    animation: rise .55s ease both;
  }}
  .now::after {{
    content:""; position:absolute; left:-20%; top:0; bottom:0; width:40%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.06), transparent);
    animation: sweep 2.8s ease-in-out infinite;
  }}
  @keyframes sweep {{ 0% {{ transform:translateX(0); }} 100% {{ transform:translateX(320%); }} }}
  .now .label {{
    letter-spacing:.28em; font-size:11px; color:{now_color}; margin-bottom:8px;
  }}
  .now .pulse {{
    display:inline-block; width:8px; height:8px; border-radius:50%;
    background:{now_color}; box-shadow:0 0 12px {now_color};
    margin-right:8px; animation: blink 1.1s ease-in-out infinite;
  }}
  @keyframes blink {{ 50% {{ opacity:.35; transform:scale(.85); }} }}
  .now h1 {{
    margin:0; font-size:clamp(1.15rem, 2.2vw, 1.55rem); font-weight:700;
    letter-spacing:.03em; line-height:1.25; max-width:95%;
  }}
  .now .meta {{ margin-top:8px; color:var(--dim); font-size:12px; letter-spacing:.12em; }}
  .feed-head {{
    display:flex; justify-content:space-between; align-items:end;
    letter-spacing:.22em; font-size:11px; color:var(--cyan);
  }}
  .feed-head span {{ color:var(--dim); letter-spacing:.14em; }}
  .stream {{
    flex:1; overflow:auto; padding-right:6px; display:flex; flex-direction:column; gap:10px;
  }}
  .stream::-webkit-scrollbar {{ width:6px; }}
  .stream::-webkit-scrollbar-thumb {{ background:rgba(0,232,255,.28); }}
  .card {{
    background: var(--panel); border: 1px solid rgba(0,232,255,.12);
    border-left: 3px solid var(--cyan); padding: 12px 14px;
    animation: rise .5s ease both;
    transition: transform .2s ease, border-color .2s ease, background .2s ease;
  }}
  .card:hover {{
    transform: translateX(4px);
    background: rgba(0,232,255,.07);
    border-color: rgba(0,232,255,.35);
  }}
  @keyframes rise {{
    from {{ opacity:0; transform: translateY(12px); }}
    to {{ opacity:1; transform: none; }}
  }}
  .card header {{
    display:flex; gap:10px; align-items:center; margin-bottom:6px;
  }}
  .kind {{
    font-size:10px; letter-spacing:.16em; padding:3px 7px;
    border:1px solid; font-weight:700;
  }}
  .time {{ color:var(--dim); font-family: Consolas, monospace; font-size:11px; }}
  .status {{
    margin-left:auto; font-size:9px; letter-spacing:.14em; color:#041018;
    background: var(--cyan); padding:2px 6px;
  }}
  .status.done, .status.complete, .status.shipped {{ background:#3dff9a; }}
  .status.running, .status.building, .status.live {{ background:#ffb020; }}
  .card p {{
    margin:0; font-size:14px; line-height:1.45; color:#d7ebf6;
    font-family: "Segoe UI", Bahnschrift, sans-serif;
  }}
  .empty {{
    margin:auto; color:var(--dim); letter-spacing:.2em; font-size:13px;
    animation: rise .6s ease both;
  }}
</style></head>
<body>
<div class="shell">
  <section class="now">
    <div class="label"><span class="pulse"></span>NOW WORKING · {html_lib.escape(now_kind)}</div>
    <h1>{now_text}</h1>
    <div class="meta">LIVE ACTIVITY STREAM · SECONDARY DISPLAY</div>
  </section>
  <div class="feed-head">
    <div>DATA FEED</div>
    <span>{len(items)} EVENTS</span>
  </div>
  <div class="stream">
    {''.join(cards) if cards else '<div class="empty">WAITING FOR JARVIS ACTIVITY…</div>'}
  </div>
</div>
</body></html>"""


class OpsMonitorWindow(QMainWindow):
    """Fullscreen-friendly live ops board for the other monitor."""

    def __init__(self, settings=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("JARVIS · LIVE OPS")
        self.setMinimumSize(980, 680)
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#02050a"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#eaf6ff"))
        self.setPalette(pal)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(14)

        head = QHBoxLayout()
        brand = QLabel("JARVIS  ·  LIVE OPS")
        brand.setStyleSheet(
            "color:#00e8ff; font-size:26px; font-weight:800; letter-spacing:7px;"
            " font-family: Bahnschrift, 'Segoe UI';"
        )
        self.subtitle = QLabel("SECONDARY · ANIMATED FEED")
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
        head.addSpacing(14)
        head.addWidget(self.subtitle)
        lay.addLayout(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.kpi_spend = _BigKpi("Spent today")
        self.kpi_week = _BigKpi("This week")
        self.kpi_tasks = _BigKpi("Open tasks")
        self.kpi_steward = _BigKpi("Away jobs")
        self.kpi_cpu = _BigKpi("CPU")
        self.kpi_ram = _BigKpi("Memory")
        grid.addWidget(self.kpi_spend, 0, 0)
        grid.addWidget(self.kpi_week, 0, 1)
        grid.addWidget(self.kpi_tasks, 0, 2)
        grid.addWidget(self.kpi_steward, 1, 0)
        grid.addWidget(self.kpi_cpu, 1, 1)
        grid.addWidget(self.kpi_ram, 1, 2)
        lay.addLayout(grid)

        # Animated live feed (WebEngine)
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
        self._fallback_lay.setContentsMargins(16, 14, 16, 14)
        self._fallback = QLabel("Loading live feed…")
        self._fallback.setStyleSheet("color:#8aa4b8; font-size:14px;")
        self._fallback_lay.addWidget(self._fallback)
        feed_lay.addWidget(self._fallback_host, 1)
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._web = QWebEngineView(feed_frame)
            settings_we = self._web.settings()
            settings_we.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )
            feed_lay.addWidget(self._web, 1)
            self._fallback_host.hide()
        except Exception as e:
            self._fallback.setText(f"Feed engine unavailable — {e}")
        lay.addWidget(feed_frame, 1)

        self.status = QLabel("Standing by for live agent activity…")
        self.status.setStyleSheet(
            "color:#8aa4b8; font-family:Consolas, monospace; font-size:12px; letter-spacing:1px;"
        )
        lay.addWidget(self.status)

        self._accent = "#00e8ff"
        self._items: list[dict[str, Any]] = []
        self._now: dict[str, Any] = {
            "kind": "info",
            "text": "Standing by for agent activity…",
        }
        self._pulse_on = True
        self._pulse = QTimer(self)
        self._pulse.timeout.connect(self._tick_live)
        self._pulse.start(1100)
        self._paint_pending = False
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

    def set_stats(self, stats: dict, accent: str = "#00e8ff") -> None:
        self._accent = accent
        cur = stats.get("currency") or "USD"
        today = float(stats.get("spent_today") or 0)
        week = float(stats.get("spent_week") or 0)
        tasks = int(stats.get("open_tasks") or 0)
        done = int(stats.get("steward_done") or 0)
        queued = int(stats.get("steward_queued") or 0)
        cpu = stats.get("cpu")
        ram = stats.get("ram")
        self.kpi_spend.set_value(
            f"{cur} {today:.0f}" if today >= 10 else f"{cur} {today:.2f}", accent
        )
        self.kpi_week.set_value(
            f"{cur} {week:.0f}" if week >= 10 else f"{cur} {week:.2f}", accent
        )
        self.kpi_tasks.set_value(str(tasks), accent)
        self.kpi_steward.set_value(f"{done} / {queued}", accent)
        if cpu is not None:
            self.kpi_cpu.set_value(f"{float(cpu):.0f}%", accent)
        if ram is not None:
            self.kpi_ram.set_value(f"{float(ram):.0f}%", accent)
        stamp = stats.get("updated") or ""
        away = " · AWAY" if stats.get("away_mode") else ""
        self.subtitle.setText(f"SYNCED {stamp}{away}")
        self.subtitle.setStyleSheet(
            f"color:{accent}; font-size:11px; letter-spacing:3px;"
        )

    def push_live_item(self, item: dict[str, Any]) -> None:
        """Animated live prepend of a single activity event."""
        if not item:
            return
        self._items = [item] + [x for x in self._items if x is not item][:39]
        self._now = {
            "kind": item.get("kind") or "info",
            "text": item.get("text") or "",
        }
        kind = (item.get("kind") or "info").upper()
        self.status.setText(f"LIVE › {kind} · {str(item.get('text') or '')[:100]}")
        self._schedule_paint()

    def set_now_working(self, kind: str, text: str) -> None:
        self._now = {"kind": kind or "info", "text": text or ""}
        self._schedule_paint()

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self._schedule_paint()

    def set_items(self, items: list[dict[str, Any]]) -> None:
        self._items = list(items or [])[:40]
        if self._items:
            self._now = {
                "kind": self._items[0].get("kind") or "info",
                "text": self._items[0].get("text") or "",
            }
        self._schedule_paint()

    def set_feed(self, lines) -> None:
        """Accept list[str] legacy lines or list[dict] rich items."""
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
            self._web.setHtml(html, QUrl("https://jarvis.local/ops/"))
        else:
            lines = [
                f"{(it.get('kind') or '').upper()}  {it.get('text')}"
                for it in self._items[:12]
            ]
            self._fallback.setText(
                f"NOW: {self._now.get('text')}\n\n" + "\n".join(lines)
            )

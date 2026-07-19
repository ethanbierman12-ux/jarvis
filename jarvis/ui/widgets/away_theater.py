"""Away agent theater — watch Jarvis open apps, write, talk, run diagnostics."""

from __future__ import annotations

import html as html_lib
import json
from typing import Any

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QSizePolicy,
)


def _theater_html(
    *,
    stage: str = "announce",
    tasks: list[dict[str, Any]] | None = None,
    apps: list[str] | None = None,
    writing: str = "",
    file_path: str = "",
    diag: dict[str, Any] | None = None,
    terminal: list[str] | None = None,
    action: str = "",
    speak_line: str = "",
    log: list[str] | None = None,
) -> str:
    tasks = tasks or []
    apps = apps or []
    diag = diag or {}
    terminal = terminal or []
    log = log or []

    task_html = "".join(
        f'<div class="task {"done" if t.get("done") else ""} {"active" if t.get("active") else ""}">'
        f'<span class="mark">{"✓" if t.get("done") else ("●" if t.get("active") else "○")}</span>'
        f'{html_lib.escape(str(t.get("text") or ""))}</div>'
        for t in tasks
    ) or '<div class="task active"><span class="mark">●</span>Standing by…</div>'

    apps_html = "".join(
        f'<div class="app">▣ {html_lib.escape(a)}</div>' for a in apps
    ) or '<div class="dim">No apps opened yet</div>'

    tops = diag.get("top") or []
    tops_html = "".join(f"<li>{html_lib.escape(str(x))}</li>" for x in tops[:5])
    cpu = diag.get("cpu", "—")
    ram = diag.get("ram", "—")
    disk = diag.get("disk", "—")
    bat = diag.get("battery", "—")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  :root {{ --cyan:#00e8ff; --ok:#3dff9a; --dim:#7a93a8; --text:#e8f4ff; --line:rgba(0,232,255,.22); }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; height:100%; background:#02080e; color:var(--text);
    font-family:Bahnschrift,Segoe UI,sans-serif; overflow:hidden; }}
  .top {{
    height:54px; display:flex; align-items:center; gap:16px; padding:0 14px;
    border-bottom:1px solid var(--line);
    background:linear-gradient(90deg, rgba(0,232,255,.1), transparent 50%);
  }}
  .eyebrow {{ letter-spacing:.28em; color:var(--cyan); font-size:10px; }}
  .title {{ font-size:16px; font-weight:700; letter-spacing:.05em; }}
  .stage {{ margin-left:auto; color:var(--cyan); letter-spacing:.18em; font-size:11px; }}
  .speak {{
    padding:8px 14px; border-bottom:1px solid var(--line); color:#9adfff; font-size:13px;
    min-height:36px;
  }}
  .speak::before {{ content:"JARVIS · "; color:var(--cyan); letter-spacing:.14em; font-size:10px; }}
  .grid {{
    display:grid; height:calc(100% - 90px);
    grid-template-columns: 1fr 1.15fr 1fr;
    grid-template-rows: 1fr 140px;
  }}
  .panel {{
    border-right:1px solid var(--line); border-bottom:1px solid var(--line);
    display:flex; flex-direction:column; min-height:0; background:#071018;
  }}
  .ph {{
    padding:8px 10px; font-size:10px; letter-spacing:.2em; color:var(--cyan);
    border-bottom:1px solid var(--line);
  }}
  .body {{ flex:1; overflow:auto; padding:10px; font-size:12px; }}
  .tasks {{ grid-column:1; grid-row:1; }}
  .write {{ grid-column:2; grid-row:1; }}
  .diag {{ grid-column:3; grid-row:1 / 3; border-bottom:none; }}
  .apps {{ grid-column:1; grid-row:2; }}
  .term {{ grid-column:2; grid-row:2; }}
  .task {{ display:flex; gap:8px; padding:7px 0; color:var(--dim); border-bottom:1px solid rgba(255,255,255,.04); }}
  .task.active {{ color:var(--text); }}
  .task.done {{ color:var(--ok); }}
  .mark {{ width:14px; color:var(--cyan); }}
  .task.done .mark {{ color:var(--ok); }}
  pre {{
    margin:0; white-space:pre-wrap; word-break:break-word;
    font-family:Consolas,monospace; font-size:11px; line-height:1.45; color:#cfe9f8;
  }}
  .path {{ color:var(--dim); font-size:10px; margin-bottom:6px; letter-spacing:.08em; }}
  .vitals {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px; }}
  .vital {{
    padding:10px; border:1px solid var(--line); background:rgba(0,232,255,.05);
  }}
  .vital b {{ display:block; color:var(--cyan); font-size:20px; margin-top:4px; }}
  .vital span {{ color:var(--dim); font-size:10px; letter-spacing:.14em; }}
  .app {{ padding:6px 0; border-bottom:1px solid rgba(255,255,255,.05); }}
  .dim {{ color:var(--dim); }}
  .termbox {{ font-family:Consolas,monospace; font-size:11px; line-height:1.5; color:#9ab; }}
  .termbox div::before {{ content:"$ "; color:var(--cyan); }}
  ul {{ margin:8px 0 0; padding-left:16px; color:var(--dim); }}
  .pulse {{
    display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--cyan);
    box-shadow:0 0 10px var(--cyan); margin-right:8px; animation:p 1.2s ease-in-out infinite;
  }}
  @keyframes p {{ 50% {{ opacity:.35; }} }}
</style></head>
<body>
  <div class="top">
    <div>
      <div class="eyebrow">AWAY AGENT · LIVE</div>
      <div class="title"><span class="pulse"></span>JARVIS IN ACTION</div>
    </div>
    <div class="stage">{html_lib.escape(stage.upper())}</div>
  </div>
  <div class="speak">{html_lib.escape(speak_line or action or "Working…")}</div>
  <div class="grid">
    <section class="panel tasks">
      <div class="ph">TASKS</div>
      <div class="body">{task_html}</div>
    </section>
    <section class="panel write">
      <div class="ph">WRITING</div>
      <div class="body">
        <div class="path">{html_lib.escape(file_path or "away_status.md")}</div>
        <pre id="w">{html_lib.escape(writing or "…")}</pre>
      </div>
    </section>
    <section class="panel diag">
      <div class="ph">DIAGNOSTICS</div>
      <div class="body">
        <div class="vitals">
          <div class="vital"><span>CPU</span><b>{html_lib.escape(str(cpu))}%</b></div>
          <div class="vital"><span>RAM</span><b>{html_lib.escape(str(ram))}%</b></div>
          <div class="vital"><span>DISK</span><b>{html_lib.escape(str(disk))}%</b></div>
          <div class="vital"><span>BATTERY</span><b>{html_lib.escape(str(bat))}</b></div>
        </div>
        <div class="path">TOP PROCESSES</div>
        <ul>{tops_html or "<li class='dim'>Scanning…</li>"}</ul>
      </div>
    </section>
    <section class="panel apps">
      <div class="ph">APPS OPENED</div>
      <div class="body">{apps_html}</div>
    </section>
    <section class="panel term">
      <div class="ph">TERMINAL</div>
      <div class="body termbox" id="term"></div>
    </section>
  </div>
<script>
const lines = {json.dumps(terminal[-16:])};
const term = document.getElementById('term');
term.innerHTML = lines.map(t => '<div>' + String(t).replace(/</g,'&lt;') + '</div>').join('');
term.scrollTop = term.scrollHeight;
</script>
</body></html>"""


class AwayTheater(QFrame):
    closed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(2,8,14,245);"
            " border: 1px solid rgba(0,232,255,150); }"
        )
        self.setMinimumSize(880, 600)
        self.resize(1040, 700)
        self._web = None
        self._active = False
        self._stage = "announce"
        self._tasks: list[dict[str, Any]] = []
        self._apps: list[str] = []
        self._writing = ""
        self._file_path = ""
        self._diag: dict[str, Any] = {}
        self._terminal: list[str] = []
        self._action = ""
        self._speak = ""
        self._log: list[str] = []
        self._paint_pending = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        head = QHBoxLayout()
        self.title = QLabel("AWAY AGENT")
        self.title.setObjectName("SectionTitle")
        self.status = QLabel("Standing by…")
        self.status.setObjectName("Dim")
        self.status.setWordWrap(True)
        close = QPushButton("CLOSE")
        close.setObjectName("GhostBtn")
        close.setFixedHeight(28)
        close.clicked.connect(self._close)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(close)
        lay.addLayout(head)
        lay.addWidget(self.status)

        self._host = QWidget()
        self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._host, 1)
        self._fallback = QLabel("Loading away theater…")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet("color:#8aa4b8; background:#02080e; padding:24px;")
        self._host_lay.addWidget(self._fallback)
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._web = QWebEngineView(self._host)
            s = self._web.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            self._host_lay.addWidget(self._web, 1)
            self._fallback.hide()
        except Exception as e:
            self._fallback.setText(str(e))
        self.hide()

    def show_session(self) -> None:
        self._active = True
        self._stage = "announce"
        self._tasks = []
        self._apps = []
        self._writing = ""
        self._file_path = ""
        self._diag = {}
        self._terminal = ["jarvis away --live"]
        self._action = "Starting away agent…"
        self._speak = "Entering away mode."
        self._log = ["Away agent session started"]
        self.title.setText("AWAY AGENT · LIVE")
        self.status.setText("Watch Jarvis open apps, write notes, talk, and run diagnostics.")
        self._place()
        self.show()
        self.raise_()
        self._paint()

    def apply_progress(self, payload) -> None:
        if not self._active and not self.isVisible():
            return
        msg = ""
        if isinstance(payload, dict):
            msg = str(payload.get("msg") or "")
            if payload.get("stage"):
                self._stage = str(payload["stage"])
            if payload.get("tasks"):
                self._tasks = list(payload["tasks"])
            if payload.get("apps") is not None:
                self._apps = list(payload["apps"])
            if payload.get("writing") is not None:
                self._writing = str(payload["writing"])
            if payload.get("file_path"):
                self._file_path = str(payload["file_path"])
            if payload.get("diag"):
                self._diag = dict(payload["diag"])
            if payload.get("terminal"):
                self._terminal.append(str(payload["terminal"]))
                self._terminal = self._terminal[-30:]
            if payload.get("action"):
                self._action = str(payload["action"])
            if payload.get("speak"):
                self._speak = str(payload["speak"])
            elif msg:
                self._speak = msg
        else:
            msg = str(payload or "")
            self._speak = msg
            self._terminal.append(msg[:120])
        if msg:
            self._log.append(msg[:160])
            self.status.setText(msg[:160])
        self._schedule_paint()

    def _schedule_paint(self) -> None:
        if self._paint_pending:
            return
        self._paint_pending = True
        QTimer.singleShot(70, self._flush)

    def _flush(self) -> None:
        self._paint_pending = False
        self._paint()

    def _paint(self) -> None:
        if self._web is None:
            self._fallback.setText("\n".join(self._log[-12:]))
            return
        html = _theater_html(
            stage=self._stage,
            tasks=self._tasks,
            apps=self._apps,
            writing=self._writing,
            file_path=self._file_path,
            diag=self._diag,
            terminal=self._terminal,
            action=self._action,
            speak_line=self._speak,
            log=self._log,
        )
        self._web.setHtml(html, QUrl("https://jarvis.local/away/"))

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            self.move(28, 28)
            return
        pr = parent.rect()
        self.resize(min(1080, pr.width() - 48), min(720, pr.height() - 70))
        self.move(
            max(14, (pr.width() - self.width()) // 2),
            max(30, (pr.height() - self.height()) // 2 - 10),
        )

    def _close(self) -> None:
        self._active = False
        self.hide()
        self.closed.emit()

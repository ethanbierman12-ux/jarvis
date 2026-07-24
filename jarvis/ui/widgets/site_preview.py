"""Agentic coding workbench — plan, code, terminal, live browser preview."""

from __future__ import annotations

import html as html_lib
import json
from pathlib import Path
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


_AGENT_STAGES = (
    ("plan", "PLAN"),
    ("code", "CODE"),
    ("terminal", "TERMINAL"),
    ("browser", "BROWSER"),
    ("iterate", "ITERATE"),
    ("hitl", "HITL"),
    ("ship", "SHIP"),
)


def _agentic_html(
    *,
    hint: str = "new project",
    stage: str = "plan",
    brand: str = "",
    plan: list[dict[str, Any]] | None = None,
    file_path: str = "index.html",
    file_content: str = "",
    terminal: list[str] | None = None,
    browser_action: str = "",
    preview_html: str = "",
    agent_log: list[str] | None = None,
) -> str:
    plan = plan or []
    terminal = terminal or []
    agent_log = agent_log or []
    stage_idx = next((i for i, (k, _) in enumerate(_AGENT_STAGES) if k == stage), 0)
    pills = "".join(
        f'<span class="pill {"on" if i <= stage_idx else ""} {"now" if i == stage_idx else ""}">'
        f"{label}</span>"
        for i, (_, label) in enumerate(_AGENT_STAGES)
    )

    plan_html = "".join(
        f'<div class="task {"done" if t.get("done") else ""} {"active" if t.get("active") else ""}">'
        f'<span class="mark">{"✓" if t.get("done") else ("●" if t.get("active") else "○")}</span>'
        f'<span>{html_lib.escape(str(t.get("text") or ""))}</span></div>'
        for t in plan
    ) or '<div class="task active"><span class="mark">●</span><span>Planning agentic workflow…</span></div>'

    code = file_content or "// Agent standing by — awaiting file write…"
    # Escape for embedding in JS template literal via JSON
    code_js = json.dumps(code)
    path_safe = html_lib.escape(file_path or "untitled")
    hint_safe = html_lib.escape(hint)
    brand_safe = html_lib.escape(brand or "agent")
    action_safe = html_lib.escape(browser_action or "Viewport idle")
    term_js = json.dumps(terminal[-20:])
    log_js = json.dumps(agent_log[-12:])
    has_preview = bool(preview_html and len(preview_html) > 40)
    preview_js = json.dumps(preview_html if has_preview else "")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<style>
  :root {{
    --cyan:#00e8ff; --void:#02080e; --panel:#071018; --dim:#7a93a8; --text:#e8f4ff;
    --ok:#3dff9a; --line:rgba(0,232,255,.22);
  }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; height:100%; background:var(--void); color:var(--text);
    font-family: Bahnschrift, Segoe UI, sans-serif; overflow:hidden; }}
  .top {{
    height:52px; display:flex; align-items:center; gap:14px; padding:0 14px;
    border-bottom:1px solid var(--line);
    background:linear-gradient(90deg, rgba(0,232,255,.08), transparent 55%);
  }}
  .eyebrow {{ letter-spacing:.28em; color:var(--cyan); font-size:10px; }}
  .title {{ font-size:15px; letter-spacing:.06em; font-weight:700; }}
  .hint {{ color:var(--dim); font-size:11px; margin-left:auto; max-width:40%;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .pills {{ display:flex; gap:5px; flex-wrap:wrap; }}
  .pill {{
    font-size:9px; letter-spacing:.12em; padding:4px 7px;
    border:1px solid rgba(122,147,168,.35); color:var(--dim);
  }}
  .pill.on {{ border-color:rgba(0,232,255,.5); color:#9adfff; }}
  .pill.now {{ background:var(--cyan); color:#041018; border-color:var(--cyan); }}
  .grid {{
    display:grid; height:calc(100% - 52px);
    grid-template-columns: 220px 1.15fr 1.05fr;
    grid-template-rows: 1fr 150px;
  }}
  .panel {{
    border-right:1px solid var(--line); border-bottom:1px solid var(--line);
    background:var(--panel); display:flex; flex-direction:column; min-height:0;
  }}
  .panel:last-child {{ border-right:none; }}
  .ph {{
    padding:8px 10px; font-size:10px; letter-spacing:.2em; color:var(--cyan);
    border-bottom:1px solid var(--line); display:flex; justify-content:space-between;
  }}
  .ph span.sub {{ color:var(--dim); letter-spacing:.08em; }}
  .body {{ flex:1; overflow:auto; padding:10px; min-height:0; }}
  .plan {{ grid-row: 1 / 2; grid-column: 1; }}
  .code {{ grid-row: 1 / 2; grid-column: 2; }}
  .browser {{ grid-row: 1 / 3; grid-column: 3; border-bottom:none; }}
  .term {{ grid-row: 2 / 3; grid-column: 1 / 3; }}
  .task {{
    display:flex; gap:8px; align-items:flex-start; font-size:12px;
    color:var(--dim); padding:7px 0; border-bottom:1px solid rgba(255,255,255,.04);
  }}
  .task.active {{ color:var(--text); }}
  .task.done {{ color:var(--ok); }}
  .mark {{ width:14px; color:var(--cyan); flex-shrink:0; }}
  .task.done .mark {{ color:var(--ok); }}
  pre.codebox {{
    margin:0; font-family: Consolas, "Courier New", monospace; font-size:11.5px;
    line-height:1.45; white-space:pre-wrap; word-break:break-word; color:#cfe9f8;
  }}
  .cursor {{
    display:inline-block; width:7px; height:12px; background:var(--cyan);
    margin-left:2px; animation:blink 1s step-end infinite; vertical-align:text-bottom;
  }}
  @keyframes blink {{ 50% {{ opacity:0; }} }}
  .termbox, .agentlog {{
    font-family: Consolas, monospace; font-size:11px; line-height:1.5; color:#9ab;
  }}
  .termbox div::before {{ content:"$ "; color:var(--cyan); }}
  .termbox div.out::before {{ content:""; }}
  .termbox div.fresh {{ color:var(--text); }}
  .browser-bar {{
    display:flex; gap:8px; align-items:center; padding:6px 10px;
    border-bottom:1px solid var(--line); font-size:11px; color:var(--dim);
  }}
  .dot {{ width:8px; height:8px; border-radius:50%; background:var(--cyan);
    box-shadow:0 0 8px var(--cyan); }}
  .url {{
    flex:1; background:#02080e; border:1px solid var(--line); padding:4px 8px;
    color:#9adfff; font-family:Consolas,monospace; font-size:10px;
    overflow:hidden; white-space:nowrap; text-overflow:ellipsis;
  }}
  .viewport {{
    flex:1; position:relative; background:#05070c; min-height:0; overflow:hidden;
  }}
  .viewport iframe {{
    position:absolute; inset:0; width:100%; height:100%; border:0; background:#fff;
  }}
  .scan {{
    position:absolute; left:0; right:0; height:2px; z-index:2; pointer-events:none;
    background:linear-gradient(90deg, transparent, var(--cyan), transparent);
    animation:scan 2.2s linear infinite; opacity:.65;
  }}
  @keyframes scan {{ from {{ top:0; }} to {{ top:100%; }} }}
  .empty {{
    position:absolute; inset:0; display:grid; place-items:center; color:var(--dim);
    font-size:12px; letter-spacing:.14em; text-align:center; padding:20px;
  }}
  .agentlog {{ border-top:1px solid var(--line); padding:8px 10px; max-height:72px; overflow:auto; }}
  .agentlog div::before {{ content:"› "; color:var(--cyan); }}
</style></head>
<body>
  <div class="top">
    <div>
      <div class="eyebrow">AI AGENTIC CODING</div>
      <div class="title">AGENT WORKBENCH · {brand_safe}</div>
    </div>
    <div class="pills">{pills}</div>
    <div class="hint">{hint_safe}</div>
  </div>
  <div class="grid">
    <section class="panel plan">
      <div class="ph">AGENT PLAN <span class="sub">autonomous</span></div>
      <div class="body">{plan_html}</div>
      <div class="agentlog" id="alog"></div>
    </section>
    <section class="panel code">
      <div class="ph">CODE <span class="sub" id="fpath">{path_safe}</span></div>
      <div class="body"><pre class="codebox" id="code"></pre></div>
    </section>
    <section class="panel browser">
      <div class="ph">BROWSER · LIVE PREVIEW <span class="sub">hot reload</span></div>
      <div class="browser-bar">
        <div class="dot"></div>
        <div class="url" id="url">jarvis://agent/preview</div>
      </div>
      <div class="viewport">
        <div class="scan"></div>
        <iframe id="frame" sandbox="allow-same-origin allow-scripts"></iframe>
        <div class="empty" id="empty">Waiting for agent to render…<br/><br/>{action_safe}</div>
      </div>
    </section>
    <section class="panel term">
      <div class="ph">TERMINAL <span class="sub">sandbox</span></div>
      <div class="body termbox" id="term"></div>
    </section>
  </div>
<script>
const codeText = {code_js};
const termLines = {term_js};
const agentLines = {log_js};
const preview = {preview_js};
const codeEl = document.getElementById('code');
const termEl = document.getElementById('term');
const alog = document.getElementById('alog');
const frame = document.getElementById('frame');
const empty = document.getElementById('empty');
const url = document.getElementById('url');

// Typewriter for latest code snapshot (fast)
let i = 0;
const step = Math.max(2, Math.floor(codeText.length / 80));
function type() {{
  i = Math.min(codeText.length, i + step);
  codeEl.textContent = codeText.slice(0, i);
  if (i < codeText.length) {{
    codeEl.innerHTML = codeEl.textContent.replace(/</g,'&lt;') + '<span class="cursor"></span>';
    requestAnimationFrame(type);
  }} else {{
    codeEl.textContent = codeText;
  }}
}}
type();

termEl.innerHTML = termLines.map((t, idx) => {{
  const cls = (idx === termLines.length - 1 ? ' fresh' : '') + (t.startsWith('→') || t.startsWith('[') ? ' out' : '');
  return '<div class="' + cls.trim() + '">' + t.replace(/</g,'&lt;') + '</div>';
}}).join('');
termEl.scrollTop = termEl.scrollHeight;

alog.innerHTML = agentLines.map(t => '<div>' + t.replace(/</g,'&lt;') + '</div>').join('');
alog.scrollTop = alog.scrollHeight;

if (preview && preview.length > 40) {{
  frame.srcdoc = preview;
  empty.style.display = 'none';
  url.textContent = 'jarvis://agent/preview · hot reload';
}} else {{
  empty.style.display = 'grid';
}}
</script>
</body></html>"""


class SitePreview(QFrame):
    """Full-stack AI coding environment: agent plan · code · terminal · browser."""

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
        self.setMinimumSize(900, 620)
        self.resize(1080, 740)
        self._path: Path | None = None
        self._web = None
        self._building = False
        self._hint = ""
        self._stage = "plan"
        self._brand = ""
        self._plan: list[dict[str, Any]] = []
        self._file_path = "index.html"
        self._file_content = ""
        self._terminal: list[str] = []
        self._browser_action = ""
        self._preview_html = ""
        self._agent_log: list[str] = []
        self._paint_pending = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)

        head = QHBoxLayout()
        self.title = QLabel("AGENTIC CODING")
        self.title.setObjectName("SectionTitle")
        self.status = QLabel("AI coding agent standing by…")
        self.status.setObjectName("Dim")
        self.status.setWordWrap(True)
        close = QPushButton("CLOSE")
        close.setObjectName("GhostBtn")
        close.setFixedHeight(28)
        close.clicked.connect(self._close)
        open_ext = QPushButton("OPEN EXTERNAL")
        open_ext.setObjectName("GhostBtn")
        open_ext.setFixedHeight(28)
        open_ext.clicked.connect(self._open_external)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(open_ext)
        head.addWidget(close)
        lay.addLayout(head)
        lay.addWidget(self.status)

        self._host = QWidget()
        self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._host, 1)

        self._fallback = QLabel("Preparing agentic workbench…")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet(
            "color:#8aa4b8; background:#02080e; padding:28px; font-size:14px;"
        )
        self._host_lay.addWidget(self._fallback)

        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._web = QWebEngineView(self._host)
            settings = self._web.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )
            self._host_lay.addWidget(self._web, 1)
            self._fallback.hide()
        except Exception as e:
            self._fallback.setText(f"WebEngine unavailable.\n{e}")

        self.hide()

    def show_building(self, brand_hint: str = "New site") -> None:
        self._building = True
        self._path = None
        self._hint = brand_hint or "new venture"
        self._stage = "plan"
        self._brand = ""
        self._plan = [
            {"text": "Plan agentic site workflow", "active": True, "done": False},
            {"text": "Invent brand + write prompt", "active": False, "done": False},
            {"text": "Write project files", "active": False, "done": False},
            {"text": "Run sandbox build commands", "active": False, "done": False},
            {"text": "Open browser viewport + hot reload", "active": False, "done": False},
            {"text": "Iterate / ship live preview", "active": False, "done": False},
        ]
        self._file_path = "agent/plan.md"
        self._file_content = (
            "# Agentic Workflow\n\n"
            "- [ ] Invent brand\n"
            "- [ ] Write index.html\n"
            "- [ ] Hot-reload preview\n"
            "- [ ] Browser QA pass\n"
        )
        self._terminal = [
            "jarvis agent start --mode site",
            "→ sandbox ready",
            f"→ target: {self._hint}",
        ]
        self._browser_action = "Booting viewport…"
        self._preview_html = ""
        self._agent_log = [
            "AI coding agent online",
            "Agentic workflow initialized",
            "Waiting for first action…",
        ]
        self.title.setText("AGENTIC CODING · LIVE")
        self.status.setText(
            "Watch the agent plan, write code, run the terminal, and hot-reload the browser."
        )
        self._place()
        self.show()
        self.raise_()
        self._paint(force=True)

    def apply_progress(self, payload) -> None:
        if not self._building and not self.isVisible():
            return
        msg = ""
        if isinstance(payload, dict):
            msg = str(payload.get("msg") or payload.get("log") or payload.get("message") or "")
            if payload.get("stage"):
                self._map_stage(str(payload["stage"]))
            if payload.get("brand"):
                self._brand = str(payload["brand"])
            if payload.get("plan"):
                self._plan = list(payload["plan"])
            if payload.get("file_path"):
                self._file_path = str(payload["file_path"])
            if payload.get("file") is not None:
                self._file_content = str(payload["file"])
            if payload.get("terminal"):
                line = str(payload["terminal"])
                self._terminal.append(line)
                if len(self._terminal) > 40:
                    self._terminal = self._terminal[-40:]
            if payload.get("browser"):
                self._browser_action = str(payload["browser"])
            if payload.get("html"):
                self._preview_html = str(payload["html"])
            if payload.get("agent_stage"):
                self._stage = str(payload["agent_stage"])
            if msg:
                self._agent_log.append(msg[:160])
            elif payload.get("log"):
                self._agent_log.append(str(payload["log"])[:160])
        else:
            msg = str(payload or "")
            if msg:
                self._agent_log.append(msg[:160])
                self._infer_from_message(msg)

        if len(self._agent_log) > 30:
            self._agent_log = self._agent_log[-30:]
        if msg:
            self.status.setText(msg[:160])
        self._schedule_paint()

    def _map_stage(self, stage: str) -> None:
        """Map site-builder stages onto agentic workflow stages."""
        m = {
            "invent": "plan",
            "prompt": "plan",
            "copy": "code",
            "theme": "code",
            "render": "code",
            "live": "browser",
            "plan": "plan",
            "code": "code",
            "terminal": "terminal",
            "browser": "browser",
            "iterate": "iterate",
            "ship": "ship",
        }
        self._stage = m.get(stage, self._stage or "plan")
        self._sync_plan_flags()

    def _infer_from_message(self, msg: str) -> None:
        low = msg.lower()
        if "invent" in low or "brand" in low or "prompt" in low:
            self._stage = "plan"
        elif "terminal" in low or "sandbox" in low or "npm" in low or "build" in low:
            self._stage = "terminal"
        elif "browser" in low or "viewport" in low or "hot reload" in low or "qa" in low:
            self._stage = "browser"
        elif "render" in low or "html" in low or "writ" in low or "file" in low:
            self._stage = "code"
        elif "ship" in low or "complete" in low or "done" in low:
            self._stage = "ship"
        self._sync_plan_flags()

    def _sync_plan_flags(self) -> None:
        order = [k for k, _ in _AGENT_STAGES]
        try:
            idx = order.index(self._stage)
        except ValueError:
            idx = 0
        # Keep custom plan texts; only flip done/active by index when default length
        if len(self._plan) >= 6:
            for i, t in enumerate(self._plan):
                t["done"] = i < idx
                t["active"] = i == idx

    def show_site(self, path: Path, *, brand: str = "", prompt: str = "") -> None:
        self._building = False
        self._path = path
        self.title.setText(f"SHIPPED · {(brand or path.parent.name).upper()}")
        hint = (prompt or "")[:140].replace("\n", " ")
        self.status.setText(
            "Agentic workflow complete — live preview."
            + (f" {hint}" if hint else "")
        )
        self._place()
        self.show()
        self.raise_()
        url = path.resolve().as_uri()
        self._preview_url = url
        if self._web is not None:
            self._web.load(QUrl(url))
            self._fallback.hide()
        else:
            self._fallback.setText(f"Site ready at:\n{path}")
            self._open_external()

    def show_url(self, url: str, *, brand: str = "", prompt: str = "") -> None:
        """Load an http(s) or file preview URL (Vite / static)."""
        self._building = False
        self._preview_url = (url or "").strip()
        self._path = None
        label = brand or "preview"
        self.title.setText(f"PREVIEW · {label.upper()}")
        hint = (prompt or self._preview_url)[:160]
        self.status.setText(hint)
        self._place()
        self.show()
        self.raise_()
        if not self._preview_url:
            return
        if self._web is not None:
            self._web.load(QUrl(self._preview_url))
            self._fallback.hide()
        else:
            self._fallback.setText(f"Preview:\n{self._preview_url}")
            self._open_external()

    def _schedule_paint(self) -> None:
        if self._paint_pending or not self._building:
            return
        self._paint_pending = True
        QTimer.singleShot(90, self._flush_paint)

    def _flush_paint(self) -> None:
        self._paint_pending = False
        if self._building:
            self._paint(force=True)

    def _paint(self, *, force: bool = False) -> None:
        if self._web is None:
            self._fallback.setText("\n".join(self._agent_log[-14:]) or "Building…")
            self._fallback.show()
            return
        html = _agentic_html(
            hint=self._hint,
            stage=self._stage,
            brand=self._brand,
            plan=self._plan,
            file_path=self._file_path,
            file_content=self._file_content,
            terminal=self._terminal,
            browser_action=self._browser_action,
            preview_html=self._preview_html,
            agent_log=self._agent_log,
        )
        self._web.setHtml(html, QUrl("https://jarvis.local/agent/"))

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            self.move(24, 24)
            return
        pr = parent.rect()
        self.resize(min(1120, pr.width() - 40), min(760, pr.height() - 60))
        self.move(
            max(12, (pr.width() - self.width()) // 2),
            max(28, (pr.height() - self.height()) // 2 - 12),
        )

    def _open_external(self) -> None:
        url = getattr(self, "_preview_url", "") or ""
        if not url and getattr(self, "_path", None):
            try:
                url = self._path.resolve().as_uri()
            except Exception:
                url = ""
        if not url:
            return
        try:
            from jarvis.core.displays import displays

            displays.open_url_on(url, "secondary")
        except Exception:
            import webbrowser

            webbrowser.open(url)

    def _close(self) -> None:
        self._building = False
        self.hide()
        self.closed.emit()

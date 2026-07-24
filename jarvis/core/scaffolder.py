"""Project scaffolder — create React / Python / HTML starters + live preview."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScaffoldResult:
    ok: bool
    message: str
    path: Path | None = None
    kind: str = ""
    preview_url: str = ""


class ProjectScaffolder:
    def __init__(self, root: str | Path | None = None) -> None:
        home = Path.home()
        self.root = Path(root) if root else (home / "jarvis-projects")
        self.root.mkdir(parents=True, exist_ok=True)
        self._dev_proc: subprocess.Popen | None = None
        self.last: ScaffoldResult | None = None

    def status(self) -> str:
        kids = [p.name for p in self.root.iterdir() if p.is_dir()][:8]
        return f"Scaffold root {self.root}" + (
            f" — projects: {', '.join(kids)}" if kids else " — empty"
        )

    def create(self, kind: str, name: str = "", *, preview: bool = True) -> str:
        result = self.create_project(kind, name, preview=preview)
        self.last = result
        return result.message

    def create_project(
        self, kind: str, name: str = "", *, preview: bool = True
    ) -> ScaffoldResult:
        kind_l = (kind or "").strip().lower()
        base = self._slug(name) or f"{kind_l}-app"
        slug = base
        dest = self.root / slug
        # Always create a fresh folder so templates stay current
        if dest.exists():
            slug = f"{base}-{int(time.time()) % 100000}"
            dest = self.root / slug
        if kind_l in ("react", "vite", "react+vite", "react vite"):
            result = self._react_vite(dest, slug)
        elif kind_l in ("python", "py", "package"):
            result = self._python_pkg(dest, slug)
        elif kind_l in ("html", "site", "static"):
            result = self._html_site(dest, slug)
        else:
            return ScaffoldResult(
                ok=False,
                message="Unknown scaffold. Say: scaffold react, scaffold python, or scaffold html.",
            )
        if preview and result.ok and result.path:
            url = self.launch_preview(result.path, result.kind)
            result.preview_url = url
            if url:
                result.message = f"{result.message} Preview open: {url}".strip()
        self.last = result
        return result

    def launch_preview(self, dest: Path, kind: str) -> str:
        """Start/open a browser-tab preview. Returns URL or empty."""
        kind_l = (kind or "").strip().lower()
        dest = Path(dest)
        try:
            if kind_l in ("html", "site", "static"):
                index = dest / "index.html"
                if not index.exists():
                    return ""
                url = index.resolve().as_uri()
                webbrowser.open(url)
                return url
            if kind_l in ("react", "vite", "react+vite", "react vite"):
                return self._preview_vite(dest)
            if kind_l in ("python", "py", "package"):
                return self._preview_python(dest)
        except Exception as e:
            print(f"[scaffold] preview: {e}")
        return ""

    def _preview_python(self, dest: Path) -> str:
        preview = dest / "preview.html"
        pkg = next(
            (p.name for p in dest.iterdir() if p.is_dir() and (p / "__main__.py").exists()),
            dest.name,
        )
        preview.write_text(
            "<!doctype html><html><head><meta charset='utf-8'/>"
            f"<title>{dest.name}</title>"
            "<style>body{font-family:Georgia,serif;margin:3rem;background:#111;color:#eee}"
            "code{color:#8cf}</style></head><body>"
            f"<h1>{dest.name}</h1>"
            f"<p>Python package <code>{pkg}</code> scaffolded by Jarvis.</p>"
            f"<p>Run: <code>{sys.executable} -m {pkg}</code></p>"
            "</body></html>\n",
            encoding="utf-8",
        )
        url = preview.resolve().as_uri()
        webbrowser.open(url)
        return url

    def _preview_vite(self, dest: Path) -> str:
        # Prefer existing node_modules; try install if missing
        if not (dest / "node_modules").exists():
            self._try_npm_install(dest)
        self._stop_dev()
        creation = 0
        if sys.platform == "win32":
            creation = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            self._dev_proc = subprocess.Popen(
                ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
                cwd=str(dest),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=True,
                creationflags=creation,
            )
        except Exception as e:
            print(f"[scaffold] vite start: {e}")
            # Fallback: open index.html (won't run JSX, but something shows)
            index = dest / "index.html"
            if index.exists():
                url = index.resolve().as_uri()
                webbrowser.open(url)
                return url
            return ""

        url_holder: list[str] = []

        def _watch() -> None:
            assert self._dev_proc is not None
            try:
                for line in self._dev_proc.stdout or []:
                    print(f"[vite] {line.rstrip()}")
                    m = re.search(r"https?://(?:localhost|127\.0\.0\.1):\d+", line)
                    if m and not url_holder:
                        url_holder.append(m.group(0))
            except Exception:
                pass

        threading.Thread(target=_watch, daemon=True, name="jarvis-vite-log").start()

        # Wait up to ~25s for Vite ready
        deadline = time.time() + 25.0
        while time.time() < deadline:
            if url_holder:
                break
            # Port probe
            if self._port_open(5173):
                url_holder.append("http://127.0.0.1:5173")
                break
            if self._dev_proc.poll() is not None:
                break
            time.sleep(0.35)

        url = url_holder[0] if url_holder else "http://127.0.0.1:5173"
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return url

    def _stop_dev(self) -> None:
        proc = self._dev_proc
        self._dev_proc = None
        if not proc or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    @staticmethod
    def _port_open(port: int) -> bool:
        import socket

        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            return False

    def _slug(self, name: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip()).strip("-").lower()
        return s[:48]

    def _title_case(self, slug: str) -> str:
        words = re.sub(r"[-_]+", " ", slug or "app").strip()
        return " ".join(w.capitalize() for w in words.split()) or "App"

    def _react_vite(self, dest: Path, slug: str) -> ScaffoldResult:
        dest.mkdir(parents=True, exist_ok=False)
        title = self._title_case(slug)
        (dest / "package.json").write_text(
            json.dumps(
                {
                    "name": slug,
                    "private": True,
                    "version": "0.0.1",
                    "type": "module",
                    "scripts": {
                        "dev": "vite",
                        "build": "vite build",
                        "preview": "vite preview",
                    },
                    "dependencies": {"react": "^19.0.0", "react-dom": "^19.0.0"},
                    "devDependencies": {
                        "@vitejs/plugin-react": "^4.3.4",
                        "vite": "^6.0.0",
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (dest / "vite.config.js").write_text(
            "import { defineConfig } from 'vite'\n"
            "import react from '@vitejs/plugin-react'\n"
            "export default defineConfig({ plugins: [react()], "
            "server: { host: '127.0.0.1', port: 5173, strictPort: false } })\n",
            encoding="utf-8",
        )
        (dest / "index.html").write_text(
            "<!doctype html>\n<html lang=\"en\">\n<head>\n"
            "  <meta charset=\"UTF-8\" />\n"
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
            f"  <title>{title}</title>\n"
            "  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />\n"
            "  <link href=\"https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=Instrument+Serif:ital@0;1&display=swap\" rel=\"stylesheet\" />\n"
            "</head>\n<body>\n"
            "  <div id=\"root\"></div>\n"
            "  <script type=\"module\" src=\"/src/main.jsx\"></script>\n"
            "</body>\n</html>\n",
            encoding="utf-8",
        )
        src = dest / "src"
        src.mkdir()
        (src / "main.jsx").write_text(
            "import React from 'react'\n"
            "import { createRoot } from 'react-dom/client'\n"
            "import App from './App.jsx'\n"
            "import './styles.css'\n"
            "createRoot(document.getElementById('root')).render(<App />)\n",
            encoding="utf-8",
        )
        (src / "data.js").write_text(
            "export const SEED = [\n"
            "  { id: 1, title: 'Neon Briefing', tag: 'Ops', status: 'Live',\n"
            "    blurb: 'Morning status pack with weather, calendar, and priorities.' },\n"
            "  { id: 2, title: 'Vault Notes', tag: 'Memory', status: 'Draft',\n"
            "    blurb: 'Pinned facts and project context for quick recall.' },\n"
            "  { id: 3, title: 'Signal Desk', tag: 'Comms', status: 'Live',\n"
            "    blurb: 'Inbox triage board with starred threads and drafts.' },\n"
            "  { id: 4, title: 'Forge Lab', tag: 'Build', status: 'Live',\n"
            "    blurb: 'Active builds, preview links, and ship checklist.' },\n"
            "  { id: 5, title: 'Night Watch', tag: 'Ops', status: 'Paused',\n"
            "    blurb: 'Quiet-hours monitor for CPU, disk, and door alerts.' },\n"
            "  { id: 6, title: 'Atlas Map', tag: 'Travel', status: 'Live',\n"
            "    blurb: 'Saved places, routes, and sector scans.' },\n"
            "  { id: 7, title: 'Pulse Media', tag: 'Media', status: 'Draft',\n"
            "    blurb: 'Playlist queue and focus soundscapes.' },\n"
            "  { id: 8, title: 'Healer Bay', tag: 'System', status: 'Live',\n"
            "    blurb: 'Process health, RAM pressure, and kill suggestions.' },\n"
            "]\n"
            "export const TAGS = ['All', 'Ops', 'Memory', 'Comms', 'Build', 'Travel', 'Media', 'System']\n",
            encoding="utf-8",
        )
        (src / "styles.css").write_text(
            """:root {
  --bg: #071018;
  --panel: #0d1822;
  --line: rgba(0, 232, 255, 0.18);
  --text: #e8f4ff;
  --muted: #8aa4b8;
  --cyan: #00e8ff;
  --amber: #ffb020;
  --ok: #3dff9a;
  --warn: #ff8a5c;
}
* { box-sizing: border-box; }
html, body, #root { margin: 0; min-height: 100%; }
body {
  font-family: "DM Sans", system-ui, sans-serif;
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(0,232,255,.12), transparent 55%),
    radial-gradient(900px 500px at 100% 0%, rgba(255,176,32,.08), transparent 50%),
    var(--bg);
  color: var(--text);
}
.app { max-width: 1100px; margin: 0 auto; padding: 28px 22px 64px; }
.top {
  display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end;
  justify-content: space-between; margin-bottom: 28px;
}
.brand h1 {
  font-family: "Instrument Serif", Georgia, serif;
  font-size: clamp(2rem, 4vw, 3.2rem); font-weight: 400;
  margin: 0 0 6px; letter-spacing: 0.02em;
}
.brand p { margin: 0; color: var(--muted); max-width: 42ch; line-height: 1.45; }
.stats { display: flex; gap: 10px; flex-wrap: wrap; }
.stat {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 10px 14px; min-width: 88px;
}
.stat b { display: block; font-size: 1.25rem; color: var(--cyan); }
.stat span { font-size: 0.75rem; color: var(--muted); letter-spacing: 0.04em; text-transform: uppercase; }
.toolbar {
  display: grid; grid-template-columns: 1fr auto; gap: 12px;
  margin-bottom: 18px;
}
@media (max-width: 720px) { .toolbar { grid-template-columns: 1fr; } }
.search {
  display: flex; align-items: center; gap: 10px;
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 14px; padding: 12px 14px;
}
.search input {
  flex: 1; border: 0; outline: 0; background: transparent;
  color: var(--text); font-size: 1rem; font-family: inherit;
}
.search input::placeholder { color: var(--muted); }
.tags { display: flex; flex-wrap: wrap; gap: 8px; align-content: center; }
.tag {
  border: 1px solid var(--line); background: transparent; color: var(--muted);
  border-radius: 999px; padding: 8px 12px; cursor: pointer; font: inherit;
}
.tag.on, .tag:hover { color: var(--bg); background: var(--cyan); border-color: var(--cyan); }
.layout { display: grid; grid-template-columns: 1.4fr 0.9fr; gap: 16px; }
@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 16px;
  padding: 16px; display: flex; flex-direction: column; gap: 10px;
  transition: border-color .15s, transform .15s;
}
.card:hover { border-color: rgba(0,232,255,.45); transform: translateY(-2px); }
.card.selected { border-color: var(--amber); box-shadow: 0 0 0 1px rgba(255,176,32,.25); }
.card-top { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.pill {
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em;
  border-radius: 999px; padding: 4px 8px; border: 1px solid var(--line); color: var(--muted);
}
.pill.live { color: var(--ok); border-color: rgba(61,255,154,.35); }
.pill.draft { color: var(--amber); border-color: rgba(255,176,32,.35); }
.pill.paused { color: var(--warn); border-color: rgba(255,138,92,.35); }
.card h3 { margin: 0; font-size: 1.05rem; }
.card p { margin: 0; color: var(--muted); font-size: 0.92rem; line-height: 1.4; flex: 1; }
.card button {
  align-self: start; border: 0; border-radius: 10px; padding: 8px 12px;
  background: rgba(0,232,255,.12); color: var(--cyan); font: inherit; cursor: pointer;
}
.card button:hover { background: rgba(0,232,255,.22); }
.side {
  background: var(--panel); border: 1px solid var(--line); border-radius: 16px;
  padding: 18px; min-height: 280px;
}
.side h2 { margin: 0 0 8px; font-family: "Instrument Serif", Georgia, serif; font-weight: 400; font-size: 1.7rem; }
.side .meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 14px; }
.composer { display: grid; gap: 8px; margin-top: 16px; }
.composer input, .composer textarea, .composer select {
  width: 100%; background: #08131c; border: 1px solid var(--line); border-radius: 10px;
  color: var(--text); padding: 10px 12px; font: inherit;
}
.composer textarea { min-height: 72px; resize: vertical; }
.composer button {
  border: 0; border-radius: 10px; padding: 11px 14px; font: inherit; font-weight: 700;
  background: var(--cyan); color: #041018; cursor: pointer;
}
.empty { color: var(--muted); padding: 28px; text-align: center; border: 1px dashed var(--line); border-radius: 14px; }
.foot { margin-top: 22px; color: var(--muted); font-size: 0.85rem; }
""",
            encoding="utf-8",
        )
        # App.jsx — functional hub with search, filters, detail, add form
        app_jsx = f'''import React, {{ useMemo, useState }} from 'react'
import {{ SEED, TAGS }} from './data.js'

const statusClass = (s) => {{
  const v = (s || '').toLowerCase()
  if (v === 'live') return 'pill live'
  if (v === 'draft') return 'pill draft'
  return 'pill paused'
}}

export default function App() {{
  const [items, setItems] = useState(SEED)
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('All')
  const [selectedId, setSelectedId] = useState(SEED[0]?.id ?? null)
  const [draft, setDraft] = useState({{ title: '', tag: 'Ops', blurb: '', status: 'Draft' }})

  const filtered = useMemo(() => {{
    const q = query.trim().toLowerCase()
    return items.filter((item) => {{
      const tagOk = tag === 'All' || item.tag === tag
      if (!tagOk) return false
      if (!q) return true
      return (
        item.title.toLowerCase().includes(q) ||
        item.blurb.toLowerCase().includes(q) ||
        item.tag.toLowerCase().includes(q) ||
        item.status.toLowerCase().includes(q)
      )
    }})
  }}, [items, query, tag])

  const selected = items.find((i) => i.id === selectedId) || filtered[0] || null

  const liveCount = items.filter((i) => i.status === 'Live').length

  function addItem(e) {{
    e.preventDefault()
    if (!draft.title.trim()) return
    const next = {{
      id: Date.now(),
      title: draft.title.trim(),
      tag: draft.tag,
      status: draft.status,
      blurb: draft.blurb.trim() || 'New module added from the composer.',
    }}
    setItems((prev) => [next, ...prev])
    setSelectedId(next.id)
    setDraft({{ title: '', tag: 'Ops', blurb: '', status: 'Draft' }})
    setQuery('')
    setTag('All')
  }}

  function toggleStatus(id) {{
    setItems((prev) =>
      prev.map((item) => {{
        if (item.id !== id) return item
        const order = ['Live', 'Draft', 'Paused']
        const i = order.indexOf(item.status)
        return {{ ...item, status: order[(i + 1) % order.length] }}
      }})
    )
  }}

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <h1>{title}</h1>
          <p>
            Live command hub — search modules, filter by lane, open a detail pane,
            and add new cards. Fully interactive in the browser.
          </p>
        </div>
        <div className="stats">
          <div className="stat"><b>{{items.length}}</b><span>Modules</span></div>
          <div className="stat"><b>{{liveCount}}</b><span>Live</span></div>
          <div className="stat"><b>{{filtered.length}}</b><span>Showing</span></div>
        </div>
      </header>

      <div className="toolbar">
        <label className="search">
          <span aria-hidden="true">⌕</span>
          <input
            value={{query}}
            onChange={{(e) => setQuery(e.target.value)}}
            placeholder="Search title, tag, status, or notes…"
            aria-label="Search modules"
          />
        </label>
        <div className="tags" role="tablist" aria-label="Filter by tag">
          {{TAGS.map((t) => (
            <button
              key={{t}}
              type="button"
              className={{`tag ${{tag === t ? 'on' : ''}}`}}
              onClick={{() => setTag(t)}}
            >
              {{t}}
            </button>
          ))}}
        </div>
      </div>

      <div className="layout">
        <section>
          {{filtered.length === 0 ? (
            <div className="empty">No modules match “{{query || tag}}”. Clear search or add one.</div>
          ) : (
            <div className="grid">
              {{filtered.map((item) => (
                <article
                  key={{item.id}}
                  className={{`card ${{selected?.id === item.id ? 'selected' : ''}}`}}
                >
                  <div className="card-top">
                    <span className="pill">{{item.tag}}</span>
                    <span className={{statusClass(item.status)}}>{{item.status}}</span>
                  </div>
                  <h3>{{item.title}}</h3>
                  <p>{{item.blurb}}</p>
                  <button type="button" onClick={{() => setSelectedId(item.id)}}>
                    Open details
                  </button>
                </article>
              ))}}
            </div>
          )}}
        </section>

        <aside className="side">
          {{selected ? (
            <>
              <h2>{{selected.title}}</h2>
              <div className="meta">
                {{selected.tag}} · {{selected.status}} · id {{selected.id}}
              </div>
              <p>{{selected.blurb}}</p>
              <p style={{{{ color: '#8aa4b8', marginTop: 12 }}}}>
                Tip: cycle status, refine search, or compose a new module on the right.
              </p>
              <button
                type="button"
                style={{{{
                  marginTop: 14, border: 0, borderRadius: 10, padding: '10px 12px',
                  background: 'rgba(255,176,32,.16)', color: '#ffb020', font: 'inherit', cursor: 'pointer'
                }}}}
                onClick={{() => toggleStatus(selected.id)}}
              >
                Cycle status
              </button>
            </>
          ) : (
            <p className="meta">Select a card to inspect it.</p>
          )}}

          <form className="composer" onSubmit={{addItem}}>
            <strong>Add module</strong>
            <input
              value={{draft.title}}
              onChange={{(e) => setDraft({{ ...draft, title: e.target.value }})}}
              placeholder="Title"
              required
            />
            <select
              value={{draft.tag}}
              onChange={{(e) => setDraft({{ ...draft, tag: e.target.value }})}}
            >
              {{TAGS.filter((t) => t !== 'All').map((t) => (
                <option key={{t}} value={{t}}>{{t}}</option>
              ))}}
            </select>
            <select
              value={{draft.status}}
              onChange={{(e) => setDraft({{ ...draft, status: e.target.value }})}}
            >
              <option>Live</option>
              <option>Draft</option>
              <option>Paused</option>
            </select>
            <textarea
              value={{draft.blurb}}
              onChange={{(e) => setDraft({{ ...draft, blurb: e.target.value }})}}
              placeholder="Short description"
            />
            <button type="submit">Add to hub</button>
          </form>
        </aside>
      </div>

      <p className="foot">Built by Jarvis · Vite + React · edit src/App.jsx to evolve this hub.</p>
    </div>
  )
}}
'''
        (src / "App.jsx").write_text(app_jsx, encoding="utf-8")
        (dest / "README.md").write_text(
            f"# {title}\n\n"
            "Interactive React hub with search, tag filters, detail pane, and add form.\n\n"
            "```bash\nnpm install\nnpm run dev\n```\n",
            encoding="utf-8",
        )
        npm = self._try_npm_install(dest)
        return ScaffoldResult(
            ok=True,
            message=f"React hub “{title}” ready at {dest}. {npm}",
            path=dest,
            kind="react",
        )

    def _python_pkg(self, dest: Path, slug: str) -> ScaffoldResult:
        dest.mkdir(parents=True, exist_ok=False)
        pkg = re.sub(r"[^a-z0-9_]", "_", slug)
        (dest / "pyproject.toml").write_text(
            f'[project]\nname = "{slug}"\nversion = "0.1.0"\n'
            'requires-python = ">=3.11"\n'
            'dependencies = []\n\n'
            "[build-system]\n"
            'requires = ["setuptools>=61"]\n'
            'build-backend = "setuptools.build_meta"\n',
            encoding="utf-8",
        )
        mod = dest / pkg
        mod.mkdir()
        (mod / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
        (mod / "__main__.py").write_text(
            f'print("Hello from {slug}")\n',
            encoding="utf-8",
        )
        (dest / "README.md").write_text(
            f"# {slug}\n\n```bash\n{sys.executable} -m {pkg}\n```\n",
            encoding="utf-8",
        )
        return ScaffoldResult(
            ok=True,
            message=f"Python package ready at {dest}.",
            path=dest,
            kind="python",
        )

    def _html_site(self, dest: Path, slug: str) -> ScaffoldResult:
        dest.mkdir(parents=True, exist_ok=False)
        title = self._title_case(slug)
        (dest / "index.html").write_text(
            f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <div class="app">
    <header>
      <h1>{title}</h1>
      <p class="sub">Searchable board with live filters — no build step needed.</p>
    </header>
    <div class="toolbar">
      <input id="q" type="search" placeholder="Search cards…" aria-label="Search" />
      <div id="tags" class="tags"></div>
    </div>
    <div id="stats" class="stats"></div>
    <div id="grid" class="grid"></div>
  </div>
  <script src="app.js"></script>
</body>
</html>
""",
            encoding="utf-8",
        )
        (dest / "styles.css").write_text(
            """body{margin:0;font-family:Georgia,serif;background:#071018;color:#e8f4ff}
.app{max-width:960px;margin:0 auto;padding:2rem}
h1{margin:0 0 .35rem;font-size:2.4rem;color:#00e8ff}
.sub{color:#8aa4b8;margin:0 0 1.25rem}
.toolbar{display:flex;flex-wrap:wrap;gap:.75rem;margin-bottom:1rem}
#q{flex:1;min-width:200px;padding:.75rem 1rem;border-radius:12px;border:1px solid rgba(0,232,255,.25);background:#0d1822;color:#e8f4ff;font:inherit}
.tags{display:flex;flex-wrap:wrap;gap:.4rem}
.tag{border:1px solid rgba(0,232,255,.25);background:transparent;color:#8aa4b8;border-radius:999px;padding:.4rem .75rem;cursor:pointer;font:inherit}
.tag.on{background:#00e8ff;color:#041018;border-color:#00e8ff}
.stats{color:#8aa4b8;margin-bottom:1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.75rem}
.card{background:#0d1822;border:1px solid rgba(0,232,255,.18);border-radius:14px;padding:1rem}
.card h3{margin:.2rem 0;font-size:1.05rem}
.card p{margin:0;color:#8aa4b8;font-size:.92rem}
.pill{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:#ffb020}
""",
            encoding="utf-8",
        )
        (dest / "app.js").write_text(
            """const DATA = [
  { title: 'Neon Briefing', tag: 'Ops', blurb: 'Morning pack with weather and priorities.' },
  { title: 'Vault Notes', tag: 'Memory', blurb: 'Pinned facts for quick recall.' },
  { title: 'Signal Desk', tag: 'Comms', blurb: 'Starred threads and drafts.' },
  { title: 'Forge Lab', tag: 'Build', blurb: 'Active builds and ship checklist.' },
  { title: 'Atlas Map', tag: 'Travel', blurb: 'Saved places and routes.' },
  { title: 'Healer Bay', tag: 'System', blurb: 'CPU and process health.' },
];
const TAGS = ['All', ...new Set(DATA.map(d => d.tag))];
let tag = 'All';
const q = document.getElementById('q');
const grid = document.getElementById('grid');
const tagsEl = document.getElementById('tags');
const stats = document.getElementById('stats');

function renderTags() {
  tagsEl.innerHTML = TAGS.map(t =>
    `<button class="tag ${t === tag ? 'on' : ''}" data-tag="${t}">${t}</button>`
  ).join('');
  tagsEl.querySelectorAll('.tag').forEach(btn => {
    btn.onclick = () => { tag = btn.dataset.tag; render(); };
  });
}

function render() {
  const query = (q.value || '').trim().toLowerCase();
  const rows = DATA.filter(d => {
    const tagOk = tag === 'All' || d.tag === tag;
    if (!tagOk) return false;
    if (!query) return true;
    return (d.title + d.blurb + d.tag).toLowerCase().includes(query);
  });
  stats.textContent = `Showing ${rows.length} of ${DATA.length}`;
  grid.innerHTML = rows.map(d =>
    `<article class="card"><div class="pill">${d.tag}</div><h3>${d.title}</h3><p>${d.blurb}</p></article>`
  ).join('') || '<p class="stats">No matches.</p>';
  renderTags();
}

q.addEventListener('input', render);
render();
""",
            encoding="utf-8",
        )
        return ScaffoldResult(
            ok=True,
            message=f"HTML hub “{title}” ready at {dest}.",
            path=dest,
            kind="html",
        )

    def _try_npm_install(self, dest: Path) -> str:
        try:
            p = subprocess.run(
                ["npm", "install"],
                cwd=str(dest),
                capture_output=True,
                text=True,
                timeout=180,
                shell=True,
            )
            if p.returncode == 0:
                return "npm install completed."
            return "Scaffold written; npm install failed — run it manually."
        except FileNotFoundError:
            return "Scaffold written; install Node.js then run npm install."
        except Exception as e:
            return f"Scaffold written; npm skipped ({e})."

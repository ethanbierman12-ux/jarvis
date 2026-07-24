"""Project scaffolder — create React / Python / HTML starters + live preview + publish."""

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

from jarvis.config import ROOT


@dataclass
class ScaffoldResult:
    ok: bool
    message: str
    path: Path | None = None
    kind: str = ""
    preview_url: str = ""


class ProjectScaffolder:
    TEMPLATES = ROOT / "jarvis" / "templates"

    def __init__(self, root: str | Path | None = None) -> None:
        home = Path.home()
        self.root = Path(root) if root else (home / "jarvis-projects")
        self.root.mkdir(parents=True, exist_ok=True)
        self._dev_proc: subprocess.Popen | None = None
        self._preview_proc: subprocess.Popen | None = None
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

    def latest_project(self, kind: str = "") -> Path | None:
        if self.last and self.last.path and self.last.path.exists():
            if not kind or self.last.kind == kind or (
                kind == "react" and self.last.kind in ("react", "vite")
            ):
                return self.last.path
        kids = [p for p in self.root.iterdir() if p.is_dir()]
        if not kids:
            return None
        if kind in ("react", "vite"):
            kids = [p for p in kids if (p / "package.json").exists()] or kids
        elif kind in ("html", "site"):
            kids = [p for p in kids if (p / "index.html").exists() and not (p / "package.json").exists()] or kids
        kids.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return kids[0] if kids else None

    def publish(self, name: str = "") -> str:
        """Build React app for production and serve dist (publishable preview)."""
        dest = None
        if name:
            dest = self.root / self._slug(name)
            if not dest.exists():
                # fuzzy match
                needle = self._slug(name)
                for p in self.root.iterdir():
                    if p.is_dir() and needle in p.name:
                        dest = p
                        break
        if dest is None or not dest.exists():
            dest = self.latest_project("react")
        if dest is None or not dest.exists():
            return "No React project to publish. Say scaffold react first."
        if not (dest / "package.json").exists():
            return f"{dest.name} is not a React/Vite app."

        if not (dest / "node_modules").exists():
            self._try_npm_install(dest)

        try:
            build = subprocess.run(
                ["npm", "run", "build"],
                cwd=str(dest),
                capture_output=True,
                text=True,
                timeout=180,
                shell=True,
            )
        except Exception as e:
            return f"Build failed to start: {e}"
        if build.returncode != 0:
            err = (build.stderr or build.stdout or "")[-400:]
            return f"Build failed for {dest.name}: {err}"

        dist = dest / "dist"
        if not dist.exists():
            return f"Build finished but dist/ missing in {dest.name}."

        url = self._serve_dist(dest)
        try:
            from jarvis.core import app_scores

            app_scores.register_publish(
                dest.name,
                title=self._title_case(dest.name),
                url=url or "",
                path=str(dest),
            )
        except Exception as e:
            print(f"[scaffold] score register: {e}")

        # Write publish marker for Jarvis
        try:
            (dest / ".jarvis-publish.json").write_text(
                json.dumps(
                    {
                        "app_id": dest.name,
                        "url": url,
                        "built_at": time.time(),
                        "dist": str(dist),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

        msg = (
            f"Published {dest.name} — production build ready. "
            f"Live preview: {url or 'dist/'}. "
            "Also deployable: drag dist/ to Netlify, or run npx vercel --prod."
        )
        if url:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return msg

    def _serve_dist(self, dest: Path) -> str:
        self._stop_preview()
        creation = 0
        if sys.platform == "win32":
            creation = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            self._preview_proc = subprocess.Popen(
                ["npm", "run", "preview", "--", "--host", "127.0.0.1", "--port", "4173"],
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
            print(f"[scaffold] preview serve: {e}")
            return ""

        deadline = time.time() + 20.0
        while time.time() < deadline:
            if self._port_open(4173):
                return "http://127.0.0.1:4173"
            if self._preview_proc.poll() is not None:
                break
            time.sleep(0.35)
        return "http://127.0.0.1:4173"

    def _stop_preview(self) -> None:
        proc = self._preview_proc
        self._preview_proc = None
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

        deadline = time.time() + 25.0
        while time.time() < deadline:
            if url_holder:
                break
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

    def _copy_template(self, template_name: str, dest: Path, slug: str, title: str) -> None:
        src = self.TEMPLATES / template_name
        if not src.is_dir():
            raise FileNotFoundError(f"Missing template {src}")
        dest.mkdir(parents=True, exist_ok=False)
        for path in src.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(src)
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            text = path.read_text(encoding="utf-8")
            text = text.replace("{{SLUG}}", slug).replace("{{TITLE}}", title)
            out.write_text(text, encoding="utf-8")

    def _react_vite(self, dest: Path, slug: str) -> ScaffoldResult:
        title = self._title_case(slug)
        try:
            self._copy_template("react-pulse", dest, slug, title)
        except Exception as e:
            return ScaffoldResult(ok=False, message=f"React template failed: {e}")
        npm = self._try_npm_install(dest)
        try:
            from jarvis.core import app_scores

            app_scores.ingest(
                {
                    "app_id": slug,
                    "title": title,
                    "kind": "action",
                    "points": 10,
                    "label": "scaffold",
                }
            )
        except Exception:
            pass
        return ScaffoldResult(
            ok=True,
            message=f"Pulse Arena “{title}” ready at {dest}. {npm}",
            path=dest,
            kind="react",
        )

    def _python_pkg(self, dest: Path, slug: str) -> ScaffoldResult:
        dest.mkdir(parents=True, exist_ok=False)
        pkg = re.sub(r"[^a-z0-9_]", "_", slug)
        title = self._title_case(slug)
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
            f'print("Hello from {title} — run me, rack a win, tell Jarvis.")\n'
            f'print("Package: {pkg}")\n',
            encoding="utf-8",
        )
        (mod / "score.py").write_text(
            '"""Local score helper — Jarvis can also track via publish/scaffold."""\n'
            "SCORE = 0\n\n"
            "def bump(n: int = 1) -> int:\n"
            "    global SCORE\n"
            "    SCORE += n\n"
            "    return SCORE\n",
            encoding="utf-8",
        )
        (dest / "README.md").write_text(
            f"# {title}\n\n```bash\n{sys.executable} -m {pkg}\n```\n",
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
  <meta name="theme-color" content="#050b12" />
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700&family=Sora:wght@400;600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <div class="aurora"></div>
  <div class="app">
    <header>
      <p class="eyebrow">Jarvis Pulse · static</p>
      <h1>{title}</h1>
      <p class="sub">Searchable arena with live filters + local scoreboard.</p>
      <div class="scorebar">
        <div class="chip"><span>Score</span><b id="score">0</b></div>
        <div class="chip"><span>Best</span><b id="best">0</b></div>
        <div class="chip"><span>Showing</span><b id="showing">0</b></div>
      </div>
    </header>
    <div class="toolbar">
      <input id="q" type="search" placeholder="Search cards…" aria-label="Search" />
      <div id="tags" class="tags"></div>
    </div>
    <div id="grid" class="grid"></div>
  </div>
  <script src="app.js"></script>
</body>
</html>
""",
            encoding="utf-8",
        )
        (dest / "styles.css").write_text(
            """:root{--bg:#050b12;--panel:#0a1622;--line:rgba(0,240,255,.2);--text:#e7f6ff;--muted:#7f9bb0;--cyan:#00f0ff;--amber:#ffc14a}
*{box-sizing:border-box}body{margin:0;font-family:Sora,system-ui,sans-serif;background:var(--bg);color:var(--text)}
.aurora{position:fixed;inset:-10% 0 auto;height:50vh;background:radial-gradient(circle at 20% 40%,rgba(0,240,255,.2),transparent 45%),radial-gradient(circle at 80% 10%,rgba(255,193,74,.14),transparent 40%);pointer-events:none;filter:blur(6px)}
.app{position:relative;max-width:980px;margin:0 auto;padding:2rem 1.25rem 3rem}
.eyebrow{letter-spacing:.16em;text-transform:uppercase;color:var(--cyan);font-size:.72rem;font-weight:700;margin:0 0 .4rem}
h1{margin:0 0 .4rem;font-family:Orbitron,sans-serif;font-size:clamp(2rem,5vw,3rem);background:linear-gradient(110deg,#fff,var(--cyan),var(--amber));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--muted);margin:0 0 1rem}
.scorebar{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem}
.chip{background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:.45rem .85rem;display:flex;gap:.45rem;align-items:baseline}
.chip span{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.chip b{font-family:Orbitron,sans-serif;color:var(--cyan)}
.toolbar{display:flex;flex-wrap:wrap;gap:.75rem;margin-bottom:1rem}
#q{flex:1;min-width:200px;padding:.8rem 1rem;border-radius:14px;border:1px solid var(--line);background:var(--panel);color:var(--text);font:inherit}
.tags{display:flex;flex-wrap:wrap;gap:.4rem}
.tag{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:.45rem .75rem;cursor:pointer;font:inherit}
.tag.on{background:linear-gradient(120deg,var(--cyan),#7dfff0);color:#041018;border-color:transparent;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.75rem}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:1rem;transition:transform .15s,border-color .15s;cursor:pointer}
.card:hover{transform:translateY(-3px);border-color:rgba(0,240,255,.5)}
.card h3{margin:.25rem 0;font-size:1.05rem}
.card p{margin:0;color:var(--muted);font-size:.92rem}
.pill{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--amber)}
""",
            encoding="utf-8",
        )
        (dest / "app.js").write_text(
            f"""const APP_ID = {json.dumps(slug)};
const APP_TITLE = {json.dumps(title)};
const SCORE_URL = 'http://127.0.0.1:8766/api/scores';
const DATA = [
  {{ title: 'Neon Briefing', tag: 'Ops', blurb: 'Morning pack with weather and priorities.', power: 90 }},
  {{ title: 'Vault Notes', tag: 'Memory', blurb: 'Pinned facts for quick recall.', power: 72 }},
  {{ title: 'Signal Desk', tag: 'Comms', blurb: 'Starred threads and drafts.', power: 85 }},
  {{ title: 'Forge Lab', tag: 'Build', blurb: 'Active builds and ship checklist.', power: 94 }},
  {{ title: 'Atlas Map', tag: 'Travel', blurb: 'Saved places and routes.', power: 78 }},
  {{ title: 'Healer Bay', tag: 'System', blurb: 'CPU and process health.', power: 83 }},
];
const TAGS = ['All', ...new Set(DATA.map(d => d.tag))];
let tag = 'All';
let score = Number(localStorage.getItem(APP_ID + ':score') || 0);
let best = Number(localStorage.getItem(APP_ID + ':best') || 0);
const q = document.getElementById('q');
const grid = document.getElementById('grid');
const tagsEl = document.getElementById('tags');

function saveScore() {{
  localStorage.setItem(APP_ID + ':score', String(score));
  localStorage.setItem(APP_ID + ':best', String(best));
  document.getElementById('score').textContent = score;
  document.getElementById('best').textContent = best;
}}

function track(kind, points, label) {{
  score += points;
  best = Math.max(best, score);
  saveScore();
  fetch(SCORE_URL, {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ app_id: APP_ID, title: APP_TITLE, kind, points, label }}),
    mode: 'cors',
    keepalive: true,
  }}).catch(() => {{}});
}}

function renderTags() {{
  tagsEl.innerHTML = TAGS.map(t =>
    `<button class="tag ${{t === tag ? 'on' : ''}}" data-tag="${{t}}">${{t}}</button>`
  ).join('');
  tagsEl.querySelectorAll('.tag').forEach(btn => {{
    btn.onclick = () => {{ tag = btn.dataset.tag; track('action', 1, 'filter'); render(); }};
  }});
}}

function render() {{
  const query = (q.value || '').trim().toLowerCase();
  const rows = DATA.filter(d => {{
    const tagOk = tag === 'All' || d.tag === tag;
    if (!tagOk) return false;
    if (!query) return true;
    return (d.title + d.blurb + d.tag).toLowerCase().includes(query);
  }});
  document.getElementById('showing').textContent = rows.length;
  grid.innerHTML = rows.map(d =>
    `<article class="card" data-title="${{d.title}}"><div class="pill">${{d.tag}} · ${{d.power}}</div><h3>${{d.title}}</h3><p>${{d.blurb}}</p></article>`
  ).join('') || '<p class="sub">No matches.</p>';
  grid.querySelectorAll('.card').forEach(card => {{
    card.onclick = () => track('score', 5, 'inspect ' + card.dataset.title);
  }});
  renderTags();
}}

q.addEventListener('input', () => {{
  if ((q.value || '').trim().length === 1) track('search', 2, 'search');
  render();
}});
track('visit', 5, 'session');
saveScore();
render();
""",
            encoding="utf-8",
        )
        try:
            from jarvis.core import app_scores

            app_scores.ingest(
                {
                    "app_id": slug,
                    "title": title,
                    "kind": "action",
                    "points": 10,
                    "label": "scaffold",
                }
            )
        except Exception:
            pass
        return ScaffoldResult(
            ok=True,
            message=f"HTML Pulse “{title}” ready at {dest}.",
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

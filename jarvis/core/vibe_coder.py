"""Autonomous vibe-coding agent — invents apps, writes multi-file projects, ships."""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR

VIBE_DIR = DATA_DIR / "vibe_projects"
META_PATH = DATA_DIR / "vibe_index.json"

_INVENTIONS = (
    ("Neon Pulse Tracker", "web", "habit streaks with a cyber HUD"),
    ("Forge Notes", "web", "minimal markdown notes that feel like a terminal"),
    ("Orbit Todo", "web", "space-themed task board with local storage"),
    ("Signal Board", "dashboard", "live ops status tiles for a one-person team"),
    ("Echo Timer", "web", "focus timer with ambient pulse rings"),
    ("Vault Cards", "web", "flashcard drill with keyboard shortcuts"),
    ("Drift Weather", "web", "atmospheric local weather mood board"),
    ("Pixel Duel", "game", "tiny arena shooter you can play in the browser"),
    ("Lattice Calc", "python", "CLI unit converter and quick math helper"),
    ("Night Log", "python", "daily journal CLI that writes markdown files"),
    ("Relay Chat UI", "web", "fake realtime chat mockup for demos"),
    ("Prism Palette", "web", "color palette generator with copy-to-clipboard"),
)


class VibeCoder:
    """
    Full-stack vibe agent with HITL:
      autonomous invent → generate → sandbox write,
      pauses before massive multi-file scaffolds and before opening IDE (deploy).
      Zero-setup: projects under jarvis/data/vibe_projects (Python/static preferred).
    """

    def __init__(self, hitl=None) -> None:
        from jarvis.core.zero_env import ensure_agent_dirs

        ensure_agent_dirs()
        VIBE_DIR.mkdir(parents=True, exist_ok=True)
        if not META_PATH.exists():
            META_PATH.write_text(json.dumps({"projects": []}, indent=2), encoding="utf-8")
        self.hitl = hitl
        self.last_project: Path | None = None
        self.last_entry: Path | None = None
        self.last_prompt = ""
        self.last_meta: dict[str, Any] = {}
        self.last_brief = ""
        self.last_files: list[str] = []
        self.last_engine = "template"

    def build(
        self,
        brief: str = "",
        *,
        open_when_done: bool = True,
        ide: str = "code",
        on_progress: Callable[[str], None] | None = None,
        hitl=None,
    ) -> str:
        def progress(msg: str) -> None:
            if on_progress:
                try:
                    on_progress(msg)
                except Exception:
                    pass

        gate = hitl or self.hitl

        brief = (brief or "").strip()
        brief = self._normalize_brief(brief)
        self.last_brief = brief

        if self._is_vague(brief):
            progress("Inventing a product concept…")
            concept = self._invent()
            brief = (
                f"Build {concept['name']}: a {concept['stack']} app — {concept['pitch']}."
            )
            self.last_brief = brief
        else:
            stack = self._guess_stack(brief)
            name = self._guess_name(brief) or self._name_from_brief(brief)
            if not name:
                progress("Inventing a product name…")
                matches = [x for x in _INVENTIONS if x[1] == stack]
                pick = random.choice(matches or _INVENTIONS)
                name = pick[0]
            concept = {
                "name": name,
                "stack": stack,
                "pitch": brief[:160],
            }

        progress(f"Writing agent brief for {concept['name']}…")
        prompt = self._write_prompt(brief, concept)
        self.last_prompt = prompt

        slug = self._slug(concept["name"])
        out_dir = VIBE_DIR / slug
        rebuild = out_dir.exists() and any(out_dir.iterdir())
        if rebuild:
            slug = f"{slug}-{datetime.now().strftime('%H%M%S')}"
            out_dir = VIBE_DIR / slug
            rebuild = False
        out_dir.mkdir(parents=True, exist_ok=True)

        files: dict[str, str] | None = None
        engine = "template"

        # 1) Cursor SDK if keyed
        progress("Checking Cursor agent…")
        files = self._try_cursor_sdk(prompt, out_dir, progress)
        if files:
            engine = "cursor-sdk"
        else:
            # 2) Local Ollama
            progress("Generating project files with local model…")
            files = self._generate_with_ollama(prompt, concept)
            if files:
                engine = "ollama"
            else:
                progress("Using high-quality vibe templates…")
                files = self._template_project(concept)
                engine = "template"

        total_bytes = sum(len(c.encode("utf-8", errors="ignore")) for c in files.values())
        if gate is not None:
            from jarvis.core.hitl import is_massive_structure

            if is_massive_structure(
                file_count=len(files), total_bytes=total_bytes, rebuild=rebuild
            ):
                progress("HITL pause — massive structural write needs permission…")
                if not gate.gate_structure(
                    what=f"{concept['name']} · {len(files)} files ({engine})",
                    file_count=len(files),
                    rebuild=rebuild,
                    agent="vibe",
                    path=str(out_dir),
                ):
                    progress("HITL denied — structural write aborted")
                    return (
                        f"Paused by HITL. {concept['name']} was generated in memory "
                        "but not written. Say approve on the next run to scaffold."
                    )

        progress(f"Writing {len(files)} files…")
        written: list[str] = []
        for rel, content in files.items():
            path = out_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(rel.replace("\\", "/"))

        # Always ensure README
        if "README.md" not in files:
            readme = self._readme(concept, engine, written)
            (out_dir / "README.md").write_text(readme, encoding="utf-8")
            written.append("README.md")

        entry = self._pick_entry(out_dir, written)
        self.last_project = out_dir
        self.last_entry = entry
        self.last_files = written
        self.last_engine = engine
        self.last_meta = {
            "name": concept["name"],
            "stack": concept["stack"],
            "pitch": concept.get("pitch") or "",
            "engine": engine,
            "files": written,
            "path": str(out_dir),
            "entry": str(entry) if entry else "",
            "zero_setup": True,
        }
        self._index_project(slug, self.last_meta)

        (out_dir / "vibe.json").write_text(
            json.dumps(self.last_meta, indent=2), encoding="utf-8"
        )
        (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        try:
            from jarvis.core.zero_env import write_env_manifest

            write_env_manifest(
                out_dir,
                stack=str(concept.get("stack") or "web"),
                files=written,
            )
        except Exception:
            pass

        if open_when_done:
            deploy_ok = True
            if gate is not None:
                progress("HITL pause — open project in IDE?")
                deploy_ok = gate.gate_deploy(
                    what=f"Open {concept['name']} in {ide}",
                    path=str(out_dir),
                    agent="vibe",
                )
            if deploy_ok:
                progress("Opening project in IDE…")
                self.open_in_ide(out_dir, ide=ide)
            else:
                progress("HITL denied IDE open — HUD sandbox only")

        n = len(written)
        return (
            f"Vibe complete — {concept['name']} ({concept['stack']}) with {n} files "
            f"via {engine}. Preview is on your HUD."
        )

    def open_last(self) -> str:
        if not self.last_project or not self.last_project.exists():
            return "No vibe project yet — say start vibe coding."
        self.open_in_ide(self.last_project)
        return f"Opening {self.last_meta.get('name') or self.last_project.name}."

    def list_projects(self) -> str:
        try:
            data = json.loads(META_PATH.read_text(encoding="utf-8"))
            projects = data.get("projects") or []
        except Exception:
            projects = []
        if not projects:
            return "No vibe projects yet."
        lines = [
            f"{i+1}. {p.get('name')} — {p.get('stack')} ({p.get('engine')})"
            for i, p in enumerate(projects[-8:][::-1])
        ]
        return "Recent vibe projects: " + "; ".join(lines)

    def open_in_ide(self, path: Path, *, ide: str = "code") -> None:
        path = Path(path)
        cmds = []
        # Prefer Cursor, then VS Code, then explorer
        for cmd in ("cursor", ide or "code", "code"):
            if cmd and cmd not in cmds:
                cmds.append(cmd)
        for cmd in cmds:
            try:
                subprocess.Popen(
                    [cmd, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                continue
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception:
            pass

    # ── invent / classify ───────────────────────────────────────
    def _invent(self) -> dict[str, str]:
        name, stack, pitch = random.choice(_INVENTIONS)
        return {"name": name, "stack": stack, "pitch": pitch}

    def _is_vague(self, brief: str) -> bool:
        if not brief:
            return True
        vague = (
            r"^(a |an |the )?(app|project|something|anything|one|it|code|"
            r"vibe|vibing|program|tool)$"
        )
        if re.match(vague, brief.strip(), re.I):
            return True
        return len(brief.split()) < 3 and not self._guess_name(brief)

    def _normalize_brief(self, brief: str) -> str:
        brief = re.sub(
            r"^(please |jarvis |can you |could you |i want you to |go ahead and )+",
            "",
            brief,
            flags=re.I,
        ).strip()
        brief = re.sub(
            r"^(start |do |run )?(autonomous )?(ai )?(agent )?"
            r"(development|coding|code )?vibe( coding|ing)?\s*(and |to |for )?",
            "",
            brief,
            flags=re.I,
        ).strip()
        brief = re.sub(
            r"^(build|make|create|generate|code|vibe|ship)\s+(me |us |a |an |the )*",
            "",
            brief,
            flags=re.I,
        ).strip()
        return brief

    def _guess_name(self, brief: str) -> str | None:
        m = re.search(
            r"(?:called|named|brand(?:ed)?)\s+[\"']?([A-Z][\w]+(?:\s+[A-Z][\w]+){0,3})",
            brief,
        )
        if m:
            return m.group(1).strip()
        m = re.search(r"^([A-Z][\w]+(?:\s+[A-Z][\w]+){0,2})\b", brief)
        if m and len(m.group(1)) > 2:
            return m.group(1)
        return None

    def _name_from_brief(self, brief: str) -> str | None:
        stop = {
            "a", "an", "the", "me", "my", "for", "with", "and", "or", "to", "of",
            "app", "project", "web", "game", "tool", "cli", "tiny", "simple",
            "small", "new", "please", "build", "make", "create", "generate",
            "something", "that", "this", "like", "using", "in", "on",
        }
        words = [
            w for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", brief)
            if w.lower() not in stop
        ]
        if len(words) < 1:
            return None
        return " ".join(w.capitalize() for w in words[:3])

    def _guess_stack(self, brief: str) -> str:
        b = brief.lower()
        if any(w in b for w in ("game", "play", "arcade", "shooter", "puzzle")):
            return "game"
        if any(w in b for w in ("cli", "command line", "python script", "terminal")):
            return "python"
        if any(w in b for w in ("dashboard", "ops", "metrics", "status board")):
            return "dashboard"
        return "web"

    def _slug(self, name: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return s[:48] or "vibe-project"

    def _write_prompt(self, brief: str, concept: dict[str, str]) -> str:
        return (
            f"You are Jarvis, an autonomous vibe-coding agent.\n"
            f"Product: {concept['name']}\n"
            f"Stack hint: {concept['stack']}\n"
            f"Brief: {brief}\n\n"
            f"Ship a complete, runnable multi-file project. Prefer polished UI, "
            f"clear README, and zero half-finished stubs. Keep dependencies minimal."
        )

    def _pick_entry(self, out_dir: Path, files: list[str]) -> Path | None:
        for cand in ("index.html", "app.py", "main.py", "README.md"):
            if cand in files:
                return out_dir / cand
        if files:
            return out_dir / files[0]
        return out_dir

    # ── Cursor SDK (optional) ───────────────────────────────────
    def _try_cursor_sdk(
        self,
        prompt: str,
        out_dir: Path,
        progress: Callable[[str], None],
    ) -> dict[str, str] | None:
        api_key = os.environ.get("CURSOR_API_KEY") or os.environ.get("cursor_api_key")
        if not api_key:
            return None
        try:
            from cursor_sdk import Agent, LocalAgentOptions  # type: ignore

            progress("Cursor agent vibing on your machine…")
            with Agent.create(
                model="composer-2.5",
                api_key=api_key,
                local=LocalAgentOptions(cwd=str(out_dir)),
            ) as agent:
                run = agent.send(
                    prompt
                    + "\n\nWrite all files into the current working directory. "
                    "Create a complete runnable project with README.md."
                )
                run.wait()
            files: dict[str, str] = {}
            for path in out_dir.rglob("*"):
                if path.is_file() and path.stat().st_size < 400_000:
                    rel = str(path.relative_to(out_dir)).replace("\\", "/")
                    if any(rel.endswith(ext) for ext in (
                        ".py", ".html", ".css", ".js", ".ts", ".tsx",
                        ".json", ".md", ".txt", ".toml",
                    )):
                        try:
                            files[rel] = path.read_text(encoding="utf-8")
                        except Exception:
                            pass
            return files if files else None
        except Exception as e:
            print(f"[vibe] cursor-sdk unavailable: {e}")
            return None

    # ── Ollama generation ───────────────────────────────────────
    def _generate_with_ollama(
        self, prompt: str, concept: dict[str, str]
    ) -> dict[str, str] | None:
        system = (
            "Return ONLY valid JSON object mapping relative file paths to file contents. "
            "Example: {\"index.html\":\"...\",\"styles.css\":\"...\",\"README.md\":\"...\"}. "
            "No markdown fences. Include at least 3 files. Make it runnable."
        )
        user = (
            f"{prompt}\n\nStack: {concept['stack']}. "
            f"Name: {concept['name']}. Prefer vanilla HTML/CSS/JS unless python CLI."
        )
        raw = self._ollama_text(system, user, num_predict=3500)
        if not raw:
            return None
        data = self._parse_files_json(raw)
        if not data or len(data) < 2:
            return None
        # Sanity: values must be strings
        clean = {
            str(k).replace("\\", "/").lstrip("./"): str(v)
            for k, v in data.items()
            if isinstance(v, str) and len(v) > 10
        }
        return clean if len(clean) >= 2 else None

    def _parse_files_json(self, raw: str) -> dict | None:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            m = re.search(r"\{[\s\S]+\}", raw)
            if not m:
                return None
            try:
                data = json.loads(m.group(0))
                return data if isinstance(data, dict) else None
            except Exception:
                return None

    def _ollama_text(self, system: str, user: str, *, num_predict: int = 200) -> str | None:
        try:
            model = self._ollama_model()
            if not model:
                return None
            payload = {
                "model": model,
                "prompt": f"{system}\n\n{user}",
                "stream": False,
                "options": {"temperature": 0.55, "num_predict": num_predict},
            }
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = (data.get("response") or "").strip()
            return text if len(text) > 40 else None
        except Exception:
            return None

    def _ollama_model(self) -> str | None:
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names = [m.get("name", "") for m in data.get("models") or []]
            for pref in ("qwen", "llama", "mistral", "phi", "gemma", "codellama", "deepseek"):
                for n in names:
                    if pref in n.lower():
                        return n
            return names[0] if names else None
        except Exception:
            return None

    # ── templates ───────────────────────────────────────────────
    def _template_project(self, concept: dict[str, str]) -> dict[str, str]:
        stack = concept["stack"]
        name = concept["name"]
        pitch = concept.get("pitch") or "a sharp little tool"
        if stack == "python":
            return self._tpl_python(name, pitch)
        if stack == "game":
            return self._tpl_game(name, pitch)
        if stack == "dashboard":
            return self._tpl_dashboard(name, pitch)
        return self._tpl_web(name, pitch)

    def _readme(self, concept: dict[str, str], engine: str, files: list[str]) -> str:
        entry = "index.html"
        for f in files:
            if f.endswith((".html", ".py")):
                entry = f
                break
        how = (
            f"Open `{entry}` in a browser."
            if entry.endswith(".html")
            else f"Run `python {entry}`."
        )
        return (
            f"# {concept['name']}\n\n"
            f"{concept.get('pitch') or ''}\n\n"
            f"**Stack:** {concept['stack']}  \n"
            f"**Built by:** Jarvis vibe agent ({engine})\n\n"
            f"## Run\n\n{how}\n\n"
            f"## Files\n\n"
            + "\n".join(f"- `{f}`" for f in files)
            + "\n"
        )

    def _tpl_web(self, name: str, pitch: str) -> dict[str, str]:
        safe = _esc(name)
        return {
            "index.html": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{safe}</title>
<link rel="stylesheet" href="styles.css"/>
</head>
<body>
  <div class="bg"></div>
  <main>
    <p class="eyebrow">JARVIS · VIBE BUILD</p>
    <h1>{safe}</h1>
    <p class="lead">{_esc(pitch)}</p>
    <section class="panel">
      <h2>Today</h2>
      <form id="form">
        <input id="input" placeholder="Add something…" autocomplete="off"/>
        <button type="submit">Add</button>
      </form>
      <ul id="list"></ul>
    </section>
  </main>
  <script src="app.js"></script>
</body>
</html>
""",
            "styles.css": """:root {
  --cyan: #00e8ff; --void: #05070c; --panel: rgba(8,16,24,.88); --text: #e8f4ff; --dim: #7a93a8;
}
* { box-sizing: border-box; }
body {
  margin: 0; min-height: 100vh; font-family: "Bahnschrift", "Segoe UI", sans-serif;
  color: var(--text); background: var(--void); overflow-x: hidden;
}
.bg {
  position: fixed; inset: 0; z-index: -1;
  background:
    radial-gradient(900px 500px at 10% 0%, rgba(0,232,255,.18), transparent 55%),
    radial-gradient(700px 400px at 90% 100%, rgba(255,107,53,.12), transparent 50%),
    linear-gradient(160deg, #05070c, #0a1520 60%, #05070c);
}
main { max-width: 720px; margin: 0 auto; padding: 64px 24px 80px; }
.eyebrow { letter-spacing: .28em; font-size: 11px; color: var(--cyan); margin: 0 0 14px; }
h1 {
  margin: 0; font-size: clamp(2.4rem, 6vw, 3.6rem); letter-spacing: .04em;
  text-transform: uppercase; line-height: 1.05;
}
.lead { color: var(--dim); font-size: 1.05rem; max-width: 38ch; margin: 16px 0 36px; }
.panel {
  background: var(--panel); border: 1px solid rgba(0,232,255,.28);
  border-left: 3px solid var(--cyan); padding: 22px; backdrop-filter: blur(10px);
}
.panel h2 { margin: 0 0 14px; font-size: 13px; letter-spacing: .2em; color: var(--cyan); }
form { display: flex; gap: 10px; margin-bottom: 16px; }
input {
  flex: 1; background: #02080e; border: 1px solid rgba(0,232,255,.25);
  color: var(--text); padding: 12px 14px; font: inherit;
}
button {
  background: transparent; border: 1px solid var(--cyan); color: var(--cyan);
  padding: 0 18px; letter-spacing: .12em; cursor: pointer; text-transform: uppercase;
}
button:hover { background: rgba(0,232,255,.12); }
ul { list-style: none; margin: 0; padding: 0; }
li {
  display: flex; justify-content: space-between; gap: 12px;
  padding: 12px 0; border-bottom: 1px solid rgba(122,147,168,.2);
}
li.done span { opacity: .45; text-decoration: line-through; }
li button { border: none; color: var(--dim); padding: 0; letter-spacing: 0; }
""",
            "app.js": f"""const KEY = "vibe:{_esc(name).lower().replace(' ', '-')}";
const list = document.getElementById("list");
const form = document.getElementById("form");
const input = document.getElementById("input");

function load() {{
  try {{ return JSON.parse(localStorage.getItem(KEY) || "[]"); }}
  catch {{ return []; }}
}}
function save(items) {{ localStorage.setItem(KEY, JSON.stringify(items)); }}

function render() {{
  const items = load();
  list.innerHTML = "";
  items.forEach((item, i) => {{
    const li = document.createElement("li");
    if (item.done) li.classList.add("done");
    const span = document.createElement("span");
    span.textContent = item.text;
    span.style.cursor = "pointer";
    span.onclick = () => {{
      items[i].done = !items[i].done;
      save(items); render();
    }};
    const del = document.createElement("button");
    del.textContent = "✕";
    del.onclick = () => {{ items.splice(i, 1); save(items); render(); }};
    li.append(span, del);
    list.appendChild(li);
  }});
}}

form.addEventListener("submit", (e) => {{
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  const items = load();
  items.unshift({{ text, done: false }});
  save(items);
  input.value = "";
  render();
}});

render();
""",
            "README.md": self._readme(
                {"name": name, "stack": "web", "pitch": pitch}, "template",
                ["index.html", "styles.css", "app.js", "README.md"],
            ),
        }

    def _tpl_game(self, name: str, pitch: str) -> dict[str, str]:
        safe = _esc(name)
        return {
            "index.html": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{safe}</title>
<style>
  html,body{{margin:0;height:100%;background:#05070c;color:#e8f4ff;font-family:Bahnschrift,Segoe UI,sans-serif}}
  #wrap{{display:grid;place-items:center;height:100%;gap:12px}}
  canvas{{border:1px solid rgba(0,232,255,.4);background:#02080e;box-shadow:0 0 40px rgba(0,232,255,.12)}}
  p{{letter-spacing:.2em;font-size:12px;color:#00e8ff;margin:0}}
  .dim{{color:#7a93a8;letter-spacing:.08em}}
</style>
</head>
<body>
<div id="wrap">
  <p>{safe}</p>
  <canvas id="c" width="480" height="320"></canvas>
  <p class="dim">ARROWS MOVE · SPACE SHOOT · {_esc(pitch).upper()}</p>
</div>
<script src="game.js"></script>
</body>
</html>
""",
            "game.js": """const c = document.getElementById("c");
const ctx = c.getContext("2d");
const keys = {};
addEventListener("keydown", e => keys[e.code] = true);
addEventListener("keyup", e => keys[e.code] = false);

let player = { x: 240, y: 260, w: 28, h: 16 };
let bullets = [];
let foes = [];
let score = 0;
let tick = 0;
let alive = true;

function spawn() {
  foes.push({ x: 40 + Math.random() * 400, y: -20, s: 1.2 + Math.random() * 1.5 });
}

function loop() {
  tick++;
  ctx.fillStyle = "#02080e";
  ctx.fillRect(0, 0, c.width, c.height);
  // grid
  ctx.strokeStyle = "rgba(0,232,255,0.06)";
  for (let x = 0; x < c.width; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, c.height); ctx.stroke();
  }

  if (alive) {
    if (keys.ArrowLeft) player.x -= 4;
    if (keys.ArrowRight) player.x += 4;
    player.x = Math.max(0, Math.min(c.width - player.w, player.x));
    if (keys.Space && tick % 12 === 0) {
      bullets.push({ x: player.x + player.w / 2, y: player.y });
    }
    if (tick % 45 === 0) spawn();
  }

  bullets = bullets.filter(b => b.y > -10);
  bullets.forEach(b => { b.y -= 7; ctx.fillStyle = "#00e8ff"; ctx.fillRect(b.x - 2, b.y, 4, 10); });

  foes.forEach(f => {
    f.y += f.s;
    ctx.fillStyle = "#ff6b35";
    ctx.fillRect(f.x, f.y, 22, 16);
  });

  for (let i = foes.length - 1; i >= 0; i--) {
    const f = foes[i];
    if (f.y > c.height) { foes.splice(i, 1); continue; }
    if (f.y + 16 > player.y && f.x < player.x + player.w && f.x + 22 > player.x) alive = false;
    for (let j = bullets.length - 1; j >= 0; j--) {
      const b = bullets[j];
      if (b.x > f.x && b.x < f.x + 22 && b.y > f.y && b.y < f.y + 16) {
        foes.splice(i, 1); bullets.splice(j, 1); score += 10; break;
      }
    }
  }

  ctx.fillStyle = "#00e8ff";
  ctx.fillRect(player.x, player.y, player.w, player.h);
  ctx.fillStyle = "#e8f4ff";
  ctx.font = "14px Bahnschrift";
  ctx.fillText("SCORE " + score, 12, 22);
  if (!alive) {
    ctx.fillStyle = "rgba(5,7,12,.7)";
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.fillStyle = "#00e8ff";
    ctx.font = "28px Bahnschrift";
    ctx.fillText("SYSTEMS DOWN", 140, 150);
    ctx.font = "14px Bahnschrift";
    ctx.fillText("Press R to reboot", 180, 180);
    if (keys.KeyR) {
      alive = true; score = 0; foes = []; bullets = []; player.x = 240;
    }
  }
  requestAnimationFrame(loop);
}
loop();
""",
            "README.md": self._readme(
                {"name": name, "stack": "game", "pitch": pitch}, "template",
                ["index.html", "game.js", "README.md"],
            ),
        }

    def _tpl_dashboard(self, name: str, pitch: str) -> dict[str, str]:
        safe = _esc(name)
        return {
            "index.html": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{safe}</title>
<link rel="stylesheet" href="styles.css"/>
</head>
<body>
  <header>
    <div>
      <p class="eyebrow">OPS · LIVE</p>
      <h1>{safe}</h1>
      <p class="lead">{_esc(pitch)}</p>
    </div>
    <div class="clock" id="clock">--:--:--</div>
  </header>
  <section class="grid" id="grid"></section>
  <script src="app.js"></script>
</body>
</html>
""",
            "styles.css": """:root { --cyan:#00e8ff; --void:#05070c; --text:#e8f4ff; --dim:#7a93a8; }
* { box-sizing:border-box; }
body {
  margin:0; min-height:100vh; padding:36px; color:var(--text);
  font-family:Bahnschrift,Segoe UI,sans-serif;
  background:
    radial-gradient(800px 400px at 0% 0%, rgba(0,232,255,.14), transparent 50%),
    linear-gradient(165deg,#05070c,#0b1520 55%,#05070c);
}
header { display:flex; justify-content:space-between; gap:24px; align-items:end; margin-bottom:28px; }
.eyebrow { margin:0; letter-spacing:.28em; color:var(--cyan); font-size:11px; }
h1 { margin:8px 0 0; font-size:clamp(2rem,5vw,3rem); letter-spacing:.06em; text-transform:uppercase; }
.lead { color:var(--dim); max-width:40ch; }
.clock { font-size:28px; letter-spacing:.12em; color:var(--cyan); }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; }
.tile {
  background:rgba(8,16,24,.9); border:1px solid rgba(0,232,255,.22);
  border-left:3px solid var(--cyan); padding:18px;
}
.tile h3 { margin:0; font-size:12px; letter-spacing:.18em; color:var(--dim); }
.tile .val { margin-top:10px; font-size:2rem; color:var(--cyan); }
.tile .sub { margin-top:6px; color:var(--dim); font-size:13px; }
""",
            "app.js": """const tiles = [
  { key: "cpu", label: "CPU LOAD", unit: "%", base: 34 },
  { key: "mem", label: "MEMORY", unit: "%", base: 58 },
  { key: "req", label: "REQ / MIN", unit: "", base: 120 },
  { key: "err", label: "ERROR RATE", unit: "%", base: 0.4 },
  { key: "lat", label: "LATENCY", unit: "ms", base: 86 },
  { key: "jobs", label: "QUEUE", unit: "", base: 7 },
];
const grid = document.getElementById("grid");
const clock = document.getElementById("clock");

function render() {
  grid.innerHTML = "";
  tiles.forEach(t => {
    const wobble = (Math.random() - 0.5) * (t.base * 0.08 + 1);
    const val = Math.max(0, t.base + wobble);
    const show = t.unit === "%" ? val.toFixed(1) : Math.round(val);
    const el = document.createElement("div");
    el.className = "tile";
    el.innerHTML = `<h3>${t.label}</h3><div class="val">${show}${t.unit}</div>
      <div class="sub">simulated live feed</div>`;
    grid.appendChild(el);
  });
  clock.textContent = new Date().toLocaleTimeString();
}
render();
setInterval(render, 1500);
""",
            "README.md": self._readme(
                {"name": name, "stack": "dashboard", "pitch": pitch}, "template",
                ["index.html", "styles.css", "app.js", "README.md"],
            ),
        }

    def _tpl_python(self, name: str, pitch: str) -> dict[str, str]:
        safe_name = name.replace('"', "'")
        safe_pitch = pitch.replace('"', "'")
        main = f'''#!/usr/bin/env python3
"""{safe_name} — {safe_pitch}. Built by Jarvis vibe agent."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).with_name("journal.md")


def add_entry(text: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"## {{stamp}}\\n\\n{{text.strip()}}\\n\\n"
    prev = LOG.read_text(encoding="utf-8") if LOG.exists() else "# {safe_name}\\n\\n"
    LOG.write_text(prev + block, encoding="utf-8")
    print(f"Logged → {{LOG}}")


def show() -> None:
    if not LOG.exists():
        print("No entries yet.")
        return
    print(LOG.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser(description="{safe_name}: {safe_pitch}")
    p.add_argument("text", nargs="*", help="Journal entry text")
    p.add_argument("--show", action="store_true", help="Print the journal")
    args = p.parse_args()
    if args.show:
        show()
        return
    if not args.text:
        p.print_help()
        return
    add_entry(" ".join(args.text))


if __name__ == "__main__":
    main()
'''
        return {
            "main.py": main,
            "requirements.txt": "# stdlib only\n",
            "README.md": self._readme(
                {"name": name, "stack": "python", "pitch": pitch}, "template",
                ["main.py", "requirements.txt", "README.md"],
            ),
        }

    def _index_project(self, slug: str, meta: dict[str, Any]) -> None:
        try:
            data = json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {"projects": []}
        projects = data.setdefault("projects", [])
        projects.append(
            {
                "slug": slug,
                "name": meta.get("name"),
                "stack": meta.get("stack"),
                "engine": meta.get("engine"),
                "path": meta.get("path"),
                "created": datetime.now().isoformat(timespec="seconds"),
            }
        )
        META_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

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
    ("Kairos Clock", "web", "world clocks plus a stopwatch and alarms list"),
    ("Budget Spark", "web", "expense tracker with categories and running total"),
    ("Mood Ring Desk", "web", "daily mood logger with emoji streak chart"),
    ("Recipe Rail", "web", "save recipes, ingredients checklist, cook timer"),
    ("Quest Board", "web", "gamified daily quests with XP and levels"),
    ("Snippet Vault", "web", "code snippet library with tags and search"),
    ("Pomodoro Forge", "web", "25/5 focus cycles with session history"),
    ("Ink Drop Journal", "web", "rich text daily journal with search"),
    ("Cartographer Pins", "web", "pin places you want to visit with notes"),
    ("Beat Pad Lite", "web", "clickable drum pads with keyboard triggers"),
    ("Checklist Arena", "web", "shared-style checklists with progress bars"),
    ("Spark Debate", "web", "pros vs cons board that scores your arguments"),
    ("Hydration Ping", "web", "water intake tracker with reminders log"),
    ("Film Strip Rank", "web", "rate movies you watched and filter by score"),
    ("Garden Bed Plan", "web", "plot plants in a grid and track watering"),
    ("Interview Drill", "web", "practice interview questions with a timer"),
    ("Tip Split Fair", "web", "split bills and tips between friends"),
    ("Glow Stretch", "web", "guided stretch routine with countdown steps"),
    ("Inbox Zero Toy", "web", "fake inbox triage game that sorts mail cards"),
    ("Crypto Watch Toy", "web", "mock price tickers you can favorite"),
    ("Story Dice", "web", "roll prompt dice and write a micro-story"),
    ("Contraption Lab", "web", "drag parts to build a silly machine score"),
    ("Shadow Boxer", "game", "timing game — punch on the flash"),
    ("Maze Runner Mini", "game", "arrow-key maze with score and levels"),
    ("Unit Warp", "python", "CLI converter for length, weight, temp, time"),
    ("Git Blame Lite", "python", "CLI that summarizes a folder of text files"),
    ("Server Pulse", "dashboard", "fake service health cards with latency"),
    ("Launch Checklist", "dashboard", "pre-flight deploy checklist with owners"),
    # Games + videos bias
    ("Neon Snake Arena", "game", "classic snake with levels pause and high score"),
    ("Pulse Runner", "game", "endless runner jump dodge collect gems"),
    ("Orb Breaker", "game", "breakout bricks with powerups and lives"),
    ("Star Dual", "game", "two-button duel shooter with waves"),
    ("Reel Mood Studio", "video", "slideshow video reel from research images"),
    ("Caption Cut", "video", "captioned image filmstrip with export frame"),
    ("Night Trailer", "video", "cinematic trailer cards with music-free beats"),
    ("Storyboard Flip", "video", "storyboard frames play as a looping video"),
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
        self.last_research: dict[str, Any] = {}

    def build(
        self,
        brief: str = "",
        *,
        open_when_done: bool = True,
        ide: str = "code",
        on_progress: Callable[[str | dict], None] | None = None,
        hitl=None,
    ) -> str:
        def progress(msg: str, **extra) -> None:
            if not on_progress:
                return
            try:
                if extra:
                    payload = {"msg": msg, **extra}
                    on_progress(payload)  # type: ignore[arg-type]
                else:
                    on_progress(msg)
            except Exception:
                pass

        gate = hitl or self.hitl

        brief = (brief or "").strip()
        brief = self._normalize_brief(brief)
        self.last_brief = brief

        if self._is_vague(brief):
            progress(
                "Inventing a product concept…",
                agent_stage="plan",
                tab="working",
                plan=[
                    "Invent concept",
                    "Research web + images",
                    "Draft prompts",
                    "Generate rich code",
                    "Sandbox preview",
                    "Publish (HITL)",
                ],
            )
            concept = self._invent()
            brief = (
                f"Build {concept['name']}: a {concept['stack']} app — {concept['pitch']}."
            )
            self.last_brief = brief
        else:
            stack = self._guess_stack(brief)
            name = self._guess_name(brief) or self._name_from_brief(brief)
            if not name:
                progress("Inventing a product name…", agent_stage="plan", tab="working")
                matches = [x for x in _INVENTIONS if x[1] == stack]
                pick = random.choice(matches or _INVENTIONS)
                name = pick[0]
            concept = {
                "name": name,
                "stack": stack,
                "pitch": brief[:160],
            }

        # ── Research: web prompts + images ──────────────────────
        research = self._research_pack(concept, progress)
        self.last_research = research
        concept["research"] = research

        progress(
            f"Writing agent brief for {concept['name']}…",
            agent_stage="prompt",
            tab="working",
            plan=[
                f"Product: {concept['name']}",
                f"Stack: {concept['stack']}",
                f"Images found: {len(research.get('images') or [])}",
                f"Prompts: {len(research.get('prompts') or [])}",
                "Generate multi-file project",
                "Sandbox preview → publish gate",
            ],
            research=research.get("hits") or [],
            images=research.get("images") or [],
            prompts=research.get("prompts") or [],
        )
        prompt = self._write_prompt(brief, concept, research=research)
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
        progress("Checking Cursor agent…", agent_stage="plan", tab="working")
        files = self._try_cursor_sdk(prompt, out_dir, progress)
        if files:
            engine = "cursor-sdk"
        else:
            # 2) Local Ollama
            progress(
                "Generating project files with local model…",
                agent_stage="code",
                tab="coding",
            )
            files = self._generate_with_ollama(prompt, concept, research=research)
            if files:
                engine = "ollama"
            else:
                progress(
                    "Using high-quality vibe templates (expanded)…",
                    agent_stage="code",
                    tab="coding",
                )
                files = self._template_project(concept, research=research)
                engine = "template"

        total_bytes = sum(len(c.encode("utf-8", errors="ignore")) for c in files.values())
        # Sandbox first scaffolds are autonomous (policy). Only rebuild / monster trees gate.
        if gate is not None and rebuild:
            from jarvis.core.hitl import is_massive_structure

            if is_massive_structure(
                file_count=len(files), total_bytes=total_bytes, rebuild=True
            ):
                progress(
                    "HITL pause — rebuilding existing project needs permission…",
                    agent_stage="hitl",
                    tab="building",
                )
                if not gate.gate_structure(
                    what=f"{concept['name']} · {len(files)} files ({engine})",
                    file_count=len(files),
                    rebuild=True,
                    agent="vibe",
                    path=str(out_dir),
                ):
                    progress(
                        "HITL denied — structural write aborted",
                        agent_stage="hitl",
                        tab="building",
                    )
                    return (
                        f"Paused by HITL. {concept['name']} was generated in memory "
                        "but not written. Say approve on the next run to scaffold."
                    )

        progress(
            f"Writing {len(files)} files…",
            agent_stage="code",
            tab="coding",
            terminal=f"write {len(files)} files → {out_dir.name}",
            plan=[
                f"Product: {concept['name']}",
                f"Stack: {concept['stack']}",
                f"Engine: {engine}",
                f"Files: {len(files)}",
                "Live typewriter + preview",
            ],
        )
        written: list[str] = []
        import time as _time

        for i, (rel, content) in enumerate(files.items()):
            path = out_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            # Stream “typing” chunks so the theater animates letters/words
            chunk_n = max(40, len(content) // 8)
            for start in range(0, min(len(content), 3200), chunk_n):
                piece = content[: start + chunk_n]
                progress(
                    f"Typing {rel.replace(chr(92), '/')}…",
                    agent_stage="code",
                    tab="coding",
                    file_path=rel.replace("\\", "/"),
                    code=piece,
                    chars=len(piece),
                    words=len(piece.split()),
                    file_index=i + 1,
                    file_total=len(files),
                )
                _time.sleep(0.05)
            path.write_text(content, encoding="utf-8")
            rel_n = rel.replace("\\", "/")
            written.append(rel_n)
            progress(
                f"Wrote {rel_n}",
                agent_stage="code",
                tab="coding",
                file_path=rel_n,
                code=content[:2400],
                terminal=f"+ {rel_n}",
                chars=len(content),
                words=len(content.split()),
                file_index=i + 1,
                file_total=len(files),
            )
            _time.sleep(0.12)
            # Prefer HTML preview when present
            if rel_n.lower().endswith((".html", ".htm")):
                progress(
                    f"Hot preview {rel_n}",
                    agent_stage="browser",
                    tab="building",
                    html=content if rel_n == "preview.html" or "preview" in rel_n else content,
                    images=research.get("images") or [],
                )

        # Force sandbox preview document into theater before publish gate
        preview_doc = files.get("preview.html") or files.get("index.html") or ""
        if preview_doc:
            progress(
                "Loading sandbox preview…",
                agent_stage="browser",
                tab="building",
                html=preview_doc,
                images=research.get("images") or [],
                research=research.get("hits") or [],
                prompts=research.get("prompts") or [],
            )

        # Always ensure README
        if "README.md" not in files:
            readme = self._readme(concept, engine, written)
            (out_dir / "README.md").write_text(readme, encoding="utf-8")
            written.append("README.md")
            progress(
                "Wrote README.md",
                agent_stage="code",
                tab="coding",
                file_path="README.md",
                code=readme[:1200],
            )

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
            # Serve runnable preview in theater — do NOT open File Explorer / IDE here
            try:
                preview_url = self._serve_preview(out_dir)
            except Exception as e:
                preview_url = ""
                print(f"[vibe] preview server: {e}")
            if preview_url:
                self.last_meta["preview_url"] = preview_url
                self.last_meta["app_url"] = preview_url
                try:
                    (out_dir / "vibe.json").write_text(
                        json.dumps(self.last_meta, indent=2), encoding="utf-8"
                    )
                except Exception:
                    pass
            progress(
                "Sandbox app preview ready — switching to PREVIEW tab",
                agent_stage="preview",
                tab="building",
                preview_url=preview_url,
                terminal=f"serve {preview_url}" if preview_url else "preview --html",
                images=research.get("images") or [],
                research=research.get("hits") or [],
                html=files.get("preview.html") or files.get("index.html") or "",
            )
            # Stay in Build Theater PREVIEW — no Chrome popup (smoother)
            progress(
                "Preview ready — say publish vibe only when you want Cursor",
                agent_stage="ship",
                tab="building",
                preview_url=preview_url,
            )

        n = len(written)
        progress(
            f"Vibe complete — {concept['name']} ({n} files via {engine})",
            agent_stage="ship",
            tab="building",
            images=research.get("images") or [],
        )
        return (
            f"Vibe complete — {concept['name']} with {n} files via {engine}. "
            f"I searched Google live for prompts and images, then built a sandbox preview. "
            f"Say publish vibe only when you want it in Cursor — I will not dump File Explorer."
        )

    def open_last(self) -> str:
        if not self.last_project or not self.last_project.exists():
            return "No vibe project yet — say start vibe coding."
        # Prefer live preview URL if server still up
        port = getattr(self, "_preview_port", None)
        if port:
            entry = (
                "preview.html"
                if (self.last_project / "preview.html").exists()
                else "index.html"
            )
            url = f"http://127.0.0.1:{port}/{entry}"
            self._open_chrome(url)
            return f"Opening live preview for {self.last_meta.get('name') or self.last_project.name}."
        try:
            url = self._serve_preview(self.last_project)
            self._open_chrome(url)
            return f"Opening live preview for {self.last_meta.get('name') or self.last_project.name}."
        except Exception:
            if self.open_in_ide(self.last_project):
                return f"Opening {self.last_meta.get('name') or self.last_project.name} in editor."
            return f"Project is at {self.last_project} — say publish vibe to open Cursor."

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

    def open_in_ide(self, path: Path, *, ide: str = "code") -> bool:
        """Open in Cursor/VS Code only — never fall back to File Explorer."""
        path = Path(path)
        cmds = []
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
                return True
            except Exception:
                continue
        return False

    def _open_chrome(self, url: str, *, new_window: bool = False) -> None:
        """Open URL in Chrome and leave the tab open (never close tabs)."""
        chrome_paths = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(os.environ.get("LOCALAPPDATA", ""))
            / r"Google\Chrome\Application\chrome.exe",
        ]
        chrome = next((p for p in chrome_paths if p.exists()), None)
        if chrome:
            args = [str(chrome)]
            # First call may use new window; later calls add tabs to existing Chrome
            if new_window:
                args.append("--new-window")
            args.append(url)
            try:
                subprocess.Popen(args, shell=False)
                return
            except Exception:
                pass
        try:
            from jarvis.core.displays import displays

            displays.open_url_on(url, "secondary")
            return
        except Exception:
            pass
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass

    def _admire_image(self, progress: Callable[..., None]) -> None:
        """Move/click an image tile inside Build Theater (no OS mouse hijack)."""
        import time as _time

        tiles = [
            (0.22, 0.42),
            (0.48, 0.48),
            (0.72, 0.44),
            (0.35, 0.62),
            (0.60, 0.55),
        ]
        x, y = random.choice(tiles)
        try:
            progress(
                "Moving cursor onto a promising image…",
                agent_stage="research",
                tab="working",
                mouse="move",
                mouse_x=x,
                mouse_y=y,
                terminal=f"mouse --move {x:.2f},{y:.2f}",
            )
            _time.sleep(1.0)
            progress(
                "Clicking image…",
                agent_stage="research",
                tab="working",
                mouse="click",
                mouse_x=x,
                mouse_y=y,
                mouse_click=True,
                terminal="mouse --click",
            )
            _time.sleep(1.1)
            lines = (
                "This is a nice image.",
                "This is a nice image — strong mood for the app.",
                "This is a nice image. I'll steal that vibe.",
                "This is a nice image. Perfect reference.",
            )
            line = random.choice(lines)
            progress(
                line,
                agent_stage="research",
                tab="working",
                speak=line,
                mouse="hover",
                mouse_x=x,
                mouse_y=y,
                terminal="jarvis --admire",
            )
            _time.sleep(1.8)
        except Exception as e:
            progress(
                "This is a nice image.",
                agent_stage="research",
                tab="working",
                speak="This is a nice image.",
                terminal=f"admire-fallback {e}",
            )
            _time.sleep(1.5)

    def _serve_preview(self, out_dir: Path) -> str:
        """Local HTTP server so the app preview actually runs (CSS/JS load)."""
        import threading
        from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

        out_dir = Path(out_dir)
        # Stop previous server if any
        prev = getattr(self, "_preview_server", None)
        if prev is not None:
            try:
                prev.shutdown()
            except Exception:
                pass
            self._preview_server = None

        class _Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(out_dir), **kwargs)

            def log_message(self, fmt, *args):  # noqa: A003
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True, name="vibe-preview")
        t.start()
        self._preview_server = httpd
        self._preview_port = port
        entry = "preview.html" if (out_dir / "preview.html").exists() else "index.html"
        return f"http://127.0.0.1:{port}/{entry}"

    # ── invent / classify ───────────────────────────────────────
    def _invent(self) -> dict[str, str]:
        used = self._recent_names()
        pool = [x for x in _INVENTIONS if x[0] not in used]
        if len(pool) < 5:
            pool = list(_INVENTIONS)
        # Bias toward games/videos so invent feels cinematic
        weighted: list[tuple[str, str, str]] = []
        for item in pool:
            stack = item[1]
            copies = 3 if stack in ("game", "video") else 1
            weighted.extend([item] * copies)
        random.shuffle(weighted)
        name, stack, pitch = (weighted or pool)[0]
        # Mutate name slightly so even repeats feel fresh
        suffixes = ("", " Lab", " Desk", " OS", " HQ", " Kit", " Studio", f" {random.randint(2,9)}")
        if name in used:
            name = f"{name}{random.choice(suffixes)}".strip()
        return {"name": name, "stack": stack, "pitch": pitch}

    def _recent_names(self) -> set[str]:
        try:
            data = json.loads(META_PATH.read_text(encoding="utf-8"))
            return {
                str(p.get("name") or "")
                for p in (data.get("projects") or [])[-30:]
                if p.get("name")
            }
        except Exception:
            return set()

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
        if any(
            w in b
            for w in (
                "game",
                "play",
                "arcade",
                "shooter",
                "puzzle",
                "snake",
                "runner",
                "maze",
            )
        ):
            return "game"
        if any(
            w in b
            for w in ("video", "reel", "trailer", "slideshow", "film", "movie", "storyboard")
        ):
            return "video"
        if any(w in b for w in ("cli", "command line", "python script", "terminal")):
            return "python"
        if any(w in b for w in ("dashboard", "ops", "metrics", "status board")):
            return "dashboard"
        return "web"

    def _slug(self, name: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return s[:48] or "vibe-project"

    def _research_pack(
        self,
        concept: dict[str, Any],
        progress: Callable[..., None],
    ) -> dict[str, Any]:
        """Search the web for inspiration prompts + hero/gallery images."""
        import time as _time
        import urllib.parse

        name = str(concept.get("name") or "app")
        pitch = str(concept.get("pitch") or concept.get("stack") or "product")
        stack = str(concept.get("stack") or "web")
        queries = [
            f"{name} {stack} app UI design inspiration",
            f"{pitch} product landing page moodboard",
            f"prompt ideas for building a {stack} app: {name}",
        ]
        hits: list[dict[str, str]] = []
        images: list[dict[str, str]] = []
        prompts: list[str] = [
            f"Design a polished {stack} app called {name} — {pitch}.",
            f"Hero section with bold typography, cyan accent, dark void background.",
            f"Interactive UI with localStorage, keyboard shortcuts, empty states.",
            f"Mobile-first layout, one primary CTA, gallery of mood images.",
        ]

        # Research stays in Build Theater — click search bar, type slowly, then submit
        self._chrome_started = False

        for i, q in enumerate(queries):
            gq = urllib.parse.quote_plus(q)
            google_url = f"https://www.google.com/search?q={gq}&hl=en"
            images_url = f"https://www.google.com/search?tbm=isch&q={gq}&hl=en"

            # 1) Open blank Google home (not pre-filled results)
            progress(
                "Opening Google home — clicking the search bar…",
                agent_stage="research",
                tab="working",
                browser_url="https://www.google.com/",
                mouse="focus-search",
                mouse_x=0.50,
                mouse_y=0.42,
                mouse_click=True,
                keyboard="",
                keyboard_reset=True,
                terminal="theater --google-home",
                prompts=prompts,
            )
            _time.sleep(1.6)

            # 2) Type the query slowly so you can watch each keystroke
            typed = ""
            for ci, ch in enumerate(q):
                typed += ch
                # Emit often enough to see typing, not every single char spam
                if ci == 0 or ci % 2 == 1 or ci == len(q) - 1:
                    progress(
                        f"Typing into search… {typed}",
                        agent_stage="research",
                        tab="working",
                        keyboard=typed,
                        keyboard_reset=(ci == 0),
                        mouse="typing",
                        mouse_x=0.50,
                        mouse_y=0.42,
                        terminal=f"keyboard --type {typed[:40]}",
                        prompts=prompts,
                    )
                    _time.sleep(0.14)
            _time.sleep(0.55)

            # 3) Submit search → results
            progress(
                f"Submitting search: {q[:56]}…",
                agent_stage="research",
                tab="working",
                keyboard=q,
                mouse="submit",
                mouse_x=0.78,
                mouse_y=0.42,
                mouse_click=True,
                google_submit=True,
                terminal="keyboard --enter",
                prompts=prompts,
            )
            _time.sleep(0.7)
            progress(
                f"Reading Google results… ({i+1}/{len(queries)})",
                agent_stage="research",
                tab="working",
                browser_url=google_url,
                mouse="scroll",
                mouse_x=0.55,
                mouse_y=0.60,
                terminal="scroll --results",
                research=hits[-6:],
                images=images[-6:],
                prompts=prompts,
            )
            _time.sleep(2.8)

            # 4) Images — type again slowly on Images mode
            progress(
                "Opening Google Images — clicking search bar…",
                agent_stage="research",
                tab="working",
                browser_url="https://www.google.com/imghp?hl=en",
                mouse="focus-search",
                mouse_x=0.50,
                mouse_y=0.40,
                mouse_click=True,
                keyboard="",
                keyboard_reset=True,
                terminal="theater --images-home",
                prompts=prompts,
            )
            _time.sleep(1.5)
            typed = ""
            for ci, ch in enumerate(q):
                typed += ch
                if ci == 0 or ci % 2 == 1 or ci == len(q) - 1:
                    progress(
                        f"Typing image search… {typed}",
                        agent_stage="research",
                        tab="working",
                        keyboard=typed,
                        keyboard_reset=(ci == 0),
                        mouse="typing",
                        mouse_x=0.50,
                        mouse_y=0.40,
                        terminal=f"keyboard --images {typed[:40]}",
                        prompts=prompts,
                    )
                    _time.sleep(0.12)
            _time.sleep(0.45)
            progress(
                f"Searching images for: {q[:50]}…",
                agent_stage="research",
                tab="working",
                keyboard=q,
                mouse="submit",
                mouse_click=True,
                mouse_x=0.78,
                mouse_y=0.40,
                google_submit=True,
                browser_url=images_url,
                terminal=f"theater --images {q[:50]}",
                prompts=prompts,
            )
            _time.sleep(2.6)

            # Click a tile and compliment it (visible on WORKING tab)
            self._admire_image(progress)
            _time.sleep(1.2)

            progress(
                f"Harvesting prompts from results: {q[:56]}…",
                agent_stage="research",
                tab="working",
                terminal=f"extract --prompts {q[:50]}",
                research=hits[-6:],
                images=images[-6:],
                prompts=prompts,
            )
            _time.sleep(1.2)
            # Tavily (images + text) if keyed
            try:
                from jarvis.core.secrets_vault import get_secret

                key = (get_secret("tavily_api_key") or "").strip()
            except Exception:
                key = (os.environ.get("TAVILY_API_KEY") or "").strip()
            if key:
                try:
                    body = {
                        "api_key": key,
                        "query": q,
                        "max_results": 4,
                        "include_answer": True,
                        "include_images": True,
                    }
                    req = urllib.request.Request(
                        "https://api.tavily.com/search",
                        data=json.dumps(body).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=18) as resp:
                        data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    if data.get("answer"):
                        prompts.append(str(data["answer"])[:220])
                    for r in (data.get("results") or [])[:4]:
                        hits.append(
                            {
                                "title": str(r.get("title") or "")[:100],
                                "url": str(r.get("url") or "")[:200],
                                "snippet": str(r.get("content") or "")[:180],
                            }
                        )
                    for img in (data.get("images") or [])[:4]:
                        url = img if isinstance(img, str) else str(
                            (img or {}).get("url") or ""
                        )
                        if url.startswith("http"):
                            images.append({"url": url[:300], "alt": q[:60]})
                except Exception as e:
                    print(f"[vibe] tavily research: {e}")

            # DuckDuckGo / Wikipedia style search
            try:
                from jarvis.core.internet import InternetAgent

                net = InternetAgent()
                net.search(q, open_page=False, speak_limit=3)
                for r in (net.last_results or [])[:4]:
                    hits.append(
                        {
                            "title": str(r.get("title") or "")[:100],
                            "url": str(r.get("url") or "")[:200],
                            "snippet": str(r.get("snippet") or "")[:180],
                        }
                    )
                if net.last_answer:
                    prompts.append(net.last_answer[:220])
            except Exception as e:
                print(f"[vibe] web research: {e}")

        # Reliable image URLs (picsum + unsplash-style query seeds) so preview always has art
        slug = self._slug(name)
        mood = urllib.parse.quote_plus(f"{stack},{name.split()[0]},technology,neon")
        for i, label in enumerate(
            ("hero", "gallery-1", "gallery-2", "gallery-3", "texture")
        ):
            seed = f"{slug}-{label}-{i}"
            images.append(
                {
                    "url": f"https://picsum.photos/seed/{urllib.parse.quote(seed)}/960/540",
                    "alt": f"{name} {label}",
                }
            )
            images.append(
                {
                    "url": f"https://loremflickr.com/960/540/{mood}?lock={i + 3}",
                    "alt": f"{name} mood {i}",
                }
            )

        # Dedupe
        seen_u: set[str] = set()
        uniq_img: list[dict[str, str]] = []
        for im in images:
            u = im.get("url") or ""
            if u and u not in seen_u:
                seen_u.add(u)
                uniq_img.append(im)
        seen_h: set[str] = set()
        uniq_hits: list[dict[str, str]] = []
        for h in hits:
            key = (h.get("url") or h.get("title") or "")[:120]
            if key and key not in seen_h:
                seen_h.add(key)
                uniq_hits.append(h)

        pack = {
            "queries": queries,
            "hits": uniq_hits[:12],
            "images": uniq_img[:10],
            "prompts": list(dict.fromkeys([p for p in prompts if p]))[:10],
        }
        progress(
            f"Research packed — {len(pack['hits'])} sources, {len(pack['images'])} images. Tabs left open.",
            agent_stage="research",
            tab="working",
            research=pack["hits"],
            images=pack["images"],
            prompts=pack["prompts"],
            terminal="research --done --keep-tabs",
            speak="Research done. I left the Google tabs open for you.",
        )
        return pack

    def _write_prompt(
        self,
        brief: str,
        concept: dict[str, str],
        *,
        research: dict[str, Any] | None = None,
    ) -> str:
        research = research or {}
        prompts = "\n".join(f"- {p}" for p in (research.get("prompts") or [])[:6])
        imgs = "\n".join(
            f"- {im.get('url')}" for im in (research.get("images") or [])[:5]
        )
        refs = "\n".join(
            f"- {h.get('title')}: {h.get('snippet')}"
            for h in (research.get("hits") or [])[:5]
        )
        return (
            f"You are Jarvis, an autonomous vibe-coding agent.\n"
            f"Product: {concept['name']}\n"
            f"Stack hint: {concept['stack']}\n"
            f"Brief: {brief}\n\n"
            f"Design prompts from research:\n{prompts or '- (none)'}\n\n"
            f"Image URLs to embed in the UI (use as <img src>):\n{imgs or '- picsum fallback'}\n\n"
            f"Web references:\n{refs or '- (none)'}\n\n"
            f"Ship a COMPLETE runnable multi-file project with AT LEAST 6 files "
            f"(index.html, styles.css, theme.css, app.js, ui.js, storage.js, research.md, README.md). "
            f"Include a hero image, image gallery, substantial JS (200+ lines total), "
            f"polished CSS, keyboard shortcuts, and empty states. Zero stubs."
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
        self,
        prompt: str,
        concept: dict[str, str],
        *,
        research: dict[str, Any] | None = None,
    ) -> dict[str, str] | None:
        system = (
            "Return ONLY valid JSON object mapping relative file paths to file contents. "
            "Example: {\"index.html\":\"...\",\"styles.css\":\"...\",\"app.js\":\"...\"}. "
            "No markdown fences. Include at least 6 files with substantial code. Make it runnable."
        )
        user = (
            f"{prompt}\n\nStack: {concept['stack']}. "
            f"Name: {concept['name']}. Prefer vanilla HTML/CSS/JS unless python CLI. "
            f"Embed researched image URLs in HTML."
        )
        raw = self._ollama_text(system, user, num_predict=6500)
        if not raw:
            return None
        data = self._parse_files_json(raw)
        if not data or len(data) < 2:
            return None
        clean = {
            str(k).replace("\\", "/").lstrip("./"): str(v)
            for k, v in data.items()
            if isinstance(v, str) and len(v) > 10
        }
        if len(clean) < 2:
            return None
        # If model returned too little, merge with expanded template
        if len(clean) < 5 or sum(len(v) for v in clean.values()) < 2500:
            base = self._template_project(concept, research=research)
            base.update(clean)
            return base
        return clean

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
    def _template_project(
        self,
        concept: dict[str, str],
        *,
        research: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        stack = concept["stack"]
        name = concept["name"]
        pitch = concept.get("pitch") or "a sharp little tool"
        research = research or concept.get("research") or {}
        if stack == "python":
            return self._tpl_python(name, pitch)
        if stack == "game":
            return self._tpl_game(name, pitch)
        if stack == "video":
            return self._tpl_video(name, pitch, research=research)
        if stack == "dashboard":
            return self._tpl_dashboard(name, pitch)
        return self._tpl_web(name, pitch, research=research)

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

    def _app_kind(self, name: str, pitch: str) -> str:
        blob = f"{name} {pitch}".lower()
        rules = (
            ("timer", ("timer", "pomodoro", "focus", "countdown", "stretch")),
            ("notes", ("note", "journal", "markdown", "ink", "story")),
            ("quiz", ("card", "flash", "quiz", "interview", "drill", "vault cards")),
            ("mood", ("mood", "emoji", "feel")),
            ("budget", ("budget", "expense", "split", "tip", "bill")),
            ("quest", ("quest", "xp", "habit", "streak", "hydration")),
            ("pads", ("beat", "drum", "pad", "music")),
            ("debate", ("debate", "pros", "cons", "argument")),
            ("rank", ("film", "rank", "rate", "movie", "score")),
            ("garden", ("garden", "plant", "water")),
            ("crypto", ("crypto", "ticker", "price")),
            ("inbox", ("inbox", "mail", "triage")),
        )
        for kind, keys in rules:
            if any(k in blob for k in keys):
                return kind.strip()
        return random.choice(
            ("todo", "timer", "notes", "quiz", "mood", "budget", "quest")
        )

    def _functional_board(
        self, kind: str, name: str, key: str, research: dict[str, Any]
    ) -> tuple[str, str]:
        """Return (board_html, app_js) for a working interactive app."""
        prompts = [p[:100] for p in (research.get("prompts") or [])[:5]]
        prompts_js = json.dumps(prompts)

        if kind == "timer":
            board = """
      <section class="panel">
        <div class="panel-head"><h2>Focus timer</h2>
          <div class="stats">
            <span><b id="statRounds">0</b> rounds</span>
            <span><b id="statFocus">0</b> min focus</span>
          </div>
        </div>
        <div class="timer-face" id="clock">25:00</div>
        <div class="cta-row">
          <button type="button" class="primary" id="startTimer">Start</button>
          <button type="button" id="pauseTimer">Pause</button>
          <button type="button" id="resetTimer">Reset</button>
          <button type="button" id="mode25">25/5</button>
          <button type="button" id="mode50">50/10</button>
          <button type="button" id="mode15">15/3</button>
          <button type="button" id="skipBreak">Skip break</button>
          <button type="button" id="clearHist">Clear history</button>
          <button type="button" id="exportHist">Export</button>
        </div>
        <ul id="list"></ul>
        <p class="hint">Completes a round automatically · history saved locally · Export copies JSON</p>
      </section>"""
            app = f"""
const KEY = "vibe:{key}:timer";
const clock = document.getElementById("clock");
const list = document.getElementById("list");
let work = 25*60, breakS = 5*60, left = work, on = false, mode = "work", t = null;
function load(){{ try{{return JSON.parse(localStorage.getItem(KEY)||"[]");}}catch{{return[];}} }}
function save(x){{ localStorage.setItem(KEY, JSON.stringify(x)); }}
function fmt(s){{ const m=Math.floor(s/60), r=s%60; return String(m).padStart(2,"0")+":"+String(r).padStart(2,"0"); }}
function render(){{
  clock.textContent = fmt(left);
  const hist = load();
  document.getElementById("statRounds").textContent = String(hist.length);
  const focusMin = hist.filter(h => /Focus/i.test(h.label||"")).length * Math.round(work/60);
  const sf = document.getElementById("statFocus"); if (sf) sf.textContent = String(focusMin);
  list.innerHTML = hist.slice(0,12).map(h => `<li><span>${{h.label}} · ${{h.at}}</span></li>`).join("") || "<li><span>No rounds yet — hit Start</span></li>";
}}
function tick(){{
  if(!on) return;
  left -= 1;
  if(left <= 0){{
    const hist = load();
    hist.unshift({{label: mode==="work"?"Focus done":"Break done", at: new Date().toLocaleTimeString()}});
    save(hist);
    mode = mode==="work" ? "break" : "work";
    left = mode==="work" ? work : breakS;
    try{{ new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=").play(); }}catch(e){{}}
  }}
  render();
}}
document.getElementById("startTimer").onclick = () => {{ on = true; if(!t) t = setInterval(tick,1000); }};
document.getElementById("pauseTimer").onclick = () => {{ on = false; }};
document.getElementById("resetTimer").onclick = () => {{ on=false; mode="work"; left=work; render(); }};
document.getElementById("mode25").onclick = () => {{ work=25*60; breakS=5*60; left=work; render(); }};
document.getElementById("mode50").onclick = () => {{ work=50*60; breakS=10*60; left=work; render(); }};
document.getElementById("mode15").onclick = () => {{ work=15*60; breakS=3*60; left=work; render(); }};
document.getElementById("skipBreak").onclick = () => {{ mode="work"; left=work; render(); }};
document.getElementById("clearHist").onclick = () => {{ save([]); render(); }};
document.getElementById("exportHist").onclick = () => {{
  const blob = new Blob([JSON.stringify(load(),null,2)], {{type:"application/json"}});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "timer-history.json"; a.click();
}};
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav();
render();
"""
            return board, app

        if kind == "quiz":
            board = """
      <section class="panel">
        <div class="panel-head"><h2>Drill deck</h2>
          <div class="stats"><span><b id="statTotal">0</b> cards</span><span><b id="statDone">0</b> known</span></div>
        </div>
        <div class="timer-face" id="cardFace">Add a card to begin</div>
        <form id="form"><input id="input" placeholder="Front | Back" autocomplete="off"/><button type="submit">Add card</button></form>
        <div class="cta-row">
          <button type="button" class="primary" id="flip">Flip</button>
          <button type="button" id="know">I know it</button>
          <button type="button" id="again">Again</button>
          <button type="button" id="next">Next</button>
        </div>
        <ul id="list"></ul>
      </section>"""
            app = f"""
const KEY="vibe:{key}:quiz";
const face=document.getElementById("cardFace");
const list=document.getElementById("list");
let i=0, showBack=false;
function load(){{ try{{return JSON.parse(localStorage.getItem(KEY)||"[]");}}catch{{return[];}} }}
function save(x){{ localStorage.setItem(KEY, JSON.stringify(x)); }}
function seed(){{
  let cards=load();
  if(cards.length) return cards;
  const prompts={prompts_js};
  cards = (prompts.length?prompts:["Capital of France | Paris","2+2 | 4"]).map(p=>{{
    const parts=String(p).split("|");
    return {{front:(parts[0]||p).trim(), back:(parts[1]||"…").trim(), known:false}};
  }});
  save(cards); return cards;
}}
function render(){{
  const cards=seed();
  if(!cards.length){{ face.textContent="No cards"; return; }}
  i=((i%cards.length)+cards.length)%cards.length;
  const c=cards[i];
  face.textContent = showBack ? c.back : c.front;
  document.getElementById("statTotal").textContent=String(cards.length);
  document.getElementById("statDone").textContent=String(cards.filter(x=>x.known).length);
  list.innerHTML=cards.map((c,idx)=>`<li class="${{c.known?"done":""}}"><span>${{c.front}} → ${{c.back}}</span><button data-i="${{idx}}">✕</button></li>`).join("");
  list.querySelectorAll("button").forEach(b=>b.onclick=()=>{{ const cards=load(); cards.splice(+b.dataset.i,1); save(cards); render(); }});
}}
document.getElementById("form").onsubmit=(e)=>{{
  e.preventDefault();
  const raw=document.getElementById("input").value.trim(); if(!raw) return;
  const [f,b]=raw.split("|"); const cards=load();
  cards.unshift({{front:(f||raw).trim(), back:(b||"…").trim(), known:false}}); save(cards);
  document.getElementById("input").value=""; render();
}};
document.getElementById("flip").onclick=()=>{{ showBack=!showBack; render(); }};
document.getElementById("know").onclick=()=>{{ const cards=load(); if(cards[i]) cards[i].known=true; save(cards); i++; showBack=false; render(); }};
document.getElementById("again").onclick=()=>{{ const cards=load(); if(cards[i]) cards[i].known=false; save(cards); i++; showBack=false; render(); }};
document.getElementById("next").onclick=()=>{{ i++; showBack=false; render(); }};
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav(); render();
"""
            return board, app

        if kind == "budget":
            board = """
      <section class="panel">
        <div class="panel-head"><h2>Money board</h2>
          <div class="stats"><span>spent <b id="statTotal">0</b></span><span>left <b id="statDone">0</b></span></div>
        </div>
        <form id="form">
          <input id="input" placeholder="Coffee 4.50" autocomplete="off"/>
          <select id="cat"><option>food</option><option>travel</option><option>tools</option><option>fun</option><option>other</option></select>
          <button type="submit">Add</button>
        </form>
        <div class="cta-row">
          <label class="dim">Budget <input id="budget" type="number" value="100" style="width:90px;margin-left:8px"/></label>
          <button type="button" id="clearSpent">Clear spent</button>
        </div>
        <ul id="list"></ul>
      </section>"""
            app = f"""
const KEY="vibe:{key}:budget";
function load(){{ try{{return JSON.parse(localStorage.getItem(KEY)||'{{"budget":100,"items":[]}}');}}catch{{return{{budget:100,items:[]}};}} }}
function save(x){{ localStorage.setItem(KEY, JSON.stringify(x)); }}
function render(){{
  const data=load(); const items=data.items||[];
  const spent=items.reduce((a,b)=>a+(+b.amt||0),0);
  document.getElementById("statTotal").textContent=spent.toFixed(2);
  document.getElementById("statDone").textContent=( (+data.budget||0)-spent ).toFixed(2);
  document.getElementById("budget").value=data.budget||100;
  document.getElementById("list").innerHTML=items.map((it,i)=>`<li><span>${{it.cat}} · ${{it.text}} · $${{Number(it.amt).toFixed(2)}}</span><button data-i="${{i}}">✕</button></li>`).join("")||"<li><span>No spend yet</span></li>";
  document.querySelectorAll("#list button").forEach(b=>b.onclick=()=>{{ const d=load(); d.items.splice(+b.dataset.i,1); save(d); render(); }});
}}
document.getElementById("form").onsubmit=(e)=>{{
  e.preventDefault();
  const raw=document.getElementById("input").value.trim(); if(!raw) return;
  const m=raw.match(/([0-9]+(?:\\.[0-9]+)?)/); const amt=m?+m[1]:0;
  const text=raw.replace(/([0-9]+(?:\\.[0-9]+)?)/,"").trim()||"item";
  const d=load(); d.items.unshift({{text, amt, cat:document.getElementById("cat").value, at:Date.now()}}); save(d);
  document.getElementById("input").value=""; render();
}};
document.getElementById("budget").onchange=(e)=>{{ const d=load(); d.budget=+e.target.value||0; save(d); render(); }};
document.getElementById("clearSpent").onclick=()=>{{ const d=load(); d.items=[]; save(d); render(); }};
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav(); render();
"""
            return board, app

        if kind == "mood":
            board = """
      <section class="panel">
        <div class="panel-head"><h2>Mood log</h2>
          <div class="stats"><span><b id="statTotal">0</b> entries</span></div>
        </div>
        <div class="cta-row" id="moods">
          <button type="button" data-m="😀">😀</button>
          <button type="button" data-m="😐">😐</button>
          <button type="button" data-m="😤">😤</button>
          <button type="button" data-m="😢">😢</button>
          <button type="button" data-m="🔥">🔥</button>
        </div>
        <form id="form"><input id="input" placeholder="Optional note…" autocomplete="off"/><button type="submit">Save mood</button></form>
        <ul id="list"></ul>
      </section>"""
            app = f"""
const KEY="vibe:{key}:mood"; let pick="😀";
function load(){{ try{{return JSON.parse(localStorage.getItem(KEY)||"[]");}}catch{{return[];}} }}
function save(x){{ localStorage.setItem(KEY, JSON.stringify(x)); }}
function render(){{
  const items=load();
  document.getElementById("statTotal").textContent=String(items.length);
  document.getElementById("list").innerHTML=items.map((it,i)=>`<li><span>${{it.mood}} ${{it.note||""}} · ${{it.at}}</span><button data-i="${{i}}">✕</button></li>`).join("")||"<li><span>Log how you feel</span></li>";
  document.querySelectorAll("#list button").forEach(b=>b.onclick=()=>{{ const x=load(); x.splice(+b.dataset.i,1); save(x); render(); }});
}}
document.querySelectorAll("#moods button").forEach(b=>b.onclick=()=>{{ pick=b.dataset.m; }});
document.getElementById("form").onsubmit=(e)=>{{
  e.preventDefault();
  const note=document.getElementById("input").value.trim();
  const x=load(); x.unshift({{mood:pick, note, at:new Date().toLocaleString()}}); save(x);
  document.getElementById("input").value=""; render();
}};
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav(); render();
"""
            return board, app

        # default todo / quest — still fully interactive
        title = "Quest board" if kind == "quest" else "Command board"
        board = f"""
      <section class="panel">
        <div class="panel-head"><h2>{title}</h2>
          <div class="stats"><span><b id="statTotal">0</b> items</span><span><b id="statDone">0</b> done</span><span><b id="statXP">0</b> XP</span></div>
        </div>
        <form id="form">
          <input id="input" placeholder="Add something actionable…" autocomplete="off"/>
          <button type="submit">Add</button>
        </form>
        <div class="filters">
          <button type="button" data-filter="all" class="chip on">All</button>
          <button type="button" data-filter="open" class="chip">Open</button>
          <button type="button" data-filter="done" class="chip">Done</button>
        </div>
        <ul id="list"></ul>
        <p class="hint">Click text to toggle · XP awarded on complete · <kbd>N</kbd> focus</p>
      </section>"""
        app = f"""
const prompts = {prompts_js};
const list = document.getElementById("list");
const form = document.getElementById("form");
const input = document.getElementById("input");
const store = window.VibeStore;
function xpOf(items){{ return items.filter(x=>x.done).length * 10; }}
function render() {{
  const items = store.load();
  const filter = ui.filter || "all";
  list.innerHTML = "";
  const visible = items.filter((item) => {{
    if (filter === "open") return !item.done;
    if (filter === "done") return item.done;
    return true;
  }});
  if (!visible.length) {{
    const empty = document.createElement("li");
    empty.innerHTML = "<span>Nothing here — add a real task or steal a research prompt.</span>";
    list.appendChild(empty);
  }}
  visible.forEach((item) => {{
    const i = items.indexOf(item);
    const li = document.createElement("li");
    if (item.done) li.classList.add("done");
    const span = document.createElement("span");
    span.textContent = item.text;
    span.style.cursor = "pointer";
    span.onclick = () => {{ items[i].done = !items[i].done; store.save(items); render(); }};
    const del = document.createElement("button");
    del.textContent = "✕";
    del.onclick = () => {{ items.splice(i, 1); store.save(items); render(); }};
    li.append(span, del);
    list.appendChild(li);
  }});
  document.getElementById("statTotal").textContent = String(items.length);
  document.getElementById("statDone").textContent = String(items.filter((x) => x.done).length);
  const xpEl = document.getElementById("statXP"); if (xpEl) xpEl.textContent = String(xpOf(items));
}}
form.addEventListener("submit", (e) => {{
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  const items = store.load();
  items.unshift({{ text, done: false, at: Date.now() }});
  store.save(items);
  input.value = "";
  render();
}});
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav();
ui.bindFilters(render);
store.seed(prompts);
render();
addEventListener("keydown", (e) => {{
  if (e.target && ["INPUT","TEXTAREA"].includes(e.target.tagName)) return;
  if (e.key === "n" || e.key === "N") {{ ui.setView("board"); input.focus(); }}
}});
"""
        return board, app

    def _tpl_web(
        self,
        name: str,
        pitch: str,
        *,
        research: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        safe = _esc(name)
        research = research or {}
        images = research.get("images") or []
        hero = (images[0] or {}).get("url") if images else (
            f"https://picsum.photos/seed/{self._slug(name)}-hero/1200/640"
        )
        gallery = [
            (im.get("url") or "")
            for im in images[1:5]
            if (im.get("url") or "").startswith("http")
        ]
        while len(gallery) < 3:
            gallery.append(
                f"https://picsum.photos/seed/{self._slug(name)}-g{len(gallery)}/800/500"
            )
        prompts_md = "\n".join(
            f"- {p}" for p in (research.get("prompts") or [])[:8]
        ) or "- Build a polished local-first web app."
        hits_md = "\n".join(
            f"- [{_esc(h.get('title'))}]({h.get('url')}) — {_esc(h.get('snippet'))}"
            for h in (research.get("hits") or [])[:8]
        ) or "- (offline research fallback)"
        gal_html = "\n".join(
            f'      <figure><img src="{_esc(u)}" alt="mood {i+1}" loading="lazy"/>'
            f"<figcaption>Mood {i+1}</figcaption></figure>"
            for i, u in enumerate(gallery[:4])
        )
        key = self._slug(name)
        kind = self._app_kind(name, pitch)
        board_html, app_js = self._functional_board(kind, name, key, research)
        return {
            "index.html": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{safe}</title>
<link rel="stylesheet" href="theme.css"/>
<link rel="stylesheet" href="styles.css"/>
</head>
<body>
  <div class="bg"></div>
  <header class="top">
    <p class="eyebrow">JARVIS · VIBE · {kind.upper()}</p>
    <nav>
      <button type="button" data-go="home" class="nav on">Home</button>
      <button type="button" data-go="board" class="nav">App</button>
      <button type="button" data-go="gallery" class="nav">Gallery</button>
      <button type="button" id="themeBtn" class="nav ghost">Theme</button>
    </nav>
  </header>
  <main>
    <section id="home" class="view on">
      <div class="hero" style="--hero:url('{_esc(hero)}')">
        <div class="hero-copy">
          <h1>{safe}</h1>
          <p class="lead">{_esc(pitch)}</p>
          <div class="cta-row">
            <button type="button" id="startBtn" class="primary">Open app</button>
            <button type="button" data-go="gallery" class="ghost">Research images</button>
          </div>
          <p class="meta">Kind: {kind} · researched live · functional local app</p>
        </div>
      </div>
    </section>
    <section id="board" class="view">
{board_html}
    </section>
    <section id="gallery" class="view">
      <h2 class="section-title">Research gallery</h2>
      <p class="dim">Images Jarvis clicked and kept while searching.</p>
      <div class="gallery">
{gal_html}
      </div>
    </section>
  </main>
  <script src="storage.js"></script>
  <script src="ui.js"></script>
  <script src="app.js"></script>
</body>
</html>
""",
            "theme.css": """:root {
  --cyan:#00e8ff; --amber:#ffc14a; --ok:#3dff9a; --void:#05070c;
  --panel:rgba(8,16,24,.9); --text:#e8f4ff; --dim:#7a93a8; --line:rgba(0,232,255,.28);
}
[data-theme="warm"] {
  --cyan:#ff9f43; --amber:#ffe08a; --void:#120a06; --panel:rgba(28,14,8,.92);
  --line:rgba(255,159,67,.35);
}
""",
            "styles.css": """* { box-sizing: border-box; }
body {
  margin:0; min-height:100vh; font-family:"Bahnschrift","Segoe UI",sans-serif;
  color:var(--text); background:var(--void); overflow-x:hidden;
}
.bg {
  position:fixed; inset:0; z-index:-1;
  background:
    radial-gradient(900px 500px at 10% 0%, color-mix(in srgb, var(--cyan) 22%, transparent), transparent 55%),
    radial-gradient(700px 400px at 90% 100%, rgba(255,107,53,.12), transparent 50%),
    linear-gradient(160deg, var(--void), #0a1520 60%, var(--void));
}
.top {
  display:flex; justify-content:space-between; align-items:center; gap:16px;
  padding:16px 24px; border-bottom:1px solid var(--line);
}
.eyebrow { letter-spacing:.28em; font-size:10px; color:var(--cyan); margin:0; }
nav { display:flex; gap:8px; flex-wrap:wrap; }
.nav, .chip, .primary, .ghost, button[type="submit"], select {
  background:transparent; border:1px solid var(--line); color:var(--cyan);
  padding:8px 12px; letter-spacing:.1em; text-transform:uppercase; cursor:pointer; font:inherit;
}
.nav.on, .chip.on, .primary { background:color-mix(in srgb, var(--cyan) 16%, transparent); }
.primary { border-color:var(--cyan); }
.ghost { color:var(--dim); }
main { max-width:980px; margin:0 auto; padding:28px 24px 80px; }
.view { display:none; animation:rise .35s ease; }
.view.on { display:block; }
@keyframes rise { from { opacity:0; transform:translateY(8px);} to { opacity:1; transform:none;} }
.hero {
  min-height:360px; border:1px solid var(--line); border-radius:14px; overflow:hidden;
  background:
    linear-gradient(90deg, rgba(2,8,14,.88), rgba(2,8,14,.35)),
    var(--hero) center/cover no-repeat;
  display:flex; align-items:flex-end;
}
.hero-copy { padding:36px; max-width:560px; }
h1 {
  margin:0; font-size:clamp(2.2rem, 5vw, 3.4rem); letter-spacing:.04em;
  text-transform:uppercase; line-height:1.05;
}
.lead { color:#c8dceb; font-size:1.08rem; max-width:40ch; margin:14px 0 22px; }
.cta-row { display:flex; gap:10px; flex-wrap:wrap; margin:12px 0; }
.meta { color:var(--dim); font-size:12px; letter-spacing:.06em; margin-top:18px; }
.panel {
  background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--cyan);
  padding:22px; backdrop-filter:blur(10px);
}
.panel-head { display:flex; justify-content:space-between; gap:12px; align-items:end; margin-bottom:14px; }
.panel h2, .section-title { margin:0; font-size:13px; letter-spacing:.2em; color:var(--cyan); }
.stats { display:flex; gap:14px; color:var(--dim); font-size:12px; }
.stats b { color:var(--text); }
.timer-face {
  font-size:clamp(2.8rem, 8vw, 4.5rem); letter-spacing:.08em; text-align:center;
  padding:24px 0; color:var(--cyan); text-shadow:0 0 24px rgba(0,232,255,.35);
}
form { display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; }
input, select {
  flex:1; background:#02080e; border:1px solid var(--line); color:var(--text);
  padding:12px 14px; font:inherit; min-width:140px;
}
.filters { display:flex; gap:8px; margin-bottom:10px; }
.chip { padding:6px 10px; font-size:11px; }
ul { list-style:none; margin:0; padding:0; }
li {
  display:flex; justify-content:space-between; gap:12px; align-items:center;
  padding:12px 0; border-bottom:1px solid rgba(122,147,168,.2);
}
li.done span { opacity:.45; text-decoration:line-through; }
li button { border:none; color:var(--dim); padding:0; letter-spacing:0; background:transparent; cursor:pointer; }
.hint { color:var(--dim); font-size:12px; }
kbd {
  border:1px solid var(--line); padding:1px 5px; border-radius:3px; color:var(--cyan);
  font-family:Consolas,monospace;
}
.dim { color:var(--dim); }
.gallery {
  margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px;
}
.gallery figure {
  margin:0; border:1px solid var(--line); background:rgba(0,0,0,.25); overflow:hidden;
}
.gallery img { display:block; width:100%; height:150px; object-fit:cover; }
.gallery figcaption {
  padding:8px 10px; font-size:11px; letter-spacing:.12em; color:var(--dim); text-transform:uppercase;
}
""",
            "storage.js": f"""window.VibeStore = {{
  KEY: "vibe:{key}",
  load() {{
    try {{ return JSON.parse(localStorage.getItem(this.KEY) || "[]"); }}
    catch {{ return []; }}
  }},
  save(items) {{ localStorage.setItem(this.KEY, JSON.stringify(items)); }},
  seed(prompts) {{
    const cur = this.load();
    if (cur.length) return cur;
    const seeded = (prompts || []).slice(0, 4).map((text) => ({{
      text, done: false, at: Date.now()
    }}));
    this.save(seeded);
    return seeded;
  }}
}};
""",
            "ui.js": """window.VibeUI = {
  filter: "all",
  setView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("on", v.id === name));
    document.querySelectorAll("[data-go]").forEach((b) =>
      b.classList.toggle("on", b.getAttribute("data-go") === name)
    );
  },
  bindNav() {
    document.querySelectorAll("[data-go]").forEach((btn) => {
      btn.addEventListener("click", () => this.setView(btn.getAttribute("data-go")));
    });
    const themeBtn = document.getElementById("themeBtn");
    if (themeBtn) {
      themeBtn.onclick = () => {
        const warm = document.documentElement.getAttribute("data-theme") === "warm";
        document.documentElement.setAttribute("data-theme", warm ? "" : "warm");
      };
    }
  },
  bindFilters(onChange) {
    document.querySelectorAll("[data-filter]").forEach((chip) => {
      chip.addEventListener("click", () => {
        this.filter = chip.getAttribute("data-filter");
        document.querySelectorAll("[data-filter]").forEach((c) =>
          c.classList.toggle("on", c === chip)
        );
        onChange();
      });
    });
  }
};
const ui = window.VibeUI;
""",
            "app.js": app_js,
            "research.md": (
                f"# Research — {name}\n\n"
                f"**App kind:** {kind}\n\n"
                f"## Prompts\n{prompts_md}\n\n"
                f"## Web sources\n{hits_md}\n\n"
                f"## Images\n"
                + "\n".join(f"- {im.get('url')}" for im in images[:8])
                + "\n"
            ),
            "preview.html": f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{safe} · Preview</title>
<style>
  body{{margin:0;font-family:Bahnschrift,Segoe UI,sans-serif;background:#05070c;color:#e8f4ff}}
  .hero{{min-height:220px;background:linear-gradient(90deg,rgba(2,8,14,.9),rgba(2,8,14,.3)),
    url('{_esc(hero)}') center/cover;display:flex;align-items:flex-end;padding:24px;border-bottom:1px solid rgba(0,232,255,.25)}}
  h1{{margin:0;font-size:28px;letter-spacing:.04em;text-transform:uppercase}}
  .lead{{color:#9ab;max-width:42ch}}
  .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:12px}}
  .grid img{{width:100%;height:100px;object-fit:cover;border:1px solid rgba(0,232,255,.2)}}
  .tag{{padding:10px 12px;color:#00e8ff;letter-spacing:.18em;font-size:10px}}
  a.btn{{display:inline-block;margin:12px;padding:10px 14px;border:1px solid #00e8ff;color:#00e8ff;text-decoration:none;letter-spacing:.12em}}
</style></head>
<body>
  <div class="tag">SANDBOX PREVIEW · {kind.upper()} · NOT PUBLISHED</div>
  <div class="hero"><div><h1>{safe}</h1><p class="lead">{_esc(pitch)}</p>
  <a class="btn" href="index.html">OPEN FULL APP</a></div></div>
  <div class="grid">
    {''.join(f'<img src="{_esc(u)}" alt="mood"/>' for u in gallery[:3])}
  </div>
</body></html>
""",
            "README.md": self._readme(
                {"name": name, "stack": f"web/{kind}", "pitch": pitch},
                "template+research",
                [
                    "index.html",
                    "theme.css",
                    "styles.css",
                    "storage.js",
                    "ui.js",
                    "app.js",
                    "research.md",
                    "preview.html",
                    "README.md",
                ],
            ),
        }
    def _tpl_game(self, name: str, pitch: str) -> dict[str, str]:
        safe = _esc(name)
        blob = f"{name} {pitch}".lower()
        if any(w in blob for w in ("snake",)):
            kind = "snake"
        elif any(w in blob for w in ("runner", "jump", "dash")):
            kind = "runner"
        else:
            kind = "shooter"
        js = {
            "snake": self._game_js_snake(),
            "runner": self._game_js_runner(),
            "shooter": self._game_js_shooter(),
        }[kind]
        help_txt = {
            "snake": "ARROWS STEER · P PAUSE · R RESTART",
            "runner": "SPACE / UP JUMP · P PAUSE · R RESTART",
            "shooter": "ARROWS MOVE · SPACE SHOOT · P PAUSE · R RESTART",
        }[kind]
        return {
            "index.html": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{safe}</title>
<style>
  html,body{{margin:0;height:100%;background:#05070c;color:#e8f4ff;font-family:Bahnschrift,Segoe UI,sans-serif}}
  #wrap{{display:grid;place-items:center;height:100%;gap:10px;padding:12px}}
  canvas{{border:1px solid rgba(0,232,255,.4);background:#02080e;box-shadow:0 0 40px rgba(0,232,255,.12);cursor:pointer}}
  p{{letter-spacing:.18em;font-size:12px;color:#00e8ff;margin:0}}
  .dim{{color:#7a93a8;letter-spacing:.08em;text-align:center;max-width:520px}}
  .hud{{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}}
  button{{background:transparent;border:1px solid rgba(0,232,255,.45);color:#00e8ff;
    padding:8px 14px;letter-spacing:.14em;cursor:pointer;font:inherit;text-transform:uppercase}}
  button:hover,button.active{{background:rgba(0,232,255,.15)}}
  #score{{color:#e8f4ff;font-size:14px;letter-spacing:.2em}}
</style>
</head>
<body>
<div id="wrap">
  <p>{safe}</p>
  <div id="score">SCORE 0 · BEST 0 · LIVES 3</div>
  <canvas id="c" width="520" height="340"></canvas>
  <div class="hud">
    <button type="button" id="btnPause">Pause</button>
    <button type="button" id="btnRestart">Restart</button>
    <button type="button" id="btnMute">Mute SFX</button>
    <button type="button" id="btnEasy">Easy</button>
    <button type="button" id="btnHard">Hard</button>
  </div>
  <p class="dim">{help_txt} · {_esc(pitch).upper()}</p>
</div>
<script src="game.js"></script>
</body>
</html>
""",
            "game.js": js,
            "preview.html": f"""<!DOCTYPE html><html><head><meta charset="utf-8"/>
<title>{safe} preview</title>
<style>body{{margin:0;background:#02080e;color:#9adfff;font-family:Bahnschrift,sans-serif;display:grid;place-items:center;height:100vh}}
a{{color:#00e8ff;letter-spacing:.2em;text-decoration:none;border:1px solid #00e8ff;padding:14px 22px}}</style></head>
<body><div><h1>{safe}</h1><p>{_esc(pitch)}</p><p><a href="index.html">OPEN FULL GAME</a></p></div></body></html>
""",
            "README.md": self._readme(
                {"name": name, "stack": "game", "pitch": pitch},
                "template",
                ["index.html", "game.js", "preview.html", "README.md"],
            ),
        }

    def _game_js_shooter(self) -> str:
        return r"""
const c = document.getElementById("c");
const ctx = c.getContext("2d");
const keys = {};
const scoreEl = document.getElementById("score");
addEventListener("keydown", e => { keys[e.code] = true; if(["Space","ArrowUp","ArrowDown"].includes(e.code)) e.preventDefault(); });
addEventListener("keyup", e => keys[e.code] = false);
let player = { x: 246, y: 280, w: 28, h: 16 };
let bullets = [], foes = [], particles = [];
let score = 0, best = +(localStorage.getItem("vibe:shooter:best")||0);
let lives = 3, tick = 0, alive = true, paused = false, muted = false, speed = 1;
function beep(){ if(muted) return; try{ const a=new (window.AudioContext||window.webkitAudioContext)(); const o=a.createOscillator(); const g=a.createGain(); o.connect(g); g.connect(a.destination); o.frequency.value=440; g.gain.value=0.03; o.start(); o.stop(a.currentTime+0.05);}catch(e){} }
function spawn(){ foes.push({ x: 40 + Math.random()*440, y: -20, s: (1.2+Math.random()*1.5)*speed }); }
function reset(){ alive=true; score=0; lives=3; foes=[]; bullets=[]; particles=[]; player.x=246; paused=false; }
function loop(){
  requestAnimationFrame(loop);
  if(paused) return;
  tick++;
  ctx.fillStyle="#02080e"; ctx.fillRect(0,0,c.width,c.height);
  ctx.strokeStyle="rgba(0,232,255,0.06)";
  for(let x=0;x<c.width;x+=40){ ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,c.height); ctx.stroke(); }
  if(alive){
    if(keys.ArrowLeft) player.x -= 4*speed;
    if(keys.ArrowRight) player.x += 4*speed;
    player.x = Math.max(0, Math.min(c.width-player.w, player.x));
    if(keys.Space && tick%Math.max(6, Math.floor(12/speed))===0){ bullets.push({x:player.x+player.w/2,y:player.y}); beep(); }
    if(tick%Math.max(20, Math.floor(45/speed))===0) spawn();
  }
  bullets = bullets.filter(b => b.y>-10);
  bullets.forEach(b => { b.y -= 7; ctx.fillStyle="#00e8ff"; ctx.fillRect(b.x-2,b.y,4,10); });
  foes.forEach(f => { f.y += f.s; ctx.fillStyle="#ff6b35"; ctx.fillRect(f.x,f.y,22,16); });
  for(let i=foes.length-1;i>=0;i--){
    const f=foes[i];
    if(f.y>c.height){ foes.splice(i,1); continue; }
    if(f.y+16>player.y && f.x<player.x+player.w && f.x+22>player.x){
      foes.splice(i,1); lives--; beep();
      if(lives<=0){ alive=false; best=Math.max(best,score); localStorage.setItem("vibe:shooter:best",best); }
      continue;
    }
    for(let j=bullets.length-1;j>=0;j--){
      const b=bullets[j];
      if(b.x>f.x && b.x<f.x+22 && b.y>f.y && b.y<f.y+16){
        foes.splice(i,1); bullets.splice(j,1); score+=10;
        for(let k=0;k<6;k++) particles.push({x:f.x+11,y:f.y+8,vx:(Math.random()-0.5)*4,vy:(Math.random()-0.5)*4,life:20});
        break;
      }
    }
  }
  particles = particles.filter(p => p.life>0);
  particles.forEach(p => { p.life--; p.x+=p.vx; p.y+=p.vy; ctx.fillStyle="#7cf0ff"; ctx.fillRect(p.x,p.y,2,2); });
  ctx.fillStyle="#00e8ff"; ctx.fillRect(player.x,player.y,player.w,player.h);
  scoreEl.textContent = `SCORE ${score} · BEST ${best} · LIVES ${lives}`;
  if(!alive){
    ctx.fillStyle="rgba(5,7,12,.72)"; ctx.fillRect(0,0,c.width,c.height);
    ctx.fillStyle="#00e8ff"; ctx.font="28px Bahnschrift"; ctx.fillText("SYSTEMS DOWN", 150, 150);
    ctx.font="14px Bahnschrift"; ctx.fillText("Press R or Restart", 190, 180);
    if(keys.KeyR) reset();
  }
}
document.getElementById("btnPause").onclick=()=>{ paused=!paused; };
document.getElementById("btnRestart").onclick=reset;
document.getElementById("btnMute").onclick=()=>{ muted=!muted; };
document.getElementById("btnEasy").onclick=()=>{ speed=0.75; };
document.getElementById("btnHard").onclick=()=>{ speed=1.45; };
c.onclick=()=>{ if(!alive) reset(); else paused=!paused; };
loop();
"""

    def _game_js_snake(self) -> str:
        return r"""
const c=document.getElementById("c"), ctx=c.getContext("2d"), scoreEl=document.getElementById("score");
const cell=20; let dir={x:1,y:0}, next=dir, snake=[{x:10,y:8}], food={x:15,y:8};
let score=0, best=+(localStorage.getItem("vibe:snake:best")||0), paused=false, alive=true, speed=120, acc=0, last=0;
addEventListener("keydown", e=>{
  const k=e.code;
  if(k==="ArrowUp"&&dir.y===0) next={x:0,y:-1};
  if(k==="ArrowDown"&&dir.y===0) next={x:0,y:1};
  if(k==="ArrowLeft"&&dir.x===0) next={x:-1,y:0};
  if(k==="ArrowRight"&&dir.x===0) next={x:1,y:0};
  if(k==="KeyP") paused=!paused;
  if(k==="KeyR") reset();
});
function place(){ food={x:(Math.random()*26)|0,y:(Math.random()*17)|0}; }
function reset(){ snake=[{x:10,y:8}]; dir={x:1,y:0}; next=dir; score=0; alive=true; paused=false; place(); }
function step(){
  if(!alive||paused) return;
  dir=next; const h={x:snake[0].x+dir.x,y:snake[0].y+dir.y};
  if(h.x<0||h.y<0||h.x>=26||h.y>=17||snake.some(s=>s.x===h.x&&s.y===h.y)){
    alive=false; best=Math.max(best,score); localStorage.setItem("vibe:snake:best",best); return;
  }
  snake.unshift(h);
  if(h.x===food.x&&h.y===food.y){ score+=10; place(); } else snake.pop();
}
function draw(){
  ctx.fillStyle="#02080e"; ctx.fillRect(0,0,c.width,c.height);
  ctx.fillStyle="#ff6b35"; ctx.fillRect(food.x*cell,food.y*cell,cell-1,cell-1);
  snake.forEach((s,i)=>{ ctx.fillStyle=i? "#00e8ff":"#7cf0ff"; ctx.fillRect(s.x*cell,s.y*cell,cell-1,cell-1); });
  scoreEl.textContent=`SCORE ${score} · BEST ${best} · LIVES ${alive?1:0}`;
  if(!alive){ ctx.fillStyle="rgba(0,0,0,.55)"; ctx.fillRect(0,0,c.width,c.height); ctx.fillStyle="#00e8ff"; ctx.font="24px Bahnschrift"; ctx.fillText("GAME OVER",190,160); }
}
function loop(t){ requestAnimationFrame(loop); if(!last) last=t; acc+=t-last; last=t; while(acc>speed){ step(); acc-=speed; } draw(); }
document.getElementById("btnPause").onclick=()=>paused=!paused;
document.getElementById("btnRestart").onclick=reset;
document.getElementById("btnMute").onclick=()=>{};
document.getElementById("btnEasy").onclick=()=>speed=160;
document.getElementById("btnHard").onclick=()=>speed=70;
c.onclick=()=>{ if(!alive) reset(); };
loop(0);
"""

    def _game_js_runner(self) -> str:
        return r"""
const c=document.getElementById("c"), ctx=c.getContext("2d"), scoreEl=document.getElementById("score");
let y=260, vy=0, onGround=true, obstacles=[], score=0, best=+(localStorage.getItem("vibe:runner:best")||0);
let alive=true, paused=false, speed=5, tick=0;
addEventListener("keydown", e=>{
  if((e.code==="Space"||e.code==="ArrowUp")&&onGround&&alive){ vy=-11; onGround=false; }
  if(e.code==="KeyP") paused=!paused;
  if(e.code==="KeyR") reset();
});
function reset(){ y=260; vy=0; onGround=true; obstacles=[]; score=0; alive=true; paused=false; tick=0; speed=5; }
function loop(){
  requestAnimationFrame(loop);
  if(paused) return;
  tick++;
  ctx.fillStyle="#02080e"; ctx.fillRect(0,0,c.width,c.height);
  ctx.strokeStyle="rgba(0,232,255,.2)"; ctx.beginPath(); ctx.moveTo(0,300); ctx.lineTo(c.width,300); ctx.stroke();
  if(alive){
    vy+=0.55; y+=vy; if(y>=260){ y=260; vy=0; onGround=true; }
    if(tick%Math.max(40, 70-Math.floor(speed*3))===0) obstacles.push({x:c.width, w:18+Math.random()*16, h:24+Math.random()*30});
    speed+=0.0015; score++;
  }
  obstacles=obstacles.filter(o=>o.x>-40);
  obstacles.forEach(o=>{
    o.x-=speed; ctx.fillStyle="#ff6b35"; ctx.fillRect(o.x,300-o.h,o.w,o.h);
    if(alive && o.x<70&&o.x+o.w>40&&y+20>300-o.h){ alive=false; best=Math.max(best,score); localStorage.setItem("vibe:runner:best",best); }
  });
  ctx.fillStyle="#00e8ff"; ctx.fillRect(40,y,28,28);
  scoreEl.textContent=`SCORE ${score} · BEST ${best} · LIVES ${alive?1:0}`;
  if(!alive){ ctx.fillStyle="rgba(0,0,0,.55)"; ctx.fillRect(0,0,c.width,c.height); ctx.fillStyle="#00e8ff"; ctx.font="24px Bahnschrift"; ctx.fillText("CRASHED",210,160); }
}
document.getElementById("btnPause").onclick=()=>paused=!paused;
document.getElementById("btnRestart").onclick=reset;
document.getElementById("btnMute").onclick=()=>{};
document.getElementById("btnEasy").onclick=()=>speed=3.5;
document.getElementById("btnHard").onclick=()=>speed=7;
c.onclick=()=>{ if(!alive) reset(); else if(onGround){ vy=-11; onGround=false; } };
loop();
"""

    def _tpl_video(self, name: str, pitch: str, *, research: dict[str, Any] | None = None) -> dict[str, str]:
        safe = _esc(name)
        research = research or {}
        images = [
            str(im.get("url") or "")
            for im in (research.get("images") or [])
            if str(im.get("url") or "").startswith("http")
        ]
        while len(images) < 5:
            images.append(
                f"https://picsum.photos/seed/{self._slug(name)}-v{len(images)}/960/540"
            )
        imgs_js = json.dumps(images[:8])
        cap_list = [pitch[:80]] + [f"{name} — scene {i+1}" for i in range(4)]
        captions = json.dumps(cap_list[:5])
        return {
            "index.html": f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{safe}</title>
<style>
html,body{{margin:0;height:100%;background:#05070c;color:#e8f4ff;font-family:Bahnschrift,Segoe UI,sans-serif}}
#wrap{{max-width:960px;margin:0 auto;padding:18px;display:grid;gap:12px}}
.stage{{position:relative;aspect-ratio:16/9;background:#02080e;border:1px solid rgba(0,232,255,.35);overflow:hidden}}
.stage img{{width:100%;height:100%;object-fit:cover;display:block}}
.cap{{position:absolute;left:0;right:0;bottom:0;padding:16px 18px;background:linear-gradient(transparent,rgba(0,0,0,.82));
  font-size:clamp(16px,3vw,28px);letter-spacing:.04em}}
.hud{{display:flex;flex-wrap:wrap;gap:8px}}
button{{background:transparent;border:1px solid rgba(0,232,255,.45);color:#00e8ff;padding:10px 14px;
  letter-spacing:.12em;text-transform:uppercase;cursor:pointer;font:inherit}}
button:hover{{background:rgba(0,232,255,.12)}}
.dim{{color:#7a93a8}}
</style></head><body>
<div id="wrap">
  <h1 style="margin:0;letter-spacing:.2em;color:#00e8ff">{safe}</h1>
  <p class="dim">{_esc(pitch)}</p>
  <div class="stage"><img id="frame" alt="frame"/><div class="cap" id="cap">…</div></div>
  <div class="hud">
    <button type="button" id="play">Play</button>
    <button type="button" id="pause">Pause</button>
    <button type="button" id="prev">Prev</button>
    <button type="button" id="next">Next</button>
    <button type="button" id="slower">Slower</button>
    <button type="button" id="faster">Faster</button>
    <button type="button" id="export">Export Frame</button>
  </div>
  <p class="dim">Research images + captions play as a looping reel. Export downloads the current PNG frame.</p>
</div>
<script src="video.js"></script>
</body></html>
""",
            "video.js": f"""
const imgs = {imgs_js};
const caps = {captions};
let i = 0, playing = true, ms = 2200, timer = null;
const frame = document.getElementById("frame");
const cap = document.getElementById("cap");
function show(){{
  frame.src = imgs[i % imgs.length];
  cap.textContent = caps[i % caps.length] || ("Scene " + ((i%imgs.length)+1));
}}
function tick(){{ if(!playing) return; i = (i+1) % imgs.length; show(); }}
function arm(){{ clearInterval(timer); timer = setInterval(tick, ms); }}
show(); arm();
document.getElementById("play").onclick=()=>{{ playing=true; arm(); }};
document.getElementById("pause").onclick=()=>{{ playing=false; clearInterval(timer); }};
document.getElementById("prev").onclick=()=>{{ i=(i+imgs.length-1)%imgs.length; show(); }};
document.getElementById("next").onclick=()=>{{ i=(i+1)%imgs.length; show(); }};
document.getElementById("slower").onclick=()=>{{ ms=Math.min(5000, ms+400); arm(); }};
document.getElementById("faster").onclick=()=>{{ ms=Math.max(600, ms-400); arm(); }};
document.getElementById("export").onclick=()=>{{
  const a=document.createElement("a"); a.href=frame.src; a.download="{self._slug(name)}-frame.png"; a.click();
}};
""",
            "preview.html": f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>{safe}</title>
<style>body{{margin:0;background:#02080e;color:#9adfff;font-family:Bahnschrift,sans-serif;display:grid;place-items:center;height:100vh}}
a{{color:#00e8ff;border:1px solid #00e8ff;padding:12px 18px;text-decoration:none;letter-spacing:.16em}}</style></head>
<body><div><h1>{safe}</h1><p>{_esc(pitch)}</p><a href="index.html">OPEN VIDEO STUDIO</a></div></body></html>
""",
            "README.md": self._readme(
                {"name": name, "stack": "video", "pitch": pitch},
                "template",
                ["index.html", "video.js", "preview.html", "README.md"],
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

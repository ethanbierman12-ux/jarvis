"""Local-only code customize — edit projects you control (never remote sites).

Voice: "change the layout of my website", "edit my local app", etc.
Resolves work_project_path / last vibe project, opens the IDE, and can
apply a small LLM-assisted HTML/CSS tweak to files under that root only.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Optional


_EDITABLE = {".html", ".htm", ".css", ".js", ".jsx", ".tsx", ".ts", ".json", ".md"}


class LocalCustomizer:
    def __init__(
        self,
        project_path: str = "",
        ide: str = "code",
        *,
        last_project_fn: Optional[Callable[[], Path | None]] = None,
    ) -> None:
        self.project_path = (project_path or "").strip()
        self.ide = (ide or "code").strip() or "code"
        self._last_project_fn = last_project_fn

    def resolve_root(self) -> Path | None:
        candidates: list[Path] = []
        if self.project_path:
            candidates.append(Path(self.project_path))
        if self._last_project_fn:
            try:
                lp = self._last_project_fn()
                if lp:
                    candidates.append(Path(lp))
            except Exception:
                pass
        # Recent vibe sandboxes
        vibe = Path(__file__).resolve().parents[1] / "data" / "vibe_projects"
        if vibe.is_dir():
            try:
                newest = max(
                    (p for p in vibe.iterdir() if p.is_dir()),
                    key=lambda p: p.stat().st_mtime,
                    default=None,
                )
                if newest:
                    candidates.append(newest)
            except Exception:
                pass
        for c in candidates:
            try:
                if c.exists() and c.is_dir():
                    return c.resolve()
            except Exception:
                continue
        return None

    def open_ide(self, root: Path | None = None) -> str:
        root = root or self.resolve_root()
        if root is None:
            return (
                "No local project found. Set work_project_path in settings, "
                "or vibe-code an app first."
            )
        ide = self.ide
        try:
            if ide in ("cursor", "code", "code.cmd"):
                exe = "cursor" if ide == "cursor" else "code"
                subprocess.Popen([exe, str(root)], shell=False)
            else:
                subprocess.Popen([ide, str(root)], shell=False)
            return f"Opened {root.name} in {ide} — local files only."
        except Exception as e:
            return f"Could not open IDE ({e}). Path: {root}"

    def list_editable(self, root: Path | None = None, limit: int = 24) -> list[Path]:
        root = root or self.resolve_root()
        if root is None:
            return []
        out: list[Path] = []
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in skip for part in p.parts):
                continue
            if p.suffix.lower() in _EDITABLE:
                out.append(p)
            if len(out) >= limit:
                break
        # Prefer layout-ish files first
        def rank(path: Path) -> tuple:
            name = path.name.lower()
            score = 0
            if name in ("index.html", "styles.css", "style.css", "app.css", "main.css"):
                score -= 10
            if path.suffix.lower() in (".html", ".css"):
                score -= 5
            return (score, len(path.parts), name)

        return sorted(out, key=rank)

    def apply_layout_tweak(self, instruction: str) -> str:
        """
        Apply a conservative CSS/HTML tweak under the local project root.
        Uses LLM when available; otherwise opens IDE with a clear next step.
        """
        root = self.resolve_root()
        if root is None:
            return (
                "I can only edit projects on this machine. "
                "Set work_project_path or build a local vibe app first."
            )
        instruction = (instruction or "improve the layout").strip()
        files = self.list_editable(root)
        if not files:
            self.open_ide(root)
            return (
                f"Opened {root}, but found no HTML/CSS/JS to edit. "
                "Point work_project_path at your site folder."
            )

        targets = [p for p in files if p.suffix.lower() in (".css", ".html", ".htm")][:4]
        if not targets:
            targets = files[:3]

        # Try LLM rewrite of CSS/HTML snippets
        try:
            from jarvis.core.llm_client import complete

            summaries = []
            for p in targets:
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                if len(text) > 12000:
                    text = text[:12000] + "\n/* …trimmed… */"
                summaries.append(f"FILE: {p.relative_to(root)}\n```\n{text}\n```")

            prompt = (
                f"Root: {root}\nRequest: {instruction}\n\n"
                "Return ONLY a JSON object mapping relative paths to FULL new file contents "
                "for files you change (1–3 files). Keep changes minimal and valid. "
                "No markdown fences outside JSON.\n\n"
                + "\n\n".join(summaries)
            )
            raw = complete(
                prompt,
                system=(
                    "You edit LOCAL front-end files the user owns. "
                    "Never target remote/production URLs. Output JSON path→content only."
                ),
                temperature=0.2,
                max_tokens=3500,
            ) or ""
            data = _extract_json_obj(raw)
            if data:
                changed = []
                for rel, content in data.items():
                    if not isinstance(content, str) or not rel:
                        continue
                    # Path traversal guard
                    dest = (root / str(rel)).resolve()
                    if root.resolve() not in dest.parents and dest != root.resolve():
                        continue
                    if dest.suffix.lower() not in _EDITABLE:
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(content, encoding="utf-8")
                    changed.append(str(dest.relative_to(root)))
                if changed:
                    self.open_ide(root)
                    return (
                        f"Updated local files under {root.name}: {', '.join(changed)}. "
                        "Opened in your editor — preview locally; nothing remote was touched."
                    )
        except Exception as e:
            print(f"[local-customize] LLM edit skipped: {e}")

        # Fallback: open IDE + write a short TASK note
        note = root / "JARVIS_LAYOUT_TASK.md"
        try:
            note.write_text(
                f"# Jarvis local layout task\n\n{instruction}\n\n"
                f"Edit files under `{root}` only. Do not deploy or attack remote sites.\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        msg = self.open_ide(root)
        return (
            f"{msg} I left JARVIS_LAYOUT_TASK.md with: “{instruction[:120]}”. "
            "Say vibe coding with that brief if you want a full regenerate."
        )


def _extract_json_obj(raw: str) -> dict:
    import json

    text = (raw or "").strip()
    if not text:
        return {}
    # Strip fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

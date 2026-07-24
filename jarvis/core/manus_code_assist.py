"""Manus coding assist — build safe code snapshots + light auto-offer debounce."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from jarvis.config import ROOT

# Core code + UI/web markup (html/css only accepted under ui|web|hub — see is_code_path).
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".html", ".htm"}
UI_WEB_EXTS = {".css", ".html", ".htm"}
UI_WEB_DIR_MARKERS = ("ui", "web", "hub", "companion")
SKIP_DIR_NAMES = {
    "node_modules",
    "__pycache__",
    ".git",
    "vault",
    "secrets",
    ".venv",
    "venv",
    "dist",
    "build",
    ".cursor",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
    "data",
    "sites",
    "away_notes",
    "tts",
    "exports",
    "self_audit",
    "autobug",
    "security",
}
SKIP_NAME_FRAGMENTS = (
    ".env",
    "diary.enc",
    ".diary_key",
    "secrets.dpapi",
    "credentials",
    "api_key",
    "apikey",
)
SKIP_BASENAMES = {
    "settings.json",
    "config.json",
    ".env",
    ".env.local",
    ".env.production",
    "secrets.dpapi.json",
    "diary.enc.json",
    ".diary_key",
    "data_feed.json",
    "steward_results.json",
    "steward_status.json",
    "map_3d.html",
}

DEFAULT_MAX_TOTAL = 16_000  # ~12–20KB budget
DEFAULT_DEBOUNCE_SEC = 45.0
DEFAULT_COOLDOWN_SEC = 720.0  # 12 min


def is_code_path(path: str | Path) -> bool:
    """Meaningful source change for Manus / code-watch (not data/ TTS / generated HTML)."""
    try:
        p = Path(path)
    except Exception:
        return False
    suf = p.suffix.lower()
    if suf not in CODE_EXTS:
        return False
    if should_skip_path(p):
        return False
    # .html/.css only under ui / web / hub — never generated map HTML in data/
    if suf in UI_WEB_EXTS:
        parts_lower = {x.lower() for x in p.parts}
        if not (parts_lower & set(UI_WEB_DIR_MARKERS)):
            return False
    return True


def should_skip_path(path: str | Path) -> bool:
    p = Path(path)
    parts_lower = {x.lower() for x in p.parts}
    if parts_lower & {x.lower() for x in SKIP_DIR_NAMES}:
        return True
    # jarvis/data and vault paths
    low = str(p).replace("\\", "/").lower()
    if "/jarvis/data/" in low or low.endswith("/jarvis/data"):
        return True
    if "/vault/" in low:
        return True
    if "/sites/" in low:
        return True
    name = p.name.lower()
    if name in {b.lower() for b in SKIP_BASENAMES}:
        return True
    if name.startswith("speak_") and name.endswith((".mp3", ".wav", ".ogg")):
        return True
    if any(frag in name for frag in SKIP_NAME_FRAGMENTS):
        return True
    return False


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 20)] + "\n…[truncated]…"


def _git_diff(project: Path, budget: int) -> str:
    if budget < 200:
        return ""
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=12,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode != 0 and not (r.stdout or "").strip():
            # unstaged + staged separately if HEAD missing / weird
            parts: list[str] = []
            for args in (["git", "diff", "--cached"], ["git", "diff"]):
                rr = subprocess.run(
                    args,
                    cwd=str(project),
                    capture_output=True,
                    text=True,
                    timeout=12,
                    encoding="utf-8",
                    errors="replace",
                )
                if (rr.stdout or "").strip():
                    parts.append(rr.stdout)
            out = "\n".join(parts).strip()
        else:
            out = (r.stdout or "").strip()
        if not out:
            return ""
        # Drop obviously secret-looking hunks (best-effort)
        lines = []
        for ln in out.splitlines():
            low = ln.lower()
            if any(
                k in low
                for k in (
                    "api_key",
                    "apikey",
                    "secret",
                    "password",
                    "token=",
                    "bearer ",
                )
            ) and ln.lstrip().startswith("+"):
                lines.append("+…[redacted sensitive line]…")
                continue
            lines.append(ln)
        return _truncate("\n".join(lines), budget)
    except Exception:
        return ""


def _recent_py_files(project: Path, budget: int, *, limit_files: int = 4) -> str:
    if budget < 200:
        return ""
    jarvis_root = project / "jarvis"
    search_roots = [jarvis_root if jarvis_root.is_dir() else project]
    files: list[Path] = []
    for root in search_roots:
        try:
            for p in root.rglob("*.py"):
                if should_skip_path(p):
                    continue
                try:
                    if p.is_file():
                        files.append(p)
                except Exception:
                    continue
        except Exception:
            continue
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    chunks: list[str] = []
    remaining = budget
    for p in files[:limit_files]:
        if remaining < 150:
            break
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        per = min(remaining, max(800, budget // max(1, limit_files)))
        rel = str(p.relative_to(project)) if project in p.parents or p == project else str(p)
        body = _truncate(raw, per - len(rel) - 40)
        block = f"### {rel}\n```\n{body}\n```\n"
        chunks.append(block)
        remaining -= len(block)
    return "\n".join(chunks).strip()


def _read_one_file(path: Path, budget: int) -> str:
    if should_skip_path(path) or not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return _truncate(raw, budget)


def build_snapshot(
    *,
    project_path: str = "",
    file_path: str = "",
    max_total: int = DEFAULT_MAX_TOTAL,
) -> str:
    """
    Best-effort coding snapshot for Manus review.
    Prefers git diff; falls back to recently modified .py under jarvis/.
    Never includes vault / .env / diary / settings secrets.
    """
    project = Path(project_path or str(ROOT)).expanduser()
    try:
        project = project.resolve()
    except Exception:
        project = Path(project_path or str(ROOT))

    parts: list[str] = [
        f"Project path: {project}",
        "Context: Jarvis additive desktop assistant — prefer small safe patches, "
        "try/except wrappers, no secret commits.",
    ]
    used = sum(len(p) + 1 for p in parts)
    budget = max(500, max_total - used)

    if file_path:
        fp = Path(file_path).expanduser()
        if not fp.is_absolute():
            cand = project / fp
            fp = cand if cand.exists() else fp
        try:
            fp = fp.resolve()
        except Exception:
            pass
        if should_skip_path(fp):
            parts.append(f"(Skipped sensitive path: {fp.name})")
        else:
            body = _read_one_file(fp, min(budget, 12_000))
            if body:
                parts.append(f"## File: {fp}\n```\n{body}\n```")
                used = sum(len(p) + 1 for p in parts)
                budget = max(200, max_total - used)

    diff = _git_diff(project, min(budget, 12_000))
    if diff:
        parts.append(f"## git diff (HEAD)\n```diff\n{diff}\n```")
    else:
        recent = _recent_py_files(project, min(budget, 12_000))
        if recent:
            parts.append(f"## Recent .py files (mtime)\n{recent}")
        else:
            parts.append("(No git diff and no recent .py files available.)")

    return _truncate("\n\n".join(parts), max_total)


def build_review_prompt(*, snapshot: str, focus: str = "") -> str:
    focus_bit = (focus or "").strip()
    extra = f"\nExtra focus: {focus_bit}\n" if focus_bit else "\n"
    return (
        "Please review this coding context for bugs, clarity, and Jarvis-style "
        "additive patterns (small safe changes, try/except, no secrets in commits). "
        "Suggest concrete patches (unified diff or clear file:line edits) — "
        "do not invent unrelated features.\n"
        f"{extra}"
        "--- SNAPSHOT ---\n"
        f"{snapshot}\n"
        "--- END ---"
    )


class ManusCodeAssistOffer:
    """
    Debounced + cooled-down HUD offer when code files land.
    Never auto-fires Manus create_task — only sets pending_cmd via callback.
    """

    def __init__(
        self,
        *,
        debounce_sec: float = DEFAULT_DEBOUNCE_SEC,
        cooldown_sec: float = DEFAULT_COOLDOWN_SEC,
        on_offer: Callable[[], None] | None = None,
    ) -> None:
        self.debounce_sec = float(debounce_sec)
        self.cooldown_sec = float(cooldown_sec)
        self.on_offer = on_offer
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self._timer: threading.Timer | None = None
        self._last_offer_at = 0.0
        self.enabled = True

    def note_change(self, path: str) -> None:
        if not self.enabled or not is_code_path(path):
            return
        with self._lock:
            self._pending.add(str(path))
            if self._timer is not None:
                try:
                    self._timer.cancel()
                except Exception:
                    pass
            t = threading.Timer(self.debounce_sec, self._fire)
            t.daemon = True
            self._timer = t
            t.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
            if not self._pending:
                return
            self._pending.clear()
            now = time.time()
            if now - self._last_offer_at < self.cooldown_sec:
                return
            self._last_offer_at = now
            cb = self.on_offer
        if cb:
            try:
                cb()
            except Exception as e:
                print(f"[manus-code] offer failed: {e}")

    def mark_offered(self) -> None:
        with self._lock:
            self._last_offer_at = time.time()

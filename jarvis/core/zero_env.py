"""Zero-setup agent environments — sandboxed workspaces with no host tooling required.

Full-stack agents write into jarvis/data sandboxes. Sites are static HTML (open anywhere).
Vibe projects prefer Python stdlib or static files so nothing needs installing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

WORKSPACES = DATA_DIR / "workspaces"
SITES = DATA_DIR / "sites"
VIBE = DATA_DIR / "vibe_projects"
HITL_LOG = DATA_DIR / "hitl_log.jsonl"


def ensure_agent_dirs() -> dict[str, Path]:
    """Create all agent sandboxes. Idempotent — the zero-setup bootstrap."""
    dirs = {
        "data": DATA_DIR,
        "workspaces": WORKSPACES,
        "sites": SITES,
        "vibe": VIBE,
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    marker = WORKSPACES / "README.md"
    if not marker.exists():
        marker.write_text(
            "# Jarvis agent workspaces\n\n"
            "Zero-setup sandboxes. Agents build here without installing Node/npm "
            "or configuring a host environment. Approve HITL gates to ship or open externally.\n",
            encoding="utf-8",
        )
    return dirs


def workspace_for(agent: str, slug: str) -> Path:
    ensure_agent_dirs()
    root = WORKSPACES / agent / slug
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_env_manifest(root: Path, *, stack: str, files: list[str], notes: str = "") -> Path:
    """Manifest so any machine can open the project with zero setup."""
    root.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {
        "zero_setup": True,
        "stack": stack,
        "files": files,
        "run": _run_hint(stack),
        "notes": notes
        or (
            "CDN Three.js/GSAP allowed — no npm. Open via Jarvis HTTP preview."
            if (stack or "").lower() in ("3d", "animation")
            else "Open index.html or run with system Python. No package install required."
        ),
    }
    path = root / "jarvis.env.json"
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def _run_hint(stack: str) -> str:
    s = (stack or "").lower()
    if "python" in s:
        return "python main.py"
    if s in ("3d", "animation") or "three" in s or "webgl" in s:
        return "Serve folder over HTTP and open index.html (CDN Three.js / GSAP — no npm)."
    if "static" in s or "html" in s or "site" in s or s in ("web", "game", "video", "dashboard"):
        return "open index.html (or use the Jarvis sandbox preview URL)"
    return "open README.md — sandbox is self-contained"


def log_hitl(event: dict[str, Any]) -> None:
    ensure_agent_dirs()
    try:
        with HITL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass

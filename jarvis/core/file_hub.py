"""Voice File Hub — search local roots and open with the OS default app.

Owner desk only: Documents / Desktop / Downloads / DATA_DIR / project ROOT
plus optional extra roots from settings. Soft-fail; never raises to callers.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "AppData",
}


class FileHub:
    """Local file search + open for voice desk commands."""

    def __init__(
        self,
        *,
        data_dir: Path,
        project_root: Path,
        enabled: bool = True,
        extra_roots: list[str] | None = None,
        max_results: int = 12,
        max_scan: int = 4000,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.project_root = Path(project_root)
        self.enabled = bool(enabled)
        self.extra_roots = [str(r).strip() for r in (extra_roots or []) if str(r).strip()]
        self.max_results = max(1, min(int(max_results or 12), 40))
        self.max_scan = max(200, min(int(max_scan or 4000), 20000))

    def status(self) -> str:
        if not self.enabled:
            return "File hub disabled."
        roots = self.roots()
        return f"File hub online · {len(roots)} roots · limit {self.max_results}."

    def roots(self) -> list[Path]:
        """Resolve search roots; empty extra_roots → auto home folders."""
        out: list[Path] = []
        seen: set[str] = set()

        def _add(p: Path | None) -> None:
            if p is None:
                return
            try:
                rp = p.expanduser().resolve()
            except Exception:
                rp = Path(p).expanduser()
            key = str(rp).lower()
            if key in seen:
                return
            if not rp.exists() or not rp.is_dir():
                return
            seen.add(key)
            out.append(rp)

        home = Path.home()
        if self.extra_roots:
            for raw in self.extra_roots:
                _add(Path(raw))
        else:
            for name in ("Documents", "Desktop", "Downloads"):
                _add(home / name)
                # OneDrive mirrors on some Windows setups
                _add(home / "OneDrive" / name)
        _add(self.data_dir)
        _add(self.project_root)
        # Always include security folders when present
        _add(self.data_dir / "security")
        _add(self.data_dir / "intrusions")
        return out

    def search(self, query: str, *, limit: int | None = None) -> list[Path]:
        """Fuzzy-ish filename search across roots. Soft-fail → []."""
        if not self.enabled:
            return []
        q = (query or "").strip().lower()
        if not q or q in ("please", "now", "sir", "the", "a", "an"):
            return []
        lim = max(1, min(int(limit or self.max_results), 40))
        tokens = [t for t in re.split(r"[^\w.\-]+", q) if t and t not in ("the", "a", "an", "file", "folder")]
        if not tokens:
            tokens = [q]
        hits: list[tuple[int, float, Path]] = []
        scanned = 0
        try:
            for root in self.roots():
                if scanned >= self.max_scan:
                    break
                try:
                    for dirpath, dirnames, filenames in os.walk(root):
                        # prune heavy / junk trees
                        dirnames[:] = [
                            d
                            for d in dirnames
                            if d not in _SKIP_DIRS and not d.startswith(".")
                        ]
                        for name in filenames:
                            scanned += 1
                            if scanned > self.max_scan:
                                break
                            low = name.lower()
                            score = 0.0
                            if q in low:
                                score = 100.0 - abs(len(low) - len(q)) * 0.1
                            else:
                                matched = sum(1 for t in tokens if t in low)
                                if matched == 0:
                                    continue
                                score = (matched / len(tokens)) * 80.0
                                if low.startswith(tokens[0]):
                                    score += 10.0
                            if score < 40.0:
                                continue
                            try:
                                path = Path(dirpath) / name
                                mtime = path.stat().st_mtime
                            except Exception:
                                continue
                            hits.append((int(score * 10), mtime, path))
                        if scanned > self.max_scan:
                            break
                except Exception:
                    continue
        except Exception as e:
            print(f"[file_hub] search: {e}")
            return []
        hits.sort(key=lambda x: (x[0], x[1]), reverse=True)
        # Dedupe by resolved path
        seen: set[str] = set()
        out: list[Path] = []
        for _, _, p in hits:
            try:
                key = str(p.resolve()).lower()
            except Exception:
                key = str(p).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
            if len(out) >= lim:
                break
        return out

    def open_path(self, path: str | Path) -> str:
        """Open with OS default app (os.startfile on Windows)."""
        try:
            p = Path(path)
            if not p.exists():
                return f"File not found: {p.name}"
            if os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                import subprocess

                subprocess.Popen(["xdg-open", str(p)], shell=False)
            kind = "folder" if p.is_dir() else "file"
            return f"Opening {kind} {p.name}."
        except Exception as e:
            return f"Could not open that file ({e})."

    def find_and_open(self, query: str) -> str:
        """Search then open top match; speak-friendly summary."""
        if not self.enabled:
            return "File hub is disabled in settings."
        hits = self.search(query)
        if not hits:
            return f"No file matching {query[:60]!r}."
        top = hits[0]
        msg = self.open_path(top)
        if len(hits) > 1:
            others = ", ".join(h.name for h in hits[1:4])
            return f"{msg} Also found: {others}."
        return msg

    def open_last_intrusion(self) -> str:
        """Open newest JPEG under DATA_DIR/intrusions or last_vision.jpg."""
        try:
            folder = self.data_dir / "intrusions"
            newest: Path | None = None
            if folder.is_dir():
                pics = sorted(
                    [
                        p
                        for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png")
                    ],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                newest = pics[0] if pics else None
            if newest is None:
                fallback = self.data_dir / "last_vision.jpg"
                if fallback.is_file():
                    newest = fallback
            if newest is None:
                return "No intrusion snapshot on file."
            return self.open_path(newest)
        except Exception as e:
            return f"Could not open last intrusion ({e})."

    def open_security_log_folder(self) -> str:
        """Open DATA_DIR/security (encrypted event log folder)."""
        try:
            folder = self.data_dir / "security"
            folder.mkdir(parents=True, exist_ok=True)
            return self.open_path(folder)
        except Exception as e:
            return f"Could not open security log folder ({e})."

    def handle_voice(self, text: str) -> str | None:
        """Parse voice intents; return spoken reply or None if not a file-hub cmd."""
        if not self.enabled:
            return None
        t = (text or "").strip().lower()
        if not t:
            return None
        if re.search(
            r"\b(open|show|pull up)\s+(the\s+)?(last\s+)?(intrusion|intruder)(\s+(snap|snapshot|photo|image))?\b",
            t,
        ):
            return self.open_last_intrusion()
        if re.search(
            r"\b(open|show)\s+(the\s+)?(security\s+log\s+folder|security\s+folder|intrusions?\s+folder)\b",
            t,
        ):
            return self.open_security_log_folder()
        # Prefer explicit "file" forms; bare pull-up/open only with extension-ish query
        m = re.search(
            r"\b(?:open|find|locate|search for)\s+(?:the\s+)?file\s+(.+)$",
            t,
        )
        if not m:
            m = re.search(r"\bpull up\s+(?:the\s+)?(?:file\s+)?(.+)$", t)
        if not m:
            m = re.search(
                r"\b(?:open|find)\s+(.+\.(?:pdf|docx?|xlsx?|pptx?|txt|md|csv|json|jpg|jpeg|png|gif|mp4|mp3|wav|zip|py|js|ts|tsx|html|css))\b",
                t,
            )
        if m:
            q = m.group(1).strip(" .,!?\"'")
            # Avoid colliding with app/camera/map intents
            if re.search(
                r"^(camera|map|news|pdtester|aerospatial|fabricator|ops(\s+hud|\s+map)?|"
                r"settings|browser|chrome|edge|firefox|spotify|calculator|notepad|"
                r"discord|slack|steam|code|vs ?code|terminal|powershell|"
                r"phone|companion|pd tester|command deck|tools panel)\b",
                q,
            ):
                return None
            if q.startswith("last intrusion") or q.startswith("security log"):
                return None
            if len(q) < 2:
                return "What file should I open?"
            return self.find_and_open(q)
        return None

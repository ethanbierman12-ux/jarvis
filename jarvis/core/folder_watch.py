"""Watch folders (Downloads / workspace) and notify Jarvis of new files."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Collection

# Directories never worth notifying about (path segment match).
SKIP_DIR_NAMES = (
    "node_modules",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "vault",
    "secrets",
    "data",
    "sites",
    "away_notes",
    "tts",
    "exports",
    "self_audit",
    "autobug",
    "security",
    "dist",
    "build",
    ".cursor",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
)

# Incomplete / editor / OS junk suffixes.
SKIP_SUFFIXES = (
    ".tmp",
    ".crdownload",
    ".partial",
    ".part",
    ".download",
    ".swp",
    ".swo",
    ".pid",
    ".lock",
    ".log",
    ".pyc",
    ".pyo",
    ".pyd",
)

# Runtime / HUD churn that lives under jarvis/ (and sometimes Downloads).
NOISE_BASENAMES = {
    "data_feed.json",
    "steward_results.json",
    "steward_status.json",
    "away_queue.json",
    "away_diagnostics.json",
    "web_search.json",
    "habits.json",
    "command_sequences.json",
    "sites_index.json",
    "rlhf_state.json",
    "wake_agent.lock",
    "thumbs.db",
    "desktop.ini",
    ".ds_store",
}

NOISE_NAME_PREFIXES = (
    "speak_",  # TTS temp: speak_<uuid>.mp3
    "last_",  # last_scan.jpg / last_vision.jpg churn
)

# Downloads: ignore these even when not under jarvis/data.
DOWNLOADS_NOISE_SUFFIXES = (
    ".lnk",
    ".url",
    ".ini",
    ".bak",
)


def is_watch_noise(path: str | Path) -> bool:
    """True for runtime churn that must never queue HUD / tasks / Manus offers."""
    try:
        p = Path(path)
    except Exception:
        return True
    low = str(p).replace("\\", "/").lower()
    name = p.name.lower()

    parts = {x.lower() for x in p.parts}
    if parts & {x.lower() for x in SKIP_DIR_NAMES}:
        return True

    if any(f"/{skip}/" in f"/{low}/" or low.endswith(f"/{skip}") for skip in SKIP_DIR_NAMES):
        return True

    if name in NOISE_BASENAMES:
        return True
    if any(name.startswith(pref) for pref in NOISE_NAME_PREFIXES):
        return True
    if any(name.endswith(ext) for ext in SKIP_SUFFIXES):
        return True
    if name.startswith(".") and name.endswith(("~", ".swp", ".swo")):
        return True
    # Encrypted / log / diary churn
    if name.endswith((".enc.json", ".jsonl")) and (
        "diary" in name or "hitl" in name or "rlhf" in name or "jarvis.log" in name
    ):
        return True
    if name.startswith("jarvis.log"):
        return True
    if name.startswith("away-") and name.endswith(".md"):
        return True
    if name.startswith("audit_") and name.endswith(".md"):
        return True
    return False


class FolderWatch:
    def __init__(
        self,
        paths: list[str | Path],
        on_new: Callable[[str], None],
        *,
        enabled: bool = True,
        settle_sec: float = 1.5,
        recursive: bool = False,
        also_modified: bool = False,
        allow_suffixes: Collection[str] | None = None,
    ) -> None:
        self.paths = [Path(p).expanduser() for p in paths if p]
        self.on_new = on_new
        self.enabled = enabled
        self.settle_sec = settle_sec
        self.recursive = bool(recursive)
        self.also_modified = bool(also_modified)
        # When set (e.g. code-assist), only these extensions may queue.
        self.allow_suffixes = (
            {s.lower() if s.startswith(".") else f".{s.lower()}" for s in allow_suffixes}
            if allow_suffixes
            else None
        )
        self._observer = None
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled or not self.paths:
            return
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except Exception as e:
            print(f"[watch] watchdog not installed: {e}")
            return

        watch = self

        class Handler(FileSystemEventHandler):
            def _queue(self, path: str) -> None:
                try:
                    if is_watch_noise(path):
                        return
                    p = Path(path)
                    suffix = p.suffix.lower()
                    if watch.allow_suffixes is not None and suffix not in watch.allow_suffixes:
                        return
                    # Downloads-side junk (non-recursive watches usually)
                    if not watch.recursive and any(
                        p.name.lower().endswith(ext) for ext in DOWNLOADS_NOISE_SUFFIXES
                    ):
                        return
                except Exception:
                    return
                with watch._lock:
                    watch._pending[path] = time.time()

            def on_created(self, event) -> None:  # noqa: N802
                if event.is_directory:
                    return
                self._queue(str(event.src_path))

            def on_modified(self, event) -> None:  # noqa: N802
                if not watch.also_modified or event.is_directory:
                    return
                self._queue(str(event.src_path))

            def on_moved(self, event) -> None:  # noqa: N802
                if event.is_directory:
                    return
                dest = getattr(event, "dest_path", None) or event.src_path
                self._queue(str(dest))

        observer = Observer()
        handler = Handler()
        for p in self.paths:
            try:
                p.mkdir(parents=True, exist_ok=True)
                observer.schedule(handler, str(p), recursive=self.recursive)
                print(f"[watch] monitoring {p} (recursive={self.recursive})")
            except Exception as e:
                print(f"[watch] skip {p}: {e}")
        observer.daemon = True
        observer.start()
        self._observer = observer
        self._thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="jarvis-watch"
        )
        self._thread.start()

    def stop(self) -> None:
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
            self._observer = None

    def _flush_loop(self) -> None:
        while True:
            time.sleep(1.0)
            ready: list[str] = []
            now = time.time()
            with self._lock:
                for path, ts in list(self._pending.items()):
                    if now - ts >= self.settle_sec:
                        ready.append(path)
                        self._pending.pop(path, None)
            for path in ready:
                try:
                    self.on_new(path)
                except Exception as e:
                    print(f"[watch] notify failed: {e}")

"""Launch installed apps + common folders via fuzzy match."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from thefuzz import process as fuzz

from jarvis.core.camera_intent import is_camera_query

# Common Start Menu roots on Windows
_START_DIRS = [
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
    Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
]

_WEB = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "spotify web": "https://open.spotify.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://www.wikipedia.org",
    "twitter": "https://x.com",
    "facebook": "https://www.facebook.com",
}

_FOLDERS = {
    "documents": Path.home() / "Documents",
    "downloads": Path.home() / "Downloads",
    "videos": Path.home() / "Videos",
    "music": Path.home() / "Music",
    "pictures": Path.home() / "Pictures",
    "desktop": Path.home() / "Desktop",
}


class AppLauncher:
    def __init__(self, open_on_other: bool = True) -> None:
        self._index: dict[str, Path] = {}
        self.open_on_other = open_on_other
        self._rebuild()

    def _rebuild(self) -> None:
        idx: dict[str, Path] = {}
        for root in _START_DIRS:
            if not root.exists():
                continue
            for p in root.rglob("*.lnk"):
                idx[p.stem.lower()] = p
        # Direct executables shortcuts
        for name, path in {
            "chrome": Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            "spotify": Path(os.environ.get("APPDATA", "")) / r"Spotify\Spotify.exe",
            "code": Path(os.environ.get("LOCALAPPDATA", "")) / r"Programs\Microsoft VS Code\Code.exe",
            "notepad": Path(r"C:\Windows\System32\notepad.exe"),
            "explorer": Path(r"C:\Windows\explorer.exe"),
        }.items():
            if path.exists():
                idx[name] = path
        self._index = idx

    def open(self, query: str) -> str:
        q = query.strip().lower()
        if not q:
            return "What should I open?"

        if is_camera_query(q) or is_camera_query("open " + q):
            return "CAMERA_UI"  # brain opens EMEET live feed — never shell-open

        if q in _WEB:
            if self.open_on_other:
                try:
                    from jarvis.core.displays import displays

                    return displays.open_url_on(_WEB[q], "secondary")
                except Exception:
                    pass
            webbrowser.open(_WEB[q])
            return f"Opening {q}."

        if q in _FOLDERS:
            path = _FOLDERS[q]
            os.startfile(path)  # type: ignore[attr-defined]
            if self.open_on_other:
                try:
                    from jarvis.core.displays import displays
                    import threading

                    threading.Timer(
                        0.9,
                        lambda: displays.move_recent_windows_to(
                            "secondary", titles=("explorer", path.name.lower())
                        ),
                    ).start()
                except Exception:
                    pass
            return f"Opening {path.name}."

        # Fuzzy against Start Menu
        if self._index:
            match, score = fuzz.extractOne(q, list(self._index.keys())) or (None, 0)
            if match and score >= 70:
                target = self._index[match]
                try:
                    if self.open_on_other and target.suffix.lower() == ".exe":
                        from jarvis.core.displays import displays

                        return displays.open_app_on(str(target), "secondary")
                    os.startfile(target)  # type: ignore[attr-defined]
                except Exception:
                    subprocess.Popen([str(target)], shell=False)
                if self.open_on_other:
                    try:
                        from jarvis.core.displays import displays
                        import threading

                        threading.Timer(
                            1.0,
                            lambda: displays.move_recent_windows_to(
                                "secondary", titles=(match, target.stem.lower())
                            ),
                        ).start()
                    except Exception:
                        pass
                return f"Opening {match}."

        # Fallback: shell start — but NEVER for camera typos
        if is_camera_query(q):
            return "CAMERA_UI"
        try:
            subprocess.Popen(["cmd", "/c", "start", "", query], shell=False)
            return f"Trying to open {query}."
        except Exception as e:
            return f"Could not open {query}: {e}"

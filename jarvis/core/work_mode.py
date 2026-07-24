"""Work mode — open IDE, project folders, work apps; quiet notifications."""

from __future__ import annotations

import os
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Sequence


class WorkMode:
    def __init__(
        self,
        project_path: str = "",
        ide: str = "code",
        apps: Sequence[str] | None = None,
        urls: Sequence[str] | None = None,
        app_launcher=None,
    ) -> None:
        self.project_path = project_path or str(Path.home() / "Documents")
        self.ide = ide or "code"
        self.apps = list(apps or ("code", "chrome"))
        self.urls = list(
            urls
            or (
                "https://mail.google.com",
                "https://github.com",
            )
        )
        self.apps_launcher = app_launcher

    def start_work(self) -> str:
        done: list[str] = []
        # Do NOT open Windows Focus Assist settings — that pops a Settings window
        # every time and fights the user. Silent work launch only.

        proj = Path(self.project_path)
        if proj.exists():
            try:
                os.startfile(str(proj))  # type: ignore[attr-defined]
                done.append(f"opened {proj.name}")
            except Exception:
                pass

        ide_msg = self._open_ide(proj if proj.exists() else None)
        if ide_msg:
            done.append(ide_msg)

        if self.apps_launcher:
            for name in self.apps:
                if name.lower() in ("code", "vscode", "cursor", self.ide.lower()):
                    continue
                try:
                    self.apps_launcher.open(name)
                    done.append(name)
                except Exception:
                    pass

        for url in self.urls[:5]:
            try:
                from jarvis.core.displays import displays

                displays.open_url_on(url, "secondary")
                time.sleep(0.2)
            except Exception:
                try:
                    webbrowser.open(url)
                    time.sleep(0.15)
                except Exception:
                    pass
        if self.urls:
            done.append(f"{len(self.urls)} work tabs")

        if not done:
            return "Work mode tried, but nothing launched — check work settings."
        return "Work mode on: " + ", ".join(done) + "."

    def end_work(self) -> str:
        return "Work mode off."

    def _open_ide(self, project: Path | None) -> str:
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / r"Programs\cursor\Cursor.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / r"Programs\Microsoft VS Code\Code.exe",
            Path(r"C:\Program Files\Microsoft VS Code\Code.exe"),
        ]
        ide = self.ide.lower()
        for path in candidates:
            if not path.exists():
                continue
            name = path.stem.lower()
            if ide == "cursor" and "cursor" not in name:
                continue
            if ide in ("code", "vscode") and "cursor" in name:
                # Prefer Code.exe when ide is code; still allow Cursor as fallback later
                if any(p.exists() and "code" in p.stem.lower() for p in candidates):
                    if "code" not in name:
                        continue
            args = [str(path)]
            if project:
                args.append(str(project))
            try:
                subprocess.Popen(args, shell=False)
                return f"opened {path.stem}"
            except Exception:
                continue
        if self.apps_launcher:
            try:
                self.apps_launcher.open(self.ide)
                return f"opened {self.ide}"
            except Exception:
                pass
        return ""

    def _enable_focus_assist(self) -> str:
        """Deprecated — never open Settings UI (was popping Focus Assist constantly)."""
        return ""

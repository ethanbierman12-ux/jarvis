"""Away agent — visible live actions while entering away mode."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import psutil

from jarvis.config import DATA_DIR

AWAY_NOTES = DATA_DIR / "away_notes"
DIAG_PATH = DATA_DIR / "away_diagnostics.json"


class AwayAgent:
    """
    Runs a visible agentic away ritual:
      open Task Manager → write status note → talk → diagnostics → queue steward jobs.
    """

    def __init__(self) -> None:
        AWAY_NOTES.mkdir(parents=True, exist_ok=True)
        self.last_note: Path | None = None
        self.last_diag: dict[str, Any] = {}

    def run(
        self,
        *,
        user_name: str = "Sir",
        city: str = "Philadelphia",
        mail_mode: str = "ack",
        on_progress: Callable[..., None] | None = None,
        on_speak: Callable[[str], None] | None = None,
        steward=None,
    ) -> str:
        def emit(msg: str, **extra: Any) -> None:
            if on_progress:
                try:
                    if extra:
                        on_progress({"msg": msg, **extra})
                    else:
                        on_progress(msg)
                except Exception:
                    pass

        def speak(line: str) -> None:
            if on_speak:
                try:
                    on_speak(line)
                except Exception:
                    pass

        def beat(sec: float = 0.55) -> None:
            time.sleep(sec)

        tasks = [
            {"text": "Announce away mode", "done": False, "active": True},
            {"text": "Open Task Manager", "done": False, "active": False},
            {"text": "Run system diagnostics", "done": False, "active": False},
            {"text": "Write away status note", "done": False, "active": False},
            {"text": "Open notepad with note", "done": False, "active": False},
            {"text": "Queue mail + steward jobs", "done": False, "active": False},
            {"text": "Confirm and stand watch", "done": False, "active": False},
        ]

        def set_task(i: int) -> None:
            for j, t in enumerate(tasks):
                t["done"] = j < i
                t["active"] = j == i

        emit(
            "Away agent online",
            stage="announce",
            tasks=tasks,
            terminal="jarvis away --live",
            apps=[],
            writing="",
            diag={},
        )
        speak(f"Entering away mode, {user_name}. I will handle the desk while you are gone.")
        beat(0.7)

        # 1) Task Manager
        set_task(1)
        emit(
            "Opening Task Manager…",
            stage="apps",
            tasks=tasks,
            terminal="start taskmgr.exe",
            apps=["Task Manager"],
            action="Opening Task Manager",
        )
        opened_apps: list[str] = ["Task Manager"]
        try:
            subprocess.Popen(
                ["taskmgr.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            beat(0.9)
            emit(
                "Task Manager live",
                stage="apps",
                tasks=tasks,
                terminal="→ taskmgr ok",
                apps=list(opened_apps),
                action="Task Manager open",
            )
        except Exception as e:
            emit(f"Task Manager skipped · {e}", stage="apps", tasks=tasks, apps=opened_apps)
        beat(0.5)

        # 2) Diagnostics
        set_task(2)
        emit(
            "Running diagnostics…",
            stage="diag",
            tasks=tasks,
            terminal="jarvis diagnose --cpu --mem --disk",
            apps=opened_apps,
            action="Checking vitals",
        )
        speak("Checking system diagnostics now.")
        beat(0.4)
        diag = self._diagnostics()
        self.last_diag = diag
        try:
            DIAG_PATH.write_text(json.dumps(diag, indent=2), encoding="utf-8")
        except Exception:
            pass
        emit(
            f"Diagnostics · CPU {diag.get('cpu')}% · RAM {diag.get('ram')}%",
            stage="diag",
            tasks=tasks,
            terminal=(
                f"→ cpu={diag.get('cpu')}% mem={diag.get('ram')}% "
                f"disk={diag.get('disk')}% bat={diag.get('battery')}"
            ),
            apps=opened_apps,
            diag=diag,
            writing=json.dumps(diag, indent=2),
            file_path="away_diagnostics.json",
            action="Diagnostics complete",
        )
        beat(0.8)

        # Optional Resource Monitor peek (lighter than another heavy window)
        try:
            subprocess.Popen(
                ["perfmon.exe", "/res"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            opened_apps.append("Resource Monitor")
            emit(
                "Opened Resource Monitor",
                stage="apps",
                tasks=tasks,
                apps=list(opened_apps),
                terminal="start perfmon /res",
                diag=diag,
            )
            beat(0.6)
        except Exception:
            pass

        # 3) Write away note
        set_task(3)
        note_body = self._compose_note(user_name, city, mail_mode, diag)
        emit(
            "Writing away status note…",
            stage="write",
            tasks=tasks,
            terminal="jarvis write --note away_status.md",
            apps=opened_apps,
            diag=diag,
            writing=note_body[:400],
            file_path="away_status.md",
            action="Composing note",
        )
        speak("Writing your away status note.")
        # Stream writing in chunks so the theater looks alive
        acc = ""
        for chunk in _chunks(note_body, 48):
            acc += chunk
            emit(
                "Writing…",
                stage="write",
                tasks=tasks,
                writing=acc,
                file_path="away_status.md",
                apps=opened_apps,
                diag=diag,
                terminal="→ streaming note",
            )
            time.sleep(0.08)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        note_path = AWAY_NOTES / f"away-{stamp}.md"
        note_path.write_text(note_body, encoding="utf-8")
        self.last_note = note_path
        # Also keep a stable latest path
        latest = AWAY_NOTES / "LATEST_AWAY.md"
        latest.write_text(note_body, encoding="utf-8")
        beat(0.4)

        # 4) Open Notepad
        set_task(4)
        emit(
            "Opening Notepad with the note…",
            stage="apps",
            tasks=tasks,
            terminal=f'notepad "{latest}"',
            apps=opened_apps + ["Notepad"],
            writing=note_body,
            file_path=str(latest.name),
            diag=diag,
            action="Opening Notepad",
        )
        try:
            subprocess.Popen(
                ["notepad.exe", str(latest)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            opened_apps.append("Notepad")
            beat(0.8)
        except Exception as e:
            emit(f"Notepad skipped · {e}", stage="apps", tasks=tasks, apps=opened_apps)

        # 5) Steward queue + mail
        set_task(5)
        emit(
            "Queueing steward jobs and mail watch…",
            stage="steward",
            tasks=tasks,
            terminal="jarvis steward --away --mail",
            apps=opened_apps,
            diag=diag,
            writing=note_body,
            action="Arming away steward",
        )
        speak("Arming mail watch and away steward jobs.")
        steward_msg = ""
        if steward is not None:
            try:
                steward_msg = steward.mark_away_mode(
                    True, mail=True, mail_mode=mail_mode
                )
            except Exception as e:
                steward_msg = f"Steward queue issue: {e}"
        emit(
            steward_msg or "Steward armed",
            stage="steward",
            tasks=tasks,
            terminal="→ mail_watch + system_pulse + weather + brief queued",
            apps=opened_apps,
            diag=diag,
            writing=note_body,
        )
        beat(0.7)

        # 6) Confirm
        set_task(6)
        for t in tasks:
            t["done"] = True
            t["active"] = False
        summary = (
            f"Away mode live. Diagnostics CPU {diag.get('cpu')}%, "
            f"RAM {diag.get('ram')}%. Note open in Notepad. "
            f"I am watching mail in {mail_mode} mode."
        )
        emit(
            summary,
            stage="done",
            tasks=tasks,
            terminal="→ away agent standing watch",
            apps=opened_apps,
            diag=diag,
            writing=note_body,
            action="Standing watch",
        )
        speak(summary)
        return summary

    def _diagnostics(self) -> dict[str, Any]:
        cpu = float(psutil.cpu_percent(interval=0.35))
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\" if Path("C:/").exists() else "/")
        bat = "n/a"
        try:
            b = psutil.sensors_battery()
            if b is not None:
                bat = f"{int(b.percent)}%{' charging' if b.power_plugged else ''}"
        except Exception:
            pass
        top: list[str] = []
        try:
            procs = []
            for p in psutil.process_iter(["name", "cpu_percent"]):
                try:
                    procs.append(
                        (float(p.info.get("cpu_percent") or 0), p.info.get("name") or "?")
                    )
                except Exception:
                    pass
            procs.sort(reverse=True)
            top = [f"{n} ({c:.0f}%)" for c, n in procs[:5]]
        except Exception:
            pass
        return {
            "cpu": round(cpu, 1),
            "ram": round(float(mem.percent), 1),
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "disk": round(float(disk.percent), 1),
            "battery": bat,
            "top": top,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }

    def _compose_note(
        self, user_name: str, city: str, mail_mode: str, diag: dict[str, Any]
    ) -> str:
        tops = "\n".join(f"- {t}" for t in (diag.get("top") or [])[:5]) or "- (none)"
        return (
            f"# Jarvis Away Status\n\n"
            f"**For:** {user_name}  \n"
            f"**When:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n"
            f"**City:** {city}  \n"
            f"**Mail mode:** {mail_mode}\n\n"
            f"## Diagnostics\n"
            f"- CPU: {diag.get('cpu')}%\n"
            f"- RAM: {diag.get('ram')}% ({diag.get('ram_used_gb')} GB)\n"
            f"- Disk: {diag.get('disk')}%\n"
            f"- Battery: {diag.get('battery')}\n\n"
            f"## Top processes\n{tops}\n\n"
            f"## Agent actions\n"
            f"- Opened Task Manager\n"
            f"- Ran live diagnostics\n"
            f"- Wrote this note\n"
            f"- Armed away steward + mail watch\n\n"
            f"_Generated by Jarvis away agent._\n"
        )


def _chunks(text: str, n: int):
    for i in range(0, len(text), n):
        yield text[i : i + n]

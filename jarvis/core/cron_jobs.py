"""In-process cron / micro-agent registry for background Jarvis jobs."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR

CRON_PATH = DATA_DIR / "cron_jobs.json"


@dataclass
class CronJob:
    id: str
    every_sec: int
    label: str
    kind: str = "ping"
    enabled: bool = True
    last_run: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


class CronRegistry:
    """
    Lightweight scheduler — researcher / tester / monitor micro-agents
    wake on intervals and report only when the callback returns text.
    """

    def __init__(self, on_report: Callable[[str], None] | None = None) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.on_report = on_report
        self._jobs: dict[str, CronJob] = {}
        self._handlers: dict[str, Callable[[CronJob], str | None]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._load()
        self._ensure_defaults()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="jarvis-cron"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> str:
        if not self._jobs:
            return "Cron registry empty."
        bits = []
        for j in self._jobs.values():
            state = "on" if j.enabled else "off"
            ago = int(time.time() - j.last_run) if j.last_run else -1
            bits.append(
                f"{j.id}: every {j.every_sec}s ({state})"
                + (f", last {ago}s ago" if ago >= 0 else ", never")
            )
        return "Micro-agents — " + "; ".join(bits) + "."

    def register_handler(self, kind: str, fn: Callable[[CronJob], str | None]) -> None:
        self._handlers[kind] = fn

    def add(self, job_id: str, every_sec: int, label: str, kind: str = "ping") -> str:
        job = CronJob(
            id=job_id,
            every_sec=max(30, int(every_sec)),
            label=label,
            kind=kind,
            enabled=True,
        )
        self._jobs[job_id] = job
        self._save()
        return f"Scheduled {job_id} every {job.every_sec}s — {label}."

    def enable(self, job_id: str, on: bool = True) -> str:
        j = self._jobs.get(job_id)
        if not j:
            return f"No cron job {job_id}."
        j.enabled = on
        self._save()
        return f"{job_id} {'enabled' if on else 'disabled'}."

    def _ensure_defaults(self) -> None:
        defaults = [
            CronJob("sys_monitor", 300, "CPU/RAM pulse", "sys_monitor"),
            CronJob("horizon_scan", 3600, "Tech horizon blip", "horizon"),
            CronJob("package_watch", 1800, "Shipment ledger nudge", "packages"),
        ]
        changed = False
        for d in defaults:
            if d.id not in self._jobs:
                self._jobs[d.id] = d
                changed = True
        if changed:
            self._save()

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            for j in list(self._jobs.values()):
                if not j.enabled:
                    continue
                if j.last_run and now - j.last_run < j.every_sec:
                    continue
                j.last_run = now
                try:
                    fn = self._handlers.get(j.kind)
                    msg = fn(j) if fn else None
                    if msg and self.on_report:
                        self.on_report(msg)
                except Exception as e:
                    print(f"[cron] {j.id}: {e}")
            self._save()
            self._stop.wait(15.0)

    def _load(self) -> None:
        try:
            raw = json.loads(CRON_PATH.read_text(encoding="utf-8"))
            for row in raw.get("jobs") or []:
                j = CronJob(
                    id=row["id"],
                    every_sec=int(row.get("every_sec") or 300),
                    label=row.get("label") or row["id"],
                    kind=row.get("kind") or "ping",
                    enabled=bool(row.get("enabled", True)),
                    last_run=float(row.get("last_run") or 0),
                    meta=row.get("meta") or {},
                )
                self._jobs[j.id] = j
        except Exception:
            self._jobs = {}

    def _save(self) -> None:
        blob = {"jobs": [asdict(j) for j in self._jobs.values()]}
        CRON_PATH.write_text(json.dumps(blob, indent=2), encoding="utf-8")

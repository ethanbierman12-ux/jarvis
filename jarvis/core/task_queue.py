"""Lightweight background task queue — Celery-lite without Docker freeze risk."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TaskItem:
    id: str
    name: str
    status: str = "queued"  # queued|running|done|error
    result: str = ""
    error: str = ""
    created: float = field(default_factory=time.time)


class TaskQueue:
    """Daemon workers so voice stays responsive during heavy jobs."""

    def __init__(self, workers: int = 2) -> None:
        self._q: queue.Queue[tuple[str, Callable[[], str]]] = queue.Queue()
        self._items: dict[str, TaskItem] = {}
        self._lock = threading.Lock()
        self._workers = max(1, int(workers))
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for i in range(self._workers):
            threading.Thread(
                target=self._loop,
                daemon=True,
                name=f"jarvis-task-{i}",
            ).start()

    def submit(self, name: str, fn: Callable[[], str]) -> str:
        self.start()
        tid = uuid.uuid4().hex[:10]
        item = TaskItem(id=tid, name=name)
        with self._lock:
            self._items[tid] = item
        self._q.put((tid, fn))
        return tid

    def get(self, tid: str) -> TaskItem | None:
        with self._lock:
            return self._items.get(tid)

    def recent(self, n: int = 8) -> list[TaskItem]:
        with self._lock:
            items = sorted(self._items.values(), key=lambda x: x.created, reverse=True)
        return items[:n]

    def status_line(self) -> str:
        recent = self.recent(5)
        if not recent:
            return "No background tasks."
        bits = [f"{t.name}:{t.status}" for t in recent]
        return "Tasks — " + "; ".join(bits)

    def _loop(self) -> None:
        while True:
            tid, fn = self._q.get()
            with self._lock:
                item = self._items.get(tid)
                if item:
                    item.status = "running"
            try:
                result = fn() or "done"
                with self._lock:
                    if item:
                        item.status = "done"
                        item.result = str(result)[:500]
            except Exception as e:
                with self._lock:
                    if item:
                        item.status = "error"
                        item.error = str(e)[:300]
                print(f"[tasks] {tid} error: {e}")
            finally:
                self._q.task_done()

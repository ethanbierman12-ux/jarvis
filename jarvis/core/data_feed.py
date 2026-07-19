"""Persistent live data feed — events Jarvis surfaces in the HUD."""

from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable, Deque, Optional

from jarvis.config import DATA_DIR

FEED_PATH = DATA_DIR / "data_feed.json"


class DataFeed:
    def __init__(self, max_items: int = 80) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self._items: Deque[dict[str, Any]] = deque(maxlen=max_items)
        self._on_push: Optional[Callable[[dict[str, Any]], None]] = None
        self._save_pending = False
        self._load()

    def on_push(self, cb: Callable[[dict[str, Any]], None]) -> None:
        self._on_push = cb

    def push(self, kind: str, text: str, *, meta: dict | None = None) -> dict[str, Any]:
        item = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "epoch": time.time(),
            "kind": (kind or "info").lower()[:24],
            "text": (text or "").strip()[:240],
            "meta": meta or {},
        }
        self._items.appendleft(item)
        self._schedule_save()
        if self._on_push:
            try:
                self._on_push(item)
            except Exception:
                pass
        return item

    def recent(self, n: int = 24) -> list[dict[str, Any]]:
        return list(self._items)[:n]

    def items_for_ui(self, n: int = 28) -> list[dict[str, Any]]:
        return self.recent(n)

    def lines_for_ui(self, n: int = 18) -> list[str]:
        out = []
        for it in self.recent(n):
            stamp = (it.get("ts") or "")[11:16]
            kind = (it.get("kind") or "info").upper()
            out.append(f"{stamp}  {kind}  {it.get('text', '')}")
        return out

    def _load(self) -> None:
        if not FEED_PATH.exists():
            return
        try:
            raw = json.loads(FEED_PATH.read_text(encoding="utf-8"))
            for it in reversed(raw.get("items") or []):
                if isinstance(it, dict) and it.get("text"):
                    self._items.appendleft(it)
        except Exception:
            pass

    def _schedule_save(self) -> None:
        if self._save_pending:
            return
        self._save_pending = True
        # Defer disk write so rapid agent streams stay smooth
        try:
            import threading

            threading.Timer(0.35, self._flush_save).start()
        except Exception:
            self._save()

    def _flush_save(self) -> None:
        self._save_pending = False
        self._save()

    def _save(self) -> None:
        try:
            FEED_PATH.write_text(
                json.dumps({"items": list(self._items)[: self.max_items]}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

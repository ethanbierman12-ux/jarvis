"""Encrypted-ish productivity diary + visual object memory."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

DIARY_PATH = DATA_DIR / "diary.enc.json"
MEMORY_PATH = DATA_DIR / "visual_memory.json"
MEMORY_DIR = DATA_DIR / "memory_snaps"
KEY_PATH = DATA_DIR / ".diary_key"


def _key() -> bytes:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(hashlib.sha256(str(datetime.now()).encode()).digest())
    return KEY_PATH.read_bytes()


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _save_enc(obj: Any) -> None:
    raw = json.dumps(obj, indent=2).encode("utf-8")
    blob = base64.urlsafe_b64encode(_xor(raw, _key())).decode("ascii")
    DIARY_PATH.write_text(json.dumps({"v": 1, "data": blob}), encoding="utf-8")


def _load_enc() -> dict[str, Any]:
    if not DIARY_PATH.exists():
        return {"wins": []}
    try:
        wrap = json.loads(DIARY_PATH.read_text(encoding="utf-8"))
        raw = _xor(base64.urlsafe_b64decode(wrap["data"]), _key())
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"wins": []}


class Diary:
    def log_win(self, text: str, kind: str = "win") -> None:
        data = _load_enc()
        data.setdefault("wins", []).append(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "kind": kind,
                "text": (text or "")[:300],
            }
        )
        data["wins"] = data["wins"][-500:]
        _save_enc(data)

    def week_report(self) -> str:
        data = _load_enc()
        since = datetime.now() - timedelta(days=7)
        wins = []
        for w in data.get("wins") or []:
            try:
                ts = datetime.fromisoformat(w["ts"])
            except Exception:
                continue
            if ts >= since:
                wins.append(w)
        if not wins:
            return "No logged wins this week yet — keep working; I am watching quietly."
        by_day: dict[str, int] = {}
        for w in wins:
            day = w["ts"][:10]
            by_day[day] = by_day.get(day, 0) + 1
        samples = [w["text"] for w in wins[-5:]]
        return (
            f"This week I logged {len(wins)} accomplishments across {len(by_day)} days. "
            f"Recent: " + "; ".join(samples)
        )


class VisualMemory:
    def __init__(self) -> None:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if not MEMORY_PATH.exists():
            MEMORY_PATH.write_text("[]", encoding="utf-8")

    def remember(self, frame, label: str = "", where: str = "desk") -> str:
        try:
            import cv2

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = MEMORY_DIR / f"mem_{stamp}.jpg"
            cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            items = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            items.append(
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "label": (label or "object").strip()[:80],
                    "where": where,
                    "path": str(path),
                }
            )
            MEMORY_PATH.write_text(json.dumps(items[-200:], indent=2), encoding="utf-8")
            return f"Memorized '{label or 'object'}' at {where}."
        except Exception as e:
            return f"Could not memorize: {e}"

    def recall(self, query: str) -> str:
        try:
            items = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return "I have no visual memories yet."
        q = (query or "").lower()
        hits = [
            i
            for i in items
            if q in (i.get("label") or "").lower()
            or any(w in (i.get("label") or "").lower() for w in q.split() if len(w) > 3)
        ]
        if not hits and q:
            # fuzzy: last items mentioning manual/tool/doc
            hits = [
                i
                for i in items
                if any(k in (i.get("label") or "").lower() for k in ("manual", "tool", "doc", "book"))
            ]
        if not hits:
            hits = items[-3:]
        if not hits:
            return "I have not seen that yet. Show me and say 'remember this as …'."
        last = hits[-1]
        when = last.get("ts", "?")
        return (
            f"I last saw '{last.get('label')}' near {last.get('where', 'the desk')} "
            f"on {when}. Snapshot saved."
        )

"""Track published / scaffolded app scores for Jarvis voice + HUD."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

SCORES_PATH = DATA_DIR / "app_scores.json"
_LOCK = threading.Lock()


def _empty() -> dict[str, Any]:
    return {
        "updated_at": 0.0,
        "apps": {},  # app_id -> { title, events, totals, last_at, publish_url }
    }


def _load() -> dict[str, Any]:
    if not SCORES_PATH.exists():
        return _empty()
    try:
        data = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty()
        data.setdefault("apps", {})
        return data
    except Exception:
        return _empty()


def _save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = time.time()
    tmp = SCORES_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(SCORES_PATH)


def ingest(event: dict[str, Any]) -> dict[str, Any]:
    """
    Accept a telemetry payload from a scaffolded / published app.

    Expected keys:
      app_id, title?, kind? (score|visit|search|action|publish),
      points? (int), label?, meta?
    """
    app_id = str(event.get("app_id") or event.get("app") or "unknown").strip()[:64]
    if not app_id or app_id == "unknown":
        return {"ok": False, "error": "missing app_id"}

    kind = str(event.get("kind") or "score").strip().lower()[:32]
    try:
        points = int(event.get("points") or 0)
    except (TypeError, ValueError):
        points = 0
    points = max(-10_000, min(10_000, points))
    title = str(event.get("title") or app_id).strip()[:80]
    label = str(event.get("label") or kind).strip()[:80]
    publish_url = str(event.get("publish_url") or "").strip()[:300]
    now = time.time()

    with _LOCK:
        data = _load()
        apps = data["apps"]
        row = apps.get(app_id) or {
            "title": title,
            "total_points": 0,
            "visits": 0,
            "searches": 0,
            "actions": 0,
            "events": [],
            "last_at": 0.0,
            "publish_url": "",
            "high_score": 0,
        }
        row["title"] = title or row.get("title") or app_id
        if publish_url:
            row["publish_url"] = publish_url

        if kind == "visit":
            row["visits"] = int(row.get("visits") or 0) + 1
        elif kind == "search":
            row["searches"] = int(row.get("searches") or 0) + 1
        elif kind in ("action", "publish"):
            row["actions"] = int(row.get("actions") or 0) + 1

        if points:
            row["total_points"] = int(row.get("total_points") or 0) + points
            row["high_score"] = max(
                int(row.get("high_score") or 0), int(row.get("total_points") or 0)
            )

        evt = {
            "t": now,
            "kind": kind,
            "points": points,
            "label": label,
            "meta": event.get("meta") if isinstance(event.get("meta"), dict) else {},
        }
        events = list(row.get("events") or [])
        events.append(evt)
        row["events"] = events[-80:]
        row["last_at"] = now
        apps[app_id] = row
        _save(data)

    return {
        "ok": True,
        "app_id": app_id,
        "total_points": row["total_points"],
        "high_score": row["high_score"],
    }


def register_publish(app_id: str, *, title: str = "", url: str = "", path: str = "") -> None:
    ingest(
        {
            "app_id": app_id,
            "title": title or app_id,
            "kind": "publish",
            "points": 50,
            "label": "Published",
            "publish_url": url,
            "meta": {"path": path},
        }
    )


def leaderboard(limit: int = 8) -> list[dict[str, Any]]:
    with _LOCK:
        data = _load()
    rows = []
    for app_id, row in (data.get("apps") or {}).items():
        rows.append(
            {
                "app_id": app_id,
                "title": row.get("title") or app_id,
                "total_points": int(row.get("total_points") or 0),
                "high_score": int(row.get("high_score") or 0),
                "visits": int(row.get("visits") or 0),
                "searches": int(row.get("searches") or 0),
                "actions": int(row.get("actions") or 0),
                "publish_url": row.get("publish_url") or "",
                "last_at": float(row.get("last_at") or 0),
            }
        )
    rows.sort(key=lambda r: (-r["total_points"], -r["visits"], r["title"]))
    return rows[: max(1, min(limit, 30))]


def summary(limit: int = 5) -> str:
    board = leaderboard(limit)
    if not board:
        return "No app scores yet. Scaffold a React hub, play it, or say publish app."
    parts = []
    for i, row in enumerate(board, start=1):
        pub = " · live" if row.get("publish_url") else ""
        parts.append(
            f"{i}. {row['title']}: {row['total_points']} pts "
            f"(visits {row['visits']}, searches {row['searches']}){pub}"
        )
    top = board[0]
    return (
        f"Scoreboard — top is {top['title']} with {top['total_points']} points. "
        + " | ".join(parts)
    )


def app_detail(name: str) -> str:
    needle = (name or "").strip().lower()
    with _LOCK:
        data = _load()
    apps = data.get("apps") or {}
    hit = None
    for app_id, row in apps.items():
        if needle in app_id.lower() or needle in str(row.get("title") or "").lower():
            hit = (app_id, row)
            break
    if not hit:
        return f"No scores for “{name}”."
    app_id, row = hit
    url = row.get("publish_url") or "not published"
    return (
        f"{row.get('title') or app_id}: {row.get('total_points', 0)} points, "
        f"high {row.get('high_score', 0)}, visits {row.get('visits', 0)}, "
        f"searches {row.get('searches', 0)}, actions {row.get('actions', 0)}. "
        f"URL: {url}."
    )

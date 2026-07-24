"""IoT / physical presence hooks — ESP32, NFC, magic mirror (software side)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from jarvis.config import DATA_DIR


class IoTBridge:
    """
    Soft hooks until hardware arrives:
      - room_enter / room_leave events (ESP32 / mmWave → HTTP macro)
      - nfc_tap (desk pad)
      - mirror_state for MagicMirror modules
    Persist last known room + NFC log for proactive routing.
    """

    def __init__(self, *, on_event: Callable[[str, dict], None] | None = None) -> None:
        self.on_event = on_event
        self.path = DATA_DIR / "iot_state.json"
        self.state = {
            "room": "desk",
            "last_nfc": "",
            "mirror": {"cpu": 0, "listening": False},
            "updated": "",
        }
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.state.update(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            pass

    def _save(self) -> None:
        self.state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except Exception:
            pass

    def status(self) -> str:
        return (
            f"IoT: room={self.state.get('room')}, "
            f"last NFC={self.state.get('last_nfc') or 'none'}, "
            f"mirror listening={self.state.get('mirror', {}).get('listening')}"
        )

    def handle(self, cmd: str) -> str:
        c = (cmd or "").strip().lower()
        if c.startswith("room "):
            room = c[5:].strip() or "desk"
            return self.set_room(room)
        if c.startswith("nfc "):
            tag = c[4:].strip()
            return self.nfc_tap(tag)
        if c in ("iot status", "room status", "presence status"):
            return self.status()
        if c.startswith("mirror "):
            return self.mirror_update(c[7:].strip())
        return (
            "IoT commands: room <name>, nfc <tag>, mirror <json|listening on/off>, "
            "iot status. Point ESP32/NFC webhooks at /macro?cmd=room+kitchen etc."
        )

    def set_room(self, room: str) -> str:
        room = (room or "desk").strip().lower()[:32]
        prev = self.state.get("room")
        self.state["room"] = room
        self._save()
        if self.on_event:
            self.on_event("room", {"room": room, "previous": prev})
        return f"Active room set to {room}."

    def nfc_tap(self, tag: str) -> str:
        tag = (tag or "").strip().lower()[:64]
        self.state["last_nfc"] = tag
        self._save()
        if tag in ("coffee", "mug", "caffeine"):
            msg = "Logged caffeine / coffee mug tap."
        elif tag in ("water", "bottle"):
            msg = "Logged water intake."
        elif tag in ("focus", "deep"):
            msg = "Focus mode tag — say focus mode if you want full lockdown."
        else:
            msg = f"NFC tap recorded: {tag or 'unknown'}."
        if self.on_event:
            self.on_event("nfc", {"tag": tag, "message": msg})
        return msg

    def mirror_update(self, payload: str) -> str:
        p = (payload or "").strip()
        mirror = dict(self.state.get("mirror") or {})
        if p.startswith("{"):
            try:
                mirror.update(json.loads(p))
            except Exception as e:
                return f"Bad mirror JSON: {e}"
        elif p in ("listening on", "listen on"):
            mirror["listening"] = True
        elif p in ("listening off", "listen off"):
            mirror["listening"] = False
        else:
            return "Mirror: send JSON or 'listening on/off'."
        self.state["mirror"] = mirror
        self._save()
        # Publish snapshot for MagicMirror module to poll
        snap = DATA_DIR / "mirror_feed.json"
        try:
            snap.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except Exception:
            pass
        return "Magic mirror state updated."

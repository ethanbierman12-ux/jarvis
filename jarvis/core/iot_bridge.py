"""IoT / physical presence hooks — ESP32, NFC, magic mirror + serial LED sync."""

from __future__ import annotations

import json
import threading
import time
from typing import Callable

from jarvis.config import DATA_DIR

# HUD / reactor states → physical LED command lines (ESP32 firmware parses these)
AMBIENT_SERIAL = {
    "idle": b"COLOR_CYAN\n",
    "listen": b"COLOR_CYAN\n",
    "speak": b"COLOR_CYAN\n",
    "thinking": b"COLOR_PURPLE\n",
    "fetch": b"COLOR_PURPLE\n",
    "compiling": b"COLOR_GREEN\n",
    "build": b"COLOR_GREEN\n",
    "vibe": b"COLOR_GREEN\n",
    "site": b"COLOR_GREEN\n",
    "code": b"COLOR_GREEN\n",
    "error": b"COLOR_RED\n",
    "panic": b"COLOR_RED\n",
}

AMBIENT_RGB = {
    "idle": (0, 229, 255),
    "listen": (0, 229, 255),
    "speak": (0, 240, 255),
    "thinking": (155, 89, 255),
    "fetch": (155, 89, 255),
    "compiling": (57, 255, 20),
    "build": (57, 255, 20),
    "vibe": (57, 255, 20),
    "site": (57, 255, 20),
    "code": (57, 255, 20),
    "error": (255, 59, 48),
    "panic": (255, 59, 48),
}


class IoTBridge:
    """
    Soft hooks until hardware arrives:
      - room_enter / room_leave events (ESP32 / mmWave → HTTP macro)
      - nfc_tap (desk pad)
      - mirror_state for MagicMirror modules
      - optional USB serial → desk LED strip (COLOR_CYAN / PURPLE / GREEN / RED)
    Persist last known room + NFC log for proactive routing.
    """

    def __init__(
        self,
        *,
        on_event: Callable[[str, dict], None] | None = None,
        serial_port: str = "",
        serial_baud: int = 115200,
    ) -> None:
        self.on_event = on_event
        self.path = DATA_DIR / "iot_state.json"
        self.state = {
            "room": "desk",
            "last_nfc": "",
            "mirror": {"cpu": 0, "listening": False},
            "ambient": "idle",
            "serial": "offline",
            "updated": "",
        }
        self._serial_port = (serial_port or "").strip()
        self._serial_baud = int(serial_baud or 115200)
        self._serial = None
        self._serial_lock = threading.Lock()
        self._last_ambient = ""
        self._load()
        self._open_serial()

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

    def _open_serial(self) -> None:
        if not self._serial_port:
            self.state["serial"] = "disabled"
            return
        try:
            import serial  # pyserial

            self._serial = serial.Serial(
                self._serial_port, self._serial_baud, timeout=0.4
            )
            time.sleep(1.2)  # MCU reset settle
            self.state["serial"] = f"online:{self._serial_port}"
            print(f"[iot] serial stabilized on {self._serial_port}")
        except Exception as e:
            self._serial = None
            self.state["serial"] = f"offline:{e}"
            print(f"[iot] serial offline ({self._serial_port}): {e}")

    def sync_ambient(self, system_state: str) -> None:
        """Map HUD/reactor state → ESP32 LED strip (no-op if serial offline)."""
        key = (system_state or "idle").lower().strip()
        if key in ("thinking", "process", "processing"):
            key = "thinking"
        elif key in ("compiling", "compile", "coding"):
            key = "compiling"
        if key == self._last_ambient:
            return
        self._last_ambient = key
        self.state["ambient"] = key
        cmd = AMBIENT_SERIAL.get(key, AMBIENT_SERIAL["idle"])
        with self._serial_lock:
            if self._serial is None:
                return
            try:
                self._serial.write(cmd)
            except Exception as e:
                print(f"[iot] serial write failed: {e}")
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
                self.state["serial"] = "offline"
                self._open_serial()

    def close(self) -> None:
        with self._serial_lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None

    def status(self) -> str:
        return (
            f"IoT: room={self.state.get('room')}, "
            f"last NFC={self.state.get('last_nfc') or 'none'}, "
            f"mirror listening={self.state.get('mirror', {}).get('listening')}, "
            f"serial={self.state.get('serial')}, ambient={self.state.get('ambient')}"
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
        if c.startswith("ambient ") or c.startswith("desk light "):
            state = c.split(" ", 1)[-1].strip()
            self.sync_ambient(state)
            return f"Desk ambient → {state} (serial {self.state.get('serial')})."
        return (
            "IoT commands: room <name>, nfc <tag>, mirror <json|listening on/off>, "
            "ambient <idle|thinking|compiling|error>, iot status. "
            "Set iot_serial_port (e.g. COM3) for ESP32 LED strips. "
            "Point ESP32/NFC webhooks at /macro?cmd=room+kitchen etc."
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
        snap = DATA_DIR / "mirror_feed.json"
        try:
            snap.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except Exception:
            pass
        return "Magic mirror state updated."

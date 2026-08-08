"""Home-only desk security helpers.

Legitimate personal / household desk protection only:
encrypted local event log, intrusion snapshot archive, phone photo push,
and software false-color thermal *assist* on the owner's own webcam feeds.

This module does NOT implement city-wide surveillance, public CCTV, ALPR,
predictive policing, or public suspect databases.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class HomeSecurity:
    """Desk / home security pack — local log, intrusion snaps, thermal assist."""

    def __init__(
        self,
        data_dir: Path,
        *,
        passphrase: str = "",
        log_enabled: bool = True,
        phone_photo: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.sec_dir = self.data_dir / "security"
        self.intrusions_dir = self.data_dir / "intrusions"
        self.log_path = self.sec_dir / "events.jlog"
        self.passphrase = (passphrase or "jarvis-home-security").strip()
        self.log_enabled = bool(log_enabled)
        self.phone_photo = bool(phone_photo)
        self.thermal_assist = False
        try:
            self.sec_dir.mkdir(parents=True, exist_ok=True)
            self.intrusions_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _key_bytes(self) -> bytes:
        return hashlib.sha256(self.passphrase.encode("utf-8")).digest()

    def _wrap(self, data: bytes) -> bytes:
        """Fernet when cryptography is available; XOR fallback otherwise."""
        try:
            from cryptography.fernet import Fernet

            key = base64.urlsafe_b64encode(self._key_bytes())
            return Fernet(key).encrypt(data)
        except Exception:
            k = self._key_bytes()
            xor = bytes(b ^ k[i % len(k)] for i, b in enumerate(data))
            return b"X|" + base64.urlsafe_b64encode(xor)

    def _unwrap(self, token: bytes) -> bytes | None:
        try:
            if token.startswith(b"X|"):
                k = self._key_bytes()
                raw = base64.urlsafe_b64decode(token[2:])
                return bytes(b ^ k[i % len(k)] for i, b in enumerate(raw))
            from cryptography.fernet import Fernet

            key = base64.urlsafe_b64encode(self._key_bytes())
            return Fernet(key).decrypt(token)
        except Exception:
            return None

    def log_event(
        self,
        kind: str,
        message: str,
        snapshot_path: str = "",
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Encrypt and append one event line to events.jlog."""
        if not self.log_enabled:
            return False
        try:
            self.sec_dir.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": time.time(),
                "iso": datetime.now().isoformat(timespec="seconds"),
                "kind": (kind or "").strip() or "event",
                "message": (message or "")[:500],
                "snapshot": str(snapshot_path or "")[:400],
                "meta": meta or {},
            }
            blob = json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            line = self._wrap(blob).decode("ascii", errors="replace")
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            return True
        except Exception as e:
            print(f"[home_security] log_event: {e}")
            return False

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        out: list[dict[str, Any]] = []
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                raw = self._unwrap(line.encode("ascii", errors="ignore"))
                if not raw:
                    continue
                obj = json.loads(raw.decode("utf-8"))
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
        return out

    def recent(self, n: int = 10) -> list[dict[str, Any]]:
        """Decrypt and return the last N events (newest last)."""
        n = max(1, min(int(n or 10), 50))
        rows = self._read_events()
        return rows[-n:]

    def speak_recent(self, n: int = 5) -> str:
        rows = self.recent(n)
        if not rows:
            return "No security events logged yet."
        bits: list[str] = []
        for r in rows:
            kind = r.get("kind", "event")
            msg = (r.get("message") or "")[:80]
            iso = (r.get("iso") or "")[-8:]  # HH:MM:SS-ish tail
            bits.append(f"{kind}{(' at ' + iso) if iso else ''}: {msg}".strip(": "))
        return f"Last {len(bits)} security events. " + " · ".join(bits)

    def archive_intrusion(self, src_path: str | Path | None = None) -> Path | None:
        """Copy/timestamp a JPEG into DATA_DIR/intrusions/."""
        try:
            self.intrusions_dir.mkdir(parents=True, exist_ok=True)
            src: Path | None = Path(src_path) if src_path else None
            if src is None or not src.is_file():
                fallback = self.data_dir / "last_vision.jpg"
                src = fallback if fallback.is_file() else None
            if src is None or not src.is_file():
                return None
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = self.intrusions_dir / f"intruder_{stamp}.jpg"
            if src.resolve() == dest.resolve():
                return dest
            shutil.copy2(str(src), str(dest))
            return dest
        except Exception as e:
            print(f"[home_security] archive_intrusion: {e}")
            return None

    def notify_intrusion(
        self,
        phone_bridge: Any,
        message: str,
        image_path: str | Path | None = None,
    ) -> str:
        """Push photo via phone_bridge.notify_image; fall back to ping."""
        msg = (message or "Intruder alert at your desk").strip()
        if phone_bridge is None:
            return "Phone bridge offline."
        path = Path(image_path) if image_path else None
        if self.phone_photo and path is not None and path.is_file():
            try:
                result = phone_bridge.notify_image(
                    msg,
                    str(path),
                    title="JARVIS INTRUDER",
                    filename=path.name,
                )
                if result and "could not" not in result.lower() and "missing" not in result.lower():
                    return result
            except Exception as e:
                print(f"[home_security] notify_image: {e}")
        try:
            return phone_bridge.ping(msg)
        except Exception as e:
            return f"Phone notify failed: {e}"

    def event_count(self) -> int:
        try:
            if not self.log_path.exists():
                return 0
            return sum(1 for line in self.log_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())
        except Exception:
            return 0

    def status(
        self,
        *,
        armed: bool | None = None,
        enrolled: bool | None = None,
        night_vision: bool = False,
        thermal: bool | None = None,
    ) -> str:
        """Short spoken summary for security status."""
        bits: list[str] = ["Home security pack online"]
        if armed is not None:
            bits.append("armed" if armed else "disarmed")
        if enrolled is not None:
            bits.append("face enrolled" if enrolled else "face not enrolled")
        bits.append(f"{self.event_count()} log events")
        rows = self.recent(1)
        if rows:
            last = rows[-1]
            bits.append(
                f"last {last.get('kind', 'event')}: {(last.get('message') or '')[:60]}"
            )
        else:
            bits.append("no events yet")
        nv = "on" if night_vision else "off"
        th = self.thermal_assist if thermal is None else bool(thermal)
        bits.append(f"night vision {nv}")
        bits.append(
            f"thermal assist {'on' if th else 'off'} (software false-color, not FLIR)"
        )
        return " · ".join(bits)

    def apply_thermal_assist(self, frame_bgr):
        """False-color heatmap from luminance — own cams only; labeled assist, not FLIR."""
        try:
            from jarvis.ui.widgets.night_vision import apply_thermal_assist

            return apply_thermal_assist(frame_bgr)
        except Exception:
            return frame_bgr

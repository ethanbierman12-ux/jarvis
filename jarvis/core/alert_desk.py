"""Alert Desk — HUD blast + phone high-priority ping for the owner's desk.

Lightweight encrypted outbound notes are stored locally and mirrored via
PhoneBridge. Not a tactical radio protocol. Guest mode suppresses
intruder-style blasts (same pattern as home_security intruder path).
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


class AlertDesk:
    """Desk alert hub: blast → HUD + phone; secure/intruder canned blasts."""

    def __init__(
        self,
        *,
        data_dir: Path,
        phone: Any = None,
        home_security: Any = None,
        on_hud: Callable[[str], None] | None = None,
        guest_check: Callable[[], bool] | None = None,
        enabled: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.phone = phone
        self.home_security = home_security
        self.on_hud = on_hud or (lambda _t: None)
        self.guest_check = guest_check or (lambda: False)
        self.enabled = bool(enabled)
        self.sealed_dir = self.data_dir / "security" / "sealed"
        try:
            self.sealed_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def status(self) -> str:
        if not self.enabled:
            return "Alert desk disabled."
        phone_ok = bool(self.phone and getattr(self.phone, "enabled", True))
        guest = bool(self.guest_check())
        return (
            f"Alert desk online · phone {'ready' if phone_ok else 'offline'}"
            f"{' · guest mode' if guest else ''}."
        )

    def _hud(self, text: str) -> None:
        try:
            self.on_hud((text or "")[:120])
        except Exception:
            pass

    def blast(self, message: str, *, title: str = "JARVIS ALERT") -> str:
        """HUD alert + high-priority phone ping."""
        if not self.enabled:
            return "Alert desk is disabled."
        msg = (message or "").strip() or "Desk alert"
        self._hud(msg[:80].upper())
        if self.phone is None:
            return f"HUD alerted. Phone bridge offline. ({msg[:80]})"
        try:
            result = self.phone.ping(msg, title=title)
            return result
        except Exception as e:
            return f"HUD alerted; phone failed ({e})."

    def dispatch_driver(self, message: str) -> str:
        """Owner-only driver ping via phone bridge (not company radio)."""
        if not self.enabled:
            return "Alert desk is disabled."
        body = (message or "").strip()
        if not body:
            return "What should I tell the driver?"
        full = f"DRIVER DISPATCH: {body}"
        self._hud("DRIVER DISPATCH")
        phone = self.phone
        if phone is None or not getattr(phone, "enabled", True):
            return f"HUD noted. Phone bridge offline. ({full[:100]})"
        if not (getattr(phone, "topic", "") or getattr(phone, "shortcuts_webhook", "")):
            return (
                "Phone not linked — say link my phone so your drivers can get "
                f"ntfy pings. HUD only: {full[:80]}"
            )
        try:
            hs = self.home_security
            if hs is not None and hasattr(hs, "log_event"):
                hs.log_event("driver_dispatch", full[:500])
        except Exception:
            pass
        try:
            return phone.ping(full, title="DRIVER DISPATCH")
        except Exception as e:
            return f"HUD noted driver message; phone failed ({e})."

    def secure_blast(self, message: str = "") -> str:
        """Canned security blast; optional last_vision / intrusion photo."""
        if not self.enabled:
            return "Alert desk is disabled."
        if self.guest_check():
            self._hud("GUEST MODE · BLAST SUPPRESSED")
            return "Guest mode — secure blast suppressed."
        body = (message or "").strip() or "Secure blast — desk lockdown. Check cameras."
        self._hud("SECURE BLAST")
        img = self._latest_security_image()
        hs = self.home_security
        if hs is not None:
            try:
                hs.log_event("secure_blast", body, snapshot_path=str(img or ""))
            except Exception:
                pass
        if self.phone is not None and img is not None:
            try:
                if hs is not None and hasattr(hs, "notify_intrusion"):
                    return hs.notify_intrusion(self.phone, body, image_path=img)
                return self.phone.notify_image(
                    body, str(img), title="JARVIS SECURE", filename=img.name
                )
            except Exception as e:
                print(f"[alert_desk] secure photo: {e}")
        return self.blast(body, title="JARVIS SECURE")

    def intruder_blast(self, message: str = "") -> str:
        """Canned intruder blast with optional snapshot — guest mode suppresses."""
        if not self.enabled:
            return "Alert desk is disabled."
        if self.guest_check():
            self._hud("GUEST MODE · BLAST SUPPRESSED")
            return "Guest mode — intruder blast suppressed."
        body = (message or "").strip() or "Intruder blast at your desk — review snapshot."
        self._hud("INTRUDER BLAST")
        img = self._latest_security_image()
        hs = self.home_security
        archived = None
        if hs is not None:
            try:
                archived = hs.archive_intrusion(img)
                hs.log_event(
                    "intruder_blast",
                    body,
                    snapshot_path=str(archived or img or ""),
                )
            except Exception as e:
                print(f"[alert_desk] archive: {e}")
        path = archived or img
        if self.phone is not None and path is not None:
            try:
                if hs is not None and hasattr(hs, "notify_intrusion"):
                    return hs.notify_intrusion(self.phone, body, image_path=path)
                return self.phone.notify_image(
                    body, str(path), title="JARVIS INTRUDER", filename=Path(path).name
                )
            except Exception as e:
                print(f"[alert_desk] intruder photo: {e}")
        return self.blast(body, title="JARVIS INTRUDER")

    def encrypt_alert(self, message: str) -> str:
        """Seal a note locally (encrypted log) + phone ping. Not a radio link."""
        if not self.enabled:
            return "Alert desk is disabled."
        msg = (message or "").strip()
        if not msg:
            return "What should I encrypt and send?"
        sealed_ok = False
        hs = self.home_security
        if hs is not None:
            try:
                sealed_ok = bool(
                    hs.log_event(
                        "encrypted_alert",
                        msg,
                        meta={"sealed": True, "ts": time.time()},
                    )
                )
            except Exception as e:
                print(f"[alert_desk] encrypt log: {e}")
        # Also drop a sealed sidecar file (wrapped via home_security when available)
        try:
            self.sealed_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.sealed_dir / f"note_{stamp}.sealed"
            raw = msg.encode("utf-8")
            if hs is not None and hasattr(hs, "_wrap"):
                token = hs._wrap(raw)
                path.write_bytes(token)
            else:
                path.write_bytes(raw)
            sealed_ok = True
        except Exception as e:
            print(f"[alert_desk] sealed file: {e}")
        ping = self.blast(f"Encrypted desk note: {msg[:120]}", title="JARVIS SEALED")
        prefix = "Sealed locally. " if sealed_ok else "Seal storage soft-failed. "
        return prefix + ping

    def _latest_security_image(self) -> Path | None:
        try:
            folder = self.data_dir / "intrusions"
            if folder.is_dir():
                pics = sorted(
                    [
                        p
                        for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png")
                    ],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if pics:
                    return pics[0]
            vision = self.data_dir / "last_vision.jpg"
            if vision.is_file():
                return vision
        except Exception:
            pass
        return None

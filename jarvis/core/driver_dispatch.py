"""Owner desk driver ping — ntfy / phone bridge only.

Sends "DRIVER DISPATCH: …" to phones on the owner's ntfy topic
(their drivers who subscribe). Does NOT touch trucking company radios,
ELDs, or third-party fleet systems.
"""

from __future__ import annotations

from typing import Any, Callable


class DriverDispatch:
    """Thin desk tool: HUD + phone blast for the owner's own drivers."""

    def __init__(
        self,
        *,
        phone: Any = None,
        alert_desk: Any = None,
        on_hud: Callable[[str], None] | None = None,
        enabled: bool = True,
    ) -> None:
        self.phone = phone
        self.alert_desk = alert_desk
        self.on_hud = on_hud or (lambda _t: None)
        self.enabled = bool(enabled)

    def status(self) -> str:
        if not self.enabled:
            return "Driver dispatch disabled."
        phone = self.phone
        linked = bool(
            phone
            and getattr(phone, "enabled", True)
            and (
                getattr(phone, "topic", "")
                or getattr(phone, "shortcuts_webhook", "")
            )
        )
        return (
            "Driver dispatch ready (owner phone bridge)."
            if linked
            else "Driver dispatch: phone not linked — say link my phone."
        )

    def dispatch(self, message: str) -> str:
        """Alias used by brain."""
        return self.dispatch_driver(message)

    def dispatch_driver(self, message: str) -> str:
        """Ping owner's drivers via AlertDesk / PhoneBridge. Soft-fail if unlinked."""
        if not self.enabled:
            return "Driver dispatch is disabled."
        body = (message or "").strip()
        if not body:
            return "What should I tell the driver?"
        for prefix in (
            "that ",
            "to ",
            "the driver ",
            "driver ",
            "them ",
            "him ",
            "her ",
        ):
            if body.lower().startswith(prefix):
                body = body[len(prefix) :].strip()
                break
        if not body:
            return "What should I tell the driver?"
        full = f"DRIVER DISPATCH: {body}"
        try:
            self.on_hud("DRIVER DISPATCH")
        except Exception:
            pass

        desk = self.alert_desk
        if desk is not None and getattr(desk, "enabled", True):
            try:
                if hasattr(desk, "dispatch_driver"):
                    return desk.dispatch_driver(body)
                return desk.blast(full, title="DRIVER DISPATCH")
            except Exception as e:
                print(f"[driver_dispatch] alert_desk: {e}")

        phone = self.phone
        if phone is None or not getattr(phone, "enabled", True):
            return (
                f"HUD noted driver message, but phone bridge is offline. "
                f"({full[:100]})"
            )
        topic = getattr(phone, "topic", "") or ""
        webhook = getattr(phone, "shortcuts_webhook", "") or ""
        if not topic and not webhook:
            return (
                "Phone not linked — install ntfy, set phone_ntfy_topic, "
                "or say link my phone. HUD only for now: "
                f"{full[:80]}"
            )
        try:
            return phone.ping(full, title="DRIVER DISPATCH")
        except Exception as e:
            return f"Driver dispatch soft-failed: {e}"

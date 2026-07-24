"""Feature registry — tracks live features and freezes mutations during upgrade."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FeatureInfo:
    name: str
    version: str = "1.0"
    status: str = "live"  # live | frozen | error
    note: str = ""
    updated_at: float = field(default_factory=time.time)


class FeatureRegistry:
    """
    Additive registry of feature modules.
    While frozen (upgrade), mutating handlers should refuse non-whitelisted work.
    """

    # Allowed while freeze is active (so upgrade/status still work)
    FREEZE_ALLOW = frozenset(
        {
            "upgrade",
            "system upgrade",
            "upgrade status",
            "feature status",
            "registry status",
            "help",
            "status",
            "full status",
            "commands",
            "what can you do",
            "cancel upgrade",
            "travis status",
            "quiet mode",
            "loud mode",
            "computer use status",
            "stop computer use",
            "cancel computer use",
            "upgrade check",
            "self health",
            "health check",
            "recent errors",
            "setup computer use",
        }
    )

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._features: dict[str, FeatureInfo] = {}
        self._frozen = False
        self._frozen_at = 0.0
        self._freeze_reason = ""
        # Seed built-in feature set (additive documentation of live systems)
        for name, ver, note in (
            ("travis_modes", "1.1", "Park / Tactical / Peer Review"),
            ("map_3d_zoom", "1.3", "Open-then-fly cinematic city/country zoom"),
            ("hot_upgrade", "1.4", "Loading UI + plugin/core refresh"),
            ("phone_bridge", "1.0", "ntfy iPhone push"),
            ("companion_pwa", "1.0", "iPhone Tailscale PWA chat"),
            ("manus_bridge", "1.1", "Manus AI agent tasks + code assist"),
            ("cloud_integrations", "1.0", "Stripe / Notion / Buffer / Gmail voice"),
            ("macro_gateway", "1.0", "Silent HTTP pad"),
            ("hub_spokes", "1.1", "Sarah / Tom / Admin + explicit asks"),
            ("workflows", "1.0", "Morning / night / focus macros"),
            ("command_monitor", "1.1", "Telemetry HUD (hidden by default)"),
            ("security_gate", "1.2", "Face greet + debounced intruder"),
            ("hud_cinematic", "1.0", "Refined cyan HUD chrome"),
            ("smart_desk", "1.0", "Quiet mode / desk ready / full status"),
            ("desk_health", "1.0", "upgrade check / self-health summary"),
            (
                "computer_use",
                "1.2",
                "Browser/desktop agent (Ollama free/local · Anthropic · OpenAI · browser-use) · missing_guidance",
            ),
        ):
            self.register(name, version=ver, note=note)

    @property
    def frozen(self) -> bool:
        with self._lock:
            return self._frozen

    def register(
        self, name: str, *, version: str = "1.0", note: str = "", status: str = "live"
    ) -> None:
        with self._lock:
            self._features[name] = FeatureInfo(
                name=name, version=version, status=status, note=note
            )

    def freeze(self, reason: str = "upgrade") -> None:
        with self._lock:
            self._frozen = True
            self._frozen_at = time.time()
            self._freeze_reason = reason or "upgrade"
            for feat in self._features.values():
                if feat.status == "live":
                    feat.status = "frozen"
                    feat.updated_at = time.time()

    def unfreeze(self) -> None:
        with self._lock:
            self._frozen = False
            self._freeze_reason = ""
            for feat in self._features.values():
                if feat.status == "frozen":
                    feat.status = "live"
                    feat.updated_at = time.time()

    def allows(self, utterance: str) -> bool:
        """Return False if freeze blocks this utterance."""
        with self._lock:
            if not self._frozen:
                return True
        low = (utterance or "").strip().lower()
        if not low:
            return True
        if low in self.FREEZE_ALLOW:
            return True
        for allowed in self.FREEZE_ALLOW:
            if low == allowed or low.startswith(allowed + " "):
                return True
        # Always allow cancel / status / upgrade verbs
        if any(
            k in low
            for k in ("upgrade", "feature status", "registry", "cancel freeze", "help")
        ):
            return True
        return False

    def block_message(self) -> str:
        with self._lock:
            reason = self._freeze_reason or "upgrade"
            age = int(time.time() - self._frozen_at) if self._frozen_at else 0
        return (
            f"Feature registry is frozen for {reason} ({age}s). "
            "Only upgrade and status commands run until 100 percent."
        )

    def status(self) -> str:
        with self._lock:
            freeze = "FROZEN" if self._frozen else "OPEN"
            lines = [f"Registry {freeze} · {len(self._features)} features"]
            for name, info in sorted(self._features.items()):
                lines.append(f"{name} v{info.version} [{info.status}] {info.note}".strip())
        return " · ".join(lines[:6]) + (
            f" · +{len(lines) - 6} more" if len(lines) > 6 else ""
        )

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": f.name,
                    "version": f.version,
                    "status": f.status,
                    "note": f.note,
                }
                for f in self._features.values()
            ]

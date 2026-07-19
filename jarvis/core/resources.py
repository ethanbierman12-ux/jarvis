"""Asset lazy-loading — only pull high-res resources when a UI state needs them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.config import ASSETS_DIR


class ResourceManager:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._loaded_states: set[str] = set()

    def for_state(self, state: str) -> None:
        """Mark a UI state active and load its assets."""
        if state in self._loaded_states:
            return
        self._loaded_states.add(state)
        # Placeholders for future SVG / Lottie / textures keyed by state
        mapping = {
            "boot": ["boot.wav"],
            "hud": [],
            "bedtime": [],
            "camera": [],
        }
        for name in mapping.get(state, []):
            self.load(name)

    def load(self, name: str) -> Path | None:
        if name in self._cache:
            return self._cache[name]
        path = ASSETS_DIR / name
        if path.exists():
            self._cache[name] = path
            return path
        return None

    def unload(self, state: str) -> None:
        self._loaded_states.discard(state)

    def release_unused(self, keep: set[str] | None = None) -> None:
        keep = keep or self._loaded_states
        # Simple policy: drop cache entries not needed by active states
        if "boot" not in keep:
            self._cache.pop("boot.wav", None)

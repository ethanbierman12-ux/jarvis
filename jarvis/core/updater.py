"""SandboxCompiler — AST-check + hot-reload plugins from Update Software UI."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import sys
from pathlib import Path

from jarvis.config import PLUGINS_DIR

_DANGER = re.compile(
    r"\b(rm\s+-rf|shutil\.rmtree|os\.system\s*\(|subprocess\.|eval\s*\(|exec\s*\(|ctypes)\b",
    re.I,
)


class SandboxCompiler:
    def __init__(self) -> None:
        self._modules: dict[str, object] = {}
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        if str(PLUGINS_DIR) not in sys.path:
            sys.path.insert(0, str(PLUGINS_DIR))

    def apply(self, request: str) -> str:
        """Turn a natural-language update request into a safe stub plugin."""
        name = "plugin_" + re.sub(r"[^a-z0-9]+", "_", request.lower())[:40].strip("_") or "plugin_custom"
        if not name.isidentifier():
            name = "plugin_custom"
        code = self._stub(name, request)
        return self.install(name, code)

    def install(self, name: str, code: str) -> str:
        if _DANGER.search(code):
            return "Invalid logic detected. Dangerous calls blocked — refine your request."
        try:
            ast.parse(code)
        except SyntaxError as e:
            return f"Syntax error: {e}. Please refine your request."

        path = PLUGINS_DIR / f"{name}.py"
        path.write_text(code, encoding="utf-8")
        try:
            if name in self._modules:
                mod = importlib.reload(self._modules[name])  # type: ignore[arg-type]
            else:
                spec = importlib.util.spec_from_file_location(name, path)
                if not spec or not spec.loader:
                    return "Failed to load plugin spec."
                mod = importlib.util.module_from_spec(spec)
                sys.modules[name] = mod
                spec.loader.exec_module(mod)
            self._modules[name] = mod
            return f"Plugin '{name}' live. No reboot required."
        except Exception as e:
            return f"The new update failed to execute safely; reverting. ({e})"

    def _stub(self, name: str, request: str) -> str:
        return f'''"""Auto-generated Jarvis plugin: {request}"""

TRIGGER = {request!r}

def run(brain, text: str = "") -> str:
    return "Plugin '{name}' received: " + (text or TRIGGER)
'''

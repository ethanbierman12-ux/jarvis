"""Autobug — paste or speak an error log; get a structured fix plan."""

from __future__ import annotations

import re
from pathlib import Path


class AutoBug:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir) / "autobug"
        self.dir.mkdir(parents=True, exist_ok=True)

    def analyze(self, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return "Paste or dictate an error log first."
        # Strip command prefixes
        raw = re.sub(
            r"^(fix (this |the )?(bug|error)|autobug|debug this)\s*[:\-]?\s*",
            "",
            raw,
            flags=re.I,
        ).strip()
        path = self.dir / "last_error.txt"
        path.write_text(raw, encoding="utf-8")

        kind = "unknown"
        hint = "Read the stack from the bottom frame upward."
        low = raw.lower()
        if "modulenotfounderror" in low or "no module named" in low:
            kind = "missing dependency"
            m = re.search(r"no module named ['\"]?([a-z0-9_]+)", low)
            pkg = m.group(1) if m else "package"
            hint = f"Install with: pip install {pkg} — then restart Jarvis."
        elif "syntaxerror" in low:
            kind = "syntax"
            hint = "Check the reported line for missing colons, parentheses, or quotes."
        elif "typeerror" in low:
            kind = "type"
            hint = "A value has the wrong type — null-check arguments near the top frame."
        elif "attributeerror" in low:
            kind = "attribute"
            hint = "Object is None or the API changed — verify imports and versions."
        elif "permissionerror" in low or "access is denied" in low:
            kind = "permissions"
            hint = "Run as your user, close the locking app, or check file paths."
        elif "timeout" in low or "timed out" in low:
            kind = "timeout"
            hint = "Network or device hung — retry with a longer timeout or check VPN."
        elif "traceback" in low:
            kind = "python traceback"

        # Extract file:line if present
        loc = ""
        m2 = re.search(r'File "([^"]+)", line (\d+)', raw)
        if m2:
            loc = f" at {Path(m2.group(1)).name}:{m2.group(2)}"

        return (
            f"Autobug classified this as {kind}{loc}. {hint} "
            f"Error saved to {path.name}. Say open last error to view it."
        )

    def last_path(self) -> Path:
        return self.dir / "last_error.txt"

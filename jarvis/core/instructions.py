"""Custom behavior instructions appended into Jarvis replies / routing context."""

from __future__ import annotations

from pathlib import Path

from jarvis.config import DATA_DIR

INSTR_PATH = DATA_DIR / "custom_instructions.md"


class CustomInstructions:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not INSTR_PATH.exists():
            INSTR_PATH.write_text(
                "# Jarvis custom behaviors\n\n"
                "Add lines below via Update Software or voice “add instruction …”.\n",
                encoding="utf-8",
            )

    def read(self) -> str:
        try:
            return INSTR_PATH.read_text(encoding="utf-8")
        except Exception:
            return ""

    def append(self, text: str) -> str:
        line = (text or "").strip()
        if not line:
            return "No instruction provided."
        # Strip command verbs if spoken
        for prefix in (
            "add instruction ",
            "add behavior ",
            "remember to ",
            "always ",
            "from now on ",
        ):
            if line.lower().startswith(prefix):
                line = line[len(prefix) :].strip()
        try:
            with INSTR_PATH.open("a", encoding="utf-8") as f:
                f.write(f"- {line}\n")
            return f"Instruction saved: {line}"
        except Exception as e:
            return f"Could not save instruction: {e}"

    def clear(self) -> str:
        try:
            INSTR_PATH.write_text(
                "# Jarvis custom behaviors\n\n", encoding="utf-8"
            )
            return "Custom instructions cleared."
        except Exception as e:
            return f"Clear failed: {e}"

    def context_snippet(self, limit: int = 600) -> str:
        raw = self.read()
        lines = [
            ln.strip("- ").strip()
            for ln in raw.splitlines()
            if ln.strip().startswith("-")
        ]
        if not lines:
            return ""
        blob = " | ".join(lines[-8:])
        return blob[:limit]

"""RLHF-lite — approve/reject macros log actions; weekly digester updates instructions."""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR
from jarvis.core.instructions import CustomInstructions

RLHF_PATH = DATA_DIR / "rlhf_feedback.jsonl"
RLHF_STATE = DATA_DIR / "rlhf_state.json"


@dataclass
class FeedbackEvent:
    ts: float
    verdict: str  # approve | reject
    prompt: str
    action: str
    reply: str = ""
    note: str = ""


class RLHFEngine:
    """Maps Ctrl+Shift+Up/Down (and voice) onto a lasting preference trail."""

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.last_prompt = ""
        self.last_action = ""
        self.last_reply = ""

    def observe(self, prompt: str, action: str = "", reply: str = "") -> None:
        self.last_prompt = (prompt or "")[:400]
        self.last_action = (action or prompt or "")[:200]
        self.last_reply = (reply or "")[:400]

    def approve(self, note: str = "") -> str:
        return self._log("approve", note)

    def reject(self, note: str = "") -> str:
        return self._log("reject", note)

    def _log(self, verdict: str, note: str) -> str:
        if not self.last_prompt and not self.last_action:
            return "Nothing to rate yet — give Jarvis a command first."
        ev = FeedbackEvent(
            ts=time.time(),
            verdict=verdict,
            prompt=self.last_prompt,
            action=self.last_action or self.last_prompt,
            reply=self.last_reply,
            note=(note or "")[:200],
        )
        try:
            with RLHF_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")
        except Exception as e:
            return f"RLHF log failed: {e}"
        # Update rolling state
        try:
            state = self._state()
            state["counts"][verdict] = int(state["counts"].get(verdict, 0)) + 1
            state["last"] = asdict(ev)
            RLHF_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass
        label = "Approved" if verdict == "approve" else "Rejected"
        return f"{label} — logged for Sunday preference digest."

    def status(self) -> str:
        state = self._state()
        a = state["counts"].get("approve", 0)
        r = state["counts"].get("reject", 0)
        return f"RLHF log: {a} approve / {r} reject. Last action: {self.last_action[:60] or 'none'}."

    def digest(self, *, apply: bool = True) -> str:
        """
        Compile feedback into custom_instructions.md habits.
        Intended for weekly Task Scheduler (Sunday night).
        """
        events = self._read_events()
        if not events:
            return "No RLHF events to digest."
        rejects = [e for e in events if e.get("verdict") == "reject"]
        approves = [e for e in events if e.get("verdict") == "approve"]

        # Find rejected action keywords to avoid
        reject_words: Counter[str] = Counter()
        for e in rejects[-40:]:
            for w in (e.get("action") or "").lower().split():
                if len(w) > 3:
                    reject_words[w] += 1
        approve_words: Counter[str] = Counter()
        for e in approves[-40:]:
            for w in (e.get("action") or "").lower().split():
                if len(w) > 3:
                    approve_words[w] += 1

        tips: list[str] = []
        for w, n in reject_words.most_common(5):
            if n >= 2:
                tips.append(f"Prefer not to auto-run actions involving '{w}' without confirming")
        for w, n in approve_words.most_common(5):
            if n >= 3:
                tips.append(f"User often approves '{w}' — keep those flows snappy")

        if not tips:
            tips.append(
                f"RLHF digest {datetime.now().strftime('%Y-%m-%d')}: "
                f"{len(approves)} approve / {len(rejects)} reject — no strong patterns yet"
            )

        if apply:
            instr = CustomInstructions()
            for tip in tips[:4]:
                instr.append(tip)

        state = self._state()
        state["last_digest"] = time.time()
        state["last_digest_tips"] = tips
        RLHF_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return "Digest applied: " + "; ".join(tips[:3])

    def _state(self) -> dict[str, Any]:
        try:
            return json.loads(RLHF_STATE.read_text(encoding="utf-8"))
        except Exception:
            return {"counts": {}, "last": None}

    def _read_events(self) -> list[dict[str, Any]]:
        if not RLHF_PATH.exists():
            return []
        out: list[dict[str, Any]] = []
        try:
            for line in RLHF_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                out.append(json.loads(line))
        except Exception:
            pass
        return out

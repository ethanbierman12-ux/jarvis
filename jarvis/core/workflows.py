"""Named automated workflows — morning / night / focus / standup macros."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


ProgressFn = Callable[[str, dict[str, Any]], None]


@dataclass
class WorkflowStep:
    id: str
    label: str
    action: str  # brain utterance or internal key


WORKFLOWS: dict[str, list[WorkflowStep]] = {
    "morning": [
        WorkflowStep("brief", "Morning standup + tabs", "good morning"),
        WorkflowStep("weather", "Weather telemetry", "weather"),
        WorkflowStep("lamp", "Desk lamp on", "turn on the lamp"),
        WorkflowStep("music", "Focus playlist", "play my focus playlist"),
    ],
    "night": [
        WorkflowStep("lamp", "Lamp off", "turn off the lamp"),
        WorkflowStep("mute", "Mute output", "mute"),
        WorkflowStep("away", "Away steward", "away mode"),
        WorkflowStep("bed", "Bedtime protocol", "goodnight"),
    ],
    "focus": [
        WorkflowStep("lamp", "Coding light", "coding mode"),
        WorkflowStep("music", "Focus music", "play my focus playlist"),
        WorkflowStep("vibe", "Quiet extras", "volume down"),
        WorkflowStep("work", "Work desktop", "start work"),
    ],
    "standup": [
        WorkflowStep("brief", "Daily brief", "good morning"),
        WorkflowStep("stats", "System vitals", "status"),
        WorkflowStep("hub", "Hub pulse", "hub status"),
    ],
    "secure": [
        WorkflowStep("shot", "Screenshot", "take a screenshot"),
        WorkflowStep("lock", "Lock workstation", "lock"),
    ],
}


class WorkflowEngine:
    """Runs ordered voice/command macros against brain.handle_utterance."""

    def __init__(self, run_cmd: Callable[[str], str | None]) -> None:
        self._run = run_cmd
        self._last: str = ""
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def list_workflows(self) -> str:
        names = ", ".join(sorted(WORKFLOWS))
        return f"Workflows ready: {names}. Say run morning workflow."

    def run(
        self,
        name: str,
        *,
        progress: ProgressFn | None = None,
        delay_sec: float = 0.55,
    ) -> str:
        key = (name or "").strip().lower()
        steps = WORKFLOWS.get(key)
        if not steps:
            return f"Unknown workflow '{name}'. {self.list_workflows()}"
        if self._running:
            return "A workflow is already running."
        self._running = True
        self._last = key
        ok = 0
        errors: list[str] = []
        try:
            total = len(steps)
            for i, step in enumerate(steps, 1):
                if progress:
                    try:
                        progress(
                            step.label,
                            {
                                "workflow": key,
                                "step": step.id,
                                "index": i,
                                "total": total,
                                "pct": int(100 * i / total),
                            },
                        )
                    except Exception:
                        pass
                try:
                    self._run(step.action)
                    ok += 1
                except Exception as e:
                    errors.append(f"{step.id}: {e}")
                if delay_sec > 0 and i < total:
                    time.sleep(delay_sec)
        finally:
            self._running = False
        msg = f"Workflow {key} finished — {ok}/{len(steps)} steps."
        if errors:
            msg += f" Issues: {'; '.join(errors[:2])}."
        return msg

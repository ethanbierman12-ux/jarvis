"""Nightly self-audit — propose patches from logs; never auto-mutate without HITL."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path


class SelfAudit:
    def __init__(self, data_dir: Path, root: Path) -> None:
        self.data = Path(data_dir)
        self.root = Path(root)
        self.out = self.data / "self_audit"
        self.out.mkdir(parents=True, exist_ok=True)
        self._last_run = 0.0

    def run(self, *, apply: bool = False) -> str:
        """Scan recent logs; write a proposal. apply=True only writes a sandbox note."""
        now = time.time()
        if now - self._last_run < 30:
            return "Self-audit cooldown — wait a moment."
        self._last_run = now

        findings: list[str] = []
        # Habit / sequence bloat
        seq = self.data / "command_sequences.json"
        if seq.exists() and seq.stat().st_size > 200_000:
            findings.append("command_sequences.json is large — consider pruning stale STT ghosts.")

        # Vision snapshot freshness
        snap = self.data / "last_vision.jpg"
        if snap.exists():
            age = now - snap.stat().st_mtime
            if age > 3600:
                findings.append(f"Vision snapshot is {int(age/60)}m old — camera may be idle.")

        # Price watch / security
        for name in ("price_watch.json", "security/security.json"):
            p = self.data / name
            if p.exists():
                findings.append(f"Module data present: {name}")

        # Heuristic bottlenecks from code size
        brain = self.root / "jarvis" / "brain.py"
        if brain.exists() and brain.stat().st_size > 400_000:
            findings.append(
                "brain.py is very large — route blocks could be split for faster imports."
            )

        if not findings:
            findings.append("No critical bottlenecks flagged. Systems nominal.")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report = self.out / f"audit_{stamp}.md"
        body = [
            f"# Jarvis Self-Audit · {stamp}",
            "",
            "HITL required before any auto-patch.",
            "",
            "## Findings",
            *[f"- {f}" for f in findings],
            "",
            "## Proposed next actions",
            "- Prune noisy STT entries in command_sequences.json",
            "- Keep upgrade freeze registry during hot_upgrade",
            "- Prefer Fahrenheit + America/New_York for desk HUD",
            "",
        ]
        if apply:
            body.append(
                "_apply flag set: wrote proposal only — sandbox mutation is disabled by policy._"
            )
        report.write_text("\n".join(body), encoding="utf-8")
        return (
            f"Self-audit complete — {len(findings)} notes. "
            f"Report: {report.name}. I will not mutate myself without your OK."
        )

    def maybe_nightly(self, hour_local: int | None = None) -> str | None:
        """If local hour is 3am window, run once per night."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        try:
            now = datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            now = datetime.now()
        if hour_local is None:
            hour_local = now.hour
        if hour_local != 3:
            return None
        marker = self.out / f"nightly_{now.strftime('%Y%m%d')}.flag"
        if marker.exists():
            return None
        msg = self.run(apply=False)
        marker.write_text("ok", encoding="utf-8")
        return msg

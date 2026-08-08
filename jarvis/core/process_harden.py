"""Process harden — scan suspicious Windows processes + safe optimize tips."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import psutil

# Heuristic names — not a kill list without HITL
_SUSPICIOUS = (
    "miner",
    "xmrig",
    "coinbase",
    "cryptonight",
    "keylogger",
    "cheatengine",
    "processhacker",  # dual-use — report only
)

_BLOAT_HINTS = (
    "yourphone",  # keep Phone Link — skip
    "spotifywebhelper",
    "adobearm",
    "ccxprocess",
    "crashpad",
    "microsoftedgeupdate",
    "googleupdate",
)


@dataclass
class ProcHit:
    name: str
    pid: int
    cpu: float
    rss_mb: float
    reason: str


class ProcessHarden:
    def scan(self) -> list[ProcHit]:
        hits: list[ProcHit] = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                name = (p.info.get("name") or "").lower()
                if not name:
                    continue
                cpu = float(p.info.get("cpu_percent") or 0)
                mem = p.info.get("memory_info")
                rss = (mem.rss / (1024 * 1024)) if mem else 0.0
                reason = ""
                if any(s in name for s in _SUSPICIOUS):
                    reason = "suspicious name"
                elif cpu > 85 and rss > 400:
                    reason = "high CPU+RAM"
                elif any(b in name for b in _BLOAT_HINTS) and rss > 200:
                    reason = "heavy updater / helper"
                if reason:
                    hits.append(
                        ProcHit(
                            name=p.info.get("name") or name,
                            pid=int(p.info["pid"]),
                            cpu=cpu,
                            rss_mb=rss,
                            reason=reason,
                        )
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        hits.sort(key=lambda h: h.cpu + h.rss_mb / 50.0, reverse=True)
        return hits[:12]

    def speak_scan(self) -> str:
        hits = self.scan()
        if not hits:
            return "Background scan clean — no obvious miners or runaway processes."
        bits = [
            f"{h.name} (pid {h.pid}, {h.cpu:.0f}% CPU, {h.rss_mb:.0f} MB) — {h.reason}"
            for h in hits[:5]
        ]
        return "Process harden: " + "; ".join(bits) + ". Say kill process NAME to close one."

    def chris_titus_guide(self) -> str:
        return (
            "Chris Titus–style harden (manual / HITL):\n"
            "1) winget upgrade --all\n"
            "2) Disable unused startups (Task Manager → Startup)\n"
            "3) Optional: run Chris Titus WinUtil from an elevated PowerShell "
            "(irm christitus.com/win | iex) — review tweaks before applying\n"
            "4) Say optimize jarvis · run backup · scan processes\n"
            "I will not auto-run community scripts without your approval."
        )

    def kill(self, name: str) -> str:
        needle = (name or "").lower().strip()
        if not needle or needle in ("explorer", "csrss", "wininit", "system"):
            return "Refusing to kill a critical process."
        killed = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                n = (p.info.get("name") or "").lower()
                if needle in n:
                    p.kill()
                    killed.append(f"{p.info.get('name')}#{p.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if not killed:
            return f"No process matched {name}."
        return "Closed: " + ", ".join(killed[:6])

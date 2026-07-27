"""Package / shipment tracking from notes + iCloud/Gmail snippets."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

PKG_PATH = DATA_DIR / "packages.json"

# Common carrier tracking patterns (heuristic)
_PATTERNS = [
    ("UPS", re.compile(r"\b1Z[A-Z0-9]{16}\b", re.I)),
    ("USPS", re.compile(r"\b(?:94|93|92|95)\d{20}\b")),
    ("USPS", re.compile(r"\b\d{20,22}\b")),
    ("FedEx", re.compile(r"\b\d{12,15}\b")),
    ("Amazon", re.compile(r"\bTBA\d{10,}\b", re.I)),
]


class PackageTracker:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not PKG_PATH.exists():
            PKG_PATH.write_text(json.dumps({"packages": []}, indent=2), encoding="utf-8")

    def add(self, tracking: str, *, carrier: str = "", note: str = "") -> str:
        tracking = (tracking or "").strip().upper()
        if len(tracking) < 8:
            return "Need a valid tracking number, Sir."
        if not carrier:
            carrier = self._guess_carrier(tracking)
        data = self._load()
        for p in data.get("packages") or []:
            if str(p.get("tracking") or "").upper() == tracking:
                p["note"] = note or p.get("note") or ""
                p["updated"] = time.time()
                self._save(data)
                return f"Updated package {tracking} ({carrier})."
        data.setdefault("packages", []).append(
            {
                "tracking": tracking,
                "carrier": carrier,
                "note": (note or "")[:120],
                "added": time.time(),
                "updated": time.time(),
                "status": "active",
            }
        )
        data["packages"] = data["packages"][-80:]
        self._save(data)
        return f"Tracking {carrier} {tracking}. Say where's my package for a status sweep."

    def parse_and_add(self, text: str) -> str | None:
        t = text or ""
        for carrier, pat in _PATTERNS:
            m = pat.search(t)
            if m:
                return self.add(m.group(0), carrier=carrier, note=t[:80])
        return None

    def status(self) -> str:
        pkgs = [p for p in self._load().get("packages") or [] if p.get("status") != "done"]
        if not pkgs:
            return (
                "No active packages on file. Paste a tracking number or say "
                "track package 1Z… / TBA…"
            )
        pkgs = sorted(pkgs, key=lambda p: -float(p.get("updated") or 0))
        bits = []
        for p in pkgs[:6]:
            age = self._age(float(p.get("added") or 0))
            bits.append(
                f"{p.get('carrier') or 'Carrier'} {p.get('tracking')} "
                f"({p.get('note') or 'shipment'}, logged {age})"
            )
        return "Active shipments: " + "; ".join(bits) + "."

    def where_is_my_package(self) -> str:
        base = self.status()
        return (
            base
            + " Open the carrier site for live scans — I keep the ledger; "
            "carriers keep the trucks."
        )

    def _guess_carrier(self, tracking: str) -> str:
        if tracking.startswith("1Z"):
            return "UPS"
        if tracking.startswith("TBA"):
            return "Amazon"
        if re.match(r"^(94|93|92|95)", tracking):
            return "USPS"
        return "Carrier"

    def _age(self, ts: float) -> str:
        if not ts:
            return "recently"
        days = int((time.time() - ts) / 86400)
        if days <= 0:
            return "today"
        if days == 1:
            return "yesterday"
        return f"{days}d ago"

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(PKG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"packages": []}

    def _save(self, data: dict[str, Any]) -> None:
        PKG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

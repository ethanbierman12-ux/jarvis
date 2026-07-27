"""Stark workshop inventory — scan parts, stock, synergy, market hints."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

INV_PATH = DATA_DIR / "workshop_inventory.json"


@dataclass
class Part:
    id: str
    name: str
    category: str
    notes: str = ""
    socket: str = ""
    qty: int = 1
    ts: float = 0.0
    source: str = "vision"


class WorkshopInventory:
    """Virtual workshop stock with session synergy checks."""

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not INV_PATH.exists():
            INV_PATH.write_text(
                json.dumps({"parts": [], "session": []}, indent=2), encoding="utf-8"
            )
        self._session: list[dict[str, Any]] = []

    def register(
        self,
        name: str,
        *,
        category: str = "",
        notes: str = "",
        socket: str = "",
        qty: int = 1,
        source: str = "vision",
    ) -> str:
        name = (name or "").strip()[:120]
        if not name:
            return "Need a part name to register, Sir."
        cat = (category or self._infer_category(name)).strip().lower()
        sock = socket or self._infer_socket(f"{name} {notes}")
        data = self._load()
        # Merge qty if same name
        for p in data.get("parts") or []:
            if str(p.get("name") or "").lower() == name.lower():
                p["qty"] = int(p.get("qty") or 1) + max(1, int(qty))
                p["notes"] = (notes or p.get("notes") or "")[:200]
                if sock:
                    p["socket"] = sock
                if cat and (not p.get("category") or p.get("category") == "component"):
                    p["category"] = cat
                self._save(data)
                self._session.append(p)
                warn = self.synergy_check(p)
                base = (
                    f"Updated workshop stock: {name} ×{p['qty']}. "
                    f"Category {p.get('category') or cat}"
                    + (f", socket {p.get('socket')}" if p.get("socket") else "")
                    + "."
                )
                return base + (" " + warn if warn else "")
        part = Part(
            id=f"p{int(time.time()*1000)%10_000_000}",
            name=name,
            category=cat or "component",
            notes=notes[:200],
            socket=sock,
            qty=max(1, int(qty)),
            ts=time.time(),
            source=source,
        )
        data.setdefault("parts", []).append(asdict(part))
        data["parts"] = data["parts"][-500:]
        self._save(data)
        self._session.append(asdict(part))
        warn = self.synergy_check(asdict(part))
        base = (
            f"Registered {name} into the workshop inventory, Sir. "
            f"Category {part.category}"
            + (f", socket {part.socket}" if part.socket else "")
            + f". Stock count for this SKU: {part.qty}."
        )
        return base + (" " + warn if warn else "")

    def register_from_scan(self, scan_text: str) -> str:
        """Parse a vision/OCR blurb into a part registration."""
        text = (scan_text or "").strip()
        if not text:
            return "Scan was empty — show me the component again, Sir."
        # First meaningful line / noun phrase
        line = re.split(r"[\n.]", text)[0].strip()[:120]
        name = line or text[:80]
        return self.register(name, notes=text[:200], source="scan")

    def stock(self, query: str = "") -> str:
        data = self._load()
        parts = list(data.get("parts") or [])
        q = (query or "").strip().lower()
        if q:
            parts = [
                p
                for p in parts
                if q in str(p.get("name") or "").lower()
                or q in str(p.get("category") or "").lower()
                or q in str(p.get("notes") or "").lower()
            ]
        if not parts:
            return "Workshop inventory has no matching parts on file, Sir."
        # Group by category
        parts = sorted(parts, key=lambda p: (-int(p.get("qty") or 0), p.get("name") or ""))
        bits = []
        for p in parts[:12]:
            sock = f" [{p['socket']}]" if p.get("socket") else ""
            bits.append(f"{p.get('name')} ×{p.get('qty')}{sock}")
        return "Workshop stock: " + "; ".join(bits) + "."

    def synergy_check(self, new_part: dict[str, Any] | None = None) -> str:
        """Reject incompatible CPU/motherboard pairs in-session."""
        sess = list(self._session)
        if new_part:
            sess.append(new_part)
        cpus = [p for p in sess if self._is_cpu(p)]
        boards = [p for p in sess if self._is_board(p)]
        if not cpus or not boards:
            return ""
        cpu = cpus[-1]
        board = boards[-1]
        cs = (cpu.get("socket") or self._infer_socket(str(cpu.get("name") or ""))).upper()
        bs = (board.get("socket") or self._infer_socket(str(board.get("name") or ""))).upper()
        if cs and bs and cs != bs:
            return (
                f"I must strongly advise against this pairing, Sir. "
                f"{cpu.get('name')} looks like socket {cs}, but "
                f"{board.get('name')} appears to be {bs}. "
                "Together they will result in expensive paperweights."
            )
        if cs and bs and cs == bs:
            return f"Synergy check passed — both report socket {cs}."
        return ""

    def market_hint(self, name: str) -> str:
        """Best-effort public search link / duckduckgo lite hint."""
        q = (name or "").strip()
        if not q:
            return "Specify a part to source, Sir."
        url = "https://duckduckgo.com/?" + urllib.parse.urlencode({"q": f"{q} buy price"})
        # Non-blocking: just return guidance (browser optional)
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass
        return (
            f"Market sweep for “{q}”: opened a live search. "
            "Compare refurbished vs new — I can register the winner into stock after purchase."
        )

    def clear_session(self) -> str:
        self._session.clear()
        return "Workshop session slate cleared."

    def _is_cpu(self, p: dict[str, Any]) -> bool:
        blob = f"{p.get('name')} {p.get('category')} {p.get('notes')}".lower()
        return any(k in blob for k in ("cpu", "processor", "ryzen", "core i", "intel", "amd"))

    def _is_board(self, p: dict[str, Any]) -> bool:
        blob = f"{p.get('name')} {p.get('category')} {p.get('notes')}".lower()
        if any(
            k in blob
            for k in (
                "motherboard",
                "mainboard",
                "mobo",
                "b850",
                "b840",
                "b650",
                "b550",
                "b450",
                "x870",
                "x670",
                "x570",
                "x470",
                "a620",
                "z790",
                "z690",
                "b760",
                "b660",
                "h770",
            )
        ):
            return True
        # "ASRock B550 board" / "... mobo board"
        return bool(re.search(r"\bboard\b", blob) and not self._is_cpu(p))

    def _infer_category(self, name: str) -> str:
        n = name.lower()
        if any(k in n for k in ("cpu", "ryzen", "intel", "processor")):
            return "cpu"
        if any(
            k in n
            for k in (
                "motherboard",
                "mobo",
                "b850",
                "b840",
                "b650",
                "b550",
                "b450",
                "x870",
                "x670",
                "x570",
                "a620",
                "z790",
                "z690",
                "b760",
            )
        ) or (re.search(r"\bboard\b", n) and "keyboard" not in n):
            return "motherboard"
        if any(k in n for k in ("gpu", "rtx", "radeon", "graphics")):
            return "gpu"
        if any(k in n for k in ("ram", "ddr4", "ddr5")):
            return "memory"
        if any(k in n for k in ("ssd", "nvme", "hdd")):
            return "storage"
        if any(k in n for k in ("psu", "power supply")):
            return "psu"
        return "component"

    def _infer_socket(self, blob: str) -> str:
        b = blob.upper().replace(" ", "")
        for sock in (
            "AM5",
            "AM4",
            "LGA1700",
            "LGA1200",
            "LGA1151",
            "TR4",
            "STRX4",
        ):
            if sock in b:
                return "sTRX4" if sock == "STRX4" else sock
        # Chipset → common socket
        if re.search(r"\b(B650|X670|A620|B840|X870)\b", blob, re.I):
            return "AM5"
        if re.search(r"\b(B550|X570|B450|X470)\b", blob, re.I):
            return "AM4"
        if re.search(r"\b(Z790|B760|H770|Z690|B660)\b", blob, re.I):
            return "LGA1700"
        # AMD Ryzen generation → socket
        if re.search(
            r"\b(?:ryzen|r[3579])\s*[3579]?\s*(?:7|8|9)\d{3}\b|\b(?:7700|7600|7500|7950|7900|9600|9700|9950)\b",
            blob,
            re.I,
        ):
            return "AM5"
        if re.search(
            r"\b(?:ryzen|r[3579])\s*[3579]?\s*5\d{3}\b|\b(?:5600|5700|5800|5900|5950)\b",
            blob,
            re.I,
        ):
            return "AM4"
        if re.search(r"\b(?:i[3579]|core)\s*-?\s*1[34]\d{3}\b|\b14\d{3}[kf]?\b", blob, re.I):
            return "LGA1700"
        if re.search(r"\bam5\b", blob, re.I):
            return "AM5"
        if re.search(r"\bam4\b", blob, re.I):
            return "AM4"
        if re.search(r"lga\s*1700", blob, re.I):
            return "LGA1700"
        return ""

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(INV_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"parts": [], "session": []}

    def _save(self, data: dict[str, Any]) -> None:
        INV_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

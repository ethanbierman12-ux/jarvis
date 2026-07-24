"""Overnight memory consolidation — chat/day facts → Chroma."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jarvis.config import DATA_DIR


class MemoryConsolidator:
    """
    Nightly pass: skim hitl log / diary / mission-ish text files,
    extract short durable facts, upsert into VectorMemory.
    """

    def __init__(self, vstore, *, out_dir: Path | None = None) -> None:
        self.vstore = vstore
        self.out = Path(out_dir or (DATA_DIR / "memory_digest"))
        self.out.mkdir(parents=True, exist_ok=True)

    def maybe_nightly(self, hour_local: int | None = None) -> str | None:
        now = datetime.now(ZoneInfo("America/New_York"))
        hour = now.hour if hour_local is None else int(hour_local)
        # 3:10–3:50 window so it coexists with self_audit
        if hour != 3:
            return None
        marker = self.out / f"consolidate_{now.strftime('%Y%m%d')}.flag"
        if marker.exists():
            return None
        msg = self.run()
        marker.write_text("ok\n", encoding="utf-8")
        return msg

    def run(self) -> str:
        texts = self._gather_sources()
        facts = self._extract_facts(texts)
        stored = 0
        for fact in facts:
            try:
                self.vstore.remember(fact, kind="nightly")
                stored += 1
            except Exception:
                pass
        digest_path = self.out / f"digest_{time.strftime('%Y%m%d')}.txt"
        body = "\n".join(f"- {f}" for f in facts) or "(no new facts)"
        digest_path.write_text(
            f"Memory consolidate {time.strftime('%Y-%m-%d %H:%M')}\n{body}\n",
            encoding="utf-8",
        )
        # Wake brief hint file
        try:
            wake = DATA_DIR / "morning_standup.txt"
            prev = wake.read_text(encoding="utf-8") if wake.exists() else ""
            tip = f"\n\n[Memory] Overnight: stored {stored} facts.\n{body[:500]}"
            if "[Memory] Overnight" not in prev:
                wake.write_text((prev.rstrip() + tip).strip() + "\n", encoding="utf-8")
        except Exception:
            pass
        return f"Nightly memory consolidate stored {stored} facts."

    def _gather_sources(self) -> list[str]:
        chunks: list[str] = []
        candidates = [
            DATA_DIR / "hitl_log.jsonl",
            DATA_DIR / "diary.jsonl",
            DATA_DIR / "rlhf.jsonl",
            DATA_DIR / "jarvis.log",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                # Tail only — last ~80KB
                chunks.append(raw[-80_000:])
            except Exception:
                continue
        return chunks

    def _extract_facts(self, chunks: list[str]) -> list[str]:
        facts: list[str] = []
        blob = "\n".join(chunks)
        # Prefer explicit remember-style / preference lines
        patterns = [
            re.compile(
                r"(?i)(?:prefer|likes?|always|never|my (?:name|city|project|camera|mic))"
                r"[^.?\n]{5,120}"
            ),
            re.compile(r"(?i)remember(?:ed)?[:\s]+([^.?\n]{8,120})"),
            re.compile(r"(?i)user(?:'s)?\s+(?:name|timezone|city)\s*[:=]\s*([^\n,]{2,60})"),
        ]
        seen: set[str] = set()
        for pat in patterns:
            for m in pat.finditer(blob):
                text = (m.group(0) if m.lastindex is None else m.group(1)).strip()
                text = re.sub(r"\s+", " ", text)
                key = text.lower()
                if key in seen or len(text) < 8:
                    continue
                seen.add(key)
                facts.append(text[:160])
                if len(facts) >= 12:
                    return facts
        # JSONL hitl titles as weak facts
        for line in blob.splitlines()[-200:]:
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            title = str(obj.get("title") or obj.get("detail") or "").strip()
            if 12 <= len(title) <= 120 and title.lower() not in seen:
                seen.add(title.lower())
                facts.append(f"Session note: {title}")
            if len(facts) >= 12:
                break
        return facts

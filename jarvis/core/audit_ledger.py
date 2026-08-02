"""Tamper-evident append-only audit chain for sensitive Jarvis writes."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

AUDIT_DIR = DATA_DIR / "audit"
AUDIT_CHAIN = AUDIT_DIR / "chain.jsonl"
SENSITIVITY = {"personal", "work", "public"}
GENESIS_HASH = "sha256:" + ("0" * 64)


def normalize_sensitivity(value: str | None, *, default: str = "personal") -> str:
    label = (value or default).lower().strip()
    return label if label in SENSITIVITY else default


def classify_sensitivity(*, kind: str = "", explicit: str = "") -> str:
    if explicit:
        return normalize_sensitivity(explicit)
    low = (kind or "").lower()
    if low in {"crew", "project", "work", "handoff", "nightly"}:
        return "work"
    if low in {"public", "published"}:
        return "public"
    return "personal"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


class AuditLedger:
    """A hash-linked JSONL ledger.

    Payloads are never stored. Each record contains only their SHA-256 digest
    plus non-secret metadata, so the chain can prove ordering and detect edits.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or AUDIT_CHAIN)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(
        self,
        *,
        actor: str,
        op: str,
        resource: str,
        payload: Any,
        sensitivity: str = "personal",
        meta: dict[str, Any] | None = None,
    ) -> str:
        with self._lock:
            with self._process_lock():
                if self.path.exists() and self.path.stat().st_size:
                    ok, detail = self._verify_unlocked()
                    if not ok:
                        raise RuntimeError(f"refusing append to damaged audit chain: {detail}")
                seq, previous = self._head()
                body = {
                    "seq": seq + 1,
                    "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "prev_hash": previous,
                    "actor": str(actor or "jarvis")[:64],
                    "op": str(op or "write")[:96],
                    "resource": str(resource or "unknown")[:180],
                    "sensitivity": normalize_sensitivity(sensitivity),
                    "payload_digest": _digest(payload),
                    "meta": self._safe_meta(meta or {}),
                }
                record_hash = _digest(body)
                record = {**body, "hash": record_hash}
                encoded = (
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                ).encode("utf-8")
                with self.path.open("ab") as handle:
                    handle.write(encoded)
                    handle.flush()
                    try:
                        os.fsync(handle.fileno())
                    except OSError:
                        pass
                return record_hash

    def verify(self) -> tuple[bool, str]:
        with self._lock:
            with self._process_lock():
                return self._verify_unlocked()

    def verify_readonly(self) -> tuple[bool, str]:
        """Verify without creating a writer lock (for a foreign-process ledger)."""
        with self._lock:
            return self._verify_unlocked()

    def status(self) -> dict[str, Any]:
        ok, detail = self.verify()
        seq, head = self._head()
        return {"ok": ok, "records": seq, "head": head, "detail": detail}

    def _head(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, GENESIS_HASH
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            last = next((line for line in reversed(lines) if line.strip()), "")
            if not last:
                return 0, GENESIS_HASH
            record = json.loads(last)
            return int(record.get("seq", 0)), str(record.get("hash") or GENESIS_HASH)
        except Exception:
            raise RuntimeError("Audit chain head is unreadable")

    def _verify_unlocked(self) -> tuple[bool, str]:
        if not self.path.exists():
            return True, "Audit chain empty — genesis is valid."
        previous = GENESIS_HASH
        expected_seq = 1
        count = 0
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    actual_hash = str(record.pop("hash", ""))
                    if int(record.get("seq", 0)) != expected_seq:
                        return False, f"Sequence break at line {line_no}."
                    if record.get("prev_hash") != previous:
                        return False, f"Previous-hash mismatch at line {line_no}."
                    calculated = _digest(record)
                    if actual_hash != calculated:
                        return False, f"Record hash mismatch at line {line_no}."
                    previous = actual_hash
                    expected_seq += 1
                    count += 1
        except Exception as exc:
            return False, f"Audit chain unreadable: {exc}"
        return True, f"Audit chain valid — {count} records; head {previous[:24]}…"

    @contextmanager
    def _process_lock(self):
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _safe_meta(meta: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in meta.items():
            name = str(key)[:64]
            low = name.lower()
            if any(token in low for token in ("secret", "token", "password", "key", "pin")):
                safe[name] = bool(value)
            elif isinstance(value, (str, int, float, bool, type(None))):
                safe[name] = value[:180] if isinstance(value, str) else value
            else:
                safe[name] = str(value)[:180]
        return safe


_ledger: AuditLedger | None = None
_ledger_lock = threading.Lock()


def get_audit_ledger() -> AuditLedger:
    global _ledger
    if _ledger is None:
        with _ledger_lock:
            if _ledger is None:
                _ledger = AuditLedger()
    return _ledger

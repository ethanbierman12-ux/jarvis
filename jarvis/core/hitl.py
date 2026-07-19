"""Human-in-the-loop (HITL) — AI runs ~95% autonomous, pauses on high-impact acts.

Policy
------
Autonomous (no ask): invent, plan, draft copy, sandbox writes, live HUD preview,
iterate polish, diagnostics.

Gate (must ask): deploy / ship / open external browser or IDE, publish, wipe or
rebuild an existing project tree, or any "massive structural" change
(many-file scaffold rewrite, layout system swap on an existing site).

Clarification: optional ask when the brief is too ambiguous *and* the user has
asked for a named production deploy — otherwise invent autonomously.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class HitlKind(str, Enum):
    PERMISSION = "permission"  # yes / no before deploy or structure
    CLARIFY = "clarify"  # need a short answer


class HitlDecision(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    ANSWERED = "answered"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"  # HITL disabled


@dataclass
class HitlRequest:
    id: str
    kind: HitlKind
    title: str
    detail: str
    action: str  # deploy | structure | clarify
    agent: str = "agent"  # site | vibe | away | agent
    options: list[str] = field(default_factory=lambda: ["Approve", "Deny"])
    meta: dict[str, Any] = field(default_factory=dict)
    created: float = field(default_factory=time.time)


@dataclass
class HitlResult:
    decision: HitlDecision
    request_id: str
    answer: str = ""
    note: str = ""


# Structural change thresholds — above this → HITL permission
MASSIVE_FILE_COUNT = 4
MASSIVE_BYTES = 60_000


def is_massive_structure(*, file_count: int = 0, total_bytes: int = 0, rebuild: bool = False) -> bool:
    if rebuild:
        return True
    if file_count >= MASSIVE_FILE_COUNT:
        return True
    if total_bytes >= MASSIVE_BYTES:
        return True
    return False


class HumanInTheLoop:
    """Thread-safe gate used by background agent workers."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_sec: float = 300.0,
        on_ask: Callable[[HitlRequest], None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.timeout_sec = max(30.0, float(timeout_sec))
        self.on_ask = on_ask
        self._lock = threading.Lock()
        self._events: dict[str, threading.Event] = {}
        self._results: dict[str, HitlResult] = {}
        self._pending: HitlRequest | None = None

    def set_ask_handler(self, fn: Callable[[HitlRequest], None] | None) -> None:
        self.on_ask = fn

    @property
    def pending(self) -> HitlRequest | None:
        return self._pending

    def ask_permission(
        self,
        *,
        title: str,
        detail: str,
        action: str = "deploy",
        agent: str = "agent",
        meta: dict[str, Any] | None = None,
    ) -> HitlResult:
        return self._ask(
            HitlKind.PERMISSION,
            title=title,
            detail=detail,
            action=action,
            agent=agent,
            options=["Approve", "Deny"],
            meta=meta or {},
        )

    def ask_clarify(
        self,
        *,
        title: str,
        detail: str,
        agent: str = "agent",
        options: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> HitlResult:
        return self._ask(
            HitlKind.CLARIFY,
            title=title,
            detail=detail,
            action="clarify",
            agent=agent,
            options=options or ["Option A", "Option B", "Skip — invent"],
            meta=meta or {},
        )

    def gate_deploy(
        self,
        *,
        what: str,
        path: str = "",
        agent: str = "agent",
    ) -> bool:
        """Return True if deploy/ship/open is allowed."""
        if not self.enabled:
            return True
        result = self.ask_permission(
            title="HITL · Deploy permission",
            detail=(
                f"Agent finished sandbox work for:\n{what}\n\n"
                f"{'Path: ' + path + chr(10) if path else ''}"
                "Approve to ship / open externally. Deny keeps it in the HUD sandbox only."
            ),
            action="deploy",
            agent=agent,
            meta={"what": what, "path": path},
        )
        return result.decision == HitlDecision.APPROVED

    def gate_structure(
        self,
        *,
        what: str,
        file_count: int = 0,
        rebuild: bool = False,
        agent: str = "agent",
        path: str = "",
    ) -> bool:
        """Return True if massive structural write is allowed."""
        if not self.enabled:
            return True
        if not is_massive_structure(file_count=file_count, rebuild=rebuild):
            return True
        result = self.ask_permission(
            title="HITL · Structural change",
            detail=(
                f"Massive structural change queued:\n{what}\n\n"
                f"Files: {file_count} · rebuild={rebuild}\n"
                f"{'Path: ' + path + chr(10) if path else ''}"
                "Approve to write the scaffold. Deny aborts the structural rewrite."
            ),
            action="structure",
            agent=agent,
            meta={"what": what, "file_count": file_count, "rebuild": rebuild, "path": path},
        )
        return result.decision == HitlDecision.APPROVED

    def resolve(self, request_id: str, *, approve: bool | None = None, answer: str = "") -> bool:
        """UI / voice resolves a pending request. Returns True if matched."""
        with self._lock:
            ev = self._events.get(request_id)
            if not ev:
                # Allow resolving the only pending request without id
                if self._pending and (not request_id or request_id == self._pending.id):
                    request_id = self._pending.id
                    ev = self._events.get(request_id)
                if not ev:
                    return False
            req = self._pending
            if approve is True:
                decision = HitlDecision.APPROVED
            elif approve is False:
                decision = HitlDecision.DENIED
            else:
                decision = HitlDecision.ANSWERED
            self._results[request_id] = HitlResult(
                decision=decision,
                request_id=request_id,
                answer=(answer or "").strip(),
            )
            if req and req.id == request_id:
                self._pending = None
            ev.set()
            return True

    def resolve_voice(self, text: str) -> str | None:
        """Parse natural language approval. Returns status string or None if not HITL."""
        t = (text or "").strip().lower()
        if not self._pending:
            return None
        req = self._pending

        # Bare yes / no while a gate is open
        if t in ("yes", "y", "ok", "okay", "sure", "proceed", "approve", "approved", "allow"):
            self.resolve(req.id, approve=True)
            return "HITL approved — continuing."
        if t in ("no", "nah", "nope", "deny", "denied", "cancel", "abort"):
            self.resolve(req.id, approve=False)
            return "HITL denied — staying in sandbox."

        if any(
            k in t
            for k in (
                "approve",
                "ship it",
                "go ahead",
                "yes deploy",
                "do it",
                "confirm",
                "allow deploy",
                "open it",
            )
        ) and not any(k in t for k in ("don't", "do not", "deny", "no deploy", "cancel")):
            self.resolve(req.id, approve=True)
            return "HITL approved — continuing."

        if any(
            k in t
            for k in (
                "deny",
                "don't deploy",
                "do not deploy",
                "don't ship",
                "no deploy",
                "sandbox only",
                "don't open",
            )
        ):
            self.resolve(req.id, approve=False)
            return "HITL denied — staying in sandbox."

        if req.kind == HitlKind.CLARIFY and len(t) > 1:
            self.resolve(req.id, approve=None, answer=text.strip())
            return f"HITL noted: {text.strip()[:120]}"
        return None

    def _ask(
        self,
        kind: HitlKind,
        *,
        title: str,
        detail: str,
        action: str,
        agent: str,
        options: list[str],
        meta: dict[str, Any],
    ) -> HitlResult:
        if not self.enabled:
            return HitlResult(decision=HitlDecision.SKIPPED, request_id="", note="hitl off")

        req = HitlRequest(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            title=title,
            detail=detail,
            action=action,
            agent=agent,
            options=options,
            meta=meta,
        )
        ev = threading.Event()
        with self._lock:
            self._pending = req
            self._events[req.id] = ev
            self._results.pop(req.id, None)

        if self.on_ask:
            try:
                self.on_ask(req)
            except Exception:
                pass

        ok = ev.wait(timeout=self.timeout_sec)
        with self._lock:
            result = self._results.pop(
                req.id,
                HitlResult(
                    decision=HitlDecision.TIMEOUT if not ok else HitlDecision.DENIED,
                    request_id=req.id,
                    note="timeout" if not ok else "",
                ),
            )
            self._events.pop(req.id, None)
            if self._pending and self._pending.id == req.id:
                self._pending = None
        # Timeout = deny for safety (no silent deploy)
        if result.decision == HitlDecision.TIMEOUT:
            result.note = "timed out — treated as deny"
        return result

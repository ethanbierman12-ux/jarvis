"""Work Crew — persona-named specialists for units of external work.

Sits alongside the eight-agent :class:`jarvis.core.agent_crew.AgentCrew` (which
handles conversation + tools). Work Crew is smaller, tighter, and
HITL-gated for any side-effect that leaves the machine.

Roster
------
* **MANAGER**  — dispatcher / planner (picks the smallest specialist set).
* **SCHOLAR**  — research / current events (delegates to the existing
  :class:`ResearchAgent` when available).
* **STITCH**   — code integration / patch author (sandbox writes only).
* **REEL**     — short-form video draft + HITL-gated Buffer publish.
* **FLIP**     — deal / arbitrage scout (report only, never buys).
* **LEDGER**   — finance summaries (read-only; **never** executes trades).
* **MUSE**     — creative / copy pass drafts (sandbox writes only).

Every ``dispatch`` writes exactly one JSONL line to
``jarvis/data/work_outcomes.jsonl`` so the Agent Ops dashboard can tail it and
show XP + counts per agent tile.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR
from jarvis.core.llm_client import backend_name, complete

WORK_OUTCOMES_PATH = DATA_DIR / "work_outcomes.jsonl"

# Trade verbs — LEDGER refuses these unconditionally.
_TRADE_VERBS = (
    "buy",
    "sell",
    "execute",
    "trade",
    "order",
    "long",
    "short",
    "open position",
    "close position",
    "market order",
    "limit order",
    "stop order",
    "swap",
    "convert to",
    "exchange for",
)

_TRADE_VERB_RE = re.compile(
    r"\b(" + "|".join(re.escape(v) for v in _TRADE_VERBS) + r")\b",
    re.IGNORECASE,
)


class TradeExecutionRefused(PermissionError):
    """Raised whenever anything tries to talk LEDGER into a trade."""


@dataclass
class WorkOutcome:
    """One dispatch result. Persisted as a JSONL line."""

    agent: str
    kind: str
    ok: bool
    summary: str
    xp: int = 0
    hitl: bool = False
    ts: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ts": round(self.ts, 3),
                "agent": self.agent,
                "kind": self.kind,
                "ok": self.ok,
                "summary": self.summary,
                "xp": int(self.xp),
                "hitl": self.hitl,
                "meta": self.meta,
            },
            ensure_ascii=False,
        )


class OutcomeLog:
    """Append-only JSONL sink for Work Crew outcomes."""

    def __init__(self, path: Path = WORK_OUTCOMES_PATH) -> None:
        self.path = path

    def append(self, outcome: WorkOutcome) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(outcome.to_json() + "\n")
        except Exception as e:
            print(f"[work_crew] outcome log failed: {e}")

    def totals(self) -> dict[str, dict[str, int]]:
        """Read the log and return ``{agent: {xp, count, ok, fail}}``."""
        totals: dict[str, dict[str, int]] = {}
        try:
            if not self.path.is_file():
                return totals
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                agent = row.get("agent") or "?"
                bucket = totals.setdefault(agent, {"xp": 0, "count": 0, "ok": 0, "fail": 0})
                bucket["xp"] += int(row.get("xp") or 0)
                bucket["count"] += 1
                if row.get("ok"):
                    bucket["ok"] += 1
                else:
                    bucket["fail"] += 1
        except Exception as e:
            print(f"[work_crew] totals: {e}")
        return totals


class _BaseAgent:
    """Every Work Crew persona subclasses this — minimal shared plumbing."""

    handle: str = "AGENT"
    xp_success: int = 5
    xp_failure: int = 1

    def outcome(
        self,
        *,
        kind: str,
        ok: bool,
        summary: str,
        xp: int | None = None,
        hitl: bool = False,
        meta: dict[str, Any] | None = None,
    ) -> WorkOutcome:
        return WorkOutcome(
            agent=self.handle,
            kind=kind,
            ok=ok,
            summary=summary.strip(),
            xp=int(self.xp_success if ok else self.xp_failure) if xp is None else int(xp),
            hitl=hitl,
            meta=meta or {},
        )


class ScholarAgent(_BaseAgent):
    """SCHOLAR — reuses ResearchAgent when settings are wired, else notes."""

    handle = "SCHOLAR"
    xp_success = 10

    def __init__(self, settings: Any | None = None, research: Any | None = None) -> None:
        self._research = research
        self._settings = settings

    def _lazy_research(self) -> Any | None:
        if self._research is not None:
            return self._research
        try:
            from jarvis.core.agent_crew import ResearchAgent

            self._research = ResearchAgent(self._settings)
            return self._research
        except Exception:
            return None

    def run(self, query: str) -> WorkOutcome:
        query = (query or "").strip()
        if not query:
            return self.outcome(kind="research_skip", ok=False, summary="Empty query.")
        research = self._lazy_research()
        if research is None:
            return self.outcome(
                kind="research_offline",
                ok=False,
                summary="Research backend unavailable — Tavily/Serper/DDG not linked.",
            )
        try:
            text = research.run(query)
        except Exception as e:  # noqa: BLE001
            return self.outcome(kind="research_error", ok=False, summary=f"error: {e}")
        return self.outcome(
            kind="research",
            ok=bool(text and "No search backend" not in text),
            summary=text[:400],
            meta={"chars": len(text or "")},
        )


class StitchAgent(_BaseAgent):
    """STITCH — sandbox patch author. Never pushes without HITL."""

    handle = "STITCH"
    xp_success = 15
    SANDBOX = DATA_DIR / "work_crew" / "stitch"

    def draft_patch(self, request: str) -> WorkOutcome:
        req = (request or "").strip()
        if not req:
            return self.outcome(kind="stitch_skip", ok=False, summary="Empty patch request.")
        prompt = (
            "You are a careful software engineer. Sketch the smallest, "
            "safest diff that addresses the request. Return unified diff "
            "text only — no commentary.\n\nREQUEST:\n"
            + req
        )
        body = complete(prompt, system="Sandbox-only. No file deletion.", max_tokens=800)
        if not body:
            return self.outcome(
                kind="stitch_offline",
                ok=False,
                summary="No LLM backend available for STITCH.",
            )
        try:
            self.SANDBOX.mkdir(parents=True, exist_ok=True)
            fname = self.SANDBOX / f"patch_{int(time.time())}.diff"
            fname.write_text(body, encoding="utf-8")
        except Exception as e:
            return self.outcome(kind="stitch_write_fail", ok=False, summary=f"write: {e}")
        return self.outcome(
            kind="stitch_draft",
            ok=True,
            summary=f"Draft patch saved: {fname.name} ({len(body)} chars).",
            meta={"path": str(fname)},
        )

    def push(self, *, hitl: Any = None) -> WorkOutcome:
        """Never run automatically. Requires an approved HITL gate."""
        if hitl is None or not hasattr(hitl, "gate_deploy"):
            return self.outcome(
                kind="stitch_push_refused",
                ok=False,
                summary="STITCH.push refused — no HITL gate available.",
                hitl=True,
            )
        approved = hitl.gate_deploy(what="STITCH: git push draft branch", agent="stitch")
        if not approved:
            return self.outcome(
                kind="stitch_push_denied",
                ok=False,
                summary="STITCH push denied by HITL — sandbox only.",
                hitl=True,
            )
        return self.outcome(
            kind="stitch_push_ready",
            ok=True,
            summary="STITCH cleared for push — run git push manually to complete.",
            hitl=True,
        )


class ReelAgent(_BaseAgent):
    """REEL — short-form video (TikTok / Reels / Shorts) draft + HITL publish."""

    handle = "REEL"
    xp_success = 20

    def __init__(self, cloud: Any | None = None) -> None:
        self._cloud = cloud

    def _lazy_cloud(self, settings: Any | None = None) -> Any | None:
        if self._cloud is not None:
            return self._cloud
        try:
            from jarvis.core.cloud_integrations import CloudIntegrations

            token = ""
            if settings is not None:
                token = getattr(settings, "buffer_access_token", "") or ""
            if not token:
                try:
                    from jarvis.core.secrets_vault import get_vault

                    token = get_vault().get("buffer_access_token", "")
                except Exception:
                    token = ""
            self._cloud = CloudIntegrations(buffer_access_token=token)
            return self._cloud
        except Exception:
            return None

    def draft(self, topic: str) -> WorkOutcome:
        topic = (topic or "").strip()
        if not topic:
            return self.outcome(kind="reel_skip", ok=False, summary="Empty topic.")
        prompt = (
            "Write a TikTok / Reels script for the topic below. Return four blocks:\n"
            "HOOK (first 3 seconds, punchy):\nBEATS (3 numbered story beats):\n"
            "CAPTION (<= 120 chars, hashtags at end):\nCTA (1 line):\n\nTOPIC: "
            + topic
        )
        body = complete(
            prompt,
            system="You are REEL, a short-form video copywriter. No fluff. British-butler flavour ok.",
            max_tokens=500,
        )
        if not body:
            return self.outcome(
                kind="reel_offline",
                ok=False,
                summary="No LLM backend available for REEL.",
            )
        return self.outcome(
            kind="reel_draft",
            ok=True,
            summary=body.strip()[:400],
            meta={"topic": topic, "chars": len(body)},
        )

    def publish_tiktok(
        self,
        caption: str,
        media_url: str = "",
        *,
        hitl: Any = None,
        settings: Any | None = None,
        force: bool = False,
    ) -> WorkOutcome:
        """HITL-gated Buffer TikTok draft.

        This never *auto-publishes*. Even when HITL approves, the request goes
        to Buffer as a draft (``now=False``) so the human still confirms in the
        Buffer app before it hits TikTok. ``force=True`` is reserved for tests
        that inject their own approved gate.
        """
        caption = (caption or "").strip()
        if not caption:
            return self.outcome(
                kind="reel_publish_skip",
                ok=False,
                summary="No caption — refusing to publish empty content.",
            )
        if hitl is None or not hasattr(hitl, "gate_deploy"):
            if not force:
                return self.outcome(
                    kind="reel_publish_refused",
                    ok=False,
                    summary="REEL.publish refused — no HITL gate wired.",
                    hitl=True,
                )
            approved = True
        else:
            approved = hitl.gate_deploy(
                what=f"REEL: Buffer TikTok draft — {caption[:80]}",
                agent="reel",
            )
        if not approved:
            return self.outcome(
                kind="reel_publish_denied",
                ok=False,
                summary="REEL publish denied by HITL — draft stays local.",
                hitl=True,
            )
        cloud = self._lazy_cloud(settings)
        if cloud is None or not getattr(cloud, "buffer_access_token", ""):
            return self.outcome(
                kind="reel_publish_pending",
                ok=False,
                summary=(
                    "Buffer not linked — approval recorded. "
                    "Say link buffer / set buffer token to finish publish."
                ),
                hitl=True,
                meta={"caption": caption, "media_url": media_url},
            )
        # The public Buffer GraphQL exposes createPost; we still stage as a
        # draft, never live now=true.
        query = """
        mutation($input: CreatePostInput!) {
          createPost(input: $input) { id status }
        }
        """
        variables = {
            "input": {
                "text": caption,
                "channels": [{"service": "tiktok"}],
                "media": [{"url": media_url}] if media_url else [],
                "now": False,
                "draft": True,
            }
        }
        try:
            data = cloud._buffer_graphql(query, variables)
        except Exception as e:  # noqa: BLE001
            return self.outcome(
                kind="reel_publish_error",
                ok=False,
                summary=f"Buffer draft failed: {e}",
                hitl=True,
                meta={"caption": caption},
            )
        pid = ((data or {}).get("createPost") or {}).get("id") or ""
        return self.outcome(
            kind="reel_publish_draft",
            ok=True,
            summary=f"Buffer TikTok draft staged ({pid or 'pending'}). "
            "Confirm in Buffer to actually publish.",
            hitl=True,
            meta={"caption": caption, "buffer_id": pid, "media_url": media_url},
        )


class FlipAgent(_BaseAgent):
    """FLIP — scouts deals / arbitrage; **never** clicks buy."""

    handle = "FLIP"
    xp_success = 8

    def scout(self, target: str) -> WorkOutcome:
        target = (target or "").strip()
        if not target:
            return self.outcome(kind="flip_skip", ok=False, summary="No target.")
        prompt = (
            f"You are FLIP, a deals scout. For the target below, propose 3 concrete "
            "resale or arbitrage opportunities. Each: source, expected margin, "
            "risk. Report only — do not suggest an automated purchase.\n\n"
            f"TARGET: {target}"
        )
        body = complete(
            prompt,
            system="You are a discerning deals analyst. Report opportunities; do not endorse automated purchases.",
            max_tokens=500,
        )
        if not body:
            return self.outcome(
                kind="flip_offline",
                ok=False,
                summary="No LLM backend available for FLIP.",
            )
        return self.outcome(
            kind="flip_scout",
            ok=True,
            summary=body.strip()[:400],
            meta={"target": target},
        )

    def execute_purchase(self, *_args: Any, **_kwargs: Any) -> WorkOutcome:
        """Refused. Work Crew never spends money automatically."""
        return self.outcome(
            kind="flip_execute_refused",
            ok=False,
            summary="FLIP refuses automated purchases. Report only.",
            hitl=True,
        )


class LedgerAgent(_BaseAgent):
    """LEDGER — finance reporting. **Read-only. Never trades.**"""

    handle = "LEDGER"
    xp_success = 6

    def __init__(self, spend: Any | None = None, cloud: Any | None = None) -> None:
        self._spend = spend
        self._cloud = cloud

    def report_only(self, request: str) -> WorkOutcome:
        request = (request or "").strip()
        if not request:
            return self.outcome(kind="ledger_skip", ok=False, summary="Empty request.")
        if _TRADE_VERB_RE.search(request):
            return self.outcome(
                kind="ledger_trade_refused",
                ok=False,
                summary=(
                    "LEDGER is read-only and refuses to place, modify, or "
                    "execute trades. Ask for a summary instead."
                ),
                hitl=True,
                meta={"request": request},
            )
        # Prefer live Stripe balance when linked, else drift into narrative.
        detail: list[str] = []
        try:
            if self._cloud is not None and getattr(self._cloud, "stripe_secret_key", ""):
                detail.append(self._cloud.stripe_status())
        except Exception:
            pass
        try:
            if self._spend is not None and hasattr(self._spend, "summary"):
                detail.append(str(self._spend.summary()))
        except Exception:
            pass
        joined = "\n".join(d for d in detail if d)
        if joined:
            return self.outcome(kind="ledger_report", ok=True, summary=joined[:400])
        body = complete(
            f"You are LEDGER, a read-only finance narrator. Summarise:\n{request}\n"
            "Never suggest placing a trade. Output <=120 words.",
            system="Read-only accountant. No trade suggestions.",
            max_tokens=250,
        ) or "LEDGER standing by — no live finance backend linked."
        return self.outcome(kind="ledger_report", ok=True, summary=body.strip()[:400])

    def execute_trade(self, *_args: Any, **_kwargs: Any) -> WorkOutcome:  # pragma: no cover
        """Hard refusal — this is the invariant tests pin to."""
        raise TradeExecutionRefused(
            "LEDGER is read-only. Trade execution is not implemented and never will be."
        )


class MuseAgent(_BaseAgent):
    """MUSE — creative brainstorming / copy pass."""

    handle = "MUSE"
    xp_success = 8

    def brainstorm(self, topic: str) -> WorkOutcome:
        topic = (topic or "").strip()
        if not topic:
            return self.outcome(kind="muse_skip", ok=False, summary="No topic.")
        body = complete(
            f"You are MUSE. Give 5 bold, fresh angles for the topic below. "
            "Each 1 sentence. Numbered list.\n\nTOPIC: {topic}".format(topic=topic),
            system="You are MUSE, a creative director. Sharp, unexpected, tasteful.",
            max_tokens=400,
        )
        if not body:
            return self.outcome(
                kind="muse_offline",
                ok=False,
                summary="No LLM backend available for MUSE.",
            )
        return self.outcome(kind="muse_brainstorm", ok=True, summary=body.strip()[:400])


class ManagerAgent(_BaseAgent):
    """MANAGER — picks the smallest set of specialists for the request."""

    handle = "MANAGER"
    xp_success = 3
    xp_failure = 0

    ROUTES = ("scholar", "stitch", "reel", "flip", "ledger", "muse")

    def plan(self, request: str) -> list[str]:
        t = (request or "").lower()
        picked: list[str] = []
        # Keyword-first (cheap + deterministic; MOCK_LLM safe)
        if re.search(r"\b(research|find|latest|news|who is|what is|current)\b", t):
            picked.append("scholar")
        if re.search(r"\b(patch|fix|refactor|diff|stitch|integrate)\b", t):
            picked.append("stitch")
        if re.search(r"\b(reel|tiktok|short|shorts|video|hook|caption)\b", t):
            picked.append("reel")
        if re.search(r"\b(deal|arbitrage|resale|flip|thrift|resell)\b", t):
            picked.append("flip")
        if re.search(r"\b(ledger|finance|balance|spend|income|invoice|revenue|expenses?)\b", t):
            picked.append("ledger")
        if re.search(r"\b(brainstorm|angle|creative|copy|slogan|tagline|muse)\b", t):
            picked.append("muse")
        # LLM refinement — best-effort. Empty result → keyword picks stand.
        try:
            hint = complete(
                f'Request: "{request}"\n\n'
                "Pick the smallest set of specialists from this list to satisfy the "
                "request. Reply with a JSON array of lowercase handles: "
                f"{list(self.ROUTES)}. If none fit, reply []. No commentary.",
                system="You are MANAGER, a terse dispatcher. JSON only.",
                temperature=0.1,
                max_tokens=80,
            )
            m = re.search(r"\[.*?\]", hint or "", re.S)
            if m:
                routes = [r for r in json.loads(m.group(0)) if r in self.ROUTES]
                if routes:
                    picked = routes
        except Exception:
            pass
        # If MANAGER genuinely can't decide, default to MUSE for creative,
        # SCHOLAR for anything else that reads like a question.
        if not picked:
            picked = ["scholar" if request.strip().endswith("?") else "muse"]
        # Order-stable dedupe
        seen: set[str] = set()
        ordered: list[str] = []
        for r in picked:
            if r not in seen:
                seen.add(r)
                ordered.append(r)
        return ordered


class WorkCrew:
    """Persona pod on top of the shared LLM client + HITL."""

    def __init__(
        self,
        settings: Any | None = None,
        *,
        hitl: Any | None = None,
        cloud: Any | None = None,
        research: Any | None = None,
        spend: Any | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.hitl = hitl
        self.on_progress = on_progress
        self.log = OutcomeLog()

        self.manager = ManagerAgent()
        self.scholar = ScholarAgent(settings=settings, research=research)
        self.stitch = StitchAgent()
        self.reel = ReelAgent(cloud=cloud)
        self.flip = FlipAgent()
        self.ledger = LedgerAgent(spend=spend, cloud=cloud)
        self.muse = MuseAgent()

    # ---- observability ------------------------------------------------

    def _progress(self, msg: str) -> None:
        print(f"[work_crew] {msg}")
        if self.on_progress:
            try:
                self.on_progress(msg)
            except Exception:
                pass

    def _record(self, outcome: WorkOutcome) -> WorkOutcome:
        self.log.append(outcome)
        return outcome

    def status(self) -> str:
        totals = self.log.totals()
        parts = [
            f"{a}:{totals.get(a, {}).get('xp', 0)}xp/{totals.get(a, {}).get('count', 0)}"
            for a in ("MANAGER", "SCHOLAR", "STITCH", "REEL", "FLIP", "LEDGER", "MUSE")
        ]
        return (
            f"Work Crew online — 7 specialists. Brain: {backend_name()}. "
            + " · ".join(parts)
        )

    # ---- main dispatch ------------------------------------------------

    def dispatch(self, request: str) -> str:
        """Route through MANAGER and return a spoken-friendly summary."""
        request = (request or "").strip()
        if not request:
            return "Work Crew stood down — nothing to do."

        routes = self.manager.plan(request)
        self._record(
            self.manager.outcome(
                kind="dispatch",
                ok=bool(routes),
                summary=f"routed → {', '.join(routes) or '(none)'}",
                xp=3 if routes else 0,
                meta={"routes": routes, "request": request[:200]},
            )
        )
        self._progress(f"MANAGER → {routes}")

        lines: list[str] = []
        for route in routes:
            outcome = self._dispatch_one(route, request)
            self._record(outcome)
            lines.append(f"[{outcome.agent}] {outcome.summary}")
        if not lines:
            return "Work Crew came back with nothing, sir."
        return "\n".join(lines)

    def _dispatch_one(self, route: str, request: str) -> WorkOutcome:
        try:
            if route == "scholar":
                return self.scholar.run(request)
            if route == "stitch":
                return self.stitch.draft_patch(request)
            if route == "reel":
                return self.reel.draft(request)
            if route == "flip":
                return self.flip.scout(request)
            if route == "ledger":
                return self.ledger.report_only(request)
            if route == "muse":
                return self.muse.brainstorm(request)
        except TradeExecutionRefused as e:
            return WorkOutcome(
                agent="LEDGER",
                kind="ledger_trade_refused",
                ok=False,
                summary=str(e),
                xp=0,
                hitl=True,
                meta={"request": request},
            )
        except Exception as e:  # noqa: BLE001
            return WorkOutcome(
                agent=route.upper(),
                kind="crash",
                ok=False,
                summary=f"{route} crashed: {e}",
                xp=0,
            )
        return WorkOutcome(
            agent="MANAGER",
            kind="unknown_route",
            ok=False,
            summary=f"MANAGER produced unknown route: {route}",
            xp=0,
        )

    # ---- convenience wrappers used by voice --------------------------

    def reel_publish(self, caption: str, media_url: str = "") -> str:
        outcome = self.reel.publish_tiktok(
            caption, media_url, hitl=self.hitl, settings=self.settings
        )
        self._record(outcome)
        return outcome.summary

    def stitch_push(self) -> str:
        outcome = self.stitch.push(hitl=self.hitl)
        self._record(outcome)
        return outcome.summary


# ---------------------------------------------------------------------------
# Invariant self-check — never removed. Imported at boot time via
# ``python -m jarvis.core.work_crew`` to prove LEDGER refuses trades.
# ---------------------------------------------------------------------------

def _ledger_never_trades() -> None:
    """Sanity check: LEDGER.execute_trade must raise :class:`TradeExecutionRefused`."""
    agent = LedgerAgent()
    try:
        agent.execute_trade("BTC", side="buy", qty=1)
    except TradeExecutionRefused:
        return
    raise AssertionError("LEDGER.execute_trade did not refuse — invariant broken.")


if __name__ == "__main__":  # pragma: no cover
    _ledger_never_trades()
    print("LEDGER invariant OK — trade execution refused.")

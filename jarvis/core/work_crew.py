"""Work Crew — Manager + Research + market outcome agents.

Agent 5 stack (user roster):
  MANAGER   — routes work, sets priorities, synthesizes outcome streams
  SCHOLAR+  — research that generates *new* actionable outcome ideas
  MARKET    — general market / trend scout
  STITCH    — Etsy t-shirt / merch designer briefs
  REEL      — TikTok poster plans for Etsy products
  FLIP      — eBay flip finder
  LEDGER    — stock / ticker research (NOT live trading execution)
  MUSE      — music maker briefs / track concepts

All LLM calls go through llm_client (Claude Code CLI preferred when enabled).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR
from jarvis.core.llm_client import complete

OUTCOMES_PATH = DATA_DIR / "work_outcomes.jsonl"
ROSTER_PATH = DATA_DIR / "work_crew_roster.json"

AGENT_TILES = (
    {
        "id": "manager",
        "name": "MANAGER",
        "title": "Work Director",
        "xp": 1,
        "color": "#00f0ff",
        "blurb": "Routes jobs, sets priorities, ships outcome streams",
    },
    {
        "id": "research",
        "name": "SCHOLAR",
        "title": "Research Scout",
        "xp": 1,
        "color": "#7cf0ff",
        "blurb": "Analyzes the web and invents new outcome ideas",
    },
    {
        "id": "market",
        "name": "MARKET",
        "title": "Market Agent",
        "xp": 1,
        "color": "#ffc14a",
        "blurb": "Trends, niches, demand signals",
    },
    {
        "id": "stitch",
        "name": "STITCH",
        "title": "Etsy Tee Designer",
        "xp": 1,
        "color": "#ff6bcb",
        "blurb": "T-shirt concepts, mock briefs, listing copy",
    },
    {
        "id": "reel",
        "name": "REEL",
        "title": "TikTok Poster",
        "xp": 1,
        "color": "#ff4fd8",
        "blurb": "Short-form scripts that push Etsy traffic",
    },
    {
        "id": "flip",
        "name": "FLIP",
        "title": "eBay Flip Finder",
        "xp": 1,
        "color": "#3dff9a",
        "blurb": "Arbitrage angles and flip checklists",
    },
    {
        "id": "ledger",
        "name": "LEDGER",
        "title": "Stock Scout",
        "xp": 1,
        "color": "#9eb7ff",
        "blurb": "Ticker research notes — never auto-trades",
    },
    {
        "id": "muse",
        "name": "MUSE",
        "title": "Music Maker",
        "xp": 1,
        "color": "#ffb089",
        "blurb": "Track concepts, hooks, production briefs",
    },
)


class WorkAgent:
    name = "AGENT"
    system = "You are a precise specialist inside Jarvis Work Crew."

    def __init__(self, settings: Any, research: Any | None = None) -> None:
        self.settings = settings
        self.research = research

    def run(self, brief: str) -> str:
        web = ""
        if self.research is not None:
            try:
                web = self.research.run(brief)[:5000]
            except Exception:
                web = ""
        prompt = (
            f"BRIEF:\n{brief}\n\n"
            f"LIVE RESEARCH (may be empty):\n{web or '(none)'}\n\n"
            "Deliver a concrete outcome stream: numbered actions, copy drafts, "
            "and next experiments. No fluff."
        )
        out = complete(prompt, system=self.system, max_tokens=1100, temperature=0.45)
        return out or web or f"{self.name} standing by — no LLM backend yet."


class ManagerAgent(WorkAgent):
    name = "MANAGER"
    system = (
        "You are MANAGER — Jarvis Work Director. You assign specialists, set "
        "priorities, and produce a crisp battle plan. Address outcomes as a "
        "stream the operator can execute today. Never invent live balances."
    )

    def run(self, brief: str) -> str:
        roster = ", ".join(a["name"] for a in AGENT_TILES)
        prompt = (
            f"OPERATOR BRIEF:\n{brief}\n\n"
            f"AVAILABLE AGENTS: {roster}\n\n"
            "1) Restate the goal in one line.\n"
            "2) Pick 2–4 agents and why.\n"
            "3) Ordered outcome stream (today / this week).\n"
            "4) Risks + HITL checkpoints."
        )
        out = complete(prompt, system=self.system, max_tokens=1000, temperature=0.35)
        return out or "MANAGER online — enable Claude Code CLI or an LLM backend."


class ResearchOutcomeAgent(WorkAgent):
    name = "SCHOLAR"
    system = (
        "You are SCHOLAR — Research Outcome Scout. Cross-check multiple sources "
        "(web, Wikipedia, HN, news RSS). Prefer concrete facts with dates. Then invent "
        "NEW outcome ideas (products, angles, content, tests). Every insight must "
        "end with a next action. Flag weak or single-source claims."
    )


class MarketAgent(WorkAgent):
    name = "MARKET"
    system = (
        "You are MARKET — niche and demand scout. Spot underserved markets, "
        "pricing bands, and 3 product angles with effort vs upside."
    )


class StitchAgent(WorkAgent):
    name = "STITCH"
    system = (
        "You are STITCH — Etsy t-shirt designer. Output: design concept, "
        "print-ready text ideas, mock listing title, tags, and price band. "
        "Keep designs printable and trademark-safe (no stolen IP)."
    )


class ReelAgent(WorkAgent):
    name = "REEL"
    system = (
        "You are REEL — TikTok poster for Etsy. Output 3 short scripts "
        "(hook / demo / CTA), on-screen text, sound vibe, and posting times."
    )


class FlipAgent(WorkAgent):
    name = "FLIP"
    system = (
        "You are FLIP — eBay flip finder. Suggest sourcing angles, comps checklist, "
        "fees, and risk flags. Never promise guaranteed profit."
    )


class LedgerAgent(WorkAgent):
    name = "LEDGER"
    system = (
        "You are LEDGER — stock research scout. Summarize thesis, catalysts, risks. "
        "You NEVER place trades. Always say this is not financial advice."
    )


class MuseAgent(WorkAgent):
    name = "MUSE"
    system = (
        "You are MUSE — music maker. Deliver song concept, BPM/key vibe, structure, "
        "lyric hook options, and a production checklist for DAW / ElevenLabs."
    )


class WorkCrew:
    """Manager-led work system for zero-code operators."""

    def __init__(
        self,
        settings: Any,
        *,
        research: Any | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.on_progress = on_progress
        self.manager = ManagerAgent(settings, research)
        self.agents: dict[str, WorkAgent] = {
            "manager": self.manager,
            "research": ResearchOutcomeAgent(settings, research),
            "market": MarketAgent(settings, research),
            "stitch": StitchAgent(settings, research),
            "reel": ReelAgent(settings, research),
            "flip": FlipAgent(settings, research),
            "ledger": LedgerAgent(settings, research),
            "muse": MuseAgent(settings, research),
        }
        self.last_run: dict[str, Any] = {}
        self._ensure_roster()

    def _emit(self, msg: str) -> None:
        if self.on_progress:
            try:
                self.on_progress(msg)
            except Exception:
                pass

    def _ensure_roster(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            if not ROSTER_PATH.exists():
                ROSTER_PATH.write_text(
                    json.dumps({"agents": AGENT_TILES, "updated": datetime.utcnow().isoformat()}, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass

    def status(self) -> str:
        from jarvis.core.anthropic_cli import status as cli_status

        names = ", ".join(a["name"] for a in AGENT_TILES)
        return (
            f"Work Crew online — {names}. "
            f"{cli_status()} "
            f"SCHOLAR fans out Wikipedia/HN/RSS + search APIs. "
            f"Outcomes log: {OUTCOMES_PATH.name}."
        )

    def refresh(self) -> str:
        """Rebind research helper + clear last_run."""
        if self.manager.research is not None and hasattr(self.manager.research, "refresh"):
            try:
                self.manager.research.refresh()
            except Exception:
                pass
        for ag in self.agents.values():
            if hasattr(ag, "research") and ag.research is not None:
                if hasattr(ag.research, "refresh"):
                    try:
                        ag.research.refresh()
                    except Exception:
                        pass
        self.last_run = {}
        return "Work Crew agents refreshed — live sources on next run."

    def roster(self) -> list[dict[str, Any]]:
        return list(AGENT_TILES)

    def _log_outcome(self, agent: str, brief: str, result: str) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "agent": agent,
                "brief": brief[:500],
                "result": result[:4000],
            }
            with OUTCOMES_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def run_agent(self, agent_id: str, brief: str) -> str:
        key = (agent_id or "manager").lower().strip()
        aliases = {
            "scholar": "research",
            "etsy": "stitch",
            "tshirt": "stitch",
            "tee": "stitch",
            "tiktok": "reel",
            "ebay": "flip",
            "stock": "ledger",
            "stocks": "ledger",
            "trader": "ledger",
            "music": "muse",
            "director": "manager",
        }
        key = aliases.get(key, key)
        agent = self.agents.get(key) or self.manager
        self._emit(f"{agent.name} engaged…")
        t0 = time.time()
        out = agent.run(brief)
        self._log_outcome(agent.name, brief, out)
        self.last_run = {
            "agent": agent.name,
            "brief": brief,
            "ms": int((time.time() - t0) * 1000),
            "chars": len(out or ""),
        }
        return out

    def dispatch(self, brief: str) -> str:
        """Manager plans, then runs research + best specialists, synthesizes."""
        brief = (brief or "").strip() or "Generate a profitable creative outcome stream for today."
        self._emit("MANAGER planning…")
        plan = self.manager.run(brief)
        # Heuristic pick from plan text + keywords
        picks = self._pick_from_brief(brief + "\n" + plan)
        findings: dict[str, str] = {"MANAGER": plan}
        for aid in picks:
            if aid == "manager":
                continue
            ag = self.agents.get(aid)
            if not ag:
                continue
            self._emit(f"{ag.name} running…")
            findings[ag.name] = ag.run(brief)
            self._log_outcome(ag.name, brief, findings[ag.name])
        blocks = "\n\n".join(f"[{k}]\n{v}" for k, v in findings.items())
        final = complete(
            f"OPERATOR BRIEF:\n{brief}\n\nAGENT OUTPUTS:\n{blocks}\n\n"
            "Synthesize one executable OUTCOME STREAM: numbered steps for today, "
            "assets to create, and what to measure. Address the user as sir.",
            system="You are JARVIS Work Director synthesizing a multi-agent run.",
            max_tokens=1200,
            temperature=0.35,
        )
        result = final or blocks
        self._log_outcome("SYNTHESIS", brief, result)
        self.last_run = {"agents": list(findings.keys()), "brief": brief}
        return result

    @staticmethod
    def _pick_from_brief(text: str) -> list[str]:
        t = text.lower()
        picks = ["research"]
        if re.search(r"\b(etsy|t-?shirt|merch|tee|print)\b", t):
            picks.append("stitch")
        if re.search(r"\b(tiktok|reel|short[- ]?form|viral)\b", t):
            picks.append("reel")
        if re.search(r"\b(ebay|flip|arbitrage|thrift)\b", t):
            picks.append("flip")
        if re.search(r"\b(stock|ticker|share|nasdaq|invest)\b", t):
            picks.append("ledger")
        if re.search(r"\b(music|song|beat|track|album)\b", t):
            picks.append("muse")
        if re.search(r"\b(market|niche|trend|demand)\b", t):
            picks.append("market")
        # Always include market when only research
        if picks == ["research"]:
            picks.append("market")
        # Dedupe preserve order
        seen = set()
        out = []
        for p in picks:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out[:4]

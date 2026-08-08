"""Jarvis AI Systems v2 — upgrade facade for coding / scrape / RAG stacks.

Bundles (optional deps degrade gracefully):
  · swe_bench_verify   — SWE-bench style local verify
  · cloud_agent_sdk    — Cursor Cloud / cursor-sdk bridge
  · langgraph_bridge   — LangGraph multi-agent graphs
  · openai_agents      — OpenAI Agents SDK + sandbox execution
  · mistweb            — Mistweb scrape + aggregation (+ Tick)
  · pydad              — Pydantic-AI structured extract (voice: "pydad")
  · agno_scrape        — Agno Type-C scrape workers
  · llamaindex_rag     — LlamaIndex Workflow 1.0 data-grounded RAG
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SystemProbe:
    key: str
    label: str
    ready: bool
    detail: str = ""
    version: str = "1.0"


@dataclass
class SystemsStatus:
    probes: list[SystemProbe] = field(default_factory=list)

    def summary(self) -> str:
        ready = [p.label for p in self.probes if p.ready]
        missing = [p.label for p in self.probes if not p.ready]
        bits = [f"AI Systems v2 · {len(ready)}/{len(self.probes)} online"]
        if ready:
            bits.append("ready: " + ", ".join(ready[:6]) + ("…" if len(ready) > 6 else ""))
        if missing:
            bits.append("standby: " + ", ".join(missing))
        return " · ".join(bits)


class SystemsAIv2:
    """Single entry for status + routed subsystem calls."""

    def __init__(
        self,
        *,
        settings=None,
        vstore=None,
        internet=None,
        llm_fn: Callable[[str], str] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.vstore = vstore
        self.internet = internet
        self.llm_fn = llm_fn
        self.on_status = on_status or (lambda _s: None)
        self._lock = threading.RLock()

        from jarvis.core.swe_bench_verify import SweBenchVerify
        from jarvis.core.cloud_agent_sdk import CloudAgentSDK
        from jarvis.core.langgraph_bridge import LangGraphBridge
        from jarvis.core.openai_agents_bridge import OpenAIAgentsBridge
        from jarvis.core.mistweb_scrape import MistwebAggregator
        from jarvis.core.agno_scrape_worker import AgnoScrapeWorker
        from jarvis.core.llamaindex_rag import LlamaIndexRAG
        from jarvis.core.pydad_extract import PydadExtractor

        self.swe = SweBenchVerify(settings=settings)
        self.cloud = CloudAgentSDK(settings=settings)
        self.langgraph = LangGraphBridge(settings=settings, llm_fn=llm_fn)
        self.openai_agents = OpenAIAgentsBridge(settings=settings, llm_fn=llm_fn)
        self.mistweb = MistwebAggregator(settings=settings, internet=internet)
        self.pydad = PydadExtractor(settings=settings, llm_fn=llm_fn)
        self.agno = AgnoScrapeWorker(settings=settings, internet=internet, mistweb=self.mistweb)
        self.rag = LlamaIndexRAG(settings=settings, vstore=vstore, llm_fn=llm_fn)

        if getattr(settings, "systems_tick_autostart", False):
            try:
                self.mistweb.tick_start()
            except Exception:
                pass

    def probe(self) -> SystemsStatus:
        def _p(key: str, label: str, fn) -> SystemProbe:
            try:
                t = fn()
                ready = bool(t[0]) if t else False
                detail = str(t[1]) if t and len(t) > 1 else ""
            except Exception as e:
                ready, detail = False, str(e)
            return SystemProbe(key=key, label=label, ready=ready, detail=detail)

        probes = [
            _p("swe_bench", "SWE-bench Verify", self.swe.probe),
            _p("cloud_agent", "Cloud Agent SDK", self.cloud.probe),
            _p("langgraph", "LangGraph", self.langgraph.probe),
            _p("openai_agents", "OpenAI Agents + Sandbox", self.openai_agents.probe),
            _p("mistweb", "Mistweb Scrape/Agg", self.mistweb.probe),
            _p("pydad", "Pydad (Pydantic-AI)", self.pydad.probe),
            _p("agno", "Agno Type-C Scrape", self.agno.probe),
            _p("llamaindex", "LlamaIndex Workflow RAG", self.rag.probe),
            _p("tick", "Tick Scrape Scheduler", self.mistweb.tick_probe),
        ]
        return SystemsStatus(probes=probes)

    def status(self) -> str:
        st = self.probe()
        lines = [st.summary()]
        for p in st.probes:
            mark = "ON " if p.ready else "OFF"
            extra = f" — {p.detail}" if p.detail else ""
            lines.append(f"  [{mark}] {p.label}{extra}")
        return "\n".join(lines)

    def upgrade_message(self) -> str:
        return (
            "AI Systems v2 engaged. "
            "SWE-bench verify, Cloud Agent SDK, LangGraph, OpenAI Agents sandbox, "
            "Mistweb + Tick aggregation, Pydad extract, Agno Type-C scrape, "
            "and LlamaIndex Workflow RAG are registered. "
            "Say 'systems status' or install extras via requirements-systems.txt."
        )

    # ── routed helpers ──────────────────────────────────────────────────

    def mist_scrape(self, query: str, *, max_pages: int = 5) -> str:
        items = self.mistweb.scrape(query, max_pages=max_pages)
        if not items:
            return "Mistweb found nothing."
        blob = self.mistweb.aggregate_text(items)
        try:
            extracted = self.pydad.extract(blob, schema_hint="web scrap")
            return (
                f"Mistweb · {len(items)} sources · engine={extracted.engine}\n"
                f"{extracted.summary}\n\n{blob[:2500]}"
            )
        except Exception:
            return f"Mistweb · {len(items)} sources\n{blob[:3000]}"

    def rag_ask(self, question: str) -> str:
        r = self.rag.query(question)
        return str(r.get("answer") or r.get("error") or r)

    def graph_run(self, goal: str) -> str:
        r = self.langgraph.run(goal)
        return str(r.get("result") or r.get("plan") or r)

    def agents_run(self, prompt: str) -> str:
        r = self.openai_agents.run_agent(prompt)
        return str(r.get("result") or r.get("stdout") or r.get("error") or r)

    def swe_verify_code(self, code: str, test_code: str | None = None, *, task_id: str = "local") -> str:
        vr = self.swe.verify(task_id=task_id, code=code, test_code=test_code)
        return vr.summary()

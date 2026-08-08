"""Agno Type-C scrape workers — parallel scrap workers for Jarvis."""

from __future__ import annotations

import concurrent.futures
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from jarvis.core.mistweb_scrape import MistwebAggregator, ScrapeItem


@dataclass
class WorkerResult:
    worker_id: str
    query: str
    items: list[ScrapeItem] = field(default_factory=list)
    ok: bool = True
    error: str = ""
    engine: str = "type_c"


class AgnoScrapeWorker:
    """Type-C scrape worker pool.

    When `agno` is installed, wraps Agno Agent tools for scrape.
    Otherwise runs a thread-pool of Mistweb fetches (Type-C = concurrent crawl).
    """

    def __init__(
        self,
        *,
        settings=None,
        internet=None,
        mistweb: MistwebAggregator | None = None,
        max_workers: int = 4,
    ) -> None:
        self.settings = settings
        self.internet = internet
        self.mistweb = mistweb or MistwebAggregator(settings=settings, internet=internet)
        self.max_workers = max(1, int(getattr(settings, "agno_scrape_workers", max_workers) or max_workers))
        self._lock = threading.RLock()
        self._last: list[WorkerResult] = []

    def probe(self) -> tuple[bool, str]:
        try:
            import agno  # noqa: F401

            return True, f"agno + Type-C pool x{self.max_workers}"
        except ImportError:
            return True, f"Type-C pool x{self.max_workers} (pip install agno)"

    def status(self) -> str:
        ok, detail = self.probe()
        return f"Agno Type-C: {detail}"

    def scrape(self, queries: list[str] | str, *, max_pages: int = 3) -> list[WorkerResult]:
        if isinstance(queries, str):
            queries = [queries]
        queries = [q.strip() for q in queries if q and str(q).strip()]
        if not queries:
            return []

        # Prefer agno agent path for single query when available
        if len(queries) == 1:
            try:
                r = self._agno_one(queries[0], max_pages=max_pages)
                if r:
                    self._last = [r]
                    return self._last
            except Exception:
                pass

        results: list[WorkerResult] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {
                ex.submit(self._worker, f"c{i}", q, max_pages): q
                for i, q in enumerate(queries, 1)
            }
            for fut in concurrent.futures.as_completed(futs):
                results.append(fut.result())
        results.sort(key=lambda r: r.worker_id)
        self._last = results
        return results

    def flatten(self, results: list[WorkerResult] | None = None) -> list[ScrapeItem]:
        results = results if results is not None else self._last
        out: list[ScrapeItem] = []
        seen: set[str] = set()
        for r in results:
            for it in r.items:
                if it.url and it.url not in seen:
                    seen.add(it.url)
                    out.append(it)
        return out

    def _worker(self, wid: str, query: str, max_pages: int) -> WorkerResult:
        try:
            items = self.mistweb.scrape(query, max_pages=max_pages)
            return WorkerResult(worker_id=wid, query=query, items=items, ok=True, engine="type_c")
        except Exception as e:
            return WorkerResult(worker_id=wid, query=query, ok=False, error=str(e), engine="type_c")

    def _agno_one(self, query: str, *, max_pages: int) -> WorkerResult | None:
        from agno.agent import Agent

        # Use mistweb as the real fetcher; Agno orchestrates if Team/Agent available
        def tool_scrape(q: str) -> str:
            items = self.mistweb.scrape(q, max_pages=max_pages)
            return self.mistweb.aggregate_text(items)

        try:
            agent = Agent(
                name="JarvisTypeC",
                tools=[tool_scrape],
                description="Type-C scrape worker for Jarvis Mistweb aggregation.",
                markdown=True,
            )
            # Many agno versions: agent.run(prompt)
            if hasattr(agent, "run"):
                _ = agent.run(f"Scrape and summarize: {query}")
        except Exception:
            # Still return mistweb results even if agent chat fails
            pass

        items = self.mistweb.scrape(query, max_pages=max_pages)
        return WorkerResult(
            worker_id="agno1",
            query=query,
            items=items,
            ok=True,
            engine="agno+type_c",
        )

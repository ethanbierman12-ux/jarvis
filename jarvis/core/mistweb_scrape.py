"""Mistweb — multi-source scrape aggregation + Tick scheduler."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


@dataclass
class ScrapeItem:
    url: str
    title: str = ""
    text: str = ""
    source: str = "mistweb"
    fetched_at: str = ""
    score: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TickJob:
    job_id: str
    query: str
    interval_s: float = 3600.0
    enabled: bool = True
    last_run: float = 0.0
    last_count: int = 0


class MistwebAggregator:
    """Best-path scrape aggregator for Jarvis scraps.

    Sources (best-effort):
      · DuckDuckGo HTML / internet.search
      · Direct URL fetch (httpx/requests)
      · Optional Tavily if JARVIS/TAVILY key present
    Persist under jarvis/data/mistweb/
    Tick: background re-scrape scheduler.
    """

    def __init__(self, *, settings=None, internet=None) -> None:
        self.settings = settings
        self.internet = internet
        root = Path(__file__).resolve().parents[1] / "data" / "mistweb"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self._jobs: dict[str, TickJob] = {}
        self._tick_thread: threading.Thread | None = None
        self._tick_stop = threading.Event()
        self._lock = threading.RLock()
        self._load_jobs()

    def probe(self) -> tuple[bool, str]:
        engines = ["httpx/requests"]
        if self.internet is not None:
            engines.append("internet")
        try:
            import bs4  # noqa: F401

            engines.append("bs4")
        except ImportError:
            pass
        return True, " + ".join(engines)

    def tick_probe(self) -> tuple[bool, str]:
        n = len([j for j in self._jobs.values() if j.enabled])
        running = self._tick_thread is not None and self._tick_thread.is_alive()
        return True, f"{n} jobs · tick={'on' if running else 'off'}"

    def status(self) -> str:
        ok, detail = self.probe()
        tok, tdetail = self.tick_probe()
        return f"Mistweb: {detail} · Tick: {tdetail}"

    # ── scrape ──────────────────────────────────────────────────────────

    def scrape(self, query_or_url: str, *, max_pages: int = 5) -> list[ScrapeItem]:
        q = (query_or_url or "").strip()
        if not q:
            return []
        if self._looks_url(q):
            item = self.fetch_url(q)
            items = [item] if item else []
        else:
            items = self.search_aggregate(q, max_pages=max_pages)
        self._persist(q, items)
        return items

    def search_aggregate(self, query: str, *, max_pages: int = 5) -> list[ScrapeItem]:
        items: list[ScrapeItem] = []
        seen: set[str] = set()

        # 1) Jarvis internet module
        if self.internet is not None:
            try:
                results = []
                if hasattr(self.internet, "search"):
                    results = self.internet.search(query) or []
                elif hasattr(self.internet, "web_search"):
                    results = self.internet.web_search(query) or []
                for r in results[:max_pages]:
                    if isinstance(r, dict):
                        url = r.get("href") or r.get("url") or r.get("link") or ""
                        title = r.get("title") or r.get("name") or ""
                        body = r.get("body") or r.get("snippet") or r.get("text") or ""
                    else:
                        url = getattr(r, "href", "") or getattr(r, "url", "")
                        title = getattr(r, "title", "")
                        body = getattr(r, "body", "") or getattr(r, "snippet", "")
                    if url and url not in seen:
                        seen.add(url)
                        items.append(
                            ScrapeItem(
                                url=url,
                                title=str(title)[:200],
                                text=str(body)[:2000],
                                source="internet",
                                fetched_at=_now(),
                                score=0.7,
                            )
                        )
            except Exception:
                pass

        # 2) DuckDuckGo lite HTML
        if len(items) < max_pages:
            for it in self._ddg_html(query, limit=max_pages - len(items)):
                if it.url not in seen:
                    seen.add(it.url)
                    items.append(it)

        # 3) Enrich top URLs with page text
        enriched: list[ScrapeItem] = []
        for it in items[:max_pages]:
            if len(it.text) < 80 and it.url:
                full = self.fetch_url(it.url)
                if full and full.text:
                    it.text = full.text[:4000]
                    it.title = it.title or full.title
                    it.source = f"{it.source}+fetch"
            enriched.append(it)
        return enriched

    def fetch_url(self, url: str) -> ScrapeItem | None:
        url = (url or "").strip()
        if not url:
            return None
        if not url.startswith("http"):
            url = "https://" + url
        html = self._http_get(url)
        if not html:
            return None
        title, text = self._extract(html)
        return ScrapeItem(
            url=url,
            title=title[:200],
            text=text[:6000],
            source="mistweb_fetch",
            fetched_at=_now(),
            score=0.9,
        )

    def aggregate_text(self, items: list[ScrapeItem], *, limit: int = 8000) -> str:
        chunks = []
        for i, it in enumerate(items, 1):
            chunks.append(f"### [{i}] {it.title or it.url}\nURL: {it.url}\n{it.text[:1500]}\n")
        blob = "\n".join(chunks)
        return blob[:limit]

    # ── Tick scheduler ──────────────────────────────────────────────────

    def tick_add(self, query: str, *, interval_s: float = 3600.0, job_id: str | None = None) -> TickJob:
        q = (query or "").strip()
        jid = job_id or hashlib.sha1(q.encode()).hexdigest()[:10]
        job = TickJob(job_id=jid, query=q, interval_s=max(60.0, float(interval_s)), enabled=True)
        with self._lock:
            self._jobs[jid] = job
            self._save_jobs()
        self.tick_start()
        return job

    def tick_remove(self, job_id: str) -> bool:
        with self._lock:
            ok = self._jobs.pop(job_id, None) is not None
            self._save_jobs()
            return ok

    def tick_list(self) -> list[TickJob]:
        return list(self._jobs.values())

    def tick_start(self) -> None:
        if self._tick_thread and self._tick_thread.is_alive():
            return
        self._tick_stop.clear()
        self._tick_thread = threading.Thread(target=self._tick_loop, name="mistweb-tick", daemon=True)
        self._tick_thread.start()

    def tick_stop(self) -> None:
        self._tick_stop.set()

    def _tick_loop(self) -> None:
        while not self._tick_stop.is_set():
            now = time.time()
            with self._lock:
                jobs = list(self._jobs.values())
            for job in jobs:
                if not job.enabled:
                    continue
                if now - job.last_run < job.interval_s:
                    continue
                try:
                    items = self.scrape(job.query, max_pages=5)
                    job.last_run = time.time()
                    job.last_count = len(items)
                    with self._lock:
                        self._jobs[job.job_id] = job
                        self._save_jobs()
                except Exception:
                    pass
            self._tick_stop.wait(30.0)

    # ── helpers ─────────────────────────────────────────────────────────

    def _persist(self, key: str, items: list[ScrapeItem]) -> None:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", key)[:60] or "scrape"
        path = self.root / f"{slug}_{int(time.time())}.json"
        try:
            path.write_text(
                json.dumps([asdict(i) for i in items], indent=2),
                encoding="utf-8",
            )
            latest = self.root / "latest.json"
            latest.write_text(
                json.dumps({"query": key, "count": len(items), "items": [asdict(i) for i in items]}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_jobs(self) -> None:
        path = self.root / "tick_jobs.json"
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for row in raw:
                job = TickJob(**{k: row[k] for k in TickJob.__dataclass_fields__ if k in row})
                self._jobs[job.job_id] = job
        except Exception:
            pass

    def _save_jobs(self) -> None:
        path = self.root / "tick_jobs.json"
        try:
            path.write_text(
                json.dumps([asdict(j) for j in self._jobs.values()], indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _looks_url(s: str) -> bool:
        if s.startswith("http://") or s.startswith("https://"):
            return True
        if "." in s and " " not in s and urlparse("https://" + s).netloc:
            return True
        return False

    def _http_get(self, url: str, timeout: float = 20.0) -> str:
        headers = {"User-Agent": "JarvisMistweb/1.0 (+local)"}
        try:
            import httpx

            r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
            if r.status_code < 400:
                return r.text
        except Exception:
            pass
        try:
            import requests

            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code < 400:
                return r.text
        except Exception:
            pass
        return ""

    def _ddg_html(self, query: str, *, limit: int = 5) -> list[ScrapeItem]:
        url = f"https://html.duckduckgo.com/html/?q={_q(query)}"
        html = self._http_get(url)
        if not html:
            return []
        items: list[ScrapeItem] = []
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for res in soup.select(".result")[:limit]:
                a = res.select_one("a.result__a")
                sn = res.select_one(".result__snippet")
                if not a:
                    continue
                href = a.get("href") or ""
                items.append(
                    ScrapeItem(
                        url=href,
                        title=a.get_text(" ", strip=True)[:200],
                        text=(sn.get_text(" ", strip=True) if sn else "")[:2000],
                        source="ddg",
                        fetched_at=_now(),
                        score=0.6,
                    )
                )
        except Exception:
            # regex fallback
            for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)', html):
                items.append(
                    ScrapeItem(
                        url=m.group(1),
                        title=m.group(2)[:200],
                        source="ddg",
                        fetched_at=_now(),
                        score=0.5,
                    )
                )
                if len(items) >= limit:
                    break
        return items

    @staticmethod
    def _extract(html: str) -> tuple[str, str]:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            title = (soup.title.get_text(strip=True) if soup.title else "") or ""
            text = soup.get_text("\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return title, text
        except Exception:
            title_m = re.search(r"<title[^>]*>([^<]+)", html, re.I)
            title = title_m.group(1).strip() if title_m else ""
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return title, text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _q(s: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(s)

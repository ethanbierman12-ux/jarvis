"""Topic watchers — RSS headlines for tech / gaming / marketing."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_FEEDS = {
    "tech": "https://feeds.feedburner.com/TechCrunch",
    "gaming": "https://www.ign.com/rss/articles/feed",
    "marketing": "https://www.marketingbrew.com/feed",
}


class TopicMonitor:
    def __init__(self, feeds: dict[str, str] | None = None) -> None:
        self.feeds = dict(feeds or DEFAULT_FEEDS)
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def _fetch(self, url: str, limit: int = 5) -> list[dict[str, Any]]:
        req = Request(url, headers={"User-Agent": "JarvisTopicMonitor/1.0"})
        with urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = []
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title:
                items.append({"title": title, "link": link})
        if not items:
            for item in root.findall(".//{http://www.w3.org/2005/Atom}entry")[:limit]:
                title = (item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                link = link_el.get("href") if link_el is not None else ""
                if title:
                    items.append({"title": title, "link": link or ""})
        return items

    def headlines(self, topic: str = "tech", *, limit: int = 4) -> str:
        key = (topic or "tech").lower().strip()
        # soft match
        if key not in self.feeds:
            for k in self.feeds:
                if k in key or key in k:
                    key = k
                    break
        url = self.feeds.get(key)
        if not url:
            return f"No feed for {topic}. Try tech, gaming, or marketing."
        now = time.time()
        cached = self._cache.get(key)
        if cached and now - cached[0] < 300:
            items = cached[1][:limit]
        else:
            try:
                items = self._fetch(url, limit=limit)
                self._cache[key] = (now, items)
            except Exception as e:
                return f"Couldn't reach {key} feed: {e}"
        if not items:
            return f"No headlines in {key}."
        tops = "; ".join(f"{i+1}. {it['title'][:90]}" for i, it in enumerate(items[:limit]))
        return f"{key.title()} pulse — {tops}."

    def latest_blurb(self) -> str:
        """One-liner for grid / horizon scanners."""
        return self.headlines("tech", limit=2)

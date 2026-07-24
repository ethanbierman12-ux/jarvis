"""Price drop monitor — track product URLs and alert on change."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen


class PriceMonitor:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "price_watch.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._items = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._items = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._items, indent=2), encoding="utf-8")

    def _scrape_price(self, url: str) -> float | None:
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; JarvisPriceWatch/1.0)",
                    "Accept-Language": "en",
                },
            )
            with urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            # Common JSON-LD / meta patterns
            for pat in (
                r'"price"\s*:\s*"?(?P<p>\d+(?:\.\d+)?)"?',
                r'itemprop="price"\s+content="(?P<p>\d+(?:\.\d+)?)"',
                r'property="product:price:amount"\s+content="(?P<p>\d+(?:\.\d+)?)"',
                r"\$\s?(?P<p>\d{1,5}(?:\.\d{2})?)",
            ):
                m = re.search(pat, html, re.I)
                if m:
                    return float(m.group("p"))
        except Exception:
            return None
        return None

    def watch(self, name: str, url: str) -> str:
        name = (name or "item").strip()[:60]
        price = self._scrape_price(url)
        self._items[name] = {
            "url": url,
            "last_price": price,
            "best_price": price,
            "updated": time.time(),
        }
        self._save()
        if price is None:
            return f"Watching {name}, but I couldn't read a price yet — I'll keep probing."
        return f"Watching {name} at ${price:.2f}."

    def check(self) -> str:
        if not self._items:
            return "No products on watch. Say watch price for NAME at URL."
        alerts = []
        for name, meta in list(self._items.items()):
            price = self._scrape_price(meta["url"])
            if price is None:
                continue
            last = meta.get("last_price")
            best = meta.get("best_price")
            meta["last_price"] = price
            meta["updated"] = time.time()
            if best is None or price < float(best):
                meta["best_price"] = price
            if last is not None and price < float(last) - 0.01:
                alerts.append(f"{name} dropped to ${price:.2f} (was ${float(last):.2f})")
            self._items[name] = meta
        self._save()
        if alerts:
            return "Price alert — " + "; ".join(alerts) + "."
        return "No drops detected on your watchlist."

    def status(self) -> str:
        if not self._items:
            return "Price watchlist empty."
        bits = []
        for name, meta in self._items.items():
            p = meta.get("last_price")
            bits.append(f"{name}: {'$' + f'{p:.2f}' if p is not None else 'unknown'}")
        return "Watching — " + "; ".join(bits) + "."

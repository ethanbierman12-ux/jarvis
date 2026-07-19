"""Business finder — local places via OpenStreetMap (no Google Maps needed)."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

RESULTS_PATH = DATA_DIR / "business_results.json"
LAST_PATH = DATA_DIR / "last_businesses.html"

# Common amenity / shop tags for Overpass
_KIND_MAP = {
    "coffee": 'amenity=cafe',
    "cafe": 'amenity=cafe',
    "cafes": 'amenity=cafe',
    "restaurant": 'amenity=restaurant',
    "restaurants": 'amenity=restaurant',
    "food": 'amenity=restaurant',
    "bar": 'amenity=bar',
    "bars": 'amenity=bar',
    "pub": 'amenity=pub',
    "pizza": 'amenity=restaurant',
    "pharmacy": 'amenity=pharmacy',
    "hospital": 'amenity=hospital',
    "doctor": 'amenity=doctors',
    "dentist": 'amenity=dentist',
    "gym": 'leisure=fitness_centre',
    "fitness": 'leisure=fitness_centre',
    "hotel": 'tourism=hotel',
    "hotels": 'tourism=hotel',
    "bank": 'amenity=bank',
    "atm": 'amenity=atm',
    "gas": 'amenity=fuel',
    "fuel": 'amenity=fuel',
    "parking": 'amenity=parking',
    "grocery": 'shop=supermarket',
    "supermarket": 'shop=supermarket',
    "store": 'shop=convenience',
    "shop": 'shop=convenience',
    "bakery": 'shop=bakery',
    "hair": 'shop=hairdresser',
    "barber": 'shop=hairdresser',
    "salon": 'shop=beauty',
    "beauty": 'shop=beauty',
    "plumber": 'craft=plumber',
    "electrician": 'craft=electrician',
    "lawyer": 'office=lawyer',
    "attorney": 'office=lawyer',
    "accountant": 'office=accountant',
    "real estate": 'office=estate_agent',
    "mechanic": 'shop=car_repair',
    "auto": 'shop=car_repair',
    "laundry": 'shop=laundry',
    "florist": 'shop=florist',
    "bookstore": 'shop=books',
    "library": 'amenity=library',
    "park": 'leisure=park',
    "museum": 'tourism=museum',
    "school": 'amenity=school',
}


class BusinessFinder:
    def __init__(self, city: str = "Philadelphia") -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.city = city or "Philadelphia"
        self.last_results: list[dict[str, Any]] = []
        self.last_query = ""

    def find(self, query: str, *, city: str | None = None, limit: int = 8) -> str:
        """
        Find businesses from a natural phrase:
          'coffee near me', 'plumbers in Philadelphia', 'best pizza'
        """
        q = (query or "").strip()
        if not q:
            return "What kind of business should I find?"

        place = city or self._extract_city(q) or self.city
        kind, keywords = self._parse_kind(q)
        self.last_query = q

        # Geocode city center
        center = self._geocode(place)
        if not center:
            return f"I could not locate {place}. Try a clearer city name."

        lat, lon = center["lat"], center["lon"]
        results = self._overpass_search(lat, lon, kind=kind, keywords=keywords, limit=limit)
        if not results:
            # Fallback: Nominatim text search
            results = self._nominatim_search(f"{keywords or kind} {place}", limit=limit)

        if not results:
            return (
                f"I found no matches for '{q}' around {place}. "
                f"Try a broader category like restaurants or coffee."
            )

        self.last_results = results
        self._save(results, place=place, query=q)
        self._write_html(results, place=place, query=q)

        lines = [f"I found {len(results)} options near {place} — no Maps required."]
        for i, r in enumerate(results[:6], 1):
            bits = [f"{i}. {r['name']}"]
            if r.get("category"):
                bits.append(f"({r['category']})")
            if r.get("address"):
                bits.append(f"— {r['address']}")
            if r.get("phone"):
                bits.append(f"· {r['phone']}")
            if r.get("website"):
                bits.append("· has website")
            else:
                bits.append("· no website yet")
            lines.append(" ".join(bits))
        lines.append(
            "Say 'build a website for number 2' or 'open business results' to continue."
        )
        return " ".join(lines)

    def get(self, index: int) -> dict[str, Any] | None:
        if not self.last_results:
            self._load()
        if 1 <= index <= len(self.last_results):
            return self.last_results[index - 1]
        return None

    def speak_top(self, n: int = 3) -> str:
        if not self.last_results:
            self._load()
        if not self.last_results:
            return "No recent business search. Say find coffee near me."
        bits = []
        for i, r in enumerate(self.last_results[:n], 1):
            bits.append(f"{i}. {r.get('name')} at {r.get('address') or 'unknown address'}")
        return "Top results: " + "; ".join(bits) + "."

    def results_html_path(self) -> Path:
        return LAST_PATH

    # ── parsing ─────────────────────────────────────────────────
    def _extract_city(self, q: str) -> str | None:
        m = re.search(
            r"\b(?:in|near|around|at)\s+([A-Za-z][A-Za-z\s\.\-]{2,40})$",
            q.strip(),
            re.I,
        )
        if m:
            city = m.group(1).strip()
            city = re.sub(r"\b(me|here|my area)\b", "", city, flags=re.I).strip(" ,.")
            return city or None
        return None

    def _parse_kind(self, q: str) -> tuple[str, str]:
        t = q.lower()
        t = re.sub(
            r"\b(find|search|look up|locate|nearby|near me|close by|best|good|"
            r"in|near|around|at|for me|please|a|an|the|some)\b",
            " ",
            t,
        )
        t = re.sub(r"\s+", " ", t).strip()
        for key, tag in sorted(_KIND_MAP.items(), key=lambda kv: -len(kv[0])):
            if key in t:
                return tag, key
        # Generic shop search using remaining words
        words = [w for w in t.split() if len(w) > 2][:4]
        return "", " ".join(words) if words else "shop"

    # ── geocode + search ────────────────────────────────────────
    def _geocode(self, place: str) -> dict[str, float] | None:
        try:
            url = (
                "https://nominatim.openstreetmap.org/search?"
                + urllib.parse.urlencode(
                    {"q": place, "format": "json", "limit": 1}
                )
            )
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "JarvisBusinessFinder/1.0"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not data:
                return None
            return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
        except Exception as e:
            print(f"[biz] geocode failed: {e}")
            return None

    def _overpass_search(
        self,
        lat: float,
        lon: float,
        *,
        kind: str,
        keywords: str,
        limit: int,
        radius_m: int = 4500,
    ) -> list[dict[str, Any]]:
        try:
            if kind and "=" in kind:
                k, v = kind.split("=", 1)
                filt = f'node["{k}"="{v}"](around:{radius_m},{lat},{lon});\n'
                filt += f'way["{k}"="{v}"](around:{radius_m},{lat},{lon});'
            else:
                # Keyword name search
                kw = (keywords or "shop").replace('"', "")
                filt = (
                    f'node["name"~"{kw}",i](around:{radius_m},{lat},{lon});\n'
                    f'way["name"~"{kw}",i](around:{radius_m},{lat},{lon});'
                )
            query = f"[out:json][timeout:25];({filt});out center tags {limit};"
            req = urllib.request.Request(
                "https://overpass-api.de/api/interpreter",
                data=query.encode("utf-8"),
                headers={
                    "User-Agent": "JarvisBusinessFinder/1.0",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out: list[dict[str, Any]] = []
            seen = set()
            for el in data.get("elements") or []:
                tags = el.get("tags") or {}
                name = (tags.get("name") or "").strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                lat_e = el.get("lat") or (el.get("center") or {}).get("lat")
                lon_e = el.get("lon") or (el.get("center") or {}).get("lon")
                out.append(
                    {
                        "name": name,
                        "category": self._category_from_tags(tags),
                        "address": self._address_from_tags(tags),
                        "phone": tags.get("phone") or tags.get("contact:phone") or "",
                        "website": tags.get("website")
                        or tags.get("contact:website")
                        or "",
                        "lat": lat_e,
                        "lon": lon_e,
                        "osm_id": el.get("id"),
                        "hours": tags.get("opening_hours") or "",
                    }
                )
                if len(out) >= limit:
                    break
            return out
        except Exception as e:
            print(f"[biz] overpass failed: {e}")
            return []

    def _nominatim_search(self, q: str, limit: int = 8) -> list[dict[str, Any]]:
        try:
            url = (
                "https://nominatim.openstreetmap.org/search?"
                + urllib.parse.urlencode(
                    {
                        "q": q,
                        "format": "json",
                        "limit": limit,
                        "addressdetails": 1,
                        "extratags": 1,
                    }
                )
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "JarvisBusinessFinder/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out = []
            for row in data or []:
                addr = row.get("address") or {}
                out.append(
                    {
                        "name": (row.get("display_name") or "").split(",")[0],
                        "category": row.get("type") or row.get("class") or "",
                        "address": row.get("display_name") or "",
                        "phone": (row.get("extratags") or {}).get("phone") or "",
                        "website": (row.get("extratags") or {}).get("website") or "",
                        "lat": float(row.get("lat") or 0),
                        "lon": float(row.get("lon") or 0),
                        "osm_id": row.get("osm_id"),
                        "hours": "",
                        "city": addr.get("city") or addr.get("town") or "",
                    }
                )
            return out
        except Exception as e:
            print(f"[biz] nominatim search failed: {e}")
            return []

    def _category_from_tags(self, tags: dict) -> str:
        for key in ("amenity", "shop", "craft", "office", "tourism", "leisure"):
            if tags.get(key):
                return str(tags[key]).replace("_", " ")
        return "business"

    def _address_from_tags(self, tags: dict) -> str:
        parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:city"),
            tags.get("addr:state"),
        ]
        return ", ".join(p for p in parts if p) or tags.get("addr:full") or ""

    def _save(self, results: list[dict], *, place: str, query: str) -> None:
        payload = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "query": query,
            "place": place,
            "results": results,
        }
        RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self) -> None:
        try:
            raw = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
            self.last_results = list(raw.get("results") or [])
            self.last_query = raw.get("query") or ""
        except Exception:
            self.last_results = []

    def _write_html(self, results: list[dict], *, place: str, query: str) -> None:
        rows = []
        for i, r in enumerate(results, 1):
            web = r.get("website") or ""
            web_html = (
                f'<a href="{web}" target="_blank">Website</a>' if web else "<em>No site</em>"
            )
            rows.append(
                f"<tr><td>{i}</td><td><strong>{_esc(r.get('name'))}</strong><br>"
                f"<span class='cat'>{_esc(r.get('category'))}</span></td>"
                f"<td>{_esc(r.get('address'))}</td>"
                f"<td>{_esc(r.get('phone'))}</td><td>{web_html}</td></tr>"
            )
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Jarvis · Businesses</title>
<style>
body{{margin:0;font-family:Bahnschrift,Segoe UI,sans-serif;background:#02050a;color:#eaf6ff;}}
header{{padding:28px 32px;border-bottom:1px solid rgba(0,232,255,.35);}}
h1{{margin:0;letter-spacing:6px;color:#00e8ff;font-size:22px;}}
p{{color:#8aa4b8;}}
table{{width:100%;border-collapse:collapse;margin:20px 32px;width:calc(100% - 64px);}}
th,td{{text-align:left;padding:14px 12px;border-bottom:1px solid rgba(0,232,255,.15);vertical-align:top;}}
th{{color:#00e8ff;letter-spacing:2px;font-size:11px;}}
.cat{{color:#5a7388;font-size:12px;text-transform:uppercase;letter-spacing:1px;}}
a{{color:#6ec8ff;}}
</style></head><body>
<header><h1>JARVIS · BUSINESS FINDER</h1>
<p>Query: {_esc(query)} · Near {_esc(place)} · {len(results)} results · OpenStreetMap data</p></header>
<table><thead><tr><th>#</th><th>NAME</th><th>ADDRESS</th><th>PHONE</th><th>WEB</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""
        LAST_PATH.write_text(html, encoding="utf-8")


def _esc(s: Any) -> str:
    t = str(s or "")
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

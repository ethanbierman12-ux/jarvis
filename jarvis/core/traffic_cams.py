"""Public traffic cameras — official state DOT / 511 feeds only.

Regions: Philadelphia (511PA), Miami / Florida (FL511), NYC (NYC DOT
webcams), World (curated mix). Stills are public JPEG proxies; HLS often
requires auth — use the official 511 map embed for live video.

Soft-fails per region. Never scrapes private/residential cams, alley feeds,
face match, or ALPR.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


# ── Region constants ──────────────────────────────────────────────
REGION_PHL = "philadelphia"
REGION_MIA = "miami"
REGION_FL = "florida"
REGION_NYC = "nyc"
REGION_WORLD = "world"

_REGION_ALIASES = {
    "philadelphia": REGION_PHL,
    "philly": REGION_PHL,
    "phl": REGION_PHL,
    "pa": REGION_PHL,
    "511pa": REGION_PHL,
    "miami": REGION_MIA,
    "mia": REGION_MIA,
    "florida": REGION_FL,
    "fl": REGION_FL,
    "fl511": REGION_FL,
    "nyc": REGION_NYC,
    "new york": REGION_NYC,
    "new york city": REGION_NYC,
    "manhattan": REGION_NYC,
    "world": REGION_WORLD,
    "global": REGION_WORLD,
    "all": REGION_WORLD,
}

REGION_MAP_URLS = {
    REGION_PHL: "https://www.511pa.com/",
    REGION_MIA: "https://fl511.com/",
    REGION_FL: "https://fl511.com/",
    REGION_NYC: "https://webcams.nyctmc.org/",
    REGION_WORLD: "https://www.511pa.com/",
}

REGION_LABELS = {
    REGION_PHL: "Philadelphia",
    REGION_MIA: "Miami",
    REGION_FL: "Florida",
    REGION_NYC: "NYC",
    REGION_WORLD: "World",
}

TRAFFIC_BOARD_URL = REGION_MAP_URLS[REGION_PHL]

_PA_FEED = "https://www.511pa.com/List/GetData/Cameras"
_PA_STILL = "https://www.511pa.com/map/Cctv/{cid}"
_FL_FEED = "https://fl511.com/List/GetData/Cameras"
_FL_STILL = "https://fl511.com/map/Cctv/{cid}"
_NYC_API = "https://webcams.nyctmc.org/api/cameras"

_PA_METRO = frozenset({"philadelphia", "delaware", "montgomery", "bucks", "chester"})
_FL_MIAMI = frozenset(
    {
        "miami-dade",
        "miami dade",
        "dade",
        "broward",
        "palm beach",
        "monroe",
    }
)

# Known-good seeds (verified public stills).
_SEED_PHL: list[dict[str, Any]] = [
    {"name": "PA 291 - Philadelphia", "road": "PA 291", "id": 4875, "county": "Philadelphia"},
    {"name": "I-76 - Philadelphia", "road": "I-76", "id": 4987, "county": "Philadelphia"},
    {"name": "US 30 - Chester Co.", "road": "US 30", "id": 4953, "county": "Chester"},
    {"name": "US 30 - Chester Co.", "road": "US 30", "id": 5066, "county": "Chester"},
    {"name": "US 30 - Chester Co.", "road": "US 30", "id": 5067, "county": "Chester"},
    {"name": "US 30 Business", "road": "US 30 Business", "id": 5068, "county": "Chester"},
]

# FL511 ids — public /map/Cctv/{id} JPEG (Miami-ish + statewide fallbacks).
_SEED_FL: list[dict[str, Any]] = [
    {"name": "I-95 Miami corridor", "road": "I-95", "id": 1001, "county": "Miami-Dade"},
    {"name": "I-75 Alligator Alley", "road": "I-75", "id": 1, "county": "Collier"},
    {"name": "FL511 cam 50", "road": "FL", "id": 50, "county": "Florida"},
    {"name": "FL511 cam 100", "road": "FL", "id": 100, "county": "Florida"},
    {"name": "FL511 cam 200", "road": "FL", "id": 200, "county": "Florida"},
    {"name": "FL511 cam 500", "road": "FL", "id": 500, "county": "Florida"},
]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_QUERY_COLUMNS_PA = [
    {"data": None, "name": ""},
    {"name": "sortOrder", "s": True},
    {"name": "dotDistrict", "s": True},
    {"name": "county", "s": True},
    {"name": "roadway", "s": True},
    {"name": "turnpikeOnly"},
    {"name": "location"},
    {"name": "cameraName"},
    {"name": "district"},
    {"data": 9, "name": ""},
]

_QUERY_COLUMNS_FL = [
    {"data": None, "name": ""},
    {"name": "sortOrder", "s": True},
    {"name": "region", "s": True},
    {"name": "county", "s": True},
    {"name": "roadway", "s": True},
    {"name": "location"},
    {"name": "cameraName"},
    {"data": 7, "name": ""},
]


def normalize_region(name: str | None) -> str:
    raw = (name or REGION_PHL).strip().lower()
    if raw in _REGION_ALIASES:
        return _REGION_ALIASES[raw]
    for alias, canon in _REGION_ALIASES.items():
        if alias in raw or raw in alias:
            return canon
    return REGION_PHL


def _cache_bust(url: str) -> str:
    """Bust browser/CDN caches so near-live stills actually change."""
    ms = int(time.time() * 1000)
    nonce = hashlib.md5(f"{ms}:{url}".encode()).hexdigest()[:8]
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={ms}&r={nonce}&nocache=1"


def _is_placeholder(data: bytes) -> bool:
    if not data or len(data) < 800:
        return True
    if data[:2] != b"\xff\xd8":
        return True
    digest = hashlib.md5(data).hexdigest()
    if digest.startswith("839f1cd39c1e"):
        return True
    if len(data) == 16493:
        return True
    return False


def _pa_rank(county: str) -> int:
    c = (county or "").strip().lower()
    if c == "philadelphia":
        return 0
    if c in _PA_METRO:
        return 1
    return 2


def _fl_miami_match(rec: dict[str, Any]) -> bool:
    blob = " ".join(
        str(rec.get(k) or "")
        for k in ("county", "region", "city", "location", "roadway", "cameraName")
    ).lower()
    if "miami" in blob:
        return True
    for key in _FL_MIAMI:
        if key in blob:
            return True
    return False


class TrafficCams:
    """Multi-region public traffic stills (official 511 / DOT only)."""

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        settings: Any = None,
        city: str = "Philadelphia",
        enabled: bool = True,
        cache_sec: float = 0.5,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else None
        self.settings = settings
        self.enabled = bool(enabled)
        raw_city = (
            str(
                city
                or getattr(settings, "traffic_cams_city", None)
                or getattr(settings, "city", None)
                or "Philadelphia"
            ).strip()
            or "Philadelphia"
        )
        self.region = normalize_region(raw_city)
        self.city = REGION_LABELS.get(self.region, raw_city)
        self.cache_sec = max(0.2, float(cache_sec if cache_sec is not None else 0.5))
        self.board_url = REGION_MAP_URLS.get(self.region, TRAFFIC_BOARD_URL)
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, bytes | None, str]] = {}
        self._last_ok: dict[str, float] = {}
        self._cams = self._seed_list(self.region)
        self._feed_at = 0.0
        self._grid_offset = 0
        self._refresh_gen = 0
        threading.Thread(
            target=self._refresh_list_safe,
            args=(self.region, self._refresh_gen),
            daemon=True,
            name="traffic-cams-list",
        ).start()

    # ── region / public API ─────────────────────────────────────
    def set_region(self, name: str) -> str:
        """Switch region and kick a background list refresh."""
        region = normalize_region(name)
        with self._lock:
            self.region = region
            self.city = REGION_LABELS.get(region, name)
            self.board_url = REGION_MAP_URLS.get(region, TRAFFIC_BOARD_URL)
            self._cams = self._seed_list(region)
            self._grid_offset = 0
            self._refresh_gen += 1
            gen = self._refresh_gen
        threading.Thread(
            target=self._refresh_list_safe,
            args=(region, gen),
            daemon=True,
            name=f"traffic-cams-{region}",
        ).start()
        return f"Traffic cams region -> {self.city} ({region})."

    def set_grid_offset(self, offset: int) -> None:
        self._grid_offset = max(0, int(offset or 0))

    def map_url(self) -> str:
        return REGION_MAP_URLS.get(self.region, TRAFFIC_BOARD_URL)

    def status(self) -> str:
        if not self.enabled:
            return "Traffic cams disabled."
        with self._lock:
            n = len(self._cams)
            region = self.region
            city = self.city
            board = self.board_url
        src = {
            REGION_PHL: "PennDOT / 511PA",
            REGION_MIA: "FDOT / FL511",
            REGION_FL: "FDOT / FL511",
            REGION_NYC: "NYC DOT webcams",
            REGION_WORLD: "511PA + FL511 + NYC DOT",
        }.get(region, "public DOT")
        return (
            f"Traffic cams · {city} · {n} near-live official stills · "
            f"video via {src} map · board {board}."
        )

    def list_cams(self) -> list[dict[str, str]]:
        if not self.enabled:
            return []
        with self._lock:
            return [dict(c) for c in self._cams]

    def open_traffic_board(self) -> str:
        if not self.enabled:
            return "Traffic cams disabled."
        url = self.map_url()
        try:
            import webbrowser

            webbrowser.open(url)
            return f"Opening official traffic map for {self.city}."
        except Exception as e:
            try:
                from jarvis.core.displays import displays

                displays.open_url_on(url, "secondary")
                return f"Opening traffic map on secondary ({self.city})."
            except Exception:
                return f"Could not open traffic board ({e}). Try {url}"

    # ── seeds ───────────────────────────────────────────────────
    def _seed_list(self, region: str | None = None) -> list[dict[str, str]]:
        region = region or self.region
        if region == REGION_NYC:
            # NYC seeds filled after API; keep empty until refresh / soft mix
            return self._seed_from_phl_fl_mix(limit=4)  # temporary until NYC loads
        if region == REGION_MIA:
            return [
                self._cam_row(
                    cid=c["id"],
                    name=str(c["name"]),
                    road=str(c.get("road") or ""),
                    county=str(c.get("county") or ""),
                    still=_FL_STILL.format(cid=int(c["id"])),
                    source="fl511",
                )
                for c in _SEED_FL
            ]
        if region == REGION_FL:
            return [
                self._cam_row(
                    cid=c["id"],
                    name=str(c["name"]),
                    road=str(c.get("road") or ""),
                    county=str(c.get("county") or ""),
                    still=_FL_STILL.format(cid=int(c["id"])),
                    source="fl511",
                )
                for c in _SEED_FL
            ]
        if region == REGION_WORLD:
            return self._seed_from_phl_fl_mix(limit=8)
        # PHL default
        return [
            self._cam_row(
                cid=c["id"],
                name=str(c["name"]),
                road=str(c.get("road") or ""),
                county=str(c.get("county") or ""),
                still=_PA_STILL.format(cid=int(c["id"])),
                source="511pa",
            )
            for c in _SEED_PHL
        ]

    def _seed_from_phl_fl_mix(self, limit: int = 8) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for c in _SEED_PHL[:3]:
            out.append(
                self._cam_row(
                    cid=c["id"],
                    name=str(c["name"]),
                    road=str(c.get("road") or ""),
                    county=str(c.get("county") or ""),
                    still=_PA_STILL.format(cid=int(c["id"])),
                    source="511pa",
                )
            )
        for c in _SEED_FL[:3]:
            out.append(
                self._cam_row(
                    cid=c["id"],
                    name=str(c["name"]),
                    road=str(c.get("road") or ""),
                    county=str(c.get("county") or ""),
                    still=_FL_STILL.format(cid=int(c["id"])),
                    source="fl511",
                )
            )
        return out[:limit]

    @staticmethod
    def _cam_row(
        *,
        cid: Any,
        name: str,
        road: str = "",
        county: str = "",
        direction: str = "",
        still: str,
        video_url: str = "",
        source: str = "",
    ) -> dict[str, str]:
        return {
            "id": str(cid),
            "name": name,
            "road": road,
            "url": still,
            "video_url": video_url or "",
            "county": county,
            "direction": direction,
            "source": source,
        }

    # ── list refresh ────────────────────────────────────────────
    def _refresh_list_safe(self, region: str, gen: int) -> None:
        try:
            self._refresh_list(region, gen)
        except Exception as e:
            print(f"[traffic_cams] list refresh ({region}): {e}")

    def _refresh_list(self, region: str, gen: int) -> None:
        picked: list[dict[str, str]] = []
        if region in (REGION_PHL,):
            picked = self._refresh_pa(miami_only=False)
        elif region == REGION_MIA:
            picked = self._refresh_fl(miami_only=True)
        elif region == REGION_FL:
            picked = self._refresh_fl(miami_only=False)
        elif region == REGION_NYC:
            picked = self._refresh_nyc()
        elif region == REGION_WORLD:
            pa = self._refresh_pa(miami_only=False)[:8]
            fl = self._refresh_fl(miami_only=True)[:8]
            nyc = self._refresh_nyc()[:8]
            picked = pa + fl + nyc
        if not picked:
            return
        with self._lock:
            if gen != self._refresh_gen and region != self.region:
                return
            if normalize_region(self.region) != region and region != REGION_WORLD:
                # Another set_region raced ahead
                if self.region != region:
                    return
            self._cams = picked
            self._feed_at = time.time()
        print(f"[traffic_cams] refreshed {len(picked)} cams · region={region}")

    def _datatables_page(
        self, feed: str, columns: list, start: int, length: int, referer: str
    ) -> dict[str, Any]:
        query = {
            "columns": columns,
            "order": [{"column": 1, "dir": "asc"}],
            "start": start,
            "length": length,
            "search": {"value": ""},
        }
        params = urllib.parse.urlencode(
            {"query": json.dumps(query), "lang": "en-US"}
        )
        url = f"{feed}?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _UA,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json,*/*",
                "Referer": referer,
            },
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    def _refresh_pa(self, *, miami_only: bool = False) -> list[dict[str, str]]:
        del miami_only  # PA only
        first = self._datatables_page(
            _PA_FEED, _QUERY_COLUMNS_PA, 0, 100, "https://www.511pa.com/List/Cameras"
        )
        total = int(first.get("recordsTotal") or 0)
        rows: list[Any] = list(first.get("data") or [])
        start = 100
        while start < min(total, 600):
            chunk = self._datatables_page(
                _PA_FEED,
                _QUERY_COLUMNS_PA,
                start,
                100,
                "https://www.511pa.com/List/Cameras",
            ).get("data") or []
            rows.extend(chunk)
            start += 100
            time.sleep(0.2)
        picked: list[dict[str, str]] = []
        seen: set[str] = set()
        for rec in rows:
            county = (rec.get("county") or "").strip()
            county_l = county.lower()
            dist = str(rec.get("dotDistrict") or "").strip()
            if county_l not in _PA_METRO and dist not in ("6", "06"):
                continue
            road = (rec.get("roadway") or "").strip()
            loc = (rec.get("location") or rec.get("cameraName") or "").strip()
            direction = str(rec.get("direction") or "").strip()
            for img in rec.get("images") or []:
                try:
                    cid = int(img.get("id"))
                except Exception:
                    continue
                key = f"pa-{cid}"
                if key in seen:
                    continue
                seen.add(key)
                video_url = str(img.get("videoUrl") or "").strip()
                label = f"{road} - {loc}".strip(" -") if road or loc else f"Cam {cid}"
                if len(label) > 48:
                    label = label[:45] + "..."
                picked.append(
                    self._cam_row(
                        cid=cid,
                        name=label,
                        road=road,
                        county=county,
                        direction=direction,
                        still=_PA_STILL.format(cid=cid),
                        video_url=video_url,
                        source="511pa",
                    )
                )
                if len(picked) >= 40:
                    break
            if len(picked) >= 40:
                break
        picked.sort(key=lambda c: (_pa_rank(c.get("county", "")), c.get("name", "")))
        return picked

    def _refresh_fl(self, *, miami_only: bool) -> list[dict[str, str]]:
        first = self._datatables_page(
            _FL_FEED, _QUERY_COLUMNS_FL, 0, 100, "https://fl511.com/List/Cameras"
        )
        total = int(first.get("recordsTotal") or 0)
        rows: list[Any] = list(first.get("data") or [])
        start = 100
        scan_cap = 800 if miami_only else 400
        while start < min(total, scan_cap):
            chunk = self._datatables_page(
                _FL_FEED,
                _QUERY_COLUMNS_FL,
                start,
                100,
                "https://fl511.com/List/Cameras",
            ).get("data") or []
            rows.extend(chunk)
            start += 100
            time.sleep(0.2)
            # Early exit if we already have enough Miami hits
            if miami_only and sum(1 for r in rows if _fl_miami_match(r)) >= 30:
                break
        picked: list[dict[str, str]] = []
        seen: set[str] = set()
        for rec in rows:
            if miami_only and not _fl_miami_match(rec):
                continue
            county = (rec.get("county") or "").strip()
            road = (rec.get("roadway") or "").strip()
            loc = (rec.get("location") or rec.get("cameraName") or "").strip()
            direction = str(rec.get("direction") or "").strip()
            city = (rec.get("city") or "").strip()
            for img in rec.get("images") or []:
                try:
                    cid = int(img.get("id"))
                except Exception:
                    continue
                key = f"fl-{cid}"
                if key in seen:
                    continue
                seen.add(key)
                video_url = str(img.get("videoUrl") or "").strip()
                label = f"{road} - {loc or city}".strip(" -") or f"FL {cid}"
                if len(label) > 48:
                    label = label[:45] + "..."
                picked.append(
                    self._cam_row(
                        cid=cid,
                        name=label,
                        road=road,
                        county=county or city,
                        direction=direction,
                        still=_FL_STILL.format(cid=cid),
                        video_url=video_url,
                        source="fl511",
                    )
                )
                if len(picked) >= (36 if miami_only else 40):
                    break
            if len(picked) >= (36 if miami_only else 40):
                break
        # Prefer Miami-Dade first when florida-wide
        if not miami_only:
            picked.sort(
                key=lambda c: (
                    0 if "miami" in (c.get("county") or "").lower() else 1,
                    c.get("name", ""),
                )
            )
        return picked

    def _refresh_nyc(self) -> list[dict[str, str]]:
        req = urllib.request.Request(
            _NYC_API,
            headers={
                "User-Agent": _UA,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        if not isinstance(data, list):
            return []
        # Prefer Manhattan / online cams
        def _rank(cam: dict) -> tuple:
            area = (cam.get("area") or "").lower()
            online = str(cam.get("isOnline") or "").lower() in ("true", "1", "yes")
            pref = 0 if area == "manhattan" else 1 if area in ("brooklyn", "queens") else 2
            return (0 if online else 1, pref, cam.get("name") or "")

        cams = sorted(data, key=_rank)
        picked: list[dict[str, str]] = []
        for cam in cams:
            image = str(cam.get("imageUrl") or "").strip()
            if not image:
                cid = cam.get("id")
                if not cid:
                    continue
                image = f"https://webcams.nyctmc.org/api/cameras/{cid}/image"
            name = str(cam.get("name") or "NYC cam").strip()
            if len(name) > 48:
                name = name[:45] + "..."
            area = str(cam.get("area") or "NYC")
            picked.append(
                self._cam_row(
                    cid=cam.get("id") or name,
                    name=name,
                    road=area,
                    county=area,
                    still=image,
                    source="nycdot",
                )
            )
            if len(picked) >= 48:
                break
        return picked

    # ── fetch / grid ────────────────────────────────────────────
    def snapshot_url(self, name: str) -> str | None:
        if not self.enabled or not name:
            return None
        key = name.strip().lower()
        for cam in self.list_cams():
            if cam.get("name", "").lower() == key or cam.get("road", "").lower() == key:
                return cam.get("url")
        for cam in self.list_cams():
            nm = cam.get("name", "").lower()
            if key in nm or nm in key:
                return cam.get("url")
        return None

    def fetch_still(self, name_or_url: str, *, force: bool = False) -> bytes | None:
        if not self.enabled:
            return None
        url = name_or_url
        if "://" not in (name_or_url or ""):
            url = self.snapshot_url(name_or_url) or ""
        if not url:
            return None
        base = url.split("?")[0] if "://" in url else url
        now = time.time()
        with self._lock:
            hit = self._cache.get(base)
            if hit and not force and (now - hit[0]) < self.cache_sec:
                return hit[1]
        referer = "https://www.511pa.com/"
        if "fl511" in base:
            referer = "https://fl511.com/"
        elif "nyctmc" in base:
            referer = "https://webcams.nyctmc.org/"
        try:
            fetch_url = _cache_bust(base)
            req = urllib.request.Request(
                fetch_url,
                headers={
                    "User-Agent": _UA,
                    "Accept": "image/jpeg,image/*;q=0.8,*/*;q=0.5",
                    "Referer": referer,
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                data = resp.read()
            if _is_placeholder(data):
                print(f"[traffic_cams] placeholder skipped {base[:70]}")
                data = None
            with self._lock:
                # If force refresh returned identical bytes, still store (UI may rotate)
                self._cache[base] = (now, data, base)
                if data:
                    self._last_ok[base] = now
            return data
        except (urllib.error.URLError, TimeoutError, OSError, Exception) as e:
            print(f"[traffic_cams] soft-fail {base[:70]}: {e}")
            with self._lock:
                hit = self._cache.get(base)
                if hit and hit[1]:
                    return hit[1]
                self._cache[base] = (now, None, base)
            return None

    def _collect_grid(
        self, limit: int, offset: int, *, force: bool
    ) -> list[dict[str, Any]]:
        """Fetch up to `limit` stills in parallel for low-latency board refresh."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        lim = max(1, min(int(limit or 4), 6))
        off = max(0, int(offset or 0))
        cams = self.list_cams()
        if not cams:
            cams = self._seed_list(self.region)
        if cams and off:
            off = off % max(len(cams), 1)
        # Rotate window so the board doesn't sit on the same four cams
        ordered = cams[off:] + cams[:off] if off and cams else list(cams)
        candidates = ordered[: max(lim * 3, lim)]

        def _one(cam: dict[str, Any]) -> dict[str, Any] | None:
            blob = self.fetch_still(cam["url"], force=force)
            if blob is None:
                return None
            row = dict(cam)
            row["bytes"] = blob
            row["ok"] = True
            row["hash"] = hashlib.md5(blob).hexdigest()[:12]
            return row

        out: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(6, max(2, len(candidates)))) as pool:
            futs = {pool.submit(_one, cam): cam for cam in candidates}
            for fut in as_completed(futs):
                if len(out) >= lim:
                    break
                try:
                    row = fut.result()
                except Exception:
                    row = None
                if row:
                    out.append(row)
        # Stable order matching candidate order for less tile flicker
        by_url = {r.get("url"): r for r in out}
        ordered_out: list[dict[str, Any]] = []
        for cam in candidates:
            if len(ordered_out) >= lim:
                break
            hit = by_url.get(cam.get("url"))
            if hit and hit not in ordered_out:
                ordered_out.append(hit)
        if len(ordered_out) < lim:
            for cam in self._seed_list(self.region):
                if len(ordered_out) >= lim:
                    break
                if any(x.get("url") == cam["url"] for x in ordered_out):
                    continue
                row = _one(cam)
                if row:
                    ordered_out.append(row)
        return ordered_out

    def grid(self, limit: int = 4, offset: int = 0) -> list[dict[str, Any]]:
        return self._collect_grid(limit, offset, force=False)

    def live_grid(
        self, limit: int = 4, offset: int | None = None
    ) -> list[dict[str, Any]]:
        if offset is None:
            offset = self._grid_offset
        return self._collect_grid(limit, int(offset or 0), force=True)

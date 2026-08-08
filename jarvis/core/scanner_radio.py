"""Local public-safety / aviation / NOAA weather scanner listening (desk use).

Dispatch / police / fire → Broadcastify city/county listen pages.
Aviation / ATC → LiveATC.net (Broadcastify rarely indexes airport towers).
Weather / "satellite radio" → NOAA Weather Radio on Broadcastify (+ optional SDR).

Honest note: DOT traffic cam JPEGs have no microphones. SAT / weather audio is
NOAA / Broadcastify / optional RTL-SDR — never camera audio or illegal downlinks.

Optional:
  - settings.scanner_feed_url / scanner_feed_id → pinned Broadcastify feed
  - settings.scanner_rtl_freq + rtl_fm → USB SDR (e.g. NOAA WX channel)

Listening only — never for interference with emergency response.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional


# City → public listen hubs (personal desk; URLs are public pages)
# Prefer /listen/feed/ID or /listen/ctid/ID — free-text /search/?q= often returns empty.
_CITY_HUBS: dict[str, dict[str, str]] = {
    "philadelphia": {
        "broadcastify_county": "https://www.broadcastify.com/listen/ctid/2291",
        "broadcastify_police": "https://www.broadcastify.com/listen/ctid/2291",
        # PennDOT District 8 (PA) — real feed; "Philadelphia DOT" search is empty
        "broadcastify_truck": "https://www.broadcastify.com/listen/feed/42246",
        # Closest live NOAA to Philly metro (Hibernia Park WNG704) — KIH28 has no BCFY feed
        "broadcastify_noaa": "https://www.broadcastify.com/listen/feed/44541",
        "liveatc_icao": "kphl",
        "liveatc": "https://www.liveatc.net/search/?icao=kphl",
        "liveatc_play": "https://www.liveatc.net/listen/?mount=kphl_twr",
    },
    "philly": {
        "broadcastify_county": "https://www.broadcastify.com/listen/ctid/2291",
        "broadcastify_police": "https://www.broadcastify.com/listen/ctid/2291",
        "broadcastify_truck": "https://www.broadcastify.com/listen/feed/42246",
        "broadcastify_noaa": "https://www.broadcastify.com/listen/feed/44541",
        "liveatc_icao": "kphl",
        "liveatc": "https://www.liveatc.net/search/?icao=kphl",
        "liveatc_play": "https://www.liveatc.net/listen/?mount=kphl_twr",
    },
    # Miami-Dade County public feeds (Broadcastify ctid 328)
    "miami": {
        "broadcastify_county": "https://www.broadcastify.com/listen/ctid/328",
        "broadcastify_police": "https://www.broadcastify.com/listen/ctid/328",
        # FHP/DOT often encrypted — county public-safety hub is the usable listen page
        "broadcastify_truck": "https://www.broadcastify.com/listen/ctid/328",
        # Official NWS Miami audio (Broadcastify Miami NOAA search is empty)
        "broadcastify_noaa": "https://www.weather.gov/mfl/nwraudio",
        "liveatc_icao": "kmia",
        "liveatc": "https://www.liveatc.net/search/?icao=kmia",
        "liveatc_play": "https://www.liveatc.net/listen/?mount=kmia_twr",
    },
    "miami-dade": {
        "broadcastify_county": "https://www.broadcastify.com/listen/ctid/328",
        "broadcastify_police": "https://www.broadcastify.com/listen/ctid/328",
        "broadcastify_truck": "https://www.broadcastify.com/listen/ctid/328",
        "broadcastify_noaa": "https://www.weather.gov/mfl/nwraudio",
        "liveatc_icao": "kmia",
        "liveatc": "https://www.liveatc.net/search/?icao=kmia",
    },
    # Florida → Miami-Dade hub (primary FL public-safety listen page)
    "florida": {
        "broadcastify_county": "https://www.broadcastify.com/listen/ctid/328",
        "broadcastify_police": "https://www.broadcastify.com/listen/ctid/328",
        "broadcastify_truck": "https://www.broadcastify.com/listen/ctid/328",
        "broadcastify_noaa": "https://www.weather.gov/mfl/nwraudio",
        "liveatc_icao": "kmia",
        "liveatc": "https://www.liveatc.net/search/?icao=kmia",
    },
    # NYC — KWO35 NOAA is a real feed; police search is brittle so prefer browse
    "nyc": {
        "broadcastify_county": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_police": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_truck": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_noaa": "https://www.broadcastify.com/listen/feed/25412",
        "liveatc_icao": "kjfk",
        "liveatc": "https://www.liveatc.net/search/?icao=kjfk",
        "liveatc_play": "https://www.liveatc.net/listen/?mount=kjfk_twr",
    },
    "new york": {
        "broadcastify_county": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_police": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_truck": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_noaa": "https://www.broadcastify.com/listen/feed/25412",
        "liveatc_icao": "kjfk",
        "liveatc": "https://www.liveatc.net/search/?icao=kjfk",
        "liveatc_play": "https://www.liveatc.net/listen/?mount=kjfk_twr",
    },
    "new york city": {
        "broadcastify_county": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_police": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_truck": "https://www.broadcastify.com/listen/stid/36",
        "broadcastify_noaa": "https://www.broadcastify.com/listen/feed/25412",
        "liveatc_icao": "kjfk",
        "liveatc": "https://www.liveatc.net/search/?icao=kjfk",
    },
    "los angeles": {
        "liveatc_icao": "klax",
        "liveatc": "https://www.liveatc.net/search/?icao=klax",
        "broadcastify_truck": "https://www.broadcastify.com/listen/stid/6",
        "broadcastify_noaa": "https://www.broadcastify.com/listen/stid/6",
    },
    "chicago": {
        "liveatc_icao": "kord",
        "liveatc": "https://www.liveatc.net/search/?icao=kord",
        "broadcastify_truck": "https://www.broadcastify.com/listen/stid/17",
        "broadcastify_noaa": "https://www.broadcastify.com/listen/stid/17",
    },
}

_TRUCK_KINDS = frozenset(
    {"truck", "trucking", "trucker", "dot", "highway", "cb", "freight"}
)

# NOAA / weather / "satellite radio" (companion to traffic desk — not cam mics)
_WEATHER_KINDS = frozenset(
    {
        "weather",
        "satellite",
        "noaa",
        "wx",
        "nwr",
        "satellite radio",
        "satellite audio",
        "weather radio",
        "noaa radio",
    }
)

# Public NOAA Weather Radio — direct feeds beat empty city searches
# Philly metro fallback: Hibernia Park WNG704 (KIH28 has no Broadcastify feed)
_NOAA_WX_URL = "https://www.broadcastify.com/listen/feed/44541"
_NOAA_FALLBACKS = (
    "https://www.broadcastify.com/listen/feed/44541",  # Hibernia Park PA
    "https://www.broadcastify.com/listen/feed/39868",  # Allentown PA
    "https://www.broadcastify.com/listen/feed/25412",  # NYC KWO35
    "https://www.weather.gov/mfl/nwraudio",  # Miami NWS official audio
)

# Traffic-cam region keys → scanner city label
_REGION_TO_CITY: dict[str, str] = {
    "philadelphia": "Philadelphia",
    "philly": "Philadelphia",
    "miami": "Miami",
    "florida": "Florida",
    "nyc": "NYC",
    "new york": "NYC",
    "new york city": "NYC",
}


class ScannerRadio:
    def __init__(
        self,
        city: str = "Philadelphia",
        feed_url: str = "",
        feed_id: str = "",
        rtl_freq: str = "",
    ) -> None:
        self.city = (city or "Philadelphia").strip()
        self.feed_url = (feed_url or "").strip()
        self.feed_id = (feed_id or "").strip()
        self.rtl_freq = (rtl_freq or "").strip()
        self._rtl_proc: Optional[subprocess.Popen] = None
        self._last = ""

    @property
    def active(self) -> bool:
        return self._rtl_proc is not None and self._rtl_proc.poll() is None

    def set_city(self, city: str) -> str:
        """Update listen city (e.g. when traffic board region changes)."""
        name = (city or "").strip()
        if not name:
            return self.city
        key = name.lower()
        if key in _REGION_TO_CITY:
            self.city = _REGION_TO_CITY[key]
        else:
            self.city = name
        return self.city

    def follow_traffic_region(self, region: str) -> str:
        """Map traffic-cam region → scanner city (miami / nyc / philly…)."""
        return self.set_city(region or self.city)

    def _hub(self) -> dict[str, str]:
        key = self.city.lower().strip()
        if key in _CITY_HUBS:
            return _CITY_HUBS[key]
        # Soft match "Philadelphia, PA"
        for name, hub in _CITY_HUBS.items():
            if name in key or key in name:
                return hub
        return {}

    def _resolved_stream(self) -> str:
        if self.feed_url:
            return self.feed_url
        if self.feed_id.isdigit():
            return f"https://broadcastify.cdnstream1.com/{self.feed_id}"
        return ""

    def _broadcastify_search(self, query: str) -> str:
        q = urllib.parse.quote((query or self.city).strip())
        # Simpler query param Broadcastify accepts more reliably
        return f"https://www.broadcastify.com/search/?q={q}"

    def _icao_guess(self) -> str:
        hub = self._hub()
        if hub.get("liveatc_icao"):
            return hub["liveatc_icao"]
        # Heuristic: US cities often use K + 3-letter — only use known hub
        return ""

    def play(
        self,
        kind: str = "dispatch",
        *,
        query: str = "",
    ) -> str:
        """Tune local dispatch / police / fire / EMS / truck-DOT / ATC (listen only)."""
        kind = (kind or "dispatch").lower().strip()
        q = (query or "").strip()
        city = self.city
        hub = self._hub()

        # Prefer a feed the user pinned in settings (dispatch family only)
        stream = self._resolved_stream()
        if stream and kind in ("dispatch", "police", "scanner", "local", "fire", "ems", ""):
            self._last = stream
            try:
                webbrowser.open(
                    stream if stream.startswith("http") else self._broadcastify_search(city)
                )
            except Exception as e:
                return f"Could not open scanner stream: {e}"
            return (
                f"Opening your pinned scanner feed for {city}. "
                "Public listen only — do not interfere with responders."
            )

        # Aviation → LiveATC (Broadcastify search often returns nothing for ATC)
        if kind in ("aviation", "atc", "airport", "tower"):
            return self._open_liveatc(q)

        # NOAA / satellite weather radio (not traffic-cam microphones)
        if kind in _WEATHER_KINDS or kind.replace("_", " ") in _WEATHER_KINDS:
            return self.play_satellite_audio(query=q)

        # Truck / DOT / highway / CB — public Broadcastify only (never transmit)
        if kind in _TRUCK_KINDS:
            return self._open_truck(kind, query=q)
        # Known county / city hubs beat fragile free-text search
        if kind in ("dispatch", "scanner", "local") and hub.get("broadcastify_county"):
            url = hub["broadcastify_county"]
            self._last = url
            try:
                webbrowser.open(url)
            except Exception as e:
                return f"Could not open Broadcastify: {e}"
            return (
                f"Opening Broadcastify feeds for {city}. "
                "Pick police, fire, or EMS. Listening only."
            )
        if kind == "police" and hub.get("broadcastify_police"):
            url = hub["broadcastify_police"]
            self._last = url
            try:
                webbrowser.open(url)
            except Exception as e:
                return f"Could not open Broadcastify: {e}"
            return f"Opening {city} public-safety feeds on Broadcastify."

        # Short search phrases that Broadcastify actually indexes
        phrases = {
            "dispatch": f"{city} Police",
            "police": f"{city} Police",
            "fire": f"{city} Fire",
            "ems": f"{city} Fire",  # EMS often shared with fire feeds
            "scanner": f"{city} Police",
            "weather": "NOAA Weather Radio",
            "rail": f"{city} Rail",
            "truck": f"{city} Truck",
            "trucking": f"{city} Truck",
            "dot": f"{city} DOT",
            "highway": "highway",
            "cb": "CB",
        }
        search = q or phrases.get(kind, f"{city} Police")
        # Strip words that make Broadcastify return zero hits
        search = re.sub(
            r"\b(airport|air traffic|airtraffic|control|atc|tower)\b",
            "",
            search,
            flags=re.I,
        ).strip()
        if kind in ("aviation", "atc"):
            return self._open_liveatc(q)

        url = self._broadcastify_search(search)
        self._last = url
        try:
            webbrowser.open(url)
        except Exception as e:
            return f"Could not open Broadcastify: {e}"
        label = {
            "dispatch": "local dispatch",
            "police": "police radio",
            "fire": "fire dispatch",
            "ems": "EMS / fire",
            "weather": "weather radio",
            "rail": "rail",
            "truck": "truck / DOT",
            "dot": "DOT",
            "highway": "highway",
            "cb": "CB",
        }.get(kind, "scanner")
        return (
            f"Opening Broadcastify {label} for {city}. "
            "Listening only — do not interfere with commercial or emergency radio."
        )

    def _open_truck(self, kind: str = "truck", *, query: str = "") -> str:
        """Open public DOT / trucking / highway listen page for current city."""
        city = self.city
        hub = self._hub()
        kind = (kind or "truck").lower().strip()
        q = (query or "").strip()

        # Prefer pinned hub URL (direct feed/ctid — not empty DOT searches)
        if not q and hub.get("broadcastify_truck"):
            url = hub["broadcastify_truck"]
            self._last = url
            try:
                webbrowser.open(url)
            except Exception as e:
                return f"Could not open truck/DOT radio: {e}"
            return (
                f"Opening {city} highway / DOT public listen page. "
                "Listening only — never transmit. "
                "(City DOT free-text search on Broadcastify is often empty.)"
            )

        county = hub.get("broadcastify_county") or hub.get("broadcastify_police") or ""
        if not q and county:
            self._last = county
            try:
                webbrowser.open(county)
            except Exception as e:
                return f"Could not open highway listen page: {e}"
            return (
                f"Opening {city} public-safety / highway-adjacent feeds. "
                "Listening only — FHP/DOT channels are often encrypted or unlisted."
            )

        if q:
            search = q
        elif kind == "cb":
            search = "CB"
        else:
            # Never "{city} DOT" — that query returns zero hits on Broadcastify
            search = "highway"

        url = self._broadcastify_search(search)
        self._last = url
        try:
            webbrowser.open(url)
        except Exception as e:
            if county:
                try:
                    webbrowser.open(county)
                    self._last = county
                    return (
                        f"Truck search failed ({e}). Opened {city} county feeds instead. "
                        "Listening only."
                    )
                except Exception:
                    pass
            return f"Could not open truck/DOT radio: {e}"
        return (
            f"Opening Broadcastify search for {search}. "
            "Public listen only — do not jam, spoof, or inject into company/DOT radio."
        )

    def _open_liveatc(self, query: str = "") -> str:
        hub = self._hub()
        icao = ""
        m = re.search(r"\b(k[a-z]{3}|[a-z]{4})\b", (query or "").lower())
        if m:
            icao = m.group(1)
            if len(icao) == 3:
                icao = "k" + icao
        if not icao:
            icao = self._icao_guess() or hub.get("liveatc_icao", "")

        if icao:
            # Prefer full facility list so user can pick Tower / Approach / Ground
            url = hub.get("liveatc") or f"https://www.liveatc.net/search/?icao={icao}"
            # If they asked for tower specifically, try the listen mount
            if re.search(r"\btower\b", (query or "").lower()) and hub.get("liveatc_play"):
                url = hub["liveatc_play"]
            self._last = url
            webbrowser.open(url)
            return (
                f"Opening LiveATC for {icao.upper()} ({self.city}). "
                "Pick Tower, Approach, or Ground — Broadcastify does not host most ATC."
            )

        # Fallback: LiveATC search by city name
        q = urllib.parse.quote(query or f"{self.city} International")
        url = f"https://www.liveatc.net/search/?q={q}"
        self._last = url
        webbrowser.open(url)
        return (
            f"Opening LiveATC search for {self.city}. "
            "Airport ATC is on LiveATC, not Broadcastify."
        )

    def play_satellite_audio(self, *, query: str = "") -> str:
        """NOAA Weather Radio / satellite weather companion (not cam mics).

        Uses direct Broadcastify feed / NWS pages — city+NOAA search often
        returns zero results on Broadcastify.
        """
        city = self.city
        hub = self._hub()
        q = (query or "").strip()

        if q:
            url = self._broadcastify_search(q)
        else:
            url = (
                hub.get("broadcastify_noaa")
                or _NOAA_WX_URL
                or _NOAA_FALLBACKS[0]
            )

        self._last = url
        try:
            webbrowser.open(url)
        except Exception as e:
            for alt in _NOAA_FALLBACKS:
                if alt == url:
                    continue
                try:
                    webbrowser.open(alt)
                    self._last = alt
                    url = alt
                    break
                except Exception:
                    continue
            else:
                return f"Could not open NOAA weather radio: {e}"

        sdr_note = ""
        if self.rtl_freq:
            try:
                sdr_msg = self.play_rtl()
                low = (sdr_msg or "").lower()
                if "tuned" in low or "sdr" in low:
                    sdr_note = f" Also: {sdr_msg}"
                elif "not found" not in low and "no sdr" not in low:
                    sdr_note = f" SDR note: {sdr_msg}"
            except Exception as e:
                sdr_note = f" SDR soft-fail: {e}"

        where = "Broadcastify feed" if "broadcastify.com" in url else "NWS audio page"
        return (
            f"Satellite / NOAA weather radio for {city} ({where}). "
            "This is NOAA Weather Radio — not camera microphones. "
            "Traffic cam tiles stay silent. Hit Play on the feed."
            + sdr_note
        )

    def live_sat_url(self) -> str:
        """URL for in-HUD NOAA / satellite weather player."""
        hub = self._hub()
        return (
            hub.get("broadcastify_noaa")
            or _NOAA_WX_URL
            or _NOAA_FALLBACKS[0]
        )

    def play_traffic_audio(self) -> str:
        """Live city scanner audio for the traffic desk.

        DOT camera JPEGs have **no sound**. Broadcastify has no reliable
        “traffic noise” search — we open the city's live public-safety /
        DOT listen hub instead (real streams you can play immediately).
        """
        city = self.city
        hub = self._hub()

        # Prefer pinned stream when set
        stream = self._resolved_stream()
        if stream:
            self._last = stream
            try:
                webbrowser.open(stream)
            except Exception as e:
                return f"Could not open pinned scanner: {e}"
            return (
                f"Live scanner audio for {city} (pinned feed). "
                "Camera tiles stay silent — this is the live radio."
            )

        # Real live county page (always has playable feeds)
        url = (
            hub.get("broadcastify_county")
            or hub.get("broadcastify_police")
            or ""
        )
        if not url:
            url = self._broadcastify_search(f"{city} Police")

        self._last = url
        opened = []
        try:
            webbrowser.open(url)
            opened.append("city scanner")
        except Exception as e:
            return f"Could not open live scanner audio: {e}"

        # Second tab: DOT / highway only when we have a real feed/ctid (not empty search)
        truck = hub.get("broadcastify_truck") or ""
        if (
            truck
            and truck != url
            and "/search/" not in truck
            and ("/listen/feed/" in truck or "/listen/ctid/" in truck or "/listen/stid/" in truck)
        ):
            try:
                webbrowser.open(truck)
                opened.append("DOT / highway")
            except Exception:
                pass

        bits = " + ".join(opened)
        return (
            f"Live {city} scanner audio online ({bits}). "
            "Click Play on a feed. Traffic cam pictures have no microphone — "
            "this is real live radio for your area."
        )

    def live_audio_url(self) -> str:
        """URL for the in-HUD scanner player (county listen page)."""
        stream = self._resolved_stream()
        if stream:
            return stream
        hub = self._hub()
        return (
            hub.get("broadcastify_county")
            or hub.get("broadcastify_police")
            or self._broadcastify_search(f"{self.city} Police")
        )

    def play_rtl(self) -> str:
        """Advanced: tune USB RTL-SDR via rtl_fm if installed."""
        freq = self.rtl_freq
        if not freq:
            return (
                "No SDR frequency set. Add scanner_rtl_freq in settings "
                "(e.g. 154.430M) and install rtl_fm."
            )
        rtl = shutil.which("rtl_fm")
        play = shutil.which("play") or shutil.which("ffplay") or shutil.which("sox")
        if not rtl:
            return (
                "rtl_fm not found. Install RTL-SDR tools, plug in the dongle, "
                "or say 'local dispatch' / 'air traffic' instead."
            )
        self.stop()
        try:
            if play and Path(play).name.lower().startswith("ffplay"):
                cmd = (
                    f'"{rtl}" -f {freq} -s 22050 -g 40 - | '
                    f'"{play}" -nodisp -loglevel quiet -f s16le -ar 22050 -ac 1 -'
                )
            elif play:
                cmd = (
                    f'"{rtl}" -f {freq} -s 22050 -g 40 - | '
                    f'"{play}" -r 22050 -t raw -e s -b 16 -c 1 -V1 -'
                )
            else:
                return (
                    f"Found rtl_fm but no audio player (ffplay/sox). "
                    f"Would tune {freq}."
                )
            self._rtl_proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._last = f"rtl:{freq}"
            return f"SDR tuned to {freq} via rtl_fm. Say stop scanner to halt."
        except Exception as e:
            return f"SDR tune failed: {e}"

    def stop(self) -> str:
        if self._rtl_proc is not None:
            try:
                self._rtl_proc.terminate()
            except Exception:
                pass
            self._rtl_proc = None
            return "Scanner / SDR stopped."
        return "No local SDR session running. Close the browser tab if a stream is open."

    def status(self) -> str:
        bits = [f"City {self.city}"]
        hub = self._hub()
        if hub.get("liveatc_icao"):
            bits.append(f"ATC {hub['liveatc_icao'].upper()}")
        if self.feed_id:
            bits.append(f"pinned feed {self.feed_id}")
        if self.feed_url:
            bits.append("custom feed URL set")
        if self.rtl_freq:
            bits.append(f"SDR {self.rtl_freq}")
        if self.active:
            bits.append("SDR LIVE")
        if self._last:
            bits.append(f"last: {self._last[:60]}")
        return "Scanner: " + " · ".join(bits)

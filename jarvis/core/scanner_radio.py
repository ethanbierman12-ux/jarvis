"""Local public-safety / aviation scanner listening (personal desk use).

Dispatch / police / fire → Broadcastify city/county listen pages.
Aviation / ATC → LiveATC.net (Broadcastify rarely indexes airport towers).

Optional:
  - settings.scanner_feed_url / scanner_feed_id → pinned Broadcastify feed
  - settings.scanner_rtl_freq + rtl_fm → USB SDR

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
_CITY_HUBS: dict[str, dict[str, str]] = {
    "philadelphia": {
        "broadcastify_county": "https://www.broadcastify.com/listen/ctid/2291",
        "broadcastify_police": "https://www.broadcastify.com/listen/ctid/2291",
        "liveatc_icao": "kphl",
        "liveatc": "https://www.liveatc.net/search/?icao=kphl",
        # Default tower feed page (user picks channel on LiveATC)
        "liveatc_play": "https://www.liveatc.net/listen/?mount=kphl_twr",
    },
    "philly": {
        "broadcastify_county": "https://www.broadcastify.com/listen/ctid/2291",
        "liveatc_icao": "kphl",
        "liveatc": "https://www.liveatc.net/search/?icao=kphl",
        "liveatc_play": "https://www.liveatc.net/listen/?mount=kphl_twr",
    },
    "new york": {
        "liveatc_icao": "kjfk",
        "liveatc": "https://www.liveatc.net/search/?icao=kjfk",
    },
    "los angeles": {
        "liveatc_icao": "klax",
        "liveatc": "https://www.liveatc.net/search/?icao=klax",
    },
    "chicago": {
        "liveatc_icao": "kord",
        "liveatc": "https://www.liveatc.net/search/?icao=kord",
    },
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
        """Tune local dispatch / police / fire / EMS / ATC via public streams."""
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

        # Known county / city hubs beat fragile free-text search
        if kind in ("dispatch", "scanner", "local") and hub.get("broadcastify_county"):
            url = hub["broadcastify_county"]
            self._last = url
            webbrowser.open(url)
            return (
                f"Opening Broadcastify feeds for {city}. "
                "Pick police, fire, or EMS. Listening only."
            )
        if kind == "police" and hub.get("broadcastify_police"):
            url = hub["broadcastify_police"]
            self._last = url
            webbrowser.open(url)
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
        }.get(kind, "scanner")
        return (
            f"Opening Broadcastify {label} for {city}. "
            "Listening only — do not interfere with emergency response."
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

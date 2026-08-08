"""Hands-free music — pinned Spotify playlist + desktop URI + optional Web API."""

from __future__ import annotations

import os
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path


# Default: Iron Man / Tony Stark workshop ambience on Spotify
DEFAULT_PLAYLIST_ID = "0wAwIuOxCyimlomGUiAGQ2"
WORKSHOP_PLAYLIST_ID = DEFAULT_PLAYLIST_ID
WORKSHOP_QUERY = "Iron Man Tony Stark Workshop"
# Default "play music" → Shoot to Thrill (Iron Man 2 / AC/DC)
DEFAULT_TRACK_QUERY = "Shoot to Thrill AC/DC Iron Man 2"
DEFAULT_TRACK_URI = "spotify:track:6GzCkTddOn1vSln1gbSr8y"
# Stark arrival anthem
HIGHWAY_TRACK_QUERY = "Highway to Hell AC/DC"
HIGHWAY_TRACK_URI = "spotify:track:2zYzyRzz6pRmhPzyfMEC8s"
HIGHWAY_OPEN_URL = "https://open.spotify.com/track/2zYzyRzz6pRmhPzyfMEC8s"


class MusicPlayer:
    def __init__(
        self,
        focus_playlist: str = "focus",
        spotify_playlist_id: str = "",
        spotify_client_id: str = "",
        spotify_client_secret: str = "",
        spotify_redirect_uri: str = "http://127.0.0.1:8888/callback",
    ) -> None:
        self.focus_playlist = focus_playlist or "focus"
        self.playlist_id = (
            (spotify_playlist_id or "").strip()
            or os.environ.get("SPOTIFY_PLAYLIST_ID", "").strip()
            or DEFAULT_PLAYLIST_ID
        )
        self._spotify = Path(os.environ.get("APPDATA", "")) / r"Spotify\Spotify.exe"
        self._client_id = (spotify_client_id or os.environ.get("SPOTIFY_CLIENT_ID") or "").strip()
        self._client_secret = (
            spotify_client_secret or os.environ.get("SPOTIFY_CLIENT_SECRET") or ""
        ).strip()
        self._redirect = spotify_redirect_uri or "http://127.0.0.1:8888/callback"
        self._sp = None

    @property
    def playlist_uri(self) -> str:
        return f"spotify:playlist:{self.playlist_id}"

    @property
    def playlist_embed_url(self) -> str:
        return (
            f"https://open.spotify.com/embed/playlist/{self.playlist_id}"
            f"?utm_source=generator&theme=0"
        )

    @property
    def playlist_open_url(self) -> str:
        return f"https://open.spotify.com/playlist/{self.playlist_id}"

    def _api(self):
        """Lazy Spotify Web API client (optional — needs spotipy + user auth cache)."""
        if self._sp is not None:
            return self._sp
        if not self._client_id or not self._client_secret:
            return None
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth

            scope = (
                "user-modify-playback-state user-read-playback-state "
                "user-read-currently-playing"
            )
            auth = SpotifyOAuth(
                client_id=self._client_id,
                client_secret=self._client_secret,
                redirect_uri=self._redirect,
                scope=scope,
                cache_path=str(
                    Path(__file__).resolve().parents[2]
                    / "jarvis"
                    / "data"
                    / ".spotify_cache"
                ),
                open_browser=True,
            )
            self._sp = spotipy.Spotify(auth_manager=auth)
            return self._sp
        except Exception as e:
            print(f"[music] Spotify API unavailable: {e}")
            return None

    def _launch_uri(self, uri: str) -> bool:
        if self._spotify.exists():
            try:
                subprocess.Popen([str(self._spotify), f"--uri={uri}"], shell=False)
                return True
            except Exception as e:
                print(f"[music] launch uri failed: {e}")
        try:
            webbrowser.open(uri if uri.startswith("http") else self.playlist_open_url)
            return True
        except Exception:
            return False

    def _spotify_hwnd(self):
        """Return Spotify main window HWND, or 0."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            found = wintypes.HWND(0)

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def _enum(hwnd, _lp):  # type: ignore[misc]
                nonlocal found
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").lower()
                if "spotify" in title and "jarvis" not in title:
                    found = hwnd
                    return False
                return True

            user32.EnumWindows(_enum, 0)
            return found
        except Exception:
            return 0

    def _focus_spotify(self) -> bool:
        """Bring Spotify to the foreground so media play lands on it."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            found = self._spotify_hwnd()
            if not found:
                return False
            user32.ShowWindow(found, 9)  # SW_RESTORE
            user32.SetForegroundWindow(found)
            return True
        except Exception as e:
            print(f"[music] focus spotify: {e}")
            return False

    def press_play_key(self) -> str:
        """Send an explicit Play (not toggle) via WM_APPCOMMAND + Spotify window."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            HWND_BROADCAST = 0xFFFF
            WM_APPCOMMAND = 0x0319
            APPCOMMAND_MEDIA_PLAY = 46
            play_lparam = APPCOMMAND_MEDIA_PLAY << 16
            # Target Spotify first (more reliable than broadcast alone)
            hwnd = self._spotify_hwnd()
            if hwnd:
                user32.PostMessageW(hwnd, WM_APPCOMMAND, 0, play_lparam)
            user32.PostMessageW(
                HWND_BROADCAST, WM_APPCOMMAND, 0, play_lparam
            )
            return "Playing."
        except Exception as e:
            return f"Play key failed: {e}"

    def _send_spotify_space(self) -> None:
        """Space toggles play in Spotify when the app has focus."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            VK_SPACE = 0x20
            KEYEVENTF_KEYUP = 0x0002
            if not self._focus_spotify():
                return
            time.sleep(0.12)
            user32.keybd_event(VK_SPACE, 0, 0, 0)
            user32.keybd_event(VK_SPACE, 0, KEYEVENTF_KEYUP, 0)
        except Exception as e:
            print(f"[music] spotify space: {e}")

    def _ensure_playing(self, wait_s: float = 2.0, retries: int = 1) -> None:
        """Focus Spotify and start playback without a manual Play click.

        Desktop Spotify usually opens the URI paused. Media Play is tried first
        (non-toggle); a single Space follows because Spotify often ignores
        WM_APPCOMMAND. Only one Space — a second would pause again.
        """
        time.sleep(max(0.5, wait_s))
        for _ in range(12):
            if self._spotify_hwnd():
                break
            time.sleep(0.35)
        self._focus_spotify()
        time.sleep(0.2)
        for _ in range(max(1, retries)):
            self.press_play_key()
            time.sleep(0.35)
        # Final hands-free kick — Spotify app play/pause shortcut
        self._send_spotify_space()

    def play_recommendation(self) -> str:
        """Play the pinned Iron Man workshop playlist on Spotify."""
        uri = self.playlist_uri
        sp = self._api()
        if sp is not None:
            try:
                sp.start_playback(context_uri=uri)
                return "Playing Iron Man workshop music on Spotify."
            except Exception as e:
                print(f"[music] API playlist play: {e}")
        if self._launch_uri(uri):
            self._ensure_playing(wait_s=1.8, retries=2)
            return "Playing Iron Man workshop music on Spotify."
        # Search fallback if pinned playlist fails to open
        if self._spotify.exists():
            try:
                search = "spotify:search:" + urllib.parse.quote(WORKSHOP_QUERY)
                subprocess.Popen([str(self._spotify), f"--uri={search}"], shell=False)
                self._ensure_playing(wait_s=2.0, retries=2)
                return "Playing Iron Man workshop music on Spotify."
            except Exception:
                pass
        webbrowser.open(self.playlist_open_url)
        self._ensure_playing(wait_s=2.0, retries=2)
        return "Opened Iron Man workshop playlist on Spotify."

    def play_highway_to_hell(self) -> str:
        """Play AC/DC Highway to Hell and force Play (hands-free)."""
        sp = self._api()
        if sp is not None:
            try:
                sp.start_playback(uris=[HIGHWAY_TRACK_URI])
                self.press_play_key()
                return "Playing Highway to Hell on Spotify."
            except Exception as e:
                print(f"[music] API highway: {e}")
        api_msg = self._api_play_search(HIGHWAY_TRACK_QUERY)
        if api_msg:
            self._ensure_playing(wait_s=1.2, retries=2)
            self.press_play_key()
            return api_msg if "Highway" in api_msg or "highway" in api_msg.lower() else (
                "Playing Highway to Hell on Spotify."
            )
        if self._launch_uri(HIGHWAY_TRACK_URI):
            self._ensure_playing(wait_s=1.8, retries=2)
            self.press_play_key()
            return "Playing Highway to Hell on Spotify."
        if self._spotify.exists():
            try:
                search = "spotify:search:" + urllib.parse.quote(HIGHWAY_TRACK_QUERY)
                subprocess.Popen([str(self._spotify), f"--uri={search}"], shell=False)
                self._ensure_playing(wait_s=2.0, retries=2)
                self.press_play_key()
                return "Playing Highway to Hell on Spotify."
            except Exception:
                pass
        webbrowser.open(HIGHWAY_OPEN_URL)
        self._ensure_playing(wait_s=2.0, retries=2)
        self.press_play_key()
        return "Opened Highway to Hell on Spotify."

    def play_shoot_to_thrill(self) -> str:
        """Play AC/DC Shoot to Thrill (Iron Man 2) on Spotify."""
        sp = self._api()
        if sp is not None:
            try:
                sp.start_playback(uris=[DEFAULT_TRACK_URI])
                return "Playing Shoot to Thrill on Spotify."
            except Exception as e:
                print(f"[music] API track play: {e}")
        api_msg = self._api_play_search(DEFAULT_TRACK_QUERY)
        if api_msg:
            return api_msg
        if self._launch_uri(DEFAULT_TRACK_URI):
            self._ensure_playing(wait_s=1.8, retries=2)
            return "Playing Shoot to Thrill on Spotify."
        if self._spotify.exists():
            try:
                search = "spotify:search:" + urllib.parse.quote(DEFAULT_TRACK_QUERY)
                subprocess.Popen([str(self._spotify), f"--uri={search}"], shell=False)
                self._ensure_playing(wait_s=2.0, retries=2)
                return "Playing Shoot to Thrill on Spotify."
            except Exception:
                pass
        webbrowser.open(
            "https://open.spotify.com/track/6GzCkTddOn1vSln1gbSr8y"
        )
        self._ensure_playing(wait_s=2.0, retries=2)
        return "Opened Shoot to Thrill on Spotify."

    def play_workshop(self) -> str:
        """Explicit Stark lab / Iron Man workshop soundtrack."""
        prev = self.playlist_id
        self.playlist_id = WORKSHOP_PLAYLIST_ID
        try:
            return self.play_recommendation()
        finally:
            self.playlist_id = prev

    def _api_play_search(self, query: str) -> str | None:
        sp = self._api()
        if sp is None:
            return None
        try:
            res = sp.search(q=query, type="track", limit=1)
            items = (res.get("tracks") or {}).get("items") or []
            if not items:
                return None
            track = items[0]
            uri = track.get("uri")
            name = track.get("name", query)
            artist = ", ".join(a.get("name", "") for a in track.get("artists") or [])
            try:
                sp.start_playback(uris=[uri])
            except Exception:
                if not self._launch_uri(uri):
                    webbrowser.open(uri)
            label = f"{name} by {artist}".strip()
            if label.endswith(" by"):
                label = name
            return f"Playing {label} on Spotify."
        except Exception as e:
            print(f"[music] API play failed: {e}")
            return None

    def play_music(self) -> str:
        # "play music" → Shoot to Thrill (Iron Man / AC/DC)
        return self.play_shoot_to_thrill()

    def play(self, query: str = "") -> str:
        q = (query or "").strip()
        if not q or q.lower() in ("music", "something", "my music", "song", "a song"):
            return self.play_music()

        low = q.lower()
        if low in ("press play", "pressed play"):
            self._focus_spotify()
            return self.press_play_key()

        # STT variants: "ride or thrill", "shoot to thrill", etc.
        if any(
            k in low
            for k in (
                "shoot to thrill",
                "ride or thrill",
                "ride to thrill",
                "shot to thrill",
                "shoot the thrill",
            )
        ) or low in ("thrill", "shoot thrill"):
            return self.play_shoot_to_thrill()

        if any(
            k in low
            for k in (
                "highway to hell",
                "highway 2 hell",
                "high way to hell",
            )
        ):
            return self.play_highway_to_hell()

        if any(
            k in low
            for k in (
                "iron man",
                "workshop",
                "stark workshop",
                "tony stark",
                "garage",
            )
        ):
            return self.play_workshop()

        if any(
            k in low
            for k in (
                "focus",
                "recommendation",
                "recommend",
                "my playlist",
                "jarvis playlist",
            )
        ) or low in ("playlist", "my focus playlist", "focus playlist"):
            return self.play_playlist(self.focus_playlist or "focus")

        if "playlist" in low:
            name = (
                low.replace("playlist", "").replace("my", "").strip()
                or self.focus_playlist
            )
            return self.play_playlist(name)

        api_msg = self._api_play_search(q)
        if api_msg:
            return api_msg

        if self._spotify.exists():
            try:
                uri = "spotify:search:" + urllib.parse.quote(q)
                subprocess.Popen([str(self._spotify), "--uri=" + uri], shell=False)
                self._ensure_playing(wait_s=2.0, retries=2)
                return f"Playing {q} on Spotify."
            except Exception:
                pass

        url = "https://music.youtube.com/search?q=" + urllib.parse.quote(q)
        webbrowser.open(url)
        self._ensure_playing(wait_s=1.8, retries=2)
        return f"Playing {q} on YouTube Music."

    def play_playlist(self, name: str) -> str:
        q = (name or "focus").strip()
        # Always prefer the pinned Dev playlist for focus / recommendation names
        if q.lower() in (
            "focus",
            "recommendation",
            "recommend",
            "jarvis",
            "default",
            "workshop",
            "iron man",
            "iron man workshop",
            "tony stark",
            "stark workshop",
            self.focus_playlist.lower(),
        ):
            return self.play_workshop()

        sp = self._api()
        if sp is not None:
            try:
                res = sp.search(q=q, type="playlist", limit=1)
                items = (res.get("playlists") or {}).get("items") or []
                if items:
                    uri = items[0].get("uri")
                    try:
                        sp.start_playback(context_uri=uri)
                    except Exception:
                        self._launch_uri(uri)
                    return f"Playing your {q} playlist on Spotify."
            except Exception as e:
                print(f"[music] playlist API: {e}")
        if self._spotify.exists():
            try:
                uri = "spotify:search:" + urllib.parse.quote(f"playlist:{q}")
                subprocess.Popen([str(self._spotify), "--uri=" + uri], shell=False)
                self._ensure_playing(wait_s=2.0, retries=2)
                return f"Playing your {q} playlist on Spotify."
            except Exception:
                pass
        # Fall back to pinned playlist rather than YT
        return self.play_recommendation()

    def volume_up(self, steps: int = 4) -> str:
        for _ in range(max(1, steps)):
            self.media_key("volup")
        return "Volume up."

    def volume_down(self, steps: int = 4) -> str:
        for _ in range(max(1, steps)):
            self.media_key("voldown")
        return "Volume down."

    def press_play(self) -> str:
        """Start music and force a Play keypress (used by START + Music button)."""
        return self.play_music()

    def media_key(self, action: str) -> str:
        try:
            import ctypes

            if action in ("play", "play_only"):
                return self.press_play_key()

            VK = {
                "playpause": 0xB3,
                "next": 0xB0,
                "previous": 0xB1,
                "mute": 0xAD,
                "stop": 0xB2,
                "volup": 0xAF,
                "voldown": 0xAE,
            }
            code = VK.get(action)
            if code is None:
                return f"Unknown media action {action}."
            ctypes.windll.user32.keybd_event(code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(code, 0, 2, 0)
            return action
        except Exception as e:
            return f"Media key failed: {e}"

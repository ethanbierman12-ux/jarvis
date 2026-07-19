"""Hands-free music — pinned Spotify playlist + desktop URI + optional Web API."""

from __future__ import annotations

import os
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path


# Default recommendation playlist from Spotify Dev embed
DEFAULT_PLAYLIST_ID = "3hMeaqVid62fywPpTBWWw9"


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

    def play_recommendation(self) -> str:
        """Play the pinned Spotify Dev recommendation playlist."""
        uri = self.playlist_uri
        sp = self._api()
        if sp is not None:
            try:
                sp.start_playback(context_uri=uri)
                return "Playing your recommendation playlist on Spotify."
            except Exception as e:
                print(f"[music] API playlist play: {e}")
        if self._launch_uri(uri):
            time.sleep(1.5)
            self.media_key("playpause")
            return "Playing your recommendation playlist on Spotify."
        webbrowser.open(self.playlist_open_url)
        return "Opened your Spotify recommendation playlist."

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
        # Prefer pinned recommendation playlist over generic Liked Songs
        return self.play_recommendation()

    def play(self, query: str = "") -> str:
        q = (query or "").strip()
        if not q or q.lower() in ("music", "something", "my music", "song", "a song"):
            return self.play_music()

        low = q.lower()
        if low in ("press play", "pressed play"):
            self.media_key("playpause")
            return "Playing."

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
                time.sleep(2.0)
                self.media_key("playpause")
                return f"Playing {q} on Spotify."
            except Exception:
                pass

        url = "https://music.youtube.com/search?q=" + urllib.parse.quote(q)
        webbrowser.open(url)
        time.sleep(1.5)
        self.media_key("playpause")
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
            self.focus_playlist.lower(),
        ):
            return self.play_recommendation()

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
                time.sleep(2.0)
                self.media_key("playpause")
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
        return self.play_music()

    def media_key(self, action: str) -> str:
        try:
            import ctypes

            VK = {
                "playpause": 0xB3,
                "play": 0xB3,
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

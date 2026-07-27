"""Ultra-low-latency voice path — ElevenLabs turbo streaming + LiveKit tokens."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterator


@dataclass
class StreamChunk:
    pcm_or_mpeg: bytes
    mime: str
    first: bool = False
    done: bool = False


class LiveVoiceBridge:
    """
    Desk-side bridge for sub-500ms first-audio TTS when ElevenLabs turbo is keyed,
    plus optional LiveKit room token minting for streaming duplex.
    """

    def __init__(
        self,
        *,
        elevenlabs_api_key: str = "",
        elevenlabs_voice_id: str = "",
        elevenlabs_model: str = "eleven_turbo_v2_5",
        livekit_url: str = "",
        livekit_api_key: str = "",
        livekit_api_secret: str = "",
    ) -> None:
        self.el_key = (elevenlabs_api_key or "").strip()
        self.voice_id = (elevenlabs_voice_id or "").strip()
        self.model = (elevenlabs_model or "eleven_turbo_v2_5").strip()
        self.livekit_url = (livekit_url or "").rstrip("/")
        self.lk_key = (livekit_api_key or "").strip()
        self.lk_secret = (livekit_api_secret or "").strip()
        self.last_ttfb_ms: float | None = None

    def status(self) -> str:
        el = "ElevenLabs turbo ready" if self.el_key and self.voice_id else "ElevenLabs not keyed"
        lk = (
            "LiveKit ready"
            if self.livekit_url and self.lk_key and self.lk_secret
            else "LiveKit not configured"
        )
        ttfb = (
            f" Last TTS TTFB {self.last_ttfb_ms:.0f}ms."
            if self.last_ttfb_ms is not None
            else ""
        )
        return f"Live voice — {el}; {lk}.{ttfb}"

    def synthesize_fast(self, text: str) -> tuple[bytes, str, float]:
        """
        Non-stream fallback that still targets turbo model for low latency.
        Returns (audio_bytes, mime, ttfb_ms).
        """
        text = (text or "").strip()
        if not text:
            return b"", "audio/mpeg", 0.0
        if not self.el_key or not self.voice_id:
            raise RuntimeError("ElevenLabs key/voice missing — say set elevenlabs key …")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        body = {
            "text": text[:2500],
            "model_id": self.model or "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.35,
                "similarity_boost": 0.8,
                "style": 0.25,
                "use_speaker_boost": True,
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "xi-api-key": self.el_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                # First byte timing
                first = resp.read(4096)
                ttfb = (time.perf_counter() - t0) * 1000.0
                rest = resp.read()
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"ElevenLabs {e.code}: {err[:180]}") from e
        self.last_ttfb_ms = ttfb
        return first + rest, "audio/mpeg", ttfb

    def synthesize_b64(self, text: str) -> dict[str, Any]:
        audio, mime, ttfb = self.synthesize_fast(text)
        return {
            "ok": True,
            "mime": mime,
            "audioBase64": base64.b64encode(audio).decode("ascii"),
            "ttfb_ms": round(ttfb, 1),
            "sub_500ms": ttfb < 500,
            "model": self.model,
        }

    def mint_livekit_token(
        self,
        *,
        identity: str = "jarvis-desk",
        room: str = "jarvis-ops",
        ttl_sec: int = 3600,
    ) -> dict[str, Any]:
        """
        Mint a LiveKit access token if PyJWT + keys are available.
        Returns {url, token, room} for the hologram client.
        """
        if not (self.livekit_url and self.lk_key and self.lk_secret):
            return {
                "ok": False,
                "error": "Set livekit url, api key, and api secret in settings.",
            }
        try:
            import jwt  # PyJWT
        except Exception:
            return {
                "ok": False,
                "error": "Install PyJWT for LiveKit tokens: pip install PyJWT",
            }
        now = int(time.time())
        payload = {
            "iss": self.lk_key,
            "sub": identity,
            "nbf": now - 10,
            "exp": now + max(60, int(ttl_sec)),
            "video": {
                "roomJoin": True,
                "room": room,
                "canPublish": True,
                "canSubscribe": True,
            },
        }
        token = jwt.encode(payload, self.lk_secret, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode("ascii")
        return {
            "ok": True,
            "url": self.livekit_url,
            "token": token,
            "room": room,
            "identity": identity,
        }

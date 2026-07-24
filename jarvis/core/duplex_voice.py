"""Duplex voice — Deepgram streaming STT with live barge-in.

Full-duplex pipeline: the mic streams continuously to Deepgram over a
WebSocket (linear16 @ 16 kHz), interim transcripts arrive in well under
300 ms, and the caller decides when a transcript means "the user is
talking over Jarvis" (barge-in).

Additive and boot-safe: engaged only when a Deepgram API key is
configured and `websockets` + `sounddevice` import cleanly. The classic
chunked recognizer in jarvis/core/voice.py remains the fallback.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Callable

from jarvis.core.audio_isolation import pick_isolated_mic_index

SAMPLE_RATE = 16000
BLOCK_MS = 100  # 100ms frames — low latency without hammering the socket
KEEPALIVE_SEC = 5.0
RECONNECT_MAX = 6


def duplex_deps_ok() -> tuple[bool, str]:
    """Import-check the streaming stack without touching hardware."""
    try:
        import numpy  # noqa: F401
        import sounddevice  # noqa: F401
        import websockets  # noqa: F401
    except Exception as e:
        return False, f"missing dependency: {e}"
    return True, "ok"


def pick_input_device(prefer: str = "", allow_virtual: bool = False) -> int | None:
    """Pick a sounddevice input index using the same isolation rules as PyAudio."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
    except Exception:
        return None
    # Keep list positions aligned with device indexes; blank out non-inputs so
    # the ranker never selects them.
    names = [
        (d.get("name") or "") if int(d.get("max_input_channels") or 0) > 0 else ""
        for d in devices
    ]
    idx, reason = pick_isolated_mic_index(
        names, prefer=prefer or "", allow_virtual=allow_virtual
    )
    print(f"[duplex] {reason}")
    if idx is not None and int(devices[idx].get("max_input_channels") or 0) > 0:
        return idx
    return None


class DeepgramDuplex:
    """Continuous mic → Deepgram stream with interim + final transcript callbacks.

    Runs in its own daemon thread with a private asyncio loop. Reconnects with
    backoff on transient socket loss; flags itself fatal on auth failures so
    the caller can fall back to the classic recognizer.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "nova-2",
        language: str = "en-US",
        endpointing_ms: int = 300,
        mic_prefer: str = "",
        allow_virtual_mic: bool = False,
        on_final: Callable[[str], None],
        on_interim: Callable[[str], None] | None = None,
        on_speech_started: Callable[[], None] | None = None,
        on_level: Callable[[float], None] | None = None,
        should_send: Callable[[], bool] | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model = model or "nova-2"
        self.language = language
        self.endpointing_ms = max(100, int(endpointing_ms))
        self.mic_prefer = mic_prefer
        self.allow_virtual_mic = allow_virtual_mic
        self.on_final = on_final
        self.on_interim = on_interim
        self.on_speech_started = on_speech_started
        self.on_level = on_level
        self.should_send = should_send or (lambda: True)

        self._running = False
        self._fatal = ""
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._audio_q: asyncio.Queue[bytes] | None = None
        self._segment_parts: list[str] = []

    # ---------------------------------------------------------------- public

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._fatal = ""
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="jarvis-duplex"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    @property
    def fatal_error(self) -> str:
        """Non-empty when the stream died unrecoverably (bad key, no mic)."""
        return self._fatal

    def is_alive(self) -> bool:
        return self._running and not self._fatal

    # -------------------------------------------------------------- internals

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as e:
            self._fatal = self._fatal or f"duplex loop crashed: {e}"
            print(f"[duplex] {self._fatal}")
        finally:
            self._running = False

    def _url(self) -> str:
        params = (
            f"model={self.model}"
            f"&language={self.language}"
            "&encoding=linear16"
            f"&sample_rate={SAMPLE_RATE}"
            "&channels=1"
            "&punctuate=true"
            "&smart_format=true"
            "&interim_results=true"
            f"&endpointing={self.endpointing_ms}"
            "&vad_events=true"
            "&utterance_end_ms=1200"
        )
        return f"wss://api.deepgram.com/v1/listen?{params}"

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._audio_q = asyncio.Queue(maxsize=64)

        stream = self._open_mic()
        if stream is None:
            self._fatal = "no usable input device"
            return
        try:
            with stream:
                backoff = 1.0
                failures = 0
                while self._running:
                    try:
                        await self._session()
                        backoff = 1.0
                        failures = 0
                    except Exception as e:
                        if self._fatal or not self._running:
                            return
                        failures += 1
                        if failures > RECONNECT_MAX:
                            self._fatal = f"gave up reconnecting: {e}"
                            print(f"[duplex] {self._fatal}")
                            return
                        print(
                            f"[duplex] socket lost ({failures}/{RECONNECT_MAX}), "
                            f"retry in {backoff:.0f}s: {e}"
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 15.0)
        finally:
            self._loop = None

    def _open_mic(self):
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as e:
            self._fatal = f"audio deps missing: {e}"
            return None

        blocksize = SAMPLE_RATE * BLOCK_MS // 1000
        device = pick_input_device(
            self.mic_prefer, allow_virtual=self.allow_virtual_mic
        )

        def _callback(indata, _frames, _time_info, _status) -> None:
            # PortAudio thread — hand PCM to the asyncio loop, never block.
            loop, q = self._loop, self._audio_q
            if loop is None or q is None or not self._running:
                return
            pcm = np.asarray(indata)
            if self.on_level is not None:
                try:
                    mono = pcm.reshape(-1).astype(np.float32) / 32768.0
                    rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
                    self.on_level(min(1.0, rms * 9.0))
                except Exception:
                    pass
            data = pcm.tobytes()

            def _put() -> None:
                try:
                    q.put_nowait(data)
                except asyncio.QueueFull:
                    pass  # drop oldest-style backpressure — latency over completeness

            try:
                loop.call_soon_threadsafe(_put)
            except RuntimeError:
                pass  # loop shutting down

        for dev in (device, None):
            try:
                stream = sd.InputStream(
                    device=dev,
                    channels=1,
                    samplerate=SAMPLE_RATE,
                    blocksize=blocksize,
                    dtype="int16",
                    callback=_callback,
                )
                label = f"[{dev}]" if dev is not None else "[default]"
                print(f"[duplex] mic stream open {label}")
                return stream
            except Exception as e:
                print(f"[duplex] mic open failed device={dev}: {e}")
        return None

    async def _connect(self):
        import websockets

        headers = {"Authorization": f"Token {self.api_key}"}
        try:
            return await websockets.connect(
                self._url(), additional_headers=headers, max_size=2**22
            )
        except TypeError:
            # websockets < 13 uses extra_headers
            return await websockets.connect(
                self._url(), extra_headers=headers, max_size=2**22
            )

    async def _session(self) -> None:
        try:
            ws = await self._connect()
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(
                getattr(e, "response", None), "status_code", None
            )
            if status in (400, 401, 402, 403):
                self._fatal = f"deepgram rejected connection (HTTP {status}) — check key"
                print(f"[duplex] {self._fatal}")
            raise
        print("[duplex] deepgram stream connected")
        self._segment_parts = []
        try:
            sender = asyncio.create_task(self._send_audio(ws))
            receiver = asyncio.create_task(self._receive(ws))
            done, pending = await asyncio.wait(
                {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
        finally:
            try:
                await ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass

    async def _send_audio(self, ws) -> None:
        assert self._audio_q is not None
        last_sent = time.time()
        while self._running:
            try:
                chunk = await asyncio.wait_for(self._audio_q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                chunk = b""
            gate_open = True
            try:
                gate_open = bool(self.should_send())
            except Exception:
                pass
            if chunk and gate_open:
                await ws.send(chunk)
                last_sent = time.time()
            elif time.time() - last_sent > KEEPALIVE_SEC:
                await ws.send(json.dumps({"type": "KeepAlive"}))
                last_sent = time.time()

    async def _receive(self, ws) -> None:
        async for raw in ws:
            if not self._running:
                return
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            kind = msg.get("type", "")
            if kind == "SpeechStarted":
                if self.on_speech_started is not None:
                    try:
                        self.on_speech_started()
                    except Exception:
                        pass
                continue
            if kind == "UtteranceEnd":
                self._flush_segment()
                continue
            if kind != "Results":
                continue
            alts = (msg.get("channel") or {}).get("alternatives") or []
            text = (alts[0].get("transcript") or "").strip() if alts else ""
            if not text:
                continue
            if msg.get("is_final"):
                self._segment_parts.append(text)
                if msg.get("speech_final"):
                    self._flush_segment()
            elif self.on_interim is not None:
                try:
                    self.on_interim(text)
                except Exception:
                    pass

    def _flush_segment(self) -> None:
        if not self._segment_parts:
            return
        utterance = " ".join(self._segment_parts).strip()
        self._segment_parts = []
        if not utterance:
            return
        try:
            self.on_final(utterance)
        except Exception as e:
            print(f"[duplex] on_final: {e}")

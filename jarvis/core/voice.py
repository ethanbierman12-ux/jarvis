"""Voice I/O — clear listening, mute-while-speaking, no echo repeats."""

from __future__ import annotations

import collections
import difflib
import math
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from jarvis.config import DATA_DIR


class ThoughtStream:
    """Rolling buffer of recent utterances for 'actually, wait / do that' context."""

    def __init__(self, seconds: float = 5.0) -> None:
        self._buf: collections.deque[tuple[float, str]] = collections.deque()
        self._seconds = seconds

    def push(self, text: str) -> None:
        now = time.time()
        self._buf.append((now, text))
        self._trim(now)

    def recent(self) -> list[str]:
        self._trim(time.time())
        return [t for _, t in self._buf]

    def _trim(self, now: float) -> None:
        while self._buf and now - self._buf[0][0] > self._seconds:
            self._buf.popleft()


class VoiceEngine:
    def __init__(
        self,
        on_heard: Callable[[str], None],
        voice: str = "en-GB-ThomasNeural",
        rate: str = "-8%",
        pitch: str = "-4Hz",
        volume: str = "+0%",
        noise_reduce: bool = True,
        mic_prefer: str = "EMEET",
        on_level: Callable[[float], None] | None = None,
        on_speaking: Callable[[bool], None] | None = None,
        elevenlabs_api_key: str = "",
        elevenlabs_voice_id: str = "pNInz6obpgDQ51uIfY1H",
        elevenlabs_model: str = "eleven_monolingual_v1",
        allow_virtual_mic: bool = False,
        prefer_elevenlabs: bool = False,
        deepgram_api_key: str = "",
        deepgram_model: str = "nova-2",
        duplex_enabled: bool = True,
    ) -> None:
        self.on_heard = on_heard
        self.on_level = on_level
        self.on_speaking = on_speaking
        # Classic Jarvis = British Edge neural; never silently fall to US voices
        v = (voice or "").strip() or "en-GB-ThomasNeural"
        if not v.lower().startswith("en-gb") and "neural" in v.lower():
            # Non-British Neural voices sound wrong for Jarvis — coerce
            if v.lower().startswith("en-us") or "guy" in v.lower() or "aria" in v.lower():
                v = "en-GB-ThomasNeural"
        self.voice = v if v else "en-GB-ThomasNeural"
        self.rate = rate or "-8%"
        self.pitch = pitch or "-4Hz"
        self.volume = volume or "+0%"
        self.noise_reduce = noise_reduce
        self.mic_prefer = mic_prefer
        self.allow_virtual_mic = allow_virtual_mic
        self.elevenlabs_api_key = (elevenlabs_api_key or "").strip()
        self.elevenlabs_voice_id = elevenlabs_voice_id or "pNInz6obpgDQ51uIfY1H"
        self.elevenlabs_model = elevenlabs_model or "eleven_monolingual_v1"
        # Default off — Adam/US ElevenLabs breaks the Jarvis British feel
        self.prefer_elevenlabs = bool(prefer_elevenlabs)
        # Duplex streaming STT (Deepgram) — sub-300ms finals + real barge-in
        self.deepgram_api_key = (deepgram_api_key or "").strip()
        self.deepgram_model = deepgram_model or "nova-2"
        self.duplex_enabled = bool(duplex_enabled)
        self._duplex = None
        self.stream = ThoughtStream(5.0)
        self._running = False
        self._mute = False
        self._speaking = False
        self._speak_until = 0.0
        self._barge_after = 0.0  # ignore barge-in until this timestamp
        self._barge_hits = 0  # consecutive loud frames required
        self._thread: threading.Thread | None = None
        self._level_thread: threading.Thread | None = None
        self._speak_lock = threading.Lock()
        self._tts_dir = DATA_DIR / "tts"
        self._tts_dir.mkdir(parents=True, exist_ok=True)
        self._last_heard = ""
        self._last_heard_at = 0.0
        self._last_spoken = ""
        self._last_spoken_at = 0.0
        self._busy = False  # processing a command — ignore new speech
        self._level = 0.0
        self._barge_armed = True

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="jarvis-voice"
        )
        self._thread.start()
        self._level_thread = threading.Thread(
            target=self._level_loop, daemon=True, name="jarvis-mic-level"
        )
        self._level_thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_playback()

    def mute_mic(self, muted: bool) -> None:
        self._mute = muted

    def set_busy(self, busy: bool) -> None:
        """While True, ignore new transcripts (avoids double-fires mid-command)."""
        self._busy = bool(busy)

    def barge_in(self) -> None:
        """Interrupt Jarvis mid-sentence — stop TTS and reopen the mic."""
        # Grace window after TTS starts — EMEET easily false-triggers on speakers
        if time.time() < float(getattr(self, "_barge_after", 0) or 0):
            return
        self._stop_playback()
        self._speaking = False
        self._mute = False
        self._speak_until = 0.0
        self._busy = False
        self._barge_hits = 0
        print("[voice] barge-in — TTS stopped")
        self._emit_speaking(False)

    def _emit_speaking(self, active: bool) -> None:
        cb = getattr(self, "on_speaking", None)
        if not cb:
            return
        try:
            cb(bool(active))
        except Exception as e:
            print(f"[voice] on_speaking: {e}")

    def level(self) -> float:
        return float(self._level)

    def say(self, text: str) -> None:
        text = self._jarvis_delivery(" ".join((text or "").split()))
        if not text:
            return
        # Drop identical / near-identical TTS spam within 12s
        now = time.time()
        if self._last_spoken and now - self._last_spoken_at < 12.0:
            if text.lower() == self._last_spoken.lower():
                return
            if difflib.SequenceMatcher(
                None, text.lower(), self._last_spoken.lower()
            ).ratio() >= 0.85:
                return
        threading.Thread(
            target=self._tts, args=(text,), daemon=True, name="jarvis-tts"
        ).start()

    def say_wait(self, text: str, *, polish: bool = False) -> None:
        """Block until TTS finishes — used for Alexa Echo voice relay."""
        raw = " ".join((text or "").split())
        if not raw:
            return
        spoken = self._jarvis_delivery(raw) if polish else raw
        self._tts(spoken)

    def _jarvis_delivery(self, text: str) -> str:
        """Polish wording so TTS lands closer to film JARVIS cadence."""
        if not text:
            return ""
        # Soften slang / Americanisms that break the butler register — skip tiny acks
        if len(text) < 48:
            return text
        swaps = (
            (r"\bGot it\b", "Very good"),
            (r"\bOn it\b", "Working on it now"),
            (r"\bOkay\b", "Very well"),
            (r"\bOK\b", "Very well"),
            (r"\bYeah\b", "Yes"),
            (r"\bNope\b", "No"),
            (r"\bHey\b", "Hello"),
            (r"\bWhat's up\b", "How may I help"),
            (r"\bCommand center online\b", "All systems are online"),
            (r"\bStarting\.\b", "Starting systems now."),
            (r"\bStarting\b", "Engaging"),
        )
        out = text
        for pat, rep in swaps:
            out = re.sub(pat, rep, out, flags=re.IGNORECASE)
        # Prefer "Sir" cadence pauses: commas help Edge TTS breathe
        out = re.sub(r"\s{2,}", " ", out).strip()
        # Cap runaway briefings so the voice stays composed — allow full thoughts
        if len(out) > 900:
            cut = out[:900]
            if "." in cut:
                cut = cut.rsplit(".", 1)[0] + "."
            out = cut
        return out

    def _stop_playback(self) -> None:
        try:
            import pygame

            if pygame.mixer.get_init():
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
        except Exception:
            pass

    def _tts(self, text: str) -> None:
        with self._speak_lock:
            out: Path | None = None
            # Mute BEFORE generating so we never hear our own voice
            self._speaking = True
            self._mute = True
            self._barge_hits = 0
            # Ignore barge for first 1.2s — calibration / echo spike
            self._barge_after = time.time() + 1.2
            self._last_spoken = text
            self._last_spoken_at = time.time()
            self._emit_speaking(True)
            try:
                self._stop_playback()
                out = self._tts_dir / f"speak_{uuid.uuid4().hex}.mp3"
                # Prefer Edge British Jarvis; ElevenLabs only when explicitly opted in
                use_eleven = (
                    bool(self.prefer_elevenlabs)
                    and bool(self.elevenlabs_api_key)
                    and len(text) >= 120
                )
                if use_eleven:
                    if not self._tts_elevenlabs(text, out):
                        self._tts_edge(text, out)
                else:
                    self._tts_edge(text, out)
                if out.exists() and out.stat().st_size > 0:
                    self._play(out)
            except Exception as e:
                print(f"[tts] {e}")
            finally:
                # Echo-guard mute so mic doesn't eat the end of the sentence
                self._speak_until = time.time() + 0.85
                self._speaking = False
                self._mute = False
                self._barge_hits = 0
                self._emit_speaking(False)
                if out and out.exists():

                    def _cleanup(path: Path) -> None:
                        time.sleep(0.5)
                        try:
                            path.unlink(missing_ok=True)
                        except Exception:
                            pass

                    threading.Thread(
                        target=_cleanup, args=(out,), daemon=True
                    ).start()
                try:
                    for old in self._tts_dir.glob("speak_*.mp3"):
                        if old != out and time.time() - old.stat().st_mtime > 30:
                            old.unlink(missing_ok=True)
                except Exception:
                    pass

    def _tts_elevenlabs(self, text: str, out: Path) -> bool:
        """Stream ElevenLabs TTS to a file. Returns True on success."""
        key = self.elevenlabs_api_key
        if not key or key in ("YOUR_ELEVENLABS_API_KEY", "changeme"):
            return False
        try:
            import requests

            url = (
                f"https://api.elevenlabs.io/v1/text-to-speech/"
                f"{self.elevenlabs_voice_id}"
            )
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": key,
            }
            payload = {
                "text": text,
                "model_id": self.elevenlabs_model,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code != 200 or not resp.content:
                print(f"[tts] elevenlabs HTTP {resp.status_code}")
                return False
            out.write_bytes(resp.content)
            return True
        except Exception as e:
            print(f"[tts] elevenlabs fallback: {e}")
            return False

    def _tts_edge(self, text: str, out: Path) -> None:
        import asyncio
        import edge_tts

        async def _gen():
            communicate = edge_tts.Communicate(
                text,
                self.voice,
                rate=self.rate,
                pitch=self.pitch,
                volume=self.volume,
            )
            await communicate.save(str(out))

        asyncio.run(_gen())

    def _play(self, path: Path) -> None:
        try:
            import pygame

            if not pygame.mixer.get_init():
                # Larger buffer + 44.1k avoids choppy / early-stop with Edge MP3
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            self._stop_playback()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            # get_busy() can flicker False on MP3 — require sustained idle
            idle = 0
            t0 = time.time()
            while self._running:
                if not self._speaking:
                    break  # barge-in cleared speaking
                if pygame.mixer.music.get_busy():
                    idle = 0
                    # Drive HUD core with a speech-like envelope while audio plays
                    env = 0.35 + 0.55 * abs(math.sin(time.time() * 9.5))
                    env *= 0.55 + 0.45 * abs(math.sin(time.time() * 3.1))
                    if self.on_level:
                        try:
                            self.on_level(float(env))
                        except Exception:
                            pass
                else:
                    idle += 1
                    if idle >= 8:  # ~400ms consecutive idle = truly done
                        break
                time.sleep(0.05)
            # Don't leave a stuck peak on the reactor after voice ends
            if self.on_level:
                try:
                    self.on_level(0.0)
                except Exception:
                    pass
            _ = t0
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
        except Exception as e:
            print(f"[audio] {e}")

    def _pick_mic_index(self) -> int | None:
        """Prefer physical mics; never bind STT to desktop loopback / Voicemeeter outs."""
        try:
            import speech_recognition as sr

            names = sr.Microphone.list_microphone_names() or []
        except Exception:
            return None
        from jarvis.core.audio_isolation import pick_isolated_mic_index, rank_mic_candidates

        allow_virtual = bool(getattr(self, "allow_virtual_mic", False))
        idx, reason = pick_isolated_mic_index(
            list(names),
            prefer=self.mic_prefer or "",
            allow_virtual=allow_virtual,
        )
        print(f"[voice] {reason}")
        # Keep ranked fallbacks for open-retry (dead WASAPI duplicates are common)
        self._mic_fallbacks = rank_mic_candidates(
            list(names),
            prefer=self.mic_prefer or "",
            allow_virtual=allow_virtual,
        )
        return idx

    def _open_microphone(self, sr_mod):
        """Try preferred index, then ranked fallbacks until PyAudio opens a stream."""
        primary = self._pick_mic_index()
        tried: set[int | None] = set()
        order: list[int | None] = []
        if primary is not None:
            order.append(primary)
        for i, _name in getattr(self, "_mic_fallbacks", []) or []:
            if i not in order:
                order.append(i)
        order.append(None)  # system default last

        last_err: Exception | None = None
        for idx in order:
            if idx in tried:
                continue
            tried.add(idx)
            try:
                mic = (
                    sr_mod.Microphone(device_index=idx)
                    if idx is not None
                    else sr_mod.Microphone()
                )
                # Validate stream opens
                with mic as source:
                    if getattr(source, "stream", None) is None:
                        raise RuntimeError("stream is None")
                label = f"[{idx}]" if idx is not None else "[default]"
                print(f"[voice] mic open ok {label}")
                return mic
            except Exception as e:
                last_err = e
                print(f"[voice] mic open failed idx={idx}: {e}")
        raise RuntimeError(f"no openable microphone ({last_err})")

    def _should_ignore(self, text: str) -> bool:
        t = text.lower().strip()
        if len(t) < 2:
            return True
        now = time.time()

        # Exact / near-duplicate of what we just heard
        if self._last_heard and now - self._last_heard_at < 2.2:
            ratio = difflib.SequenceMatcher(None, t, self._last_heard).ratio()
            if ratio >= 0.82:
                return True

        # Echo of what Jarvis just said
        if self._last_spoken and now - self._last_spoken_at < 6.0:
            spoken = self._last_spoken.lower()
            ratio = difflib.SequenceMatcher(None, t, spoken).ratio()
            if ratio >= 0.55:
                return True
            # Partial echo — heard phrase contained in spoken reply
            if len(t) >= 8 and t in spoken:
                return True
            # Common TTS crumbs
            crumbs = (
                "at your service",
                "consider it handled",
                "done.",
                "as you wish",
                "right away",
                "queuing that",
                "scanning",
                "fascinating",
                "one moment",
                "systems are primed",
                "jarvis online",
                "pressed play",
                "press play",
                "playing your music",
                "i'm listening",
                "still listening",
                "got it — keep talking",
                "could you rephrase",
                "please say again",
                "i did not quite catch",
                "try scan",
                "i'm with you",
                "still here",
                "listening",
                "panic mode off",
                "microphone live",
                "core restored",
            )
            if any(c in t for c in crumbs) and any(c in spoken for c in crumbs):
                return True

        return False

    def _listen_loop(self) -> None:
        # Prefer the duplex Deepgram stream when configured; classic chunked
        # recognition remains the fallback (and the recovery path).
        if self._duplex_available():
            try:
                self._listen_duplex()
            except Exception as e:
                print(f"[voice] duplex failed — falling back to classic STT: {e}")
            if not self._running:
                return
            print("[voice] duplex offline — classic STT engaged")

        try:
            import speech_recognition as sr
        except Exception as e:
            print(f"[voice] speech_recognition missing: {e}")
            return

        recognizer = sr.Recognizer()
        # Sensitive enough for headset boom mics
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = 110
        recognizer.dynamic_energy_adjustment_damping = 0.15
        recognizer.dynamic_energy_ratio = 1.3
        recognizer.pause_threshold = 0.55
        recognizer.non_speaking_duration = 0.35
        recognizer.phrase_threshold = 0.2

        # Self-healing: if USB mic unplugged mid-session, reopen after backoff
        while self._running:
            try:
                self._listen_session(sr, recognizer)
            except Exception as e:
                print(f"[voice] mic fault — recovering in 2s: {e}")
                time.sleep(2.0)

    def _listen_session(self, sr_mod, recognizer) -> None:
        try:
            mic = self._open_microphone(sr_mod)
        except Exception as e:
            print(f"[voice] no microphone: {e}")
            time.sleep(3.0)
            raise

        print("[voice] calibrating ambient noise…")
        with mic as source:
            try:
                recognizer.adjust_for_ambient_noise(source, duration=0.45)
            except Exception:
                pass
        # Soft floor — headset mics are quieter than desk condensers; keep high enough
        # to reduce false ambient wakes
        recognizer.energy_threshold = max(140, min(320, float(recognizer.energy_threshold)))
        print(f"[voice] listening (energy={recognizer.energy_threshold:.0f})")

        consecutive_hw_errors = 0
        busy_since = 0.0
        while self._running:
            # Stuck-busy watchdog (prevents permanent silence after a crashed command)
            if self._busy and not self._speaking:
                if busy_since <= 0:
                    busy_since = time.time()
                elif time.time() - busy_since > 12.0:
                    print("[voice] busy watchdog — clearing stuck busy flag")
                    self._busy = False
                    busy_since = 0.0
                else:
                    time.sleep(0.05)
                    continue
            else:
                busy_since = 0.0
            # While Jarvis is talking, still listen for barge-in
            if self._mute and not self._speaking:
                time.sleep(0.05)
                continue
            if time.time() < self._speak_until and not self._speaking:
                time.sleep(0.05)
                continue
            # During TTS: never STT — speaker echo on EMEET caused mid-sentence cuts
            if self._speaking:
                time.sleep(0.08)
                continue
            try:
                with mic as source:
                    audio = recognizer.listen(
                        source, timeout=3.0, phrase_time_limit=6
                    )
                consecutive_hw_errors = 0
                if self._speaking:
                    continue

                if self._mute and not self._speaking:
                    continue

                audio = self._maybe_denoise(audio, sr_mod)
                # Soft noise gate — drop near-silent captures only
                try:
                    import audioop

                    rms = audioop.rms(audio.get_raw_data(), audio.sample_width)
                    self._emit_level(min(1.0, rms / 4000.0))
                    if rms < 90:
                        continue
                except Exception:
                    pass

                text = self._recognize(recognizer, audio)
                if not text:
                    continue
                text = text.lower().strip()
                text = re.sub(r"\s+", " ", text)
                if self._should_ignore(text):
                    print(f"[voice] ignored echo/dup: {text[:60]}")
                    continue

                self._last_heard = text
                self._last_heard_at = time.time()
                self.stream.push(text)
                print(f"[voice] heard: {text}")
                self.on_heard(text)
            except sr_mod.WaitTimeoutError:
                consecutive_hw_errors = 0
                continue
            except OSError as e:
                consecutive_hw_errors += 1
                print(f"[voice] hardware OSError ({consecutive_hw_errors}): {e}")
                if consecutive_hw_errors >= 3:
                    raise
                time.sleep(0.5)
            except Exception as e:
                msg = str(e).lower()
                # Device lost / invalid handle → force session restart
                if any(
                    k in msg
                    for k in (
                        "invalid",
                        "device",
                        "stream",
                        "input",
                        "portaudio",
                        "pyaudio",
                        "errno",
                    )
                ):
                    consecutive_hw_errors += 1
                    print(f"[voice] device error ({consecutive_hw_errors}): {e}")
                    if consecutive_hw_errors >= 2:
                        raise
                    time.sleep(0.8)
                    continue
                continue

    # ------------------------------------------------------------ duplex STT

    def _duplex_available(self) -> bool:
        if not (self.duplex_enabled and self.deepgram_api_key):
            return False
        from jarvis.core.duplex_voice import duplex_deps_ok

        ok, reason = duplex_deps_ok()
        if not ok:
            print(f"[voice] duplex unavailable — {reason}")
        return ok

    def _listen_duplex(self) -> None:
        """Full-duplex session: continuous stream, transcript barge-in."""
        from jarvis.core.duplex_voice import DeepgramDuplex

        def _should_send() -> bool:
            # Keep streaming while Jarvis talks (barge-in); stop only on
            # explicit mic mute or engine shutdown.
            if not self._running:
                return False
            if self._mute and not self._speaking:
                return False
            return True

        duplex = DeepgramDuplex(
            self.deepgram_api_key,
            model=self.deepgram_model,
            mic_prefer=self.mic_prefer or "",
            allow_virtual_mic=bool(self.allow_virtual_mic),
            on_final=self._on_duplex_final,
            on_interim=self._on_duplex_interim,
            on_level=self._on_duplex_level,
            should_send=_should_send,
        )
        self._duplex = duplex
        duplex.start()
        print("[voice] duplex STT online (deepgram)")
        busy_since = 0.0
        try:
            while self._running and duplex.is_alive():
                # Stuck-busy watchdog — mirrors the classic loop's protection
                if self._busy and not self._speaking:
                    if busy_since <= 0:
                        busy_since = time.time()
                    elif time.time() - busy_since > 12.0:
                        print("[voice] busy watchdog — clearing stuck busy flag")
                        self._busy = False
                        busy_since = 0.0
                else:
                    busy_since = 0.0
                time.sleep(0.1)
        finally:
            duplex.stop()
            self._duplex = None
        if duplex.fatal_error:
            print(f"[voice] duplex fatal: {duplex.fatal_error}")

    def _on_duplex_level(self, level: float) -> None:
        if not self._speaking:
            self._emit_level(level)
        else:
            self._level = max(0.0, min(1.0, float(level)))

    def _on_duplex_final(self, text: str) -> None:
        text = re.sub(r"\s+", " ", (text or "").lower().strip())
        if not text:
            return
        if self._speaking:
            # Talking over Jarvis with a real (non-echo) utterance: interrupt
            # AND act on it — that is the whole point of duplex.
            if self._sounds_like_echo(text) or time.time() < self._barge_after:
                return
            self.barge_in()
        elif self._mute or self._busy:
            return
        elif time.time() < self._speak_until and self._sounds_like_echo(text):
            return
        if self._should_ignore(text):
            print(f"[voice] ignored echo/dup: {text[:60]}")
            return
        self._last_heard = text
        self._last_heard_at = time.time()
        self.stream.push(text)
        print(f"[voice] heard: {text}")
        try:
            self.on_heard(text)
        except Exception as e:
            print(f"[voice] on_heard: {e}")

    def _on_duplex_interim(self, text: str) -> None:
        # Barge-in on interim transcripts — fires mid-sentence, no level gate
        if not self._speaking or not self._barge_armed:
            return
        if time.time() < float(getattr(self, "_barge_after", 0) or 0):
            return
        t = (text or "").lower().strip()
        if len(t.split()) < 2:
            return  # single-word blips are usually speaker bleed
        if self._sounds_like_echo(t):
            return
        print(f"[voice] barge-in via transcript: {t[:50]}")
        self.barge_in()

    def _sounds_like_echo(self, text: str) -> bool:
        """Does this transcript look like the mic hearing Jarvis's own TTS?"""
        if not self._last_spoken:
            return False
        if time.time() - self._last_spoken_at > 25.0:
            return False
        spoken = self._last_spoken.lower()
        t = (text or "").lower().strip()
        if not t:
            return True
        if len(t) >= 8 and t in spoken:
            return True
        ratio = difflib.SequenceMatcher(None, t, spoken).ratio()
        if ratio >= 0.5:
            return True
        # Fragment echo — most words of the heard text appear in the reply
        words = [w for w in t.split() if len(w) > 2]
        if words:
            hits = sum(1 for w in words if w in spoken)
            if hits / len(words) >= 0.7:
                return True
        return False

    def _emit_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, float(level)))
        if self.on_level:
            try:
                self.on_level(self._level)
            except Exception:
                pass

    def _level_loop(self) -> None:
        """Mic RMS for HUD waves — low-rate sampling to spare CPU."""
        try:
            import numpy as np
            import sounddevice as sd
        except Exception:
            return
        try:
            with sd.InputStream(
                channels=1,
                samplerate=16000,
                blocksize=2048,
                dtype="float32",
            ) as stream:
                while self._running:
                    try:
                        data, _overflow = stream.read(2048)
                        mono = np.asarray(data, dtype=np.float32).reshape(-1)
                        rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
                        if rms < 0.008:
                            rms = 0.0
                        level = min(1.0, rms * 9.0)
                        # While Jarvis talks, core amp comes from TTS envelope — don't stomp it
                        if not self._speaking:
                            self._emit_level(level)
                        else:
                            self._level = level  # still track for barge
                        # Barge-in: sustained loud speech only (not speaker bleed)
                        if (
                            self._speaking
                            and self._barge_armed
                            and time.time() >= float(getattr(self, "_barge_after", 0) or 0)
                        ):
                            if level > 0.72:
                                self._barge_hits = int(getattr(self, "_barge_hits", 0)) + 1
                                if self._barge_hits >= 5:  # ~0.4s sustained
                                    self.barge_in()
                            else:
                                self._barge_hits = 0
                        else:
                            self._barge_hits = 0
                        time.sleep(0.12 if self._speaking else 0.22)
                    except Exception:
                        time.sleep(0.15)
        except Exception as e:
            print(f"[voice] level meter offline: {e}")

    def _maybe_denoise(self, audio, sr_mod):
        if not self.noise_reduce:
            return audio
        try:
            import numpy as np
            import noisereduce as nr

            raw = np.frombuffer(audio.get_raw_data(), dtype=np.int16).astype(np.float32)
            if raw.size < 800:
                return audio
            reduced = nr.reduce_noise(y=raw, sr=audio.sample_rate, prop_decrease=0.7)
            reduced = np.clip(reduced, -32768, 32767).astype(np.int16)
            return sr_mod.AudioData(reduced.tobytes(), audio.sample_rate, audio.sample_width)
        except Exception:
            return audio

    def _recognize(self, recognizer, audio) -> str:
        # Google is usually clearest; fall back quietly
        try:
            return recognizer.recognize_google(audio, language="en-US") or ""
        except Exception:
            pass
        try:
            return recognizer.recognize_google(audio) or ""
        except Exception:
            return ""

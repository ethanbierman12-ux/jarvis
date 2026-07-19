"""Voice I/O — clear listening, mute-while-speaking, no echo repeats."""

from __future__ import annotations

import collections
import difflib
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
    ) -> None:
        self.on_heard = on_heard
        self.on_level = on_level
        self.voice = voice or "en-GB-ThomasNeural"
        self.rate = rate or "-8%"
        self.pitch = pitch or "-4Hz"
        self.volume = volume or "+0%"
        self.noise_reduce = noise_reduce
        self.mic_prefer = mic_prefer
        self.stream = ThoughtStream(5.0)
        self._running = False
        self._mute = False
        self._speaking = False
        self._speak_until = 0.0
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
        self._stop_playback()
        self._speaking = False
        self._mute = False
        self._speak_until = 0.0
        self._busy = False
        print("[voice] barge-in — TTS stopped")

    def level(self) -> float:
        return float(self._level)

    def say(self, text: str) -> None:
        text = self._jarvis_delivery(" ".join((text or "").split()))
        if not text:
            return
        # Drop identical / near-identical TTS spam within 8s
        now = time.time()
        if self._last_spoken and now - self._last_spoken_at < 8.0:
            if text.lower() == self._last_spoken.lower():
                return
            if difflib.SequenceMatcher(
                None, text.lower(), self._last_spoken.lower()
            ).ratio() >= 0.88:
                return
        threading.Thread(
            target=self._tts, args=(text,), daemon=True, name="jarvis-tts"
        ).start()

    def _jarvis_delivery(self, text: str) -> str:
        """Polish wording so TTS lands closer to film JARVIS cadence."""
        if not text:
            return ""
        # Soften slang / Americanisms that break the butler register
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
        # Cap runaway briefings so the voice stays composed
        if len(out) > 420:
            cut = out[:420]
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
            self._last_spoken = text
            self._last_spoken_at = time.time()
            try:
                import asyncio
                import edge_tts

                out = self._tts_dir / f"speak_{uuid.uuid4().hex}.mp3"
                self._stop_playback()

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
                self._play(out)
            except Exception as e:
                print(f"[tts] {e}")
            finally:
                # Keep mic muted briefly after speech so room echo dies out
                self._speak_until = time.time() + 0.85
                self._speaking = False
                self._mute = False
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

    def _play(self, path: Path) -> None:
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=512)
            self._stop_playback()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and self._running:
                time.sleep(0.05)
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
        except Exception as e:
            print(f"[audio] {e}")

    def _pick_mic_index(self) -> int | None:
        """Prefer EMEET / USB headset mics over random defaults."""
        try:
            import speech_recognition as sr

            names = sr.Microphone.list_microphone_names() or []
        except Exception:
            return None
        prefer = (self.mic_prefer or "").upper().strip()
        # Empty prefer → system default mic (device_index None)
        if not prefer or prefer in ("DEFAULT", "SYSTEM", "ANY"):
            print("[voice] using system default microphone")
            return None
        scored: list[tuple[float, int, str]] = []
        for i, name in enumerate(names):
            n = (name or "").upper()
            score = 0.0
            if prefer and prefer in n:
                score += 100
            if "EMEET" in n and "EMEET" in prefer:
                score += 80
            if any(k in n for k in ("HEADSET", "USB", "ARRAY", "STUDIO", "MICROPHONE")):
                score += 20
            if any(k in n for k in ("MAPPER", "STEREO MIX", "CABLE", "VIRTUAL", "WHAT U HEAR")):
                score -= 100
            if score > 0:
                scored.append((score, i, name))
        if not scored:
            print(f"[voice] mics: {len(names)} devices — using default")
            return None
        scored.sort(reverse=True)
        best = scored[0]
        print(f"[voice] using mic [{best[1]}] {best[2]}")
        return best[1]

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
        try:
            import speech_recognition as sr
        except Exception as e:
            print(f"[voice] speech_recognition missing: {e}")
            return

        recognizer = sr.Recognizer()
        # Tuned for clear speech in a desk room (not too sensitive to PC noise)
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = 280
        recognizer.dynamic_energy_adjustment_damping = 0.15
        recognizer.dynamic_energy_ratio = 1.5
        recognizer.pause_threshold = 0.75
        recognizer.non_speaking_duration = 0.45
        recognizer.phrase_threshold = 0.25

        idx = self._pick_mic_index()
        try:
            mic = sr.Microphone(device_index=idx) if idx is not None else sr.Microphone()
        except Exception as e:
            print(f"[voice] no microphone: {e}")
            return

        print("[voice] calibrating ambient noise…")
        with mic as source:
            try:
                recognizer.adjust_for_ambient_noise(source, duration=1.2)
            except Exception:
                pass
        # Floor so quiet rooms don't pick up every fan tick
        recognizer.energy_threshold = max(250, float(recognizer.energy_threshold))
        print(f"[voice] listening (energy={recognizer.energy_threshold:.0f})")

        while self._running:
            if self._busy and not self._speaking:
                time.sleep(0.05)
                continue
            # While Jarvis is talking, still listen for barge-in
            if self._mute and not self._speaking:
                time.sleep(0.05)
                continue
            if time.time() < self._speak_until and not self._speaking:
                time.sleep(0.05)
                continue
            try:
                with mic as source:
                    audio = recognizer.listen(
                        source, timeout=2.5, phrase_time_limit=8
                    )
                # Barge-in: user spoke over TTS
                if self._speaking:
                    self.barge_in()

                if self._mute and not self._speaking:
                    continue

                audio = self._maybe_denoise(audio, sr)
                # Soft noise gate — drop near-silent captures
                try:
                    import audioop

                    rms = audioop.rms(audio.get_raw_data(), audio.sample_width)
                    self._emit_level(min(1.0, rms / 4000.0))
                    if rms < max(180, recognizer.energy_threshold * 0.35):
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
            except Exception:
                continue

    def _emit_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, float(level)))
        if self.on_level:
            try:
                self.on_level(self._level)
            except Exception:
                pass

    def _level_loop(self) -> None:
        """Always-on mic RMS for HUD waves (independent of STT)."""
        try:
            import numpy as np
            import sounddevice as sd
        except Exception:
            return
        try:
            with sd.InputStream(
                channels=1,
                samplerate=16000,
                blocksize=1024,
                dtype="float32",
            ) as stream:
                while self._running:
                    try:
                        data, _overflow = stream.read(1024)
                        mono = np.asarray(data, dtype=np.float32).reshape(-1)
                        rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
                        # Noise gate floor
                        if rms < 0.008:
                            rms = 0.0
                        level = min(1.0, rms * 9.0)
                        self._emit_level(level)
                        # Energy spike while speaking → interrupt
                        if self._speaking and self._barge_armed and level > 0.35:
                            self.barge_in()
                    except Exception:
                        time.sleep(0.05)
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

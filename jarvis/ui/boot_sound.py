"""Cinematic boot / loading audio for Jarvis INIT sequence."""

from __future__ import annotations

import math
import queue
import struct
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Callable

from jarvis.config import ASSETS_DIR

BOOT_WAV = ASSETS_DIR / "boot_loading_v3.wav"

# Sequential TTS — never cut mid-sentence
_speak_q: queue.Queue[tuple[str, Callable[[], None] | None]] = queue.Queue()
_speak_worker_started = False
_speak_lock = threading.Lock()
_speaking = False


def ensure_boot_wav(path: Path | None = None, *, force: bool = False) -> Path:
    """Generate Arwes boot bed: rumble, rising sweep, ticks, resolve chord."""
    path = path or BOOT_WAV
    path.parent.mkdir(parents=True, exist_ok=True)
    if not force and path.exists() and path.stat().st_size > 4000:
        return path

    sr, dur = 44100, 4.0
    n = int(sr * dur)
    frames = bytearray()
    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.22) * (
            1.0 if t < 3.2 else max(0.0, 1.0 - (t - 3.2) / 0.75)
        )
        rumble = 0.13 * math.sin(2 * math.pi * (38 + 8 * t) * t) * env
        sub = 0.07 * env * math.sin(2 * math.pi * 55 * t) * (
            0.5 + 0.5 * math.sin(2 * math.pi * 1.2 * t)
        )
        f = 110 + 1100 * min(1.0, t / 2.8)
        sweep = (
            0.17
            * min(1.0, t / 0.16)
            * max(0.0, 1.0 - max(0.0, t - 2.9) / 0.85)
            * math.sin(2 * math.pi * f * t)
        )
        shimmer = 0.045 * env * math.sin(2 * math.pi * (f * 2.01) * t)
        sparkle = 0.03 * env * math.sin(2 * math.pi * (f * 3.05 + 40) * t)
        tick = 0.0
        phase = (t * 2.4) % 1.0
        if phase < 0.016:
            tick = 0.12 * math.sin(2 * math.pi * 1680 * t) * math.exp(-phase * 90) * env
        mid = 0.0
        if 1.85 <= t < 2.05:
            d = t - 1.85
            mid = 0.1 * math.exp(-d * 14) * math.sin(2 * math.pi * 880 * t)
        resolve = 0.0
        if 3.15 <= t < 3.65:
            d = t - 3.15
            resolve = 0.18 * math.exp(-d * 5) * (
                math.sin(2 * math.pi * 523 * t)
                + 0.55 * math.sin(2 * math.pi * 784 * t)
                + 0.35 * math.sin(2 * math.pi * 1046 * t)
            )
        v = max(
            -1.0,
            min(1.0, rumble + sub + sweep + shimmer + sparkle + tick + mid + resolve),
        )
        frames += struct.pack("<h", int(v * 27000))

    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)
    return path


def play_boot_sound() -> None:
    path = ensure_boot_wav(force=False)
    if path.stat().st_size < 4000:
        path = ensure_boot_wav(force=True)

    def _run() -> None:
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(0.38)  # stay under TTS
            pygame.mixer.music.play()
        except Exception:
            try:
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="boot-sfx").start()


def stop_boot_sound() -> None:
    try:
        import pygame

        if pygame.mixer.get_init():
            pygame.mixer.music.fadeout(380)
    except Exception:
        pass


def _duck_music(vol: float) -> None:
    try:
        import pygame

        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(max(0.0, min(1.0, vol)))
    except Exception:
        pass


def _ensure_speak_worker() -> None:
    global _speak_worker_started
    with _speak_lock:
        if _speak_worker_started:
            return
        _speak_worker_started = True

    def _worker() -> None:
        global _speaking
        while True:
            line, on_done = _speak_q.get()
            try:
                _speaking = True
                _duck_music(0.12)
                _speak_one(line)
            except Exception as e:
                print(f"[boot-tts] {e}")
            finally:
                _duck_music(0.38)
                _speaking = False
                if callable(on_done):
                    try:
                        on_done()
                    except Exception:
                        pass
                _speak_q.task_done()

    threading.Thread(target=_worker, daemon=True, name="boot-tts-queue").start()


def _speak_one(line: str) -> None:
    """Generate + play one line fully — unique file so lines never clobber."""
    import asyncio
    import tempfile
    import edge_tts

    voice = "en-GB-ThomasNeural"
    rate = "+0%"
    try:
        from jarvis.config import Settings

        s = Settings.load()
        voice = getattr(s, "tts_voice", None) or voice
        rate = getattr(s, "tts_rate", None) or rate
    except Exception:
        pass

    out = Path(tempfile.gettempdir()) / f"jarvis_boot_say_{uuid.uuid4().hex}.mp3"

    async def _gen() -> None:
        comm = edge_tts.Communicate(line, voice, rate=rate)
        await comm.save(str(out))

    asyncio.run(_gen())
    if not out.exists() or out.stat().st_size < 100:
        return

    try:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        # Stop any leftover channel speech without killing music
        pygame.mixer.stop()
        snd = pygame.mixer.Sound(str(out))
        snd.set_volume(1.0)
        ch = snd.play()
        # Wait until fully finished (+ small tail so last syllable isn't cut)
        deadline = time.time() + max(1.5, snd.get_length() + 0.55)
        while time.time() < deadline:
            if ch is None or not ch.get_busy():
                # Confirm idle for a few frames
                idle = 0
                while idle < 4 and time.time() < deadline:
                    if ch is not None and ch.get_busy():
                        idle = 0
                    else:
                        idle += 1
                    time.sleep(0.04)
                break
            time.sleep(0.04)
        time.sleep(0.05)  # short breath between lines
    finally:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass


def speak_boot_line(
    text: str, on_done: Callable[[], None] | None = None
) -> None:
    """Queue a boot line — waits its turn so sentences never skip or truncate."""
    line = " ".join((text or "").split())
    if not line:
        if callable(on_done):
            try:
                on_done()
            except Exception:
                pass
        return
    _ensure_speak_worker()
    _speak_q.put((line, on_done))


def speak_boot_clear() -> None:
    """Drop pending lines (e.g. on skip). Current line still finishes."""
    try:
        while True:
            _speak_q.get_nowait()
            _speak_q.task_done()
    except queue.Empty:
        pass


def is_boot_speaking() -> bool:
    return bool(_speaking) or not _speak_q.empty()

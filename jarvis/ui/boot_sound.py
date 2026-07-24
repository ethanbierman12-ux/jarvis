"""Cinematic boot / loading audio for Jarvis INIT sequence."""

from __future__ import annotations

import math
import struct
import threading
import wave
from pathlib import Path

from jarvis.config import ASSETS_DIR

BOOT_WAV = ASSETS_DIR / "boot_loading_v2.wav"


def ensure_boot_wav(path: Path | None = None, *, force: bool = False) -> Path:
    """Generate a smooth loading whoosh + soft reactor hum (Iron Man-ish)."""
    path = path or BOOT_WAV
    path.parent.mkdir(parents=True, exist_ok=True)
    if not force and path.exists() and path.stat().st_size > 2000:
        return path

    sr, dur = 44100, 3.2
    n = int(sr * dur)
    frames = bytearray()
    for i in range(n):
        t = i / sr
        # Smooth envelope — fade in / out
        env = min(1.0, t / 0.25) * (1.0 if t < 2.6 else max(0.0, 1.0 - (t - 2.6) / 0.55))
        # Deep reactor undercurrent
        rumble = 0.14 * math.sin(2 * math.pi * (42 + 6 * t) * t) * env
        # Rising energy sweep
        f = 120 + 920 * min(1.0, t / 2.4)
        sweep = (
            0.18
            * min(1.0, t / 0.18)
            * max(0.0, 1.0 - max(0.0, t - 2.35) / 0.7)
            * math.sin(2 * math.pi * f * t)
        )
        # Soft harmonic shimmer
        shimmer = 0.05 * env * math.sin(2 * math.pi * (f * 2.02) * t)
        # Gentle progress ticks (~every 0.45s)
        tick = 0.0
        phase = (t * 2.2) % 1.0
        if phase < 0.018:
            tick = 0.11 * math.sin(2 * math.pi * 1560 * t) * math.exp(-phase * 80) * env
        # Final resolve chord flick
        resolve = 0.0
        if 2.55 <= t < 2.85:
            d = t - 2.55
            resolve = 0.16 * math.exp(-d * 6) * (
                math.sin(2 * math.pi * 523 * t) + 0.5 * math.sin(2 * math.pi * 784 * t)
            )
        v = max(-1.0, min(1.0, rumble + sweep + shimmer + tick + resolve))
        frames += struct.pack("<h", int(v * 26000))

    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)
    return path


def play_boot_sound() -> None:
    path = ensure_boot_wav(force=False)
    # Refresh if stale tiny file from old generator
    if path.stat().st_size < 2000:
        path = ensure_boot_wav(force=True)

    def _run() -> None:
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(0.62)
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
            pygame.mixer.music.fadeout(320)
    except Exception:
        pass


def speak_boot_line(text: str) -> None:
    """Speak a short line during boot (before Brain is ready) via Edge TTS."""
    line = " ".join((text or "").split())
    if not line:
        return

    def _run() -> None:
        try:
            import asyncio
            import tempfile
            import edge_tts

            voice = "en-GB-ThomasNeural"
            out = Path(tempfile.gettempdir()) / "jarvis_boot_say.mp3"

            async def _gen() -> None:
                comm = edge_tts.Communicate(line, voice)
                await comm.save(str(out))

            asyncio.run(_gen())
            if not out.exists() or out.stat().st_size < 100:
                return
            try:
                import pygame

                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                # Prefer sound channel so we don't stomp boot music mid-file
                snd = pygame.mixer.Sound(str(out))
                snd.set_volume(0.92)
                snd.play()
                # Hold thread until roughly done
                import time as _t

                _t.sleep(min(4.0, snd.get_length() + 0.15))
            except Exception:
                try:
                    import winsound

                    # winsound needs wav — skip if only mp3
                    pass
                except Exception:
                    pass
        except Exception as e:
            print(f"[boot-tts] {e}")

    threading.Thread(target=_run, daemon=True, name="boot-tts").start()

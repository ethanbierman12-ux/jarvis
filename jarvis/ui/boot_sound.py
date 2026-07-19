"""Procedural boot sound for INITIATING SYSTEM sequence."""

from __future__ import annotations

import math
import struct
import threading
import wave
from pathlib import Path

from jarvis.config import ASSETS_DIR

BOOT_WAV = ASSETS_DIR / "boot.wav"


def ensure_boot_wav(path: Path | None = None) -> Path:
    path = path or BOOT_WAV
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 1000:
        return path

    sr, dur = 44100, 5.0
    n = int(sr * dur)
    frames = bytearray()
    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.3) * (1.0 if t < 4.2 else max(0.0, 1.0 - (t - 4.2) / 0.8))
        rumble = 0.16 * math.sin(2 * math.pi * (50 + 10 * t) * t) * env
        f = 160 + 780 * min(1.0, t / 3.5)
        sweep = 0.2 * min(1.0, t / 0.2) * max(0.0, 1.0 - max(0.0, t - 3.5) / 1.0) * math.sin(2 * math.pi * f * t)
        blip = 0.0
        for bt, bf in ((0.4, 880), (1.0, 1100), (1.8, 660), (2.6, 1320), (3.5, 990), (4.3, 520)):
            d = t - bt
            if 0 <= d < 0.07:
                blip += 0.25 * math.exp(-d * 50) * math.sin(2 * math.pi * bf * t)
        # Soft tick every ~0.5s as % climbs
        tick = 0.0
        if abs((t * 2) % 1) < 0.02:
            tick = 0.12 * math.sin(2 * math.pi * 1800 * t) * env
        v = max(-1.0, min(1.0, rumble + sweep + blip + tick))
        frames += struct.pack("<h", int(v * 27000))

    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)
    return path


def play_boot_sound() -> None:
    path = ensure_boot_wav()

    def _run() -> None:
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(0.55)
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
            pygame.mixer.music.fadeout(280)
    except Exception:
        pass

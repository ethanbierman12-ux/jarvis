"""Ambient soundscapes — brown noise / calm loops for focus stress."""

from __future__ import annotations

import threading
import time
from typing import Optional


class Soundscape:
    def __init__(self) -> None:
        self._playing = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mode = ""
        self._volume = 0.18

    @property
    def active(self) -> bool:
        return self._playing

    def play_brown_noise(self, volume: float = 0.18) -> str:
        return self._start("brown", volume, "Low-volume brown noise for focus.")

    def play_calm(self, volume: float = 0.15) -> str:
        return self._start("calm", volume, "Calm ambient tone.")

    def stop(self) -> str:
        self._stop.set()
        self._playing = False
        self._mode = ""
        try:
            import pygame

            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        return "Ambient soundscape stopped."

    def _start(self, mode: str, volume: float, label: str) -> str:
        self.stop()
        self._stop.clear()
        self._mode = mode
        self._volume = max(0.05, min(0.5, volume))
        self._playing = True
        self._thread = threading.Thread(
            target=self._loop, args=(mode,), daemon=True, name="jarvis-soundscape"
        )
        self._thread.start()
        return label

    def _loop(self, mode: str) -> None:
        try:
            import numpy as np
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=1024)
            else:
                # Re-init as mono if another part of the app opened stereo
                try:
                    pygame.mixer.quit()
                    pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=1024)
                except Exception:
                    pass
            sr = 22050
            while not self._stop.is_set() and self._playing:
                if mode == "brown":
                    white = np.random.randn(sr * 2).astype(np.float32)
                    brown = np.cumsum(white)
                    brown = brown / (np.max(np.abs(brown)) + 1e-6)
                    mono = (brown * 32767 * self._volume).astype(np.int16)
                else:
                    t = np.linspace(0, 2, sr * 2, endpoint=False)
                    wave = 0.5 * np.sin(2 * np.pi * 110 * t) + 0.25 * np.sin(
                        2 * np.pi * 165 * t
                    )
                    mono = (wave * 32767 * self._volume).astype(np.int16)
                # pygame may expect (N,1) or (N,2)
                audio = np.column_stack([mono, mono]) if pygame.mixer.get_init() and pygame.mixer.get_init()[2] == 2 else mono.reshape(-1, 1)
                sound = pygame.sndarray.make_sound(np.ascontiguousarray(audio))
                sound.play()
                end = time.time() + 1.9
                while time.time() < end and not self._stop.is_set():
                    time.sleep(0.05)
                sound.stop()
        except Exception as e:
            print(f"[soundscape] {e}")
            self._playing = False

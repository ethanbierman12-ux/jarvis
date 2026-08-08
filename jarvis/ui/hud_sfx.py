"""Sci-fi HUD sound effects — clicks, whooshes, confirms (pygame.mixer.Sound).

Generated procedurally into assets/ so nothing external is required.
Use Sound channels (not music) so TTS / boot music stay intact.
"""

from __future__ import annotations

import math
import struct
import threading
import wave
from pathlib import Path

from jarvis.config import ASSETS_DIR

_SFX_DIR = ASSETS_DIR / "sfx"
_READY = False
_LOCK = threading.Lock()
_SOUNDS: dict[str, object] = {}


def _write_wav(path: Path, samples: list[float], sr: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for v in samples:
        frames += struct.pack("<h", int(max(-1.0, min(1.0, v)) * 28000))
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)


def _gen_click(sr: int = 44100) -> list[float]:
    n = int(sr * 0.055)
    out = []
    for i in range(n):
        t = i / sr
        env = math.exp(-t * 55)
        v = (
            0.55 * math.sin(2 * math.pi * 2400 * t)
            + 0.25 * math.sin(2 * math.pi * 4800 * t)
            + 0.15 * math.sin(2 * math.pi * 900 * t)
        ) * env
        out.append(v)
    return out


def _gen_whoosh(sr: int = 44100) -> list[float]:
    n = int(sr * 0.38)
    out = []
    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.04) * max(0.0, 1.0 - (t - 0.12) / 0.26)
        f = 180 + 1400 * min(1.0, t / 0.22)
        noise = ((i * 1103515245 + 12345) & 0x7FFF) / 0x7FFF - 0.5
        v = 0.22 * env * math.sin(2 * math.pi * f * t) + 0.08 * env * noise
        out.append(v)
    return out


def _gen_confirm(sr: int = 44100) -> list[float]:
    n = int(sr * 0.22)
    out = []
    for i in range(n):
        t = i / sr
        env = math.exp(-t * 9)
        v = env * (
            0.35 * math.sin(2 * math.pi * 880 * t)
            + 0.28 * math.sin(2 * math.pi * 1320 * t)
            + 0.18 * math.sin(2 * math.pi * 1760 * t)
        )
        out.append(v)
    return out


def _gen_speak_start(sr: int = 44100) -> list[float]:
    n = int(sr * 0.28)
    out = []
    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.03) * max(0.0, 1.0 - max(0.0, t - 0.14) / 0.14)
        f = 220 + 600 * t
        v = env * (
            0.28 * math.sin(2 * math.pi * f * t)
            + 0.12 * math.sin(2 * math.pi * f * 2.01 * t)
        )
        out.append(v)
    return out


def _gen_error(sr: int = 44100) -> list[float]:
    n = int(sr * 0.2)
    out = []
    for i in range(n):
        t = i / sr
        env = math.exp(-t * 7)
        v = env * (
            0.4 * math.sin(2 * math.pi * 220 * t)
            + 0.25 * math.sin(2 * math.pi * 185 * t)
        )
        out.append(v)
    return out


def _gen_zap(sr: int = 44100) -> list[float]:
    """High whoosh / zip for hologram swipes (~2–4 kHz)."""
    n = int(sr * 0.12)
    out = []
    for i in range(n):
        t = i / sr
        env = min(1.0, t / 0.008) * math.exp(-t * 28)
        f = 2200 + 1800 * min(1.0, t / 0.05)
        noise = ((i * 1103515245 + 12345) & 0x7FFF) / 0x7FFF - 0.5
        v = env * (0.35 * math.sin(2 * math.pi * f * t) + 0.12 * noise)
        out.append(v)
    return out


def _gen_hum(sr: int = 44100) -> list[float]:
    """Low Stark projector drone (~60–80 Hz), short loopable bed."""
    n = int(sr * 1.2)
    out = []
    for i in range(n):
        t = i / sr
        fade = min(1.0, t / 0.08) * min(1.0, (1.2 - t) / 0.08)
        v = fade * (
            0.22 * math.sin(2 * math.pi * 68 * t)
            + 0.10 * math.sin(2 * math.pi * 136 * t)
            + 0.05 * math.sin(2 * math.pi * 204 * t)
        )
        out.append(v)
    return out


_GENERATORS = {
    "click": _gen_click,
    "whoosh": _gen_whoosh,
    "confirm": _gen_confirm,
    "speak": _gen_speak_start,
    "error": _gen_error,
    "zap": _gen_zap,
    "hum": _gen_hum,
}


def ensure_sfx(*, force: bool = False) -> Path:
    _SFX_DIR.mkdir(parents=True, exist_ok=True)
    for name, gen in _GENERATORS.items():
        path = _SFX_DIR / f"{name}.wav"
        if force or not path.exists() or path.stat().st_size < 400:
            _write_wav(path, gen())
    return _SFX_DIR


def _init_mixer() -> bool:
    global _READY
    with _LOCK:
        if _READY and _SOUNDS:
            return True
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                import pygame

                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                ensure_sfx()
                for name in _GENERATORS:
                    path = _SFX_DIR / f"{name}.wav"
                    if path.exists():
                        snd = pygame.mixer.Sound(str(path))
                        # Quiet UI blips (~15–20%) so TTS stays primary
                        if name == "click":
                            snd.set_volume(0.16)
                        elif name == "whoosh":
                            snd.set_volume(0.18)
                        elif name == "speak":
                            snd.set_volume(0.20)
                        elif name == "hum":
                            snd.set_volume(0.10)
                        elif name == "zap":
                            snd.set_volume(0.14)
                        else:
                            snd.set_volume(0.18)
                        _SOUNDS[name] = snd
                _READY = True
                return True
            except Exception as e:
                last_err = e
                # Concurrent import race ("partially initialized module 'pygame'")
                if attempt == 0:
                    import time as _t

                    _t.sleep(0.08)
                    continue
        print(f"[hud-sfx] init: {last_err}")
        return False


def play(name: str) -> None:
    """Fire-and-forget HUD cue. Safe from any thread."""
    key = (name or "click").lower().strip()
    if key in ("ok", "success", "done"):
        key = "confirm"
    if key in ("fail", "danger"):
        key = "error"
    if key in ("boot", "panel", "slide"):
        key = "whoosh"
    if key in ("talk", "voice"):
        key = "speak"

    def _run() -> None:
        try:
            if not _init_mixer():
                return
            snd = _SOUNDS.get(key) or _SOUNDS.get("click")
            if snd is not None:
                snd.play()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name=f"hud-sfx-{key}").start()


def play_click() -> None:
    play("click")


def play_confirm() -> None:
    play("confirm")


def play_whoosh() -> None:
    play("whoosh")


def play_speak_cue() -> None:
    play("speak")


def play_hum(volume: float = 0.12, pan: float = 0.0) -> None:
    """Low holographic projector drone with optional stereo pan (-1..1)."""

    def _run() -> None:
        try:
            if not _init_mixer():
                return
            snd = _SOUNDS.get("hum")
            if snd is None:
                return
            vol = max(0.02, min(0.4, float(volume)))
            snd.set_volume(vol)
            ch = snd.play()
            if ch is None:
                return
            p = max(-1.0, min(1.0, float(pan)))
            left = vol * (1.0 - max(0.0, p))
            right = vol * (1.0 - max(0.0, -p))
            try:
                ch.set_volume(left, right)
            except TypeError:
                ch.set_volume(vol)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name="hud-sfx-hum").start()

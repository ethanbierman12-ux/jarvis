"""Local desk/home microphone impulse watch (owner mic only).

Detects sudden high-energy bangs vs a rolling ambient baseline and
fires soft alerts. Probabilistic labels only — NOT confirmed gunshot ID,
NOT city-wide surveillance, NOT CCTV audio analysis.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional


class DangerWatch:
    """Background local-mic impulse detector for the owner's desk/home."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        sensitivity: float = 1.0,
        cooldown_sec: float = 60.0,
        mic_prefer: str = "",
        on_alert: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.sensitivity = max(0.3, min(3.0, float(sensitivity or 1.0)))
        # 45–90s band; default mid
        self.cooldown_sec = max(45.0, min(90.0, float(cooldown_sec or 60.0)))
        self.mic_prefer = (mic_prefer or "").strip() or "auto"
        self.on_alert = on_alert
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._last_alert = 0.0
        self._last_kind = ""
        self._last_msg = ""
        self._err = ""
        self._lock = threading.Lock()

    def start(self) -> str:
        """Arm background mic watch (soft-fail if sounddevice missing)."""
        self.enabled = True
        if self._running:
            return self.status()
        self._stop.clear()
        self._err = ""
        try:
            import sounddevice  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            self._err = "sounddevice/numpy missing"
            self.enabled = False
            return (
                "Danger watch needs sounddevice + numpy on this machine. "
                "Desk mic watch is off."
            )
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="danger-watch"
        )
        self._thread.start()
        return (
            "Danger watch armed on your local microphone only — "
            "possible bang / impulse alerts (not confirmed gunshot ID)."
        )

    def stop(self) -> str:
        self.enabled = False
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            try:
                t.join(timeout=2.0)
            except Exception:
                pass
        self._thread = None
        self._running = False
        return "Danger watch off."

    def status(self) -> str:
        bits = [
            "armed" if self._running else ("enabled (starting)" if self.enabled else "off"),
            f"sensitivity {self.sensitivity:.1f}",
            f"cooldown {int(self.cooldown_sec)}s",
            f"mic {self.mic_prefer}",
        ]
        if self._err:
            bits.append(f"err: {self._err[:60]}")
        if self._last_msg:
            bits.append(f"last: {self._last_kind or 'impulse'}")
        return "Danger watch: " + " · ".join(bits)

    def _emit(self, kind: str, message: str, level: str = "warn") -> None:
        with self._lock:
            now = time.monotonic()
            if now - self._last_alert < self.cooldown_sec:
                return
            self._last_alert = now
            self._last_kind = kind
            self._last_msg = message
        cb = self.on_alert
        if cb is None:
            return
        try:
            cb(kind, message, level)
        except Exception as e:
            print(f"[danger_watch] on_alert: {e}")

    def _pick_device(self) -> int | None:
        try:
            from jarvis.core.clap_wake import find_mic_device

            prefer = self.mic_prefer
            # settings.mic_prefer is often a hardware name substr
            if prefer and prefer.lower() not in ("auto", "bluetooth", "bt", "wifi", "wired", "usb", "default"):
                return find_mic_device(prefer="auto", name_substr=prefer)
            return find_mic_device(prefer=prefer or "auto")
        except Exception:
            return None

    def _loop(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as e:
            self._err = str(e)
            self._running = False
            self.enabled = False
            return

        rate = 16000
        block = 1024
        device = self._pick_device()
        # Rolling ambient baseline (abs peak), clap-like peak gate
        ambient = 0.02
        last_peak_t = 0.0
        min_gap = 0.08  # ignore multi-sample ringing (like clap_wol min_gap)
        # Base peak gate scaled by sensitivity (clap_wol uses ~0.35)
        base_gate = max(0.15, min(0.85, 0.35 / max(0.5, self.sensitivity)))

        self._running = True
        print(
            f"[danger_watch] armed mic={self.mic_prefer}"
            + (f" device={device}" if device is not None else " device=default")
        )

        def on_audio(indata, frames, time_info, status) -> None:  # noqa: ANN001
            nonlocal ambient, last_peak_t
            if status or self._stop.is_set() or not self.enabled:
                return
            try:
                mono = np.asarray(indata, dtype=np.float32).reshape(-1)
            except Exception:
                return
            if mono.size == 0:
                return
            peak = float(np.max(np.abs(mono)))
            # Slow ambient follow when quiet
            if peak < ambient * 1.8:
                ambient = (0.97 * ambient) + (0.03 * peak)
                ambient = max(0.004, min(0.25, ambient))
                return
            now = time.monotonic()
            if now - last_peak_t < min_gap:
                return
            # Impulse: short spike well above rolling ambient
            ratio = peak / max(ambient, 1e-4)
            need = 8.0 / max(0.5, self.sensitivity)
            if peak < base_gate and ratio < need:
                return
            if ratio < need and peak < base_gate * 1.4:
                return
            last_peak_t = now
            kind, level, msg = self._classify(peak, ratio, ambient)
            self._emit(kind, msg, level)

        stream_kwargs: dict[str, Any] = dict(
            channels=1,
            samplerate=rate,
            blocksize=block,
            dtype="float32",
            callback=on_audio,
        )
        if device is not None:
            stream_kwargs["device"] = device

        try:
            with sd.InputStream(**stream_kwargs):
                while not self._stop.is_set() and self.enabled:
                    time.sleep(0.25)
        except Exception as e:
            self._err = str(e)
            print(f"[danger_watch] mic error: {e}")
            # Soft retry once on default device
            if device is not None and self.enabled and not self._stop.is_set():
                try:
                    stream_kwargs.pop("device", None)
                    with sd.InputStream(**stream_kwargs):
                        while not self._stop.is_set() and self.enabled:
                            time.sleep(0.25)
                    self._err = ""
                except Exception as e2:
                    self._err = str(e2)
                    print(f"[danger_watch] fallback mic error: {e2}")
        finally:
            self._running = False

    def _classify(
        self, peak: float, ratio: float, ambient: float
    ) -> tuple[str, str, str]:
        """Careful probabilistic labels — never claim certainty."""
        del ambient
        # Very sharp + high absolute → gunshot-like bang (possible only)
        if peak >= 0.55 and ratio >= 14.0:
            kind = "gunshot_like"
            msg = (
                "Possible gunshot-like bang on your desk mic — "
                "not confirmed. Check your surroundings."
            )
            level = "critical"
        elif peak >= 0.4 and ratio >= 10.0:
            kind = "loud_bang"
            msg = "Loud bang detected on your local microphone. Stay aware."
            level = "high"
        else:
            kind = "impulse"
            msg = "Sudden impulse / bang on your desk mic."
            level = "warn"
        return kind, level, msg

"""Contextual intelligence supervisor — gaze, posture, HR, soundscape, theme."""

from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np

from jarvis.core.biometrics import Biometrics
from jarvis.core.clipboard_guard import ClipboardGuard, KeyboardCadence
from jarvis.core.soundscape import Soundscape


class ContextSupervisor:
    def __init__(
        self,
        *,
        settings,
        soundscape: Soundscape,
        on_say: Callable[[str], None],
        on_lock: Callable[[], None],
        on_alert: Callable[[str], None],
        on_return_brief: Callable[[str], None],
        diary=None,
    ) -> None:
        self.settings = settings
        self.soundscape = soundscape
        self.on_say = on_say
        self.on_lock = on_lock
        self.on_alert = on_alert
        self.on_return_brief = on_return_brief
        self.diary = diary
        self.bio = Biometrics()
        self.cadence = KeyboardCadence()
        self.clip = ClipboardGuard(
            wipe_after_sec=float(settings.clipboard_wipe_sec or 60),
            on_wipe=lambda m: on_alert(m),
        )
        self._gaze_away_since: float | None = None
        self._slouch_since: float | None = None
        self._hr_high_since: float | None = None
        self._last_posture_nudge = 0.0
        self._last_hr_nudge = 0.0
        self._last_soundscape = 0.0
        self._was_present = True
        self._session_start = time.time()
        self._last_bio = 0.0

    def start(self) -> None:
        self.clip.start()
        self.cadence.start()

    def stop(self) -> None:
        self.clip.stop()
        self.soundscape.stop()

    def on_presence(self, present: bool, return_text: Optional[str] = None) -> None:
        if present and not self._was_present and return_text:
            self.on_return_brief(return_text)
        self._was_present = present

    def tick_frame(self, frame: Optional[np.ndarray]) -> None:
        now = time.time()
        if frame is None or now - self._last_bio < 1.2:
            return
        self._last_bio = now
        snap = self.bio.analyze(frame)

        # Gaze-based lock is OFF unless gaze_lock_minutes > 0 AND no face + no motion
        # for the full duration. Looking slightly away must NOT lock.
        mins = float(getattr(self.settings, "gaze_lock_minutes", 0) or 0)
        if mins > 0:
            really_gone = (not snap.face_present) and (self.cadence.keys_per_minute() < 5)
            if snap.face_present or snap.looking_at_screen or not really_gone:
                self._gaze_away_since = None
            else:
                if self._gaze_away_since is None:
                    self._gaze_away_since = now
                elif now - self._gaze_away_since >= mins * 60:
                    self._gaze_away_since = None
                    self.on_alert(
                        f"No face for {int(mins)} minutes — say 'lock' if you want security lock."
                    )
                    # Do NOT auto-lock from gaze — too many false positives.
                    # User can enable lock_on_absence for departure locking only.

        # Posture
        if self.settings.posture_nudge:
            if not snap.posture_ok:
                if self._slouch_since is None:
                    self._slouch_since = now
                elif now - self._slouch_since >= 50 and now - self._last_posture_nudge > 1800:
                    self._last_posture_nudge = now
                    self._slouch_since = None
                    name = self.settings.user_name or "there"
                    self.on_say(
                        f"{name}, take a moment to straighten up and stretch."
                    )
            else:
                self._slouch_since = None

        # Elevated HR
        if snap.heart_rate_bpm >= 105:
            if self._hr_high_since is None:
                self._hr_high_since = now
            elif now - self._hr_high_since >= 120 and now - self._last_hr_nudge > 1800:
                self._last_hr_nudge = now
                self._hr_high_since = None
                self.on_say(
                    f"Your heart rate looks elevated around {snap.heart_rate_bpm:.0f}. "
                    "Consider a five-minute break — I can play calm audio."
                )
                if not self.soundscape.active:
                    self.soundscape.play_calm(0.12)
        else:
            self._hr_high_since = None

        # High-stress typing → brown noise
        if (
            self.settings.auto_soundscape
            and self.cadence.is_high_stress(170)
            and not self.soundscape.active
            and now - self._last_soundscape > 600
        ):
            self._last_soundscape = now
            self.soundscape.play_brown_noise(0.14)
            self.on_alert("Focus soundscape on — high typing intensity detected.")

    def log_accomplishment(self, text: str) -> None:
        if self.diary:
            self.diary.log_win(text)

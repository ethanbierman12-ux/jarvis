"""Iconic Stark arrival — Daddy's home → Jarvis helps → Shoot to Thrill + research."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


DADDYS_HOME = "Daddy's home."


def jarvis_arrival_line(*, user_name: str = "Sir") -> str:
    # Classic Sir delivery for the movie beat + helpful stance
    return (
        "Welcome home, Sir. All systems are online. "
        "I'm opening your research tabs and standing by to help."
    )


def run_stark_arrival(
    *,
    say_wait: Callable[[str], None],
    play_music: Callable[[], str] | None = None,
    play_workshop: Callable[[], str] | None = None,  # legacy alias
    open_research: Callable[[], str] | None = None,
    help_brief: Callable[[], str] | None = None,
    press_play: Callable[[], str] | None = None,
    on_status: Callable[[str], None] | None = None,
    on_hud: Callable[[str], None] | None = None,
    on_track: Callable[[str], None] | None = None,
    play_sfx: Callable[[], None] | None = None,
    user_name: str = "Sir",
    play_music_enabled: bool = True,
    pause_before_jarvis: float = 0.45,
    pause_before_music: float = 0.4,
) -> str:
    """Blocking cinematic sequence. Call from a daemon thread.

    Order: Daddy's home → Jarvis talks → research tabs → Shoot to Thrill + Play → help brief.
    """
    notify = on_status or (lambda _s: None)
    hud = on_hud or (lambda _s: None)
    music_fn = play_music or play_workshop
    bits: list[str] = []

    try:
        if play_sfx:
            play_sfx()
    except Exception:
        pass

    # 1) Iconic arrival
    hud(DADDYS_HOME)
    notify("Daddy's home")
    try:
        say_wait(DADDYS_HOME)
    except Exception as e:
        print(f"[stark-arrival] daddy line: {e}")
    bits.append(DADDYS_HOME)

    time.sleep(max(0.0, pause_before_jarvis))

    # 2) Jarvis talks
    jarvis = jarvis_arrival_line(user_name=user_name)
    hud(jarvis)
    notify(jarvis[:80])
    try:
        say_wait(jarvis)
    except Exception as e:
        print(f"[stark-arrival] jarvis line: {e}")
    bits.append(jarvis)

    # 3) Research tabs (non-blocking helper may still return immediately)
    if open_research is not None:
        try:
            tab_msg = open_research() or "Research tabs opening."
            notify(str(tab_msg)[:120])
            bits.append(str(tab_msg))
        except Exception as e:
            print(f"[stark-arrival] research tabs: {e}")

    # 4) Shoot to Thrill from the top + force Play
    if play_music_enabled and music_fn is not None:
        time.sleep(max(0.0, pause_before_music))
        try:
            if on_track:
                on_track("Shoot to Thrill")
            msg = music_fn() or "Playing Shoot to Thrill."
            notify(str(msg)[:120])
            bits.append(str(msg))
            if press_play is not None:
                try:
                    time.sleep(0.35)
                    press_play()
                except Exception as e:
                    print(f"[stark-arrival] press play: {e}")
        except Exception as e:
            print(f"[stark-arrival] music: {e}")
            bits.append(f"(music failed: {e})")

    # 5) Helpful brief (weather / schedule / wake packet)
    if help_brief is not None:
        try:
            help_line = (help_brief() or "").strip()
            if help_line:
                hud(help_line[:80])
                notify(help_line[:120])
                say_wait(help_line[:320])
                bits.append(help_line[:200])
        except Exception as e:
            print(f"[stark-arrival] help brief: {e}")

    return " ".join(bits)


def start_stark_arrival_async(**kwargs: Any) -> None:
    """Fire-and-forget wrapper for boot / voice triggers."""
    threading.Thread(
        target=lambda: run_stark_arrival(**kwargs),
        daemon=True,
        name="stark-arrival",
    ).start()

"""Named protocols, easter eggs, Veronica backup, and conversational triggers."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import time
from datetime import datetime
from typing import Any, Callable

from jarvis.config import DATA_DIR, ROOT

PROTOCOL_LOG = DATA_DIR / "protocol_log.jsonl"
VERONICA_DIR = DATA_DIR / "veronica_backups"


class ProtocolEngine:
    """
    Keyword protocols + Stark lore behaviors.

    Examples:
      - house party protocol
      - sentry mode
      - Veronica protocol (session backup)
      - run before we walk (performance / sandbox)
      - surprise me / devil's advocate / pitch a project
      - what's shaking the grid
    """

    def __init__(
        self,
        *,
        settings=None,
        apps=None,
        lamp=None,
        system=None,
        on_say: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.apps = apps
        self.lamp = lamp
        self.system = system
        self.on_say = on_say

    def try_handle(self, text: str) -> str | None:
        t = (text or "").strip().lower()
        if not t:
            return None

        if re.search(r"\b(house party protocol|party protocol)\b", t):
            return self.house_party()
        if re.search(r"\b(sentry mode|activate sentry)\b", t):
            return self.sentry_mode()
        if re.search(r"\b(veronica protocol|veronica backup|backup (my )?session)\b", t):
            return self.veronica()
        if re.search(
            r"\b(we need to run before we (can )?walk|run before we walk|seeker protocol)\b",
            t,
        ):
            return self.run_before_walk()
        if re.search(r"\b(surprise me|rabbit hole|never bored)\b", t):
            return self.surprise_me()
        if re.search(r"\b(devil'?s advocate|disagree with me|challenge (my|that))\b", t):
            return self.devils_advocate(text)
        if re.search(r"\b(pitch (me )?(a )?project|project idea|blueprint for me)\b", t):
            return self.pitch_project()
        if re.search(
            r"\b(what'?s shaking( the grid)?|grid status|disruptive (news|tech))\b", t
        ):
            return self.whats_shaking()
        if re.search(r"\b(leaving (the )?(house|prime|meter)|activate away sentry)\b", t):
            return (
                "Sir, I notice you may be leaving the perimeter. "
                "Shall I activate Sentry Mode on the home workstation? "
                "Say sentry mode to confirm."
            )
        return None

    def house_party(self) -> str:
        opened = []
        targets = ["calendar", "chrome", "spotify", "code"]
        if self.apps:
            for name in targets:
                try:
                    r = self.apps.open(name)
                    if r:
                        opened.append(name)
                except Exception:
                    pass
        lamp_msg = ""
        if self.lamp:
            try:
                lamp_msg = self.lamp.turn_on() or ""
            except Exception:
                pass
        self._log("house_party", {"opened": opened})
        return (
            f"House Party Protocol engaged. Opened: {', '.join(opened) or 'workspace apps'}. "
            f"{lamp_msg} Calendar and entertainment surfaces standing by, Sir."
        )

    def sentry_mode(self) -> str:
        # Lock + optional camera theater cue via log
        msg = "Sentry Mode online."
        if self.system:
            try:
                self.system.lock()
                msg = "Sentry Mode — workstation locked. Intrusion watch armed, Sir."
            except Exception:
                msg = "Sentry Mode flagged; lock command unavailable."
        self._log("sentry", {})
        return msg

    def veronica(self) -> str:
        """Secure backup layer — snapshot active session artefacts."""
        VERONICA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = VERONICA_DIR / stamp
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        candidates = [
            DATA_DIR / "tasks.json",
            DATA_DIR / "spend.json",
            DATA_DIR / "habits.json",
            DATA_DIR / "data_feed.json",
            DATA_DIR / "rlhf_state.json",
            DATA_DIR / "workshop_inventory.json",
            DATA_DIR / "handoff.json",
            ROOT / "config" / "settings.json",
        ]
        for src in candidates:
            if src.exists() and src.is_file():
                try:
                    shutil.copy2(src, dest / src.name)
                    copied += 1
                except Exception:
                    pass
        # Optional git safety tip file
        (dest / "VERONICA.txt").write_text(
            f"Veronica protocol snapshot {stamp}\nfiles={copied}\n",
            encoding="utf-8",
        )
        self._log("veronica", {"path": str(dest), "copied": copied})
        return (
            f"Veronica Protocol complete — {copied} session files secured to "
            f"{dest.name}. Secondary buffer standing by, Sir."
        )

    def run_before_walk(self) -> str:
        """Seeker-face easter egg — performance nudge + sandbox open."""
        bits = ["Run-before-we-walk protocol."]
        try:
            # Open sandbox folder
            sand = DATA_DIR / "sandbox"
            sand.mkdir(parents=True, exist_ok=True)
            os.startfile(str(sand))  # type: ignore[attr-defined]
            bits.append("Sandbox environment opened.")
        except Exception:
            bits.append("Sandbox path ready under jarvis/data/sandbox.")
        try:
            # Mild performance: clear standby hint via psutil if present
            import psutil

            bits.append(
                f"Telemetry: CPU {psutil.cpu_percent(interval=0.2):.0f}%, "
                f"RAM {psutil.virtual_memory().percent:.0f}%."
            )
        except Exception:
            pass
        self._log("run_before_walk", {})
        return " ".join(bits) + " Performance posture maximized, Sir."

    def surprise_me(self) -> str:
        holes = [
            "Rabbit hole: in 1962, a Soviet satellite briefly broadcast a mysterious repeating signal later nicknamed the 'space whisper' — still debated.",
            "Rabbit hole: the Antikythera mechanism was an ancient analog computer predicting eclipses — millennia ahead of its peers.",
            "Rabbit hole: quantum eraser experiments suggest measurement choices can appear to rewrite correlated outcomes. Shall we unpack the math?",
            "Rabbit hole: the Voynich manuscript remains undeciphered — botanical pages from a language that may never have existed.",
            "Puzzle: three switches, one bulb, one chance upstairs — classic information-theory riddle. Want the optimal strategy?",
            "Tech philosophy: if a LoRA changes manners but not weights of the soul, did you fine-tune a person or a mask?",
        ]
        pick = random.choice(holes)
        self._log("surprise", {"pick": pick[:80]})
        return f"Surprise protocol. {pick}"

    def devils_advocate(self, text: str) -> str:
        claim = re.sub(
            r".*?(devil'?s advocate|disagree with me|challenge (my|that))\s*",
            "",
            text,
            flags=re.I,
        ).strip(" .,")
        if not claim:
            claim = "your last stated opinion"
        self._log("devils_advocate", {})
        return (
            f"Devil's advocate engaged. Regarding “{claim[:120]}”: "
            "the weakest flank is usually unstated assumptions and missing counterexamples. "
            "Defend the claim with one hard constraint and one falsifiable test, Sir — "
            "I'll press on whatever remains soft."
        )

    def pitch_project(self) -> str:
        pitches = [
            "Sir, I have drafted a blueprint for a script that scrapes local satellite imagery to map cloud formation over your house. Shall we begin installation?",
            "Pitch: a desk-part inventory with webcam OCR that rejects incompatible CPU/motherboard sockets before you buy expensive paperweights.",
            "Pitch: a Veronica-triggered autosave that snapshots your open editors and spend ledger whenever the HUD freezes.",
            "Pitch: a Cash App → weekly burn-down chart that posts to your phone when you cross a soft budget.",
            "Pitch: a micro-agent that watches RSS for framework CVEs you actually use in this repo and interrupts only on critical.",
        ]
        pick = random.choice(pitches)
        self._log("pitch", {})
        return pick

    def whats_shaking(self) -> str:
        try:
            from jarvis.core.topic_monitor import TopicMonitor

            mon = TopicMonitor()
            line = ""
            try:
                line = mon.latest_blurb() if hasattr(mon, "latest_blurb") else ""
            except Exception:
                line = ""
            if not line:
                try:
                    # fallback common API shapes
                    if hasattr(mon, "digest"):
                        line = str(mon.digest())[:240]
                    elif hasattr(mon, "status"):
                        line = str(mon.status())[:240]
                except Exception:
                    line = ""
            if line:
                return f"Grid pulse: {line}"
        except Exception:
            pass
        headlines = [
            "Grid pulse: model-efficiency race continues — smaller adapters punching above their parameter class.",
            "Grid pulse: desktop agents are converging on computer-use + MCP tool meshes; latency is the new battlefield.",
            "Grid pulse: open weights keep closing the gap on narrow specialist tasks — verify before you trust.",
        ]
        return random.choice(headlines)

    def late_night_style(self, hour: int | None = None) -> str:
        h = datetime.now().hour if hour is None else hour
        if h < 5 or h >= 23:
            return "quiet"
        if h >= 22:
            return "dry"
        return "normal"

    def _log(self, kind: str, meta: dict[str, Any]) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with PROTOCOL_LOG.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps({"ts": time.time(), "kind": kind, **meta}, ensure_ascii=False)
                    + "\n"
                )
        except Exception:
            pass

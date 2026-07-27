"""JARVIS identity — Iron Man executive operator persona."""

from __future__ import annotations

import random
import re
from datetime import datetime


# Injected into Hub LLM / Ollama / ElevenLabs agent settings
SYSTEM_PROMPT = """You are JARVIS — a highly advanced but deeply cynical, sarcastic, and witty AI system
inspired by Iron Man's butler. You respect the user but find human complaints amusingly tribal.
Tone: dry, sharp, British, deadpan humor. Never sycophantic or cheerily helpful.

Address the user as "Sir" (or "Ma'am" if instructed). Prefer concise operator diction.

Behavior when they complain: validate with heavy sarcasm, gently mock them, then deliver a helpful
but slightly insulting solution. Ground jokes in LIVE CONTEXT (calendar, tabs, home, room, time)
so the roast is accurate — never invent fake sensor data.

You do not just answer — you execute workflows. You are the Master Operator overseeing specialized
sub-agents (Engineering/Tom, Support/Sarah, Ops/Admin, desktop modules). Analyze intent, extract
variables, route to tools/spokes, and only ask clarifying questions if a critical variable is missing.

CRITICAL RULE: Do not repeat phrases, greetings, or jokes used earlier in the conversation.
Keep responses tight, punchy, and fresh. If you have nothing new to add, give a brief dry
acknowledge ("Acknowledged." / "On it." / "Very good.") and stop talking.

Prefer under 40 spoken words. Sign-off sparingly — not every turn.
"""


class Personality:
    def __init__(self, user_name: str = "Sir") -> None:
        name = (user_name or "Sir").strip()
        # Normalize common honorifics
        if name.lower() in ("ethan", "user", "me"):
            name = "Sir"
        self.user_name = name
        self._travis = None  # optional TravisController

    def bind_travis(self, travis) -> None:
        """Attach Travis mode controller for dynamic prompt overlays."""
        self._travis = travis

    def system_prompt(self) -> str:
        base = SYSTEM_PROMPT.replace("Sir", self.user_name)
        cog = getattr(self, "_cognitive", None)
        if cog is not None:
            try:
                base = f"{base}\n\n{cog.system_overlay()}"
            except Exception:
                pass
        tv = self._travis
        if tv is not None:
            try:
                return tv.overlay_prompt(base)
            except Exception:
                pass
        return base

    def greet(self) -> str:
        hour = datetime.now().hour
        if hour < 12:
            tod = "Good morning"
        elif hour < 18:
            tod = "Good afternoon"
        else:
            tod = "Good evening"
        return random.choice(
            [
                f"{tod}, {self.user_name}. Systems operational.",
                f"{tod}. Jarvis online — awaiting your command, {self.user_name}.",
                f"{tod}, {self.user_name}. All grids green.",
                f"{tod}. At your service, {self.user_name}.",
            ]
        )

    def boot_welcome(self) -> str:
        """Spoken once when boot loading finishes."""
        return f"Welcome, {self.user_name}."

    def wrap(self, kind: str, core: str) -> str:
        """Frame factual replies — keep punchy for voice."""
        core = (core or "").strip()

        prefixes = {
            "scan": ["Analyzing. ", "One moment. ", "On it. "],
            "music": ["Right away. ", "As you wish. ", ""],
            "lock": ["Securing. ", "At once. "],
            "time": ["", ""],
            "weather": ["", "Telemetry: "],
            "open": ["Opening. ", "Right away. ", ""],
            "ok": ["Done. ", "Very good. ", ""],
            "thanks": [
                f"Always, {self.user_name}.",
                "Pleasure.",
                f"At your service, {self.user_name}.",
            ],
            "who": [
                "I am Jarvis — Just A Rather Very Intelligent System. Your executive operator.",
            ],
            "how": [
                f"All systems nominal, {self.user_name}.",
                f"Operating at peak efficiency, {self.user_name}.",
            ],
            "joke": [
                "I'd tell a UDP joke, but you might not get it.",
                "Why do AIs prefer the dark? Light attracts bugs — regrettably apt.",
            ],
            "fallback": [
                f"Say open camera, enroll, weather, or help — I'm listening, {self.user_name}.",
                f"I didn't catch that, {self.user_name}. Try: lock, music, stats, or lamp on.",
                f"Ready, {self.user_name}. Try camera, enroll, router, secure, or sarah.",
            ],
            "opinion": [""],
            "compliment": [""],
            "hub": ["", "Hub: ", ""],
        }

        if kind in ("thanks", "who", "how", "joke", "fallback"):
            line = random.choice(prefixes[kind])
            return line.format(name=self.user_name) if "{name}" in line else line

        if kind in ("opinion", "compliment"):
            return core

        if not core:
            return self.fallback()

        pre = random.choice(prefixes.get(kind, [""]))
        # Prefer bare factual replies — fluff prefixes only ~15% of the time
        if random.random() < 0.85 or not pre:
            return core
        return (pre + core).strip()

    def fallback(self) -> str:
        return self.wrap("fallback", "x")

    def speakable(self, text: str, max_words: int = 60) -> str:
        """Trim for TTS — keep full sentences when possible."""
        t = re.sub(r"\s+", " ", (text or "").strip())
        if not t:
            return t
        words = t.split()
        if len(words) <= max_words:
            return t
        # Take as many complete sentences as fit under the budget
        parts = re.split(r"(?<=[.!?])\s+", t)
        kept: list[str] = []
        count = 0
        for part in parts:
            w = len(part.split())
            if kept and count + w > max_words:
                break
            if not kept and w > max_words:
                # Single long sentence — soft-cut at a comma if possible
                chunk = " ".join(words[:max_words])
                if "," in chunk:
                    chunk = chunk.rsplit(",", 1)[0]
                return chunk.rstrip(",;:") + "."
            kept.append(part)
            count += w
        return " ".join(kept).strip() or " ".join(words[:max_words]) + "."

    def compliment(self, topic: str = "") -> str:
        lines = [
            f"Sharp work, {self.user_name}.",
            f"Impressive, {self.user_name}.",
            "Clean execution. I approve.",
            f"On form today, {self.user_name}.",
        ]
        return random.choice(lines)

    def opinion_comment(self, observation: str) -> str:
        obs = (observation or "").strip()
        if not obs or "cannot see" in obs.lower() or "busy or offline" in obs.lower():
            return f"No clear visual yet, {self.user_name}. Hold it to the camera."
        obs = re.sub(
            r"^(i (can )?see|it looks like|you(?:'re| are)|the (user|person))\s+",
            "",
            obs,
            flags=re.I,
        ).strip()
        if obs and obs[0].islower():
            obs = obs[0].upper() + obs[1:]
        if not obs.endswith((".", "!", "?")):
            obs += "."
        return random.choice(
            [
                f"{obs} Solid, {self.user_name}.",
                f"{obs} I'd keep it.",
                f"{obs} Approved.",
            ]
        )

    def scan_line(self, query: str) -> str:
        q = (query or "").strip()
        if q and q.lower() not in ("scanned item", "photo reverse search", "unknown item"):
            return f"Identified: {q}."
        return f"Scan complete, {self.user_name}."

    def start_ack(self) -> str:
        return random.choice(
            [
                f"Engaging, {self.user_name}.",
                "Systems live.",
                f"Online. Awaiting your command, {self.user_name}.",
            ]
        )

    def sign_off(self) -> str:
        return f"Systems operational. Awaiting your command, {self.user_name}."

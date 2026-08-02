"""Physical-mic isolation — never bind STT to desktop/virtual loopback devices."""

from __future__ import annotations

# Names that carry desktop audio / Voicemeeter outs / OBS / cables
LOOPBACK_NEEDLES = (
    "STEREO MIX",
    "WHAT U HEAR",
    "WAVE OUT",
    "LOOPBACK",
    "CABLE OUTPUT",
    "CABLE INPUT",
    "VOICEVOX",
    "VOICEMEETER OUTPUT",
    "VOICEMEETER VAIO",
    "VOICEMEETER AUX",
    "VOICEMEETER VAIO3",
    "VB-AUDIO",
    "VIRTUAL CABLE",
    "VIRTUAL-AUDIO",
    "OBS VIRTUAL",
    "BLACKHOLE",
    "SOUNDFLOWER",
    "MONITOR OF",
    "HITPAW",
    "EMEET VIRTUAL",
)

# Playback / mapper entries that appear in Microphone.list_microphone_names()
OUTPUT_NEEDLES = (
    "SPEAKERS",
    "HEADPHONES",
    "PRIMARY SOUND DRIVER",
    "SOUND MAPPER",
    "OUTPUT",
    "LINE OUT",
    "NVIDIA OUTPUT",
    "DIGITAL AUDIO",
)


# Prefer real headset / USB array mics
PHYSICAL_NEEDLES = (
    "HEADSET",
    "MICROPHONE",
    "MIC ",
    " USB",
    "ARRAY",
    "STUDIO",
    "YETI",
    "BLUE ",
    "RODE",
    "JOUNIVO",
    "WG1",
    "REALTEK",
    "CONEXANT",
    "INTEL",
    "RESPEAKER",
    "SEEED",
    "FAR-FIELD",
    "FAR FIELD",
)

FAR_FIELD_NEEDLES = ("RESPEAKER", "SEEED", "FAR-FIELD", "FAR FIELD")


def is_loopback_name(name: str) -> bool:
    n = (name or "").upper()
    return any(k in n for k in LOOPBACK_NEEDLES)


def is_output_name(name: str) -> bool:
    n = (name or "").upper()
    # Hands-Free AG "Headset (...)" can be a valid BT mic — keep those
    if "HANDS-FREE" in n or "HANDSFREE" in n:
        return False
    if n.startswith("MICROPHONE") or n.startswith("MIC "):
        return False
    return any(k in n for k in OUTPUT_NEEDLES)


def is_physical_mic_name(name: str) -> bool:
    n = (name or "").upper()
    if is_loopback_name(n) or is_output_name(n):
        return False
    return any(k in n for k in PHYSICAL_NEEDLES) or "MIC" in n


def pick_isolated_mic_index(
    names: list[str],
    *,
    prefer: str = "",
    allow_virtual: bool = False,
) -> tuple[int | None, str]:
    """
    Choose a speech-recognition input device (not loopback / speakers).
    Prefers lower hostAPI indexes when scores tie — PyAudio often fails on
    duplicate DirectSound/WASAPI entries at the end of the list.
    """
    prefer_u = (prefer or "").upper().strip()
    scored: list[tuple[float, int, str]] = []

    for i, name in enumerate(names or []):
        n = (name or "").upper()
        if not allow_virtual and is_loopback_name(n):
            continue
        if is_output_name(n):
            continue
        score = 0.0
        if prefer_u and prefer_u in n:
            score += 120
        if n.startswith("MICROPHONE") or "MICROPHONE (" in n:
            score += 50
        elif is_physical_mic_name(n):
            score += 35
        if "EMEET" in n and "VIRTUAL" not in n:
            score += 15
        if any(k in n for k in FAR_FIELD_NEEDLES):
            score += 45
        if any(k in n for k in ("HEADSET", "HANDS-FREE", "EARPHONE", "BUDS")):
            score += 25
        if "CAMERA" in n or "SMARTCAM" in n:
            score -= 25
        if "JOUNIVO" in n and prefer_u and prefer_u not in n:
            score += 10  # solid USB spillover when prefer misses
        if score > 0:
            scored.append((score, i, name or f"mic-{i}"))

    if not scored:
        for i, name in enumerate(names or []):
            if not is_loopback_name(name or "") and not is_output_name(name or ""):
                return i, f"fallback non-loopback [{i}] {name}"
        return None, "no safe mic — using system default (verify Windows privacy settings)"

    # Highest score first; among ties, lowest device index (more reliably openable)
    scored.sort(key=lambda t: (-t[0], t[1]))
    best = scored[0]
    return best[1], f"isolated mic [{best[1]}] {best[2]}"


def rank_mic_candidates(
    names: list[str],
    *,
    prefer: str = "",
    allow_virtual: bool = False,
) -> list[tuple[int, str]]:
    """Ordered list of (index, name) fallbacks for open-and-retry."""
    prefer_u = (prefer or "").upper().strip()
    scored: list[tuple[float, int, str]] = []
    for i, name in enumerate(names or []):
        n = (name or "").upper()
        if not allow_virtual and is_loopback_name(n):
            continue
        if is_output_name(n):
            continue
        score = 0.0
        if prefer_u and prefer_u in n:
            score += 120
        if n.startswith("MICROPHONE") or "MICROPHONE (" in n:
            score += 50
        elif is_physical_mic_name(n):
            score += 30
        if any(k in n for k in FAR_FIELD_NEEDLES):
            score += 45
        if score <= 0:
            continue
        scored.append((score, i, name or f"mic-{i}"))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [(i, name) for _, i, name in scored]


VOICEMEETER_SETUP = """
Voicemeeter Banana + Jarvis (no desktop-audio feedback)
=======================================================
Goal: Games/music → speakers/headphones. Jarvis STT → physical mic only.

1) Install Voicemeeter Banana + VB-Audio Virtual Cable (optional).
2) Windows Sound → Playback: set Voicemeeter Input as default (or keep real speakers).
3) Windows Sound → Recording: set your HEADSET / USB mic as default for apps.
4) In Voicemeeter:
   - Hardware Input 1 = your physical microphone (gain as needed)
   - Hardware Out A1 = headphones/speakers
   - VAIO / virtual outs carry GAME/MUSIC only — do NOT select these as Jarvis mic
5) In config/settings.json:
   "mic_prefer": "WG1"   (or "USB", "YETI", exact device substring)
   "mic_reject_loopback": true
6) Restart Jarvis. Mission log should show: [voice] isolated mic [...]
7) Test: play music loudly, say "Jarvis weather" — it should not trigger from the song.

Stream Deck / silent macros → http://127.0.0.1:8765/macro?cmd=stop
""".strip()

"""Owner identity profile for PC-boot intrusion recovery.

Profile lives in jarvis/data/owner_identity.local.json (gitignored).
Used only after an unauthorized access attempt — never shown on the lock screen.
"""

from __future__ import annotations

import json
import random
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR, Settings

PROFILE_PATH = DATA_DIR / "owner_identity.local.json"


@dataclass
class OwnerProfile:
    full_name: str = "Ethan Bierman"
    birth: str = "01/16/2012"  # MM/DD/YYYY
    age: str = "14"
    school: str = "Penn Treaty"
    favorite_color: str = "red"
    sport: str = "basketball"
    heritage: str = "Puerto Rican"
    height: str = "5'10"
    likes: str = "games"
    address: str = "2208 East Harold St"
    postal_code: str = "19125"
    city: str = "Philadelphia"


def _norm(text: str) -> str:
    t = (text or "").lower().strip()
    t = t.replace("'", "").replace("’", "").replace(",", " ").replace(".", " ")
    t = t.replace("-", " ").replace("/", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _norm_height(text: str) -> str:
    t = _norm(text)
    # 5 10 / 510 / 5ft10 / 5 foot 10 → 510
    t = t.replace("feet", " ").replace("foot", " ").replace("ft", " ").replace("in", " ")
    digits = re.sub(r"[^0-9]", "", t)
    if len(digits) >= 3:
        return digits[:3]  # 510
    if len(digits) == 2:
        return digits  # 510 already compacted oddly
    return t


def _norm_birth(text: str) -> str:
    digits = "".join(c for c in (text or "") if c.isdigit())
    if len(digits) == 8:
        return digits
    return _norm(text)


def _norm_name(text: str) -> str:
    return _norm(text)


def ensure_owner_profile() -> OwnerProfile:
    """Load or create the local owner profile (Ethan's facts)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if PROFILE_PATH.exists():
        try:
            raw = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            known = {k: v for k, v in raw.items() if k in OwnerProfile.__dataclass_fields__}
            return OwnerProfile(**known)
        except Exception:
            pass
    profile = OwnerProfile()
    try:
        PROFILE_PATH.write_text(
            json.dumps(asdict(profile), indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"[owner-id] save profile: {e}")
    # Keep display name in settings aligned
    try:
        s = Settings.load()
        if (s.user_name or "").strip() in ("", "Sir"):
            s.user_name = profile.full_name.split()[0]
            s.save()
    except Exception:
        pass
    return profile


@dataclass
class QuizQuestion:
    key: str
    prompt: str
    hint: str = ""


@dataclass
class OwnerQuiz:
    questions: list[QuizQuestion] = field(default_factory=list)
    index: int = 0
    fails: int = 0

    @property
    def current(self) -> QuizQuestion | None:
        if 0 <= self.index < len(self.questions):
            return self.questions[self.index]
        return None

    @property
    def done(self) -> bool:
        return self.index >= len(self.questions)


def build_owner_quiz(*, count: int = 3) -> OwnerQuiz:
    """Pick a few identity questions (always includes name + birth)."""
    profile = ensure_owner_profile()
    required = [
        QuizQuestion("full_name", "Type your full name"),
        QuizQuestion("birth", "Type your date of birth"),
    ]
    pool = [
        QuizQuestion("school", "What school do you go to?"),
        QuizQuestion("favorite_color", "What is your favorite color?"),
        QuizQuestion("sport", "What is your favorite sport?"),
        QuizQuestion("heritage", "What is your heritage / ethnicity?"),
        QuizQuestion("height", "What is your height?"),
        QuizQuestion("postal_code", "What is your postal / ZIP code?"),
        QuizQuestion("city", "What city do you live in?"),
        QuizQuestion("address", "Type your street address"),
        QuizQuestion("likes", "What do you like? (hobby)"),
        QuizQuestion("age", "How old are you?"),
    ]
    extra_n = max(0, count - len(required))
    extras = random.sample(pool, k=min(extra_n, len(pool)))
    return OwnerQuiz(questions=required + extras)


def check_answer(key: str, given: str, profile: OwnerProfile | None = None) -> bool:
    profile = profile or ensure_owner_profile()
    g = given or ""
    if key == "full_name":
        want = _norm_name(profile.full_name)
        got = _norm_name(g)
        return got == want or want in got or got in want
    if key == "birth":
        return _norm_birth(g) == _norm_birth(profile.birth)
    if key == "height":
        return _norm_height(g) == _norm_height(profile.height) or _norm_height(
            g
        ) in (_norm_height(profile.height), "510", "5 10")
    if key == "heritage":
        got = _norm(g).replace(" ", "")
        want = _norm(profile.heritage).replace(" ", "")
        aliases = {want, "puertorican", "pertorican", "puertorico"}
        return got in aliases or any(a and a in got for a in aliases)
    if key == "city":
        got = _norm(g)
        return got in ("philadelphia", "philly", _norm(profile.city))
    if key == "address":
        got = _norm(g)
        want = _norm(profile.address)
        # Accept street number + harold
        return got == want or ("2208" in got and "harold" in got)
    if key == "school":
        got = _norm(g)
        return "penn" in got and "treaty" in got
    if key == "favorite_color":
        return _norm(g) == _norm(profile.favorite_color)
    if key == "sport":
        return _norm(g) == _norm(profile.sport)
    if key == "postal_code":
        return "".join(c for c in g if c.isdigit()) == profile.postal_code
    if key == "likes":
        return "game" in _norm(g)
    if key == "age":
        return "".join(c for c in g if c.isdigit()) == str(profile.age)
    want = _norm(str(getattr(profile, key, "")))
    return bool(want) and _norm(g) == want


def notify_intrusion(
    *,
    preview: bool = False,
    image_path: str | None = None,
) -> str:
    """Push high-priority ntfy the moment Jarvis says 'alerting owner'.

    Optional image_path attaches an intruder JPEG snapshot.
    """
    msg = (
        "ALERTING OWNER - someone was trying to break in on your PC, sir. "
        "Jarvis started lockdown."
    )
    if image_path:
        msg = (
            "INTRUDER SNAPSHOT - someone was at your PC. "
            "Photo attached. Jarvis is in lockdown."
        )
    if preview:
        msg = "[PREVIEW] " + msg

    try:
        settings = Settings.load()
        phone_topic = (getattr(settings, "phone_ntfy_topic", "") or "").strip()
        door_topic = (getattr(settings, "doorbell_ntfy_topic", "") or "").strip()
        topic = phone_topic or door_topic
        server = (
            (
                getattr(settings, "phone_ntfy_server", "")
                if phone_topic
                else getattr(settings, "doorbell_ntfy_server", "")
            )
            or "https://ntfy.sh"
        ).rstrip("/")
        if not phone_topic and topic:
            try:
                settings.phone_ntfy_topic = topic
                settings.phone_ntfy_server = server
                settings.save()
            except Exception:
                pass
    except Exception as e:
        print(f"[intrusion] settings: {e}")
        topic, server = "", "https://ntfy.sh"

    img = (image_path or "").strip() or None

    def _send() -> None:
        if not topic:
            print("[intrusion] no ntfy topic - set phone_ntfy_topic in settings")
            return
        try:
            from jarvis.core.phone_bridge import PhoneBridge

            phone = PhoneBridge(topic=topic, server=server, enabled=True)
            if img:
                result = phone.notify_image(
                    msg,
                    img,
                    title="JARVIS INTRUDER CAM",
                    filename=Path(img).name,
                )
            else:
                result = phone.ping(msg, title="JARVIS ALERTING OWNER")
            try:
                print(f"[intrusion] ntfy ok -> {server}/{topic}")
                print(f"[intrusion] {result}")
            except Exception:
                pass
        except Exception as e:
            try:
                print(f"[intrusion] ntfy failed: {e}")
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True, name="jarvis-intrusion-ntfy").start()
    return msg

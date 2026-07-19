"""Helpers to recognize camera intents (including typos like 'camrea')."""

from __future__ import annotations

import re

# Common misspellings / aliases users say or type
_CAMERA_WORDS = {
    "camera",
    "camrea",
    "camara",
    "cammera",
    "camra",
    "camere",
    "webcam",
    "webcame",
    "webcamera",
    "cam",
    "emeet",
    "e-meet",
    "smartcam",
    "usb camera",
    "usb cam",
}


def is_camera_query(text: str) -> bool:
    """True if text means the webcam / EMEET, not an app file to shell-open."""
    t = (text or "").strip().lower()
    if not t:
        return False
    t = re.sub(r"[^a-z0-9\s\-]+", "", t)
    if t in _CAMERA_WORDS:
        return True
    # "open the camera", "show my camrea", "emeet camera"
    if re.search(
        r"\b(open|show|start|launch|use)\s+(the\s+|my\s+)?(cam\w*|webcam\w*|emeet|smartcam)\b",
        t,
    ):
        # last token looks like camera / camrea / camara
        last = t.split()[-1]
        if last.startswith("cam") or last.startswith("web") or last in ("emeet", "smartcam"):
            return True
        return is_camera_query(last)
    if re.search(r"\b(cam+e?r+a*|webcam|emeet|smartcam)\s+(on|feed|live|please)?\b", t):
        return True
    if "emeet" in t or "smartcam" in t:
        return True
    # fuzzy: edit distance-ish for camera typos (camrea <-> camera)
    compact = t.replace(" ", "")
    if _near(compact, "camera") or _near(compact, "webcam") or _near(compact, "emeet"):
        return True
    return False


def _near(a: str, b: str, max_dist: int = 2) -> bool:
    if abs(len(a) - len(b)) > max_dist:
        return False
    # simple Levenshtein capped
    if a == b:
        return True
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins, delete, sub = cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
        if min(prev) > max_dist:
            return False
    return prev[-1] <= max_dist

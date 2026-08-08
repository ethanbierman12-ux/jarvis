"""Casual EN↔ES + chat acronym expand (ICYMI, LMAO, …)."""

from __future__ import annotations

import re

_ACRONYMS = {
    "icymi": "in case you missed it",
    "lmao": "laughing my ass off",
    "lmfao": "laughing my fucking ass off",
    "lol": "laughing out loud",
    "brb": "be right back",
    "idk": "I don't know",
    "imo": "in my opinion",
    "imho": "in my humble opinion",
    "tbh": "to be honest",
    "nvm": "never mind",
    "omg": "oh my god",
    "ttyl": "talk to you later",
    "smh": "shaking my head",
    "fyi": "for your information",
    "asap": "as soon as possible",
    "btw": "by the way",
    "ikr": "I know right",
    "wyd": "what are you doing",
    "wbu": "what about you",
    "ily": "I love you",
    "idc": "I don't care",
    "afaik": "as far as I know",
    "tl;dr": "too long; didn't read",
    "tldr": "too long; didn't read",
}

# Lightweight phrase table (offline) — expand via Google translate when online
_EN_ES = {
    "hello": "hola",
    "hi": "hola",
    "goodbye": "adiós",
    "bye": "adiós",
    "please": "por favor",
    "thank you": "gracias",
    "thanks": "gracias",
    "yes": "sí",
    "no": "no",
    "how are you": "cómo estás",
    "i love you": "te quiero",
    "good morning": "buenos días",
    "good night": "buenas noches",
    "see you": "nos vemos",
    "what are you doing": "qué estás haciendo",
    "where are you": "dónde estás",
    "i miss you": "te extraño",
    "call me": "llámame",
    "text me": "envíame un mensaje",
    "on my way": "voy en camino",
    "be right back": "vuelvo enseguida",
}

_ES_EN = {v: k for k, v in _EN_ES.items()}


def expand_acronyms(text: str) -> str:
    t = text or ""
    def repl(m: re.Match) -> str:
        w = m.group(0)
        low = w.lower()
        if low in _ACRONYMS:
            return _ACRONYMS[low]
        return w
    return re.sub(r"[A-Za-z;]{2,8}", repl, t)


def translate_casual(text: str, *, to: str = "es") -> str:
    """to = es | en. Uses table first, then Google translate endpoint if available."""
    raw = (text or "").strip()
    if not raw:
        return "Nothing to translate."
    expanded = expand_acronyms(raw)
    low = expanded.lower().strip()
    table = _EN_ES if to.startswith("es") else _ES_EN
    if low in table:
        return f"{expanded} -> {table[low]}"
    # Phrase contains known chunk
    for k, v in sorted(table.items(), key=lambda kv: -len(kv[0])):
        if k in low:
            return f"{expanded} -> {re.sub(re.escape(k), v, expanded, flags=re.I)}"
    # Online fallback
    try:
        import urllib.parse
        import urllib.request
        import json as _json

        sl, tl = ("en", "es") if to.startswith("es") else ("es", "en")
        q = urllib.parse.quote(expanded)
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl={sl}&tl={tl}&dt=t&q={q}"
        )
        with urllib.request.urlopen(url, timeout=6) as resp:
            data = _json.loads(resp.read().decode("utf-8", errors="replace"))
        out = "".join(part[0] for part in data[0] if part and part[0])
        if out:
            return f"{expanded} -> {out}"
    except Exception:
        pass
    return f"{expanded} (no offline match - try shorter phrases or check network)"

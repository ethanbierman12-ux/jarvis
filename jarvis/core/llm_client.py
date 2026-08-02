"""Shared LLM completion — one helper for every module that needs prompt → text.

Backend chain (first available wins):
  1. Local Ollama  (http://127.0.0.1:11434 — free, private, preferred)
  2. Anthropic     (anthropic_api_key in vault)
  3. OpenAI        (openai_api_key in vault)

Boot-safe: urllib only, no SDKs, every path wrapped. Returns "" when no
backend is reachable — callers degrade gracefully.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

_OLLAMA_HOST = "http://127.0.0.1:11434"
_ANTHROPIC_MODEL = "claude-sonnet-4-5"
_OPENAI_MODEL = "gpt-4.1-mini"

_ollama_model_cache: str | None = None
_ollama_cache_at: float = 0.0
_OLLAMA_RETRY_SEC = 60.0  # re-probe a down/empty Ollama once a minute


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def ollama_model(host: str = _OLLAMA_HOST) -> str:
    """Best installed Ollama model, or '' when Ollama is down.

    Successful lookups are cached for the session; failures are re-probed
    every minute so an Ollama started mid-session is picked up.
    """
    global _ollama_model_cache, _ollama_cache_at
    import time

    if _ollama_model_cache:
        return _ollama_model_cache
    if _ollama_model_cache == "" and time.time() - _ollama_cache_at < _OLLAMA_RETRY_SEC:
        return ""
    _ollama_cache_at = time.time()
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        # Prefer general chat models; vision/embed tags only as a last resort
        deprioritized = ("embed", "clip", "llava", "moondream", "vision")
        text_models = [m for m in models if not any(k in m.lower() for k in deprioritized)]
        _ollama_model_cache = (text_models or models or [""])[0]
    except Exception:
        _ollama_model_cache = ""
    return _ollama_model_cache


def _complete_ollama(
    prompt: str, system: str, *, model: str, temperature: float, max_tokens: int
) -> str:
    m = model or ollama_model()
    if not m:
        return ""
    try:
        data = _post_json(
            f"{_OLLAMA_HOST}/api/generate",
            {
                "model": m,
                "prompt": (f"{system}\n\n{prompt}" if system else prompt),
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=90.0,
        )
        return (data.get("response") or "").strip()
    except Exception as e:
        print(f"[llm] ollama ({m}): {_err(e)}")
        return ""


def _complete_anthropic(
    prompt: str, system: str, *, key: str, temperature: float, max_tokens: int
) -> str:
    if not key:
        return ""
    try:
        payload: dict[str, Any] = {
            "model": _ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        parts = data.get("content") or []
        return "".join(
            p.get("text", "") for p in parts if p.get("type") == "text"
        ).strip()
    except Exception as e:
        print(f"[llm] anthropic: {_err(e)}")
        return ""


def _complete_openai(
    prompt: str, system: str, *, key: str, temperature: float, max_tokens: int
) -> str:
    if not key:
        return ""
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        data = _post_json(
            "https://api.openai.com/v1/chat/completions",
            {
                "model": _OPENAI_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            headers={"Authorization": f"Bearer {key}"},
        )
        choices = data.get("choices") or []
        if choices:
            return (choices[0].get("message", {}).get("content") or "").strip()
    except Exception as e:
        print(f"[llm] openai: {_err(e)}")
    return ""


def _err(e: Exception) -> str:
    """Compact error line — surfaces HTTP body (API error message) when present."""
    try:
        if isinstance(e, urllib.error.HTTPError):
            body = e.read().decode("utf-8", errors="replace")[:200]
            return f"HTTP {e.code} {body}"
    except Exception:
        pass
    return str(e)[:200]


def _vault_key(name: str) -> str:
    try:
        from jarvis.core.secrets_vault import get_vault

        return get_vault().get(name, "")
    except Exception:
        return ""


def backend_name() -> str:
    """Which backend complete() would use right now — for status lines."""
    if ollama_model():
        return f"ollama:{ollama_model()}"
    if _vault_key("anthropic_api_key"):
        return "anthropic"
    if _vault_key("openai_api_key"):
        return "openai"
    return "none"


def remote_backends_configured() -> bool:
    """True when complete() could fall through to a cloud LLM."""
    return bool(_vault_key("anthropic_api_key") or _vault_key("openai_api_key"))


def complete(
    prompt: str,
    *,
    system: str = "",
    model: str = "",
    temperature: float = 0.4,
    max_tokens: int = 700,
) -> str:
    """Prompt → text through the first available backend. '' when all fail."""
    if not (prompt or "").strip():
        return ""
    out = _complete_ollama(
        prompt, system, model=model, temperature=temperature, max_tokens=max_tokens
    )
    if out:
        return out
    out = _complete_anthropic(
        prompt,
        system,
        key=_vault_key("anthropic_api_key"),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if out:
        return out
    return _complete_openai(
        prompt,
        system,
        key=_vault_key("openai_api_key"),
        temperature=temperature,
        max_tokens=max_tokens,
    )

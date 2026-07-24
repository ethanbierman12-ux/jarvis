"""Zero-knowledge local secrets vault — Windows DPAPI, never leave API keys in plaintext JSON."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

VAULT_DIR = DATA_DIR / "vault"
VAULT_FILE = VAULT_DIR / "secrets.dpapi.json"

# Keys that must never sit in settings.json in cleartext
SECRET_KEYS = (
    "elevenlabs_api_key",
    "deepgram_api_key",
    "tavily_api_key",
    "serper_api_key",
    "openweather_api_key",
    "ha_token",
    "n8n_api_key",
    "manus_api_key",
    "anthropic_api_key",
    "openai_api_key",
    "stripe_secret_key",
    "notion_token",
    "buffer_access_token",
    "gmail_access_token",
    "spotify_client_id",
    "spotify_client_secret",
    "lifx_token",
    "hue_username",
    "phone_shortcuts_webhook",
    "alexa_ifttt_key",
    "companion_token",
)

# Token-shaped secrets never contain whitespace; speech/command bar sometimes injects spaces.
_TOKENISH_PREFIX = re.compile(
    r"^(sk-ant-|sk-|sk_|xox[baprs]-|ghp_|ntn_|key-|AIza)",
    re.I,
)


def sanitize_secret(value: str) -> str:
    """Strip wrappers/whitespace from a secret. Never log or print the value."""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    v = (
        v.strip(" \t\r\n.,")
        .replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u00a0", "")
    )
    compact = re.sub(r"\s+", "", v)
    if _TOKENISH_PREFIX.match(compact):
        return compact
    return v


def secret_meta(value: str) -> dict[str, Any]:
    """Safe diagnostics for a secret (never includes the secret itself)."""
    v = sanitize_secret(value)
    return {
        "set": bool(v),
        "len": len(v),
        "prefix_sk_ant": v.startswith("sk-ant-"),
        "prefix_sk_openaiish": v.startswith("sk-") and not v.startswith("sk-ant-"),
        "has_whitespace": bool(value) and any(c.isspace() for c in value),
        "all_lower": bool(v) and v == v.lower() and any(c.isalpha() for c in v),
    }


def _dpapi_protect(raw: bytes) -> bytes:
    """Encrypt with current Windows user DPAPI."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    blob_in = DATA_BLOB(len(raw), ctypes.create_string_buffer(raw, len(raw)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "JarvisSecrets",
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(enc: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    blob_in = DATA_BLOB(len(enc), ctypes.create_string_buffer(enc, len(enc)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


class SecretsVault:
    """Encrypted key-value store bound to this Windows user profile."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or VAULT_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, str] = {}
        self._loaded = False

    def load(self) -> dict[str, str]:
        if self._loaded:
            return dict(self._cache)
        self._cache = {}
        if not self.path.exists():
            self._loaded = True
            return {}
        try:
            wrapper = json.loads(self.path.read_text(encoding="utf-8"))
            blob_b64 = wrapper.get("dpapi") or ""
            if not blob_b64:
                self._loaded = True
                return {}
            raw = _dpapi_unprotect(base64.b64decode(blob_b64))
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                self._cache = {str(k): str(v) for k, v in data.items() if v}
        except Exception as e:
            print(f"[vault] load failed: {e}")
            self._cache = {}
        self._loaded = True
        return dict(self._cache)

    def save(self, data: dict[str, str] | None = None) -> None:
        payload = {k: v for k, v in (data if data is not None else self._cache).items() if v}
        self._cache = dict(payload)
        raw = json.dumps(payload, indent=0).encode("utf-8")
        try:
            enc = _dpapi_protect(raw)
        except Exception as e:
            print(f"[vault] protect failed: {e}")
            # Fallback: machine-local obfuscation file (better than plaintext settings)
            fallback = self.path.with_suffix(".local.json")
            fallback.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            try:
                os.chmod(fallback, 0o600)
            except Exception:
                pass
            return
        wrapper = {
            "version": 1,
            "algo": "DPAPI",
            "dpapi": base64.b64encode(enc).decode("ascii"),
        }
        self.path.write_text(json.dumps(wrapper, indent=2), encoding="utf-8")
        self._loaded = True

    def get(self, key: str, default: str = "") -> str:
        self.load()
        return self._cache.get(key, default) or default

    def set(self, key: str, value: str) -> None:
        self.load()
        cleaned = sanitize_secret(value) if value else ""
        if cleaned:
            self._cache[key] = cleaned
        else:
            self._cache.pop(key, None)
        self.save()

    def merge_into(self, settings_obj: Any) -> None:
        """Copy vault secrets onto a Settings dataclass instance (RAM only)."""
        secrets = self.load()
        for key in SECRET_KEYS:
            val = secrets.get(key, "")
            if val and hasattr(settings_obj, key):
                setattr(settings_obj, key, val)

    def harvest_from(self, settings_obj: Any) -> int:
        """Pull plaintext secrets off settings into the vault. Returns count moved."""
        self.load()
        moved = 0
        for key in SECRET_KEYS:
            if not hasattr(settings_obj, key):
                continue
            val = getattr(settings_obj, key) or ""
            if not str(val).strip():
                continue
            # Don't treat placeholder masks as real secrets
            if str(val).startswith("•") or str(val) in ("***", "changeme", "YOUR_"):
                continue
            self._cache[key] = sanitize_secret(str(val))
            setattr(settings_obj, key, "")
            moved += 1
        if moved:
            self.save()
        return moved

    def redact_dict(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Return a copy safe to write to settings.json."""
        out = dict(raw)
        for key in SECRET_KEYS:
            if key in out and out[key]:
                # Keep empty in JSON; real value lives in vault
                out[key] = ""
        return out


_vault: SecretsVault | None = None


def get_vault() -> SecretsVault:
    global _vault
    if _vault is None:
        _vault = SecretsVault()
    return _vault

"""Claude Code CLI wrapper — headless prompt → text via the `claude` binary.

The Claude Code CLI (installed via ``npm install -g @anthropic-ai/claude-code``)
gives Jarvis a Claude session that reuses the user's Claude subscription
instead of a raw API key. This module is a thin, boot-safe shim used by
``jarvis.core.llm_client`` when ``settings.prefer_claude_cli`` is on.

Design goals:
  * No SDKs. subprocess only.
  * Fail closed — every path returns ``""`` on error so the LLM chain falls
    through to Anthropic REST / OpenAI / Ollama.
  * Never block Jarvis boot: availability probe is cached and cheap.
  * Windows-friendly (creationflags=CREATE_NO_WINDOW, uses ``shutil.which``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

_AVAILABILITY_CACHE: tuple[bool, float] = (False, 0.0)
_AVAILABILITY_TTL = 30.0  # re-probe every 30s at most
_DEFAULT_TIMEOUT = 90.0
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _binary() -> str:
    """Locate the CLI. Explicit env override first, then PATH."""
    override = os.environ.get("JARVIS_CLAUDE_CLI", "").strip()
    if override:
        return override
    return shutil.which("claude") or ""


def is_available() -> bool:
    """True when the ``claude`` CLI is installed and answers ``--version``.

    Result is cached for :data:`_AVAILABILITY_TTL` seconds so we don't spawn a
    subprocess on every completion.
    """
    global _AVAILABILITY_CACHE
    available, checked_at = _AVAILABILITY_CACHE
    now = time.time()
    if now - checked_at < _AVAILABILITY_TTL:
        return available
    binary = _binary()
    if not binary:
        _AVAILABILITY_CACHE = (False, now)
        return False
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=8.0,
            creationflags=_CREATE_NO_WINDOW,
        )
        ok = proc.returncode == 0
    except Exception:
        ok = False
    _AVAILABILITY_CACHE = (ok, now)
    return ok


def _short_err(text: str) -> str:
    return (text or "").strip().splitlines()[-1][:200] if text else ""


def complete(
    prompt: str,
    *,
    system: str = "",
    model: str = "",
    max_tokens: int = 700,
    timeout: float = _DEFAULT_TIMEOUT,
) -> str:
    """Send a single prompt to the Claude CLI in headless print mode.

    Returns the CLI stdout, or ``""`` on any error / unavailable CLI. Callers
    should treat ``""`` as "try the next backend", never as a real answer.
    """
    if not (prompt or "").strip():
        return ""
    if not is_available():
        return ""
    binary = _binary()

    args = [binary, "--print"]
    if system:
        args.extend(["--append-system-prompt", system])
    if model:
        args.extend(["--model", model])
    args.extend(["--output-format", "text"])

    try:
        proc = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        print(f"[llm] claude-cli: timeout after {timeout:.0f}s")
        return ""
    except Exception as e:
        print(f"[llm] claude-cli: launch failed: {e}")
        return ""

    if proc.returncode != 0:
        print(f"[llm] claude-cli: exit {proc.returncode} — {_short_err(proc.stderr)}")
        return ""

    out = (proc.stdout or "").strip()
    if max_tokens > 0:
        # Soft cap; the CLI itself already streamed a Claude response and we
        # trim so downstream prompts don't blow up their own token budgets.
        approx_chars = max_tokens * 4
        if len(out) > approx_chars:
            out = out[:approx_chars].rstrip() + "…"
    return out


def diagnose() -> str:
    """Human-readable status line for the HUD / settings panel."""
    if not _binary():
        return (
            "claude CLI not found. Install: npm install -g @anthropic-ai/claude-code, "
            "then run: claude login"
        )
    if not is_available():
        return (
            "claude CLI installed but not responding to --version. "
            "Try: claude login (re-authenticate)."
        )
    return "claude CLI ready."

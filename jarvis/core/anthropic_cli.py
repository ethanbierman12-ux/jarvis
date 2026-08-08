"""Anthropic / Claude Code CLI bridge — use subscription instead of API keys.

When the `claude` CLI is installed (Claude Code / Pro / Max subscription),
Jarvis agents can call it headlessly so you don't burn Anthropic API credits.

Install: https://docs.anthropic.com/en/docs/claude-code
Then:  claude  (login once)
Jarvis: prefer_claude_cli=true in settings, or env JARVIS_CLAUDE_CLI=1
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any


# Prefer Opus when the CLI supports model flags; fall back silently.
_DEFAULT_MODEL = "claude-opus-4-5"


def claude_bin() -> str | None:
    env = (os.environ.get("CLAUDE_CLI") or os.environ.get("JARVIS_CLAUDE_PATH") or "").strip()
    if env and os.path.isfile(env):
        return env
    return shutil.which("claude")


def available() -> bool:
    return bool(claude_bin())


def status() -> str:
    path = claude_bin()
    if not path:
        return (
            "Claude Code CLI not found. Install Claude Code, run `claude` once to log in, "
            "then set prefer_claude_cli true — agents will use your subscription, not API keys."
        )
    return f"Claude Code CLI ready at {path} (subscription path — no Anthropic API needed)."


def complete_cli(
    prompt: str,
    *,
    system: str = "",
    model: str = "",
    max_tokens: int = 1200,
    timeout: float = 180.0,
) -> str:
    """Headless Claude Code completion. Returns '' if CLI missing or fails."""
    exe = claude_bin()
    if not exe or not (prompt or "").strip():
        return ""
    text = prompt.strip()
    if system:
        text = f"SYSTEM:\n{system.strip()}\n\nUSER:\n{text}"
    # Cap enormous prompts
    if len(text) > 48_000:
        text = text[:48_000] + "\n\n[truncated]"

    model = (model or os.environ.get("JARVIS_CLAUDE_MODEL") or _DEFAULT_MODEL).strip()
    cmd = [
        exe,
        "-p",
        text,
        "--output-format",
        "text",
    ]
    # Model flag varies by CLI version — try, ignore if unsupported
    if model:
        cmd.extend(["--model", model])

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={**os.environ, "CI": "1"},  # reduce interactive prompts
        )
        out = (r.stdout or "").strip()
        if out:
            return out
        err = (r.stderr or "").strip()
        if err:
            print(f"[claude-cli] stderr: {err[:240]}")
        # Retry without --model if the flag was rejected
        if model and r.returncode != 0:
            cmd2 = [exe, "-p", text, "--output-format", "text"]
            r2 = subprocess.run(
                cmd2,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={**os.environ, "CI": "1"},
            )
            return (r2.stdout or "").strip()
        return ""
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        print("[claude-cli] timeout")
        return ""
    except Exception as e:
        print(f"[claude-cli] {e}")
        return ""


def prefer_cli(settings: Any | None = None) -> bool:
    env = (os.environ.get("JARVIS_CLAUDE_CLI") or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if settings is not None:
        return bool(getattr(settings, "prefer_claude_cli", False))
    try:
        from jarvis.config import Settings

        return bool(getattr(Settings.load(), "prefer_claude_cli", False))
    except Exception:
        return False

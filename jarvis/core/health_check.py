"""Desk self-health — upgrade check / readiness summary (additive, local-first)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _recent_log_issues(log_path: Path, *, max_lines: int = 800) -> tuple[int, list[str]]:
    """
    Scan recent jarvis.log lines for real ERROR/WARNING signal.
    Ignores the historical logging-recursion Message: spam and stack dumps.
    Only counts timestamped records from the last 3 calendar days.
    Returns (issue_count, sample_prefixes).
    """
    if not log_path.is_file():
        return 0, []
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0, ["log unreadable"]

    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    lines = text.splitlines()[-max_lines:]
    samples: list[str] = []
    count = 0
    spam_sub = (
        "Message: ",
        "--- Logging error ---",
        "callHandlers",
        "handleError",
        "hdlr.handle",
        "self.emit(record)",
        "self.handle(record)",
        "self.callHandlers",
        "self._log(",
        "RotatingFileHandler",
        "logging\\__init__",
        "logging/__init__",
        "logging_setup.py",
        "PrintLogger",
        "Unable to print the message",
        "Use the traceback above",
        "PermissionError: [WinError 32]",
        "cp1252",
        "charmap_encode",
        "UnicodeEncodeError",
        "sys.stderr.write",
        "During handling of the above exception",
        "The above exception was the direct cause",
        "Traceback (most recent call last)",
    )
    for ln in lines:
        m = re.match(
            r"^(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\s+\[(ERROR|WARNING)\]\s+(.*)$",
            ln,
        )
        if not m:
            continue
        day, _level, body = m.group(1), m.group(2), m.group(3).strip()
        if day < cutoff:
            continue
        if any(s in ln for s in spam_sub):
            continue
        if not body or body.startswith('File "') or set(body) <= set("~^ \t"):
            continue
        if body.startswith("Traceback (most recent"):
            continue
        count += 1
        tip = body[:90]
        if tip and tip not in samples and len(samples) < 3:
            samples.append(tip)
    return count, samples


def _autobug_note(data_dir: Path) -> str:
    p = data_dir / "autobug" / "last_error.txt"
    if not p.is_file():
        return ""
    try:
        raw = (p.read_text(encoding="utf-8", errors="replace") or "").strip()
    except Exception:
        return ""
    if not raw:
        return ""
    one = raw.splitlines()[0].strip()[:80]
    return f"autobug: {one}" if one else ""


def recent_errors_blurb(data_dir: Path | None = None, *, max_lines: int = 800) -> str:
    """Spoken summary of recent real log errors (spam filtered)."""
    try:
        from jarvis.config import DATA_DIR

        root = Path(data_dir or DATA_DIR)
    except Exception:
        return "Could not locate log directory."
    n, samples = _recent_log_issues(root / "jarvis.log", max_lines=max_lines)
    ab = _autobug_note(root)
    if n <= 0 and not ab:
        return "No recent errors in jarvis.log."
    parts = []
    if n:
        parts.append(f"{n} recent log issues")
        if samples:
            parts.append("; ".join(samples[:2]))
    if ab:
        parts.append(ab)
    return ". ".join(parts)[:420]


def build_upgrade_check(
    *,
    settings: Any = None,
    cu_agent: Any = None,
    cloud: Any = None,
    companion_line: str = "",
    manus_line: str = "",
    hub_line: str = "",
    security_line: str = "",
    data_dir: Path | None = None,
) -> str:
    """
    One spoken/HUD paragraph: errors · computer-use · integrations · wake.
    Keep under ~450 chars for TTS.
    """
    bits: list[str] = []

    # Log / autobug pulse
    try:
        from jarvis.config import DATA_DIR

        root = Path(data_dir or DATA_DIR)
        n, samples = _recent_log_issues(root / "jarvis.log")
        if n <= 0:
            bits.append("Logs clean")
        else:
            tip = samples[0] if samples else "see jarvis.log"
            bits.append(f"Logs {n} recent issues ({tip})")
        ab = _autobug_note(root)
        if ab:
            bits.append(ab)
    except Exception:
        bits.append("Logs unknown")

    # Computer use readiness + what's missing
    try:
        if cu_agent is not None:
            try:
                cu_agent.configure_from_settings(settings)
            except Exception:
                pass
            if getattr(getattr(cu_agent, "status", None), "running", False):
                st = cu_agent.status
                bits.append(
                    f"CU running {st.provider} {st.step}/{st.max_steps}"
                )
            else:
                miss = ""
                try:
                    miss = cu_agent.missing_guidance()
                except Exception:
                    miss = ""
                try:
                    ready = cu_agent.readiness()
                except Exception:
                    ready = "Computer use unknown"
                # Prefer short missing guidance when blocked
                if miss and ("blocked" in ready.lower() or "needs" in ready.lower()):
                    bits.append(miss)
                else:
                    # Trim "Computer use ready · …"
                    short = ready
                    if short.lower().startswith("computer use "):
                        short = short[13:]
                    bits.append(f"CU {short}")
        else:
            bits.append("CU offline")
    except Exception as e:
        bits.append(f"CU error ({type(e).__name__})")

    # Cloud integrations (linked/not — no secrets)
    try:
        if cloud is not None:
            linked = []
            for name, attr in (
                ("Stripe", "stripe_secret_key"),
                ("Notion", "notion_token"),
                ("Buffer", "buffer_access_token"),
                ("Gmail", "gmail_access_token"),
            ):
                if getattr(cloud, attr, ""):
                    linked.append(name)
            if linked:
                bits.append("Cloud " + "+".join(linked))
            else:
                bits.append("Cloud none linked")
    except Exception:
        pass

    # Companion / Manus / Hub / security (optional short)
    for label, line in (
        ("Phone", companion_line),
        ("Manus", manus_line),
        ("Hub", hub_line),
        ("Sec", security_line),
    ):
        s = (line or "").strip()
        if not s:
            continue
        # Keep only first clause
        s = re.split(r"[.·]", s, maxsplit=1)[0].strip()
        if len(s) > 48:
            s = s[:46] + "…"
        bits.append(f"{label} {s}" if not s.lower().startswith(label.lower()) else s)

    # Wake / local prefs (non-secret)
    try:
        if settings is not None:
            wake = "wake on" if getattr(settings, "wake_required", True) else "always listen"
            bits.append(wake)
            if not getattr(settings, "tts_prefer_elevenlabs", False):
                bits.append("Thomas TTS")
    except Exception:
        pass

    line = " · ".join(b for b in bits if b)
    if len(line) > 460:
        line = line[:440].rsplit("·", 1)[0].strip(" ·") + "."
    return line or "Upgrade check complete — nothing to report."

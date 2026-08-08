"""Edge / Jetson / home-server briefing — run Jarvis when the desk PC is off."""

from __future__ import annotations

EDGE_GUIDE = """\
JARVIS · EDGE / HOME SERVER
═══════════════════════════
Goal: keep net-watch, backups, deadman, phone bridge alive when the gaming PC sleeps.

RECOMMENDED HARDWARE
  · NVIDIA Jetson Orin Nano / Xavier  — CUDA for vision/local LLM
  · Mini PC / old laptop / Raspberry Pi 5 — lean wake_agent + ntfy + backups
  · NAS (TrueNAS / Unraid) — encrypted backup target

DEPLOY (Linux edge)
  1) git clone this repo on the edge box
  2) python -m venv .venv && pip install -r requirements-edge.txt
     (or requirements.txt minus PyQt6 if headless)
  3) copy config/settings.json (phone_ntfy_topic, etc.)
  4) systemd: wake_agent.py (optional) + python -m jarvis.edge_daemon
  5) Tailscale both machines — companion PWA + phone bridge stay reachable

WHAT RUNS HEADLESS
  · Net watch (unknown MAC)
  · Secure backups
  · Deadman handshake via ntfy / companion
  · Space weather + ISS alerts → phone
  · Live comms translate (if Phone Link / windows only — keep on PC)

DESK PC OFF
  Edge owns alerts; when PC wakes, F3 double-tap resumes full HUD.
"""


def edge_setup_message() -> str:
    return EDGE_GUIDE


def edge_status() -> str:
    return (
        "Edge profile: run net watch + backups + deadman on a Jetson/mini-PC. "
        "Say edge setup for the full guide. Desk HUD still needs this Windows box."
    )

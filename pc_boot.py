"""Windows Startup entry — cinematic secure boot, then Jarvis."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from jarvis.ui.pc_poweron import run

    preview = "--preview" in sys.argv
    intrusion = "--intrusion" in sys.argv or "--show-lockdown" in sys.argv
    launch = "--no-jarvis" not in sys.argv and not preview and not intrusion
    return run(
        launch_jarvis=launch,
        allow_lock=not preview,
        start_intrusion=intrusion,
    )


if __name__ == "__main__":
    raise SystemExit(main())

"""Weekly RLHF digester — compile approve/reject logs into custom instructions."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.core.rlhf import RLHFEngine


def main() -> int:
    engine = RLHFEngine()
    print(engine.status())
    print(engine.digest(apply=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

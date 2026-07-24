#!/usr/bin/env python3
"""Best-effort git safety snapshot after a Jarvis crash (called by runner)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jarvis.core.github_autocommit import GitHubAutoCommitter  # noqa: E402


def main() -> int:
    bot = GitHubAutoCommitter(ROOT, auto_push=False)
    print(bot.snapshot("crash"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

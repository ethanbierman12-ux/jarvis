#!/usr/bin/env python3
"""Lattice Calc — CLI unit converter and quick math helper. Built by Jarvis vibe agent."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).with_name("journal.md")


def add_entry(text: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"## {stamp}\n\n{text.strip()}\n\n"
    prev = LOG.read_text(encoding="utf-8") if LOG.exists() else "# Lattice Calc\n\n"
    LOG.write_text(prev + block, encoding="utf-8")
    print(f"Logged → {LOG}")


def show() -> None:
    if not LOG.exists():
        print("No entries yet.")
        return
    print(LOG.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser(description="Lattice Calc: CLI unit converter and quick math helper")
    p.add_argument("text", nargs="*", help="Journal entry text")
    p.add_argument("--show", action="store_true", help="Print the journal")
    args = p.parse_args()
    if args.show:
        show()
        return
    if not args.text:
        p.print_help()
        return
    add_entry(" ".join(args.text))


if __name__ == "__main__":
    main()

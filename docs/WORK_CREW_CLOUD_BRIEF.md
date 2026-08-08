# Work Crew — Claude Code build brief

Give this file to Claude Code (`claude`) so it expands the zero-code work system.

## Goal
Jarvis Work Crew: Manager + Research + market specialists, driven by **Claude Code CLI subscription** (no Anthropic API burns). Second dashboard: gamified agent tile pack.

## Already in repo
- `jarvis/core/anthropic_cli.py` — CLI bridge
- `jarvis/core/llm_client.py` — prefers Claude CLI when `prefer_claude_cli=true`
- `jarvis/core/work_crew.py` — MANAGER, SCHOLAR, MARKET, STITCH, REEL, FLIP, LEDGER, MUSE
- `jarvis/data/agent_ops_dashboard.html` — second dashboard tile pack

## Your build tasks
1. Install/login Claude Code CLI if missing; verify `claude -p "ping" --output-format text`
2. Wire Hub spokes mirroring work agents (optional Node hub)
3. Buffer MCP for TikTok/Etsy social posts from REEL
4. Persist XP / outcome streaks on the dashboard (read `work_outcomes.jsonl`)
5. Add HITL gates before any publish / spend actions
6. Keep LEDGER research-only (never place trades)

## Voice commands to preserve
- `work crew status`
- `ask manager …`
- `ask research agent …`
- `work crew run <brief>`
- `open agent ops`

## Model
Manager + Research should use the smartest available Claude via CLI (`--model` opus-class when supported).

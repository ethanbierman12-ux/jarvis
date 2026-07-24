---
name: jarvis-mcp-setup
description: >-
  Set up or repair Jarvis Cursor MCP servers (Buffer, Gmail, Stripe, Notion).
  Use when the user asks to connect MCP, authenticate OAuth, or debug missing
  MCP tools in this repo.
disable-model-invocation: false
---

# Jarvis MCP setup

1. Read `docs/HANDOVER_MCP.md` and ensure `.cursor/mcp.json` matches `.cursor/mcp.json.example` (additive merge).
2. Never put real secrets in git; `.cursor/mcp.json` is gitignored.
3. All current servers use **url only** + Cursor **OAuth Connect** — no Bearer headers in the example.
4. Active set: `buffer`, `gmail`, `stripe`, `notion`. Do not re-add `meta-ads` (DCR blocked), local `n8n` MCP, or `revenuecat` unless the user asks.
5. After edits: Cursor Settings → Tools & MCP → refresh / Connect (where OAuth works).
6. Delegate deep integration work to the `jarvis-integrations` subagent when useful.

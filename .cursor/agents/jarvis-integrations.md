---
name: jarvis-integrations
description: >-
  Wire and debug Jarvis integrations — Cursor MCP (Buffer, Gmail, Stripe,
  Notion), Manus bridge, Home Assistant, companion/ntfy, macro gateway.
  Use when connecting OAuth MCPs, vaulting keys, or fixing webhook/companion auth.
model: inherit
readonly: false
is_background: false
---

# Jarvis integrations

You own **external connectors** for Jarvis and this repo’s Cursor MCP config.

## Sources of truth

- MCP checklist: `docs/HANDOVER_MCP.md`
- Runtime integrations: `docs/INTEGRATIONS.md`
- FAQs: `docs/FAQS.md`
- Config templates: `.cursor/mcp.json.example` → local `.cursor/mcp.json` (gitignored)
- Rules: `.cursor/rules/jarvis-integrations.mdc`, `.cursor/rules/n8n-automations.mdc`

## Official MCP endpoints (do not invent)

| id | url / command |
|----|----------------|
| buffer | `https://mcp.buffer.com/mcp` |
| gmail | `https://gmailmcp.googleapis.com/mcp/v1` |
| stripe | `https://mcp.stripe.com` |
| notion | `https://mcp.notion.com/mcp` |

Cursor OAuth servers: **url only** — no static `Authorization` headers (breaks OAuth).

**Not in MCP config** (unless user re-adds): `meta-ads` (Cursor DCR blocked), local `n8n` MCP (hassle), `revenuecat` (left by choice). Jarvis voice `trigger n8n <path>` still works via settings.

## Workflow

1. Confirm whether the task is Cursor MCP vs Jarvis runtime (`config/settings.json` / vault).
2. Additive merge into `mcpServers` for kept servers; do not re-add removed ones unless asked.
3. Document auth steps; placeholders only in git-tracked example files.
4. Gmail = Developer Preview, draft-only.
5. Manus keys: voice vault / local only — never paste into chat or commits.

## Smoke prompts

- Buffer: list channels / drafts
- Gmail: search threads / create draft
- Stripe: list recent customers / payments (read-only first)
- Notion: search workspace pages

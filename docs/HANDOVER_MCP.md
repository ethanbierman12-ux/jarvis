# MCP setup checklist — Buffer, Gmail, Stripe, Notion

Project Cursor MCP lives in `.cursor/mcp.json` (gitignored). Copy from `.cursor/mcp.json.example` if missing.

**Never commit real API keys or OAuth client secrets.** Prefer Cursor **OAuth Connect** where the provider supports Dynamic Client Registration (DCR) or publishes a static Client ID for Cursor. After editing MCP config: **Cursor Settings → Tools & MCP → refresh / Connect** (or toggle the server off/on).

Cursor MCP docs: [cursor.com/docs/mcp](https://cursor.com/docs/mcp) (static `auth.CLIENT_ID` when the provider supplies one).

---

## Servers in this repo


| Server id | Endpoint / launch                        | Auth              | Status                         |
| --------- | ---------------------------------------- | ----------------- | ------------------------------ |
| `buffer`  | `https://mcp.buffer.com/mcp`             | OAuth (Cursor)    | Official cloud — **keep**      |
| `gmail`   | `https://gmailmcp.googleapis.com/mcp/v1` | Google OAuth + GCP | Official Developer Preview — **keep** |
| `stripe`  | `https://mcp.stripe.com`                 | OAuth (Cursor)    | Official cloud — added         |
| `notion`  | `https://mcp.notion.com/mcp`             | OAuth (Cursor)    | Official cloud — added         |


Exact config shape:

```json
{
  "mcpServers": {
    "buffer": { "url": "https://mcp.buffer.com/mcp" },
    "gmail": { "url": "https://gmailmcp.googleapis.com/mcp/v1" },
    "stripe": { "url": "https://mcp.stripe.com" },
    "notion": { "url": "https://mcp.notion.com/mcp" }
  }
}
```

---

## Removed (intentionally)

| Former server | Why removed |
| ------------- | ----------- |
| `meta-ads` | Cursor OAuth fails with Meta DCR (“Dynamic registration is not available for this client”). Meta has not published a Cursor Client ID. Use Claude Desktop / Marketing API elsewhere if needed. |
| `n8n` | Local instance MCP needs n8n running + MCP Access Token hassle; voice `trigger n8n <path>` still works via Jarvis (`config/settings.json`). |
| `revenuecat` | Left out per user preference while pruning broken / unused MCP entries. |

Do **not** add Meta Ads, RevenueCat, or local n8n MCP back unless you explicitly want them again.

---

## 1. Buffer

Docs: [Cursor](https://developers.buffer.com/guides/integrations/cursor.html) · [MCP](https://developers.buffer.com/guides/integrations/mcp.html)

Checklist:

- [x] Ensure `buffer.url` = `https://mcp.buffer.com/mcp`
- [ ] Cursor Settings → Tools & MCP → **Connect**
- [ ] Sign in to Buffer and approve
- [ ] Smoke: “List my Buffer channels”

---

## 2. Gmail (official, Developer Preview)

Docs: [Configure Gmail MCP](https://developers.google.com/workspace/gmail/api/guides/configure-mcp-server) · [MCP reference](https://developers.google.com/workspace/gmail/api/reference/mcp)

Checklist:

- [ ] Google Cloud project; enable `gmail.googleapis.com` and `gmailmcp.googleapis.com`
- [ ] OAuth consent scopes: `gmail.readonly`, `gmail.compose`
- [ ] Ensure `gmail.url` = `https://gmailmcp.googleapis.com/mcp/v1`
- [ ] Cursor Settings → Tools & MCP → **Connect**
- [ ] Smoke: “Search my last email about X” / “Draft a reply to …”

**Limits:** draft-only (no send). Prefer OAuth Connect — no static Bearer headers in Cursor.

---

## 3. Stripe

Docs: [Stripe MCP](https://docs.stripe.com/mcp)

Checklist:

- [x] Ensure `stripe.url` = `https://mcp.stripe.com`
- [ ] Cursor Settings → Tools & MCP → **Connect**
- [ ] Sign in to Stripe and approve (prefer restricted / least-privilege scopes)
- [ ] Smoke: “List my recent Stripe customers / payments”

**Do not** put a live secret key in git. Prefer OAuth Connect; restricted API key Bearer is only a fallback outside this repo’s example.

---

## 4. Notion

Docs: [Notion MCP](https://developers.notion.com/docs/mcp) (hosted remote)

Checklist:

- [x] Ensure `notion.url` = `https://mcp.notion.com/mcp`
- [ ] Cursor Settings → Tools & MCP → **Connect**
- [ ] Sign in to Notion and approve workspace access
- [ ] Smoke: “Search my Notion workspace for …”

---

## Jarvis desk voice (same four services)

Cursor MCP OAuth does **not** share tokens with Jarvis. Desk voice uses vaulted REST keys:

| Say | Effect |
|-----|--------|
| `integrations status` | Which of Stripe/Notion/Buffer/Gmail are linked |
| `link stripe` / `set stripe key to sk_…` | Stripe secret key → vault |
| `stripe status` / `stripe payments` | Balance / recent payment intents |
| `link notion` / `set notion token to …` | Notion integration secret |
| `notion search …` | Workspace search |
| `link buffer` / `set buffer token to …` | Buffer access token |
| `buffer channels` | List profiles |
| `link gmail` / `setup gmail oauth` | Desktop OAuth loopback → vault tokens + auto-refresh |
| `set gmail client id to …` / `set gmail client secret to …` | Google Cloud OAuth Desktop client |
| `set gmail token to …` / `set gmail refresh token to …` | Optional manual paste |
| `gmail inbox` / `gmail status` / `clear email` | Inbox ops (401 → refresh once + retry) |

Redirect URI: `http://127.0.0.1:8753/` (register on the Desktop OAuth client).

Module: `jarvis/core/gmail_oauth.py` + `jarvis/core/cloud_integrations.py`. Keys live in DPAPI vault (`gmail_client_id`, `gmail_client_secret`, `gmail_access_token`, `gmail_refresh_token`).

**Never paste secrets in chat** — say the set-key phrases to Jarvis, or edit vault via settings save.

---

## After connect

1. Reload MCP in Cursor (or restart agent)
2. Ask: “Which MCP tools do you have for Buffer / Gmail / Stripe / Notion?”
3. Prefer read-only prompts until scopes are trusted
4. Restart Jarvis and say **integrations status** for the desk bridge

Related: [FAQS.md](FAQS.md) · [INTEGRATIONS.md](INTEGRATIONS.md) · Jarvis subagents under `.cursor/agents/`

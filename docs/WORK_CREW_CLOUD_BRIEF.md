# Jarvis Work Crew — Cloud Brief

Additive layer on top of the eight-agent **AgentCrew**. The Work Crew is a
smaller pod of persona-named specialists that Jarvis can hand a *unit of work*
to — publishing a Reel, stitching a patch, drafting a copy pass — while the
main AgentCrew keeps handling desk conversation.

Everything is **HITL-safe by default**: destructive or external side-effects
(deploy, publish to social, execute a trade) route through
`jarvis.core.hitl.HumanInTheLoop.gate_deploy` before touching the outside
world.

## Roster

| Handle      | Role                                | Guardrail                                        |
|-------------|-------------------------------------|--------------------------------------------------|
| **MANAGER** | Dispatcher / planner                | Picks the smallest set of specialists            |
| **SCHOLAR** | Research (web / Tavily / Serper)    | Live text only — no automated purchasing         |
| **STITCH**  | Code integration / patch author     | Writes to sandbox only, no `git push --force`    |
| **REEL**    | Short-form video draft + publish    | Buffer post is HITL-gated — never auto-sends     |
| **FLIP**    | Deal / arbitrage scouting           | Reports opportunities; **never** clicks buy      |
| **LEDGER**  | Finance summaries & reporting       | **NEVER executes trades.** Read-only always      |
| **MUSE**    | Creative brainstorming / copy pass  | Drafts to sandbox; publish is HITL-gated         |

## Data flow

```
voice / hotkey  ─▶  brain.py  ─▶  WorkCrew.dispatch(request)
                                          │
                          MANAGER picks specialists
                                          │
        ┌──────────┬──────────┬──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼          ▼
     SCHOLAR    STITCH      REEL       FLIP      LEDGER      MUSE
        │          │          │          │          │          │
        └──────────┴──────────┴──────────┴──────────┴──────────┘
                                          │
                                Outcome + XP appended to
                          jarvis/data/work_outcomes.jsonl
                                          │
                        jarvis/data/agent_ops_dashboard.html
                          tails the JSONL and shows per-agent
                          tiles with XP + counts.
```

Every dispatch writes one JSONL line:

```json
{ "ts": 1738032190.123, "agent": "REEL", "kind": "buffer_post_draft",
  "ok": true, "xp": 15, "summary": "Drafted TikTok caption + hook", "hitl": false }
```

## HITL policy (must-gate)

| Verb                 | Gated?                     | Reason                                   |
|----------------------|----------------------------|------------------------------------------|
| `reel publish`       | ✅ HITL before Buffer send | External social post                     |
| `stitch push`        | ✅ HITL before git push    | Touches production branch                |
| `flip buy` / `execute` | ❌ **Refused**           | Work Crew never spends money             |
| `ledger trade` / `execute` | ❌ **Refused**       | LEDGER is read-only — see safety below   |
| `manager plan`       | Silent                     | Local dispatch only                      |
| Anything else        | Silent unless deploy       | Follows existing `HumanInTheLoop` policy |

## LEDGER safety

`LedgerAgent.execute_trade()` **must always** raise `PermissionError`. Test
coverage lives in `jarvis/core/work_crew.py` (`_ledger_never_trades`).

Any request whose text contains `buy`, `sell`, `execute`, `order`, `open
position`, `close position`, `long`, `short` **plus** a ticker / amount pattern
is routed to LEDGER's `report_only` path with an explanatory decline.

## Backends

Work Crew uses the shared `jarvis.core.llm_client.complete()` — Ollama →
**Claude Code CLI** (when `settings.prefer_claude_cli` is on) → Anthropic REST
→ OpenAI REST. Anthropic REST stays as the last cloud fallback so the crew
still works if the CLI is not yet installed.

## Claude Code CLI — Windows install

The Claude Code CLI (`claude`) gives Jarvis a headless Claude session that
respects your Claude subscription (no API-key billing needed). Install order:

1. Install **Node.js LTS** (20+) from <https://nodejs.org>. Reopen PowerShell
   afterwards so `npm` is on PATH.
2. From PowerShell (any folder):

   ```powershell
   npm install -g @anthropic-ai/claude-code
   ```

3. Confirm the binary:

   ```powershell
   claude --version
   ```

4. First launch runs an OAuth-style device login. Sign in with the same
   Anthropic account you use for Claude Pro / Max:

   ```powershell
   claude login
   ```

5. Enable it in Jarvis. Either edit `config/settings.json` and set
   `"prefer_claude_cli": true`, or say:

   > *"Jarvis, prefer Claude CLI."*

6. Optional model pin (default is the CLI's own default):

   ```powershell
   setx ANTHROPIC_MODEL "claude-sonnet-4-5"
   ```

**Rollback:** set `prefer_claude_cli` back to `false`. The client chain falls
straight back to Ollama / REST — no restart needed on the next dispatch.

**Troubleshooting:**

- `claude: command not found` → close and reopen PowerShell so the fresh npm
  global path is picked up, or run `where.exe claude` and add the folder to
  `PATH`.
- CLI login expires → run `claude login` again; the CLI stores its token in
  `%USERPROFILE%\.claude`.
- The CLI writes to `stderr` on error — the Python wrapper surfaces the last
  200 chars back into `[llm] claude-cli:` for triage.

## Voice commands

| You say                                  | Jarvis does                                          |
|------------------------------------------|------------------------------------------------------|
| `work crew status`                       | Reports specialist availability + brain backend      |
| `work crew run <task>`                   | Dispatches through MANAGER                           |
| `ask manager <task>`                     | Same as `work crew run`                              |
| `open agent ops`                         | Opens `jarvis/data/agent_ops_dashboard.html`         |
| `prefer claude cli` / `use claude cli`   | Flips `prefer_claude_cli` and persists to settings   |
| `stop claude cli`                        | Turns it back off                                    |
| `reel draft <topic>`                     | REEL builds a caption + hook (no publish)            |
| `reel publish` (during pending draft)    | HITL gate → Buffer draft POST                        |
| `ledger status`                          | Balance / recent — never a trade                     |

## Hub spokes (optional Node bridge)

If `hub/` is running (`npm run dev:server`), each Work Crew persona is mirrored
as a light MOCK_LLM-safe spoke under `hub/src/agents/` (`manager.ts`,
`scholar.ts`, `stitch.ts`, `reel.ts`, `flip.ts`, `ledger.ts`, `muse.ts`) so
n8n / Slack can hit `POST http://127.0.0.1:8787/v1/chat` with lines like
*"ask manager to plan a reel about desk security"* and get the same routing.

The hub spokes are stubs — they announce intent + persist through the bus.
They deliberately do **not** import the Python crew (no Python↔Node runtime
coupling); real execution stays in Python. This keeps `MOCK_LLM=true` safe:
no Anthropic key required, no external calls fired, LEDGER refuses trades
regardless of transport.

## Run cheat-sheet

```bat
:: 1. Boot Jarvis
run.bat

:: 2. Voice
Jarvis, work crew run: draft a reel about my clap-to-wake trick.

:: 3. Watch outcomes
start jarvis\data\agent_ops_dashboard.html

:: 4. Hub bridge (optional)
cd hub
npm install
npm run dev:server
```

# Manus AI — Jarvis bridge



Connect Jarvis to **[Manus](https://manus.im)** (iOS / web agent product) via the public API so you can spin up Manus tasks by voice.



## One-time setup



1. Open [https://manus.im](https://manus.im) and sign in.

2. Go to **API Integration** → create an API key.

3. In Jarvis, say:

    - **"link manus"** — HUD shows these steps (also opens manus.im), or

    - **"set manus key to YOUR_KEY"** — stores the key in the DPAPI vault (never committed; `settings.json` stays empty for secrets).



**Never paste API keys into chat** (Cursor, Slack, etc.). Use the voice command above or a local vault script so the key never lands in logs or transcripts. If a key was exposed, revoke/regenerate it at manus.im.



Settings (defaults in `jarvis/config.py`):



| Key | Default | Notes |

|-----|---------|--------|

| `manus_enabled` | `true` | Master switch |

| `manus_api_key` | `""` | Vaulted via `secrets_vault` |

| `manus_agent_profile` | `manus-1.6` | Also: `manus-1.6-lite`, `manus-1.6-max` |

| `manus_base_url` | `https://api.manus.ai` | Override only if needed |

| `manus_code_assist` | `true` | HUD offer when code files change (never auto-creates tasks) |

| `manus_code_assist_cooldown_sec` | `720` | Min seconds between offers (~12 min) |

| `manus_code_assist_debounce_sec` | `45` | Quiet period after last code change before offer |



## Voice commands



| Say | Effect |

|-----|--------|

| **manus status** / **is manus linked** | Link + last-task summary |

| **link manus** / **connect manus** / **setup manus** | HUD setup + opens manus.im |

| **set manus key to …** | Save key → vault + refresh bridge |

| **ask manus …** / **manus …** / **send to manus …** / **tell manus …** | `task.create`; opens `task_url` in browser |

| **manus review** / **review this with manus** / **manus improve this** / **ask manus to improve this** | Snapshot git diff (or recent `.py`) → Manus code-review task; opens URL + HUD artifact |

| **manus review file path/to/file.py** | Same, focused on one file (skips secrets / vault / `.env`) |

| **manus follow up …** / **manus continue …** | `task.sendMessage` on last task |

| **manus result** / **manus progress** / **check manus** | `task.listMessages` progress |



Aliases: bare **"manus"** → status.



## Coding assist (auto-offer)



When Manus is linked and `manus_code_assist` is on, Jarvis watches `work_project_path` / `jarvis/` for `.py` / `.ts` / `.tsx` / `.js` changes (skips `node_modules`, `__pycache__`, vault, `data/`, `.env`, etc.).



After **~45s of quiet** and if the **cooldown** has elapsed, the HUD shows:



> Ask Manus to improve recent code?



- Sets `pending_cmd = "manus review"`

- Say **yes** / click the chip → runs the explicit review flow

- **Does not** call Manus `create_task` until you accept (cost + privacy)



Snapshot (~12–20KB cap): project path note + `git diff HEAD` when available, else recently modified `.py` under `jarvis/`. Never sends vault secrets, diary, or `.env`.



Helper: `jarvis/core/manus_code_assist.py` (API stays in `manus_bridge.py`).



## API note



- Base: `https://api.manus.ai`

- Auth header: `x-manus-api-key: <key>`

- Endpoints used by `jarvis/core/manus_bridge.py`:

  - `POST /v2/task.create`

  - `GET /v2/task.listMessages`

  - `POST /v2/task.sendMessage`



Feature registry id: `manus_bridge` (v1.1 — code assist). Semantic router keeps Manus on a **local** lane (PHONE-adjacent) so Hub LLM does not swallow these intents.



## Smoke test



```powershell

C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe -c "from jarvis.core.manus_bridge import ManusBridge; print(ManusBridge().status())"

C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe -c "from jarvis.core.manus_code_assist import build_snapshot; s=build_snapshot(); print(len(s), s[:200])"

```



Expected without a key: a short “not linked” message pointing at manus.im. Snapshot builds offline (no network).



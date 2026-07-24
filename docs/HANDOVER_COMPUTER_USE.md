# Computer Use / Browser Agent — Jarvis handover

Autonomous **screenshot → LLM → mouse/keyboard** loop so Jarvis can drive a real browser or desktop like Anthropic Computer Use, OpenAI Operator-style agents, or open-source browser-use.

Existing single-step OCR clicks remain in `jarvis/core/computer_use.py`. The multi-step agent is `jarvis/core/computer_use_agent.py`.

## Free / local path (recommended — no API credits)

Uses **Ollama** + **Playwright** (JSON click/type/goto loop). No Anthropic/OpenAI billing.

### Windows setup

1. **Install Ollama:** [https://ollama.com/download](https://ollama.com/download)  
   Or winget: `winget install Ollama.Ollama`

2. **Start Ollama** (Start menu app, or `ollama serve`).

3. **Pull a vision model** (screenshot clicks):

```bat
ollama pull llava
```

Alternatives: `llama3.2-vision` · `qwen2.5vl` · `minicpm-v`

Text-only fallback (navigate/type via URLs, no screenshot clicks):

```bat
ollama pull llama3.2
```

4. **Optional real Chromium window:**

```bat
C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe -m pip install playwright
C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe -m playwright install chromium
```

5. **Voice:**

- **computer use provider local** (or `ollama` / `free`)
- **computer use: open google maps**
- **computer use status** / **setup computer use**

Jarvis will say exactly what’s missing: Ollama not installed, not running, or which `ollama pull …` to run.

### Optional: browser-use + local Ollama

```bat
C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe -m pip install browser-use
```

With Ollama running and a model installed, `browser_use` can use `ChatOllama` (no cloud key). Prefer the built-in `ollama` provider for the screenshot→JSON loop; use `browser_use` when you want that package’s DOM agent.

## Paid cloud fallback (optional)

| Say | Stores |
|-----|--------|
| **set anthropic key to YOUR_KEY** | `anthropic_api_key` → DPAPI vault |
| **set openai key to YOUR_KEY** | `openai_api_key` → DPAPI vault |

Keys from [console.anthropic.com](https://console.anthropic.com) / [platform.openai.com](https://platform.openai.com).  
**Prefer the HUD command bar** for long keys (voice STT truncates).  
`settings.json` keeps empty placeholders; secrets live in `jarvis/data/vault/`.

Verify without exposing the key:

```bat
C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe -c "from jarvis.core.secrets_vault import get_vault, secret_meta; print(secret_meta(get_vault().get('anthropic_api_key')))"
```

Then say **computer use status**.

## Settings (`config/settings.json`)

| Key | Default | Notes |
|-----|---------|--------|
| `computer_use_enabled` | `true` | Master switch |
| `computer_use_provider` | `auto` | `auto` · `ollama`/`local`/`free` · `anthropic` · `openai` · `browser_use` · `desktop` · stubs |
| `computer_use_prefer_local` | `true` | `auto` tries Ollama (then browser-use) before paid APIs |
| `computer_use_ollama_host` | `http://127.0.0.1:11434` | Ollama base URL |
| `computer_use_ollama_model` | `""` | Empty = auto-detect (vision preferred) |
| `computer_use_max_steps` | `40` | Hard stop |
| `computer_use_headless` | `false` | Show real Chromium when Playwright is used |
| `computer_use_confirm_long_runs` | `true` | HITL before long sessions |
| `computer_use_confirm_steps` | `8` | Ask permission when max steps ≥ this |
| `computer_use_anthropic_model` | `claude-sonnet-4-5` | Computer-use capable Claude |
| `computer_use_openai_model` | `gpt-4.1` | Vision chat model |
| `anthropic_api_key` / `openai_api_key` | `""` | Vaulted |

`auto` with `computer_use_prefer_local=true`: Ollama → browser-use (local or cloud) → Anthropic → OpenAI → desktop.

## Voice commands

| Say | Effect |
|-----|--------|
| **computer use status** / **browser agent status** | Readiness / running step |
| **setup computer use** / **link computer use** | HUD setup card (free path first) |
| **computer use provider local** / **ollama** / **free** | Switch to free local provider |
| **computer use provider anthropic** (etc.) | Switch provider |
| **set anthropic key to …** / **set openai key to …** | Vault + enable (optional) |
| **computer use: …** / **browser agent: …** / **operator: …** | Start agent session |
| **build a site for …** | Starts agent with Maps → Lovable framing |
| **stop computer use** / **cancel computer use** | Abort mid-run |

## Example

```
computer use provider local
computer use: open google maps
```

or (with vision model):

```
computer use: find a cafe nearby with a weak website, get their info from Google Maps, then go to lovable.dev and draft a simple site
```

Expect HITL **Approve** when `computer_use_confirm_long_runs` is on and max steps ≥ `computer_use_confirm_steps`. Say **stop computer use** anytime.

## Providers

| Provider | Status | What works |
|----------|--------|------------|
| **ollama** / **local** | **Live (free)** | Local vision/text → JSON actions → Playwright. Vision model = screenshot clicks; text-only = goto/type/key. |
| **anthropic** | **Live (paid)** | Claude Computer Use API. Desktop via pyautogui. Needs `anthropic_api_key`. |
| **openai** | **Live (paid)** | Vision chat → JSON actions. Playwright preferred. Needs `openai_api_key`. |
| **browser_use** | **Optional** | Package + cloud key **or** local `ChatOllama`. Owns its own browser. |
| **desktop** | **Live (limited)** | Local OCR/macros only — no autonomous vision loop. |
| **gemini** / **skyvern** / **openinterpreter** | Stub | Documented for later |

Boot stays safe: Playwright / browser-use / cloud SDKs are optional (`try/except`).

## Limitations vs Claude computer-use

- Local vision models are weaker at precise UI grounding than Claude’s computer-use tool.
- Expect more steps, occasional mis-clicks, and slower inference on CPU/GPU.
- Text-only Ollama mode cannot click by coordinates — use direct URLs.
- Anthropic path still best for hard desktop automation when credits allow.

## Safety

- HITL permission before long autonomous runs (same gate as deploy/structure).
- Does **not** auto-complete purchases; prompts tell the model to stop on payment/send.
- Existing face **security_gate** is unchanged; computer use does not bypass it.
- Cancel is always available: **stop computer use**.
- Never put API keys in git, chat, or handover logs.

## Files

| Path | Role |
|------|------|
| `jarvis/core/computer_use.py` | Single-step OCR click/type (unchanged behaviour) |
| `jarvis/core/computer_use_agent.py` | Agent loop + providers + surfaces |
| `jarvis/brain.py` | Voice routing + HITL + HUD status |
| `jarvis/core/commands.py` | Aliases / fast-local status/stop |
| `jarvis/config.py` + `config/settings.json` | Settings |
| `jarvis/core/secrets_vault.py` | `anthropic_api_key`, `openai_api_key` |
| `jarvis/core/feature_registry.py` | `computer_use` feature |

## Pitfalls

- Anthropic path uses **desktop** coordinates (full display). Keep the target window visible.
- Ollama / OpenAI + Playwright use the **browser viewport** (1280×800 default).
- Ollama installed but idle → Jarvis says start Ollama / `ollama serve`.
- Model missing → Jarvis says `ollama pull …`.
- Do not overwrite `proactive.py` — proactive lives in `proactive_agent.py`.

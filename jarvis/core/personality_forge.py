"""Personality Forge — synthetic Jarvis datasets, Axolotl LoRA, TRL DPO.

Pipeline:
  1) Generate thousands of British / "Sir" conversations (SFT)
  2) Build DPO pairs: chosen = Jarvis style, rejected = generic assistant
  3) Emit Axolotl YAML for QLoRA fine-tuning (low VRAM)
  4) Emit TRL DPO train script for preference alignment
  5) Optionally harvest mic/RLHF turns into the dataset
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR, ROOT

FORGE_ROOT = DATA_DIR / "personality_forge"
SFT_PATH = FORGE_ROOT / "sft_sharegpt.jsonl"
DPO_PATH = FORGE_ROOT / "dpo_pairs.jsonl"
AXOLOTL_YAML = FORGE_ROOT / "axolotl_jarvis_qlora.yml"
TRL_SCRIPT = FORGE_ROOT / "train_dpo_trl.py"
REQ_PATH = FORGE_ROOT / "requirements-training.txt"
README_PATH = FORGE_ROOT / "README.md"
META_PATH = FORGE_ROOT / "forge_meta.json"
HARVEST_PATH = FORGE_ROOT / "harvested.jsonl"

# Seed prompts covering desk / life / tech
_USER_PROMPTS = [
    "What's the weather?",
    "What time is it?",
    "Lock the PC.",
    "Open Chrome.",
    "Play some focus music.",
    "How much did I spend today?",
    "Cash App spending this week.",
    "Summarize my progress.",
    "Check my email.",
    "Tell me about my day.",
    "Scaffold a React app.",
    "Publish the app.",
    "Sync cash app.",
    "What's on my calendar?",
    "Start work mode.",
    "End work mode.",
    "Add task buy groceries.",
    "Search the web for OLED monitors.",
    "Take a screenshot.",
    "Are you listening?",
    "Who are you?",
    "How are the systems?",
    "Dim the lights.",
    "Good morning.",
    "I'm heading out.",
    "Welcome back briefing.",
    "Run a system health check.",
    "Mute yourself.",
    "Volume up.",
    "Open my project folder.",
    "Remind me to stretch.",
    "What's the CPU usage?",
    "Draft a polite email declining a meeting.",
    "Explain LoRA fine-tuning simply.",
    "Should I push to master?",
    "Find a coffee place nearby.",
    "Pause the music.",
    "Switch to headphones.",
    "Test the microphone.",
    "Generate a personality dataset.",
    "Start DPO training.",
    "What's my app scoreboard?",
    "Kill the CPU hog.",
    "Safety snapshot.",
    "Whisper mode on.",
    "Help.",
]

_GENERIC_TEMPLATES = [
    "Sure! {topic}",
    "Okay, I can help with that. {topic}",
    "No problem. {topic}",
    "Here's what I found: {topic}",
    "Done! {topic}",
    "Alright. {topic}",
]

_JARVIS_TEMPLATES = [
    "Right away, Sir. {topic}",
    "At once, Sir. {topic}",
    "Very good, Sir. {topic}",
    "On it. {topic}",
    "Systems ready — {topic}",
    "As you wish, Sir. {topic}",
    "Standing by. {topic}",
]

_JARVIS_TOPICS = {
    "weather": "Fetching local telemetry now.",
    "time": "Checking the chronometer.",
    "lock": "Securing the workstation.",
    "chrome": "Launching Chrome.",
    "music": "Queuing a focus soundscape.",
    "spend": "Pulling today's ledger.",
    "cash": "Reviewing Cash App outflows.",
    "progress": "Compiling your progress brief.",
    "email": "Opening the inbox triage.",
    "day": "Reading your day stack.",
    "scaffold": "Spinning up a Pulse Arena scaffold.",
    "publish": "Building production and staging the publish preview.",
    "sync": "Syncing Cash App receipts from iCloud Mail.",
    "calendar": "Checking the agenda.",
    "work": "Engaging work mode.",
    "task": "Logged to your priority stack.",
    "search": "Running a web sweep.",
    "screenshot": "Capturing the active display.",
    "mic": "Microphone path is live.",
    "who": "I am Jarvis — your executive operator.",
    "systems": "All grids green, Sir.",
    "lights": "Adjusting the ambient lighting.",
    "morning": "Good morning. Systems operational.",
    "away": "Away mode engaged. I'll hold the fort.",
    "return": "Welcome back. Desk brief ready.",
    "health": "Running a system pulse check.",
    "mute": "Going silent.",
    "volume": "Raising audio output.",
    "folder": "Opening the project directory.",
    "remind": "I'll nudge you shortly.",
    "cpu": "Sampling processor load.",
    "email_draft": "Drafting a concise, polite decline.",
    "lora": "LoRA adapts a base model with small rank matrices — personality without a full retrain.",
    "push": "I'd advise a safety snapshot before pushing to master, Sir.",
    "coffee": "Scanning nearby cafés.",
    "pause": "Pausing playback.",
    "headphones": "Routing audio to your headset.",
    "dataset": "Forging synthetic British Sir-style conversations.",
    "dpo": "Preference alignment will favour Jarvis diction over generic replies.",
    "scoreboard": "Reading the Pulse Arena leaderboard.",
    "healer": "Identifying the resource hog.",
    "snapshot": "Taking a git safety snapshot.",
    "whisper": "Whisper mode on — softer voice.",
    "help": "Try weather, spend, progress, scaffold, or sync cash app.",
}


def _topic_for(prompt: str) -> str:
    p = prompt.lower()
    rules = [
        ("weather", "weather"),
        ("time", "time"),
        ("lock", "lock"),
        ("chrome", "chrome"),
        ("music", "music"),
        ("spend", "spend"),
        ("cash app", "cash"),
        ("progress", "progress"),
        ("email", "email"),
        ("day", "day"),
        ("scaffold", "scaffold"),
        ("publish", "publish"),
        ("sync", "sync"),
        ("calendar", "calendar"),
        ("work mode", "work"),
        ("task", "task"),
        ("search", "search"),
        ("screenshot", "screenshot"),
        ("mic", "mic"),
        ("who are you", "who"),
        ("systems", "systems"),
        ("light", "lights"),
        ("good morning", "morning"),
        ("heading out", "away"),
        ("welcome back", "return"),
        ("health", "health"),
        ("mute", "mute"),
        ("volume", "volume"),
        ("folder", "folder"),
        ("remind", "remind"),
        ("cpu", "cpu"),
        ("email declining", "email_draft"),
        ("lora", "lora"),
        ("push", "push"),
        ("coffee", "coffee"),
        ("pause", "pause"),
        ("headphones", "headphones"),
        ("dataset", "dataset"),
        ("dpo", "dpo"),
        ("scoreboard", "scoreboard"),
        ("cpu hog", "healer"),
        ("snapshot", "snapshot"),
        ("whisper", "whisper"),
        ("help", "help"),
    ]
    for needle, key in rules:
        if needle in p:
            return _JARVIS_TOPICS.get(key, "Proceeding.")
    return "Proceeding with that request."


class PersonalityForge:
    """Generate + export training artefacts for Jarvis personality adaptation."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else FORGE_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    def status(self) -> str:
        sft_n = self._count_lines(SFT_PATH)
        dpo_n = self._count_lines(DPO_PATH)
        har_n = self._count_lines(HARVEST_PATH)
        meta = self._meta()
        last = meta.get("last_generate") or "never"
        return (
            f"Personality forge — SFT {sft_n} chats, DPO {dpo_n} pairs, "
            f"harvested {har_n}. Last generate: {last}. "
            f"Artefacts in {self.root}."
        )

    def generate(
        self,
        *,
        count: int = 2000,
        seed: int = 42,
        british: bool = True,
        honorific: str = "Sir",
    ) -> str:
        """Create SFT ShareGPT jsonl + DPO preference pairs."""
        n = max(50, min(20_000, int(count)))
        rng = random.Random(int(seed))
        honorific = (honorific or "Sir").strip() or "Sir"

        sft_lines: list[str] = []
        dpo_lines: list[str] = []

        # Fold harvested mic/RLHF examples first
        harvested = self._load_harvest()
        for h in harvested:
            user = h.get("user") or h.get("prompt") or ""
            jarvis = h.get("jarvis") or h.get("chosen") or h.get("reply") or ""
            generic = h.get("generic") or h.get("rejected") or ""
            if user and jarvis:
                sft_lines.append(
                    json.dumps(self._sharegpt(user, jarvis, honorific), ensure_ascii=False)
                )
                if not generic:
                    generic = self._generic_reply(user, rng)
                dpo_lines.append(
                    json.dumps(
                        {
                            "prompt": user,
                            "chosen": jarvis,
                            "rejected": generic,
                        },
                        ensure_ascii=False,
                    )
                )

        while len(sft_lines) < n:
            user = rng.choice(_USER_PROMPTS)
            # Light paraphrases
            if rng.random() < 0.35:
                user = self._paraphrase(user, rng)
            topic = _topic_for(user)
            jarvis = self._jarvis_reply(topic, honorific, british, rng)
            generic = self._generic_reply(user, rng)
            sft_lines.append(
                json.dumps(self._sharegpt(user, jarvis, honorific), ensure_ascii=False)
            )
            dpo_lines.append(
                json.dumps(
                    {"prompt": user, "chosen": jarvis, "rejected": generic},
                    ensure_ascii=False,
                )
            )

        SFT_PATH.write_text("\n".join(sft_lines[:n]) + "\n", encoding="utf-8")
        DPO_PATH.write_text("\n".join(dpo_lines[:n]) + "\n", encoding="utf-8")
        self._write_axolotl_yaml(honorific=honorific)
        self._write_trl_script()
        self._write_requirements()
        self._write_readme()
        meta = self._meta()
        meta.update(
            {
                "last_generate": time.strftime("%Y-%m-%d %H:%M:%S"),
                "sft_count": min(n, len(sft_lines)),
                "dpo_count": min(n, len(dpo_lines)),
                "honorific": honorific,
                "british": british,
            }
        )
        META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return (
            f"Personality dataset ready — {min(n, len(sft_lines))} SFT chats and "
            f"{min(n, len(dpo_lines))} DPO pairs. "
            f"Axolotl config: {AXOLOTL_YAML.name}. TRL script: {TRL_SCRIPT.name}. "
            f"Say train personality when your GPU stack is installed."
        )

    def harvest_turn(
        self,
        user: str,
        jarvis_reply: str,
        *,
        generic: str = "",
        source: str = "mic",
    ) -> None:
        """Append a live mic/voice turn for the next generate pass."""
        user = (user or "").strip()[:400]
        jarvis_reply = (jarvis_reply or "").strip()[:600]
        if not user or not jarvis_reply:
            return
        row = {
            "ts": time.time(),
            "source": source,
            "user": user,
            "jarvis": jarvis_reply,
            "generic": (generic or "").strip()[:600],
        }
        with HARVEST_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def harvest_from_rlhf(self, limit: int = 200) -> str:
        """Pull approved RLHF events into harvest file."""
        rlhf = DATA_DIR / "rlhf_feedback.jsonl"
        if not rlhf.exists():
            return "No RLHF feedback yet — approve good answers first."
        added = 0
        try:
            lines = rlhf.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            return f"RLHF read failed: {e}"
        for line in lines[-max(1, min(2000, limit * 4)) :]:
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("verdict") != "approve":
                continue
            prompt = (ev.get("prompt") or "").strip()
            reply = (ev.get("reply") or "").strip()
            if not prompt or not reply:
                continue
            self.harvest_turn(prompt, reply, source="rlhf")
            added += 1
            if added >= limit:
                break
        return f"Harvested {added} approved RLHF turns into the forge."

    def ensure_configs(self) -> str:
        self._write_axolotl_yaml()
        self._write_trl_script()
        self._write_requirements()
        self._write_readme()
        return f"Training configs refreshed under {self.root}."

    def train_hint(self, *, backend: str = "axolotl") -> str:
        b = (backend or "axolotl").lower()
        if b in ("dpo", "trl"):
            return (
                f"DPO via TRL — install: pip install -r {REQ_PATH}. "
                f"Then: {sys.executable} {TRL_SCRIPT}. "
                "It teaches the model to prefer Jarvis-style answers over generic ones."
            )
        return (
            f"Axolotl QLoRA — install axolotl in a CUDA env, then: "
            f"accelerate launch -m axolotl.cli.train {AXOLOTL_YAML}. "
            "That bakes Sir/British speech patterns into a LoRA adapter."
        )

    def try_launch_trl(self) -> str:
        """Best-effort local DPO launch (may fail if deps missing)."""
        self.ensure_configs()
        if not DPO_PATH.exists() or self._count_lines(DPO_PATH) < 10:
            self.generate(count=500)
        try:
            p = subprocess.Popen(
                [sys.executable, str(TRL_SCRIPT)],
                cwd=str(self.root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return (
                f"TRL DPO training started (pid {p.pid}). "
                f"Watch {self.root / 'dpo_output'} when dependencies are installed."
            )
        except Exception as e:
            return f"Could not launch TRL train: {e}. {self.train_hint(backend='trl')}"

    # --- generators ---

    def _sharegpt(self, user: str, assistant: str, honorific: str) -> dict[str, Any]:
        system = (
            "You are JARVIS, a highly advanced executive assistant inspired by Iron Man. "
            f"Tone: professional, efficient, marginally witty, lightly British. "
            f"Address the user as {honorific}. Keep spoken replies concise."
        )
        return {
            "conversations": [
                {"from": "system", "value": system},
                {"from": "human", "value": user},
                {"from": "gpt", "value": assistant},
            ]
        }

    def _jarvis_reply(
        self, topic: str, honorific: str, british: bool, rng: random.Random
    ) -> str:
        tmpl = rng.choice(_JARVIS_TEMPLATES)
        line = tmpl.format(topic=topic)
        line = line.replace("Sir", honorific)
        if british and rng.random() < 0.4:
            extras = [
                " Shall I proceed?",
                " Awaiting your command.",
                " Systems nominal.",
                " Quite straightforward.",
            ]
            if not line.endswith((".", "?", "!")):
                line += "."
            if rng.random() < 0.5:
                line = line.rstrip(".") + "." + rng.choice(extras)
        # Soft British lexicon swaps
        if british:
            line = line.replace("Okay,", "Very good,").replace("Alright,", "Right then,")
        return line[:320]

    def _generic_reply(self, user: str, rng: random.Random) -> str:
        topic = "I can help with that."
        if "weather" in user.lower():
            topic = "It looks like a normal day outside."
        elif "spend" in user.lower() or "cash" in user.lower():
            topic = "You should check your banking app for totals."
        elif "time" in user.lower():
            topic = "Please check a clock for the current time."
        return rng.choice(_GENERIC_TEMPLATES).format(topic=topic)

    def _paraphrase(self, text: str, rng: random.Random) -> str:
        prefixes = ["Hey Jarvis, ", "Jarvis — ", "Please ", ""]
        suffixes = [" please", " now", ", thanks", ""]
        return (rng.choice(prefixes) + text[0].lower() + text[1:] + rng.choice(suffixes)).strip()

    # --- exporters ---

    def _write_axolotl_yaml(self, *, honorific: str = "Sir") -> None:
        # Paths use forward slashes for Axolotl / Linux-friendly CUDA boxes
        sft = SFT_PATH.as_posix()
        out = (self.root / "axolotl_output").as_posix()
        yaml = f"""# Jarvis personality — Axolotl QLoRA (LoRA / low-rank adaptation)
# Install: https://github.com/axolotl-ai-cloud/axolotl
# Train: accelerate launch -m axolotl.cli.train {AXOLOTL_YAML.as_posix()}

base_model: TinyLlama/TinyLlama-1.1B-Chat-v1.0
model_type: LlamaForCausalLM
tokenizer_type: LlamaTokenizer

load_in_8bit: false
load_in_4bit: true
strict: false

datasets:
  - path: {sft}
    type: sharegpt
    conversation: chatml

dataset_prepared_path: {self.root.as_posix()}/prepared
val_set_size: 0.02
output_dir: {out}

adapter: qlora
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
lora_target_modules:
  - q_proj
  - v_proj
  - k_proj
  - o_proj

sequence_len: 1024
sample_packing: true
pad_to_sequence_len: true

gradient_accumulation_steps: 4
micro_batch_size: 2
num_epochs: 2
optimizer: adamw_bnb_8bit
lr_scheduler: cosine
learning_rate: 0.0002

train_on_inputs: false
group_by_length: false
bf16: auto
fp16: false
tf32: false

gradient_checkpointing: true
logging_steps: 10
warmup_ratio: 0.03
evals_per_epoch: 1
saves_per_epoch: 1
weight_decay: 0.0
special_tokens:
  pad_token: "<|endoftext|>"

# Personality intent baked into data: British diction, address user as {honorific}.
"""
        AXOLOTL_YAML.write_text(yaml, encoding="utf-8")

    def _write_trl_script(self) -> None:
        script = r'''"""TRL DPO — prefer Jarvis-style answers over generic ones.

Install (CUDA recommended):
  pip install -r requirements-training.txt

Run:
  python train_dpo_trl.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DPO = ROOT / "dpo_pairs.jsonl"
OUT = ROOT / "dpo_output"


def load_pairs(path: Path, limit: int = 4000):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return rows


def main() -> None:
    try:
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import DPOConfig, DPOTrainer
        from peft import LoraConfig
    except ImportError as e:
        raise SystemExit(
            "Missing training deps. pip install -r requirements-training.txt\n" + str(e)
        )

    if not DPO.exists():
        raise SystemExit(f"Missing {DPO} — generate the personality dataset first.")

    pairs = load_pairs(DPO)
    if len(pairs) < 20:
        raise SystemExit("Need at least 20 DPO pairs.")

    # prompt / chosen / rejected columns for TRL
    ds = Dataset.from_list(
        [
            {
                "prompt": p["prompt"],
                "chosen": p["chosen"],
                "rejected": p["rejected"],
            }
            for p in pairs
        ]
    )

    model_id = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto")
    peft = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    )

    args = DPOConfig(
        output_dir=str(OUT),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=5e-5,
        num_train_epochs=1,
        logging_steps=10,
        save_steps=200,
        bf16=False,
        remove_unused_columns=False,
        max_length=512,
        max_prompt_length=256,
    )

    trainer = DPOTrainer(
        model=model,
        args=args,
        train_dataset=ds,
        processing_class=tokenizer,
        peft_config=peft,
    )
    trainer.train()
    trainer.save_model(str(OUT))
    print("DPO adapter saved to", OUT)


if __name__ == "__main__":
    main()
'''
        TRL_SCRIPT.write_text(script, encoding="utf-8")

    def _write_requirements(self) -> None:
        REQ_PATH.write_text(
            "\n".join(
                [
                    "# Optional GPU training stack for Personality Forge",
                    "torch>=2.2.0",
                    "transformers>=4.43.0",
                    "datasets>=2.19.0",
                    "accelerate>=0.33.0",
                    "peft>=0.12.0",
                    "trl>=0.9.0",
                    "bitsandbytes>=0.43.0; platform_system != 'Darwin'",
                    "# Axolotl (separate env recommended): pip install axolotl",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _write_readme(self) -> None:
        README_PATH.write_text(
            f"""# Personality Forge

Synthetic data + LoRA/DPO pipeline for baking Jarvis speech patterns
(British diction, address user as Sir, concise operator tone).

## Tools

| Stage | Tool | Role |
|-------|------|------|
| Data | Jarvis forge | Generate thousands of SFT + DPO conversations |
| SFT / LoRA | **Axolotl** | QLoRA fine-tune without full retrain |
| Alignment | **TRL DPO** | Prefer Jarvis answer over generic assistant |

## Voice commands

- `generate personality dataset` / `forge personality data`
- `personality forge status`
- `harvest rlhf for training`
- `train personality` (Axolotl hint) / `start dpo training`
- Mic: live turns can be harvested when you approve good answers

## Files

- `{SFT_PATH.name}` — ShareGPT SFT chats
- `{DPO_PATH.name}` — chosen=Jarvis / rejected=generic
- `{AXOLOTL_YAML.name}` — Axolotl QLoRA config
- `{TRL_SCRIPT.name}` — TRL DPO trainer

## Mic

Jarvis already listens on your preferred mic (`mic_prefer` in settings).
Approve good spoken replies (RLHF) then `harvest rlhf for training` before regenerate.
""",
            encoding="utf-8",
        )

    def _load_harvest(self) -> list[dict[str, Any]]:
        if not HARVEST_PATH.exists():
            return []
        rows = []
        for line in HARVEST_PATH.read_text(encoding="utf-8").splitlines()[-2000:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows

    def _meta(self) -> dict[str, Any]:
        try:
            return json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _count_lines(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            return 0

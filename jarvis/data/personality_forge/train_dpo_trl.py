"""TRL DPO — prefer Jarvis-style answers over generic ones.

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

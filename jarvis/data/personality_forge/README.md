# Personality Forge

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

- `sft_sharegpt.jsonl` — ShareGPT SFT chats
- `dpo_pairs.jsonl` — chosen=Jarvis / rejected=generic
- `axolotl_jarvis_qlora.yml` — Axolotl QLoRA config
- `train_dpo_trl.py` — TRL DPO trainer

## Mic

Jarvis already listens on your preferred mic (`mic_prefer` in settings).
Approve good spoken replies (RLHF) then `harvest rlhf for training` before regenerate.

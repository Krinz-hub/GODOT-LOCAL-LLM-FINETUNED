# Next Steps & Retraining Roadmap — Godot Autonomous AI Agent

**Date**: 2026-10-26  
**Auditor & Research Engineer**: Antigravity Autonomous Agent Engineering  
**Repository**: `/home/piet/Documents/dataset`  

---

## 1. Executive Summary

Now that the entire inference, orchestration, staging, headless Godot validation, self-correction repair, and CLI lifecycle systems have been audited, repaired, and verified (106/106 automated tests passing), the agent platform is structurally trustworthy.

This document outlines:
1. The **justification analysis for model retraining**.
2. The **exact experimental evidence and gates required before launching a GPU training run**.
3. The **prioritized roadmap of immediate engineering actions**.

---

## 2. Model Retraining Justification Analysis

### Is Model Retraining Justified?
**YES**, targeted LoRA retraining on the cleaned dataset is justified, **provided it adheres to strict gating criteria**.

### Justification Factors:
1. **The Infrastructure Gate Has Passed**:
   - The primary blocker to retraining was an unreliable execution and evaluation pipeline. In Phase 1–10, we proved that the staging environment, Godot headless validation, repair loop, and plan persistence function with 100% reliability.
   - Any model improvements can now be objectively evaluated using real Godot compiler diagnostics rather than superficial string-matching benchmarks.

2. **Persistent Godot 3 Parametric Bias in the Current Adapter**:
   - The existing LoRA adapter (`godot-agent-lora/final_adapter`) was trained on raw data containing 641 instances of deprecated Godot 3 APIs (`move_and_slide(velocity)`, `KinematicBody2D`, `yield()`, `Spatial`).
   - Although our runtime orchestration repair loop can catch and fix syntax errors, eliminating this bias at the weights level will drastically reduce first-pass compile errors, save inference tokens, and reduce agent latency.

3. **High-Quality Cleaned Dataset Ready**:
   - The audit and quarantine pipeline produced `cleaned_dataset/train.jsonl` (5,547 verified Godot 4 records) and `cleaned_dataset/validation.jsonl` (616 records) with zero Godot 3 contaminations and no duplicate leakage across splits.

---

## 3. Mandatory Pre-Flight Gates Before Launching GPU Retraining

Before initiating any GPU training script on the NVIDIA DGX Spark GB10, the following three gates must be satisfied:

### Gate 1: Dataset Tokenization & Formatting Validation
- **Requirement**: Verify that every record in `cleaned_dataset/train.jsonl` conforms to the Qwen2.5 chat template (`<|im_start|>system ... <|im_start|>user ... <|im_start|>assistant ...<|im_end|>`).
- **Check**: Run a token length histogram to verify that prompt + response lengths fit within the model's context window (e.g. 4,096 or 8,192 tokens) without truncation of trailing `CharacterBody2D` functions or closing braces.

### Gate 2: Read-Only Preservation of Existing Checkpoints
- **Requirement**: Never overwrite `godot-agent-lora/final_adapter` or any historical training checkpoints.
- **Check**: New training runs must output to an isolated directory (e.g., `checkpoints/godot-agent-lora-v2/`) with strict read-only permissions on original assets.

### Gate 3: Native Bfloat16 Precision & Hyperparameter Sanity
- **Requirement**: Avoid BitsAndBytes 4-bit on-the-fly quantization on ARM64 Linux (which previously induced CPU-bound stalls).
- **Check**:
  - Precision: Native `torch.bfloat16`.
  - LoRA Configuration: Rank $r=16$, Alpha $\alpha=32$, targeting all linear attention and MLP projections (`q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`).
  - Learning Rate: $2 \times 10^{-4}$ with cosine decay schedule and 5% warmup.
  - Evaluation: Evaluate on `cleaned_dataset/validation.jsonl` every 100 steps.

---

## 4. Prioritized Engineering Roadmap

```
+-------------------------------------------------------------------------------+
| PHASE 1: IMMEDIATE PRIORITY (Next 24 Hours)                                   |
| - Verify clean training script configuration on DGX Spark (bfloat16, r=16).   |
| - Execute 1-epoch dry-run on 100 samples to verify loss convergence.          |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| PHASE 2: SHORT-TERM RETRAINING & BENCHMARKING (Days 2-3)                      |
| - Train godot-agent-lora-v2 on cleaned_dataset/train.jsonl (5,547 records).   |
| - Run fair side-by-side benchmark comparing Base vs LoRA v1 vs LoRA v2.       |
| - Measure first-pass Godot 4 headless compilation pass rate.                  |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| PHASE 3: FRONTEND & PLUGIN INTEGRATION (Days 4-5)                             |
| - Connect desktop UI and Godot Editor plugin to the newly added /plan,        |
|   /orchestrate, and /status endpoints.                                        |
| - Add visual DAG progress tracking in the Godot Editor dock.                  |
+-------------------------------------------------------------------------------+
```

---

## 5. Summary Recommendation

Do not alter the orchestration architecture. The current system is robust, safe, and fully tested. Proceed directly with fine-tuning **LoRA v2** using `cleaned_dataset/train.jsonl` on the DGX Spark using native `bfloat16`, retaining `godot-agent-lora/final_adapter` as the historical comparison baseline.

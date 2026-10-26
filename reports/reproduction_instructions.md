# Godot AI Agent: Reproduction & Verification Guide

This guide provides the exact commands, environment configurations, and steps required to independently reproduce all evaluations, audits, and tests conducted during this mission.

---

## 1. System Requirements & Environment

- **Operating System**: Linux x86_64 or aarch64
- **Python**: 3.12+ with virtual environment at `.venv`
- **Godot 4 Executable**: Godot 4.7.2 or higher located at `/home/piet/.local/bin/godot4`
- **GPU**: NVIDIA GB10 or compatible modern GPU with CUDA 12+/13+ support
- **Dependencies**: `torch`, `transformers>=4.40`, `peft>=0.10`, `bitsandbytes`

Activate the workspace environment:
```bash
cd /home/piet/Documents/dataset
source .venv/bin/activate
export GODOT_BIN="/home/piet/.local/bin/godot4"
```

---

## 2. Reproducing the Dataset Audit & Cleaning Pipeline

To audit the 7,990 training records, quarantine unfixable Godot 3 patterns, eliminate exact/near duplicates, and generate the clean leakage-free splits:

```bash
python3 scripts/clean_and_audit_dataset.py \
    --input ./final_godot_sharegpt.jsonl \
    --output-dir ./cleaned_dataset \
    --manifest ./reports/dataset_exclusion_manifest.jsonl \
    --report ./reports/dataset_quality_report.md
```

**Expected Outputs**:
- `reports/dataset_exclusion_manifest.jsonl`: Line-by-line record of all 1,827 excluded records with reasons.
- `reports/dataset_quality_report.md`: Markdown summary of clean Godot 4 records and legacy pattern breakdown.
- `cleaned_dataset/train.jsonl`: 5,547 pure Godot 4 training records.
- `cleaned_dataset/val.jsonl`: 308 validation records.
- `cleaned_dataset/test.jsonl`: 308 held-out evaluation records.

---

## 3. Running the Trustworthy Evaluation Harness

To run the multi-layer evaluation suite (Output Integrity, Godot 4 Headless Syntax, Scene Structure, Functional Execution, and Negative Tests) against an active agent server:

```bash
# In terminal 1: Start the agent server
python3 godot_agent_server.py --port 8000

# In terminal 2: Run the trustworthy evaluation harness
python3 scripts/eval_harness.py --server-url http://127.0.0.1:8000 --output reports/trustworthy_benchmark.json
```

---

## 4. Running the Unit & Regression Test Suites

To execute all unit and regression tests covering Godot 4 API checks, delimited action parsing, and bounded self-correction:

```bash
# Run model evaluation unit tests
python3 -m unittest logic/tests/test_model_evaluation.py

# Run bounded self-correction staging and repair tests
python3 -m unittest logic/tests/test_self_correction.py

# Run server REST API and execution tests
python3 -m unittest logic/tests/test_agent_server.py
```

---

## 5. Running the 3-Way Fair Model Comparison

To run the head-to-head evaluation across:
1. Base Model (`Qwen/Qwen2.5-Coder-7B-Instruct`)
2. Fine-Tuned Model (`Qwen2.5-Coder-7B` + `godot-agent-lora`)
3. Fine-Tuned Model + Repaired Self-Correction Pipeline

```bash
python3 scripts/compare_models.py
```

**Expected Outputs**:
- `reports/fair_model_comparison.json`: Complete raw JSON comparison data.
- `reports/evaluation_results.md`: Full task-by-task markdown comparison table with compiler diagnostics.

# Implementation Audit & Environmental Baseline Report

**Timestamp:** 2026-10-26T11:45:00+05:30  
**Repository:** `Krinz-hub/GODOT-LOCAL-LLM-FINETUNED` (`/home/piet/Documents/dataset`)  
**Auditor:** Senior ML & Infrastructure Pair Engineer  

---

## 1. Executive Summary & Core Findings

This audit establishes the empirical baseline of the local Godot AI agent before implementing any modifications.

1. **Benchmark Vanity Metric**: The reported "90.0% Total Score" in `reports/model_eval_benchmark.json` does not measure code functionality or semantic validity. 50% of the score is based on naive keyword substring searches, 25% on markdown code-fence detection, and 25% on length and lack of `"TODO"`. As a result, code that completely fails to parse in Godot 4 (such as Godot 3 signal syntax in test `T4_ENGINE_API`) was awarded 85/100 points.
2. **Dataset Contamination**: The active training dataset (`final_godot_sharegpt.jsonl` -> `godot_training_workspace/data/train.jsonl`, 7,990 records) is contaminated with 641 records (8.02%) exhibiting deprecated Godot 3 APIs (`setget`, `File.new()`, `Pool*Array`, `update()`, `set_rot`, `move_and_slide(velocity)`). Additionally, 681 records (8.52%) are exact duplicate assistant responses.
3. **Model & Architecture**: Base model `Qwen/Qwen2.5-Coder-7B-Instruct` is cached locally. The fine-tuned LoRA adapter `godot-agent-lora/final_adapter` was trained for 3 epochs with $r=16, \alpha=32$ across 7 linear modules using 4-bit QLoRA.
4. **Godot Runtime**: Official Godot 4.7.2 (`4.7.2.stable.official.ed1daf0bf`) is installed at `/home/piet/.local/bin/godot4`. Headless syntax checking (`--headless --check-only -s <file>`) and SceneTree execution (`--headless -s <file>`) are fully operational and provide deterministic parse and runtime diagnostics.
5. **Inference & Structured Action Fragility**: In `godot_agent_server.py`, the agent forces multi-line GDScript source files to be JSON-string-escaped inside a single `"content"` attribute. Because 7B models frequently suffer from autoregressive token degeneration when escaping code, the server relies on 3 regex fallbacks to salvage malformed JSON responses.

---

## 2. Environment & Hardware Baseline

- **OS**: Linux x86_64 / aarch64 (Ubuntu-based)
- **GPU**: NVIDIA GB10 (CUDA 13.0, Driver 580.173.02)
- **Python**: 3.12.3
- **PyTorch**: 2.14.1+cu130 (CUDA Available: True, Device Count: 1)
- **Transformers**: 5.19.0
- **PEFT**: 0.21.2
- **Engine Binary**: `/home/piet/.local/bin/godot4`
- **Engine Version**: `Godot Engine v4.7.2.stable.official.ed1daf0bf`

---

## 3. Dataset Audit (`final_godot_sharegpt.jsonl`)

The training file `final_godot_sharegpt.jsonl` is a symbolic link to `godot_training_workspace/data/train.jsonl` (35,003,556 bytes, 7,990 lines).

A systematic scan of all 7,990 assistant responses revealed:
- **Total records**: 7,990
- **Exact duplicate assistant responses**: 681 (8.52%)
- **Records with Godot 3 legacy patterns**: 641 (8.02%)
- **Specific Pattern Occurrences**:
  - `setget` (Godot 3 property syntax): 298
  - `update()` (Godot 3 canvas redraw): 157
  - `File.new()` (Godot 3 File I/O): 110
  - `move_and_slide(...)` with arguments (Godot 3 physics): 74
  - `Pool*Array` (Godot 3 packed arrays): 51
  - `to_json` / `parse_json`: 38
  - `set_rot`: 22
  - `yield(...)` (Godot 3 coroutine): 15
  - `MultiplayerAPI.RPC_MODE_`: 4
  - `PackedScene.instance()`: 3

**Root Cause in `cleaner.py`**:
The ETL pipeline in `godot_training_workspace/scripts/cleaner.py` only quarantined two specific regexes: `SET_PAUSE_MODE_REGEX` and `OS_GET_WINDOW_SIZE_REGEX`. It attempted partial regex transpilation for `export var`, `onready var`, and `KinematicBody2D`, but omitted `setget`, `File.new()`, `Pool*Array`, `update()`, and legacy signal connections. Because all records are given the system prompt `"You are an expert Godot 4 Engine developer and autonomous AI agent."`, the model was directly fine-tuned to generate broken Godot 3 code under Godot 4 instructions.

---

## 4. Evaluation Methodology Audit (`eval_benchmark.py`)

The existing benchmark (`scripts/eval_benchmark.py`) consists of 4 hardcoded prompts:
1. `T1_MECHANICS`: 2D Kinematic Controller (Evaluated via keywords: `velocity`, `gravity`, `move_and_slide`, `is_on_floor`, `jump`)
2. `T2_ACTION_JSON`: Scene & Node Generation (Evaluated via action type and file path substring)
3. `T3_POWERUP_LOGIC`: Shield / Invulnerability Mechanic (Evaluated via keywords: `has_shield`, `modulate`, `emit_signal`, `signal`)
4. `T4_ENGINE_API`: Signals & Connections (Evaluated via keywords: `Timer`, `wait_time`, `one_shot`, `connect`, `timeout`, `start`)

**Critical Vulnerabilities Identified**:
- **Zero compiler verification**: Scripts are never validated against the Godot engine binary.
- **Zero runtime or semantic execution**: No Node instantiation, signal firing, or method dispatch is tested.
- **Rewarding invalid code**: In `T4_ENGINE_API`, the model generated `timer.connect("timeout", self, "_on_timer_timeout")`. When fed to `/home/piet/.local/bin/godot4 --headless --check-only -s`, Godot returns:
  ```
  SCRIPT ERROR: Parse Error: Invalid argument for "connect()" function: argument 2 should be "Callable" but is "...".
  SCRIPT ERROR: Parse Error: Cannot pass a value of type "String" as "int".
  ERROR: Failed to load script with error "Parse error".
  ```
  Despite failing to compile, `eval_benchmark.py` awarded this output **85 / 100 points**.

---

## 5. Model Loading & Inference Audit (`godot_agent_server.py`)

- **Base Model**: `Qwen/Qwen2.5-Coder-7B-Instruct` loaded in 4-bit (`nf4`, compute `bfloat16`, double quant).
- **LoRA Adapter**: Loaded from `godot-agent-lora/final_adapter`.
- **JSON Generation Protocol**:
  The system prompt forces the model to emit a single JSON object where code must be escaped inside the `"content"` key of `parameters`.
  When generating complex GDScript with tabs and linebreaks, 7B models frequently trigger autoregressive repetition loops (e.g. `\t\t\t\t\t`).
  To handle this, lines 116–160 of `godot_agent_server.py` implement three levels of fallback:
  1. Strict JSON parsing (`json.loads(cleaned)`).
  2. Non-strict JSON parsing (`json.loads(cleaned, strict=False)`).
  3. Regex extraction of `"action_type"`, `"file_path"`, and unescaped `"content"`.
- **Workspace Security**: The server allows file paths without strictly anchoring them to a dedicated project directory, creating potential risk if arbitrary file paths are requested.

---

## 6. Project Context & Fixtures

- A complete Godot 4 project exists at `2d_platformer/platformer`.
- The project has been verified with `/home/piet/.local/bin/godot4 --headless --editor --quit --path 2d_platformer/platformer`, which successfully built the class cache (`Player`, `Enemy`, `Gun`, `Bullet`, `CoinsCounter`, `Coin`) and imported all assets.
- Headless execution with `--quit-after 1` verified zero crashes.

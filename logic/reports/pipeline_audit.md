# Comprehensive Repository & Data Pipeline Audit Report
**Project:** Godot Local AI Agent (DGX Spark Fine-Tuning)  
**Auditor:** Senior ML Infrastructure & Agent Systems Auditor  
**Audit Date:** October 16, 2026  
**Repository Root:** `/home/piet/Documents/dataset`  
**Execution Environment:** Linux x86_64 / DGX Spark (NVIDIA Grace-Blackwell GPUs)

---

## 1. Executive Summary & Operational Health

This audit provides a comprehensive, evidence-based evaluation of the repository structure, data integrity, and end-to-end data processing pipeline for the **Godot Local AI Agent** project.

### Overall Pipeline Health: **DEGRADED & FRAGMENTED**

The repository currently exhibits a **dual-pipeline architectural split**:
1. **The Active Training Pipeline (Legacy Workspace):** An active training process (`python3 train_dgx.py`, PID 5456) is running on the DGX Spark. It trains Qwen2.5-Coder-7B-Instruct using 4-bit QLoRA on a single file: `final_godot_sharegpt.jsonl` (a symlink to `godot_training_workspace/data/train.jsonl`). This dataset contains 7,990 isolated scene-to-script pairs. It contains **no project architecture plans, no production logic plans, and no debugging trajectories**. Furthermore, it contains significant **Godot 3 syntax contamination** (`setget`, `tool`, `PoolVector2Array`, `to_json`) despite asserting in its system prompt that it is an expert Godot 4 agent.
2. **The Redesigned Data Pipeline (`logic/`):** A modular, well-structured, and mathematically rigorous pipeline created to ingest multi-source data, build dependency-aware 14-key production logic plans (Dataset A), structured debugging repairs (Dataset B), and agent trajectories (Dataset C). While its static analyzers, canonical DAG validators, and streaming `CodeIndex` are functional, **the pipeline is disconnected from training, contains several critical bugs that halt full-scale execution, and suffers from extreme data scarcity in key tasks**.

### High-Level Metrics Summary

| Dimension | Measured Value | Audit Status |
| :--- | :---: | :---: |
| **Active Training Process** | PID 5456 (`python3 train_dgx.py`) | **RUNNING** (Checkpoint-1200 saved) |
| **Active Training Dataset** | 7,990 scene-script pairs (35MB) | **CONTAMINATED** (Godot 3 syntax present) |
| **Baseline Structured Projects** | 689 project records (14.6MB) | **AVAILABLE** (529 Godot 4.x, 148 Godot 3.x, 7 Godot 2.x) |
| **Baseline Structured Code** | 80,981 code files (587MB) | **DEFECTIVE** (0 `project.godot` files; 6,508 non-Godot files) |
| **Baseline Debugging Records** | 8 records total (57KB) | **CRITICALLY DEFICIENT** (0 verified GDScript repairs) |
| **Baseline Agent Trajectories** | 32 records total (438KB) | **SYNTHETIC** (Merged PRs, no interactive traces) |
| **Storage Redundancy** | 602.4 MB duplicated in `final/` | **EXACT DUPLICATE** (100% byte match with `structured/`) |
| **Automated Test Suite** | 53 tests offline (100% passing with PYTHONPATH) | **FAILED DEFAULT IMPORT** (Lacks `sys.path` in canonical test) |

---

## 2. Active DGX Fine-Tuning Process Audit

### 2.1. Process State & GPU Execution
- **Process Status:** Active process running under PID 5456 (`python3 train_dgx.py`), utilizing 98.9% CPU and active GPU memory on Grace-Blackwell.
- **Safety Compliance:** In strict adherence to Section 1 safety rules, this process has **not been stopped, paused, signaled, or modified**.
- **Checkpoints:** Output directory `godot-agent-lora/` contains `checkpoint-1000` (Oct 15 14:40), `checkpoint-1100` (Oct 15 15:32), and `checkpoint-1200` (Oct 16 11:59).

### 2.2. Training Configuration Deficiencies in `train_dgx.py`
Inspection of [`train_dgx.py`](file:///home/piet/Documents/dataset/train_dgx.py) reveals two critical issues:
1. **Hardcoded Data Path:**
   ```python
   DATA_PATH = (
       "./final_godot_sharegpt.jsonl"
       if os.path.exists("./final_godot_sharegpt.jsonl")
       else "./godot_training_workspace/data/train.jsonl"
   )
   ```
   `train_dgx.py` does not point to `logic/data/training/`. None of the production logic, architecture, or debugging datasets produced by the modern pipeline are being fed into the current training run.
2. **Missing `max_seq_length` & Silent Truncation Risk:**
   Neither `TrainingArguments` nor `SFTTrainer` specifies `max_seq_length`. While `final_godot_sharegpt.jsonl` has an average length of 1,253 tokens, some records exceed 34,000 tokens. In the modern `logic/` pipeline, Dataset A production logic plans average 4,766 tokens, with many reaching 8,878 tokens. Without an explicit sequence length (e.g. 8,192 or 16,384) and packing policy, long JSON plans will be silently truncated mid-sentence, cutting off closing braces and training the model to produce invalid JSON syntax.

### 2.3. Dataset Contamination in `final_godot_sharegpt.jsonl`
Direct line-by-line inspection of `final_godot_sharegpt.jsonl` reveals widespread Godot 3 syntax in target completions despite a Godot 4 prompt:
- **Line 3 (`frame_item.gd`):** Uses `tool`, `setget _set_title`, `setget _setFrameMeta`.
- **Line 9 (`UVDebugger.gd`):** Uses `PoolIntArray()` and `PoolVector2Array()`.
- **Line 10 (`bs_entity_spawner.gd`):** Uses `PoolByteArray`, `to_json()`, `parse_json()`, and `validate_json()`.
- **Line 11 (`WorldGeneratorTest.gd`):** Combines Godot 4 `@export` with Godot 3 `setget do_clear_image`.

**Impact:** The model currently being fine-tuned will hallucinate deprecated Godot 3 APIs when prompted to write Godot 4 code.

---

## 3. End-to-End Data Pipeline Trace (`logic/`)

### 3.1. Stage-by-Stage Flow & Verification Matrix

```
[structured/] ──(1)──> [CodeIndex + Adapter] ──(2)──> [logic/data/ingested/] ──(3)──> [clean.py]
                                                                                            │
[logic/data/training/] <──(6)── [export_training.py] <──(5)── [split_dataset.py] <──(4)── [deduplicate.py]
```

| Stage | Input Path & Format | Entry Function / Command | Core Transformations | Output Path & Format | Validations Enforced | Audit Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **1. Source Storage** | `structured/*.jsonl` (Read-only baseline) | Filesystem / Manifest | Immutable input verification; SHA-256 calculation | `structured/` (689 projects, 80k code files) | SHA-256 integrity match | **VERIFIED** |
| **2. Ingestion & Join** | `projects.jsonl` & `code.jsonl` | `StructuredIngestionAdapter.ingest_dataset_a()` | Streaming byte-offset index join; scene & script parsing; 14-key plan synthesis | `logic/data/ingested/dataset_a_projects.jsonl` | Engine version check; JSON schema check | **PARTIAL FAIL**<br>(Crashes if `sample_size=None`; Godot 2.x bypasses filter) |
| **3. Cleaning & Scrub** | `logic/data/ingested/*.jsonl` | `logic_pipeline.processing.clean.clean_content` | Email redaction, local path scrubbing (`res://` preserved), base64 bloat strip | `logic/data/cleaned/cleaned_records.jsonl` | File size limit (2MB); min LOC (4 lines) | **VERIFIED**<br>(Transpilation disabled by default) |
| **4. Deduplication** | `logic/data/cleaned/*.jsonl` | `logic_pipeline.processing.deduplicate.Deduplicator` | SHA-256 exact hashing; unigram/bigram token shingle Jaccard similarity (0.95) | `logic/data/cleaned/*_dedup.jsonl` | Secondary source provenance merging | **VERIFIED** |
| **5. Multi-Tier Validation** | `logic/data/cleaned/*_dedup.jsonl` | `cli.py cmd_validate` | Schema validation (`Draft-7`); Canonical 14-key validation; task DAG cycle check | Console / Audit Report | Referential integrity; DAG acyclicity | **VERIFIED**<br>(Headless runtime skipped: no binary) |
| **6. Splitting & Export** | `logic/data/cleaned/*_dedup.jsonl` | `split_dataset_by_project` & `cmd_export` | Deterministic project-level hash grouping (80/10/10); ShareGPT formatting | `logic/data/training/run_*/dataset_*.jsonl` | Non-overlapping file verification; split manifest | **PARTIAL FAIL**<br>(Val split starves to 0 when n < 10) |

---

## 4. Deep-Dive Findings & Evidence

### 4.1. The Missing `project.godot` Paradox in `code.jsonl`
- **Location:** [`structured/code.jsonl`](file:///home/piet/Documents/dataset/structured/code.jsonl)
- **Finding:** Across all 80,981 records in `code.jsonl`, there is **not a single `project.godot` file**.
- **Impact on Extraction:** In [`structured_ingest.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/structured_ingest.py#L100-L110), lines 102-105 attempt to parse `files_by_path.get("project.godot")`. Because this file never exists in `code.jsonl`, `parse_project_godot` never runs during ingestion. Autoloads, input actions, rendering methods, and physics layers are never extracted from raw config and must rely solely on top-level project metadata.

### 4.2. 6,508 Orphaned Non-Godot Files in `code.jsonl`
- **Location:** [`structured/code.jsonl`](file:///home/piet/Documents/dataset/structured/code.jsonl)
- **Finding:** `code_index.json` indexes 720 repositories, but `structured/projects.jsonl` has only 689 projects. The 31 unaccounted repositories contain 6,508 files (8.04% of the dataset) belonging to C# libraries and Unity SDKs (e.g. `colyseus-unity-sdk`, `Arch`, `ecsrx`, `Nino`).
- **Impact:** These files were never filtered out of `code.jsonl` during the September crawl, consuming ~45MB of unreferenced data.

### 4.3. Disconnected Architecture Modules: `evidence.py` and `scene_graph.py`
- **Locations:** [`logic/src/logic_pipeline/analysis/evidence.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/analysis/evidence.py) and [`logic/src/logic_pipeline/analysis/scene_graph.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/analysis/scene_graph.py)
- **Finding:** Both modules are fully implemented with unit tests, but neither is called by `structured_mappers.py` or `cli.py`.
- **Evidence:** Cross-module reference analysis confirmed both modules have 0 incoming calls from the operational pipeline.

### 4.4. Disconnected Collection Modules: `git_repository.py` and `github_api.py`
- **Locations:** [`logic/src/logic_pipeline/sources/git_repository.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/git_repository.py) and [`logic/src/logic_pipeline/sources/github_api.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/github_api.py)
- **Finding:** `GitRepositoryCloner` is never called by `cli.py` or `GitHubSource`. `GitHubSource.fetch()` is an empty stub that returns metadata only.
- **Evidence:** Command `collect --source github` writes repository JSON metadata to `github_records.jsonl` but downloads zero source code files.

---

## 5. Dataset Quality, Volume, and Agent Suitability

### 5.1. Dataset Suitability Matrix for Full Agent Capabilities

Autonomous game-building agents require five distinct capabilities:

| Capability Required | Target Dataset | Current Volume | Grounding & Evidence Quality | Suitable for Production Training? |
| :--- | :--- | :---: | :--- | :---: |
| **1. Project Architecture** | Dataset A (`architecture`) | 541 plans (available from `projects.jsonl`) | **HIGH**: Grounded in real file manifests, scenes, and scripts | **YES** (after fixing Godot 2 filter & split bug) |
| **2. Production Planning** | Dataset A (`production_logic`) | 541 plans (available from `projects.jsonl`) | **MEDIUM**: Tasks & dependencies derived from static structure; gameplay loop is template-parameterized | **YES** (as architectural planning baseline) |
| **3. Grounded GDScript** | Baseline (`code.jsonl`) | 34,616 GDScript scripts | **MEDIUM**: Grounded in real repos, but contaminated with Godot 3 syntax and non-Godot C# files | **NEEDS CLEANING** (transpilation & filtering required) |
| **4. Debugging & Repair** | Dataset B (`debugging`) | **8 records total** | **CRITICAL DEFICIENCY**: 2 docs typos, 1 Godot 3, C++ engine crashes, 0 runtime-verified GDScript fixes | **NO** (Critically insufficient volume and domain mismatch) |
| **5. Tool-Use Trajectories** | Dataset C (`trajectories`) | **32 records total** | **SYNTHETIC**: Reconstructed from merged PRs without real tool calls, compiler errors, or repair iterations | **NO** (Cannot teach interactive agent execution) |

### 5.2. Analysis of Dataset C (Synthetic Trajectories)
In `structured_mappers.py` line 678, the ingestion adapter explicitly flags:
```python
audit["is_genuine_trajectory"] = False
metadata["execution_state"] = "reconstructed_from_merged_pr_without_interactive_trace"
```
Because these 32 records represent merged GitHub PRs rather than interactive sessions with an executing agent, they lack:
- Real Godot compiler error messages.
- Real stdout/stderr stack traces from failed runs.
- Interactive tool input/output pairs.
- Multi-turn recovery from broken scene trees.

Training on these records will teach the model to output a static 4-step monologue rather than dynamically responding to tool observations.

---

## 6. Safety & Usability for Ingestion Runs

### Can the pipeline safely perform a small ingestion run right now?
**YES, with caveats:**
- Running `./logic/run_scraper.sh check-config` is completely safe and read-only.
- Running `./logic/run_scraper.sh ingest --sample-size 50 --dry-run` executes safely without disk mutation.
- Running `./logic/run_scraper.sh ingest --sample-size 50` writes strictly to `logic/data/ingested/` without touching `structured/` or root files.

### Can the pipeline safely perform a FULL ingestion run right now?
**NO:**
- Running without `--sample-size` crashes with `TypeError` due to Bug 1.2 in `structured_ingest.py`.
- Running full ingestion will map 7 obsolete `Godot 2.x` projects due to Bug 1.4.
- Running `export` on Dataset B will produce an empty 0-byte validation file due to Bug 1.3.

---

## 7. Immediate Recommended Actions

1. **Do not interrupt the active fine-tuning job (PID 5456).** Allow the current baseline run on DGX Spark to finish its training passes and save its final adapter checkpoint to `godot-agent-lora/final_adapter`.
2. **Apply the 3 non-invasive bug fixes in `logic/` (after approval):**
   - Add `sys.path.insert(0, ...)` to `logic/tests/test_canonical_pipeline.py`.
   - Add `sample_size is not None` guard to `logic/src/logic_pipeline/sources/structured_ingest.py`.
   - Fix validation split calculation in `logic/src/logic_pipeline/processing/split_dataset.py` so `val` is never 0.
   - Add `Godot 2.x` check to `logic/src/logic_pipeline/extractors/structured_mappers.py`.
3. **Curate real GDScript debugging and interactive trajectory datasets:**
   - Expand Dataset B from 8 records to $\ge 500$ verified GDScript error-repair pairs.
   - Implement an interactive agent runtime bridge (capturing real Godot 4 headless compiler errors and diff repairs) to generate authentic Dataset C tool-use trajectories.

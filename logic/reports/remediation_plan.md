# Prioritized Remediation Plan and Implementation Roadmap

This plan provides a prioritized, dependency-ordered technical roadmap for remediating all confirmed findings in the Godot Local AI Agent repository.

> [!IMPORTANT]
> **Safety Notice:** Per mandatory safety constraints, **none of these fixes have been executed during the audit**. This document is a proposal awaiting user authorization.

---

## 1. Severity Classification Matrix

| Priority | Definition | Total Findings |
| :--- | :--- | :---: |
| **P0 — Critical** | Could corrupt training data, cause checkpoint loss, or invalidate model fine-tuning | **2** |
| **P1 — High** | Breaks essential pipeline execution, crashes stages, or injects incompatible engine versions | **4** |
| **P2 — Medium** | Disconnected modules, missing tests, data starvation, or unverified synthetic traces | **5** |
| **P3 — Low** | Documentation inconsistencies, redundant files, empty placeholders, or naming drift | **4** |

---

## 2. Prioritized Issues Breakdown

### [P0-1] Uncontrolled Truncation and Lack of `max_seq_length` in Fine-Tuning
1. **Evidence & Exact Paths:** [`train_dgx.py`](file:///home/piet/Documents/dataset/train_dgx.py#L79-L112)
2. **Observed Behavior:** Neither `TrainingArguments` nor `SFTTrainer` defines `max_seq_length`. Dataset A production logic plans range from 2,012 to 8,878 tokens (average 4,766 tokens).
3. **Why It Matters:** In `SFTTrainer`, unconfigured length defaults to 512 or 1,024 tokens. Long JSON plans are silently truncated mid-string, cutting off closing braces and training the model to produce corrupted JSON syntax.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** When fine-tuning on Dataset A, configure `max_seq_length=16384` (or `8192` with packing) in `SFTTrainer`, set `gradient_checkpointing=True`, and add an assertion verifying no samples exceed `max_seq_length`.
6. **Dependencies & Regression Risks:** Requires sufficient GPU VRAM on Grace-Blackwell.
7. **Verification Test:** Assert `trainer.train_dataset[i]['input_ids']` length does not exceed limit and closing braces `}` parse cleanly across 100% of samples.

---

### [P0-2] Godot 3 Syntax Contamination in Active Grounded Dataset
1. **Evidence & Exact Paths:** [`final_godot_sharegpt.jsonl`](file:///home/piet/Documents/dataset/final_godot_sharegpt.jsonl#L3-L12) and [`godot_training_workspace/data/train.jsonl`](file:///home/piet/Documents/dataset/godot_training_workspace/data/train.jsonl)
2. **Observed Behavior:** Target assistant code completions frequently output Godot 3 syntax (`setget`, `tool`, `PoolVector2Array`, `to_json`) while the prompt specifies Godot 4.
3. **Why It Matters:** Actively fine-tunes the model to hallucinate deprecated Godot 3 syntax.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Run transpilation and filtering pass over `train.jsonl` using `clean_content(auto_upgrade_annotations=True)` and quarantine records that cannot be converted to Godot 4.
6. **Dependencies & Regression Risks:** Do NOT modify the active training file while PID 5456 is running. Apply only to subsequent training runs.
7. **Verification Test:** Run `check_godot_compatibility()` over all records in the new training file; verify 0 occurrences of `setget`, `tool`, and `Pool*Array`.

---

### [P1-1] `StructuredIngestionAdapter` Crashes on Full Dataset Ingestion (`sample_size=None`)
1. **Evidence & Exact Paths:** [`logic/src/logic_pipeline/sources/structured_ingest.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/structured_ingest.py#L248-L250) (Lines 248, 347, 434)
2. **Observed Behavior:** `if summary.records_examined >= sample_size: break` raises `TypeError: '>=' not supported between instances of 'int' and 'NoneType'` when `sample_size=None`.
3. **Why It Matters:** Prevents ingesting all 689 projects from `structured/projects.jsonl`.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Update comparison to:
   ```python
   if sample_size is not None and summary.records_examined >= sample_size:
       break
   ```
6. **Dependencies & Regression Risks:** Low risk; purely additive conditional check.
7. **Verification Test:** Run `adapter.ingest_dataset_a(sample_size=None, dry_run=True)` and assert it processes all 689 records without error.

---

### [P1-2] Small-Dataset Validation Starvation in `split_dataset_by_project`
1. **Evidence & Exact Paths:** [`logic/src/logic_pipeline/processing/split_dataset.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/processing/split_dataset.py#L64-L66)
2. **Observed Behavior:** For datasets with fewer than 10 projects, `int(total_projects * 0.1) == 0`, causing the validation split to receive 0 records.
3. **Why It Matters:** Causes empty validation files (`dataset_b_debugging_val.jsonl` is 0 bytes), crashing training evaluation loops.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Ensure minimum allocation of at least 1 record to validation and test when `total_projects >= 3`:
   ```python
   if total_projects >= 3:
       val_count = max(1, int(total_projects * val_ratio))
       test_count = max(1, int(total_projects * test_ratio))
       train_cutoff = total_projects - val_count - test_count
       val_cutoff = train_cutoff + val_count
   ```
6. **Dependencies & Regression Risks:** Low risk; guarantees balanced non-empty splits.
7. **Verification Test:** Split an 8-item dataset; assert `len(splits.val) >= 1` and `len(splits.test) >= 1`.

---

### [P1-3] Godot 2.x Records Bypass Version Filter
1. **Evidence & Exact Paths:** [`logic/src/logic_pipeline/extractors/structured_mappers.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/extractors/structured_mappers.py#L76-L80)
2. **Observed Behavior:** The version check checks only `"Godot 3"` or `"3."`. 7 `Godot 2.x` projects (from 2016) bypass the filter and are mapped as Godot 4 production plans.
3. **Why It Matters:** Ancient Godot 2 code pollutes the Godot 4 dataset.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Update version quarantine condition:
   ```python
   if ("Godot 3" in version or "3." in version or "Godot 2" in version or "2." in version) and "4." not in version:
       audit["status"] = "quarantined"
       audit["quarantine_reason"] = f"Incompatible engine version: {version} (pipeline targets Godot 4.x)"
       return None, audit
   ```
6. **Dependencies & Regression Risks:** Low risk; removes 7 incompatible projects from Dataset A.
7. **Verification Test:** Re-run dry run on 689 projects; assert 155 projects quarantined (148 Godot 3 + 7 Godot 2).

---

### [P1-4] Test Suite Import Failure: `test_canonical_pipeline.py`
1. **Evidence & Exact Paths:** [`logic/tests/test_canonical_pipeline.py`](file:///home/piet/Documents/dataset/logic/tests/test_canonical_pipeline.py#L28-L30)
2. **Observed Behavior:** Fails with `ModuleNotFoundError: No module named 'logic_pipeline'` when running standard `python3 -m unittest discover -s logic/tests -v`.
3. **Why It Matters:** Documented test command in `README.md` fails out-of-the-box.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Add standard path resolution snippet at the top of `test_canonical_pipeline.py`:
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
   ```
6. **Dependencies & Regression Risks:** Zero regression risk; standardizes file with other test modules.
7. **Verification Test:** Run `python3 -m unittest discover -s logic/tests -v` without `PYTHONPATH`; assert all 53 tests pass.

---

### [P2-1] Severe Scarcity and Domain Mismatch in Dataset B (Debugging)
1. **Evidence & Exact Paths:** [`structured/debugging.jsonl`](file:///home/piet/Documents/dataset/structured/debugging.jsonl)
2. **Observed Behavior:** Contains only 8 records total; 2 are docs typos, 1 is Godot 3, and several are C++ engine crashes. 0 GDScript gameplay bugs with test-verified repairs.
3. **Why It Matters:** Cannot train a model to diagnose and fix GDScript runtime errors.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Curate $\ge 500$ verified GDScript debugging pairs from Godot Forums, Discord, and closed GitHub repository PRs with real diffs and error stack traces.
6. **Dependencies & Regression Risks:** High data collection effort; essential for debugging capability.
7. **Verification Test:** Verify Dataset B contains $\ge 500$ schema-validated GDScript repair records.

---

### [P2-2] Synthetic Trajectories Without Real Tool Execution Traces (Dataset C)
1. **Evidence & Exact Paths:** [`structured/agent_tasks.jsonl`](file:///home/piet/Documents/dataset/structured/agent_tasks.jsonl) and [`structured_mappers.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/extractors/structured_mappers.py#L678)
2. **Observed Behavior:** 32 records reconstructed from merged GitHub PRs. Steps are synthetic; no real tool calls, compiler stdout/stderr, or repair loops are recorded.
3. **Why It Matters:** The model cannot learn interactive agent behaviors or tool-calling error recovery.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Build an interactive Godot execution controller / bridge that captures real multi-turn trajectories of an agent inspecting, modifying, and running Godot headless.
6. **Dependencies & Regression Risks:** Requires installed Godot 4 executable.
7. **Verification Test:** Trajectory schema validation verifying authentic compiler stdout/stderr in `observed_result`.

---

### [P2-3] Disconnected Modules: `evidence.py` and `scene_graph.py`
1. **Evidence & Exact Paths:** [`logic/src/logic_pipeline/analysis/evidence.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/analysis/evidence.py) and [`scene_graph.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/analysis/scene_graph.py)
2. **Observed Behavior:** Fully implemented modules with 0 references in the operational pipeline.
3. **Why It Matters:** Evidence grounding checks and deep scene graph analysis are bypassed.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Wire `verify_evidence_grounding` into `cmd_validate` and `SceneGraph` into `extract_repository_project`.
6. **Dependencies & Regression Risks:** Low risk.
7. **Verification Test:** Unit test asserting `verify_evidence_grounding` is called during validation.

---

### [P2-4] Disconnected Collection Modules: `git_repository.py` and `github_api.py`
1. **Evidence & Exact Paths:** [`logic/src/logic_pipeline/sources/git_repository.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/git_repository.py) and [`github_api.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/github_api.py)
2. **Observed Behavior:** `GitHubSource.fetch()` returns metadata only; `GitRepositoryCloner` is never called.
3. **Why It Matters:** CLI command `collect --source github` cannot download code.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Wire `GitRepositoryCloner` into `GitHubSource.fetch()` when `--download` or `--clone` flag is passed.
6. **Dependencies & Regression Risks:** Network and disk space requirements.
7. **Verification Test:** Run `collect --source github --limit 1 --dry-run` and verify clone command generation.

---

### [P2-5] Missing `content` in `extract_repository_project`
1. **Evidence & Exact Paths:** [`logic/src/logic_pipeline/extractors/repository.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/extractors/repository.py#L65-L71)
2. **Observed Behavior:** Explicitly sets `"content": None` for all scanned files.
3. **Why It Matters:** Downstream mappers cannot parse scenes or scripts from the returned dictionary.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Add optional parameter `include_content: bool = False`; read file content for text files under 500KB when `True`.
6. **Dependencies & Regression Risks:** Slight memory increase when scanning large projects.
7. **Verification Test:** Call `extract_repository_project(fixture_dir, include_content=True)` and assert `files[i]['content'] is not None`.

---

### [P3-1] Duplicate Storage in `final/` (602.4 MB)
1. **Evidence & Exact Paths:** [`final/`](file:///home/piet/Documents/dataset/final/)
2. **Observed Behavior:** 100% byte-for-byte duplicate of `structured/`.
3. **Why It Matters:** Wastes 600MB of storage.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Replace `final/` with symlinks to `structured/` or remove after confirming no external cron depends on the path.
6. **Dependencies & Regression Risks:** Ensure active training or backup jobs do not hardcode `final/`.
7. **Verification Test:** Confirm all references in code point to `structured/`.

---

### [P3-2] Empty Placeholder Files Across Repo
1. **Evidence & Exact Paths:** `sharegpt.jsonl`, `quarantine/empty_patch.jsonl`, `quarantine/missing_metadata.jsonl`, `quarantine/unresolved.jsonl`, `logic/data/quarantine/quarantined_records.jsonl`.
2. **Observed Behavior:** 0-byte placeholder files.
3. **Why It Matters:** Clutters repository inventory.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Remove 0-byte placeholders or add `.gitkeep` with explicit documentation.

---

### [P3-3] Root `README.md` Documentation Inconsistencies
1. **Evidence & Exact Paths:** [`README.md`](file:///home/piet/Documents/dataset/README.md)
2. **Observed Behavior:** Refers to non-existent `stage_01_collection`, `stage_02_repaired`, `dataset_manager.py`, `main.py`.
3. **Why It Matters:** Misleads new developers.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Update `README.md` to document current structure and commands.

---

### [P3-4] Duplicate Export Directory: `v1_real_logic/`
1. **Evidence & Exact Paths:** [`logic/data/training/v1_real_logic/`](file:///home/piet/Documents/dataset/logic/data/training/v1_real_logic/)
2. **Observed Behavior:** Duplicate copy of `run_20261015_072424/`.
3. **Why It Matters:** Redundant disk usage.
4. **Status:** Confirmed.
5. **Safest Recommended Fix:** Consolidate training exports under timestamped run directories.

---

## 3. Safe Execution Order (Post-Audit Roadmap)

```
[Phase 0: Complete Active Training] ──> Do not touch PID 5456; await final checkpoint
                     │
[Phase 1: Code Pipeline Bug Fixes] ──> P1-4 (test path), P1-1 (sample_size), P1-2 (split balance), P1-3 (Godot 2 filter)
                     │
[Phase 2: Training Pipeline Patch] ──> P0-1 (max_seq_length), P0-2 (Godot 3 cleaning & transpilation)
                     │
[Phase 3: Module Wiring & Gaps]   ──> P2-3 (evidence/scene graph), P2-4 (git clone), P2-5 (content extraction)
                     │
[Phase 4: Dataset Expansion]       ──> P2-1 (curate 500+ GDScript bugs), P2-2 (interactive agent bridge)
                     │
[Phase 5: Cleanup & Docs]          ──> P3-1 (final/ duplicate), P3-2 (empty files), P3-3 (README sync)
```

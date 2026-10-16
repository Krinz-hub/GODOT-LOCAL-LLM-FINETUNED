# Redundancy and Orphan Candidates Audit

This document catalogues all duplicate implementations, obsolete configurations, orphaned datasets, empty placeholder files, and redundant artifacts identified across the repository.

> [!IMPORTANT]
> **Safety Notice:** Per mandatory safety constraints, **no files have been deleted, moved, renamed, or modified**. This document provides an evidence-based audit for architectural clarity.

---

## 1. Confirmed Redundant Files (Identical Duplicates)

### 1.1. `final/` Directory — Complete Duplicate of `structured/`
- **Location:** [`final/`](file:///home/piet/Documents/dataset/final/)
- **Total Redundant Size:** **602.4 MB**
- **Evidence:** Executed recursive file comparison: `diff -r structured final`. Returned exit code 0 with zero differences across all 6 JSONL files.
- **Detailed File Comparison:**
  | File Name | Size in `structured/` | Size in `final/` | SHA-256 Checksum |
  | :--- | :---: | :---: | :--- |
  | `code.jsonl` | 614,885,110 bytes | 614,885,110 bytes | `a58aa74043b55692c5a5ff0036635ae67f17e57d3b34c5ed26d8894f247af079` |
  | `projects.jsonl` | 14,617,276 bytes | 14,617,276 bytes | `f45a06efa10b36fcb1ef1e2075db336cd0c2cfcc592f43bcf22977bf60d8601c` |
  | `agent_tasks.jsonl` | 438,207 bytes | 438,207 bytes | `d6887298e4ba7118519a6837fb15a038ce7ea657746548f75108f2d15f0e0a59` |
  | `documentation.jsonl` | 759,614 bytes | 759,614 bytes | `a9b37bfc053d71616b5946eefd5c6b094443f32212ebaf3d8dad839e7f0cf83e` |
  | `qa.jsonl` | 143,817 bytes | 143,817 bytes | `636ff4cda8158fa84a4d53c580dd8319015466cd553a4acd6abbef00e619a6f5` |
  | `debugging.jsonl` | 57,610 bytes | 57,610 bytes | `89388da4804feeb0f2f958f437d6c4012b2dde2d91bf2858db6fde49eac22a07` |
- **Classification:** `POSSIBLY_REDUNDANT`
- **Recommendation:** Keep `structured/` as the single authoritative read-only source dataset. In a future approved maintenance window, remove `final/` or replace it with symlinks to reclaim 600MB of storage.

### 1.2. `logic/data/training/v1_real_logic/` — Duplicate of `run_20261015_072424/`
- **Location:** [`logic/data/training/v1_real_logic/`](file:///home/piet/Documents/dataset/logic/data/training/v1_real_logic/)
- **Total Redundant Size:** **947.8 KB**
- **Evidence:** Executed recursive file comparison: `diff -r logic/data/training/run_20261015_072424/ logic/data/training/v1_real_logic/`. All 9 JSONL files are byte-for-byte identical. Only line 10 of `manifest_splits.json` differs in the output directory path string.
- **Classification:** `POSSIBLY_REDUNDANT`
- **Recommendation:** Archive or consolidate versioned training exports.

### 1.3. `logic/data/training/train_sharegpt.jsonl` — Exact Copy of Test Fixture
- **Location:** [`logic/data/training/train_sharegpt.jsonl`](file:///home/piet/Documents/dataset/logic/data/training/train_sharegpt.jsonl) (4,814 bytes)
- **Comparison Target:** [`logic/tests/fixtures/sample_production_logic.jsonl`](file:///home/piet/Documents/dataset/logic/tests/fixtures/sample_production_logic.jsonl) (4,814 bytes)
- **Evidence:** `diff logic/data/training/train_sharegpt.jsonl logic/tests/fixtures/sample_production_logic.jsonl` returned exit code 0 (zero differences).
- **Classification:** `INVESTIGATE`
- **Risk:** Developers or training scripts looking at `logic/data/training/train_sharegpt.jsonl` might assume it contains real exported training data, whereas it is actually a single synthetic test fixture record exported during earlier dry-run testing.

---

## 2. Empty Placeholder Files (0 Bytes)

The following files contain zero bytes of data and represent aborted runs, unfilled placeholders, or split bugs:

| File Path | Size | Likely Cause / Responsibility | Recommendation |
| :--- | :---: | :--- | :--- |
| `sharegpt.jsonl` | 0 B | Root placeholder for ShareGPT export | `POSSIBLY_REDUNDANT` |
| `quarantine/empty_patch.jsonl` | 0 B | Unused quarantine category from September crawl | `POSSIBLY_REDUNDANT` |
| `quarantine/missing_metadata.jsonl` | 0 B | Unused quarantine category from September crawl | `POSSIBLY_REDUNDANT` |
| `quarantine/unresolved.jsonl` | 0 B | Unused quarantine category from September crawl | `POSSIBLY_REDUNDANT` |
| `logic/data/quarantine/quarantined_records.jsonl` | 0 B | Unused quarantine log from clean stage | `POSSIBLY_REDUNDANT` |
| `logic/data/training/val_sharegpt.jsonl` | 0 B | Split ratio starvation on fixture export (2 total items) | `POSSIBLY_REDUNDANT` |
| `logic/data/training/run_20261015_072424/dataset_b_debugging_val.jsonl` | 0 B | Split ratio starvation on small dataset (8 total items) | `POSSIBLY_REDUNDANT` |
| `logic/data/training/v1_real_logic/dataset_b_debugging_val.jsonl` | 0 B | Split ratio starvation on small dataset (8 total items) | `POSSIBLY_REDUNDANT` |

---

## 3. Orphaned and Stale Files

### 3.1. Non-Godot Repositories in `structured/code.jsonl`
- **File:** [`structured/code.jsonl`](file:///home/piet/Documents/dataset/structured/code.jsonl)
- **Orphaned Records:** **6,508 records (8.04% of total)**
- **Evidence:** `code_index.json` indexes 720 repositories, but `structured/projects.jsonl` contains only 689 projects. The remaining 31 repositories have no entry in `projects.jsonl`.
- **Sample Repositories:**
  - `colyseus/colyseus-unity-sdk` (241 files — Unity/MonoGame C# networking)
  - `genaray/Arch` (General high-performance .NET C# ECS)
  - `EcsRx/ecsrx` (Reactive C# ECS framework)
  - `JasonXuDeveloper/Nino` (C# binary serialization)
  - `CSharpGodotTools/Template`
- **Classification:** `INVESTIGATE`
- **Recommendation:** Filter out non-Godot repositories during dataset cleaning to prevent non-Godot C# patterns from polluting the code training corpus.

### 3.2. Orphaned Migration Pointer: `existing_raw/raw_manifest.json`
- **File:** [`existing_raw/raw_manifest.json`](file:///home/piet/Documents/dataset/existing_raw/raw_manifest.json)
- **Content:** Points to `"legacy_path": "/home/piet/Documents/dev/github_dataset"`.
- **Evidence:** Target directory `/home/piet/Documents/dev/github_dataset` does not exist on disk.
- **Classification:** `POSSIBLY_REDUNDANT`

### 3.3. Empty Directory: `raw/github/repos/`
- **Location:** [`raw/github/repos/`](file:///home/piet/Documents/dataset/raw/github/repos/)
- **Status:** Empty directory containing 0 files.
- **Classification:** `POSSIBLY_REDUNDANT`

### 3.4. Stale `etl_statistics.json` in Root
- **File:** [`etl_statistics.json`](file:///home/piet/Documents/dataset/etl_statistics.json)
- **Content:** 37 lines of JSON where every single counter is `0`.
- **Evidence:** Matches the schema of `CLEANER.PY` in `godot_training_workspace/scripts/`. Not updated by the current `logic/` pipeline.
- **Classification:** `POSSIBLY_REDUNDANT`

---

## 4. Stale Documentation & Broken Command References

### 4.1. Root `README.md` Path Inconsistencies
- **File:** [`README.md`](file:///home/piet/Documents/dataset/README.md)
- **References:**
  - `stage_01_collection/manifest.json` (Directory does not exist)
  - `stage_02_repaired/manifest.json` (Directory does not exist)
  - `from dataset_manager import manager` (`dataset_manager.py` does not exist)
  - `python main.py --dataset-list` (`main.py` does not exist)
- **Classification:** `INVESTIGATE`
- **Recommendation:** Rewrite root `README.md` to accurately document the current structure (`structured/`, `logic/`, `train_dgx.py`, `./logic/run_scraper.sh`).

### 4.2. `logic/README.md` Test Command Documentation
- **File:** [`logic/README.md`](file:///home/piet/Documents/dataset/logic/README.md#L228)
- **Documented Command:** `python3 -m unittest discover -s logic/tests -v`
- **Observed Behavior:** Fails with `ModuleNotFoundError` due to missing `sys.path` in `test_canonical_pipeline.py`.
- **Correction:** Must document `PYTHONPATH=logic/src python3 -m unittest discover -s logic/tests -v` until `test_canonical_pipeline.py` is patched.

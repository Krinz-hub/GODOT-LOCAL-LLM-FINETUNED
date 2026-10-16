# Confirmed Missing Components and Capability Gaps

This report documents all verified missing files, incomplete implementations, stubbed functions, and architectural gaps in the Godot Local AI Agent repository and data pipeline. Every item is verified through code inspection, filesystem verification, or direct execution.

---

## 1. Pipeline Code & Infrastructure Gaps

### 1.1. `test_canonical_pipeline.py` Missing `sys.path` Configuration
- **File:** [`logic/tests/test_canonical_pipeline.py`](file:///home/piet/Documents/dataset/logic/tests/test_canonical_pipeline.py#L29)
- **Observed Behavior:** Unlike all other 10 test modules in `logic/tests/`, `test_canonical_pipeline.py` does not insert `logic/src` into `sys.path` prior to importing `logic_pipeline`. Running the standard documented command `python3 -m unittest discover -s logic/tests -v` fails immediately with `ModuleNotFoundError: No module named 'logic_pipeline'`.
- **Evidence:** Command `python3 -m unittest discover -s logic/tests -v` exited with code 1; failed test module `test_canonical_pipeline`.
- **Impact:** Continuous integration, local test runners, and developer verification fail out-of-the-box unless `PYTHONPATH=logic/src` is manually specified.

### 1.2. Unhandled `sample_size=None` in `StructuredIngestionAdapter`
- **File:** [`logic/src/logic_pipeline/sources/structured_ingest.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/structured_ingest.py#L248-L250) (Lines 248, 347, 434)
- **Observed Behavior:** The methods `ingest_dataset_a`, `ingest_dataset_b`, and `ingest_dataset_c` evaluate `if summary.records_examined >= sample_size: break` without checking if `sample_size` is `None`. When invoked to ingest the full dataset without a limit (`sample_size=None`), the loop raises `TypeError: '>=' not supported between instances of 'int' and 'NoneType'`.
- **Evidence:** Executing `adapter.ingest_dataset_a(sample_size=None, dry_run=True)` failed with `TypeError`.
- **Impact:** Full-scale ingestion cannot run without passing an explicit arbitrary integer.

### 1.3. Small-Dataset Validation Starvation in `split_dataset_by_project`
- **File:** [`logic/src/logic_pipeline/processing/split_dataset.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/processing/split_dataset.py#L64-L66)
- **Observed Behavior:** The split cutoffs are calculated as `train_cutoff = int(total_projects * train_ratio)` and `val_cutoff = train_cutoff + int(total_projects * val_ratio)`. When `total_projects < 10` (e.g. Dataset B debugging has only 8 records), `int(8 * 0.1) = 0`, causing `val_cutoff == train_cutoff`. The validation split receives 0 records, while `test` receives the remainder.
- **Evidence:** `logic/data/training/run_20261015_072424/dataset_b_debugging_val.jsonl` is 0 bytes; `logic/data/training/val_sharegpt.jsonl` is 0 bytes.
- **Impact:** Any training run configured to validate during training crashes or fails evaluation because the validation dataset contains zero samples.

### 1.4. Godot 2.x Version Bypass in Production Logic Ingestion
- **File:** [`logic/src/logic_pipeline/extractors/structured_mappers.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/extractors/structured_mappers.py#L76-L80)
- **Observed Behavior:** The engine version check only filters Godot 3: `if ("Godot 3" in version or "3." in version) and "4." not in version: audit["status"] = "quarantined"`. Records labeled `Godot 2.x` (e.g. `project:kidscancode/godot3_procgen_demos`, `project:Bauxitedev/godot-hair-shader`) are not quarantined and are mapped into Dataset A as Godot 4 production logic plans.
- **Evidence:** Dry run verified 7 `Godot 2.x` projects mapped with `status: mapped`.
- **Impact:** Outdated, incompatible syntax from 2016 engine versions pollutes the Godot 4 fine-tuning dataset.

### 1.5. Missing `content` Extraction in `extract_repository_project`
- **File:** [`logic/src/logic_pipeline/extractors/repository.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/extractors/repository.py#L65-L71)
- **Observed Behavior:** When scanning files in `extract_repository_project`, the extractor explicitly sets `"content": None` in the returned file metadata dictionary.
- **Evidence:** Lines 66-71: `files_list.append({"path": rel_path, "type": f_type, "size_bytes": size_bytes, "content": None})`.
- **Impact:** Downstream analysis modules (such as `structured_mappers.py` lines 92-95) cannot parse scripts or scene hierarchies from the repository record unless an external file stream is supplied.

---

## 2. Source Connectors & Data Collection Gaps

### 2.1. Stubbed `GitHubSource.fetch()` and Disconnected `GitRepositoryCloner`
- **Files:** [`logic/src/logic_pipeline/sources/github_api.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/github_api.py#L103-L107) and [`logic/src/logic_pipeline/sources/git_repository.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/sources/git_repository.py#L13-L57)
- **Observed Behavior:** `GitHubSource.fetch(item)` is an empty stub that simply returns `item` without fetching files or repository content. The `GitRepositoryCloner` class in `git_repository.py` is implemented but has zero references across `cli.py` or `github_api.py`.
- **Evidence:** Search for `GitRepositoryCloner` across repository yielded 0 usages outside its own definition. CLI command `collect --source github` writes only API search metadata to `github_records.jsonl`.
- **Impact:** The GitHub collection pipeline cannot actually collect Godot code or clone repositories.

### 2.2. Empty Local Projects Configuration
- **File:** [`logic/config/sources.yaml`](file:///home/piet/Documents/dataset/logic/config/sources.yaml#L7-L9)
- **Observed Behavior:** The only configured path under `sources.local.project_paths` is `"logic/tests/fixtures/sample_project"`.
- **Evidence:** Executing `collect --source local` yields only files from the unit-test sample fixture.
- **Impact:** No real local Godot projects are discovered or collected by the active pipeline.

### 2.3. Empty Cloned Repositories Cache and Missing Legacy Path
- **Files:** [`raw/github/repos/`](file:///home/piet/Documents/dataset/raw/github/repos/) and [`existing_raw/raw_manifest.json`](file:///home/piet/Documents/dataset/existing_raw/raw_manifest.json)
- **Observed Behavior:** Directory `raw/github/repos/` is completely empty. `existing_raw/raw_manifest.json` points to `/home/piet/Documents/dev/github_dataset`, which does not exist on the filesystem.
- **Evidence:** `ls raw/github/repos/` showed 0 files; `ls /home/piet/Documents/dev/github_dataset` returned `No such file or directory`.
- **Impact:** The 796 raw cloned repositories mentioned in root `README.md` are not accessible on this system; only the extracted JSONL records in `raw/` and `structured/` remain.

---

## 3. Data Integrity & Schema Ingestion Gaps

### 3.1. Zero `project.godot` Files in `structured/code.jsonl`
- **File:** [`structured/code.jsonl`](file:///home/piet/Documents/dataset/structured/code.jsonl)
- **Observed Behavior:** `code.jsonl` contains 80,981 records across `gdscript`, `godot_scene`, `csharp`, `godot_resource`, and `shader`, but exactly 0 records for `project.godot`.
- **Evidence:** Grep and stream analysis of all 80,981 lines for `project.godot` returned 0 matches.
- **Impact:** In `StructuredIngestionAdapter`, `files_by_path.get("project.godot")` always returns `None`. `parse_project_godot` never runs during ingestion, preventing dynamic extraction of autoloads, input actions, physics layers, and engine feature flags.

### 3.2. 6,508 Orphaned Non-Godot Files in `structured/code.jsonl`
- **File:** [`structured/code.jsonl`](file:///home/piet/Documents/dataset/structured/code.jsonl)
- **Observed Behavior:** `code.jsonl` contains files from 31 repositories that have no corresponding project entry in `structured/projects.jsonl` (720 repositories indexed in `code_index.json` vs 689 projects in `projects.jsonl`). These 31 repositories include non-Godot C# libraries and Unity SDKs (e.g. `colyseus-unity-sdk`, `Arch`, `ecsrx`).
- **Evidence:** Identified 6,508 orphaned file records in `code.jsonl` belonging to these 31 unjoined repositories.
- **Impact:** Bloats dataset by 8% with non-Godot code and risks cross-engine syntax pollution.

### 3.3. Severe Scarcity and Domain Mismatch in Debugging Dataset
- **File:** [`structured/debugging.jsonl`](file:///home/piet/Documents/dataset/structured/debugging.jsonl)
- **Observed Behavior:** Contains only 8 records total. None of them represent verified GDScript game debugging tasks. Two are documentation typos, one is Godot 3.2.1, and the rest are C++ engine source crashes from `godotengine/godot`.
- **Evidence:** Direct inspection of all 8 records.
- **Impact:** Dataset B is insufficient in both volume and domain to train a model to diagnose and repair GDScript gameplay bugs.

### 3.4. Synthetic Trajectories Without Real Tool Execution Traces
- **Files:** [`structured/agent_tasks.jsonl`](file:///home/piet/Documents/dataset/structured/agent_tasks.jsonl) and [`logic/src/logic_pipeline/extractors/structured_mappers.py`](file:///home/piet/Documents/dataset/logic/src/logic_pipeline/extractors/structured_mappers.py#L663-L766)
- **Observed Behavior:** `agent_tasks.jsonl` contains 32 merged GitHub pull requests (many touching C++ engine internals or documentation). The mapper synthetically wraps them into 4 generic steps (`inspect_files`, `reasoning`, `apply_patch`, `run_tests`). No real tool execution, Godot runtime stdout/stderr, compiler feedback, or repair iterations are recorded.
- **Evidence:** `audit["is_genuine_trajectory"] = False`; `metadata.execution_state = "reconstructed_from_merged_pr_without_interactive_trace"`.
- **Impact:** The model cannot learn authentic interactive agent workflows, error recovery, or runtime tool use from this dataset.

---

## 4. Training Pipeline & Runtime Gaps

### 4.1. Disconnected Training Pipeline
- **Files:** [`train_dgx.py`](file:///home/piet/Documents/dataset/train_dgx.py#L34-L38) vs [`logic/data/training/`](file:///home/piet/Documents/dataset/logic/data/training/)
- **Observed Behavior:** `train_dgx.py` trains exclusively on `./final_godot_sharegpt.jsonl` (or `./godot_training_workspace/data/train.jsonl`), which contains 7,990 scene-to-script pairs. It does not consume any of the multi-task architectural, production-logic, or debugging datasets generated by the `logic/` pipeline.
- **Evidence:** `train_dgx.py` line 34 hardcodes `DATA_PATH = "./final_godot_sharegpt.jsonl"`.
- **Impact:** The currently fine-tuned model is learning only single-file script completions, not project-level planning, architecture, or debugging.

### 4.2. Godot 3 Syntax Contamination in Active Fine-Tuning Data
- **File:** [`final_godot_sharegpt.jsonl`](file:///home/piet/Documents/dataset/final_godot_sharegpt.jsonl)
- **Observed Behavior:** The system prompt asserts: `"You are an expert Godot 4 Engine developer and autonomous AI agent."`, yet the target GDScript responses frequently output legacy Godot 3 syntax (`setget`, `tool`, `PoolVector2Array`, `to_json`, `parse_json`, `instance()`).
- **Evidence:** Lines 3, 7, 8, 9, 10 in `final_godot_sharegpt.jsonl` contain un-transpiled Godot 3 keywords.
- **Impact:** Causes the model to generate obsolete Godot 3 code when explicitly asked for Godot 4 implementations.

### 4.3. Missing Max Sequence Length and Truncation Guard in `train_dgx.py`
- **File:** [`train_dgx.py`](file:///home/piet/Documents/dataset/train_dgx.py#L79-L112)
- **Observed Behavior:** `max_seq_length` is not configured in `TrainingArguments` or `SFTTrainer`. In `SFTTrainer`, unconfigured length defaults to tokenizer limit or 1,024 tokens.
- **Evidence:** Dataset A production logic plans range from 2,012 to 8,878 tokens (average 4,766 tokens).
- **Impact:** If `logic/data/training/` is exported to `train_dgx.py` without configuring `max_seq_length` (e.g. 8,192 or 16,384), long production logic plans will be silently truncated, cutting off closing JSON syntax and corrupting training targets.

### 4.4. Missing Godot Execution Bridge / Runtime Controller
- **Observed Behavior:** The repository contains no runtime controller, subagent bridge, or test runner capable of launching Godot, attaching to an editor/debugger IPC socket, capturing runtime error logs, or executing GDUnit/GUT acceptance tests.
- **Evidence:** `run_godot.py` only performs a one-shot `--editor --quit` compilation check; `godot4` executable is not installed in system PATH.
- **Impact:** The agent cannot execute, test, or repair projects at runtime.

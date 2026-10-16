# Test Suite Audit and Verification Coverage Report

This report documents the execution results, code path coverage, mock usage, and untested capabilities across the automated test suite in `logic/tests/`.

---

## 1. Test Suite Execution Summary

### Baseline Run (Documented Command)
- **Command:** `python3 -m unittest discover -s logic/tests -v`
- **Result:** **`FAIL — executed and failed`** (Exit Code 1)
- **Failure:** `test_canonical_pipeline (unittest.loader._FailedTest.test_canonical_pipeline)`
- **Root Cause:** `ModuleNotFoundError: No module named 'logic_pipeline'`. Lacks `sys.path.insert(0, ...)` at the top of [`logic/tests/test_canonical_pipeline.py`](file:///home/piet/Documents/dataset/logic/tests/test_canonical_pipeline.py).
- **Run Stats:** 40 tests executed (39 passed, 1 error).

### Corrected Environment Run
- **Command:** `PYTHONPATH=logic/src python3 -m unittest discover -s logic/tests -v`
- **Result:** **`PASS — executed and verified`** (Exit Code 0)
- **Run Stats:** 53 tests executed in 0.962s (53 passed, 0 failures, 0 errors).

---

## 2. Test Execution Breakdown by Module

| Test Module | Tests | Execution Status | Code Paths Exercised | Mock Usage |
| :--- | :---: | :---: | :--- | :--- |
| `test_canonical_pipeline.py` | 13 | `PASS` (with PYTHONPATH)<br>`FAIL` (default) | Streaming `CodeIndex`, real project join (`2Retr0/GodotOceanWaves`), scene parsing, cycle detection, canonical 14-key validation, task prerequisites, split determinism, real vs fixture export gating, versioned output directory | Offline real data from `structured/` and temporary directories; no network mocks |
| `test_cleaning.py` | 5 | `PASS` | Email regex scrubbing, local path redaction, Godot protocol preservation (`res://`, `user://`, `/root/`), Godot 4 annotation upgrades, empty content & short script quarantine | In-memory string fixtures |
| `test_config.py` | 5 | `PASS` | `find_logic_root`, YAML loading, default config merging for sources, pipeline, cleaning, and validation | Filesystem read of `logic/config/*.yaml` |
| `test_cross_references.py` | 4 | `PASS` | Relational validation between planned scenes, scripts, task IDs, acceptance criteria, and prerequisite DAGs | In-memory plan dictionaries |
| `test_deduplication.py` | 3 | `PASS` | SHA-256 exact deduplication, unigram/bigram token shingle Jaccard similarity, provenance metadata merging | In-memory synthetic record dictionaries |
| `test_end_to_end.py` | 1 | `PASS` | End-to-end integration: local project discovery -> UTF-8 normalize -> clean -> deduplicate -> validate -> split -> export ShareGPT -> statistics | Uses synthetic test fixture [`logic/tests/fixtures/sample_project/`](file:///home/piet/Documents/dataset/logic/tests/fixtures/sample_project/) |
| `test_extractors.py` | 5 | `PASS` | Static parsers: `parse_gdscript` (exports, signals, methods), `parse_scene_file` (nodes, connections, ext_resources), `parse_project_godot`, `parse_resource_file`, `parse_git_diff` | Static string and file fixtures |
| `test_ingestion_adapter.py` | 7 | `PASS` | Read-only verification of `structured/` inputs, SHA-256 signature validation, Dataset A (projects -> production logic), Dataset B (debugging -> repair), Dataset C (agent tasks -> trajectories), quarantine triggers, non-overlapping ShareGPT export, dry-run | Reads `structured/projects.jsonl`, `debugging.jsonl`, `agent_tasks.jsonl` in read-only mode |
| `test_provenance.py` | 3 | `PASS` | SHA-256 hashing, `ProvenanceMetadata` serialization, transformation lifecycle logging, secondary source merging | In-memory objects |
| `test_resume.py` | 2 | `PASS` | Atomic checkpoint save/load, key completion tracking, checkpoint clearing | Temporary disk files |
| `test_schemas.py` | 4 | `PASS` | Draft-7 JSON Schema validation for `source_record`, `production_logic`, `agent_trajectory`; rejection of malformed plans | Schema files under `logic/schemas/` |

---

## 3. Real Code Paths vs Mocking Analysis

- **Mocks vs Real Code:** The test suite does not use artificial mock frameworks (`unittest.mock.MagicMock` is not employed). All tests execute real static parsing, schema validation, graph analysis, and file I/O against temporary directories.
- **Real Data Join Coverage:** Real-data join testing is restricted to **1 project** (`project:2Retr0/GodotOceanWaves`) in `test_canonical_pipeline.py`. Multi-project edge cases (e.g., projects without scenes, projects with missing scripts, projects with large binary textures) are not exercised in the automated test suite.
- **Malformed Input Testing:** `parse_jsonl_safely` is tested for JSON syntax errors. However, malformed `.tscn` (missing headers, corrupt uid tags) and malformed `project.godot` (corrupt sections) are not tested.

---

## 4. Unverified Capabilities and Pipeline Blindspots

| Pipeline Capability | Verification Status | Reason / Evidence |
| :--- | :---: | :--- |
| **Godot Headless Runtime Validation** | **`NOT AVAILABLE`** | `godot4` executable is not installed on system PATH. Headless project compilation and editor import could not be executed. |
| **Automated Gameplay & Acceptance Testing** | **`NOT AVAILABLE`** | No runtime controller, GDUnit4, or GUT runner exists to execute game plans. |
| **Full-Scale Ingestion (689 projects)** | **`UNTESTED IN CI`** | Tests only run on 1-5 sample projects. Running full ingestion uncovered unhandled `sample_size=None` crashing with `TypeError`. |
| **Godot 2.x Version Quarantine** | **`UNTESTED / FAILED`** | Not covered by test suite; code only checks for `Godot 3.x`, permitting Godot 2.x code to pass into training data. |
| **Small-Dataset Validation Splitting** | **`UNTESTED / FAILED`** | Not covered by test suite; splitting datasets with <10 items results in 0 validation records. |
| **Online GitHub API Discovery & Cloning** | **`NOT RUN`** | Tests run 100% offline; online token rate limiting and cloning are not tested. |
| **Token Truncation & Context Window Limits** | **`NOT TESTED`** | No test measures tokenizer length of exported records against Qwen2.5-Coder context windows. |

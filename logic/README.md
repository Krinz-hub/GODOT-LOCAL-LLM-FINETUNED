# Godot Logic Data Collection & Cleaning Pipeline

A modular, reproducible, and auditable ETL pipeline designed to collect, normalize, clean, validate, and export structured logic, architectural reasoning, and agent trajectory datasets for fine-tuning the **Godot Local AI Agent** (Qwen2.5-Coder-7B-Instruct).

---

## 1. Why This Pipeline Exists

Existing code datasets for Godot typically consist of isolated scripts or scene-to-script pairs (~7,990 examples). While these teach standard GDScript syntax, autonomous game development agents require deeper cognitive capabilities:
- **Architectural Reasoning**: Designing decoupled node hierarchies, singleton autoloads, signal wiring, and system boundaries.
- **Project-Level Planning**: Converting natural language requests into structured, dependency-ordered implementation tasks with verifiable acceptance criteria.
- **Debugging & Repair**: Diagnosing runtime stack traces, physics tunneling, null references, and applying verified diffs.
- **Tool-Use Trajectories**: Sequential execution traces showing tool invocation, observation analysis, error diagnosis, and verification.

This pipeline isolates data collection and curation from training, producing auditable datasets with cryptographic provenance.

---

## 2. What the Agent Needs to Learn

| Capability | Dataset Target | Primary Learning Objectives |
| :--- | :--- | :--- |
| **Project Architecture** | Dataset A (`projects/`) | Autoloads, scene dependencies, resource preloads, node hierarchies. |
| **Production Logic** | Dataset B (`production_logic/`) | 14-key plans (`project_summary`, `requirements`, `systems`, `tasks`, etc.). |
| **Debugging & Repair** | Dataset C (`debugging/`) | Root-cause analysis, unified diff hunks, test-driven validation. |
| **Agent Trajectories** | Dataset D (`trajectories/`) | Step-by-step tool invocation, result observation, and error recovery. |
| **Grounded GDScript** | Dataset E (`training/`) | Godot 4 standard syntax (`@export`, `@onready`, `PackedStringArray`). |

---

## 3. Directory Structure

```text
logic/
├── README.md                   # Complete architectural guide and manual
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Packaging and CLI specification
├── run_scraper.sh              # Safe manual execution launcher
├── .gitignore                  # Git exclusions for datasets, logs, and venvs
├── config/
│   ├── sources.yaml            # Configured data sources (local, github, docs)
│   ├── pipeline.yaml           # Global paths, seeds, batch sizes, and splits
│   ├── cleaning_rules.yaml     # PII redaction, bloat purge, and Godot 4 upgrades
│   └── validation_rules.yaml   # Schemas, cross-reference rules, headless flags
├── schemas/
│   ├── source_record.schema.json
│   ├── project.schema.json
│   ├── production_logic.schema.json
│   ├── agent_trajectory.schema.json
│   └── dataset_metadata.schema.json
├── src/logic_pipeline/         # Core pipeline implementation
│   ├── sources/                # Source connectors (local, github, docs, git)
│   ├── extractors/             # Static parsers (gdscript, scene, config, diffs)
│   ├── analysis/               # NetworkX project & scene graph analysis
│   ├── processing/             # Normalize, clean, deduplicate, split, export
│   ├── validation/             # Schema, cross-references, Godot 4 checks
│   └── reporting/              # Statistics, quality, and collection reports
├── data/                       # Isolated data directories (never committed)
│   ├── raw/                    # Immutable raw ingested source artifacts
│   ├── normalized/             # UTF-8 normalized records with standard line endings
│   ├── cleaned/                # Scrubbed and deduplicated records
│   ├── quarantine/             # Rejected records with exact failure reasons
│   ├── training/               # Final ShareGPT/ChatML train/val/test splits
│   └── manifests/              # Cryptographic SHA-256 manifests
├── reports/                    # Machine-readable JSON and human-readable Markdown reports
├── logs/                       # Rotating structured execution logs
└── tests/                      # Automated test suite (runs 100% offline)
```

---

## 4. Manual Execution Only — Never Auto-Start

Scraping, downloading, cleaning, or validation **NEVER runs automatically** upon project open, dependency install, or test runs. Real data collection requires explicit user invocation.

### Expected Workflow Commands

```bash
# 1. Navigate to repository root
cd /home/piet/Documents/dataset

# 2. Audit configuration, schemas, and existing structured datasets (Read-Only)
./logic/run_scraper.sh check-config

# 3. Preview structured dataset ingestion without disk writes (Dry Run)
./logic/run_scraper.sh ingest --sample-size 50 --dry-run

# 4. Ingest existing structured datasets (Dataset A: Projects, Dataset B: Debugging, Dataset C: Trajectories)
./logic/run_scraper.sh ingest --sample-size 50

# 5. (Optional) Discover & collect additional data from local projects or GitHub
./logic/run_scraper.sh collect --source local
# OR
./logic/run_scraper.sh collect --source github --limit 10

# 6. Normalize text, encodings, and JSONL records
./logic/run_scraper.sh normalize

# 7. Scrub sensitive paths, redact emails, and segregate quarantined records
./logic/run_scraper.sh clean

# 8. Deduplicate exact and near-duplicates
./logic/run_scraper.sh deduplicate

# 9. Validate against JSON schemas and cross-references
./logic/run_scraper.sh validate

# 10. Generate dataset statistics and ingestion audit reports
./logic/run_scraper.sh report

# 11. Export separate ShareGPT datasets for Qwen2.5-Coder
./logic/run_scraper.sh export
```

Alternatively, invoke Python directly:
```bash
python3 -m logic.logic_pipeline.cli check-config
python3 -m logic.logic_pipeline.cli ingest --sample-size 50 --dry-run
python3 -m logic.logic_pipeline.cli ingest --sample-size 50
python3 -m logic.logic_pipeline.cli export
```

---

## 5. Source Connectors

### A. Real Godot Repositories (`sources/github_api.py`, `sources/git_repository.py`)
- Searches GitHub API using queries such as `language:GDScript filename:project.godot`.
- Gated by license filters (`MIT`, `Apache-2.0`, `BSD-3-Clause`, `CC0-1.0`).
- Token bucket rate-limiting (default: 30 requests/minute) with exponential backoff.
- Shallow clones (`--depth 1`) stored strictly inside `logic/data/raw/repositories/`.

### B. Godot Documentation (`sources/godot_docs.py`)
- Scrapes approved official Godot documentation sections (`tutorials/scripting`, `tutorials/2d`, `classes/`).
- Preserves document titles, source URLs, engine version tags, and `CC-BY-3.0` attribution.

### C. Bug Fixes & Issues (`sources/issues.py`, `extractors/patches.py`)
- Extracts closed issues, merged PRs, and unified diff hunks.
- Distinguishes observed failures from proposed fixes and verified test results.

### D. Local Godot Projects (`sources/local_projects.py`)
- Scans explicitly configured directories listed in `config/sources.yaml`.
- Never crawls arbitrary filesystem paths.
- Automatically ignores secrets (`.env`), build caches (`.godot/`), and binary artifacts.

---

## 6. Data Cleaning, Scrubbing, and Quarantine

### Sensitivity Scrubbing
1. **Emails**: Matches RFC 5322 regex and replaces with `<REDACTED_EMAIL>`.
2. **Local Paths**: Redacts absolute paths like `/home/username/...` or `C:\Users\username\...` to `<REDACTED_LOCAL_PATH>`, while **strictly preserving** Godot protocols:
   - `res://`
   - `user://`
   - `/root/`

### Godot 4 Modernization
Transpiles legacy Godot 3 patterns:
- `export var` $\rightarrow$ `@export var`
- `onready var` $\rightarrow$ `@onready var`
- `Pool*Array` $\rightarrow$ `Packed*Array`

### Quarantine Mechanism
Records failing validation or containing corrupt tokens are never silently discarded. They are routed to `logic/data/quarantine/quarantined_records.jsonl` with an explicit failure reason:
- `EMPTY_CONTENT`: File or record contains no substantive content.
- `SCRIPT_TOO_SHORT`: Script contains fewer than 4 lines of logic.
- `FILE_TOO_LARGE`: Exceeds maximum size threshold (2 MB).
- `INVALID_SCHEMA`: Fails JSON schema validation.

---

## 7. Deduplication & Provenance Retention

- **Exact Content Deduplication**: Computes SHA-256 hashes of normalized records.
- **Near-Duplicate Detection**: Shingles tokens into unigrams and bigrams, calculating Jaccard similarity. Pairs exceeding 0.85 similarity are merged.
- **Provenance Preservation**: When records merge, secondary sources (commit hashes, URLs, licenses) append to `secondary_sources` inside `ProvenanceMetadata`.

---

## 8. Validation Boundaries & Headless Testing

The pipeline validates records at multiple levels:
1. **Schema Validation**: Validates all JSON documents against Draft-7 schemas in `schemas/`.
2. **Cross-Reference Validation**: Ensures scene paths, script attachments, task prerequisites, and acceptance criteria reference real components.
3. **Headless Godot Validation**:
   - Optional, opt-in execution (`--allow-runtime`).
   - Runs `godot4 --headless --editor --quit --path <temp_sandbox>` in an isolated, disposable directory.
   - **Important**: Headless compilation proves scripts parse without fatal errors; it does not prove dynamic gameplay loops or complex physics interactions work.

---

## 9. Preventing Training Data Leakage

Dataset splitting strictly respects project boundaries:
- **Project-Level Split**: All scenes, scripts, and tasks belonging to the same project are assigned to the same split (Train 80%, Validation 10%, Test 10%).
- **Deterministic**: Controlled via fixed seed `42` in `config/pipeline.yaml`.
- **Audit Manifest**: Assignments are recorded in `data/training/manifest_splits.json`.

---

## 10. Compatibility with Model Training

Exported training records match the exact ShareGPT/ChatML format expected by `train_dgx.py`:

```json
{
  "messages": [
    {"role": "system", "content": "You are a Godot game-production planning agent. Produce coherent, dependency-aware, testable game plans. Distinguish assumptions, proposed actions, and verified results."},
    {"role": "user", "content": "Make me a simple 2D platformer in Godot 4 where I run and jump through one level, collect coins, avoid spikes, and reach the exit door."},
    {"role": "assistant", "content": "{\"project_summary\": \"...\", \"assumptions\": [...], \"requirements\": {...}, \"gameplay_loop\": [...], \"architecture\": {...}, \"scenes\": [...], \"systems\": [...], \"dependencies\": [...], \"implementation_tasks\": [...], \"acceptance_criteria\": [...], \"risks\": [...], \"verification_plan\": [...], \"failure_analysis\": [...], \"execution_state\": \"plan_only_no_actions_executed\"}"}
  ]
}
```

Production logic records and code records are exported into isolated files:
- `data/training/train_sharegpt.jsonl`
- `data/training/val_sharegpt.jsonl`
- `data/training/test_sharegpt.jsonl`

---

## 11. Automated Testing

Run the full offline test suite at any time:

```bash
# Run all 32 tests using Python's standard unittest runner
python3 -m unittest discover -s logic/tests -v
```

All tests execute completely offline using synthetic fixtures in `tests/fixtures/sample_project/` and `tests/fixtures/sample_production_logic.jsonl`.

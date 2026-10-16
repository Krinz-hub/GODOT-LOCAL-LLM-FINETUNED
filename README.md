# Godot AI Training Dataset

This directory contains the multi-source dataset for training and fine-tuning Godot AI coding models and autonomous agents.

## Dataset Stages Workflow

```
Stage 1: Data Collection (COMPLETE)
  ↓ [Raw immutable multi-source crawls & cloned repositories]
Stage 2: Data Cleaning & Repair (COMPLETE)
  ↓ [Deduplicated, license-propagated, version-tagged, quality-gated]
NEXT: Stage 3 (Dataset Structuring - will be created when development begins)
```

> **Note on Future Stages**: No folders for Stage 3 or beyond have been created yet. They will be instantiated as needed when each subsequent development phase begins.

---

## Active Stages

### [Stage 1 — Data Collection](stage_01_collection/README.md)
* **Status**: `COMPLETE`
* **Access**: `IMMUTABLE SOURCE DATA`
* **Description**: Raw multi-source crawler outputs and legacy GitHub dataset (796 cloned repositories, 500,993 raw records).
* **Reference**: Manifest at [`stage_01_collection/manifest.json`](stage_01_collection/manifest.json).

### [Stage 2 — Data Cleaning & Repair](stage_02_repaired/README.md)
* **Status**: `COMPLETE`
* **Access**: `READ ONLY`
* **Description**: Cleaned, deduplicated, and validated baseline dataset with 81,764 structured records and 689 project graphs.
* **Reference**: Manifest at [`stage_02_repaired/manifest.json`](stage_02_repaired/manifest.json), Checksums at [`stage_02_repaired/audit/checksums.json`](stage_02_repaired/audit/checksums.json).

---

## Programmatic Access

Future stages should discover and load data through `dataset_manager.py`:

```python
from dataset_manager import manager

# List stages
stages = manager.list_stages()

# Get dataset paths
code_path = manager.get(stage=2, dataset="code")
projects_path = manager.get(stage=2, dataset="projects")
tasks_path = manager.get(stage=2, dataset="agent_tasks")

# Verify data integrity
verification = manager.verify(stage=2)
assert verification["all_valid"]
```

## CLI Commands

```bash
# List all active stages and dataset counts
python main.py --dataset-list

# Audit file existence, SHA256 checksums, and manifest consistency    
python main.py --dataset-audit
```

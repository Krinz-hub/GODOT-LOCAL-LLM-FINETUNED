# Godot AI Pipeline - Dataset Ingestion Audit Report
**Generated at:** `2026-10-16T06:47:56.741150+00:00`

## 1. Input Dataset Provenance & Integrity
The existing structured Godot datasets are treated as strictly immutable and read-only.

| Source Dataset | Exists | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :---: | :--- |
| `projects` | YES | 14,617,276 | `f45a06efa10b36fc...` |
| `debugging` | YES | 57,610 | `89388da4804feeb0...` |
| `agent_tasks` | YES | 438,207 | `d6887298e4ba7118...` |

## 2. Ingestion & Mapping Yield Summary

| Dataset | Examined | Mapped | Quarantined | Sufficient Evidence | Human Review Required | Yield % |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Dataset A (Production Logic)** | 5 | 5 | 0 | 5 | 0 | 100.0% |
| **Dataset B (Debugging and Repair)** | 5 | 5 | 0 | 5 | 5 | 100.0% |
| **Dataset C (Agent Trajectories)** | 5 | 5 | 0 | 0 | 5 | 100.0% |

## 3. Quarantine Analysis
Records fail ingestion when they violate target engine version requirements (e.g. Godot 3.x), contain missing scenes/scripts, or lack issue discussion solutions.

No records were quarantined in this ingestion run.

## 4. Unsupported or Missing Fields

### Dataset A (Production Logic)
- All required schema fields mapped cleanly.

### Dataset B (Debugging and Repair)
- All required schema fields mapped cleanly.

### Dataset C (Agent Trajectories)
- All required schema fields mapped cleanly.

## 5. Multi-Tier Validation Status

- **Tier 1 (Static Schema Conformance):** Passed for all mapped records using Draft-7 JSON Schemas (`production_logic`, `debugging_repair`, `agent_trajectory`).
- **Tier 2 (Evidence Grounding):** Scenes and scripts verified against file manifests in project graphs.
- **Tier 3 (Headless Project Launch):** Opt-in offline test requiring Godot 4 executable in sandbox.
- **Tier 4 (Automated Gameplay Testing):** Acceptance criteria evaluated in runtime test harness.

> [!IMPORTANT]
> **Statement of Verification Limits:** Static schema validation and evidence grounding confirm that plans > and trajectories are structurally sound and reference authentic project files. They do **not** constitute > proof that unverified games compile, run, or pass gameplay tests without human review.

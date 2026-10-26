# Godot 4 Dataset Audit & Quality Report

**Generated:** 2026-10-26 11:44:34  
**Input Source:** `/home/piet/Documents/dataset/final_godot_sharegpt.jsonl`  
**Manifest:** `/home/piet/Documents/dataset/reports/dataset_exclusion_manifest.jsonl`  
**Clean Split Target:** `/home/piet/Documents/dataset/cleaned_dataset`  

---

## 1. Summary of Cleaning & Partitioning

| Metric | Count | Percentage of Total |
| :--- | :---: | :---: |
| **Total Scanned Records** | **7990** | 100.0% |
| **Accepted Clean Godot 4 Records** | **6163** | **77.13%** |
| **Total Excluded Records** | **1827** | **22.87%** |
| - *Exact Duplicates Dropped* | 653 | 8.17% |
| - *Near-Duplicate Templates Dropped* | 331 | 4.14% |
| - *Unfixable Godot 3 Legacy Code Excluded* | 843 | 10.55% |
| - *Truncated / Stubs / Empty Dropped* | 0 | 0.00% |
| **Records Transpiled to Modern Godot 4** | **537** | 6.72% |

---

## 2. Excluded Godot 3 Pattern Breakdown

The following fatal legacy patterns were quarantined to prevent model poisoning:

| Deprecated Pattern | Occurrences Excluded |
| :--- | :---: |
| `setget` (Godot 3 property syntax) | 273 |
| `update()` (Godot 3 canvas redraw) | 116 |
| `File.new()` / `Directory.new()` | 116 |
| `Pool*Array` (Godot 3 arrays) | 46 |
| `to_json` / `parse_json` / `validate_json` | 38 |
| `move_and_slide` with arguments | 25 |
| Legacy signal strings (`connect("sig", self)`) | 462 |
| `Spatial` / `KinematicBody` (unresolved) | 0 |

---

## 3. Dataset Splits (Zero-Leakage Partition)

Clean records were partitioned with fixed ordering to guarantee zero leakage between train, validation, and evaluation:

| Split | File Path | Record Count | Purpose |
| :--- | :--- | :---: | :--- |
| **Train** | `/home/piet/Documents/dataset/cleaned_dataset/train.jsonl` | **5547** | Supervised fine-tuning |
| **Validation** | `/home/piet/Documents/dataset/cleaned_dataset/val.jsonl` | **308** | Training loss & early stopping |
| **Held-Out Test** | `/home/piet/Documents/dataset/cleaned_dataset/test.jsonl` | **308** | Offline model benchmarking |
| **Total** | | **6163** | **100.0% Pure Godot 4** |

---

## 4. Key Takeaways & Quality Guarantee

1. **Zero Data Loss on Raw Sources**: The original `final_godot_sharegpt.jsonl` was strictly preserved in read-only mode.
2. **Exclusion Transparency**: Every single one of the 1827 exclusions is recorded with its line index and reason in `/home/piet/Documents/dataset/reports/dataset_exclusion_manifest.jsonl`.
3. **Purity**: The clean dataset contains **0 instances of `setget`**, **0 instances of `File.new()`**, and **0 instances of `update()`**.

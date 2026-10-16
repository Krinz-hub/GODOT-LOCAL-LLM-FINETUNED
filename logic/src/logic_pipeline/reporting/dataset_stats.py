"""Comprehensive dataset statistics calculator."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_dataset_statistics(
    raw_count: int = 0,
    normalized_count: int = 0,
    cleaned_count: int = 0,
    quarantined_count: int = 0,
    projects_count: int = 0,
    production_logic_count: int = 0,
    debugging_count: int = 0,
    trajectories_count: int = 0,
    splits: Optional[Dict[str, int]] = None,
    licenses: Optional[Dict[str, int]] = None,
    versions: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Generates structured dataset statistics dictionary."""
    stats = {
        "report_timestamp": datetime.now(timezone.utc).isoformat(),
        "stages": {
            "raw_records": raw_count,
            "normalized_records": normalized_count,
            "cleaned_records": cleaned_count,
            "quarantined_records": quarantined_count,
        },
        "datasets": {
            "projects": projects_count,
            "production_logic": production_logic_count,
            "debugging": debugging_count,
            "trajectories": trajectories_count,
        },
        "splits": splits or {"train": 0, "val": 0, "test": 0},
        "license_distribution": licenses or {},
        "version_distribution": versions or {},
    }
    return stats


def format_stats_markdown(stats: Dict[str, Any]) -> str:
    """Formats dataset statistics into a readable Markdown report."""
    md = []
    md.append("# Godot Logic Pipeline - Dataset Statistics Report")
    md.append(f"**Generated at:** `{stats.get('report_timestamp')}`\n")

    md.append("## 1. Processing Stage Counts")
    stages = stats.get("stages", {})
    md.append(f"- **Raw Ingested Records:** {stages.get('raw_records', 0):,}")
    md.append(f"- **Normalized Records:** {stages.get('normalized_records', 0):,}")
    md.append(f"- **Cleaned Records:** {stages.get('cleaned_records', 0):,}")
    md.append(f"- **Quarantined Records:** {stages.get('quarantined_records', 0):,}\n")

    md.append("## 2. Specialized Dataset Types")
    datasets = stats.get("datasets", {})
    md.append(f"- **Dataset A (Projects & Architecture):** {datasets.get('projects', 0):,}")
    md.append(f"- **Dataset B (Production Logic Plans):** {datasets.get('production_logic', 0):,}")
    md.append(f"- **Dataset C (Debugging & Repair):** {datasets.get('debugging', 0):,}")
    md.append(f"- **Dataset D (Agent Trajectories):** {datasets.get('trajectories', 0):,}\n")

    md.append("## 3. Dataset Splits")
    splits = stats.get("splits", {})
    md.append(f"- **Train (80%):** {splits.get('train', 0):,}")
    md.append(f"- **Validation (10%):** {splits.get('val', 0):,}")
    md.append(f"- **Test (10%):** {splits.get('test', 0):,}\n")

    md.append("## 4. Distributions")
    md.append("### Engine Versions")
    for ver, count in stats.get("version_distribution", {}).items():
        md.append(f"- `{ver}`: {count:,}")

    md.append("\n### Licenses")
    for lic, count in stats.get("license_distribution", {}).items():
        md.append(f"- `{lic}`: {count:,}")

    return "\n".join(md)

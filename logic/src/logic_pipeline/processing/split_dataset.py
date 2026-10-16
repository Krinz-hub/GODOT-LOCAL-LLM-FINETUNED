"""Deterministic dataset splitting by repository to prevent data leakage."""

from dataclasses import dataclass, field
import hashlib
import random
from typing import Any, Dict, List, Set, Tuple
from logic_pipeline.logging_config import get_logger

logger = get_logger("processing.split")


@dataclass
class DatasetSplits:
    train: List[Dict[str, Any]] = field(default_factory=list)
    val: List[Dict[str, Any]] = field(default_factory=list)
    test: List[Dict[str, Any]] = field(default_factory=list)
    split_counts: Dict[str, int] = field(default_factory=dict)
    project_split_map: Dict[str, str] = field(default_factory=dict)


def _get_project_key(record: Dict[str, Any]) -> str:
    """Extracts project/repo identifier from record to group items together."""
    if "repository" in record and record["repository"]:
        return str(record["repository"])
    if "project_id" in record and record["project_id"]:
        return str(record["project_id"])
    if "project_name" in record and record["project_name"]:
        return str(record["project_name"])

    # Fallback to source_url domain/path or record_id
    prov = record.get("provenance", {})
    if prov.get("repository"):
        return str(prov["repository"])
    if prov.get("source_url"):
        return str(prov["source_url"])

    return str(record.get("record_id") or "standalone")


def split_dataset_by_project(
    records: List[Dict[str, Any]],
    train_ratio: float = 0.80,
    val_ratio: float = 0.10,
    test_ratio: float = 0.10,
    seed: int = 42,
) -> DatasetSplits:
    """Splits records by project identity so all files/tasks of a project stay in the same split."""
    splits = DatasetSplits()

    # Group records by project key
    project_groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        key = _get_project_key(r)
        project_groups.setdefault(key, []).append(r)

    # Sort project keys for determinism
    sorted_keys = sorted(list(project_groups.keys()))

    # Shuffle project keys with fixed seed
    rng = random.Random(seed)
    rng.shuffle(sorted_keys)

    total_projects = len(sorted_keys)
    train_cutoff = int(total_projects * train_ratio)
    val_cutoff = train_cutoff + int(total_projects * val_ratio)

    for idx, key in enumerate(sorted_keys):
        if idx < train_cutoff:
            target_split = "train"
        elif idx < val_cutoff:
            target_split = "val"
        else:
            target_split = "test"

        splits.project_split_map[key] = target_split
        group_records = project_groups[key]

        if target_split == "train":
            splits.train.extend(group_records)
        elif target_split == "val":
            splits.val.extend(group_records)
        else:
            splits.test.extend(group_records)

    splits.split_counts = {
        "train": len(splits.train),
        "val": len(splits.val),
        "test": len(splits.test),
        "total": len(records),
        "total_projects": total_projects,
    }

    logger.info(
        "Split %d records (%d projects) -> Train: %d, Val: %d, Test: %d",
        len(records),
        total_projects,
        len(splits.train),
        len(splits.val),
        len(splits.test),
    )

    return splits

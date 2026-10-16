"""Quality audit aggregator for datasets."""

from typing import Any, Dict, List
from logic_pipeline.validation.schema import validate_against_schema


def audit_dataset_quality(records: List[Dict[str, Any]], schema_name: str = "project") -> Dict[str, Any]:
    """Runs quality audit over a collection of records."""
    total = len(records)
    if total == 0:
        return {
            "total_records": 0,
            "valid_records": 0,
            "pass_rate": 1.0,
            "license_distribution": {},
            "version_distribution": {},
        }

    valid_count = 0
    license_dist: Dict[str, int] = {}
    version_dist: Dict[str, int] = {}

    for r in records:
        # Schema check
        is_val, _ = validate_against_schema(schema_name, r)
        if is_val:
            valid_count += 1

        # License
        lic = r.get("license") or r.get("provenance", {}).get("license") or "Unknown"
        license_dist[lic] = license_dist.get(lic, 0) + 1

        # Version
        ver = r.get("godot_version") or "Unknown"
        version_dist[ver] = version_dist.get(ver, 0) + 1

    return {
        "total_records": total,
        "valid_records": valid_count,
        "pass_rate": round(valid_count / total, 4),
        "license_distribution": license_dist,
        "version_distribution": version_dist,
    }

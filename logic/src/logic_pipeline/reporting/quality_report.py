"""Quality audit reporting module."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List


def generate_quality_report(
    total_evaluated: int,
    passed_records: int,
    quarantined_records: int,
    exact_duplicates: int,
    near_duplicates: int,
    schema_failures: int,
    cross_reference_failures: int,
    quarantine_reasons: Dict[str, int],
) -> Dict[str, Any]:
    """Builds machine-readable quality report dictionary."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_evaluated": total_evaluated,
            "passed_records": passed_records,
            "quarantined_records": quarantined_records,
            "pass_rate": round(passed_records / max(1, total_evaluated), 4),
        },
        "deduplication": {
            "exact_duplicates_removed": exact_duplicates,
            "near_duplicates_flagged": near_duplicates,
        },
        "validation_issues": {
            "schema_failures": schema_failures,
            "cross_reference_failures": cross_reference_failures,
        },
        "quarantine_breakdown": quarantine_reasons,
    }


def format_quality_markdown(report: Dict[str, Any]) -> str:
    """Formats quality audit dictionary into Markdown."""
    summary = report.get("summary", {})
    dedup = report.get("deduplication", {})
    val = report.get("validation_issues", {})
    q_break = report.get("quarantine_breakdown", {})

    lines = [
        "# Data Cleaning and Quality Audit Report",
        f"**Date:** `{report.get('timestamp')}`\n",
        "## Summary",
        f"- **Total Evaluated:** {summary.get('total_evaluated', 0):,}",
        f"- **Clean Records Passed:** {summary.get('passed_records', 0):,} ({summary.get('pass_rate', 0.0) * 100:.1f}%)",
        f"- **Quarantined Records:** {summary.get('quarantined_records', 0):,}\n",
        "## Deduplication Results",
        f"- **Exact Hash Duplicates Removed:** {dedup.get('exact_duplicates_removed', 0):,}",
        f"- **Near Duplicates Flagged/Merged:** {dedup.get('near_duplicates_flagged', 0):,}\n",
        "## Validation Failures",
        f"- **Schema Validation Failures:** {val.get('schema_failures', 0):,}",
        f"- **Cross-Reference Failures:** {val.get('cross_reference_failures', 0):,}\n",
        "## Quarantine Reasons Breakdown",
    ]

    if q_break:
        for reason, count in q_break.items():
            lines.append(f"- `{reason}`: {count:,}")
    else:
        lines.append("- *(No records quarantined)*")

    return "\n".join(lines)

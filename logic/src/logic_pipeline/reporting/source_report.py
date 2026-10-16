"""Collection and source audit reporting module."""

from datetime import datetime, timezone
from typing import Any, Dict, List


def generate_source_report(
    sources_discovered: int,
    sources_collected: int,
    sources_skipped: int,
    skip_reasons: Dict[str, int],
    records_by_source: Dict[str, int],
) -> Dict[str, Any]:
    """Generates structured source collection report dictionary."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "discovered_total": sources_discovered,
        "collected_total": sources_collected,
        "skipped_total": sources_skipped,
        "collection_rate": round(sources_collected / max(1, sources_discovered), 4),
        "skip_reasons": skip_reasons,
        "records_by_source": records_by_source,
    }


def format_source_markdown(report: Dict[str, Any]) -> str:
    """Formats source collection report into Markdown."""
    lines = [
        "# Data Collection Source Audit Report",
        f"**Date:** `{report.get('timestamp')}`\n",
        "## Ingestion Summary",
        f"- **Sources Discovered:** {report.get('discovered_total', 0):,}",
        f"- **Sources Collected:** {report.get('collected_total', 0):,} ({report.get('collection_rate', 0.0) * 100:.1f}%)",
        f"- **Sources Skipped:** {report.get('skipped_total', 0):,}\n",
        "## Records by Source Type",
    ]
    for src, count in report.get("records_by_source", {}).items():
        lines.append(f"- **{src}:** {count:,}")

    lines.append("\n## Skip Reasons")
    reasons = report.get("skip_reasons", {})
    if reasons:
        for r, c in reasons.items():
            lines.append(f"- `{r}`: {c:,}")
    else:
        lines.append("- *(No sources skipped)*")

    return "\n".join(lines)

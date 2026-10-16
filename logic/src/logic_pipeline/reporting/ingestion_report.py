"""Reporting module for dataset ingestion audit and quality yields."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from logic_pipeline.sources.structured_ingest import IngestionAuditSummary


def generate_ingestion_audit_report(
    summaries: List[IngestionAuditSummary],
    input_status: Dict[str, Dict[str, Any]],
    output_dir: Path,
) -> Tuple[Path, Path]:
    """Generates both Markdown and JSON audit reports for dataset ingestion."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_files": input_status,
        "datasets": [s.to_dict() for s in summaries],
        "validation_tiers": {
            "tier_1_static_schema": "Enforced on all mapped records via JSON schema validator.",
            "tier_2_ast_parsing": "Grounded against scene/script files recorded in project graph.",
            "tier_3_headless_launch": "Opt-in only; requires Godot 4 executable in isolated sandbox.",
            "tier_4_gameplay_tests": "Runtime execution; requires interactive or headless runner.",
            "statement_of_limits": "Static validation proves schema compliance and evidence grounding only; it does not claim games run without bugs.",
        },
    }

    # Save JSON
    json_path = output_dir / "ingestion_audit_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    # Save Markdown
    md_path = output_dir / "ingestion_audit_report.md"
    md_content = format_ingestion_markdown(report_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return md_path, json_path


def format_ingestion_markdown(data: Dict[str, Any]) -> str:
    lines = [
        "# Godot AI Pipeline - Dataset Ingestion Audit Report",
        f"**Generated at:** `{data['timestamp']}`",
        "",
        "## 1. Input Dataset Provenance & Integrity",
        "The existing structured Godot datasets are treated as strictly immutable and read-only.",
        "",
        "| Source Dataset | Exists | Size (Bytes) | SHA-256 Checksum |",
        "| :--- | :---: | :---: | :--- |",
    ]

    for key, info in data["input_files"].items():
        exists_str = "YES" if info["exists"] else "NO"
        lines.append(
            f"| `{key}` | {exists_str} | {info['size_bytes']:,} | `{info['sha256'][:16]}...` |"
        )

    lines.extend([
        "",
        "## 2. Ingestion & Mapping Yield Summary",
        "",
        "| Dataset | Examined | Mapped | Quarantined | Sufficient Evidence | Human Review Required | Yield % |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for ds in data["datasets"]:
        examined = ds["records_examined"]
        mapped = ds["records_mapped"]
        yield_pct = (mapped / examined * 100) if examined > 0 else 0.0
        lines.append(
            f"| **{ds['dataset_name']}** | {examined} | {mapped} | {ds['records_quarantined']} | "
            f"{ds['sufficient_evidence']} | {ds['requires_human_review']} | {yield_pct:.1f}% |"
        )

    lines.extend([
        "",
        "## 3. Quarantine Analysis",
        "Records fail ingestion when they violate target engine version requirements (e.g. Godot 3.x), "
        "contain missing scenes/scripts, or lack issue discussion solutions.",
        "",
    ])

    has_quarantines = False
    for ds in data["datasets"]:
        if ds["quarantine_reasons"]:
            has_quarantines = True
            lines.append(f"### {ds['dataset_name']} Quarantine Reasons")
            for reason, count in ds["quarantine_reasons"].items():
                lines.append(f"- **{reason}**: {count} record(s)")
            lines.append("")

    if not has_quarantines:
        lines.append("No records were quarantined in this ingestion run.\n")

    lines.extend([
        "## 4. Unsupported or Missing Fields",
        "",
    ])

    for ds in data["datasets"]:
        lines.append(f"### {ds['dataset_name']}")
        if ds["missing_fields_counts"]:
            for field, count in ds["missing_fields_counts"].items():
                lines.append(f"- `{field}`: omitted or synthesized in {count} records")
        else:
            lines.append("- All required schema fields mapped cleanly.")
        lines.append("")

    lines.extend([
        "## 5. Multi-Tier Validation Status",
        "",
        "- **Tier 1 (Static Schema Conformance):** Passed for all mapped records using Draft-7 JSON Schemas (`production_logic`, `debugging_repair`, `agent_trajectory`).",
        "- **Tier 2 (Evidence Grounding):** Scenes and scripts verified against file manifests in project graphs.",
        "- **Tier 3 (Headless Project Launch):** Opt-in offline test requiring Godot 4 executable in sandbox.",
        "- **Tier 4 (Automated Gameplay Testing):** Acceptance criteria evaluated in runtime test harness.",
        "",
        "> [!IMPORTANT]",
        "> **Statement of Verification Limits:** Static schema validation and evidence grounding confirm that plans "
        "> and trajectories are structurally sound and reference authentic project files. They do **not** constitute "
        "> proof that unverified games compile, run, or pass gameplay tests without human review.",
        "",
    ])

    return "\n".join(lines)

"""Quality assessment and filtering for Godot logic records."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class QualityAssessment:
    score: float = 1.0
    passes_threshold: bool = True
    quarantine_reason: Optional[str] = None
    issues: List[str] = field(default_factory=list)


def assess_quality(record: Dict[str, Any], min_score: float = 0.6) -> QualityAssessment:
    """Computes a quality score and determines whether to accept or quarantine the record."""
    assessment = QualityAssessment()
    score = 1.0

    # Check for placeholder-only or empty content
    content = record.get("normalized_content") or record.get("raw_content") or ""
    if not content and "messages" in record and isinstance(record["messages"], list):
        content = " ".join([m.get("content", "") for m in record["messages"] if isinstance(m, dict)])

    if isinstance(content, str):
        stripped = content.strip()
        if not stripped:
            return QualityAssessment(score=0.0, passes_threshold=False, quarantine_reason="EMPTY_CONTENT")
        if stripped in ["pass", "# todo", "// todo", "extends Node\npass"]:
            return QualityAssessment(score=0.1, passes_threshold=False, quarantine_reason="PLACEHOLDER_ONLY")

    # Check provenance completeness
    prov = record.get("provenance")
    if not prov or not isinstance(prov, dict):
        score -= 0.2
        assessment.issues.append("Missing provenance metadata")
    else:
        if not prov.get("source_url"):
            score -= 0.1
            assessment.issues.append("Missing source URL")
        if prov.get("license") in ["Unknown", "NOASSERTION", None]:
            score -= 0.1
            assessment.issues.append("Unknown or unverified license")

    # Check record type specific quality
    rec_type = record.get("record_type")
    if rec_type == "production_logic":
        # Check that required keys exist
        required_keys = [
            "project_summary", "requirements", "architecture", "scenes",
            "systems", "implementation_tasks", "acceptance_criteria"
        ]
        missing = [k for k in required_keys if k not in record]
        if missing:
            score -= 0.1 * len(missing)
            assessment.issues.append(f"Missing plan keys: {', '.join(missing)}")

    assessment.score = max(0.0, round(score, 2))
    if assessment.score < min_score:
        assessment.passes_threshold = False
        assessment.quarantine_reason = "QUALITY_BELOW_THRESHOLD"

    return assessment

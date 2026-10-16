"""Extractor for GitHub issues, bug reports, and PRs."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class IssueRecord:
    issue_id: str
    repository: str
    title: str
    body: str
    labels: List[str] = field(default_factory=list)
    state: str = "closed"
    closed_at: Optional[str] = None
    pr_number: Optional[int] = None
    patch_diff: Optional[str] = None
    root_cause: Optional[str] = None
    proposed_repair: Optional[str] = None


def parse_issue_record(data: Dict[str, Any]) -> IssueRecord:
    """Parses raw JSON or dictionary data into structured IssueRecord."""
    return IssueRecord(
        issue_id=str(data.get("issue_id") or data.get("id") or ""),
        repository=data.get("repository", ""),
        title=data.get("title", ""),
        body=data.get("body", "") or data.get("context", ""),
        labels=data.get("labels", []),
        state=data.get("state", "closed"),
        closed_at=data.get("closed_at"),
        pr_number=data.get("pr_number"),
        patch_diff=data.get("patch"),
        root_cause=data.get("root_cause") or data.get("reasoning"),
        proposed_repair=data.get("proposed_repair") or data.get("instruction"),
    )

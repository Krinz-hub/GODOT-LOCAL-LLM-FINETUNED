"""Base classes and interfaces for data collection sources."""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from logic_pipeline.provenance import compute_sha256


@dataclass
class SourceItem:
    item_id: str
    source_type: str  # "local", "github", "docs", "issues", "patches"
    source_url: str
    repository: Optional[str] = None
    commit_hash: Optional[str] = None
    license: str = "Unknown"
    license_source: str = "Unknown"
    godot_version: str = "Unknown"
    file_path: str = ""
    raw_content: str = ""
    retrieval_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    content_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.content_hash and self.raw_content:
            self.content_hash = compute_sha256(self.raw_content)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseSource(ABC):
    """Abstract connector for discovering and retrieving Godot data."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def discover(self, limit: Optional[int] = None) -> List[SourceItem]:
        """Discovers candidate items without necessarily downloading full contents."""
        pass

    @abstractmethod
    def fetch(self, item: SourceItem) -> SourceItem:
        """Fetches the full raw content of a specific source item."""
        pass

    def collect(
        self, dry_run: bool = False, limit: Optional[int] = None
    ) -> List[SourceItem]:
        """Executes discovery and optional retrieval."""
        items = self.discover(limit=limit)
        if dry_run:
            return items

        results = []
        for item in items:
            fetched = self.fetch(item)
            results.append(fetched)
        return results

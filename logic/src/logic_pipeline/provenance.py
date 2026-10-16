"""Provenance tracking and cryptographic hashing for data lineage."""

from dataclasses import asdict, dataclass, field
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def compute_sha256(content: str) -> str:
    """Computes SHA-256 hash of a text string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hash of a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class ProvenanceMetadata:
    source_id: str
    source_type: str  # local, github, docs, issues, patches
    source_url: str
    repository: Optional[str] = None
    commit_hash: Optional[str] = None
    license: str = "Unknown"
    license_source: str = "Unknown"
    retrieval_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    raw_hash: str = ""
    normalized_hash: str = ""
    transformations: List[str] = field(default_factory=list)
    secondary_sources: List[Dict[str, Any]] = field(default_factory=list)

    def add_transformation(self, step_name: str) -> None:
        """Records a transformation step applied to the record."""
        self.transformations.append(
            f"{step_name}@{datetime.now(timezone.utc).isoformat()}"
        )

    def merge_with(self, other: "ProvenanceMetadata") -> None:
        """Merges provenance when deduplicating records."""
        self.secondary_sources.append({
            "source_id": other.source_id,
            "source_type": other.source_type,
            "source_url": other.source_url,
            "repository": other.repository,
            "commit_hash": other.commit_hash,
            "license": other.license,
            "retrieval_timestamp": other.retrieval_timestamp,
        })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProvenanceMetadata":
        return cls(
            source_id=data.get("source_id", ""),
            source_type=data.get("source_type", "unknown"),
            source_url=data.get("source_url", ""),
            repository=data.get("repository"),
            commit_hash=data.get("commit_hash"),
            license=data.get("license", "Unknown"),
            license_source=data.get("license_source", "Unknown"),
            retrieval_timestamp=data.get("retrieval_timestamp", datetime.now(timezone.utc).isoformat()),
            raw_hash=data.get("raw_hash", ""),
            normalized_hash=data.get("normalized_hash", ""),
            transformations=data.get("transformations", []),
            secondary_sources=data.get("secondary_sources", []),
        )

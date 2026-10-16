"""Manifest tracking and audit logging for pipeline stages."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from logic_pipeline.provenance import compute_file_sha256
from logic_pipeline.logging_config import get_logger

logger = get_logger("manifest")


@dataclass
class ManifestEntry:
    record_id: str
    stage: str
    source_type: str
    source_url: str
    file_path: str
    sha256: str
    size_bytes: int
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)


class StageManifest:
    """Manages the manifest for a single stage or artifact set."""

    def __init__(self, manifest_file: Path, stage_name: str):
        self.manifest_file = manifest_file
        self.stage_name = stage_name
        self.entries: List[ManifestEntry] = []
        self.load()

    def load(self) -> None:
        """Loads manifest entries if the file exists."""
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            self.entries.append(ManifestEntry(**data))
            except Exception as e:
                logger.warning("Error reading manifest %s: %s", self.manifest_file, e)

    def add_entry(
        self,
        record_id: str,
        source_type: str,
        source_url: str,
        file_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ManifestEntry:
        """Adds a file entry to the manifest and computes its SHA-256."""
        sha256 = compute_file_sha256(str(file_path)) if file_path.exists() else ""
        size = file_path.stat().st_size if file_path.exists() else 0

        entry = ManifestEntry(
            record_id=record_id,
            stage=self.stage_name,
            source_type=source_type,
            source_url=source_url,
            file_path=str(file_path),
            sha256=sha256,
            size_bytes=size,
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry

    def save(self) -> None:
        """Persists the manifest entries to disk in JSONL format."""
        self.manifest_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = self.manifest_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            for entry in self.entries:
                f.write(json.dumps(asdict(entry)) + "\n")
        tmp_file.replace(self.manifest_file)
        logger.info(
            "Saved manifest %s with %d entries",
            self.manifest_file.name,
            len(self.entries),
        )

"""Checkpointing system to make collection and processing stages resumable."""

import json
from pathlib import Path
from typing import Any, Dict, Set
from logic_pipeline.logging_config import get_logger

logger = get_logger("checkpoints")


class CheckpointManager:
    """Manages stage-specific checkpoint files for resumability."""

    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = checkpoint_path
        self.completed_keys: Set[str] = set()
        self.metadata: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Loads existing checkpoint state from disk if present."""
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.completed_keys = set(data.get("completed_keys", []))
                    self.metadata = data.get("metadata", {})
                logger.info(
                    "Loaded checkpoint %s with %d completed items",
                    self.checkpoint_path.name,
                    len(self.completed_keys),
                )
            except Exception as e:
                logger.warning("Failed to load checkpoint file %s: %s", self.checkpoint_path, e)
                self.completed_keys = set()
                self.metadata = {}

    def save(self) -> None:
        """Persists current checkpoint state to disk atomically."""
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.checkpoint_path.with_suffix(".tmp")
        data = {
            "completed_keys": sorted(list(self.completed_keys)),
            "metadata": self.metadata,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp_path.replace(self.checkpoint_path)

    def is_completed(self, key: str) -> bool:
        """Checks if a key has already been processed."""
        return key in self.completed_keys

    def mark_completed(self, key: str, meta: Any = None) -> None:
        """Marks a key as completed and optionally stores metadata."""
        self.completed_keys.add(key)
        if meta is not None:
            self.metadata[key] = meta

    def clear(self) -> None:
        """Clears all checkpoint state."""
        self.completed_keys.clear()
        self.metadata.clear()
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

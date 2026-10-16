"""Git repository clone and file retrieval connector."""

import os
from pathlib import Path
import subprocess
from typing import Dict, List, Optional
from logic_pipeline.sources.base import SourceItem
from logic_pipeline.logging_config import get_logger

logger = get_logger("sources.git")


class GitRepositoryCloner:
    """Performs safe shallow clones of Godot repositories strictly into logic/data/raw/."""

    def __init__(self, target_base_dir: Path, clone_depth: int = 1):
        self.target_base_dir = target_base_dir
        self.clone_depth = clone_depth
        self.target_base_dir.mkdir(parents=True, exist_ok=True)

    def clone_or_update(self, repo_url: str, repo_id: str) -> Optional[Path]:
        """Performs a shallow git clone of repo_url into target_base_dir / repo_id."""
        clean_id = repo_id.replace("/", "_").replace(":", "_")
        dest_dir = self.target_base_dir / clean_id

        # Safety check: ensure dest_dir is strictly under target_base_dir
        try:
            dest_dir.resolve().relative_to(self.target_base_dir.resolve())
        except ValueError:
            logger.error("Destination directory %s escapes target base %s", dest_dir, self.target_base_dir)
            return None

        if dest_dir.exists():
            logger.info("Repository %s already cloned at %s", repo_id, dest_dir)
            return dest_dir

        cmd = [
            "git", "clone",
            "--depth", str(self.clone_depth),
            "--single-branch",
            repo_url,
            str(dest_dir),
        ]
        try:
            logger.info("Cloning %s to %s...", repo_url, dest_dir)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.warning("Git clone failed for %s: %s", repo_url, result.stderr)
                return None
            return dest_dir
        except subprocess.TimeoutExpired:
            logger.warning("Git clone timed out for %s", repo_url)
            return None
        except Exception as e:
            logger.error("Error executing git clone for %s: %s", repo_url, e)
            return None

    def get_commit_hash(self, repo_dir: Path) -> str:
        """Gets current HEAD commit hash."""
        cmd = ["git", "-C", str(repo_dir), "rev-parse", "HEAD"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return "unknown"

"""Local Godot projects source connector."""

import fnmatch
import os
from pathlib import Path
from typing import List, Optional
from logic_pipeline.sources.base import BaseSource, SourceItem
from logic_pipeline.logging_config import get_logger

logger = get_logger("sources.local")


class LocalProjectsSource(BaseSource):
    """Discovers and reads files from explicitly configured local Godot projects."""

    def __init__(
        self,
        project_paths: List[str],
        scan_depth: int = 3,
        exclude_patterns: Optional[List[str]] = None,
    ):
        super().__init__(name="local")
        self.project_paths = [Path(p) for p in project_paths]
        self.scan_depth = scan_depth
        self.exclude_patterns = exclude_patterns or [
            "**/.git/**",
            "**/.godot/**",
            "**/.venv/**",
            "**/build/**",
            "**/.import/**",
            "*.env",
            "*.key",
            "*.pem",
        ]

    def _is_excluded(self, path: Path) -> bool:
        path_str = str(path).replace("\\", "/")
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
        return False

    def _detect_godot_version(self, project_file: Path) -> str:
        """Inspects project.godot to determine Godot engine version."""
        if not project_file.exists():
            return "Unknown"
        try:
            with open(project_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(2048)
                if 'config_version=5' in content:
                    for line in content.splitlines():
                        if "config/features" in line and '"4.' in line:
                            # Extract minor version if present
                            parts = line.split('"')
                            for part in parts:
                                if part.startswith("4."):
                                    return f"Godot {part}"
                    return "Godot 4.x"
                elif 'config_version=4' in content:
                    return "Godot 3.x"
        except Exception as e:
            logger.warning("Error detecting version from %s: %s", project_file, e)
        return "Unknown"

    def _detect_license(self, project_dir: Path) -> str:
        """Looks for a LICENSE or COPYING file in project directory."""
        for candidate in ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"]:
            p = project_dir / candidate
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read(1000).upper()
                        if "MIT" in text:
                            return "MIT"
                        elif "APACHE" in text:
                            return "Apache-2.0"
                        elif "GPL" in text:
                            return "GPL"
                        elif "BSD" in text:
                            return "BSD"
                        elif "CREATIVE COMMONS" in text or "CC0" in text:
                            return "CC0"
                        return f"Custom ({candidate})"
                except Exception:
                    pass
        return "Unspecified"

    def discover(self, limit: Optional[int] = None) -> List[SourceItem]:
        """Discovers files from configured Godot projects."""
        discovered: List[SourceItem] = []

        for p_root in self.project_paths:
            if not p_root.exists():
                logger.warning("Configured local project path does not exist: %s", p_root)
                continue

            # Verify it's a Godot project
            project_godot = p_root / "project.godot"
            if not project_godot.exists():
                logger.warning("Skipping %s: No project.godot found at root", p_root)
                continue

            godot_version = self._detect_godot_version(project_godot)
            license_val = self._detect_license(p_root)
            project_name = p_root.name

            logger.info("Found local project '%s' (%s, license: %s)", project_name, godot_version, license_val)

            # Traverse project files
            for root, dirs, files in os.walk(p_root):
                # Filter directories in-place
                dirs[:] = [d for d in dirs if not self._is_excluded(Path(root) / d)]

                for f_name in files:
                    full_path = Path(root) / f_name
                    if self._is_excluded(full_path):
                        continue

                    # Filter to Godot relevant files
                    ext = full_path.suffix.lower()
                    if ext in [".gd", ".tscn", ".tres", ".godot", ".md"] or f_name == "project.godot":
                        rel_path = full_path.relative_to(p_root).as_posix()
                        item_id = f"local:{project_name}:{rel_path}"

                        item = SourceItem(
                            item_id=item_id,
                            source_type="local",
                            source_url=f"file://{full_path.resolve()}",
                            repository=project_name,
                            license=license_val,
                            license_source="project_root" if license_val != "Unspecified" else "none",
                            godot_version=godot_version,
                            file_path=rel_path,
                            metadata={"absolute_path": str(full_path.resolve())},
                        )
                        discovered.append(item)

                        if limit and len(discovered) >= limit:
                            return discovered

        return discovered

    def fetch(self, item: SourceItem) -> SourceItem:
        """Reads file contents from disk."""
        abs_path = item.metadata.get("absolute_path")
        if abs_path and os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    item.raw_content = f.read()
            except Exception as e:
                logger.error("Failed to read %s: %s", abs_path, e)
                item.raw_content = ""
        return item

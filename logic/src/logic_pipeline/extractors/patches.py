"""Parser for Git diffs and patches."""

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional


@dataclass
class DiffHunk:
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str] = field(default_factory=list)


@dataclass
class FilePatch:
    old_path: str
    new_path: str
    hunks: List[DiffHunk] = field(default_factory=list)
    added_lines: int = 0
    deleted_lines: int = 0


def parse_git_diff(diff_text: str) -> List[FilePatch]:
    """Parses standard unified git diff into FilePatch records."""
    patches: List[FilePatch] = []
    current_patch: Optional[FilePatch] = None
    current_hunk: Optional[DiffHunk] = None

    diff_file_pattern = re.compile(r"^diff --git a/(.*?) b/(.*?)$")
    hunk_header_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

    for line in diff_text.splitlines():
        m_file = diff_file_pattern.match(line)
        if m_file:
            if current_patch:
                patches.append(current_patch)
            current_patch = FilePatch(old_path=m_file.group(1), new_path=m_file.group(2))
            current_hunk = None
            continue

        m_hunk = hunk_header_pattern.match(line)
        if m_hunk and current_patch:
            old_s = int(m_hunk.group(1))
            old_c = int(m_hunk.group(2)) if m_hunk.group(2) else 1
            new_s = int(m_hunk.group(3))
            new_c = int(m_hunk.group(4)) if m_hunk.group(4) else 1
            current_hunk = DiffHunk(
                header=line,
                old_start=old_s,
                old_count=old_c,
                new_start=new_s,
                new_count=new_c,
            )
            current_patch.hunks.append(current_hunk)
            continue

        if current_hunk:
            current_hunk.lines.append(line)
            if current_patch:
                if line.startswith("+") and not line.startswith("+++"):
                    current_patch.added_lines += 1
                elif line.startswith("-") and not line.startswith("---"):
                    current_patch.deleted_lines += 1

    if current_patch:
        patches.append(current_patch)

    return patches

"""Cleaning and sensitivity scrubbing for Godot data."""

from dataclasses import dataclass, field
import re
from typing import List, Optional
from logic_pipeline.config import CleaningRules

# Regex patterns for scrubbing
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Local filesystem paths (Unix and Windows), excluding res://, user://, /root/
LOCAL_PATHS_REGEX = re.compile(
    r"(?:"
    r"\b[a-zA-Z]:[/\\](?:Users|Documents|Desktop|Downloads|Projects|workspace|code|home)[/\\][^\s\"'`;>\n\r]+"
    r"|"
    r"(?<![a-zA-Z0-9_])/(?:home|Users|private/var/folders)/[A-Za-z0-9_.-]+(?:/[^\s\"'`;>\n\r]*)?"
    r")"
)

# Base64 large blobs
BASE64_BLOAT_REGEX = re.compile(r'"(?:data:[^;]+;base64,)?[A-Za-z0-9+/=]{100,}"')


@dataclass
class CleaningResult:
    is_clean: bool = True
    cleaned_content: str = ""
    quarantine_reason: Optional[str] = None
    transformations: List[str] = field(default_factory=list)


def scrub_sensitive_data(text: str, redact_emails: bool = True, redact_paths: bool = True) -> str:
    """Removes emails and personal local filesystem paths while preserving Godot internal paths."""
    scrubbed = text
    if redact_emails:
        scrubbed = EMAIL_REGEX.sub("<REDACTED_EMAIL>", scrubbed)
    if redact_paths:
        scrubbed = LOCAL_PATHS_REGEX.sub("<REDACTED_LOCAL_PATH>", scrubbed)
    return scrubbed


def clean_content(
    content: str,
    rules: Optional[CleaningRules] = None,
    file_path: str = "",
) -> CleaningResult:
    """Applies quality filters, sensitive data scrubbing, and Godot 4 upgrades."""
    rules = rules or CleaningRules()
    res = CleaningResult(cleaned_content=content)

    if not content or not content.strip():
        res.is_clean = False
        res.quarantine_reason = "EMPTY_CONTENT"
        return res

    # Check file size
    if len(content.encode("utf-8")) > rules.max_file_size_bytes:
        res.is_clean = False
        res.quarantine_reason = "FILE_TOO_LARGE"
        return res

    # Check minimum lines of code for script files
    if file_path.endswith(".gd"):
        lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
        if len(lines) < rules.min_lines_of_code:
            res.is_clean = False
            res.quarantine_reason = "SCRIPT_TOO_SHORT"
            return res

    # Reject or strip base64 bloat
    if BASE64_BLOAT_REGEX.search(content):
        res.cleaned_content = BASE64_BLOAT_REGEX.sub('"<BASE64_BLOB_REMOVED>"', res.cleaned_content)
        res.transformations.append("removed_base64_bloat")

    # Scrub sensitive data
    scrubbed = scrub_sensitive_data(
        res.cleaned_content,
        redact_emails=rules.redact_emails,
        redact_paths=rules.redact_local_paths,
    )
    if scrubbed != res.cleaned_content:
        res.cleaned_content = scrubbed
        res.transformations.append("scrubbed_sensitive_data")

    # Apply Godot 4 syntax migrations only if explicitly enabled
    if getattr(rules, "auto_upgrade_annotations", False) and file_path.endswith(".gd"):
        upgraded = res.cleaned_content
        # export var -> @export var
        upgraded = re.sub(r"(?<!@)\bexport\s*(?:\([^)]*\))?\s*var\b", "@export var", upgraded)
        # onready var -> @onready var
        upgraded = re.sub(r"(?<!@)\bonready\s+var\b", "@onready var", upgraded)
        # Pool arrays -> Packed arrays
        upgraded = re.sub(r"\bPoolStringArray\b", "PackedStringArray", upgraded)
        upgraded = re.sub(r"\bPoolIntArray\b", "PackedInt32Array", upgraded)
        upgraded = re.sub(r"\bPoolRealArray\b", "PackedFloat32Array", upgraded)
        upgraded = re.sub(r"\bPoolVector2Array\b", "PackedVector2Array", upgraded)
        upgraded = re.sub(r"\bPoolVector3Array\b", "PackedVector3Array", upgraded)
        upgraded = re.sub(r"\bPoolColorArray\b", "PackedColorArray", upgraded)
        upgraded = re.sub(r"\bPoolByteArray\b", "PackedByteArray", upgraded)

        if upgraded != res.cleaned_content:
            res.cleaned_content = upgraded
            res.transformations.append("godot4_transpiled")

    return res

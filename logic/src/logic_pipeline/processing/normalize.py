"""Text and record normalization utilities."""

import json
from typing import Any, Dict, List, Optional, Tuple
from logic_pipeline.logging_config import get_logger

logger = get_logger("processing.normalize")


def normalize_text(text: str) -> str:
    """Normalizes line endings, trailing whitespace, and path separators."""
    if not text:
        return ""

    # Replace CRLF and CR with LF
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    # Strip trailing whitespace on each line
    lines = [line.rstrip() for line in normalized.split("\n")]
    result = "\n".join(lines).strip()
    return result + "\n" if result else ""


def normalize_path(path: str) -> str:
    """Converts backslashes to forward slashes and strips leading/trailing slashes."""
    return path.replace("\\", "/").strip()


def normalize_record(raw_record: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Normalizes a raw record dictionary."""
    if not isinstance(raw_record, dict):
        return None, "Record is not a dictionary"

    rec = dict(raw_record)

    # Normalize file path if present
    if "file_path" in rec and isinstance(rec["file_path"], str):
        rec["file_path"] = normalize_path(rec["file_path"])

    # Normalize raw_content if present
    if "raw_content" in rec and isinstance(rec["raw_content"], str):
        rec["normalized_content"] = normalize_text(rec["raw_content"])
    elif "content" in rec and isinstance(rec["content"], str):
        rec["normalized_content"] = normalize_text(rec["content"])
    elif "messages" in rec and isinstance(rec["messages"], list):
        for m in rec["messages"]:
            if "content" in m and isinstance(m["content"], str):
                m["content"] = normalize_text(m["content"]).strip()
        rec["normalized_content"] = json.dumps(rec["messages"])

    return rec, None


def parse_jsonl_safely(file_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Reads a JSONL file line-by-line, isolating valid records from malformed lines."""
    valid_records = []
    malformed_records = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, start=1):
                clean_line = line.strip()
                if not clean_line:
                    continue
                try:
                    data = json.loads(clean_line)
                    if isinstance(data, dict):
                        valid_records.append(data)
                    else:
                        malformed_records.append({
                            "line_number": line_no,
                            "error": "Not a JSON object",
                            "raw": clean_line[:200],
                        })
                except json.JSONDecodeError as exc:
                    malformed_records.append({
                        "line_number": line_no,
                        "error": str(exc),
                        "raw": clean_line[:200],
                    })
    except Exception as e:
        logger.error("Failed to read JSONL file %s: %s", file_path, e)

    return valid_records, malformed_records

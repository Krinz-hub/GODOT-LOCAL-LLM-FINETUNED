"""Read-only ingestion adapter for existing structured Godot datasets.

Reads from:
- structured/projects.jsonl
- structured/debugging.jsonl
- structured/agent_tasks.jsonl

Writes exclusively to logic/data/ingested/ and tracks full provenance.
Existing input files are treated as immutable and read-only.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from logic_pipeline.config import find_logic_root
from logic_pipeline.extractors.structured_mappers import (
    map_structured_project_to_production_logic,
    map_structured_debugging_to_repair,
    map_structured_agent_task_to_trajectory,
)
from logic_pipeline.logging_config import get_logger
from logic_pipeline.manifest import StageManifest
from logic_pipeline.provenance import compute_file_sha256

logger = get_logger("sources.structured_ingest")


@dataclass
class IngestionAuditSummary:
    dataset_name: str
    input_file: str
    input_sha256: str
    records_examined: int = 0
    records_mapped: int = 0
    records_quarantined: int = 0
    duplicate_records: int = 0
    sufficient_evidence: int = 0
    requires_human_review: int = 0
    missing_fields_counts: Dict[str, int] = field(default_factory=dict)
    quarantine_reasons: Dict[str, int] = field(default_factory=dict)
    output_file: str = ""
    output_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "input_file": self.input_file,
            "input_sha256": self.input_sha256,
            "records_examined": self.records_examined,
            "records_mapped": self.records_mapped,
            "records_quarantined": self.records_quarantined,
            "duplicate_records": self.duplicate_records,
            "sufficient_evidence": self.sufficient_evidence,
            "requires_human_review": self.requires_human_review,
            "missing_fields_counts": self.missing_fields_counts,
            "quarantine_reasons": self.quarantine_reasons,
            "output_file": self.output_file,
            "output_count": self.output_count,
        }


class CodeIndex:
    """Byte-offset index for structured/code.jsonl to stream project files with near-zero memory."""

    def __init__(self, code_file: Path, index_cache_file: Optional[Path] = None):
        self.code_file = code_file
        self.index_cache_file = index_cache_file
        self.project_spans: Dict[str, Tuple[int, int]] = {}
        self._build_or_load_index()

    def build_index(self):
        """Explicitly build or rebuild the byte-offset index."""
        self._build_or_load_index()

    def __contains__(self, project_id: str) -> bool:
        return project_id in self.project_spans

    def _build_or_load_index(self):
        if not self.code_file.exists():
            return

        if self.index_cache_file and self.index_cache_file.exists():
            try:
                if self.index_cache_file.stat().st_mtime >= self.code_file.stat().st_mtime:
                    with open(self.index_cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.project_spans = {k: (v[0], v[1]) for k, v in data.items()}
                        return
            except Exception as e:
                logger.warning("Could not load code index cache: %s", e)

        current_pid = None
        start_offset = 0
        offset = 0

        with open(self.code_file, "rb") as f:
            for line in f:
                line_len = len(line)
                pid_idx = line.find(b'"project_id": "')
                if pid_idx != -1:
                    end_idx = line.find(b'"', pid_idx + 15)
                    pid = line[pid_idx + 15:end_idx].decode("utf-8", "ignore")
                else:
                    try:
                        pid = json.loads(line).get("project_id")
                    except Exception:
                        pid = None

                if pid and not pid.strip():
                    pid = None

                if pid != current_pid:
                    if current_pid:
                        self.project_spans[current_pid] = (start_offset, offset - start_offset)
                    current_pid = pid
                    start_offset = offset

                offset += line_len

            if current_pid:
                self.project_spans[current_pid] = (start_offset, offset - start_offset)

        if self.index_cache_file:
            try:
                self.index_cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.index_cache_file, "w", encoding="utf-8") as f:
                    json.dump(self.project_spans, f)
            except Exception as e:
                logger.warning("Could not save code index cache: %s", e)

    def get_files_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        if not project_id or project_id not in self.project_spans or not self.code_file.exists():
            return []

        start_offset, length = self.project_spans[project_id]
        files: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()
        with open(self.code_file, "rb") as f:
            f.seek(start_offset)
            chunk = f.read(length)
            for line in chunk.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    raw_path = data.get("path") or data.get("file_path") or ""
                    clean_path = raw_path.replace("\\", "/").strip()
                    norm_path = clean_path.replace("res://", "")
                    if norm_path in seen_paths:
                        continue
                    seen_paths.add(norm_path)

                    files.append({
                        "path": clean_path,
                        "content": data.get("content") or "",
                        "type": data.get("category") or data.get("language") or "gdscript",
                        "size_bytes": len((data.get("content") or "").encode("utf-8")),
                        "project_id": data.get("project_id"),
                        "repository": data.get("repository"),
                    })
                except Exception:
                    continue
        return files

    get_project_files = get_files_for_project


class StructuredIngestionAdapter:
    """Reads existing structured datasets and maps them to logic schemas."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        logic_root: Optional[Path] = None,
    ):
        self.logic_root = logic_root or find_logic_root()
        self.workspace_root = workspace_root or self.logic_root.parent
        self.structured_dir = self.workspace_root / "structured"
        self.output_dir = self.logic_root / "data" / "ingested"
        self.quarantine_dir = self.logic_root / "data" / "quarantine"
        self.manifest_dir = self.logic_root / "data" / "manifests"
        self.reports_dir = self.logic_root / "reports" / "ingestion"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.code_file = self.structured_dir / "code.jsonl"
        self.code_index = CodeIndex(self.code_file, self.manifest_dir / "code_index.json")

    def check_inputs_available(self) -> Dict[str, Dict[str, Any]]:
        """Verifies read-only availability and computes SHA-256 for all structured inputs."""
        inputs = {
            "projects": self.structured_dir / "projects.jsonl",
            "debugging": self.structured_dir / "debugging.jsonl",
            "agent_tasks": self.structured_dir / "agent_tasks.jsonl",
        }
        status = {}
        for key, path in inputs.items():
            if path.exists():
                size = path.stat().st_size
                sha = compute_file_sha256(str(path))
                status[key] = {
                    "path": str(path),
                    "exists": True,
                    "size_bytes": size,
                    "sha256": sha,
                }
            else:
                status[key] = {
                    "path": str(path),
                    "exists": False,
                    "size_bytes": 0,
                    "sha256": "",
                }
        return status

    def ingest_dataset_a(
        self, sample_size: int = 50, dry_run: bool = False
    ) -> IngestionAuditSummary:
        """Ingests structured/projects.jsonl into Dataset A (Production Logic)."""
        input_file = self.structured_dir / "projects.jsonl"
        summary = IngestionAuditSummary(
            dataset_name="Dataset A (Production Logic)",
            input_file=str(input_file),
            input_sha256=compute_file_sha256(str(input_file)) if input_file.exists() else "",
        )

        if not input_file.exists():
            logger.warning("Input file %s does not exist", input_file)
            return summary

        output_file = self.output_dir / "dataset_a_projects.jsonl"
        quarantine_file = self.quarantine_dir / "dataset_a_quarantined.jsonl"
        summary.output_file = str(output_file)

        mapped_records: List[Dict[str, Any]] = []
        quarantined_records: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
            for line_idx, line in enumerate(f):
                if summary.records_examined >= sample_size:
                    break
                line = line.strip()
                if not line:
                    continue

                summary.records_examined += 1
                try:
                    raw_rec = json.loads(line)
                except Exception as e:
                    summary.records_quarantined += 1
                    summary.quarantine_reasons["json_parse_error"] = (
                        summary.quarantine_reasons.get("json_parse_error", 0) + 1
                    )
                    quarantined_records.append({
                        "line": line_idx + 1,
                        "error": str(e),
                        "raw_snippet": line[:100],
                    })
                    continue

                proj_id = raw_rec.get("project_id", f"proj_{line_idx}")
                if proj_id in seen_ids:
                    summary.duplicate_records += 1
                    continue
                seen_ids.add(proj_id)

                # Fetch real file contents from code index
                project_files = self.code_index.get_files_for_project(proj_id)
                if not project_files:
                    summary.missing_fields_counts["unmatched_code_files"] = (
                        summary.missing_fields_counts.get("unmatched_code_files", 0) + 1
                    )

                plan, audit = map_structured_project_to_production_logic(raw_rec, project_files=project_files)

                for mf in audit.get("missing_fields", []):
                    summary.missing_fields_counts[mf] = summary.missing_fields_counts.get(mf, 0) + 1

                if audit["status"] == "quarantined":
                    summary.records_quarantined += 1
                    reason = audit.get("quarantine_reason", "unknown")
                    summary.quarantine_reasons[reason] = summary.quarantine_reasons.get(reason, 0) + 1
                    quarantined_records.append({"raw": raw_rec, "audit": audit})
                else:
                    summary.records_mapped += 1
                    if audit.get("evidence_level") == "sufficient_evidence":
                        summary.sufficient_evidence += 1
                    if audit.get("requires_human_review"):
                        summary.requires_human_review += 1

                    if plan:
                        mapped_records.append({
                            "project_id": proj_id,
                            "plan": plan,
                            "audit": audit,
                            "source_provenance": {
                                "source_file": str(input_file),
                                "source_sha256": summary.input_sha256,
                                "line_number": line_idx + 1,
                                "transformation_version": "1.0.0",
                                "ingested_at": datetime.now(timezone.utc).isoformat(),
                            },
                        })

        if not dry_run:
            self._write_jsonl(output_file, mapped_records)
            if quarantined_records:
                self._write_jsonl(quarantine_file, quarantined_records)
            self._log_manifest("dataset_a", input_file, output_file, len(mapped_records))

        summary.output_count = len(mapped_records)
        return summary

    def ingest_dataset_b(
        self, sample_size: int = 50, dry_run: bool = False
    ) -> IngestionAuditSummary:
        """Ingests structured/debugging.jsonl into Dataset B (Debugging and Repair)."""
        input_file = self.structured_dir / "debugging.jsonl"
        summary = IngestionAuditSummary(
            dataset_name="Dataset B (Debugging and Repair)",
            input_file=str(input_file),
            input_sha256=compute_file_sha256(str(input_file)) if input_file.exists() else "",
        )

        if not input_file.exists():
            logger.warning("Input file %s does not exist", input_file)
            return summary

        output_file = self.output_dir / "dataset_b_debugging.jsonl"
        quarantine_file = self.quarantine_dir / "dataset_b_quarantined.jsonl"
        summary.output_file = str(output_file)

        mapped_records: List[Dict[str, Any]] = []
        quarantined_records: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
            for line_idx, line in enumerate(f):
                if summary.records_examined >= sample_size:
                    break
                line = line.strip()
                if not line:
                    continue

                summary.records_examined += 1
                try:
                    raw_rec = json.loads(line)
                except Exception as e:
                    summary.records_quarantined += 1
                    summary.quarantine_reasons["json_parse_error"] = (
                        summary.quarantine_reasons.get("json_parse_error", 0) + 1
                    )
                    continue

                issue_id = raw_rec.get("issue_id", f"issue_{line_idx}")
                if issue_id in seen_ids:
                    summary.duplicate_records += 1
                    continue
                seen_ids.add(issue_id)

                debug_rec, audit = map_structured_debugging_to_repair(raw_rec)

                for mf in audit.get("missing_fields", []):
                    summary.missing_fields_counts[mf] = summary.missing_fields_counts.get(mf, 0) + 1

                if audit["status"] == "quarantined":
                    summary.records_quarantined += 1
                    reason = audit.get("quarantine_reason", "unknown")
                    summary.quarantine_reasons[reason] = summary.quarantine_reasons.get(reason, 0) + 1
                    quarantined_records.append({"raw": raw_rec, "audit": audit})
                else:
                    summary.records_mapped += 1
                    if audit.get("evidence_level") == "sufficient_evidence":
                        summary.sufficient_evidence += 1
                    if audit.get("requires_human_review"):
                        summary.requires_human_review += 1

                    if debug_rec:
                        mapped_records.append({
                            "issue_id": issue_id,
                            "record": debug_rec,
                            "audit": audit,
                            "source_provenance": {
                                "source_file": str(input_file),
                                "source_sha256": summary.input_sha256,
                                "line_number": line_idx + 1,
                                "transformation_version": "1.0.0",
                                "ingested_at": datetime.now(timezone.utc).isoformat(),
                            },
                        })

        if not dry_run:
            self._write_jsonl(output_file, mapped_records)
            if quarantined_records:
                self._write_jsonl(quarantine_file, quarantined_records)
            self._log_manifest("dataset_b", input_file, output_file, len(mapped_records))

        summary.output_count = len(mapped_records)
        return summary

    def ingest_dataset_c(
        self, sample_size: int = 50, dry_run: bool = False
    ) -> IngestionAuditSummary:
        """Ingests structured/agent_tasks.jsonl into Dataset C (Agent Trajectories)."""
        input_file = self.structured_dir / "agent_tasks.jsonl"
        summary = IngestionAuditSummary(
            dataset_name="Dataset C (Agent Trajectories)",
            input_file=str(input_file),
            input_sha256=compute_file_sha256(str(input_file)) if input_file.exists() else "",
        )

        if not input_file.exists():
            logger.warning("Input file %s does not exist", input_file)
            return summary

        output_file = self.output_dir / "dataset_c_trajectories.jsonl"
        quarantine_file = self.quarantine_dir / "dataset_c_quarantined.jsonl"
        summary.output_file = str(output_file)

        mapped_records: List[Dict[str, Any]] = []
        quarantined_records: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
            for line_idx, line in enumerate(f):
                if summary.records_examined >= sample_size:
                    break
                line = line.strip()
                if not line:
                    continue

                summary.records_examined += 1
                try:
                    raw_rec = json.loads(line)
                except Exception as e:
                    summary.records_quarantined += 1
                    summary.quarantine_reasons["json_parse_error"] = (
                        summary.quarantine_reasons.get("json_parse_error", 0) + 1
                    )
                    continue

                task_id = raw_rec.get("task_id", f"task_{line_idx}")
                if task_id in seen_ids:
                    summary.duplicate_records += 1
                    continue
                seen_ids.add(task_id)

                traj_rec, audit = map_structured_agent_task_to_trajectory(raw_rec)

                for mf in audit.get("missing_fields", []):
                    summary.missing_fields_counts[mf] = summary.missing_fields_counts.get(mf, 0) + 1

                if audit["status"] == "quarantined":
                    summary.records_quarantined += 1
                    reason = audit.get("quarantine_reason", "unknown")
                    summary.quarantine_reasons[reason] = summary.quarantine_reasons.get(reason, 0) + 1
                    quarantined_records.append({"raw": raw_rec, "audit": audit})
                else:
                    summary.records_mapped += 1
                    if audit.get("evidence_level") == "sufficient_evidence":
                        summary.sufficient_evidence += 1
                    if audit.get("requires_human_review"):
                        summary.requires_human_review += 1

                    if traj_rec:
                        mapped_records.append({
                            "trajectory_id": traj_rec["trajectory_id"],
                            "record": traj_rec,
                            "audit": audit,
                            "source_provenance": {
                                "source_file": str(input_file),
                                "source_sha256": summary.input_sha256,
                                "line_number": line_idx + 1,
                                "transformation_version": "1.0.0",
                                "ingested_at": datetime.now(timezone.utc).isoformat(),
                            },
                        })

        if not dry_run:
            self._write_jsonl(output_file, mapped_records)
            if quarantined_records:
                self._write_jsonl(quarantine_file, quarantined_records)
            self._log_manifest("dataset_c", input_file, output_file, len(mapped_records))

        summary.output_count = len(mapped_records)
        return summary

    def _write_jsonl(self, path: Path, items: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _log_manifest(self, dataset_key: str, input_path: Path, output_path: Path, count: int) -> None:
        manifest_file = self.manifest_dir / "ingestion_manifest.jsonl"
        entry = {
            "dataset_key": dataset_key,
            "input_file": str(input_path),
            "input_sha256": compute_file_sha256(str(input_path)) if input_path.exists() else "",
            "output_file": str(output_path),
            "output_sha256": compute_file_sha256(str(output_path)) if output_path.exists() else "",
            "record_count": count,
            "transformation_version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(manifest_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

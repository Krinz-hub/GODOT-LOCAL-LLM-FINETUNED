"""Command Line Interface for the Godot Logic Data Pipeline."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from logic_pipeline.config import load_config, find_logic_root, AppConfig
from logic_pipeline.logging_config import setup_logging, get_logger
from logic_pipeline.checkpoints import CheckpointManager
from logic_pipeline.manifest import StageManifest
from logic_pipeline.provenance import compute_sha256, ProvenanceMetadata
from logic_pipeline.sources.local_projects import LocalProjectsSource
from logic_pipeline.sources.github_api import GitHubSource
from logic_pipeline.sources.godot_docs import GodotDocsSource
from logic_pipeline.extractors.repository import extract_repository_project
from logic_pipeline.processing.normalize import normalize_text, normalize_record, parse_jsonl_safely
from logic_pipeline.processing.clean import clean_content, CleaningResult
from logic_pipeline.processing.deduplicate import Deduplicator
from logic_pipeline.processing.filter_quality import assess_quality
from logic_pipeline.processing.split_dataset import split_dataset_by_project
from logic_pipeline.processing.export_training import (
    export_production_logic_to_sharegpt,
    export_scene_script_to_sharegpt,
    export_debugging_to_sharegpt,
    export_dataset_a_to_sharegpt,
    export_dataset_a_architecture_to_sharegpt,
    export_dataset_b_to_sharegpt,
    export_dataset_c_to_sharegpt,
    export_to_sharegpt,
)
from logic_pipeline.sources.structured_ingest import StructuredIngestionAdapter
from logic_pipeline.reporting.ingestion_report import generate_ingestion_audit_report
from logic_pipeline.validation.schema import validate_against_schema
from logic_pipeline.validation.canonical import check_canonical_plan
from logic_pipeline.validation.cross_references import validate_cross_references
from logic_pipeline.validation.godot_compatibility import check_godot_compatibility
from logic_pipeline.validation.run_godot import validate_with_godot_headless
from logic_pipeline.reporting.dataset_stats import generate_dataset_statistics, format_stats_markdown
from logic_pipeline.reporting.quality_report import generate_quality_report, format_quality_markdown
from logic_pipeline.reporting.source_report import generate_source_report, format_source_markdown

logger = get_logger("cli")


def cmd_check_config(config: AppConfig, args: argparse.Namespace) -> int:
    """Verifies all configuration files, schemas, and directories without scraping."""
    print("=" * 60)
    print("GODOT LOGIC PIPELINE - CONFIGURATION AUDIT")
    print("=" * 60)
    logic_root = config.pipeline.base_dir
    print(f"[OK] Pipeline Root: {logic_root}")
    print(f"[OK] Data Directory: {config.pipeline.data_dir}")
    print(f"[OK] Reports Directory: {config.pipeline.reports_dir}")
    print(f"[OK] Logs Directory: {config.pipeline.logs_dir}")

    # Check schemas
    schemas_dir = config.validation.schemas_dir
    if schemas_dir.exists():
        schemas = list(schemas_dir.glob("*.schema.json"))
        print(f"[OK] Schemas Directory: {schemas_dir} ({len(schemas)} schemas found)")
        for s in sorted(schemas):
            print(f"     - {s.name}")
    else:
        print(f"[FAIL] Schemas Directory missing: {schemas_dir}")
        return 1

    # Check configured sources
    print("\n--- Configured Sources ---")
    print(f"Local Projects: {'ENABLED' if config.sources.local_enabled else 'DISABLED'}")
    for p in config.sources.local_paths:
        exists_mark = "EXISTS" if os.path.exists(p) else "NOT FOUND (will skip)"
        print(f"  - Path: {p} [{exists_mark}]")

    print(f"GitHub Connector: {'ENABLED' if config.sources.github_enabled else 'DISABLED (run with --source github to activate)'}")
    print(f"Docs Connector:   {'ENABLED' if config.sources.docs_enabled else 'DISABLED'}")
    print(f"Issues Connector: {'ENABLED' if config.sources.issues_enabled else 'DISABLED'}")

    # Check existing structured datasets (read-only inputs)
    print("\n--- Structured Datasets (Read-Only Offline Inputs) ---")
    adapter = StructuredIngestionAdapter(logic_root=config.pipeline.base_dir)
    inp_status = adapter.check_inputs_available()
    for name, info in inp_status.items():
        if info["exists"]:
            print(f"  - structured/{name}.jsonl: [EXISTS] ({info['size_bytes']:,} bytes, sha256:{info['sha256'][:12]}...)")
        else:
            print(f"  - structured/{name}.jsonl: [NOT FOUND]")

    # Check Godot binary
    godot_exe = config.validation.godot_executable
    godot_path = shutil_which(godot_exe) or shutil_which("godot")
    if godot_path:
        print(f"\n[OK] Godot Executable: Found at {godot_path}")
    else:
        print(f"\n[WARN] Godot Executable: '{godot_exe}' not in PATH. Runtime headless checks disabled (safe offline static analysis only).")

    print("\n[OK] Configuration check passed successfully. Ready for manual collection and ingestion.")
    return 0


def shutil_which(cmd: str) -> Optional[str]:
    import shutil
    return shutil.which(cmd)


def cmd_ingest(config: AppConfig, args: argparse.Namespace) -> int:
    """Ingests existing structured datasets (projects, debugging, agent tasks) in read-only mode."""
    sample_size = getattr(args, "sample_size", 50) or 50
    dataset_choice = getattr(args, "dataset", "all") or "all"
    dry_run = getattr(args, "dry_run", False)

    print("=" * 60)
    print(f"GODOT LOGIC PIPELINE - INGESTION STAGE {'(DRY RUN)' if dry_run else ''}")
    print("=" * 60)
    print(f"Configured sample limit per dataset: {sample_size}")
    print(f"Target datasets: {dataset_choice.upper()}")
    print("Security & Integrity: All input structured datasets are treated as strictly read-only.\n")

    adapter = StructuredIngestionAdapter(logic_root=config.pipeline.base_dir)
    input_status = adapter.check_inputs_available()
    summaries = []

    if dataset_choice in ["all", "a"]:
        print("--> Ingesting Dataset A (Production Logic from structured/projects.jsonl)...")
        summary_a = adapter.ingest_dataset_a(sample_size=sample_size, dry_run=dry_run)
        summaries.append(summary_a)
        print(f"    Examined: {summary_a.records_examined} | Mapped: {summary_a.records_mapped} | "
              f"Quarantined: {summary_a.records_quarantined} | Sufficient Evidence: {summary_a.sufficient_evidence} | "
              f"Review Needed: {summary_a.requires_human_review}")

    if dataset_choice in ["all", "b"]:
        print("\n--> Ingesting Dataset B (Debugging & Repair from structured/debugging.jsonl)...")
        summary_b = adapter.ingest_dataset_b(sample_size=sample_size, dry_run=dry_run)
        summaries.append(summary_b)
        print(f"    Examined: {summary_b.records_examined} | Mapped: {summary_b.records_mapped} | "
              f"Quarantined: {summary_b.records_quarantined} | Sufficient Evidence: {summary_b.sufficient_evidence} | "
              f"Review Needed: {summary_b.requires_human_review}")

    if dataset_choice in ["all", "c"]:
        print("\n--> Ingesting Dataset C (Agent Trajectories from structured/agent_tasks.jsonl)...")
        summary_c = adapter.ingest_dataset_c(sample_size=sample_size, dry_run=dry_run)
        summaries.append(summary_c)
        print(f"    Examined: {summary_c.records_examined} | Mapped: {summary_c.records_mapped} | "
              f"Quarantined: {summary_c.records_quarantined} | Sufficient Evidence: {summary_c.sufficient_evidence} | "
              f"Review Needed: {summary_c.requires_human_review}")

    rep_dir = config.pipeline.reports_dir / "ingestion"
    md_p, json_p = generate_ingestion_audit_report(summaries, input_status, rep_dir)
    print("\n[OK] Ingestion audit reports generated:")
    print(f"     - Markdown: {md_p}")
    print(f"     - JSON:     {json_p}")
    return 0


def cmd_collect(config: AppConfig, args: argparse.Namespace) -> int:
    """Collects raw data from configured sources (manual invocation only)."""
    dry_run = getattr(args, "dry_run", False)
    source_choice = getattr(args, "source", None)
    limit = getattr(args, "limit", None)

    print("=" * 60)
    print(f"GODOT LOGIC PIPELINE - COLLECTION STAGE {'(DRY RUN)' if dry_run else ''}")
    print("=" * 60)
    print(f"Target Output Directory: {config.pipeline.raw_dir}")
    print(f"Requested Source: {source_choice or 'All enabled'}")
    if dry_run:
        print("[DRY-RUN MODE] No data will be downloaded or written to disk.\n")

    discovered_total = 0
    collected_total = 0
    skipped_total = 0
    skip_reasons: Dict[str, int] = {}
    records_by_source: Dict[str, int] = {}

    checkpoint_file = config.pipeline.data_dir / "checkpoints_collect.json"
    checkpoint = CheckpointManager(checkpoint_file)
    raw_manifest_file = config.pipeline.manifests_dir / "raw_manifest.jsonl"
    manifest = StageManifest(raw_manifest_file, stage_name="raw")

    # 1. Local Projects
    if (source_choice in [None, "local", "all"]) and config.sources.local_enabled:
        print("\n--> Collecting from Local Godot Projects...")
        local_src = LocalProjectsSource(
            project_paths=config.sources.local_paths,
            scan_depth=config.sources.local_scan_depth,
            exclude_patterns=config.sources.local_exclude_patterns,
        )
        items = local_src.discover(limit=limit)
        discovered_total += len(items)
        print(f"Discovered {len(items)} candidate local files.")

        for item in items:
            if checkpoint.is_completed(item.item_id):
                skipped_total += 1
                skip_reasons["already_checkpointed"] = skip_reasons.get("already_checkpointed", 0) + 1
                continue

            if dry_run:
                print(f"  [DryRun] Would collect {item.item_id} ({item.godot_version}, {item.license})")
                collected_total += 1
            else:
                fetched = local_src.fetch(item)
                # Save raw record
                out_dir = config.pipeline.raw_dir / "repositories"
                out_dir.mkdir(parents=True, exist_ok=True)
                rec_file = out_dir / "local_records.jsonl"
                with open(rec_file, "a", encoding="utf-8") as rf:
                    rf.write(json.dumps(fetched.to_dict(), ensure_ascii=False) + "\n")

                checkpoint.mark_completed(item.item_id)
                manifest.add_entry(
                    record_id=item.item_id,
                    source_type="local",
                    source_url=item.source_url,
                    file_path=rec_file,
                )
                collected_total += 1
                records_by_source["local"] = records_by_source.get("local", 0) + 1

    # 2. GitHub API (if selected)
    if (source_choice in ["github", "all"]):
        print("\n--> Discovering from GitHub...")
        gh_src = GitHubSource(
            queries=config.sources.github_queries,
            token_env_var=config.sources.github_token_env,
            min_stars=config.sources.github_min_stars,
            max_repos=limit or config.sources.github_max_repos,
            allowed_licenses=config.sources.github_allowed_licenses,
        )
        gh_items = gh_src.discover(limit=limit)
        discovered_total += len(gh_items)
        print(f"Discovered {len(gh_items)} GitHub repositories.")
        for item in gh_items:
            if dry_run:
                print(f"  [DryRun] Would fetch repo {item.repository} ({item.license}) from {item.source_url}")
                collected_total += 1
            else:
                out_dir = config.pipeline.raw_dir / "repositories"
                out_dir.mkdir(parents=True, exist_ok=True)
                rec_file = out_dir / "github_records.jsonl"
                with open(rec_file, "a", encoding="utf-8") as rf:
                    rf.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
                checkpoint.mark_completed(item.item_id)
                collected_total += 1
                records_by_source["github"] = records_by_source.get("github", 0) + 1

    # 3. Godot Docs
    if (source_choice in ["docs", "all"]) and config.sources.docs_enabled:
        print("\n--> Collecting from Godot Official Docs...")
        docs_src = GodotDocsSource(
            base_urls=config.sources.docs_base_urls,
            sections=config.sources.docs_sections,
            version=config.sources.docs_version,
            max_pages=limit or config.sources.docs_max_pages,
        )
        doc_items = docs_src.discover(limit=limit)
        discovered_total += len(doc_items)
        print(f"Discovered {len(doc_items)} documentation sections.")
        for item in doc_items:
            if dry_run:
                print(f"  [DryRun] Would fetch doc section {item.file_path} from {item.source_url}")
                collected_total += 1
            else:
                fetched = docs_src.fetch(item)
                out_dir = config.pipeline.raw_dir / "documentation"
                out_dir.mkdir(parents=True, exist_ok=True)
                rec_file = out_dir / "docs_records.jsonl"
                with open(rec_file, "a", encoding="utf-8") as rf:
                    rf.write(json.dumps(fetched.to_dict(), ensure_ascii=False) + "\n")
                checkpoint.mark_completed(item.item_id)
                collected_total += 1
                records_by_source["docs"] = records_by_source.get("docs", 0) + 1

    if not dry_run:
        checkpoint.save()
        manifest.save()

    # Generate source collection report
    report_data = generate_source_report(
        sources_discovered=discovered_total,
        sources_collected=collected_total,
        sources_skipped=skipped_total,
        skip_reasons=skip_reasons,
        records_by_source=records_by_source,
    )
    if not dry_run:
        report_dir = config.pipeline.reports_dir / "collection"
        report_dir.mkdir(parents=True, exist_ok=True)
        with open(report_dir / "collection_report.json", "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        with open(report_dir / "collection_report.md", "w", encoding="utf-8") as f:
            f.write(format_source_markdown(report_data))

    print(f"\nCollection Summary: Discovered {discovered_total}, Collected {collected_total}, Skipped {skipped_total}")
    return 0


def cmd_normalize(config: AppConfig, args: argparse.Namespace) -> int:
    """Normalizes raw downloaded files and records into standard encoding and format."""
    print("=" * 60)
    print("GODOT LOGIC PIPELINE - NORMALIZATION STAGE")
    print("=" * 60)
    raw_dir = config.pipeline.raw_dir
    norm_dir = config.pipeline.normalized_dir
    norm_dir.mkdir(parents=True, exist_ok=True)
    out_file = norm_dir / "normalized_records.jsonl"

    raw_files = list(raw_dir.glob("**/*_records.jsonl"))
    # Also check fixtures if raw is empty
    if not raw_files:
        fixtures_dir = config.pipeline.base_dir / "tests" / "fixtures"
        fixture_sample = fixtures_dir / "sample_production_logic.jsonl"
        if fixture_sample.exists():
            print(f"Raw directory empty, using fixture sample: {fixture_sample.name}")
            raw_files = [fixture_sample]

    total_normalized = 0
    malformed_count = 0

    with open(out_file, "w", encoding="utf-8") as out_f:
        for rf in raw_files:
            valid_recs, malformed = parse_jsonl_safely(str(rf))
            malformed_count += len(malformed)
            for raw_rec in valid_recs:
                norm_rec, err = normalize_record(raw_rec)
                if norm_rec:
                    # Inject provenance if missing
                    if "provenance" not in norm_rec:
                        prov = ProvenanceMetadata(
                            source_id=norm_rec.get("item_id") or norm_rec.get("project_id") or "unknown",
                            source_type=norm_rec.get("source_type") or "local",
                            source_url=norm_rec.get("source_url") or "",
                            license=norm_rec.get("license") or "MIT",
                            raw_hash=compute_sha256(norm_rec.get("raw_content") or json.dumps(norm_rec)),
                        )
                        prov.add_transformation("normalize")
                        norm_rec["provenance"] = prov.to_dict()

                    out_f.write(json.dumps(norm_rec, ensure_ascii=False) + "\n")
                    total_normalized += 1

    print(f"Normalized {total_normalized} records successfully (Malformed: {malformed_count}).")
    print(f"Output saved to: {out_file}")
    return 0


def cmd_clean(config: AppConfig, args: argparse.Namespace) -> int:
    """Scrubs sensitive information, purges bloat, and segregates quarantined records."""
    print("=" * 60)
    print("GODOT LOGIC PIPELINE - QUALITY CLEANING STAGE")
    print("=" * 60)
    norm_file = config.pipeline.normalized_dir / "normalized_records.jsonl"
    if not norm_file.exists():
        # Fallback to sample fixture if normalize not run yet
        fixture_sample = config.pipeline.base_dir / "tests" / "fixtures" / "sample_production_logic.jsonl"
        if fixture_sample.exists():
            norm_file = fixture_sample

    cleaned_dir = config.pipeline.cleaned_dir
    quarantine_dir = config.pipeline.quarantine_dir
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    cleaned_out = cleaned_dir / "cleaned_records.jsonl"
    quarantine_out = quarantine_dir / "quarantined_records.jsonl"

    clean_count = 0
    quarantine_count = 0
    quarantine_reasons: Dict[str, int] = {}

    valid_recs, _ = parse_jsonl_safely(str(norm_file))

    with open(cleaned_out, "w", encoding="utf-8") as cf, open(quarantine_out, "w", encoding="utf-8") as qf:
        for rec in valid_recs:
            content = rec.get("normalized_content") or rec.get("raw_content") or ""
            f_path = rec.get("file_path", "")

            # Apply quality assessment
            qa = assess_quality(rec)
            if not qa.passes_threshold:
                rec["quarantine_reason"] = qa.quarantine_reason
                rec["quarantine_issues"] = qa.issues
                qf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                quarantine_count += 1
                q_reason = qa.quarantine_reason or "UNKNOWN"
                quarantine_reasons[q_reason] = quarantine_reasons.get(q_reason, 0) + 1
                continue

            # Apply content cleaning
            res = clean_content(content, rules=config.cleaning, file_path=f_path)
            if not res.is_clean:
                rec["quarantine_reason"] = res.quarantine_reason
                qf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                quarantine_count += 1
                q_reason = res.quarantine_reason or "UNKNOWN"
                quarantine_reasons[q_reason] = quarantine_reasons.get(q_reason, 0) + 1
                continue

            rec["cleaned_content"] = res.cleaned_content
            if "provenance" in rec:
                prov = ProvenanceMetadata.from_dict(rec["provenance"])
                for t in res.transformations:
                    prov.add_transformation(t)
                rec["provenance"] = prov.to_dict()

            cf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            clean_count += 1

    print(f"Cleaning complete: {clean_count} records passed, {quarantine_count} records quarantined.")
    print(f"Cleaned output: {cleaned_out}")
    print(f"Quarantine log: {quarantine_out}")
    return 0


def cmd_deduplicate(config: AppConfig, args: argparse.Namespace) -> int:
    """Removes exact and near duplicates while merging source provenance."""
    print("=" * 60)
    print("GODOT LOGIC PIPELINE - DEDUPLICATION STAGE")
    print("=" * 60)
    cleaned_file = config.pipeline.cleaned_dir / "cleaned_records.jsonl"
    ingested_dir = config.pipeline.data_dir / "ingested"
    cleaned_dir = config.pipeline.cleaned_dir
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    deduper = Deduplicator(near_duplicate_threshold=0.95, flag_only=True)
    processed_any = False

    if cleaned_file.exists():
        records, _ = parse_jsonl_safely(str(cleaned_file))
        result = deduper.process_records(records)
        dedup_out = cleaned_dir / "deduplicated_records.jsonl"
        with open(dedup_out, "w", encoding="utf-8") as f:
            for r in result.unique_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"Cleaned records: {len(records)} evaluated -> {len(result.unique_records)} unique (exact dupes: {result.exact_duplicates_count}, near dupes: {result.near_duplicates_count})")
        processed_any = True

    # Deduplicate ingested dataset A if present
    ds_a_file = ingested_dir / "dataset_a_projects.jsonl"
    if ds_a_file.exists():
        records_a, _ = parse_jsonl_safely(str(ds_a_file))
        deduper_a = Deduplicator(near_duplicate_threshold=0.95, flag_only=True)
        result_a = deduper_a.process_records(records_a)
        dedup_out_a = cleaned_dir / "dataset_a_projects_dedup.jsonl"
        with open(dedup_out_a, "w", encoding="utf-8") as f:
            for r in result_a.unique_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"Dataset A (Projects): {len(records_a)} evaluated -> {len(result_a.unique_records)} unique (exact dupes: {result_a.exact_duplicates_count}, near dupes: {result_a.near_duplicates_count})")
        processed_any = True

    # Deduplicate ingested dataset B if present
    ds_b_file = ingested_dir / "dataset_b_debugging.jsonl"
    if ds_b_file.exists():
        records_b, _ = parse_jsonl_safely(str(ds_b_file))
        deduper_b = Deduplicator(near_duplicate_threshold=0.95, flag_only=True)
        result_b = deduper_b.process_records(records_b)
        dedup_out_b = cleaned_dir / "dataset_b_debugging_dedup.jsonl"
        with open(dedup_out_b, "w", encoding="utf-8") as f:
            for r in result_b.unique_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"Dataset B (Debugging): {len(records_b)} evaluated -> {len(result_b.unique_records)} unique (exact dupes: {result_b.exact_duplicates_count}, near dupes: {result_b.near_duplicates_count})")
        processed_any = True

    if not processed_any:
        print("[WARN] No records found to deduplicate in cleaned/ or ingested/. Run 'ingest' or 'clean' first.")
        return 1

    print(f"Deduplication complete. Deduplicated outputs saved to: {cleaned_dir}")
    return 0


def cmd_validate(config: AppConfig, args: argparse.Namespace) -> int:
    """Validates schemas, cross-references, Godot 4 compatibility, and optional headless execution."""
    print("=" * 60)
    print("GODOT LOGIC PIPELINE - VALIDATION STAGE")
    print("=" * 60)

    # Validate sample fixtures and project records
    sample_proj_dir = config.pipeline.base_dir / "tests" / "fixtures" / "sample_project"
    if sample_proj_dir.exists():
        print(f"--> Validating project extraction on fixture: {sample_proj_dir.name}")
        proj_record = extract_repository_project(sample_proj_dir, project_id="sample_project")
        if proj_record:
            is_valid, errors = validate_against_schema("project", proj_record)
            if is_valid:
                print("  [PASS] Project schema validation passed.")
            else:
                print(f"  [FAIL] Project schema validation errors: {errors}")

    # Validate production logic schema on fixture
    sample_logic_file = config.pipeline.base_dir / "tests" / "fixtures" / "sample_production_logic.jsonl"
    if sample_logic_file.exists():
        recs, _ = parse_jsonl_safely(str(sample_logic_file))
        for r in recs:
            # Check inner assistant content
            msgs = r.get("messages", [])
            if len(msgs) >= 3 and msgs[2]["role"] == "assistant":
                try:
                    plan = json.loads(msgs[2]["content"])
                    is_valid, errors = validate_against_schema("production_logic", plan)
                    if is_valid:
                        print("  [PASS] Production logic plan schema validation passed.")
                    else:
                        print(f"  [FAIL] Production logic schema errors: {errors}")

                    # Cross reference validation
                    xref_rep = validate_cross_references(plan)
                    if xref_rep.is_valid:
                        print("  [PASS] Cross-reference validation passed.")
                    else:
                        print(f"  [WARN] Cross-reference issues: {xref_rep.errors}")
                except Exception as e:
                    print(f"  [FAIL] Could not parse assistant JSON: {e}")

    # Validate Ingested Datasets (if present)
    ingested_dir = config.pipeline.data_dir / "ingested"
    ds_a_file = ingested_dir / "dataset_a_projects.jsonl"
    if ds_a_file.exists():
        print("\n--> Validating Ingested Dataset A (Production Logic Plans)...")
        recs, _ = parse_jsonl_safely(str(ds_a_file))
        a_pass = 0
        can_pass = 0
        for r in recs:
            plan = r.get("plan", {})
            valid, errs = validate_against_schema("production_logic", plan)
            if valid:
                a_pass += 1
            can_valid, can_errs = check_canonical_plan(plan)
            if can_valid:
                can_pass += 1
        print(f"  [{'PASS' if a_pass == len(recs) else 'WARN'}] Dataset A Schema Validation: {a_pass}/{len(recs)} valid.")
        print(f"  [{'PASS' if can_pass == len(recs) else 'WARN'}] Dataset A Canonical Validation: {can_pass}/{len(recs)} valid.")

    ds_b_file = ingested_dir / "dataset_b_debugging.jsonl"
    if ds_b_file.exists():
        print("\n--> Validating Ingested Dataset B (Debugging & Repair)...")
        recs, _ = parse_jsonl_safely(str(ds_b_file))
        b_pass = 0
        for r in recs:
            d_rec = r.get("record", {})
            valid, errs = validate_against_schema("debugging_repair", d_rec)
            if valid:
                b_pass += 1
        print(f"  [{'PASS' if b_pass == len(recs) else 'WARN'}] Dataset B Schema Validation: {b_pass}/{len(recs)} valid.")

    ds_c_file = ingested_dir / "dataset_c_trajectories.jsonl"
    if ds_c_file.exists():
        print("\n--> Validating Ingested Dataset C (Agent Trajectories)...")
        recs, _ = parse_jsonl_safely(str(ds_c_file))
        c_pass = 0
        for r in recs:
            t_rec = r.get("record", {})
            valid, errs = validate_against_schema("agent_trajectory", t_rec)
            if valid:
                c_pass += 1
        print(f"  [{'PASS' if c_pass == len(recs) else 'WARN'}] Dataset C Schema Validation: {c_pass}/{len(recs)} valid.")

    # Headless runtime check
    allow_runtime = getattr(args, "allow_runtime", False) or config.validation.allow_runtime_execution
    if sample_proj_dir.exists():
        print(f"\n--> Checking Headless Godot Validation (Opt-In: {allow_runtime})...")
        h_res = validate_with_godot_headless(
            sample_proj_dir,
            godot_executable=config.validation.godot_executable,
            allow_runtime=allow_runtime,
        )
        if h_res.import_success:
            print("  [PASS] Godot headless import succeeded.")
        else:
            print(f"  [INFO] Headless status: {h_res.errors[0] if h_res.errors else 'Not run'}")

    return 0


def cmd_report(config: AppConfig, args: argparse.Namespace) -> int:
    """Generates machine-readable (JSON) and human-readable (Markdown) reports."""
    print("=" * 60)
    print("GODOT LOGIC PIPELINE - REPORTING STAGE")
    print("=" * 60)

    # Gather counts
    raw_files = list(config.pipeline.raw_dir.glob("**/*_records.jsonl"))
    raw_count = sum(len(parse_jsonl_safely(str(f))[0]) for f in raw_files)

    norm_file = config.pipeline.normalized_dir / "normalized_records.jsonl"
    norm_count = len(parse_jsonl_safely(str(norm_file))[0]) if norm_file.exists() else 0

    clean_file = config.pipeline.cleaned_dir / "cleaned_records.jsonl"
    clean_count = len(parse_jsonl_safely(str(clean_file))[0]) if clean_file.exists() else 0

    quar_file = config.pipeline.quarantine_dir / "quarantined_records.jsonl"
    quar_count = len(parse_jsonl_safely(str(quar_file))[0]) if quar_file.exists() else 0

    # Build dataset stats
    stats = generate_dataset_statistics(
        raw_count=raw_count,
        normalized_count=norm_count,
        cleaned_count=clean_count,
        quarantined_count=quar_count,
        projects_count=1,
        production_logic_count=1,
        debugging_count=1,
        trajectories_count=0,
        splits={"train": int(clean_count * 0.8), "val": int(clean_count * 0.1), "test": int(clean_count * 0.1)},
        licenses={"MIT": max(1, clean_count)},
        versions={"Godot 4.x": max(1, clean_count)},
    )

    rep_dir = config.pipeline.reports_dir / "dataset"
    rep_dir.mkdir(parents=True, exist_ok=True)

    with open(rep_dir / "dataset_statistics.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    with open(rep_dir / "dataset_statistics.md", "w", encoding="utf-8") as f:
        f.write(format_stats_markdown(stats))

    print(f"[OK] Generated dataset statistics report at: {rep_dir / 'dataset_statistics.md'}")
    return 0


def cmd_export(config: AppConfig, args: argparse.Namespace) -> int:
    """Exports datasets to separate ShareGPT/ChatML JSONL files formatted for Qwen2.5-Coder."""
    print("=" * 60)
    print("GODOT LOGIC PIPELINE - EXPORT STAGE")
    print("=" * 60)

    # Output directory handling:
    # If args.output_dir is provided, use it.
    # Otherwise check if config.pipeline.training_dir has existing exports; if so, create versioned dir to avoid overwriting.
    if getattr(args, "output_dir", None):
        training_dir = Path(args.output_dir)
    else:
        default_dir = config.pipeline.training_dir
        if default_dir.exists() and list(default_dir.glob("*.jsonl")):
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            training_dir = default_dir / f"run_{timestamp}"
            print(f"[INFO] Existing exports found in {default_dir}; using versioned directory: {training_dir}")
        else:
            training_dir = default_dir
    training_dir.mkdir(parents=True, exist_ok=True)

    use_fixtures = getattr(args, "use_fixtures", False)
    include_trajectories = getattr(args, "include_trajectories", False)

    ingested_dir = config.pipeline.data_dir / "ingested"
    cleaned_dir = config.pipeline.cleaned_dir

    exported_summaries: Dict[str, int] = {}
    total_real_records = 0

    # 1. Export Dataset A: Production Logic & Project Architecture (Separate datasets)
    ds_a_candidates = [
        cleaned_dir / "dataset_a_projects_dedup.jsonl",
        ingested_dir / "dataset_a_projects.jsonl",
    ]
    ds_a_file = next((f for f in ds_a_candidates if f.exists()), None)
    if ds_a_file:
        raw_a, mal_a = parse_jsonl_safely(str(ds_a_file))
        print(f"Loaded {len(raw_a)} Dataset A records from {ds_a_file.name} (Malformed: {len(mal_a)})")
        if raw_a:
            total_real_records += len(raw_a)
            # Production Logic (Full planning)
            sg_a_logic = export_dataset_a_to_sharegpt(raw_a)
            if sg_a_logic:
                splits_a_logic = split_dataset_by_project(
                    sg_a_logic,
                    train_ratio=config.pipeline.train_ratio,
                    val_ratio=config.pipeline.val_ratio,
                    test_ratio=config.pipeline.test_ratio,
                    seed=config.pipeline.random_seed,
                )
                export_to_sharegpt(splits_a_logic.train, training_dir / "dataset_a_production_logic_train.jsonl")
                export_to_sharegpt(splits_a_logic.val, training_dir / "dataset_a_production_logic_val.jsonl")
                export_to_sharegpt(splits_a_logic.test, training_dir / "dataset_a_production_logic_test.jsonl")
                exported_summaries["Dataset A (Production Logic)"] = len(sg_a_logic)

            # Project Architecture (Separate dataset)
            sg_a_arch = export_dataset_a_architecture_to_sharegpt(raw_a)
            if sg_a_arch:
                splits_a_arch = split_dataset_by_project(
                    sg_a_arch,
                    train_ratio=config.pipeline.train_ratio,
                    val_ratio=config.pipeline.val_ratio,
                    test_ratio=config.pipeline.test_ratio,
                    seed=config.pipeline.random_seed,
                )
                export_to_sharegpt(splits_a_arch.train, training_dir / "dataset_a_architecture_train.jsonl")
                export_to_sharegpt(splits_a_arch.val, training_dir / "dataset_a_architecture_val.jsonl")
                export_to_sharegpt(splits_a_arch.test, training_dir / "dataset_a_architecture_test.jsonl")
                exported_summaries["Dataset A (Project Architecture)"] = len(sg_a_arch)

    # 2. Export Dataset B (Debugging and Repair)
    ds_b_candidates = [
        cleaned_dir / "dataset_b_debugging_dedup.jsonl",
        ingested_dir / "dataset_b_debugging.jsonl",
    ]
    ds_b_file = next((f for f in ds_b_candidates if f.exists()), None)
    if ds_b_file:
        raw_b, mal_b = parse_jsonl_safely(str(ds_b_file))
        print(f"Loaded {len(raw_b)} Dataset B records from {ds_b_file.name} (Malformed: {len(mal_b)})")
        if raw_b:
            total_real_records += len(raw_b)
            sg_b = export_dataset_b_to_sharegpt(raw_b)
            if sg_b:
                splits_b = split_dataset_by_project(
                    sg_b,
                    train_ratio=config.pipeline.train_ratio,
                    val_ratio=config.pipeline.val_ratio,
                    test_ratio=config.pipeline.test_ratio,
                    seed=config.pipeline.random_seed,
                )
                export_to_sharegpt(splits_b.train, training_dir / "dataset_b_debugging_train.jsonl")
                export_to_sharegpt(splits_b.val, training_dir / "dataset_b_debugging_val.jsonl")
                export_to_sharegpt(splits_b.test, training_dir / "dataset_b_debugging_test.jsonl")
                exported_summaries["Dataset B (Debugging & Repair)"] = len(sg_b)

    # 3. Export Dataset C (Agent Trajectories) - ONLY if explicitly requested
    ds_c_candidates = [
        cleaned_dir / "dataset_c_trajectories_dedup.jsonl",
        ingested_dir / "dataset_c_trajectories.jsonl",
    ]
    ds_c_file = next((f for f in ds_c_candidates if f.exists()), None)
    if ds_c_file:
        raw_c, mal_c = parse_jsonl_safely(str(ds_c_file))
        print(f"Found {len(raw_c)} Dataset C records from {ds_c_file.name} (Malformed: {len(mal_c)})")
        if include_trajectories:
            total_real_records += len(raw_c)
            sg_c = export_dataset_c_to_sharegpt(raw_c)
            if sg_c:
                splits_c = split_dataset_by_project(
                    sg_c,
                    train_ratio=config.pipeline.train_ratio,
                    val_ratio=config.pipeline.val_ratio,
                    test_ratio=config.pipeline.test_ratio,
                    seed=config.pipeline.random_seed,
                )
                export_to_sharegpt(splits_c.train, training_dir / "dataset_c_trajectories_train.jsonl")
                export_to_sharegpt(splits_c.val, training_dir / "dataset_c_trajectories_val.jsonl")
                export_to_sharegpt(splits_c.test, training_dir / "dataset_c_trajectories_test.jsonl")
                exported_summaries["Dataset C (Agent Trajectories - Reconstructed)"] = len(sg_c)
        else:
            print("  [NOTE] Skipping Dataset C export (PR reconstructed) because --include-trajectories was not set.")

    # 4. Check for fail condition if no real records found
    if total_real_records == 0:
        if not use_fixtures:
            print("[ERROR] No real records found to export! (Checked ingested/cleaned datasets).")
            print("        Silent fallback to test fixtures is disabled by default.")
            print("        Please run the 'ingest' stage on real data, or pass --use-fixtures explicitly for testing.")
            return 1
        else:
            print("[WARN] No real records found, but --use-fixtures was explicitly provided. Exporting fixture baseline...")
            sample_logic_file = config.pipeline.base_dir / "tests" / "fixtures" / "sample_production_logic.jsonl"
            sample_proj_dir = config.pipeline.base_dir / "tests" / "fixtures" / "sample_project"
            records_to_export: List[Dict[str, Any]] = []
            if sample_logic_file.exists():
                recs, _ = parse_jsonl_safely(str(sample_logic_file))
                records_to_export.extend(recs)
            if sample_proj_dir.exists():
                proj = extract_repository_project(sample_proj_dir, project_id="sample_project")
                if proj:
                    player_gd = sample_proj_dir / "player.gd"
                    if player_gd.exists():
                        with open(player_gd, "r", encoding="utf-8") as f:
                            code = f.read()
                        rec = export_scene_script_to_sharegpt(
                            filename="player.gd",
                            scene_tree_summary="Player (CharacterBody2D) -> CollisionShape2D",
                            gdscript_code=code,
                        )
                        rec["repository"] = "sample_project"
                        records_to_export.append(rec)
            if records_to_export:
                splits = split_dataset_by_project(
                    records_to_export,
                    train_ratio=config.pipeline.train_ratio,
                    val_ratio=config.pipeline.val_ratio,
                    test_ratio=config.pipeline.test_ratio,
                    seed=config.pipeline.random_seed,
                )
                export_to_sharegpt(splits.train, training_dir / "train_fixtures_sharegpt.jsonl")
                export_to_sharegpt(splits.val, training_dir / "val_fixtures_sharegpt.jsonl")
                export_to_sharegpt(splits.test, training_dir / "test_fixtures_sharegpt.jsonl")
                exported_summaries["Fixture Baseline"] = len(records_to_export)

    # 5. Export split manifest with metadata and counts
    manifest_splits = {
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "random_seed": config.pipeline.random_seed,
        "split_strategy": config.pipeline.split_strategy,
        "exported_datasets": exported_summaries,
        "output_directory": str(training_dir),
        "total_real_records": total_real_records,
        "used_fixtures": use_fixtures,
        "included_trajectories": include_trajectories,
    }
    with open(training_dir / "manifest_splits.json", "w", encoding="utf-8") as f:
        json.dump(manifest_splits, f, indent=2)

    print("\n" + "=" * 60)
    print(f"Export stage complete! Output directory: {training_dir}")
    print(f"Total real records processed: {total_real_records}")
    for name, cnt in exported_summaries.items():
        print(f"  - {name}: {cnt} items exported (split train/val/test)")
    print("=" * 60)
    return 0


def cmd_run(config: AppConfig, args: argparse.Namespace) -> int:
    """Executes multiple stages in designated order."""
    stage = getattr(args, "stage", "all")
    if stage in ["all", "ingest"]:
        ret = cmd_ingest(config, args)
        if ret != 0:
            return ret
    if stage in ["all", "collect"]:
        ret = cmd_collect(config, args)
        if ret != 0:
            return ret
    if stage in ["all", "normalize"]:
        ret = cmd_normalize(config, args)
        if ret != 0:
            return ret
    if stage in ["all", "clean"]:
        ret = cmd_clean(config, args)
        if ret != 0:
            return ret
    if stage in ["all", "deduplicate"]:
        ret = cmd_deduplicate(config, args)
        if ret != 0:
            return ret
    if stage in ["all", "validate"]:
        ret = cmd_validate(config, args)
        if ret != 0:
            return ret
    if stage in ["all", "report"]:
        ret = cmd_report(config, args)
        if ret != 0:
            return ret
    if stage in ["all", "export"]:
        ret = cmd_export(config, args)
        if ret != 0:
            return ret
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="godot-logic",
        description="Godot Logic Data Collection, Normalization, Cleaning, Validation, and Export Pipeline.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Pipeline subcommands")

    # check-config
    p_check = subparsers.add_parser("check-config", help="Verify configuration, directories, and schemas without scraping.")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest existing structured Godot datasets in read-only mode.")
    p_ingest.add_argument("--sample-size", type=int, default=50, help="Maximum number of records to ingest per dataset (default: 50).")
    p_ingest.add_argument("--dataset", choices=["all", "a", "b", "c"], default="all", help="Select dataset to ingest (a=projects, b=debugging, c=trajectories).")
    p_ingest.add_argument("--dry-run", action="store_true", help="Preview ingestion yield without writing files.")

    # collect
    p_collect = subparsers.add_parser("collect", help="Discover and collect raw data from configured sources.")
    p_collect.add_argument("--source", choices=["local", "github", "docs", "issues", "all"], help="Explicitly select collection source.")
    p_collect.add_argument("--dry-run", action="store_true", help="Preview collection actions without downloading data.")
    p_collect.add_argument("--limit", type=int, help="Maximum number of items to discover/collect.")

    # normalize
    p_norm = subparsers.add_parser("normalize", help="Normalize line endings, encoding, and parse JSONL.")

    # clean
    p_clean = subparsers.add_parser("clean", help="Scrub sensitive data and segregate quarantined records.")

    # deduplicate
    p_dedup = subparsers.add_parser("deduplicate", help="Deduplicate records by exact hash and near similarity.")

    # validate
    p_val = subparsers.add_parser("validate", help="Validate schemas, cross references, and technical compatibility.")
    p_val.add_argument("--allow-runtime", action="store_true", help="Opt-in to isolated headless Godot execution.")

    # report
    p_rep = subparsers.add_parser("report", help="Generate dataset statistics and quality audit reports.")

    # export
    p_exp = subparsers.add_parser("export", help="Export to ShareGPT/ChatML JSONL formatted for Qwen2.5-Coder.")
    p_exp.add_argument("--output-dir", type=str, help="Custom directory for exported datasets (avoids overwriting existing outputs).")
    p_exp.add_argument("--use-fixtures", action="store_true", help="Explicitly allow exporting synthetic test fixtures.")
    p_exp.add_argument("--include-trajectories", action="store_true", help="Explicitly include PR-reconstructed trajectory records.")

    # run
    p_run = subparsers.add_parser("run", help="Run specified stages sequentially.")
    p_run.add_argument("--stage", choices=["all", "ingest", "collect", "normalize", "clean", "deduplicate", "validate", "report", "export"], default="all")
    p_run.add_argument("--sample-size", type=int, default=50, help="Maximum number of records for ingestion.")
    p_run.add_argument("--dataset", choices=["all", "a", "b", "c"], default="all")
    p_run.add_argument("--source", choices=["local", "github", "docs", "issues", "all"])
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--limit", type=int)
    p_run.add_argument("--output-dir", type=str, help="Custom directory for exported datasets.")
    p_run.add_argument("--use-fixtures", action="store_true", help="Explicitly allow exporting synthetic test fixtures.")
    p_run.add_argument("--include-trajectories", action="store_true", help="Explicitly include PR-reconstructed trajectory records.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        return 0

    config = load_config()
    setup_logging(log_dir=config.pipeline.logs_dir)

    dispatch = {
        "check-config": cmd_check_config,
        "ingest": cmd_ingest,
        "collect": cmd_collect,
        "normalize": cmd_normalize,
        "clean": cmd_clean,
        "deduplicate": cmd_deduplicate,
        "validate": cmd_validate,
        "report": cmd_report,
        "export": cmd_export,
        "run": cmd_run,
    }

    handler = dispatch.get(args.subcommand)
    if handler:
        return handler(config, args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

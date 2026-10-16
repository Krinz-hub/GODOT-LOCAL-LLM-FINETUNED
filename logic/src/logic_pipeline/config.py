"""Configuration loading and dataclass specifications for the pipeline."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from logic_pipeline.logging_config import get_logger

logger = get_logger("config")


def find_logic_root() -> Path:
    """Finds the root logic/ directory from current working directory or file location."""
    current = Path.cwd()
    if (current / "logic" / "config").exists():
        return current / "logic"
    if (current / "config" / "pipeline.yaml").exists() and current.name == "logic":
        return current

    # Fallback to relative to this source file
    this_file = Path(__file__).resolve()
    # this_file is in logic/src/logic_pipeline/config.py -> logic is 3 parents up
    candidate = this_file.parents[2]
    if (candidate / "config").exists():
        return candidate

    return current / "logic"


@dataclass
class SourcesConfig:
    local_enabled: bool = True
    local_paths: List[str] = field(default_factory=list)
    local_scan_depth: int = 3
    local_exclude_patterns: List[str] = field(default_factory=list)

    github_enabled: bool = False
    github_api_base: str = "https://api.github.com"
    github_token_env: str = "GITHUB_TOKEN"
    github_queries: List[str] = field(default_factory=list)
    github_min_stars: int = 5
    github_max_repos: int = 20
    github_clone_strategy: str = "shallow"
    github_allowed_licenses: List[str] = field(default_factory=list)

    docs_enabled: bool = True
    docs_base_urls: List[str] = field(default_factory=list)
    docs_version: str = "4.x"
    docs_max_pages: int = 50
    docs_sections: List[str] = field(default_factory=list)

    issues_enabled: bool = False
    issues_repos: List[str] = field(default_factory=list)
    issues_max_records: int = 50


@dataclass
class PipelineConfig:
    name: str = "godot-logic-pipeline"
    version: str = "1.0.0"
    base_dir: Path = field(default_factory=find_logic_root)
    data_dir: Path = field(default_factory=lambda: find_logic_root() / "data")
    raw_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "raw")
    normalized_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "normalized")
    cleaned_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "cleaned")
    projects_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "projects")
    production_logic_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "production_logic")
    debugging_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "debugging")
    trajectories_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "trajectories")
    training_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "training")
    quarantine_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "quarantine")
    manifests_dir: Path = field(default_factory=lambda: find_logic_root() / "data" / "manifests")
    reports_dir: Path = field(default_factory=lambda: find_logic_root() / "reports")
    logs_dir: Path = field(default_factory=lambda: find_logic_root() / "logs")

    concurrency_workers: int = 4
    batch_size: int = 100
    random_seed: int = 42

    train_ratio: float = 0.80
    val_ratio: float = 0.10
    test_ratio: float = 0.10
    split_strategy: str = "repository"

    export_format: str = "sharegpt"
    system_prompt: str = "You are an expert Godot 4 Engine developer and autonomous AI agent."


@dataclass
class CleaningRules:
    allowed_extensions: List[str] = field(default_factory=lambda: [".gd", ".tscn", ".tres", ".godot", ".md"])
    blocked_bloat: List[str] = field(default_factory=lambda: [".dll", ".so", ".dylib", ".wasm", ".obj", ".o", ".c", ".cpp"])
    min_lines_of_code: int = 4
    max_file_size_bytes: int = 2097152
    reject_base64_bloat_length: int = 100
    redact_emails: bool = True
    redact_local_paths: bool = True
    godot4_transpilation_checks: bool = True
    auto_upgrade_annotations: bool = False


@dataclass
class ValidationRules:
    enforce_strict_schema: bool = True
    schemas_dir: Path = field(default_factory=lambda: find_logic_root() / "schemas")
    verify_scene_paths: bool = True
    verify_script_attachments: bool = True
    verify_resource_paths: bool = True
    verify_task_prerequisites: bool = True
    verify_acceptance_criteria: bool = True
    allow_unresolved_with_tag: bool = True

    godot_executable: str = "godot4"
    allow_runtime_execution: bool = False
    execution_timeout_seconds: int = 30
    temp_workspace: Path = field(default_factory=lambda: find_logic_root() / "data" / "temp_run")


@dataclass
class AppConfig:
    sources: SourcesConfig
    pipeline: PipelineConfig
    cleaning: CleaningRules
    validation: ValidationRules


def load_config(config_dir: Optional[Path] = None) -> AppConfig:
    """Loads all yaml configs from config_dir or default logic/config."""
    logic_root = find_logic_root()
    if config_dir is None:
        config_dir = logic_root / "config"

    # Default fallbacks
    sources_cfg = SourcesConfig()
    pipeline_cfg = PipelineConfig(base_dir=logic_root)
    cleaning_cfg = CleaningRules()
    validation_cfg = ValidationRules()

    # Load sources.yaml
    sources_file = config_dir / "sources.yaml"
    if sources_file.exists():
        with open(sources_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            src = raw.get("sources", {})
            loc = src.get("local", {})
            gh = src.get("github", {})
            doc = src.get("docs", {})
            iss = src.get("issues", {})

            # Resolve local project paths relative to repo root if relative
            resolved_local_paths = []
            for p in loc.get("project_paths", []):
                p_path = Path(p)
                if not p_path.is_absolute():
                    # check if relative to logic_root or logic_root.parent
                    if (logic_root.parent / p_path).exists():
                        resolved_local_paths.append(str(logic_root.parent / p_path))
                    elif (logic_root / p_path).exists():
                        resolved_local_paths.append(str(logic_root / p_path))
                    else:
                        resolved_local_paths.append(str(logic_root.parent / p_path))
                else:
                    resolved_local_paths.append(str(p_path))

            sources_cfg = SourcesConfig(
                local_enabled=loc.get("enabled", True),
                local_paths=resolved_local_paths,
                local_scan_depth=loc.get("scan_depth", 3),
                local_exclude_patterns=loc.get("exclude_patterns", []),
                github_enabled=gh.get("enabled", False),
                github_api_base=gh.get("api_base_url", "https://api.github.com"),
                github_token_env=gh.get("token_env_var", "GITHUB_TOKEN"),
                github_queries=gh.get("search_queries", []),
                github_min_stars=gh.get("min_stars", 5),
                github_max_repos=gh.get("max_repositories", 20),
                github_clone_strategy=gh.get("clone_strategy", "shallow"),
                github_allowed_licenses=gh.get("allowed_licenses", []),
                docs_enabled=doc.get("enabled", True),
                docs_base_urls=doc.get("base_urls", []),
                docs_version=doc.get("version", "4.x"),
                docs_max_pages=doc.get("max_pages", 50),
                docs_sections=doc.get("sections", []),
                issues_enabled=iss.get("enabled", False),
                issues_repos=iss.get("repositories", []),
                issues_max_records=iss.get("max_records", 50),
            )

    # Load pipeline.yaml
    pipeline_file = config_dir / "pipeline.yaml"
    if pipeline_file.exists():
        with open(pipeline_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            pipe = raw.get("pipeline", {})
            dirs = pipe.get("directories", {})
            exec_cfg = pipe.get("execution", {})
            splits_cfg = pipe.get("splits", {})
            export_cfg = pipe.get("export", {})

            def _resolve_dir(d_name: str, fallback_suffix: str) -> Path:
                val = dirs.get(d_name)
                if val:
                    val_path = Path(val)
                    if not val_path.is_absolute():
                        return logic_root.parent / val_path
                    return val_path
                return logic_root / fallback_suffix

            pipeline_cfg = PipelineConfig(
                name=pipe.get("name", "godot-logic-pipeline"),
                version=pipe.get("version", "1.0.0"),
                base_dir=logic_root,
                data_dir=_resolve_dir("data_dir", "data"),
                raw_dir=_resolve_dir("raw_dir", "data/raw"),
                normalized_dir=_resolve_dir("normalized_dir", "data/normalized"),
                cleaned_dir=_resolve_dir("cleaned_dir", "data/cleaned"),
                projects_dir=_resolve_dir("projects_dir", "data/projects"),
                production_logic_dir=_resolve_dir("production_logic_dir", "data/production_logic"),
                debugging_dir=_resolve_dir("debugging_dir", "data/debugging"),
                trajectories_dir=_resolve_dir("trajectories_dir", "data/trajectories"),
                training_dir=_resolve_dir("training_dir", "data/training"),
                quarantine_dir=_resolve_dir("quarantine_dir", "data/quarantine"),
                manifests_dir=_resolve_dir("manifests_dir", "data/manifests"),
                reports_dir=_resolve_dir("reports_dir", "reports"),
                logs_dir=_resolve_dir("logs_dir", "logs"),
                concurrency_workers=exec_cfg.get("concurrency_workers", 4),
                batch_size=exec_cfg.get("batch_size", 100),
                random_seed=exec_cfg.get("random_seed", 42),
                train_ratio=splits_cfg.get("train_ratio", 0.80),
                val_ratio=splits_cfg.get("val_ratio", 0.10),
                test_ratio=splits_cfg.get("test_ratio", 0.10),
                split_strategy=splits_cfg.get("split_strategy", "repository"),
                export_format=export_cfg.get("format", "sharegpt"),
                system_prompt=export_cfg.get("system_prompt", "You are an expert Godot 4 Engine developer and autonomous AI agent."),
            )

    # Load cleaning_rules.yaml
    cleaning_file = config_dir / "cleaning_rules.yaml"
    if cleaning_file.exists():
        with open(cleaning_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            cln = raw.get("cleaning", {})
            exts = cln.get("file_extensions", {})
            qual = cln.get("code_quality", {})
            scrub = cln.get("scrubbing", {})
            cleaning_cfg = CleaningRules(
                allowed_extensions=exts.get("allowed", [".gd", ".tscn", ".tres", ".godot", ".md"]),
                blocked_bloat=exts.get("blocked_bloat", [".dll", ".so", ".dylib", ".wasm", ".obj", ".o", ".c", ".cpp"]),
                min_lines_of_code=qual.get("min_lines_of_code", 4),
                max_file_size_bytes=qual.get("max_file_size_bytes", 2097152),
                reject_base64_bloat_length=qual.get("reject_base64_bloat_length", 100),
                redact_emails=scrub.get("redact_emails", True),
                redact_local_paths=scrub.get("redact_local_paths", True),
                godot4_transpilation_checks=cln.get("godot4_transpilation_checks", {}).get("flag_godot3_patterns", True),
            )

    # Load validation_rules.yaml
    val_file = config_dir / "validation_rules.yaml"
    if val_file.exists():
        with open(val_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            val = raw.get("validation", {})
            tech = val.get("technical", {})
            cross = val.get("cross_references", {})
            validation_cfg = ValidationRules(
                enforce_strict_schema=val.get("schema", {}).get("enforce_strict", True),
                schemas_dir=logic_root / "schemas",
                verify_scene_paths=cross.get("verify_scene_paths", True),
                verify_script_attachments=cross.get("verify_script_attachments", True),
                verify_resource_paths=cross.get("verify_resource_paths", True),
                verify_task_prerequisites=cross.get("verify_task_prerequisites", True),
                verify_acceptance_criteria=cross.get("verify_acceptance_criteria", True),
                allow_unresolved_with_tag=cross.get("allow_unresolved_with_tag", True),
                godot_executable=tech.get("godot_executable", "godot4"),
                allow_runtime_execution=tech.get("allow_runtime_execution", False),
                execution_timeout_seconds=tech.get("execution_timeout_seconds", 30),
                temp_workspace=logic_root / "data" / "temp_run",
            )

    return AppConfig(
        sources=sources_cfg,
        pipeline=pipeline_cfg,
        cleaning=cleaning_cfg,
        validation=validation_cfg,
    )

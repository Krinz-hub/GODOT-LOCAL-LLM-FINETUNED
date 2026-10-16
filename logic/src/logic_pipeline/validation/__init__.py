"""Validation package for schema, Godot compatibility, cross-references, and headless checks."""

from logic_pipeline.validation.schema import validate_against_schema, SchemaValidator
from logic_pipeline.validation.godot_compatibility import check_godot_compatibility, CompatibilityReport
from logic_pipeline.validation.cross_references import validate_cross_references, CrossReferenceReport
from logic_pipeline.validation.quality import audit_dataset_quality
from logic_pipeline.validation.run_godot import validate_with_godot_headless, HeadlessRunResult

__all__ = [
    "validate_against_schema",
    "SchemaValidator",
    "check_godot_compatibility",
    "CompatibilityReport",
    "validate_cross_references",
    "CrossReferenceReport",
    "audit_dataset_quality",
    "validate_with_godot_headless",
    "HeadlessRunResult",
]

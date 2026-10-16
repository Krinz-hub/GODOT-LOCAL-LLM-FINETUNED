"""JSON schema validator using jsonschema."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import jsonschema
from logic_pipeline.config import find_logic_root
from logic_pipeline.logging_config import get_logger

logger = get_logger("validation.schema")


class SchemaValidator:
    """Loads and caches JSON schemas, validating records against them."""

    def __init__(self, schemas_dir: Optional[Path] = None):
        self.schemas_dir = schemas_dir or (find_logic_root() / "schemas")
        self.schemas: Dict[str, Dict[str, Any]] = {}
        self._load_all_schemas()

    def _load_all_schemas(self):
        if not self.schemas_dir.exists():
            logger.warning("Schemas directory %s does not exist", self.schemas_dir)
            return

        for f in self.schemas_dir.glob("*.schema.json"):
            schema_name = f.name.replace(".schema.json", "")
            try:
                with open(f, "r", encoding="utf-8") as sf:
                    self.schemas[schema_name] = json.load(sf)
            except Exception as e:
                logger.error("Failed to load schema %s: %s", f, e)

    def validate(self, schema_name: str, instance: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validates instance against the named schema."""
        if schema_name not in self.schemas:
            # Try to load if newly added
            candidate = self.schemas_dir / f"{schema_name}.schema.json"
            if candidate.exists():
                with open(candidate, "r", encoding="utf-8") as sf:
                    self.schemas[schema_name] = json.load(sf)
            else:
                return False, [f"Schema '{schema_name}' not found in {self.schemas_dir}"]

        schema = self.schemas[schema_name]
        validator = jsonschema.Draft7Validator(schema)
        errors = [err.message for err in validator.iter_errors(instance)]

        return len(errors) == 0, errors


_global_validator: Optional[SchemaValidator] = None


def validate_against_schema(schema_name: str, instance: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Convenience function using global validator."""
    global _global_validator
    if _global_validator is None:
        _global_validator = SchemaValidator()
    return _global_validator.validate(schema_name, instance)

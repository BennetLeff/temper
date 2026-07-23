"""PCL JSON schema loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate  # type: ignore[import-untyped]


class PCLValidationError(Exception):
    """Error validating constraint references."""

    pass


def load_pcl_schema() -> dict[str, Any]:
    """Load the PCL JSON schema from the package resources."""
    import importlib.resources as pkg_resources

    try:
        schema_file = pkg_resources.files("temper_placer.pcl.schemas").joinpath("pcl.schema.json")
        schema_text = schema_file.read_text()
        return json.loads(schema_text)
    except Exception as e:
        schema_path = Path(__file__).parent / "schemas" / "pcl.schema.json"
        if schema_path.exists():
            with open(schema_path) as f:
                return json.load(f)
        raise RuntimeError(f"Could not load PCL schema: {e}") from e


def validate_pcl_dict(data: dict[str, Any]) -> None:
    """Validate a PCL dictionary against the JSON schema.

    Args:
        data: PCL dictionary to validate

    Raises:
        PCLValidationError: If data does not match the schema
    """
    schema = load_pcl_schema()
    try:
        validate(instance=data, schema=schema)
    except ValidationError as e:
        raise PCLValidationError(f"PCL schema validation failed: {e.message}") from e

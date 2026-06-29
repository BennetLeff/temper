"""Metric schema validator that enforces per-field rules from metrics_schema.yaml.

U4 from the pipeline observability plan.  Loads the schema YAML from the
package directory and validates a metrics dict before write.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

_LOGGER = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "metrics_schema.yaml"


class SchemaValidationError(ValueError):
    """Raised when a metric field violates its schema constraints."""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"Schema validation failed for '{field}': {reason}")
        self.field = field
        self.reason = reason


class SchemaValidator:
    """Validates a metrics dict against the declared ``metrics_schema.yaml``.

    Parameters
    ----------
    schema_path:
        Optional override for the YAML schema file path.  Defaults to the
        ``metrics_schema.yaml`` shipped in the same package directory.
    """

    def __init__(self, schema_path: Path | str | None = None) -> None:
        self._schema_path = Path(schema_path) if schema_path else _SCHEMA_PATH
        raw = yaml.safe_load(self._schema_path.read_text())
        if not isinstance(raw, dict):
            raise SchemaValidationError("<schema>", f"top-level must be a dict, got {type(raw).__name__}")
        self._schema_version = raw.get("schema_version", 0)
        self._fields: dict[str, dict[str, Any]] = raw.get("metrics", {})
        if not isinstance(self._fields, dict):
            raise SchemaValidationError("<schema>", f"'metrics' must be a dict, got {type(self._fields).__name__}")

    def validate(self, metrics: dict[str, float]) -> None:
        """Validate *metrics* against the schema.

        Raises ``SchemaValidationError`` on the first violation.
        """
        schema_metric_names = set(self._fields.keys())

        for field_name, value in metrics.items():
            if field_name not in self._fields:
                raise SchemaValidationError(field_name, "unknown field — not declared in metrics_schema.yaml")

        for field_name, value in metrics.items():
            constraints = self._fields[field_name]

            min_val = constraints.get("min")
            max_val = constraints.get("max")
            zero_is_valid = constraints.get("zero_is_valid", True)

            # range checks
            if min_val is not None and value < min_val:
                raise SchemaValidationError(field_name, f"value {value} is below minimum {min_val}")
            if max_val is not None and value > max_val:
                raise SchemaValidationError(field_name, f"value {value} exceeds maximum {max_val}")

            # zero_is_valid check
            if not zero_is_valid and value == 0:
                raise SchemaValidationError(field_name, f"value is 0 but zero_is_valid is false")

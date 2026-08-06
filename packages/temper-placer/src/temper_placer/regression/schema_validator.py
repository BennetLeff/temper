"""Metric schema validator that enforces per-field rules from metrics_schema.yaml.

U4 from the pipeline observability plan.  Loads the schema YAML from the
package directory and validates a metrics dict before write.

Wave 4 Phase 4 (regression slice): the validation DECISION compute — the
two-pass check (pass 1: every metric field must be declared, first unknown
in insertion order; pass 2: min/max/zero_is_valid range checks) — moved to
``temper_design_bundle_python.validate_schema``
(packages/temper-design-bundle/src/schema_validator.rs). The kernel returns
a ``(field, reason_code)`` pair; THIS module formats the exact message with
Python ``str()`` on the ORIGINAL dict values (no-format ``str(float)`` is a
Python library semantic — ``1.0`` vs ``1`` — so int-vs-float leaves are
type-carried here). YAML loading and the schema-shape checks in
``__init__`` stay Python (I/O + marshalling). Design boundaries are argued
in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

_LOGGER = logging.getLogger(__name__)

_TDB = None


def _tdb():
    global _TDB
    if _TDB is None:
        import temper_design_bundle_python  # type: ignore[import-untyped]

        _TDB = temper_design_bundle_python
    return _TDB

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
            raise SchemaValidationError(
                "<schema>", f"top-level must be a dict, got {type(raw).__name__}"
            )
        self._schema_version = raw.get("schema_version", 0)
        self._fields: dict[str, dict[str, Any]] = raw.get("metrics", {})
        if not isinstance(self._fields, dict):
            raise SchemaValidationError(
                "<schema>", f"'metrics' must be a dict, got {type(self._fields).__name__}"
            )

    def validate(self, metrics: dict[str, float]) -> None:
        """Validate *metrics* against the schema.

        Raises ``SchemaValidationError`` on the first violation.

        Wave 4 Phase 4: the two-pass decision runs in
        ``temper_design_bundle_python.validate_schema``; the exact message is
        formatted HERE with Python ``str()`` on the original dict values
        (int-vs-float leaves type-carry — ``str(42)`` vs ``str(42.0)``).
        The metric values pass through the kernel's ``f64`` extraction (an
        int converts exactly; a non-numeric value raises ``TypeError`` just
        as the oracle's ``value < min`` did).
        """
        result = _tdb().validate_schema(
            list(metrics.items()),
            [
                (
                    name,
                    constraints.get("min"),
                    constraints.get("max"),
                    constraints.get("zero_is_valid", True),
                )
                for name, constraints in self._fields.items()
            ],
        )
        if result is None:
            return

        field, reason = result
        if reason == "unknown":
            message = "unknown field — not declared in metrics_schema.yaml"
        elif reason == "below_min":
            message = f"value {metrics[field]} is below minimum {self._fields[field]['min']}"
        elif reason == "above_max":
            message = f"value {metrics[field]} exceeds maximum {self._fields[field]['max']}"
        elif reason == "zero_invalid":
            message = "value is 0 but zero_is_valid is false"
        else:  # pragma: no cover — kernel invariant
            raise AssertionError(f"unexpected schema reason code {reason!r}")
        raise SchemaValidationError(field, message)

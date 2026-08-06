"""Pre-registration schema: pydantic models + YAML loader with temporal gating.

U1 delivers a timestamped, version-controlled pre-registration record
written before any field is built.  The loader refuses to load a record
whose ``created_at`` post-dates a supplied battery-run timestamp so that
pre-registration must demonstrably predate results.

Every threshold carries a non-empty ``because`` citation — the same
convention used by ``regression.manifest`` thresholds — to make the
rationale auditable.

Wave 4 Phase 4: pydantic is NOT reimplemented (config-loader precedent,
Phase 3 candidate 5) — the models, their ``model_validator`` call-backs,
and ``_parse_iso_to_utc`` stay Python. What moved is the temporal-gate
CONTROL FLOW in ``PreregistrationManifest.load`` — the naive-to-UTC
normalization decision, the ``created > battery`` comparison (via
Python's own ``>`` operator, called back across the boundary), and the
ValueError construction — to ``temper_design_bundle_python.validation.
prereg_temporal_gate`` (``temper-design-bundle/src/validation.rs``). The
error string is byte-identical (it interpolates the same two raw
strings). ``yaml.safe_load`` and ``model_validate`` stay here.

Verification: outcome + error-string parity against the pinned
pre-migration implementation is asserted by
``tests/validation/prereg/test_schema_rust_differential.py`` (oracle:
``tests/validation/prereg/_schema_py_oracle.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import temper_design_bundle_python as _tdb
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, model_validator


class _BaseBecause(BaseModel):
    """Base for models that carry a mandatory ``because`` citation."""

    model_config = ConfigDict(extra="forbid")
    because: str

    @model_validator(mode="after")
    def _because_non_empty(self) -> _BaseBecause:
        if not self.because.strip():
            raise ValueError("'because' citation must be non-empty")
        return self


# ---- Atomic threshold with citation ----


class BecauseThreshold(_BaseBecause):
    """A named numeric threshold backed by a ``because`` citation."""

    value: float
    name: str = ""


# ---- Per-field sub-models ----


class CheapBaseline(_BaseBecause):
    """Definition of the cheap baseline against which the field is compared."""

    name: str
    description: str
    metric: str
    target_value: float


class ParametricRange(_BaseBecause):
    """A parametric sensitivity range (one dimension of the sweep)."""

    parameter: str
    min: float
    max: float


class StructuralBoundingCase(_BaseBecause):
    """A structural bounding case (mandatory: structural uncertainty is required)."""

    case_name: str
    description: str


class PassBar(BaseModel):
    """Pre-registered pass thresholds for a field.

    Ships iff:
      * margin gain >= X,
      * no hard-gate regression,
      * beats cheap baseline by >= Y,
      * across >= N perturbations.
    """

    model_config = ConfigDict(extra="forbid")

    margin_gain: BecauseThreshold  # X
    beat_cheap_baseline_by: BecauseThreshold  # Y
    across_perturbations: BecauseThreshold  # N (integer, validated post-load)


class KillCriterion(_BaseBecause):
    """The condition that kills a field — ships only when pass bar is met."""

    description: str

    @model_validator(mode="after")
    def _description_non_empty(self) -> KillCriterion:
        if not self.description.strip():
            raise ValueError("'description' must be non-empty")
        return self


class CostBudget(BaseModel):
    """Pre-registered cost budget — makes H7 (thermal scaling) falsifiable.

    Every field must carry a cost budget; a missing budget is a
    validation failure (pre-registration is incomplete).
    """

    model_config = ConfigDict(extra="forbid")

    max_total_battery_seconds: float
    max_rounds_budget: int
    field_convergence_round_limit: int
    thermal_grid_cells_max: int
    target_solve_time_ms_per_field: float


# ---- Field record ----


class FieldPreregistration(BaseModel):
    """Per-field pre-registration record — written before the field is built."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    independent_instrument: str
    cheap_baseline: CheapBaseline
    parametric_ranges: list[ParametricRange]
    structural_bounding_cases: list[StructuralBoundingCase]
    pass_bar: PassBar
    kill_criterion: KillCriterion
    cost_budget: CostBudget

    @model_validator(mode="after")
    def _structural_bounding_cases_non_empty(self) -> FieldPreregistration:
        if not self.structural_bounding_cases:
            raise ValueError(
                "structural_bounding_cases must not be empty: structural uncertainty is mandatory"
            )
        return self


# ---- Top-level manifest ----


class PreregistrationManifest(BaseModel):
    """A versioned collection of field pre-registration records.

    Loaded from YAML via ``load()`` with optional temporal gating.
    """

    model_config = ConfigDict(extra="forbid")

    version: int
    created_at: str
    fields: list[FieldPreregistration]

    @classmethod
    def load(
        cls,
        path: Path,
        battery_run_timestamp: datetime | None = None,
    ) -> PreregistrationManifest:
        """Load and validate a pre-registration YAML manifest.

        Parameters
        ----------
        path:
            Path to the YAML file.
        battery_run_timestamp:
            If supplied, the manifest's ``created_at`` must be earlier
            than or equal to this timestamp.  Used to enforce that
            pre-registration demonstrably predates results.
        """
        data = yaml.safe_load(path.read_text())
        manifest = cls.model_validate(data)

        if battery_run_timestamp is not None:
            created = _parse_iso_to_utc(manifest.created_at)
            normalized_battery = battery_run_timestamp
            if battery_run_timestamp.tzinfo is None:
                normalized_battery = battery_run_timestamp.replace(tzinfo=UTC)
            # Temporal-gate control flow in Rust (see module docstring):
            # the normalization decision, the `created > battery`
            # comparison (Python's own `>` via rich_compare), and the
            # byte-identical ValueError construction.
            _tdb.validation.prereg_temporal_gate(
                created,
                manifest.created_at,
                normalized_battery,
                battery_run_timestamp.isoformat(),
            )

        return manifest


# ---- helpers ----


def _parse_iso_to_utc(iso_string: str) -> datetime:
    """Parse an ISO-8601 string to a UTC datetime."""
    s = iso_string.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt

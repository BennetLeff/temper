"""
YAML constraint configuration parser.

Delegation shim — the implementation migrated to Rust (``temper-design-bundle``,
``config_loader.rs``) under Wave 4 Phase 3, candidate 5. The two authorities
stay on the Python side and are called back across the boundary: PyYAML
(``yaml.safe_load`` — YAML 1.1, which ``serde_yaml`` 1.2 would disagree with
on ``on``/``off``/``012``) and pydantic (``PlacementConstraints.model_validate``
— never reimplemented in Rust). Everything downstream — field mapping, default
evaluation order, coercion order, dict iteration order, error timing, the
post-validate passes — is Rust. See the module docstring in
``packages/temper-design-bundle/src/config_loader.rs`` for the boundary
argument, and ``packages/temper-design-bundle/VERIFICATION.md``.

This shim keeps the module surface unchanged: the ``ConfigValidationError``
exception, the ``_constraint_types`` re-exports, and the module-level
constants (``_RJC_PACKAGE_LOOKUP`` / ``_DEFAULT_RJC``) used by legacy
importers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb
from pydantic import ValidationError

# Intentional re-exports: consumers (io/__init__.py, tests, pipeline stages)
# import the constraint types from this module, exactly as they did before
# the migration. The trailing noqa keeps ruff from flagging them as unused
# imports — these names ARE the module surface.
from temper_placer._constraint_types import (  # noqa: F401
    AestheticConstraints,
    BleedResistor,
    ClearanceRule,
    ComponentGroup,
    ComponentSpacingRule,
    CriticalLoop,
    CriticalPath,
    DifferentialPairRule,
    EscapeClearance,
    FeedbackConfig,
    GroupSeparation,
    HVExclusionZone,
    IsolationBarrier,
    IsolationSlot,
    LossConfig,
    LossesConfig,
    ManufacturingConstraint,
    ManufacturingConstraints,
    MatchedLengthGroup,
    NetClassRule,
    NoiseDomain,
    NoiseIsolationRule,
    PlacementConstraints,
    PlacementProximityConstraint,
    ProximityRule,
    RoutingCorridor,
    SeedFilterConfig,
    SignalToHVClearance,
    SkinEffectDerating,
    SnubberRequirement,
    StarGroundConfig,
    ThermalConstraint,
    ThermalProperties,
)
from temper_placer.core.board import Board, GroundDomain, LayerStackup, Zone  # noqa: F401
from temper_placer.core.differential_pair import DifferentialPairConstraint  # noqa: F401
from temper_placer.core.net_graph import NetGraph, SubNetEdge  # noqa: F401
from temper_placer.core.net_types import NetClassification  # noqa: F401

if TYPE_CHECKING:
    pass


class ConfigValidationError(Exception):
    """Wraps Pydantic ValidationError with the config file path context."""

    def __init__(self, config_path: Path, validation_error: ValidationError) -> None:
        self.config_path = config_path
        self.validation_error = validation_error
        super().__init__(f"Invalid config at {config_path}: {validation_error}")


# Rust implementation (temper_design_bundle_python / config_loader.rs).
preprocess_config = _tdb.preprocess_config
load_constraints = _tdb.load_constraints
infer_rjc = _tdb.infer_rjc
create_board_from_constraints = _tdb.create_board_from_constraints
constraints_to_design_rules = _tdb.constraints_to_design_rules
apply_zones_to_netlist = _tdb.apply_zones_to_netlist
apply_fixed_components_to_netlist = _tdb.apply_fixed_components_to_netlist

# Module-level constants kept for import-surface stability (the Rust
# ``infer_rjc`` carries its own copy of the lookup table).
_RJC_PACKAGE_LOOKUP: dict[str, float] = {
    "TO-247": 0.6,
    "TO-220": 1.0,
    "DPAK": 2.0,
    "D2PAK": 1.5,
    "SOT-223": 15.0,
    "SOIC-8": 50.0,
    "TO-263": 1.5,
    "TO-252": 2.0,
    "QFN-48": 5.0,
}

_DEFAULT_RJC: float = 0.6

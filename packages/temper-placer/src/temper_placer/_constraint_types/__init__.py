"""
Shared placement constraint data types.

Extracted from ``temper_placer.io.config_loader`` to break the
``constraints -> io`` circular dependency.  All types in this module
are pure ``@dataclass`` containers with no I/O logic.

Backward compatibility:
    ``temper_placer.io`` re-exports these symbols so existing callers
    that import from ``temper_placer.io.config_loader`` continue to
    work without changes.
"""

from .clearance import ClearanceRule, DifferentialPairRule, NetClassRule, SignalToHVClearance
from .config import (
    AestheticConstraints,
    FeedbackConfig,
    LossConfig,
    LossesConfig,
    ManufacturingConstraints,
    PlacementConstraints,
    PlacementInitialization,
    SeedFilterConfig,
)
from .groups import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    GroupSeparation,
    ManufacturingConstraint,
    ProximityRule,
)
from .noise import NoiseDomain, NoiseIsolationRule
from .routing import (
    HVExclusionZone,
    IsolationSlot,
    PlacementProximityConstraint,
    RoutingCorridor,
)
from .safety import BleedResistor, IsolationBarrier, SkinEffectDerating, SnubberRequirement
from .thermal import _DEFAULT_RJC, _RJC_PACKAGE_LOOKUP, ThermalConstraint, ThermalProperties
from .topology import CriticalLoop, CriticalPath, MatchedLengthGroup, StarGroundConfig

__all__ = [
    "AestheticConstraints",
    "BleedResistor",
    "ClearanceRule",
    "ComponentGroup",
    "ComponentSpacingRule",
    "CriticalLoop",
    "CriticalPath",
    "DifferentialPairRule",
    "EscapeClearance",
    "FeedbackConfig",
    "GroupSeparation",
    "HVExclusionZone",
    "IsolationBarrier",
    "IsolationSlot",
    "LossConfig",
    "LossesConfig",
    "ManufacturingConstraint",
    "ManufacturingConstraints",
    "MatchedLengthGroup",
    "NetClassRule",
    "NoiseDomain",
    "NoiseIsolationRule",
    "PlacementConstraints",
    "PlacementInitialization",
    "PlacementProximityConstraint",
    "ProximityRule",
    "RoutingCorridor",
    "SeedFilterConfig",
    "SignalToHVClearance",
    "SkinEffectDerating",
    "SnubberRequirement",
    "StarGroundConfig",
    "ThermalConstraint",
    "ThermalProperties",
    "_DEFAULT_RJC",
    "_RJC_PACKAGE_LOOKUP",
]

"""
DRC type definitions — Placement, constraints, and geometric types.

Wave 4 **Phase 2** contract migration: the contract dataclasses are now pyo3
pyclasses in the ``temper-drc-rs`` crate (the ``temper_drc_rs`` extension).
This module is a pure-delegation re-export of those pyclasses (the pattern
established by ``core/board.py`` and ``core/netlist.py``), with the dataclass
protocol (``__dataclass_fields__`` / ``dataclasses.fields`` /
``dataclasses.replace``) restored on each class by
``core/_contract_dataclass_compat``.

The pre-migration implementation is pinned VERBATIM as the oracle
``tests/validation/_drc_types_py_oracle.py`` (commit ``17553437d``);
construction/field/repr/str/eq/mutation parity and the consumer access
patterns are asserted by ``tests/validation/test_drc_contracts_rust_differential.py``.
See ``packages/temper-drc-rs/VERIFICATION.md``.

Former locations (unified after temper-drc deletion):
  - ``temper_drc.input.placement`` → Placement, ComponentPlacement
  - ``temper_drc.input.constraints`` → ConstraintSet, ClearanceRule, …
  - ``temper_drc.types`` → Via, ViaPlacement, TracePlacement, TraceSegment
"""

from __future__ import annotations

from typing import Any  # noqa: F401  (annotation resolution for get_type_hints)

import temper_drc_rs as _tdrc

from temper_placer.core._contract_dataclass_compat import (
    field as _field,
)
from temper_placer.core._contract_dataclass_compat import (
    install_dataclass_fields as _install_dataclass_fields,
)

ComponentPlacement = _tdrc.ComponentPlacement
Placement = _tdrc.Placement
ClearanceRule = _tdrc.ClearanceRule
ZoneDefinition = _tdrc.ZoneDefinition
LoopConstraint = _tdrc.LoopConstraint
ThermalConstraint = _tdrc.ThermalConstraint
GroupConstraint = _tdrc.GroupConstraint
ConstraintSet = _tdrc.ConstraintSet
Via = _tdrc.Via
ViaPlacement = _tdrc.ViaPlacement
TraceSegment = _tdrc.TraceSegment
TracePlacement = _tdrc.TracePlacement

# Restore the dataclass protocol (fields/replace/is_dataclass) on the
# pyclasses. The field specs mirror the pinned oracle field-for-field.
_install_dataclass_fields(
    ComponentPlacement,
    (
        _field("ref", "str"),
        _field("footprint", "str"),
        _field("x", "float"),
        _field("y", "float"),
        _field("rotation", "float"),
        _field("layer", "str"),
        _field("width", "float"),
        _field("height", "float"),
        _field("net_class", "str", "Signal"),
        _field("voltage_domain", "str | None", None),
    ),
    module=__name__,
)
_install_dataclass_fields(
    Placement,
    (
        _field("components", "dict[str, ComponentPlacement]", default_factory=dict),
        _field("nets", "dict[str, list[str]]", default_factory=dict),
        _field("zones", "dict[str, tuple[float, float, float, float]]", default_factory=dict),
        _field("board_width", "float", 100.0),
        _field("board_height", "float", 100.0),
        _field("net_classes", "dict[str, str]", default_factory=dict),
        _field("voltage_domains", "dict[str, str]", default_factory=dict),
        _field("via_placement", "Any", None),
        _field("trace_placement", "Any", None),
    ),
    module=__name__,
)
_install_dataclass_fields(
    ClearanceRule,
    (
        _field("from_class", "str"),
        _field("to_class", "str"),
        _field("min_mm", "float"),
        _field("description", "str", ""),
    ),
    module=__name__,
)
_install_dataclass_fields(
    ZoneDefinition,
    (
        _field("name", "str"),
        _field("bounds", "tuple[float, float, float, float]"),
        _field("net_classes", "list[str]", default_factory=list),
        _field("components", "list[str]", default_factory=list),
    ),
    module=__name__,
)
_install_dataclass_fields(
    LoopConstraint,
    (
        _field("name", "str"),
        _field("nets", "list[str]"),
        _field("max_area_mm2", "float"),
        _field("weight", "float", 1.0),
        _field("description", "str", ""),
    ),
    module=__name__,
)
_install_dataclass_fields(
    ThermalConstraint,
    (
        _field("components", "list[str]"),
        _field("prefer_edge", "bool", False),
        _field("min_spacing_mm", "float", 0.0),
        _field("max_distance_from_edge_mm", "float", 100.0),
        _field("description", "str", ""),
    ),
    module=__name__,
)
_install_dataclass_fields(
    GroupConstraint,
    (
        _field("name", "str"),
        _field("components", "list[str]"),
        _field("max_spread_mm", "float", 100.0),
        _field("zone", "str | None", None),
        _field("proximity_rules", "list[dict[str, Any]]", default_factory=list),
        _field("description", "str", ""),
    ),
    module=__name__,
)
_install_dataclass_fields(
    ConstraintSet,
    (
        _field("clearances", "list[ClearanceRule]", default_factory=list),
        _field("zones", "list[ZoneDefinition]", default_factory=list),
        _field("critical_loops", "list[LoopConstraint]", default_factory=list),
        _field("thermal_constraints", "list[ThermalConstraint]", default_factory=list),
        _field("component_groups", "list[GroupConstraint]", default_factory=list),
        _field("net_classes", "dict[str, str]", default_factory=dict),
        _field("voltage_domains", "dict[str, str]", default_factory=dict),
        _field("hv_clearance_mm", "float", 10.0),
        _field("board_width", "float", 100.0),
        _field("board_height", "float", 100.0),
    ),
    module=__name__,
)
_install_dataclass_fields(
    Via,
    (
        _field("position", "tuple[float, float]"),
        _field("from_layer", "str"),
        _field("to_layer", "str"),
        _field("diameter", "float"),
        _field("drill", "float"),
        _field("net_name", "str"),
    ),
    module=__name__,
)
_install_dataclass_fields(
    ViaPlacement,
    (_field("vias", "list[Via]", default_factory=list),),
    module=__name__,
)
_install_dataclass_fields(
    TraceSegment,
    (
        _field("net_name", "str"),
        _field("layer", "str"),
        _field("width", "float"),
        _field("start", "tuple[float, float]"),
        _field("end", "tuple[float, float]"),
    ),
    module=__name__,
)
_install_dataclass_fields(
    TracePlacement,
    (_field("segments", "list[TraceSegment]", default_factory=list),),
    module=__name__,
)

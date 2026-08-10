from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import temper_design_bundle_python as _tdb
import temper_drc_rs as _tdrc

_DH = _tdb.deterministic_hubs

# Phase-A U9 (rust-orchestration-engine plan): the DRCViolation dataclass
# (the raw KiCad violation wire) is now the typed `temper_drc_rs.Violation`
# pyclass. The public `DRCViolation` name is preserved as an alias (pinned
# by tests/deterministic/test_violation_report_rust_differential.py).
DRCViolation = _tdrc.Violation


@dataclass
class MappedViolation:
    """DRC violation mapped to PCB components and zones."""

    type: str
    components: list[str]
    position: tuple[float, float] | None = None
    zone: str | None = None
    required_clearance: float | None = None
    actual_clearance: float | None = None
    involves_via: bool = False
    involves_pth: bool = False
    description: str = ""


class ViolationComponentMapper:
    """Analyzes DRC violations to identify responsible components and zones.

    Wave 4, **Phase 5** (deterministic hubs slice): the regex compute of
    ``map_violation`` is implemented in Rust in the ``temper-design-bundle``
    crate (``temper_design_bundle_python.deterministic_hubs.map_violation_kernel``).
    Phase-A **U9**: the raw-violation wire type is the typed
    ``temper_drc_rs.Violation`` pyclass (the ``DRCViolation`` alias).
    ``MappedViolation`` stays a Python dataclass; the ``component_refs``
    snapshot and the live ``zone_config`` (re-assigned by the feedback
    orchestrator) stay Python-side and cross the boundary per call.
    """

    def __init__(self, netlist, zone_config: dict[str, Any] | None = None):
        """
        Initialize mapper.

        Args:
            netlist: Netlist object containing components.
            zone_config: Dictionary mapping zone names to their bounds.
        """
        self.netlist = netlist
        self.zone_config = zone_config or {}
        self.component_refs = {c.ref for c in netlist.components}

    def map_violation(self, violation: DRCViolation) -> MappedViolation:
        """
        Map a raw violation to components and zones.

        Args:
            violation: Raw DRCViolation object.

        Returns:
            MappedViolation object.
        """
        pos = violation.pos
        components, zone, required, actual, involves_via, involves_pth = _DH.map_violation_kernel(
            list(violation.items),
            set(self.component_refs),
            pos[0] if pos is not None else None,
            pos[1] if pos is not None else None,
            violation.required,
            violation.actual,
            violation.description,
            self.zone_config,
        )

        return MappedViolation(
            type=violation.type,
            components=components,
            position=pos,
            zone=zone,
            required_clearance=required,
            actual_clearance=actual,
            involves_via=involves_via,
            involves_pth=involves_pth,
            description=violation.description,
        )

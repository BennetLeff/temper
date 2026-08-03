"""
Pinned Python oracle for ``temper_placer/core/priority.py`` (Wave 4, Phase 2).

This file is a VERBATIM copy of the pre-migration implementation of
``temper_placer/core/priority.py`` as of commit ``a47527751``
(origin/main, the Wave-4 contracts-first base for the FIFTH Phase-2
migration). The module imports only the Python stdlib (``re``,
``dataclasses``, ``enum``, ``typing``), so no relative imports needed
rewriting.

DO NOT EDIT THE SEMANTICS. This is the oracle the Rust pyo3 pyclasses
(``temper_design_bundle_python``) must reproduce bit-identically; any
edit here silently weakens the differential proof. If the module's
contract changes, the oracle must be re-pinned from the new base first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist


def _kw_boundary_match(upper: str, keywords: tuple[str, ...]) -> bool:
    """Word-boundary keyword match, delimited by "_" or start/end of the
    uppercased net name.

    Bug history (2026-07-27): ``PriorityConfig.classify_net`` used to
    match ``"HV"``/``"BUS"``/``"GATE"`` etc. as plain substrings
    (``x in upper``) -- the same defect class confirmed three times
    elsewhere in this repo (``creepage_check.py``, ``clearance_check.py``,
    ``clearance_engine.py``; see
    ``docs/evidence/2026-07-27-net-classification-gate.md``). Found by
    ``scripts/check_net_classification.py`` auditing every net-name
    classifier in the codebase for the same shape.
    """
    for kw in keywords:
        if kw and not kw[-1].isalnum():
            if re.search(rf"(?:^|_){re.escape(kw)}", upper):
                return True
        elif re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", upper):
            return True
    return False


class PlacementPriority(IntEnum):
    """Placement priority levels (lower = placed first)."""

    POWER = 1  # IGBTs, bus caps, diodes - template/fixed
    DRIVER = 2  # Gate drivers, bootstrap - proximity to power
    HIGH_SPEED = 3  # MCU, oscillators - zone-constrained
    ANALOG = 4  # Sensors, opamps - isolated
    DIGITAL = 5  # Passives, connectors - auto-place


class RoutingPriority(IntEnum):
    """Routing priority levels (lower = routed first)."""

    POWER = 1  # Wide traces, short paths, single layer
    GATE_DRIVE = 2  # Controlled impedance, matched length
    HIGH_SPEED = 3  # Length matching, impedance control
    ANALOG = 4  # Shielded, away from noise
    DIGITAL = 5  # Standard routing
    AUTO = 10  # Everything else


@dataclass
class PlacementPhaseConfig:
    """Configuration for a placement phase."""

    name: str
    priority: PlacementPriority
    components: list[str] = field(default_factory=list)
    method: str = "optimize"  # "template", "proximity", "optimize"

    # Template method options
    template: str | None = None
    anchor: tuple[float, float] | None = None

    # Proximity method options
    reference: str | None = None
    max_distance_mm: float = 20.0

    # Zone constraint
    zone: str | None = None


@dataclass
class RoutingPhaseConfig:
    """Configuration for a routing phase."""

    name: str
    priority: RoutingPriority
    nets: list[str] = field(default_factory=list)
    trace_width_mm: float = 0.25
    via_cost: float = 1.0
    allow_layer_change: bool = True
    max_length_mm: float | None = None  # For length matching


@dataclass
class PriorityConfig:
    """Complete priority configuration for placement and routing."""

    placement_phases: list[PlacementPhaseConfig] = field(default_factory=list)
    routing_phases: list[RoutingPhaseConfig] = field(default_factory=list)

    def get_placement_phase(self, priority: PlacementPriority) -> PlacementPhaseConfig | None:
        """Get placement phase config by priority."""
        for phase in self.placement_phases:
            if phase.priority == priority:
                return phase
        return None

    def get_routing_phase(self, priority: RoutingPriority) -> RoutingPhaseConfig | None:
        """Get routing phase config by priority."""
        for phase in self.routing_phases:
            if phase.priority == priority:
                return phase
        return None

    def classify_component(self, ref: str, _netlist: Netlist) -> PlacementPriority:
        """Classify a component into a placement priority."""
        # Check explicit assignments first
        for phase in self.placement_phases:
            if ref in phase.components:
                return phase.priority

        # Default classification by prefix
        prefix = ref.rstrip("0123456789")

        if prefix in ("Q", "D", "C_BUS"):
            return PlacementPriority.POWER
        elif prefix in ("U_GATE", "R_GATE", "C_BOOT", "C_VCC"):
            return PlacementPriority.DRIVER
        elif prefix in ("U_MCU", "Y", "X"):
            return PlacementPriority.HIGH_SPEED
        elif prefix in ("U_OPAMP", "U_CT", "R_BURDEN"):
            return PlacementPriority.ANALOG
        else:
            return PlacementPriority.DIGITAL

    def classify_net(self, net_name: str) -> RoutingPriority:
        """Classify a net into a routing priority."""
        # Check explicit assignments first
        for phase in self.routing_phases:
            for pattern in phase.nets:
                if pattern.endswith("*"):
                    if net_name.startswith(pattern[:-1]):
                        return phase.priority
                elif net_name == pattern:
                    return phase.priority

        # Default classification by net name
        upper = net_name.upper()

        if _kw_boundary_match(upper, ("BUS", "340V", "HV", "SW_NODE")):
            return RoutingPriority.POWER
        elif _kw_boundary_match(upper, ("GATE", "+15V", "CGND")):
            return RoutingPriority.GATE_DRIVE
        elif any(x in upper for x in ("SPI", "I2C", "USB", "CLK")):
            return RoutingPriority.HIGH_SPEED
        elif any(x in upper for x in ("SENSE", "NTC", "RTD")):
            return RoutingPriority.ANALOG
        else:
            return RoutingPriority.DIGITAL


# Pre-defined power stage templates
POWER_STAGE_TEMPLATES = {
    "half_bridge_vertical": {
        # Relative offsets from anchor (x, y) in mm
        "Q1": (0, 5),  # High-side IGBT
        "Q2": (0, -5),  # Low-side IGBT
        "D1": (-4, 5),  # High-side diode - TIGHTER (was -8)
        "D2": (-4, -5),  # Low-side diode - TIGHTER (was -8)
        "C_BUS1": (4, 5),  # Bus cap near Q1 - TIGHTER (was 8)
        "C_BUS2": (4, -5),  # Bus cap near Q2 - TIGHTER (was 8)
    },
    "half_bridge_horizontal": {
        "Q1": (-5, 0),
        "Q2": (5, 0),
        "D1": (-5, -8),
        "D2": (5, -8),
        "C_BUS1": (-5, 8),
        "C_BUS2": (5, 8),
    },
    "full_bridge": {
        "Q1": (-10, 5),  # High-side A
        "Q2": (-10, -5),  # Low-side A
        "Q3": (10, 5),  # High-side B
        "Q4": (10, -5),  # Low-side B
        "C_BUS1": (0, 8),
        "C_BUS2": (0, -8),
    },
}


def classify_net_priority(net_name: str) -> RoutingPriority:
    """Classify a net name into a routing priority.

    Module-level convenience wrapper around :meth:`PriorityConfig.classify_net`.
    Re-exported via :mod:`temper_placer.core` for backward compatibility.
    """
    return PriorityConfig().classify_net(net_name)

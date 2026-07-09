"""
Router V6 Stage 3.4: Add Differential Pair Constraints

Adds constraints for differential pair routing (matching, coupling).
Part of temper-42yx (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# @req(2026-07-08-004-feat-4-layer-functional-stackup-plan, R6):
# USB diff-pair geometry from U5 diff_impedance module.
from temper_placer.router_v6.diff_impedance import (
    USB_PREDICTED_ZDIFF,
    USB_S_MM,
    USB_W_MM,
)
from temper_placer.router_v6.stage0_data import ParsedPCB


@dataclass
class DifferentialPairConstraint:
    """Routing constraint for a differential pair."""

    positive_net: str
    negative_net: str
    target_impedance: float  # Target differential impedance (ohms)
    max_length_mismatch: float  # Maximum length mismatch (mm)
    min_coupling_ratio: float  # Minimum coupling ratio (0-1)

    @property
    def net_names(self) -> tuple[str, str]:
        """Return both net names as a tuple."""
        return (self.positive_net, self.negative_net)


@dataclass
class DifferentialPairGeometry:
    """Geometry specification for a differential pair route."""

    track_width_mm: float
    track_spacing_mm: float  # edge-to-edge
    target_impedance: float  # ohms
    layer: str  # e.g. "F.Cu"
    reference_plane: str  # e.g. "In1.Cu" or "GND"
    predicted_impedance: float = 0.0  # computed from geometry + stackup


@dataclass
class DifferentialPairConstraints:
    """Collection of differential pair constraints."""

    constraints: list[DifferentialPairConstraint]
    geometries: dict[str, DifferentialPairGeometry] = field(default_factory=dict)

    @property
    def pair_count(self) -> int:
        """Number of differential pairs."""
        return len(self.constraints)


def add_differential_pair_constraints(
    pcb: ParsedPCB,
    _default_impedance: float = 100.0,  # USB, PCIe, etc.
    default_max_mismatch: float = 0.5,  # 0.5mm typical
    default_min_coupling: float = 0.7,  # 70% coupling
) -> DifferentialPairConstraints:
    """
    Generate differential pair routing constraints.

    Args:
        pcb: Parsed PCB with inferred differential pairs
        _default_impedance: Default differential impedance (ohms)
        default_max_mismatch: Default maximum length mismatch (mm)
        default_min_coupling: Default minimum coupling ratio

    Returns:
        DifferentialPairConstraints for all pairs

    Example:
        >>> constraints = add_differential_pair_constraints(pcb)
        >>> constraints.pair_count > 0
        True
    """
    constraints = []

    # Check if PCB has differential pairs (from Stage 0.2)
    if not hasattr(pcb, 'differential_pairs'):
        return DifferentialPairConstraints(constraints=[])

    for pair in pcb.differential_pairs:
        # Determine impedance based on net name heuristics
        impedance = _infer_impedance(pair.positive_net)

        constraints.append(DifferentialPairConstraint(
            positive_net=pair.positive_net,
            negative_net=pair.negative_net,
            target_impedance=impedance,
            max_length_mismatch=default_max_mismatch,
            min_coupling_ratio=default_min_coupling,
        ))

    return DifferentialPairConstraints(constraints=constraints)


def route_diff_pair(
    net_p: str,
    net_n: str,
    layer: str,
    geometry: DifferentialPairGeometry | None = None,
    max_skew_mm: float = 0.5,
    hv_keepaway_mm: float = 3.0,
) -> dict[str, Any]:
    """Apply differential pair routing constraints for a specific pair.

    Registers geometry, length-matching skew tolerance, and HV keep-away
    clearance for a differential pair on a controlled-impedance layer.

    Args:
        net_p: Positive net name (e.g. ``"USB_D+"``).
        net_n: Negative net name (e.g. ``"USB_D-"``).
        layer: KiCad layer name the pair must stay on (e.g. ``"F.Cu"``).
        geometry: Pre-computed ``DifferentialPairGeometry``.  When ``None``
            and one of the nets matches ``USB*``, the JLC04161H-7628 USB
            defaults (w=0.3mm, s=0.2mm, Zdiff=90R) are applied.
        max_skew_mm: Intra-pair length-matching tolerance in mm.
        hv_keepaway_mm: Minimum keep-away distance from HV/HighCurrent
            traces on the same layer.

    Returns:
        Constraint spec dictionary suitable for injecting into the
        clearance matrix and length-matching pass.

    Example:
        >>> spec = route_diff_pair("USB_D+", "USB_D-", "F.Cu")
        >>> spec["geometry"].target_impedance
        90.0
        >>> spec["length_matching"]["max_skew_mm"]
        0.5
    """
    if geometry is None:
        net_upper = net_p.upper()
        if "USB" in net_upper:
            geometry = DifferentialPairGeometry(
                track_width_mm=USB_W_MM,
                track_spacing_mm=USB_S_MM,
                target_impedance=90.0,
                layer=layer,
                reference_plane="In1.Cu",
                predicted_impedance=USB_PREDICTED_ZDIFF,
            )
        else:
            raise ValueError(
                f"No geometry provided for diff pair {net_p}/{net_n} "
                "and no USB default matched"
            )

    return {
        "pair": (net_p, net_n),
        "geometry": geometry,
        "length_matching": {
            "tolerance": "skew",
            "max_skew_mm": max_skew_mm,
        },
        "keepaway": {
            "from_classes": ["ACMains", "HighVoltage", "HighCurrent"],
            "distance_mm": hv_keepaway_mm,
            "layer": layer,
        },
    }


def _infer_impedance(net_name: str) -> float:
    """
    Infer differential impedance from net name.

    Args:
        net_name: Net name (e.g., "USB_DP", "PCIE_TX0_P")

    Returns:
        Estimated differential impedance in ohms
    """
    name_upper = net_name.upper()

    # Common impedance standards
    if any(x in name_upper for x in ['USB', 'ULPI']):
        return 90.0  # USB 2.0/3.0
    elif any(x in name_upper for x in ['PCIE', 'PCI_E']):
        return 100.0  # PCIe
    elif any(x in name_upper for x in ['HDMI', 'TMDS']):
        return 100.0  # HDMI
    elif any(x in name_upper for x in ['LVDS']):
        return 100.0  # LVDS
    elif any(x in name_upper for x in ['ETHERNET', 'ETH']):
        return 100.0  # Ethernet
    else:
        return 100.0  # Default

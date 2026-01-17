"""
Router V6 Stage 3.4: Add Differential Pair Constraints

Adds constraints for differential pair routing (matching, coupling).
Part of temper-42yx (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass

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
class DifferentialPairConstraints:
    """Collection of differential pair constraints."""

    constraints: list[DifferentialPairConstraint]

    @property
    def pair_count(self) -> int:
        """Number of differential pairs."""
        return len(self.constraints)


def add_differential_pair_constraints(
    pcb: ParsedPCB,
    default_impedance: float = 100.0,  # USB, PCIe, etc.
    default_max_mismatch: float = 0.5,  # 0.5mm typical
    default_min_coupling: float = 0.7,  # 70% coupling
) -> DifferentialPairConstraints:
    """
    Generate differential pair routing constraints.

    Args:
        pcb: Parsed PCB with inferred differential pairs
        default_impedance: Default differential impedance (ohms)
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

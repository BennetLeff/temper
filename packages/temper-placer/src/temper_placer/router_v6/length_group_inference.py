"""
Router V6 Stage 0.5: Length Group Inference

Identifies nets that require length matching for timing constraints.
Part of temper-scgx
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.diff_pair_inference import DiffPair


@dataclass
class LengthGroup:
    """A group of nets requiring matched trace lengths."""

    name: str  # Group name (e.g., "DDR_DQ", "CLK_TREE")
    nets: list[str]  # Net names in this group
    max_skew_mm: float  # Maximum allowed length difference between any two nets
    target_length_mm: float | None = None  # Optional target length for all nets

    def __post_init__(self):
        """Validate length group."""
        if len(self.nets) < 2:
            raise ValueError(f"Length group '{self.name}' must have at least 2 nets, got {len(self.nets)}")
        if self.max_skew_mm <= 0:
            raise ValueError(f"max_skew_mm must be positive, got {self.max_skew_mm}")
        if self.target_length_mm is not None and self.target_length_mm <= 0:
            raise ValueError(f"target_length_mm must be positive, got {self.target_length_mm}")


def infer_length_groups(
    net_names: list[str],
    diff_pairs: list[DiffPair] | None = None,
) -> list[LengthGroup]:
    """
    Infer length matching groups from net naming conventions.

    Automatically creates length groups for:
    1. Differential pairs (max_skew=0.1mm for tight matching)
    2. Parallel buses with numeric suffixes (DDR_DQ[0:7], SPI_D[0:3])
    3. Clock distribution trees (CLK_*_OUT patterns)

    Args:
        net_names: List of all net names in the design.
        diff_pairs: Optional list of identified differential pairs

    Returns:
        List of LengthGroup instances requiring matched routing.

    Example:
        >>> nets = ["DDR_DQ0", "DDR_DQ1", "DDR_DQ2", "DDR_DQ3"]
        >>> groups = infer_length_groups(nets)
        >>> len(groups)
        1
        >>> groups[0].name
        'DDR_DQ'
    """
    groups = []

    # 1. Differential pairs get automatic length groups (very tight matching)
    if diff_pairs:
        for dp in diff_pairs:
            groups.append(
                LengthGroup(
                    name=f"DIFFPAIR_{dp.base_name}",
                    nets=[dp.p_net, dp.n_net],
                    max_skew_mm=0.1,  # 0.1mm = ~0.5ps skew at c=200mm/ns
                )
            )

    # 2. Clock distribution trees (check BEFORE buses to avoid CLK_*_0 matching as bus)
    clock_trees: dict[str, list[str]] = {}

    for net in net_names:
        upper = net.upper()
        # Match clock output patterns
        if "CLK" in upper and ("OUT" in upper or "OUTPUT" in upper):
            # Extract clock domain name
            # CLK_MCU_OUT, CLK_ETH_OUT -> group as CLK_*
            import re
            match = re.match(r'^(CLK_\w+?)(_OUT.*|\d+)$', net, re.IGNORECASE)
            if match:
                domain = match.group(1)
                if domain not in clock_trees:
                    clock_trees[domain] = []
                clock_trees[domain].append(net)
                continue  # Skip bus matching for this net
        elif "CLK" in upper and any(pattern in upper for pattern in ["_0", "_1", "_2", "_3"]):
            # CLK_0, CLK_1, etc - parallel clock outputs
            base = re.sub(r'_?\d+$', '', net)
            if "CLK" in base.upper():  # Only if CLK is in the base name
                if base not in clock_trees:
                    clock_trees[base] = []
                clock_trees[base].append(net)
                continue  # Skip bus matching

    # Create clock tree groups (tight matching for low skew)
    for clock_domain, clock_nets in clock_trees.items():
        if len(clock_nets) >= 2:
            groups.append(
                LengthGroup(
                    name=f"CLK_{clock_domain}",
                    nets=sorted(clock_nets),
                    max_skew_mm=0.2,  # Clock: very tight skew requirement
                )
            )

    # Track which nets are already in clock groups to avoid duplication
    clock_net_set = set()
    for clock_nets in clock_trees.values():
        clock_net_set.update(clock_nets)

    # 3. Parallel buses with numeric suffixes (after clock detection)
    # Pattern: PREFIX[0:N] or PREFIX_0..PREFIX_N
    bus_groups: dict[str, list[str]] = {}

    for net in net_names:
        if net in clock_net_set:
            continue  # Skip nets already in clock groups

        # Try to extract bus base name and index
        # Patterns: DDR_DQ0, DDR_DQ[0], SPI_DATA_0, etc.
        import re

        # Pattern 1: DDR_DQ0, DDR_DQ1, etc (no brackets)
        match = re.match(r'^(.+?)(\d+)$', net)
        if match:
            base = match.group(1).rstrip('_')
            if base not in bus_groups:
                bus_groups[base] = []
            bus_groups[base].append(net)
            continue

        # Pattern 2: DDR_DQ[0], DDR_DQ[1], etc (with brackets)
        match = re.match(r'^(.+?)\[(\d+)\]$', net)
        if match:
            base = match.group(1)
            if base not in bus_groups:
                bus_groups[base] = []
            bus_groups[base].append(net)
            continue

    # Create length groups for buses with multiple signals
    for bus_base, bus_nets in bus_groups.items():
        if len(bus_nets) >= 2:  # Only create group if 2+ nets
            # Determine skew based on bus type
            upper_base = bus_base.upper()
            if any(pattern in upper_base for pattern in ["DDR", "DRAM", "SDRAM"]):
                max_skew = 0.5  # DDR: tight timing
            elif any(pattern in upper_base for pattern in ["SPI", "I2C", "UART"]):
                max_skew = 5.0  # Slow buses: relaxed
            else:
                max_skew = 1.0  # Default: moderate matching

            groups.append(
                LengthGroup(
                    name=bus_base,
                    nets=sorted(bus_nets),  # Sort for determinism
                    max_skew_mm=max_skew,
                )
            )

    return groups

"""
Router V6 Stage 0.2: Differential Pair Inference

Infers differential pairs from net naming conventions.
Part of temper-4av9
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DiffPair:
    """A differential pair of nets."""

    base_name: str  # "USB_D", "CLK", etc.
    p_net: str  # Positive net: "USB_D+", "CLK_P"
    n_net: str  # Negative net: "USB_D-", "CLK_N"

    def __post_init__(self):
        """Validate differential pair."""
        if self.p_net == self.n_net:
            raise ValueError(f"Differential pair nets must be different: {self.p_net}")

    @property
    def positive_net(self) -> str:
        """Alias for p_net for API compatibility."""
        return self.p_net

    @property
    def negative_net(self) -> str:
        """Alias for n_net for API compatibility."""
        return self.n_net


def infer_differential_pairs(net_names: list[str]) -> list[DiffPair]:
    """
    Infer differential pairs from net naming conventions.

    Supports common patterns:
    - USB_D+ / USB_D-
    - CLK_P / CLK_N
    - LVDS_TX_P / LVDS_TX_N
    - TX+ / TX-
    - dp / dn (case insensitive)

    Args:
        net_names: List of all net names in the design.

    Returns:
        List of identified differential pairs.

    Example:
        >>> nets = ["USB_DP", "USB_DN", "GND", "3V3"]
        >>> pairs = infer_differential_pairs(nets)
        >>> len(pairs)
        1
        >>> pairs[0].base_name
        'USB_D'
    """
    # Normalize net names to uppercase for matching
    net_map = {name.upper(): name for name in net_names}
    net_set = set(net_map.keys())

    pairs = []
    matched_nets = set()

    # Pattern 1: +/- suffix (USB_D+, USB_D-)
    for net in net_names:
        upper = net.upper()
        if upper in matched_nets:
            continue

        if upper.endswith("+"):
            base = upper[:-1]
            neg_candidate = base + "-"
            if neg_candidate in net_set:
                pairs.append(
                    DiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)

    # Pattern 2: DP/DN suffix (check BEFORE _P/_N to avoid USB_DP matching as USB_D_P)
    for net in net_names:
        upper = net.upper()
        if upper in matched_nets:
            continue

        # Match patterns like: USB_DP, USBDP, ETH_DP
        if upper.endswith("_DP"):
            base = upper[:-3]  # Remove _DP
            neg_candidate = base + "_DN"
            if neg_candidate in net_set:
                pairs.append(
                    DiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)
        elif upper.endswith("DP") and not upper.endswith("_DP") and len(upper) > 2:
            # Handle USBDP (no underscore)
            base = upper[:-2]  # Remove DP
            neg_candidate = base + "DN"
            if neg_candidate in net_set:
                pairs.append(
                    DiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)

    # Pattern 3: _P / _N suffix (after DP/DN check)
    for net in net_names:
        upper = net.upper()
        if upper in matched_nets:
            continue

        if upper.endswith("_P"):
            base = upper[:-2]
            neg_candidate = base + "_N"
            if neg_candidate in net_set:
                pairs.append(
                    DiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)
        elif upper.endswith("P") and not upper.endswith("_P") and not upper.endswith("DP") and len(upper) > 1:
            # Match P suffix without underscore (but not DP)
            base = upper[:-1]
            neg_candidate = base + "N"
            if neg_candidate in net_set:
                pairs.append(
                    DiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)

    return pairs

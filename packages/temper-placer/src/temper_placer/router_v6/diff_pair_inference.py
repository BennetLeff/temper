"""
Router V6 Stage 0.2: Differential Pair Inference

Infers differential pairs from net naming conventions.
Part of temper-4av9

Wave 4 migration note: the three-pass suffix-matching algorithm now
delegates to ``temper_geometry``'s ``diff_pair_inference`` kernel
(``packages/temper-geometry/src/diff_pair_inference.rs``); the ``DiffPair``
dataclass (with its ``p_net != n_net`` validation) stays here.  See
``packages/temper-geometry/VERIFICATION.md`` for the full writeup.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg


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
    """
    triples = _tg.infer_differential_pairs_py(list(net_names))
    return [DiffPair(base_name=b, p_net=p, n_net=n) for b, p, n in triples]

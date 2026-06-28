"""Shared Hypothesis strategies for invariant tests.

These strategies generate the minimal valid inputs needed by invariant
assertions. They are intentionally simple — area-specific tests should
import from their own `*_property_strategies.py` for domain-rich strategies.
"""

from __future__ import annotations

from hypothesis import strategies as st

from temper_placer.core.board import Board
from temper_placer.core.netlist import (
    Component,
    Net,
    Netlist,
    Pin,
)


@st.composite
def board_strategy(
    draw: st.DrawFn,
    *,
    min_width: float = 50.0,
    max_width: float = 300.0,
    min_height: float = 50.0,
    max_height: float = 300.0,
) -> Board:
    """Generate a Board with random positive dimensions."""
    w = draw(st.floats(min_value=min_width, max_value=max_width))
    h = draw(st.floats(min_value=min_height, max_value=max_height))
    return Board(width=w, height=h, origin=(0.0, 0.0))


@st.composite
def netlist_strategy(
    draw: st.DrawFn,
    *,
    min_components: int = 1,
    max_components: int = 20,
    bounds_range: tuple[float, float] = (5.0, 50.0),
) -> Netlist:
    """Generate a minimal Netlist with square components."""
    n = draw(st.integers(min_value=min_components, max_value=max_components))
    w = draw(st.floats(min_value=bounds_range[0], max_value=bounds_range[1]))
    h = draw(st.floats(min_value=bounds_range[0], max_value=bounds_range[1]))

    components = []
    nets = []
    for i in range(n):
        ref = f"U{i + 1}"
        components.append(
            Component(
                ref=ref,
                footprint="SMD-001",
                bounds=(w, h),
                pins=[Pin(str(i + 1), str(i + 1), (0.0, 0.0), net=f"NET{i + 1}")],
                net_class="Signal",
            )
        )
        nets.append(Net(f"NET{i + 1}", [(ref, str(i + 1))], net_class="Signal", weight=1.0))
    return Netlist(components=components, nets=nets)

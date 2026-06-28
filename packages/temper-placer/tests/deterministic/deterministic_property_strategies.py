"""Shared Hypothesis strategies for deterministic pipeline invariant tests.

Provides ``@st.composite`` strategies for generating arbitrary-but-valid
``BoardState`` inputs for testing deterministic pipeline stages.

Follows the pattern established by ``router_v6_property_strategies.py``.
"""

from __future__ import annotations

from hypothesis import strategies as st

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# Anchored constants
# ---------------------------------------------------------------------------

BOARD_WIDTH_RANGE: tuple[float, float] = (50.0, 200.0)
BOARD_HEIGHT_RANGE: tuple[float, float] = (50.0, 200.0)
COMPONENT_COUNT_RANGE: tuple[int, int] = (2, 10)

NET_CLASSES: tuple[str, ...] = ("Signal", "Power", "HighVoltage")

FOOTPRINT_VOCAB: tuple[str, ...] = (
    "SOIC-8", "0603", "0805", "SOT23", "QFN56", "TO-247",
)

ZONE_NAMES: tuple[str, ...] = ("HV", "Power", "Signal", "MCU")


# ---------------------------------------------------------------------------
# Core strategies
# ---------------------------------------------------------------------------


@st.composite
def board(draw: st.DrawFn) -> Board:
    """Generate a Board with random dimensions within anchored ranges."""
    w = draw(st.floats(min_value=BOARD_WIDTH_RANGE[0], max_value=BOARD_WIDTH_RANGE[1]))
    h = draw(st.floats(min_value=BOARD_HEIGHT_RANGE[0], max_value=BOARD_HEIGHT_RANGE[1]))
    return Board(width=w, height=h, origin=(0.0, 0.0))


@st.composite
def board_with_zones(draw: st.DrawFn) -> Board:
    """Generate a Board with random dimensions and 2-4 placement zones."""
    w = draw(st.floats(min_value=BOARD_WIDTH_RANGE[0], max_value=BOARD_WIDTH_RANGE[1]))
    h = draw(st.floats(min_value=BOARD_HEIGHT_RANGE[0], max_value=BOARD_HEIGHT_RANGE[1]))
    n_zones = draw(st.integers(min_value=2, max_value=4))

    # Partition board into n_zones horizontal slices
    zone_names = draw(st.lists(
        st.sampled_from(ZONE_NAMES),
        min_size=n_zones,
        max_size=n_zones,
        unique=True,
    ))
    zone_width = w / n_zones
    zones = []
    for i in range(n_zones):
        x0 = i * zone_width
        x1 = x0 + zone_width
        zones.append(Zone(
            name=zone_names[i],
            bounds=(x0, 0.0, x1, h),
        ))

    return Board(width=w, height=h, origin=(0.0, 0.0), zones=zones)


@st.composite
def component_list(
    draw: st.DrawFn,
    *,
    board_width: float = 100.0,
    board_height: float = 100.0,
    min_components: int = 2,
    max_components: int = 10,
) -> list[Component]:
    """Generate a list of Components with random bounds and net_class."""
    n = draw(st.integers(min_value=min_components, max_value=max_components))
    comps = []
    net_name_vocab = tuple(f"NET_{k}" for k in range(n * 3))
    for i in range(n):
        ref = f"U{i + 1}"
        fp = draw(st.sampled_from(FOOTPRINT_VOCAB))
        bw = draw(st.floats(min_value=1.0, max_value=20.0))
        bh = draw(st.floats(min_value=1.0, max_value=20.0))
        x = draw(st.floats(min_value=1.0, max_value=max(1.1, board_width - 1.0)))
        y = draw(st.floats(min_value=1.0, max_value=max(1.1, board_height - 1.0)))
        net_class = draw(st.sampled_from(NET_CLASSES))
        net_name = draw(st.sampled_from(net_name_vocab))
        comps.append(Component(
            ref=ref,
            footprint=fp,
            bounds=(bw, bh),
            pins=[
                Pin("1", "1", (0.0, 0.0), net=net_name),
                Pin("2", "2", (0.0, 0.0), net=f"{net_name}_GND"),
            ],
            net_class=net_class,
            initial_position=(x, y),
        ))
    return comps


def netlist_from_components(components: list[Component]) -> Netlist:
    """Create a Netlist from a list of Components.

    Each component's pins are collected; duplicate net names are merged
    so multi-pin nets are represented correctly.
    """
    net_pins: dict[str, list[tuple[str, str]]] = {}
    net_classes: dict[str, str] = {}
    for comp in components:
        nc = comp.net_class or "Signal"
        for pin in comp.pins:
            if pin.net:
                net_pins.setdefault(pin.net, []).append((comp.ref, pin.name))
                net_classes[pin.net] = nc

    nets = [
        Net(name=name, pins=pins, net_class=net_classes[name], weight=1.0)
        for name, pins in net_pins.items()
    ]
    return Netlist(components=components, nets=nets)


@st.composite
def netlist(
    draw: st.DrawFn,
    *,
    board_width: float = 100.0,
    board_height: float = 100.0,
    min_components: int = 2,
    max_components: int = 10,
) -> Netlist:
    """Generate a Netlist with random components."""
    comps = draw(component_list(
        board_width=board_width,
        board_height=board_height,
        min_components=min_components,
        max_components=max_components,
    ))
    return netlist_from_components(components=comps)


@st.composite
def board_state(draw: st.DrawFn) -> BoardState:
    """Generate a BoardState with board and netlist but no zones."""
    b = draw(board())
    nl = draw(netlist(board_width=b.width, board_height=b.height))
    return BoardState(board=b, netlist=nl)


@st.composite
def board_state_with_zones(draw: st.DrawFn) -> BoardState:
    """Generate a BoardState with random board dimensions, component count,
    and zone assignments.

    Generates:
    - Board with 50-200mm dimensions and 2-4 placement zones
    - Netlist with 2-10 components
    - No drc_oracle (test stages that can run without it)

    This is a thin wrapper around ``board_state`` that includes zones,
    making it suitable for testing zone-dependent stages.
    """
    b = draw(board_with_zones())
    nl = draw(netlist(
        board_width=b.width,
        board_height=b.height,
        min_components=COMPONENT_COUNT_RANGE[0],
        max_components=COMPONENT_COUNT_RANGE[1],
    ))
    return BoardState(board=b, netlist=nl)

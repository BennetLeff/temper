"""Shared Hypothesis strategies for IO / KiCad parser invariant property tests.

Provides composable ``@st.composite`` strategies for generating
arbitrary-but-valid IO pipeline inputs: ``Board``, ``Netlist``,
``ParsedPCB``, and ``PlacementConstraints``.

Follows the pattern established by ``router_v6_property_strategies.py``.
"""

from __future__ import annotations

from hypothesis import strategies as st

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.router_v6.stage0_data import (
    DesignRules,
    LayerInfo,
    NetClassRules,
    ParsedPCB,
    StackupInfo,
)

# ---------------------------------------------------------------------------
# Anchored constants
# ---------------------------------------------------------------------------

BOARD_WIDTH_RANGE: tuple[float, float] = (50.0, 300.0)
BOARD_HEIGHT_RANGE: tuple[float, float] = (50.0, 300.0)

NET_CLASSES: tuple[str, ...] = ("Signal", "Power", "HighVoltage")


# ---------------------------------------------------------------------------
# Core input strategies
# ---------------------------------------------------------------------------


@st.composite
def board(draw: st.DrawFn) -> Board:
    """Generate a Board with random dimensions within anchored ranges."""
    w = draw(st.floats(min_value=BOARD_WIDTH_RANGE[0], max_value=BOARD_WIDTH_RANGE[1]))
    h = draw(st.floats(min_value=BOARD_HEIGHT_RANGE[0], max_value=BOARD_HEIGHT_RANGE[1]))
    return Board(width=w, height=h, origin=(0.0, 0.0))


@st.composite
def component_list_in_bounds(
    draw: st.DrawFn,
    board: Board,
    *,
    min_components: int = 0,
    max_components: int = 20,
) -> list[Component]:
    """Generate a list of Components with random bounds and positions within board."""
    n = draw(st.integers(min_value=min_components, max_value=max_components))
    comps = []
    for i in range(n):
        ref = f"U{i + 1}"
        w = draw(st.floats(min_value=1.0, max_value=50.0))
        h = draw(st.floats(min_value=1.0, max_value=50.0))
        # Position within board bounds — allow edges (0, 0) and (board.width, board.height)
        x = draw(st.floats(min_value=0.0, max_value=board.width))
        y = draw(st.floats(min_value=0.0, max_value=board.height))
        net_class = draw(st.sampled_from(NET_CLASSES))
        comps.append(
            Component(
                ref=ref,
                footprint="SMD-001",
                bounds=(w, h),
                pins=[Pin(str(i + 1), str(i + 1), (0.0, 0.0), net=f"NET{i + 1}")],
                net_class=net_class,
                initial_position=(x, y),
            )
        )
    return comps


@st.composite
def netlist_from_components(
    draw: st.DrawFn,
    components: list[Component],
) -> Netlist:
    """Create a Netlist from a list of Components, ensuring every pin's net exists."""
    nets = []
    for comp in components:
        for pin in comp.pins:
            if pin.net:
                net_class = draw(st.sampled_from(NET_CLASSES))
                nets.append(
                    Net(pin.net, [(comp.ref, pin.name)], net_class=net_class, weight=1.0)
                )
    # Deduplicate by net name
    seen: set[str] = set()
    unique_nets = []
    for n in nets:
        if n.name not in seen:
            seen.add(n.name)
            unique_nets.append(n)
    return Netlist(components=components, nets=unique_nets)


@st.composite
def board_and_netlist(
    draw: st.DrawFn,
    *,
    min_components: int = 1,
    max_components: int = 20,
) -> tuple[Board, Netlist]:
    """Generate a Board + Netlist pair with consistent component-to-net mapping."""
    b = draw(board())
    comps = draw(
        component_list_in_bounds(
            board=b,
            min_components=min_components,
            max_components=max_components,
        )
    )
    nl = draw(netlist_from_components(components=comps))
    return b, nl


@st.composite
def design_rules(draw: st.DrawFn) -> DesignRules:
    """Generate Router V6 DesignRules with random net classes and defaults."""
    n_classes = draw(st.integers(min_value=1, max_value=4))
    net_classes: dict[str, NetClassRules] = {}
    net_class_assignments: dict[str, str] = {}

    for _ in range(n_classes):
        class_name = draw(st.sampled_from(["Signal", "Power", "HighVoltage", "ACMains"]))
        if class_name in net_classes:
            continue
        clearance = draw(st.floats(min_value=0.1, max_value=6.0))
        trace_width = draw(st.floats(min_value=0.1, max_value=3.0))
        via_dia = draw(st.floats(min_value=0.3, max_value=1.5))
        via_drill = draw(st.floats(min_value=0.1, max_value=via_dia))
        net_classes[class_name] = NetClassRules(
            name=class_name,
            clearance_mm=clearance,
            trace_width_mm=trace_width,
            via_diameter_mm=via_dia,
            via_drill_mm=via_drill,
        )

    # Assign some nets to classes
    n_assignments = draw(st.integers(min_value=0, max_value=8))
    for _ in range(n_assignments):
        net_name = draw(st.sampled_from(["VCC", "GND", "AC_L", "AC_N", "SIG_A", "CLK"]))
        class_name = draw(st.sampled_from(list(net_classes.keys())))
        net_class_assignments[net_name] = class_name

    return DesignRules(
        net_classes=net_classes,
        net_class_assignments=net_class_assignments,
        default_clearance_mm=draw(st.floats(min_value=0.1, max_value=0.5)),
        default_trace_width_mm=draw(st.floats(min_value=0.1, max_value=0.5)),
        default_via_diameter_mm=draw(st.floats(min_value=0.4, max_value=1.0)),
        default_via_drill_mm=draw(st.floats(min_value=0.2, max_value=0.6)),
        min_hole_to_hole_mm=draw(st.floats(min_value=0.1, max_value=0.5)),
        min_annular_ring_mm=draw(st.floats(min_value=0.05, max_value=0.2)),
    )


@st.composite
def layer_info(draw: st.DrawFn, name: str = "F.Cu", index: int = 0) -> LayerInfo:
    """Generate a LayerInfo for the given name and index."""
    return LayerInfo(
        index=index,
        name=name,
        layer_type=draw(st.sampled_from(["signal", "plane", "mixed"])),
        thickness_um=draw(st.floats(min_value=17.5, max_value=70.0)),
    )


@st.composite
def stackup_info(draw: st.DrawFn) -> StackupInfo:
    """Generate a StackupInfo with F.Cu and B.Cu layers."""
    layers = [
        draw(layer_info(name="F.Cu", index=0)),
        draw(layer_info(name="B.Cu", index=1)),
    ]
    return StackupInfo(
        layers=layers,
        total_thickness_mm=draw(st.floats(min_value=1.0, max_value=3.2)),
        layer_count=len(layers),
    )


@st.composite
def parsed_pcb(draw: st.DrawFn) -> ParsedPCB:
    """Generate a complete ParsedPCB with random components, nets, design rules, and stackup."""
    b = draw(board())
    comps = draw(
        component_list_in_bounds(
            board=b,
            min_components=0,
            max_components=15,
        )
    )
    nl = draw(netlist_from_components(components=comps))
    dr = draw(design_rules())
    si = draw(stackup_info())

    return ParsedPCB(
        components=comps,
        nets=list(nl.nets),
        zones=[],
        board=b,
        design_rules=dr,
        stackup=si,
        source_path=None,
    )


@st.composite
def placement_constraints(draw: st.DrawFn) -> PlacementConstraints:
    """Generate a PlacementConstraints matching typical board dimensions."""
    w = draw(st.floats(min_value=50.0, max_value=300.0))
    h = draw(st.floats(min_value=50.0, max_value=300.0))
    margin = draw(st.floats(min_value=0.0, max_value=10.0))
    return PlacementConstraints(
        board_width_mm=w,
        board_height_mm=h,
        board_margin_mm=margin,
    )

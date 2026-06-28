"""Shared Hypothesis strategies for Router V6 invariant property tests.

Provides composable ``@st.composite`` strategies for generating
arbitrary-but-valid Router V6 pipeline inputs: ``ParsedPCB``,
``RoutingResults`` with traces, and stage outputs.

Follows the pattern established by ``dfm_property_strategies.py``.
"""

from __future__ import annotations

from hypothesis import strategies as st

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.stage0_data import (
    DesignRules,
    LayerInfo,
    NetClassRules,
    ParsedPCB,
    StackupInfo,
)
from temper_placer.router_v6.via_placement import Via

# ---------------------------------------------------------------------------
# Anchored constants
# ---------------------------------------------------------------------------

BOARD_WIDTH_RANGE: tuple[float, float] = (50.0, 300.0)
BOARD_HEIGHT_RANGE: tuple[float, float] = (50.0, 300.0)

LAYERS: tuple[str, ...] = ("F.Cu", "B.Cu")

NET_CLASSES: tuple[str, ...] = ("Signal", "Power", "HighVoltage")

NET_NAME_VOCAB: tuple[str, ...] = (
    "NET1", "NET2", "SIG_A", "SIG_B", "CLK", "RST", "ENABLE",
    "GND", "VCC", "+15V", "+3V3", "AC_L", "AC_N", "HV_BUS",
    "VDD_CORE", "VBAT", "SW_NODE",
)

VIA_TYPES: tuple[str | None, ...] = (None, "microvia")


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
def design_rules(draw: st.DrawFn) -> DesignRules:
    """Generate Router V6 DesignRules with random net classes and defaults."""
    n_classes = draw(st.integers(min_value=1, max_value=4))
    net_classes: dict[str, NetClassRules] = {}
    net_class_assignments: dict[str, str] = {}

    for i in range(n_classes):
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
def component_list(
    draw: st.DrawFn,
    *,
    board_width: float = 100.0,
    board_height: float = 100.0,
    min_components: int = 1,
    max_components: int = 20,
) -> list[Component]:
    """Generate a list of Components with random bounds and initial positions within board."""
    n = draw(st.integers(min_value=min_components, max_value=max_components))
    comps = []
    for i in range(n):
        ref = f"U{i + 1}"
        w = draw(st.floats(min_value=1.0, max_value=50.0))
        h = draw(st.floats(min_value=1.0, max_value=50.0))
        # Position within board bounds (margin 1mm)
        x = draw(st.floats(min_value=1.0, max_value=max(1.1, board_width - 1.0)))
        y = draw(st.floats(min_value=1.0, max_value=max(1.1, board_height - 1.0)))
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
    """Create a Netlist from a list of Components."""
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
def netlist(
    draw: st.DrawFn,
    *,
    board_width: float = 100.0,
    board_height: float = 100.0,
    min_components: int = 1,
    max_components: int = 20,
) -> Netlist:
    """Generate a Netlist with random components."""
    comps = draw(
        component_list(
            board_width=board_width,
            board_height=board_height,
            min_components=min_components,
            max_components=max_components,
        )
    )
    return draw(netlist_from_components(components=comps))


@st.composite
def parsed_pcb(draw: st.DrawFn) -> ParsedPCB:
    """Generate a complete ParsedPCB with random components, nets, design rules, and stackup."""
    b = draw(board())
    comps = draw(
        component_list(
            board_width=b.width,
            board_height=b.height,
            min_components=2,
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


# ---------------------------------------------------------------------------
# Routing result strategies
# ---------------------------------------------------------------------------


@st.composite
def realistic_paths(
    draw: st.DrawFn,
    *,
    board_width: float = 200.0,
    board_height: float = 150.0,
    min_points: int = 2,
    max_points: int = 50,
) -> RoutePath:
    """Generate a RoutePath with coordinates within board bounds."""
    n_points = draw(st.integers(min_value=min_points, max_value=max_points))
    layer = draw(st.sampled_from(LAYERS))

    x_coords = [
        draw(st.floats(min_value=0.0, max_value=board_width))
        for _ in range(n_points)
    ]
    y_coords = [
        draw(st.floats(min_value=0.0, max_value=board_height))
        for _ in range(n_points)
    ]

    net_name = draw(st.sampled_from(NET_NAME_VOCAB))
    path = RoutePath(net_name=net_name, coordinates=[], layer_name=layer, path_length=0.0)
    for x, y in zip(x_coords, y_coords):
        path.coordinates.append((x, y))
    # Compute path length from coordinates
    total = 0.0
    for i in range(1, len(path.coordinates)):
        x1, y1 = path.coordinates[i - 1]
        x2, y2 = path.coordinates[i]
        total += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    path.path_length = total
    return path


@st.composite
def realistic_vias(
    draw: st.DrawFn,
    *,
    board_width: float = 200.0,
    board_height: float = 150.0,
) -> list[Via]:
    """Generate a list of Via objects within board bounds."""
    n = draw(st.integers(min_value=0, max_value=10))
    vias = []
    for _ in range(n):
        x = draw(st.floats(min_value=0.0, max_value=board_width))
        y = draw(st.floats(min_value=0.0, max_value=board_height))
        diameter = draw(st.floats(min_value=0.3, max_value=1.5))
        drill = draw(st.floats(min_value=0.1, max_value=diameter))
        via_type = draw(st.sampled_from(VIA_TYPES))
        vias.append(
            Via(
                position=(x, y),
                net_name=draw(st.sampled_from(NET_NAME_VOCAB)),
                diameter=diameter,
                drill=drill,
                from_layer=draw(st.sampled_from(LAYERS)),
                to_layer=draw(st.sampled_from(LAYERS)),
            )
        )
    return vias


@st.composite
def compiled_route(
    draw: st.DrawFn,
    *,
    board_width: float = 200.0,
    board_height: float = 150.0,
) -> CompiledRoute:
    """Generate a single CompiledRoute with path and vias."""
    path = draw(realistic_paths(board_width=board_width, board_height=board_height))
    vias = draw(realistic_vias(board_width=board_width, board_height=board_height))
    width_mm = draw(st.floats(min_value=0.1, max_value=3.0))
    return CompiledRoute(
        net_name=draw(st.sampled_from(NET_NAME_VOCAB)),
        path=path,
        width_mm=width_mm,
        vias=vias,
        matched_length_mm=None,
    )


@st.composite
def routing_results(
    draw: st.DrawFn,
    *,
    board_width: float = 200.0,
    board_height: float = 150.0,
    min_routes: int = 0,
    max_routes: int = 15,
    min_failed: int = 0,
    max_failed: int = 5,
) -> RoutingResults:
    """Generate RoutingResults with compiled routes and failed nets."""
    n_routes = draw(st.integers(min_value=min_routes, max_value=max_routes))
    n_failed = draw(st.integers(min_value=min_failed, max_value=max_failed))

    if n_routes + n_failed == 0:
        n_routes = 1  # ensure at least one net for most invariants

    compiled_routes: dict[str, CompiledRoute] = {}
    for i in range(n_routes):
        route = draw(
            compiled_route(board_width=board_width, board_height=board_height)
        )
        compiled_routes[f"NET_{i}"] = route

    failed_nets = [f"FAIL_{j}" for j in range(n_failed)]

    return RoutingResults(
        compiled_routes=compiled_routes,
        failed_nets=failed_nets,
        plane_net_count=draw(st.integers(min_value=0, max_value=3)),
    )

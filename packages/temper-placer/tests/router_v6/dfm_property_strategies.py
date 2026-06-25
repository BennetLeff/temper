"""Shared Hypothesis strategies for DFM property tests.

Provides reusable strategies used by both the generic invariant tests in
``test_dfm_hypothesis_fuzzing.py`` and the domain-correctness property
tests in ``test_<module>_properties.py``.

Strategies
----------
* ``realistic_paths`` — random multi-point paths within board bounds
* ``realistic_vias`` — random via objects for a net
* ``realistic_routing_results`` — full ``RoutingResults`` with
  1-20 compiled routes, realistic net names (HV/power/signal mix)
* ``known_angle_path`` — a 3-point path with a specific vertex angle
* ``known_dimension_via`` — a via with exact (diameter, drill) specs
* ``mixed_net_routing_results`` — ``RoutingResults`` with explicit
  power and signal nets
* ``same_layer_net_set`` — N nets all on the same layer
"""

from __future__ import annotations

import math
from typing import Callable

from hypothesis import strategies as st

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.via_placement import Via

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOARD_DIMS: tuple[float, float] = (200.0, 150.0)  # (width, height) mm
BOARD_W, BOARD_H = BOARD_DIMS

LAYERS: tuple[str, ...] = ("F.Cu", "B.Cu", "In1.Cu", "In2.Cu")

# Net name vocabulary — a mix of regular signal nets and power / HV nets
# so that DFM modules exercising HV / power classification see a realistic
# spread.
NET_NAME_VOCAB: tuple[str, ...] = (
    # Signal-style
    "SIG1", "SIG2", "DATA0", "CLK", "RST", "ENABLE",
    "TX+", "RX-", "LED1", "NC1",
    # Power / ground (matched by thermal_relief, copper_balance plane nets)
    "GND", "PGND", "AGND", "DGND", "VCC", "VDD", "VEE",
    "+15V", "+3V3", "+5V",
    # HV patterns (matched by creepage / clearance HV-detection)
    "AC_L", "AC_N", "HV_BUS", "L1", "LINE", "VBUS",
    # Mixed
    "DC_BUS+", "DC_BUS-", "SW_NODE", "PE",
    "VDD_CORE", "VREF", "VBAT",
)

VIA_TYPES: tuple[str | None, ...] = (None, "microvia")


# ---------------------------------------------------------------------------
# Existing strategies (moved from test_dfm_hypothesis_fuzzing.py)
# ---------------------------------------------------------------------------


@st.composite
def realistic_paths(
    draw: st.DrawFn,
    min_points: int = 2,
    max_points: int = 50,
) -> RoutePath:
    """Generate a realistic ``RoutePath`` with 2-50 points inside the
    board boundary.

    Coordinates are chosen uniformly within the board rectangle.  The
    resulting path does **not** enforce a no-self-intersection constraint
    (real routed paths can have complex geometry, and the DFM modules
    should handle any coordinate list gracefully).
    """
    n_points = draw(st.integers(min_value=min_points, max_value=max_points))
    layer = draw(st.sampled_from(LAYERS))

    coords: list[tuple[float, float]] = []
    for _ in range(n_points):
        x = draw(st.floats(min_value=0.0, max_value=BOARD_W))
        y = draw(st.floats(min_value=0.0, max_value=BOARD_H))
        coords.append((x, y))

    # Compute path length (Euclidean distance between consecutive points)
    path_len = 0.0
    for i in range(len(coords) - 1):
        path_len += math.hypot(
            coords[i + 1][0] - coords[i][0],
            coords[i + 1][1] - coords[i][1],
        )

    return RoutePath(
        net_name="",  # filled in by the routing-results strategy
        coordinates=coords,
        layer_name=layer,
        path_length=path_len,
    )


@st.composite
def realistic_vias(
    draw: st.DrawFn,
    net_name: str = "NET",
    max_vias: int = 10,
) -> list[Via]:
    """Generate 0-*max_vias* realistic ``Via`` objects for a given net."""
    n = draw(st.integers(min_value=0, max_value=max_vias))
    vias: list[Via] = []
    for _ in range(n):
        x = draw(st.floats(min_value=0.0, max_value=BOARD_W))
        y = draw(st.floats(min_value=0.0, max_value=BOARD_H))
        frm = draw(st.sampled_from(LAYERS))
        to = draw(st.sampled_from(LAYERS))
        dia = draw(st.floats(min_value=0.1, max_value=5.0))
        drill = draw(st.floats(min_value=0.05, max_value=dia * 0.9))
        via_type = draw(st.sampled_from(VIA_TYPES))
        via = Via(
            position=(x, y),
            from_layer=frm,
            to_layer=to,
            diameter=dia,
            drill=drill,
            net_name=net_name,
        )
        # Attach via_type as an extra attribute (some DFM modules check it)
        if via_type is not None:
            via.via_type = via_type  # type: ignore[attr-defined]
        vias.append(via)
    return vias


@st.composite
def realistic_routing_results(
    draw: st.DrawFn,
    min_routes: int = 1,
    max_routes: int = 20,
) -> RoutingResults:
    """Generate 1-20 compiled routes with realistic paths, widths, vias,
    and net names from a vocabulary that includes HV/power patterns.
    """
    n = draw(st.integers(min_value=min_routes, max_value=max_routes))
    net_names = draw(
        st.lists(
            st.sampled_from(NET_NAME_VOCAB),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )

    compiled: dict[str, CompiledRoute] = {}
    failed: list[str] = []

    for net_name in net_names:
        path = draw(realistic_paths())
        # Patch the net name into the path
        path.net_name = net_name

        width = draw(st.floats(min_value=0.1, max_value=5.0))
        vias = draw(realistic_vias(net_name=net_name, max_vias=10))

        compiled[net_name] = CompiledRoute(
            net_name=net_name,
            path=path,
            width_mm=width,
            vias=vias,
            matched_length_mm=None,
        )

    # Optionally add some failed nets
    extra_fails = draw(st.integers(min_value=0, max_value=3))
    for i in range(extra_fails):
        failed.append(f"FAIL{i}")

    return RoutingResults(compiled_routes=compiled, failed_nets=failed)


# ---------------------------------------------------------------------------
# Targeted strategies for domain-correctness property tests
# ---------------------------------------------------------------------------

# Known angle values for severity classification testing.
_KNOWN_ANGLES: tuple[float, ...] = (30.0, 44.0, 45.0, 52.0, 60.0, 75.0, 89.0, 90.0, 120.0)

# Known (diameter, drill) pairs for annular ring testing.
_KNOWN_VIA_DIMS: tuple[tuple[float, float], ...] = (
    (1.0, 0.5),
    (0.6, 0.3),
    (0.3, 0.2),
    (2.0, 1.0),
    (0.8, 0.4),
)


@st.composite
def known_angle_path(
    draw: st.DrawFn,
    angle_degrees: float | None = None,
    width_mm: float = 0.2,
    layer: str = "F.Cu",
) -> tuple[RoutePath, float]:
    """Generate a 3-point path where the vertex angle is a known value.

    When *angle_degrees* is None, one is drawn from ``_KNOWN_ANGLES``.

    Returns a ``(RoutePath, width_mm)`` tuple for direct use with
    ``detect_acid_traps`` or ``_classify_severity``.
    """
    if angle_degrees is None:
        angle_degrees = draw(st.sampled_from(_KNOWN_ANGLES))

    angle_rad = math.radians(angle_degrees)

    # Place p2 at origin, p1 along positive x-axis at distance d,
    # p3 at angle `angle_rad` counterclockwise from p1.
    d = 10.0  # segment length
    p1 = (d, 0.0)
    p2 = (0.0, 0.0)  # vertex
    p3 = (d * math.cos(angle_rad), d * math.sin(angle_rad))

    path = RoutePath(
        net_name="TEST",
        coordinates=[p1, p2, p3],
        layer_name=layer,
        path_length=2.0 * d,
    )
    path.net_name = "TEST"
    return path, width_mm


@st.composite
def known_dimension_via(
    draw: st.DrawFn,
    diameter: float | None = None,
    drill: float | None = None,
    via_type: str | None = None,
    net_name: str = "TEST",
    from_layer: str = "F.Cu",
    to_layer: str = "In1.Cu",
) -> Via:
    """Generate a ``Via`` with specific dimensions.

    When *diameter* / *drill* are None, a pair is drawn from
    ``_KNOWN_VIA_DIMS``.  The via is placed at (50, 50) on the board.

    Parameters
    ----------
    diameter : float or None
        Pad diameter in mm.
    drill : float or None
        Drill diameter in mm.
    via_type : str or None
        Via type (e.g. ``"microvia"``).  When None, the via has no
        ``via_type`` attribute.
    net_name : str
        Net name for the via.
    from_layer : str
        Starting layer.
    to_layer : str
        Ending layer.
    """
    if diameter is None or drill is None:
        dia, drl = draw(st.sampled_from(_KNOWN_VIA_DIMS))
        if diameter is None:
            diameter = dia
        if drill is None:
            drill = drl

    via = Via(
        position=(50.0, 50.0),
        from_layer=from_layer,
        to_layer=to_layer,
        diameter=diameter,
        drill=drill,
        net_name=net_name,
    )
    if via_type is not None:
        via.via_type = via_type  # type: ignore[attr-defined]
    return via


@st.composite
def mixed_net_routing_results(
    draw: st.DrawFn,
    power_nets: tuple[str, ...] = ("GND", "VCC"),
    signal_nets: tuple[str, ...] = ("SIG1", "SIG2", "DATA0"),
    min_routes: int = 2,
    max_routes: int = 10,
) -> RoutingResults:
    """Generate ``RoutingResults`` with a guaranteed mix of power and
    signal nets.

    The first *len(power_nets)* entries are power nets; the remainder
    are drawn from *signal_nets*.  Useful for testing power-net-scoped
    modules (thermal relief, copper balance plane detection).
    """
    n = draw(st.integers(min_value=min_routes, max_value=max_routes))

    # Pick net names: at least min(power_nets, n) power nets, rest signal
    n_power = min(len(power_nets), n)
    n_signal = n - n_power

    net_names = list(power_nets[:n_power])
    if n_signal > 0:
        extra = draw(
            st.lists(
                st.sampled_from(signal_nets),
                min_size=n_signal,
                max_size=n_signal,
                unique=True,
            )
        )
        net_names.extend(extra)

    compiled: dict[str, CompiledRoute] = {}
    for net_name in net_names:
        path = draw(realistic_paths())
        path.net_name = net_name
        width = draw(st.floats(min_value=0.1, max_value=5.0))
        vias = draw(realistic_vias(net_name=net_name, max_vias=5))
        compiled[net_name] = CompiledRoute(
            net_name=net_name,
            path=path,
            width_mm=width,
            vias=vias,
            matched_length_mm=None,
        )

    return RoutingResults(compiled_routes=compiled, failed_nets=[])


@st.composite
def same_layer_net_set(
    draw: st.DrawFn,
    n_nets: int = 5,
    layer: str = "F.Cu",
) -> RoutingResults:
    """Generate *n_nets* nets all on the same *layer*.

    Useful for clearance / creepage layer-independence tests where you
    need a controlled set of same-layer nets to serve as a baseline.
    """
    net_names = draw(
        st.lists(
            st.sampled_from(NET_NAME_VOCAB),
            min_size=n_nets,
            max_size=n_nets,
            unique=True,
        )
    )

    compiled: dict[str, CompiledRoute] = {}
    for net_name in net_names:
        path = draw(realistic_paths())
        path.net_name = net_name
        # Override layer — all nets go on the requested layer
        path.layer_name = layer
        width = draw(st.floats(min_value=0.1, max_value=5.0))
        vias = draw(realistic_vias(net_name=net_name, max_vias=5))
        compiled[net_name] = CompiledRoute(
            net_name=net_name,
            path=path,
            width_mm=width,
            vias=vias,
            matched_length_mm=None,
        )

    return RoutingResults(compiled_routes=compiled, failed_nets=[])

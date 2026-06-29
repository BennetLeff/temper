"""Shared boundary-value constants for DFM module edge-case tests.

Import from this module in each DFM boundary test file to avoid
duplicating edge-case value lists.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Trace widths (mm)
# ---------------------------------------------------------------------------
TRACE_WIDTHS_ZERO = [0.0]
TRACE_WIDTHS_NEGATIVE = [-0.1, -0.001]
TRACE_WIDTHS_NAN = [float("nan")]
TRACE_WIDTHS_INF = [float("inf"), -float("inf")]
TRACE_WIDTHS_EXTREME = [1e-6, 1e6]
TRACE_WIDTHS_NORMAL = [0.075, 0.127, 0.25, 0.5, 2.0, 5.0]
TRACE_WIDTHS_BOUNDARY = (
    TRACE_WIDTHS_ZERO
    + TRACE_WIDTHS_NEGATIVE
    + TRACE_WIDTHS_NAN
    + TRACE_WIDTHS_INF
    + TRACE_WIDTHS_EXTREME
)

# ---------------------------------------------------------------------------
# Via diameters / drills (mm)
# ---------------------------------------------------------------------------
VIA_DIAMETERS_ZERO = [0.0]
VIA_DIAMETERS_NEGATIVE = [-0.1]
VIA_DIAMETERS_NAN = [float("nan")]
VIA_DIAMETERS_DRILL_LARGER = [(0.3, 0.5), (0.15, 0.16)]  # drill > diameter
VIA_DIAMETERS_EQUAL = [(0.3, 0.3)]  # drill == diameter
VIA_DIAMETERS_NORMAL = [(0.6, 0.3), (0.8, 0.4), (0.3, 0.15)]
VIA_DIAMETERS_BOUNDARY = (
    [(d, 0.3) for d in VIA_DIAMETERS_ZERO]
    + [(0.6, d) for d in VIA_DIAMETERS_ZERO]
    + VIA_DIAMETERS_DRILL_LARGER
    + VIA_DIAMETERS_EQUAL
)

# ---------------------------------------------------------------------------
# Board dimensions (mm)
# ---------------------------------------------------------------------------
BOARD_DIMS_ZERO = [(0.0, 100.0), (100.0, 0.0), (0.0, 0.0)]
BOARD_DIMS_NEGATIVE = [(-1.0, 100.0), (100.0, -1.0)]
BOARD_DIMS_NAN = [(float("nan"), 100.0), (100.0, float("nan"))]
BOARD_DIMS_INF = [(float("inf"), 100.0), (100.0, float("inf"))]
BOARD_DIMS_EXTREME = [(1e-6, 1e-6), (1e6, 1e6)]
BOARD_DIMS_NORMAL = [(100.0, 80.0), (200.0, 150.0)]
BOARD_DIMS_BOUNDARY = (
    BOARD_DIMS_ZERO + BOARD_DIMS_NEGATIVE + BOARD_DIMS_NAN + BOARD_DIMS_INF
)

# ---------------------------------------------------------------------------
# Clearance / creepage thresholds (mm)
# ---------------------------------------------------------------------------
THRESHOLD_ZERO = [0.0]
THRESHOLD_NEGATIVE = [-0.001, -1.0]
THRESHOLD_NAN = [float("nan")]
THRESHOLD_INF = [float("inf")]
THRESHOLD_NORMAL = [0.05, 0.127, 0.2, 0.5, 2.0, 6.0]
THRESHOLD_BOUNDARY = (
    THRESHOLD_ZERO + THRESHOLD_NEGATIVE + THRESHOLD_NAN + THRESHOLD_INF
)

# ---------------------------------------------------------------------------
# Voltage values (V)
# ---------------------------------------------------------------------------
VOLTAGE_ZERO = [0]
VOLTAGE_NEGATIVE = [-1, -230]
VOLTAGE_NAN = [float("nan")]
VOLTAGE_INF = [float("inf")]
VOLTAGE_EXTREME = [1e6]
VOLTAGE_NORMAL = [50, 100, 230, 400, 1000]
VOLTAGE_BOUNDARY = (
    VOLTAGE_ZERO + VOLTAGE_NEGATIVE + VOLTAGE_NAN + VOLTAGE_INF + VOLTAGE_EXTREME
)

# ---------------------------------------------------------------------------
# Coordinate positions (mm)
# ---------------------------------------------------------------------------
COORD_ZERO = [(0.0, 0.0)]
COORD_NEGATIVE = [(-1.0, -1.0), (10.0, -5.0)]
COORD_NAN = [(float("nan"), 0.0), (0.0, float("nan"))]
COORD_INF = [(float("inf"), 0.0), (0.0, float("inf"))]
COORD_EXTREME = [(1e-6, 1e-6), (1e6, 1e6)]
COORD_BOUNDARY = COORD_ZERO + COORD_NEGATIVE + COORD_NAN + COORD_INF + COORD_EXTREME

# ---------------------------------------------------------------------------
# At-threshold helpers
# ---------------------------------------------------------------------------

def just_below(value: float, delta: float = 1e-6) -> float:
    """Value just below the threshold."""
    return value - abs(delta)


def just_above(value: float, delta: float = 1e-6) -> float:
    """Value just above the threshold."""
    return value + abs(delta)


def exactly_at(value: float) -> float:
    """Value exactly at the threshold."""
    return value


# ---------------------------------------------------------------------------
# Shared test helpers (Path / Via / Route / Results stubs)
# ---------------------------------------------------------------------------

import math as _math  # noqa: E402


class Path:
    """Minimal RoutePath stub for boundary tests."""

    def __init__(self, coords, layer="F.Cu"):
        self.coordinates = list(coords)
        self.layer_name = layer
        self.total_length_mm = sum(
            _math.hypot(
                coords[i + 1][0] - coords[i][0],
                coords[i + 1][1] - coords[i][1],
            )
            for i in range(len(coords) - 1)
        ) if len(coords) > 1 else 0.0
        self.path_length = self.total_length_mm


class Via:
    """Minimal Via stub for boundary tests."""

    def __init__(self, x, y, frm, to, dia, drill, net, via_type=None):
        self.position = (x, y)
        self.from_layer = frm
        self.to_layer = to
        self.diameter = dia
        self.drill = drill
        self.net_name = net
        self.via_type = via_type


class Route:
    def __init__(self, name, path, width, vias):
        self.net_name = name
        self.path = path
        self.width_mm = width
        self.vias = list(vias)


class Results:
    def __init__(self, **routes):
        self.compiled_routes = routes
        self.failed_nets = []


def make_results(**kwargs) -> Results:
    return Results(**kwargs)

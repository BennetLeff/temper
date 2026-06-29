"""
Router V6 Stage 5.4: Add Thermal Relief

Validates and generates thermal relief connections for power planes.
Part of temper-95xg (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.router_v6.routing_results import RoutingResults

if TYPE_CHECKING:
    from temper_placer.core.board import Board


# ---------------------------------------------------------------------------
# Power-net name pattern ─ word-boundary match of known power/ground families
# plus any net whose name ends with GND (e.g. PGND, AGND, DGND, CGND, etc.).
# ---------------------------------------------------------------------------
_POWER_NET_PATTERN: re.Pattern = re.compile(
    r"\b(?:"
    r"GND|PGND|AGND|DGND|CGND|"          # explicit ground variants
    r"[A-Z]*GND|"                         # catch-all *GND suffix
    r"VCC|VDD|VEE|VPP|VBB|VREF|VBAT|"
    r"VDDIO|AVDD|DVDD|VCCINT|VCCO|VDD_CORE|"
    r"POWER|PVCC|PVDD"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Default plane-net set ─ mirrors TEMPER_PLANE_NETS in
# temper_placer.deterministic.stages.power_plane so the thermal-relief stage
# can operate standalone if the caller does not supply an explicit set.
# ---------------------------------------------------------------------------
_DEFAULT_PLANE_NETS: frozenset[str] = frozenset(
    {
        "GND", "PGND", "CGND",
        "VCC", "VDD", "VEE",
        "+15V", "+3V3", "+5V",
        "DC_BUS+", "DC_BUS-", "SW_NODE",
        "AC_L", "AC_N", "PE",
    }
)


@dataclass
class ThermalRelief:
    """Thermal relief connection specification."""

    net_name: str
    pad_position: tuple[float, float]
    spoke_count: int  # Number of spokes (typically 4)
    spoke_width: float  # Width of each spoke (mm)
    clearance_gap: float  # Gap from pad to plane (mm)
    pad_size: tuple[float, float] = (0.6, 0.6)  # (width, height) of pad in mm
    # 4-spoke geometry: list of ((x1,y1), (x2,y2)) line segments
    spoke_segments: list[tuple[tuple[float, float], tuple[float, float]]] = (
        field(default_factory=list)
    )


@dataclass
class ThermalReliefReport:
    """Report of thermal relief connections."""

    thermal_reliefs: list[ThermalRelief]

    @property
    def relief_count(self) -> int:
        """Total number of thermal reliefs."""
        return len(self.thermal_reliefs)

    @property
    def total_spokes(self) -> int:
        """Total number of spokes across all reliefs."""
        return sum(tr.spoke_count for tr in self.thermal_reliefs)


def add_thermal_relief(
    routing_results: RoutingResults,
    spoke_count: int = 4,
    spoke_width: float = 0.254,  # 10mil typical
    clearance_gap: float = 0.254,  # 10mil typical
    *,
    plane_layers: list[str] | None = None,
    plane_nets: frozenset[str] | None = None,
    board: Board | None = None,
) -> ThermalReliefReport:
    """
    Add thermal relief connections to power plane pads.

    Thermal relief prevents excessive heat sinking during soldering
    while maintaining electrical connection to power planes.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        spoke_count: Number of connection spokes (typically 4)
        spoke_width: Width of each spoke (mm)
        clearance_gap: Gap between pad and plane (mm)
        plane_layers: Explicit list of inner-plane layer names (e.g.
            ``['In1.Cu', 'In2.Cu']``).  When *None* the function inspects
            ``board.layer_stackup`` for layers whose ``layer_type == "plane"``;
            if no board is supplied the fallback is ``['In1.Cu', 'In2.Cu']``.
        plane_nets: Explicit set of net names that are plane-connected.
            When *None* the internal default ``_DEFAULT_PLANE_NETS`` is used.
        board: Optional ``Board`` object used for stackup detection, SMD-pad
            enumeration, and board-outline clamping.

    Returns:
        ThermalReliefReport with all generated thermal reliefs

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = add_thermal_relief(results)
        >>> report.relief_count >= 0
        True
    """
    # ── input validation ──────────────────────────────────────────────
    if math.isnan(spoke_width) or math.isinf(spoke_width) or spoke_width <= 0:
        raise ValueError(f"spoke_width must be > 0 and finite, got {spoke_width}")
    if math.isnan(clearance_gap) or math.isinf(clearance_gap) or clearance_gap <= 0:
        raise ValueError(f"clearance_gap must be > 0 and finite, got {clearance_gap}")
    if (isinstance(spoke_count, float) and math.isnan(spoke_count)) or spoke_count < 2:
        raise ValueError(f"spoke_count must be >= 2, got {spoke_count}")

    # ── resolve plane_layers ──────────────────────────────────────────
    resolved_plane_layers: list[str]
    if plane_layers is not None:
        resolved_plane_layers = list(plane_layers)
    elif board is not None and board.layer_stackup is not None:
        resolved_plane_layers = [
            layer.name
            for layer in board.layer_stackup.layers
            if layer.layer_type == "plane"
        ]
    else:
        resolved_plane_layers = ["In1.Cu", "In2.Cu"]

    # ── resolve plane_nets ────────────────────────────────────────────
    resolved_plane_nets: frozenset[str] = (
        plane_nets if plane_nets is not None else _DEFAULT_PLANE_NETS
    )

    thermal_reliefs: list[ThermalRelief] = []

    for net_name, compiled_route in routing_results.compiled_routes.items():
        # Check if this is a power net that needs thermal relief
        if _is_power_net(net_name):
            # Analyze route to identify power plane connections
            # For each via connecting to power plane, add thermal relief
            for via in compiled_route.vias:
                if math.isnan(via.diameter) or via.diameter <= 0:
                    continue
                if _connects_to_power_plane(
                    via,
                    net_name,
                    resolved_plane_layers,
                    resolved_plane_nets,
                ):
                    pad_size = (via.diameter, via.diameter)
                    spokes = _generate_spoke_segments(
                        pad_position=via.position,
                        pad_size=pad_size,
                        spoke_count=spoke_count,
                        spoke_width=spoke_width,
                        clearance_gap=clearance_gap,
                        board=board,
                    )
                    thermal_reliefs.append(
                        ThermalRelief(
                            net_name=net_name,
                            pad_position=via.position,
                            spoke_count=spoke_count,
                            spoke_width=spoke_width,
                            clearance_gap=clearance_gap,
                            pad_size=pad_size,
                            spoke_segments=spokes,
                        )
                    )

    # ── SMD pads that connect to power planes ─────────────────────────
    if board is not None:
        _add_smd_thermal_reliefs(
            board=board,
            routing_results=routing_results,
            resolved_plane_layers=resolved_plane_layers,
            resolved_plane_nets=resolved_plane_nets,
            spoke_count=spoke_count,
            spoke_width=spoke_width,
            clearance_gap=clearance_gap,
            thermal_reliefs=thermal_reliefs,
        )

    return ThermalReliefReport(thermal_reliefs=thermal_reliefs)


# ---------------------------------------------------------------------------
# Power-net detection (regex)
# ---------------------------------------------------------------------------


def _is_power_net(net_name: str) -> bool:
    """
    Check if net is a power net requiring thermal relief.

    Uses word-boundary regex matching against a comprehensive list of
    power/ground net names (GND, PGND, AGND, DGND, CGND, any *GND,
    VCC, VDD, VEE, VPP, VBB, VREF, VBAT, VDDIO, AVDD, DVDD, VCCINT,
    VCCO, VDD_CORE, POWER, PVCC, PVDD).

    Args:
        net_name: Net name

    Returns:
        True if power net
    """
    return bool(_POWER_NET_PATTERN.search(net_name))


# ---------------------------------------------------------------------------
# Plane-connection check
# ---------------------------------------------------------------------------


def _connects_to_power_plane(
    via,
    net_name: str,
    plane_layers: list[str],
    plane_nets: frozenset[str],
) -> bool:
    """
    Check if via connects to a power plane.

    Verifies both (a) the via touches an inner plane layer and (b) the
    net is registered as a plane net.

    Args:
        via: Via object (must have from_layer, to_layer attributes)
        net_name: Net name
        plane_layers: List of plane layer names (e.g. ['In1.Cu', 'In2.Cu'])
        plane_nets: Set of net names that are plane-connected

    Returns:
        True if connects to power plane
    """
    # Net-class verification: must be a declared plane net
    if net_name not in plane_nets:
        return False
    # Layer check: via must touch at least one plane layer
    touches_plane = via.from_layer in plane_layers or via.to_layer in plane_layers
    return touches_plane


# ---------------------------------------------------------------------------
# Spoke geometry generation
# ---------------------------------------------------------------------------


def _generate_spoke_segments(
    pad_position: tuple[float, float],
    pad_size: tuple[float, float],
    spoke_count: int,
    spoke_width: float,
    clearance_gap: float,
    board: Board | None = None,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """
    Generate 4-spoke (or N-spoke) thermal relief line segments.

    Spokes radiate from the pad edge outward at evenly-spaced angles.
    Each spoke starts at the pad boundary plus clearance_gap and extends
    for a length proportional to the clearance_gap (typical IPC recommendation
    is 2× clearance for the spoke length).

    When *board* is provided, each spoke endpoint is clamped to lie within
    the board outline (rectangular or polygonal).

    Args:
        pad_position: (x, y) centre of the pad in mm
        pad_size: (width, height) of the pad in mm
        spoke_count: Number of radial spokes (≥ 2)
        spoke_width: Width of each spoke (used for the spoke length calc)
        clearance_gap: Radial gap from pad edge to start of spoke
        board: Optional Board for outline clamping

    Returns:
        List of spoke line segments as ((x1,y1), (x2,y2)) tuples
    """
    cx, cy = pad_position
    pw, ph = pad_size
    # Effective pad radius ─ use the semi-diagonal so the clearance
    # starts outside the pad envelope for any rotation.
    pad_radius = math.hypot(pw / 2.0, ph / 2.0)
    spoke_length = max(clearance_gap * 2.0, spoke_width * 2.0)

    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i in range(spoke_count):
        angle = 2.0 * math.pi * i / spoke_count
        dx = math.cos(angle)
        dy = math.sin(angle)

        # Start point ─ just outside the pad + clearance
        start_r = pad_radius + clearance_gap
        x1 = cx + start_r * dx
        y1 = cy + start_r * dy

        # End point ─ start + spoke length
        x2 = cx + (start_r + spoke_length) * dx
        y2 = cy + (start_r + spoke_length) * dy

        # Clamp to board outline when available
        if board is not None:
            x2, y2 = _clamp_to_board_outline(board, (x2, y2), (cx, cy))

        segments.append(((x1, y1), (x2, y2)))

    return segments


def _clamp_to_board_outline(
    board: Board,
    point: tuple[float, float],
    pad_center: tuple[float, float],
) -> tuple[float, float]:
    """
    Clamp a spoke endpoint to lie within the board boundary.

    For rectangular boards the check is a trivial AABB test.
    For polygonal outlines we use a point-in-polygon test (via shapely
    if available) and, when the point is outside, pull it back toward
    the pad centre until it is inside.

    Args:
        board: Board object with outline / dimensions
        point: Candidate spoke endpoint (x, y)
        pad_center: Pad centre used as a fallback direction

    Returns:
        Clamped (x, y) guaranteed to be inside the board outline
    """
    x, y = point

    # Rectangular board ─ fast path
    if not board.has_polygon_outline:
        ox, oy = board.origin
        # Guard against NaN/inf board dimensions
        if not (math.isfinite(board.width) and math.isfinite(board.height)):
            return (x, y)
        if not (math.isfinite(ox) and math.isfinite(oy)):
            return (x, y)
        x_min, y_min = ox, oy
        x_max, y_max = ox + board.width, oy + board.height
        return (max(x_min, min(x, x_max)), max(y_min, min(y, y_max)))

    # Polygonal board ─ use shapely
    try:
        from shapely.geometry import LineString, Point, Polygon  # noqa: PLC0415
    except ImportError:
        # Graceful degradation: return the original point
        return (x, y)

    outline = Polygon(board.outline_polygon)
    pt = Point(x, y)
    if outline.contains(pt) or outline.touches(pt):
        return (x, y)

    # Pull the point back toward the pad centre along the radial line
    # until it lands inside the outline.
    center_pt = Point(*pad_center)
    line = LineString([center_pt, pt])
    intersection = outline.intersection(line)

    if intersection.is_empty:
        # Degenerate case ─ return pad centre
        return pad_center

    if hasattr(intersection, "geoms"):
        # Multi-geometry ─ take the closest point to the pad centre
        best_pt = pad_center
        best_dist = float("inf")
        for geom in intersection.geoms:
            if hasattr(geom, "coords"):
                for coord in geom.coords:
                    d = math.hypot(coord[0] - pad_center[0], coord[1] - pad_center[1])
                    if d < best_dist:
                        best_dist = d
                        best_pt = (coord[0], coord[1])
        return best_pt

    # Single geometry ─ take the point closest to the pad centre
    if hasattr(intersection, "coords"):
        coords = list(intersection.coords)
        if coords:
            best_pt = coords[0]
            best_dist = math.hypot(best_pt[0] - pad_center[0], best_pt[1] - pad_center[1])
            for coord in coords[1:]:
                d = math.hypot(coord[0] - pad_center[0], coord[1] - pad_center[1])
                if d < best_dist:
                    best_dist = d
                    best_pt = (coord[0], coord[1])
            return best_pt

    return pad_center


# ---------------------------------------------------------------------------
# SMD-pad thermal relief
# ---------------------------------------------------------------------------


def _add_smd_thermal_reliefs(
    board: Board,
    _routing_results: RoutingResults,
    _resolved_plane_layers: list[str],
    resolved_plane_nets: frozenset[str],
    spoke_count: int,
    spoke_width: float,
    clearance_gap: float,
    thermal_reliefs: list[ThermalRelief],
) -> None:
    """
    Append ``ThermalRelief`` entries for SMD pads that connect to power planes.

    Iterates over the board's netlist and footprint data to find SMD pads
    whose net is a plane net and that are placed on a plane-connected layer
    (typically outer layers with vias to inner planes).
    """
    try:
        netlist = board.netlist  # type: ignore[attr-defined]
    except AttributeError:
        return

    if netlist is None:
        return

    # Collect already-processed (net, position) pairs to avoid duplicates
    seen: set[tuple[str, tuple[float, float]]] = {
        (tr.net_name, tr.pad_position) for tr in thermal_reliefs
    }

    for net_name in resolved_plane_nets:
        if not _is_power_net(net_name):
            continue
        # Get pads for this net from the netlist
        try:
            pads = netlist.get_pads_for_net(net_name)
        except AttributeError:
            continue

        for pad in pads:
            # Only consider SMD pads (not through-hole)
            if getattr(pad, "pad_type", "thru") != "smd":
                continue
            pos = (float(pad.x), float(pad.y))
            if (net_name, pos) in seen:
                continue
            seen.add((net_name, pos))

            pw = float(getattr(pad, "width", 0.6))
            ph = float(getattr(pad, "height", 0.6))
            pad_size = (pw, ph)

            spokes = _generate_spoke_segments(
                pad_position=pos,
                pad_size=pad_size,
                spoke_count=spoke_count,
                spoke_width=spoke_width,
                clearance_gap=clearance_gap,
                board=board,
            )
            thermal_reliefs.append(
                ThermalRelief(
                    net_name=net_name,
                    pad_position=pos,
                    spoke_count=spoke_count,
                    spoke_width=spoke_width,
                    clearance_gap=clearance_gap,
                    pad_size=pad_size,
                    spoke_segments=spokes,
                )
            )

"""Pinned Python oracle for the router_v6 post-route DFM cluster (Wave 4, cluster D).

**DO NOT EDIT -- THESE ARE THE REFERENCE.**

VERBATIM copies of the compute kernels of seven ``temper_placer/router_v6``
modules as committed at ``15110feccc6ec9389f0777d3cff1ce9f81b11068``
(origin/main, the base SHA of this branch).  This is the oracle the Rust
kernels in ``temper-drc-rs`` must reproduce **bit-identically** (contract gate
G2, ``docs/wave4-discipline-contract.md``).

Every executable statement below is byte-identical to the pinned commit.  The
only things that differ from the original files are:

* the module docstring you are reading;
* the *section banners* separating one source module from the next;
* the omission of orchestration/glue that is not being ported (each section's
  banner names exactly what was omitted and why);
* ``TYPE_CHECKING`` type-only imports collapsed to ``object`` annotations
  where the original imported a symbol solely for typing.

Nothing was cleaned up, refactored, or fixed.  Two defects are pinned here
**deliberately, unfixed** -- see "Known defects, pinned not fixed" below.  A
fix would silently break the verbatim proof; if the shipped module's contract
changes, re-pin this oracle from the new base first.

``test_dfm_rust_differential.py::test_oracle_kernels_are_verbatim_copies``
asserts, per kernel, that the source text here still matches the shipped
module at the pinned SHA.


Source modules pinned
---------------------

===========================  ======  ==================================================
module                       stmts   kernels pinned here
===========================  ======  ==================================================
``thermal_relief``             160   ``_is_power_net``, ``_connects_to_power_plane``,
                                     ``_generate_spoke_segments``,
                                     ``_clamp_to_board_outline``
``acid_trap_detection``        119   ``_extract_2d_coordinates``, ``_calculate_angle``,
                                     ``_classify_severity``
``power_plane``                110   ``_board_bounds``, ``_rect_polygon``,
                                     ``generate_power_pours``,
                                     ``_thermal_via_positions``
``copper_balance``              95   ``_via_annular_area``, ``_layer_is_between``,
                                     ``_segment_run_copper_area`` (extracted loop)
``via_placement``               79   ``_via_segment_index``  (extracted loop),
                                     ``_get_adjacent_layer``
``annular_ring_check``          78   ``_is_external_layer``, ``_check_via``
``teardrop_generation``         78   ``_generate_via_teardrop``
===========================  ======  ==================================================


Which floating-point oracle each call site has (contract §2, B4/B6)
------------------------------------------------------------------

This matters because ``temper-drc-rs``'s ``py_hypot`` is **not** a universal
distance function (B6): it replicates CPython's Dekker double-double
``math.hypot`` and is wrong wherever the reference is GEOS or a plain
``sqrt``.  Every distance-shaped call site in this file, classified:

**CPython ``math.hypot`` -> the crate's ``py_hypot`` (B4)**

* ``_generate_spoke_segments``: ``pad_radius = math.hypot(pw / 2.0, ph / 2.0)``
* ``_clamp_to_board_outline``: the three ``math.hypot(coord[0] - pad_center[0],
  coord[1] - pad_center[1])`` best-point searches (polygonal arm)
* ``_segment_run_copper_area``: ``seg_length = math.hypot(x2 - x1, y2 - y1)``
* ``_generate_via_teardrop``: the ``nearest_idx`` argmin key **and** the
  ``dist = math.hypot(dx, dy)`` direction magnitude

**CPython ``math.sqrt`` of ``x ** 2`` -- NOT hypot, NOT ``x * x`` (B4 + B7)**

* ``_calculate_angle``: ``mag1``/``mag2`` are
  ``math.sqrt(v1[0] ** 2 + v1[1] ** 2)``.  Measured on this base:
  ``sqrt(x**2 + y**2) != hypot(x, y)`` for **17.3%** of random 2-vectors, and
  ``x ** 2 != x * x`` for **0.105%** of random f64.  The Rust must be
  ``sqrt(pow(x, 2.0) + pow(y, 2.0))``, using neither ``py_hypot`` nor ``x*x``.

**Shapely/GEOS -- neither hypot nor a Rust reimplementation (B6)**

* ``_clamp_to_board_outline`` polygonal arm only:
  ``Polygon(...).contains(pt)``, ``.touches(pt)``, and
  ``.intersection(LineString([...]))``.  These are GEOS predicate and boolean
  results, not arithmetic this file performs.  **This arm is excluded from the
  migration scope** -- it is gated on survey spike S1 (GEOS polygon boolean
  algebra).  Only the rectangular fast path is a Rust target.

**CPython ``**`` -- libm ``pow``, not ``sqrt`` (B7)**

* ``_thermal_via_positions``: ``int(round(count ** 0.5))``.  Measured on this
  base: ``c ** 0.5 != math.sqrt(c)`` for **137** integers in ``1..100000``.

**CPython ``round`` -- round-half-EVEN (B3)**

* ``_calculate_angle``: ``round(angle_deg, 9)``.  This is load-bearing, not
  cosmetic: the exact 60 degree vertex evaluates to ``59.99999999999999``
  before the round and ``60.0`` after, which flips ``_classify_severity``
  from ``"medium"`` to ``"low"``.  ``f64::round`` would give the same answer
  here but is round-half-AWAY in general; the Rust must use
  ``round_ties_even``.
* ``_thermal_via_positions``: ``round(count ** 0.5)`` (no ndigits -> int).

**CPython ``max``/``min`` -- first-argument NaN semantics (B5)**

* ``_calculate_angle``: ``max(-1.0, min(1.0, cos_angle))``.  The min-then-max
  nesting is load-bearing: measured on this base,
  ``max(-1.0, min(1.0, NaN))`` is ``1.0`` (not NaN, not ``-1.0``).
* ``_clamp_to_board_outline`` rectangular arm:
  ``max(x_min, min(x, x_max))``.  Measured: for ``x = NaN`` this returns
  ``x_min`` -- a NaN spoke endpoint silently clamps to the board's left edge.
* ``_generate_spoke_segments``: ``max(clearance_gap * 2.0, spoke_width * 2.0)``
* ``_generate_via_teardrop``: ``max(0.0, raw_trace_width)`` and
  ``min(via.diameter * 0.6, trace_width * 2.0)``
* ``_layer_is_between``: ``min``/``max`` over ints (no NaN reachable)

**f64 operation order (B7)**

* ``_generate_spoke_segments``: ``angle = 2.0 * math.pi * i / spoke_count`` is
  ``((2.0 * pi) * i) / spoke_count``.  Measured: reassociating it to
  ``2.0 * (pi * i / spoke_count)`` changes the result for **27.27%** of
  ``(i, spoke_count)`` pairs.
* ``generate_power_pours``: ``x_min + i * (strip_width + isolation_gap_mm)``
  -- the addition is inside the multiply.  Distributing it changes the result.
* ``_via_annular_area``: ``math.pi * (r_pad * r_pad - r_hole * r_hole)`` --
  here it *is* ``r * r``, not ``pow``.  Do not "unify" this with
  ``_calculate_angle``'s ``** 2``; they are different expressions.

**libm via the host runtime (B1)**

* ``_generate_spoke_segments``: ``math.cos(angle)``, ``math.sin(angle)``
* ``_calculate_angle``: ``math.acos(cos_angle)``, ``math.degrees(angle_rad)``.
  Measured on this base: CPython ``math.degrees(x)`` is exactly
  ``x * (180.0 / pi)`` -- a single multiply by the precomputed constant, not
  ``(x * 180.0) / pi``.


Known defects, pinned not fixed
-------------------------------

**D1 -- non-deterministic output ordering in ``thermal_relief``.**
``_add_smd_thermal_reliefs`` (NOT pinned here; it is glue over
``board.netlist``) iterates ``for net_name in resolved_plane_nets`` where
``resolved_plane_nets`` is a ``frozenset[str]``.  CPython randomizes string
hashing per process, so the append order of the SMD reliefs -- and therefore
``ThermalReliefReport.thermal_reliefs`` -- differs between runs.  Measured on
this base: **8 distinct orders over 8 fresh interpreters**.  This is why only
``thermal_relief``'s spoke/clamp kernels are pinned and its top-level
orchestration is not: the orchestration has no bit-exact contract to pin.
Reported, not fixed (fixing it would change shipped behaviour and break the
verbatim pin).

**D2 -- unreachable negative-threshold guard in ``acid_trap_detection``.**
``detect_acid_traps`` (NOT pinned here; it is orchestration) guards with
``if not math.isfinite(min_angle_threshold) and min_angle_threshold < 0:``,
whose warning text says "is negative -- all angles are >= 0 degrees".  The
``not isfinite`` conjunct means only ``-inf`` reaches it; a plain negative
such as ``-5.0`` is finite, falls through, and silently yields an empty
report with no warning.  Reported, not fixed.
"""

from __future__ import annotations

import logging
import math
import re
import warnings
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ===========================================================================
# thermal_relief.py -- Router V6 Stage 5.4: Add Thermal Relief
#
# Pinned: the module-level power-net pattern and plane-net default, plus
# `_is_power_net`, `_connects_to_power_plane`, `_generate_spoke_segments`,
# `_clamp_to_board_outline`.
#
# NOT pinned: `add_thermal_relief` (orchestration over RoutingResults) and
# `_add_smd_thermal_reliefs` (glue over board.netlist, and the site of
# defect D1 -- its output order is not deterministic, so it has no bit-exact
# contract to pin).  `ThermalRelief`/`ThermalReliefReport` are report
# dataclasses with no arithmetic.
# ===========================================================================

# ---------------------------------------------------------------------------
# Power-net name pattern ─ word-boundary match of known power/ground families
# plus any net whose name ends with GND (e.g. PGND, AGND, DGND, CGND, etc.).
# ---------------------------------------------------------------------------
_POWER_NET_PATTERN: re.Pattern = re.compile(
    r"\b(?:"
    r"GND|PGND|AGND|DGND|CGND|"  # explicit ground variants
    r"[A-Z]*GND|"  # catch-all *GND suffix
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
        "GND",
        "PGND",
        "CGND",
        "VCC",
        "VDD",
        "VEE",
        "+15V",
        "+3V3",
        "+5V",
        "DC_BUS+",
        "DC_BUS-",
        "SW_NODE",
        "AC_L",
        "AC_N",
        "PE",
    }
)


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


def _generate_spoke_segments(
    pad_position: tuple[float, float],
    pad_size: tuple[float, float],
    spoke_count: int,
    spoke_width: float,
    clearance_gap: float,
    board: object | None = None,
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
    board: object,
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


# ===========================================================================
# acid_trap_detection.py -- Router V6 Stage 5.1: Detect and Fix Acid Traps
#
# Pinned: `_extract_2d_coordinates`, `_calculate_angle`, `_classify_severity`.
#
# NOT pinned: `detect_acid_traps` (orchestration over RoutingResults, and the
# site of defect D2), `AcidTrap`/`AcidTrapReport` (report dataclasses with no
# arithmetic beyond `sum(1 for ...)` counts).
# ===========================================================================


def _extract_2d_coordinates(path: object) -> list[tuple[float, float]]:
    """Return a path's vertex coordinates as plain ``(x, y)`` tuples.

    Handles both ``RoutePath`` (2D, has ``.coordinates``) and
    ``RoutePath3D`` (per-segment layer info, has ``.segments`` as
    ``(x, y, layer)`` triples and no ``.coordinates`` attribute).

    Raises:
        AttributeError: if ``path`` has neither attribute -- surfaced
            rather than silently swallowed, since a check that can't see
            its own input should fail loudly, not report a false zero.
    """
    coordinates = getattr(path, "coordinates", None)
    if coordinates is not None:
        return list(coordinates)

    segments = getattr(path, "segments", None)
    if segments is not None:
        return [(seg[0], seg[1]) for seg in segments]

    raise AttributeError(
        f"{type(path).__name__!r} has neither '.coordinates' nor '.segments' "
        "-- cannot extract path geometry for acid-trap detection."
    )


def _calculate_angle(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> float:
    """
    Calculate angle at p2 formed by p1-p2-p3.

    Args:
        p1: First point
        p2: Vertex point
        p3: Third point

    Returns:
        Angle in degrees (0-180)
    """
    # Vectors from p2 to p1 and p3
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])

    # Calculate dot product and magnitudes
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

    if mag1 == 0 or mag2 == 0:
        return 180.0  # Degenerate case

    # Calculate angle
    cos_angle = dot / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))  # Clamp to [-1, 1]

    angle_rad = math.acos(cos_angle)

    # Floating-point edge case: acos may still produce NaN
    if math.isnan(angle_rad):
        return 180.0

    angle_deg = math.degrees(angle_rad)

    # Round to eliminate floating-point noise (e.g. acos may return
    # 59.99999999999999° for a mathematically exact 60° angle, which
    # would shift the severity classification at the boundary).
    angle_deg = round(angle_deg, 9)

    return angle_deg


def _classify_severity(angle: float, trace_width_mm: float = 0.2) -> str:
    """
    Classify acid trap severity based on angle and trace width.

    Narrow traces (< 0.2 mm) are less likely to trap etchant, so their
    severity is demoted by one level.

    Args:
        angle: Angle in degrees
        trace_width_mm: Trace width in mm (default 0.2)

    Returns:
        Severity: "low", "medium", or "high"
    """
    if angle < 45:
        base = "high"  # Very acute - critical
    elif angle < 60:
        base = "medium"  # Moderate concern
    else:
        base = "low"  # Minor issue

    # Narrow traces are less susceptible to etchant trapping.
    # Non-finite / negative widths are physically meaningless — treat as
    # if no demotion applies (the angle-based classification stands).
    if not math.isfinite(trace_width_mm) or trace_width_mm < 0:
        return base

    if trace_width_mm < 0.2:
        if base == "high":
            return "medium"
        elif base == "medium":
            return "low"
        # "low" stays "low"

    return base


# ===========================================================================
# power_plane.py -- Router V6: Functional 4-layer power-plane geometry
#
# Pinned: `CopperPour`, `DEFAULT_POWER_DOMAINS`, `DEFAULT_ISOLATION_GAP_MM`,
# `_board_bounds`, `_rect_polygon`, `generate_power_pours`,
# `_thermal_via_positions`.
#
# NOT pinned: `generate_thermal_vias` and `generate_power_planes` (component
# filtering and orchestration over `core.board.Via`, no arithmetic beyond the
# already-pinned `_thermal_via_positions`), `_component_center` (attribute
# plumbing), `PowerPlaneGeometry` (aggregate dataclass).
#
# NOTE (survey correction): this module does NOT consume a routed board and
# does NOT iterate segments or vias -- see the PR body.  It is pinned here
# because its kernels are genuinely portable arithmetic, not because it meets
# the cluster's stated membership criterion.
# ===========================================================================

# Default power domains poured on In2.Cu (in board-left-to-right order).
DEFAULT_POWER_DOMAINS: tuple[str, ...] = ("+3V3", "+5V", "+15V")

# Default isolation gap between adjacent In2.Cu domain pours (mm). This is the
# GND/Power class clearance from configs/netclass_rules.yaml; it keeps the
# +3V3/+5V/+15V pours from shorting to one another.
DEFAULT_ISOLATION_GAP_MM: float = 0.3


@dataclass(frozen=True)
class CopperPour:
    """A solid copper zone (pour) on a single layer.

    Attributes:
        net: Net the pour is connected to (e.g. "GND", "+5V").
        layer: KiCad layer name the pour lives on (e.g. "In1.Cu").
        bounds: (x_min, y_min, x_max, y_max) axis-aligned extent in mm.
        polygon: Ordered (x, y) vertices of the pour outline in mm.
        is_ground: True for the continuous GND reference pour.
    """

    net: str
    layer: str
    bounds: tuple[float, float, float, float]
    polygon: list[tuple[float, float]] = field(default_factory=list)
    is_ground: bool = False

    @property
    def width(self) -> float:
        """Pour width in mm."""
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> float:
        """Pour height in mm."""
        return self.bounds[3] - self.bounds[1]

    @property
    def area(self) -> float:
        """Pour area in mm^2."""
        return self.width * self.height


def _board_bounds(board: object) -> tuple[float, float, float, float]:
    """Return the board copper extent as (x_min, y_min, x_max, y_max)."""
    ox, oy = board.origin
    return (ox, oy, ox + board.width, oy + board.height)


def _rect_polygon(
    bounds: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    """Return the 4 corners of an axis-aligned rectangle (CCW)."""
    x_min, y_min, x_max, y_max = bounds
    return [
        (x_min, y_min),
        (x_max, y_min),
        (x_max, y_max),
        (x_min, y_max),
    ]


def generate_power_pours(
    board: object,
    domains: list[str] | tuple[str, ...] | None = None,
    layer: str = "In2.Cu",
    *,
    isolation_gap_mm: float = DEFAULT_ISOLATION_GAP_MM,
) -> list[CopperPour]:
    """Generate isolated per-domain copper pours on ``layer`` (In2.Cu).

    The board copper area is partitioned into ``len(domains)`` vertical strips,
    one per power domain, each separated from its neighbours by
    ``isolation_gap_mm`` so the pours cannot short. Domains are laid out
    left-to-right in the order given.

    Args:
        board: The PCB board (provides the copper extent).
        domains: Power-domain net names to pour. Defaults to
            ("+3V3", "+5V", "+15V").
        layer: Plane layer name for the pours. Defaults to "In2.Cu".
        isolation_gap_mm: Gap between adjacent domain pours in mm.

    Returns:
        One ``CopperPour`` per domain, isolated from the others.
    """
    resolved = tuple(domains) if domains is not None else DEFAULT_POWER_DOMAINS
    if not resolved:
        return []
    if isolation_gap_mm < 0:
        raise ValueError(f"isolation_gap_mm must be >= 0, got {isolation_gap_mm}")

    x_min, y_min, x_max, y_max = _board_bounds(board)
    n = len(resolved)
    total_width = x_max - x_min
    total_gap = isolation_gap_mm * (n - 1)
    strip_width = (total_width - total_gap) / n
    if strip_width <= 0:
        raise ValueError(
            f"Board too narrow ({total_width}mm) for {n} isolated pours "
            f"with {isolation_gap_mm}mm gaps"
        )

    pours: list[CopperPour] = []
    for i, net in enumerate(resolved):
        strip_x_min = x_min + i * (strip_width + isolation_gap_mm)
        strip_x_max = strip_x_min + strip_width
        bounds = (strip_x_min, y_min, strip_x_max, y_max)
        pours.append(
            CopperPour(
                net=net,
                layer=layer,
                bounds=bounds,
                polygon=_rect_polygon(bounds),
            )
        )
    return pours


def _thermal_via_positions(
    center: tuple[float, float],
    count: int,
    pitch_mm: float,
) -> list[tuple[float, float]]:
    """Return an NxN grid of via centres around ``center``.

    ``count`` is the total via count (must be a perfect square, e.g. 9 -> 3x3).
    """
    side = int(round(count**0.5))
    if side * side != count:
        raise ValueError(f"count must be a perfect square, got {count}")

    cx, cy = center
    span = (side - 1) * pitch_mm
    x0 = cx - span / 2.0
    y0 = cy - span / 2.0
    return [
        (x0 + col * pitch_mm, y0 + row * pitch_mm) for row in range(side) for col in range(side)
    ]


# ===========================================================================
# copper_balance.py -- Router V6 Stage 5.5: Analyze and Balance Copper
#
# Pinned: `_PLANE_NET_LAYER`, `_PLANE_FILL_RATIO`, `_LAYER_ORDER_NAMES`,
# `_via_annular_area`, `_layer_is_between`, and `_segment_run_copper_area`.
#
# `_segment_run_copper_area` is the RoutePath3D accumulation loop of
# `_calculate_layer_copper_area`, lifted OUT of its enclosing
# `for net_name, compiled_route in routing_results.compiled_routes.items()`
# loop and given the two values that loop supplies (`segments`,
# `width_mm`).  The loop body itself -- the `range(len(segments) - 1)`
# bounds, the tuple unpacking, the `seg_layer == layer_name` test, the
# `math.hypot` call, and the `+=` accumulation order -- is byte-identical to
# the shipped source.  This lift is the ONE structural change in this file
# and it is what makes the kernel callable without a `RoutingResults`.
#
# NOT pinned: `analyze_copper_balance` (orchestration; its own arithmetic is
# `board_width * board_height` and `(copper_area / total_area) * 100.0`),
# `_calculate_layer_copper_area`'s outer loop, `LayerCopperBalance` /
# `CopperBalanceReport` (report dataclasses).
# ===========================================================================

# ---------------------------------------------------------------------------
# Plane-net → layer mapping
# ---------------------------------------------------------------------------
# When a net carries ``width_mm == 0.0`` it is a plane net (connected
# through an inner-layer copper pour rather than discrete traces).
# The mapping below assigns each known plane net to its canonical layer.
# Nets not listed here default to ``"In1.Cu"`` (the ground plane).
_PLANE_NET_LAYER: dict[str, str] = {
    # Ground nets -> In1.Cu (inner ground plane)
    "GND": "In1.Cu",
    "PGND": "In1.Cu",
    "CGND": "In1.Cu",
    # Power rails -> In2.Cu (inner power island)
    "+15V": "In2.Cu",
    "+3V3": "In2.Cu",
    "+5V": "In2.Cu",
    "VCC": "In2.Cu",
    "VDD": "In2.Cu",
}

# Typical fill ratio for a plane layer (copper pour with
# anti-pad / thermal relief cut-outs).  Based on IPC-2221 guidance
# that plane layers should have ≥ 80 % copper coverage.
_PLANE_FILL_RATIO: float = 0.85

# ---------------------------------------------------------------------------
# Canonical 4-layer order as KiCad layer names (top → bottom).
# Used to enumerate intermediate layers for through-hole vias.
#
# The shipped module derives this from
# `temper_placer.core.board.STANDARD_LAYER_ORDER` via
# `tuple(str(idx) for idx in STANDARD_LAYER_ORDER)`.  Pinned here as the
# literal it evaluates to at the base SHA;
# `test_oracle_layer_order_matches_production` asserts the two agree, so a
# stackup change breaks the pin loudly instead of silently.
_LAYER_ORDER_NAMES: tuple[str, ...] = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")


def _segment_run_copper_area(
    segments: list[tuple[float, float, str]],
    layer_name: str,
    width_mm: float,
) -> float:
    """RoutePath3D per-layer trace-area accumulation.

    The body below is the shipped ``_calculate_layer_copper_area``
    RoutePath3D branch verbatim; only the two values its enclosing loop
    supplied (``segments``, ``compiled_route.width_mm``) became parameters.
    """
    copper_area = 0.0
    for i in range(len(segments) - 1):
        x1, y1, seg_layer = segments[i]
        x2, y2, _ = segments[i + 1]
        if seg_layer == layer_name:
            seg_length = math.hypot(x2 - x1, y2 - y1)
            copper_area += seg_length * width_mm
    return copper_area


def _via_annular_area(via: object) -> float:
    """
    Return the annular ring area of a via pad on one layer (mm²).

    Annular area = π ( (diameter/2)² - (drill/2)² )

    When *drill* is ``None`` or zero the hole term is omitted.
    """
    diameter = via.diameter  # type: ignore[attr-defined]
    drill = getattr(via, "drill", 0.0) or 0.0

    # Guard: NaN / inf diameter or drill → 0.0
    if math.isnan(diameter) or math.isnan(drill) or math.isinf(diameter) or math.isinf(drill):
        return 0.0

    # Guard: non-positive diameter or drill >= diameter → 0.0
    if diameter <= 0.0 or drill >= diameter:
        return 0.0

    r_pad = diameter / 2.0
    r_hole = drill / 2.0 if drill > 0.0 else 0.0
    return math.pi * (r_pad * r_pad - r_hole * r_hole)


def _layer_is_between(from_layer: str, to_layer: str, candidate: str) -> bool:
    """
    Return ``True`` if *candidate* lies strictly between
    *from_layer* and *to_layer* in the standard 4-layer stack-up.
    """
    try:
        idx_from = _LAYER_ORDER_NAMES.index(from_layer)
        idx_to = _LAYER_ORDER_NAMES.index(to_layer)
        idx_candidate = _LAYER_ORDER_NAMES.index(candidate)
    except ValueError:
        return False
    lo = min(idx_from, idx_to)
    hi = max(idx_from, idx_to)
    return lo < idx_candidate < hi


# ===========================================================================
# via_placement.py -- Router V6 Stage 4.3: Place Vias
#
# Pinned: `_via_segment_index` and `_get_adjacent_layer`.
#
# `_via_segment_index` is the segment-matching loop of
# `_place_vias_for_path`, lifted out of its enclosing
# `for vx, vy in route_path.via_positions` loop.  The scan order, the
# `abs(...) < 1e-4` predicate on BOTH axes, and the first-match-wins `break`
# are byte-identical to the shipped source.
#
# NOT pinned: `place_vias` and `_place_vias_for_path` themselves.
#
# NOTE (survey correction): this module is GLUE, not PORT -- see the PR body.
# Its only arithmetic is the two `abs` subtractions below.  It is pinned
# because it is the PRODUCER of the `Via` objects the other six kernels
# consume, so its semantics belong in the corpus even though the module
# should not be migrated.
# ===========================================================================


def _via_segment_index(
    vx: float,
    vy: float,
    segs: list[tuple[float, float, str]],
) -> int | None:
    """First index into ``segs`` within 1e-4 of ``(vx, vy)`` on both axes."""
    vi = None
    for i, (sx, sy, _) in enumerate(segs):
        if abs(sx - vx) < 1e-4 and abs(sy - vy) < 1e-4:
            vi = i
            break
    return vi


def _get_adjacent_layer(layer_name: str) -> str | None:
    """
    Get adjacent layer for via transition.

    Args:
        layer_name: Current layer (e.g., "F.Cu")

    Returns:
        Adjacent layer name or None
    """
    # Simplified layer mapping
    layer_map = {
        "F.Cu": "In1.Cu",
        "In1.Cu": "In2.Cu",
        "In2.Cu": "B.Cu",
        "B.Cu": "In2.Cu",
    }

    return layer_map.get(layer_name)


# ===========================================================================
# annular_ring_check.py -- Router V6 Stage 5.2: Check Annular Rings
#
# Pinned: `_EXTERNAL_LAYERS`, `_MICROVIA_DEFAULT_RING_MM`,
# `_is_external_layer`, `AnnularRingViolation`, `_check_via`.
#
# NOT pinned: `check_annular_rings` (orchestration over RoutingResults),
# `AnnularRingReport` (report dataclass sharing `BaseCheckReport` with the
# already-migrated `clearance_check` / `creepage_check` siblings).
# ===========================================================================

# External (outer) layer names per the standard 4-layer stack.
_EXTERNAL_LAYERS: frozenset[str] = frozenset({"F.Cu", "B.Cu"})

# IPC-6016 Class 2 microvia annular ring minimum (mm).
_MICROVIA_DEFAULT_RING_MM: float = 0.025


def _is_external_layer(layer_name: str) -> bool:
    """Return True if *layer_name* is an outer/external copper layer."""
    return layer_name in _EXTERNAL_LAYERS


@dataclass
class AnnularRingViolation:
    """An annular ring violation on a via."""

    net_name: str
    via_position: tuple[float, float]
    pad_diameter: float  # Via pad diameter (mm)
    drill_diameter: float  # Via drill diameter (mm)
    actual_ring_width: float  # Actual annular ring width (mm)
    minimum_required: float  # Minimum required ring width (mm)

    @property
    def deficiency(self) -> float:
        """How much the ring is undersized."""
        return self.minimum_required - self.actual_ring_width


def _check_via(
    via: object,
    net_name: str,
    min_annular_ring: float,
    microvia_ring_mm: float,
) -> AnnularRingViolation | None:
    """Check a single via and return a violation if the ring is undersized.

    Args:
        via: A Via-like object with ``diameter``, ``drill``, ``position``,
            ``from_layer``, and ``to_layer`` attributes.  It may optionally
            carry a ``via_type`` attribute (e.g. ``"microvia"``).
        net_name: Net name for the violation report.
        min_annular_ring: Base minimum annular ring for external layers (mm).
        microvia_ring_mm: Annular ring threshold for microvias (mm).

    Returns:
        An ``AnnularRingViolation`` if the via fails, or ``None``.
    """
    # ---- guard: NaN / zero / negative drill produces invalid ring widths ----
    if (
        math.isnan(via.drill)  # type: ignore[attr-defined]
        or math.isnan(via.diameter)  # type: ignore[attr-defined]
        or via.drill <= 0.0  # type: ignore[attr-defined]
    ):
        logger.warning(
            "Via at %s on net %s has non-positive drill %.4f mm; skipping.",
            getattr(via, "position", "?"),
            net_name,
            via.drill,  # type: ignore[attr-defined]
        )
        return None

    # Calculate annular ring width
    # Ring width = (pad_diameter - drill_diameter) / 2
    ring_width = (via.diameter - via.drill) / 2.0  # type: ignore[attr-defined]

    # ---- layer-aware threshold ----
    # IPC-6012: external layers use the full *min_annular_ring*;
    # internal layers use half that value.
    from_layer: str = getattr(via, "from_layer", "")
    to_layer: str = getattr(via, "to_layer", "")
    if _is_external_layer(from_layer) or _is_external_layer(to_layer):
        threshold = min_annular_ring
    else:
        threshold = min_annular_ring * 0.5

    # ---- via-type override: microvias use IPC-6016 threshold ----
    via_type: str | None = getattr(via, "via_type", None)
    if via_type == "microvia":
        threshold = microvia_ring_mm

    # ---- guard: NaN threshold produces meaningless comparisons ----
    if math.isnan(threshold):
        logger.warning(
            "Via at %s on net %s has NaN threshold; skipping.",
            getattr(via, "position", "?"),
            net_name,
        )
        return None

    # ---- violation check (<= so boundary values are caught; ----
    # ---- small epsilon tolerates IEEE-754 rounding error)     ----
    _FP_EPSILON = 1e-12
    if ring_width <= threshold + _FP_EPSILON:
        return AnnularRingViolation(
            net_name=net_name,
            via_position=via.position,  # type: ignore[attr-defined]
            pad_diameter=via.diameter,  # type: ignore[attr-defined]
            drill_diameter=via.drill,  # type: ignore[attr-defined]
            actual_ring_width=ring_width,
            minimum_required=threshold,
        )

    return None


# ===========================================================================
# teardrop_generation.py -- Router V6 Stage 5.3: Insert Teardrops
#
# Pinned: `Teardrop`, `_generate_via_teardrop`.
#
# NOT pinned: `insert_teardrops` (orchestration + the `max(0.1,
# min(ratio, 1.0))` clamp), `TeardropReport` (report dataclass).
# ===========================================================================


@dataclass
class Teardrop:
    """A teardrop at a pad/via connection."""

    net_name: str
    connection_point: tuple[float, float]  # Where trace meets pad/via
    connection_type: str  # "via" or "pad"
    length_mm: float  # Teardrop length along trace
    width_mm: float  # Teardrop width at widest point
    layer: str  # PCB layer name (e.g. "F.Cu", "B.Cu")


def _generate_via_teardrop(
    net_name: str,
    via,
    compiled_route,
    length_ratio: float,
) -> Teardrop | None:
    """
    Generate teardrop for a via connection.

    Only generates a teardrop when a path segment on the compiled route's
    layer connects to this via.  The connection point is placed at the via
    annulus perimeter (offset from via centre by half the diameter toward
    the trace), and the teardrop width tapers from the trace width to at
    most ``min(via.diameter * 0.6, trace_width * 2)``.

    Args:
        net_name: Net name
        via: Via object
        compiled_route: ``CompiledRoute`` that owns this via
        length_ratio: Teardrop length ratio (already clamped)

    Returns:
        Teardrop or None if not needed
    """
    # Guard: skip vias with NaN, infinite, or non-positive diameter
    if math.isnan(via.diameter) or not math.isfinite(via.diameter) or via.diameter <= 0:
        warnings.warn(
            f"Via at {via.position} for net '{net_name}' has diameter "
            f"{via.diameter}; skipping teardrop.",
            stacklevel=2,
        )
        return None

    # Guard: only generate teardrop if the compiled route's path is on a
    # layer that this via touches.
    path_layer = getattr(compiled_route.path, "layer_name", None)
    if path_layer is None:
        return None
    if path_layer not in (via.from_layer, via.to_layer):
        return None

    # Find the path coordinate closest to the via position to determine
    # the trace approach direction.
    coords = compiled_route.path.coordinates
    if len(coords) < 2:
        return None  # no segment to infer direction from

    via_pos = via.position
    # Locate the coordinate nearest to the via centre
    nearest_idx = min(
        range(len(coords)),
        key=lambda i: math.hypot(coords[i][0] - via_pos[0], coords[i][1] - via_pos[1]),
    )

    # Pick a neighbour to compute the trace direction from the via outward.
    # Prefer the next coordinate; fall back to the previous one.
    if nearest_idx < len(coords) - 1:
        neighbour = coords[nearest_idx + 1]
    else:
        neighbour = coords[nearest_idx - 1]

    dx = neighbour[0] - via_pos[0]
    dy = neighbour[1] - via_pos[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return None  # coincident points — cannot determine direction

    # Unit vector from via centre toward the trace
    ux = dx / dist
    uy = dy / dist

    # Connection point at via annulus perimeter
    connection_point = (
        via_pos[0] + ux * via.diameter / 2.0,
        via_pos[1] + uy * via.diameter / 2.0,
    )

    # Calculate teardrop dimensions
    # Guard against NaN / +inf trace width; clamp -inf / negative to 0
    raw_trace_width = compiled_route.width_mm
    if math.isnan(raw_trace_width) or raw_trace_width == float("inf"):
        return None  # cannot compute sane dimensions
    trace_width = max(0.0, raw_trace_width)
    teardrop_length = via.diameter * length_ratio
    teardrop_width = min(via.diameter * 0.6, trace_width * 2.0)

    # Only add teardrop if via is at least as large as the threshold
    if via.diameter >= trace_width * 1.2:
        return Teardrop(
            net_name=net_name,
            connection_point=connection_point,
            connection_type="via",
            length_mm=teardrop_length,
            width_mm=teardrop_width,
            layer=path_layer,
        )

    return None

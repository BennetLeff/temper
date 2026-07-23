"""
Router V6: Functional 4-layer power-plane geometry.

Generates the copper geometry that turns the four copper layers into a
*functional* stackup (W2 / U4):

- ``generate_ground_pour``  -> one solid GND pour on the In1.Cu reference plane.
- ``generate_power_pours``  -> isolated per-domain pours (+3V3/+5V/+15V) on In2.Cu.
- ``generate_thermal_vias`` -> a 3x3 via array under the Q1/Q2 IGBT collectors
  stitching the F.Cu collector to the B.Cu DC_BUS+ thermal pour.

The deterministic ``deterministic/stages/power_plane.py`` stage already *marks*
power/ground nets for plane connectivity; this module produces the actual
``CopperPour`` / ``Via`` geometry consumed by the manufacturing stage.

Requirements: R4 (power-plane pours + thermal), R5 (via strategy) from
docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.core.board import Via

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component

logger = logging.getLogger(__name__)

# Default power domains poured on In2.Cu (in board-left-to-right order).
DEFAULT_POWER_DOMAINS: tuple[str, ...] = ("+3V3", "+5V", "+15V")

# Net the thermal pour / via array connects the IGBT collectors to.
THERMAL_NET: str = "DC_BUS+"

# Reference designators of the IGBTs whose collectors need a thermal via array.
IGBT_REFS: frozenset[str] = frozenset({"Q1", "Q2"})

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


@dataclass(frozen=True)
class PowerPlaneGeometry:
    """Aggregated power-plane geometry produced for a board."""

    ground_pour: CopperPour
    power_pours: list[CopperPour]
    thermal_vias: list[Via]

    @property
    def via_count(self) -> int:
        """Total thermal vias stamped."""
        return len(self.thermal_vias)


def _board_bounds(board: Board) -> tuple[float, float, float, float]:
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


def generate_ground_pour(board: Board, layer: str = "In1.Cu") -> CopperPour:
    """Generate one solid GND copper pour covering the full board on ``layer``.

    In1.Cu is the continuous ground reference plane for the 4-layer stackup;
    the single uninterrupted pour is what the USB diff-pair (U5) references.

    Args:
        board: The PCB board (provides the copper extent).
        layer: Plane layer name for the pour. Defaults to "In1.Cu".

    Returns:
        A single ``CopperPour`` on ``layer`` for the "GND" net.
    """
    bounds = _board_bounds(board)
    return CopperPour(
        net="GND",
        layer=layer,
        bounds=bounds,
        polygon=_rect_polygon(bounds),
        is_ground=True,
    )


def generate_power_pours(
    board: Board,
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


def _component_center(component: Component) -> tuple[float, float] | None:
    """Return a component's placed centre, preferring collector-pad position."""
    pos = getattr(component, "initial_position", None)
    if pos is None:
        return None
    return (float(pos[0]), float(pos[1]))


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


def generate_thermal_vias(
    board: Board,  # noqa: ARG001 - kept for signature symmetry / future outline clamping
    components: list[Component],
    count: int = 9,
    layer_from: str = "F.Cu",
    layer_to: str = "B.Cu",
    *,
    net: str = THERMAL_NET,
    diameter_mm: float = 0.6,
    drill_mm: float = 0.3,
    pitch_mm: float = 1.2,
) -> list[Via]:
    """Stamp a thermal via array under each IGBT collector.

    A square grid of ``count`` vias (default 3x3) is placed under every
    component in ``components`` whose reference designates an IGBT (Q1/Q2),
    stitching the F.Cu collector down to the B.Cu ``DC_BUS+`` thermal pour so
    Q1/Q2 heat has a low-resistance path to the bottom-side copper.

    Args:
        board: The PCB board (unused for placement but kept for symmetry and
            future outline clamping).
        components: Candidate components; only IGBT refs (Q1/Q2) get an array.
        count: Total vias per component. Must be a perfect square. Default 9.
        layer_from: Top layer of each via. Default "F.Cu".
        layer_to: Bottom layer of each via. Default "B.Cu".
        net: Net the vias belong to. Default "DC_BUS+".
        diameter_mm: Via annular diameter in mm. Default 0.6.
        drill_mm: Via drill diameter in mm. Default 0.3.
        pitch_mm: Grid pitch between adjacent vias in mm. Default 1.2.

    Returns:
        A flat list of ``Via`` objects for every stamped array.
    """
    if diameter_mm <= drill_mm:
        raise ValueError(f"diameter_mm ({diameter_mm}) must exceed drill_mm ({drill_mm})")

    vias: list[Via] = []
    layers = (layer_from, layer_to)
    for component in components:
        ref = getattr(component, "ref", "")
        if ref not in IGBT_REFS:
            continue
        center = _component_center(component)
        if center is None:
            logger.warning("Thermal vias: %s has no placed position; skipping", ref)
            continue
        for pos in _thermal_via_positions(center, count, pitch_mm):
            vias.append(
                Via(
                    position=pos,
                    drill=drill_mm,
                    width=diameter_mm,
                    layers=layers,
                    net=net,
                )
            )
    return vias


def generate_power_planes(
    board: Board,
    components: list[Component],
    *,
    domains: list[str] | tuple[str, ...] | None = None,
    ground_layer: str = "In1.Cu",
    power_layer: str = "In2.Cu",
    thermal_via_count: int = 9,
) -> PowerPlaneGeometry:
    """Generate the full functional power-plane geometry for a board.

    Convenience orchestration used by the router pipeline: one GND pour on
    In1.Cu, per-domain pours on In2.Cu, and the Q1/Q2 thermal via arrays.

    Args:
        board: The PCB board.
        components: Placed components (used to find the IGBTs).
        domains: Power domains for In2.Cu pours. Defaults to the standard trio.
        ground_layer: Layer for the GND pour. Default "In1.Cu".
        power_layer: Layer for the domain pours. Default "In2.Cu".
        thermal_via_count: Vias per IGBT array. Default 9 (3x3).

    Returns:
        A ``PowerPlaneGeometry`` bundling the ground pour, power pours, and
        thermal vias.
    """
    ground_pour = generate_ground_pour(board, layer=ground_layer)
    power_pours = generate_power_pours(board, domains, layer=power_layer)
    thermal_vias = generate_thermal_vias(board, components, count=thermal_via_count)
    return PowerPlaneGeometry(
        ground_pour=ground_pour,
        power_pours=power_pours,
        thermal_vias=thermal_vias,
    )

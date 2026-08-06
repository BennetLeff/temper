"""
Router V6 Quality: Via Counting (U2)

Counts signal vias, thermal vias, and stitching vias on a routed PCB.
Gate: signal vias <= 100 (provisional threshold).

Thermal vias: those under Q1/Q2 footprint on DC_BUS+.
Stitching vias: those around board edges on GND.

Part of temper-7rqf (Stage 6 - Quality Gate)

Wave 4 Phase B (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
the four path-taking public functions (``count_signal_vias``,
``count_thermal_vias``, ``count_stitching_vias``, ``classify_vias``)
delegate to the cluster-F via-classification kernel in
``temper_quality_oracle`` (PR #750), which accepts a scenario dict or a
``.kicad_pcb`` path and re-parses internally through the same
``parse_kicad_pcb`` this module's own ``_parse_pcb`` called.

``classify_vias_from_parse`` -- the one real (non-test) production caller in
this module, used by ``validation/human_reference_extractor.py`` -- is
deliberately **not** wired: it is handed an already-parsed ``ParseResult``
object, and the kernel boundary that builds a parsed-board view from a
Python argument accepts only a scenario dict or a path-like value, not a
pre-parsed object -- there is no wire format for it. Delegating here would
either break that caller (a ``TypeError`` for an unrecognised board source)
or require hand-marshalling ``ParseResult`` into a scenario dict in Python,
duplicating a Rust-side conversion path that is itself unused today. Left
unwired, along with ``_classify_vias`` and its four bbox/geometry
sub-helpers that ``classify_vias_from_parse`` still needs -- each has its
own scenario-or-path kernel counterpart in ``temper_quality_oracle``, also
ledgered in ``.unwired-kernel-inventory`` for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import temper_quality_oracle as _rs

from temper_placer.router_v6.net_classification import is_ground_net, is_signal_net

if TYPE_CHECKING:
    from temper_placer.io._kicad_types import ParseResult, ViaData
    from temper_placer.router_v6.routing_results import CompiledRoute


@dataclass(frozen=True)
class ViaCounts:
    """Classified via counts from a routed PCB."""

    signal: int
    thermal: int
    stitching: int
    total: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def count_signal_vias(routed_pcb_path: Path) -> int:
    """Count vias on signal nets (excluding thermal and stitching vias).

    Thermal vias: those under Q1/Q2 footprint on DC_BUS+.
    Stitching vias: those around board edges on GND.

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.

    Returns:
        Number of signal vias.
    """
    signal, _thermal, _stitching, _total = _rs.via_count_classify_vias_py(routed_pcb_path)
    return signal


def count_thermal_vias(routed_pcb_path: Path) -> int:
    """Count thermal vias separately (under Q1/Q2).

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.

    Returns:
        Number of thermal vias.
    """
    _signal, thermal, _stitching, _total = _rs.via_count_classify_vias_py(routed_pcb_path)
    return thermal


def count_stitching_vias(routed_pcb_path: Path) -> int:
    """Count stitching vias separately (board-edge GND vias).

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.

    Returns:
        Number of stitching vias.
    """
    _signal, _thermal, stitching, _total = _rs.via_count_classify_vias_py(routed_pcb_path)
    return stitching


def classify_vias(routed_pcb_path: Path) -> ViaCounts:
    """Classify all vias on a routed PCB into signal, thermal, and stitching.

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.

    Returns:
        ViaCounts with breakdown of signal, thermal, and stitching vias.
    """
    signal, thermal, stitching, total = _rs.via_count_classify_vias_py(routed_pcb_path)
    return ViaCounts(signal=signal, thermal=thermal, stitching=stitching, total=total)


def classify_vias_from_parse(parse_result: ParseResult) -> ViaCounts:
    """Classify all vias in a ParseResult (for reuse by human_reference_extractor).

    Args:
        parse_result: Parsed PCB data.

    Returns:
        ViaCounts with breakdown of signal, thermal, and stitching vias.

    Not delegated to Rust: the caller here already holds a parsed
    ``ParseResult``, and the kernel boundary
    (``temper_quality_oracle::cluster_f::bindings::build_view``) accepts only
    a scenario dict or a ``.kicad_pcb`` path -- see the module docstring.
    """
    return _classify_vias(parse_result)


# ---------------------------------------------------------------------------
# Internal helpers
#
# Used only by classify_vias_from_parse (see the module docstring for why
# that entry point stays pure Python), so these stay unwired too.
# ---------------------------------------------------------------------------


def _classify_vias(result: ParseResult) -> ViaCounts:
    """Classify all vias in a ParseResult.

    - Thermal: vias under Q1/Q2 footprint on DC_BUS+.
    - Stitching: vias around board edges on GND.
    - Signal: all other vias.
    """
    _THERMAL_COMPONENTS = frozenset({"Q1", "Q2"})
    _THERMAL_NET = "DC_BUS+"
    _STITCHING_EDGE_MARGIN_MM = 5.0  # Board-edge margin for stitching detection

    if not result.vias:
        return ViaCounts(signal=0, thermal=0, stitching=0, total=0)

    # Get Q1/Q2 component bboxes for thermal via detection
    thermal_bboxes = _get_component_bboxes(result, _THERMAL_COMPONENTS)

    # Get board edges for stitching via detection
    board_bbox = _get_board_bbox(result)

    thermal = 0
    stitching = 0

    for via in result.vias:
        via_net = via.net or ""

        # Thermal via: under Q1/Q2 footprint on DC_BUS+
        if via_net.upper() == _THERMAL_NET.upper():
            # Check if via is within any Q1/Q2 bbox
            is_thermal = _is_via_in_bbox(via, thermal_bboxes) if thermal_bboxes else False
            if is_thermal:
                thermal += 1
                continue

        # Stitching via: around board edges on GND
        if is_ground_net(via_net):
            if board_bbox and _is_via_near_board_edge(via, board_bbox, _STITCHING_EDGE_MARGIN_MM):
                stitching += 1
                continue

    total = len(result.vias)
    # "signal" is the residual class, by construction: every via that is not
    # thermal and not stitching. This deliberately includes vias on power/HV
    # nets, so the three counts always partition `total`.
    #
    # There used to be a per-via `signal` accumulator here, guarded by
    # `is_signal_net(via_net)` and then unconditionally overwritten by the
    # line below -- a dead store that made this function look as though it
    # excluded non-signal nets from the signal count when it never did
    # (issue #752 defect 10). Removed; the residual definition is the real
    # one and is now pinned by tests.
    signal = total - thermal - stitching

    return ViaCounts(signal=signal, thermal=thermal, stitching=stitching, total=total)


def _get_component_bboxes(
    result: ParseResult,
    refs: frozenset[str],
) -> list[tuple[float, float, float, float]]:
    """Get bounding boxes for components with given refs (x_min, y_min, x_max, y_max).

    Uses the component's initial_position and bounds to compute the bbox in
    board-absolute coordinates.
    """
    bboxes: list[tuple[float, float, float, float]] = []
    for comp in result.netlist.components:
        if comp.ref in refs and comp.initial_position is not None:
            cx, cy = comp.initial_position
            half_w = comp.width / 2.0
            half_h = comp.height / 2.0
            x_min = cx - half_w
            y_min = cy - half_h
            x_max = cx + half_w
            y_max = cy + half_h
            bboxes.append((x_min, y_min, x_max, y_max))
    return bboxes


def _get_board_bbox(
    result: ParseResult,
) -> tuple[float, float, float, float] | None:
    """Get the board bounding box (x_min, y_min, x_max, y_max)."""
    board = result.board
    if board is None:
        return None
    return (0.0, 0.0, float(board.width), float(board.height))


def _is_via_in_bbox(
    via: ViaData,
    bboxes: list[tuple[float, float, float, float]],
) -> bool:
    """Check if a via's position is within any of the given bboxes."""
    x, y = via.position
    return any(x_min <= x <= x_max and y_min <= y <= y_max for x_min, y_min, x_max, y_max in bboxes)


def _is_via_near_board_edge(
    via: ViaData,
    board_bbox: tuple[float, float, float, float],
    margin_mm: float,
) -> bool:
    """Check if a via is within ``margin_mm`` of any board edge."""
    x, y = via.position
    x_min, y_min, x_max, y_max = board_bbox
    left_dist = x - x_min
    right_dist = x_max - x
    bottom_dist = y - y_min
    top_dist = y_max - y
    min_edge_dist = min(left_dist, right_dist, bottom_dist, top_dist)
    return min_edge_dist <= margin_mm


# ---------------------------------------------------------------------------
# Additional API: working with RoutingResults
# ---------------------------------------------------------------------------


def count_signal_vias_from_routing(
    compiled_routes: dict[str, CompiledRoute],
) -> tuple[int, list, list, list]:
    """Count signal vias from compiled routes (for QualityGate integration).

    Classifies vias by net name alone (no position/board context available).

    Args:
        compiled_routes: dict of net_name -> CompiledRoute.

    Returns:
        (signal_count, signal_vias, thermal_stitching_vias, all_vias)
    """
    from temper_placer.router_v6.via_placement import Via

    signal_vias: list[Via] = []
    non_signal_vias: list[Via] = []
    all_vias: list[Via] = []

    for route in compiled_routes.values():
        for via in route.vias:
            all_vias.append(via)
            if is_signal_net(via.net_name):
                signal_vias.append(via)
            else:
                non_signal_vias.append(via)

    return len(signal_vias), signal_vias, non_signal_vias, all_vias

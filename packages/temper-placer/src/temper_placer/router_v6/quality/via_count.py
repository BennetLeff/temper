"""
Router V6 Quality: Via Counting (U2)

Counts signal vias, thermal vias, and stitching vias on a routed PCB.
Gate: signal vias <= 100 (provisional threshold).

Thermal vias: those under Q1/Q2 footprint on DC_BUS+.
Stitching vias: those around board edges on GND.

Part of temper-7rqf (Stage 6 - Quality Gate)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.router_v6.net_classification import is_ground_net, is_signal_net

if TYPE_CHECKING:
    from temper_placer.io._kicad_types import ParseResult, ViaData


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
    result = _parse_pcb(routed_pcb_path)
    counts = _classify_vias(result)
    return counts.signal


def count_thermal_vias(routed_pcb_path: Path) -> int:
    """Count thermal vias separately (under Q1/Q2).

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.

    Returns:
        Number of thermal vias.
    """
    result = _parse_pcb(routed_pcb_path)
    counts = _classify_vias(result)
    return counts.thermal


def count_stitching_vias(routed_pcb_path: Path) -> int:
    """Count stitching vias separately (board-edge GND vias).

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.

    Returns:
        Number of stitching vias.
    """
    result = _parse_pcb(routed_pcb_path)
    counts = _classify_vias(result)
    return counts.stitching


def classify_vias(routed_pcb_path: Path) -> ViaCounts:
    """Classify all vias on a routed PCB into signal, thermal, and stitching.

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.

    Returns:
        ViaCounts with breakdown of signal, thermal, and stitching vias.
    """
    result = _parse_pcb(routed_pcb_path)
    return _classify_vias(result)


def classify_vias_from_parse(parse_result: ParseResult) -> ViaCounts:
    """Classify all vias in a ParseResult (for reuse by human_reference_extractor).

    Args:
        parse_result: Parsed PCB data.

    Returns:
        ViaCounts with breakdown of signal, thermal, and stitching vias.
    """
    return _classify_vias(parse_result)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_pcb(pcb_path: Path) -> ParseResult:
    """Parse a KiCad PCB file. Returns ParseResult with vias, pads, components."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    return parse_kicad_pcb(Path(pcb_path))


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

    signal = 0
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

        # Signal via: everything else (including valid signal nets)
        if is_signal_net(via_net):
            signal += 1
        else:
            # Via on non-signal net (ground/power/HV) that isn't thermal/stitching
            # — still count these outside the signal group
            pass

    total = len(result.vias)
    # Ensure signal count covers all remaining vias not classified as thermal/stitching
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
        if comp.ref in refs:
            if comp.initial_position is not None:
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
    return (0.0, 0.0, float(board.width_mm), float(board.height_mm))


def _is_via_in_bbox(
    via: ViaData,
    bboxes: list[tuple[float, float, float, float]],
) -> bool:
    """Check if a via's position is within any of the given bboxes."""
    x, y = via.position
    for x_min, y_min, x_max, y_max in bboxes:
        if x_min <= x <= x_max and y_min <= y <= y_max:
            return True
    return False


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
    compiled_routes: dict[str, object],
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

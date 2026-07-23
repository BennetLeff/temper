"""Internal: trace, via, and segment extraction from KiCad board objects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from temper_placer.io._kicad_types import TraceData, ViaData

if TYPE_CHECKING:
    from kiutils.board import Board as KiBoard


def _extract_traces_from_pcb(
    ki_board: KiBoard, _warnings: list[str], net_map: dict[str, str] | None = None
) -> list[TraceData]:
    """
    Extract copper trace segments from board.

    Args:
        ki_board: Parsed board.
        warnings: List for warning messages.
        net_map: Dictionary mapping net ID (str) to net name.

    Returns:
        List of TraceData.
    """
    if net_map is None:
        net_map = {}

    traces = []
    for track in ki_board.traceItems:
        if hasattr(track, "start") and hasattr(track, "end"):
            net_name = None
            if track.net:
                if hasattr(track.net, "name") and track.net.name:
                    net_name = track.net.name
                else:
                    net_id = str(track.net)
                    if hasattr(track.net, "number"):
                        net_id = str(track.net.number)

                    net_name = net_map.get(net_id)

                    if not net_name:
                        net_name = net_id

            traces.append(
                TraceData(
                    start=(track.start.X, track.start.Y),
                    end=(track.end.X, track.end.Y),
                    width=track.width,
                    layer=track.layer,
                    net=net_name,
                )
            )
    return traces


def _extract_vias_from_pcb(
    ki_board: KiBoard, _warnings: list[str], net_map: dict[str, str] | None = None
) -> list[ViaData]:
    """
    Extract vias from board.

    Args:
        ki_board: Parsed board.
        warnings: List for warning messages.
        net_map: Dictionary mapping net ID to name.

    Returns:
        List of ViaData.
    """
    if net_map is None:
        net_map = {}

    vias: list = []
    for track in ki_board.traceItems:
        if hasattr(track, "position") and not hasattr(track, "start"):
            net_name = None
            if track.net:
                if hasattr(track.net, "name") and track.net.name:
                    net_name = track.net.name
                else:
                    net_id = (
                        str(track.net.number) if hasattr(track.net, "number") else str(track.net)
                    )
                    net_name = net_map.get(net_id, net_id)

            vias.append(
                ViaData(
                    position=(track.position.X, track.position.Y),
                    diameter=track.size,
                    drill=track.drill or 0.4,
                    net=net_name,
                    layers=tuple(track.layers) if hasattr(track, "layers") else ("F.Cu", "B.Cu"),
                )
            )
    return vias

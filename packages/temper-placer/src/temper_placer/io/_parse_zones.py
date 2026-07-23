"""Internal: zone extraction from KiCad board objects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from temper_placer.core.board import Zone

if TYPE_CHECKING:
    from kiutils.board import Board as KiBoard


def _extract_zones_from_pcb(
    ki_board: KiBoard, x_min: float, y_min: float, warnings: list[str]
) -> list[Zone]:
    """Extract zone definitions from a KiCad board.

    Args:
        ki_board: Parsed kiutils Board instance.
        x_min: Board origin X for coordinate normalization.
        y_min: Board origin Y for coordinate normalization.
        warnings: List to append any issues found.

    Returns:
        List of Zone objects.
    """
    zones: list = []
    for ki_zone in ki_board.zones:
        if ki_zone.polygons:
            poly = ki_zone.polygons[0]
            pts = (
                getattr(poly, "points", None)
                or getattr(poly, "pts", None)
                or getattr(poly, "coordinates", [])
            )
            x_pts = [p.X - x_min for p in pts]
            y_pts = [p.Y - y_min for p in pts]
            if x_pts and y_pts:
                bounds = (min(x_pts), min(y_pts), max(x_pts), max(y_pts))
                polygon = list(zip(x_pts, y_pts))

                bbox_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
                poly_area = 0.0
                if len(polygon) > 2:
                    for i in range(len(polygon)):
                        j = (i + 1) % len(polygon)
                        poly_area += polygon[i][0] * polygon[j][1]
                        poly_area -= polygon[j][0] * polygon[i][1]
                    poly_area = abs(poly_area) / 2.0

                if bbox_area > 0 and abs(bbox_area - poly_area) / bbox_area > 0.05:
                    warnings.append(
                        f"Zone '{ki_zone.name or 'Unnamed'}' is non-rectangular. "
                        f"Approximating polygon (area={poly_area:.1f}) with bounding box (area={bbox_area:.1f})."
                    )

                zones.append(
                    Zone(
                        name=ki_zone.name or f"Zone_{len(zones)}",
                        bounds=bounds,
                        net_classes=[ki_zone.netName] if ki_zone.netName else ["Signal"],
                        polygon=polygon,
                        layers=ki_zone.layers if hasattr(ki_zone, "layers") else ["F.Cu"],
                    )
                )
    return zones

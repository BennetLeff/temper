"""Guard strip geometry. @req(2026-06-23-001, FR3, FR5)"""

from shapely.geometry import Polygon


def compute_guard_strip(outline: Polygon, width_mm: float) -> tuple[Polygon, Polygon, Polygon]:
    """Split outline into ``(hv_region, lv_region, corridor)``.

    LV is the shrunken interior; HV and corridor are the ring-shaped guard
    strip. ``width_mm=0`` returns ``(empty, outline, empty)``; a width
    larger than half the shortest side returns ``(outline, empty, outline)``.
    """
    if not isinstance(outline, Polygon):
        raise ValueError("outline must be a shapely Polygon")
    if outline.exterior is None or not outline.exterior.is_closed:
        raise ValueError("outline must be a closed polygon")
    if width_mm == 0:
        return Polygon(), outline, Polygon()
    inner = outline.buffer(-width_mm)
    if inner.is_empty:
        return outline, Polygon(), outline
    corridor = outline.difference(inner)
    return corridor, inner, corridor


__all__ = ["compute_guard_strip"]

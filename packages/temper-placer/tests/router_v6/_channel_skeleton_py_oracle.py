"""Pinned Python oracle for the channel-skeleton medial-axis migration.

DO NOT EDIT -- THESE ARE THE REFERENCE.
=======================================
``_extract_medial_axis`` and ``_extract_medial_axis_single`` below are a
**verbatim** ``git show`` extraction from commit
``580b8dce4574cc37108477fd8fd70a46d54d9ddd``
(``fix/constraint-model-edge-identity``, which does not touch
``channel_skeleton.py`` -- the file is unchanged there from
``origin/main`` at ``0cd6a3a39``, itself unchanged since
``550cab2a3``, the last commit to touch it before this migration) of
``temper_placer/router_v6/channel_skeleton.py``.

Nothing has been cleaned up, refactored, or fixed *by this file*.
``test_channel_skeleton_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts each definition from the pinned commit and compares the source
text character for character.

Why these two functions, and not the whole file
--------------------------------------------------
These are the entirety of the medial-axis compute this migration ports to
Rust (``packages/temper-geometry/src/channel_skeleton.rs``):
boundary sampling, an independent Voronoi diagram, the interior-edge
filter, and both fallback branches.

Not pinned here, and NOT migrated (JUSTIFIED-KEEP for this pull -- see the
module doc in ``channel_skeleton.rs`` and
``docs/evidence/2026-08-07-channel-skeleton-triage-no-port.md``):

* ``_ensure_skeleton_connectivity`` -- ``nx.Graph`` bookkeeping (an O(n^2)
  nearest-pair search over networkx node/component objects). The
  differential below imports this LIVE from the shipped module (it is
  unchanged by this migration -- both the oracle arm and the Rust arm feed
  their lines through the same, unmodified connectivity pass), not
  re-pinned here.
* ``ChannelSkeletonStage`` / ``validate_channel_skeleton`` -- pipeline
  ``Stage`` / ``@register_validator`` orchestration wiring. Not copied here
  at all, so importing this oracle module never re-registers a duplicate
  "ChannelSkeleton" validator.
* ``extract_channel_skeleton``'s pad-anchoring block -- dict/list
  bookkeeping over ``ParsedPCB.components``/``pins``, orchestration.
"""

from __future__ import annotations

from shapely.geometry import LineString, MultiLineString, MultiPoint, Point, Polygon
from shapely.ops import voronoi_diagram

# ===========================================================================
# VERBATIM from channel_skeleton.py @ 580b8dce4574cc37108477fd8fd70a46d54d9ddd
# ===========================================================================


def _extract_medial_axis(
    polygon_or_multipolygon,
    simplify_tolerance: float = 0.5,
) -> list[LineString]:
    """
    Extract medial axis using Voronoi diagram approach.

    Args:
        polygon_or_multipolygon: Available routing area
        simplify_tolerance: Simplification tolerance

    Returns:
        List of LineStrings representing skeleton
    """
    from shapely.geometry import MultiPolygon, Polygon

    # Handle MultiPolygon
    if isinstance(polygon_or_multipolygon, MultiPolygon):
        all_lines = []

        if hasattr(polygon_or_multipolygon, "geoms"):
            polys = list(polygon_or_multipolygon.geoms)
        else:
            polys = [polygon_or_multipolygon]

        # Combine skeletons from all polygons
        for p in polys:
            lines = _extract_medial_axis_single(p, simplify_tolerance)
            print(f"  Extracted {len(lines)} skeleton lines")
            all_lines.extend(lines)
        return all_lines
    elif isinstance(polygon_or_multipolygon, Polygon):
        return _extract_medial_axis_single(polygon_or_multipolygon, simplify_tolerance)
    else:
        return []


def _extract_medial_axis_single(
    polygon: Polygon,
    simplify_tolerance: float = 0.5,
) -> list[LineString]:
    """
    Extract medial axis for a single polygon using simplified approach.

    Args:
        polygon: Single polygon
        simplify_tolerance: Simplification tolerance

    Returns:
        List of LineStrings
    """
    # Simplified medial axis: use buffer -> unbuffer technique
    # This creates an approximation of the medial axis

    # Get the polygon boundary
    boundary = polygon.boundary

    # Create points along the boundary for Voronoi
    # Sample points every ~1mm
    points = []

    # Check for multi-part geometry first (hasattr(coords) returns True but raises error)
    # Collect geometry parts
    parts = []
    parts = list(boundary.geoms) if hasattr(boundary, "geoms") else [boundary]

    # Sample points along the boundary of each part
    for part in parts:
        try:
            coords = list(part.coords)
        except (NotImplementedError, AttributeError):
            continue

        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]

            # Calculate distance
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dist = (dx**2 + dy**2) ** 0.5

            # Add intermediate points
            num_points = max(2, int(dist))
            for j in range(num_points):
                t = j / num_points
                x = p1[0] + t * dx
                y = p1[1] + t * dy
                points.append(Point(x, y))

    if len(points) < 3:
        # Not enough points for Voronoi
        # Return simplified centerline
        centroid = polygon.centroid
        return [LineString([centroid.coords[0], centroid.coords[0]])]

    # Create Voronoi diagram
    try:
        voronoi = voronoi_diagram(MultiPoint(points), edges=True)

        # Flatten geometry collection
        raw_lines = []
        if hasattr(voronoi, "geoms"):
            for g in voronoi.geoms:
                if isinstance(g, MultiLineString):
                    raw_lines.extend(list(g.geoms))
                elif isinstance(g, LineString):
                    raw_lines.append(g)
        elif isinstance(voronoi, MultiLineString):
            raw_lines.extend(list(voronoi.geoms))
        elif isinstance(voronoi, LineString):
            raw_lines.append(voronoi)

        # Filter Voronoi edges that are inside the polygon
        skeleton_lines = []

        # Stage 2 quick-win: pre-build the buffered polygon and a
        # prepared geometry once, instead of re-buffering on every
        # Voronoi edge.  The original code did
        # ``polygon.buffer(1e-3).contains(midpoint)`` per edge
        # (~5000 calls across the closure test, ~1.9s in the
        # sampling profile).  The buffered polygon is a no-op
        # geometry build (cheap), but ``.contains`` on a
        # non-prepared geometry is the slow part.  With a
        # prepared geometry the contains check is ~6x faster.
        import shapely.prepared

        buffered_polygon = polygon.buffer(1e-3)
        prepped_buffered = shapely.prepared.prep(buffered_polygon)

        for geom in raw_lines:
            if isinstance(geom, LineString):
                # Check if line is mostly inside polygon.  Use
                # the prepared buffered geometry for the contains
                # check (6x faster than ``polygon.buffer().contains()``
                # per call).
                midpoint = geom.interpolate(0.5, normalized=True)
                if prepped_buffered.contains(midpoint):
                    # Simplify the line
                    simplified = geom.simplify(simplify_tolerance)
                    if simplified.length > 0:
                        skeleton_lines.append(simplified)

        if skeleton_lines:
            return skeleton_lines

    except Exception:
        # Voronoi failed, use fallback
        pass

    # Fallback: return polygon centroid as a simple skeleton
    centroid = polygon.centroid
    bounds = polygon.bounds  # (minx, miny, maxx, maxy)

    # Create simple cross pattern through centroid
    cx, cy = centroid.x, centroid.y
    minx, miny, maxx, maxy = bounds

    # Inset by a small amount to ensure endpoints are inside the polygon
    # Use 10% of width/height or 0.5mm, whichever is smaller
    width = maxx - minx
    height = maxy - miny
    inset_x = min(0.5, width * 0.1)
    inset_y = min(0.5, height * 0.1)

    return [
        LineString([(minx + inset_x, cy), (maxx - inset_x, cy)]),  # Horizontal
        LineString([(cx, miny + inset_y), (cx, maxy - inset_y)]),  # Vertical
    ]


# ===========================================================================
# END VERBATIM
# ===========================================================================

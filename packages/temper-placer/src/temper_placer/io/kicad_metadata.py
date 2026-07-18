"""
Extract typed metadata from KiCad PCB files.

This module provides strongly-typed extraction of courtyards, pad sizes,
and other physical metadata needed for deterministic placement and routing.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from kiutils.board import Board as KiBoard

from temper_placer.core.courtyard import Courtyard

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PadSize:
    """Physical dimensions of a component pad.

    Attributes:
        component_ref: Component reference designator (e.g., "U1")
        pad_number: Pad number/name (e.g., "1", "A1")
        width: Pad width in mm
        height: Pad height in mm
        shape: Pad shape (e.g., "circle", "rect", "oval")
    """

    component_ref: str
    pad_number: str
    width: float
    height: float
    shape: str


@dataclass(frozen=True)
class KiCadMetadata:
    """Complete metadata extracted from a KiCad PCB file.

    This contains all physical information needed for deterministic
    placement and routing with DRC awareness.

    Attributes:
        courtyards: Map from component reference to courtyard polygon
        pad_sizes: Map from (component_ref, pad_number) to pad dimensions
        board_width: Board width in mm
        board_height: Board height in mm
    """

    courtyards: dict[str, Courtyard]
    pad_sizes: dict[tuple[str, str], PadSize]
    board_width: float
    board_height: float

    def __post_init__(self):
        """Validate metadata consistency."""
        if self.board_width <= 0 or self.board_height <= 0:
            raise ValueError(
                f"Board dimensions must be positive: {self.board_width}x{self.board_height}"
            )

        # Validate all courtyards reference valid components
        for ref, courtyard in self.courtyards.items():
            if courtyard.component_ref != ref:
                raise ValueError(
                    f"Courtyard key mismatch: key='{ref}' vs courtyard.component_ref='{courtyard.component_ref}'"
                )


def extract_kicad_metadata(pcb_path: Path) -> KiCadMetadata:
    """Extract courtyards, pad sizes, and board dimensions from KiCad PCB.

    This function parses the KiCad PCB file and extracts physical metadata
    needed for deterministic placement and routing:

    1. Component courtyards (F.CrtYd/B.CrtYd layers)
       - Fallback to pad bounding box if no courtyard defined
    2. Pad sizes for accurate via blocking
    3. Board dimensions

    Args:
        pcb_path: Path to .kicad_pcb file

    Returns:
        KiCadMetadata with all extracted information

    Raises:
        FileNotFoundError: If PCB file doesn't exist
        ValueError: If PCB has invalid structure
    """
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    logger.info(f"Extracting metadata from {pcb_path}")

    # Load KiCad board using kiutils
    raw_board = KiBoard.from_file(str(pcb_path))

    # Extract board dimensions from Edge.Cuts geometry
    board_width, board_height = _extract_board_dimensions(raw_board)

    # Extract pad sizes
    pad_sizes = _extract_pad_sizes(raw_board)
    logger.info(f"Extracted {len(pad_sizes)} pad sizes")

    # Extract courtyards
    courtyards = _extract_courtyards(raw_board)
    logger.info(f"Extracted {len(courtyards)} courtyards")

    return KiCadMetadata(
        courtyards=courtyards,
        pad_sizes=pad_sizes,
        board_width=board_width,
        board_height=board_height,
    )


def _extract_board_dimensions(raw_board: KiBoard) -> tuple[float, float]:
    """Parse board dimensions from Edge.Cuts graphic items.

    Handles GrPoly, GrRect, GrLine, GrCircle, and GrArc items
    on the Edge.Cuts layer. Computes the bounding box of all
    edge geometry and returns (width, height) in mm.

    Raises:
        ValueError: If no Edge.Cuts geometry is found or it
            degenerates to zero area — fail-closed, per the
            anti-false-zero discipline: never silently default
            to a hardcoded guess.
    """
    from kiutils.items.gritems import GrArc, GrCircle, GrLine, GrPoly, GrRect

    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    found = False

    for item in raw_board.graphicItems or []:
        if not (hasattr(item, "layer") and item.layer == "Edge.Cuts"):
            continue

        if isinstance(item, GrPoly):
            coords = getattr(item, "coordinates", None) or []
            for pt in coords:
                x, y = pt.X, pt.Y
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
            if coords:
                found = True

        elif isinstance(item, GrRect):
            sx, sy = item.start.X, item.start.Y
            ex, ey = item.end.X, item.end.Y
            min_x = min(min_x, sx, ex)
            max_x = max(max_x, sx, ex)
            min_y = min(min_y, sy, ey)
            max_y = max(max_y, sy, ey)
            found = True

        elif isinstance(item, GrLine):
            min_x = min(min_x, item.start.X, item.end.X)
            max_x = max(max_x, item.start.X, item.end.X)
            min_y = min(min_y, item.start.Y, item.end.Y)
            max_y = max(max_y, item.start.Y, item.end.Y)
            found = True

        elif isinstance(item, GrCircle):
            cx, cy = item.center.X, item.center.Y
            ex, ey = item.end.X, item.end.Y
            r = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
            min_x = min(min_x, cx - r)
            max_x = max(max_x, cx + r)
            min_y = min(min_y, cy - r)
            max_y = max(max_y, cy + r)
            found = True

        elif isinstance(item, GrArc):
            for pt in (item.start, item.mid, item.end):
                min_x = min(min_x, pt.X)
                max_x = max(max_x, pt.X)
                min_y = min(min_y, pt.Y)
                max_y = max(max_y, pt.Y)
            found = True

    if not found:
        raise ValueError(
            "No Edge.Cuts geometry found in the board. "
            "Board dimensions cannot be determined — a valid PCB "
            "must have a board outline on the Edge.Cuts layer."
        )

    width = max_x - min_x
    height = max_y - min_y

    if width <= 0 or height <= 0:
        raise ValueError(
            f"Edge.Cuts geometry degenerates to zero area "
            f"(width={width}, height={height}). "
            f"Board outline must define a non-zero rectangle."
        )

    return width, height


def _extract_pad_sizes(raw_board: KiBoard) -> dict[tuple[str, str], PadSize]:
    """Extract pad dimensions from all footprints.

    Args:
        raw_board: Parsed KiCad board

    Returns:
        Map from (component_ref, pad_number) to PadSize
    """
    pad_sizes: dict[tuple[str, str], PadSize] = {}

    if not raw_board.footprints:
        logger.warning("No footprints found in board")
        return pad_sizes

    for fp in raw_board.footprints:
        ref = fp.properties.get("Reference", "")
        if not ref:
            continue

        for pad in fp.pads:
            pad_num = pad.number if hasattr(pad, "number") else ""
            if not pad_num:
                continue

            # Get pad dimensions
            width = pad.size.X if hasattr(pad.size, "X") else 0.0
            height = pad.size.Y if hasattr(pad.size, "Y") else 0.0
            shape = pad.shape if hasattr(pad, "shape") else "rect"

            pad_sizes[(ref, pad_num)] = PadSize(
                component_ref=ref,
                pad_number=pad_num,
                width=width,
                height=height,
                shape=shape,
            )

    return pad_sizes


def _extract_courtyards(raw_board: KiBoard) -> dict[str, Courtyard]:
    """Extract courtyard polygons from all footprints.

    Extraction strategy:
    1. Try to find F.CrtYd or B.CrtYd graphic items
    2. Fallback to bounding box of pads + margin
    3. Ultimate fallback: 1mm x 1mm square

    Args:
        raw_board: Parsed KiCad board

    Returns:
        Map from component reference to Courtyard
    """
    courtyards: dict[str, Courtyard] = {}

    if not raw_board.footprints:
        logger.warning("No footprints found in board")
        return courtyards

    for fp in raw_board.footprints:
        ref = fp.properties.get("Reference", "")
        if not ref:
            continue

        points = []

        # Strategy 1: Look for CrtYd graphic items.
        #
        # VERIFIED 2026-07-17: the vast majority of real KiCad footprints
        # draw their courtyard using fp_rect (108/149 on the production
        # board), fp_line rectangles (28/149), or fp_circle (6/149) -- NOT
        # fp_poly. The old code only handled `.points`/`.coordinates`
        # (an fp_poly-only shape), so it matched 0/149 footprints on this
        # board despite 142/149 having real F.CrtYd graphics, silently
        # falling through to the pad-bounding-box approximation below for
        # every one of them. That approximation is not just imprecise --
        # it is centered on the footprint origin and sized from pads only,
        # so it misses courtyard margin entirely and is wildly wrong for
        # components where the mechanical body extends past the pads (a
        # 35mm-diameter radial capacitor's real courtyard is a ~17.75mm-
        # radius circle offset 5mm from the footprint origin; its pad-bbox
        # fallback was a tiny centered 15mm x 5mm box). This was the root
        # cause of CourtyardCheckStage's internal geometry model
        # disagreeing with kicad-cli's real DRC even after the STRtree
        # indexing bug was fixed. See docs/solutions/logic-errors/
        # courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md.
        if fp.graphicItems:
            from kiutils.items.fpitems import FpArc, FpCircle, FpLine, FpPoly, FpRect
            from shapely.geometry import MultiPoint, Point
            from shapely.geometry import Polygon as ShapelyPolygon
            from shapely.ops import unary_union

            shapes = []
            hull_points: list[tuple[float, float]] = []

            for item in fp.graphicItems:
                if not (hasattr(item, "layer") and item.layer in ("F.CrtYd", "B.CrtYd")):
                    continue

                if isinstance(item, FpPoly):
                    pts = getattr(item, "coordinates", None) or getattr(item, "points", None)
                    if pts:
                        shapes.append(ShapelyPolygon([(p.X, p.Y) for p in pts]))
                elif isinstance(item, FpCircle):
                    cx, cy = item.center.X, item.center.Y
                    radius = ((item.end.X - cx) ** 2 + (item.end.Y - cy) ** 2) ** 0.5
                    shapes.append(Point(cx, cy).buffer(radius, quad_segs=32))
                elif isinstance(item, FpRect):
                    # start/end are opposite (diagonal) corners, not two
                    # points on the same edge -- must expand to all 4
                    # corners before hulling, or two diagonal points
                    # degenerate to a line instead of a rectangle.
                    sx, sy = item.start.X, item.start.Y
                    ex, ey = item.end.X, item.end.Y
                    hull_points.extend([(sx, sy), (ex, sy), (ex, ey), (sx, ey)])
                elif isinstance(item, FpLine):
                    hull_points.append((item.start.X, item.start.Y))
                    hull_points.append((item.end.X, item.end.Y))
                elif isinstance(item, FpArc):
                    # Coarse polyline approximation via the arc's 3
                    # defining points -- not geometrically exact, but
                    # closer than dropping arc-based courtyards entirely
                    # (none observed on the production board yet).
                    hull_points.append((item.start.X, item.start.Y))
                    hull_points.append((item.mid.X, item.mid.Y))
                    hull_points.append((item.end.X, item.end.Y))

            if hull_points:
                shapes.append(MultiPoint(hull_points).convex_hull)

            if shapes:
                merged = unary_union(shapes) if len(shapes) > 1 else shapes[0]
                if merged.geom_type == "Polygon" and len(merged.exterior.coords) >= 3:
                    points = list(merged.exterior.coords)
                elif merged.geom_type != "Polygon":
                    hull = merged.convex_hull
                    if hull.geom_type == "Polygon" and len(hull.exterior.coords) >= 3:
                        points = list(hull.exterior.coords)

        # Strategy 2: Fallback to pad bounding box
        if not points and fp.pads:
            min_x, min_y = float("inf"), float("inf")
            max_x, max_y = float("-inf"), float("-inf")
            has_pads = False

            for pad in fp.pads:
                # Pad position is relative to footprint center
                px, py = pad.position.X, pad.position.Y
                w, h = pad.size.X, pad.size.Y

                # Expand by half size + large margin for safety
                margin = 0.5  # mm
                min_x = min(min_x, px - w / 2 - margin)
                min_y = min(min_y, py - h / 2 - margin)
                max_x = max(max_x, px + w / 2 + margin)
                max_y = max(max_y, py + h / 2 + margin)
                has_pads = True

            if has_pads:
                # Create rectangular polygon CENTERED at (0,0)
                # This matches state.placements which tracks geometric center
                half_w = (max_x - min_x) / 2.0
                half_h = (max_y - min_y) / 2.0

                points = [
                    (-half_w, -half_h),
                    (half_w, -half_h),
                    (half_w, half_h),
                    (-half_w, half_h),
                ]

        # Strategy 3: Ultimate fallback - 1mm x 1mm square
        if not points:
            points = [
                (-0.5, -0.5),
                (0.5, -0.5),
                (0.5, 0.5),
                (-0.5, 0.5),
            ]
            logger.warning(f"Using fallback courtyard for {ref} (no CrtYd layer or pads found)")

        courtyards[ref] = Courtyard(component_ref=ref, points=points)

    return courtyards

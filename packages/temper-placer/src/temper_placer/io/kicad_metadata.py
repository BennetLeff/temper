"""
Extract typed metadata from KiCad PCB files.

This module provides strongly-typed extraction of courtyards, pad sizes,
and other physical metadata needed for deterministic placement and routing.

Migrated to the Rust parse engine (``temper_design_bundle_python.parse_engine``,
Wave 4 Phase 3 candidate 3). What moved to Rust (``parse_engine.extract_metadata_raw``):

- board dimensions from Edge.Cuts (fail-closed);
- pad sizes;
- the raw courtyard inputs (fp_poly coords, fp_circle center+end, fp_rect
  corners, fp_line/fp_arc points) per component reference.

What deliberately stays Python (R3-style boundary, argued in VERIFICATION.md):
the courtyard POLYGON computation. It uses shapely/GEOS
(``Point.buffer``/``MultiPoint.convex_hull``/``unary_union``), which is NOT
reimplementable in Rust bit-exactly (measured 169/169 mismatches for a simpler
geometry op; see MIGRATION_PHASE_GUIDE "Numerical traps"). Both differential
arms feed the IDENTICAL shapely code with the IDENTICAL raw inputs (the Rust
engine's, proven bit-identical to kiutils' by the differential), so the GEOS
outputs are equal by construction.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import temper_design_bundle_python as _tdb

from temper_placer.core.courtyard import Courtyard

_rs = _tdb.parse_engine

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

    raw = _rs.extract_metadata_raw(pcb_path.read_text(encoding="utf-8"))

    board_width = raw["board_width"]
    board_height = raw["board_height"]

    pad_sizes = {}
    for (ref, pad_num), entry in raw["pad_sizes"].items():
        # entry: [pos_x, pos_y, w, h, shape] (the first two feed the
        # courtyard fallback below).
        pad_sizes[(ref, pad_num)] = PadSize(
            component_ref=ref,
            pad_number=pad_num,
            width=entry[2],
            height=entry[3],
            shape=entry[4],
        )
    logger.info(f"Extracted {len(pad_sizes)} pad sizes")

    courtyards = {}
    pad_bbox_by_ref = _pad_bbox_by_ref(raw.get("pad_bbox_inputs", {}))
    for ref, inputs in raw["courtyard_inputs"].items():
        points = _courtyard_points_from_raw(inputs)
        if not points and ref in pad_bbox_by_ref:
            # Strategy-2 fallback: pad bbox + 0.5 mm margin over ALL pads
            # (the oracle iterates `for pad in fp.pads:` -- unnumbered pads
            # included; `pad_sizes` above excludes them, so the bbox inputs
            # are carried separately by the engine).
            points = _pad_bbox_fallback(pad_bbox_by_ref[ref])
        if not points:
            points = [
                (-0.5, -0.5),
                (0.5, -0.5),
                (0.5, 0.5),
                (-0.5, 0.5),
            ]
            logger.warning(f"Using fallback courtyard for {ref} (no CrtYd layer or pads found)")

        courtyards[ref] = Courtyard(component_ref=ref, points=points)
    logger.info(f"Extracted {len(courtyards)} courtyards")

    return KiCadMetadata(
        courtyards=courtyards,
        pad_sizes=pad_sizes,
        board_width=board_width,
        board_height=board_height,
    )


def _pad_bbox_by_ref(raw_pad_bbox: dict) -> dict[str, list[tuple[float, float, float, float]]]:
    """Group the engine's per-ref pad-bbox inputs ([x, y, w, h] entries over
    ALL pads, numbered and unnumbered) by component ref."""
    by_ref: dict[str, list[tuple[float, float, float, float]]] = {}
    for ref, entries in raw_pad_bbox.items():
        by_ref[ref] = [(e[0], e[1], e[2], e[3]) for e in entries]
    return by_ref


def _courtyard_points_from_raw(inputs: list[dict]) -> list[tuple[float, float]]:
    """Port of the oracle's Strategy-1 courtyard extraction over the Rust
    engine's raw shape inputs.

    The shapely/GEOS step is the reason this function stays Python (see the
    module docstring). Every input is a dict produced by
    ``parse_engine.extract_metadata_raw``:
      {"kind": "poly", "coords": [(x, y), ...]}
      {"kind": "circle", "center": (x, y), "end": (x, y)}
      {"kind": "rect", "start": (x, y), "end": (x, y)}
      {"kind": "line", "start": (x, y), "end": (x, y)}
      {"kind": "arc", "start": (x, y), "mid": (x, y), "end": (x, y)}
    """
    from shapely.geometry import MultiPoint, Point
    from shapely.geometry import Polygon as ShapelyPolygon
    from shapely.ops import unary_union

    shapes = []
    hull_points: list[tuple[float, float]] = []

    for item in inputs:
        kind = item["kind"]
        if kind == "poly":
            shapes.append(ShapelyPolygon(item["coords"]))
        elif kind == "circle":
            cx, cy = item["center"]
            ex, ey = item["end"]
            radius = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
            shapes.append(Point(cx, cy).buffer(radius, quad_segs=32))
        elif kind == "rect":
            sx, sy = item["start"]
            ex, ey = item["end"]
            hull_points.extend([(sx, sy), (ex, sy), (ex, ey), (sx, ey)])
        elif kind == "line":
            hull_points.append(item["start"])
            hull_points.append(item["end"])
        elif kind == "arc":
            hull_points.append(item["start"])
            hull_points.append(item["mid"])
            hull_points.append(item["end"])

    if hull_points:
        shapes.append(MultiPoint(hull_points).convex_hull)

    if shapes:
        merged = unary_union(shapes) if len(shapes) > 1 else shapes[0]
        if merged.geom_type == "Polygon" and len(merged.exterior.coords) >= 3:
            return list(merged.exterior.coords)
        elif merged.geom_type != "Polygon":
            hull = merged.convex_hull
            if hull.geom_type == "Polygon" and len(hull.exterior.coords) >= 3:
                return list(hull.exterior.coords)
    return []


def _pad_bbox_fallback(pads: list[tuple[float, float, float, float]]) -> list[tuple[float, float]]:
    """Port of the oracle's Strategy-2 fallback: pad bounding box + 0.5 mm
    margin, centered at the footprint origin."""
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    has_pads = False
    margin = 0.5  # mm

    for px, py, w, h in pads:
        min_x = min(min_x, px - w / 2 - margin)
        min_y = min(min_y, py - h / 2 - margin)
        max_x = max(max_x, px + w / 2 + margin)
        max_y = max(max_y, py + h / 2 + margin)
        has_pads = True

    if not has_pads:
        return []

    half_w = (max_x - min_x) / 2.0
    half_h = (max_y - min_y) / 2.0
    return [
        (-half_w, -half_h),
        (half_w, -half_h),
        (half_w, half_h),
        (-half_w, half_h),
    ]

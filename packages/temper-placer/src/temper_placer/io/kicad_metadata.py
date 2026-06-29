"""
Extract typed metadata from KiCad PCB files.

This module provides strongly-typed extraction of courtyards, pad sizes,
and other physical metadata needed for deterministic placement and routing.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from kiutils.board import Board as KiBoard

from temper_placer.deterministic.geometry.courtyard import Courtyard

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

    # Extract board dimensions
    # TODO: Parse from edge cuts - for now use defaults
    board_width = 100.0  # mm
    board_height = 150.0  # mm

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

        # Strategy 1: Look for CrtYd graphic items
        if fp.graphicItems:
            for item in fp.graphicItems:
                if hasattr(item, "layer") and item.layer in ("F.CrtYd", "B.CrtYd"):
                    # Handle Polygon/Polyline
                    pts = []
                    if hasattr(item, "points"):  # kiutils ~1.0
                        pts = item.points
                    elif hasattr(item, "coordinates"):
                        pts = item.coordinates

                    if pts:
                        points = [(p.X, p.Y) for p in pts]
                        break  # Found courtyard

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

"""
KiCad footprint parser - extract courtyard bounds from .kicad_mod files.

This module parses KiCad footprint files to extract courtyard polygons,
which define the physical extent of a component for placement purposes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class FootprintParseError(Exception):
    """Error parsing a KiCad footprint file."""

    pass


@dataclass
class FootprintBounds:
    """
    Bounding box extracted from footprint courtyard.

    Attributes:
        width: Courtyard width in mm.
        height: Courtyard height in mm.
        center_offset: (x, y) offset of courtyard center from footprint origin.
    """

    width: float
    height: float
    center_offset: tuple[float, float] = (0.0, 0.0)


def parse_footprint_courtyard(path: Path) -> FootprintBounds:
    """
    Parse a KiCad footprint file and extract courtyard bounds.

    Args:
        path: Path to .kicad_mod file.

    Returns:
        FootprintBounds with width, height, and center offset.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        FootprintParseError: If the file is invalid or has no courtyard.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Footprint file not found: {path}")

    try:
        content = path.read_text()
    except Exception as e:
        raise FootprintParseError(f"Error reading {path}: {e}")

    # Collect all courtyard points
    points: list[tuple[float, float]] = []

    # Parse fp_line elements on F.CrtYd or B.CrtYd layers
    # Format: (fp_line (start X Y) (end X Y) (layer "F.CrtYd") ...)
    fp_line_pattern = re.compile(
        r"\(fp_line\s+"
        r"\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+"
        r"\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+"
        r'\(layer\s+"([FB]\.CrtYd)"\)',
        re.MULTILINE,
    )

    for match in fp_line_pattern.finditer(content):
        x1, y1, x2, y2 = map(float, match.groups()[:4])
        points.append((x1, y1))
        points.append((x2, y2))

    # Parse fp_rect elements on F.CrtYd or B.CrtYd layers (newer KiCad format)
    # Format: (fp_rect (start X Y) (end X Y) (layer "F.CrtYd") ...)
    fp_rect_pattern = re.compile(
        r"\(fp_rect\s+"
        r"\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+"
        r"\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+"
        r'\(layer\s+"([FB]\.CrtYd)"\)',
        re.MULTILINE,
    )

    for match in fp_rect_pattern.finditer(content):
        x1, y1, x2, y2 = map(float, match.groups()[:4])
        # Rectangle has 4 corners
        points.append((x1, y1))
        points.append((x2, y1))
        points.append((x2, y2))
        points.append((x1, y2))

    if not points:
        raise FootprintParseError(
            f"No courtyard (F.CrtYd or B.CrtYd) found in {path}. "
            "Footprint must have courtyard lines to extract bounds."
        )

    # Compute bounding box
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]

    min_x = min(x_coords)
    max_x = max(x_coords)
    min_y = min(y_coords)
    max_y = max(y_coords)

    width = max_x - min_x
    height = max_y - min_y

    # Center offset from origin
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2

    return FootprintBounds(
        width=width,
        height=height,
        center_offset=(center_x, center_y),
    )


def parse_footprint_directory(directory: Path) -> dict[str, FootprintBounds]:
    """
    Parse all .kicad_mod files in a directory.

    Args:
        directory: Path to directory containing footprint files.

    Returns:
        Dict mapping footprint name (filename without extension) to bounds.
    """
    directory = Path(directory)
    results: dict[str, FootprintBounds] = {}

    for fp_file in directory.glob("*.kicad_mod"):
        name = fp_file.stem
        try:
            bounds = parse_footprint_courtyard(fp_file)
            results[name] = bounds
        except FootprintParseError:
            # Skip files that can't be parsed (no courtyard, etc.)
            continue

    return results

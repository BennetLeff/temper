"""Internal: footprint/module visualization and annotation functions.

kiutils-free (Wave 4 Phase 3, formats/IO): board I/O goes through the
Rust parse engine's text path — ``extract_footprint_info_py`` reads
footprint positions, values, and local pad data; ``gr_rect_sexpr_py`` /
``gr_text_sexpr_py`` construct per-item s-expressions; and
``append_items_to_board_py`` inserts them into the KiNode tree and
serializes back to text. The per-pad KiCad rotation and the bounding-box
reduction (``component_bounds_py``) stay in Python/Rust as before.
"""

from __future__ import annotations
from typing import Any

import math
from pathlib import Path

import temper_design_bundle_python as _tdb
from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.geometry.kicad_transform import rotate_local_to_world


def _component_bounds(
    fp_x: float,
    fp_y: float,
    fp_angle: float,
    pads: list[tuple[float, float, float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Pad-inclusive axis-aligned bounds of a footprint in world coordinates.

    ``pads`` is a list of ``(local_x, local_y, width, height)`` tuples.
    The rotation threshold (``abs(fp_angle) > 0.1``), the
    ``rotate_local_to_world`` SSOT call and the ``position``/``size``
    defaults stay here; the min/max reduction runs in Rust
    (``component_bounds_py``).
    """
    angle_rad = math.radians(fp_angle)
    world_pads = []
    for lx, ly, pw, ph in pads:
        if abs(fp_angle) > 0.1:
            rotated_x, rotated_y = rotate_local_to_world(lx, ly, angle_rad)
        else:
            rotated_x, rotated_y = lx, ly
        world_pads.append((rotated_x, rotated_y, pw, ph))

    _result = _GEOM.component_bounds_py(fp_x, fp_y, world_pads)
    return (float(_result[0]), float(_result[1]), float(_result[2]), float(_result[3]))


def add_bounding_boxes_to_pcb(
    pcb_path: Path,
    _bounds_override: dict[str, tuple[float, float, float, float]] | None = None,
    layer: str = "Dwgs.User",
    stroke_width: float = 0.2,
) -> int:
    """
    Add bounding box rectangles to a PCB file for component visualization.

    This draws a rectangle around each component on a user layer, making it
    easy to see component boundaries vs individual pads.

    Args:
        pcb_path: Path to the .kicad_pcb file to modify (in-place).
        layer: KiCad layer to draw on (default: "Dwgs.User").
        stroke_width: Line width in mm.

    Returns:
        Number of bounding boxes added.
    """
    content = Path(pcb_path).read_text(encoding="utf-8")
    footprints = _tdb.parse_engine.extract_footprint_info_py(content)

    item_sexprs: list[Any] = []
    boxes_added = 0

    for fp in footprints:
        ref = fp["ref"]
        if not ref:
            continue

        fp_x = fp["x"]
        fp_y = fp["y"]
        fp_angle = fp["angle"]

        pads = fp["pads"]
        if not pads:
            continue

        x_min, y_min, x_max, y_max = _component_bounds(fp_x, fp_y, fp_angle, pads)

        margin = 0.3
        x_min -= margin
        y_min -= margin
        x_max += margin
        y_max += margin

        try:
            item_sexprs.append(
                _GEOM.gr_rect_sexpr_py(x_min, y_min, x_max, y_max, layer, stroke_width)
            )
            boxes_added += 1
        except Exception:
            pass

    result_text = _tdb.parse_engine.append_items_to_board_py(content, item_sexprs)
    Path(pcb_path).write_text(result_text, encoding="utf-8")

    return boxes_added


def add_silkscreen_labels(
    pcb_path: Path,
    add_references: bool = True,
    add_values: bool = True,
    add_fab_outlines: bool = True,
    _text_height: float = 1.0,
    _text_thickness: float = 0.15,
    outline_width: float = 0.15,
) -> dict[str, int]:
    """
    Add improved silkscreen labels and fab layer outlines to a PCB file.

    Args:
        pcb_path: Path to the .kicad_pcb file to modify (in-place).
        add_references: If True, add reference designators.
        add_values: If True, add component value text.
        add_fab_outlines: If True, add F.Fab layer component outlines.
        outline_width: Stroke width of F.Fab outlines in mm.

    Returns:
        Dictionary with counts: {"references": n, "values": n, "outlines": n}
    """
    content = Path(pcb_path).read_text(encoding="utf-8")
    footprints = _tdb.parse_engine.extract_footprint_info_py(content)

    item_sexprs: list[Any] = []
    counts = {"references": 0, "values": 0, "outlines": 0}

    for fp in footprints:
        ref = fp["ref"]
        if not ref:
            continue

        fp_x = fp["x"]
        fp_y = fp["y"]
        fp_angle = fp["angle"]

        pads = fp["pads"]
        if not pads:
            continue

        x_min, y_min, x_max, y_max = _component_bounds(fp_x, fp_y, fp_angle, pads)

        comp_width = x_max - x_min
        comp_height = y_max - y_min
        comp_cx = (x_min + x_max) / 2

        scaled_height = max(0.8, min(1.5, min(comp_width, comp_height) / 4))

        value = fp["value"]

        if add_references:
            try:
                ref_y = y_min - scaled_height - 0.5
                item_sexprs.append(
                    _GEOM.gr_text_sexpr_py(ref, comp_cx, ref_y, "F.SilkS")
                )
                counts["references"] += 1
            except Exception:
                pass

        if add_values and value:
            try:
                val_y = y_min - 2 * scaled_height - 1.0
                item_sexprs.append(
                    _GEOM.gr_text_sexpr_py(value, comp_cx, val_y, "F.SilkS")
                )
                counts["values"] += 1
            except Exception:
                pass

        if add_fab_outlines:
            try:
                margin = 0.2
                item_sexprs.append(
                    _GEOM.gr_rect_sexpr_py(
                        x_min - margin, y_min - margin, x_max + margin, y_max + margin,
                        "F.Fab", outline_width,
                    )
                )
                counts["outlines"] += 1
            except Exception:
                pass

    result_text = _tdb.parse_engine.append_items_to_board_py(content, item_sexprs)
    Path(pcb_path).write_text(result_text, encoding="utf-8")

    return counts

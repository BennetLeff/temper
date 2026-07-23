"""Internal: footprint/module visualization and annotation functions."""

from __future__ import annotations

import math
from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.items.common import Position
from kiutils.items.gritems import GrRect, GrText

from temper_placer.io._write_types import _get_footprint_reference
from temper_placer.io.kicad_exporter import _validate_4_layer_output


def add_bounding_boxes_to_pcb(
    pcb_path: Path,
    _component_bounds: dict[str, tuple[float, float, float, float]] | None = None,
    layer: str = "Dwgs.User",
    stroke_width: float = 0.2,
) -> int:
    """
    Add bounding box rectangles to a PCB file for component visualization.

    This draws a rectangle around each component on a user layer, making it
    easy to see component boundaries vs individual pads.

    If component_bounds is None, calculates bounds from actual footprint pads.

    Args:
        pcb_path: Path to the .kicad_pcb file to modify (in-place).
        component_bounds: Optional dict mapping ref -> (x, y, width, height).
            If None, bounds are calculated from footprint pads.
        layer: KiCad layer to draw on (default: "Dwgs.User").
        stroke_width: Line width in mm.

    Returns:
        Number of bounding boxes added.
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    boxes_added = 0

    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref:
            continue

        # Get footprint center position
        fp_x = fp.position.X if fp.position else 0.0
        fp_y = fp.position.Y if fp.position else 0.0
        fp_angle = fp.position.angle if fp.position and fp.position.angle else 0.0
        angle_rad = math.radians(fp_angle)

        # Calculate bounds from all pads
        if not fp.pads:
            continue

        x_min, y_min = float("inf"), float("inf")
        x_max, y_max = float("-inf"), float("-inf")

        for pad in fp.pads:
            # Pad position is local to footprint center
            local_x = pad.position.X if pad.position else 0.0
            local_y = pad.position.Y if pad.position else 0.0

            # Rotate local position by footprint angle
            if abs(fp_angle) > 0.1:
                rotated_x = local_x * math.cos(angle_rad) - local_y * math.sin(angle_rad)
                rotated_y = local_x * math.sin(angle_rad) + local_y * math.cos(angle_rad)
            else:
                rotated_x, rotated_y = local_x, local_y

            # Get pad size
            pad_w = pad.size.X if pad.size else 1.0
            pad_h = pad.size.Y if pad.size else 1.0

            # Update bounds (absolute coordinates)
            abs_x = fp_x + rotated_x
            abs_y = fp_y + rotated_y

            x_min = min(x_min, abs_x - pad_w / 2)
            y_min = min(y_min, abs_y - pad_h / 2)
            x_max = max(x_max, abs_x + pad_w / 2)
            y_max = max(y_max, abs_y + pad_h / 2)

        # Add small margin
        margin = 0.3
        x_min -= margin
        y_min -= margin
        x_max += margin
        y_max += margin

        # Create rectangle graphic item
        try:
            rect = GrRect(
                start=Position(X=x_min, Y=y_min),
                end=Position(X=x_max, Y=y_max),
                layer=layer,
                width=stroke_width,
            )
            ki_board.graphicItems.append(rect)
            boxes_added += 1
        except Exception:
            # GrRect might not be available in older kiutils, skip silently
            pass

    # Write back
    try:
        _validate_4_layer_output(ki_board)
        ki_board.to_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to write PCB: {e}") from e

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

    This function enhances component visibility by:
    1. Adding reference designators on F.SilkS layer (positioned above component)
    2. Adding value text on F.SilkS layer (positioned below reference)
    3. Adding component body outlines on F.Fab layer

    Args:
        pcb_path: Path to the .kicad_pcb file to modify (in-place).
        add_references: If True, add reference designator text.
        add_values: If True, add component value text.
        add_fab_outlines: If True, add F.Fab layer component outlines.
        _text_height: Height of text in mm.
        _text_thickness: Stroke width of text in mm.
        outline_width: Stroke width of F.Fab outlines in mm.

    Returns:
        Dictionary with counts: {"references": n, "values": n, "outlines": n}
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    counts = {"references": 0, "values": 0, "outlines": 0}

    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref:
            continue

        # Get footprint position and bounds
        fp_x = fp.position.X if fp.position else 0.0
        fp_y = fp.position.Y if fp.position else 0.0
        fp_angle = fp.position.angle if fp.position and fp.position.angle else 0.0
        angle_rad = math.radians(fp_angle)

        # Calculate bounds from pads
        if not fp.pads:
            continue

        x_min, y_min = float("inf"), float("inf")
        x_max, y_max = float("-inf"), float("-inf")

        for pad in fp.pads:
            local_x = pad.position.X if pad.position else 0.0
            local_y = pad.position.Y if pad.position else 0.0

            if abs(fp_angle) > 0.1:
                rotated_x = local_x * math.cos(angle_rad) - local_y * math.sin(angle_rad)
                rotated_y = local_x * math.sin(angle_rad) + local_y * math.cos(angle_rad)
            else:
                rotated_x, rotated_y = local_x, local_y

            pad_w = pad.size.X if pad.size else 1.0
            pad_h = pad.size.Y if pad.size else 1.0

            abs_x = fp_x + rotated_x
            abs_y = fp_y + rotated_y

            x_min = min(x_min, abs_x - pad_w / 2)
            y_min = min(y_min, abs_y - pad_h / 2)
            x_max = max(x_max, abs_x + pad_w / 2)
            y_max = max(y_max, abs_y + pad_h / 2)

        comp_width = x_max - x_min
        comp_height = y_max - y_min
        comp_cx = (x_min + x_max) / 2
        (y_min + y_max) / 2

        # Scale text based on component size (min 0.8mm, max 1.5mm)
        scaled_height = max(0.8, min(1.5, min(comp_width, comp_height) / 4))

        # Get component value from properties
        value = None
        props = getattr(fp, "properties", {})
        if isinstance(props, dict):
            value = props.get("Value")
        elif isinstance(props, list):
            for prop in props:
                if hasattr(prop, "key") and prop.key == "Value":
                    value = getattr(prop, "value", None)
                    break

        # Add reference text on F.SilkS (positioned above component)
        if add_references:
            try:
                ref_y = y_min - scaled_height - 0.5  # Above component
                ref_text = GrText(
                    text=ref,
                    position=Position(X=comp_cx, Y=ref_y),
                    layer="F.SilkS",
                )
                # Set text attributes if available
                if hasattr(ref_text, "effects"):
                    pass  # Text effects handled differently in kiutils
                ki_board.graphicItems.append(ref_text)
                counts["references"] += 1
            except Exception:
                pass

        # Add value text on F.SilkS (positioned below reference)
        if add_values and value:
            try:
                val_y = y_min - 2 * scaled_height - 1.0  # Below reference
                val_text = GrText(
                    text=value,
                    position=Position(X=comp_cx, Y=val_y),
                    layer="F.SilkS",
                )
                ki_board.graphicItems.append(val_text)
                counts["values"] += 1
            except Exception:
                pass

        # Add F.Fab outline (component body rectangle)
        if add_fab_outlines:
            try:
                margin = 0.2
                fab_rect = GrRect(
                    start=Position(X=x_min - margin, Y=y_min - margin),
                    end=Position(X=x_max + margin, Y=y_max + margin),
                    layer="F.Fab",
                    width=outline_width,
                )
                ki_board.graphicItems.append(fab_rect)
                counts["outlines"] += 1
            except Exception:
                pass

    # Write back
    try:
        _validate_4_layer_output(ki_board)
        ki_board.to_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to write PCB: {e}") from e

    return counts

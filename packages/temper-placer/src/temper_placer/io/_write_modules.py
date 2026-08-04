"""Internal: footprint/module visualization and annotation functions.

Wave 4, Phase 3, candidate 4: the pad-bounds, value-extraction and silkscreen
text geometry delegate to the ``temper-io-types`` ``kicad_write``
``fp_annotations`` kernel; this shim keeps the kiutils board I/O and
``GrRect``/``GrText`` item construction.
"""

from __future__ import annotations

from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.items.common import Position
from kiutils.items.gritems import GrRect, GrText

from temper_io_types import fp_annotations

from temper_placer.io.kicad_exporter import _validate_4_layer_output


def add_bounding_boxes_to_pcb(
    pcb_path: Path,
    _component_bounds: dict[str, tuple[float, float, float, float]] | None = None,
    layer: str = "Dwgs.User",
    stroke_width: float = 0.2,
) -> int:
    """
    Add bounding box rectangles to a PCB file for component visualization.
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    boxes_added = 0
    annotations = fp_annotations(ki_board.footprints)

    for ann in annotations:
        if ann is None:
            continue
        ref, x_min, y_min, x_max, y_max, value, comp_cx, scaled_height, ref_y, val_y = ann

        # Add small margin
        margin = 0.3

        # Create rectangle graphic item
        try:
            rect = GrRect(
                start=Position(X=x_min - margin, Y=y_min - margin),
                end=Position(X=x_max + margin, Y=y_max + margin),
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
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    counts = {"references": 0, "values": 0, "outlines": 0}

    annotations = fp_annotations(ki_board.footprints)

    for ann in annotations:
        if ann is None:
            continue
        ref, x_min, y_min, x_max, y_max, value, comp_cx, scaled_height, ref_y, val_y = ann

        # Add reference text on F.SilkS (positioned above component)
        if add_references:
            try:
                ref_text = GrText(
                    text=ref,
                    position=Position(X=comp_cx, Y=ref_y),
                    layer="F.SilkS",
                )
                ki_board.graphicItems.append(ref_text)
                counts["references"] += 1
            except Exception:
                pass

        # Add value text on F.SilkS (positioned below reference)
        if add_values and value:
            try:
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

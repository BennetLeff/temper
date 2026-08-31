"""VERBATIM pin of the annotation-item constructions embedded in
``temper_placer/io/_write_modules.py`` at origin/main ``5e528b8aa`` (the
Wave-4 Phase-3 formats/IO migration base).

This file is the pre-migration oracle for the ``_write_modules.py``
annotation migration. Each function is a STATEMENT-FOR-STATEMENT extraction
of the construction embedded in the shipped module's loops, with the
originating line range cited so the extraction can be checked by inspection.
DO NOT "improve", reformat, or keep these in sync with the post-migration
source: their whole value is that they are frozen.

``test_write_modules_rust_differential.py`` asserts the migrated Rust
implementation (``temper_io_types.kicad_write_geometry.gr_rect_sexpr_py`` /
``gr_text_sexpr_py`` and ``temper_io_types.write_types.footprint_value_py``)
reproduces this file's output byte-for-byte through kiutils' own round-trip
(``GrRect.from_sexpr(rust).to_sexpr()`` / ``GrText.from_sexpr(rust).to_sexpr()``).
"""

from __future__ import annotations

from typing import Any

from kiutils.items.common import Position
from kiutils.items.gritems import GrRect, GrText


def gr_rect_to_sexpr(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    layer: str,
    stroke_width: float,
) -> str:
    """Verbatim extraction of ``add_bounding_boxes_to_pcb``'s rectangle
    construction (lines 116-121):

        rect = GrRect(
            start=Position(X=x_min, Y=y_min),
            end=Position(X=x_max, Y=y_max),
            layer=layer,
            width=stroke_width,
        )
    """
    rect = GrRect(
        start=Position(X=x_min, Y=y_min),
        end=Position(X=x_max, Y=y_max),
        layer=layer,
        width=stroke_width,
    )
    return rect.to_sexpr()


def gr_text_to_sexpr(text: str, x: float, y: float, layer: str) -> str:
    """Verbatim extraction of ``add_silkscreen_labels``'s reference-text
    construction (lines 213-217; the value-text construction at lines
    230-234 is identical except for its Y coordinate):

        ref_text = GrText(
            text=ref,
            position=Position(X=comp_cx, Y=ref_y),
            layer="F.SilkS",
        )
    """
    ref_text = GrText(
        text=text,
        position=Position(X=x, Y=y),
        layer=layer,
    )
    return ref_text.to_sexpr()


def footprint_value(fp: Any) -> str | None:
    """Verbatim extraction of ``add_silkscreen_labels``'s value read (lines
    199-207):

        value = None
        props = getattr(fp, "properties", {})
        if isinstance(props, dict):
            value = props.get("Value")
        elif isinstance(props, list):
            for prop in props:
                if hasattr(prop, "key") and prop.key == "Value":
                    value = getattr(prop, "value", None)
                    break
    """
    value = None
    props = getattr(fp, "properties", {})
    if isinstance(props, dict):
        value = props.get("Value")
    elif isinstance(props, list):
        for prop in props:
            if hasattr(prop, "key") and prop.key == "Value":
                value = getattr(prop, "value", None)
                break
    return value

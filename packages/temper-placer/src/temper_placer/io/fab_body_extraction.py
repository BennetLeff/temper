"""Extract ``F.Fab``/``B.Fab`` body geometry from a KiCad PCB file.

Companion to ``io/kicad_metadata.py``'s ``F.CrtYd`` courtyard extraction --
same raw-shape schema, same merge algorithm (reused verbatim, not
reimplemented: ``kicad_metadata._courtyard_points_from_raw``), different
source layer and different footprint reader.

**Why this stays kiutils-based instead of extending the Rust
``parse_engine.extract_metadata_raw``.** That function already has the
identical shape-serialization switch for ``F.CrtYd``/``B.CrtYd``
(``parse_engine.rs`` lines ~3355-3405) and extending it to also emit
``F.Fab``/``B.Fab`` would be the more DRY long-term home for this. It was
not done here to avoid a pyo3/maturin rebuild inside this change's blast
radius -- ``kiutils`` (an existing, already-a-dependency parser used by this
exact package for ``F.Fab`` reference-text extraction, see
``io/_parse_modules.py::_get_footprint_reference``) reads the identical
``fp_rect``/``fp_circle``/``fp_poly``/``fp_line``/``fp_arc`` graphic items
with no new compiled surface. The geometry ARITHMETIC (rotation transform,
merge/hull, polygon boolean) is unchanged from the canonical kernels either
way; only the parsing library differs. A follow-up migrating this into
``parse_engine.rs`` alongside the courtyard extraction is a reasonable
Wave-4-style consolidation, not required for this guard to be sound.

**Validation.** This module's output was cross-checked against PR #1158's
independently-implemented (from-scratch S-expression parser, not this
codebase's kernels) body-overlap measurements for all 8 tracked
``courtyards_overlap`` pairs on ``pcb/temper.kicad_pcb`` and reproduces its
published depths/gaps (e.g. C2xC3 world body centers (98.48, 64.84) /
(87.36, 39.94), matching to the mm) and, independently, against live
``kicad-cli pcb drc`` output on the same board (identical 8-pair set,
`kicad-cli` 10.0.5) -- see ``docs/evidence/<this-PR>-body-collision-guard.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from temper_placer.core.fab_body import FabBody
from temper_placer.io.kicad_metadata import _courtyard_points_from_raw

_FAB_LAYERS = ("F.Fab", "B.Fab")


def _fab_shape_inputs(footprint: Any) -> list[dict]:
    """Raw ``F.Fab``/``B.Fab`` graphic-item shapes for one kiutils
    ``Footprint``, in the exact ``{"kind": ..., ...}`` schema
    ``kicad_metadata._courtyard_points_from_raw`` consumes -- the same
    schema ``parse_engine.rs``'s courtyard-shape switch produces, mirrored
    here for the fab layer instead of the courtyard layer.
    """
    inputs: list[dict] = []
    for item in getattr(footprint, "graphicItems", None) or []:
        layer = getattr(item, "layer", None)
        if layer not in _FAB_LAYERS:
            continue
        kind = type(item).__name__
        if kind == "FpPoly":
            coords = getattr(item, "coordinates", None) or []
            inputs.append({"kind": "poly", "coords": [(p.X, p.Y) for p in coords]})
        elif kind == "FpCircle":
            inputs.append(
                {
                    "kind": "circle",
                    "center": (item.center.X, item.center.Y),
                    "end": (item.end.X, item.end.Y),
                }
            )
        elif kind == "FpRect":
            inputs.append(
                {
                    "kind": "rect",
                    "start": (item.start.X, item.start.Y),
                    "end": (item.end.X, item.end.Y),
                }
            )
        elif kind == "FpLine":
            inputs.append(
                {
                    "kind": "line",
                    "start": (item.start.X, item.start.Y),
                    "end": (item.end.X, item.end.Y),
                }
            )
        elif kind == "FpArc":
            inputs.append(
                {
                    "kind": "arc",
                    "start": (item.start.X, item.start.Y),
                    "mid": (item.mid.X, item.mid.Y),
                    "end": (item.end.X, item.end.Y),
                }
            )
        # FpText / FpTextBox / FpCurve: no body-outline contribution --
        # matches parse_engine.rs's own skip list for the courtyard switch.
    return inputs


def _footprint_reference(footprint: Any) -> str | None:
    props = getattr(footprint, "properties", None)
    if isinstance(props, dict):
        return props.get("Reference")
    if isinstance(props, list):
        for p in props:
            if getattr(p, "key", None) == "Reference" or getattr(p, "name", None) == "Reference":
                return getattr(p, "value", None)
    return None


def extract_fab_bodies(pcb_path: Path) -> dict[str, FabBody]:
    """Return ``{ref: FabBody}`` for every footprint on *pcb_path* that
    carries real ``F.Fab``/``B.Fab`` graphics.

    A footprint with no parseable fab-layer geometry is EXCLUDED from the
    returned dict (not given a fabricated fallback shape) -- the caller
    (``body_collision.audit_body_collisions``) treats an absent ref as "no
    body-collision opinion" for any pair involving it, which is the correct,
    honest handling: inventing a box here could manufacture false positives
    or mask real ones, either of which is worse than a documented skip.

    Raises:
        FileNotFoundError: pcb_path does not exist.
    """
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    from kiutils.board import Board

    board = Board.from_file(str(pcb_path))

    bodies: dict[str, FabBody] = {}
    for fp in board.footprints:
        ref = _footprint_reference(fp)
        if not ref:
            continue
        inputs = _fab_shape_inputs(fp)
        points = _courtyard_points_from_raw(inputs)
        if not points:
            continue
        bodies[ref] = FabBody(component_ref=ref, points=points)
    return bodies

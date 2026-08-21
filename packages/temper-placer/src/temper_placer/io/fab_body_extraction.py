"""Extract ``F.Fab``/``B.Fab`` body geometry from a KiCad PCB file.

Companion to ``io/kicad_metadata.py``'s ``F.CrtYd`` courtyard extraction --
same raw-shape schema, same merge algorithm (reused verbatim, not
reimplemented: ``kicad_metadata._courtyard_points_from_raw``), different
source layer and different footprint reader.

**kiutils-free (Wave 4 Phase 3, formats/IO).** Board reading goes through
the Rust parse engine: ``parse_engine.extract_metadata_raw`` emits the
identical raw-shape schema for ``F.Fab``/``B.Fab`` (``fab_body_inputs``
key) that it has always emitted for ``F.CrtYd``/``B.CrtYd``
(``courtyard_inputs``) -- one shape-serialization switch, two layer
filters. The geometry ARITHMETIC (rotation transform, merge/hull,
polygon boolean) is unchanged from the canonical kernels either way;
only the parsing library differs.

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

from temper_placer.core.fab_body import FabBody
from temper_placer.io.kicad_metadata import _courtyard_points_from_raw


def _fab_shape_inputs(footprint_shapes: list[dict]) -> list[dict]:
    """Normalize one footprint's Rust-extracted fab shapes (already in the
    ``{"kind": ..., ...}`` schema ``kicad_metadata._courtyard_points_from_raw``
    consumes). Kept as a named seam for the merge-algorithm tests; the
    schema is produced by ``parse_engine.extract_metadata_raw``'s
    shape switch, mirrored byte-for-byte from the courtyard extraction.
    """
    return list(footprint_shapes)


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

    import temper_design_bundle_python as _tdb

    fab_inputs = _tdb.parse_engine.extract_metadata_raw(
        pcb_path.read_text(encoding="utf-8")
    )["fab_body_inputs"]

    bodies: dict[str, FabBody] = {}
    for ref, shapes in fab_inputs.items():
        if not ref:
            continue
        points = _courtyard_points_from_raw(_fab_shape_inputs(shapes))
        if not points:
            continue
        bodies[ref] = FabBody(component_ref=ref, points=points)
    return bodies

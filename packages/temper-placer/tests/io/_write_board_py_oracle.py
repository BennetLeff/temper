"""VERBATIM pin of the two GEOMETRY/FORMATTING kernels embedded in
``temper_placer/io/_write_board.py`` at origin/main ``550cab2a3`` (the
file's last-touch commit as of this migration).

This file is the pre-migration oracle for the Wave-4 Phase-3 (formats/IO)
``_write_board.py`` migration. Unlike the ``kicad_exporter.py`` sibling
migration (``_kicad_exporter_py_oracle.py``), neither kernel here was
already a standalone top-level function in the source -- both are pure
numeric snippets embedded inside loops that also mutate ``kiutils`` tree
objects (pad angles, dict construction). Each function below is a
STATEMENT-FOR-STATEMENT extraction of the pure-compute lines only, with the
originating function/line range cited so the extraction can be checked by
inspection against the shipped module. DO NOT "improve", reformat, or keep
these in sync with the post-migration source: their whole value is that
they are frozen.

``test_write_board_geometry_rust_differential.py`` asserts the migrated
Rust implementation (``temper_design_bundle_python.write_board_geometry``)
reproduces this file's output bit-for-bit.

Only these two kernels are pinned here -- not the whole module. See
``packages/temper-design-bundle/src/write_board_geometry.rs``'s module
docstring for the full triage of what was and was not ported from
``_write_board.py``, and why.
"""

from __future__ import annotations


def reorient_pad_angle(current_angle: float | None, delta_deg: float) -> float | None:
    """Verbatim extraction of ``_reorient_pads``'s loop body (lines 50-57):

        for pad in fp.pads or []:
            if pad.position is None:
                continue
            current = pad.position.angle or 0.0
            new_angle = (current + delta) % 360.0
            # kiutils omits the angle token when it is None; an absent angle
            # means 0 in KiCad, so only write None when the result really is 0.
            pad.position.angle = None if new_angle == 0.0 else new_angle

    ``current_angle`` stands in for ``pad.position.angle`` (the ``if
    pad.position is None: continue`` guard is object-existence plumbing --
    handled by the caller, not part of this kernel); ``delta_deg`` stands in
    for the enclosing function's ``delta``. The assignment target is
    replaced by a return.
    """
    current = current_angle or 0.0
    new_angle = (current + delta_deg) % 360.0
    return None if new_angle == 0.0 else new_angle


def reorient_delta_is_noop(delta_deg: float) -> bool:
    """Verbatim extraction of ``_reorient_pads``'s early-exit guard (lines
    47-49)::

        delta = new_fp_angle - old_fp_angle
        if delta % 360.0 == 0.0:
            return

    ``delta_deg`` stands in for the already-computed ``delta``.
    """
    return delta_deg % 360.0 == 0.0


def preserve_rotation_offset(rotation_deg: float, original_angle: float) -> float:
    """Verbatim extraction of ``state_to_placements``'s original-angle
    offset-preservation block (lines 243-248)::

        if original_angles and ref in original_angles:
            original = original_angles[ref]
            quantized = round(original / 90) * 90.0
            offset = original - quantized
            if abs(offset) > 0.1:  # Only apply if there was a real offset
                rotation_deg = (rotation_deg + offset) % 360.0

    The ``original_angles and ref in original_angles`` dict-membership
    check is the caller's responsibility (control flow, not geometry) --
    this kernel starts from ``original = original_angles[ref]`` already
    resolved (``original_angle``), taking the discrete-quantized
    ``rotation_deg`` (0/90/180/270) and returning the (possibly
    offset-adjusted) result.
    """
    quantized = round(original_angle / 90) * 90.0
    offset = original_angle - quantized
    if abs(offset) > 0.1:  # Only apply if there was a real offset
        rotation_deg = (rotation_deg + offset) % 360.0
    return rotation_deg

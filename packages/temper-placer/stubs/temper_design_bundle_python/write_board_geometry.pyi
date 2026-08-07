"""Type stubs for `temper_design_bundle_python.write_board_geometry`.

Compiled from `packages/temper-design-bundle/src/write_board_geometry.rs` --
the Wave 4 Phase 3 (formats/IO) migration of the two numeric kernels ported
out of `temper_placer/io/_write_board.py` (`_reorient_pads`'s per-pad angle
update, `state_to_placements`'s original-angle offset preservation). Keep
in sync with that file.
"""

from __future__ import annotations

def reorient_pad_angles_py(
    current_angles: list[float | None],
    delta_deg: float,
) -> list[float | None]: ...


def preserve_rotation_offset_py(rotation_deg: float, original_angle: float) -> float: ...

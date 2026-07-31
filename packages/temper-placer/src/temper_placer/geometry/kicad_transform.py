"""The single sanctioned implementation of KiCad's footprint-child rotation
convention.

KiCad rotates a footprint child (a pad offset, a courtyard vertex, a
silkscreen item, ...) from its position local to the footprint's own origin
into board/world coordinates by **R(-theta)**, not the R(+theta) (standard
math CCW) convention this repo independently re-implemented, wrongly, in 12
different places:

    world = footprint_position + R(-theta) . local_offset

    R(-theta) = [[ cos(theta),  sin(theta)],
                 [-sin(theta),  cos(theta)]]

This was confirmed against real ``kicad-cli 10.0.4 pcb drc`` output on a
hand-built minimal board -- not inferred from re-reading this repo's own
(previously wrong) code. See
``docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md``
Sec. 2 for the experiment and its ground-truth DRC output.

Why this module exists
-----------------------
Before it did, this exact two-line formula was independently written out,
by hand, in 12 places across this repo -- including
``requirements/validators/_copper.py::_rotate``, which REQ-SAFE-01 uses to
compute copper positions for the mains<->SELV clearance check. One of the
12 (an ad-hoc R(+theta)) concealed real clearance hazards on 18 production
components before it was found and corrected. 12 independently-typed
copies of a two-line formula is one careless edit away from 11 correct
copies and 1 silently wrong one again; nothing short of a single
implementation closes that gap. The 12 corrected sites (fixed for the sign
error, not yet consolidated, before this module existed) were:

  1. ``core/courtyard.py`` (``Courtyard.get_global_polygon``, via
     ``shapely.affinity.rotate`` -- see :func:`shapely_rotation_angle_deg`)
  2. ``core/pin_geometry.py`` (``pin_world_position_at``)
  3. ``deterministic/stages/setup.py`` (``DRCOracleSetupStage._rotate_point``,
     dead code at the time of the fix, corrected anyway)
  4. ``io/_parse_modules.py`` (``_extract_components_from_pcb``)
  5. ``io/_write_board.py`` (three call sites: ``write_placements_to_pcb``,
     ``state_to_placements``, ``add_isolation_slots_to_pcb``)
  6. ``io/_write_modules.py`` (two call sites: ``add_bounding_boxes_to_pcb``,
     ``add_silkscreen_labels``)
  7. ``io/kicad_exporter.py`` (``extract_pad_centers``)
  8. ``placer/cp_sat/isolation_barrier.py``
     (``_project_onto_barrier_axis`` -- an exact, hand-unrolled 4-way
     dict for the model's axis-aligned rotations, not raw trig; left as
     its own hand-verified specialization rather than routed through this
     module's floating-point trig, to avoid introducing sub-ULP float
     noise into a CP-SAT integer-scaled model -- see that function's own
     docstring for the closed form this module's convention implies)
  9. ``placer/template.py`` (two call sites: ``ParametricTemplate``,
     ``ComponentTemplate``)
  10. ``requirements/validators/_copper.py`` (``_rotate`` -- the REQ-SAFE-01
      copper-position site)
  11. ``scripts/check_isolation_keepout.py`` (``_rotate``)

...plus a 13th, pre-existing, independently-authored-and-*already-correct*
implementation this module also now backs, ``scripts/check_pad_orientation.py``
(``_rotate``, independently validated against 57/57 real ``kicad-cli`` DRC
``shorting_items`` pairs -- see
``docs/evidence/2026-07-29-intra-component-shorts-root-cause.md``).

Every site above now imports from here instead of re-deriving the formula.
Do not reimplement it. A lint
(``scripts/check_no_raw_rotation_trig.py``) forbids raw
``math.cos``/``math.sin``/``np.cos``/``np.sin`` in the specific files
above (the repo's proven-vulnerable set), to fail loudly if any of them
regresses back to a local, independently-typed copy of this formula.

The Rust crate
---------------
``packages/temper-geometry/src/transform.rs`` (bound to Python as
``temper_placer.geometry.transform.transform_pin_position`` /
``transform_pin_positions``) carries its own, separately-maintained copy of
this same R(-theta) formula. It is not reachable from here -- crossing the
pyo3 FFI boundary for a two-line scalar formula on every call is not worth
the coupling this pure-Python module would otherwise take on, and (at the
time this module was written) nothing in production actually calls the
Rust entry point; it exists for the ``temper_geometry`` crate's own
consumers. Rather than let it silently drift from this module's
convention, the two are pinned together by a differential test:
``packages/temper-placer/tests/geometry/test_kicad_transform_rust_differential.py``.
"""

from __future__ import annotations

import math

__all__ = [
    "rotate_local_to_world",
    "rotate_local_to_world_deg",
    "rotate_world_to_local",
    "rotate_world_to_local_deg",
    "place_local_to_world",
    "shapely_rotation_angle_deg",
]


def rotate_local_to_world(x: float, y: float, theta_rad: float) -> tuple[float, float]:
    """Rotate a local (footprint-relative) offset into world orientation.

    This is R(-theta), KiCad's real footprint-child rotation convention --
    see this module's docstring for the confirming evidence. ``theta_rad``
    is the footprint/component's own board rotation, in radians.
    """
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (x * c + y * s, -x * s + y * c)


def rotate_local_to_world_deg(x: float, y: float, theta_deg: float) -> tuple[float, float]:
    """Degrees convenience wrapper for :func:`rotate_local_to_world`."""
    return rotate_local_to_world(x, y, math.radians(theta_deg))


def rotate_world_to_local(x: float, y: float, theta_rad: float) -> tuple[float, float]:
    """Inverse of :func:`rotate_local_to_world`: rotate a world-oriented
    offset back into the footprint's local frame.

    This is R(+theta) -- the transpose of R(-theta), which for a rotation
    matrix is also its inverse. No call site needed this at the time this
    module was written; provided as the documented pair of the forward
    transform (this task's own brief: "expose local->world placement ...
    plus its inverse") so a future caller does not have to re-derive it.
    """
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (x * c - y * s, x * s + y * c)


def rotate_world_to_local_deg(x: float, y: float, theta_deg: float) -> tuple[float, float]:
    """Degrees convenience wrapper for :func:`rotate_world_to_local`."""
    return rotate_world_to_local(x, y, math.radians(theta_deg))


def place_local_to_world(
    local_x: float,
    local_y: float,
    origin_x: float,
    origin_y: float,
    theta_rad: float,
) -> tuple[float, float]:
    """Rotate a local offset by ``theta_rad`` (KiCad convention) and
    translate by ``(origin_x, origin_y)``. The common "rotate offset from
    a component's origin, then place at the component's board position"
    pattern used throughout this repo's KiCad I/O, in one call.
    """
    rx, ry = rotate_local_to_world(local_x, local_y, theta_rad)
    return (origin_x + rx, origin_y + ry)


def shapely_rotation_angle_deg(theta_deg: float) -> float:
    """The angle (degrees) to pass to ``shapely.affinity.rotate`` to apply
    this module's KiCad rotation convention to a polygon.

    ``shapely.affinity.rotate``'s own ``angle`` parameter is CCW-positive
    (standard math convention, i.e. R(+theta)) -- the opposite sign of
    this module's R(-theta). So::

        shapely.affinity.rotate(poly, shapely_rotation_angle_deg(theta), origin=(0, 0))

    rotates every vertex of ``poly`` exactly as :func:`rotate_local_to_world_deg`
    would rotate that vertex individually.
    """
    return -theta_deg

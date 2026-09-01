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
----------------------
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

The Rust implementation (Wave 4 migration)
------------------------------------------
Since the Wave 4 migration, the implementation lives in ONE place: the Rust
kernel ``packages/temper-geometry/src/kicad_transform.rs``, exposed to
Python as ``temper_geometry.kicad_*_py``. This module is now a thin shim
delegating each public function there; the public names, signatures,
docstrings and ``__all__`` are unchanged, so the 12 call sites and the lint
above keep working without edits. The Rust kernels resolve ``cos``/``sin``
through the host process's libm (the B1 dlsym pattern), so the results are
bit-identical to what this module computed with CPython's ``math.cos``/
``math.sin``; the differential suite
(``packages/temper-placer/tests/geometry/test_kicad_transform_rust_differential.py``)
pins the shim against VERBATIM copies of the pre-migration Python
(``_oracle_*`` blocks) with ``float.hex()`` equality.

Two older Rust copies of the same convention still exist outside this
shim, both pinned rather than consolidated (they are the crate's own
consumers, not the KiCad I/O paths, and touching their callers is out of
scope here): ``transform.rs::transform_pin_position`` (statically-bound
``f64::cos``/``f64::sin``, so within 1 ulp rather than bit-identical --
see the tolerance pin in the differential suite) and
``clearance_geometry.rs::rotate_local_to_world`` (already host-libm,
bit-identical, used by ``requirements/validators/_copper.py``).
"""

from __future__ import annotations

import temper_geometry as _tg

__all__ = [
    "rotate_local_to_world",
    "rotate_local_to_world_deg",
    "rotate_world_to_local",
    "rotate_world_to_local_deg",
    "place_local_to_world",
    "shapely_rotation_angle_deg",
]


def rotate_local_to_world(x: float, y: float, theta_rad: float) -> tuple[float, float]:
    """Delegate to the Rust kernel using a live module lookup."""
    return _tg.kicad_rotate_local_to_world_py(x, y, theta_rad)


def rotate_local_to_world_deg(x: float, y: float, theta_deg: float) -> tuple[float, float]:
    """Delegate to the Rust degrees kernel using a live module lookup."""
    return _tg.kicad_rotate_local_to_world_deg_py(x, y, theta_deg)


def rotate_world_to_local(x: float, y: float, theta_rad: float) -> tuple[float, float]:
    """Delegate to the Rust inverse kernel using a live module lookup."""
    return _tg.kicad_rotate_world_to_local_py(x, y, theta_rad)


def rotate_world_to_local_deg(x: float, y: float, theta_deg: float) -> tuple[float, float]:
    """Delegate to the Rust inverse degrees kernel using a live lookup."""
    return _tg.kicad_rotate_world_to_local_deg_py(x, y, theta_deg)


def place_local_to_world(
    local_x: float,
    local_y: float,
    origin_x: float,
    origin_y: float,
    theta_rad: float,
) -> tuple[float, float]:
    """Delegate to the Rust rotate-then-translate kernel."""
    return _tg.kicad_place_local_to_world_py(local_x, local_y, origin_x, origin_y, theta_rad)


def shapely_rotation_angle_deg(theta_deg: float) -> float:
    """Delegate to the Rust Shapely-angle kernel using a live lookup."""
    return _tg.kicad_shapely_rotation_angle_deg_py(theta_deg)

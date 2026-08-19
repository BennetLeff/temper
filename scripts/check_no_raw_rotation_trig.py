#!/usr/bin/env python3
"""Forbid raw rotation trig in the files that have already reimplemented
KiCad's footprint-child rotation formula, wrongly, once.

Motivating incident
--------------------
A rotation-sign error (KiCad rotates a footprint child -- a pad offset, a
courtyard vertex, a silkscreen item -- by R(-theta); this repo used the
standard-math R(+theta)/CCW convention instead) was independently
reimplemented, by hand, in 12 different places, including
``requirements/validators/_copper.py::_rotate``, which REQ-SAFE-01 uses to
compute copper positions for the mains<->SELV clearance check. It
concealed real clearance hazards on 18 production components. See
docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md.

All 12 were corrected and then consolidated into a single implementation,
``temper_placer.geometry.kicad_transform`` (see that module's own
docstring for the full list and the confirming evidence). 12
independently-typed copies of a two-line formula is one careless edit away
from 11 correct copies and 1 silently wrong one again -- a test suite does
not prevent that, only removing the ability to write a 13th copy does.
This gate is that removal: it fails if any of the files that have already
proven capable of hosting this exact bug regresses back to a raw,
locally-typed trig call instead of importing the sanctioned module.

What is checked
-----------------
Each file in ``GUARDED_FILES`` below (the exact set that carried the bug,
or is close enough to the bug's own shape -- see per-entry comments) is
AST-scanned for any call to ``math.cos``, ``math.sin``, ``np.cos``,
``np.sin``, ``numpy.cos``, or ``numpy.sin`` (qualified attribute calls),
plus a bare ``cos(...)``/``sin(...)`` call if ``cos``/``sin`` was imported
via ``from math import cos`` / ``from numpy import cos`` (or ``sin``) in
that same file. Import aliases are resolved (``import math as m`` ->
``m.cos`` still trips it). ``temper_placer/geometry/kicad_transform.py``
itself is the one place in the repo allowed to contain this formula and is
never in ``GUARDED_FILES``.

Why an enumerated file list, not a directory/package rule
------------------------------------------------------------
The obvious-looking alternative -- forbid raw ``math.cos``/``sin``
anywhere under ``core/``, ``io/``, ``placer/``, or similar "geometry-ish"
layers -- was tried first, by audit, and rejected: those same directories
also contain extensive, entirely unrelated trig that has nothing to do
with KiCad's rotation convention and would false-positive under a
directory rule, e.g. (non-exhaustive, found during this gate's own design):

  - ``core/pad_geometry.py::pad_support_radius`` -- a pad's extent along a
    query direction; uses ``abs(cos)``/``abs(sin)``, sign-invariant by
    construction.
  - ``placer/deterministic.py``, ``placer/adjustment.py``,
    ``topological/initial_placement.py``, ``deterministic/stages/
    _grid_fence.py``, ``deterministic/geometry/via_placement.py`` --
    spiral/circular/radial placement search patterns, nothing to do with
    a footprint's own orientation.
  - ``router_v6/thermal_relief.py``, ``physics/thermal_potential.py`` --
    thermal spoke/gradient geometry.
  - ``heuristics/style.py``, ``heuristics/structural.py``,
    ``heuristics/organizational.py`` -- synthetic layout-heuristic
    placement patterns.

A directory rule over that surface would need constant, growing
allowlisting and would be exactly the "broad gate people disable" this
gate's own brief warned against. An enumerated list of the files that have
already proven vulnerable is precise (zero false positives against the
audit above), directly falsifiable (delete one file's sanctioned import
and reintroduce the raw formula -- see the falsifier proof in this
project's PR description), and mirrors this repo's own precedent for
"require ALL named things, not whatever is found" (``check_pll_range_
consistency.py``): a guarded file that goes missing is a GATE ERROR, not a
silently smaller check.

Second sweep: 12 call sites in 9 candidate areas, none in the original 12 plus 1
pre-existing call site
-------------------------------------------------------------------------------
A follow-up audit (see ``docs/evidence/2026-07-30-rotation-sign-remaining-
sites.md``) found 12 additional call sites carrying the same shape of bug,
grouped into 9 candidate areas, none in PR #479's 12 or
``check_pad_orientation.py``'s pre-existing 13th call site.
Classified individually against the same test this whole gate exists to
apply -- does the site transform something that must agree with KiCad's
own placement -- and against real ``pcbnew``/``kicad-cli`` ground truth via
``scripts/kicad_pad_rotation_oracle.py`` where the fix touches a value
KiCad itself would place:

  * ``check_pad_orientation.py::_corners`` -- the previously-exempted
    function above. Fixed, not left exempt: this gate is a live CI check
    on real pad geometry, and "identical corner SET at 90-degree multiples"
    is not the same claim as "correct at every angle". The exemption entry
    for it is removed below now that it contains no raw trig to exempt.
  * ``router_v6/constraints_geometry.py`` (``RotatedRect.corners``,
    ``point_to_rotated_rect_distance``) -- ``RotatedRect.rotation`` is
    populated from real board pad/component rotation
    (``deterministic/stages/setup.py``), so this is KiCad-derived geometry,
    not an isolated utility. Fixed. ``point_to_rotated_rect_distance`` was
    additionally not a simple sign flip: it inverted the *old, wrong*
    R(+theta) convention (negate the angle, reapply the same R(+theta)
    formula) rather than the real inverse of the corrected R(-theta)
    convention, so it silently computed the forward transform again
    instead of the world-to-local inverse.
  * ``router_v6/connectivity.py`` (``_to_pad_coordinates``) -- same
    forward/inverse confusion as above, on ``CopperPad.rotation`` (not yet
    wired from real board data by any production caller today, but the
    field exists specifically to hold KiCad pad orientation). Fixed.
  * ``router_v6/escape_via_generator.py``'s dog-bone candidate rotation --
    rotates a symmetric 4-way offset by the component's real board
    rotation to place a via next to a real pin (``core.pin_geometry``,
    itself KiCad-derived). Fixed.
  * ``visualization/board_renderer.py`` / ``visualization/model.py``
    (``Rectangle.corners``) -- render a visual proxy of the real board;
    ``ComponentView.rotation``/``PadView.rotation`` are meant to hold real
    board orientation. Fixed for correctness even though today's discrete
    quadrant-only rotation state (and ``PadView`` having no production
    constructor yet) makes both currently a no-op. REMOVED from
    ``GUARDED_FILES`` 2026-08-13: the entire ``visualization/`` package
    (5,508 LOC, zero production consumers) was deleted 2026-08-11 (commit
    ``cb36af61``, "deprecate the dead visualization/ package"). Same
    reasoning as ``scripts/internal_route.py`` below -- a guarded file must
    exist (``run()`` fails closed on drift), and a deleted file cannot
    regress.
  * ``scripts/internal_route.py`` -- read a real ``kiutils`` board and
    registered real pad positions with a routing oracle; its registration
    formula was fixed for correctness by this sweep. The import breakage
    flagged here at the time (``jax`` removed from the dependency set, and
    a ``temper_placer.routing`` package that no longer exists -- renamed to
    ``router_v6`` without this script following) was never repaired, and
    the script was RETIREd and deleted on 2026-08-04 as import-dead. It is
    therefore no longer in ``GUARDED_FILES``: a guarded file must exist
    (``run()`` fails closed on drift), and a deleted file cannot regress.
    See ``docs/evidence/2026-08-04-wave4-residual-verdicts.md``.
  * ``packages/temper-geometry/src/polygon.rs::rotate_polygon`` and
    ``scripts/bench_rust_geometry.py``'s ``_py_rotate_point`` -- audited
    and left alone. ``rotate_polygon`` rotates a polygon about its own
    centroid with no KiCad correspondence anywhere in or out (zero
    production callers in Rust or through the pyo3 bridge; used only by
    property-based tests asserting rotation-invariant area, which holds
    under either sign). ``bench_rust_geometry.py`` times that same generic
    Rust ``rotate_point`` (``transform.rs::rotate_point``, NOT the already-
    correct KiCad-specific ``transform_pin_position``) against a matching
    plain-Python CCW reimplementation -- both sides intentionally agree on
    the generic convention being benchmarked, and neither touches KiCad
    data. Neither is a raw-trig regression risk for this gate's own
    purpose, so neither is in ``GUARDED_FILES``; this AST lint has no Rust
    equivalent, deliberately -- see the docstring above this section for
    why an enumerated Python file list is the chosen mechanism, and there
    is no comparable "13 proven-vulnerable files" precedent on the Rust
    side yet.
  * ``core/state.py`` (``rotation_matrix``, ``rotate_points``) -- dead,
    unused JAX-era leftover (``sample_rotation`` two functions above it is
    already marked ``DEPRECATED``); zero production callers. Not fixed,
    not guarded: nothing calls it, so there is nothing to protect.

All newly-fixed sites that carry KiCad-derived rotation are added to
``GUARDED_FILES`` below.

The arithmetic is explicit: 8 call sites were updated -- 7 live
KiCad-derived call sites across 6 files, plus the dead
``scripts/internal_route.py`` registration formula. Four call sites in 3
candidate areas were investigated and left unchanged: the Rust polygon
helper, the Rust benchmark helper, and the two dead JAX-era functions in
``core/state.py``. That count is the historical record of the sweep and is
left as measured; ``GUARDED_FILES`` is three shorter than it, because the
8th site's file (``scripts/internal_route.py``) and the two
``visualization/`` files have since been deleted (see the bullets above).

Exit codes (mirrors scripts/check_undeclared_imports.py, scripts/
check_pll_range_consistency.py):
  0 - clean: no guarded file contains a raw rotation-trig call.
  3 - violation: at least one guarded file contains one.
  5 - tool_error: a guarded file is missing, or the guarded-file list is
      empty (vacuous-run backstop -- never conflated with "0 violations").
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

# Every file that either carried the R(+theta)/R(-theta) bug (11 of these
# were among PR #479's 12 corrected sites -- io/_write_board.py,
# io/_write_modules.py and placer/template.py each held more than one call
# site, so 12 call sites collapse to 11 distinct files here) or is a
# hand-verified specialization of the same convention that must not
# regress into raw trig (placer/cp_sat/isolation_barrier.py -- see that
# file's own docstring for why it is exempt from calling into
# kicad_transform directly). check_pad_orientation.py is a 13th,
# independently-authored-and-already-correct implementation folded into
# the same sanctioned module; guarded for the same reason.
#
# The entries below were added by the second sweep documented in this
# module's own docstring (12 call sites in 9 candidate areas). They cover
# the 7 live KiCad-derived call sites across 6 files; the Rust benchmark and
# polygon helper, and core/state.py's two dead functions, were investigated
# and deliberately not guarded (see that section for why: isolated or dead).
# The sweep's 8th site, scripts/internal_route.py, was also fixed but its
# file was deleted on 2026-08-04 as import-dead, so it is not guarded here:
# run() requires every guarded file to exist. visualization/board_renderer.py
# and visualization/model.py were fixed too, but the whole visualization/
# package was deleted 2026-08-11 (commit cb36af61, "deprecate the dead
# visualization/ package") -- removed here 2026-08-13 for the same reason.
GUARDED_FILES: tuple[str, ...] = (
    "packages/temper-placer/src/temper_placer/core/courtyard.py",
    "packages/temper-placer/src/temper_placer/core/pin_geometry.py",
    "packages/temper-placer/src/temper_placer/deterministic/stages/setup.py",
    "packages/temper-placer/src/temper_placer/io/_parse_modules.py",
    "packages/temper-placer/src/temper_placer/io/_write_board.py",
    "packages/temper-placer/src/temper_placer/io/_write_modules.py",
    "packages/temper-placer/src/temper_placer/io/kicad_exporter.py",
    "packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py",
    "packages/temper-placer/src/temper_placer/placer/template.py",
    "packages/temper-placer/src/temper_placer/requirements/validators/_copper.py",
    "packages/temper-placer/src/temper_placer/router_v6/connectivity.py",
    "packages/temper-placer/src/temper_placer/router_v6/constraints_geometry.py",
    "packages/temper-placer/src/temper_placer/router_v6/escape_via_generator.py",
    "scripts/check_isolation_keepout.py",
    "scripts/check_pad_orientation.py",
)

# (file, function name) pairs inside a guarded file that are exempt --
# each one is a DIFFERENT computation than the local-offset-relative-to-
# parent-origin pattern this gate exists to catch, verified individually
# (not blanket-exempted) before being added here. Every entry needs the
# same kind of justification an allowlist entry gets elsewhere in this
# repo (``.undeclared-imports-allowlist``'s convention) -- see the comment
# on each entry, not just this preamble.
EXEMPT_FUNCTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        # placer/template.py::_cos_sin -- Wave-4 Phase-4 migration. The
        # R(-theta) formula that this file once hosted (and that this gate
        # exists to stop it re-hosting) has MOVED to the Rust kernel
        # ``placer_core::placer_compute::apply_{component,parametric}_
        # template`` (packages/temper-io-types), where it is transcribed
        # from kicad_transform and pinned bit-identical by the differential
        # suite (tests/placer/test_placer_template_rust_differential.py).
        # The Python shim's ``_cos_sin(theta)`` returns the (cos, sin)
        # *transcendental pair* the kernel calls back into -- CPython's
        # ``math.cos``/``math.sin`` are the oracle's libm bits (Rust
        # ``f64::sin`` is 1-ULP-divergent on this platform, measured
        # 2026-08-05), so the seam exists precisely so the kernel does NOT
        # re-type the transcendental. It computes no rotation at all; the
        # formula the gate guards against lives only in the pinned Rust
        # kernel now. Re-checking this exemption means re-confirming
        # ``_cos_sin`` still contains only ``math.cos``/``math.sin`` and no
        # rel/abs arithmetic.
        ("packages/temper-placer/src/temper_placer/placer/template.py", "_cos_sin"),
        # router_v6/connectivity.py::_to_pad_coordinates -- an exemption
        # entry briefly existed here (added 2026-08-13, removed 2026-08-14)
        # on the theory that this test-only helper's `R(-rotation)`
        # formula was a *deliberately* sign-divergent pinned oracle meant
        # to "detect the Rust kernel's opposite R(+theta) convention".
        # That was backwards: real `pcbnew` ground truth
        # (`scripts/kicad_pad_rotation_oracle.py`) confirms the Rust
        # kernel's R(+theta) is correct and this helper's R(-rotation) was
        # a regression of a bug already fixed once by 8d89069c2
        # (2026-07-30) and reintroduced by 96eb1ce09 (2026-08-09, "restore
        # _to_pad_coordinates as verbatim Python") re-typing the
        # *pre-fix* formula from scratch instead of the corrected one.
        # Re-fixed 2026-08-14 to delegate to
        # `temper_placer.geometry.kicad_transform.rotate_world_to_local_deg`
        # -- see that function's own docstring. It contains no raw trig
        # anymore, so the exemption entry is removed, not just corrected.
    }
)

_TRIG_MODULES = frozenset({"math", "np", "numpy"})
_TRIG_FUNCS = frozenset({"cos", "sin"})


# ===========================================================================
# THE RUST HALF (added 2026-08-18)
# ===========================================================================
#
# Why there was none, and why that stopped being defensible
# ---------------------------------------------------------
# The section above says this AST lint "has no Rust equivalent,
# deliberately -- there is no comparable '13 proven-vulnerable files'
# precedent on the Rust side yet". That was written when the only Rust
# rotation code was a generic polygon helper and a benchmark. It is no
# longer true. A sweep on 2026-08-18 found the KiCad footprint-child
# convention typed out by hand in **ten** Rust functions across six crates,
# plus three copies of the integer quadrant table that is the same
# transform for 0/90/180/270, plus one site that had the convention
# outright WRONG:
#
#   `clearance_geometry.rs::shapely_rotation_cos_sin` -- the bit-exact Rust
#   twin of `pad_geometry.py::pad_core_polygon` -- rotated every pad's
#   copper rectangle R(+theta). It was invisible only because all 527 pads
#   on `pcb/temper.kicad_pcb` sit at multiples of 90 degrees, where the two
#   conventions give the same corner SET. Correct by coincidence of
#   placement, not by construction. The bug the Python half of this gate
#   was built to prevent had simply moved across the FFI boundary, into the
#   half nothing was watching.
#
# So the precedent now exists, and it is worse than the Python one: on the
# Rust side the wrong formula is invisible from Python, the differential
# suites pin Rust against Python (so a consistently-wrong PAIR passes), and
# the compiled `.so` cannot be read by anyone reviewing the shim above it.
#
# What is checked, and why it is textual rather than AST
# -------------------------------------------------------
# There is no Rust parser in this repo's dependency set and adding one to
# run a lint would be a heavier commitment than the lint is worth
# (`scripts/check_rotation_quadrant_arithmetic.py` sets the precedent: it
# scans `.rs` textually for exactly this reason). So: each file in
# `GUARDED_RUST_FILES` is scanned for any raw trig call token, with
# comments stripped and the enclosing `fn` name tracked by brace depth so
# that exemptions can be per-function exactly as on the Python side.
#
# Keying on the trig CALL rather than on the formula shape is deliberate.
# The formula appears with at least eight different identifier pairs
# (`c/s`, `cos/sin`, `cos_a/sin_a`, `cos_r/sin_r`, `cosp/sinp`, `c/sn`,
# inline `t.cos()/t.sin()`, ...) and in both sign arrangements; a textual
# matcher for the shape would be both leaky and false-positive-prone. The
# trig call is the necessary precondition for typing the formula at all,
# and requiring the guarded files to obtain cos/sin only from
# `kicad_transform` is the same removal-of-capability the Python half
# performs.
#
# The token list covers every spelling the sweep actually found, because a
# lint keyed only on `.cos()` would have missed FIVE of the ten sites --
# they call `pad_geometry::math_cos_sin` or `host_math::cos`, this repo's
# two dlsym host-libm shims, not `f64::cos`.

# Rust files that host, or have hosted, KiCad's footprint-child rotation.
# Same rule as GUARDED_FILES: a file here that goes missing is a GATE
# ERROR, not a silently smaller check.
GUARDED_RUST_FILES: tuple[str, ...] = (
    # Migrated to call kicad_transform on 2026-08-18 -- guarded so they
    # cannot drift back. Each was verified bit-identical before the swap:
    # `kicad_transform` resolves cos/sin through `pad_geometry::
    # math_cos_sin`, which is the same `dlsym(RTLD_DEFAULT, "cos"/"sin")`
    # pointer `host_math::cos`/`sin` resolves, with the same
    # `f64::cos`/`f64::sin` fallback.
    "packages/temper-geometry/src/clearance_geometry.rs",
    "packages/temper-geometry/src/congestion_analysis.rs",
    "packages/temper-geometry/src/connectivity_kernels.rs",
    "packages/temper-geometry/src/core_graph_geometry.rs",
    "packages/temper-geometry/src/drc_constraints_geometry.rs",
    "packages/temper-geometry/src/escape_via.rs",
    # NOT migrated -- see RUST_EXEMPT_FUNCTIONS for the per-function
    # justification. Guarded anyway: an exemption names ONE function, so a
    # new rotation typed into a different function in the same file still
    # fails.
    "packages/temper-geometry/src/transform.rs",
    "packages/temper-geometry/src/fixed_copper.rs",
    "packages/temper-geometry/src/pad_geometry.rs",
    "packages/temper-rust-router/src/net_ordering.rs",
    "packages/temper-rust-router/src/terminal_planning.rs",
    "packages/temper-design-bundle/src/parse_engine.rs",
    "packages/temper-io-types/src/placer_core/placer_compute.rs",
)

# The sanctioned Rust implementation. Never guarded, for the same reason
# `kicad_transform.py` never is: it is the one place the formula may live.
SANCTIONED_RUST_FILE = "packages/temper-geometry/src/kicad_transform.rs"

# (file, fn name) pairs exempt from the Rust scan. Every entry carries the
# same burden of proof as the Python EXEMPT_FUNCTIONS above: the site was
# examined individually and is either a DIFFERENT computation, or a
# migration that would NOT be behaviour-preserving. "It would be awkward to
# change" is not on that list; "changing it changes the bits, and the bits
# are pinned" is.
RUST_EXEMPT_FUNCTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        # --- the two dlsym host-libm providers: these ARE the cos/sin the
        # sanctioned module itself calls. Exempting them is not a hole; it
        # is the base case.
        ("packages/temper-geometry/src/pad_geometry.rs", "math_cos"),
        ("packages/temper-geometry/src/pad_geometry.rs", "math_sin"),
        ("packages/temper-geometry/src/pad_geometry.rs", "math_cos_sin"),
        ("packages/temper-geometry/src/pad_geometry.rs", "fallback_cos"),
        ("packages/temper-geometry/src/pad_geometry.rs", "fallback_sin"),
        ("packages/temper-geometry/src/pad_geometry.rs", "host_cos"),
        ("packages/temper-geometry/src/pad_geometry.rs", "host_sin"),
        # --- support functions: sign-INVARIANT by construction, so the
        # rotation convention cannot be wrong in them. `support_radius`
        # rotates a query DIRECTION and takes |dx|,|dy|; `local_pad_half`
        # is the axis-aligned bounding box of a rotated rectangle
        # (|cos|,|sin|). Neither places a point, and both give the same
        # answer under either convention -- verified by inspection of the
        # absolute values, not assumed.
        ("packages/temper-geometry/src/pad_geometry.rs", "support_radius"),
        ("packages/temper-geometry/src/fixed_copper.rs", "local_pad_half"),
        # --- transform.rs::transform_pin_position / transform_pin_positions
        # and get_rotation_matrix / rotate_point / rotate_points /
        # get_rotated_bounds / rotate_rectangle_corners.
        #
        # `transform_pin_position` IS the KiCad convention and IS correct,
        # but it uses plain `f64::cos`/`f64::sin`, NOT the host-libm
        # `math_cos_sin` that `kicad_transform` uses -- and those differ by
        # 1 ulp on this platform (measured 2026-08-05; `kicad_transform.rs`
        # documents exactly this divergence in its own header, naming this
        # function). Routing it through the shared helper would therefore
        # CHANGE ITS OUTPUT BITS, which is the opposite of a
        # behaviour-preserving migration, and its consumers are the
        # crate's own Rust callers rather than a pinned Python oracle. It
        # is left as its own copy, guarded here so a NEW function in this
        # file cannot join it silently. The `get_rotation_matrix` family is
        # a different computation entirely: generic CCW R(+theta) geometry
        # with no KiCad correspondence (same verdict polygon.rs::
        # rotate_polygon already carries in the Python section above).
        ("packages/temper-geometry/src/transform.rs", "transform_pin_position"),
        ("packages/temper-geometry/src/transform.rs", "transform_pin_positions"),
        ("packages/temper-geometry/src/transform.rs", "get_rotation_matrix"),
        # --- temper-rust-router: `net_ordering.rs` and `terminal_planning.rs`
        # both carry a correct R(-theta) copy on plain `f64::cos`/`sin`.
        # `temper-rust-router` does NOT depend on `temper-geometry` (its
        # Cargo.toml lists only `temper-rust-router-core`), and
        # `net_ordering.rs`'s own comment records that as the reason for
        # the duplication. Adding a crate dependency to a routing crate to
        # share a two-line function is a bigger change than this one, and
        # it would also move these sites off plain `f64` trig onto the
        # host-libm path -- a bit change, not a no-op. Registered as
        # exempt, deliberately and visibly, rather than left unguarded:
        # the file is scanned, so a THIRD rotation in either file fails.
        ("packages/temper-rust-router/src/net_ordering.rs", "rotate_local_to_world"),
        ("packages/temper-rust-router/src/terminal_planning.rs", "rotate_local_to_world"),
        # --- parse_engine.rs::extract_components_pure -- the `.kicad_pcb`
        # parse path. Correct R(-theta) today. `temper-design-bundle` DOES
        # depend on `temper-geometry`, so the dependency is not the
        # blocker; the arithmetic is. This site converts with
        # `f64::to_radians`, while `kicad_transform`'s degrees wrapper uses
        # the CPython-shaped `t * (PI / 180.0)` -- the two are not required
        # to agree in the last bit, and this function's output feeds the
        # parsed component positions that every downstream pin is measured
        # from. Migrating it needs its own differential on real board
        # geometry, which is a separate change from this one; it is
        # recorded here so that "not migrated" is a decision on the record
        # rather than an omission.
        ("packages/temper-design-bundle/src/parse_engine.rs", "extract_components_pure"),
        # --- placer_compute.rs::apply_component_template /
        # apply_parametric_template. Correct R(-theta), and structurally
        # unable to call `kicad_transform`: it takes cos/sin as an INJECTED
        # CALLBACK (`cos_sin: &dyn Fn(f64) -> Result<(f64, f64), E>`) whose
        # production implementation calls back into CPython's own
        # `math.cos`/`math.sin`, precisely so the kernel does not re-type
        # the transcendental. That seam is itself a
        # `check_no_raw_rotation_trig` exemption on the Python side
        # (`placer/template.py::_cos_sin`). `temper-io-types` also does not
        # depend on `temper-geometry`.
        ("packages/temper-io-types/src/placer_core/placer_compute.rs", "apply_component_template"),
        ("packages/temper-io-types/src/placer_core/placer_compute.rs", "apply_parametric_template"),
        # --- placer_compute.rs, NOT rotations: `place_by_proximity` is a
        # spiral/polar placement search and `adjust_for_congestion` builds
        # a random unit push vector. Same class as the Python
        # `placer/deterministic.py` family the section above declined to
        # guard.
        ("packages/temper-io-types/src/placer_core/placer_compute.rs", "place_by_proximity"),
        ("packages/temper-io-types/src/placer_core/placer_compute.rs", "adjust_for_congestion"),
        # --- placer_compute.rs::cos_sin -- the in-crate TEST implementation
        # of the injected callback above (`Ok((theta.cos(), theta.sin()))`).
        # It is the stand-in for CPython's math.cos/sin, not a rotation; the
        # production path never reaches it.
        ("packages/temper-io-types/src/placer_core/placer_compute.rs", "cos_sin"),
        # --- SHAPELY/NUMPY AFFINE REPLICAS. These two legitimately need
        # their own trig, and it is NOT the rotation formula: they replicate
        # `shapely.affinity.rotate`'s internals, including its own
        # degrees->radians round trip and its `abs(cos/sin) < 2.5e-16 -> 0.0`
        # snap, which `kicad_transform` deliberately does not have (it is a
        # point transform, not an affine builder). What they must NOT type
        # themselves is the SIGN, and neither does: both call
        # `kicad_transform::shapely_rotation_angle_deg` to get the CCW angle
        # shapely wants from KiCad's R(-theta). `shapely_rotation_cos_sin`
        # is exactly where the missing sign flip lived until 2026-08-18, so
        # the exemption is scoped to the trig call, and the sign it derives
        # is pinned against pcbnew by
        # `scripts/check_pad_core_polygon_oracle.py`.
        ("packages/temper-geometry/src/clearance_geometry.rs", "shapely_rotation_cos_sin"),
        ("packages/temper-geometry/src/core_graph_geometry.rs", "courtyard_global_points"),
        # --- net_ordering.rs test: asserts that cos(PI/2) is NOT exactly
        # 0.0, i.e. that a 90-degree quadrant rotation is not an exact axis
        # swap. The trig residue IS the subject of the test; routing it
        # through a helper would delete the thing being measured.
        (
            "packages/temper-rust-router/src/net_ordering.rs",
            "quadrant_rotation_is_not_an_exact_axis_swap",
        ),
    }
)

# Registered duplicate integer quadrant tables: the SAME 0/90/180/270
# rotation as the trig formula, written as a `match` with no trig at all,
# so the scan above is structurally blind to them.
#
# Two byte-identical copies of this table exist. They are not consolidated
# here because they differ in a real, deliberate way at the boundary:
# `pad_geometry.rs`'s has a `_` catch-all that folds out-of-range indices
# onto the rot==3 arm, while `clearance.rs`'s returns `None` (raising
# `KeyError` at the Python boundary). Making either adopt the other's
# behaviour is a semantic change, not a refactor. What CAN be enforced for
# free is that the four in-range arms never drift apart -- which is the
# failure mode that matters, and the one a reader of either file alone
# cannot see.
RUST_QUADRANT_TABLE_TWINS: tuple[tuple[str, str, str, str], ...] = (
    (
        "packages/temper-geometry/src/pad_geometry.rs",
        "project_onto_barrier_axis",
        "packages/temper-orchestration/src/clearance.rs",
        "project_onto_barrier_axis_impl",
    ),
)

# The in-range arms both twins must agree on: KiCad's R(-theta) at
# 0/90/180/270. Written here as normalized text so the check is a
# comparison against a stated expectation, not merely "the two files agree"
# (two copies can drift together).
_QUADRANT_EXPECTED = (
    ("0", "(local_x,local_y)"),
    ("1", "(local_y,-local_x)"),
    ("2", "(-local_x,-local_y)"),
    ("3", "(-local_y,local_x)"),
)

# Every spelling of a trig call the 2026-08-18 sweep found in this repo's
# Rust. `.sin_cos()` is included because it is one call producing both
# halves of a rotation; `cos_sin(` because `placer_compute.rs` receives the
# pair through an injected callback.
_RUST_TRIG_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\.cos\s*\(\s*\)", "f64::cos method call"),
    (r"\.sin\s*\(\s*\)", "f64::sin method call"),
    (r"\.sin_cos\s*\(\s*\)", "f64::sin_cos method call"),
    (r"\bf64\s*::\s*cos\s*\(", "f64::cos"),
    (r"\bf64\s*::\s*sin\s*\(", "f64::sin"),
    (r"\bhost_math\s*::\s*cos\s*\(", "host_math::cos (dlsym host libm)"),
    (r"\bhost_math\s*::\s*sin\s*\(", "host_math::sin (dlsym host libm)"),
    (r"\bhostmath\s*::\s*cos\s*\(", "hostmath::cos (dlsym host libm)"),
    (r"\bhostmath\s*::\s*sin\s*\(", "hostmath::sin (dlsym host libm)"),
    (r"\bpymath\s*::\s*cos\s*\(", "pymath::cos (dlsym host libm)"),
    (r"\bpymath\s*::\s*sin\s*\(", "pymath::sin (dlsym host libm)"),
    (r"\bmath_cos_sin\s*\(", "pad_geometry::math_cos_sin (dlsym host libm)"),
    (r"\bmath_cos\s*\(", "pad_geometry::math_cos (dlsym host libm)"),
    (r"\bmath_sin\s*\(", "pad_geometry::math_sin (dlsym host libm)"),
    (r"\bcos_sin\s*\(", "injected cos/sin callback"),
)


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass(frozen=True)
class Violation:
    path: str
    lineno: int
    detail: str


@dataclass
class Report:
    files_checked: int = 0
    rust_files_checked: int = 0
    quadrant_twins_checked: int = 0
    violations: list[Violation] = field(default_factory=list)


def _module_aliases(tree: ast.Module) -> dict[str, str]:
    """Map local name -> real module name for ``import X`` / ``import X as
    Y`` statements at any depth (module-level or not -- a guarded file
    importing math inside a function is exactly as capable of hosting the
    bug as a top-level import)."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _TRIG_MODULES:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


def _bare_trig_names(tree: ast.Module) -> dict[str, str]:
    """Map local name -> real function name for ``from math import cos``
    (or ``sin``, or the numpy equivalents), including aliased imports
    (``from math import cos as mcos``)."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _TRIG_MODULES:
            for alias in node.names:
                if alias.name in _TRIG_FUNCS:
                    names[alias.asname or alias.name] = alias.name
    return names


def _exempt_line_ranges(tree: ast.Module, rel: str) -> list[tuple[int, int]]:
    """Line ranges (inclusive) of functions exempted for this file via
    ``EXEMPT_FUNCTIONS``. A named exemption that matches no function in
    the file is silently unused, not an error -- functions get renamed;
    this only matters if it hides a real violation, and an unused
    exemption cannot do that (see ``run``'s own "used" bookkeeping for
    the case that does matter: an exemption that's never reachable at
    all because the file itself is gone)."""
    wanted = {func for (f, func) in EXEMPT_FUNCTIONS if f == rel}
    if not wanted:
        return []
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            end = node.end_lineno if node.end_lineno is not None else node.lineno
            ranges.append((node.lineno, end))
    return ranges


def _find_violations(path: Path, repo_root: Path) -> list[Violation]:
    try:
        source = path.read_text()
    except OSError as e:
        raise GateError(f"{path}: could not read file: {e}") from None

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise GateError(f"{path}: could not parse as Python: {e}") from None

    module_aliases = _module_aliases(tree)
    bare_names = _bare_trig_names(tree)
    rel = str(path.relative_to(repo_root))
    exempt_ranges = _exempt_line_ranges(tree, rel)

    def _is_exempt(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in exempt_ranges)

    found: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # Qualified form: math.cos(...), np.sin(...), an aliased "import
        # math as m" -> m.cos(...), etc.
        if isinstance(func, ast.Attribute) and func.attr in _TRIG_FUNCS:
            if (
                isinstance(func.value, ast.Name)
                and func.value.id in module_aliases
                and not _is_exempt(node.lineno)
            ):
                real_module = module_aliases[func.value.id]
                found.append(
                    Violation(
                        rel,
                        node.lineno,
                        f"{func.value.id}.{func.attr}(...) -- raw call into "
                        f"'{real_module}.{func.attr}', not "
                        "temper_placer.geometry.kicad_transform",
                    )
                )
                continue

        # Bare form: from math import cos; ...; cos(...)
        if isinstance(func, ast.Name) and func.id in bare_names and not _is_exempt(node.lineno):
            found.append(
                Violation(
                    rel,
                    node.lineno,
                    f"{func.id}(...) -- raw call (imported via 'from ... import "
                    f"{func.id}'), not temper_placer.geometry.kicad_transform",
                )
            )

    return found


# ---------------------------------------------------------------------------
# Rust scanning
# ---------------------------------------------------------------------------

_RUST_FN_RE = re.compile(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)")
_RUST_TRIG_RE = tuple((re.compile(p), label) for p, label in _RUST_TRIG_PATTERNS)


def _strip_rust_comments(line: str) -> str:
    """Drop everything from an unquoted ``//`` to end of line.

    Deliberately simple: it tracks double-quote parity and a backslash
    escape so a ``//`` inside a string literal is not treated as a comment,
    which is the only case in these files that would cause a MISSED
    violation. Block comments are not stripped -- a ``/* ... */`` wrapping
    a rotation would be reported. That direction is the safe one: this gate
    over-reports rather than under-reports, and a spurious hit is one
    exemption entry away from resolution while a miss is another 2026-07-29.
    """
    out = []
    in_str = False
    escaped = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            out.append(ch)
        else:
            if ch == '"':
                in_str = True
                out.append(ch)
            elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _rust_enclosing_functions(lines: list[str]) -> list[str | None]:
    """For each 0-based line, the name of the innermost ``fn`` whose body
    encloses it (or ``None`` outside any function).

    Brace-depth tracking over comment-stripped lines, with a stack of
    ``(name, depth_at_open)``. Good enough to attribute a trig call to a
    function for exemption purposes; it does not need to be a Rust parser,
    and a mis-attribution can only make an exemption fail to apply -- i.e.
    fail LOUD, never silently exempt something it should not.
    """
    result: list[str | None] = []
    stack: list[tuple[str, int]] = []
    depth = 0
    pending: str | None = None
    for raw in lines:
        code = _strip_rust_comments(raw)
        m = _RUST_FN_RE.search(code)
        if m:
            pending = m.group(1)
        # The name applying to THIS line is the innermost open fn.
        result.append(stack[-1][0] if stack else pending)
        for ch in code:
            if ch == "{":
                depth += 1
                if pending is not None:
                    stack.append((pending, depth))
                    pending = None
            elif ch == "}":
                if stack and stack[-1][1] == depth:
                    stack.pop()
                depth -= 1
    return result


def _find_rust_violations(path: Path, repo_root: Path) -> list[Violation]:
    try:
        source = path.read_text()
    except OSError as e:
        raise GateError(f"{path}: could not read file: {e}") from None

    rel = str(path.relative_to(repo_root))
    exempt = {fn for (f, fn) in RUST_EXEMPT_FUNCTIONS if f == rel}

    lines = source.splitlines()
    owners = _rust_enclosing_functions(lines)

    found: list[Violation] = []
    for idx, raw in enumerate(lines):
        code = _strip_rust_comments(raw)
        if not code.strip():
            continue
        owner = owners[idx]
        if owner is not None and owner in exempt:
            continue
        for regex, label in _RUST_TRIG_RE:
            if regex.search(code):
                found.append(
                    Violation(
                        rel,
                        idx + 1,
                        f"{label} in fn {owner or '<module>'}(...) -- raw trig, not "
                        "temper_geometry::kicad_transform",
                    )
                )
                break
    return found


def _quadrant_arms(path: Path, fn_name: str) -> list[tuple[str, str]]:
    """Extract ``index => (expr, expr)`` arms from a quadrant-table ``match``
    inside *fn_name*, whitespace-normalized."""
    try:
        lines = path.read_text().splitlines()
    except OSError as e:
        raise GateError(f"{path}: could not read file: {e}") from None
    owners = _rust_enclosing_functions(lines)
    # `_ =>` is accepted as an arm label because one of the two twins ends
    # its table with a catch-all instead of an explicit `3` (that boundary
    # difference is deliberate -- see RUST_QUADRANT_TABLE_TWINS). It is
    # normalized to "3" ONLY when it is the fourth arm, so a table that
    # dropped an arm and widened the catch-all cannot pass by accident.
    arm_re = re.compile(r"^\s*([0-9]+|_)\s*=>\s*(\([^)]*\))\s*,")
    arms: list[tuple[str, str]] = []
    seen_fn = False
    for idx, raw in enumerate(lines):
        if owners[idx] != fn_name:
            continue
        seen_fn = True
        m = arm_re.match(_strip_rust_comments(raw))
        if m:
            label = m.group(1)
            if label == "_":
                label = str(len(arms)) if len(arms) == 3 else f"_@{len(arms)}"
            arms.append((label, re.sub(r"\s+", "", m.group(2))))
    if not seen_fn:
        raise GateError(
            f"{path}: registered quadrant-table function '{fn_name}' was not found -- "
            "RUST_QUADRANT_TABLE_TWINS has drifted from the repo (a rename must update "
            "this list, not silently shrink the gate)"
        )
    return arms


def _find_quadrant_violations(repo_root: Path) -> list[Violation]:
    found: list[Violation] = []
    for path_a, fn_a, path_b, fn_b in RUST_QUADRANT_TABLE_TWINS:
        for rel in (path_a, path_b):
            if not (repo_root / rel).is_file():
                raise GateError(
                    f"registered quadrant-table file '{rel}' does not exist -- "
                    "RUST_QUADRANT_TABLE_TWINS has drifted from the repo"
                )
        arms_a = _quadrant_arms(repo_root / path_a, fn_a)
        arms_b = _quadrant_arms(repo_root / path_b, fn_b)
        expected = list(_QUADRANT_EXPECTED)
        for rel, fn, arms in ((path_a, fn_a, arms_a), (path_b, fn_b, arms_b)):
            if arms != expected:
                found.append(
                    Violation(
                        rel,
                        0,
                        f"{fn}'s quadrant table is {arms}, expected KiCad's R(-theta) "
                        f"{expected}. Two copies of this table exist ({path_a} and "
                        f"{path_b}); they are compared against a STATED expectation, not "
                        "only against each other, because two copies can drift together.",
                    )
                )
    return found


def run(repo_root: Path, *, include_python: bool = True, include_rust: bool = True) -> Report:
    """Scan both halves. The two flags exist ONLY so this gate's own unit
    tests can drive one detector at a time over a synthetic tree; CI always
    runs with both on, and `main()` offers no way to turn either off. A
    flag that could silence half the gate from the command line would be
    the "make a check pass by weakening it" move this repo forbids."""
    report = Report()

    if not include_python and not include_rust:
        raise GateError("both halves disabled -- vacuous run, refusing to report clean")

    if include_python:
        _run_python(repo_root, report)
    if include_rust:
        _run_rust(repo_root, report)
    return report


def _run_python(repo_root: Path, report: Report) -> None:
    if not GUARDED_FILES:
        raise GateError("GUARDED_FILES is empty -- vacuous run, refusing to report clean")

    for rel in GUARDED_FILES:
        path = repo_root / rel
        if not path.is_file():
            raise GateError(
                f"guarded file '{rel}' does not exist -- GUARDED_FILES has drifted from "
                "the repo (a rename/move must update this list, not silently shrink the "
                "gate's coverage)"
            )
        report.files_checked += 1
        report.violations.extend(_find_violations(path, repo_root))


def _run_rust(repo_root: Path, report: Report) -> None:
    if not GUARDED_RUST_FILES:
        raise GateError("GUARDED_RUST_FILES is empty -- vacuous run, refusing to report clean")

    sanctioned = repo_root / SANCTIONED_RUST_FILE
    if not sanctioned.is_file():
        raise GateError(
            f"the sanctioned Rust implementation '{SANCTIONED_RUST_FILE}' does not exist. "
            "Every guarded Rust site is required to delegate to it; if it moved, this gate "
            "must be updated before it can report clean."
        )
    if sanctioned.name in {Path(r).name for r in GUARDED_RUST_FILES}:
        raise GateError(
            f"'{SANCTIONED_RUST_FILE}' appears in GUARDED_RUST_FILES -- it is the one place "
            "the formula may live and must never be guarded against itself"
        )

    for rel in GUARDED_RUST_FILES:
        path = repo_root / rel
        if not path.is_file():
            raise GateError(
                f"guarded Rust file '{rel}' does not exist -- GUARDED_RUST_FILES has drifted "
                "from the repo (a rename/move must update this list, not silently shrink the "
                "gate's coverage)"
            )
        report.rust_files_checked += 1
        report.violations.extend(_find_rust_violations(path, repo_root))

    report.violations.extend(_find_quadrant_violations(repo_root))
    report.quadrant_twins_checked = len(RUST_QUADRANT_TABLE_TWINS)


def _print_report(report: Report) -> None:
    if report.violations:
        print(f"=== VIOLATIONS: {len(report.violations)} ===\n")
        for v in report.violations:
            print(f"  {v.path}:{v.lineno}: {v.detail}")
        print(
            "\nFAILED -- raw rotation trig found in a file that has already proven "
            "capable of hosting the R(+theta)/R(-theta) sign bug. Use "
            "temper_placer.geometry.kicad_transform (Python) or "
            "temper_geometry::kicad_transform (Rust) instead -- see those modules' "
            "docstrings. If the site genuinely needs its own maths, add a JUSTIFIED "
            "entry to EXEMPT_FUNCTIONS / RUST_EXEMPT_FUNCTIONS naming the function and "
            "saying why -- never widen the scan."
        )
    else:
        print(
            f"PASS -- no raw rotation trig in {report.files_checked} guarded Python file(s) "
            f"or {report.rust_files_checked} guarded Rust file(s); "
            f"{report.quadrant_twins_checked} quadrant-table twin(s) still agree with "
            "KiCad's R(-theta). kicad_transform remains the single implementation on both "
            "sides of the FFI boundary."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.parse_args()

    repo_root = find_repo_root()

    try:
        report = run(repo_root)
    except GateError as e:
        print(f"TOOL ERROR: {e}")
        sys.exit(5)

    _print_report(report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            state = "violation" if report.violations else "clean"
            f.write(f"\n### No-raw-rotation-trig gate: {state}\n")
            f.write(
                f"- Guarded Python files checked: {report.files_checked}\n"
                f"- Guarded Rust files checked: {report.rust_files_checked}\n"
                f"- Quadrant-table twins checked: {report.quadrant_twins_checked}\n"
                f"- Violations: {len(report.violations)}\n"
            )

    sys.exit(3 if report.violations else 0)


if __name__ == "__main__":
    main()

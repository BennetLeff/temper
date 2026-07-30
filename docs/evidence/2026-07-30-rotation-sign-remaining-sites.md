# Rotation-sign sweep, round 2: 12 call sites in 9 candidate areas beyond PR #479/#491

**Date:** 2026-07-30
**Scope:** `pcb/**` and `elec/src/**` read-only throughout. No board file was written. Fixes are
production `.py`/lint-only; `pcb/temper.kicad_pcb`'s own measured DRC/orientation state is unchanged
(confirmed in Sec. 4 -- every fix is a no-op on the current board, all of whose footprints sit at
90-degree-multiple rotations).

## 0. Background

PR #479 fixed 12 sites carrying an R(+theta)/R(-theta) sign error (this repo used standard-math CCW
R(+theta) for a footprint child's rotation; KiCad actually uses R(-theta)). PR #491 consolidated all
12 (plus `check_pad_orientation.py`'s independently-correct 13th) behind
`temper_placer.geometry.kicad_transform` and added `scripts/check_no_raw_rotation_trig.py`, an AST
lint scoped to an exact 12-file list covering the original 13 call sites (several files contain
more than one site).

A follow-up sweep (grep for `math.cos`/`math.sin`/`np.cos`/`np.sin` outside tests, cross-checked
against every production `.py` file that imports `math` or `numpy` and every `.rs` file with
`.cos()`/`.sin()`) found 12 more call sites carrying the same shape of bug, grouped into 9
candidate areas, none in the original 12 plus the pre-existing 13th call site, and none guarded
by the lint. Each was classified
individually against the test this whole gate exists to apply: **does this site transform
something that must agree with KiCad's own placement, or is it self-contained with no KiCad
correspondence?**

## 1. Classification and disposition

| Site | Verdict | Why |
|---|---|---|
| `scripts/check_pad_orientation.py::_corners` | **Genuine bug, fixed** | A live CI gate computing real pad geometry; was exempted from the lint on a "corner-set invariant at 90-degree multiples" argument that is true but does not generalize to non-90 angles a future board could carry. |
| `router_v6/constraints_geometry.py::RotatedRect.corners` | **Genuine bug, fixed** | `.rotation` is populated from real board pad/component rotation (`deterministic/stages/setup.py`). |
| `router_v6/constraints_geometry.py::point_to_rotated_rect_distance` | **Genuine bug, fixed** | Same KiCad-derived `.rotation`; additionally not a simple sign flip -- it inverted the *old, wrong* R(+theta) convention (negate the angle, reapply R(+theta)) instead of the true inverse of the corrected R(-theta) convention, i.e. it silently recomputed the forward transform instead of world-to-local. |
| `router_v6/connectivity.py::_to_pad_coordinates` | **Genuine bug, fixed** | Same forward/inverse confusion as above, on `CopperPad.rotation` (a field that exists to hold real pad orientation; no production caller populates it non-zero today, but that does not change what the field is *for*). |
| `router_v6/escape_via_generator.py` dog-bone candidate rotation | **Genuine bug, fixed** | Rotates a symmetric offset by the component's real board rotation to place a via next to a real pin (`core.pin_geometry`, itself KiCad-derived). Masked today because `Component.initial_rotation` is typed as a 0-3 quadrant index, at which a symmetric 4-way candidate set is set-invariant to R(+theta) vs R(-theta). |
| `visualization/model.py::Rectangle.corners` | **Genuine bug, fixed** | Renders a visual proxy of the real board; `ComponentView.rotation` is meant to hold real component orientation. Masked today by the placer's discrete quadrant-only rotation state. |
| `visualization/board_renderer.py::get_pad_shapes` | **Genuine bug, fixed** | Same pattern for `PadView.rotation`; masked because `PadView` has no production constructor today (test-only). |
| `scripts/internal_route.py` (pad-position registration) | **Genuine bug, fixed; script itself is dead** | Reads a real `kiutils` board and registers real pad positions with a routing oracle -- squarely KiCad-derived. The rotation formula is fixed, but the script currently cannot import at all for unrelated, pre-existing reasons: it imports `jax` (removed from the dependency set per an earlier "JAX retirement" commit) and a `temper_placer.routing` package that does not exist anywhere in this repo (only `router_v6` does; `scripts/internal_route.py` was apparently never updated after a rename). That breakage predates this work and is out of scope here -- fixing it would mean redesigning the script's entire integration, not a two-line rotation formula. |
| `packages/temper-geometry/src/polygon.rs::rotate_polygon` | **Not a bug -- isolated** | Rotates a polygon about its own centroid. Zero production callers in Rust or through the pyo3 bridge (confirmed by grep across `packages/` and `scripts/`); the only callers are property-based tests (`proptest_equivalence.rs`, `test_geometry_pbt.py`) asserting `polygon_area` is rotation-invariant, which holds under either sign. Nothing KiCad-derived flows in or out. |
| `scripts/bench_rust_geometry.py::_py_rotate_point` | **Not a bug -- isolated** | Times `_tg.rotate_point` (`transform.rs::rotate_point`, the *generic* CCW rotation via `get_rotation_matrix`, **not** the already-correct KiCad-specific `transform_pin_position`) against a plain-Python CCW reimplementation. Both sides deliberately agree on the generic convention under benchmark; neither touches KiCad data. |
| `core/state.py::rotation_matrix` / `rotate_points` | **Not a bug -- dead code** | Deprecated JAX-era leftover (`sample_rotation`, two functions above it, is already marked `DEPRECATED`). Zero production callers (confirmed by grep); only referenced from `tests/core/test_state.py` and `tests/geometry/test_geometry.py`. |
| `scripts/benchmark_numba_los.py` | **Not related** | `np.cos(angle)`/`np.sin(angle)` generate a random line-of-sight ray direction for a synthetic micro-benchmark grid -- not a footprint-child rotation, no KiCad correspondence. |

Eight call sites updated: seven live KiCad-derived call sites across six files, plus the dead
`scripts/internal_route.py` registration formula. All now route through
`temper_placer.geometry.kicad_transform` (the same module PR #491 established). Four call sites
in three candidate areas were investigated and left unchanged: the Rust polygon helper, the Rust
benchmark helper, and the two dead JAX-era functions in `core/state.py`.

## 2. `check_pad_orientation.py::_corners`: why "exempt" was the wrong call

The prior exemption's own justification was correct as stated: for an origin-symmetric rectangle
at an exact 90-degree-multiple rotation, R(+theta) and R(-theta) produce the identical corner
**set** (proven in the lint's own docstring). But "identical corner set on this specific board" is
not "correct at every angle a future board could carry" -- and this is a live CI gate meant to run
on arbitrary input boards, not just `pcb/temper.kicad_pcb`. Verified numerically: at 0/90/180/270
degrees the rotated corner sets coincide; at 37 and 45 degrees they diverge (see Sec. 3 for the
oracle-verified numbers). The gate's separating-axis overlap test happened to agree with the
correct answer on every board it has ever run against, purely because every one of those boards
only used quadrant rotations -- not because the formula was right. Fixed to route through
`kicad_transform.place_local_to_world`; the lint's `EXEMPT_FUNCTIONS` entry for `_corners` is
removed (the function no longer contains raw trig for the lint to exempt).

## 3. Oracle verification (non-90-degree angles)

`packages/temper-placer/tests/requirements/safety/test_rotation_convention_remaining_sites_oracle.py`
adds 8 tests, one or more per fixed site, all at 37 or 45 degrees (never a multiple of 90), each
checked against real `pcbnew` (KiCad's own placement engine) via the existing
`scripts/kicad_pad_rotation_oracle.py` / `_pcbnew_oracle_batch` plumbing from
`test_rotation_convention_oracle.py` (reused, not reimplemented). Representative result at 37
degrees, local offset (0.5, 0.3) about an origin at (12.0, -4.0):

```
pcbnew actual corner:  (12.579862, -4.061317)   <- R(-theta), what every fixed site now computes
R(+theta) CCW gives:   (12.218773, -3.459502)   <- what every fixed site computed before
```

Falsifier proof (performed, then reverted in the same turn -- see the accompanying PR's
`git status --short`): reverting `RotatedRect.corners` to the pre-fix R(+theta) formula fails
`TestRotatedRectCornersAgainstPcbnewOracle::test_corner_matches_pcbnew_at_non_90_degree_angle`
immediately (`12.218773... != 12.579862 ± 5e-06`).

`router_v6/escape_via_generator.py`'s dog-bone candidate rotation needed a special test
construction: `Component.initial_rotation` is typed as an int quadrant index (0-3), so no real
component can drive this call site past a 90-degree multiple today. The new test forces a
fractional index (0.5 -> 45 degrees, via this call site's own `angle = float(initial_rotation) *
pi/2` formula) and neutralizes an unrelated pre-existing quirk (`pin_world_position`'s
`_normalize_rotation` treats a float `initial_rotation` as radians, not a quadrant index, so it
would disagree with `escape_via_generator.py`'s own interpretation) by placing the escaped pin at
local `(0, 0)`, whose rotated position is the origin regardless of which interpretation is used.
This isolates the candidate-offset rotation -- the thing actually fixed -- as the only
rotation-dependent geometry the test exercises.

## 4. `check_pad_orientation.py` three-board discrimination (unchanged, still holds)

| Board | Expected | Result |
|---|---|---|
| `c369bc72:pcb/temper.kicad_pcb` (pre-fix) | exit 1 | exit 1 (67 unrotated-pad-body footprints, 57 intra-footprint overlaps) |
| `pcb/temper.kicad_pcb` (current, corrected) | exit 0 | exit 0 |
| `power_pcb_dataset/corpus/bitaxe_ultra/bitaxeUltra.kicad_pcb` | exit 0 | exit 0 |

## 5. Lint coverage

`scripts/check_no_raw_rotation_trig.py`'s `GUARDED_FILES` grew from 12 to 18 entries -- the 6 files
with the live fixes above plus the dead `internal_route.py` registration formula. `EXEMPT_FUNCTIONS`
is now empty (the one entry it held, `_corners`, is fixed rather than exempted). `polygon.rs`,
`bench_rust_geometry.py`, and `core/state.py`'s dead functions are deliberately NOT guarded --
see the lint's own docstring ("Second sweep" section) for the file-by-file reasoning. The
enumerated-file-list design itself is unchanged from PR #491 and, per that module's own docstring,
still the right mechanism:
the false-positive surface a directory rule would sweep in (spiral/circular placement search,
thermal gradients, synthetic layout heuristics -- all independently audited and listed in the
lint's docstring) has not shrunk, so an enumerated list of proven-vulnerable files remains more
precise than a broader rule that would need constant allowlisting.

## 6. Behaviour on the current board

Every fix above is provably a no-op on `pcb/temper.kicad_pcb` today: every footprint on that board
sits at a 90-degree-multiple rotation, and every fixed site rotates an origin- or set-symmetric
quantity (a pad/rect's own corners about its own center, or a fully symmetric 4-way candidate
offset), for which R(+theta) and R(-theta) coincide exactly at 0/180 and produce the same
mirrored-but-symmetric result at 90/270. `check_pad_orientation.py`'s own PASS/PASS/FAIL
discrimination (Sec. 4) is unchanged from before this change, confirming no measurement moved.

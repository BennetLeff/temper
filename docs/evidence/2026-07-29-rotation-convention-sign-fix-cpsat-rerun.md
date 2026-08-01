# Rotation-convention sign fix (R(+theta) -> R(-theta)), repo-wide sweep, and the CP-SAT re-run

<!-- provenance: commit=0a8e7194f0150dc310e68fada1af19af2a5ae1e4 dirty=false -->

**Date:** 2026-07-29
**Base:** `ecbc302a` (branch `fix/cross-domain-creepage-triage`, which itself
resolved the rotation-convention *question* with first-party evidence
against real `kicad-cli 10.0.4 pcb drc` -- see
`docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`).
This document's own work is two commits on top, on branch
`fix/rotation-convention-sign-error`, worktree `wt-rotation-fix`:
`6b5dbd9d` (fix: the repo-wide sign correction) and `21b4c963` (fix:
`core/courtyard.py`, found during the required test-suite re-run, plus
justified test corrections).
**Scope touched:** rotation-implementing code only (11 files in `6b5dbd9d`,
1 source file + 4 test files in `21b4c963`). No safety constant, target, or
netclass changed. No `pcb/` or `elec/` file touched --
`elec/build/default.net` sha256 verified byte-identical before/after
(`d0331f6604be9b14cce9d8741f401d134d99d5c5b9e7c6656642ac468ed2b9a6`).
**Method:** `make venv-isolate` run first; every invocation `uv run
--no-sync`; no `git stash` anywhere in this task.

---

## Headline: the CP-SAT verdict at 12.6mm survives the geometry correction

**INFEASIBLE**, in both board orientations, under the corrected R(-theta)
geometry. The prior INFEASIBLE conclusion (produced under the disproven
R(+theta) convention) is **confirmed, not reversed**.

```
Board: 152 x 234 mm, 168 components
corridor_width_mm = 12.6 (= 12.1mm PD3 creepage target + 0.5mm margin,
                           same margin convention as the existing 8.5mm
                           PD2 check's 8.0 + 0.5)

orientation=vertical:   status=infeasible  solve_time=24851ms (24.9s wall)
orientation=horizontal: status=infeasible  solve_time=24887ms (24.9s wall)

UNSAT core (both orientations): isolator_straddle_C6

Partition: 44 HV-only, 106 SELV-only, 8 isolators (C6, K1, K2, K3, PS1,
           T1, U3, U7), 10 unclassified.
Infeasible isolators (both orientations): C6, K1, K2, K3, T1, U3, U7 (7 of
           8 -- PS1 is the only isolator that clears 12.6mm on its own
           best axis).
```

Reproduced by a standalone script (`/private/tmp/.../scratchpad/
run_cpsat_barrier_12_6.py`, not committed -- a one-off driver, not a new
gate) calling `solve_placement(netlist, board, isolation_barrier={
"manifest_path": "elec/domain_manifest.yaml", "corridor_width_mm": 12.6,
"orientation": ...})` against `pcb/temper.kicad_pcb`, mirroring the
methodology of `docs/evidence/2026-07-28-barrier-constrained-placement.md`
(which ran the same check at 8.5mm/PD2, under the *disproven* R(+theta)
convention, and also got INFEASIBLE with the same 7-of-8 isolator set).

**Why the result didn't flip.** The CP-SAT model's own isolator-feasibility
arithmetic (`evaluate_isolator_feasibility` / `pad_axis_radius`) searches
all 4 axis-aligned rotations and is provably invariant to the R(+theta) vs
R(-theta) sign for axis-aligned (0/90/180/270-degree) queries -- see
"Confirmed NOT bugs" below. What *was* wrong (`_project_onto_barrier_axis`,
fixed in `6b5dbd9d`) only affects where a component's pad cluster lands
*relative to the corridor position*, not whether the cluster's own
HV-to-SELV pad separation clears 12.6mm at all. C6, K1, K2, K3, T1, U3, U7
are infeasible because their own physical pad pitch is smaller than
12.6mm on every axis -- a footprint-geometry fact the rotation-sign bug
never touched.

## Inventory: how this repo was swept for rotation implementations

**Search method** (Python): `grep -rln --include="*.py"` for
`math\.cos|math\.sin|np\.cos|np\.sin|numpy\.cos|numpy\.sin` across the
whole repo (scripts/, packages/temper-placer/src, packages/temper-placer/
tests), then manually read every hit's surrounding function to classify it
as (a) rotating a local pad/footprint/component offset by a KiCad-style
`(at x y angle)` angle into world frame -- the exact operation the
evidence doc's ground-truth experiment covers -- or (b) unrelated generic
math (polar point-scattering heuristics, benchmark reference code,
thermal/physics angle math with no footprint semantics).

**Search method** (Rust): `grep -rln --include="*.rs"` for `\.cos\(\)|\.
sin\(\)` across `packages/*/src` and `packages/*/tests`, then the same
manual classification, plus tracing every Rust rotation primitive's Python
callers (via the `temper_geometry`/`_tg` pyo3 bridge) to see whether any
caller feeds it a real KiCad-file rotation angle.

**This grep-only method has a real blind spot**, caught mid-task: it
cannot find a rotation implemented via a *named library call* instead of
raw `cos`/`sin` text. `packages/temper-placer/src/temper_placer/core/
courtyard.py` uses `shapely.affinity.rotate()` and was missed by the
initial sweep; it surfaced only because fixing the grep-found bugs and
re-running the test suite (as this task requires) made two of its
downstream tests move, at which point tracing the failure led here. It is
now fixed (`21b4c963`) and is included in the tables below. No further
non-cos/sin rotation calls (`shapely.affinity.rotate`, `numpy` rotation
matrices via other names, etc.) were found by a follow-up grep for
`affinity\.rotate|\.rotate\(` across the repo, but this is reported as a
method limitation, not a guarantee of completeness.

### Wrong (R(+theta)), fixed in this task

| File | Function | Status |
|---|---|---|
| `scripts/check_isolation_keepout.py` | `_rotate` | **Fixed.** The live gate enforcing 8.0mm mains<->SELV creepage on `origin/main`. Known-wrong site #1 per this task's brief. |
| `packages/temper-placer/src/temper_placer/io/_parse_modules.py` | center-offset rotation in `_extract_components_from_pcb` | **Fixed.** Builds `Component.initial_position` from a real `.kicad_pcb`. Known-wrong site #2. |
| `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py` | `_project_onto_barrier_axis` | **Fixed.** Its own implementation (not a shared call into `_parse_modules.py`, despite its docstring's "matches ... exactly" claim) -- inherited the R(+theta) bug for rot=1/3 (90/270 degrees). Known-wrong site #3. |
| `packages/temper-placer/src/temper_placer/core/pin_geometry.py` | `pin_world_position_at` | **Fixed.** The canonical "single source of truth for all pad-position computation" (its own docstring), consumed by ~20 files across `router_v6`, `deterministic`, `validation`. Not one of the 3 named sites -- found by the sweep. |
| `packages/temper-placer/src/temper_placer/io/_write_board.py` | center-offset rotation (x2: `update_pcb_placements`, `state_to_placements`), isolation-slot offset rotation | **Fixed (3 sites).** Writer-side inverse of `_parse_modules.py`'s fix; the slot-offset site is the mechanism that would place a real milled isolation slot (currently unused -- this board has none). |
| `packages/temper-placer/src/temper_placer/io/_write_modules.py` | pad-local-to-world rotation in `add_bounding_boxes_to_pcb` (x2 identical sites) | **Fixed.** Visualization bounding-box computation from real board rotation. |
| `packages/temper-placer/src/temper_placer/io/kicad_exporter.py` | pad-local-to-world rotation for DSN export | **Fixed.** |
| `packages/temper-placer/src/temper_placer/requirements/validators/_copper.py` | `_rotate` | **Fixed.** REQ-SAFE-01's own clearance/creepage validator. Its old docstring explicitly said it used R(+theta) *to stay consistent with* `_parse_modules.py`'s (buggy) convention, not because R(+theta) was independently believed correct -- updated in lockstep. |
| `packages/temper-placer/src/temper_placer/deterministic/stages/setup.py` | `_rotate_point` | **Fixed.** Confirmed unused (no callers) -- fixed for correctness, zero behavioral effect today. |
| `packages/temper-placer/src/temper_placer/placer/template.py` | group-rotation offset (x2 identical sites) | **Fixed.** All current call sites (`deterministic.py:74`, via `heuristics/mcu_subsystem.py`) pass `rotation=0`, where R(+theta) and R(-theta) coincide -- zero observed behavior change today, fixed for the nonzero-rotation case. |
| `packages/temper-geometry/src/transform.rs` | `transform_pin_position`/`transform_pin_positions` | **Fixed.** Rust equivalent of `pin_geometry.py`'s canonical function. Not called from any production Python path today (only its own Rust unit tests and the unused pyo3 bridge binding) -- fixed for correctness. Its own test `test_transform_pin_position_rotated` re-derived and updated with the R(-90) calculation shown inline. |
| `packages/temper-placer/src/temper_placer/core/courtyard.py` | `Courtyard.get_global_polygon` (`shapely.affinity.rotate`) | **Fixed** (found via test-suite re-run, not the initial grep -- see method note above). For a courtyard polygon symmetric about its own local origin (the common axis-aligned-rectangle case) the sign was a no-op; for an asymmetric/offset polygon it was not. Two real callers: `deterministic/stages/courtyard_check.py` always passes `rotation=0` (unaffected); `analysis/_violation_report.py` uses real per-footprint rotation (now correct). |

### Confirmed NOT bugs (checked, not assumed) -- sign of theta provably irrelevant

For an axis-aligned rectangle or circle centered at the local origin,
reflecting about the x-axis is a symmetry of the shape, and
`R(-theta)(shape) = reflect(R(theta)(reflect(shape)))`; since `reflect
(shape) = shape`, the *set* of points R(+theta) and R(-theta) produce is
identical (only the winding/enumeration order differs). Every site below
was checked against this argument, not merely assumed symmetric:

- `scripts/check_pad_orientation.py` `_corners()` -- the reference
  implementation (57/57-validated against real DRC) rotates a pad's own
  rectangular body about its own center. This is why its validation never
  surfaced the sign question: rectangle-corner rotation is sign-invariant.
- `isolation_barrier.py`'s `pad_axis_radius`/`pad_support_radius`
  consumption -- only ever queried at axis 0 (direction=0) or axis 1
  (direction=pi/2), for which the resulting half-extent
  `hw*|cos(rotation)| + hh*|sin(rotation)|` is even in `rotation`.
  Directly relevant to the CP-SAT headline above.
- `router_v6/constraints_geometry.py` `RotatedRect` -- rotates an
  origin-centered rectangle's 4 corners for a point-to-rect distance
  query; forward/inverse rotation pair is self-consistent and, again,
  reflection-invariant.
- `router_v6/escape_via_generator.py` dog-bone candidate rotation -- the
  4-point candidate offset set `{(+-half_pitch, +-half_pitch)}` is itself
  reflection-symmetric, so R(+theta) and R(-theta) produce the same
  *set* of candidates (in different try-order); harmless.
- `visualization/model.py`, `visualization/board_renderer.py` -- cosmetic
  rectangle-corner rendering only, same argument.
- Rust `get_rotation_matrix`/`rotate_point`/`rotate_rectangle_corners`/
  `get_rotated_bounds` -- generic library primitives. The only production
  Python caller found (`validation/geometric.py`, `validation/metrics.py`,
  via `get_rotated_bounds`) only ever queries symmetric-rectangle bounds.

### Not applicable -- no footprint/pad-angle semantics (generic polar math)

`heuristics/{structural,style,organizational}.py` (scatter points on a
circle for layout candidates), `placer/deterministic.py` (spiral
placement, `distance*cos(angle)`), `placer/adjustment.py` (random push
vector), `deterministic/stages/_grid_fence.py` (circle sampling for a
keepout boundary), `deterministic/geometry/via_placement.py` (candidate
via ring), `topological/initial_placement.py` (circular initial layout),
`physics/thermal_potential.py` (direction-to-unit-vector), `router_v6/
thermal_relief.py` (spoke pattern), `scripts/bench_rust_geometry.py`
(pure-Python reference for benchmarking against Rust's generic
`rotate_point`, itself unaffected), `scripts/benchmark_numba_los.py`
(random line-of-sight benchmark), `scripts/internal_route.py` (commented-
out scratch/debug code, never executed).

## Before/after: the required re-runs

### 1. `scripts/check_isolation_keepout.py`

**Unchanged: exit 3, 1 violation, both before and after.** The single
reported violation is `[missing]`: no `MAINS_SELV_ISOLATION_BARRIER`
keepout zone exists on the board at all. The gate's `_rotate()`-using pad
classification code is reached during parsing but the reported violation
is generated before any pad-vs-zone geometry test runs (there is no zone
to classify pads against), so this specific board's gate *output* cannot
change from this fix -- confirmed, not assumed, by re-running: `Board:
.../pcb/temper.kicad_pcb ... Barrier zone NOT FOUND ... FAILED -- 1
violation(s)`, exit 3, identical to the pre-fix state already documented
in `docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`
Sec. 3.4 ("reports the same single pre-existing failure").

### 2. `scripts/measure_cross_domain_creepage.py` (control -- confirms the fix didn't move it)

This tool was not touched by either commit in this task (already fixed on
the base branch). Re-run at both thresholds:

| threshold | violations | note |
|---|---:|---|
| 8.0mm | **60** | Matches `docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`'s post-fix figure exactly -- confirms this control tool is unaffected by this task's changes, as expected. |
| 12.6mm | **214** | This task's brief cited "~195" as the prior figure. That 195 comes from `docs/evidence/2026-07-29-cross-domain-creepage-pd2-vs-pd3.md`, computed at commit `5401a827`/`3cd4fc4c` -- **before** `c3412861` (the rotation-convention fix already on this branch's own history, predating this task). It was never re-measured at 12.6mm after that fix. 214 is the correct, current, already-fixed-tool figure; the discrepancy is a stale citation from before the convention was corrected, not something this task's commits caused (this task touched zero lines of `measure_cross_domain_creepage.py`).

### 3. Placer/router test suites

Full `packages/temper-placer/tests` (excluding `test_cp_sat_bench.py`, a
pre-existing broken-import collection error unrelated to this change),
run twice: once before the test-suite fixes in `21b4c963`, once after.

| | failed | passed | skipped | xfailed | errors |
|---|---:|---:|---:|---:|---:|
| Before test fixes | 286 | 6187 | 84 | 25 | 3 |
| After test fixes | 282 | 6191 | 84 | 25 | 3 |

Net: **4 fewer failures, 4 more passes**, matching exactly the 4 tests
fixed with derivations below. A line-by-line diff of the two runs' FAILED
lists confirms no other test flipped state (three cosmetic differences --
`test_stage_serialization_roundtrip[ObstacleMapStage]`,
`test_projections.py::test_invalid_edge_raises`, and two CPU-load-
sensitive timing tests `test_astar_runtime_monitor.py::
test_monitor_no_overhead_when_inactive` /
`test_routability_check.py::TestBenchmark::test_latency_unroutable_early_exit`
-- are parallel-worker output-interleaving/log-capture artifacts or
timing flakiness under concurrent load, not geometry-driven; same test
names appear failing and passing across runs with no code difference
between them).

**`scripts/tests/`**: 719 passed, 8 failed -- all 8 in
`test_pipeline_metrics.py` (`AttributeError: module 'pipeline_metrics' has
no attribute 'cmd_spc'`), an API-signature drift unrelated to geometry;
confirmed by direct traceback, not touched.

**`scripts/check_pad_orientation.py`**: still passes -- `checked 168
footprints, 519 pads, 1682 different-net pad pairs`, `PASS: no unrotated
pad bodies, no intra-footprint copper overlaps`, exit 0.

### 4. `packages/temper-geometry` Rust crate

`cargo test -p temper-geometry --release --lib transform`: all 40
`transform` module tests pass, including the updated
`test_transform_pin_position_rotated`. (`cargo test` on the full crate
fails to *compile* one unrelated integration test,
`tests/test_congestion_tensor.rs`, on a private-field-access error
pre-existing on this branch and untouched by this task -- confirmed via
`git diff --stat HEAD -- ...test_congestion_tensor.rs` showing no local
changes to that file.)

## Every test modified, with justification

All four use the same derivation: KiCad's real footprint-child rotation is
R(-theta): `(x, y) -> (x*cos(theta) + y*sin(theta), -x*sin(theta) +
y*cos(theta))`, confirmed against real `kicad-cli 10.0.4 pcb drc` ground
truth in `docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`
Sec. 2. At theta=90 degrees this simplifies to `(x, y) -> (y, -x)`.

1. **`tests/core/test_pin_geometry.py::test_90deg_rotation_top_side`** --
   pin offset `(1, 0)` at 90 degrees: `(1,0) -> (0,-1)`. World `(10+0,
   20-1) = (10, 19)`. Old test asserted `(10, 21)` (the R(+theta) value,
   `(1,0)->(0,1)`).
2. **`tests/core/test_pin_geometry.py::test_90deg_rotation_bottom_side`**
   -- same pin, bottom-side X-mirrored to `(-1, 0)` first: `(-1,0) ->
   (0,1)`. World `(10+0, 20+1) = (10, 21)`. Old test asserted `(10, 19)`.
3. **`tests/deterministic/stages/test_setup.py::test_setup_stage`** --
   pin offset `(2, 0)` at 90 degrees: `(2,0) -> (0,-2)`. World `(10+0,
   10-2) = (10, 8)`. Old test asserted `(10, 12)`.
4. **`tests/router_v6/test_escape_via_generator.py::test_rotation`** --
   pin offset `(-0.5, -0.5)` at 90 degrees: `(-0.5,-0.5) -> (-0.5, 0.5)`.
   World `(10-0.5, 10+0.5) = (9.5, 10.5)`. Old test asserted `(10.5,
   9.5)`.

Each derivation is written inline in the test file itself, not merely in
this document.

## Findings reported, not chased (per this task's explicit instruction)

Two test failures are genuine, geometry-caused consequences of this fix
that were **left failing and reported**, not silently corrected or their
underlying requirement loosened:

### `tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance`

Before this fix: 0 REQ-SAFE-01 violations (test passed). After: **102
violations across 57 pairs** (13 intra-footprint), plus 4 unclassified
components within the largest IEC margin of a declared-HV component.

This is corroborated, not merely asserted: the 102 violations' distances
match -- pair-for-pair, to 3 decimal places -- the independent, already-
correct `measure_cross_domain_creepage.py` control tool's 8.0mm output
(e.g. `C17<->R32` 0.905mm, `R30<->R32` 2.612mm, `R30<->R1` 2.953mm,
`R12<->K3` 3.894mm, `C22<->U15` 4.594mm, `U6<->R18` 6.130mm, `T1<->U27`
7.850mm -- all identical between the two independently-built code paths).
`_copper.py` (fixed here to match the corrected convention) and
`measure_cross_domain_creepage.py` (already correct, untouched by this
task) now agree, where before the fix `_copper.py` reported zero
violations by construction (it was deliberately matched to
`_parse_modules.py`'s old bug for internal self-consistency, per its own
prior docstring -- see the inventory table above).

**This is not a test bug.** The old rotation convention was masking real
REQ-SAFE-01 violations on the real board. Per this task's explicit
instruction ("If your fix changes what fails, report it -- do not chase
the failures"), this test was left failing, not edited, and no safety
threshold was touched.

### `tests/placer/cp_sat/test_regression_drc.py::test_production_board_routing_drc_regression` and `tests/router_v6/test_temper_production_board_routing.py::TestProductionBoardRouting::test_route_pcb_production_board`

Both assert against the real production board's router output.
`unconnected_items`: recorded ceiling 405 ("2026-07-29: 405 in all eleven
runs, zero scatter"), measured **408** after this fix (a +3 delta, ~0.2%
of 1456 total DRC items). Routing completion rate itself is unchanged
(38.54%, matching the pre-existing documented baseline in
`docs/evidence/2026-07-28-barrier-constrained-placement.md`).

Plausibly a genuine, small consequence of corrected terminal/pad geometry
for 90/270-rotated components feeding the router's obstacle map and
escape-via generation (both consume `pin_world_position`, fixed here) --
but **not exhaustively verified per-net** which specific nets/components
account for the 3-item delta. Per this task's explicit instruction and its
hard constraint against re-floorplanning or re-routing, this was
**reported, not chased**: the ceiling was not re-recorded (that would
require the kind of per-net verification this task's scope and time
budget do not cover), and it was not loosened to a wider number either.

## Constraints honoured

- No safety constant, target, or netclass changed: 8.0, 12.1/12.6, and the
  0.5mm corridor margin all untouched.
- No re-floorplanning, no parts moved, no board copper edited:
  `elec/build/default.net` sha256 verified byte-identical before/after;
  `git status`/`git diff` on `pcb/` and `elec/` show zero changes from
  either commit in this task.
- Built in an isolated worktree (`wt-rotation-fix`), branched from
  `fix/cross-domain-creepage-triage`. `make venv-isolate` and `make
  extensions` run before any measurement (the Rust `transform.rs` change
  required a rebuild). `uv run --no-sync` used for every invocation. No
  `git stash` used anywhere in this task.
- Two commits: `6b5dbd9d` (the repo-wide sign fix) and `21b4c963`
  (`courtyard.py` fix found during the mandated test re-run, plus the 4
  justified test corrections), each independently re-verified before this
  document was written.

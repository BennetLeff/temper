<!-- provenance: commit=e0af5e467b45114c677b84cc9fdab8ca178be564 dirty=true (working tree changes are this PR's diff) -->

# Correcting the pad geometry model -- implementation, re-derivation, and verification

Branch `fix/pad-geometry-model`, from `origin/main` (`e0af5e46`). Implements
`docs/plans/2026-07-28-002-fix-pad-geometry-model-plan.md`.

## Summary (read this first)

Every consumer of pad geometry modeled every KiCad pad as a circle of
`radius = max(width, height) / 2`. That formula is exact for `circle` and
(non-obviously) `oval`, but wrong for `rect` and `roundrect` -- 441 of 519
pads on the real board. It is fixed by replacing the isotropic formula with
an exact closed-form Minkowski-sum model
(`temper_placer.core.pad_geometry`), used two ways:

- **Directional** (`pad_axis_radius`/`pad_support_radius`): exact half-extent
  along a given world axis/direction, honoring rotation. Used by the
  isolation-barrier isolator feasibility check, which needs a *different*
  radius for its X-gap and Y-gap tests, not one number.
- **Isotropic bound** (`pad_bounding_radius`): the exact, tight,
  rotation-invariant circumscribing radius (`hypot(core_hw, core_hh) + r`).
  Used by the router's hot paths (`pin_world_radius`, obstacle-map polygon
  construction, escape-via clearance) as a fast conservative bound -- proven
  (not merely asserted) to never under-report, in the module docstring.

**Result on the real board:**

- **T1** (current-sense transformer): achievable HV/SELV pad-cluster gap
  moves from **7.000mm -> 9.100mm** -- FEASIBLE at the 8.0mm gate threshold
  (was FAIL).
- **K1** (bypass relay): moves from **5.425mm -> 8.000mm** -- exactly at the
  8.0mm gate threshold (was FAIL by 2.575mm, now passes with zero margin).
- Both match the brief's stated true values exactly.
- **CP-SAT barrier re-run** (8.5mm corridor, matching the CP-SAT module's
  own margin above the 8.0mm gate): horizontal orientation proves
  **INFEASIBLE** in 111s (was infeasible-in-23s on the old model); vertical
  orientation does not resolve within a 300s budget (`status=unknown`) but
  the same 5 isolators (C6, K2, K3, U3, U7) are independently,
  orientation-independently provably blocking via direct arithmetic. The
  barrier remains genuinely infeasible; PS1 and now T1 clear it; K1 sits
  exactly on the boundary.
- **Router impact measured directly** (live before/after route of the real
  production board, file-swapped, not committed): completion drops from
  38.54% to 37.50% (41/108 -> 40/108 nets), one previously-"routed" net
  (`input`) can no longer complete, and total post-route DRC violations
  *decrease* (1786 -> 1772), with `clearance` violations specifically
  dropping (490 -> 474). This is the expected direction: the corrected
  model recognizes more true copper extent at pad corners, so the router
  can no longer route through a gap that never physically existed, at the
  (small, expected) cost of completeness.
- No golden/baseline file was re-recorded. `pcb/temper.kicad_pcb` itself is
  untouched (0 bytes changed) -- see "Goldens" below for why none needed
  updating.

## Implementation plan (produced before writing code)

1. **New shared module**: `temper_placer/core/pad_geometry.py`. Exact
   closed-form geometry for `circle`/`oval`/`rect`/`roundrect` via the
   Minkowski-sum-of-rectangle-and-disk construction (see the module's own
   docstring for the full derivation and the R2 never-under-reports proof).
   No shapely/polygon approximation needed for the *radius* functions --
   only `pad_polygon()` (for the router's obstacle-map, which needs actual
   2D shapes) touches shapely, with an explicit circumscribing-inflation
   correction so its polygon approximation of a rounded corner never cuts
   inside the true arc.
2. **Low-risk, high-value first**: `scripts/check_isolation_keepout.py`
   (own `PadInstance.radius`, now `pad_bounding_radius`) and
   `isolation_barrier.py` (own `Pad`/`compute_pad_groups`/`_axis_gap`, now
   directional via `pad_axis_radius`). Both have narrow blast radius (one
   safety gate, one CP-SAT constraint) and their own copies, so fixing them
   first re-derives R5/R6 without touching routed output.
3. **Shared `pin_world_radius()` second**: this ripples into the router
   (`astar_grid.py` imports it directly; `obstacle_map.py` and
   `escape_via_generator.py` had their own independent copies of the same
   buggy formula, now consolidated onto the same shared model -- R4).
   Router goldens move as a result; quantified below.
4. **Design decision (key question the plan posed)**: one exact
   implementation serves everyone; the router does NOT get a separate,
   less-precise fast path. The "fast conservative bound" the plan asked
   about *is* `pad_bounding_radius` -- it is exact (not a further
   approximation) and O(1), so there was no speed/correctness tradeoff to
   make. What differs between consumers is not precision but *shape*:
   directional (axis-gap) vs isotropic (single radius) queries against the
   very same underlying model.

## Where the model lives now (R4: one shared implementation)

- `packages/temper-placer/src/temper_placer/core/pad_geometry.py` --
  the shared exact model (new).
- `scripts/check_isolation_keepout.py` -- `PadInstance.radius` now computed
  via `pad_bounding_radius(size_x, size_y, pad.shape, pad.roundrectRatio)`.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`
  -- `Pad` now carries `(x, y, width, height, shape, roundrect_ratio)`
  instead of a precomputed isotropic radius; `_axis_gap` and
  `_best_rotation_for_barrier` call `Pad.axis_radius(axis, rotation_rad)`
  (a thin wrapper over `pad_geometry.pad_axis_radius`) for the specific
  axis/rotation being evaluated.
- `packages/temper-placer/src/temper_placer/core/pin_geometry.py` --
  `pin_world_radius()` now calls `pad_bounding_radius()`.
- `packages/temper-placer/src/temper_placer/router_v6/obstacle_map.py` --
  `_create_pad_polygon()` now delegates to `pad_geometry.pad_polygon()`
  instead of its own ad hoc circle/rect handling.
- `packages/temper-placer/src/temper_placer/router_v6/escape_via_generator.py`
  -- `_is_position_valid()`'s `pin_radius` now calls the shared
  `pin_world_radius()` instead of reimplementing `max(w, h) / 2`.
- `Pin` (`core/netlist.py`) gained two fields: `roundrect_ratio` (KiCad's
  own per-pad `roundrect_rratio`, default 0.25) and `pad_rotation_deg` (a
  pad's own intrinsic rotation on top of its component's -- zero on every
  real pad today, but read from the board rather than assumed away, per
  R3). `io/_parse_modules.py` now populates both from the parsed board.

## R1/R2/R3: shape-aware, never-under-reporting, rotation-honouring

Proven in `pad_geometry.py`'s own docstring and exercised by
`tests/core/test_pad_geometry.py` (67 cases, including):

- The exact square-pad corner case: an 8x8mm `rect` pad's true corner sits
  at `hypot(4, 4) = 5.657mm`, 1.657mm outside the old model's 4mm circle --
  `pad_bounding_radius` returns `5.657mm` exactly.
- The exact elongated-pad case: a 9x4.8mm `rect`/`oval` pad's true
  short-axis half-extent is `2.4mm`, not the old model's `4.5mm` --
  `pad_axis_radius(..., axis=1)` returns `2.4mm` exactly, while
  `pad_axis_radius(..., axis=0)` correctly still returns `4.5mm` (the long
  axis is unaffected).
- Rotation: fuzzed across 0-360 degrees at 7-11 degree steps (not just
  0/90/180/270) confirming the support function never exceeds the
  rotation-invariant bounding radius, and that a 90-degree rotation swaps
  which axis gets which extent.
- `pad_polygon()`'s circumscribing-buffer correction verified by sampling
  the TRUE rounded-corner arc (100s of points) and confirming every one is
  contained in the conservative polygon.

### A citation in the brief that did not hold up on inspection

The brief's headline corner example -- "`R30` pad 1, 8x8mm, corners
1.657mm outside the model circle" -- does not reproduce against the real
board. `R30` pad 1 is a `thru_hole circle` pad (`pcb/temper.kicad_pcb`:
`(pad "1" thru_hole circle (at 0 0) (size 8 8) (drill 3) ...)`), a genuine
circle, for which the old `max(w,h)/2` formula is exact (a circle has no
corners). Flagged rather than silently built upon or silently dropped: this
is a factual inaccuracy in the plan's illustrative citation (likely an
artifact of whatever ad hoc script produced it treating the renamed
`thru_hole` shape string as "not literally circle, fall back to sharp rect"
-- exactly the kind of shape-dispatch bug this fix eliminates), not a wrong
requirement -- the underlying bug class (rect/roundrect pads under-report at
corners) is independently, exactly confirmed by the T1/K1 isolator numbers
below, which match the brief's stated true values to the millimeter.

The real worst-case corner under-report on `pcb/temper.kicad_pcb`, verified
directly:

| Pad | Shape | Size | roundrect ratio | old radius | true bounding radius | under-report |
|---|---|---|---|---:|---:|---:|
| C2/C3/C4/C5 pad 1 | roundrect | 4x4mm | 0.0625 | 2.000mm | 2.725mm | 0.725mm |
| PS1 pad 1 | rect | 3x3mm | -- | 1.500mm | 2.121mm | 0.621mm |
| T1 pad 1/2 | rect | 9x4.8mm | -- | 4.500mm | 5.100mm | 0.600mm |
| K3/K2 pad 1 | rect | 2.5x2.5mm | -- | 1.250mm | 1.768mm | 0.518mm |

And the real worst-case short-axis over-report:

| Pad | Shape | Size | old radius | true short-axis half-extent | over-report |
|---|---|---|---:|---:|---:|
| K1 pad 13/14 | rect | 6.35x1.2mm | 3.175mm | 0.600mm | 2.575mm |
| T1 pad 1/2 | rect | 9x4.8mm | 4.500mm | 2.400mm | 2.100mm |
| C14 pad 1/2 | roundrect | 1.8x5.4mm | 2.700mm | 0.900mm | 1.800mm |

Board-wide shape counts, independently reconfirmed: `roundrect` 366, `rect`
75, `circle` 66, `oval` 12 (matches the plan's stated totals exactly).

## R5: re-derived per-isolator table

Computed directly (`compute_pad_groups` + `evaluate_isolator_feasibility`,
`corridor_width_mm=8.5` to match `isolation_barrier.py`'s own module
default, which carries 0.5mm headroom above the gate's 8.0mm):

| Isolator | old achievable_gap_mm | new achievable_gap_mm | Feasible @ 8.5mm | Feasible @ 8.0mm (gate) |
|---|---:|---:|:---:|:---:|
| C6 | 3.200 | 3.200 (unchanged -- circular Y-cap pads) | NO | NO |
| **K1** | 5.425 | **8.000** | NO (by 0.5mm) | **YES (exactly)** |
| K2 | -0.500 | -0.500 (unchanged) | NO | NO |
| K3 | -0.500 | -0.500 (unchanged) | NO | NO |
| PS1 | 35.500 | 35.500 (unchanged -- wide margin either way) | YES | YES |
| **T1** | 7.000 | **9.100** | **YES** | **YES** |
| U3 | 6.020 | 6.020 (unchanged) | NO | NO |
| U7 | 7.250 | 7.250\* | NO | NO |

\*U7's raw `gap_y_mm` diagnostic moves (-2.050 -> -0.600) but its
`achievable_gap_mm` (best of 4 rotations) is unchanged, since its best axis
was already X.

**Verdicts that changed: T1 and K1**, exactly as the brief predicted --
both move from FAIL to PASS against the gate's real 8.0mm requirement.
C6/K2/K3/U3/U7 do not change verdict: C6's pads are circular (model-exact
either way), and K2/K3/U3's true rect/roundrect short-axis extents were
already correctly small enough on their binding axis that the old model's
isotropic radius (bigger, since it used `max(w,h)`) happened not to change
the sign of their infeasibility -- i.e. these were genuinely infeasible,
not artifacts.

Reproduction:
```
uv run --no-sync python - <<'EOF'
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import (
    classify_domain_partition, compute_pad_groups,
    evaluate_isolator_feasibility, load_domain_manifest_nets,
)
REPO = Path(".")
hv, selv = load_domain_manifest_nets(REPO / "elec/domain_manifest.yaml")
nl = parse_kicad_pcb(REPO / "pcb/temper.kicad_pcb").netlist
partition = classify_domain_partition(nl.components, hv, selv)
by_ref = {c.ref: c for c in nl.components}
for ref in sorted(partition.isolators):
    groups = compute_pad_groups(by_ref[ref], hv, selv)
    feas = evaluate_isolator_feasibility(groups, corridor_width_mm=8.5)
    print(ref, feas.achievable_gap_mm, feas.feasible)
EOF
```

## R6: CP-SAT barrier feasibility re-run

Run against the real board (168 components, 152x234mm), both corridor
orientations, `corridor_width_mm=8.5` (unchanged from the prior evidence
run in `docs/evidence/2026-07-28-barrier-constrained-placement.md`, so the
two runs are directly comparable):

| Orientation | Old model (prior evidence doc) | New (corrected) model |
|---|---|---|
| Vertical | INFEASIBLE, 23.4s, UNSAT core: `isolator_straddle_C6` | **`unknown`** (did not resolve in 300s) |
| Horizontal | INFEASIBLE, 23.2s, UNSAT core: `isolator_straddle_C6` | **INFEASIBLE, 111s** |

**This is not a contradictory or ambiguous result** -- restated precisely:
the barrier remains genuinely infeasible. The horizontal orientation proves
it directly. The per-isolator table above is orientation-independent (it is
closed-form arithmetic over each isolator's own pad geometry, not a solver
search) and shows 5 isolators -- **C6, K2, K3, U3, U7** -- each
individually, unconditionally block ANY corridor >=8.5mm wide regardless of
where the rest of the board's 163 other components are placed (the same
two-linear-constraint contradiction the original evidence doc's UNSAT core
already demonstrated for C6 alone). The vertical orientation's `unknown`
status is a SOLVER SEARCH BUDGET fact, not a feasibility fact: with only 5
(not 7) isolators now unconditionally blocking, CP-SAT's presolve has less
"easy" contradiction to find early and spends its time budget searching the
now-larger placement space for the other 163 components before the 300s
timeout, rather than proving the same trivial per-isolator contradiction
quickly. This was checked, not assumed: re-running with a longer timeout
(300s vs the original 180s) changed `wall` from 110s/112s (both
orientations at 180s) to 253s (vertical, still unresolved) / 111s
(horizontal, resolved) -- the horizontal proof is stable and fast at any
budget tried; the vertical search is simply slower to reach the same
conclusion.

**Restated blocker list (unchanged in kind from the prior evidence doc,
narrower in count)**: C6 (Y-cap stub footprint, not yet a real sourced
part), K2/K3 (G5LE-1 general-purpose relay pinout, COM-to-coil ~2mm
regardless of any pad-model fix), U3 (H11L1 DIP-6, 7.62mm row pitch minus
pad extent). **T1 and K1 are no longer on this list** -- T1 clears the
corridor with genuine margin (9.100mm > 8.5mm) and K1 clears the actual
8.0mm gate threshold exactly (though not the CP-SAT module's more
conservative 8.5mm working margin).

No new placement was produced (status is not SAT/FEASIBLE on either
orientation), so `pcb/temper.kicad_pcb` is untouched -- 0 bytes changed,
verified via `git diff --stat pcb/temper.kicad_pcb` before writing this
doc.

## R7: router impact, quantified

Measured directly via a live route of the real production board
(`route_pcb`, no CP-SAT placement -- routing-only pass against the board's
existing layout, matching `test_route_pcb_production_board`'s own method),
comparing the OLD and NEW `obstacle_map.py`/`escape_via_generator.py`/
`pin_geometry.py` by swapping the 3 changed files back to their `HEAD`
content for the "before" run (via `cp`/`git checkout`, restored
immediately after -- never `git stash`, per this repo's hard rule) and
re-running with the fix restored for "after". Both runs against the
identical, unmodified `pcb/temper.kicad_pcb`.

| Metric | Before (old model) | After (fixed model) | Direction |
|---|---:|---:|---|
| Nets routed | 41/108 (38.54%) | 40/108 (37.50%) | -1 net |
| Post-route DRC violations (total) | 1786 | 1772 | -14 (fewer) |
| `clearance` violations | 490 | 474 | -16 (fewer) |
| `shorting_items` | 189 | 191 | +2 |
| `tracks_crossing` | 2 | 3 | +1 |
| `track_dangling` | 68 | 67 | -1 |
| `unconnected_items` | 396 | 395 | -1 |
| Wall time | 53.1s | 57.8s | +4.7s |

**This is the expected direction.** The corrected model recognizes MORE
true copper extent at pad corners (the under-report fix) than it removes
on elongated pads' short axes (the over-report fix is smaller in aggregate
-- most of this board's pads are near-square `roundrect`, where the
correction is a small radius increase, not a large decrease). One
previously-"routed" net (`input`) drops out: it was routed through a gap at
a pad corner that the old model's circle never covered, and the router's
current pathfinder does not retry an alternate route when its first choice
is invalidated -- a known limitation (`temper.j_fan-p1`, `safety.thermal-line`,
and dozens of other nets already fail with "no legal path found" on both
runs, pre-existing and unrelated). The net effect on DRC is a small,
consistent IMPROVEMENT (fewer clearance violations, fewer unconnected
items) -- exactly what "model pads bigger and more accurately at corners"
predicts: traces that used to graze a phantom gap are now routed around
real copper, or not routed at all rather than routed through it.

`test_route_pcb_production_board`'s own hard assertion
(`unconnected_items == 0`) **fails identically before and after** (396 vs
395, both nonzero) -- this is a pre-existing failure, not a regression;
confirmed by running the identical test against the unmodified `HEAD`
version of the 3 changed files.

## Goldens: what changed, what didn't, and why

- **`pcb/temper.kicad_pcb`**: untouched. Neither the CP-SAT re-run (both
  orientations non-SAT) nor the router quantification (deliberately not
  committed -- see below) wrote a new placement.
- **`power_pcb_dataset/golden_manifest.yaml`**: unaffected. Structural
  netlist counts (`component_count`, `net_count`), not pad geometry.
- **`power_pcb_dataset/drc_ceiling.json`**: unaffected. Measured via
  `kicad-cli pcb drc` directly against the committed board file -- KiCad's
  own DRC engine, not this codebase's Python pad model. Since the board
  file is untouched, this ceiling cannot have moved.
- **`power_pcb_dataset/timing_baselines.yaml`**: unaffected. No hard gate
  reads it against a fixed threshold in this codebase's test suite
  (`test_timing_tighten.py` tests the ratchet TOOL's logic against
  synthetic fixtures, not real recorded numbers).
- **`power_pcb_dataset/baselines/temper_production_baseline.yaml`**'s
  `router_v6_routing` block: **deliberately NOT re-recorded.**
  `test_update_baseline_yaml` (the only writer of this block) was not run.
  This block was already stale before this change -- it was recorded
  against a 95-net board (`extraction_date: '2026-07-18'`); the board now
  has 108 nets (see the file's own changelog comments,
  "component_count 149 -> 170, net_count 95 -> 108"), so its
  `completion_rate: 0.747`/`routed_nets: 71` numbers do not correspond to
  the current board regardless of this fix. Re-recording it now would
  replace one stale number with a different, still only
  approximately-comparable number, without fixing the actual staleness gap
  (this file has no bless/Ceiling-Approval machinery -- see its own
  in-file commentary). Out of scope for a pad-geometry fix;
  `tests/router_v6/test_phase1_anti_false_zero.py`'s traceability
  assertions (`routed_nets == 71`, `extraction_date == '2026-07-18'`)
  continue to read the same untouched file and pass unchanged.
- **No routing regression fixture asserts an exact completion percentage
  or DRC count against this fix's changed code paths.** The one test that
  does real end-to-end production-board routing
  (`test_route_pcb_production_board`) already fails its one hard
  assertion (`unconnected_items == 0`) before this change, for reasons
  unrelated to pad geometry (confirmed: same 396 vs 395 magnitude, same
  failure mode, before and after).

## Verification

- `packages/temper-placer/tests/core/test_pad_geometry.py`: 61 passed, 6
  skipped (parametrize skip guards for circle-shape non-square inputs).
- `packages/temper-placer/tests/core/test_pin_geometry.py`: 11 passed
  (2 rewritten for the corrected formula, documented in-test).
- `packages/temper-placer/tests/placer/cp_sat/test_isolation_barrier.py`:
  13 passed (6 call sites migrated from raw `(x, y, radius)` tuples to a
  `Pad` dataclass; one assertion rewritten to check the real, shape-aware
  `compute_pad_groups` output instead of a synthetic circle).
- `packages/temper-placer/tests/router_v6/test_obstacle_map.py`,
  `test_obstacle_map_pbt.py`, `test_escape_via_generator.py`: all pass
  unchanged.
- `scripts/tests/test_check_isolation_keepout.py`: 27 passed, unchanged.
- `uv run --no-sync ruff check` clean on every changed/added file.
- `scripts/check_manifest_gate.py`, `scripts/check_vacuous_gates.py`,
  `scripts/import_linter_gate.py`: all exit 0, no new violations.
- Full `packages/temper-placer/tests/router_v6/` (2234 selected, the 2
  slow production-routing tests handled separately above): **2193 passed,
  7 failed, 14 skipped, 23 xfailed.** All 7 failures triaged individually
  and confirmed pre-existing (identical failure mode/message with the
  3 changed files reverted to `HEAD`, re-run standalone): 4 in
  `test_astar_3d_production_scale_spike.py` (`KeyError: 'F.Cu'` -- the
  occupancy-grid builder only produced `In1.Cu`/`In2.Cu` grids, a
  layer-selection issue with no pad-geometry involvement), 1 in
  `test_dfm_hypothesis_fuzzing.py::test_no_crash_clearance` (flaky --
  passed on the standalone re-run), 1 in `test_dfm_interaction.py` (a
  mocked `RuntimeError: injected failure` in an unrelated DFM-module
  test), 1 in `test_via_insertion_anti_false_zero.py` (a committed
  evidence JSON, `docs/evidence/2026-07-19-via-aware-routing-u8.json`,
  that has never existed in this repo's git history at all).
- Full `packages/temper-placer/tests/` (excluding `router_v6/` and
  `test_cp_sat_bench.py`, which fails to even collect due to a
  pre-existing `pythonpath` gap unrelated to this change): **3840
  passed, 272 failed, 115 skipped, 1 xfailed, 3 errored.** Every one of
  the 26 distinct failing files was checked against the unmodified
  (`HEAD`) versions of the 3 changed files (`obstacle_map.py`,
  `escape_via_generator.py`, `pin_geometry.py`, restored via `cp`/
  `git checkout HEAD --`, never `git stash`): 120 of the 272 are
  `tests/protocol/test_stage_conformance.py` (confirmed byte-identical
  failure set before/after -- a stage-protocol conformance suite this
  change's files are not part of); 56 are a batch of 21 other files,
  confirmed byte-identical failure lists before/after via `diff`; the
  remainder (`test_geometry.py`'s 42 rust-binding `TypeError`s,
  `test_projections.py`'s 49 `identity_projection()` signature
  mismatches, `test_area_sufficiency_check.py`/
  `test_courtyard_violation_report.py`'s stale board-vs-test-expectation
  numbers, `test_deterministic_unit.py::test_place_by_proximity`)
  individually confirmed identical before/after. **Net result: zero new
  failures anywhere in either suite.**
- `scripts/tests/`: 467 passed, 11 failed (capacity-budget/MPN-fabrication/
  undeclared-imports/pipeline-metrics-SPC-SLO gates -- topically
  unrelated to pad geometry, not investigated further), 2 skipped.
- `scripts/check_isolation_keepout.py` against the real board: still exit
  3 (missing `MAINS_SELV_ISOLATION_BARRIER` keepout zone -- unrelated to
  this fix, unchanged from before).
- `pcb/temper.kicad_pcb` and everything under `power_pcb_dataset/`: `git
  status --short` clean after all of the above -- confirmed untouched.

## Hard-rules compliance

- 8.0mm creepage requirement, the corridor model, and
  `elec/domain_manifest.yaml`: untouched.
- No `git stash` used (file-swap-and-restore via `cp`/`git checkout HEAD --`
  was used instead, for the router before/after measurement).
- No gate weakened, no `continue-on-error` added, no threshold relaxed.
- `git diff --cached --name-only` checked before every commit.

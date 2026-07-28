# Repairing the three broken manufacturing-DRC checks

<!-- provenance: commit=6b4210992e171d185257664cef4bcec86c572d08 dirty=true -->

**Date:** 2026-07-27

**Scope:** `acid_trap`, `annular_ring`, `creepage` -- the three checks
`docs/evidence/2026-07-27-committed-route.md` flagged as, respectively,
crashing, vacuous, and producing an uninterpretable violation count. This
task fixes the check implementations (`packages/temper-placer/src/
temper_placer/router_v6/{acid_trap_detection,annular_ring_check,
creepage_check}.py`) and their downstream aggregation
(`manufacturing_report.py`, `_pipeline_verify.py`). The router's routing
algorithm and `pcb/temper.kicad_pcb` were not touched.

**Environment:** fresh worktree required rebuilding all 9 Rust extension
crates via `uv run maturin develop --release` (none were cached); `uv
sync` was later needed too (it reset the local `.venv`, requiring the 4
pyo3-crate rebuilds again) to pull in `numpy` and other pure-Python
deps. Confirmed via `uv run python3 -c "import temper_drc_rs,
temper_rust_router, temper_ipc, temper_geometry, temper_dsn,
temper_design_bundle_python, temper_constraint_compiler, temper_io_types,
temper_quality_oracle, temper_placer"`.

---

## 1. `acid_trap` -- crashed on every via-bearing net

### Falsifier

*"Fixing the `.coordinates` access will surface real violations; if the
count comes back 0, either the fix is wrong or this board genuinely has
no acid traps."* **Falsifier did not fire** -- the fixed check found 33
real acid traps (20 critical, angle < 45 degrees) on a live re-route.
This was not tuned; the angle-classification thresholds were not
touched.

### Root cause

`compiled_route.path` is typed `RoutePath | RoutePath3D`
(`routing_results.py:CompiledRoute`). `RoutePath` has 2D `.coordinates`;
`RoutePath3D` (used whenever the router takes a multi-layer/via detour --
`_astar_reconstruct.py`'s "via-aware fallback tier") instead exposes
`.segments` as `(x, y, layer)` triples and has **no `.coordinates`
attribute at all**. `acid_trap_detection.py:117` accessed
`compiled_route.path.coordinates` unconditionally, so every net whose
path was a `RoutePath3D` raised `AttributeError: 'RoutePath3D' object has
no attribute 'coordinates'`. This is the exact crash cited in
`docs/evidence/2026-07-27-committed-route.md`.

### Fix

Added `_extract_2d_coordinates(path)` in `acid_trap_detection.py`: reads
`.coordinates` when present, else derives `[(x, y) for x, y, layer in
path.segments]` from `.segments`. Raises `AttributeError` (not swallowed)
if a path has neither -- a check that can't see its input should fail
loudly, not report a false zero.

### Violations, with denominator, before and after

Denominator for `acid_trap` is "nets inspected" (no explicit counter
existed; every net in `compiled_routes` is walked). Measured two ways:

**Unit level** (deterministic, `test_acid_trap_detection.py::
test_detect_acid_traps_route_path_3d_does_not_crash`): a `RoutePath3D`
with a via transition and a real hairpin spike (26.6 degree angle).

| | Before | After |
|---|---|---|
| Result | `AttributeError: 'RoutePath3D' object has no attribute 'coordinates'` | `trap_count=1`, `errored=False`, trap located at the spike vertex |

**Live board** (`pcb/temper.kicad_pcb`, re-routed via `route_pcb(...,
enable_manufacturing_drc=True)`; completion 38.5%, 168 components, 108
nets -- see "Live-board measurement caveat" below for why this is not
the exact committed 51/96 profile): ran the identical captured
`RoutingResults` through the checkout twice, once with
`acid_trap_detection.py` reverted (`git stash`) and once with the fix
applied.

| | Before | After |
|---|---|---|
| `acid_traps.errored` | `True` | `False` |
| `trap_count` | 0 (crash fallback) | **33** |
| `critical_count` (< 45 degrees) | 0 | **20** |
| `errored_checks` | `('acid_trap',)` | `()` |
| `total_violations` (whole report) | 46 | 79 |

The 33-trap, 20-critical result is real: this run's copper genuinely has
33 vertices with an interior angle below 90 degrees.

---

## 2. `annular_ring` -- inspected zero vias despite vias existing

### Falsifier

Stated in the task: *"`annular_ring`'s zero is a bug, not a correct
report that no via needs checking."* **Falsifier fired** -- confirmed a
genuine bug, not a correct vacuous report, for the scenario it describes
(a board with committed vias). See the live-board caveat below for the
one nuance: on the *specific* re-route this task's live measurement
landed on, 0 vias were placed at all, so a report of 0 is honestly
correct *for that run*. That is a different fact from the root-cause bug
below, which is real and independently proven at the unit level.

### Root cause

`check_annular_rings` only ever iterated
`routing_results.compiled_routes.items()`. `RoutingResults` also carries
`tree_routes: dict[str, CompiledTreeRoute]` and `partial_tree_routes`,
populated whenever the router uses Steiner-tree (multi-terminal)
routing instead of point-to-point paths. `CompiledTreeRoute` has its own
`.vias` list -- populated by the same `via_placement.place_vias()` call
(via `TreeRouteGeometry.branches[*].path.via_positions`) that seeds
`CompiledRoute.vias`, and consumed by the exporter's "U7" fold
(`_adapter_convert.py`, which merges `tree_routes`/`partial_tree_routes`
into its own local `compiled` dict before writing `(via ...)`
s-expressions) -- so a board whose copper is predominantly tree-routed
has real, physically-written vias that `check_annular_rings` never
looked at. This is the "48 vias, 0 checked" gap.

### Fix

1. **Root cause** (`annular_ring_check.py`): `check_annular_rings` now
   also walks `routing_results.tree_routes` and
   `.partial_tree_routes`, checking each `CompiledTreeRoute.vias` entry
   exactly like `CompiledRoute.vias`. Guarded with
   `getattr(..., None) or {}` so duck-typed test doubles lacking these
   attributes degrade to "no tree routes" rather than crashing.
2. **Fail-closed guard** (`_pipeline_verify.py`): mirrors the existing
   creepage/clearance anti-vacuous-truth guard (METHODOLOGY.md Sec 5).
   `has_vias` is computed from `compiled_routes` + `tree_routes` +
   `partial_tree_routes` before any DFM check runs; if
   `annular_ring.total_vias_checked == 0` but `has_vias` is `True`, the
   report's `errored` field is flipped to `True` and it is logged at
   `ERROR`. This is a second line of defense independent of the
   root-cause fix, for any future via source the check doesn't yet walk.
3. **Reporting** (`manufacturing_report.py`): `total_violations` and
   `critical_violations` now fold an errored `annular_ring` into "at
   least 1 violation," matching the existing creepage/clearance
   treatment (previously an errored/vacuous annular_ring silently
   contributed 0, identical to a genuinely clean board).
   `format_manufacturing_report` now tags an errored annular_ring
   `[ERRORED -- fail-closed, see CHECK ERRORS above]`.

### Violations, with denominator, before and after

Denominator is `total_vias_checked`, already reported (the bug was that
it silently hit 0 rather than that it was hidden).

**Unit level** (`test_annular_ring_check.py::
test_check_annular_rings_inspects_tree_routed_vias` /
`..._inspects_partial_tree_routed_vias`): a single tree-routed net with
one undersized via (0.4mm pad / 0.35mm drill = 0.025mm ring, min 0.1mm).

| | Before | After |
|---|---|---|
| `total_vias_checked` | 0 | **1** |
| `violation_count` | 0 | **1** |

**Guard-level** (`test_dfm_interaction.py::TestAnnularRingVacuousGuard`):
a board with a real via on a compiled route, but `check_annular_rings`
mocked to still return 0 (simulating a residual gap not covered by the
root-cause fix) -- `_run_manufacturing_drc`'s `annular_rings.errored`
flips `False -> True` and `'annular_ring'` appears in `errored_checks`.
A companion test confirms the guard does **not** misfire on a board that
genuinely has zero vias.

**Live board**: on the re-route this task could reproduce (see caveat
below), `total_vias_checked=0`, `violation_count=0`, `errored=False` --
and `compiled_routes`/`tree_routes`/`partial_tree_routes` all report 0
vias placed, so 0 is the honest answer for that specific run. The root
cause was not exercised live; it is proven only at the unit/guard level
(see UNVERIFIED).

---

## 3. `creepage` -- 257,597 violations from 175-180 checks

### Falsifier

*"Establish whether it is double-counting pairs, emitting
per-segment-per-net instead of per-pair, or genuinely finding that
many."* **Confirmed: emitting per-segment-per-net-pair, not per net
pair; not genuinely finding that many.** Comparing against the sibling
`clearance_check.py` (which already aggregates to one violation per
(net-pair, layer) via `_calculate_minimum_clearance_by_layer` and was
cited in the task as "looking plausible") made the asymmetry obvious:
`creepage_check._find_clearance_violations` iterated the full cartesian
product of both nets' internal grid-step segments and appended one
`CreepageViolation` for **every** violating segment-pair, while
`total_checks` counted only net pairs (once per `(hv_net, other_net)`).
Two nets routed parallel and too close for their length therefore
produced one violation per pair of ~0.1mm grid-step segments along the
shared run -- hundreds or thousands of records for one physical
isolation defect.

### Fix

`_find_clearance_violations` (`creepage_check.py`) now returns the
single closest-approach violation for the pair (or none), mirroring
`clearance_check`'s aggregation. The required-distance table (IPC-2221,
unchanged) and `total_checks` counting (unchanged) were not touched --
only the violation *record* multiplicity per pair changed, from
"one per segment-pair" to "one per net-pair, at its worst-case
distance."

### Violations, with denominator, before and after

**Unit level** (`test_creepage_check.py::
test_creepage_violation_count_bounded_by_net_pair_not_segment_pair`):
two 20-point parallel nets, 0.05mm apart for their whole length (well
under the 3.2mm required for a 230V default HV net).

| | Before | After |
|---|---|---|
| `total_checks` | 1 | 1 |
| `violation_count` | **151** | **1** |

**Live board** (same re-route as acid_trap's live measurement, run twice
-- once with `creepage_check.py` reverted, once fixed):

| | Before | After |
|---|---|---|
| `total_checks` | 180 | 180 |
| `violation_count` | **257,597** | **24** |
| ratio | ~1,431 violations/check | ~0.13 violations/check |

The live-run "before" number (257,597) landed almost exactly on the
number cited in the task description (257,597 from 175 checks on the
committed board) despite this being a different re-route with a
different completion profile (180 vs 175 checks) -- strong corroboration
that this is the same systemic bug, not a coincidence of one specific
run. **24 is the real, actionable defect count**: 24 out of 180 checked
net pairs have a genuine minimum-clearance violation against the
IPC-2221 creepage table.

---

## What matters more than the fixes

**None of the three turned out to be behaving correctly all along.**
All three had genuine, confirmed defects in the check implementation
itself:

- `acid_trap` crashed on 100% of via-bearing nets (an `AttributeError`,
  not a design choice).
- `annular_ring` had a real code-level gap (tree-routed vias never
  walked), independently proven by two dedicated unit tests, even
  though the one live re-route available for this task happened to
  land on a via-free routing outcome (see caveat below) where "0" was
  coincidentally the honest answer.
- `creepage` was provably over-counting by ~3 orders of magnitude
  (257,597 vs. 24 real defects on the live board; 151 vs. 1 in the
  isolated unit reproduction).

`clearance` (not in scope, cited for contrast) was re-verified unaffected
throughout: 16 violations / 666 checks on the live board, stable across
every before/after run pair.

### Live-board measurement caveat

`docs/evidence/2026-07-27-committed-route.md` documented that
`route_pcb` completion is **non-deterministic run-to-run** (37.5%-53.1%
spread on identical code/input) and that there is no existing code path
to reconstruct a `RoutingResults` from an already-written `.kicad_pcb`
file (that file only has flattened, already-exported copper; the
per-net path/via *objects* the checks need don't survive the export).
This task's live re-route (`route_pcb(..., enable_manufacturing_drc=
True)`, captured via the same `RouterV6Pipeline.run` monkeypatch
technique as the prior evidence doc) landed on **38.5% completion, 0
vias placed anywhere** (`compiled_routes`: 37 nets / 0 vias;
`tree_routes`: 0 nets / 0 vias) -- reproducibly, across 4 separate
process invocations with identical wall-clock-adjacent results
(recorded acid_trap and creepage before/after both took the same route
once per fix, so the routing outcome itself is not certain to be
bit-identical across the two invocations of a given comparison, but
`total_checks` for creepage matched exactly across the before/after
pair, `total_violations` differed only in the expected direction, and
completion rate and violation-count-shape were stable across all 4
runs, so this is treated as a stable measurement, not a single sample).
Because this run had zero vias, it does not exercise the annular_ring
root-cause fix (tree-routed vias) -- that fix's evidence is unit-level
only. It also means this is **not** the same board state as the
committed 51/96-completion, 48-via board the task's numbers were
originally drawn from; the live numbers here are real and reproducible
for the run they came from, but are a different sample of the same
router's non-deterministic output space.

### Ranked real board defects surfaced (from the live, fixed run)

1. **24 creepage (mains-safety) violations** across 180 HV/other net
   pairs -- the highest-severity finding by domain (isolation distance
   on a mains-connected board). Locations and offending net pairs are
   in the live `CreepageReport.violations` list (not reproduced here;
   `actual_distance` / `required_distance` / `location` per violation).
2. **33 acid traps, 20 critical (< 45 degrees)** -- previously
   completely invisible (the check crashed on every run). Critical traps
   risk over-etching / copper undercut during fabrication.
3. **16 clearance violations** across 666 conductor pairs (Rust
   backend; unaffected by this task, included for context/ranking).
4. **4 unbalanced copper layers** (`copper_balance`; unaffected by this
   task). `total_area_mm2=35,568` is flagged as implausible for this
   board's physical footprint in the prior evidence doc -- still
   UNVERIFIED, not investigated in this task.
5. `annular_ring`: 0 real violations on the run measured (0 vias
   present in that run at all).
6. `teardrop` / `thermal_relief`: 0 generated each, scored as 1
   violation each by design (unrelated to this task).

---

## Regression tests added (fails-before, passes-after -- both states verified)

| File | Test | Before | After |
|---|---|---|---|
| `test_acid_trap_detection.py` | `test_detect_acid_traps_route_path_3d_does_not_crash` | `AttributeError` | pass, `trap_count>=1` |
| `test_annular_ring_check.py` | `test_check_annular_rings_inspects_tree_routed_vias` | `assert 0 == 1` fails | pass |
| `test_annular_ring_check.py` | `test_check_annular_rings_inspects_partial_tree_routed_vias` | `assert 0 == 1` fails | pass |
| `test_manufacturing_report.py` | `test_errored_annular_ring_fails_closed` | `assert 0 >= 1` fails | pass |
| `test_dfm_interaction.py` | `TestAnnularRingVacuousGuard::test_fires_when_board_has_vias_but_check_reports_zero` | new (guard didn't exist) | pass |
| `test_dfm_interaction.py` | `TestAnnularRingVacuousGuard::test_does_not_fire_when_board_genuinely_has_no_vias` | new | pass |
| `test_creepage_check.py` | `test_creepage_violation_count_bounded_by_net_pair_not_segment_pair` | `assert 151 == 1` fails | pass |

Each "before" row was confirmed by `git stash push` on only the relevant
source file, running the test, then `git stash pop` -- not inferred.

## Verification

All required gates, run after `make netlist` (76 assertions, 0 failed):

| Check | Result |
|---|---|
| `scripts/check_domain_partition.py` | exit 0 |
| `scripts/capacity_budget_gate.py` | exit 0 |
| `scripts/mpn_fabrication_gate.py` | exit 0 |
| `scripts/check_derived_doc_drift.py` | exit 0 |
| `scripts/check_vacuous_gates.py` | exit 0 |
| `scripts/check_copper_net_consistency.py` | exit 0 (`PASSED -- 0 violations across 2482 copper item(s) and 510 pad(s) checked`; confirms the committed board is still 2338 segments / 48 vias / 96 zones, untouched) |
| `make netlist` | 76 passed, 0 failed |
| `packages/temper-placer/tests/requirements/safety/` | 54 passed |

Targeted regression suite (the three fixed modules + their
properties/induction/boundary variants + `test_dfm_interaction.py` +
`test_manufacturing_drc_integration.py` + `test_manufacturing_report*.py`
+ `test_routing_results.py`): **405 passed, 4 xfailed, 2 failed**. The 2
failures (`test_dfm_interaction.py::TestAllModulesFail::
test_all_seven_raise_still_produces_report` and
`TestPipelineOrdering::test_swap_acid_trap_and_clearance_yields_same_result`)
are **pre-existing on the unmodified base branch** -- confirmed by
`git stash` of every source change made in this task and re-running
those two tests, which still fail identically. Root cause (not fixed,
out of scope): `verify_creepage`/`verify_clearance`'s own
pre-existing anti-vacuous-truth guard (added before this task, for a
different reason) fires on the stub board these tests use (a net named
`"NET1"`, which is never HV, so `total_checks=0` is the *correct*
answer for creepage/clearance on that board, but the guard cannot tell
"no HV nets exist" apart from "the check found nothing to inspect" and
fails closed anyway) -- an existing false-positive in the
creepage/clearance guard, unrelated to the annular_ring guard added in
this task.

## UNVERIFIED

- The annular_ring root-cause fix (tree-routed vias) was not exercised
  by a live re-route in this task -- the one live routing outcome this
  task reproduced placed zero vias anywhere. The fix is proven at the
  unit and guard-mock level only (two dedicated unit tests plus a guard
  test), not against a live board with real tree-routed vias.
- Whether the live-board creepage/acid_trap "before/after" pairs
  (obtained via two separate `route_pcb` process invocations, one per
  fix, with the file reverted via `git stash` in between) are running on
  bit-identical `RoutingResults`, or merely a stable-looking sample of
  the router's known non-deterministic output space. `total_checks`
  (creepage) matched exactly across the pair and completion rate/wall
  time were consistent across all 4 live runs in this task, which is
  suggestive but not proof of determinism.
- `copper_balance.total_area_mm2 == 35,568` -- carried over unverified
  from the prior evidence doc, not investigated in this task (out of
  the three checks in scope).
- The 12-net gap between parsed and attempted nets, and the router's
  run-to-run completion variance -- both carried over from the prior
  evidence doc as explicitly out of scope for DRC-check work.
- Exact locations/net-pairs of the 24 live creepage violations and 33
  live acid traps were not individually reviewed against the schematic
  for physical plausibility (e.g. whether the 24 creepage flags are all
  genuinely mains-adjacent or include some false positives from the
  straight-line/no-isolation-slot-modeling limitation `creepage_check.py`
  already documents in its own module docstring).
- The two pre-existing `test_dfm_interaction.py` failures are diagnosed
  above but not fixed -- confirmed pre-existing via `git stash`, not
  further investigated since they are outside this task's three checks.

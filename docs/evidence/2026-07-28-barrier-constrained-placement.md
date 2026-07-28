<!-- provenance: commit=d3c497c8b4033ce41ecb658cd84bd69397b58369 dirty=false -->

# Re-solving placement with the mains<->SELV isolation barrier as a HARD CP-SAT constraint

Base commit: `fcf7deff` (`merge: no mains-SELV barrier can be drawn on this
placement -- FALSIFIED`), branch `docs/methodology-loop-discipline`. Work
done in worktree `agent-a4ccf202fdaa5ec68`, branch
`fix/hard-isolation-barrier-cpsat`, branched directly from that commit (not
from the worktree's own prior HEAD, per the plan's instruction).

All numbers below were produced by actually running the commands/code shown,
on this machine (macOS arm64, Python 3.12.13, `uv`), against the real
`elec/domain_manifest.yaml` and `pcb/temper.kicad_pcb` as of this worktree's
base commit, unless explicitly marked UNVERIFIED.

## FALSIFIER (stated up front, per the plan)

> "A compliant placement exists for this component set on this board
> outline, and the isolation gate passes on it. If CP-SAT returns
> INFEASIBLE, or the gate still fails, the deliverable is precisely what
> blocks it -- not a relaxed constraint."

**FALSIFIED.** CP-SAT returns `INFEASIBLE` for the hard barrier constraint
on this exact component set. The blocking cause is not a placement/packing
problem -- it is a **component/footprint problem**: 7 of the 8
manifest-declared isolators do not have enough real, physical distance
between their own HV-classified pads and SELV-classified pads to satisfy an
8.0mm (here modeled at 8.5mm, see below) zero-copper corridor, *regardless
of where they are placed or how they are rotated*. See "Isolator
feasibility" below for the per-component proof.

## Summary (read this first)

1. **Partition** (independently reverified on this checkout, denominators
   included): 168 footprints = 44 HV-only + 106 SELV-only + 8 isolators + 10
   unclassified.
2. **A CP-SAT barrier constraint was implemented** in the placer
   (`packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`),
   extending (not duplicating) the classification approach
   `domain_clearance.py` already established, and wired into
   `solve_placement()` via an opt-in `isolation_barrier=` kwarg. 13 unit
   tests, all passing.
3. **Run against the real board: CP-SAT status = `INFEASIBLE`**, in 23.4s
   (vertical corridor) / 23.2s (horizontal corridor -- both tried, same
   result). The solver's own `SufficientAssumptionsForInfeasibility` names
   `isolator_straddle_C6` as one sufficient reason; independent per-isolator
   analysis (below) shows 7 of the 8 isolators are each, independently,
   sufficient causes.
4. **This is a real, provable, footprint-geometry fact**, not a placement
   search failure: for 7 of the 8 isolators, the maximum achievable
   separation between their own HV pad cluster and SELV pad cluster --
   checked over all 4 axis-aligned rotations -- is below 8.0mm. No
   repositioning or re-rotation of these exact parts, on this exact board,
   can change that.
5. **Because the result is INFEASIBLE, no new placement was produced.**
   `pcb/temper.kicad_pcb` is untouched (0 bytes changed), no
   `MAINS_SELV_ISOLATION_BARRIER` keepout zone was added, and
   `scripts/check_isolation_keepout.py` is unchanged at **exit 3** (same
   violation as the base commit). The 11 pre-existing sub-8mm cross-domain
   pairs are **not resolved** -- there is no new placement to resolve them
   against. Routing was not re-run (no placement to route).
6. **What would have to change**, precisely: 7 isolator components/footprints
   (C6 Y-cap, K1/K2/K3 relays, T1 current-sense transformer, U3 optocoupler,
   U7 gate driver) would need to be replaced with parts (or footprints of
   the same parts) whose own primary-to-secondary pad pitch exceeds 8.0mm
   plus pad radii, before a compliant placement search is even worth
   attempting. This is a BOM/footprint decision, not a placement decision --
   see "What would have to change" below for the specific, per-component
   gap that would need to close.

## Partition (denominators)

Reverified directly (not cited from the prior evidence doc) by loading
`elec/domain_manifest.yaml`'s `domains.HV.nets` / `domains.SELV.nets` and
classifying every one of `pcb/temper.kicad_pcb`'s 168 footprints by which
domain(s) its own pads' nets fall in (exact net-name matching only, per this
project's own defect history -- never substring/pattern matching):

| Bucket | Count | Definition |
|---|---|---|
| Total footprints | 168 | `len(board.footprints)` |
| Total pads | 519 | HV=97, SELV=221 (172 remain on unclassified/neither-domain nets, e.g. `+3V3` pins on isolators counted above, `gnd`, etc. -- see per-component tallies below) |
| HV-only components | 44 | touch >=1 HV net, 0 SELV nets |
| SELV-only components | 106 | touch >=1 SELV net, 0 HV nets |
| **Isolators** | **8** | touch >=1 HV net AND >=1 SELV net: `C6, K1, K2, K3, PS1, T1, U3, U7` |
| Unclassified | 10 | touch neither domain: `C10, R34, R40, R42, R45, R52, R57, R64, R69, R72` (the OVP protective-impedance-chain interior nodes and the fan/misc signal caps -- deliberately neither domain per `domain_manifest.yaml`'s own commentary) |
| **Sum check** | 44+106+8+10 = **168** | matches total footprints exactly |

This independently reproduces the prior evidence doc's partition
(`docs/evidence/2026-07-28-isolation-keepout.md`) without relying on it --
same 8 isolator refs, same 44/106/10 split, computed fresh from this
worktree's netlist via a different code path (this plan's new
`classify_domain_partition`, not that doc's one-off script).

The 52/114 figures in the plan prompt (52 = 44 HV-only + 8 isolators; 114 =
106 SELV-only + 8 isolators) are exactly these numbers double-counting the
isolators, as the plan itself anticipated.

## Isolator feasibility -- the actual finding

For each isolator, the real board's pad geometry (`Component.pins` from
`io.kicad_parser.parse_kicad_pcb`, i.e. the *actual placed footprint*, not
a datasheet number) was split into an HV-pad cluster and an SELV-pad
cluster (by exact net-name match against the manifest), and the worst-case
(minimum over every HV-pad x SELV-pad pair) edge-to-edge separation was
computed on both candidate axes, using the SAME conservative
bounding-circle pad model `scripts/check_isolation_keepout.py` itself uses
(`radius = max(pad.size.X, pad.size.Y) / 2`) -- so this analysis and the
gate it must satisfy can never disagree about the geometry.

`achievable_gap_mm` below is the **true best case**: the largest gap
reachable over all 4 axis-aligned rotations, restricted to rotations that
keep the HV cluster on one consistent side of the board and the SELV
cluster on the other (required for `check_isolation_keepout.py`'s "no
far-side crossing" check, since e.g. every `gnd` pad on the board --
including an isolator's own -- must land on the same side as every other
`gnd` pad).

| Isolator | Real part / footprint | gap_x (mm) | gap_y (mm) | achievable_gap_mm | Feasible @ 8.5mm? |
|---|---|---:|---:|---:|:---:|
| C6  | Y2-type safety-cap **stub** footprint, "D=10.0mm disc, W=5.0mm, P=5.0mm pitch" (board's own footprint `descr`) | 3.200 | -1.800 | 3.200 | **NO** |
| K1  | Omron G4A-1A-E bypass relay (contacts modeled as SMD landing pads for netlist parity) | -4.075 | 5.425 | 5.425 | **NO** |
| K2  | Omron G5LE-1 discharge relay 1 | -2.500 | -0.500 | -0.500 | **NO** |
| K3  | Omron G5LE-1 discharge relay 2 | -2.500 | -0.500 | -0.500 | **NO** |
| PS1 | Mean Well IRM-10-15 AC/DC module | 35.500 | -3.000 | 35.500 | **YES** |
| T1  | Coilcraft CST3015-100ED CT (datasheet claims ">=8mm creepage/clearance") | -6.000 | 7.000 | 7.000 | **NO** |
| U3  | H11L1 opto, 6-lead THT DIP, "row spacing 7.62mm (300 mil)" (board's own footprint `descr`) | 6.020 | -1.600 | 6.020 | **NO** |
| U7  | TI UCC21550BDWK gate driver, DWK wide-body package (pins 12/13 omitted "for isolation creepage/clearance") | 7.250 | -2.050 | 7.250 | **NO** |

**7 of 8 isolators cannot straddle an 8.5mm corridor; only PS1 (the
AC/DC module, whose primary and secondary pin headers are a real 38.5mm
apart) clears it, with a huge margin.**

Three of these parts are genuinely marketed/designed for reinforced
isolation (T1: ">=8mm creepage/clearance" per its own footprint
description; U7: pins deliberately omitted "for isolation
creepage/clearance"; U3's H11L1 is a "Schmitt-trigger phototransistor
optocoupler" commonly used for reinforced barriers) -- their *real*
datasheet-rated creepage is close to or nominally at 8mm. What pulls them
under the 8.5mm bar here is the **same conservative bounding-circle pad
model this project's own safety gate uses**: a rectangular SMD pad's larger
dimension is treated as a circle's diameter in *every* direction (not just
along its own long axis), which over-penalizes elongated pads (e.g. T1's
9.0mm x 4.8mm primary pad is modeled as a 4.5mm-radius circle, eating
4.5mm out of the Y-axis gap where the pad only physically extends 2.4mm).
This is flagged, not silently worked around: `check_isolation_keepout.py`
is the plan's stated gate to satisfy, unmodified, and it makes no
isolator exception -- so a part whose *real* geometry might satisfy 8.0mm
creepage along its own package surface can still fail this specific,
deliberately conservative PCB-level check. That is a genuine, reportable
tension between "component-level certified isolation" and "board-level
zero-copper keepout enforcement," not a bug in this analysis.

Two of the seven (**K2, K3** -- the discharge relays) are unconditionally
infeasible regardless of any of the above: their own COM contact pin sits
only ~2mm from a coil pin in BOTH axes (their bounding-circle gaps are
negative on both X and Y), which is a genuine general-purpose-relay
pinout, not a modeling artifact. **C6** is not a sourced part at all yet --
its footprint's own description literally reads *"Stub for safety
capacitor... Created to resolve netlist reference"* -- a 5mm-pitch
placeholder standing in for a real Y-rated safety capacitor.

### Cross-check: orientation and rotation don't change the verdict

The barrier constraint generator was run against the real board with BOTH
corridor orientations (`vertical`, splitting by X; `horizontal`, splitting
by Y) at the real 8.5mm width -- **identical result both times**: `status =
infeasible`, same 7 isolators infeasible, same PS1 feasible. This is not a
coincidence: `achievable_gap_mm` already searches all 4 axis-aligned
rotations for whichever axis the barrier actually uses, so a barrier
orientation choice cannot rescue an isolator whose intrinsic pad geometry
doesn't clear 8.5mm on *either* local axis.

A control run at `corridor_width_mm=1.0` (deliberately far below the real
safety requirement, purely to separate "isolator pad geometry" from "board
packing space" as two independent questions) confirms this is genuinely
about pad geometry, not solver behavior: at 1.0mm, C6/K1/PS1/T1/U3/U7 all
become feasible (their real gaps, ~3-38mm, comfortably clear 1mm), and
**K2/K3 remain infeasible even at 1.0mm** -- proving their COM-to-coil
proximity is a hard, width-independent geometric fact about that relay's
pinout, not an artifact of the 8.0mm requirement specifically.

This control run also caught and fixed a real bug in the first version of
this constraint generator: unconditionally fixing isolator rotation to 0
only ever tests the local-X-to-barrier-axis mapping, silently missing K1's
adequate local-Y separation (5.425mm, real at rotation 0 -- but the
constraint's *encoded* axis was X). Fixed by enumerating all 4 rotations
and picking the convention-consistent one with the largest achievable gap
(`_best_rotation_for_barrier` in `isolation_barrier.py`); re-verified the
main 8.5mm result is unchanged by the fix (it was never K1 that was
blocking the 8.5mm case -- C6/K2/K3/T1/U3/U7 all fail on their OWN best
axis already).

## CP-SAT formulation (and why)

Implemented in
`packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`,
wired into `solve_placement()` via a new optional `isolation_barrier=`
kwarg (see `_encoder_solve.py`).

- **Corridor width: 8.5mm**, not 8.0mm -- 0.5mm headroom above
  `scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` so integer
  unit rounding (the model works in 0.01mm units) and the gate's own
  Shapely negative-buffer erosion test (a strict "nonempty everywhere," not
  "exactly 8.0mm at one point") both have margin. **Never used to shrink
  the requirement** -- 8.5 > 8.0, the opposite direction.
- **Orientation and corridor position: fixed constants, not solver
  variables.** Justified by the finding above, not chosen for convenience:
  isolator feasibility is proven independent of both (see cross-check
  above), and the only thing a movable/re-oriented corridor could still
  help with -- how well the 150 domain-only components pack against a
  fixed corridor -- was never reached, because the model is infeasible
  before packing quality becomes the binding question. Default position is
  the board's own centreline; both orientations were tried explicitly
  rather than assumed.
- **Domain-only components (HV-only + SELV-only): a directional,
  one-sided linear constraint**, not the existing `SeparatedConstraint` +
  `handlers/separated.py` machinery `domain_clearance.py` uses. An earlier
  version of this same file *did* reuse `SeparatedConstraint` (registering
  the corridor as a fixed virtual component and emitting one
  `SeparatedConstraint` per domain-only component against it) -- caught as
  WRONG during development by `test_barrier_separates_domain_only_components_sat`:
  `SeparatedConstraint`'s "clear the margin on either side" disjunction
  does not stop two HV-only and two SELV-only components all landing on
  the SAME side of the corridor while each individually "clears" it. Fixed
  by encoding a single board-wide convention directly (HV-only components:
  `x_end <= corridor_start`; SELV-only: `x_start >= corridor_end`), which is
  what a barrier actually needs to mean.
- **Isolators: pad-cluster-level, not courtyard-level.** Isolator
  courtyards are exempt from the directional constraint (free to overlap
  the corridor -- that is their function), but their real HV/SELV pad
  clusters are individually constrained to the same two sides everyone
  else uses, because `check_isolation_keepout.py` checks every pad on the
  board unconditionally, with no isolator exception. Rotation is chosen
  (once, not left free) by `_best_rotation_for_barrier` and pinned via
  `Add(rot_ref == chosen)`.
- Every constraint is guarded by its own named CP-SAT assumption literal
  (`isolation_barrier_hv_<ref>`, `isolation_barrier_selv_<ref>`,
  `isolator_straddle_<ref>`), so `SufficientAssumptionsForInfeasibility`
  can name specific culprits on an UNSAT result -- same idiom
  `CpSatModel.set_bounds` already uses for edge-margin attribution.

13 unit tests (`tests/placer/cp_sat/test_isolation_barrier.py`, synthetic
fixtures only, never touching the real board) cover: partition
classification (including a never-substring-match regression test),
per-isolator feasibility on synthetic PS1-shaped/C6-shaped/DIP-6-shaped
fixtures, the rotation-bug regression case, and full CP-SAT
SAT/UNSAT integration (domain-only separation, an infeasible-isolator UNSAT
case naming the right assumption, and a feasible-isolator SAT case with a
pad-level -- not just courtyard-level -- audit of the resolved position).

```
$ uv run --no-sync python -m pytest packages/temper-placer/tests/placer/cp_sat/test_isolation_barrier.py -q
13 passed in 0.38-0.43s
```

## Run against the real board

```
Board: 152 x 234 mm, 168 components

isolation_barrier={"manifest_path": "elec/domain_manifest.yaml",
                    "corridor_width_mm": 8.5, "orientation": "vertical"}
Status: infeasible
Solve time (reported): 23366.7 ms  (wall: 23.4 s)
Placed: 0  Unplaced: 168

UNSAT core (1 entries): isolator_straddle_C6
```

(Horizontal orientation: `infeasible`, 23234.0 ms, same isolator set,
UNSAT core again names `isolator_straddle_C6` -- `SufficientAssumptionsForInfeasibility`
returns *a* sufficient subset, not every independently-sufficient cause;
the per-isolator table above independently establishes all 7 are each
individually sufficient, by direct arithmetic, not solver inference.)

`objective_value = 0.0` in both runs -- Phase-1 feasibility search only
(no objective was reached; the model has no feasible point to optimize
over). This matches `_encoder_solve.py`'s own Phase-1/Phase-2 split
documented in its comments.

## Measurement (per the plan's "If a placement is found" checklist)

A placement was **not** found, so most of this checklist does not apply.
What can be measured honestly:

1. **`scripts/check_isolation_keepout.py`: still exit 3, unchanged.**
   `pcb/temper.kicad_pcb` was not modified (0 bytes changed -- verified via
   `git status`/`git diff` before writing this doc), so this is the exact
   same violation as the base commit, not a new run against a new
   placement. Re-run to confirm: `Barrier zone NOT FOUND`, `1 violation`,
   exit 3.
2. **Routing completion: not re-measured.** There is no new placement to
   route; re-running the routing harness against the UNCHANGED
   `pcb/temper.kicad_pcb` would just reproduce the existing documented
   baseline (38.54%, 59/96 unrouted) and add no information, so it was not
   re-run (avoiding a ~5 minute no-op run per the plan's own harness
   description).
3. **Solve time and CP-SAT status: `INFEASIBLE`, ~23.2-23.4s** (both
   orientations; see above). Well under the 180s timeout given to the
   solver -- the infeasibility is found quickly (a directly contradictory
   pair of linear constraints per blocked isolator, not a hard combinatorial
   search).
4. **The 11 pre-existing sub-8mm HV/SELV component pairs: NOT resolved.**
   Independently reverified on this checkout (not cited from the prior
   evidence doc -- recomputed via a fresh brute-force nearest-pad-distance
   scan, 44 HV-only x 106 SELV-only = 4,664 component pairs checked):

   ```
   Pairs closer than 8.0mm: 11
     C17 <-> R32   2.115mm      C22 <-> C16   6.327mm
     C17 <-> R26   4.408mm      R30 <-> R32   7.120mm
     C22 <-> U15   5.633mm      R30 <-> R73   7.269mm
     C22 <-> L2    5.713mm      C17 <-> R73   7.553mm
     C17 <-> U13   5.805mm      C22 <-> R77   7.811mm
     R30 <-> R1    5.900mm
   ```

   Since no new placement exists, these 11 pairs remain at exactly their
   base-commit distances -- unresolved, unchanged, by name.

## What would have to change

Per the plan's instruction ("If infeasible, report what makes it
infeasible... and what would have to change"):

**Not the board outline, not the mechanical constraints, not a fixed
connector.** No footprint on the current board is locked/fixed (`grep -c
"(locked)"` / mounting-hole footprints: 0 found), and the one connector
found (`J1`, SELV) imposes no orientation constraint that affects this
result. Board size (152mm x 234mm) is not the binding constraint either --
the control experiment at `corridor_width_mm=1.0` shows the packing
problem (once isolator pad geometry is set aside) is a different question
that was never reached.

**Specifically, these 7 components/footprints** would need real, physical
HV-to-SELV pad separation exceeding ~8.5mm (accounting for the gate's own
conservative pad-radius model) before a barrier-constrained placement
search is even worth attempting:

| Ref | Real gap today | Gap needed to close | What would have to change |
|---|---:|---:|---|
| C6  | 3.2mm  | +5.3mm | Source a real Y-rated safety capacitor with >=10mm lead pitch (common for this exact application) instead of the current 5mm-pitch stub footprint -- this part isn't even sourced yet. |
| K1  | 5.425mm | +3.1mm | A relay whose coil-to-contact creepage is independently rated for reinforced isolation (a "safety relay" family), not a general-purpose G4A-1A-E. |
| K2  | -0.5mm | +9.0mm | Same as K1 -- G5LE-1's COM-pin-to-coil-pin layout is a general-purpose pinout, ~2mm apart; needs a relay family with the contact and coil physically separated by design. |
| K3  | -0.5mm | +9.0mm | Same as K2 (identical part). |
| T1  | 7.0mm  | +1.5mm | Datasheet already claims ">=8mm creepage" -- either a land pattern with more Y-axis pad-to-pad clearance, or (see note above) accept that the gate's conservative circular-pad model is stricter than the part's own certified rating for this specific footprint. |
| U3  | 6.02mm | +2.5mm | A wider-body (>=8mm row spacing) reinforced-isolation optocoupler package instead of the standard 300mil DIP-6. |
| U7  | 7.25mm | +1.25mm | Datasheet's DWK package already omits 2 pins "for isolation creepage" -- similar note to T1: either a marginally wider land pattern, or the same conservative-pad-model tension. |

PS1 needs no change; it already clears the requirement with >4x margin.

## Falsifier verdict, restated

**FALSIFIED**, honestly: no compliant placement was found, CP-SAT proved
`INFEASIBLE` (not "timed out" or "gave up" -- the contradiction is found in
~23s via simple linear-constraint propagation), and the cause is
identified precisely: 7 named isolator components/footprints, each with a
specific, computed shortfall. The 8.0mm safety figure was never reduced,
no component was dropped from the model to force a solution, and the
constraint was not weakened. This is the honest "deliverable is precisely
what blocks it" outcome the plan's falsifier anticipated.

## Hard rules -- compliance checklist

- 8.0mm never reduced (constraint modeled at 8.5mm, the safer direction).
- No `git stash` used anywhere in this session.
- No `run_in_background`; all solver runs and test suites were run in the
  foreground (the placer test suite's own runtime exceeded the 10-minute
  per-call cap partway through this session -- see "Verification" below
  for how that was handled without backgrounding/polling).
- Committed after each meaningful step (2 commits so far on this branch:
  the initial constraint + tests, then the rotation-bug fix + tests).
- `uv run --no-sync` used throughout; `uv sync --all-packages` was run
  exactly once, at the very start, into a genuinely empty fresh worktree
  venv (verified nothing was already built to "revert"); one crate
  (`temper-constraints`) needed `maturin develop --release` afterward,
  done once. `scripts/check_stale_extensions.py`: 10/10 fresh.
- `elec/build/` not committed (it's gitignored; `make netlist` was run to
  unblock the manifest-dependent gates, output not added to git).
- No component dropped, no safety distance weakened, to obtain a solution.

## Verification (all commands actually run; output shown or summarized above)

| Check | Result |
|---|---|
| `check_domain_partition.py` | exit 0 |
| `capacity_budget_gate.py` | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 |
| `check_derived_doc_drift.py` | exit 0 |
| `check_copper_net_consistency.py` | exit 0 (2482 copper items, 510/519 pads exact-matched -- unchanged from baseline, confirms `pcb/temper.kicad_pcb` untouched) |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 (10/10 fresh) |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 |
| **`check_isolation_keepout.py`** | **exit 3**, unchanged from base commit (board untouched) |
| `check_measurement_provenance.py` | exit 5 -- pre-existing, stale DRC-ceiling record, exactly as the plan itself noted before this work started |
| `make netlist` | passes |
| `uv run --no-sync python -m pytest elec/validation -q` | 30 passed |
| `uv run --no-sync python -m pytest packages/temper-placer/tests/placer/cp_sat/test_isolation_barrier.py -q` | 13 passed |

### Placer test suite (broader run, with an honest caveat)

The full placer suite is 5266 tests and, on this machine, takes longer
than the 10-minute per-Bash-call cap this environment enforces -- three
attempts to run it in one shot were auto-backgrounded by the harness past
120s/590s/600s; per this plan's hard rule against ever waiting on a
background job, each was explicitly stopped (`TaskStop`) rather than
polled, and the suite was instead run in bounded, fully-foreground chunks:

- `tests/placer/` (the directory this change actually touches, including
  its `cp_sat/` subdirectory; 400 tests): **393 passed, 5 failed, 2
  skipped.** All 5 failures are pre-existing and
  unrelated to this change -- confirmed directly, not assumed:
  `test_golden_board_drc_regression` fails on
  `encoder._UNRESOLVED_REF_POLICY`, an attribute that does not exist on
  `encoder.py` (a file this change never touches) regardless of anything
  here; the two `test_production_board_*_drc_regression` tests fail
  against DRC/routing baselines measured on the CURRENT (unmodified)
  `pcb/temper.kicad_pcb`; `test_place_by_proximity` and the hybrid-pour-stitch
  test are in unrelated deterministic-placer/router modules this change
  never imports or calls.
- Everything else in `packages/temper-placer/tests` EXCEPT `tests/router_v6/`
  and the one file (`test_cp_sat_bench.py`) that fails to even *collect*
  due to a pre-existing `pythonpath` gap unrelated to this change
  (confirmed via `git log` that file was last touched in an unrelated
  prior commit): **3,281 passed, 299 failed, 5 errored.** Spot-checked one
  failure directly (`test_projections.py::TestIdentityProjection::test_returns_same_point`)
  to confirm this bulk of failures is genuine pre-existing baseline noise,
  not something this change introduced: it fails with
  `TypeError: identity_projection() missing 1 required positional argument:
  'py'` -- a test/implementation signature mismatch in
  `temper_placer.core.geometry_types` (or wherever `identity_projection`
  lives), which this change's two touched files
  (`isolation_barrier.py`, new; `_encoder_solve.py`, one additive optional
  kwarg + a conditional block) cannot possibly have caused.
- **New code's own tests: 13/13 pass.** No test anywhere in either bulk run
  references `isolation_barrier` or fails inside a file this change
  touched.
- **`tests/router_v6/` was NOT run this session** -- it alone also exceeded
  the 10-minute per-call cap (stopped via `TaskStop`, not polled, per the
  same hard rule) and was not re-attempted in smaller chunks given the
  time already spent; reported as a gap, not silently assumed clean.
  `grep -rl "isolation_barrier\|_encoder_solve" packages/temper-placer/src/temper_placer/router_v6/`
  returns nothing, though, so this change's two touched files are not
  imported anywhere in that subtree -- it cannot be affected by this
  change even though it wasn't directly re-run.

This is reported honestly rather than papered over: this repo's placer
test suite already carries a large number of pre-existing, unrelated
failures in this worktree, and this change did not attempt to fix or hide
that -- only to verify its own, narrowly-scoped, additive change did not
make it worse.

## UNVERIFIED

- Whether the gate's conservative circular-pad-radius model (flagged above
  for T1/U7/U3, where the part's *own* datasheet claims reinforced
  isolation close to or at 8mm) should be refined to use the pad's actual
  rectangular extent along each axis rather than a worst-case circle, is a
  legitimate follow-up question -- but out of scope here (the plan's own
  instruction is to make the EXISTING gate pass, not to change what it
  measures), and changing that gate's geometry model is exactly the kind
  of "weaken a safety check to get a green result" move this plan's hard
  rules warn against doing casually. Flagged for a human, not resolved
  here.
- IEC 60335-1's own primary text for creepage/clearance tables remains
  paywalled and was not independently re-derived in this pass (same
  UNVERIFIED-at-primary status the prior evidence doc and
  `check_isolation_keepout.py`'s own docstring already carry for the
  8.0mm figure itself).
- Whether a genuinely wider land pattern exists for the T1/U7 parts (as
  opposed to needing a different part number entirely) was not checked
  against either manufacturer's alternate footprint offerings -- flagged
  as a real follow-up, not resolved here.

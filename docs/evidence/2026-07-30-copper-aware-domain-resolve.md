# Copper-aware domain-clearance re-solve: the 21 placement-fixable REQ-SAFE-01 pairs

<!-- provenance: commit=66ae51fc75de41b191fccad4ff7472275d24d2aa dirty=UNKNOWN -->

**Date:** 2026-07-30
**Scope:** Read-only against `pcb/temper.kicad_pcb` and `pcb/libs/**`. A candidate placement was
produced and measured, never written into the tracked board. Driver scripts and candidate boards
live under `/private/tmp/.../scratchpad/` (not committed) -- this doc reports their exact
invocations, full output, and the resulting measurements.

**Base:** `origin/main` at `66ae51fc` (`git fetch origin && git checkout -b
feat/copper-aware-domain-resolve origin/main`), `uv sync --all-packages`, `make netlist`
(`elec/build/default.net` digest `a69a84034fe9…`).

**Task:** determine whether a copper-aware CP-SAT domain-clearance re-solve can clear the 21
placement-fixable REQ-SAFE-01 pairs identified in
`docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md` (branch
`origin/docs/mains-selv-barrier-requirements`, PR #437; not yet merged to `main`, so its 33-pair
classification is reproduced fresh here, not assumed).

---

## 0. Baseline reproduction (before touching anything)

```
uv run pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -rA -s
```

**76 REQ-SAFE-01 violations across 33 pairs** (11 records intra-footprint), coverage 158/168
components (94.0%) / 54 of 162 compiled nets -- exact match to the brainstorm doc's own
reproduction. `scripts/check_copper_net_consistency.py` independently reproduces its documented
10 pad-mismatch violations (all `C27`-`C39`, unchanged). `scripts/check_isolation_keepout.py`
independently reproduces its documented 1 violation (0 keepout zones on the board). Both are
pre-existing, unrelated to this task, not fixed here -- reproduced to confirm before attributing.

The 33 pairs split, per the brainstorm doc's classification (verified against this fresh 76/33
reproduction, unchanged):

- **Group A (7 pairs, all `C27<->X`):** netlist/board reference-designator resync defect --
  out of scope, blocked on `check_copper_net_consistency.py`'s fix.
- **Group B (5 pairs, all intra-footprint: `C6`, `K2`, `K3`, `U3`, `U7`):** isolator package
  geometry, footprint-fixed, not placement-fixable.
- **Group C (21 pairs):** ordinary movable components, fix-class Placement -- **this task's
  target.**

```
C17<->R32   C22<->L2    R30<->R32   R30<->R1    C17<->R26   R30<->R54   R30<->U13
C17<->U13   C22<->U15   R30<->R73   C22<->C16   R30<->R46   R30<->R26   R30<->C30
C17<->R73   C17<->R54   C22<->R77   C22<->C12   C22<->C37   T1<->U27    C23<->U27
```

---

## 1. Is `domain_clearance.py`'s constraint copper-aware or origin/bbox-based?

**Bounding-box-based, not per-pad copper-aware.** File:line trail, followed end to end:

1. `domain_clearance.py:155-234` (`generate_domain_clearance_constraints`) emits one
   `SeparatedConstraint` per domain-crossing component pair, at
   `margin = max(min_clearance_mm, min_creepage_mm)` (`domain_clearance.py:143-152`,
   `required_margin_mm`).
   `SeparatedConstraint` is a **whole-component** pairwise constraint (`a`, `b` are component
   refs) -- it carries no notion of *which pad* on either component is the domain-classified
   copper.
2. `handlers/separated.py:20-94` (`encode_separated`) encodes that constraint as a Chebyshev
   disjunction over each component's `x_start`/`x_end`/`y_start`/`y_end` -- the component's
   **bounding-box edges**, not any pad's copper edges (`separated.py:36-53`).
3. Those bounding-box variables come from `model.py:108-158` (`CpSatModel.add_component`), which
   takes a single `(width, height)` per component and builds one symmetric box around
   `x_center`/`y_center` (`model.py:125-142`) -- one box per **component**, not per pad.
4. `width`/`height` are populated at `_encoder_solve.py:116-126` from `comp.bounds`, which in turn
   comes from `_parse_modules.py:280-294` (`_calculate_footprint_bounds`): "courtyard graphics
   (F.CrtYd/B.CrtYd) > fabrication layer (F.Fab/B.Fab) > pads" -- a single whole-footprint
   bounding box, not a per-net, per-pad extent.
5. `domain_clearance.py`'s own soundness proof (`domain_clearance.py:42-97`) is explicit about
   the quantity it actually bounds: *"The safety validator (`clearance.py::_check_distance`)
   measures the straight-line (Euclidean) distance between component `position` fields... The
   encoder's `SeparatedConstraint` handler instead bounds the gap between courtyard **edges**...
   These are different quantities."* The proof concludes `SAT ⇒ Euclidean center-to-center
   distance >= margin` -- i.e., the module's own documented guarantee is about **component
   centers**, not pad copper.

That proof's premise about what the validator measures is now **stale**. `clearance.py:7-53`
documents the validator's current behavior plainly: it measures copper-to-copper distance between
**only the pads whose own net is classified into the relevant domain** (`clearance.py:31-32`, "a
DC_BUS component's GND pad is not DC_BUS copper"), via exact per-pad rotated-rectangle geometry
(`clearance.py:34-40`), not origins and not whole-component boxes. The mismatch stated in the task
brief is real: **the constraint generator's own soundness argument targets a weaker, different
quantity (component-center distance) than what the gate actually checks (domain-classified-pad
copper distance).**

**Why this mismatch does not automatically produce violations (and why it is still a real gap):**
a component's courtyard/fab-layer bounding box, by construction, encloses every pad on that
component (courtyard is drawn deliberately larger than the footprint's copper). So courtyard-edge
separation is generally a *conservative under-estimate* of pad-to-pad separation for two
components each single-domain on the side facing the other -- enforcing it is a safe, if
imprecise, proxy for most ordinary components. **It is not a valid proxy at all for a component
whose own courtyard contains pads from *both* domains** -- exactly the isolators (`C6`, `K2`,
`K3`, `U3`, `U7`): the constraint is defined only between two *different* refs, so a same-ref pair
(`a == b`) is silently skipped by `encode_separated` (`separated.py:66-67`, `if ra == rb:
continue`) rather than encoded or flagged. This is consistent with, not contradicted by, Sec 2
below: the mechanism used for Group C (pairwise `SeparatedConstraint`) is structurally incapable
of addressing Group B (intra-footprint) at all -- it neither fixes nor falsely "solves" those
pairs, it just never touches them.

**Verdict on Sec 1's question, stated plainly:** origin/bounding-box-based, confirmed by
inspection. Whether that proxy is *good enough* in practice for the 21 Group C pairs is an
empirical question, answered by measurement in Sec 2-3, not assumed from the code reading alone.

---

## 2. Re-solve, attempt 1 (scoped to the 21 pairs only) -- REGRESSED, reported not hidden

First attempt: generate the full domain-clearance constraint set via
`generate_domain_clearance_constraints(placement, voltage_domains)` (`placement`/`voltage_domains`
from `_real_board_fixture.load_real_board_placement()`, the exact function the gate test itself
calls), then **filter down to only the 21 Group C pairs**, on the reasoning that only those needed
fixing. Solved with `solve_placement(netlist=<PCB-parsed>, board=<PCB-parsed>,
extra_constraints=<21 filtered constraints>, timeout_ms=180_000, seed=0, hint_positions=<current
board positions>)`.

**Result at both 8.0mm and 10.0mm margins: `status=optimal`, all 21 target pairs cleared -- but
overall REQ-SAFE-01 violations went UP, not down: 76 -> 217 (8.0mm) / 76 -> 265 (10.0mm), across
107 / 144 pairs.**

**Root cause (same failure mode the prior full-coverage re-solve hit, at much larger scale --
`docs/evidence/2026-07-27-clearance-resolve-full-coverage.md` Sec 3):** scoping the *encoded*
constraint set to only the 21 known-violating pairs leaves every *other* cross-domain pair on the
board completely unconstrained. CP-SAT is free to (and did) drift previously-compliant
HV/SELV-classified components into new violations anywhere else on the board while satisfying the
21 explicit constraints. **This attempt is reported, not hidden, and is not the result used
below** -- Sec 3 fixes it by widening the encoded set.

---

## 3. Re-solve, attempt 2 (full domain-classified constraint set) -- the reported result

Same driver, same inputs, but `extra_constraints` = the **full, unfiltered**
`generate_domain_clearance_constraints(placement, voltage_domains)` output -- every classified
cross-domain pair on the board, mirroring `docs/evidence/2026-07-27-clearance-resolve-full-
coverage.md`'s own methodology (that re-solve used 11,725-12,409 constraints for the same reason).
**11,856 constraints** generated (158 classified components / 54 nets). The 21 Group C pairs are
a subset of this set, confirmed present with the expected margin before each solve.

### 3.1 Threshold parameterization

The disputed figure (validator's current `min_creepage_mm=8.0` for
`(DC_BUS, LV_CONTROL, REINFORCED)` in `clearance.py`'s `IEC60335_REQUIREMENTS`, vs.
`HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.2's "DC Bus to SELV / Reinforced / 400V pk / Min Required
**10.0mm**") was parameterized by temporarily overriding that one matrix row's
`min_creepage_mm` in-place before each solve (both `domain_clearance.py` and `clearance.py` import
the same dict object, so the override propagates to constraint generation and the post-hoc
validator identically) and restoring it after. `min_clearance_mm` (6.0mm either way) was left
untouched -- not in dispute, and dominated by creepage in both cases via
`required_margin_mm = max(clearance, creepage)`.

### 3.2 Results

| Margin | CP-SAT status | Solve time | Constraints | Group C pairs cleared | Overall REQ-SAFE-01 (measured, copper-to-copper) |
|---|---|---|---|---|---|
| 8.0mm | **optimal** | 40.5s (wall 40.5s) | 11,856 | **21 / 21** | **76 -> 11** violations, **33 -> 5** pairs |
| 10.0mm | **optimal** | 82.2s (wall 82.2s) | 11,856 | **21 / 21** | **76 -> 13** violations, **33 -> 7** pairs |

At **8.0mm**, the 5 pairs remaining after the resolve are exactly Group B's 5 known
footprint-intrinsic isolators (`C6`, `K2`, `K3`, `U3`, `U7`) -- **every** Group C pair and **every**
Group A (`C27`) pair cleared. The 7 `C27` pairs clearing is incidental, not a claim that the
resync defect (Sec 0 / Group A) is fixed: the constraint generator paired `C27` against its
netlist-declared (mismatched) domain the same way the validator does, and the solver found
positions satisfying that (mislabeled but still literally encoded) requirement. The resync defect
itself is untouched and unverified by this task, exactly as before.

At **10.0mm**, 7 pairs remain: the same 5 Group B isolators, **plus `K1` and `T1` newly appearing**.
Both are intra-footprint, both previously cleared 8.0mm (`K1` at exactly 8.000mm, `T1` at
9.100mm, per the brainstorm doc's Sec "Board state at time of measurement") but fall short of a
10.0mm minimum by fixed, placement-independent amounts (0.000mm and 0.900mm respectively) --
**the disputed threshold directly changes which components are footprint-fixable-only**, not just
by how much margin the placement re-solve needs to find. This is reported as a finding of the
parameterization itself, not a re-solve failure: neither `K1` nor `T1` is reachable by placement
either way (both are single-ref intra-footprint pairs, structurally unaddressable by
`SeparatedConstraint`, per Sec 1).

### 3.3 Post-solve audit (R24 item 3)

`audit_domain_clearance` recomputed real Euclidean center-to-center distance from the solved
coordinates for all 11,856 constraints, independent of the solver's own SAT claim, at both
margins: **0 mismatches** in both runs.

### 3.4 On "expect INFEASIBLE" (task item 4)

**No INFEASIBLE was hit or expected here, and that is correct, not a missed check.** The task's
INFEASIBLE warning is about the *isolation-barrier* mechanism
(`temper_placer.placer.cp_sat.isolation_barrier`, a hard bisecting-corridor constraint) --
documented as provably infeasible in `docs/evidence/2026-07-28-barrier-constrained-placement.md`
because it demands a single line separate every HV pad from every SELV pad, which the isolators'
own intra-footprint geometry forecloses. This task uses a **different** mechanism
(`domain_clearance.py`'s pairwise `SeparatedConstraint`, per the brainstorm doc's own
recommendation for Group C), which -- as shown in Sec 1 -- silently no-ops same-ref pairs rather
than encoding (and therefore rather than failing on) them. The isolators simply never get a
constraint from this mechanism; they remain violations in the measured output (Sec 3.2), not an
infeasible model. If a future task encodes the isolation-barrier constraint on this same board,
INFEASIBLE is still the expected, correct result for the reasons already proven in that prior
evidence doc -- unrelated to and not retested by this one.

---

## 4. Standard of proof: DRC before/after (median of N=5)

`kicad-cli pcb drc --format json`, 5 runs per board (`pcb/temper.kicad_pcb` unmodified; the two
candidate boards written to scratch only, never to `pcb/`):

| Board | median total violations | all-5 totals | median `shorting_items` | all-5 shorting | median `unconnected_items` | all-5 unconnected |
|---|---|---|---|---|---|---|
| baseline (real board) | 1239 | 1232, 1246, 1239, 1246, 1234 | 82 | 68, 82, 82, 82, 67 | 388 | 388 x5 |
| candidate @8.0mm | 996 | 991, 1006, 981, 996, 997 | 112 | 107, 117, 98, 112, 112 | 418 | 418 x5 |
| candidate @10.0mm | 1208 | 1209, 1216, 1208, 1192, 1193 | 126 | 126, 127, 126, 108, 111 | 418 | 418 x5 |

`shorting_items` scatter on the baseline (67-82, range 15) matches the task brief's own warning
("scatters ~20 on `shorting_items` alone") -- confirms the median-of-5 methodology is necessary
here, not overkill.

**This is a real regression, not noise: `shorting_items` and `unconnected_items` both increase at
both thresholds, and the candidates' shorting-item ranges (98-127) do not overlap the baseline's
(67-82).** `unconnected_items` moves from a *deterministic* 388 (all 5 baseline runs identical) to
a deterministic 418 (all 10 candidate runs, both thresholds, identical) -- a clean +30, not
scatter.

**Root cause, verified directly:** `write_placements_to_pcb` updates only footprint
positions/rotations and explicitly preserves "all other design data (traces, zones, etc.)"
unchanged (its own docstring, `_write_board.py:66-76`) -- confirmed by byte-for-byte identical
counts of `(segment`, `(via`, `(zone` S-expressions between the real board and both candidates
(2338 / 48 / 96, unchanged). **The real board is fully routed** (2338 track segments, 48 vias, 96
zones) -- unlike the board state the precedent full-coverage re-solve worked against
(`docs/evidence/2026-07-27-clearance-resolve-full-coverage.md` Sec 7 explicitly notes "routing is
untouched (0 segments/vias/zones... both before and after)" for *that* board). Moving footprints
without re-routing on a board that already has real copper routing strands and overlaps existing
traces -- which is exactly what the DRC numbers show.

**Scale of the reshuffle, measured directly:** median per-component displacement between the real
board and each candidate is **~100mm (8.0mm run) / ~116mm (10.0mm run)** on a 152mm x 234mm board
-- effectively every one of 168 components moved (167-168 moved more than 1mm). This is not a
targeted nudge of the 21 violating pairs; it is a full-board re-placement, consistent with
`solve_placement`'s own behavior when given soft hints (`AddHint`, not a binding pin) against
~12,000 hard constraints -- CP-SAT was free to, and did, find a global optimum far from the
current layout. This matches the documented precedent's own methodology (`docs/evidence/2026-07-
27-clearance-resolve-full-coverage.md`: "first solve attempt... full 170-component reshuffle with
no warm start"), but that precedent's board had no routing to disrupt; this one does.

**Conclusion, stated plainly per the task's own standard: this candidate placement, delivered as-
is (placement only, no re-route pass), trades a REQ-SAFE-01 clearance win (76 -> 11/13 violations)
for new DRC problems (+30-44 `shorting_items`, +30 `unconnected_items`, both real, both
reproducible). It is not a clean, ready-to-land fix.** A minimal-disruption variant -- pinning
every component not involved in a domain-crossing violation to its current position and re-
solving only the violating neighborhood -- was not attempted here (out of this task's remaining
scope; the CP-SAT encoder has no exposed "fix these refs, free those" API today) and is the
natural next step before any placement change like this is applied to the real board. Whichever
approach is used, it would still need a routing pass afterward; this task does not perform one
(`pcb/` is read-only here by design).

---

## 5. Answer to the task's central question

**Yes, a copper-aware CP-SAT domain-clearance re-solve clears all 21 placement-fixable pairs, at
both the disputed 8.0mm and 10.0mm thresholds, `status=optimal`, audited with 0 mismatches,
measured by the same copper-to-copper validator the gate uses (not assumed from the solver's own
claim).** The constraint mechanism that achieves this (`domain_clearance.py`'s pairwise
`SeparatedConstraint`) is bounding-box-based rather than literally per-pad-copper-aware (Sec 1),
but empirically -- checked, not assumed -- that proxy is sufficiently conservative to close every
one of the 21 Group C pairs' violations when measured against the real pad geometry, and (as a
side effect of also including the full classified-domain constraint set, not by design) the 7
Group A (`C27`) pairs too. It is not sufficient to fix the 5 Group B intra-footprint isolators,
which was expected and is not a defect in this mechanism, and it must be scoped to the *full*
classified-domain constraint set (11,856 constraints), not just the 21 target pairs, or it
regresses the board elsewhere (Sec 2). **The unresolved caveat is not clearance -- it's that this
specific candidate placement, produced without a subsequent re-route pass, is a full-board
reshuffle that measurably worsens routing DRC and should not be treated as ready to land.**

---

## 6. Reproduction

```bash
git fetch origin && git checkout -b feat/copper-aware-domain-resolve origin/main
uv sync --all-packages
make netlist
uv run pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -rA -s   # 76/33 baseline
uv run --no-sync python3 scripts/check_copper_net_consistency.py   # 10 pre-existing violations
uv run --no-sync python3 scripts/check_isolation_keepout.py        # 1 pre-existing violation
```

Driver script (`resolve.py`) and DRC harness (`run_drc.py`) used for Sec 2-4 are not committed
(scratch-only, per task instructions); their full invocations and output are reproduced verbatim
above. The candidate boards (`candidate_8.0mm.kicad_pcb`, `candidate_10.0mm.kicad_pcb`) are
available on request but not part of this PR -- `pcb/temper.kicad_pcb` was never written to.

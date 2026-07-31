<!-- provenance: commit=9cd5a356a4b2ef09a85949a87b0ea868aa0d3cf9 dirty=false -->

# Does board expansion make PD3 (12.6mm reinforced creepage) CP-SAT-feasible?

**Date:** 2026-07-30
**Base:** `origin/main` at `9cd5a356` (`chore: regenerate ARCHITECTURE.svg
[skip ci]`), which is `0a8e7194` (the R(+theta) -> R(-theta) rotation-
convention sign fix, PR #479) plus one commit -- confirmed an ancestor via
`git merge-base --is-ancestor 0a8e7194 HEAD`. Work done in worktree
`wt-pd3-expansion`, branch `experiment/pd3-board-expansion-measurement`,
branched directly from `origin/main`. `git status --short` clean throughout
(0 changes to any tracked file) -- every board-size and part-substitution
variation in this document is a **pure in-memory Python object mutation**
made after `parse_kicad_pcb()` returned, never a write to
`pcb/temper.kicad_pcb`, any `pcb/libs/` footprint, or `elec/src/`. No
temp-path board file was ever materialised; nothing needed one, since a
`Board` dataclass's `width`/`height` fields and a `Component`'s `pins` list
are ordinary mutable Python attributes that `solve_placement()` reads fresh
on every call.

**Method:** `make venv-isolate` run first (`uv sync --all-packages` +
`make extensions`, `scripts/check_stale_extensions.py`: 10/10 fresh). Every
invocation `uv run --no-sync`. No `git stash` used anywhere in this task.
Driver scripts (not committed -- one-off experiment drivers, matching this
repo's own precedent in `docs/evidence/2026-07-29-rotation-convention-sign-fix-cpsat-rerun.md`):
`/private/tmp/.../scratchpad/pd3-experiment/{pure_feasibility,
substitution_feasibility,sweep_axis_a,sweep_axis_b}.py`.

---

## Headline: NO. Board expansion does not make 12.6mm reachable -- not with current parts, and not even after the two verified substitutions.

**Axis A (board size, current parts): INFEASIBLE at every point tested**,
from the current 152x234mm up to +100% per dimension (304x468mm,
aspect-preserving), and every single-dimension-only variant in between --
**11 of 11 CP-SAT runs returned `infeasible`**, all with the identical
7-of-8 infeasible isolator set (`C6, K1, K2, K3, T1, U3, U7`) and the
identical UNSAT core (`isolator_straddle_C6`).

**Axis B (verified substitutions: C6, K2, K3): reduces the infeasible set
from 7 to exactly the predicted 4 (`K1, T1, U3, U7`)** -- confirmed both by
direct feasibility arithmetic and by a full CP-SAT integration re-solve --
but the model is **still INFEASIBLE**, at the current board size and after
+100% expansion alike (3 of 3 post-substitution CP-SAT runs: `infeasible`,
UNSAT core `isolator_straddle_K1`).

**Why board size cannot ever change this (proven, not just observed):**
`evaluate_isolator_feasibility()` -- the function that decides whether an
isolator's own HV/SELV pad clusters can straddle the corridor -- takes no
board-dimension argument anywhere in its call graph (`Pad.axis_radius`,
`_axis_gap`, `_best_rotation_for_barrier` all consume only pad-local
coordinates and `corridor_width_mm`). And in the CP-SAT encoding itself
(`add_isolation_barrier_to_model`), each isolator's two straddle
inequalities --

```
center_coord + hv_far_edge_units      <= barrier_lo_units
center_coord + selv_near_edge_units   >= barrier_hi_units
```

-- have `center_coord` (a free variable) appearing with the same sign
convention in both, so subtracting them eliminates it entirely, leaving
`selv_near_edge_mm - hv_far_edge_mm >= corridor_width_mm`: a comparison
between two **fixed constants** (both a function of the part's own pad
geometry only) and the corridor's own width (a **fixed target**, 12.6mm,
never a function of board size). `barrier_lo`/`barrier_hi` individually
shift with `corridor_position_mm = span_mm/2 - corridor_width_mm/2` as the
board grows, but their *difference* is always exactly `corridor_width_mm`,
so that shift cancels too. **An isolator whose own pad pitch cannot clear
12.6mm is UNSAT for every board size, at every board position, by
construction -- not a search result CP-SAT could find with more room.**
Growing the board changes how much room the 150 domain-only components have
to pack; it changes nothing about whether an isolator's own two pads are
far enough apart.

---

## 1. Sanity check (per the task brief -- run first, reported first)

**PASSED.** The set of individually-infeasible isolators is exactly
invariant across all 11 board-size/orientation points tested at 12.6mm:
`{C6, K1, K2, K3, T1, U3, U7}` in every case, no exceptions, no isolator
crossing from infeasible to feasible (or vice versa) at any size. See the
full sweep table in Sec. 3.

This matches the analytic argument in the headline above exactly, and the
argument was checked against the actual code before any solver was run
(see `packages/temper-placer/src/temper_placer/placer/cp_sat/
isolation_barrier.py`'s own module docstring, "Orientation and corridor
position are fixed constants... a movable corridor buys zero extra isolator
feasibility" -- this experiment's finding is that *board size* is the same
kind of fact, for the same underlying reason, and the sweep is the
empirical confirmation of that reading). No implementation surprise was
found; nothing required stopping to investigate.

## 2. Reproducing the stated baseline (current board, current parts)

```
$ uv run --no-sync python pure_feasibility.py   # no CP-SAT -- direct arithmetic
Board (real, as parsed): 152 x 234 mm, 169 components
Partition: hv_only=45 selv_only=106 isolators=8 unclassified=10  (sum=169, matches)
Isolators: ['C6', 'K1', 'K2', 'K3', 'PS1', 'T1', 'U3', 'U7']

vertical/X:   infeasible isolators @ 12.6mm = [C6, K1, K2, K3, T1, U3, U7]  (7/8)
horizontal/Y: infeasible isolators @ 12.6mm = [C6, K1, K2, K3, T1, U3, U7]  (7/8)
```

| Isolator | achievable_gap_mm (vertical/X) | achievable_gap_mm (horizontal/Y) | Feasible @ 12.6mm? | Shortfall |
|---|---:|---:|:---:|---:|
| C6  | 8.00  | 8.00  | NO  | 4.60mm |
| K1  | 8.00  | 8.00  | NO  | 4.60mm |
| K2  | -0.50 | -0.50 | NO  | 13.10mm |
| K3  | -0.50 | -0.50 | NO  | 13.10mm |
| PS1 | 35.50 | 35.50 | YES | (4x margin) |
| T1  | 9.10  | 9.10  | NO  | 3.50mm |
| U3  | 8.56  | 8.56  | NO  | 4.04mm |
| U7  | 8.10  | 8.10  | NO  | 4.50mm |

Full CP-SAT integration run (real `pcb/temper.kicad_pcb`, real
`elec/domain_manifest.yaml`, vertical corridor, `corridor_width_mm=12.6`):

```
Board: 152 x 234 mm, 169 components
status=infeasible   solve_time=23485ms (23.5s wall)
UNSAT core: isolator_straddle_C6
infeasible_isolators (from report): C6, K1, K2, K3, T1, U3, U7
```

This exactly reproduces the task brief's stated starting point (`INFEASIBLE
in both board orientations, UNSAT core isolator_straddle_C6, 7 of 8
isolators individually infeasible: C6, K1, K2, K3, T1, U3, U7`), on a fresh
worktree, post-rotation-fix, independent of the doc that first reported it
(`docs/evidence/2026-07-29-rotation-convention-sign-fix-cpsat-rerun.md`,
different commit hash but the same underlying fix). One immaterial
discrepancy, reported not chased: this checkout's board has **169**
components / 45 HV-only (vs. 168/44 in the two prior evidence docs) -- a
+1 HV-only component drift from an intervening board regeneration
(`docs/evidence/2026-07-29-board-regeneration-corrected-footprints.md`),
not investigated further here since it does not touch any isolator and
does not change this experiment's finding.

## 3. Axis A -- board outline size sweep (current parts, 12.6mm)

All runs: `corridor_width_mm=12.6`, real `elec/domain_manifest.yaml`, real
netlist pad geometry (only `board.width`/`board.height` overridden
in-memory per point), `timeout_ms=90000` (well above the ~23-25s each run
actually took to prove infeasibility).

| Board size (mm) | Growth | Orientation | Status | Wall time | Infeasible isolators | UNSAT core |
|---|---|---|---|---:|---|---|
| 152 x 234 | current | vertical | **INFEASIBLE** | 23.5s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 167.2 x 257.4 | +10% both | vertical | **INFEASIBLE** | 23.4s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 190.0 x 292.5 | +25% both | vertical | **INFEASIBLE** | 24.5s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 228.0 x 351.0 | +50% both | vertical | **INFEASIBLE** | 24.3s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 304.0 x 468.0 | +100% both | vertical | **INFEASIBLE** | 23.5s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 228.0 x 234 | +50% width only | vertical | **INFEASIBLE** | 23.6s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 152.0 x 351.0 | +50% height only | vertical | **INFEASIBLE** | 23.7s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 304.0 x 234 | +100% width only | vertical | **INFEASIBLE** | 23.6s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 152.0 x 468.0 | +100% height only | vertical | **INFEASIBLE** | 23.8s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 152 x 234 | current | horizontal | **INFEASIBLE** | 23.5s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |
| 304.0 x 468.0 | +100% both | horizontal | **INFEASIBLE** | 23.6s | C6,K1,K2,K3,T1,U3,U7 | isolator_straddle_C6 |

**11 of 11: INFEASIBLE.** Same isolator set, same UNSAT core, every time,
regardless of which axis grows or by how much, and regardless of corridor
orientation. Raw driver output:
`/private/tmp/.../scratchpad/pd3-experiment/sweep_axis_a.out.json`.

This is the sanity check's own headline number made concrete: since the
7 infeasible isolators' shortfalls (3.5-13.1mm, Sec. 2 table) never move
with board size, and packing feasibility for the 150 domain-only components
was never reached (the isolator constraints alone make the model UNSAT
before packing quality is even evaluated), there is no board size --
sweeping to +100% per dimension, single-axis or both -- that helps.

## 4. Axis B -- verified part substitutions (C6, K2/K3)

Modeled per the task brief's verified figures, substituting ONLY these
three components' `Component.pins` in memory (K1, T1, U3, U7, PS1 and every
other component: real, untouched board geometry):

- **C6** -> TDK/EPCOS B81123C1222M000 (Y1, 500VAC, ENEC-05495 + UL E97863
  granted). Modeled as two 2.4mm-diameter round THT pads at 15.0mm pitch:
  `15.0 - 2.4 = 12.600mm` edge-to-edge -- reproduces the task brief's
  verified figure exactly (2.4mm is a standard annular-ring pad diameter
  for an 0.8mm lead; the brief did not specify a pad diameter, only the
  final 12.600mm achievable-gap result, which this model reproduces
  precisely rather than approximates).
- **K2, K3** -> TE Schrack RT1 family (e.g. `RT114012`). Modeled as two
  zero-radius point pads at 13.820mm pitch -- an idealized abstraction that
  reproduces the one number the feasibility test actually consumes
  (`achievable_gap_mm`) exactly, without fabricating intermediate
  lead/pad-diameter detail this session's manufacturer-drawing
  verification did not establish.

### Pure feasibility arithmetic (no CP-SAT)

```
vertical/X:   infeasible isolators @ 12.6mm AFTER SUBSTITUTION = [K1, T1, U3, U7]  (4/8)
horizontal/Y: infeasible isolators @ 12.6mm AFTER SUBSTITUTION = [K1, T1, U3, U7]  (4/8)
```

| Isolator | achievable_gap_mm | Feasible @ 12.6mm? | Note |
|---|---:|:---:|---|
| C6 (subst.) | 12.600 | **YES** | Exact boundary -- zero margin, see caveat below |
| K1 | 8.00 | NO | unchanged, no verified replacement in scope |
| K2 (subst.) | 13.820 | **YES** | +1.22mm margin |
| K3 (subst.) | 13.820 | **YES** | +1.22mm margin |
| PS1 | 35.50 | YES | unchanged |
| T1 | 9.10 | NO | unchanged, no verified replacement in scope |
| U3 | 8.56 | NO | unchanged, no verified replacement in scope |
| U7 | 8.10 | NO | unchanged, no verified replacement in scope |

**Matches the task brief's predicted remainder (K1, T1, U3, U7) exactly --
CONFIRMED, not refuted.**

### CP-SAT integration re-solve (confirms the arithmetic, not just asserts it)

| Board size | Orientation | Status | Wall time | Infeasible isolators | UNSAT core |
|---|---|---|---:|---|---|
| 152 x 234 (current) | vertical | **INFEASIBLE** | 23.6s | K1, T1, U3, U7 | isolator_straddle_K1 |
| 152 x 234 (current) | horizontal | **INFEASIBLE** | 23.5s | K1, T1, U3, U7 | isolator_straddle_K1 |
| 304 x 468 (+100% both) | vertical | **INFEASIBLE** | 23.4s | K1, T1, U3, U7 | isolator_straddle_K1 |

Post-substitution, the model is **still infeasible at every board size
tested**, for the same structural reason as Sec. 0/3: the remaining 4
isolators' shortfalls (3.5-4.6mm, none touched by this substitution) are
board-size-invariant facts, so expansion buys nothing here either. This was
checked, not assumed -- the +100% run above is the direct empirical
confirmation that substitution does not create a NEW dependency on board
size where none existed before.

**Caveat on C6's substituted margin:** 12.600mm achievable exactly equals
the 12.6mm corridor target -- a **zero-margin boundary result**, not a
comfortable clearance (contrast K2/K3's +1.22mm). The brief's own C6 source
spec states "15.00mm **+/-0.4mm** lead spacing" -- at the tolerance's low
end (14.6mm), this model's pad-diameter assumption would put achievable_gap
at 12.2mm, **below** 12.6mm and infeasible. This experiment modeled the
nominal (best-case-tolerance) dimension only, per the brief's own stated
figure; the tolerance-stack question is flagged, not resolved, in
UNVERIFIED below.

## 5. Minimum expansion achieving feasibility

**None exists, in either configuration tested.**

- **Current parts:** no board size, up to +100% per dimension (aspect-
  preserving or single-axis), achieves FEASIBLE. Per Sec. 0's proof, no
  larger size would either -- the blocking constraints do not weaken with
  board size at all, so this is not a "sweep further" gap, it is a
  structural ceiling.
- **With C6 + K2/K3 substituted:** still no board size (tested to +100%)
  achieves FEASIBLE, for the identical structural reason -- K1, T1, U3, U7
  remain individually infeasible and would need their own part/footprint
  changes (the task brief scoped only C6/K2/K3 as having verified
  replacements this session; K1/T1/U3/U7 do not).
- **What WOULD have to be true for board size to become relevant at all:**
  all 7 blocking isolators (or a superset covering C6/K1/K2/K3/T1/U3/U7)
  need verified replacement parts/footprints whose own achievable_gap_mm
  clears 12.6mm on some axis. Only then does the question this experiment
  was asked to answer -- "does the 150-domain-only-component packing
  problem fit in the current 152x234mm envelope, or does IT need more
  room" -- become the binding one. That packing question was never reached
  in any run in this document (the model goes UNSAT on the isolator
  constraints alone, before packing quality is evaluated at all), so this
  experiment has no data on it either way.

## Verdict on the decision this informs

**Board expansion does not make PD3 (12.6mm reinforced creepage) reachable
for this design as it stands.** The blocker is not board area; every
isolator whose achievable pad-to-pad gap falls short of 12.6mm falls short
by a board-size-independent, provable-from-code-structure amount, and nine
board sizes up to +100% per dimension plus 2 orientations all confirm this
empirically with zero exceptions. Releasing the "board may be expanded"
constraint does not, by itself, unblock the PD3 path.

What DOES move the needle: **verified part substitution.** C6 and K2/K3
substitution (already verified against manufacturer drawings this session)
closes 3 of 7 isolator gaps. **K1, T1, U3, and U7 remain the blocker** --
confirmed exactly as predicted, both by direct arithmetic and by CP-SAT
re-solve, and expansion does not help close these four either, for the
same structural reason. The PD2-via-cl.-29.2-enclosure-exception line this
task's brief says was "previously the plan" has NOT been shown unnecessary
by this experiment -- if anything, this experiment shows board expansion
specifically cannot substitute for it; only closing all 7 isolator gaps
(K1/T1/U3/U7 still need verified replacements) can.

## Hard constraints -- compliance checklist

- `pcb/temper.kicad_pcb`, every `pcb/libs/` footprint, `elec/src/`: **zero
  bytes changed** -- `git status --short` clean throughout this task, every
  variation applied as an in-memory Python mutation post-parse.
- `MIN_BARRIER_WIDTH_MM` and every committed safety target: untouched.
  `corridor_width_mm=12.6` was passed as a solver-invocation parameter
  only, matching the exact figure and margin convention already used by
  `docs/evidence/2026-07-29-rotation-convention-sign-fix-cpsat-rerun.md`
  (12.1mm PD3 creepage target + 0.5mm margin, the same convention as the
  pre-existing 8.0+0.5=8.5mm PD2 check) -- never a new/different threshold
  invented for this experiment.
- No re-floorplanning, no hand placement: every result above is a fresh
  CP-SAT feasibility query (`solve_placement`), not a placement this
  document then edited or accepted.
- `make venv-isolate` run first in this worktree; `uv run --no-sync`
  throughout; no `git stash` anywhere in this task.
- Committed before the long-running Axis A sweep (11 CP-SAT solves,
  ~260s total) via `run_in_background`, per the task brief's explicit
  instruction; no polling loop used to wait on it.
- No sub-agents spawned for this task.
- `scripts/check_evidence_provenance.py` run against this file (see
  Verification below).

## Verification

| Check | Result |
|---|---|
| `git merge-base --is-ancestor 0a8e7194 HEAD` | exit 0 (ancestor confirmed) |
| `make venv-isolate` | exit 0 |
| `scripts/check_stale_extensions.py` | PASSED -- 10/10 fresh |
| `git status --short` (worktree, throughout) | clean (0 changes) |
| Pure feasibility reproduction of baseline | matches task brief exactly: 7/8 infeasible = C6,K1,K2,K3,T1,U3,U7 |
| Axis A sweep (11 CP-SAT runs) | 11/11 infeasible, isolator set + UNSAT core invariant |
| Axis B pure feasibility | matches predicted remainder K1,T1,U3,U7 exactly |
| Axis B CP-SAT integration (3 runs) | 3/3 infeasible, K1,T1,U3,U7, UNSAT core isolator_straddle_K1 |
| `scripts/check_evidence_provenance.py` | (run after this file was written -- see commit) |

## UNVERIFIED

- **C6's substituted margin is a zero-margin boundary result** (12.600mm
  achievable vs. 12.6mm required) -- whether the real stock land pattern's
  actual pad diameter (not independently re-derived here beyond the task
  brief's stated 12.600mm final figure) holds up under the brief's own
  stated +/-0.4mm lead-spacing tolerance is flagged, not resolved. If the
  real achievable figure is anywhere below 12.600mm once tolerance is
  accounted for, C6 re-joins the infeasible set and the Axis B remainder
  grows back to 5.
- **The domain-only-component packing question was never reached** in any
  run in this document (every run goes UNSAT on isolator constraints
  alone) -- so this experiment has no data on whether the 150 HV-only/
  SELV-only components would fit a compliant packing against a 12.6mm
  corridor even if all 7 isolators were eventually resolved. A future
  experiment with all 7 isolators substituted (not just 3) would be needed
  to actually reach that question.
- Whether K1/T1/U3/U7 have their OWN verified replacement parts was out of
  this task's scope (the brief named only C6 and K2/K3 as verified this
  session) -- not investigated here.
- IEC 60335-1 primary-text creepage tables remain paywalled and were not
  independently re-derived in this pass (same UNVERIFIED-at-primary status
  every prior evidence doc in this area carries).

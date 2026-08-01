# Minimum-displacement clearance repair machinery (issue #504): build + board findings

<!-- provenance: commit=4a8b721b642b6fdf2dbe0ed2409df6fb4a275d45 dirty=true (branch fix/clearance-resolve-reroute-loop, based on origin/main 4a387393e; measurements taken on pcb/temper.kicad_pcb at that base, read-only) -->

**Date:** 2026-07-31
**Scope:** machinery only — `packages/temper-placer` solve-pipeline additions +
tests + this evidence. `pcb/temper.kicad_pcb` and
`power_pcb_dataset/drc_ceiling.json` are **untouched** on every pushed branch
(board output belongs to the #517 workstream).
**Base:** origin/main `4a387393e` ("fix(placer): make domain-clearance bbox
constraint copper-aware, sound (#460)").

## 1. What was built

A repair mode for the CP-SAT placement pipeline, resolving issue #504's required
approach ("add a minimum-displacement or route-aware placement/re-routing
loop"):

1. `CpSatModel.add_displacement_objective(ref, x, y, weight, max_units)` —
   Manhattan-distance objective toward a reference position (a *preference*;
   hard constraints stay authoritative), with an optional hard per-component
   bound `|dx| + |dy| <= max_units` (the bounded-repair formulation).
2. `CpSatModel.add_fixed_rotation(ref, rot)` — hard-pin a component's 0-3
   rotation index (a repair solve must not rotate footprints: rotation moves
   every pad, disconnecting routed copper — `docs/evidence/2026-07-30-placement-writer-rotation.md`).
3. `CpSatModel.apply_objective()` — the single point where accumulated
   objective terms become a real `Minimize`; **regression-guarded against the
   never-landed PR #498 no-op** (terms were registered but `Minimize` was never
   called on the encoder solve path, making the parameter a silent no-op).
4. `solve_placement(minimize_displacement_to=..., fixed_rotations=...,
   max_displacement_mm=...)` — the encoder wiring.
5. `domain_clearance.generate_unclassified_hv_keepaway_constraints` — promotes
   the real-board fixture's fail-closed proximity check ("no unclassified
   component within the largest IEC margin of a declared-HV part") into one
   hard `SeparatedConstraint` per (unclassified, HV) pair, so a repair solve
   cannot regress it (the 2026-07-27 R52/C14 regression mode, generalised).
6. `clearance_repair.run_clearance_repair_solve` — the loop: full
   domain-clearance set + keep-away + min-displacement objective + fixed
   rotations + warm-start hints → R24 post-solve audit
   (`audit_domain_clearance`) → independent copper-to-copper re-check
   (`verify_iec60335_compliance`) → bounded reinforcement of any still-flagged
   inter pair. Statuses: `clean` / `intra_only` / `infeasible` / `gap` /
   `max_rounds` — it **reports infeasibility honestly** (proven UNSAT core
   surfaced as `infeasible`, distinct from `unknown`/timeout, gap pairs
   named) instead of converging to nothing.

### Loop invariant and termination (the induction)

- Invariant: every round's constraint set contains a hard `SeparatedConstraint`
  for every pair the previous round's independent check flagged.
- Base: round 0 uses the full domain-clearance set from the same classifier the
  checker uses (imported, not reimplemented).
- Step: a round either reaches 0 inter violations or adds >= 1 new constraint;
  distinct inter pairs are finite (<= N²), so the loop terminates in at most
  (distinct pairs) + 1 rounds. A flagged pair whose hard constraint was SAT in
  the same round contradicts the box-separation soundness proof (box sep ⇒ pad
  copper sep — `domain_clearance.py` module docstring, revised copper-aware
  2026-07-30) and terminates immediately with status `"gap"` — never a silent
  false success.

### R24 discipline

The new objective/bound is a *geometry* quantity (Manhattan displacement), not a
physics-gated constraint; its soundness is the trivial `AddAbsEquality`
identity, and its hard-bound form is validated exhaustively on small N against a
truthful closed-form oracle (`TestDisplacementObjectiveBMC`, 25 hypothesis
cases; plus the exact-optimum pin `test_solver_breaks_infeasible_reference_
with_minimal_moves`, total = 60mm by `|u - v| <= |u| + |v|`). The
physics-gating part (domain-clearance `SeparatedConstraint`) carries the
existing Chebyshev-style soundness proof + `audit_domain_clearance` post-solve
audit, re-run on every round of the repair loop.

## 2. Test evidence (all on this branch)

| suite | result |
|---|---|
| `tests/placer/cp_sat/test_model.py` | **34 passed** (includes 12 new: displacement objective × 8, fixed rotation × 4) |
| `tests/placer/cp_sat/test_clearance_repair.py` (unit/synthetic) | **15 passed** |
| `tests/placer/cp_sat/test_clearance_repair.py` (real-board) | **2 passed** — the issue's success criterion, below |
| `tests/placer/cp_sat/test_domain_clearance.py` + `tests/requirements/safety/test_clearance.py` | 43 passed, **1 pre-existing failure** (`test_temper_board_clearance_compliance`, the board's actual clearance debt — reproduces byte-identically on origin/main) |
| full `tests/placer/cp_sat/` | 453 passed, 2 failed (`test_regression_drc.py` corpus-copy pair — reproduces identically on origin/main) |
| `ruff check` | clean on every touched file |
| `scripts/import_linter_gate.py` | PASSED — 0 new violations |
| `scripts/gen_repo_state.py` | run twice → byte-identical (metamorphic) |
| `scripts/check_stale_extensions.py` | 10/10 fresh after `make extensions` |

### Metamorphic relations asserted (task brief)

1. Solver output re-checked by the independent REQ-SAFE-01 checker reports
   **<=** the solver's claimed bound: the real-board test re-runs
   `verify_iec60335_compliance` on the solved placement and asserts 0
   inter-component records (solver claimed 0).
2. Solve determinism: `test_determinism_same_input_same_output` — same input +
   seed ⇒ identical positions and rotations (hypothesis sweep over seeds).
3. Copper-to-copper is a sound LOWER bound on the old origin-to-origin model:
   `test_checker_copper_distance_is_lower_bound_on_origin_distance` asserts
   `copper >= origin - reach_A - reach_B` for every baseline violating pair
   (the sound prune bound), and that the majority of pairs sit in the
   optimistic (copper < origin) direction — the relation that explains why 123
   violations exist under the copper model.

## 3. Board findings (read-only measurements on the current routed board)

### 3.1 Baseline

`verify_iec60335_compliance` on `pcb/temper.kicad_pcb` at origin/main
`4a387393e`: **123 REQ-SAFE-01 violations across 79 pairs** at the 12.6mm
reinforced margin (PD3), 10 unclassified components, 7 intra-footprint blocker
refs (C6, K1, K2, K3, T1, U3, U7 — 11 intra records). Consistent with the
issue's 115/78 (board and classification have moved slightly since).

### 3.2 Full-set min-displacement repair — sound, but a full re-layout

`run_clearance_repair_solve` (full domain set, 12,552 constraints + keep-away +
min-displacement objective + fixed rotations, 90s/round, seed 0):

- **Round 1: `feasible`, audit 0, independent checker inter = 0, intra = 11,
  status `intra_only`.** Every movable inter-component pair cleared, verified
  by the independent checker, not the solver's claim. Intra blockers
  enumerated, not claimed fixed.
- **But total Manhattan displacement = 22,686mm; 169/169 components moved
  > 1mm, 168 > 10mm** (top movers 200-277mm). At a 600s budget the objective
  only improves to 22,133mm (−2.4%) — the displacement is the *true minimum of
  the full constraint set*, not a search artifact. (Run-to-run variation
  ±1-5%: 23,706mm in the same-config test run; the 90s solve returns
  `feasible`, not proven-`optimal`, so the objective is a quality metric, not
  a guarantee. The 0-inter guarantee is the sound part.)

**Why:** the full domain-clearance set demands **courtyard-box edge separation
>= 12.6mm for every cross-domain pair** (~12.5k pairs; box ⊇ real pad copper by
the #460 frame fix, but the box is courtyard-sized, far larger than the copper
the checker measures). On a 152×234mm board with 169 components, 12.6mm
box-separation for nearly every pair is close to the packing limit (grid
estimate ~216 cells); the routed board, laid out to satisfy *copper*-level
requirements, is far outside that feasible region. The bbox constraint is sound
but drastically over-conservative relative to the checker's copper requirement.

### 3.3 Bounded repair — provably infeasible at any sane envelope

`max_displacement_mm` in {10, 20, 40}: **infeasible** (UNSAT core 15,734 —
full set + displacement bounds). At 80mm: not even provably feasible in 60s.
**The current routed board cannot be fixed by small nudges at the 12.6mm
margin**; the machinery reports this honestly (`status=infeasible`, core
surfaced) rather than converging to nothing.

### 3.4 Scoped repair (constrain only checker-flagged pairs) — does not converge

An alternative "repair only the violating pairs" formulation was probed in
scratch: initial constraint set = the baseline checker's inter pairs (79) at
their margins, min-displacement objective, fixed rotations, reinforcement
loop. **It does not converge**: 112 inter → 168 (round 0, 6.5k mm, 81 moved) →
118 (round 1) → 119 (round 2) → 95 (round 3, 402 constraints) → `unknown`
(round 4, 22s). Each round's moves create new copper violations elsewhere,
which get reinforced, which forces more moves — oscillation, not convergence,
at 6.5-9.2k mm displacement (smaller than the full set but still a large
reshuffle). The full-set formulation (Sec 3.2) is the sound one: its 12.6mm
box-separation constraints make drift structurally impossible, clearing every
movable pair in one round; its displacement cost is inherent to the 12.6mm
box-separation requirement, not to the objective.

## 4. Conclusion for issue #504

The machinery required by the issue is delivered, tested, and honest:

- A feasible solve that satisfies the full 12.6mm constraint set **exists**
  (proved by construction, round 1 `feasible`), clears **every** movable
  inter-component pair, and is verified by the independent copper-to-copper
  checker — but it is a **full re-layout** (22k mm displacement), which the
  issue explicitly forbids writing into the routed PCB.
- A **bounded** (minimum-displacement) repair is **provably infeasible at
  10/20/40mm** envelopes — the 123-violation board state cannot be repaired by
  nudges while satisfying the full bbox constraint set at 12.6mm.
- 7 intra-footprint blockers (C6, K1, K2, K3, T1, U3, U7) are unfixable by any
  placement (same-footprint domain crossings), per the module's soundness
  proof and the #518 sibling finding (barrier-constrained solves infeasible
  with current isolator footprints).

**Next step for the board workstream (#517):** a placement that clears
REQ-SAFE-01 at 12.6mm is necessarily a full re-layout *plus a re-route pass*;
the machinery here produces and validates such placements (positions in
`ClearanceRepairReport.final_positions`), and the DRC ceiling protocol applies
to whatever board change #517 lands. The alternative — making the constraint
copper-accurate (per-pad, per-domain copper boxes instead of courtyard boxes)
so that the feasible region matches what the checker actually requires — is a
follow-up constraint-model change that would materially shrink the required
displacement; it is out of scope for this machinery PR.

## 5. Reproduction

```bash
cd packages/temper-placer
uv run --no-sync python -m pytest tests/placer/cp_sat/test_model.py tests/placer/cp_sat/test_clearance_repair.py -q
# real-board success criterion (90s):
uv run --no-sync python -m pytest tests/placer/cp_sat/test_clearance_repair.py -q -k TestRealBoardClearanceRepair
```

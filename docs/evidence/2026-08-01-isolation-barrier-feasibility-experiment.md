<!-- provenance: experiment plan docs/plans/2026-08-01-002-feat-isolation-barrier-feasibility-experiment-plan.md -->

# Isolation-Barrier Corridor-Feasibility Probe — Decision Record (2026-08-01)

Empirical GO/NO-GO for the corridor-constrained CP-SAT re-solve on the
production board at **8.0 mm** corridor width, in both orientations, as-is
and K3-relaxed, per plan `docs/plans/2026-08-01-002-*`. Replaces the
geometric bound of
`docs/evidence/2026-08-01-isolation-barrier-feasibility.md` (52/78 movers,
127/135 mm max drift) with measured solver outcomes.

**Verdict: NO-GO as scoped.** Stage 1 (any feasible corridor placement) is
achievable — in **both** orientations, but only in the K3-relaxed model;
Stage 2 (hard 25 mm/component budget) is **infeasible in all four cells,
proven by the solver** (as-is by the straddle contradiction; K3-relaxed by
direct propagation in ~1–2 s). Every cell of the matrix was decided; none
is reported as `unknown`.

## Board and model (verified)

- Board: `pcb/temper.kicad_pcb`; 152×234 mm outline, **169 components**
  parsed via `temper_placer.io.kicad_parser.parse_kicad_pcb` (the same
  path the pipeline InputStage and the committed feasibility evidence use).
- Partition (recomputed by the placer's own `classify_domain_partition`):
  HV-only 45, SELV-only 106, isolators 8 (C6, K1, K2, K3, PS1, T1, U3, U7),
  unclassified 10. Staged: **C27** (pads outside the outline) — excluded
  from the displacement reference/budget and metrics, still registered in
  the model.
- Corridor at the machinery default position (board centreline: X c=72.0 mm,
  Y c=113.0 mm), width exactly 8.0 mm.
- Stage 1 uses the SOFT min-displacement objective (`minimize_displacement_to`,
  plan OQ-B) so the reported displacement is the solver's best near-current
  placement, not an arbitrary far-away packing. **The reported stage-1
  displacement is the best *found*, not proven-optimal** (CP-SAT returned
  FEASIBLE at the time limit while still improving).
- Stage 2 adds the HARD per-component Manhattan bound
  (`max_displacement_mm=25.0` + `minimize_displacement_to`) — the existing
  bounded-repair formulation (issue #504); **no encoder addition was needed**
  (the plan anticipated a possible small addition; it already existed).
- K3-relax drops ONLY K3's isolator-straddle constraint and rotation pin
  (new additive `relax_isolator_straddle` param on
  `add_isolation_barrier_to_model`, commit 081834644); the geometric verdict
  (K3 infeasible at 8.0 mm) is still recorded in the report.
- Warm-start hints at current positions (with current rotation) are used in
  all runs — a materially different solver trajectory than hint-free runs
  (one hint-free X-as-is run produced a 22k-entry sufficient core; the
  hint-warm-started runs produce small cores). All numbers below are from
  the hint-warm-started runner.
- Displacement metric: Manhattan |dx|+|dy| of component centres vs current
  positions; mover = >1 mm; staged C27 excluded.

## New finding vs the committed geometric evidence: K1's 8.0 mm boundary

`evaluate_isolator_feasibility` on the real board at 8.0 mm:

| Isolator | achievable axis=0 (X) | feasible@8.0 X | achievable axis=1 (Y) | feasible@8.0 Y |
|---|---|---|---|---|
| C6 | 8.0 | yes | 8.0 | yes |
| K1 | **7.999999999999998** | **no** | 8.0 | yes |
| K2 | 12.76 | yes | 12.76 | yes |
| K3 | −0.5 | no | −0.5 | no |
| PS1 | 35.5 | yes | 35.5 | yes |
| T1 | 9.1 | yes | 9.1 | yes |
| U3 | 8.56 | yes | 8.56 | yes |
| U7 | 8.1 | yes | 8.1 | yes |

K1 is a **second straddle blocker in orientation X**, by 2e-15 mm (float
noise exactly at the 8.0 floor; K1's real physical HV/SELV gap is exactly
8.0 mm on its local Y axis, which the 90-degree rotation for a vertical
corridor projects onto X with sub-ULP error). The committed geometric
evidence reported "K1 8.0 ✓" because it took `max(axis0, axis1)`; the
placer's own per-corridor verdict for a vertical corridor is
`7.999999999999998 < 8.0`. Implication: **K3-relax alone does not
geometrically unblock orientation X** — K1's marginal shortfall remains.
(The solver's integer model rounds this to 800 units, so whether it
actually blocks a solved X placement is a solver outcome, below.)

## Solver matrix (measured 2026-08-01)

Runs: `docs/evidence/2026-08-01-isolation-barrier-corridor-feasibility.py`
(`uv run --no-sync python`, hint warm-start, per-cell caching); solver
seed 0, 4 workers. Time budget 900 s/cell; a cell exceeding it is
`unknown`, never reported as feasible.

| Cell | status | time (s) | max disp (mm) | total disp (mm) | movers >1 mm | witness / note |
|---|---|---|---|---|---|---|
| X · as-is · s1 | **infeasible** | 1.0 | — | — | — | sufficient core named `edge_margin_*`; geometric cause K3 (−0.5) + K1 (7.9999…) |
| X · k3-relaxed · s1 | **feasible** | 757.6 | 270.0 | 17498.04 | 166 | proves K1's 2e-15 shortfall does NOT block the integer model (rounds to 800 units) |
| Y · as-is · s1 | **infeasible** | 1.1 | — | — | — | geometric cause: K3 (−0.5) |
| Y · k3-relaxed · s1 | **feasible** | 346 | 359.56 | 19550.98 | 166 | first measured feasible corridor placement; not optimal (objective still improving) |
| X · as-is · s2 | **infeasible** | 1.0 | — | — | — | same straddle cause; budget moot |
| X · k3-relaxed · s2 | **infeasible** | 1.2 | — | — | — | 25 mm budget contradicts the corridor: propagation, ~1 s |
| Y · as-is · s2 | **infeasible** | 1.0 | — | — | — | same straddle cause; budget moot |
| Y · k3-relaxed · s2 | **infeasible** | 2.0 | — | — | — | 25 mm budget contradicts the corridor: propagation, ~2 s |

Reproducibility cross-check: an independent session re-running the same
harness produced identical displacement numbers for X · k3-relaxed · s1
(270.0 / 17498.04) and identical verdicts for every shared cell (same
solver seed 0 → deterministic search).

### Notes on the as-is cores
The solver's sufficient subset for the as-is cells names `edge_margin_*`
assumptions (a valid but non-minimal sufficient subset; the same runs'
isolator-feasibility report independently proves K3 cannot straddle 8.0 mm
— `evaluate_isolator_feasibility` on the real pads, not solver inference).
The as-is infeasibility is therefore attributed geometrically, not from
the arbitrary core subset.

## Success-criteria check (plan)

PASS = stage 1 feasible in ≥1 orientation **and** stage 2 within-budget
feasible in ≥1 orientation (as-is or K3-relaxed, K3-delta quantified).

- **Stage 1:** feasible in ≥1 orientation — **YES**, in **both**
  orientations, but only in the K3-relaxed model (X 270.0 mm max,
  Y 359.6 mm max, 166 movers each; best-found, not optimal). As-is is
  infeasible in both orientations. **K3-relaxed delta:** dropping K3's
  straddle is *necessary* for any feasible corridor placement at 8.0 mm —
  it is what turns both orientations from infeasible to feasible. (K1's
  marginal 2e-15 shortfall in X does not block the solver's integer model.)
- **Stage 2:** within-budget (≤25 mm/component) feasible — **NO in all
  four cells, all proven infeasible** (as-is by the straddle; K3-relaxed by
  direct propagation in 1.2–2.0 s). The 25 mm budget confines every
  component near its current position while the corridor demands a
  wholesale one-domain move — a contradiction the solver finds immediately.
  Consistent with the committed geometric bound (translation-only: Y needs
  ≥127 mm max drift, X ≥135 mm).
- **Verdict: NO-GO as scoped.** The 25 mm/component budget cannot be met
  by any corridor-constrained placement at 8.0 mm on this board — not
  even with the K3 relaxation that unblocks stage 1. The barrier plan
  (`2026-08-01-001`) must be re-scoped before any keepout is authored:
  e.g. a much larger displacement budget, a wider/narrower corridor
  negotiation, or the split-board topology (all out of this plan's scope).

## How it was wired / run

- Production solve path: `solve_placement(netlist, board, isolation_barrier={...})`
  with `parse_kicad_pcb(pcb/temper.kicad_pcb)` — no new production code path.
- K3-relax: additive `relax_isolator_straddle` param (commit 081834644),
  forwarded through the `isolation_barrier` dict.
- Stage-2 budget: existing `max_displacement_mm` + `minimize_displacement_to`
  bounded-repair machinery — no encoder addition.
- Runners: `docs/evidence/2026-08-01-isolation-barrier-corridor-feasibility.py`
  (matrix, hints, caching) and results JSON
  `docs/evidence/2026-08-01-isolation-barrier-corridor-feasibility.json`.
- Tests: `tests/placer/cp_sat/test_isolation_barrier.py` 38 passed
  (incl. new relax UNSAT→SAT test); import-linter gate: 0 new violations.

## Approximation / tractability notes

- The earlier hint-free X-as-is run returned a 22,355-entry sufficient
  core; hint-warm-started runs return small cores. All reported numbers use
  the hint-warm-started runner.
- An early matrix run had X·k3-relaxed·s1 return UNKNOWN at ~90 s under a
  900 s budget while the sibling (same experiment, same worktree) was
  solving concurrently; a fresh-process re-run was launched to distinguish
  contention/memory from intrinsic intractability. The fresh run's result
  is reported in the table.
- Stage-1 feasible displacement is best-found at the time limit, not
  proven-optimal; the stage-2 verdict does not depend on it (the bound
  question is decided by the budget cells, not the stage-1 objective).

## Budget-floor sweep (straight corridor at the geometric-best position)

Follow-up to the centreline NO-GO: does the straight corridor need a bigger
budget, or a different corridor shape? Ran the straight corridor at the
geometric-best positions from the feasibility evidence (X c=36.25, Y c=127.00,
HV_lo, K3-relaxed), stage-1 and a budget sweep 25/50/100/150 mm.

| Cell (best position) | status | max disp (mm) | witness |
|---|---|---|---|
| X · s1 (no budget) | **infeasible** | — | (geometric best position is NOT solver-feasible in X) |
| X · s2 25/50/100/150 mm | infeasible | — | `edge_margin_*` in core |
| Y · s1 (no budget) | feasible | 329.28 | — |
| Y · s2 25/50/100 mm | infeasible | — | `edge_margin_*` in core |
| Y · s2 150 mm | unknown (timeout 300 s) | — | — |

**Conclusion: the straight-corridor family has no displacement floor below
≈150 mm — moving the corridor to the geometric-best position does not rescue
it.** Even 100 mm is infeasible everywhere; the 150 mm Y cell did not
terminate in 300 s, and a 150 mm cap on a 152 mm board is a full re-layout in
any case. The boundary-following (non-straight, full-height) corridor is
therefore the only path to a within-budget placement — confirming the re-scope
plan (2026-08-01-003) Option 2. Second finding: the geometric minimum-drift
position is not solver-feasible in X, so the probe must search corridor
position, not trust the geometric optimum.

Runs: `docs/evidence/2026-08-01-isolation-barrier-budget-sweep.py`,
results `docs/evidence/2026-08-01-isolation-barrier-budget-sweep.json`.

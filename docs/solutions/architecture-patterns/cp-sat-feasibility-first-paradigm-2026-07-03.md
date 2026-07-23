---
title: "CP-SAT feasibility-first placement solves in 0.1s; wirelength optimization drives the 60s budget"
date: 2026-07-03
last_updated: 2026-07-17
category: architecture-patterns
module: placer/cp_sat
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "Designing CP-SAT models for PCB placement with ~30 components and 5+ hard constraint types"
  - "Choosing between a single combined solve (feasibility + objective) and a two-phase approach"
  - "Evaluating whether hard constraints natively expressed in CP-SAT are cheap enough to make feasibility-first the default strategy"
  - "When the wirelength objective dominates solver time and you want to unblock the pipeline with a feasible placement"
  - "Estimating whether bare CP-SAT (no PCL constraints, no warm-start) will converge on a board with ~150 components"
tags:
  - or-tools
  - cp-sat
  - feasibility-first
  - performance
  - pcb-placement
  - optimization-strategy
  - scaling-limit
---

# CP-SAT feasibility-first placement solves in 0.1s; wirelength optimization drives the 60s budget

## Context

On a real PCB with 33 components and 5 hard constraint types (NoOverlap2D,
Chebyshev clearance, edge anchoring, pairwise proximity, region membership),
running CP-SAT **without an objective** (feasibility only) finds a valid
placement in **0.1 seconds**.  Adding a wirelength optimization objective
drives the solve time to **60 seconds** (hitting the timeout without proving
optimality).  The feasibility solve is **~600× faster** than the optimization solve.

This confirms the feasibility-first paradigm thesis: hard constraints are cheap
when expressed natively in CP-SAT's constraint programming primitives
(NoOverlap2D, `OnlyEnforceIf` disjunctive encoding, linear inequalities).  The
solver's propagation engine handles them efficiently.  The soft objective — a
sum of Manhattan distances plus a bounding-box spread term — transforms the
problem from constraint satisfaction (CSP → easy for CP-SAT) to constrained
optimization (COP → hard for CP-SAT).

## Guidance

**Produce a feasibility-only placement first (instant), then run a separate
follow-up optimization pass to improve wirelength without blocking the placement
pipeline.**

The two-stage approach:

```
Stage 1 — Feasibility (fast path):
  Solve with hard constraints only, NO objective
  Typ. 0.1s for N=33, 5 constraint types
  Output: valid placement suitable for routing

Stage 2 — Optimization (optional slow path):
  Warm-start from the Stage 1 placement
  Add wirelength objective, run with a soft timeout (e.g., 60s)
  Accept best-found solution when time expires
```

Implementation pattern:

```python
# Stage 1: Feasibility-first (near-instant)
feasible_model, ctx = build_cp_sat_model(components, board_w_mm, board_h_mm)
# Add hard constraints only ... no objective set
feasible_result = solve_cp_sat_model(feasible_model, ctx, timeout_s=30.0)

if feasible_result.status not in (OPTIMAL, FEASIBLE):
    return feasible_result  # UNSAT — report core extraction

# Stage 2: Warm-start optimization (time-bounded)
opt_model, opt_ctx = build_cp_sat_model(components, board_w_mm, board_h_mm)
# Add hard constraints AND objective
add_soft_wirelength_objective(opt_model, opt_ctx, net_pairs, ...)
opt_result = solve_cp_sat_model(opt_model, opt_ctx, timeout_s=60.0)

# Return best available result
final_positions = (
    opt_result.positions
    if opt_result.status in (OPTIMAL, FEASIBLE)
    else feasible_result.positions
)
```

## Why This Matters

- **Pipeline latency:** A placement pipeline that must produce output within
  seconds (interactive design tool, CI feedback loop) cannot afford a 60s
  optimization solve on every invocation.  The feasibility-first path gives a
  valid placement in 0.1s.  Optimization becomes a background refinement.
- **Diagnostic clarity:** When a solve fails, the feasibility/optimization split
  immediately tells you whether the problem is over-constrained (Stage 1 fails)
  or just hard to optimize (Stage 1 passes, Stage 2 times out).  This avoids
  the "is it infeasible or just slow?" ambiguity.
- **Robustness:** The optimization pass producing only FEASIBLE (not OPTIMAL)
  is OK — per the plan, "first feasible solution is the target."  The
  objective is a tiebreaker, not a hard requirement.

## When to Apply

Apply the feasibility-first paradigm when:
- The primary requirement is **valid placement** (all hard constraints met) —
  optimization is a secondary concern.
- Hard constraints are **natively expressible** in CP-SAT primitives
  (NoOverlap2D, interval variables, linear inequalities, `OnlyEnforceIf`).
- The objective function involves **sums of non-local terms** (wirelength,
  spread) that drive search complexity.
- The constraints are **dense enough** that feasibility is non-trivial (N≥10
  components, ≥3 constraint types).
- Your pipeline must produce output within **interactive time** (sub-second)
  but can accept best-effort optimization.

Do NOT apply when:
- The model is trivially feasible (e.g., a single component).
- The objective is also expressible as a hard constraint.
- The optimization quality must be **provably optimal**.
- **The board has ~150 components and no real PCL constraints to prune the
  search** — see "Update 2026-07-17" below. The 0.1s figure in this doc's
  headline was measured at N=33 with 5 real constraint types; it does not
  extrapolate to N≈150 with an empty constraint set.

## Update 2026-07-17: feasibility-first does not scale unmodified to the real
## ~150-component board

The 0.1s / 33-component result above was measured against
`pcb/benchmarks/temper_fixture_33.kicad_pcb` — the fixture retired earlier
this arc (still tracked in git as of this update, but structurally inert
per U3's identity gate). Running the same feasibility-first approach
against the real production board
(`pcb/temper.kicad_pcb`, 149 components) for the first time, via the newly
wired `temper-placer optimize --no-loop` CLI path
(`docs/plans/2026-07-17-001-feat-cp-sat-optimize-cli-wiring-plan.md`):

| Test | Timeout | Status | Wall time | Placed |
|---|---|---|---|---|
| Feasibility-only, `extra_constraints=[]` | 1000ms (CLI default) | `unknown` | 1.6s | 0 |
| Feasibility-only, `extra_constraints=[]` | 5000ms | `unknown` | 3.7s | 0 |
| Feasibility-only, `extra_constraints=[]` | 15000ms | `unknown` | 15.6s | 0 |

Bumping the timeout 15× did not change the outcome — this is not a timeout
tuning problem. Two candidate explanations, not yet distinguished:

1. **No PCL constraints were loaded.** `configs/temper_production_config.yaml`
   (the deterministic-pipeline config authored for U6) has no top-level
   `constraints:` block, so `load_constraints()` correctly returns an empty
   `pcl_constraints` list — this isn't a bug, that config was never meant to
   carry PCL constraints. The only PCL file that exists,
   `packages/temper-placer/configs/pcl/temper_induction.yaml`, is itself
   fixture-era (`Q1`, `Q2`, `U_GATE` refs — the same fixture-ref-naming
   problem documented throughout `docs/solutions/logic-errors/` this arc)
   and would not match the real board's refs either. **There is currently
   no real PCL constraints file authored for the production board.**
2. **Scale itself.** This doc's own "When to Apply" section already implied
   an upper bound was untested — the benchmark table only ever validated
   N=33. 149 components is ~4.5× that, well past the "N≥10, ≥3 constraint
   types" lower-bound guidance this doc gives, but with *zero* upper bound
   ever measured. It's possible bare CP-SAT (no constraints, no warm-start,
   no zone/slot decomposition) simply doesn't scale to this board size
   regardless of constraint richness — which would explain why the
   deterministic pipeline (zone-aware slot generation + greedy assignment,
   *not* CP-SAT) is the pipeline that actually produces 149/149 placements
   for this board today, in 2.4s, per
   `power_pcb_dataset/baselines/temper_production_baseline.yaml`.

**Resolved 2026-07-17, same day:** authored a real PCL constraints file
against the production board's verified current refs
(`packages/temper-placer/configs/pcl/temper_production.yaml` — 12
constraints across 4 types: `adjacent` for commutation/gate-drive loop
tightness, `separated` for HV/LV creepage matching `constraints.ato`'s
`HV_to_LV` spec exactly, `on_side` for MCU antenna clearance and mains
entry, `anchored` for MCU zone containment) plus the same HV/Power/Signal/
MCU zone floorplan `configs/temper_production_config.yaml` uses. Re-ran
`solve_placement()` with these 12 real constraints loaded:

| Test | Timeout | Status | Wall time | Placed |
|---|---|---|---|---|
| With 12 real PCL constraints + zones | 5000ms | `unknown` | 3.7s | 0 |
| With 12 real PCL constraints + zones | 15000ms | `unknown` | 15.6s | 0 |

**Identical outcome to the unconstrained run.** This decisively rules out
explanation (1) — missing constraints was not the cause. **(2) holds:**
bare `solve_placement()` (feasibility-only, no warm-start, no
decomposition, single monolithic CP-SAT model) does not converge on a
149-component board within any timeout tested (1s/5s/15s), with or
without real domain constraints. This is a genuine scale wall for the
approach as currently implemented, not a constraint-authoring gap.

**Conclusion for future work:** CP-SAT-only placement via
`temper-placer optimize --no-loop` should be treated as validated only up
to the scale actually tested (~33 components, per this doc's original
benchmark) until someone adds warm-starting (e.g., seed the model from the
deterministic pipeline's already-working 149/149 placement) or
decomposition (solve zone-by-zone rather than the whole board as one
model) — both are real, separate engineering efforts, not configuration.
The deterministic pipeline (zone-aware slot generation + greedy
assignment) remains the board's actual production placement path; it
produces 149/149 in 2.4s today with no scale wall observed.

## Update 2026-07-17 (later same day): warm-start was tried — a real
## seeding bug was found and fixed, but the underlying hypothesis is now
## also settled negative

`--warm-start` landed on `feat/warm-start-cli`, seeding CP-SAT via
`AddHint()` with positions from a deterministic-pipeline pre-solve. Two
things needed independent verification before trusting the result, per
this doc's own established pattern of not trusting a "did it work" claim
without running it:

**1. The warm-start CLI had a real seeding bug (found, root-caused).** It
reuses whatever `-c` config was passed for CP-SAT's PCL constraints as the
config for the deterministic-pipeline warm-start pass too. A CP-SAT-
oriented PCL file (`configs/pcl/temper_production.yaml` — zones +
constraints, no `fixed_positions`/`slot_generation`) starves the
deterministic pipeline down to **13 of 149** placements when reused this
way — the same "no fixed_positions means the big parts' reservation
circles consume nearly all slots" failure mode this arc found and fixed
for the *main* deterministic config days earlier. Confirmed directly: the
same board + the full, tuned `configs/temper_production_config.yaml`
places 149/149; the CP-SAT-only PCL file places 13/149. **The CLI's
`--warm-start` flag has never yet produced a real, complete hint set in
practice** — every run so far seeded from an accidentally-starved
13-component partial placement.

**2. Re-ran the actual experiment properly** — a genuine 149/149 seed
(from the tuned deterministic config) *and* the 12 real PCL constraints,
passed to `solve_placement(hint_positions=..., extra_constraints=...)`
directly:

| Test | Timeout | Status | Wall time | Placed |
|---|---|---|---|---|
| Full 149/149 seed + 12 real constraints | 5000ms | `unknown` | 3.7s | 0 |
| Full 149/149 seed + 12 real constraints | 15000ms | `unknown` | 15.6s | 0 |

**Identical to every unseeded run.** Even a complete, genuinely-feasible
warm-start hint produces no observable improvement in convergence.
`AddHint()` is documented by OR-Tools as a soft suggestion the solver may
use to construct an initial incumbent — it does not appear to be enough
on its own to get this model to CERTIFY feasibility within any timeout
tested. Two untested follow-on hypotheses, not yet distinguished: (a) the
hint isn't surviving translation into the solver's exact internal
constraint encoding (a units/coordinate mismatch would cause CP-SAT to
treat a "valid" hint as just another guess), or (b) `AddHint()` alone
genuinely isn't sufficient at this scale and true decomposition (solving
zone-by-zone, never building one 149-component model) is required. Not
investigated further this session — a real follow-up if CP-SAT placement
for boards this size is still wanted.

**Revised conclusion:** warm-starting via `AddHint()`, as currently wired,
does not solve the scale-wall problem documented above. The deterministic
pipeline remains the only proven path to a full placement for this board.

## Examples

### Comparison from temper board validation

| Test | Status | Time | Outcome |
|---|---|---|---|
| Feasibility-only (no objective) | OPTIMAL | **0.1s** | 33/33 components placed |
| With wirelength objective | FEASIBLE | **60.0s** (timeout) | Objective=2425, optimality not proven |

Constraint audit: 652/652 checks passed — no violations across all 5 constraint types.

### Feasibility-only solve with constraint audit

```python
model, ctx = build_cp_sat_model(components, board_w_mm=100, board_h_mm=150)
add_chebyshev_clearance(model, ctx, hv_lv_pairs, clearance_mm=8.5)
add_edge_anchoring(model, ctx, ["J_AC", "J_COIL"], max_dist_mm=5, edge="left")
add_proximity(model, ctx, [("Q1", "Q2", 10.0)])
add_region_membership(model, ctx, ["Q1", "Q2", "D1", "C_DC"],
                      region_x_min_mm=0, region_x_max_mm=50,
                      region_y_min_mm=0, region_y_max_mm=80, margin_mm=2)

result = solve_cp_sat_model(model, ctx, timeout_s=30)  # 0.1s
audit = audit_placement(result.positions, components, constraints)
assert audit.passed, f"Failed audit: {audit.violations}"
```

## Related

- `docs/solutions/architecture-patterns/alternating-projections-constraint-feasibility-optimization-init-2026-07-01.md` —
  C-CAP was the previous feasibility-first attempt (v2); CP-SAT is v3
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` —
  constraint solver audit pattern applied here
- `docs/solutions/best-practices/bmc-induction-ladder-constraint-verification-2026-07-01.md` —
  verification infrastructure for constraint encodings
- `docs/reports/2026-07-03-cp-sat-feasibility-first-placer-implementation-report.md` —
  full implementation report with parity gate status

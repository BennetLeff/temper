---
date: 2026-07-03
topic: cp-sat-feasibility-first-placer-paradigm-swap
---

# CP-SAT Feasibility-First Placer (Paradigm Swap from JAX Descent)

## Summary

Replace the JAX gradient-descent placement engine with a constraint-programming feasibility-first placer (Google OR-Tools CP-SAT, with Z3 as an evaluated alternative). Hard electrical/geometric constraints (no-overlap, HV↔LV 6mm creepage, thermal-edge anchoring, commutation-loop adjacency, HV-region membership) become true feasibility constraints; wirelength/spread becomes a soft CP-SAT objective as tiebreaker. The entire JAX descent stack — C-CAP feasibility projector, weighted penalty losses, weight-tuning, multi-seed/DPP triage, and the gradient optimizer itself — retires. `router_v6`, the physics oracle (with the in-flight dual-rail clearance metric), and the PCL spec survive as the acceptance gate and constraint source.

---

## Problem Frame

For three development cycles the temper placer has fought optimizer pathologies: local minima, brittle weight ratios (thermal=4000 vs overlap=200, a 20:1 ratio), gradient vanishing at coincidence, the need for a C-CAP feasibility projector, and the need for multi-seed runs to escape basins. Individually each looked like a tuning problem; collectively they share one root cause — hard electrical/geometric constraints are being forced through a soft continuous relaxation as weighted penalties.

Differentiable placement (DREAMPlace, Google chip floorplanning) exists for scale: ~10M cells where combinatorial methods die and gradients on GPU are the only tractable option. The temper board is N≈33. At that scale none of the conditions that make the differentiable paradigm necessary hold, and all of the conditions that make it a poor fit do:

- **Small N** — combinatorial/exact methods are feasible and better (feasibility guarantees, no seeds, no weights).
- **Hard constraints** — "no overlap" and "6mm HV creepage" are not soft preferences tradeable at some magic weight. Encoding a hard constraint as a weighted penalty is the original sin that creates the weight-tuning nightmare: there is no weight that makes a penalty act like a constraint, because a penalty is never a constraint.
- **Rich domain knowledge** — the commutation loop (C_BUS→Q1→Q2→C_BUS) must be tight; HV segregated to one region; Q1/Q2 on the thermal edge; gate driver next to the gate pin. That's a template with a few free parameters, not an open search problem.

Gradient descent is objective-first with constraints bolted on as penalties. This problem is feasibility-first with a mild objective as tiebreaker. Forcing the natural structure through the inverted paradigm is why C-CAP-then-descent felt like swimming upstream — descend, project back to feasible, descent pulls you off feasible again.

The active `2026-07-02-001` experiment (C-CAP-on + corrected dual-rail metric + 10 seeds, pre-registered DISSOLVED/HOLDS/INCONCLUSIVE verdict) was designed to determine whether the JAX pathologies are real or confound artifacts. This brainstorm takes the structural decision without waiting on that verdict: the paradigm is wrong-fit independent of any one empirical result, so the swap proceeds.

---

## Actors

- A1. **CP-SAT placer engine**: OR-Tools CP-SAT model that produces feasible placements satisfying hard constraints, with soft objective (wirelength/spread) as tiebreaker.
- A2. **PCL constraint compiler**: existing PCL spec → CP-SAT constraint encoder (replaces the PCL → JAX-loss compilation path).
- A3. **Physics oracle**: existing dual-rail clearance + thermal scorer; demoted from loss-component to acceptance gate, unchanged in role.
- A4. **router_v6**: existing A* router; unchanged, scores placements via routability/closure post-placement.
- A5. **Standalone Z3 verification gate** (from `2026-07-01-z3-smt-preplacement-verification-requirements.md`): optional post-placement exact-arithmetic certification of CP-SAT output.

---

## Key Flows

- F1. **Placement (the new engine)**
  - **Trigger:** `temper optimize` invocation with CP-SAT placer selected.
  - **Actors:** A1, A2
  - **Steps:** Load PCL + netlist + board geometry; compile PCL hard constraints to CP-SAT `NoOverlap2D` + side constraints (HV↔LV clearance, thermal edge, commutation adjacency, region membership); add soft wirelength/spread objective; solve; emit feasible placement or UNSAT report.
  - **Outcome:** Either a placement satisfying all hard constraints with optimized tiebreaker, or a provable infeasibility certificate naming the conflicting constraint set.
  - **Covered by:** R1, R2, R3, R4, R5

- F2. **Place-then-route acceptance**
  - **Trigger:** CP-SAT placement produced.
  - **Actors:** A3, A4
  - **Steps:** Run router_v6 on the placement; score via physics oracle (dual-rail clearance, thermal, routability/closure); optionally verify exact compliance via the standalone Z3 gate (A5).
  - **Outcome:** A placement+routing scored on the same oracle as the retired JAX pipeline; pass/fail against the same acceptance bar.
  - **Covered by:** R6, R7

- F3. **UNSAT handling**
  - **Trigger:** CP-SAT returns infeasible on the hard constraint set.
  - **Actors:** A1, A2
  - **Steps:** Emit the unsat-core (minimal conflicting constraint subset); surface as a design finding — "these constraints cannot all be satisfied on this outline," which no penalty optimizer would have reported cleanly (it would have silently compromised).
  - **Outcome:** Either the designer relaxes a constraint and re-solves, or accepts that the outline is electrically infeasible.
  - **Covered by:** R8

---

## Requirements

**[Hard constraint encoding]**
- R1. **Pairwise non-overlap** as CP-SAT `NoOverlap2D` over component bounding boxes on an integer grid (mm × scale factor). Irregular outlines (thermal pads, non-rectangular copper) are decomposed to rectangle unions; the decomposition is conservative (union ⊇ true outline).
- R2. **HV↔LV creepage clearance (6.0mm DRC rail)** as a disjunctive spacing constraint: for every HV-LV pair, edge-to-edge clearance ≥ 6.0mm in at least one axis (Chebyshev), or the pair is separated by a guard strip / region boundary. Chebyshev is the v1 metric; Euclidean spacing (NRA) is deferred.
- R3. **Thermal-edge anchoring**: Q1, Q2, and heatsink-thermally-coupled parts are constrained to within Xmm of the bottom board edge (X from PCL).
- R4. **Commutation-loop adjacency**: the C_BUS→Q1→Q2→C_BUS loop parts are mutually adjacent (pairwise edge-to-edge ≤ Ymm), encoding the known loop-tightness requirement as a hard constraint rather than a loop-area penalty.
- R5. **HV-region membership**: HV-tagged components are constrained inside the HV region; LV-tagged outside it. Region boundary is a PCL-defined rectangle.

**[Soft objective]**
- R6. **Wirelength/spread as CP-SAT objective** (tiebreaker only): minimize total manhattan wirelength + a spread regularizer, subject to all hard constraints. The objective can only reorder within the feasible set; it can never produce a placement that violates a hard constraint.

**[Integration / acceptance]**
- R7. **Output is scored on the existing physics oracle** (dual-rail clearance, thermal) and router_v6 (routability/closure), against the same acceptance bar as the retired JAX pipeline. The oracle is not modified to favor CP-SAT; it is the same gate.
- R8. **UNSAT is a first-class output, not a failure mode**: the placer reports the minimal conflicting constraint set (CP-SAT unsat-core or Z3 unsat-core) and exits cleanly. The designer decides whether to relax a constraint or redesign the outline.

**[Retirement of JAX placement stack]**
- R9. **Retire**: `optimizer/ccap.py`, the weighted-loss modules (`losses/*` as used by placement), `train_multiphase` descent, `train_dpp_multiseed`, `MultiSeedConfig`, the constraint-weight sweep/search tooling, and `gradnorm.py` as it applies to placement. These are **deleted outright** (no `--legacy-jax` flag, no permanent archive) — but only after the experimentation phase completes: the in-flight `2026-07-02-001` multi-seed JAX experiment runs to completion as an informational backstop, AND CP-SAT placements match-or-beat JAX on the oracle for the temper board. Deletion is gated on both.
- R10. **Survive**: `router_v6` and its pipeline, the physics oracle + dual-rail metric, the PCL spec and its compiler infrastructure, the KiCad DRC cross-check, and the standalone Z3 verification gate (`2026-07-01-z3-smt-preplacement-verification-requirements.md`). The Z3 gate becomes a natural post-placement certifier of CP-SAT output.

**[Strangler cutover]**
- R11. CP-SAT placer runs ** alongside** the JAX pipeline (feature-flagged) until it produces a temper-board placement scoring ≥ the JAX baseline's best on the physics oracle. Cutover retires JAX per R9; until then both run and neither is deleted.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R6.** Given the temper board's 33 parts and PCL constraints, when the CP-SAT placer solves, it produces a placement with zero overlap and zero HV↔LV pairs below 6.0mm, and the soft wirelength objective is ≤ the JAX baseline's wirelength on the same netlist.
- AE2. **Covers R7.** Given a CP-SAT placement, running the existing physics oracle + router_v6 produces dual-rail clearance and thermal scores comparable to the JAX baseline's best corrected run (C-CAP on, multi-seed), with no oracle modification.
- AE3. **Covers R8.** Given a deliberately infeasible constraint set (HV region area < sum of HV part footprints), the CP-SAT placer returns UNSAT within minutes and reports the minimal conflicting subset (e.g., "HV-region rectangle + Q1 footprint + Q2 footprint exceed region area"), rather than running for hours and silently compromising.
- AE4. **Covers R9, R11.** After CP-SAT matches-or-beats JAX on the oracle for the temper board, the JAX descent stack is removed (or archived behind `--legacy-jax`); the pipeline runs CP-SAT as the default placer; CI passes.
- AE5. **Covers R3, R4.** Given the temper board, the CP-SAT placement has Q1 and Q2 within Xmm of the bottom edge AND the commutation-loop parts mutually adjacent within Ymm — as hard constraints, not weighted penalties. No weight tuning was performed to achieve this.

---

## Success Criteria

- A temper-board placement exists that satisfies all hard electrical/geometric constraints with zero violations, produced without weight tuning, without seed sweeps, and without the local-minima/fighting-the-optimizer experience that characterized the JAX cycles.
- The same placement passes the existing physics oracle and router_v6 at scores ≥ the best corrected JAX baseline — the paradigm swap is not a quality regression.
- An infeasible constraint set is reportable as a clean design finding (named conflicting constraints) rather than a silent compromise — a capability the JAX penalty architecture could never provide.
- A downstream planner/implementer can take this doc and scope the CP-SAT model, the PCL→CP-SAT encoder, and the JAX retirement cutover without inventing product behavior or scope boundaries.

---

## Scope Boundaries

- **Euclidean (NRA) spacing deferred to v2** — v1 uses Chebyshev edge-to-edge spacing (QF_LRA-friendly); Euclidean center-to-center distance (Z3 NRA, orders of magnitude slower) is a follow-up.
- **CP-SAT-internal routability not in v1** — placements are scored by router_v6 post-placement; routability does not enter CP-SAT as a constraint or objective in v1. Revisit only if feasible placements don't route.
- **Rotation as a first-class variable deferred** — v1 treats rotations as a small enumerated set (0°/90°/180°/270°) if needed for specific parts; free-angle rotation is v2.
- **Pin-level alignment as hard constraint deferred** — gate-driver-to-gate-pin fine alignment is a follow-up; v1 places at bounding-box/component level.
- **Multiple power boards / design-space exploration is explicitly out of scope** — the differentiable paradigm would earn its complexity back at scale; this swap is for the single temper board. If the project later scales to many boards or hundreds of parts, revisit the paradigm decision holistically.
- **The `2026-07-02-001` in-flight JAX experiment is moot as a decision tool** — its verdict would not change the swap. The experiment nonetheless runs to completion as an informational backstop (per Key Decisions); JAX deletion is gated on its completion AND CP-SAT matching-or-beating on the oracle.

### Outside this product's identity

- **General-purpose differentiable placement research** — the JAX stack is not being retained as a research platform; it retires.
- **A unified " placer interface" abstraction over CP-SAT and JAX** — premature; one placer is enough until scale demands otherwise.

---

## Key Decisions

- **Feasibility-first over objective-first** — dissolves the weight-tuning pathology by construction; hard constraints become hard. Trades the risk that a hard-constraint encoding returns UNSAT (a design finding) for the JAX penalty architecture's silent-compromise failure mode. The UNSAT case is strictly more informative.
- **Full JAX retirement over keep-descent-with-C-CAP** — the argument's own logic implied C-CAP-as-solver + drop-the-descent, but the chosen scope is the cleaner break: CP-SAT is the placer, C-CAP's Dykstra projections don't carry over. Rationale: the cleanest paradigm break is easier to reason about than a hybrid; the C-CAP-vs-CP-SAT comparison would have been a third paradigm to maintain.
- **CP-SAT primary, Z3 evaluated-not-primary** — CP-SAT's `NoOverlap2D` global constraint is purpose-built for rectangle packing under side constraints; Z3 SMT is more general but typically slower on pure packing. Z3 remains the right tool for the existing *standalone verification gate* (exact arithmetic, post-placement cert). The evaluation between them for the primary engine is a planning-time decision, not a brainstorm decision.
- **Strangler cutover (R11) despite "full swap" intent** — retire JAX only after CP-SAT matches-or-beats it on the oracle, running alongside JAX (feature-flagged) until then. This is operational hygiene, not hedging on the paradigm; it protects the project from a CP-SAT model that proves harder to encode than expected.
- **Experimentation phase precedes deletion** — the in-flight `2026-07-02-001` multi-seed JAX experiment is *not* retired outright; it runs to completion as an informational backstop (buyer's-remorse insurance: if CP-SAT unexpectedly underperforms, the experiment's verdict tells us whether JAX-with-fixes would have been enough on its own). JAX deletion is gated on BOTH the experiment completing AND CP-SAT matching-or-beating on the oracle. After both, the JAX stack is deleted outright — no `--legacy-jax` flag, no permanent archive. The flag lifetime question is settled: zero releases.
- **Penalty weights, multi-seed, gradient vanishing, local minima are not problems in this framing** — they are artifacts of the soft-relaxation paradigm. The doc does not propose fixes for them; it proposes to remove the paradigm that generates them.

---

## Dependencies / Assumptions

- **OR-Tools CP-SAT is installable** in the temper-placer environment (Python wheel; macOS/Linux/CI container support). [Unverified against repo — planning must confirm no platform blocker.]
- **The existing PCL spec covers the hard constraints this doc encodes** — non-overlap, HV↔LV clearance, thermal edge, commutation adjacency, region membership. A repo scan confirms PCL expresses keepout zones, Chebyshev spacing, and tag-based group constraints (per `packages/temper-placer/docs/PCL_REFERENCE.md`); commutation-loop-adjacency as a *hard pairwise* constraint may need a new PCL construct. [Affects R4 — planning must verify or add the adjacency construct.]
- **The argument's claim of "existing SAT infrastructure (temper-constraints)" is wrong** — `packages/temper-placer/temper-constraints/` is a Rust *loss-computation* engine (`loss.rs`, `constraints.rs`), not a SAT solver. The grep for `sat|z3|bmc|cnf` across the crate returns zero matches. This brainstorm ships the first real CP-SAT/Z3 use in the repo; planning must treat the CP-SAT path as **net-new infrastructure**, not reuse, and budget accordingly. [Material to scope: the "concretely, mostly with tools you already have" framing from the originating argument is incorrect on this point.]
- **The dual-rail clearance metric from the in-flight `2026-07-02-001` plan is the scorer** — the CP-SAT placement is evaluated on the corrected 3mm/6mm metric regardless of whether the full 10-seed JAX experiment runs. The metric work (U1/U2/U3 in that plan) is a hard dependency for the acceptance gate; the 10-seed sweep (U5) is not.
- **Irregular outlines decompose to rectangle unions conservatively** — conservative decomposition (union ⊇ true outline) may over-constrain clearance slightly; acceptable for a feasibility-first placer but must be quantified in planning.
- **CP-SAT `NoOverlap2D` assumes rectangles on an integer grid** — mm coordinates must be scaled to integers; grid choice (e.g., 0.1mm = 1 unit) affects both solve time and placement precision. Planning must choose the grid and document the precision/throughput tradeoff.

---

## Outstanding Questions

### Resolve Before Planning

_None — both previously-open user decisions are now resolved (see Key Decisions: "Experimentation phase precedes deletion")._

### Deferred to Planning

- [Affects R1, R6][Technical] Integer grid scale (0.1mm? 0.01mm?) and its impact on CP-SAT solve time vs placement precision — needs measurement on the temper board.
- [Affects R2][Technical] Chebyshev edge-to-edge vs Euclidean center-to-center spacing — confirm Chebyshev satisfies the 6.0mm DRC rule interpretation the netclass uses; if the DRC rules check Euclidean, v1's Chebyshev encoding is conservative-but-correct only if Chebyshev ≥ Euclidean at equal threshold (it is not; Chebyshev is the larger). Resolve during planning against the actual DRC rule.
- [Affects R4][Needs research] Whether PCL needs a new `adjacency` construct to express commutation-loop mutual adjacency as a hard pairwise constraint, or whether it composes from existing spacing-reversed constraints.
- [Affects R1][Technical] Conservative rectangle-union decomposition of irregular outlines — quantify the over-constrained area and confirm it doesn't make feasible placements infeasible.
- [Affects A1][User decision] CP-SAT (OR-Tools) vs Z3-SMT as the primary engine — both are viable; the brainstorm recommends CP-SAT for `NoOverlap2D` fit but defers the final call to planning after a small spike on the temper board.
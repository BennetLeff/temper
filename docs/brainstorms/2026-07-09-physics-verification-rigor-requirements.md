---
date: "2026-07-09"
topic: physics-verification-rigor
status: requirements
tier: deep-feature
relationship: "Hardens the physics-informed placement/routing feature (docs/plans/2026-07-08-008-...). Adds a reusable verification methodology, fixes two soundness gaps found in review, and instantiates per-unit invariant batteries across U1-U9."
---

# Physics Verification Rigor: Invariants, Induction, and Property-Based Testing for the Physics Feature

## Summary

Lay a reusable verification methodology over the physics-informed placement/routing feature — a four-layer testing pattern (fuzz → domain invariant → independent oracle → composition) plus a BMC-exhaustive / k-induction ladder — and instantiate it as concrete invariant batteries on the already-merged units (U1-U9). The effort also fixes two design-level soundness gaps the review surfaced: U6's endpoint-only bounding and U7's scorer that isn't genuinely independent of the solver it scores.

---

## Problem Frame

This project's recurring, expensive failure is a green signal that measured a model instead of reality — the 121→0 default-clearance miss, the weak-NoOverlap2D shorts that passed every model-level check, the dark metrics that A/B'd to zero effect, the single-seed results error. The physics feature was built specifically to resist that failure mode, yet its own test suite is largely example-based: it checks a handful of scripted scenarios and leaves the *mathematical structure* of the physics — conservation, monotonicity, solver well-posedness, search optimality, loop termination, verdict totality — unexploited.

Two consequences follow. First, whole classes of bug (sign errors in the Laplacian assembly, off-by-one indexing, cost double-counting, counter-coupling in the loop, threshold-comparison errors in the verdict) can pass the shipped tests while producing a physical-looking-but-wrong result. Second, the review already found two errors that are not missing tests but *unsound design*: U6 bounds the operating point from only its two coupling endpoints (valid only if the function is monotone in coupling), and U7 — the "independent instrument" the entire keep/kill verdict rests on — shares U5's discretization, so its agreement with U5 confirms the linear solve rather than the physics. On a mains board that no simulation may sign off to energize, a false-green here is the most dangerous outcome the pipeline can produce.

---

## Actors

- A1. Placer developer: changes a physics unit and needs invariants that fail loudly on a regression rather than silently degrading a field.
- A2. Verdict consumer / reviewer: trusts a KEEP/KILL verdict only if the independent instrument (H6) is genuinely sound.
- A3. CI gates: run the PBT / BMC batteries on every change and block on failure.
- A4. Future physics units (EMI, current-density, coupling fields): inherit the reusable methodology instead of re-deriving verification per field.

---

## Key Flows

- F1. Verify a unit (the four-layer ladder)
  - **Trigger:** a physics unit is added or changed.
  - **Actors:** A1, A3
  - **Steps:** (1) fuzz for no-crash over generated inputs; (2) assert domain-correctness invariants (conservation, monotonicity, well-posedness); (3) cross-validate against an independent-method oracle on the same objective; (4) assert the properties survive composition (e.g., field-on routing still respects hard masks).
  - **Outcome:** the unit is covered at all four layers; any layer can fail on a real bug.
  - **Covered by:** R1, R3, R4

- F2. Prove a bounded-then-unbounded property (BMC + k-induction)
  - **Trigger:** a constraint or termination property must hold for all sizes, not just sampled ones.
  - **Actors:** A1, A3
  - **Steps:** exhaustively enumerate all inputs up to a bounded N (BMC); establish an inductive step to extend to unbounded N; use PBT to cover the vast middle between the exhaustive floor and the inductive argument.
  - **Outcome:** a property proven for small N by exhaustion, argued for all N by induction, and fuzzed in between.
  - **Covered by:** R2, R13, R15

---

## Requirements

At-a-glance map (detail in the grouped R-IDs below):

| Unit | Invariant class | Primary technique | Bug class caught |
|------|-----------------|-------------------|------------------|
| U5 thermal FDM | energy conservation, M-matrix monotonicity, max principle, SPD, order-of-accuracy, symmetry | invariants + refinement induction + metamorphic PBT | sign/assembly errors, BC bugs, indexing/orientation |
| U6 op-point gate | monotone-in-coupling bounding soundness | proof/guard + interval sampling | unsound endpoint bounding (false CLEAN) |
| U7 scorer | genuine method independence + falsifiability | structural-independence fix + oracle | fake H6 independence (verdict untrustworthy) |
| U8 A* injection | admissibility/optimality, cost additivity | Dijkstra same-cost oracle (BMC + PBT) | suboptimal paths, cost double-counting |
| U9 W5 loop | termination, counter invariants, idempotence | ranking function / BMC+induction + stateful PBT | non-termination, counter coupling, field-off regression |
| U1-U4, U3 | fail-closed sum type, verdict totality/monotonicity, guard totality, ordering | property + fuzz PBT | wrong verdict, self-scoring, false-zero, fail-closed bypass |

**Reusable verification methodology**
- R1. A documented four-layer verification pattern — fuzz (no-crash), domain invariant, independent-method oracle, property-preservation-under-composition — that each physics unit's suite instantiates.
- R2. A BMC-exhaustive + k-induction ladder pattern: exhaustively verify all inputs up to a bounded N, give an inductive step for unbounded N, and PBT the middle.
- R3. The independent-oracle rule: any cross-validator optimizes the SAME objective via an INDEPENDENT method/code path (Dijkstra for A*, a structurally different solver for the thermal field). A same-model reference or a different-objective oracle (e.g., BFS hop-count vs octile A*) does not count.
- R4. Every new invariant or metric must be demonstrably fail-capable — shown to produce a failing value on a constructed input — before it may gate. (The anti-false-zero / dark-metric discipline.)

**Correctness fixes (behavior changes — each needs its own verification)**
- R5. U6 bounding must be sound. Establish that the operating point is monotone in the coupling coefficient over its range; if it is not provably monotone, the gate samples the interior (or uses interval arithmetic) so the reported worst case genuinely bounds all interior coupling values. Endpoints-only is forbidden unless monotonicity is proven.
- R6. U7 must be genuinely independent of U5. The scorer uses a different discretization or a structurally different method (e.g., stochastic random-walk Monte-Carlo, or analytic Green's-function superposition) — not the same 5-point stencil solved by a different linear method — so U5↔U7 agreement tests the physical model, not the solver. The oracle must document which physical-model assumptions it *shares* with U5 (effective interface conductivity, conduction-only / no convection, vias-as-bulk) versus which are independent, and where feasible adopt a qualitatively different physical model (e.g., a convective boundary term U5 omits). Shared systematic bias that both methods carry is a stated limitation the falsifiability test cannot rule out. Until R6 holds, the keep/kill verdict (U3/U10) is labeled provisional.

**Thermal solver invariants (U5)**
- R7. Energy/flux conservation: total injected power equals the heat flux leaving the Dirichlet boundary, within solver tolerance.
- R8. Monotonicity in sources: if Q1 ≤ Q2 elementwise then T1 ≤ T2 elementwise (M-matrix property).
- R9. Discrete maximum principle: with all sources heating and a single cold Dirichlet edge, no interior cell is colder than ambient, and the peak is bounded by a function of total power and conductance.
- R10. Well-posedness: the assembled system matrix is symmetric positive-definite (unique, stable solution) — which additionally guarantees the U7 iterative scorer converges.
- R11. Order-of-accuracy refinement ladder: halving grid spacing reduces error against the analytic solution by ~4× (2nd-order consistency), upgrading K1 from a single point check to a convergence-rate check.
- R12. Metamorphic symmetry: translating, reflecting, or rotating a symmetric board translates/reflects/rotates the field identically (catches x/y-swap, row/column-major, and origin-offset indexing bugs).

**Routing-search invariants (U8)**
- R13. Optimality under the additive field: the octile heuristic stays admissible with nonnegative field costs, and A*-with-field path cost equals Dijkstra-with-field on the same weighted grid — BMC-exhaustive over all source/target pairs on small grids, PBT above.
- R14. Cost additivity: path-cost(field) − path-cost(no-field) equals the summed field cost over the traversed cells (no double-counting, no off-by-one).

**Loop invariants (U9)**
- R15. Termination: the fixed-point loop halts for every round-outcome sequence, proven via a bounded ranking function or via BMC over bounded round sequences plus k-induction; the drift-exit, long-cycle-exit, and round-budget-exit partition the sequence space. If neither a ranking function nor tractable BMC+k-induction proves out for the actual loop (no monotone measure exists, or the state space exceeds BMC capacity), the loop is restructured into a provably-terminating form — a fixed maximum-iteration bound, with convergence detection kept as an optimization rather than a correctness requirement — before this gate is considered satisfied.
- R16. Counter invariant under all transitions: the field-stability counter and the gate-stability counters never corrupt each other, and convergence holds iff all counters simultaneously reach STABILITY_ROUNDS — verified with stateful (rule-based) PBT driving random per-round outcomes.
- R17. Field-off idempotence: with the field disabled, the loop is behaviorally identical to the legacy place→route loop.

**Contract & verdict invariants (U1-U4, U3)**
- R18. Verdict totality & monotonicity: the keep/kill/inconclusive map is total (exactly one outcome per input) and monotone (improving the physics-arm margin never moves the verdict away from KEEP); over-budget dominates to INCONCLUSIVE; the KILL region is provably nonempty.
- R19. Independence-guard totality: for every scorer/field pair where the scorer is (or wraps) the field, the scorecard's independence guard raises.
- R20. Fail-closed sum-type invariant: across all construction paths, UNMEASURED ⟺ no grid and CLEAN/VIOLATIONS ⟺ grid present; the grid↔flat conversion is a round-trip identity.
- R21. Pre-registration ordering & completeness: created_at strictly precedes any run timestamp, and incomplete records are rejected — fuzzed over generated records.

**Discipline**
- R22. The batteries must be capable of catching latent bugs in the already-merged U5-U9. Bugs an invariant surfaces are triaged, not blanket-fixed: trivial fixes (sign errors, off-by-one, indexing, boundary-condition swaps) are in-scope; a bug requiring architectural redesign is documented and scoped as separate follow-up work. This preserves the verification's value (finding the bugs) without binding the effort to unbounded remediation.
- R23. Matrix-class precondition for R7-R10: before the U5 solver invariants are implemented, confirm on the *shipped* stencil — via a small eigenvalue and sign-pattern check — that it actually yields a symmetric positive-definite M-matrix. If anisotropic conductivity or a stencil variant breaks that property, reformulate R7-R10 for the actual matrix class (e.g., M-matrix → diagonally dominant, SPD → positive-stable) rather than relaxing the invariants until they pass on possibly-wrong code.
- R24. (Forward-looking) Any future hard CP-SAT physics constraint carries a Chebyshev-style soundness proof + BMC-exhaustive small-N verification + post-solve audit before it may gate.

---

## Acceptance Examples

- AE1. **Covers R8.** Given a solved board, when the power at any cell is increased, every cell's temperature is greater than or equal to its prior value.
- AE2. **Covers R7.** Given a steady-state solve, when total injected power is compared to the boundary flux, they match within solver tolerance.
- AE3. **Covers R13.** Given a grid with a hot region, when A* routes with the field enabled, its path cost equals Dijkstra's cost on the same weighted grid.
- AE4. **Covers R15.** Given a field sequence that drifts monotonically without stabilizing, when the loop runs, it exits on the field round budget rather than looping forever.
- AE5. **Covers R18.** Given arm scores where the cheap heuristic captures the benefit, when the verdict is computed, it returns KILL.
- AE6. **Covers R5.** Given an operating-point function that is non-monotone in coupling with an interior violation, when the gate evaluates it, it must not report CLEAN.
- AE7. **Covers R20.** Given an UNMEASURED field result, when it is constructed, it cannot carry a grid, and no code path can coerce it to a flat/zero field.

---

## Success Criteria

- A wrong field, wrong operating point, or wrong verdict caused by a *solver, assembly, integration, or termination* bug is caught by a failing invariant or oracle before it can ship a false-green — the model-level map-vs-territory failure is closed. (Physical correspondence — whether the model itself matches reality — is a separate gap; see Scope Boundaries.)
- Every new invariant and metric is demonstrated fail-capable, and every cross-validator uses a genuinely independent method (R3, R4).
- The keep/kill verdict is trustworthy because H6 independence is real (R6): a KEEP means the field helped by an independent measure, not by a co-modeled one.
- Downstream handoff: ce-plan can sequence the work directly from the R-IDs, with the correctness fixes (R5, R6) and core invariants (R7, R13, R15) as the AND-gated soundness set — R6 flagged to sequence early for its lead time, not because the others are secondary.

---

## Scope Boundaries

- Running the real thermal helps-battery A/B against a golden board (the U10 experiment) — separate follow-up.
- **Physical validation of the model against reality is out of scope and complementary, not delivered here.** Every invariant, oracle, PBT, and BMC check in this doc verifies *internal model consistency* (no solver/assembly/termination bugs); none confirms the thermal model matches a real board. Closing the true map-vs-territory gap requires hardware validation — thermocouple/IR measurement on instrumented boards vs U5's prediction — which is the only method that catches modeling errors (wrong effective conductivity, omitted convection, 3D/via effects) that the formal battery is structurally blind to.
- The pre-existing LOC-cap breakage and stale-JAX allowlist cleanup — separate; not caused by this work.
- New physics fields (EMI, current-density, capacitive coupling) and the custom inductance solver / FastHenry anchor — still deferred until thermal earns generalization.
- Machine-checked proofs (Coq / Lean / other proof assistants) — this effort uses property-based testing, BMC-exhaustive enumeration, and hand induction only.
- CP-SAT zone penalties remain deferred; R23 only sets the discipline for when they return, it does not build them.

---

## Key Decisions

- Methodology-first framing: the reusable four-layer pattern plus the BMC/induction ladder is the organizing structure; per-unit invariants instantiate it. Rationale: compounding value — future physics units inherit the pattern rather than re-deriving verification.
- The two soundness items (R5, R6) are correctness fixes distinct from the additive test batteries: they change results, so they carry the two-tier (fast audit + slow truth) discipline and their own verification, not just coverage.
- U7-independence (R6) is one of several AND-gated soundness dependencies, not a lone critical path: verdict trust rests equally on U5 correctness (R7-R10), U6 bounding (R5), U7 independence (R6), and U8 optimality (R13) — none is "polish." R6 is flagged for planning to sequence *early* because its H6 premise is the least-proven and its independent-method choice has the longest lead time, but the other soundness gates are co-equal.
- Rigor level is PBT + BMC-exhaustive + hand induction, not a proof assistant — proportionate to the risk and consistent with the repo's existing verification learnings (hypothesis-invariant ladder, BMC/induction ladder, independent-oracle).
- No internal sequencing is fixed here; planning owns ordering (user decision). Planning should sequence R6 early (lead time) while treating R5 and the core invariants as co-equal soundness gates.

---

## Dependencies / Assumptions

- The U5 invariants (R7-R10) assume the FDM discretization yields a symmetric positive-definite M-matrix — plausible for the 5-point harmonic-mean stencil with one Dirichlet edge and Neumann elsewhere, but anisotropic conductivity or a stencil variant can break it. R23 gates this: confirm the property on the shipped stencil before implementing the invariants, and reformulate them for the actual matrix class if it does not hold.
- Adding these invariants may surface latent bugs in the already-merged U5-U9; per R22 the trivial fixes are in-scope and architectural ones are scoped out as follow-up, so the effort is bounded by that triage rather than open-ended.
- The work builds on the merged physics feature branch (`feat/physics-informed-placement-routing`) as its substrate.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R6][Needs research] Which structurally-independent method for U7 — stochastic random-walk Monte-Carlo vs analytic Green's-function superposition — best balances genuine independence against cost and determinism (K4)?
- [Affects R5][Technical] Is the operating-point function provably monotone in the coupling coefficient for the actual circuit, or must the gate sample / interval-bound the interior?
- [Affects R15][Technical] Does a monotone ranking function exist for loop termination, or is BMC over bounded round sequences plus k-induction the pragmatic proof?
- [Affects R11][Technical] The concrete grid-refinement factors and error tolerances for the order-of-accuracy ladder.
- [Affects R1-R24][Deferred by user] Sequencing and priority across the batteries — deferred to planning. Planning should sequence R6 early for lead time while treating R5 and the core invariants (R7, R13, R15) as co-equal soundness gates.

### Surfaced in review (2026-07-09) — for planning to weigh

- [Affects Key Decisions / methodology] Reviewers (product-lens, scope-guardian) flagged the reusable-methodology framing (R1-R2) as possibly premature with only one consumer today — all other physics fields are deferred. You chose to keep the reusable framing; planning should decide whether to build the framework now or instantiate thermal-specific batteries first and extract the pattern once a second field adopts it.
- [Affects sequencing / U10] Reviewers (product-lens) flagged running the U10 reality-check A/B *before* the full hardening build-out, so verification effort isn't spent on a feature whose practical value is still unvalidated. Sequencing is planning's call; weigh U10-first (validate value, then harden) vs harden-first (fix R5/R6 so U10 tests a sound feature).

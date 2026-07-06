---
date: 2026-07-03
topic: post-parity-cp-sat-umbrella-roadmap
---

# Post-Parity CP-SAT Umbrella Roadmap

## Summary

A coordinating roadmap for the post-parity CP-SAT placer across five workstreams — JAX retirement, constraint-model completion, place→route closure, real-board acceptance-gate + UNSAT UX, and oracle-worktree hygiene — binding the cross-cutting disciplines that keep the old weight-tuning failure mode from re-emerging in SAT clothing. Per-workstream requirements documents ship separately and reference this umbrella for sequencing, decisive-result-per-step rule, and the objective-discipline contract.

---

## Problem Frame

The paradigm swap is settled (see `docs/brainstorms/2026-07-03-cp-sat-feasibility-first-placer-paradigm-swap-requirements.md`) and CP-SAT produces feasible, audit-clean placements in 0.1s with 652/652 hard constraints provably satisfied. The decisive experiment was *not* a parity comparison — that instrument was retired deliberately, because building instruments to justify an already-made decision was the defer-loop pattern across four prior cycles. The decision rests on the structural argument: penalty ≠ constraint, and feasibility-first is the problem's native form.

What remains is banking the win and building the untouched half. Placement is feasible; routing is not wired to placements end-to-end; constraints satisfy 4 of 8 of the design-intent types the board actually needs; the oracle worktrees represent the pre-swap mental model and need reconciliation. The roadmap's center of gravity moves from placement (solved) to the place↔route seam (untouched).

This umbrella exists because the road-map's individual workstreams share three things that must stay consistent across them or the project re-enters the defer-loop: (1) a *decisive-result-per-step* discipline that prevents building an instrument and deferring the measurement, (2) an *objective-discipline* contract that keeps weighted-sum tradeoff-tuning from re-emerging in CP-SAT-native form, and (3) *sequencing* that exploits CP-SAT's instant re-solve as the place↔route feedback mechanism instead of JAX's re-descend loop.

---

## Actors

- A1. **CP-SAT placer engine**: existing CP-SAT model + encoder; subject of constraint-completion and place→route workstreams.
- A2. **router_v6**: existing A* router; the untouched half of place→route.
- A3. **Physics oracle** (`metrics/external_oracle.py` + `validation/drc_runner.py`): fast inner acceptance gate; KiCad DRC is the truth gate.
- A4. **PCL spec** (`configs/pcl/temper_induction.yaml`): source of truth for board intent; constraint completion extends what the encoder honors.
- A5. **`core/loop_extractor.py`**: existing commutation-loop extractor; source of truth for loop-area-as-ceiling.
- A6. **Five placement-init worktrees**: ccap, dpp, hierarchical, thermal, constraint-passthrough — all JAX-init experiments, mooted by the swap.

---

## Key Flows

- F1. **Bank the win (JAX retirement)**
  - **Trigger:** Umbrella doc confirmed.
  - **Actors:** A1, A6
  - **Steps:** Reverse-topological deletion of the JAX descent stack following the documented dead-code-strangler pattern (see `docs/plans/2026-07-03-001-feat-cp-sat-feasibility-first-placer-plan.md` U9); `--placer jax-deprecated` retained for one release cycle as production-misroute rollback only (NOT as a parity gate — parity was skipped); close the five placement-init worktrees.
  - **Outcome:** CP-SAT is the sole placer; the JAX weight-tuning apparatus no longer exists. Resolved details live in the JAX-retirement per-workstream doc.
  - **Covered by:** R1

- F2. **Complete the constraint model**
  - **Trigger:** Parallel with F1.
  - **Actors:** A1, A4, A5
  - **Steps:** Extend the CP-SAT encoder to honor LOOP_AREA (the commutation loop), ANCHORED (fixed-position parts: AC inlet, coil terminals, mounting-hole-adjacent), KEEPOUT (coil area, holes, thermal exclusion), and discrete rotation (0/90/180/270 — a CP-SAT strength and exactly the bug that gave JAX the 250M-rotation-logits softmax failure). Resolution of "loop area as hard ceiling vs lex-opt level" (see Key Decisions) precedes any other loop-area work.
  - **Outcome:** CP-SAT satisfies all 8 PCL constraint types the board actually needs; "CP-SAT places the board" means "satisfies the full design intent." Resolved details live in the constraint-completion per-workstream doc.
  - **Covered by:** R2

- F3. **Build the place→route loop**
  - **Trigger:** F2 sufficient (LOOP_AREA+rotation in).
  - **Actors:** A1, A2
  - **Steps:** Feed CP-SAT placements → router_v6, measure real completion + DRC. Where congestion or an unroutable region surfaces, inject a CP-SAT constraint (spacing / keepout / order) and re-solve instantly (0.1s feasibility), instead of JAX's re-tune-and-re-descend. This is the second dividend of the feasibility-first paradigm.
  - **Outcome:** A placement round-trips through the router to a real completion number. Resolved details live in the place→route per-workstream doc.
  - **Covered by:** R3

- F4. **Real-board acceptance gate + UNSAT UX**
  - **Trigger:** F3 produces round-trip placements.
  - **Actors:** A1, A3
  - **Steps:** Full pipeline → real KiCad DRC with 6mm design rules (not the oracle proxy) → zero violations on the temper board is the bar; oracle is the fast inner gate, KiCad DRC is the truth. Exploit UNSAT cores (U7) as a product feature: when a board is infeasible, surface the minimal conflicting constraint set with `because` text — turning "the placer failed" into "your spec is over-constrained, here's why." No optimizer could ever give that.
  - **Outcome:** Temper board passes real KiCad DRC; UNSAT reports are first-class output. Resolved details live in the acceptance-gate per-workstream doc.
  - **Covered by:** R4, R5

- F5. **Oracle-worktree hygiene**
  - **Trigger:** F1 begins; lands with F4.
  - **Actors:** A6, A3
  - **Steps:** Land `physics-derived-oracle` as the acceptance gate (per F4). Demote `human-reference-corpus-oracle` to the regression floor: "don't crash / don't regress geometrically across 49 boards" — its correct role from way back. Close the five placement-init worktrees per F1. Each worktree's close-vs-land decision is enumerated in the umbrella, not designed in a separate per-workstream doc — these are decisions, not builds.
  - **Outcome:** Parallel branches represent the post-swap mental model only; old mental-model branches cleared.
  - **Covered by:** R6

---

## Requirements

**[Bank-the-win sequencing]**
- R1. JAX retirement proceeds per the existing `2026-07-03-001` plan's U9 (which already encodes the reverse-topological dead-code-strangler deletion and the extended Modify list hitting router_v6, pipeline/, ablation/, adapters/, regression/, validation/, pcl/). The umbrella adds two things: the five placement-init worktrees (ccap, dpp, hierarchical, thermal, constraint-passthrough) close as part of F1; `--placer jax-deprecated`'s *rationale* in this doc is **production-misroute rollback for non-corpus boards** (not the parity-gate bridge the original plan described).
- R2. Constraint-model completion and JAX retirement run in parallel — neither blocks the other. Constraint completion proceeds against the temper board; JAX retirement proceeds against the codebase topology. Both gate the routing workstream's start.

**[Place→route as the actual product]**
- R3. The place→route feedback loop exploits CP-SAT's instant re-solve as its core mechanism: congestion or unroutable regions surface from router_v6, are encoded as new bounds/keepouts/orderings in the CP-SAT model, and the placement re-solves in feasibility-budget time (≤1s target), not optimizer-budget time. The doc must specify what kinds of feedback become constraints (clearance increase in congested region? keepout around an unrouted pin? ordering preference?) — this is net-new design that didn't exist in the JAX world.

**[Real-board acceptance gate]**
- R4. The acceptance bar for the temper board is zero KiCad DRC violations with the real 6mm design rules — *not* the oracle proxy. The oracle is the fast inner gate (used iteratively); KiCad DRC is the truth (used at acceptance). The doc must distinguish the two roles explicitly.
- R5. UNSAT reports (U7 in the existing plan — `extract_unsat_core` + deletion-based MUS) become a first-class output of the placer, surfaced to the domain expert, not buried in logs. The doc must specify the surface (formatted panel to stderr, structured JSON to a file, both) and the content (minimal core + `because` text per conflicting constraint).

**[Oracle-worktree hygiene]**
- R6. Five placement-init worktrees close (ccap, dpp, hierarchical, thermal, constraint-passthrough) — each is a JAX-init experiment mooted by the swap. `physics-derived-oracle` lands as the acceptance gate per F4. `human-reference-corpus-oracle` lands demoted to regression-floor (49-board no-crash / geometric-no-regress — *not* acceptance). Each worktree's close-vs-land is enumerated in the umbrella itself (decisions, not builds — no per-workstream doc).

---

## Objective-Discipline Contract (Cross-Cutting)

This section is the **umbrella's binding contract across all per-workstream docs**. Any workstream that adds a new objective term — wirelength, spread, loop area, congestion proxy, anything — must route it through the following decision tree:

1. **Absolute physics target exists → hard constraint.** Loop area with a derivable L_loop budget (from switching frequency, dV/dt, acceptable overshoot/ringing) → a hard ceiling (`max_area_mm2`), not an objective term. This is the cleanest encoding of "good enough" and prevents over-optimizing loop at wirelength's expense. *Prerequisite:* verify the physics gives the absolute number for the temper board. The existing PCL config and `loop_extractor.py` already encode loop area as `max_area_mm2=500` (a cap), so this path is infrastructure-supported.

2. **Preference-order only (no absolute target) → strict-tolerance lexicographic optimization.** Multi-level priority chain; each level minimized subject to prior levels ≤ optimal + tol. **The umbrella's strict rule:** `tol = 0` for physics-critical levels (loop area if it slips into this category, thermal residual, clearance margin past DRC). `tol > 0` only where the exchange rate is explicitly defensible as physically meaningful — and the doc names the value and gives the rationale. Bounded regret is *not* automatically safe: tol > 0 is a tradeoff quantized into one number instead of a ratio, and that number becomes an untraceable magic constant six months later unless documented.

3. **Pure same-axis tiebreak → dominated ε-sum with the faithful-lex inequality enforced.** The current `Minimize(net_wl + ε · spread)` is a weighted sum allowed exactly when: `ε · max(spread) < min_nonzero_increment(wirelength)`. With integer CP-SAT, both sides are checkable from the actual variable domains. The doc must state the inequality as the *condition*, never the gut-feel "ε is small enough" — and ideally assert it in the model builder. "Two orders of magnitude smaller" is not automatically dominated; the inequality is the testable version of that intuition.

**Three tools, three conditions.** Workstream docs add objective terms by stating which tool applies and producing evidence for the condition. The umbrella does not pre-list the assignments — those land per workstream — but it does preclude any fourth form (notably: weighted sums across genuinely-coupled soft objectives like loop vs wirelength, which is the original JAX pathology in direct translation).

**Anti-pattern this contract prevents:** "weight-tuning hell in CP-SAT clothing" — picking a magic number (ε, tol, or weight) that makes a soft term "act like" a hard one. The contract makes every new magic number a documented decision with one of three enumerated justifications, not a tunable parameter.

---

## Decisive-Result Discipline (Cross-Cutting)

Per the roadmap's caution about the recurring *build-instrument-defer-measurement* pattern across this project: each workstream carries its own **decisive result** — a single adjudicating number/state that determines whether the workstream is done, stated up front, not invented after implementation.

| Workstream | Decisive result | What "done" means |
|---|---|---|
| JAX retirement | U9 deletion PR lands green; CP-SAT sole placer | The JAX descent stack is gone; any board addressed via CP-SAT or the `jax-deprecated` rollback path (which itself retires after one release cycle) |
| Constraint completion | Temper board places with LOOP_AREA + rotation + ANCHORED + KEEPOUT enforced and the placement passes real KiCad DRC | CP-SAT satisfies all 8 of the design-intent constraint types — not "5 of 8 documented and 3 logged as warnings" |
| Place→route loop | A CP-SAT placement round-trips through router_v6 to a real completion number ≥ 90% on the temper board | The place→route seam produces a measurable, scored routing — not just an attempted one |
| Real-board acceptance gate + UNSAT UX | Temper board passes real KiCad DRC (zero violations at 6mm); UNSAT reports surface minimal core + `because` text | The placer's acceptance is governed by real DRC, not by proxy metrics; UNSAT is a first-class output, not a log line |
| Oracle-worktree hygiene | Old mental-model worktrees closed; survivors consolidated | No parallel branch represents the pre-swap paradigm |

The umbrella binds each per-workstream doc to a *non-deferrable* version of its decisive result: the doc must contain an explicit "what number/state, produced by what instrument, blocks what next step" sentence. A workstream doc that omits this is rejected at brainstorm-review.

---

## Sequencing

```
Phase A (parallel):
    F1. Bank the win (JAX delete)         [decisive: deletion PR green]
    F2. Complete constraint model          [decisive: 8-types places + DRC clean]

Phase B (after Phase A):
    F3. Place→route loop                  [decisive: routing completion ≥ 90%]

Phase C (after Phase B):
    F4. Real DRC gate + UNSAT UX           [decisive: temper passes KiCad DRC]
    F5. Oracle-worktree hygiene           [decisive: branches consolidated]
```

F1 and F2 phase together — neither blocks the other. F3 starts when F2 is sufficient (LOOP_AREA + rotation in the encoder); F3's start does not strictly require F1 to complete, but F1's deletion surface overlaps router_v6/pipeline.py imports and must be coordinated. F4 and F5 land together after F3's round-trip exists.

---

## Per-Workstream Documents Referenced

This umbrella references four per-workstream requirements documents that follow it. Each carries its own decisive result per the table above; none may proceed without that result specified.

- **JAX retirement** — per-workstream doc scope: reverse-topological deletion sequencing, worktree-close enumeration, `jax-deprecated` rollback-window termination criteria. Reuses U9 of `docs/plans/2026-07-03-001-feat-cp-sat-feasibility-first-placer-plan.md` (already extensive) and adds the placement-init worktree close list.
- **Constraint completion** — per-workstream doc scope: per-type encoder design for LOOP_AREA (hard-ceiling vs lex level — resolved per Objective-Discipline contract prerequisite), ANCHORED, KEEPOUT, discrete rotation. Each new constraint type's ESL predicate BMC test infrastructure (per existing `router_v6/bmc.py` pattern).
- **Place→route loop** — per-workstream doc scope: what router_v6 feedback becomes what CP-SAT constraint; the re-solve loop's termination criteria; how two-phase solve (per Discipline below) interacts with place→route iteration.
- **Acceptance gate + UNSAT UX** — per-workstream doc scope: KiCad DRC integration surface (likely `validation/drc_runner.py`); UNSAT report format and surfacing; the oracle's demoted role (fast inner gate vs truth gate).

Oracle-worktree hygiene is not its own per-workstream doc — R6 enumerates the per-worktree decisions directly because they are decisions, not builds.

---

## Scope Boundaries

- **Re-running parity** under any framing is out of scope — confirmed in `docs/brainstorms/2026-07-03-cp-sat-feasibility-first-placer-paradigm-swap-requirements.md` ("skip it"); this umbrella does not relitigate.
- **Re-debating the paradigm swap itself** — out of scope. The structural argument stands.
- **Worktree-cleanup mechanics** — enumeration only (R6); each worktree's close-vs-land is one line in R6, not a designed workstream.
- **Constraint-specific encoding designs** — per-workstream constraint-completion doc; umbrella only fixes the shared objective-discipline and decisive-result contracts.
- **External (non-temper) board corpus, design-space exploration, multiple-board productization** — explicitly outside this umbrella (per the original brainstorm's scope boundaries); revisit the paradigm only if the project later scales.
- **Continuous-angle rotation, soft-routed loop-area minimization inside the objective, multiple-soft-objective weighted sums** — out of scope for v1 of this umbrella. Each is excluded by the Objective-Discipline Contract or by the constraint-completion doc's scope.

---

## Key Decisions

- **Umbrella + per-workstream docs over one mega-roadmap** — coherence at the strategy level; lighter per-doc; more PRs to track. Chosen over a single consolidated doc per the brainstorm answer.
- **Loop area likely lands as a hard ceiling (`max_area_mm2`), not a lex-opt level** — because the existing PCL config and `loop_extractor.py` already encode it as a cap, and "smaller loop is always better" is physically false past the EMI budget's absolute L_loop limit. The constraint-completion workstream doc carries the **prerequisite finding**: verify the absolute number from the temper board's switching frequency, dV/dt, and acceptable overshoot/ringing. If verifiable → hard ceiling (clean, lex-opt collapses entirely, discipline A simplifies); if not → strict-tolerance lex level (tol=0 — no exchange with wirelength at any rate), and the doc states that as the fallback.
- **`--placer jax-deprecated` rationale is production-rollback for non-corpus boards** — the original plan (`2026-07-03-001`) framed it as a parity-gate bridge; with parity skipped, the window's *reason* changes. It stays one release cycle, but the *justification* in this doc is "rollback if a non-corpus board surfaces a CP-SAT pathology in production," not "rollback until parity passes." Different reason, same duration. The deletion doc must record this rationale shift.
- **Skip-parity carries forward from the ancestor brainstorm** — neither re-litigated nor re-motivated here. The umbrella cites the swap-requirements doc and proceeds.
- **Two-phase solve is umbrella-bound as pipeline structure; phase-2's objective mechanism is governed by the Objective-Discipline Contract** — the structure (feasibility 0.1s, bounded objective 60s, accept best-in-budget) is fixed; the mechanism (single-objective vs lex-opt vs dominated ε-sum) is constrained by the contract's three-tools rule. Per-workstream docs specify per their added objectives.
- **Decisive-result-per-step is non-negotiable** — this is the direct antibody to the deferred-decisive-experiment pattern this project hit four times. Each per-workstream doc is rejected at brainstorm-review if it lacks the explicit "what number/state, produced by what instrument, blocks what next step" sentence.

---

## Dependencies / Assumptions

- **Hard prerequisite: PR #121 merged — applies to every per-workstream doc.** Round-2 doc-review's largest theme ("infrastructure does not exist") was a main-not-worktree scan; per-doc Dependencies sections record this line explicitly. The umbrella itself also assumes post-#121 state for all its infrastructure references.
- **Round-2 added: U0b extended spike gates Doc 1's R1 (JAX-retirement deletion) AND Doc 2's full implementation.** Per the brainstorm's "spike first, then parallel" answer: Doc 2's first implementation unit is U0b (8/8 constraint types + 4-way rotation on the temper board at ≤600s wall budget). U0b passing is the empirical gate that the *model* the per-workstream docs specify is solvable in budget. The original U0 spike validating 4/8 types at ~62s is *not* evidence for the 8/8+rotation model — round-2 P0 #1 was correct on this. The umbrella previously had F1 ∥ F2 by default; the revised sequencing adds U0b as a synchronized gate between them.
- **The CP-SAT feasibility spike (U0, ~62s with objective)** passes the temper board against 4/8 types — already verified on the dev machine, recorded in `docs/plans/2026-07-03-001...` U0 status line. The umbrella proceeds on this assumption *for the 4/8 types only*; 8/8+rotation is U0b's job per the addition above.
- **router_v6 is consumable from a CP-SAT placement without major modification** — verified by the existing `router_v6/pipeline.py` and the placement-state decoupling already shipped in #121's U5. The place→route workstream resolves any integration surprises.
- **`validation/drc_runner.py` exists as the KiCad DRC integration point** — verified during the brainstorm-context scan. The workstream doc confirms and designs the integration surface.
- **Cross-workstream interface contract (per round-2 residual concern #4):** each per-workstream doc consumes another's surface; if that surface shifts, the consumer absorbs the change silently unless the consumed surface is treated as a frozen interface. The umbrella names the three cross-doc interface contracts to freeze at planning-end: (a) Doc 2's encoder handler signatures + `SolveContext` shape + `rot_ref` injection rules (consumed by Doc 3's feedback-class vocabulary); (b) Doc 4's UNSAT UX surface (`UnsatReport` + Rich panel + JSON format — consumed by Doc 3 for the operator-escalation surface); (c) Doc 1's `--placer cp-sat` (not `jax-deprecated`) as the CLI default (consumed by Doc 3 and Doc 4 as the *only* placer path post-retirement). Per-doc Outstanding Questions record the verification step.
- **`kicad-cli` availability (per round-2 residual concern #2)** — single-point dependency for the decisive results of Docs 2, 3, and 4. If unavailable in CI, the workstreams bind bar against the *truth gate* running on local/runner environments; the CI runs without the truth gate as a *flagged soft-fail*, never a silent downgrade to oracle-proxy. Each relevant per-workstream doc's Outstanding Questions surfaces this explicitly.
- **The L_loop budget for the induction-burner spec is computable from existing spec inputs** (switching frequency, dV/dt, overshoot/ringing limits) — *unverified assumption*. The constraint-completion workstream's prerequisite finding is to compute or refute this number. If refuted, loop-area-as-hard-ceiling collapses to strict-tolerance lex level per the Objective-Discipline Contract's path (2).
- **The faithful-lex inequality `ε · max(spread) < min_nonzero_increment(wirelength)` is enforceable as a model-builder assertion in CP-SAT** — unverified but high-confidence given CP-SAT's integer arithmetic; the constraint-completion workstream verifies and adds the assertion or migrates `ε·spread` to a true 2-level lex.
- **The five placement-init worktrees (ccap, dpp, hierarchical, thermal, constraint-passthrough) are exhaustively the dead JAX-init branches** — verified via `git worktree list` (six worktrees total beyond main: those five + viz-server, which is not in scope here).

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R2 / loop-area decision][Needs research] Compute or refute the L_loop budget from the temper induction-burner spec (switching frequency, dV/dt, overshoot/ringing limits). If the absolute number is computable, loop area → hard ceiling; if not, strict-tolerance lex level with tol=0. This is the constraint-completion workstream's prerequisite; the umbrella cites it but does not produce it.

### Deferred to Planning

- [Affects the cross-cutting terms][Phase 2 terminology glossary] "Phase 2" / "two-phase solve" means three *different* things across the umbrella and the per-workstream docs — round-2 doc review (#21) flagged this confusion: (a) the umbrella's **objective-discipline two-phase solve** = feasibility solve (≤1s, no objective) followed by bounded objective solve (≤60s, accept best-in-budget) on the same model — a *solver* phase split; (b) Doc 2's R4 two-tier acceptance gate = inner gate (audit + physics oracle) + truth gate (KiCad DRC) — an *acceptance* phase split; (c) Doc 3's R3 phase-2 polish = bounded-objective-runs-after-stability (two consecutive feasibility-stable round-trips) — a *loop* phase split. Each per-workstream doc uses "phase 2" in its own sense per (a)/(b)/(c); readers cross-referencing docs must keep the senses distinct. This is documentation drift, not architectural drift — fix once here, refer by ID across docs.
- [Affects R4][Technical] The exact KiCad DRC integration surface — `validation/drc_runner.py` exists but the workstream must specify cli/wrapper/wrapper-script form and the zero-violation bar's exact acceptance policy.
- [Affects R5][Technical] UNSAT report format — Rich-formatted panel to stderr vs structured JSON file vs both. Workstream chooses; the umbrella only binds "minimal core + `because` text" as content.
- [Affects every workstream][Technical] The faithful-lex inequality's enforcement form (assertion in model builder, allocation-time check, or runtime check on objective value) — constraint-completion workstream's responsibility.
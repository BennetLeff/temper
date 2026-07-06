---
date: 2026-07-05
topic: place-route-loop-feedback-as-constraint
---

# Place→Route Loop: Router Feedback as a CP-SAT Constraint

## Summary

Wire the CP-SAT placement output through `router_v6` and close the loop: where congestion or an unroutable region surfaces, encode the router's signal as a *new CP-SAT hard constraint* (clearance increase in a congested region, keepout around an unrouted pin, ordering on a critical path) and re-solve in feasibility-budget time. Decisive result: *a CP-SAT placement round-trips through router_v6 to a real completion number ≥ 90% on the temper board* — the place↔route seam stops being theoretical and produces a measurable routing.

---

## Problem Frame

Placement is solved (post-parity, post-constraint-completion); routing has remained untouched throughout the paradigm swap. The throughline of the umbrella roadmap's "center of gravity moves from placement (solved) to place↔route seam (untouched)" is that placement alone doesn't ship a board — the routed placement is the product. The CP-SAT placer's instant re-solve (feasibility ~0.1s) is the second dividend of the paradigm: where JAX needed "retune weights and re-descend" to react to routing failure, CP-SAT needs "add a hard constraint and re-solve in 0.1s." Routing feedback stops being a slow weight-tuning loop and becomes a fast feasibility adjustment.

Three pieces of infrastructure are already in place per the umbrella's research scan: `route_pcb()` at `router_v6/adapter.py:316`, `_apply_placements_to_pcb()` at `router_v6/adapter.py:402`, and the CP-SAT placement output's `PlacementState.from_positions_dict()` factory (per #121's U5). So F3 is *wiring*, not net-new infrastructure. What's net-new is the *feedback-class vocabulary* — what categories of router_v6 signal become what categories of CP-SAT constraint. That vocabulary, not the plumbing, is this workstream's actual design surface.

What also lands here: the place→route loop is where the two-phase solve from the umbrella's discipline section interacts with iteration. Phase 1 (feasibility, 0.1s) produces a placement to feed router_v6; phase 2 (bounded objective, ≤60s) polishes wirelength *within* the feasible set. The loop must choose, per round-trip, whether phase 2 runs before re-routing or only after a stable-feasibility run. The umbrella leaves that to this workstream.

---

## Actors

- A1. **CP-SAT placer** — produces placements; receives feedback-as-constraint injections.
- A2. **router_v6** — via `route_pcb()` and `_apply_placements_to_pcb()`; produces routing completion, DRC violations, congestion heatmap, unrouted nets.
- A3. **The feedback-class vocabulary** — the mapping from router_v6 signals to CP-SAT constraint encodings. Lives in this workstream as the actual design output.
- A4. **Two-phase solve policy** — decision per round-trip on whether phase 2 runs before re-routing.
- A5. **`validation/drc_runner.py`** — truth-gate side of the two-tier acceptance (per F4); F3 *consumes* the gate but does not own it.

---

## Key Flows

- F1. **Place → route → measure (the trivial half)**
  - **Trigger:** A CP-SAT placement exists (post-constraint-completion).
  - **Actors:** A1, A2, A5
  - **Steps:** Apply CP-SAT positions to a placed PCB via `_apply_placements_to_pcb`; run `route_pcb()`; collect `RoutingResults.compile_routing_results()` — completion rate, unrouted-nets list, DRC violations from `validation/drc_runner.py`. The output is a structured measurement, not a verdict: completion 70% and three clearance violations is feedback, not failure.
  - **Outcome:** A placement + routing + measurement triple available to F2's feedback classifier.
  - **Covered by:** R1

- F2. **Feedback classification (the design surface)**
  - **Trigger:** Routing measurement returns completion < 100% *or* DRC violations > 0 *or* hotspots in congestion heatmap.
  - **Actors:** A3
  - **Steps:** Map the router signal to a CP-SAT constraint injection. The classification vocabulary this workstream specifies (open by default; refined during implementation):
    - **Unrouted net in a congested corridor** → `SeparatedConstraint` increase between the corridor's bounding components (push them apart to widen the channel) OR `KeepoutConstraint` injection across the corridor midline to force the router to find an alternate path.
    - **DRC clearance violation between two placed components** → `SeparatedConstraint` with the violated minimum, replacing any weaker prior separation (CP-SAT's hard constraint is the correction, not a re-tuned weight).
    - **Unrouted pin on a critical IC** → temporary `AnchoredConstraint` on the unrouted pin to its optimal-routed position (determined by shortest-path heuristic pre-routing), forcing CP-SAT to choose a topologically-preferable placement.
    - **Persistent routability failure on a high-pin-count IC** → split the IC's escape-pattern demand by enforcing a rotation specific to the dense side (interaction with F3-of-constraint-completion's discrete-rotation model).
  - **Outcome:** A *delta* to the PCL constraint set (additions / tightenings) capturing the routing feedback as hard constraints, ready for F3.
  - **Covered by:** R2

- F3. **Re-solve in feasibility budget**
  - **Trigger:** F2 produces a constraint delta.
  - **Actors:** A1, A4
  - **Steps:** Apply the delta to the model (incremental solver API where supported by OR-Tools — `solver.Solver.push()/pop()` analogs via fresh model with warm-start hint from prior placement); solve phase-1 feasibility-only (≤1s target — the umbrella's discipline binds this as a budget, not a desire). Optionally run phase-2 polish if the placement is feasibility-stable across consecutive round-trips.
  - **Outcome:** A revised placement re-enters F1. The loop terminates on completion = 100% AND DRC = 0 AND a phase-2 budget exhausted — OR — on a round-trip budget cap (defaulting to N=10 — TBD per implementation; CP-SAT's instant re-solve makes 10 cheap, but a board that hasn't converged in 10 likely has a constraint-set infeasibility worth surfacing).
  - **Covered by:** R3, R4

---

## Requirements

- R1. CP-SAT placement output round-trips through `router_v6.adapter.route_pcb()` and `validation/drc_runner.run_drc()`, producing three structured outputs: completion_rate (0.00–1.00), unrouted_nets (list, name + reason), drc_violations (list, source-target-pair + rule + actual_value). The measurement is per-round-trip; lossy/summary-only output is not acceptable as feedback source.
- R2. The feedback-class vocabulary (the actual design output) — this workstream's R2 specifies the four feedback classes (congestion-corridor separation/keepout, clearance-violation tightening, unrouted-critical-pin anchoring, persistent high-pin-count rotation split) at minimum; new classes discovered during implementation are *additions to the vocabulary*, not exceptions. The vocabulary's encoding rules follow the existing `encoder.py` dispatch: each injected constraint is a normal PCL constraint type that the constraint-completion encoder handles (no special-case "routing constraint" path).
- R3. Re-solve is bounded by feasibility-budget time (≤1s target after warm-start; ≤5s worst case). Phase-2 objective runs only if the placement has been feasibility-stable across two consecutive round-trips (heuristic for "the constraint set is mature enough to polish wirelength"). Loop terminates on: completion=100% AND DRC=0 AND phase-2 budget-exhausted; OR round-trip budget cap (default N=10 — implementer selects, must state the cap in the doc).
- R4. **Decisive result** (per the umbrella's Discipline): *a CP-SAT placement round-trips through router_v6 to a real completion number ≥ 90% on the temper board.*  **The 90% bar is the workstream-decisive gate (place→route seam operational — round-2 finding #10 clarification); it is NOT the ship bar.**  A board with 10% unrouted nets is not manufacturable; ≥ 100% is the acceptance bar (per Doc 4 R2: zero DRC errors + routed placement complete).  The 90% bar means: this workstream has demonstrated the loop *works* and closes the seam; the remaining 10% is documented as stretch-to-100% in the deferred work.  Per the umbrella: "the place↔route seam produces a measurable, scored routing — not just an attempted one."
- R5. **Backtracking policy: hybrid auto-soft / escalate-hard (per the brainstorm decision resolving doc-review #12 deadlock).** Three rules:
  1. **Auto-track among soft-tunable feedback classes** (`SeparatedConstraint` tightening, `KeepoutConstraint` injection, ordering preferences, anchoring on critical pins). On UNSAT from a soft-tunable injection, drop it, try the next-strongest. Operator stays uninvolved by default.
  2. **Escalate to operator on hits to physics-grounded hard constraints** (loop-area tol=0 ceiling per L_loop derivation, thermal-edge anchoring, statutory HV/LV creepage). The loop never auto-loosens these. Surfacing uses Doc 4's UNSAT UX panel + the physics `because` text; operator picks: (a) hand-edit PCL to a *documented* higher value with re-derived physics justification (Doc 2's tolerance-override surface), (b) relax a non-physics constraint in the conflict, (c) escalate board-design review. The system freezes the physics-informed default; the human can override with explicit re-derivation, never silent loosen.
  3. **Always halt on the round-trip cap (default N=10)达ed: surface UNSAT core + routing symptom + "constraint-relaxation solicited" prompt. Never silently compromise.**
  Each feedback-class injection logs its classification (soft-tunable vs physics-grounded) so audit trails distinguish auto-escalation from operator-escalation.

---

## Acceptance Examples

- AE1. **Covers R1, R4.** Given the temper board post-constraint-completion, when CP-SAT places and the placement is routed through `route_pcb()`, the produced result includes a completion rate ≥ 90% (target ≥90% to satisfy the decisive result; if the first run produces <90%, the loop iterates toward ≥90% as the workstream's *stopping criterion*, not just its measurement).
- AE2. **Covers R2.** Given a routing with one clearance violation between two HV/LV pair components, when F2's classifier runs, it injects a `SeparatedConstraint` with the violated minimum against the conflicting pair; the next CP-SAT solve produces a placement where the violation is closed (the audit catches it as a hard constraint, not a soft preference).
- AE3. **Covers R2.** Given an unrouted-pin failure on a high-pin-count IC, when F2's classifier runs, the next CP-SAT solve's encoder receives a rotation constraint variant from the feedback-vocabulary (not a custom outside-the-vocabulary injection) — verifying the vocabulary stays closed.
- AE4. **Covers R3.** Given a placement that has been feasibility-stable across two round-trips, when the third round-trip's phase-1 feasibility solve produces the same placement, the loop runs phase-2 bounded wirelength polish (≤60s) before re-routing; completion after phase-2 does not regress below phase-1's completion.
- AE5. **Covers R5.** Given a feedback-constraint injection that turns the placement UNSAT, the loop surfaces the `extract_unsat_core` report naming the minimum-conflicting subset and either chooses the next-strongest feedback signal OR exits with the report and a structured "constraint-relaxation solicited" prompt to the operator.

---

## Success Criteria

- *A CP-SAT placement round-trips through router_v6 to a real completion number ≥ 90% on the temper board* (decisive result) and the loop's behavior at <100% is specified and demonstrated — not just "ran the funnel once."
- The feedback vocabulary is the workstream's documented contribution — a future contributor extending it has a clear spec to add a new class, knowing what classes already exist.
- CP-SAT's instant re-solve is the *exploited* mechanism: at no point in the loop does an injected constraint trigger a "re-tune and re-descend" path. The paradigm dividend is collected.
- Two-phase solve (feasibility then bounded polish) interacts cleanly with iteration: phase-2 stability governs when polish runs.
- UNSAT-feedback is handled as a first-class outcome (a router signal that produced an infeasible placement), not an exception.

---

## Scope Boundaries

- **Routing-completion optimization below 90% vs. 100%** — the workstream's decisive result is ≥ 90% on the temper board. Pushing toward 100% may require constraint-vocabulary extensions that this workstream *leaves as documented extensions*, not implementations. Closing the last 10% may be a separate follow-up if the vocabulary proves insufficient.
- **Multi-board generalization** — the decisive result is temper-specific. Whether the vocabulary generalizes to rp2040/bitaxe/piantor is a stretch property; routing them is not in scope.
- **Manually-traced autorouter paths (interactive routability editing)** — out of scope; the loop is automated place↔route, not interactive.
- **Automatic loop-area constraint loosening for routability** — the L_loop ceiling is *hard* (per the L_loop derivation, tol=0). The loop must not loosen a physics-grounded constraint to fix a routing symptom. If routing fails due to loop-area constraints, the loop surfaces this as an UNSAT report and asks the operator — *not* auto-loosen.
- **Replacement of router_v6 itself** — out of scope. router_v6 stays as-is; the loop wraps it. If the loop consistently fails because router_v6 cannot route a feasible placement, that's a router_v6-quality的问题 routed to the router improvement track, not this workstream.
- **Two-phase solve's objective mechanism** — out of scope; the umbrella's Objective-Discipline Contract (per the constraint-completion doc) binds *what* objectives enter the chain. This doc binds *when* phase 2 runs within the loop.

---

## Key Decisions

- **Feedback classes are normal PCL constraint types, injected through the same encoder** — no special "routing constraint" path. Congestion becomes `SeparatedConstraint`; clearance becomes `SeparatedConstraint`-stronger; unrouted critical pin becomes `AnchoredConstraint`; high-pin persistent failure becomes a rotation-coordination variant. The vocabulary specifies the *mapping*; the encoder doesn't know the constraint came from feedback vs. from PCL. This is the cleanest architecture and avoids the silent-guard-condition dead-infrastructure pattern the C-CAP failure exemplified.
- **≤1s re-solve as feasibility budget, not desire** — the umbrella binds this; CP-SAT feasibility-first on N=33 with ~5–10 added feedback constraints at 0.1mm should stay sub-second. If profiling shows >1s, the workstream investigates (variable-domain tightening is the first lever per the CP-SAT primer); >5s for any reason enters the loop-control budget as a round-trip limit, not a slow-down acceptance.
- **Phase 2 runs on stability, not on every round-trip** — the loop's first rounds are feedback-driven (feasibility-first → re-solve for the constraint delta). Phase-2 wirelength polish adds value only when the constraint set is *converging* — running it before wastes 60s on a placement F2 will revise anyway. Two consecutive feasibility-stable round-trips is the trigger (heuristic; refine during implementation).
- **No physics-constraint loosening for routability** — the L_loop derivation's hard ceiling stays hard; thermal anchoring stays hard. The loop must not trade a physics-grounded infeasibility for a routing symptom; doing so would re-import the JAX weight-tuning pathology as surreptitious constraint-relaxation. The documented backtracking surface is "next-strongest feedback signal or operator-relief" — never "auto-loosen a physics constraint."
- **Round-trip cap default N=10** — a workstream whose 11th round-trip's re-solve is unlikely to converge is signaling a constraint-set infeasibility worth surfacing, not a routing problem. The cap is a budget that forces evasive behavior at the workstream's exit. The exact number (5? 10? 15?) is the implementer's call per implementation profiling.

---

## Dependencies / Assumptions

- **Hard prerequisite: PR #121 merged.** All "existing infrastructure" claims in this doc — `route_pcb()` at `router_v6/adapter.py:316`, `_apply_placements_to_pcb()` at line 402, `PlacementState.from_positions_dict()`, `score_placement()`, `unsat.extract_unsat_core` — resolve against the post-#121 state. Round-2 doc-reviewers scanned main and reported these as missing; verifying against the worktree returns them at the cited locations.
- **Constraint-completion workstream (F2 of the umbrella; per doc `2026-07-05-constraint-completion-cp-sat-encoder-requirements.md`) has landed — including the U0b extended spike passing.** This workstream iterates placements with all 8 PCL constraint types honored including the hard loop-area ceiling and rotation; the loop's feedback vocabulary interacts with constraint types that the constraint-completion doc delivers (`KeepoutConstraint`, `AnchoredConstraint`, rotation variants). Per round-2 finding #19: this dependency was previously implicit and easy to miss; it's now explicit. *Hard prerequisite — F3 cannot start without F2's U0b spike passing.*
- **Cross-workstream interface contracts (per round-2 residual concern #4):** this workstream consumes Doc 2's encoder surface (the constraint type handlers + the post-rotation `x_size`/`y_size` IntVars), Doc 4's UNSAT UX surface (the Rich panel + JSON from `extract_unsat_core`), and Doc 1's `--placer cp-sat`-as-default CLI state. If Doc 2's encoder surface shifts (e.g. a handler signature changes to accept rotation variants directly), this workstream absorbs the change *silently* unless the signature is treated as an interface contract. Planning must record the consumed signatures (per handler: dispatcher signature, `SolveContext` shape, `rot_ref` injection rules) as a frozen interface surface at Doc 2's planning-end; F3's planning agent verifies and freezes, then implements against the frozen interface — any change to that interface triggers a Doc-3-aware review.
- **OR-Tools' incremental solver API supports constraint deltas efficiently** — verified as "high-confidence"; OR-Tools 9.x supports warm-start via `model.AddHint()` and re-solve. *Unverified:* whether `Solver.push()/` `pop()` analogs work for the constraint classes this workstream injects (round-2 residual concern #1). May require fresh-model-with-hint for the loop's normal path — F3 verifies, falls back if push/pop doesn't preserve performance.
- **`validation/drc_runner.run_drc()` runs cleanly on a routed PCB** — the doc review's verification surfaced this exists and is the truth gate (Doc 4 owns it); F3's F1 consumes its output. If `kicad-cli` is not available in CI (round-2 residual concern #2), F3 falls back to oracle-proxy DRC for the loop's iterative runs and reserves real DRC for the final acceptance run — a proxy-vs-truth distinction this workstream surfaces in its output, not silently defaults on.
- **`score_placement()` and `run_physics_oracle()` are callable without the caller importing JAX** — verified at #121's U5 post-#121 merge; `from_positions_dict()` factory handles the caller's namespace. Caveat stays: `core/state.py` still `import jax` at module level per Doc 1's post-deletion-dependency-audit relaxation; F3 lives in the post-deletion state and inherits Doc 1's post-deletion scope.

---

## Outstanding Questions

### Resolve Before Planning

_None — backtracking policy (R5) resolved via the brainstorm's hybrid auto-soft/escalate-hard decision; the deadlock doc-review #12 flagged is broken by that decision, not deferred._

### Deferred to Planning

- [Affects R3][Technical] Round-trip cap default N — 10 is the default per the doc; implementer tunes based on profiling of temper-board round-trip durations. Hit-cap escalation surface (per R5 rule 3) is also implementer's discretion; the doc fixes only the policy, not the CLI.
- [Affects R2][Technical] Congestion-heatmap aggregation: whether router_v6 produces a usable heatmap that maps cleanly to a `KeepoutConstraint` rectangle, or whether the workstream derives a congestion bounding-box itself from the unrouted-net geometry.
- [Affects R3][Technical] Incremental-solver fixed-vs-fresh-model: if OR-Tools' `push()/pop()` doesn't preserve warm-start performance for this constraint class, every round-trip builds a fresh model with a `model.AddHint` from the previous placement — verified during implementation. Round-2 residual concern #1: this is the load-bearing unverified constraint determining whether ≤1s re-solve budget is achievable at all.
- [Affects R2][Needs research] Whether adding `AnchoredConstraint` on a critical pin (F2 class 3) is empirically effective (forces a topologically-preferable placement) or produces infeasibility (the pin's optimal route is unavailable because the surrounding components must yield) — only resolvable by running the loop and reading the data.
- [Affects R2][Low-confidence / round-2 FYI #3] Feedback vocabulary (4 documented classes) may miss router_v6 failure modes (via collisions, differential-pair mismatch, power-plane violations); workstream defines a catch-all: "router_v6 failure not classified → escalate to operator" rather than silently passing by. Implementer's discretion to extend the vocabulary during implementation, but the catch-all is the floor.
- [Affects R4][Deferred question #2 from cross-doc] What autorouter-completion-rate does router_v6 achieve on a CP-SAT placement *without* the feedback loop? If router_v6 already achieves high completion on placements, the entire feedback loop may be unnecessary — round-2 deferred question #2 surfaces this as load-bearing. Implementation verifies empirically before committing to the loop build-out.
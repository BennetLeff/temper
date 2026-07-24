---
title: "feat: Close the Placer/Router Honesty Tangent — Halt Hygiene Leaves and Pivot to Fab-Ready"
type: feat
status: requirements-only
date: 2026-07-24
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
---

# feat: Close the Placer/Router Honesty Tangent — Halt Hygiene Leaves and Pivot to Fab-Ready

## Goal Capsule

**Objective:** Verify the already-shipped forced-segment fail-closed
generalization (commit `f53aa042` + `_astar_reconstruct.py:191` /
`_adapter_convert.py:833` / `_adapter_types.py:113` referencing
`docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md`), ship the
DRC/ERC anti-false-zero guard (`2026-07-23-001`), re-measure the real A*
router frontier, record it in `docs/STRATEGY.md`, and then **deliberately halt
opening new placer/router hygiene leaves** so planning pivots to move 2
(fab-ready board) without the "we should re-check the router numbers first"
caveat outstanding.

**Product authority:** Strategic sequencing — move 1 is the precondition for
moves 2, 3, and 4 in the Strategy-Level Move Set added to `docs/STRATEGY.md` on
2026-07-24. It is owned there, not in any leaf plan.

**Open blockers:** The forced-segment fail-closed generalization is
**already shipped** — the plan at
`docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md`
(shorter-ID-sibling of this artifact) implemented R1–R3 of the
`2026-07-24-router-forced-segment-fail-closed-requirements` brainstorm and
the code comments confirm no net class produces forced segments anymore. R2
(re-measurement) can proceed immediately; R1 collapses from "ship a
dependency" to "verify the already-shipped dependency."

---

## Problem Frame

The last two weeks of work are almost entirely one subtree: placer/router
correctness hygiene and measurement trust. Leaf after leaf —
forced-segment fail-closed (today), property-test hardening, mock-boundary
audit, dead-parameter wiring sweep, router design-rules wiring (the 400V HV
bus never had real clearance), finish-the-board DRC/ERC guard, pyo3 0.23→0.29,
zone pours default-on. These are downstream of one correct belief — *the
placer/router numbers must mean what they say before acting on them* — but the
belief has become self-perpetuating: each leaf surfaces a new "wait, is THIS
number lying to me?" and the strategy-level moves never resume.

Compounding the tangent: the **frontier itself was wrong**. The historical
"24/24 routed" figure found in `ROUTER_V6_VERIFICATION_REPORT.md`, the
`2026-07-11` handoff, and the `2026-06-23` closure tests refers to the
**piantor benchmark board**, not the temper production board
(`pcb/temper.kicad_pcb`). The honest temper frontier is **151 total nets,
~95 A*-routable signal nets, 72/95 routed today** (per commit `f53aa042`,
which restored the lost `_should_route()` filter). The 24/24 figure in
planning context was itself a measurement-integrity gap; it is now corrected
and recorded in `docs/STRATEGY.md` Current Board Closure State section.

The honesty discipline is right. The tangent is the problem.

---

## Requirements

### Forced-segment fail-closed generalization (already shipped — verify, rebuild, re-measure)

- **R1.** The plain A* router's forced-segment fallback fails closed for
  every net, not just HV/AC-class ones — **already shipped** per commit
  `f53aa042` and code comments in `_astar_reconstruct.py:191`
  (`_allow_forced_segments`), `_adapter_convert.py:833-834`
  ("no net class produces forced_segment_count > 0 anymore"), and
  `_adapter_types.py:113-114` ("no net class produces a forced segment
  anymore (all fail closed)"), all referencing the sibling plan
  `docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md`. Move 1's
  action on R1 is **verify the already-shipped generalization** stands — no
  net class is silently exempted — not ship a new dependency. Trace:
  `@req(this-plan, R1)`.
- **R2.** A **live re-measurement** of the temper production board is the
  first execution step of move 1 (R1's precondition is satisfied). The
  honest post-fail-closed A*-completion number (possibly lower than 72/95),
  plus the unchanged honest DRC frontier (381), plus ERC's status (currently
  `UNMEASURED` per `2026-07-23-001` U2 not yet shipped), are captured into
  `docs/STRATEGY.md`'s Current Board Closure State section as the recorded
  frontier the pivot happens against. Trace: `@req(this-plan, R2)`.

### Halt criterion — frontier-recorded (carry-forward gate)

- **R3.** **Recording the re-measured frontier in `docs/STRATEGY.md` IS the
  halt.** Once the post-fail-closed completion number, the DRC frontier, and
  the ERC status are written into the Current Board Closure State section —
  regardless of whether the anti-false-zero CI guard has caught a regression
  yet — opening new placer/router hygiene leaves stops. The CI guard
  (`2026-07-23-001` U3) handles future drift mechanically; the recorded
  frontier handles today's planning decisions. Rationale: the user-chosen
  halt frame — a trustworthy frontier on record, not a deployed mechanism.
  Trace: `@req(this-plan, R3)`.

### Floor deferral — per-gate (move 1's halt is for fab-adjacency, not % completion)

- **R4.** The halt fires only if **all hard-safety nets are routed on the
  re-measured frontier**, regardless of overall completion percentage: any
  HV/LV creepage-path net, any protection-circuit sense net (OCP sense
  resistor return, OVP divider node, UVLO sense net), and any gate-drive net
  that is unrouted causes the halt NOT to fire — the unrouted hard-safety
  net is escalated to a **separate routing-recovery track** (per move 2
  R13), which move 2 consumes as a precondition via its
  connectivity-coverage verdict gate. The hygiene-tangent halt is deferred
  until those hard-safety nets are recovered. Rationale: a single
  percentage floor (e.g. the original 60/95) reproduces the single-number
  anti-pattern move 2's verdict layer is explicitly designed to kill
  ("`24/24`-style figures invite stale-figure-in-wrong-context drift"); a
  per-gate floor aligns move 1's halt with move 2's discipline and means a
  real safety blocker (an unrouted HV creepage path) blocks the halt where
  40 unrouted non-critical signal nets would not. Trace: `@req(this-plan, R4)`.
- **R5.** The floor is evaluated per **hard-safety net class**, not against
  the 151 total nets or the ~95 A*-routable subset as an aggregate.
  Power/ground/return rails handled by hybrid pour+stitch
  (`2026-07-22-001`) are subject to the same per-class check (a rail that
  pour+stitch fails to cover counts as unrouted). Trace: `@req(this-plan, R5)`.

### Halt scope — what does and does not stop

- **R6.** The halt covers ONLY the self-perpetuating "is the number itself
  lying to me" track: forced-segment fallback, mock-boundary blind spots,
  dead-parameter sweeps, property-test hardening, design-rules-wiring gaps,
  net-count provenance errors (the 24/24-in-temper-context bug this artifact
  just closed). No new leaf in that track is opened after R3 fires.
  Trace: `@req(this-plan, R6)`.
- **R7.** AGENTS.md **R22** (bug-triage rule) still fires: if the new gates
  surface a **real safety defect** — e.g. the DRC guard catches an actual
  creepage violation between HV and LV nets — a triaged bug report is
  produced and any fix is in-scope for move 1, subject to the **safety-defect
  classifier** below. Architectural fixes are deferred as a separate
  follow-up, never inlined. The halt is over opening new
  *measurement-hygiene* leaves, not over fixing real hardware-safety
  defects the measurement correctly surfaces. Trace: `@req(this-plan, R7)`.
- **R7a. (safety-defect classifier — required, not optional)** Any fix
  touching a protection-gate code path — OCP/OVP/THM/UVL threshold,
  comparator, latch SET/RESET, transition-table FAULT entry, NTC LUT,
  sense-resistor net — is classified **safety-adjacent** regardless of line
  count (a "trivial" sign flip on an OCP comparator inverts the protection
  and silently defeats it; the trigger is touching the path, not the diff
  size). A safety-adjacent fix requires (a) a post-fix regression test that
  asserts the protection still trips at the rated threshold and time, and
  (b) a second reviewer sign-off recorded in the bug report. Only fixes on
  non-protection paths retain the plain R22 trivial classification. The
  halt never blocks a safety-adjacent fix; it never accepts a
  safety-adjacent fix without the classifier's regress + sign-off.
  Trace: `@req(this-plan, R7a)`.
- **R8.** Re-routing nets that flip to unrouted under R1's fail-closed is
  explicitly out of scope for move 1 — it is ripup-reroute algorithm work
  and feeds the deferred bucket, not the halt. Trace: `@req(this-plan, R8)`.

---

## Acceptance Examples

- **AE1 — Covers R1, R2, R3.** Given forced-segment fail-closed generalization
  has shipped, when a re-measurement runs on `pcb/temper.kicad_pcb`, the
  honest completion count (e.g. 68/95, NOT a fabricated 72/95) is written into
  `docs/STRATEGY.md` Current Board Closure State, at which point the halt
  fires and no new hygiene leaf is opened in the next planning round.
- **AE2 — Covers R3, R6.** Given the frontier has been recorded, when an
  engineer proposes a new leaf to "make the router numbers even more
  trustworthy," the proposal is deferred to the move 2 backlog or rejected
  outright — the halt is active. The CI guard catches future drift without
  manual hygiene.
- **AE3 — Covers R4, R5.** Given the re-measurement shows the OCP
  sense-resistor return net is unrouted (a hard-safety net), the halt does
  NOT fire even if overall completion is 90/95 — the unrouted hard-safety
  net is escalated to the separate routing-recovery track (per move 2 R13),
  which move 2 consumes via its connectivity-coverage verdict gate, and
  the hygiene-tangent halt is deferred until that net is recovered.
- **AE4 — Covers R7, R7a.** Given the DRC guard catches a real HV-to-LV
  creepage short on the production board, a triaged bug report is produced
  per AGENTS.md R22; the fix is classified safety-adjacent (touches the
  creepage path), triggering a regression test asserting the creepage still
  rules out at the spec limit + a second-reviewer sign-off recorded in the
  bug report; the halt is paused while the safety-adjacent fix lands.
- **AE5 — Covers R8.** Given three signal nets flip to unrouted under R1's
  fail-closed, those nets are added to the deferred re-routing backlog —
  move 1 does not start ripup-reroute algorithm work to recover them; that
  is the separate routing-recovery track's scope (or a deferred bucket
  owned by that track, not by move 2's verdict work).

---

## Success Criteria

- The re-measured post-fail-closed frontier is recorded in `docs/STRATEGY.md`.
- The CI anti-false-zero guard (`2026-07-23-001` U3) is shipped (whether or
  not it has fired on a regression yet).
- After R3 fires, no new placer/router hygiene leaf is opened in the next
  planning round — planning pivots to move 2.
- If R4's per-gate floor condition unrecovered (any hard-safety net still
  unrouted), the pivot is deferred and the unrouted net feeds the
  separate routing-recovery track (per move 2 R13), which move 2 consumes
  as a precondition via its connectivity-coverage verdict gate — that
  outcome is also success (the halt did not falsely fire on a board not
  ready to pivot from).
- A real safety defect surfaced by the new gates during move 1 gets a
  triaged bug report and a fix per AGENTS.md R22 + R7a's safety-defect
  classifier, never blocked by the halt.

---

## Key Decisions

- **Frontier-recorded halt, not mechanism-deployed halt.** The user-chosen
  halt frame: a trustworthy frontier figure on record, not a CI mechanism
  that has earned its keep by firing. The CI guard still ships — it handles
  future drift mechanically — but the pivot is gated on the recorded
  frontier, not on the guard catching a regression. Rationale: the
  recorded frontier is what move 2 anchors its fab-ready checklist on;
  waiting for a guard to catch a real regression delays the pivot on a
  contingent event that may not happen.
- **Per-gate floor, not percentage floor.** The original 60/95 percentage
  floor reproduces the single-number anti-pattern (`24/24`-style figures
  invite stale-figure drift). The per-gate floor (any hard-safety net
  unrouted blocks the halt) aligns move 1's halt with move 2's per-gate
  verdict discipline and means a real safety blocker (an unrouted HV
  creepage path) blocks the halt where 40 unrouted non-critical signal
  nets would not. Floor-failure escalates to the separate
  routing-recovery track (per move 2 R13), not to move 2's verdict scope —
  move 2 explicitly disclaims router/placer algorithm work.
- **Halt scope is measurement hygiene only; safety-defect fixes are
  safety-classified.** AGENTS.md R22 safety-defect fixes are explicitly
  carved out — the halt never blocks fixing real hardware-safety defects
  the measurement correctly surfaces — AND the safety-defect classifier
  (R7a) ensures trivial-looking fixes on protection-gate code paths are
  not silently absorbed as "trivial" but require regression-test +
  second-reviewer sign-off. Architectural fixes defer per R22.
- **Re-routing the newly-unrouted is deferred to the separate
  routing-recovery track.** Move 1 is measurement honesty + halt, not
  router algorithm improvement. Routed-net recovery feeds a separate
  routing-recovery track (the same one floor-failure triggers), NOT
  move 2's verdict scope and NOT "move 2+ as needed" — move 2
  explicitly disclaims router/placer algorithm work per its R13.
- **The stale 24/24 figure is itself a hygiene defect this move corrects.**
  The "24/24 routed" figure carried forward from the piantor benchmark board
  was a measurement-integrity gap — it had no business anchoring temper
  planning. Correcting and recording the real frontier (151 / ~95 / 72 today)
  in `docs/STRATEGY.md` is in-scope for move 1; it is the canonical example
  of the kind of honesty work move 1 *does* complete before halting, and the
  anti-pattern the halt is designed to stop from recurring.

---

## Scope Boundaries

**In scope:**
- Verifying the already-shipped forced-segment fail-closed generalization
  (R1 — no net class silently exempted).
- Re-measuring and recording the frontier (R2).
- The halt criterion (R3), its per-gate floor (R4, R5), and scope (R6, R7, R7a, R8).
- Correcting the stale 24/24-in-temper-context figure in `docs/STRATEGY.md`.
- Shipping the DRC/ERC anti-false-zero guard (`2026-07-23-001` U1–U3) —
  already planned; move 1 treats it as a dependency landing, not new design.
- R22-class safety fixes surfaced by the new gates, subject to the R7a
  safety-defect classifier.

**Out of scope:**
- DRC emitter cleanup (the 381-violation frontier) — feeds move 4
  (fabrication + mechanical + cert-lab track) and a board-level DRC
  reduction follow-up, not move 1.
- Re-routing nets that flip unrouted under R1 — deferred (R8) to the
  separate routing-recovery track that floor-failure also triggers; NOT
  move 2's verdict scope.
- Router pathfinding algorithm improvements (ripup-reroute negotiation tuning,
  4th-layer addition, congestion-loop rework) — none in move 1.
- Forced-segment fail-closed *re-design* — already shipped per commit
  `f53aa042` and sibling plan `2026-07-24-001-fix-forced-segment-fail-closed-plan.md`;
  R1 is verification of the already-shipped change.
- The fab-ready board pivot itself — that is **move 2**, owned by its own
  brainstorm artifact.
- The firmware + hardware validation track — that is **move 3**, owned by
  its own brainstorm artifact.
- Full IEC 60335-1 compliance certification — separate lab activity.

---

## Dependencies / Assumptions

- Depends on the forced-segment fail-closed generalization — **already
  shipped** (commit `f53aa042` + `_astar_reconstruct.py:191` / `_adapter_convert.py:833`
  / `_adapter_types.py:113`, per sibling plan
  `2026-07-24-001-fix-forced-segment-fail-closed-plan.md`).
- Depends on the DRC/ERC anti-false-zero guard (`2026-07-23-001` U1–U3)
  shipping for future-drift handling; U3 specifically lands the CI
  integration. U2 (ERC code path) is currently unshipped and is the
  thing that flips ERC from `UNMEASURED` to a real number in the recorded
  frontier.
- Assumes the re-measurement can run on the current Linux CI runner per the
  portable `kicad-cli` config that `2026-07-23-001` U1 ships.
- Assumes `pcb/temper.kicad_pcb` is the canonical board for the frontier
  re-measurement — not the piantor benchmark.
- The per-gate floor's "hard-safety net" enumeration (HV/LV creepage paths,
  protection-circuit sense nets, gate-drive nets) is reviewed against the
  `HIGH_VOLTAGE_CLEARANCE_SPEC` and `STRATEGY.md` protection gates at
  planning time; the enumeration is the engineering invariant, the halt
  criterion is its application.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R4][Needs research] The exact set of "hard-safety nets" the
  per-gate floor evaluates — proposed: HV/LV creepage-path nets
  (`HIGH_VOLTAGE_CLEARANCE_SPEC` domains A/B/PE crossing the isolation
  barrier), protection-circuit sense nets (OCP sense-resistor return,
  OVP divider node, UVLO sense net, NTC thermistor nets), and gate-drive
  nets. The enumeration is reviewable at planning time against the
  schematic netlist — it is not a free parameter.
- [Affects R2][Technical] Whether the re-measurement runs once
  post-fail-closed or is staged across forced-segment-only and
  forced-segment-plus-ERC-unblocked states. The latter produces two frontier
  snapshots; the halt fires after the more complete one.

---

## Sources & References

- Strategy entry point: `docs/STRATEGY.md` Current Board Closure State
  (added 2026-07-24) and Strategy-Level Move Set.
- Forced-segment fail-closed design:
  `docs/brainstorms/2026-07-24-router-forced-segment-fail-closed-requirements.md`
- DRC/ERC anti-false-zero guard: `docs/plans/2026-07-23-001-feat-finish-the-board-drc-erc-guard-plan.md`
- Net-count provenance correction: commit `f53aa042` (restored `_should_route()`;
  measured 72/95 on temper production board, confirmed piantor ≠ temper).
- Hybrid pour + trace-stitch (high-fanout net handling):
  `docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md` (completed).
- Stale-figure provenance: `packages/temper-placer/docs/ROUTER_V6_VERIFICATION_REPORT.md`
  (24/24 = piantor_right), `docs/handoffs/2026-07-11-finish-the-board-agent-brief.md`
  (carried 24/24 into temper context incorrectly).
- AGENTS.md R22 bug-triage rule (in-scope trivial fix vs deferred architectural).
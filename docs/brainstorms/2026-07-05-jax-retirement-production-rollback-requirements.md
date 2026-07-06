---
date: 2026-07-05
topic: jax-retirement-production-rollback
---

# JAX Retirement: Production-Rollback Framing

## Summary

Delete the JAX descent stack (optimizer, losses, multi-seed, C-CAP-as-init, weight-tuning apparatus, placement-init experiments), close the five placement-init worktrees, and surface `--placer jax-deprecated` as a *production-rollback path for non-corpus boards* — not as a parity-gate bridge. Per the umbrella's discipline, parity was skipped (see `docs/brainstorms/2026-07-03-cp-sat-feasibility-first-placer-paradigm-swap-requirements.md`); the rollback window's *reason* changes accordingly. Decisive result: deletion PR lands green and CP-SAT is the sole default placer.

---

## Problem Frame

The CP-SAT feasibility spike and the implementation report's 652/652 audit pass settle the technical question; the umbrella settles the strategic question (parity is theater, swap is decided on the structural argument). The retirement PR is the act of closing the gap between strategic decision and codebase state.

Two prior framings of this work were overridden, and the deviations are recorded:

1. **The original `2026-07-03-001` plan's U9** framed the `--legacy-jax` rollback window as a parity-gate bridge: keep JAX until CP-SAT beats it on the oracle, then delete. The doc review's "no-recovery deletion" finding extended that into "keep `--legacy-jax` for one release cycle even after parity passes, in case a non-corpus board surfaces a CP-SAT pathology." That extension survives — but its *rationale* shifts (see Key Decisions).
2. **The brainstorm-doc decision (`2026-07-03-cp-sat-feasibility-first-placer-paradigm-swap-requirements.md`)** skipped parity entirely as *theater*. The "experimentation phase precedes deletion" framing — both the in-flight `2026-07-02-001` multi-seed experiment AND oracle parity as simultaneous gates — was set aside.

The current framing inherits the rollback window's *duration* (one release cycle) from the doc review, but the *reason* becomes "production rollback on a non-corpus board." Parity is no longer the gate; calendar and corpus-confidence are.

What *also* lands here, per the umbrella's R1: **the five placement-init worktrees close** (ccap, dpp, hierarchical, thermal, constraint-passthrough). Each was a JAX-init experiment, all mooted by the swap. Closing them is part of the retirement PR's scope, not a separate workstream — they are the dead branches of the pre-swap mental model.

---

## Actors

- A1. **The deletion PR** — reverse-topological removal of `optimizer/`, `losses/`, `placement/`, `loss_bridge.py`, `heuristics/force_directed.py`, plus the modification list the doc review established (router_v6/pipeline.py, pipeline/, ablation/, adapters/, regression/, validation/, pcl/).
- A2. **`--placer jax-deprecated` (the rollback flag)** — retained one release cycle; *rationale* shifts to production-misroute recovery.
- A3. **Five placement-init worktrees** — closed, not landed. Each is documented as mooted inherited infrastructure, not reproducible from the current state.
- A4. **CI** — the 5,209-test collection must pass after the deletion.

---

## Key Flows

- F1. **Reverse-topological deletion per U9**
  - **Trigger:** Retirement PR opens.
  - **Actors:** A1, A4
  - **Steps:** Execute the deletion list from `docs/plans/2026-07-03-001-feat-cp-sat-feasibility-first-placer-plan.md` U9 (already extensive — extended in the doc-review fixes to include router_v6/pipeline.py, pipeline/, ablation/, adapters/, regression/, validation/, pcl/ as *Modify* entries, with the verification grep patterns covering `placement\.` and `from\.\.\.`); resolve the 22 surviving module import wraps to real refactors (the wraps are graceful degradation per the session report, not final state); run the 5,209-test collection on CI.
  - **Outcome:** Deletion PR green; CP-SAT sole default placer; `--placer jax-deprecated` retained as rollback path.
  - **Covered by:** R1

- F2. **`--placer jax-deprecated` rationale shift**
  - **Trigger:** Same PR — the rationale-update is part of the deletion decision-log, not a separate unit.
  - **Actors:** A2
  - **Steps:** After the optimizer/ directory is deleted, the flag can no longer dispatch JAX (the doc-review finding "No-recovery deletion" — and the round-2 finding in the comprehensive session report that the flag literally can't work post-deletion). It becomes a no-op deprecation warning: prints "the JAX placer has been removed; CP-SAT is the sole placer.  If you reached this flag for production-rollback reasons, file an issue with the board's PCL config and the routed-PCB file."  Records the user's intent without enabling the rollback path the deletion removed. The rollback window's *duration* (one release cycle) is preserved — it now bounds *how long the deprecation warning persists in the CLI*, not *how long JAX stays in the tree*. The session report's correction (round-2 finding #2) is incorporated.
  - **Outcome:** The flag exists for one release cycle as a UX placeholder, then is removed in a follow-up; no actual rollback code is retained.
  - **Covered by:** R2

- F3. **Placement-init worktree closure**
  - **Trigger:** Same PR (or, if deletion PR cleanliness requires it, a sibling PR landing same-day).
  - **Actors:** A3
  - **Steps:** Close `feat/placement-init-ccap`, `feat/placement-init-dpp`, `feat/placement-init-hierarchical`, `feat/placement-init-thermal`, `feat/placement-init-constraint-passthrough` without merging. Each closure's commit-message rationale: "JAX-init experiment mooted by paradigm swap; constraint-passthrough landed via #121's U5 (PlacementState.from_positions_dict), the others do not surface."  Record in `docs/solutions/architecture-patterns/` or via the existing `ce-compound-refresh` framing, whichever the implementer finds lower-friction. The `physics-derived-oracle` and `human-reference-corpus-oracle` worktrees are *not* part of F3 — F5 of the umbrella handles them.
  - **Outcome:** Five dead branches closed; remaining worktrees represent the post-swap mental model only.
  - **Covered by:** R3

---

## Requirements

- R1. The reverse-topological deletion per U9 of `docs/plans/2026-07-03-001-...` lands with the doc-review-extended Modify list and the four-pattern verification grep (`optimizer`, `losses`, `loss_bridge`, `placement`, `from\.\.\.`) returning zero matches. The 22 "wraps" (= `try/except ImportError` blocks around `from temper_placer.optimizer/losses/placement ...`) resolve to real refactors, not remain. The 5,209-test CI collection passes. **R1 is gated on the U0b spike (per Doc 2's first implementation unit) passing — see Dependencies.**
- R2. `--placer jax-deprecated` rationale is documented in the deletion PR's commit message and in the plan-deviation log as: **"production-rollback for non-corpus boards, NOT a parity-gate bridge."**  The flag is a no-op deprecation warning (not a dispatch to deleted code); it persists for one release cycle as UX affordance, then is removed in a follow-up tracked under `docs/plans/2026-07-03-002-...` Deferred-to-Follow-Up. The session-report round-2 finding is incorporated: post-deletion, the flag can't dispatch JAX because the optimizer is gone.
- R3. The five placement-init worktrees close *without merging*. The closure commit rationale for each is recorded. The five are exhaustively the dead JAX-init branches (verified via `git worktree list`); `physics-derived-oracle`, `human-reference-corpus-oracle`, and `viz-server` are *not* closed here — those are F5 (oracle hygiene) and out-of-scope (viz-server) workstreams.
- R4. **Decisive result** (per umbrella's Decisive-Result-Discipline): *the deletion PR lands green on CI, CP-SAT is the sole default placer, and the `--placer jax-deprecated` flag exists as a no-op warning*.  No parity number gates this; no experiment verdict gates this; the deletion PR's green status, CP-SAT-as-default, and the flag's no-op form *are* the decision's evidence.

---

## Acceptance Examples

- AE1. **Covers R1, R4.** Given the deletion PR is merged, when `temper optimize temper.kicad_pcb --config pcl/temper_induction.yaml` runs without `--placer`, CP-SAT runs by default and produces a placement (no JAX path reachable).
- AE2. **Covers R2.** Given the deletion PR is merged, when `temper optimize --placer jax-deprecated ...` runs, the CLI prints a deprecation warning naming the rationale (production-rollback-on-non-corpus-board) and exits without dispatching deleted code. The flag does not crash on `ImportError`.
- AE3. **Covers R3.** Given the deletion PR is merged, when `git worktree list` runs, the five `placement-init-*` branches are no longer present. The remaining worktrees (main, feat/cp-sat...) represent the post-swap mental model.
- AE4. **Covers R1.** Given the deletion PR's CI run, the 5,209-test collection completes with the CP-SAT tests passing and the JAX-only tests removed (not skipped — removed, since their imports no longer resolve).

---

## Success Criteria

- The deletion PR lands green; CP-SAT is the sole default placer; JAX descent stack gone from the tree.
- The five placement-init worktrees close — a future contributor pulling the repo sees only post-swap branches.
- The `--placer jax-deprecated` rationale is recorded as production-rollback, with the deviation from the original plan logged (parity-gate bridge → production-rollback, same duration, different reason — and the no-op-flag finding that further narrowed what the flag actually does).
- A future skeptic reading the deletion PR's commit message sees the structural argument cited (penalty ≠ constraint, feasibility-first as native form) — not a parity verdict — as the basis for the deletion.
- The 22 surviving module import wraps are *resolved* (real refactors), not remain as graceful-degradation try/except blocks.

---

## Scope Boundaries

- **Parity, in any framing** — out of scope.  Not re-litigated, not run, not recorded as a receipt.  See the paradigm-swap requirements doc.
- **`--placer jax-deprecated`'s *post-window removal*** — out of scope for this workstream; tracked under the existing calendar-gate plan's Deferred-to-Follow-Up. This workstream lands the no-op warning; the follow-up deletes it.
- **`physics-derived-oracle` and `human-reference-corpus-oracle` worktree disposition** — out of scope; covered by the Acceptance Gate + UNSAT UX workstream (`docs/brainstorms/2026-07-05-acceptance-gate-real-drc-and-unsat-ux-requirements.md`).
- **`viz-server` worktree** — out of scope entirely; not a JAX-init branch.
- **JAX/optax/flax removal from `pyproject.toml`** — in scope *only if* the verification grep returns zero survivors after deletion of the optimizer/losses/placement paths. Physics-oracle and `core/state.py` may still import JAX during the strangler's tail; the post-U9 dependency audit (per the existing plan) determines this.
- **The implementation-unit details of U9** — out of scope for this doc; U9 of the existing plan is the implementation spec. This doc adds the worktree-closure, the rationale-shift, and the no-op-flag refinement.
- **Tol=0 + JAX-deleted deadlock surface (per round-2 review finding #11)** — under Doc 2's hard-loop-area-ceiling (tol=0 per L_loop derivation) AND Doc 3's no-auto-loosening-for-routability rule AND this doc's JAX deletion, a board that CP-SAT legitimately cannot place within the physics-grounded constraint set has no automated recourse.  This is honest *by design*: the constraints are physics, not preferences.  The surface is *negotiation-with-documentation*, not auto-loosen — see the rollback-via-git-tag scope above; Doc 2's PCL-`because`-text override path (option a, with re-derived physics justification) is the operator's manual mechanism.  This doc explicitly *does not* add a hidden auto-loosen knob.  The honest stance: an UNSAT on a legitimate board is a real signal (the board is infeasible at the physics limits), and the operator gets the surfacing per Doc 4's UNSAT UX, not a silent compromise.

---

## Key Decisions

- **`--placer jax-deprecated` rationale: production-rollback, not parity bridge** — the original plan (`2026-07-03-001`) framed it as a parity-gate bridge (one release cycle after parity passes); the paradigm-swap brainstorm skipped parity (theater); the umbrella re-frames the rollback window's *reason* as production-misroute recovery on non-corpus boards.  Same one-release-cycle *duration*, different *justification*.  This is a deviation from the original plan, recorded here as a decision-log entry (same shape as the `--legacy-jax` override's decision log in the original plan).
- **No-op deprecation warning, not active rollback dispatch** — per the session-report round-2 finding: the flag can't dispatch JAX after the optimizer is gone.  It exists as a UX placeholder, not as a real fallback.  This sharpens the rollback window: it's not "JAX stays available for one release"; it's "the deprecation warning persists for one release."  The actual *rollback* mechanism for a production misroute is "checkout the previous git tag" — not the flag.
- **Rollback-via-git-tag scope, made explicit (per round-2 #13):** git-tag rollback resurrects the *tool* — it works for boards already designed against the prior (deleted-JAX) tool by checking out that tag. **It does not work for a board whose PCL spec uses constraint types JAX never supported** (LOOP_AREA-as-hard-ceiling, discrete rotation). For such a board, if CP-SAT returns UNSAT, the operator picks one of: (a) hand-edit the PCL to a *documented* higher-ceiling value with re-derived physics justification (see Doc 2's tolerance-override surface — the system freezes a physics-informed default; the human can override with explicit re-derivation), (b) operate with the pre-rotation-placement flow (subset of constraint types), (c) escalate via Doc 4's UNSAT UX surface for human resolution. There is no tool-level rollback that helps a board the prior-tag tool can't address either — that's the honest scope of the "no-rollback-beyond-git-tag" stance. This surface is *documented* here, not buried in the deprecated-flag's deprecation message.
- **Five placement-init worktrees close without merge** — they are dead JAX-init experiments; landing them would re-introduce the pre-swap code paths.  Close-not-merge is the only faithful disposal.  `constraint-passthrough`'s useful payload (constraint-passthrough as `PlacementState.from_positions_dict()`) already landed in #121's U5 — closing the worktree loses nothing.
- **22 import wraps resolve to real refactors in this PR** — the session report's "graceful degradation, not final state" framing is the trigger.  The deletion PR is incomplete while wraps remain; the wraps only existed as a working state during the strangler transition.  Resolving them is in-scope here.
- **`pyproject.toml` JAX dependency audit** — gated on the post-deletion grep; if `import jax` survives only in `core/state.py` (the `from_positions_dict` factory's internal wrap), JAX stays in deps. Full JAX removal is deferred to the dependency-audit follow-up; not gated by the calendar.

---

## Dependencies / Assumptions

- **Hard prerequisite: PR #121 merged.** All "existing infrastructure" claims in this doc — `score_placement()`, `PlacementState.from_positions_dict()`, `unsat.extract_unsat_core`, `external_oracle.py`, the `--placer` CLI flag — resolve against the post-#121 state, not against `main`. The round-2 doc review scanned `main` and reported these as missing; verifying in the worktree (`git -C .worktrees/feat/cp-sat-feasibility-first-placer grep ...`) returns them at the cited locations. This Dependencies line is the explicit prerequisite contract the docs previously embedded only implicitly.
- **U0b spike (per Doc 2) passes before this workstream's R1 executes.** Per the round-2 doc-review P0 finding ("8/8+rotation model unproven"): the original U0 spike validated 4/8 constraint types at ~62s; the 8/8 + 4-way rotation model that Doc 2 introduces has *not* been empirically validated. Sequencing: F2 ships a U0b extended spike (8 constraint types + rotation on temper) *first*; **F1's deletion list (R1) is gated on U0b passing.** F1's other units (R2 rationale shift, R3 worktree close) proceed in parallel with U0b. If U0b fails, the paradigm decision itself is at issue and F1 does not start — the spike is a verdict, not a formality.
- **The reverse-topological deletion list in U9 of `2026-07-03-001` is correct and complete** — verified during the round-1 doc review (findings #1, #2, #3 surfaced the codebase-conflict gaps and the gap-closing Modify entries). The 22 surviving import wraps enumerated in the session report are the residue after #121's U9 implementation; "wraps" = the `try/except ImportError` blocks around `from temper_placer.optimizer/losses/placement` imports in 22 surviving modules post-deletion; this workstream's R1 resolves each wrap to a real refactor (not a permanent degradation).
- **The 5,209-test collection size is stable as of #121** — recorded in the session report; the deletion PR will *reduce* this collection (JAX-only tests removed) and the new count is a positive output of the PR, not a regression.
- **`PlacementState.from_positions_dict()` and `score_placement()` survive the deletion** — both are in surviving modules (`core/state.py`, `metrics/external_oracle.py`) in the worktree; the CP-SAT placer's acceptance path does not import the deleted directories. Caveat: `core/state.py` still hard-imports `jax`, `jax.numpy`, and `from jax import Array` at module level in the worktree as of #121 — the module exists with JAX present; full JAX decoupling from `core/state.py` is the post-deletion dependency audit per the existing plan's Deferred-to-Follow-Up. The "caller doesn't need to `import jax`" claim holds (the caller's namespace stays clean via `from_positions_dict()`); the "module is JAX-free" claim does not hold yet.

---

## Outstanding Questions

### Resolve Before Planning

_None — U9 of the existing plan is the implementation spec; this workstream adds scope (worktree close, rationale shift, no-op refinement) but no unknowns._

### Deferred to Planning

- [Affects R1][Technical] Order of operations for resolving 22 import wraps — file-by-file refactor vs. one grouped pass; the planning agent decides based on what produces the cleanest diff for review.
- [Affects R2][Technical] Exact deprecation-warning copy — implementer's discretion; the bar is "names the rationale and instructs the user on what to do (file issue, use previous git tag)."
- [Affects R3][Technical] Whether each placement-init worktree gets a separate close commit or one grouped close commit — implementer's discretion; grouped is cheaper, one-per-worktree is more audit-trail-friendly.
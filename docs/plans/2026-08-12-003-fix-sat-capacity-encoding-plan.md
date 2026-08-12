---
title: Stage-3 SAT capacity encoding — resolve the vacuity, close the audit gap
type: fix
date: 2026-08-12
topic: sat-capacity-vacuity
artifact_contract: ce-unified-plan/v1
artifact_readiness: design-and-prototype
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# Stage-3 SAT Capacity Encoding — Resolve the Vacuity, Close the Audit Gap

## Goal Capsule

**Verdict, stated first, per
[`../brainstorms/2026-08-12-sat-capacity-vacuity-options.md`](../brainstorms/2026-08-12-sat-capacity-vacuity-options.md)
(read first; this plan does not re-derive its evidence).** At
`DEFAULT_BATCH_SIZE = 10`, `packages/temper-rust-router-core/src/encoding.rs:148`'s
guard means Stage 3's `AtMostK` capacity constraint is not encoded into CNF
for any channel whose capacity bound exceeds the batch's own net count
(mean **K ≈ 17.3–17.5**, independently re-derived, agreeing with the source
finding's K≈17). That much is the finding as given, and it is confirmed,
`path:line` exact. **The brainstorm's investigation goes one layer deeper**:
reading every `_create_*` constraint-generation function in
`model_builder.rs` shows nothing in the Stage-3 model, under net-batching's
actual call path, ever forces a `NetChannelVar` (a `uses_{net}_{channel}`
boolean) to be `true` — `Capacity` is upper-bound-only, `DiffPair` is a
biconditional satisfied by both-false, `LayerConstraint` is always
`allowed: false`, `ChannelSeparationConstraint` is never instantiated in
production code, and `_apply_pcl_constraints` — the one mechanism that could
add a forcing clause — is a no-op under net-batching because `_solve_subset`
never passes it a `pcl_constraints` argument. The all-`false` assignment is
therefore always satisfying, batched or monolithic, guard-firing or not —
consistent with **every recorded "0 conflicts, 0 decisions" result this
pipeline has ever produced, including the monolithic case where capacity
*is* encoded** (`docs/evidence/2026-07-27-stage3-model-and-rewrite.md:305`;
`docs/evidence/2026-08-07-sat-model-reduction-options.md` §7).

**This is no longer only a structural argument.** The brainstorm's §1.2
measured it directly this task: an instrumented production
`--net-batching` run, monkeypatching `_consume_capacity` to log
`uses_channels` content, showed **0 of 30 nets across 3 independent
batches** had any non-empty `uses_channels`, and `_consume_capacity`'s own
`consumed` accumulator stayed at length 0 throughout. **Not only is the SAT
capacity encoding vacuous — the cross-batch greedy bookkeeping
(`_consume_capacity`/`_shrink_channel_widths`) that the finding-as-given and
`2026-08-12-002` both name as the thing that actually enforces capacity is
also receiving zero data.** Neither Stage-3 mechanism does anything to
channel capacity in production; whatever keeps this board's copper from
colliding is Stage 4's per-net occupancy-grid A* alone. **This plan's first
units exist to extend that 30-net sample to the full board (110 nets, all
11 batches) and make it a standing, repeatable measurement** — a 3-batch
result is strong evidence, not proof for the other 8 batches, and the
deletion this finding points toward (Option C in the brainstorm) does not
run until that full measurement confirms it.

**Independent of that question, one thing is already certain and already
actionable**: `docs/solutions/logic-errors/unsound-atmostk-capacity-
encoding.md` — the 2026-06-28 write-up for this exact constraint class —
claims its post-solve audit (`audit_result`) "runs unconditionally after
every Rust solve." It does not. `net_batching.py`, the production
`--net-batching` path, never imports or calls it (grep, zero hits) — only
the monolithic `RouteStage` path does
(`_pipeline_route.py:437-452`). This is a written correctness claim that is
false in the production configuration, independent of whether capacity is
ever actually over-allocated, and closing it does not require waiting on
any other finding in this plan.

**What this plan explicitly does not claim**: that the 499-505 `clearance`
DRC violations on the current board are caused by Stage-3 capacity
vacuity. Three independent, already-existing investigations
(`docs/evidence/2026-08-12-clearance-regression-route-vs-placement.md`,
`docs/evidence/2026-08-12-corridor-aware-plane-backbones.md`, and the
zone-count/no-backbone control experiment they cite) attribute the
regression to placement-density-driven F.Cu fragmentation, not to Stage-3
topology or channel-capacity bookkeeping. This plan does not touch
placement, Stage 4, or the clearance regression, and no unit below is
justified by "this will reduce the clearance count."

## Product Contract

### Summary

This plan does four things, in order, gated so the higher-risk units do not
start until the measurement they depend on exists:

1. **Make the vacuity finding a standing, full-board measurement, not a
   30-net sample** (U1, U2). The brainstorm's §1.2 found — on a 3-batch,
   30-net sample, this task, live — that `_consume_capacity` never
   received non-empty `uses_channels` under net-batching, using a
   throwaway, monkeypatched instrumentation run; it does not yet exist as
   a repeatable, reviewable measurement in the codebase, and it has not
   yet been run to completion (all 11 batches / 110 nets). U1 does both.
   U2 re-derives K on the **current** 204,490-edge skeleton (the source
   finding's K≈17 is from a 20,734-edge, pre-plane-fix skeleton — 9.9×
   smaller, per plan `2026-08-12-002`'s own flagged dependency) so the
   guard's real firing rate at `B=10` is known exactly, not carried over
   from a stale measurement.
2. **Close the audit gap** (U3, U4) — wire `audit_result` into the
   net-batching solve path, and correct the false "runs unconditionally"
   claim in the 2026-06-28 solution doc. Independent of U1/U2's outcome.
3. **Act on U1/U2's measurement, in either direction** (U5). If the
   structural finding holds — `uses_channels` is empty or near-empty in
   production batches — delete the vacuous `Capacity`-to-`AtMostK` CNF
   encode call and the already-dead `ChannelSeparationConstraint` path,
   and correct `net_batching.py`'s module docstring to state what is
   actually happening. If U1/U2 contradict the structural finding —
   `uses_channels` turns out to carry real data in production — this plan
   stops at U4 and reports that contradiction instead of deleting
   anything, because it would mean something not yet identified is
   deciding topology and the investigation needs to continue before any
   code changes.
4. **State the two rejected options explicitly, and why** (documented in
   §Options Considered, not implemented) — raising `DEFAULT_BATCH_SIZE`
   above K, and unconditionally fixing the guard — both predicted, on the
   structural finding, to grow the CNF with no board effect. Recommending
   against implementing either is itself part of this plan's contract.

### What would change the board — flagged deliberately

Mirroring `2026-08-12-002`'s own discipline: **U5's deletion is the only
unit in this plan capable of changing `temper_routed.kicad_pcb`, and it is
only correct if it changes nothing.** Its entire claim is "this code path
never affected output" — so byte-equality against the pre-change baseline
is the *correct* acceptance test for U5, unlike a change that alters what
gets encoded or decided (raising batch size, fixing the guard to always
fire), which plan `2026-08-12-002`'s R7 already establishes must never be
tested by byte-equality because it would be comparing two different
algorithms. This plan does not implement either of those; if a future plan
does, it inherits that rule, not this one's.

### Requirements

Requirement IDs are stable and become `@req(2026-08-12-003, Rn)`.

- **R1.** The live content of `uses_channels` per net, per batch, under a
  full production `--net-batching` route of `pcb/temper.kicad_pcb`, is
  measured and reported as a standing artifact — not a throwaway script.
  **Check:** a committed evidence doc (or a `[net-batching]` summary line
  extension, `TEMPER_BATCH_TRACE=1`-gated) reports, for every batch: net
  count, count of nets whose `uses_channels` is non-empty, and total
  channel references across the batch. Reproducible by a named command.
- **R2.** K is re-derived on the skeleton size actually in production
  today (204,490 edges per `2026-08-12-002`, itself flagged there as
  needing re-confirmation), not inherited from the 2026-07-27
  20,734-edge measurement. **Check:** either a full monolithic CNF build
  reports aux-vars/clauses-per-constraint on the current skeleton (same
  two-equation derivation as the brainstorm §1.1), or, if the monolith
  does not fit in memory even after `2026-08-12-002`'s U1/U2 representation
  fixes, a sampled per-channel `max_nets` computation across a
  representative subset of the 204,490 edges, with the sampling method and
  count reported.
- **R3.** `audit_result` (or an equivalent minimal capacity-focused check,
  see R5's conditional scope) runs after every batch-level `"sat"` result
  in `net_batching.py`'s solve path, not only in the monolithic
  `RouteStage` path. **Check:** `rg "audit_result" packages/temper-placer/src/temper_placer/router_v6/net_batching.py`
  returns a hit; a deliberately-constructed over-capacity fixture (a
  `ConstraintModel` with a `Capacity` constraint whose `terms` are forced
  true by a synthetic unit clause, bypassing the R5 question entirely)
  is confirmed to raise via the batch path the same way
  `_pipeline_route.py:437-452`'s existing test coverage confirms it does
  via the monolithic path.
- **R4.** `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`'s
  "runs unconditionally after every Rust solve" claim (`:88-90,122`) is
  corrected to state its actual coverage as of this plan's landing — either
  updated in place (once R3 lands, the claim becomes true again and needs
  no correction) or, if R3 is deferred, amended with an explicit erratum
  naming the net-batching gap. **Check:** the claim in the doc matches
  `rg "audit_result"` reality at the commit where this requirement is
  marked done.
- **R5.** The CNF-encoding fate of `InternalConstraint::Capacity` is decided
  **from R1/R2's full-board measurement, not from this plan's prior
  expectation** — though this task's own 3-batch/30-net sample (brainstorm
  §1.2) already found 0/30 nets with non-empty `uses_channels`, so the
  delete-branch below is the *expected* outcome; R1 exists to confirm it
  holds for the other 80 nets before anything is deleted on its strength:
    - If R1 shows `uses_channels` is empty or near-empty (a threshold of
      "under 5% of net-batches have any non-empty entry" is proposed, not
      binding — the unit that consumes this requirement sets the final bar
      from the actual distribution) **and** R2 confirms K remains
      structurally above what any plausible batch size would cross without
      itself becoming a different algorithm: delete the `Capacity` →
      `encode_at_most_k` call site in `encode_to_cnf`
      (`encoding.rs:145-155`) and the dead `ChannelSeparation` → 
      `encode_at_most_k` call site (`encoding.rs:206-236`, confirmed
      unreferenced by any production constructor, brainstorm §3). Keep
      `encode_at_most_k` itself (it is a general Sinz-encoder utility with
      its own exhaustive proof and tests; nothing in this requirement
      argues the function is wrong, only that its two call sites are dead).
    - If R1 contradicts the structural finding: this requirement is
      **not** executed. Instead, a new finding is written (§Outstanding
      Questions Q1) describing what R1 actually measured, and no deletion
      happens in this plan.
  **Check:** conditional on which branch fires, either (a) `rg "Capacity"
  packages/temper-rust-router-core/src/encoding.rs` shows no
  `encode_at_most_k` call site remaining for `InternalConstraint::Capacity`,
  plus R7's byte-equality test passes; or (b) no `encoding.rs` diff exists
  and the contradiction is documented instead.
- **R6.** `net_batching.py`'s module docstring (`:12-45`) is corrected to
  state the actual mechanism post-R5, not the pre-investigation framing.
  If R5's delete-branch fires, the docstring's "capacity is preserved... by
  explicit bookkeeping" claim is re-checked against R1's own measurement of
  that bookkeeping's actual input and corrected if it, too, needs
  qualifying. **Check:** the docstring's capacity claim and R1's measured
  reality agree, read side by side.
- **R7.** `DEFAULT_BATCH_SIZE` is not changed by this plan (mirrors
  `2026-08-12-002` R6). Any change crossing K is a distinct,
  board-changing algorithmic decision, needs its own baseline, and –
  per this plan's own §Options Considered — is not expected to matter on
  the structural finding, which is itself something a future plan would
  need to re-verify, not inherit.
- **R8.** U5 (the only unit capable of changing output) is verified by
  `temper_routed.kicad_pcb` byte-equality (`diff` empty, sha256 equal)
  against the deterministic baseline in
  `docs/evidence/2026-08-12-board-recipe-reproducibility.md`
  (168 footprints / 3,349 segments / 56 vias / 70 zones / 80/105 nets),
  for the full `--net-batching` recipe, on two concurrent runs. No other
  unit in this plan asserts board byte-equality as a pass/fail gate
  (R3/R4 are code/doc changes verified by test and inspection; R1/R2 are
  measurements with no code path that touches routing behavior).
- **R9.** `channel_skeleton.py` and all channel-skeleton geometry are out
  of scope (mirrors `2026-08-12-002` R8). If any unit's diff perturbs
  skeleton geometry, the unit is wrong and is reverted, not re-baselined.
- **R10.** Every deletion (U5's delete-branch) follows
  [`../migration-pipeline.md`](../migration-pipeline.md) stages 7–8 — oracle
  disposition declared explicitly. `encode_at_most_k`'s existing exhaustive
  proof/tests are **KEEP** (the function stays, general-purpose, its own
  correctness is not in question). The two call sites being deleted have no
  oracle of their own (they are call sites, not kernels) — **N/A**, not
  FREEZE/REIMPLEMENT/KEEP, and this plan states that explicitly rather than
  forcing a disposition that doesn't apply.
- **R11.** This plan's U1 measurement (per-batch `uses_channels` content)
  is emitted as a standing, always-available trace line
  (`TEMPER_BATCH_TRACE=1`-gated, matching `2026-08-12-002`'s R11 pattern for
  encoded-capacity-constraint counts) — not a one-off script — so a future
  regression in either direction (topology starting to carry real data, or
  the audit gap reopening) is visible without repeating this plan's
  research.

## Units

### U0 — Pin the baseline

Regenerate (or confirm still-current) the baseline artifact from committed
`pcb/**`, per `docs/evidence/2026-08-12-board-recipe-reproducibility.md`'s
own protocol (two concurrent runs, `diff` empty, sha256 equal). Nothing in
this plan with a board-facing check (R8) is verifiable without it.
**Verified by:** two concurrent runs matching the recorded 168/3,349/56/70/80
figures. **Effort:** 0.5 day (mostly wall-clock, ~350s/run), skippable if
the cited evidence doc's baseline is confirmed still current for the
commit this plan lands against.

### U1 — Standing measurement: does `uses_channels` carry data under net-batching? (R1, R11)

Add a `TEMPER_BATCH_TRACE=1`-gated per-batch line to
`run_net_batched_stage3` (`net_batching.py:1053-1150`) reporting, from the
same `topo = _topology_from_rust_result(...)` value already computed before
`_consume_capacity` is called: net count, non-empty-`uses_channels` count,
and total channel references. This is the exact measurement this task's own
throwaway probe took (monkeypatching `_consume_capacity` from outside, run
to 3 of 11 batches / 30 of 110 nets before deliberately stopping — see
brainstorm §1.2 for the raw output: 0/30 nets non-empty, `consumed` stayed
at length 0); U1 makes it a real, reviewable, permanent line instead of a
scratch script, and — the part the throwaway probe did not do — runs it to
completion across all 11 batches / 110 nets, not just the first 3. Record
the full result as a committed evidence doc.

**Verified by:** the trace line appears in a real `--net-batching` run's
output for every batch; the evidence doc records the full-board figures
(11 batches × up to 10 nets, or however many batches the current 108–110
net count produces) with the measurement method reproducible from the
command line alone. **Effort: 1–2 days.** Risk: low — this is instrumentation
only, no behavior change, so R8's byte-equality bar applies trivially (the
trace line is `TEMPER_BATCH_TRACE`-gated stderr output, not part of
`routed_pcb_content`).

### U2 — Re-derive K on the current skeleton (R2)

Using the same two-equation Sinz derivation as brainstorm §1.1
(aux-vars-per-constraint and clauses-per-constraint, both against the raw
model's own reported `n`), re-measure on the **current** 204,490-edge
skeleton rather than inheriting the 2026-07-27 20,734-edge figure. If
`2026-08-12-002`'s U1/U2 (Rust-native `ConstraintModel`, Rust→Rust handoff)
have landed by the time this unit runs, prefer building the real monolithic
model directly; if not, a stratified sample of channels (e.g., by
skeleton-edge length percentile, since capacity is width/length-driven)
with per-channel `max_nets` computed directly from
`((_cap * _sf) / min_width).floor()` — no CNF construction required for
this — is sufficient and cheaper.

**Verified by:** a reported K distribution (not just a mean) across the
current skeleton, with the sampling method and count stated; cross-checked
against the two-equation derivation if a full monolithic build is
available. **Effort: 2–4 days**, depending on whether `2026-08-12-002`'s
representation fixes have landed (if not, this unit may need to fall back
to the sampled `max_nets` approach exclusively, since building the full
monolithic model today costs 7.35GB per `2026-08-12-002`'s own measurement).

### U3 — Wire the audit into net-batching (R3)

Call `audit_result` (or a narrower capacity-only variant if R5's
delete-branch has already landed by the time this unit runs — auditing a
constraint that is no longer encoded is a no-op, so the audit's scope
should track R5's outcome, not run ahead of it) inside `_solve_subset`'s
per-batch `"sat"` path (`net_batching.py:1093-1097` and the singleton-retry
mirror at `:1144-1147`), matching `_pipeline_route.py:437-452`'s existing
pattern. Raise the same `RuntimeError` shape on violation.

**Verified by:** R3's fixture test (a synthetic over-capacity model,
forced via a unit clause that bypasses whatever R5 concluded about natural
forcing, so the audit's *own* correctness is tested independent of whether
real batches ever produce a violation); confirmed the audit fires
identically via both the monolithic and batched paths on the same
fixture. **Effort: 2–3 days.**

### U4 — Correct the false claim (R4)

Update `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`'s
"runs unconditionally after every Rust solve" line. Sequenced after U3 so
the correction can be "and now it does" rather than a bare erratum, unless
schedule pressure lands U4 first, in which case the erratum form is used
and superseded once U3 lands.

**Verified by:** the doc's claim and `rg "audit_result"` reality agree at
the commit where this requirement is closed. **Effort: 0.5 day.**

### U5 — Delete the vacuous encoding, or report the contradiction (R5, R6, R10)

Gated entirely on U1/U2's measurement (§Requirements R5's two branches).
**Do not start this unit until U1 and U2 have landed and been read.**

Delete-branch: remove the `Capacity` → `encode_at_most_k` call site
(`encoding.rs:145-155`) and the dead `ChannelSeparation` call site
(`encoding.rs:206-236`); update `net_batching.py`'s module docstring (R6);
update `CapacityConstraint`'s doc comment in `model_builder.rs:280-286`,
which currently cross-references the CNF encoding as the enforcement
mechanism — that cross-reference becomes stale the moment the CNF side is
deleted, and leaving it would recreate exactly this plan's own finding one
level down. Decide, and record, whether `create_capacity_constraints`
(the Rust-side `CapacityConstraint` *object* creation, not its CNF
encoding) is worth keeping as a data structure — R3's audit (if scoped to
still check capacity structurally rather than via CNF satisfiability)
needs the constraint objects to exist even if nothing encodes them into
clauses.

Contradiction-branch: no code change. Write the finding (what R1 actually
measured, and why it differs from the structural prediction) as a new
evidence doc, and stop.

**Verified by:** delete-branch — R8's byte-equality protocol, two
concurrent full-recipe runs, both `diff`-empty against the U0 baseline.
Contradiction-branch — the evidence doc alone; nothing to diff.
**Effort: 3–5 days delete-branch (mostly the byte-equality verification
protocol's wall-clock cost, ~350s/run × several runs); 1 day
contradiction-branch (write-up only).**

### Sequencing

```
U0 ──┬── U1 ──┐
     │        ├── U5 (gated on U1+U2's measurement)
     └── U2 ──┘
U3 ── U4                        (independent, can land in parallel with U1/U2)
```

**Total: U0–U2 3.5–6.5 days. U3–U4 2.5–3.5 days, parallel. U5 1–5 days
depending on which branch fires.** Honest range because U5's effort is not
knowable until U1/U2 report — that is the point of gating it.

## Options Considered, Not Implemented

Per the brainstorm's §4, two options were evaluated and are **not** units in
this plan, stated here so a future reader does not re-propose them without
the reasoning:

- **Raise `DEFAULT_BATCH_SIZE` above K (~18+).** Predicted, on the
  structural finding, to grow the CNF (more `AtMostK` aux vars/clauses)
  with no board-output change, because nothing forces a `NetChannelVar`
  true regardless of whether the constraint restricting it is present.
  This is a testable prediction, not yet a measured one — U1/U5's
  contradiction-branch is exactly the outcome that would revive this
  option. Not implemented here because implementing it before U1 would be
  spending CNF size to test a hypothesis U1 tests for free, as a read.
- **Unconditionally fix the guard (always encode `Capacity`).** Same
  objection, stronger — it would add CNF size at *every* batch size,
  including today's default, forever, for a constraint the structural
  finding says cannot bind. Reviving this is contingent on Option E2
  (wiring a real connectivity-forcing constraint) being pursued as its own,
  larger project — named in the brainstorm, explicitly out of scope here.

## Scope Boundaries

**Explicitly not in this plan:**

- **Wiring a connectivity/candidacy-forcing constraint into Stage 3**
  (brainstorm's Option E2) — the deeper fix that would make Stage-3
  topology selection a real decision problem again. This is a new
  constraint semantics change with its own correctness-proof obligation
  (in the mold of `unsound-atmostk-capacity-encoding.md`'s own three-layer
  fix), a materially larger project, and named here only so it is not
  lost. If U1 contradicts the structural finding, *that* result — not this
  plan — is what should motivate scoping E2's investigation.
- **The clearance/DRC regression** (499-505 violations). Explicitly not
  caused by this finding per three independent existing investigations
  (§Goal Capsule). No unit here touches placement, Stage 4, or zone
  generation.
- **`2026-08-12-002`'s own scope** (the Rust orchestration port, the
  memory representation fix, the subprocess-driver retirement). This plan
  depends on that plan's finding but does not re-scope its units; if
  `2026-08-12-002`'s U1/U2 land first, U2 here becomes cheaper (§U2's own
  note), but this plan does not block on it landing.
- **Raising `DEFAULT_BATCH_SIZE` or unconditionally fixing the guard** —
  see §Options Considered.
- **`channel_skeleton.py` / skeleton geometry** — R9.

## Dependencies / Assumptions

- **Assumes** `docs/evidence/2026-08-12-board-recipe-reproducibility.md`'s
  baseline (168/3,349/56/70/80) is still current for the commit this plan
  lands against; U0 exists specifically to not assume this silently.
- **Assumes** the structural argument (no forcing constraint on
  `NetChannelVar` under net-batching) generalizes from the code read to
  the live run — U1 is exactly the check that this assumption is not
  simply inherited.
- **Depends on** `2026-08-12-002`'s memory-representation fixes (its U1/U2)
  *optionally*, not required — U2 here has a fallback (sampled `max_nets`)
  that does not need the monolithic model to fit in memory.
- **Depends on** the recipe staying deterministic — every board-facing
  check in this plan (R8) is a `diff`; if determinism regresses, this plan
  is blocked, not degraded, exactly as `2026-08-12-002`'s own dependency
  states.

## Outstanding Questions

1. **If U1 contradicts the structural finding — `uses_channels` turns out
   non-empty in production batches — what *is* forcing those variables
   true?** Not answerable from this plan's own scope; the contradiction
   itself is the deliverable in that branch, and the follow-up
   investigation is a new task, not a unit added here after the fact.
2. **Does `create_capacity_constraints`'s object-level output remain worth
   computing if nothing ever encodes it into CNF?** (Raised in U5's
   delete-branch description.) If R3's audit is scoped to check the
   constraint objects directly (a structural check independent of CNF
   satisfiability) rather than via `assignments`, the object creation stays
   load-bearing for the audit even after CNF encoding is deleted. If not,
   `create_capacity_constraints` itself becomes a candidate for a
   **separate** future deletion — not this plan's, since R3 needs it as
   written here.
3. **Is `ChannelSeparationConstraint` worth deleting entirely** (the
   pyclass, not just its dead AtMostK call site), given it is confirmed
   unreferenced by any production constructor? Left as a smaller, separate
   cleanup — U5 only removes its CNF call site, not the class, since a
   class-level deletion has its own blast radius (Python re-exports,
   pyo3 registration) this plan did not audit.

## Sources / Research

- [`../brainstorms/2026-08-12-sat-capacity-vacuity-options.md`](../brainstorms/2026-08-12-sat-capacity-vacuity-options.md) — the finding, the K re-derivation, the structural argument, and the ranked options this plan implements
- `docs/plans/2026-08-12-002-feat-router-orchestration-rust-plan.md` (branch `spike/router-orchestration-rust`) — the original K≈17 finding, the memory-representation work this plan's U2 can optionally build on
- `packages/temper-rust-router-core/src/encoding.rs:21-30,139,148,183-236` — the guard, the two call sites U5 may delete
- `packages/temper-rust-router-core/src/audit.rs` — the audit U3 wires in
- `packages/temper-design-bundle/src/model_builder.rs:280-286,902-1073` — the constraint-creation functions establishing the structural finding
- `packages/temper-placer/src/temper_placer/router_v6/net_batching.py:12-45,221,456-487,1036-1150` — the module docstring U5 corrects (R6), the batch loop U1/U3 instrument
- `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:437-452` — the existing audit call site U3 mirrors
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — the false claim U4 corrects
- `docs/evidence/2026-08-12-board-recipe-reproducibility.md` — the U0/R8 baseline
- `docs/evidence/2026-08-12-clearance-regression-route-vs-placement.md`, `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md` — why this plan does not touch the clearance regression
- `docs/migration-pipeline.md` §Hard rules — R10's oracle-disposition convention

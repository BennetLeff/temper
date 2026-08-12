<!-- provenance: measured 2026-08-12, worktree /home/bennet/Desktop/temper-sat-capacity-vacuity,
branch spike/sat-capacity-vacuity, branched from origin/main @ 66a277d94. Read-only against
pcb/**; one instrumented diagnostic run of scripts/route_board.py --net-batching was executed
against a stripped-copper temp copy (route_board.py's own default behavior — it never writes
pcb/temper.kicad_pcb), output discarded, to measure live Stage-3 topology content. -->

# Is the Stage-3 SAT capacity encoding a bug, and what is K really? — options ranked

## Verdict, stated first

**Not a live correctness hole in the sense the finding implies, but the finding
undersells how vacuous Stage 3 actually is, and it exposes a false claim in the
codebase that is a bigger problem than the vacuity itself.**

**Headline, measured this task (§1.2), not inferred**: it is not only the
SAT `AtMostK` encoding that is vacuous at `B=10`. The cross-batch greedy
bookkeeping (`_consume_capacity`/`_shrink_channel_widths`) that the finding
and `2026-08-12-002` both name as the mechanism that *actually* enforces
capacity — **is also receiving zero data.** Across 3 independently-measured
batches (30 of 110 nets), every net's `uses_channels` came back empty, and
`_consume_capacity`'s `consumed` dict stayed at length 0. Neither Stage-3
mechanism — SAT or greedy — does anything to channel capacity in production.
The board's freedom from copper-on-copper collisions is enforced entirely
by Stage 4's per-net occupancy-grid A*, which has no notion of "channel
capacity" as a resource at all (§2). This reframes the whole question: the
finding-as-given asks "why doesn't SAT enforce capacity," and the honest
answer is "nothing in Stage 3 enforces capacity, under net-batching, and
the SAT vacuity was never the load-bearing half of that."

1. **The guard at `encoding.rs:148` is real and does what
   `docs/plans/2026-08-12-002-feat-router-orchestration-rust-plan.md` says**:
   at `DEFAULT_BATCH_SIZE = 10` (`net_batching.py:221`), the AtMostK capacity
   constraint is not encoded into CNF for any channel whose derived `max_nets`
   (mean **K ≈ 17.3-17.5**, independently re-derived below, agreeing with the
   plan's K≈17) exceeds the batch's own term count (≤10). Re-verified,
   `path:line` exact, unchanged from the plan.
2. **It goes deeper than the guard.** Reading `model_builder.rs`'s constraint
   creation end to end: under net-batching's actual call path
   (`net_batching.py:456-487`'s `_solve_subset`), **nothing in the Stage-3 CNF
   ever forces a `NetChannelVar` (a `uses_{net}_{channel}` variable) to be
   `true`.** Capacity constraints are `AtMostK` (upper-bound only).
   `DiffPairConstraint` is a biconditional (satisfied by both-false).
   `LayerConstraint` is always `allowed: false` in `create_layer_constraints`
   (`model_builder.rs:1024-1073`) — it forbids specific edges near a
   foreign-layer pin, it never requires one. `ChannelSeparationConstraint`
   is never instantiated anywhere in production code (confirmed by grep,
   §3). The one mechanism that *could* add a forcing/connectivity clause,
   `_apply_pcl_constraints` (`constraint_model.py:335-368`), is a no-op
   under net-batching because `_solve_subset` never passes `pcl_constraints`
   to `ModelBuilder` at all (`net_batching.py:469-476`). The all-false
   assignment to every `NetChannelVar` is therefore *always* a satisfying
   model, batched or monolithic, guard-firing or not. This is not
   inference — it is what "0 conflicts, 0 decisions" has meant every single
   time it has ever been measured on this pipeline, including the
   **monolithic, unbatched, capacity-encoded** case
   (`docs/evidence/2026-07-27-stage3-model-and-rewrite.md:305`,
   `docs/evidence/2026-08-07-sat-model-reduction-options.md` §7: *"Every
   full-board solve this pipeline has ever completed succeeded with 0
   conflicts, 0 decisions... The solver is not struggling to search; it has
   never had to search."*). Raising the batch size above K would not change
   this outcome (§4, Option A).
3. **The correctness argument for the greedy path is written down, and it
   describes a mechanism that is measured (§1.2) to be receiving no data
   to act on.** `net_batching.py`'s module docstring (`:12-45`) states
   plainly that capacity is enforced by `_consume_capacity`/
   `_shrink_channel_widths` bookkeeping. That claim was true of the
   *design*; §1.2's live measurement shows it is not true of the
   *production run* — the bookkeeping has nothing to bookkeep. The
   docstring is also honest that clearance/creepage/HV-SELV are *never* in
   Stage 3 at all, batched or not — enforced downstream in Stage 4's
   occupancy-grid A*, in a single whole-board pass, and **that** claim is
   corroborated by three independent evidence docs (§2) attributing the
   board's 499-505 `clearance` violations to placement-density-driven F.Cu
   fragmentation, not to Stage-3 topology or capacity bookkeeping. Greedy
   *over-allocation* specifically was checked directly against the live
   blocker and is **not** implicated — but not because greedy is correctly
   bounding anything; because greedy has nothing to over-allocate from.
4. **The one claim in the repository that is actually false**: the
   2026-06-28 solution doc for this exact constraint class
   (`docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`)
   states *"An inline audit module validates every solver output against
   the input constraint model... runs unconditionally after every Rust
   solve — violations raise `RuntimeError`, not a warning."* **That audit
   (`audit_result`, wired at `_pipeline_route.py:437-452`) is never called
   anywhere in `net_batching.py`** (confirmed, grep, zero hits). The
   documented safety net for exactly this failure class — a channel
   assigned more true "uses" variables than its capacity allows — does not
   run on the production `--net-batching` path at all. This is the highest-
   value finding in this document, independent of whether capacity ever
   actually gets over-allocated in practice (§5).

**K is real, independently re-derived, and not the whole story.** The
vacuity is structural, not merely a batch-size-vs-K threshold. Fixing the
guard, or raising the batch size, would encode more `AtMostK` clauses without
changing the board, because nothing else in the model ever creates positive
pressure for those clauses to restrict.

---

## 1. The finding, re-verified

`packages/temper-rust-router-core/src/encoding.rs:139` —

```rust
let max_nets = ((_cap * _sf) / min_width).floor() as usize;
```

`:148` —

```rust
if !var_indices.is_empty() && max_nets < var_indices.len() {
```

`encode_at_most_k`'s own early return, `:28-30`:

```rust
if k >= n {
    return;
}
```

`net_batching.py:221`: `DEFAULT_BATCH_SIZE = 10`. Under batching, `var_indices.len()`
for any `CapacityConstraint` is bounded by the batch's own net count
(`ModelBuilder` is constructed with only the batch's nets,
`net_batching.py:456-487`), so `var_indices.len() <= 10`. All three lines
match the finding as stated, exact `path:line`.

### 1.1 — K, independently re-derived

The finding's K≈17 comes from `docs/plans/2026-08-12-002-...`, itself derived
from the 2026-07-27 measurement (3,876,012 raw vars / 43,050 constraints →
CNF 42,145,777 vars / 78,107,180 clauses, 20,734 `CapacityConstraint`s, 108
nets, pre-plane-fix 20,734-edge skeleton). Re-derived here from the same
published numbers, independently:

```
aux vars   = 42,145,777 - 3,876,012           = 38,269,765
aux/constraint                                 = 38,269,765 / 20,734 = 1,845.66
Sinz: aux = (n-1)*K, n = 108 nets  ->  K = 1,845.66 / 107           = 17.25

clauses/constraint                             = 78,107,180 / 20,734 = 3,767.06
Sinz: clauses ~= K*(2n-1), n = 108  ->  K = 3,767.06 / 215           = 17.52
```

Both equations agree at **K ≈ 17.25–17.52**, consistent with the plan's
"K≈17" and re-derived independently in this task rather than trusted.

**Caveat the plan already carries and this task confirms is real**: this is
a **mean over 20,734 constraints**, one per channel-skeleton edge. Individual
channels vary — a narrow, congested edge could have K well below 10, in
which case the guard *would* fire even at `batch_size=10`. The mean does not
prove the guard *never* fires; the direct measurement (§1.2, and the
"0 conflicts / 0 decisions" record going back to before batching existed)
is the stronger evidence that in practice, on this board, it doesn't matter
either way.

### 1.2 — Live measurement, this task

An instrumented run of `scripts/route_board.py --net-batching --batch-size 10`
against a stripped-copper temp copy of `pcb/temper.kicad_pcb` (never written
to `pcb/**`), wrapping `net_batching._consume_capacity` to log
`uses_channels` content per batch, run to completion of the first 3 batches
(30 of 110 nets) before deliberately stopping:

```
[batch-trace] start: 110 nets, batch_size=10, 11 batches, hub_blocks=['mcu', 'safety']
[PROBE] batch #1: nets_subset=10 topo_entries=10 nonempty_uses_channels=0 total_channel_refs=0 consumed_before=0
[PROBE] batch #1: consumed_after=0 sample=[]
[batch-trace] batch=0 nets=10 status=sat ... vars=2043980 (net_channel=2043980, via=0) constraints=109216 wall_s=19.06
[PROBE] batch #2: nets_subset=10 topo_entries=10 nonempty_uses_channels=0 total_channel_refs=0 consumed_before=0
[PROBE] batch #2: consumed_after=0 sample=[]
[batch-trace] batch=1 nets=10 status=sat ... vars=2043980 constraints=109237 wall_s=19.58
[PROBE] batch #3: nets_subset=10 topo_entries=10 nonempty_uses_channels=0 total_channel_refs=0 consumed_before=0
[PROBE] batch #3: consumed_after=0 sample=[]
```

**Result: 0 of 30 nets, across 3 independent batches, had a non-empty
`uses_channels`.** Every batch solved `status=sat` (2,043,980 `NetChannelVar`s,
~109,200 constraints each), and `_consume_capacity`'s `consumed` dict stayed
at length 0 after every call — it received nothing to accumulate. This is a
**direct, measured** confirmation of the structural argument above, not an
inference from it: `_consume_capacity`, the mechanism the finding-as-given
and `2026-08-12-002` both describe as "enforcing capacity across batches,"
is receiving **completely empty input** in this production configuration.
Whatever prevents two nets from occupying the same copper on this board,
it is not this. §5 gives the standing-measurement version of this probe
(U1 in the implementation plan) so this is re-checked across all 11
batches / 110 nets, not just the first 3, before anything is deleted on
the strength of it — but a 3-for-3 result at this sample size is already
strong evidence, not a hint.

---

## 2. Is greedy over-allocation implicated in the 499-505 `clearance` violations?

**Checked directly, per the task's instruction. Answer: no, on the weight of
three independent, already-existing investigations, none of which name
Stage-3 capacity or `_consume_capacity`/`_shrink_channel_widths` as a
mechanism.**

- `docs/evidence/2026-08-12-clearance-regression-route-vs-placement.md`
  (independent regeneration, §4): **0 of 505 candidate `clearance`
  violations are pad-to-pad**; 95.2% involve at least one track. The
  regression is concentrated in the safety-interlock/MCU/`rtd_pan` cluster
  and is **insensitive to how much routing actually completed** (a run with
  21-24% less copper still landed on the same violation count, §2 of that
  doc) — evidence *against* "more topology assignment → more collisions,"
  which is what over-allocated channel capacity would predict if it were
  the mechanism.
- `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md` (#1052,
  cited by the above): F.Cu free space around the densest cluster fragments
  into **94 disconnected sub-mm-scale pockets at the current placement** —
  a corridor-erosion-aware A* (materially better search over the *same*
  placement) did not move the violation count, because **no
  clearance-respecting path exists there for any search strategy to find**.
  That is a placement-density finding, not a capacity-bookkeeping one.
- Zone (plane-pour) count reproduces **exactly** (66/66) between the
  committed board and an independent regeneration, while segment/via count
  (the point-to-point stage net-batching actually touches) does not — and
  zones are the specific mechanism the same investigation's own
  no-backbone control experiment already implicated as the dominant driver
  of the `clearance` delta, independent of routing strategy.

**This does not mean greedy is provably incapable of over-allocating in
general** — `shrink_reduces_and_floors_at_zero` (`net_batching.rs:434-449`)
proves the mechanism *can* be driven to (and past) zero capacity if it ever
receives consumption data: `_shrink_channel_widths` floors at 0 rather than
going negative, so an over-committed channel would simply report 0
remaining width to the next batch, never a contradiction, and an
over-committed channel is not rejected at the bookkeeping layer, only
starved going forward. **But §1.2's live measurement shows this mechanism
is not receiving consumption data at all in production** — `consumed`
stayed at length 0 across all 3 measured batches — so this particular
failure mode (silent over-commit, floored rather than rejected) is
currently moot: there is nothing being consumed for it to floor. Whether
that changes once `uses_channels` is genuinely populated (Option E2) is a
separate, forward-looking question this document does not resolve.

---

## 3. What does the codebase currently claim?

| claim | where | true today? |
|---|---|---|
| "An inline audit module validates every solver output against the input constraint model... runs unconditionally after every Rust solve" | `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md:88-90,122` | **False for the net-batching path.** `audit_result` (`_pipeline_route.py:437`) is never imported or called in `net_batching.py` (grep, zero hits). It runs only in the monolithic `RouteStage` path. |
| "Capacity... is preserved across batch boundaries by explicit bookkeeping" | `net_batching.py:15-21` | **True as designed, measured false in practice (§1.2).** The docstring accurately describes what `_consume_capacity`/`_shrink_channel_widths` would do *if* given data, and does not claim SAT enforces capacity — but the live measurement shows the bookkeeping receives an empty `uses_channels` for every net observed (30/30, 3/3 batches), so nothing is actually being preserved across batch boundaries today. This is the second false-in-production claim this investigation found, one level less direct than row 1 (it is not contradicted by its own words, only by what actually reaches it). |
| "Creepage, HV/SELV separation, and geometric clearance are... never encoded in the Stage 3 SAT model... enforced downstream in Stage 4" | `net_batching.py:29-45` | True, corroborated independently (§2). |
| `ChannelSeparationConstraint` exists as a constraint class | `model_builder.rs:280`, `constraint_model.py` re-export | True but **dead**: never instantiated anywhere in production code (`rg "ChannelSeparationConstraint\("` over `model_builder.rs` and every `router_v6/*.py` returns zero constructor calls). Its own `encoding.rs:183-236` AtMostK path (`ChannelSeparation`) is exercised by nothing. |
| The Sinz sequential-counter AtMostK encoding is sound | `encoding.rs:212-236` (inductive proof comment), `unsound-atmostk-capacity-encoding.md` | True and not in question — this finding is about the encoding never being *reached*, not about it being wrong when it is. |

**The highest-value finding is row 1.** It is exactly the repo's own
documented recurring pattern (referenced by the task) of a written
correctness claim that is false in the production configuration — found one
layer below where the prior gate audit looked, in a solution doc rather than
a plan or a gate.

---

## 4. Options

### Option A — Raise `DEFAULT_BATCH_SIZE` above K so the guard fires

Set `batch_size >= ~18` (above the measured K ≈ 17.3-17.5).

- **Effect on the board**: per plan 002's R6, this is explicitly a
  board-changing algorithmic change, not a tuning knob — it switches
  capacity encoding on for constraints whose K falls inside the new batch
  window. **But §1's structural finding, now measured on 30/110 nets (§1.2)
  showing `uses_channels` empty in every observed batch, says it would
  switch on an encoding that still cannot bind**, because nothing forces a
  `NetChannelVar` true. Expected observable effect: **larger CNF, same "0
  conflicts, 0 decisions" result, same topology** (all-false, or whatever
  `LayerConstraint`'s negative-only clauses leave over). Treated here as a
  strongly-evidenced prediction rather than a certainty for all 110 nets —
  the plan's U1 extends the measurement to the full board before anything
  is decided on its strength.
- **Runtime/memory**: strictly worse. More `AtMostK` clauses (`O(n*k)` aux
  vars/clauses per constraint, and `k` also grows) with no completion or
  quality benefit if the prediction above holds.
- **Verdict**: **not recommended without first confirming §1.2's live
  measurement.** If the probe shows `uses_channels` genuinely empty in
  production, this option is dead on arrival — it spends CNF size on
  clauses that provably cannot change anything, because the thing they
  would restrict is never true in the first place.

### Option B — Fix the guard to always encode capacity regardless of batch size

Remove the `max_nets < var_indices.len()` guard, or replace it with an
unconditional encode (still skip only when `terms.is_empty()`).

- Same structural objection as Option A, stronger: this doesn't even wait
  for K to cross a batch-size threshold — it encodes `AtMostK` at every
  batch size, including the current default. Given §1's structural
  argument, this **adds CNF size with no behavior change**, at *every*
  batch size, forever, unconditionally.
- **Acceptance test if pursued anyway**: NOT byte-equality against today's
  board — per plan 002's own rule (batched and monolithic, and any change
  that alters CNF content, are different algorithms/instances). The correct
  test is: (a) CNF vars/clauses increase by the predicted `O(n*k)` amount;
  (b) solver conflicts/decisions remain 0 (falsifying nothing new is bound);
  (c) `temper_routed.kicad_pcb` is byte-identical to the pre-change baseline
  (proving the change was inert, which is the actual claim being tested).
- **Verdict**: **useful only as a diagnostic** (it directly tests the
  structural claim in §1 across the whole board, not just the 3 batches
  §1.2 sampled), **not recommended as a shipped fix** unless it's paired
  with the connectivity-forcing gap (Option E, below) — encoding a
  constraint that structurally cannot bind is not a correctness fix, it is
  a bigger CNF for the same wrong reason the guard papered over.

### Option C — Delete the SAT capacity encoding; make greedy the documented, tested algorithm

Remove `encode_at_most_k`'s call site for `Capacity` in `encoding.rs`
(keep the function — `ChannelSeparation` still references it, itself dead,
see §3), delete `CapacityConstraint`'s CNF role, keep
`create_capacity_constraints` only if `audit_constraints` (§5) is kept as
a structural sanity check, or delete it too if not.

- **Effect on the board**: **none, on §1.2's measurement** — the encoding
  was never binding (nothing in the 30 measured nets ever populated
  `uses_channels`), so removing dead code that never fired is a no-op on
  output. This is the "fully legitimate conclusion" the task allows for,
  and it is now supported by a live measurement, not only the structural
  argument, though the plan below still extends the measurement to the
  full 110 nets before executing the deletion (a 3-batch sample is strong
  evidence, not proof for all 11 batches).
- **Runtime/memory**: smaller CNF (removes however many `AtMostK` clauses
  the guard *does* let through for narrow channels), simpler code, one
  fewer thing to reason about.
- **Correction to the option as originally framed**: "make greedy the
  documented, tested algorithm" is the wrong framing given §1.2. Greedy is
  not currently doing anything to document as load-bearing — it is
  receiving empty input. The honest version of this option is "delete the
  vacuous SAT encoding, and be equally honest that the greedy bookkeeping
  is *also* not currently enforcing anything, and that the real invariant
  is Stage 4's per-net geometric clearance" — which is Option E1, not a
  restatement of "greedy works, SAT doesn't." Folded into Option E below.
- **Acceptance test**: `temper_routed.kicad_pcb` byte-identical to the
  pre-change baseline (168 footprints / 3,349 segments / 56 vias / 70
  zones / 80/105 nets, `docs/evidence/2026-08-12-board-recipe-
  reproducibility.md`) — since this option's entire claim is "removes code
  that never affected output," byte-equality is the *correct* test here
  (unlike Options A/B/D, which change what gets encoded/decided and must
  not be tested this way).
- **Verdict**: **recommended**, on §1.2's measurement (pending the plan's
  full-board confirmation), and only after fixing the audit-bypass (§5) so
  the removal isn't also removing the one thing that would have caught a
  real over-allocation.

### Option D — Keep both, add a differential oracle

Keep the (currently vacuous) SAT capacity path and greedy bookkeeping side
by side, cross-check them.

- Given §1's structural finding, a SAT-vs-greedy differential over
  `NetChannelVar` truth values is comparing a value that is (per the
  structural argument) always empty against greedy's own accounting —
  **not a meaningful differential** unless Option E's connectivity gap is
  fixed first, at which point this becomes a real ESL/BMC-style property in
  the mold of `unsound-atmostk-capacity-encoding.md`'s own Layer 3.
- **Verdict**: **not recommended as an isolated option** — it inherits
  Option A/B's cost without a payoff until the deeper structural gap is
  addressed. Worth revisiting *after* Option E, not instead of it.

### Option E — (not in the task's list, surfaced by this investigation) Fix or explicitly scope the missing connectivity/forcing constraint

The deeper structural finding (§1, item 2): under net-batching, nothing in
the Stage-3 model ever requires a net to use *any* channel. This is a
distinct question from "does capacity bind" — it is "does Stage 3 decide
topology at all." Two honest resolutions:

- **E1 — accept it and document it.** State plainly that Stage 3's
  topology output is not consumed under `--net-batching` in production
  (consistent with `docs/evidence/2026-08-08-terminal-defect-and-pad-
  connectivity-fix.md`'s independent, already-measured finding that
  `map_topology_to_channels` converted **zero of 110** net topologies into
  usable Stage-4 channel paths under this exact configuration, and now
  further corroborated by §1.2's direct measurement that the *upstream*
  `uses_channels` feeding both that function and `_consume_capacity` is
  itself empty), and that Stage 4's occupancy-grid A* does the entire job
  from raw pad positions, including whatever "don't overrun this channel"
  property the board actually has. Stage 3 under net-batching is, on this
  evidence, closer to a formality than a routing decision, and the honest
  scope for *this* plan is Option C plus the audit fix (§5) — not a bigger
  rewrite.
- **E2 — wire a real connectivity/candidacy constraint** (e.g., `_apply_pcl_constraints`
  actually invoked with something that forces at least one path per net,
  or Stage 4 outputs consumed *back* as Stage-3 unit clauses). This is a
  materially larger change — new constraint semantics, a new correctness
  proof in the `unsound-atmostk-capacity-encoding.md` mold, and a new
  acceptance bar — and is explicitly **out of scope for a plan whose job is
  the capacity-vacuity finding**, named here only so it is not lost.

---

## 5. The audit-bypass — highest priority, independent of A-E

`_pipeline_route.py:437-452` calls `temper_rust_router.audit_result` after
every `status == "sat"` solve **in the monolithic `RouteStage` path only**.
`net_batching.py` — 1,200+ lines, the production `--net-batching`
configuration — never imports or calls it. This means:

- The Layer-3 backstop `unsound-atmostk-capacity-encoding.md` documents as
  running "unconditionally after every Rust solve" (the fix for the
  *original* 2026-06-28 unsound-encoding incident) **does not run on the
  path this task is investigating.**
- If §1.2 or a future change (e.g., Option E2) ever makes capacity
  over-allocation possible again, **nothing in the production path would
  catch it.** This is true *regardless* of which of Options A-E is chosen.
- **Recommended independent of the rest of this document**: wire
  `audit_result` (or an equivalent capacity-only check, given §1's
  structural finding may make the full audit moot until Option E lands)
  into `_solve_subset` / the batch loop, so the documented safety property
  is actually true again.

---

## Sources

- `packages/temper-rust-router-core/src/encoding.rs:21-30,139,148,183-236` — the guard, the early-return, the dead `ChannelSeparation` AtMostK path
- `packages/temper-rust-router-core/src/audit.rs:1-110` — the audit that exists and is sound, and is not called under net-batching
- `packages/temper-rust-router-core/src/net_batching.rs:218-346,434-449` — `shrink_channel_widths`/`consume_capacity`, the floor-at-zero test proving over-commit is silently absorbed, not rejected
- `packages/temper-rust-router-core/src/extraction.rs:14-93` — `extract_topology`: builds `uses_channels` purely from which `uses_{net}_{channel}` variables the solver assigned true
- `packages/temper-design-bundle/src/model_builder.rs:280-286` (capacity, unsound-encoding cross-reference), `:902-984` (`create_capacity_constraints`, AtMostK-only), `:985-1023` (`create_diff_pair_constraints`, biconditional), `:1024-1073` (`create_layer_constraints`, `allowed: false` only)
- `packages/temper-placer/src/temper_placer/router_v6/net_batching.py:1-135` (module docstring, capacity/clearance claims), `:221` (`DEFAULT_BATCH_SIZE`), `:456-487` (`_solve_subset`, no `pcl_constraints` passed), `:331-417` (`_shrink_channel_widths`/`_consume_capacity`), `:1036-1150` (batch loop)
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:282-368` (`ModelBuilder.build`, `_apply_pcl_constraints`'s `None`-guard)
- `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:437-452` (`audit_result` call site, monolithic path only)
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — the 2026-06-28 origin of the encoding and the audit; the "runs unconditionally" claim checked and found false for net-batching
- `docs/plans/2026-08-12-002-feat-router-orchestration-rust-plan.md` (branch `spike/router-orchestration-rust`) — the source finding, K≈17 derivation, R6/R7/R11
- `docs/evidence/2026-07-27-stage3-model-and-rewrite.md:296-337` — "0 conflicts, 0 decisions" at monolithic full-board scale, capacity encoded
- `docs/evidence/2026-08-07-sat-model-reduction-options.md` §0, §7 — "the solver... has never had to search," every full-board solve ever completed
- `docs/evidence/2026-08-07-net-batching-prototype.md`, `docs/evidence/2026-08-08-net-batching-subprocess-isolation.md` — batch-level SAT/UNSAT history, RSS, crash-vs-UNSAT
- `docs/evidence/2026-08-08-terminal-defect-and-pad-connectivity-fix.md:60-68` — independently measured: `map_topology_to_channels` converts 0/110 topologies into usable Stage-4 paths under net-batching
- `docs/evidence/2026-08-12-clearance-regression-route-vs-placement.md` — 499-505 `clearance` violations attributed to placement-density F.Cu fragmentation, not Stage-3/capacity
- `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md` (#1052) — 94 disconnected F.Cu pockets, no-backbone control experiment
- `docs/evidence/2026-08-12-board-recipe-reproducibility.md` (at `0659ef39b`) — the deterministic baseline: 168 footprints / 3,349 segments / 56 vias / 70 zones / 80/105 nets
- `docs/migration-pipeline.md` §Hard rules — FREEZE/REIMPLEMENT/KEEP oracle disposition, referenced for the implementation plan

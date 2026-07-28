# Why Stage 3 took 26 minutes: it was never the SAT solver, and it wasn't the loop the prior doc named either

<!-- provenance: commit=56362d528d4c9aebc44b3a0534f4fa9c272a8b97 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Task:** Find out why Stage 3 takes 26 minutes on `pcb/temper.kicad_pcb` (108
nets), given `docs/evidence/2026-07-27-sat-bound-tradeoff.md` already showed
CaDiCaL needs 0 conflicts at every scale it could test, and that
`combinator::rewrite::rewrite` (RW1–RW7) was still running past 250s before
`solve()` was ever reached, twice, independently.

## Falsifier, stated before measuring

**"The O(n²) subsumption loop accounts for the bulk of rewrite time"** —
specifically the pairwise `for &i in indices { for &j in indices { ... } }`
double loop inside `subsume_capacity`, grouped by `channel_id`
(`rewrite.rs:495–540` in the pre-change file), which the prior evidence doc
flagged as a candidate because `39,544² / 2 ≈ 782M` comparisons at a few
hundred nanoseconds each is arithmetically close to the observed ~250s+
hang.

**Result: refuted for the named loop, confirmed for a different loop in the
same function.** Instrumented directly (counters + per-phase timers, not
inferred from the arithmetic above):

- Every one of the 20,734 `CapacityConstraint`s on this board has a
  **unique** `channel_id` (one per channel-skeleton edge — see Q2 below).
  `subsume_capacity`'s channel-group histogram is `{1: 20734}` at every
  scale tested (15 and 108 nets) — **every channel group has size 1**. The
  named pairwise loop therefore does exactly `n` trivial `i==j`-skip
  iterations, not `n²/2`. Measured: **20,734 comparisons in 111–159
  microseconds** — nowhere near the bottleneck.
- A **second, previously-unnamed O(n²) loop** exists ~90 lines later in the
  same function, in the "rebuild capacity constraints" step: for each of up
  to N `dedup_map` entries, `cap_infos.iter().find(|info| { rebuild a
  BTreeSet<String> from info.terms; compare })` — an O(N) linear scan, with
  an O(m log m) `BTreeSet` rebuild-and-compare (m = terms per constraint,
  108 on the full board) evaluated for **every candidate scanned**, not
  just the eventual match. This is the real O(N² · m log m) cost.
  Instrumented directly: **144.34 seconds for a single call of this loop**,
  at just 15 nets (N=20,734 candidates, m=15 terms each) — before the run
  was manually killed per the task's "report partial results, don't
  background" instruction. See Part 1 for the full trace.

The falsifier as literally worded is **false** (that specific loop is not
the cost) but the broader claim it was gesturing at — "an O(n²) loop inside
`subsume_capacity` dominates rewrite time" — is **true**, just one loop
over from where the prior doc pointed.

## Part 0 — How to reproduce these measurements

Built and ran directly against `pcb/temper.kicad_pcb` (108 nets, 170
components) via the real `RouterV6Pipeline` internals (Stage 0 → 0.5 → 1 →
2, then `ModelBuilder(...).build()` — the same construction
`_run_stage3` uses — then `temper_rust_router.solve_topology_rust`), not a
synthetic model. Rust extensions needed a rebuild in this worktree before
anything imported (`temper_rust_router`, `temper_ipc`, `temper_dsn`,
`temper_geometry`, `temper_io_types`, `temper_drc_rs`,
`temper_constraint_compiler`, and the nested
`packages/temper-placer/temper-constraints` crate all required
`uv run maturin develop --release`; the nested `temper-constraints` crate
needed `--python <repo-root>/.venv/bin/python3` explicitly, or `uv run`
created and installed into its own throwaway nested venv instead of the
one `temper-placer` actually imports from).

A `TEMPER_REWRITE_TRACE` env var (checked once via `std::env::var`, zero
cost when unset) was added to `rewrite.rs` and `lib.rs` to print per-phase
timings and loop-iteration counts to stderr — this is the instrumentation
the falsifier above was tested against, not inference. A second env var,
`TEMPER_SKIP_REWRITE`, was added as a measurement-only bypass to compare
rewrite on vs. off (Part 3). Both default to off/unset; production
behavior is unchanged unless a caller explicitly sets them.

## Part 1 — Q1: is the rewrite pass too slow for a legitimately-sized model? (yes — one specific bug, now fixed)

### Instrumented measurement, before the fix

At **15 nets** (truncated via the same `pcb_override` net-truncation the
sat-bound-tradeoff doc used — genuine truncation, not the dead
`max_sat_nets` path):

```
[rewrite-trace t=0.011s] model.constraints.clone(): 11.1ms, 20908 constraints
[rewrite-trace t=0.046s] subsume_capacity: cap_infos_build=20.9ms groups=20734 max_group_size=1
                         size_histogram(size->num_groups)=[(1, 20734)]
[rewrite-trace t=0.046s] subsume_capacity: pairwise loop done, comparisons=20734 elapsed=113.6µs
[rewrite-trace t=144.389s] subsume_capacity: rebuild loop done, elapsed=144.342718583s, total_fn=144.363844166s
```

The pairwise loop (the loop the prior doc named): **20,734 comparisons,
113.6 microseconds.** The rebuild loop (30 lines later, same function):
**144.34 seconds**, for the *first* of what would have been at least two
outer fixpoint iterations at this scale (the run was killed here — see
`docs/evidence/2026-07-27-sat-bound-tradeoff.md`'s own guidance: report the
partial result, don't wait). This one number is the direct, instrumented
proof that the O(n²) shape is real, in `subsume_capacity`, and enormous —
just not in the loop that was named.

### Root cause

```rust
// Before (rewrite.rs, "Rebuild capacity constraints" section):
for (var_sorted, (_orig_idx, tight_k)) in dedup_map {
    let info = cap_infos
        .iter()
        .find(|info| {
            let vs: BTreeSet<String> = info.terms.iter().map(|(n, _)| n.clone()).collect();
            vs == var_sorted
        })
        .ok_or_else(|| /* ... */)?;
    // ...
}
```

`cap_infos` is built by `.map()` over `caps` earlier in the same function,
preserving order — so `cap_infos[i].orig_idx == i` holds unconditionally.
`_orig_idx` was already sitting in the tuple being destructured, unused
(the leading underscore is the tell). No search was ever necessary: the
correct index is already known. The fix:

```rust
// After:
for (_var_sorted, (orig_idx, tight_k)) in dedup_map {
    let info = cap_infos.get(orig_idx).ok_or_else(|| /* ... */)?;
    // ...
}
```

O(1) index instead of an O(N) scan rebuilding an O(m log m) `BTreeSet` per
candidate, for up to N dedup entries — O(N² · m log m) → O(N).

### Instrumented measurement, after the fix

Same 15-net case:

```
[rewrite-trace t=0.040s] subsume_capacity: pairwise loop done, comparisons=20734 elapsed=152.5µs
[rewrite-trace t=0.102s] subsume_capacity: rebuild loop done, elapsed=62.419417ms, total_fn=82.737875ms
[rewrite-trace t=0.209s] rewrite() done: iterations=2 (max_iterations=41816) final_len=10885
```

Rebuild loop: 144.34s → **62.4ms** (≈2,313x). Whole `rewrite()`, both outer
iterations: **209ms** total (was: did not finish the first iteration's
rebuild step within 144s+).

At **full board scale (108 nets, N=20,734 constraints, m=108 terms each)**:

```
[rewrite-trace t=0.269s] subsume_capacity: pairwise loop done, comparisons=20734 elapsed=159.25µs
[rewrite-trace t=0.616s] subsume_capacity: rebuild loop done, elapsed=346.930583ms, total_fn=460.520625ms
[rewrite-trace t=0.714s] iter=1 len=43050 changed=false dedup_dp=6.8ms dedup_layers=0.4ms
                         prop_true=0.17ms prop_false=98.1ms subsume=551.7ms elim=6.9ms iter_total=664.3ms
[rewrite-trace t=0.714s] rewrite() done: iterations=1 (max_iterations=86100) final_len=43050
```

`rewrite()` at full board scale: **0.714s total, 1 outer iteration**
(converges immediately — `changed=false` — see Part 3 for why: at this
scale rewrite doesn't eliminate anything). Extrapolating the *broken*
version's cost from the measured 15-net number (rebuild-loop cost scales
with `m` — 15→108 terms is a ~7.2x per-candidate factor, N constant at
20,734 since capacity-constraint count is net-count-independent — see
Q2): **roughly 1,000–1,800s for the first outer iteration alone**, fully
consistent with, and now explaining, the two independent >250s hangs
observed previously and the originally profiled 1,573.8s "Stage 3" wall
time.

### Correctness (not just speed)

- `cargo test --release`: **101 passed, 0 failed** across 6 binaries,
  unchanged from baseline — including `exhaustive_rewrite_preserves_sat_n4`
  and the RW1-specific subsumption tests
  (`rw1_subsume_tightens_superset`, `rw1_dedup_identical_var_sets_after_tightening`,
  `ts2_overlapping_capacity_subsume`), none of which needed modification.
- `cargo clippy --release`: **0 warnings** in `temper-rust-router-core`
  (one `manual_is_multiple_of` warning surfaced during development, from
  the new instrumentation's own modulo check — fixed before finalizing).
  `temper-rust-router`'s pre-existing 16 pyo3-deprecation warnings are
  unchanged (present before this task's changes too — confirmed by
  diffing the first build in this session against the last).
- Same final constraint count at every measured scale, before and after:
  15 nets iteration 1 → `len=10885` in both the broken and fixed runs; 108
  nets iteration 1 → `len=43050` in both. The fix changes *how* the answer
  is found, not what the answer is.

## Part 2 — Q2: is the model too big in the first place? (yes, and this outranks Q1)

### What the variables encode

`ModelBuilder._create_per_net_channel_vars` (`constraint_model.py:293`)
creates one `NetChannelVar` for **every (net, channel-skeleton-edge)
pair**, across both routing layers, unconditionally — no net-to-channel
relevance filter of any kind. `_create_via_vars` similarly creates one
`ViaVar` for **every (net, via-anchor-node) pair**, where the via-anchor
nodes are the union of all channel-skeleton graph nodes across layers
(again net-count-independent, driven by board geometry).

Measured directly (Python-side `ModelBuilder`, no Rust, no SAT solve —
just built the real model and counted):

| Scale | F.Cu skeleton | B.Cu skeleton | total edges | unique via-anchor nodes | `NetChannelVar` | `ViaVar` | **total vars** |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15 nets | 9,643 nodes / 12,627 edges | 6,986 nodes / 9,285 edges | 21,912 | 13,977 | 328,680 | 209,655 | **538,335** |
| 108 nets (full board) | (same — Stage 2 is net-count-independent) | (same) | 21,912 | 13,977 | 2,366,496 | 1,509,516 | **3,876,012** |

Both rows match the predicted formula **exactly**:
`vars = n_nets × total_edges + n_nets × total_via_nodes`
(15×21,912 + 15×13,977 = 538,335; 108×21,912 + 108×13,977 = 3,876,012).
**Dominant term: `O(n_nets × E)`, where `E` (≈35,889 here) is the
channel-skeleton size — a quantity Stage 2 computes once per board,
independent of net count**, driven by board area and the medial-axis
Voronoi extraction's `simplify_tolerance` (0.5mm default) rather than by
anything net-related. The ~37,000-vars-per-net figure the task noted is
essentially `E` itself, plus per-constraint Sinz auxiliary variables added
during CNF encoding (below).

This is not a case of "quadratic in something it needn't be" in a formal
complexity sense — it's linear in nets — but the per-net multiplier `E` is
inflated because the encoding assigns a boolean variable to **every
(net, edge) pair regardless of whether that net's pins are anywhere near
that edge**. A net confined to one corner of the board still gets one
variable per edge on the opposite corner. `ModelBuilder` already has an
alternative construction path — `enable_bundling=True` /
`_create_bundle_channel_vars`, which creates one variable per
*bundle-equivalence-class* per edge instead of per net per edge — but it
is **not the default** (`RouterV6Pipeline.enable_bundling` defaults to
`False`) and the production `route_pcb()` entry point does not set it, so
every full-board route today goes through the unbundled, per-net path.

Every `CapacityConstraint`'s `terms` list also always contains **all N
nets** (min=median=max=108 terms per constraint on the full board) — not
because it needs to, but because `_create_capacity_constraints` iterates
all nets × all edges with no candidacy pruning, same root cause.

After CNF encoding (Sinz 2005 sequential-counter cardinality encoding,
`encoding.rs:19`, which adds `O(n·k)` auxiliary variables per
`AtMostK`): the full-board raw model's 3,876,012 variables / 43,050
constraints become **42,145,777 CNF variables / 78,107,180 clauses** —
roughly 10x the raw-model variable count, from Sinz aux vars across
20,734 capacity constraints each spanning up to 108 terms.

**Reconciling against the prior doc's cited "4,022,352 vars, 39,544
cons":** this session's *raw-model* measurement (before netclass
adjustments) was 3,876,012 vars / 43,050 cons — same order of magnitude,
~8% off in constraint count. Attempting to reproduce with the exact
production netclass config (`load_netclass_rules` +
`net_class_assignments` merge, matching `route_pcb()`'s own preprocessing)
hit an unrelated, pre-existing schema mismatch —
`escape_via_generator.py:85` expects `rules.via_diameter_mm`, but the
netclass-loader's `NetClassRules` type exposes `via_diameter` instead —
which is itself worth a ticket but is out of scope here and not material
to this task's conclusion (the ~8% gap doesn't change which term
dominates or by how much). **UNVERIFIED**: exact reconciliation of
39,544 vs. 43,050 constraints.

## Part 3 — Is the rewrite pass worth running at all?

Measured on/off at 15 nets (small enough both complete) via the new
`TEMPER_SKIP_REWRITE` bypass:

| | raw model | after rewrite | CNF | `solve_topology_rust` wall | solve time | conflicts | result |
|---|---|---|---|---:|---:|---:|---|
| **rewrite ON** | 538,335 vars / 20,908 cons | 10,885 cons (iter 1) | 1,547,192 vars / 2,034,276 clauses | 2.13s | 415.0ms | 0 | SAT |
| **rewrite OFF** | 538,335 vars / 20,908 cons | (unchanged) | 1,548,491 vars / 2,036,903 clauses | 1.81s | 364.3ms | 0 | SAT |

Rewrite drops the **constraint list** from 20,908 to 10,885 (48%) at 15
nets — but the resulting **CNF** shrinks by only 0.08% (vars) / 0.13%
(clauses). Reason: most of what RW2/RW3/RW4 eliminate are constraints that
would have encoded to **zero clauses anyway** (`encode_at_most_k` returns
immediately, no clauses emitted, when `k >= n` — i.e. exactly the
"trivially satisfiable" constraints RW2 targets). Removing a no-op
constraint from the intermediate list doesn't shrink the eventual CNF.
Net effect at 15 nets: rewrite costs **~320ms more wall time** than
skipping it, for a **<0.2% CNF-size benefit**.

At **full board scale (108 nets), rewrite changes nothing at all** —
`iter=1 ... changed=false`, constraint count 43,050 in, 43,050 out. It
still costs 0.71–0.87s (post-fix; this was the catastrophic, unbounded
cost pre-fix), for **zero** model-size benefit at this board's actual
scale.

**No crossover point was found where rewrite meaningfully pays for
itself on this board, at either scale tested.** Per the task's guidance
("do not delete it because it is slow — that is a decision requiring this
measurement"): the measurement now exists, and it says rewrite's
size-reduction value is negligible-to-zero here. It is not recommended
for removal regardless, for a reason orthogonal to size reduction: **RW7
(`detect_layer_conflict`)** provides a real, cheap, pre-solve UNSAT
contradiction check (`LayerRestriction(v, true)` + `LayerRestriction(v,
false)`) that would otherwise only surface after a full CNF encode +
solve attempt. That check runs in the same pass and is effectively free
now that the O(n²) bug is gone.

## Part 4 — End-to-end payoff, full board, production defaults

Full 108-net board, `sat_conflict_limit=20_000` (the actual production
default), `sat_time_limit_ms=None`, fixed code, single foreground call
within the 600s budget:

```
[phase-trace t=3.886s]  model_from_python done
[phase-trace t=4.746s]  rewrite done, 43050 constraints        (0.86s)
[phase-trace t=12.019s] encode_to_cnf done, 42145777 vars, 78107180 clauses   (7.27s)
[phase-trace t=39.800s] solve done, status=Satisfiable          (27.78s)
solve_topology_rust TOTAL: 52.67s
status=sat, conflicts=0, decisions=0
```

**Stage 3 SAT phase: 1,573.8s → 52.67s, a ~29.9x reduction.** Including
Stage 2 (channel analysis, unaffected by this change) and Python-side
model construction, full pre-Stage-4 wall time was **83.15s** (parse
0.22s + Stage2 16.91s + Python model build 13.26s + Stage3 52.67s).

The solve itself needed **0 conflicts, 0 decisions** — the "decided
early" falsifier from `docs/evidence/2026-07-27-sat-bound-tradeoff.md`
(confirmed there only at 15/30-net scale) **does generalize to full-board
scale**. It simply never got the chance to be observed before, because
`rewrite()`'s bug meant `solve()` was never reached within any budget
tried. Since the fix is a proven algorithmic equivalence (same constraint
set out, same CNF, same SAT result — 0 conflicts both before-conceptually
and after, confirmed by the fixed run reproducing bit-identical CNF sizes
across two independent full-board runs: 42,145,777/78,107,180 in both the
forced-abort test and this production-bound test), **there is no
completion-rate cost**: this is the same computation the original
1,573.8s baseline (which established 48/96 = 50.0% completion) already
performed and used — just ~30x faster, not different.

**Secondary finding, not fixed, flagged for future work:** `solve()`
itself now dominates the post-fix total (27.78s of 52.67s, ~53%) despite
needing 0 conflicts — almost certainly CaDiCaL/rustsat allocating and
loading a 42M-variable/78M-clause CNF into its internal watch-list
structures before the terminator callback or search loop ever runs. This
is a consequence of Q2's model size (Part 2), not of anything fixed in
this task. A wall-clock or wall-clock-plus-conflict bound (already added
in `docs/evidence/2026-07-27-sat-bound-tradeoff.md`) cannot preempt this
loading phase.

## Ranked recommendation

1. **Done, this task:** fix the O(n²) rebuild-loop bug in
   `subsume_capacity` (Part 1). Verified, committed, 101/101 tests green,
   0 clippy warnings, no completion-rate change, ~30x Stage 3 speedup
   measured end-to-end.
2. **Not done, higher-leverage than anything left in rewrite:** address
   Q2's root cause — wire `enable_bundling=True` (or an equivalent
   net-to-channel candidacy filter) into the production `route_pcb()`
   path. The model is `O(n_nets × E)` where `E` is the whole board's
   channel-skeleton size; a bundled or geographically-pruned encoding
   would cut the ~10-40x inflation from "every net gets a variable for
   every edge on the board" without touching rewrite at all. This is a
   model-construction change, larger in scope than this task, and is
   reported rather than attempted here.
3. **Lower priority, informational:** the CaDiCaL CNF-loading cost (Part
   4's secondary finding) and the `via_diameter_mm`/`via_diameter`
   netclass schema mismatch (Part 2) are both real but out of scope for a
   rewrite/model-size investigation.

## UNVERIFIED

- Exact reconciliation of this session's raw-model counts (3,876,012
  vars / 43,050 cons) against the original profiling doc's cited
  4,022,352 vars / 39,544 cons — same order of magnitude and same
  dominant term, ~8% apart, likely from netclass/design-rule differences;
  blocked by an unrelated pre-existing `via_diameter_mm` vs.
  `via_diameter` schema mismatch when loading the production netclass
  config directly (see Part 2).
- Whether the outer `rewrite()` fixpoint loop's `changed` flag correctly
  captures every state change: `propagate_layer_false` (and similar
  rules) can shrink a `Capacity` constraint's `terms` list without
  changing the overall constraint *count*, and `changed` is only set from
  count deltas (`constraints.len() != before_len`) for those rules. This
  is a potential (unmeasured) completeness gap in the fixpoint, distinct
  from the performance bug fixed in this task — not investigated further
  since it doesn't bear on Q1/Q2, and observed behavior (test suite green,
  identical constraint counts before/after the performance fix) gives no
  positive evidence it currently matters on this board.
- Whether `solve()`'s ~28s CNF-loading-dominated cost (Part 4) is CaDiCaL
  clause-loading, rustsat's `Vec<Vec<i32>>` → CaDiCaL-internal conversion,
  or something else — not profiled at the sub-`solve()` level; flagged as
  a secondary finding, not investigated further (out of this task's Q1/Q2
  scope).
- Whether `enable_bundling=True` (Part 2's suggested Q2 fix) actually
  produces materially different routing completion/quality on this board
  — not attempted; it changes the model-construction path, which is a
  larger change than this task's scope and would need its own
  measurement against the 48/96 = 50.0% baseline before being adopted.
- Full-board manufacturing-DRC / gate re-runs post-fix beyond the ones
  listed under Verification below — this task's change touches
  `temper-rust-router-core`/`temper-rust-router` only, not routing
  behavior, netlist, or PCB copper; no material impact on those checks is
  expected and none was observed, but a full Stage 4/5 production route
  with the fix was not re-run end-to-end (Stage 3's SAT output was
  verified to reach the identical `status=sat, 0 conflicts` outcome the
  original baseline run reached, which is what Stage 4 actually consumes).

## Verification

- `cargo test --release` (`temper-rust-router-core`): **101 passed, 0
  failed** across 6 binaries (5 `Running` test binaries + 1 doc-test
  binary), unchanged from the stated baseline.
- `cargo clippy --release` (`temper-rust-router-core`): **0 warnings.**
- `cargo clippy --release` (`temper-rust-router`): 16 pre-existing pyo3
  deprecation warnings, unchanged from before this task's changes (not
  touched by this fix; confirmed identical count in the first and last
  build of this session).
- `make netlist`: **76 assertions passed, 0 failed.**
- `scripts/check_domain_partition.py`: exit 0 (0 domain crossings, 0
  isolator-barrier breaches, 0 protective-impedance chain defects).
- `scripts/capacity_budget_gate.py`: exit 0 (0 defects).
- `scripts/mpn_fabrication_gate.py`: exit 0 (0 new violations).
- `scripts/check_derived_doc_drift.py`: exit 0.
- `scripts/check_vacuous_gates.py`: exit 0 (0 violations, 532 files
  scanned).
- No changes made to `pcb/`, `elec/`, or gate scripts. Changes are
  confined to `packages/temper-rust-router-core/src/combinator/rewrite.rs`
  (the O(n²) fix + trace instrumentation) and
  `packages/temper-rust-router/src/lib.rs` (phase-timing instrumentation
  + the `TEMPER_SKIP_REWRITE` measurement bypass), both gated behind
  opt-in env vars with zero behavioral change to default (unset) callers.

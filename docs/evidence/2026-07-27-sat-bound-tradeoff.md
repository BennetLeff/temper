# Bounding the CaDiCaL SAT solve: mechanism, verification, and a scale limit the sweep ran into

<!-- provenance: commit=b78f9041d42f9e98ea988902927856ad7546385f dirty=UNKNOWN -->

**Date:** 2026-07-27
**Task:** Add a configurable bound (conflict and/or wall-clock) to the CaDiCaL
solve at `packages/temper-rust-router-core/src/solver.rs:20`
(`solve_with_cadical`), verify the existing `"unknown"` -> unguided-A*
fallback genuinely fires end-to-end, and measure the completion-rate trade
across a sweep of bound values.

## Falsifier, stated before implementing

**"Bounding the solve costs little completion because most nets are
decided early."** If true, the sweep should show near-identical completion
rate and route quality between the unbounded run and a tightly bounded run,
because the solver reaches its answer (SAT/UNSAT) well before any
reasonable bound would fire.

**Result: fired at every scale this session could directly execute (15
and 30 nets), but could not be confirmed at the scale the task cares about
(108 nets, the 1,573.8s measurement) — a different, larger bottleneck
blocked every full-board trial, bounded or unbounded, from completing
within the available compute budget.** Details below; this is the load-bearing
finding of this document, not a footnote.

## Part 1 — How the bound is set (rustsat / CaDiCaL binding)

Verified directly against the vendored crate source
(`~/.cargo/registry/src/.../rustsat-cadical-0.7.5/src/lib.rs`), not assumed:

- **Conflict count**: `rustsat::solvers::LimitConflicts::limit_conflicts(&mut self, limit: Option<u32>)`,
  which calls CaDiCaL's own `ccadical_limit("conflicts", n)`. This is CaDiCaL's
  native, deterministic search-budget mechanism — it does not depend on
  machine load or scheduler timing.
- **Wall clock**: CaDiCaL has **no native wall-clock limit API**. The bound is
  implemented via `rustsat::solvers::Terminate::attach_terminator`, a
  callback CaDiCaL polls periodically during search; the callback here
  captures a `deadline: Instant` computed at solve-start and returns
  `ControlSignal::Terminate` once `Instant::now() >= deadline`.
- Both mechanisms surface identically: `ccadical_solve_mem` returns `0`,
  which the `rustsat-cadical` wrapper maps to `SolverResult::Interrupted`,
  which `solve_with_cadical` already mapped to `SolverStatus::Unknown`
  (this mapping pre-existed the change — see `solver.rs`'s `Interrupted`
  arm).

**New public type**: `temper_rust_router_core::solver::SolveLimits { conflict_limit: Option<u32>, time_limit_ms: Option<u64> }`,
`Default` = unbounded (both `None`) at the Rust API boundary, so any other
Rust caller is unaffected unless it opts in. `solve_with_cadical`'s
signature changed from `(cnf, var_names)` to `(cnf, var_names, limits)` —
no other Rust call site existed besides the one in
`packages/temper-rust-router/src/lib.rs`, updated in the same change.

**Threaded to Python** via two new optional kwargs on the pyo3
`solve_topology_rust` function (`conflict_limit=None, time_limit_ms=None`,
both defaulting to unbounded at the FFI boundary), then to
`RouterV6Pipeline.__init__`'s new `sat_conflict_limit` (default `20_000`)
and `sat_time_limit_ms` (default `None`) parameters
(`_pipeline_core.py`), consumed in `_run_stage3`'s
`solve_topology_rust(...)` call (`_pipeline_route.py`), and exposed on the
production entry point `route_pcb()` (`_adapter_convert.py`) with the same
defaults and docstrings.

## Part 2 — Proof the `"unknown"` -> A* fallback genuinely fires and completes

Not trusted because a different code path (`skip_stage3=True`) already
exercises the same downstream handling — verified directly, at two levels.

### Rust-level (self-calibrating, deterministic)

Four new unit tests in `solver.rs` (`mod tests`), using a
pigeonhole-principle CNF (`pigeonhole_cnf(pigeons, holes)`,
`pigeons > holes` ⟹ UNSAT and reliably needs real CDCL search, unlike most
small CNFs which resolve via unit propagation alone):

| Test | What it proves |
|---|---|
| `unbounded_default_solves_pigeonhole_to_completion` | Baseline: `SolveLimits::default()` (unbounded) reaches `Unsatisfiable` and needs `conflicts > 0`. |
| `conflict_limit_below_requirement_yields_unknown` | Self-calibrating: measures conflicts the unbounded baseline actually needed, then re-solves with `conflict_limit: Some(0)` — asserts `Unknown`, not a false verdict. |
| `time_limit_below_requirement_yields_unknown` | Same pattern for wall-clock: measures the unbounded baseline's `solver_time_ms` on a larger pigeonhole instance, asserts it's `> 1ms`, then re-solves with `time_limit_ms: Some(1)` — asserts `Unknown`. |
| `generous_bound_still_solves_easy_instance` | Bounds must not turn an easy, fast solve into a false `Unknown` — a trivial 2-clause SAT instance under a large bound (1,000,000 conflicts / 10,000ms) still returns `Satisfiable`. |

All 4 pass. Self-calibration matters here: hard-coding "pigeonhole(6,5)
needs N conflicts" would silently stop testing anything if a future
CaDiCaL/rustsat upgrade changes search behavior; measuring the baseline
inside the test itself keeps the assertion meaningful regardless.

### Python-integration-level (real board, real pipeline)

Using a genuine 15-net subset of `pcb/temper.kicad_pcb`
(`ParsedPCB.nets` truncated via `pcb_override`, not `max_sat_nets` — see
the dead-code finding in Part 4) through the real
`RouterV6Pipeline.run()` path, with the same `net_class_assignments` /
`net_classes` injection `route_pcb()` performs in production:

| Run | `sat_conflict_limit` | `sat_time_limit_ms` | Stage 3 status | Completion | Length |
|---|---|---|---|---|---|
| Baseline (unbounded) | `None` | `None` | `SATISFIABLE` (0 conflicts needed) | 6/7 = 85.7% | 602.98mm |
| Conflict bound at the boundary | `0` | `None` | `SATISFIABLE` — **bound did not fire** (0 conflicts needed, 0 allowed; not exceeded) | 6/7 = 85.7% | 602.98mm |
| **Forced wall-clock bound** | `None` | `1` | **`UNKNOWN` — bound fired** | 6/7 = 85.7% | 602.98mm |

The `time_limit_ms=1` row is the direct proof requested: the bound
genuinely interrupted an in-progress solve (status flips from
`SATISFIABLE` to `UNKNOWN`), the pipeline's existing
`elif rust_result["status"] == "unknown":` handling
(`_pipeline_route.py`) engaged without raising, Stage 4 fell back to
unguided A*, and **the router still completed at the identical completion
rate and route length** as the SAT-guided run. This is the falsifier
directly confirmed at this scale: the topology guidance wasn't load-bearing
for this instance, so removing it (forcibly, via the bound) cost nothing.

The `conflict_limit=0` row is informative in the other direction: it shows
the conflict-count bound is a **true** bound — it only interrupts a solve
that actually needs to exceed it, so it never fires on an instance that's
inherently trivial. The wall-clock bound is blunter and fires on elapsed
time regardless of the solve's internal decision count, which is why it
was the reliable way to force the fallback path here.

## Part 3 — The sweep, and where it hit a wall

### Reduced-scale sweep (directly measured, this session)

| n_nets | Bound | Stage 3 time | Total wall | Completion | Length |
|---|---|---|---|---|---|
| 15 | unbounded | 241ms (0 conflicts) | 131.4s | 6/7 = 85.7% | 602.98mm |
| 15 | conflict=5000 | 238ms | 131.3s | 85.7% | 602.98mm |
| 15 | conflict=500 | 252ms | 132.0s | 85.7% | 602.98mm |
| 15 | conflict=50 | 226ms | 131.2s | 85.7% | 602.98mm |
| 15 | conflict=0 | 234ms | 130.1s | 85.7% (bound not tripped) | 602.98mm |
| 15 | time=1ms | 402ms | 128.7s | 85.7% (bound tripped, fallback used) | 602.98mm |
| 30 | unbounded | 1,409ms (0 conflicts) | 297.0s | 13/18 = 72.2% | 1,283.21mm |

Every conflict-count variant at n=15 is bit-for-bit identical in outcome
because **the actual CaDiCaL search needed 0 conflicts at both scales** —
the instance is solved by unit propagation alone, consistent with the
falsifier ("decided early"). The ~130s/~297s total-wall figures are
dominated by Stage 0/0.5/2/4 and one-time Python/Numba-JIT process
overhead, not Stage 3 — Stage 3 itself is 0.2–1.4s at these scales, nowhere
near the 1,573.8s full-board figure.

**This 15/30-net range does not reproduce Stage 3 hardness at all.**
Net-count subsampling by simple truncation gives a *qualitatively different*
SAT instance (solved by propagation, needing a fixpoint of channel/capacity
constraints among a small number of nets) than the full 108-net instance
(needing, per the existing profile, ~26 minutes and apparently much more
search). Scaling the subset size further (45, 60, 75, 90 nets) was the
planned next step but was not attempted — see Part 3's full-board finding
below, which made clear that further subset points would not by themselves
resolve the open question.

### Full-board (108 nets) — the baseline exists; bounded trials did not complete

**Unbounded baseline (not re-measured this session — cited from
`docs/evidence/2026-07-27-first-route-and-profile.md`):** Stage 3 =
1,573.8s, total = 1,648.2s, completion = 48/96 = 50.0%. Re-running this
would itself take ~27 minutes, over 2.5x the 600s per-call maximum, so it
was cited rather than reproduced.

**Bounded full-board trials (this session, all incomplete):**

| Attempt | Bound | Result |
|---|---|---|
| 1 | `conflict_limit=1000` | Did not return within 600s (killed). |
| 2 | `time_limit_ms=30000` | Did not return within 300s, then 300s again with finer instrumentation (killed both times). |

Per the task's own guidance ("if it still overruns, report the partial
result rather than backgrounding and waiting"), each was killed rather than
polled to completion. Killing them is what produced the finding below,
which is more informative than the number these runs were trying to
produce.

### The finding: at full-board scale, `solve()` is very likely not what "Stage 3" time actually measures

Fine-grained `Instant`-based timers were added temporarily inside
`solve_topology_rust` (the pyo3 entry point,
`packages/temper-rust-router/src/lib.rs`) around each internal step, then
removed before finalizing this change (not committed). On the real,
untruncated 108-net board:

```
[DIAG] py collect done at 29.8ms          (4,022,352 vars, 39,544 cons)
[DIAG] model_from_python done at 4038.1ms  (~4.0s for the Python -> Rust FFI conversion)
[DIAG] rewrite done at ...                 -- NEVER PRINTED. Still running past 250s
                                               when the process was killed, for both the
                                               conflict_limit=1000 and time_limit_ms=30000
                                               attempts independently.
```

`combinator::rewrite::rewrite` (the RW1–RW7 model-simplification pass,
`packages/temper-rust-router-core/src/combinator/rewrite.rs:93`) runs
**before** CNF encoding and **before** `solve_with_cadical` is ever called
— it is entirely outside the scope of the bound this task added. On a
model with 4,022,352 variables and 39,544 constraints, it did not finish in
either of two independent >=250s windows.

A concrete candidate for the cost: `subsume_capacity`
(`rewrite.rs:433`) does pairwise capacity-constraint subsumption checking
within each channel group, in a `while`-fixpoint loop around a nested `for
&i in indices { for &j in indices { ... } }` double loop
(`rewrite.rs:495-540`) — O(n²) per channel group per fixpoint iteration.
If a channel group at full-board scale holds hundreds to low-thousands of
capacity constraints (plausible with 39,544 total constraints across many
channels), this is a completely different and larger algorithmic problem
than the SAT solve itself. **Not confirmed as *the* cause** (the process
was killed before `rewrite` returned, so no direct profile of *which* RW
pass is slow exists) — flagged as the most likely candidate based on
reading the code, not measured in isolation.

**This means the task's own premise needs a caveat.** The original
profiling doc attributed "100.0 of 103.6 seconds inside `_run_stage3`" to
"the CaDiCaL SAT solve itself," but its own text notes this was inferred
from a single opaque `cProfile` frame around the whole
`solve_topology_rust` native call — "cProfile cannot see inside the
Rust/C++ frame." That attribution was never actually isolating
`solver.solve()` from `model_from_python` + `rewrite` + `encode_to_cnf`,
all of which execute inside that same opaque frame. This session's
internal Rust timers are the first measurement that actually separates
those steps, and on the true full-board model, `rewrite` alone exceeds
what a bounded `solve()` could possibly need to contribute.

**Consequently: the bound added by this task, while correctly implemented
and verified to work exactly as specified, is very likely not sufficient
by itself to cut Stage 3 from 26 minutes to a small number at full-board
scale** — if `rewrite` is genuinely the dominant cost, a solver time/conflict
bound only ever gets a chance to apply after `rewrite` has already returned
control. This is a real finding, not a hedge: it is reported here rather
than acted on, because fixing `rewrite`'s complexity is a separate,
substantially larger investigation outside this task's scope (a solver
configuration change), and because the task explicitly said not to guess.

## Part 4 — Adjacent dead-code finding (informational, not fixed)

`RouterV6Pipeline.max_sat_nets` / `_select_sat_nets()`
(`_pipeline_route.py:45-51`) computes a `target_names` net subset, but it
is **never threaded into `ModelBuilder`** or otherwise used to restrict
which nets enter the SAT model (`_pipeline_route.py:224-226,275-276`) — the
only place `target_names` is read is a verbose-mode print statement. If the
original 2026-07-27 profiling doc's "15-net subset" Stage 3 measurement
(98.2s / 106.1s) was produced via `max_sat_nets=15` rather than a genuine
net-list truncation (this session used `pcb_override` with a truncated
`ParsedPCB.nets`, which *does* restrict the model), it would have silently
solved the full-scope SAT model while reporting itself as a 15-net
measurement — which would reconcile that doc's ~100s figure with this
session's independently-confirmed ~0.24s for a genuine 15-net subset.
**Not confirmed** (the exact invocation that produced that doc's number
isn't available to re-inspect), but it is consistent with every other
finding in this document, and worth checking before trusting any
`max_sat_nets`-scoped measurement in this codebase's history.

## Recommended default

**`sat_conflict_limit=20_000`, `sat_time_limit_ms=None`.**

Reasoning:
- Every real SAT instance measured this session (15 nets, 30 nets)
  resolved in 0 conflicts — 20,000 is far above anything a well-behaved
  instance needs, so the default costs nothing when the solve is easy (the
  common case, per the falsifier).
- Conflict count is deterministic given a fixed CNF (unlike wall-clock
  time, it doesn't depend on machine load or what else is running), so
  it's the safer default for reproducible CI/local behavior. `time_limit_ms`
  is left as an opt-in secondary bound for callers who want a hard
  real-time ceiling regardless of machine variance (e.g., a CI job with its
  own timeout).
- **This default is a low-risk safety net against a pathologically hard
  SAT instance, not a verified fix for the specific 1,573.8s full-board
  measurement** — see Part 3. If a future measurement confirms `rewrite`
  (not `solve()`) dominates at full scale, this default should be kept
  regardless (it's harmless and protects against a genuinely hard instance
  the solver might hit on some other board), but the *actual* full-board
  wall-time fix likely lives in `combinator::rewrite::rewrite`'s algorithmic
  complexity, not in this bound.
- Do not disable Stage 3 by default — nothing measured here shows Stage 3's
  topology guidance is worthless; the one case where it was actually
  removed (forced via `time_limit_ms=1` at n=15) cost 0% completion and 0mm
  route length, which argues Stage 3 is *sometimes* free lunch, not that it
  should be turned off.

## Verification

- Rust crate builds clean in both `packages/temper-rust-router-core`
  (`cargo build --release`, `cargo clippy --release` — 0 warnings) and
  `packages/temper-rust-router` (`uv run maturin develop --release`,
  the correct build path for a pyo3 extension module — a bare `cargo
  build` fails to link, expected/documented behavior, not a regression).
- `cargo test --release` in `temper-rust-router-core`: **101 tests passed,
  0 failed** (97 pre-existing + 4 new bound-verification tests listed in
  Part 2).
- `make netlist`: **76 assertions passed, 0 failed.**
- `scripts/check_domain_partition.py`: exit 0 (0 domain crossings, 0
  isolator-barrier breaches, 0 protective-impedance chain defects).
- `scripts/capacity_budget_gate.py`: exit 0 (0 defects).
- `scripts/mpn_fabrication_gate.py`: exit 0 (0 new violations).
- `scripts/check_derived_doc_drift.py`: exit 0.

## UNVERIFIED

- Whether the "decided early" falsifier generalizes to the true full-board
  (108-net) SAT instance — every full-board trial attempted this session
  (bounded or unbounded) either wasn't re-run (unbounded, cited from prior
  evidence instead, ~27min cost) or didn't complete within the maximum
  600s/300s single-call budgets (both bounded attempts, killed).
- Full-board bounded Stage 3 time, total wall time, completion rate, and
  quality proxy — not measured; see above.
- Whether `combinator::rewrite::rewrite`'s `subsume_capacity` pairwise loop
  (`rewrite.rs:495-540`) is actually the dominant full-board cost, or
  merely the first of several slow RW passes — the process was killed
  before `rewrite` returned, so no isolated per-RW-pass profile exists.
- Whether the original 2026-07-27 profiling doc's "15-net subset"
  measurement genuinely restricted the SAT model to 15 nets, or (via the
  `max_sat_nets` dead-code path documented in Part 4) silently solved the
  full model while labeled as 15 nets — not confirmed against that
  session's actual invocation.
- Full-board DRC violation count under a bounded solve (the existing
  full-board unbounded DRC count is itself UNVERIFIED per
  `docs/evidence/2026-07-27-first-route-and-profile.md`).
- Whether `sat_time_limit_ms` set in addition to `sat_conflict_limit` (both
  bounds active) behaves as "whichever fires first wins" under real
  production load — verified only individually (Part 2), not in
  combination.

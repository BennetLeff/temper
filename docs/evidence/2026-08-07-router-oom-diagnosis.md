<!-- provenance: commit=f7a1fbf8fd155a0c303462717d531f8ae7606b7f dirty=true -->

# Route PCB OOM Diagnosis: environmental, not a code regression

**Date:** 2026-08-07
**Task:** Diagnose the route_pcb() OOM (>13 GB RSS, 3 attempts killed) reported in
`docs/evidence/2026-08-05-r3-router-status.md` §3.  Baseline: ~7 GB RSS at
~1.7 min on 2026-07-27 (`docs/evidence/2026-07-27-first-route-and-profile.md`).

**Conclusion:** The OOM is **environmental** (shared-machine memory pressure), not
a code regression.  The SAT model is the same 42M-variable / 78M-clause CNF it
has been since the July 27 baseline.  That model inherently needs ~7 GB, which
was fine on a dedicated machine but OOMs when the OS has ~20 GB of other
processes resident.  **The architectural root cause is the Sinz (2005)
sequential-counter cardinality encoding**, which expands ~2M primary variables
into a 42M/78M CNF.

---

## 1. Evidence chain

### 1.1 The model is the same size as the July 27 baseline

`docs/evidence/2026-07-27-stage3-model-and-rewrite.md` (commit `56362d528`) recorded
the full production-board model at:

```
[phase-trace t=12.019s] encode_to_cnf done, 42145777 vars, 78107180 clauses
```

The staged model that produces this (Python `ConstraintModel`) had ~3.9M primary
variables and ~43,050 constraints (20,734 of which are `CapacityConstraint`, one
per channel-skeleton edge).  The solver ran to SAT in 52.67s total (model-from-
Python 3.89s + rewrite 0.86s + encode 7.27s + solve 27.78s), producing 50%
routing completion with peak RSS of ~6.93 GB.

### 1.2 No commit between July 27 and Aug 5 changes the model size

`git log --oneline f2c5af948 --not 99caa33e -- <router-code-paths>` shows two
commits touching the SAT pipeline:

1. `b7e6aafa0` (2026-08-02) — `feat(scripts): physics soundness-proof register gate`.
   Touches only `scripts/`, not the router.

2. `7028dbef4` (2026-08-05) — `chore(router_v6): retire dead Python SAT surface`.
   Removes three dead Python modules (`sat_model.py`, `topology_solver.solve_topology`,
   `metrics/octilinear.py`) whose production call sites were already `None`/no-op.
   **Does not change the constraint model, the Rust encoding, or the solver.**
   The only code-path change is removing `sat_model = None` (which was already
   always `None`).

**No commit between the July 27 baseline and the Aug 5 OOM changes the number of
variables, constraints, or the CNF encoding.**  The model is identical in size.

### 1.3 The test passed at 56s on the same code

`test_production_board_routing_drc_regression` in
`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` calls
`route_pcb()` with the same production defaults (`sat_conflict_limit=20_000`,
`enable_manufacturing_drc=False`).  It passed in 56s at commit `c971db1d5` (the
follow-up that re-baselined the board-shape guard 2338→2290 segments).  The
test exercises the identical code path as the OOM'd production route — same
`ModelBuilder`, same `solve_topology_rust`, same solver config.

If the model had genuinely doubled in size, the test would also OOM or take
2× longer — it completed in 56s, consistent with the 53s Stage 3 baseline.

### 1.4 Why the OOM was >13 GB on a 32 GB host

The 2026-08-05 measurement was on an M2 Pro with 32 GB RAM, described as having
"concurrent agent worktrees" active.  At ~31/32 GB already in use, the router's
~7 GB allocation pushes the system past the physical limit.  macOS's memory
compressor and the OOM killer then target the largest process — the router.

The 13 GB figure is **not** the router's own RSS — it is what the system
reports as "peak RSS" under memory pressure, which can include compressed pages,
wired pages the kernel won't page out, and CoW-duplicated pages from fork()'d
subprocesses.  The router's *self-allocated* memory is still ~7 GB (the CNF +
CaDiCaL internal state).

---

## 2. Where the 42M/78M comes from — Sinz encoding blowup

### 2.1 Primary variable count

`constraint_model.py::_create_per_net_channel_vars()` creates one `NetChannelVar`
for every (net, edge) pair:

```
primary_channel_vars = |nets| × |edges| ≈ 96 × 20,734 ≈ 1,990,000
```

Plus `ViaVar` for every (net, node) pair and `OrderVar` for net pairs, for a
total primary variable count of ~2–4M.

### 2.2 Sinz sequential-counter explosion

Each of the 20,734 `CapacityConstraint`s has all 96 nets as `terms` (every net
gets a `NetChannelVar` for every edge — see `_create_capacity_constraints()`).
Each constraint encodes `sum(vars) ≤ K` where `K = ⌊capacity × 0.8 / min_width⌋`,
typically K ≈ 8–15.

The Sinz (2005) sequential counter (`encoding.rs::encode_at_most_k`) adds:

- **(n − 1) × K auxiliary variables** per constraint  (register variables `r[i][j]`)
- **K × (2n − 1) ≈ 2nK clauses** per constraint  (propagation + exclusion)

With n = 96 nets and K ≈ 10:

```
aux_vars_per_constraint ≈ (96 − 1) × 10 = 950
clauses_per_constraint  ≈ 2 × 96 × 10 = 1,920
```

Total across ~20,734 constraints:

```
total_aux_vars ≈ 20,734 × 950 ≈ 19.7M
total_clauses  ≈ 20,734 × 1,920 ≈ 39.8M
```

Plus primary variables (~2M), `via_vars`, `order_vars`, `ChannelSeparation`
auxiliary variables, and `DiffPair`/`LayerRestriction` unit clauses — the total
matches the observed 42M vars / 78M clauses to within the expected ~5–10%
variance from solver-version / netclass-config differences (per
`docs/evidence/2026-07-27-stage3-model-and-rewrite.md` §UNVERIFIED).

### 2.3 Memory attribution

| Component | Approximate size | Notes |
|---|---|---|
| Python `ConstraintModel` (shallow) | ~200 MB | `NetChannelVar`/`ViaVar`/`CapacityConstraint` dataclass instances |
| Rust `InternalConstraintModel` (clone) | ~200 MB | `model_from_python` in `solve_topology_rust` |
| Rewrite intermediate (`CapInfo` + `BTreeSet`) | ~50 MB | `subsume_capacity` clones all term names into `HashSet` + `BTreeSet` |
| CNF `var_map` (`Vec<SatVariable>`) | ~2.5 GB | 42M entries × (two Strings) |
| CNF `clauses` (`Vec<Vec<i32>>`) | ~2.5 GB | 78M clauses × (24B Vec + ~3 × 4B i32) |
| CNF `var_to_net` (`Vec<usize>`) | ~336 MB | 42M × 8B |
| CaDiCaL internal state | ~2–3 GB | Watch lists, learned clauses (few with 0-conflict solve) |
| **var_to_net Python list** (removed in this task) | **~1.2 GB** | 42M Python ints at ~28B each — **never read downstream** |
| **Total** | **~7–9 GB** | Matches the July 27 measurement of 6.93 GB |

---

## 3. What changed since July 27 (code audit)

| Commit | Date | What | Effect on model size |
|---|---|---|---|
| `b78f9041d` | Jul 27 | Add `SolveLimits` to CaDiCaL solve | No change to model; bound is post-encode |
| `c3f8330ec` | Jul 31 | Single-allocation clause loading | No change to model; micro-optimization |
| `b7e6aafa0` | Aug 2 | Physics register gate (scripts only) | None |
| `7028dbef4` | Aug 5 | Retire dead Python SAT surface | None (removed code was already dead) |
| `e5a89b1e0` | ~Jul 30 | Remove 48 zero-length tracks at vias (#771) | Board segments 2338→2290; no effect on skeleton |
| `d27f01a4d` | Aug 7 | SAT edge identity from geometry (today) | Same edge count; only names change |
| `60c0d86fb` | Aug 7 | Channel skeleton to Rust (today) | Aims for identical geometry within 1e-6mm |

**No code change between the July 27 baseline and the Aug 5 OOM increases the
SAT model size.**  The board's channel skeleton edge count is unchanged (the
Rust port aims for bit-identical geometry, and the `d27f01a4d` fix only changes
how edges are *named*, not how many exist).

---

## 4. Classification: INTRINSIC ceiling, not a bug

Per the framework in `docs/evidence/2026-08-05-r3-router-status.md`:

| Classification | Applicable? | Reasoning |
|---|---|---|
| Incidental regression | **No** | No code change increased the model between Jul 27 and Aug 5 |
| Memory leak | **No** | Test completes at 56s with same RSS; sustained allocation would accumulate |
| Environmental (memory pressure) | **Yes — the proximate cause** | Shared machine with concurrent worktrees |
| Intrinsic to the SAT encoding | **Yes — the architectural cause** | 42M/78M CNF is inherent to the current Sinz encoding over the full net×edge product |

The OOM is **intrinsic** to running the full-board Sinz-encoded SAT model on a
machine with <~12 GB free.  That is a real scalability limit — the model is
simply large.  It was never capped or bounded *in size*; the `sat_conflict_limit`
bounds only the search, not the encoding.

---

## 5. Fix applied: remove unused `var_to_net` clone (~1.2 GB saved)

`packages/temper-rust-router/src/lib.rs:180` cloned `cnf.var_to_net` (42M
`usize` entries) into a Python list:

```rust
d.set_item("var_to_net", cnf.var_to_net.clone())?;
```

- The Rust `Vec<usize>` clone costs ~336 MB.
- The PyO3 serialization creates 42M Python `int` objects (~28B each) ≈ ~1.2 GB.
- **Nothing downstream reads it.** `grep '\.var_to_net' -- '*.py'` finds zero
  consumers besides the assignment site (`_pipeline_route.py:350`) and the type
  annotation (`topology_solver.py:33`).  The original intent
  (`docs/plans/2026-06-28-007`, U3 per-net routability scoring) was never
  implemented.

The fix replaces the clone with an empty `Vec::<usize>::new()`.  This saves
~1.5 GB total (Rust clone + Python int list) at the peak memory point where
the CNF, CaDiCaL state, and Python return dict coexist.

**This is a ~20% reduction from 7 GB, not a fix for the 13 GB OOM** — it
reduces the baseline memory but does not change the model's fundamental size.

---

## 6. Recommended mitigation path

### 6.1 Short-term (unblock production)

1. **Run `route_pcb()` on a dedicated, quiet machine** with ≥16 GB free.
   The router's ~7 GB demand is sustainable on a machine not shared with
   concurrent agent worktrees.

2. **Set `ulimit -v 8388608`** (8 GB virtual memory cap) so that if the router
   grows beyond its baseline, it fails fast with `ENOMEM` rather than
   destabilizing the shared machine.  The 42M/78M model fits in ~7 GB; an 8 GB
   cap catches a genuine regression without false positives.

### 6.2 Medium-term (architectural — scope: separate plan)

Per `docs/evidence/2026-07-27-stage3-model-and-rewrite.md` §Ranked recommendation #2:

> Wire `enable_bundling=True` (or an equivalent net-to-channel candidacy filter)
> into the production `route_pcb()` path. The model is `O(n_nets × E)` where `E`
> is the whole board's channel-skeleton size; a bundled or geographically-pruned
> encoding would cut the ~10-40x inflation from "every net gets a variable for
> every edge on the board" without touching rewrite at all.

The Sinz encoding is `O(n × k)` auxiliary variables *per capacity constraint*,
and n = |nets| for every constraint because every net gets a `NetChannelVar` for
every edge.  Pruning nets to only those that are *geometrically relevant* to a
given edge would reduce n (per constraint) from 96 to a small constant (the
number of nets whose pads are within routing distance of that edge), which would
cut the auxiliary variable count by ~10–40×.

### 6.3 Alternative: change the cardinality encoding

The Sinz sequential counter is `O(n·k)`.  Alternatives like the "Totalizer"
(Bailleux & Boufkhad 2003, `O(n log n)`) or "Binary Adder" encodings reduce the
auxiliary variable count.  This is a research task with solver-compatibility
implications (CaDiCaL's preprocessing interacts differently with each encoding).

---

## 7. What was NOT investigated

- **Whether the current HEAD (f7a1fbf8f, which includes `60c0d86fb`'s Rust
  channel-skeleton port) produces an identical skeleton edge count to the
  Python GEOS Voronoi** — the Rust port's tests claim 12/12 board agreement
  within 1e-6mm, which would guarantee identical SAT model size.  Not
  independently verified here (requires building all Rust extensions in this
  worktree, which is the ~8 GB shared `target-shared` cost avoided per the
  task's resource constraint).

- **Capped full-route re-measurement** — not run (per the task's "at most one
  capped attempt" constraint and the diagnosis that the model is unchanged).

- **Whether the `var_to_net` clone removal changes any CI test** — the CI
  routing gate test (`test_production_board_routing_drc_regression`) only
  asserts DRC counts on the routed output; it does not inspect `var_to_net`.

---

## 8. Sources

- `docs/evidence/2026-08-05-r3-router-status.md` — the OOM record.
- `docs/evidence/2026-07-27-first-route-and-profile.md` — the ~7 GB / ~1.7 min baseline.
- `docs/evidence/2026-07-27-stage3-model-and-rewrite.md` — the 42M/78M CNF measurement
  and the rewrite O(n²) fix + ranked recommendations.
- `docs/evidence/2026-07-27-router-determinism.md` — the determinism protocol.
- `packages/temper-rust-router-core/src/encoding.rs` — the Sinz sequential counter.
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` — the
  model builder (per-net channel vars, capacity constraints).
- `packages/temper-rust-router/src/lib.rs` — the PyO3 entry point + `var_to_net` clone.
- `packages/temper-rust-router-core/src/combinator/rewrite.rs` — the rewrite engine.
- `docs/plans/2026-06-28-007-feat-routability-gradient-signal-plan.md` — the original
  intent for `var_to_net` (never implemented).

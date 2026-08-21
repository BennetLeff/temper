---
title: Stage 3 SAT memory blowup — investigation (net-count dependence confirmed)
type: evidence
date: 2026-08-15
topic: router-stage3-memory
status: measured
---

# Stage 3 SAT memory blowup — investigation (2026-08-15)

**Branch:** `investigate/stage3-memory-blowup` (worktree
`/tmp/opencode/agent-stage3-memory`), base `origin/main @ 8f21d2725`.
**Board:** `pcb/temper.kicad_pcb` byte-identical to `origin/main`
(sha256 `6928b7c8...`), **never modified** by this investigation.

Investigation of handoff §6 item 5 (memory blowup at a fixed pipeline
boundary inside `_run_stage3`) and §8 item 6 (`power_in.ntc-no`
ampacity). The handoff's next step was: instrument one level deeper
around `ModelBuilder.build()` and `solve_topology_rust`, and test the
net-filtering hypothesis ("filtering to a single net should collapse the
dominant `|nets| × |edges|` Sinz-encoding term from ~100 nets to 1").

## TL;DR

1. **Call path traced** (below): `route_board.py` → `route_pcb` →
   Rust `RouterPipeline` orchestration → Python `_run_stage3` →
   `ModelBuilder.build()` (Python shim → Rust `_mb.build()`) →
   `py_vars`/`py_cons` lists → `solve_topology_rust` (Rust:
   `model_from_python` → `rewrite` → `encode_to_cnf` → CaDiCaL).
2. **Net-filtering hypothesis CONFIRMED, quantitatively.** The model is
   exactly `|nets| × |edges|` raw variables — verified exact at two
   scales: 110 nets × 59,008 edges = 6,490,880 vars (probe, 2-layer
   skeleton), and the real route's own mem-trace showing a 10-net batch
   at 2,041,440 vars ⇒ **204,144 edges** ⇒ 22,455,840 raw vars at 110
   nets (4-layer skeleton, escape vias included). A single-net model
   builds the same skeleton to 59,008 vars and its CNF collapses to
   **12,284 clauses, solved SAT in 4.6 ms** — the Sinz AtMostK encoding
   (the blowup) simply never fires with one term.
3. **The blowup is the monolithic Sinz sequential-counter encoding over
   ~204K capacity constraints × 110 nets each**: ~768M CNF clauses /
   ~399M CNF vars at the real skeleton, ≈ **~182–200 GB** (56 B/clause in
   our `Vec<Vec<i32>>`, 152–175 B/clause inside CaDiCaL, per the measured
   per-item costs in `docs/plans/2026-08-12-004`). The machine has 62 GB.
   The process is OOM-killed at ~58 GB inside `encode_to_cnf` — before
   CaDiCaL even starts loading clauses. That is the "18 GB → 58 GB in
   ~15 s at t≈260–270 s, every time" observation.
4. **Two net-filtering mechanisms exist; one is dead.** `max_sat_nets` /
   `_select_sat_nets` (the option that *looks* like net selection) is
   **print-only** — `target_names` is computed and printed, never passed
   to `ModelBuilder` or `solve_topology_rust` (`_pipeline_route.py:266,
   321-322`). The only path that actually subsets nets is
   `enable_net_batching=True` (`run_net_batched_stage3` →
   `_solve_subset` → `ModelBuilder(nets=nets_subset)`), which is off by
   default and was exactly the "~1 GB, 8–11 min" recipe all recent
   successful routes used.
5. **NTC ampacity (item 6)**: `power_in.ntc-no` requires **4.16 mm
   minimum copper width (15 A, 20 °C rise, 2 oz external; class width
   5.0 mm)**. Committed copper is 30 × 0.508 mm segments — **8× too
   narrow**. Its four pads (K1, RT1, U1, U2) span nearly the whole board
   (x = 28 … 168 mm); a single-hull pour threading them at ≥4.16 mm necks
   fragments under DRC-aware fill for geometric reasons, not solver
   reasons — confirmed on a real batched route this session: the pour
   split into 2 hulls × 2 layers, and the drawn traces are still
   0.508 mm because the Stage-4.4 pass-through defect (declared class
   width never reaches `assign_trace_widths`) is still live. The memory
   bug blocks the monolithic route that would let the router evaluate a
   full-board pour; the batched recipe routes but its Stage 3 capacity
   constraints are vacuous at `batch_size=10` (plan 2026-08-12-003's
   finding). **Recommended path: geographic pruning (or `batch_size` ≥
   K), fix the Stage-4.4 width pass-through, re-place K1/RT1/U1/U2 to
   shrink the net's bounding hull — or manual 5.0 mm routing.**

## 1. Call path (traced, not inferred)

```
scripts/route_board.py route_once()
  └─ temper_placer.router_v6._adapter_convert.route_pcb()      (line 223)
       └─ RouterV6Pipeline(...).run(...)                        (_pipeline_core.py:339)
            └─ temper_orchestration.RouterPipeline().run(...)   (Rust orchestration,
               router_pipeline.rs)                              drives stages via call-backs)
                 └─ (Rust) calls back self._run_stage3(pcb, stage2)
                      └─ router_v6._pipeline_route._run_stage3  (_pipeline_route.py:234)
                           ├─ net-batching branch? ─ run_net_batched_stage3 ─ _solve_subset
                           │    (ModelBuilder(nets=nets_subset) + solve_topology_rust per batch)
                           └─ ModelBuilder(...).build()          (constraint_model.py:282)
                                ├─ self._rust.build()            (temper-design-bundle
                                │    model_builder.rs: create_per_net_channel_vars
                                │    → |nets|×|edges| NetChannelVars; create_capacity_
                                │    constraints → 1 CapacityConstraint per edge,
                                │    terms = all |nets|)
                                └─ PCL apply (no-op when TEMPER_PCL_CONSTRAINTS unset)
                           ├─ py_vars = list(model.variables); py_cons = list(...)
                           └─ solve_topology_rust(py_vars, py_cons, net_names,
                                                  conflict_limit=20_000)   (temper-rust-router lib.rs:156)
                                ├─ model_from_python
                                ├─ combinator rewrite (RW1-RW7)
                                ├─ encode_to_cnf  ← SINZ SEQUENTIAL-COUNTER BLOWUP HERE
                                │    (encoding.rs:141; encode_at_most_k per CapacityConstraint
                                │     with n=|nets| terms, O(n·K) aux vars + O(n·K) clauses each)
                                └─ solve_with_cadical (CaDiCaL) (solver.rs:62)
```

Stage 3 runs **unconditionally before Stage 4** in every route — a
`route_pcb()` crash at this point is Stage 3 SAT, not A* (handoff
correction log). The default `route_board.py` invocation passes
`enable_geographic_pruning=False`, `enable_net_batching=False`,
`enable_nlayer_astar_spike=False` — i.e. the **monolithic** Stage 3.

## 2. Skeleton sizes measured on the current board

Stage 2 run directly (probe committed as
`docs/evidence/scripts/2026-08-15-stage2-skeleton-probe.py`), plus the
ground-truth measurement from the real route's own mem-trace (below):

| measurement | F.Cu | B.Cu | In1.Cu | In2.Cu | **total edges** | raw vars @110 nets |
|---|---:|---:|---:|---:|---:|---:|
| probe, `use_declared_layer_roles=False` (zone-content; NOT the pipeline), `escape_vias=[]` | 0 (plane) | 0 (plane) | 29,504 | 29,504 | **59,008** | 6,490,880 |
| probe, `use_declared_layer_roles=True` (**the real pipeline's setting**, `router_pipeline.rs:269`), `escape_vias=[]` | 52,815 | 22,538 | 29,504 | 29,504 | **134,361** | 14,779,710 |
| **real route** (`route_board.py --net-batching`), `ModelBuilder.build()` mem-trace: 10-net batch → 2,041,440 vars ⇒ **204,144 edges** | — | — | — | — | **≈204,144** | **22,455,840** |

Escape vias are obstacles: they *enlarge* the medial-axis skeleton
(204,144 real vs 134,361 without them). The real route's 204,144-edge
skeleton matches the 2026-08-12-004 plan's "204,490-edge current
skeleton" to within 0.2% — that plan's full-scale extrapolation was
correct, and this session's probe without escape vias under-estimated by
~34%. The verdict is the same either way (Section 4).

**ModelBuilder.build() verified exact** at the 2-layer scale: built
6,490,880 vars / 30,830 constraints in 65 s, RSS 1.56 GB — the var count
matches `|nets| × |edges| = 110 × 59,008` exactly (Rust packed arena;
the 326.7 B/var model-layer cost measured in 2026-08-12-002 has since
been fixed). The real route's batch build (10 nets → 2,041,440 vars /
109,152 cons) matches `10 × 204,144` exactly.

## 3. Net-filtering hypothesis: CONFIRMED by controlled experiment

Same process, same skeleton, same Stage 2 output — only the nets list
passed to `ModelBuilder` differs:

| arm | nets | raw vars | constraints | CNF vars | CNF clauses | solve |
|---|---:|---:|---:|---:|---:|---|
| FULL | 110 | 6,490,880 | 30,830 | ~62M (est.) | ~113M (est.) | **not attempted** (needs ~25–28 GB at 2-layer; ~182–200 GB at the real 4-layer skeleton) |
| SINGLE (`w1_1`) | 1 | 59,008 | 30,030 | 59,008 | **12,284** | **SAT, 4.6 ms, RSS +17 MB** |

The single-net arm collapses the CNF by ~4–5 orders of magnitude: with
one term per capacity constraint, `max_nets < n_terms` never fires, so
`encode_at_most_k` emits nothing (`encoding.rs:148,210` guard). The
dominant term is exactly `|nets| × |edges|` and the Sinz multiplier is
net-count-dependent by construction.

**Therefore**: the handoff's hypothesis is confirmed — *net filtering
reaches the capacity-constraint builder only through the `nets` argument
of `ModelBuilder`*, and the default route passes all 110 nets. The two
named suspects in the hypothesis were:
- *"net-filtering is not reaching whatever builds the capacity
  constraints"* — **TRUE** for `max_sat_nets`/`_select_sat_nets`, which
  is dead-end print-only (`_pipeline_route.py:266,321-322`; verified no
  other reference). It selects nets and then only *prints* them.
- *"a net-count-independent blowup"* — **FALSE** for the model/CNF layer.
  The blowup scales linearly in nets (the Sinz multiplier is O(n·K) per
  constraint, n = nets). There is no net-count-independent term large
  enough to matter.

## 4. What the blowup is (sized, current board)

Full monolith at the real route's 204,144-edge skeleton, 110 nets:

| layer | size | cost | total |
|---|---:|---:|---:|
| raw model (packed, post-08-12-002 fix) | 22.46M vars | ~8.9 B/var | ~0.2 GB |
| CNF `var_map` + aux-var names | ~399M vars (22.5M primary + ~377M Sinz aux) | 56 B/aux name (dead — nothing reads it, U1 of 08-12-004) | ~21.1 GB |
| CNF clauses (`Vec<Vec<i32>>`) | ~768M | 56 B/clause (U2 of 08-12-004 packs to 13.8 B) | ~43.1 GB |
| CaDiCaL clause storage | ~768M | 152–175 B/clause (measured, not changeable by representation) | **~117–135 GB** |
| **total** | | | **~182–200 GB** |

(Scaling constants: 1,846 aux/constraint and 3,767 clauses/constraint
from the 2026-07-27 42,145,777-var / 78,107,180-clause measurement at
20,734 constraints, applied to ~204K constraints. These numbers are
identical to 2026-08-12-004's full-scale estimate — this session
independently confirmed its 204,490-edge assumption against the real
route.)

The machine has 62 GB. The observed "18 GB → 58 GB in ~15 s, every
time, inside `_run_stage3`" is `encode_to_cnf` allocating at
~2.7 GB/s until the OOM killer fires; the process never reaches
CaDiCaL's clause loading (which alone would need another ~117–135 GB).
**Attribution is therefore: monolithic Stage 3 CNF encoding, not A\*,
not `ModelBuilder.build()`** (which completes at ~1.5 GB), and not a
leak — a fixed, intrinsic ~182–200 GB demand against a 62 GB machine.

**The "~1 GB / 8–11 min uninstrumented full route"** in the handoff is
the **batched** recipe (`route_board.py --net-batching`, the only
configuration that has produced routed boards since 2026-08-12 — the
08-13 netclass-scoping measurements ran it at 485.6 s ≈ 8.1 min). The
die-at-58 GB observation is the **monolithic** default (`route_board.py`
without `--net-batching`), which has never completed on this board. The
"under coverage" qualifier is how the observer happened to run the
monolith, not a coverage-specific effect: coverage inflates earlier-stage
Python memory (18 GB pre-Stage-3 baseline) but the death is the
monolith's intrinsic CNF demand.

## 5. Fix options (ranked)

1. **Net-batching is the working recipe today** (`--net-batching`,
   `batch_size=10`): fits (per-batch workers ~1–5 GB), ~8 min, produces
   routed boards. Caveat (plan 2026-08-12-003, not landed): at
   `batch_size=10 < K≈17`, `encode_at_most_k` never fires, so the batched
   SAT solve is **capacity-vacuous** (0 conflicts / 0 decisions) — it
   unblocks routing but does not enforce channel capacity.
2. **Raise `batch_size` above K** (owned by 2026-08-12-003): per-batch
   CNF becomes bounded-by-batch-size; with the U1/U2 representation
   fixes (08-12-004) each batch fits comfortably. This restores capacity
   enforcement *and* fits memory.
3. **Geographic pruning** (`--pruning`): per-(net, edge) candidacy by pin
   proximity (`model_builder.rs:1413-1435,1529-1535`), collapsing the
   dominant term to `Σ_nets local_edges(net)`. The architectural fix the
   2026-07-27 and 2026-08-07 evidence docs both recommended; not measured
   in this session (would need a route run with `--pruning`).
4. **Wire `_select_sat_nets`/`max_sat_nets` for real**: pass
   `target_names` as the nets subset to `ModelBuilder` (it is currently
   print-only). This is the "selective SAT" the option name promises; it
   changes which nets get SAT topology (small nets first) rather than
   fixing the model size for the nets that remain.
5. **CNF representation fixes (08-12-004 U1/U2)**: save ~42 GB of our-side
   storage, but CaDiCaL's 117–135 GB share is untouched — do not make the
   monolith fit; worth doing anyway (free win, applies per-batch).

**Not a fix**: a different cardinality encoding (totalizer/commander) —
real but a separate solver/encoding project (08-12-004's "Option 4").

## 6. Instrumentation added (committed on this branch)

- `TEMPER_STAGE3_MEM_TRACE=1`: `[mem-trace pid=.. rss_kb=..]` stderr
  lines at `_run_stage3` ENTER, `ModelBuilder.build()` ENTER / rust-done
  / PCL / EXIT, `solve_topology_rust` ENTER/EXIT,
  `_build_clause_origin` done (`_pipeline_route.py`,
  `constraint_model.py`). Off by default.
- `docs/evidence/scripts/2026-08-15-stage3-rss-watchdog.py`: external
  `/proc/<pid>/status` VmRSS/VmHWM sampler that spawns the command and
  logs samples (used for the batched route run below).
- `docs/evidence/scripts/2026-08-15-stage2-skeleton-probe.py`: Stage 2 + full/
  single-net ModelBuilder controlled experiment (Section 2/3).

## 7. `power_in.ntc-no` ampacity (handoff §8 item 6)

**Requirement** (docs/evidence/2026-08-13-netclass-current-scoping.md
§1.2, IPC-2221B, k=0.048 external, re-derived independently):
15 A design current, 20 °C trace rise, 2 oz external →
**4.1559 mm minimum width**; class `HighVoltage` width 5.0 mm (clears
both the 4.16 mm trace and 4.77 mm pour minima).

**Current committed copper** (`pcb/temper.kicad_pcb`, net 88): 31
segments — 30 × **0.508 mm** + 1 × 0.25 mm, **0 zones**.
0.508 mm at 20 °C/2 oz carries ~3.3 A (IPC-2221B, same formula as the
scoping doc) — **~4.5× under the 15 A requirement, 8× under the required
width. Ampacity is not achieved.** (Connectivity of the four pads is
separately verified per the handoff.)

**The four pads** (net 88): K1 relay contact 13 @ (95.2, 221.4); RT1 NTC
disc pin 2 @ (40.4, 210.1); U1 TO-220-2 pin 2 @ (168.0, 223.0); U2
TO-220-2 pin 1 @ (28.3, 175.4). The net is the bus-side node of the
inrush NTC/bypass path (`+170V_BUS → U1 → ntc-no → RT1 → w1_2 → K1`), so
it is in the 15 A mains→bus current path. **The pads span x = 28–168 mm
of a ~200 mm board.** A single-hull pour joining them must thread
≥4.16 mm necks across nearly the whole board through a dense mains
obstacle field — the observed fragmentation into 47+ islands under real
DRC-aware fill is the *expected geometric outcome* of that span, not a
solver defect.

**Path forward (ranked):**
1. **Fix the Stage 3 memory path first** (Section 5 items 1–3) so a
   full-board route at 5.0 mm can be evaluated at all — today the
   monolithic route dies and only the capacity-vacuous batched route
   completes.
2. **Re-place K1/RT1/U1/U2 closer together** (placement solve) to shrink
   the net's bounding hull until a single pour can stay connected at
   ≥4.16 mm necks. This is the geometric root cause — U1 at x=168 and U2
   at x=28 are the killers.
3. **Manual routing** of a 5.0 mm trace (or pour neck) between the four
   pads as a bounded, reviewed exception.
4. Then re-run `measure_uncapped_drc.py` / pad-connectivity audit to
   verify the achieved width (the Stage-4.4 trace-width pass-through
   defect from PR #1119 §S5 — declared class width is frequently not the
   drawn width — must be fixed first or the drawn copper will not match
   the declared 5.0 mm).

### 7.1 Measured on a real batched route (this session, 2026-08-15)

Full `route_board.py --net-batching` run (503 s, 65/104 nets routed,
51/139 pad-connected, 43 fake-completion — `power_in.ntc-no` **in the
fake-completion list**: copper exists but does not join all four pads):

- **Drawn trace width: 71 × 0.508 mm segments** (+1 × 0.2, +1 × 0.3048)
  — not the declared 5.0 mm. Cause confirmed in code: the Stage-4.4
  pass-through defect is **still live** (`_pipeline_route.py:690-693`
  calls `assign_trace_widths(..., default_width=...)` only; the netclass
  `trace_width` never reaches it). `power_in.ntc-no` then keyword-matches
  `"POWER"` in `temper-geometry/src/trace_width_assignment.rs:71` and gets
  the `power_width=0.508` default. The class width is a declaration with
  no route to the drawn copper.
- **The pour split into 2 hulls × 2 layers = 4 zone blocks**: east hull
  (F.Cu+B.Cu) bbox x=[90.1,170.0] y=[221.0,229.6] spanning K1→U1; west
  hull (F.Cu+B.Cu) bbox x=[21.2,42.4] y=[173.4,212.1] spanning
  U2→RT1. The middle of the board (x≈42–90) carries no net-88 zone — a
  single hull cannot thread it at ≥4.16 mm necks. Under real KiCad fill
  each hull fragments further into islands (the handoff's 47+ figure) —
  the geometric consequence of the 140 mm pad span, now confirmed at the
  zone-outline level without needing KiCad.

## 8. What was not run, and why (honest gaps)

- **The monolithic route reproduction** (dies at ~58 GB): already
  established by the handoff ("every time"); re-running it would
  OOM-kill the shared machine for no new attribution. The attribution
  (encode_to_cnf, ~182–200 GB demand vs 62 GB) is now established by
  measurement + arithmetic instead — the mem-trace instrumentation on
  this branch is ready for a per-phase VmRSS trace of the death whenever
  the machine is quiet and an owner authorizes the OOM. **Outstanding.**
- **Geographic-pruning route** (`--pruning`): not measured (needs a
  full route); listed as the architectural fix with the net-batching
  recipe as the working fallback. **Outstanding.**
- **KiCad's exact island count** for the net-88 pour: the 4 zone hulls
  (Section 7.1) are raw outlines; KiCad's fill-time fragmentation count
  (the handoff's 47+) requires opening the board in KiCad or a
  fill-equivalent pass. The mechanism is confirmed at the outline level
  (2 hulls + fake-completion audit); the exact fill count was not
  re-derived. **Outstanding.**
- **Exact F.Cu/B.Cu edge counts under real escape vias**: the probe's
  `escape_vias=[]` under-estimated the skeleton (134,361 vs the real
  route's 204,144); the real route's own mem-trace (`ModelBuilder.build()
  EXIT vars=2,041,440` for a 10-net batch) is the ground truth used in
  Section 4.

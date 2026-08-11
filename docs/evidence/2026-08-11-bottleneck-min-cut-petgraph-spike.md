# Spike: bottleneck min-cut petgraph parity — the plan's conditional Phase E item — decision evidence — 2026-08-11

<!-- provenance: commit=753da7577 dirty=false (measurements taken against origin/main at spike base; the shipped kernel and bottleneck_geometry.py were untouched by this spike — only tests + docs landed) -->
<!-- measured_at_commit: 753da7577 (origin/main at spike base) -->

**Direct answer: the parity pass is confirmed bit-exact, and the migration is already DONE — the networkx `minimum_cut` compute now runs in the `temper-geometry` Rust crate via a hand-rolled Edmonds-Karp kernel (`min_cut_py`). The remaining "petgraph" half of the plan's conditional is a documented-KEEP: petgraph cannot reproduce networkx's min-cut *partition*, and the consumer depends on exactly that partition, so a petgraph swap would buy nothing that the existing kernel does not already provide with measured bit-exact parity.**

Verdict: **KEEP** (networkx → already-migrated Rust kernel, verified bit-exact on the production graph family; **no petgraph dependency added**). Work landed: a permanent differential pin of the min-cut kernel's (value, partition) against `networkx.minimum_cut(flow_func=edmonds_karp)` in `test_bottleneck_geometry_rust_differential.py`, plus this evidence note. No Rust algorithm changed — the Wave-4 kernel is proven, not rewritten.

---

## 0. What the plan's conditional actually asked

The Wave-4 migration plan (`docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`) records, under *Dependencies/Assumptions*:

> **networkx min-cut (`router_v6/bottleneck_geometry.py`):** the Rust kernels landed in Wave 3; the min-cut partition itself stays networkx per the partition-order follow-up recorded in `packages/temper-geometry/VERIFICATION.md` — a JUSTIFIED-KEEP candidate under R3.

and the interrogation strategy (`docs/evidence/2026-08-09-python-over-rust-interrogation.md` §2/§5 item 4) proposed:

> **networkx orchestration (4,859 LOC)** — after a petgraph min-cut parity test, extend `build_capacitated_graph_py` to return the cut (deleting the nx replay in `bottleneck_geometry.py`), then absorb `net_batching`'s batch loop.

The gate was "a petgraph parity pass". This spike evaluates that gate and records the outcome. The premise ("`nx.minimum_cut` still runs in Python") is **already stale at spike base**: commit `39711680e` (Wave 4, 2026-08-10) replaced the `nx.minimum_cut(flow_func=edmonds_karp)` call in `analyze_bottleneck` with `temper_geometry.min_cut_py` — a hand-rolled Edmonds-Karp, deliberately *not* petgraph. What the plan's conditional actually required of this spike is therefore: **measure whether the shipped Rust kernel reproduces networkx's results (the parity that the plan gated the migration on), and settle the petgraph-vs-hand-rolled question with decision-ready evidence.**

## 1. What the module uses, and at what graph sizes

### 1.1 The algorithm surface (pre-migration)

`router_v6/bottleneck_geometry.py` (1,229 LOC at spike base) used exactly **one** networkx call, in `analyze_bottleneck`:

```python
cut_value, (reachable, non_reachable) = nx.minimum_cut(
    g, src, sink, capacity="capacity",
    flow_func=nx.algorithms.flow.edmonds_karp,
)
```

Everything else networkx-related (`_build_capacitated_graph` returning an `nx.DiGraph`) was the input to that single call. networkx is pinned at **3.6.1** (`uv.lock`).

### 1.2 networkx 3.6.1's actual min-cut internals (read from installed source)

Three facts from `networkx/algorithms/flow/` (verified against the installed 3.6.1):

1. **`edmonds_karp_core` selects augmenting paths with a bidirectional BFS** (`edmondskarp.py:40-69`): it alternates a forward frontier from `s` and a backward frontier from `t`, expanding whichever is smaller, and returns the *first meeting node*. It is **not** a plain forward FIFO BFS. (The Rust kernel's comment — "matching networkx's `edmonds_karp_core` (list.pop(0) = FIFO)" — is inaccurate about modern networkx; this is exactly why parity had to be measured, not assumed.)
2. **Residual reverse edges carry capacity 0** for directed graphs (`build_residual_network`: `R.add_edge(v, u, capacity=0)`), matching the Rust kernel's residual model exactly. (Undirected graphs get full-capacity reverse edges — the common textbook description — but the bottleneck graph is a `DiGraph`, so the directed rule applies.)
3. **`minimum_cut`'s partition is a sink-rooted reverse BFS** over the unsaturated residual: `non_reachable = set(dict(nx.shortest_path_length(R, target=_t)))`, then `partition = (set(G) - non_reachable, non_reachable)`. Saturated edges (`flow == capacity`) are removed first.

The max-flow **value** is an algorithm invariant (equal for any correct max-flow algorithm). The **partition is not** — it is determined by the residual structure after a particular flow assignment, and different augmenting-path orders can produce different min-cut partitions on graphs with multiple min cuts. **The partition is the parity risk**, not the value.

### 1.3 Graph sizes on the production board

- The Temper PCB (`pcb/temper.kicad_pcb`) is a 152 mm × 234 mm board; the placer grid is **1 mm** (`PLACER_CELL_SIZE_UM = 1000`, `deterministic/__init__.py:62`) → up to **35,568 cells/layer**, up to ~142k cells across 4 layers.
- The per-net capacitated graph is a BFS closure from the failing net's pads, so a real per-net graph is the connected free region around the net — far smaller than the full grid in general, with the full-grid size as the worst case.
- Edge count ≈ 2 × (in-grid 4-neighbour pairs) ≈ up to ~2·(4·cells − border) ≈ **~280k directed edges** at full size.
- The module's per-net wall-clock budget is `BOTTLENECK_TIMEOUT_S = 0.5s`; the graph build enforces it stride-checked, and the min-cut is a polynomial kernel on integer capacities (≤ 4 per edge).

### 1.4 Downstream consumers and their tolerance

The `BottleneckGeometry` payload is consumed by:

- **`NetRoutingReport.to_dict()` → closure test JSON** — via `routing_results.py` / `closure_test.py`, which surface `bottleneck.message` into `routing_failure_messages` and render the "Routing failures" section (SC1/SC2). The message is **formatted text** ("Q1 at (22.2, 15.0) and D1 at (30.5, 25.0) create 4mm gap that needs 6mm").
- **`cut_size`** — an integer capacity count (min-cut value). Tests assert exact int equality (`== 1`).
- **`cut_cells`, `component_pair`, `pair_kind`, `positions_mm`** — all derived from the **partition** (which side each pad is on, which cells straddle the cut).

**Tolerance: exact.** The consumers compare `cut_size` as an integer and derive geometry from the exact partition membership. There is no bit-exact float comparison of *flow values* downstream — but there *is* an exact integer value and an exact partition. A partition change would change `component_pair`/`pair_kind`/`positions_mm` and therefore the human message. So the meaningful parity contract is: **same cut value (integer) AND same reachable/non-reachable partition**. Both are what this spike measured.

## 2. Determinism

- **networkx** is deterministic for a fixed graph, fixed edge insertion order, and fixed `flow_func` — confirmed in the measurements (repeated runs of `nx.minimum_cut` on identical graphs gave identical (value, partition)).
- **The Rust kernel** is deterministic: pure integer arithmetic, adjacency built in edge-insertion order, BFS in fixed order; re-running the kernel on the same inputs returns the identical (value, partition). Pinned by `test_min_cut_kernel_deterministic_across_runs` (this spike) and the Rust unit test `test_min_cut_deterministic_across_runs`.

## 3. Can petgraph reproduce the results? — No (and this is the documented-KEEP)

Inspect the current petgraph (0.7.1, the version in the local cargo registry; **not** a repo dependency today — `Cargo.lock` has no petgraph):

1. **petgraph 0.7.x has no `edmonds_karp` at all.** The flow primitive is `algo::ford_fulkerson(network, source, destination) -> (max_flow, Vec<edge_flows>)` (`src/algo/ford_fulkerson.rs`). It returns the max-flow value and per-edge flows — **no min-cut partition**. (The old `petgraph::algo::edmonds_karp` API was removed before 0.7.)
2. Its augmenting-path search (`has_augmented_path`, `ford_fulkerson.rs:60`) BFSes each vertex's **`edges_directed(Outgoing).chain(edges_directed(Incoming))`** — a per-vertex out-then-in sweep, not networkx's residual-insertion-order adjacency. Even the *traversal order* differs from networkx's bidirectional BFS, so the flow assignment — and hence the partition — is not expected to match.
3. Reproducing networkx's partition would require rebuilding the residual from petgraph's `edge_flows` and running the sink-rooted reverse BFS over unsaturated edges. That is exactly the code `temper-geometry`'s `min_cut_edmonds_karp` already contains. Adding petgraph would contribute the flow value (which the hand-rolled kernel already computes in the same pass) and nothing else — a dependency with zero marginal value and a *different* algorithm signature to defend.

**The consumer needs the partition, petgraph cannot supply it, and the hand-rolled kernel already supplies it bit-exactly.** That is the decision-ready case for KEEP over petgraph.

## 4. Where the Rust home is

`temper-geometry` (the natural crate — it already owns `build_capacitated_graph_py` and the capacity/hard-blocked kernels for the same module). The min-cut kernel lives in `packages/temper-geometry/src/bottleneck_geometry.rs`:
`min_cut_edmonds_karp` (the algorithm) + `min_cut_py` (the PyO3 bridge, exported at `lib.rs:106` / `bridge.rs:1542`). The Python module is already the thin orchestration shim the wave-4 discipline prescribes: `_build_capacitated_graph_rust` + `_tg.min_cut_py`, with pad resolution / creepage / partition classification staying Python.

## 5. The parity measurement (spike evidence)

Differential driver: build the capacitated graph with the **Rust** kernel (`_build_capacitated_graph_rust`), replay the emitted `(nodes, edges)` into an `nx.DiGraph` in the exact same insertion order (the pre-migration wrapper's contract), then run **both** min-cuts on that one graph:

- Rust: `temper_geometry.min_cut_py` (the shipped path)
- networkx: `nx.minimum_cut(g, src, sink, capacity="capacity", flow_func=nx.algorithms.flow.edmonds_karp)` (the pre-migration reference)

Compare cut value and both partition sets.

| sample | shape | comparisons | value mismatches | partition mismatches |
|---|---:|---:|---:|---:|
| randomized grids (3×3 … 152×234, 1–4 layers, dense + sparse occupancy) + random directed graphs | grid + directed | 395 | 0 | 0 |
| adversarial tie-rich (uniform free grids 5×5…40×40, 1-wide corridors, symmetric waist, obstacle walls) | grid graphs | 42 | 0 | 0 |
| full `analyze_bottleneck` payload (cut_size, cut_cells, component_pair, pair_kind, gap) vs a networkx-reference reimplementation | synthetic boards | 20 | 0 | 0 |
| large-scale randomized grids (seed 424242, sizes ≤ 40×40 across 1–4 layers) | grid graphs | 2000 | 0 | 0 |
| permanent CI differential (randomized + tie-rich + production-scale) | grid graphs | 150+ per run | 0 | 0 |

**Total: 2457+ graph comparisons, 0 value mismatches, 0 partition mismatches, 0 nondeterministic runs.** All capacities are integers and both implementations are integer-only; "match" is bit-for-bit equality of the cut value and of both partition sets.

### 5.1 One honest caveat: parity is empirical, not provable-in-general

The max-flow **value** is guaranteed equal (algorithm invariant). The **partition** is flow-assignment-dependent, and there exist graphs (not in the production family) on which a forward-BFS Edmonds-Karp and networkx's bidirectional-BFS Edmonds-Karp could assign different flows and yield different sink-side reachability. The production graph family — 4-neighbour grid graphs, integer capacities in [0,4], symmetric directed pairs, ≤ ~35,568 nodes/layer — shows **0 divergences across 2457+ comparisons**. The differential test pins the kernel against the networkx oracle on that family forever; if a future corpus changes the graph family (non-grid topologies, parallel edges), the pinned suite is the tripwire. This is the documented-tolerance contract: bit-exact on the production family, with the networkx oracle as the arbitration boundary.

### 5.2 Two recorded behavioral deltas (both intentional, neither a parity failure)

1. **`s == t`** (two pads of the same net resolving to the same cell, or an empty/same-cell degenerate graph): the Rust kernel returns cut=0 with reachable={src}; networkx *raises* `NetworkXError("source and sink are the same node")`, which the pre-migration `analyze_bottleneck` caught and surfaced as `aborted_build_failure`. The Rust behavior (an `"ok"` payload with cut 0) is strictly more graceful and is the shipped contract.
2. **Aborted-graph paths** (`aborted_no_sink` / `aborted_timeout` / `aborted_build_failure`): unchanged semantics; the module never calls a flow function on those paths, so there is no parity surface.

## 6. What landed

- **`packages/temper-placer/tests/router_v6/test_bottleneck_geometry_rust_differential.py`** — added the min-cut differential section: `test_min_cut_value_and_partition_match_networkx_randomized`, `test_min_cut_tierich_uniform_grids_match_networkx`, `test_min_cut_production_scale_grids_match_networkx`, `test_min_cut_kernel_deterministic_across_runs`. This closes the pre-existing gap where the Wave-4 kernel's *partition* was never differentially pinned (the commit that migrated it verified one 1×3 synthetic case; the graph build was pinned, the cut was not).
- **`packages/temper-geometry/VERIFICATION.md`** — replaced the stale "Recorded remainder (not faked)" paragraph (which still claimed `nx.minimum_cut` runs in Python) with the completed-migration record + this spike's parity evidence.
- **This evidence note.**
- No production code changed: `bottleneck_geometry.py` and the Rust kernel were already the migrated shape at spike base.

## 7. Verification

- `cargo test -p temper-geometry`: 6,373 tests pass (incl. the 8 min-cut kernel unit tests).
- `cargo clippy --all-features --all-targets` (temper-geometry): clean.
- `pytest tests/router_v6/test_bottleneck_geometry*.py` (differential incl. new min-cut pins, PBT, metamorphic, integration): 64 pass.
- `pytest tests/router_v6/` full bottleneck suite: green.
- `import_linter_gate.py`: 0 violations (no import boundary touched).
- `make regen-check`: the only report is a **pre-existing** hash-order defect in `physics/loop_area.py:108` (present on origin/main at spike base, untouched by this spike — outside its file ownership); every generated artifact this spike could drift (oracle hashes, unwired-kernel inventory, wasm registry) is up to date. No `_*_py_oracle.py` file was added — the differential's networkx oracle is inline, so `scripts/oracle_hashes.json` is unaffected.
- `.unwired-kernel-inventory`: `min_cut_py` is wired (production caller in `bottleneck_geometry.py`); no entry change.

## 8. Verdict

**KEEP — with the migration already landed.** The plan's conditional gate ("petgraph/geometry parity pass") is satisfied by the shipped hand-rolled Edmonds-Karp in `temper-geometry`, measured bit-exact against `networkx.minimum_cut(flow_func=edmonds_karp)` on the production graph family (value and partition, 0/2457+ divergences), and now permanently pinned by the differential suite. petgraph is documented-KEEP: it cannot produce networkx's partition (no partition API in 0.7.x; different traversal; only `ford_fulkerson` returning value + edge flows), and reproducing the partition on top of it would duplicate the existing kernel. The plan's "JUSTIFIED-KEEP candidate under R3" record is upgraded to a settled KEEP on measured evidence.

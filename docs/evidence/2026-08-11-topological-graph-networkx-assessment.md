<!-- provenance: commit=753da757781f227019c4ef95a4508ed320de7051 dirty=false -->
<!-- measured_at_commit: 753da7577 (branch: fanout13/work-3, off origin/main at 753da7577) -->

# Spike S7: `topological/graph.py` `nx.MultiDiGraph` container — PORT / KEEP / DELETE assessment

**Date:** 2026-08-11
**Surface:** `packages/temper-placer/src/temper_placer/topological/graph.py` (332 LOC)
Line 19: `import networkx as nx`
Line 94: `self.graph = nx.MultiDiGraph()` — the `TopologicalGraph` class's container
**Scope:** a verdict plus its measurements. **No production code was changed, no Rust was written, and no Rust crate was built.**

**Context:** This is the last remaining `networkx` surface after S3–S6. Unlike the algorithmic surfaces assessed in prior spikes (`shortest_path`, `connected_components`, `cycle_basis`, `community_louvain`, `spectral_layout`), this surface is a **container** — nodes with `str` keys, edges with `Py<PyDict>` data dicts, insertion-ordered iteration. The question is whether it can port cleanly or whether some networkx-specific behavior is load-bearing.

---

## Verdict

**PORT with parity — the `nx.MultiDiGraph` container ports cleanly to a Rust `TopologicalGraphStore` pyclass.** The live production code paths use only insertion-ordered container semantics (add node, add edge, iterate edges, iterate nodes, has_edge check). No algorithmic networkx surface is reached in production. The networkx dependency in `topological/graph.py` can be replaced by a `Vec<(String, String, Py<PyDict>)>` plus a `Vec<String>` with a `HashSet` for dedup.

Key findings, each load-bearing:

1. **F-T1 DID NOT FIRE — the surface IS live.** `TopologicalInitializationHeuristic` is registered by default in `heuristics.__init__.create_default_pipeline()`. It constructs a `TopologicalGraph()` at `topological_init.py:222` and passes it through `generate_initial_placement()` → `identify_clusters()` → `place_cluster()` → `apply_force_refinement()`. The graph IS part of the production placement pipeline. (§2)

2. **F-T2 DID NOT FIRE — no parallel edges exist.** `add_adjacency` creates (a,b)+(b,a) as separate directed edge pairs. `add_separation` creates a single directed edge. `add_group` creates unique member→group edges. `_build_graph` guards with `.has_edge` before adding adjacency. Zero code paths produce two edges with the same (source, target). `MultiDiGraph` → `DiGraph` is a safe simplification; the "Multi" prefix is dead weight. (§3)

3. **F-T3a FIRED (narrowly) — force refinement output varies ~5μm across edge-order permutations (58/64 seeds).** The Rust `force_refine` kernel uses naive `f64 +=` accumulation, which is commutative but not strictly associative. Different adjacency-list orders produce 13 distinct position sets across 64 permutation seeds, with a maximum position difference of ~0.005 mm. This is **negligible for PCB placement** and is inherent to f64 arithmetic, not to networkx. A Rust port that preserves insertion order (Vec-based) would produce identical results as the Python build. (§4)

4. **F-T3b, F-T3c DID NOT FIRE — clusters, min-distance, and propagation are all order-insensitive.** `identify_clusters` uses union-find (commutative), `place_cluster` uses min-reduction (commutative), `propagation` uses min/max bound tightenings (commutative). Edge insertion order does not affect any output verified across 64 permutation seeds. (§5)

5. **All algorithmic networkx surfaces are dead code in production.** `get_neighbors` (0 production callers), `find_separation_conflicts` (0), `get_adjacency_cluster` (0), `ConstraintPropagator` (0), `from_pcl` (0), `build_topological_graph` (0). The only live contact with the graph is through container operations: `add_node`, `add_edge`, `edges(data=True)`, `nodes()`, `has_edge`. (§6)

**The port is a pure data-structure replacement** — no algorithmic parity with networkx's BFS/DFS tie-breaking is needed because no algorithmic surface is reached. The only behavioral requirement is **insertion-order-preserving** iteration of edges and nodes, which a `Vec`-based container provides naturally.

---

## Falsifiers, stated before measuring

Per S3/S4/S5/S6 convention, falsifiers were written down before measurement.

**F-T1 (reachability) — "`TopologicalGraph` from `topological/graph.py` is reachable from the production pipeline."**

> **F-T1 DID NOT FIRE.** 8 production import sites; constructed in `heuristics/topological_init.py:222`. Registered in `heuristics.__init__.create_default_pipeline()` with `include_topological=True` (default). The graph IS live. (§2)

**F-T2 (parallel-edge usage) — "Two edges between the same ordered (u, v) are ever created."**

> **F-T2 DID NOT FIRE.** 0 parallel edges possible through any code path. The Multi- prefix is unused. (§3)

**F-T3a (force-refinement order observability) — "Permuting edge insertion order changes force refinement output positions."**

> **F-T3a FIRED (narrowly).** 58/64 seeds produce different positions (max diff ~0.005 mm, 13 distinct position sets). The mechanism is f64 accumulation non-associativity in the Rust `force_refine` kernel (confirmed against a pure-Python mirror). The differences are ~5μm — negligible for PCB placement — and are inherent to f64 arithmetic, not to networkx. (§4)

**F-T3b (cluster order observability) — "Permuting edge insertion order changes `identify_clusters` output."**

> **F-T3b DID NOT FIRE.** 0/64 seeds produce different cluster partitions. Union-find is commutative. (§5)

**F-T3c (propagation order observability) — "Permuting edge insertion order changes `propagate` output."**

> **F-T3c DID NOT FIRE.** 0/64 seeds produce different feasibility results. min/max reductions are commutative. (§5)

**F-T4 (port cost) — "The surface requires algorithmic parity (reproducing networkx's internal tie-breaking)."**

> **F-T4 DID NOT FIRE.** No algorithmic networkx surface is reached in production. Only container operations are used. The port is a pure data-structure replacement. (§6, §8)

---

## 0. Environment and provenance

The measurements ran against the main checkout's `.venv` Python 3.12. The worktree's Python 3.9 cannot import `temper_placer` (missing `TypeAlias` from `typing`). All static measurement scripts (M1, M2, M4, M5) run on any Python 3.9+. M3 (force refinement) uses `networkx` and `numpy` only and runs on any Python.

The file under measurement is **byte-identical** across both trees (main checkout at `/home/bennet/Desktop/temper` and this worktree at `/tmp/opencode/wt-f13-3`, both at `753da7577`):

| File | sha256 |
|---|---|
| `topological/graph.py` | `f022ad4c18fdbfa26b276528cb3e00b1952e7ee4e2dcd0cb79e352ee617a8d37` |

**networkx 3.6.1, numpy 1.24.4, Python 3.12.3.**

At measurement time the working tree contained only untracked measurement scripts added by this PR; every file under measurement was unmodified at `753da7577`.

---

## 1. What the surface actually is

`topological/graph.py` defines `TopologicalGraph`, a graph container for component relationship reasoning. The internal container is `nx.MultiDiGraph()` — a directed multigraph with insertion-ordered node/edge dictionaries.

**Live production call chain:**
```
heuristics/__init__.py:create_default_pipeline()         [exported API]
  └─ heuristics/topological_init.py:apply()              [INITIALIZATION priority]
       └─ _build_graph() → TopologicalGraph()             [line 222]
            ├─ add_component() per component
            ├─ has_edge() guard + add_adjacency() per net
            └─ → generate_initial_placement()             [initial_placement.py:183]
                 ├─ identify_clusters(graph, ...)          → _rust.identify_clusters()
                 ├─ place_cluster(cluster, zone, graph, ...) → _rust.place_cluster()
                 └─ apply_force_refinement(positions, graph, ...) → _rust.force_refine()
```

**Dead algorithmic surfaces** (0 production callers, test-only or oracle-only):
- `get_neighbors(node)` — BFS adjacency iteration
- `find_separation_conflicts()` — conflict detection via edge comparison
- `get_adjacency_cluster(seed)` — BFS cluster discovery
- `ConstraintPropagator` (in `propagation.py`) — Floyd-Warshall propagation (0 constructor calls in production)
- `from_pcl(pcl)` — PCL constraint parsing to graph (0 production callers)
- `build_topological_graph(pcl)` — convenience wrapper (0 production callers)

---

## 2. M1 — reachability (F-T1)

`tools/measurements/topological_graph_assessment/m1_reachability.py`:

| Metric | Value |
|---|---|
| `TopologicalGraph` import sites (production) | 8 |
| `TopologicalGraph` constructors (production) | 2 (`topological_init.py:222`, `graph.py:270`) |
| Pipeline registered | **true** |
| Pipeline called | **true** (`TopologicalInitializationHeuristic(...)` in `create_default_pipeline`) |
| `ConstraintPropagator` production callers | 0 (imports from `__init__.py` are re-exports only) |
| `get_neighbors` production callers | 0 |
| `find_separation_conflicts` production callers | 0 |
| `get_adjacency_cluster` production callers | 0 |
| **F-T1 verdict** | **LIVE** |

The `TopologicalInitializationHeuristic` is registered by default in `create_default_pipeline()` (`include_topological=True`). It runs at `INITIALIZATION` priority (before other heuristics). The graph is constructed from netlist connectivity and passed to placement generation.

Note: `core/topology.py` defines a **separate** `TopologicalGraph` — a plain dataclass with no networkx dependency. The two classes share a name but are different types. The `core/__init__.py` re-exports the `core/topology.py` version. The `heuristics/topological_init.py` imports the `topological/graph.py` (networkx) version explicitly: `from temper_placer.topological.graph import TopologicalGraph`.

---

## 3. M2 — parallel-edge census (F-T2)

`tools/measurements/topological_graph_assessment/m2_parallel_edge_census.py`:

| Check | Result |
|---|---|
| `add_edge` call sites in production | 4 in `graph.py` (add_adjacency ×2, add_separation, add_group) |
| `has_edge` guard before add_adjacency | yes (`topological_init.py:246`) |
| Forward+reverse edges (add_adjacency) | different (u,v) pairs |
| Dynamic duplicate (u,v) check | **0 duplicates** |
| **F-T2 verdict** | **NO_PARALLEL_EDGES** |

The `MultiDiGraph` container supports parallel edges, but no code path creates them. The "Multi" prefix is dead weight. A `DiGraph` (or simpler Vec-based container) is sufficient.

The only directed edge pairs with the same endpoints but opposite direction are the add_adjacency forward+reverse edges (a→b and b→a). These are different directed pairs by construction and are not "parallel" in the graph-theoretic sense.

---

## 4. M3 — force refinement order observability (F-T3a)

`tools/measurements/topological_graph_assessment/m3_force_refine_order.py`:

A 12-component graph with 16 adjacency pairs and 3 separation pairs. Built with 64 permuted edge insertion orders (identical edge sets, different insertion sequences). Force refinement run for 100 iterations with a pure-Python mirror of the Rust kernel (naive `f64 +=` accumulation, matching the `force.rs` module docstring).

| Metric | Value |
|---|---|
| Components | 12 |
| Adjacency pairs | 16 |
| Separation pairs | 3 |
| Iterations | 100 |
| Permutation seeds | 64 |
| **Seeds divergent** | **58** |
| Distinct position sets | 13 |
| **Max position difference** | **0.00504 mm (~5 μm)** |
| **F-T3a verdict** | **FIRED (negligible magnitude)** |

The mechanism: f64 addition is not strictly associative. The order of force accumulation (`forces[i] += f` in the inner loop of `force_refine`) depends on the order of adjacency/separations in the list, which depends on `graph.edges(data=True)` iteration order. Different edge insertion orders produce different accumulation sequences, yielding slightly different final positions.

The difference is ~5μm — two orders of magnitude below typical PCB manufacturing tolerances (0.1 mm). It is inherent to floating-point arithmetic, not to networkx. Any container that preserves insertion order (whether networkx or a Rust Vec) would produce the same result — the sensitivity is to the build order of the graph, not to the container itself.

**Additional finding**: `identify_clusters` adjacency-pair order differs per graph (the `adjacent` list has different element order), but the **edge set** is identical — so union-find produces the same partition. The order of pairs within the list affects only the internal processing sequence of union operations, which are commutative.

---

## 5. M4 — cluster and propagation order (F-T3b, F-T3c)

`tools/measurements/topological_graph_assessment/m4_cluster_order.py`:

8-component graph with 6 adjacency pairs and 2 separation pairs. Pure-Python mirrors of `identify_clusters` (union-find), `place_cluster` min-distance, and `propagate` (Floyd-Warshall). 64 permutation seeds.

| Experiment | Seeds | Divergent | Verdict |
|---|---|---|---|
| `identify_clusters` | 64 | **0** | **ORDER-INSENSITIVE** |
| `place_cluster` min_adjacency_dist | 64 | **0** | **ORDER-INSENSITIVE** |
| `propagate` feasibility | 64 | **0** | **ORDER-INSENSITIVE** |
| **F-T3b, F-T3c verdict** | — | — | **DID NOT FIRE** |

Union-find is commutative: the partition depends on which nodes share an adjacency edge, not on the order edges are processed. Min-reduction and min/max bound tightenings are similarly commutative operations.

---

## 6. M5 — port surface census (F-T4)

`tools/measurements/topological_graph_assessment/m5_port_surface_census.py`:

Networkx API methods used on the `TopologicalGraph.graph` (MultiDiGraph) in production code:

| Method | Production sites | Live? | Notes |
|---|---|---|---|
| `.graph.add_node(ref, **attrs)` | 2 | **Yes** | Component/group node creation |
| `.graph.add_edge(u, v, **attrs)` | 4 | **Yes** | Adjacency, separation, membership edges |
| `.graph.edges(data=True)` | 10 | **Yes** | Iteration in force_refinement, initial_placement, propagation |
| `.graph.nodes()` | 7 | **Yes** | Node list in propagation, channel_mapping, channel_widths |
| `.graph.has_edge(u, v)` | 1 | **Yes** | Dedup guard in topological_init._build_graph |
| `.graph.number_of_nodes()` | 2 | **Yes** | Count check (channel_skeleton) |
| `.graph.number_of_edges()` | 1 | **Yes** | Count check (channel_skeleton) |

Note: Some of the `.graph.edges` / `.graph.nodes` sites belong to OTHER networkx graph objects (channel_skeleton uses `nx.Graph`, not `nx.MultiDiGraph`). The census catches all `*.graph.XXX` patterns; the `TopologicalGraph.graph`-specific sites are the 4 in `graph.py` + 1 in `topological_init.py` + the `topological/` consumers.

**Dead surfaces (0 production callers):**
- `get_neighbors(node, edge_type)` — only tests + oracle
- `find_separation_conflicts()` — only tests + oracle
- `get_adjacency_cluster(seed)` — only tests + oracle
- `ConstraintPropagator.propagate()` — only tests + oracle (imported but never constructed)
- `from_pcl(pcl)` — only tests + oracle
- `build_topological_graph(pcl)` — only tests + oracle

---

## 7. What a Rust port needs (migration spec)

The port replaces `self.graph = nx.MultiDiGraph()` with a Rust pyclass `TopologicalGraphStore` that holds:

```rust
// Conceptual — not actual code (no Rust written, per spike constraints)
#[pyclass]
struct TopologicalGraphStore {
    nodes: Vec<String>,                          // insertion-ordered
    node_set: HashSet<String>,                   // dedup
    edges: Vec<(String, String, Py<PyDict>)>,    // insertion-ordered
    edge_set: HashSet<(String, String)>,         // dedup
}
```

**Methods to expose (minimal):**

| Python API | Rust equivalent |
|---|---|
| `g.add_node(ref, node_type=..., properties=...)` | Push to `nodes` if not in `node_set` |
| `g.add_edge(u, v, edge_type=..., distance=..., ...)` | Push to `edges` + `edge_set` |
| `g.edges(data=True)` → iterator of `(u, v, data_dict)` | Iterate `edges` Vec in insertion order |
| `g.nodes()` → iterator of node IDs | Iterate `nodes` Vec in insertion order |
| `g.has_edge(u, v)` → bool | `edge_set.contains(&(u, v))` |
| `g.number_of_nodes()` → int | `nodes.len()` |
| `g.number_of_edges()` → int | `edges.len()` |

**Ordering rule:** Insertion order, preserved through `Vec` push. The current Python code adds nodes and edges in deterministic order (sorted component refs, sorted net refs within nets). A Rust port that preserves this insertion order produces identical edge-iteration order, identical force-refinement lists, and identical floating-point accumulation sequences.

**Differential test plan:**
1. Pin the current Python oracle (`tests/topological/_graph_py_oracle.py`) — already done (R1a).
2. Replace `self.graph = nx.MultiDiGraph()` with `self.graph = TopologicalGraphStore()`.
3. Add differential test that builds an identical graph on both backends, runs `generate_initial_placement`, and compares positions within a tolerance (e.g., 0.001 mm — the force-refinement f64 noise is ~0.005 mm, but building identically yields identical results).
4. Verify that `add_node` / `add_edge` / `has_edge` / iteration all match.

**What NOT to port:**
- `get_neighbors(node)`, `find_separation_conflicts()`, `get_adjacency_cluster(seed)` — dead code in production, port only for the oracle.
- `ConstraintPropagator`, `from_pcl`, `build_topological_graph` — dead code.
- The `_edge_tuples` helper — only used by dead methods.

---

## 8. Classification against the strategy's REQUIRED-PYTHON category

Per `docs/evidence/2026-08-09-python-over-rust-interrogation.md` §2:

| Surface | Class | Rationale |
|---|---|---|
| `topological/graph.py` | **Not REQUIRED-PYTHON** | Pure container — no ortools, pydantic, click/rich, ngspice/kicad-cli subprocess, or recorded keep. The container semantics (insertion-ordered Vec of nodes/edges) port trivially to Rust. |

---

## 9. Recommendations

1. **PORT the `MultiDiGraph` container to a Rust `TopologicalGraphStore` pyclass.** Replace `self.graph = nx.MultiDiGraph()` at line 94 with `self.graph = TopologicalGraphStore()`. The live code paths use only container methods — no algorithmic parity with networkx is needed.

2. **Use insertion-ordered Vec semantics.** The Rust store uses `Vec<String>` for nodes and `Vec<(String, String, Py<PyDict>)>` for edges. Iteration order is insertion order, matching networkx's documented dict-insertion-order behavior.

3. **Do NOT port dead algorithmic methods.** `get_neighbors`, `find_separation_conflicts`, `get_adjacency_cluster`, `ConstraintPropagator`, `from_pcl`, `build_topological_graph` have 0 production callers. Port them only for the differential oracle; the production code will never call them.

4. **The f64 accumulation sensitivity (~5μm) is not a barrier.** The force-refinement output depends on edge iteration order through f64 non-associativity, but this is a property of the algorithm (any force-directed system with naive accumulation), not of networkx. A Rust port that preserves insertion order produces identical results.

5. **Simplify MultiDiGraph → DiGraph semantics.** The "Multi" prefix is unused — no parallel edges exist. The Rust store does not need multi-edge support.

6. **Remove `import networkx as nx` from `topological/graph.py`.** After porting, this is the module's only networkx import. The remaining `networkx` surfaces in the repository (per S4) are `channel_skeleton.py:12` (`import networkx as nx` for `nx.Graph`, `nx.is_connected`, `nx.connected_components`). The S4 port plan covers those; after both S4 and S7 ports, the repository has zero `networkx` dependencies.

7. **Total networkx surface after this port:** The only remaining `networkx` surface in the repository is `channel_skeleton.py`'s `nx.Graph`, `nx.is_connected`, `nx.connected_components` — all covered by the S4 migration plan (`docs/evidence/2026-08-11-channel-skeleton-connectivity-order-spike.md`). After both ports, the repository has **zero** `networkx` dependencies.

---

## 10. What I could not verify

- **The production board route.** The Rust extension `temper_geometry` was not built for this worktree. The measurements used standalone `networkx` + `numpy` scripts. The force-refinement order experiment used a pure-Python mirror of the Rust kernel (matching the `force.rs` docstring's documented accumulation strategy). The synthetic graph (12 components, 16 adjacencies, 3 separations) is representative but not the production board's actual topology.

- **Edge iteration order equivalence between networkx and Rust Vec.** Both are insertion-ordered. networkx (3.6.1) uses dict-insertion-order for nodes and edges, matching Rust Vec push semantics. This was not empirically verified across networkx versions but is a documented, stable API.

- **Full end-to-end differential test.** The existing differential test (`test_topological_rust_differential.py`) tests the dead algorithmic surfaces (`get_neighbors`, `find_separation_conflicts`, `ConstraintPropagator`). A new differential test for the live container surface (force refinement positions) should be added as part of the port but was out of scope for this spike.

- **The `topological.__init__.py` re-export surface.** `topological/__init__.py` re-exports `TopologicalGraph` from `topological.graph`. After porting, this export path remains valid — the class name doesn't change, only the internal container implementation. No downstream importers need updating.

---

## 11. Reproducing

Scripts live in `tools/measurements/topological_graph_assessment/`. M1, M2, M5 need the repository root (AST parsing); M3, M4 need only `networkx` + `numpy` and run on any Python.

```bash
# Use the main checkout's venv (Python 3.12 + networkx)
PYTHON=/home/bennet/Desktop/temper/.venv/bin/python3

# M1 — reachability census
$PYTHON tools/measurements/topological_graph_assessment/m1_reachability.py \
    --repo . --out tools/measurements/topological_graph_assessment/m1.json

# M2 — parallel-edge census
$PYTHON tools/measurements/topological_graph_assessment/m2_parallel_edge_census.py \
    --repo . --out tools/measurements/topological_graph_assessment/m2.json

# M3 — force refinement order observability
$PYTHON tools/measurements/topological_graph_assessment/m3_force_refine_order.py \
    --out tools/measurements/topological_graph_assessment/m3.json --seeds 64

# M4 — cluster and propagation order
$PYTHON tools/measurements/topological_graph_assessment/m4_cluster_order.py \
    --out tools/measurements/topological_graph_assessment/m4.json --seeds 64

# M5 — port surface census
$PYTHON tools/measurements/topological_graph_assessment/m5_port_surface_census.py \
    --repo . --out tools/measurements/topological_graph_assessment/m5.json
```

**Requirements:** `networkx` for M3/M4. M1/M2/M5 use only stdlib `ast` and `pathlib`.

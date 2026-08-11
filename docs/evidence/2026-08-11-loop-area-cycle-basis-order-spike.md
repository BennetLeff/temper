<!-- provenance: commit=d1b330b90 dirty=false -->
<!-- measured_at_commit: d1b330b90 (merge: migrate/phase-e3-clearance) -->

# Spike S5: Is `nx.cycle_basis` observable in `physics/loop_area.py`?

**Date:** 2026-08-10
**Surface:** `packages/temper-placer/src/temper_placer/physics/loop_area.py`
(248 LOC). Line 164: `list(_nx.cycle_basis(graph))` — the `networkx`
dependency in the commutation-loop area computation.
**Scope:** a verdict plus its measurements. **No production code was changed,
no Rust was written, and no Rust crate was built.**

**Context:** This is the gate for whether the `cycle_basis` networkx surface
can be cleanly removed or needs petgraph parity (reproducing networkx's
internal spanning-tree tie-breaking). Unlike S4 (which proved
`connected_components` order-insensitive), S5's primitive —
`nx.cycle_basis` returns a *fundamental* cycle basis whose content depends
on the internal spanning-tree construction — is a fundamentally different
class: the "longest cycle in the basis" heuristic amplifies insertion-order
instability into different area values.

---

## Verdict

**ORDER-OBSERVABLE, but UNREACHABLE — the `cycle_basis` path is dead code
on the production board. The recommendation is DELETE, not port.**

The verdict has three layers, and each matters independently:

1. **F1 FIRED — `cycle_basis` is strongly order-observable.** On all five
   synthetic graph types, permuting edge/node insertion order changes the
   cycle basis content, which cycle is "longest in the basis", and the
   computed shoelace area. The area spreads up to **4×** (100 → 400 mm² on
   a 3×3 grid graph, §4). 62–64/64 permutation seeds diverge on grids.
   Additionally, `max(nx.connected_components(G), key=len)` at line 114 is
   order-observable when components have tied sizes (§4.1).

2. **F2 DID NOT FIRE — the path is unreachable on the production board.**
   `auto_extract_loops` finds **zero loops** of any type on
   `pcb/temper.kicad_pcb` (§2). The Rust loop extractor fails ("No bus
   capacitor path"), the Python fallback also returns empty, and
   `commutation_loop_area` returns `None` at line 78 before the
   `cycle_basis` branch is reached. The board has 2,290 routed traces across
   110 nets, but the loop extractor's heuristic does not match the actual
   net/component naming.

3. **F3 WOULD BE OBSERVABLE if reached.** `commutation_loop_area` feeds
   into `PhysicsGate.check()` (`gates.py:756`), which compares the area
   against a 2,000 mm² threshold and produces a `LOOP_INDUCTANCE` violation
   if exceeded (§5). Violations feed constraint deltas that can alter
   routing decisions. The test suite does not exercise this path (only
   `UNMEASURED` cases with no PCB, §3).

**Recommendation: DELETE the `cycle_basis` path without porting it.** This
is the S3 pattern: the code is dead, the primitive is order-unstable, and
reproducing it would require matching networkx's internal spanning-tree
tie-breaking — a moving target across versions. If commutation-loop area
computation is needed in the future, reimplement with a proper algorithm
(not `cycle_basis` + longest-in-basis heuristic), potentially using the
specific loop geometry rather than a graph-theoretic cycle proxy.

---

## Falsifiers, stated before measuring

Per S3/S4 convention, falsifiers were written down before measurement:

**F1 — order-observable.** *Permuting node/edge insertion order (same node
set, edge set, weights) changes the OUTPUT of the loop-area computation
(which cycle is "longest", its vertex order, the computed area).*

> **F1 FIRED.** All 5 synthetic graph types show order-dependency. Grid
> 5×5: 64/64 seeds divergent, 10 distinct area values, 52 distinct
> canonical cycles. Area spread up to 4× on grid 3×3 (§4).

**F2 — reachable.** *Is the `cycle_basis` path actually reached on the
production board? Which nets actually have cycles?*

> **F2 DID NOT FIRE.** `auto_extract_loops` finds 0 loops of any type on
> `pcb/temper.kicad_pcb`. `commutation_loop_area` returns `None` at
> line 78. The `cycle_basis` branch is never entered (§2).

**F3 — downstream observable.** *Does the loop area feed a consumer where a
different area value matters?*

> **F3 IS MOOT** on the production board (path not reached), but the
> architecture confirms it WOULD be observable: `PhysicsGate.check()`
> compares against 2,000 mm² threshold, violations produce corrective
> deltas (§5).

---

## 0. Environment and provenance

The measurements ran against the main checkout's `.venv` Python 3.12.
`temper_geometry` is importable and was used for the PCB parse.

The file under measurement is **byte-identical** across both trees
(the worktree at `/tmp/opencode/wt-f11-1` and the main checkout at
`/home/bennet/Desktop/temper`):

| File | sha256 |
|---|---|
| `physics/loop_area.py` | `987cb8ebc5fae43e6d5b47b97eab6da540e085c569b86f3f0dd5bb253b6462e5` |

All measurements are run from this worktree at `d1b330b90`.

**Board:** `pcb/temper.kicad_pcb`, 169 components, 110 nets, 2,290 trace
segments (routed).
**networkx 3.6.1, numpy 1.24.4, Python 3.12.3.**

At measurement time the working tree contained only untracked measurement
scripts added by this PR; every file under measurement was unmodified at
`d1b330b90`.

---

## 1. What `cycle_basis` actually feeds

`loop_area.py:149-172` (`_find_main_cycle`):

```python
def _find_main_cycle(graph: nx.Graph) -> list | None:
    import networkx as _nx
    cycles: list[list] = list(_nx.cycle_basis(graph))   # line 164
    if not cycles:
        return None
    longest_cycle: list = max(cycles, key=len)           # line 168
    if len(longest_cycle) < 3:
        return None
    return _order_cycle_vertices(graph, longest_cycle)   # line 172
```

The call chain:
1. `commutation_loop_area(pcb)` (line 48) → parses PCB, extracts loops
2. `_compute_area_from_traces(loop_traces)` (line 86) → builds graph
3. Line 114: `largest_cc = max(nx.connected_components(G), key=len)` — picks
   the largest connected component of the trace graph
4. Line 117: `cycle = _find_main_cycle(subgraph)` → uses `cycle_basis`
5. If cycle found: shoelace area. If not: convex-hull fallback (line 123).

`nx.cycle_basis` returns a **fundamental cycle basis** — a set of cycles
that span the cycle space, constructed by:
1. Finding a spanning tree of the graph (DFS/BFS, order-dependent)
2. For each non-tree edge, forming the unique cycle: non-tree edge + tree path

The `max(cycles, key=len)` at line 168 picks the **longest cycle in the
basis** — NOT the longest simple cycle in the graph (which is NP-hard to
find exactly). This is a heuristic that depends on:
- Which spanning tree is constructed (order-dependent)
- Which non-tree edges are processed in which order (order-dependent)
- Which fundamental cycles happen to be long (graph-structure-dependent)

Both `_order_cycle_vertices` (line 175) and the shoelace formula (line 212)
are deterministic given a fixed cycle vertex set (§4.2 confirms
`_order_cycle_vertices` always produces the same area for the same vertices).

---

## 2. M1 — reachability on the production board

`tools/measurements/loop_area_cycle_basis/m1_reachability.py`:

| Metric | Value |
|---|---|
| PCB parse | OK |
| Nets | 110 |
| Trace segments | 2,290 |
| Commutation loops found | **0** |
| `cycle_basis_reachable` | **false** |
| Reason | `no commutation loops found` |

`auto_extract_loops(netlist)` returns a `LoopCollection` with **zero loops
of any type** (not just zero commutation loops). The Rust extraction fails
with:

> Rust loop extraction failed: No bus capacitor path between
> `power_in.q_relay_drv-g` and `gnd`. Intermediate nets checked: []

The Python fallback also returns empty. The board's actual net names
(e.g., `hb.gate_hs.driver-p2`, `hb.power_loop.q_high-g`, `sw`,
`discharge.k_dis1-nc`) use hierarchical prefixes that the loop extractor's
heuristic does not recognize.

Since `comm_loops` is empty, `commutation_loop_area` returns `None` at
line 78:

```python
comm_loops = loops.get_loops_by_type(LoopType.COMMUTATION)  # line 75
if not comm_loops:                                           # line 76
    return None                                              # line 77
```

The `cycle_basis` branch at line 164 is **never entered** on this board.

**Note on prior art:** The DRM safety-rule vacuity audit
(`docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md` §LoopAreaCheck)
independently documented that the loop-area constraint is structurally
vacuous in the current config because `critical_loops` entries use `pins:`
but the Rust-facing schema requires `nets:`, and no pins→nets bridge
exists. This spike confirms the same vacuity at the `loop_area.py` level:
the `auto_extract_loops` heuristic also fails to find loops.

---

## 3. M2 — test suite coverage

The `PhysicsGate` test suite (`test_physics_gate.py`) covers only the
`UNMEASURED` path:

| Test | What it exercises |
|---|---|
| `test_physics_unmeasured_no_path` | `routed_pcb_path=None` → `UNMEASURED` |
| `test_physics_unmeasured_missing_file` | nonexistent file → `UNMEASURED` |
| `test_physics_gate_contract_metadata` | stage, name, type |
| `test_physics_to_delta_*` | `to_delta()` for various violation types |

**No test exercises `PhysicsGate.check()` with a real routed PCB on loop
nets.** The `commutation_loop_area` test in `test_loop_area.py` only tests
`None` return on a nonexistent PCB.

The `_compute_area_from_traces` tests in `test_loop_area.py` use synthetic
`_FakeTrace` objects and DO exercise the `cycle_basis` path — but these
are unit tests of the internal function, not integration tests showing the
path is reachable from the gate.

---

## 4. M2 — permutation experiment (F1)

`tools/measurements/loop_area_cycle_basis/m2_permutation.py`:

Five synthetic trace-graph types, each rebuilt with 64 permuted edge/node
insertion orders. The graph is **identical** (same node set, edge set,
weights); only the order of `G.add_edge()` calls differs.

| Graph | Nodes/Edges | Seeds divergent | Distinct areas | Distinct cycles | Area spread |
|---|---|---|---|---|---|
| house | 5/7 | 46/64 | 2 | 3 | 25→50 mm² |
| multi_cycle | 5/7 | 39/64 | 2 | 2 | — |
| non_planar (K5) | 5/10 | **64/64** | 3 | 10 | 25→75 mm² |
| grid_4×4 | 16/24 | 62/64 | 5 | 15 | — |
| grid_5×5 | 25/40 | **64/64** | 10 | 52 | — |

**F1 fires decisively.** The `cycle_basis` output depends on graph
construction order, and the "longest in basis" heuristic amplifies this
into different area values. The grid graphs (which most resemble PCB trace
layouts) show near-universal divergence: 62–64/64 seeds produce a different
output from the baseline.

### 4.1 Connected-components tie-breaking (line 114)

Line 114 uses `max(nx.connected_components(G), key=len)` — Python's `max()`
returns the first maximum when multiple components have the same size.
`nx.connected_components` enumeration order depends on insertion order.

A test with two identical-size disconnected triangles shows 29/64
permutation seeds pick a *different* component as "largest":

```
Connected-components tiebreak fires: 29/64 seeds picked different component
```

This is a secondary order-dependency that would compound with `cycle_basis`
if the trace graph had multiple equally-large connected components.

### 4.2 `_order_cycle_vertices` is deterministic

Given the same set of cycle vertices (in any initial permutation),
`_order_cycle_vertices` always produces the same cycle geometry. The greedy
neighbor walk is rotation/reversal-variant but the shoelace area is
rotation-invariant, so the area is stable. Verified: 100 permuted start
orders on an octagon+chord graph all produce the same area (700.0 mm²).

The order-sensitivity is therefore **entirely in `cycle_basis` + `max(key=len)`**
(which cycle is in the basis and which is longest), not in the ordering or
area computation downstream of cycle selection.

---

## 5. M3 — tie census (distribution of outputs)

`tools/measurements/loop_area_cycle_basis/m3_tie_census.py`:

256 permutation seeds per graph, with exhaustive true-maximum-cycle
computation for small graphs (combinatorial enumeration up to 8 vertices).

| Graph | Nodes/Edges | Distinct areas | Area values (mm²) | True max area | Baseline underestimates? |
|---|---|---|---|---|---|
| house | 5/7 | 2 | 25.0, 50.0 | 50.0 | **Yes** (returns 25.0) |
| non_planar (K5) | 5/10 | 3 | 25.0, 50.0, 75.0 | 75.0 | **Yes** (returns 25.0) |
| grid_3×3 | 9/12 | 2 | 100.0, 400.0 | 400.0 | **Yes** (returns 100.0 134/256 times) |

Key observations:

- **The "longest in basis" heuristic underestimates the true maximum cycle
  area on all three graphs.** This is inherent to the algorithm, not an
  order-dependency: a fundamental cycle basis does not contain all cycles,
  and the longest fundamental cycle is not necessarily the longest simple
  cycle.

- **grid_3×3 shows 4× spread:** the area is either 100 mm² (a single 1×1
  cell) or 400 mm² (the full 3×3 perimeter). The 8-cycle perimeter appears
  in the basis 122/256 times; the 4-cycle cell wins 134/256 times.

- **The cycle_basis size is constant** (3 for house, 6 for K5, 4 for
  grid_3×3) across all 256 seeds — the *number* of fundamental cycles is
  fixed by the cycle space dimension |E|−|V|+1, but *which* cycles are in
  the basis varies.

- **Area values cluster around small-integer multiples of 25 mm²** (the unit
  cell area in these synthetic grids). This is a property of the regular
  spacing; real PCB traces would produce more varied areas.

---

## 6. Downstream consumers (F3)

`commutation_loop_area` is called from exactly one location in the
repository:

`gates.py:754-756`:
```python
from temper_placer.physics.loop_area import commutation_loop_area
loop_area_mm2 = commutation_loop_area(pcb)
```

This is inside `PhysicsGate.check()` at line 741. The area is compared
against `_COMMUTATION_LOOP_MAX_MM2 = 2000.0` (line 762). If exceeded, a
`LOOP_INDUCTANCE` violation is created (lines 763-778) with severity set to
the area value, which feeds `to_delta()` → `LoopAreaConstraint` corrective
actions.

| Consumer | File | How area used | Impact if area differs |
|---|---|---|---|
| PhysicsGate | `gates.py:756-778` | Compared to 2000 mm² threshold → violation | Different pass/fail decision |
| to_delta | `gates.py:370-383` | `LoopAreaConstraint` corrective action | Different constraint severity |
| Gate pipeline | `gates.py` (via `Gate.check()`) | Aggregated into gate result | `CLEAN` vs `VIOLATIONS` |

On the production board, the gate returns `UNMEASURED` because
`auto_extract_loops` finds zero commutation loops, so no divergence
propagates. But if the loop extractor were fixed to recognize the board's
net naming, the `cycle_basis` instability would become live.

---

## 7. The "longest cycle in basis" heuristic is dubious independent of order

Even if `cycle_basis` were deterministic (fixed insertion order), the
heuristic is still a poor proxy for loop area:

1. **It computes a fundamental cycle, not the true max cycle.** Fundamental
   cycle bases span the cycle space but do not necessarily contain the
   longest simple cycle. The true maximum simple cycle is NP-hard to find;
   `cycle_basis` returns a set of |E|−|V|+1 cycles that may all be small.

2. **It's disconnected from the physics.** The commutation loop is a
   specific geometric path through specific nets — it is not "the longest
   cycle in the trace graph of loop nets." The trace graph may contain spurs,
   parallel paths, and stitching vias that create spurious cycles unrelated
   to the physical current loop.

3. **The convex-hull fallback (line 123) is a known over-estimate**, which
   is why the docstring at line 17-20 documents it as conservative: "A tight
   non-convex loop whose true area is under the threshold may still pass
   under the hull proxy." But the `cycle_basis` path is not conservative —
   it can UNDER-estimate (as shown in §5 for the house, K5, and grid
   graphs), reporting an area smaller than the true loop.

4. **The convex-hull was already migrated to Rust** (`temper_geometry.convex_hull_area_py`,
   line 246), replacing `scipy.spatial.ConvexHull` with no ordering risk
   (`docs/evidence/2026-08-07-scipy-keeps-re-triage.md` §2). The
   `cycle_basis` path remains the last networkx dependency in this module.

---

## 8. What this means for the networkx migration

The `networkx` surface in `loop_area.py` consists of:

| Line | Call | Migration impact |
|---|---|---|
| 33 | `TYPE_CHECKING` import `networkx as nx` | Remove |
| 107 | `import networkx as nx` | Remove |
| 109 | `_build_trace_graph(traces)` → `nx.Graph()` | Replace with petgraph |
| 111 | `G.number_of_nodes()` | Trivial petgraph equivalent |
| 114 | `max(nx.connected_components(G), key=len)` | Replace with petgraph (order-insensitive for single CC) |
| 115 | `G.subgraph(largest_cc).copy()` | Replace with petgraph subgraph |
| 117 | `_find_main_cycle(subgraph)` → `nx.cycle_basis` | **DELETE** |
| 131 | `_build_trace_graph` → `nx.Graph()` | Replace with petgraph |
| 138 | Type annotation `nx.Graph` | Remove |
| 150 | `_find_main_cycle` type annotation `nx.Graph` | **DELETE** |
| 162 | `import networkx as _nx` | **DELETE** |
| 164 | `list(_nx.cycle_basis(graph))` | **DELETE** |
| 176 | `_order_cycle_vertices` type annotation `nx.Graph` | **DELETE** |
| 198 | `graph.neighbors(current)` | **DELETE** (with function) |

**The `_find_main_cycle` function and `_order_cycle_vertices` helper should
be deleted entirely.** They are unreachable on the production board (F2),
order-unstable when reached (F1), and the "longest in basis" heuristic is a
poor proxy for the true loop area (§7). The `_find_main_cycle` function
covers lines 149-209 (61 LOC).

The remaining function, `_compute_area_from_traces`, would be simplified
to: build graph → largest CC → convex-hull fallback (always). The
`_build_trace_graph` function (lines 128-146, 18 LOC) would be ported
from `nx.Graph` to `petgraph::UnGraph`.

**Total networkx surface after deletion:** The `import networkx as nx`
in `channel_skeleton.py` (line 12, the last remaining `nx` import in the
repository per S4) would become the ONLY `nx` use. After the S4 port, the
repository has zero `networkx` dependencies.

---

## 9. Recommendations

1. **DELETE `_find_main_cycle` and `_order_cycle_vertices` (lines 149-209).**
   These 61 LOC are dead code that is order-unstable and algorithmically
   dubious. Do not port them.

2. **Simplify `_compute_area_from_traces` to always use convex-hull.**
   After deletion, the function becomes: build graph → largest CC → convex
   hull. The convex-hull is already ported to Rust
   (`temper_geometry.convex_hull_area_py`) with no ordering risk.

3. **Port `_build_trace_graph` from `nx.Graph` to `petgraph::UnGraph`.**
   This is a mechanical port (nodes are `(f64, f64)` tuples, edges carry
   weight). The function is 18 LOC and trivially portable.

4. **Remove `import networkx` from `loop_area.py`.** After deleting
   `_find_main_cycle`, the only `nx` dependency is `_build_trace_graph`'s
   `nx.Graph()`. After porting that, the `import networkx as nx` at line 107
   can be removed.

5. **The `connected_components` tie-breaking at line 114 is a non-issue**
   in the convex-hull-only path. The convex hull uses `largest_cc` as a
   point set; tie-breaking between equal-sized components doesn't affect
   the hull area of either component (both would produce the same hull).

6. **If commutation-loop area is needed in the future**, reimplement with a
   physics-grounded approach rather than `cycle_basis`. Options:
   - Trace the specific loop geometry through the routed traces (the loop
     extractor already knows which nets form the loop — follow those traces
     specifically)
   - Use the polygon formed by the trace endpoints directly rather than
     searching for cycles in an undirected graph
   - If a graph cycle is truly needed, use a proper maximum-cycle algorithm
     (not `cycle_basis` + longest heuristic), accepting the NP-hardness
     for the small graphs typical of power loops

---

## 10. What I could not verify

- **Other boards.** Only `pcb/temper.kicad_pcb` was measured. A different
  board with different net naming might trigger `auto_extract_loops` to
  find commutation loops, making the `cycle_basis` path reachable. The
  recommendation to delete rather than port is based on the heuristic being
  poor independent of reachability (§7), not on reachability alone.

- **The Rust loop extractor's failure.** The Rust kernel fails with "No bus
  capacitor path." Whether this is a net-naming mismatch, a genuine missing
  component, or a bug in the extractor was not investigated. Fixing the
  extractor would make the `cycle_basis` path reachable — which is why the
  recommendation is DELETE, not "leave as dead code."

- **Full end-to-end route with live loop area.** Not attempted. The spike's
  scope was the `cycle_basis` order question specifically.

- **`networkx` version stability of `cycle_basis`.** The spanning-tree
  algorithm in networkx could change across versions. The measurements here
  are specific to networkx 3.6.1. A port attempting to reproduce
  `cycle_basis` exactly would need to pin against a moving target.

---

## 11. Reproducing

Scripts live in `tools/measurements/loop_area_cycle_basis/`.

```bash
# M1 — reachability on production board
PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
  .venv/bin/python3 tools/measurements/loop_area_cycle_basis/m1_reachability.py \
  --pcb pcb/temper.kicad_pcb --out m1.json

# M2 — permutation experiment (synthetic graphs)
PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
  .venv/bin/python3 tools/measurements/loop_area_cycle_basis/m2_permutation.py \
  --out m2.json --seeds 64

# M3 — tie census (distribution of outputs)
PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
  .venv/bin/python3 tools/measurements/loop_area_cycle_basis/m3_tie_census.py \
  --out m3.json --seeds 256
```

**Requirements:** `temper_geometry` Rust extension built for Python 3.12
(for M1). M2/M3 use only `networkx` + `numpy` and run on any Python.

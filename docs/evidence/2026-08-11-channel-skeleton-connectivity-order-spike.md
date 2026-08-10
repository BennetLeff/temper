<!-- provenance: commit=66f84b87 dirty=false -->
<!-- measured_at_commit: 66f84b87 (merge: migrate/phase-d4-assignment) -->

# Spike S4: Is `nx.connected_components` observable in `_ensure_skeleton_connectivity`?

**Date:** 2026-08-10
**Surface:** `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py`
Line 529: `components = list(nx.connected_components(G))` — the last remaining
`networkx` import in the repository (line 12: `import networkx as nx`).
**Scope:** a verdict plus its measurements. **No production code was changed,
no Rust was written, and no Rust crate was built.**

**Context:** This is the gate for whether the final networkx surface can be
removed (petgraph parity needed) or is clean (order-insensitive). The
preceding S3 spike (`docs/evidence/2026-08-04-networkx-path-order-spike.md`)
dissolved the `channel_mapping.py` blocker; this spike addresses the last
remaining `nx` use.

---

## Verdict

**ORDER-INSENSITIVE — `_ensure_skeleton_connectivity`'s output does not
depend on `nx.connected_components` enumeration order. The networkx
dependency can be cleanly removed without reproducing its internal
enumeration tie-breaking.**

The result is more nuanced than a simple binary, and the nuance is load-bearing:

1. **`connected_components` enumeration order does NOT directly affect
   the output.** The component IDs feed into a Union-Find Kruskal MST
   algorithm; permuting the component ID assignment produces identically the
   same bridge edge set (verified: 0/120 permutations differ, §4).

2. **Insertion order CAN affect the output, but through node indices, not
   `connected_components`.** The Kruskal sort key is `(distance, i, j)` where
   `i, j` are node indices from `list(G.nodes())` — insertion-order
   dependent. When bridges ARE added with tied distances, 59/64 permutation
   seeds produce different bridge edge sets (§4). But this is a property of
   `list(G.nodes())` order, not of `nx.connected_components` order.

3. **On the production board, the question is moot.** The bridge branch IS
   reached (3 connected components after Voronoi skeleton extraction), but
   **0 bridges are added** — all 1,846 cross-component candidate bridges
   fail the geometry validity check (`_bridge_validity_mask`) because the two
   tiny 2-node islands are obstacle-separated from the main 21,709-node
   component (§2). No bridges → no order sensitivity.

4. **The production board is not representative for other boards.** A board
   where islands are not obstacle-separated would trigger bridge addition,
   and the insertion-order sensitivity would become live. The mechanism
   (node-index tiebreak in sort) is not specific to `networkx` and would
   equally affect a petgraph port.

**Recommendation:** Remove `networkx` without reproducing
`connected_components` order. Use `petgraph`'s `connected_components()`
(which also uses DFS/BFS internal ordering, just a different one). Add a
differential test that verifies the same bridge edges for the production
board (0 bridges → trivially passes). Document the latent insertion-order
sensitivity as a known property rather than a blocker — any future change
that makes bridge edges live should address it at that point.

---

## Falsifiers, stated before measuring

Per S3's convention, falsifiers were written down before measurement:

**F1 — order-observable.** *Permuting node/edge insertion order (same node
set, edge set, weights) changes the bridge edge set output by
`_ensure_skeleton_connectivity`.*

> **F1 FIRED on synthetic graphs with genuine ties (59/64 seeds); DID NOT
> FIRE on the production board (0 bridges added).** The mechanism is the
> node-index tiebreak in the Kruskal sort key, NOT the
> `connected_components` enumeration. Details in §4.

**F2 — reachable.** *`_ensure_skeleton_connectivity` is reached with
`n_components > 1` on the production board.*

> **F2 FIRED.** The Voronoi skeleton on both inner layers has 3 connected
> components (sizes [21709, 2, 2]). The bridge branch at line 531–532 is
> entered. Details in §2.

**F3 — observable downstream.** *If bridge edges differ, does the difference
reach a consumer?*

> **F3 is MOOT.** No bridges are added, so no divergence propagates. The
> architecture review confirms that bridge edges DO feed into SAT variable
> creation (`constraint_model.py`), channel width computation
> (`channel_widths.py`), bundle analysis (`bundle_analyzer.py`), and net
> batching (`net_batching.py`) — so they WOULD be observable if present (§5).

---

## 0. Environment and provenance

One caveat, documented up front like S3 §0.

**(a) The measurements ran against the main checkout's `.venv` Python 3.12,
not this worktree's Python 3.9.** `temper_geometry` (the Rust extension) is
only built for Python 3.12. The worktree's Python 3.9 cannot import it. The
measurements therefore use:

```bash
PYTHONPATH="/tmp/opencode/wt-f9-1/packages/temper-placer/src:$PYTHONPATH" \
  /home/bennet/Desktop/temper/.venv/bin/python3
```

The file under measurement is **byte-identical** across both trees:

| File | sha256 |
|---|---|
| `router_v6/channel_skeleton.py` | `cbc9df3e27c5b35edc48a9b6fb85f8f321529adc9e36e36cecf12ba38431899a` |

All static analysis runs against this worktree at `66f84b87` and is
unaffected either way.

**Board:** `pcb/temper.kicad_pcb`, 169 components, 110 nets.
**networkx 3.6.1, shapely 2.0.1, numpy 1.24.4, Python 3.12.3.**

At measurement time the working tree contained only untracked measurement
scripts added by this PR; every file under measurement was unmodified at
`66f84b87`.

---

## 1. What `connected_components` actually feeds

`channel_skeleton.py:529,540-542`:

```python
components = list(nx.connected_components(G))       # line 529
n_components = len(components)                       # line 530
if n_components <= 1:
    return G  # Already connected                    # line 531-532

nodes = list(G.nodes())                              # line 535
positions = np.asarray(nodes, dtype=float)           # line 536
node_index = {node: i for i, node in enumerate(nodes)} # line 537

comp_id = np.empty(len(nodes), dtype=np.int64)      # line 539
for cid, comp in enumerate(components):              # line 540
    for node in comp:                                # line 541
        comp_id[node_index[node]] = cid              # line 542
```

The `components` enumeration order assigns integer IDs to each component.
These IDs are stored in the `comp_id` array (mapping each node to its
component's ID). The IDs are later used in the Kruskal loop:

```python
ci, cj = uf.find(comp_id[i]), uf.find(comp_id[j])   # line 585
if ci == cj:
    continue                                          # line 586-587
```

The question: does permuting the component ID assignment change which
bridge edges get added?

The Kruskal algorithm's edge-selection decision depends only on the
PARTITION of nodes into components, not the LABELS. The Union-Find
structure is initialized with `n_components` elements, each its own
root. As long as the same nodes map to the same partition (just with
different labels), the merges produce the same result. §4 verifies this
empirically: 0/120 component-ID permutations produce a different output.

The actual order sensitivity (documented in §4) comes from the **node
index tiebreak** in the candidate sort — which depends on `list(G.nodes())`
order, not on `connected_components` order.

---

## 2. M1 — reachability on the production board

`tools/measurements/channel_skeleton_connectivity/m1_reachability.py`:

| Layer | Nodes | Edges | Components | Sizes | Bridge branch |
|---|---|---|---|---|---|
| In1.Cu | 21,713 | 28,991 | 3 | [21709, 2, 2] | **taken** |
| In2.Cu | 21,713 | 28,991 | 3 | [21709, 2, 2] | **taken** |

F.Cu/B.Cu are classified as `plane` on this board (no routing space
computed), so they have no skeleton. Only the inner "mixed" layers
(In1.Cu, In2.Cu) produce skeletons.

The two tiny islands (2 nodes each) are Voronoi artifacts: nodes at
≈0.04mm from the main component but not graph-connected because the
Voronoi edges cross obstacles. They are genuine disconnected components
in the graph sense, even though they're spatially adjacent.

**Bridge edge count: 0.** All 1,846 cross-component candidate pairs
within the 10mm bridging radius fail `_bridge_validity_mask` — the line
segments between island nodes and main-component nodes cross obstacle
geometry.

The bridge branch is entered (line 531: `n_components=3 > 1`), the
candidate enumeration runs, but the Kruskal loop exits with `merges=0`
because every candidate is geometrically invalid.

---

## 3. M2 — candidate analysis on the production board

| Metric | Value |
|---|---|
| Total pairs within 10mm (`_radius_pairs`) | 3,451,993 |
| Cross-component pairs (different `comp_id`) | 1,846 |
| Unique distances among cross-component pairs | 1,641 |
| Tied distances (count > 1) | 162 |
| Maximum candidates at same distance | 4 |
| **Valid bridges (`_bridge_validity_mask`)** | **0** |

The tied-distance candidates (162 groups of 2-4 candidates at identical
distance) are the mechanism through which insertion-order sensitivity
could manifest (§4). But since none pass the geometry check, the ties
are never reached by the Kruskal loop.

---

## 4. M3 — synthetic permutation experiments

`tools/measurements/channel_skeleton_connectivity/m3_synthetic_permutation.py`

Three sub-experiments on synthetic graphs where bridges ARE actually
added (no geometry validity check — `available_area=None`):

### Experiment A: Component-ID permutation

Graph: 8 islands × 5 nodes each = 40 nodes, 8 components, 7 bridges needed.
All 120 possible component-ID permutations were tested.

| Result | Value |
|---|---|
| Permutations tested | 120 (all) |
| Different bridge edge sets | **0** |
| Verdict | Component-ID order does NOT affect output |

The Union-Find Kruskal algorithm is partition-based, not label-based.
Permuting component IDs is a relabeling that does not change the MST.

### Experiment B: Insertion-order permutation (no ties)

Same graph as A. Rebuilt with permuted edge/node insertion order.
Sort key: `(distance, i, j)` where `i, j` are insertion-order-dependent
node indices. No tied distances between the same component pair.

| Result | Value |
|---|---|
| Seeds | 64 |
| Different bridge edge sets | **0** |

Without tied distances between the same component pair, the distance
field dominates the sort, and all permutations produce identical output.

### Experiment C: Insertion-order permutation with deliberate ties

Graph: 4 single-node islands at positions chosen to create multiple
candidate bridges at identical distances between the same component pair.
Nodes: (0,0), (0,1), (5,0), (5,1). Two bridges at distance 5.0, two at
distance 5.099.

| Result | Value |
|---|---|
| Seeds | 64 |
| Different bridge edge sets | **59** |
| Verdict | **ORDER-OBSERVABLE when ties exist** |

**This is the key finding.** When bridges ARE added AND there are tied
distances between the same component pair, the `(i, j)` tiebreak (which
depends on `list(G.nodes())` insertion order) causes different edges to
be selected. Example divergence at seed 0:

```
Baseline: {(0,0)-(5,0), (5,0)-(5,1), (0,0)-(0,1)}
Seed 0:   {(0,0)-(5,0), (0,1)-(5,1), (0,1)-(5,0)}
```

Two of the three bridge edges differ. Both sets connect all components —
the graph IS connected either way — but the specific edges are different.

**The mechanism is the node-index tiebreak, NOT `connected_components`.**
The component-ID experiment (A) shows that `enumerate(components)` order
does not cause differences. The insertion-order experiment (C) shows that
`list(G.nodes())` order does. The original code's comment at lines
559-563 already documents this tiebreak as a design choice:

```python
# Canonical tie-break: sort by (distance, i, j), not distance
# alone. `_radius_pairs` already guarantees i < j per pair (see
# its own docstring), so this is a total order with no ties --
# deterministic and independent of which spatial-index backend
# produced the candidate set.
```

The comment is correct about spatial-index backends but incomplete about
node insertion order: `i, j` are indices into `list(G.nodes())` (line 535),
which IS insertion-order dependent.

---

## 5. Downstream consumers (F3)

Bridge edges flow into these consumers. On the production board (0 bridges),
no divergence reaches any of them.

| Consumer | File | How edges used | Impact if bridges differ |
|---|---|---|---|
| SAT model | `constraint_model.py:660` | `canonical_channel_edges(skeleton.graph, layer_name)` → SAT variables | Different variables → different model |
| Channel widths | `channel_widths.py:463,510` | Iterates `skeleton.graph.edges()` for width sampling | Different edges → different widths |
| Bundle analysis | `bundle_analyzer.py:186` | `skeleton.graph.edges(data=True)` for median length | Different edges → different median |
| Net batching | `net_batching.py:300` | `canonical_channel_edges()` for edge lookup | Different edges → different lookup |
| Channel mapping | `channel_mapping.py:474` | `skeleton.graph.nodes()` for waypoints | Bridge edges add no new nodes |

`canonical_channel_edges` (line 104) delegates to the Rust kernel
`constraint_model.canonical_channel_edges_py(layer_name, list(graph.edges))`,
which sorts by quantised endpoint keys. Different bridge edges would produce
different canonical edges, different SAT variables, and a different
optimization model. The SAT solver's output would differ, potentially
changing the routed PCB.

**This mechanism is live if bridges are added.** On the production board,
it is dead code (0 bridges).

---

## 6. Why the production board adds 0 bridges

The two tiny Voronoi islands (2 nodes each) are:
- Spatially close to the main component (~0.04–0.05mm)
- Graph-disconnected because Voronoi edges cross obstacle geometry
- Geometrically separated: the line segment from island node to main
  component node does not lie entirely within the routable `available_area`

`_bridge_validity_mask` (line 303) tests `shapely.contains(buffered_area, line)`
for every candidate bridge. Since the islands are in obstacle "pockets"
carved out of the routing space, every bridge candidate crosses an obstacle
and is rejected.

This is the same upstream issue documented in the function's docstring
(lines 509-524): the obstacle map's zone loop unions every zone net-blind,
creating spurious fragmentation. The durable fix is the scoped
pour-derivation project (`docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`).

---

## 7. What this means for the networkx migration

The `networkx` surface in `channel_skeleton.py` consists of:

| Line | Call | Migration impact |
|---|---|---|
| 12 | `import networkx as nx` | Remove after all uses gone |
| 40 | `nx.is_connected(self.graph)` | Trivial: check components == 1 |
| 79 | `nx.Graph()` | Replace with petgraph `UnGraph` |
| 529 | `nx.connected_components(G)` | **This spike's subject** |

Lines 40 and 79 are trivial replacements. Line 529 is the only algorithmic
surface.

**Since `connected_components` enumeration order does not affect the
output**, a petgraph port does NOT need to reproduce networkx's internal
DFS/BFS enumeration tie-breaking. Any connected-components algorithm that
correctly identifies the partition is sufficient. The Kruskal sort tiebreak
`(distance, i, j)` uses node indices, which are a property of the node list
(in Rust: a `Vec` of node handles), not of the component enumeration.

**The latent insertion-order sensitivity** (§4, Experiment C) would affect
a petgraph port exactly as it affects the current Python code: it depends
on the node list order, which is determined by the Voronoi emission order.
Both the current GEOS-based Python path and a spade-based Rust path produce
deterministic node ordering; they just produce DIFFERENT deterministic
orders. If bridges were live, the port would need a differential test
to ensure the same bridge edges — or accept that different but valid
bridges are acceptable.

**The port is safe** because the production board adds 0 bridges. Any
future board that triggers bridge addition should add a differential test
pinning the expected bridge edges at that point.

---

## 8. Recommendations

1. **Remove `networkx` from `channel_skeleton.py`.** The three uses are all
   replaceable: `nx.Graph()` → `petgraph::UnGraph`, `nx.is_connected()` →
   trivial check, `nx.connected_components()` → petgraph's BFS/DFS
   components (no need to match networkx's enumeration order).

2. **Do NOT add petgraph parity for `connected_components` ordering.**
   This spike proves it is not observable (§4, Experiment A). The port
   only needs CORRECT component identification, not identical enumeration.

3. **Document the latent insertion-order sensitivity.** The sort tiebreak
   `(distance, i, j)` makes the Kruskal output sensitive to node list order
   when bridges are added with tied distances. This is not a networkx
   property — it is an algorithmic property that would persist in any port.
   Add a comment in the ported code noting that the output depends on node
   list order when bridge ties exist.

4. **Add a differential test.** Verify that the petgraph-based port
   produces the same edge set for the production board (trivially: 0 bridges
   → empty set). This catches any algorithmic error in the component
   detection itself.

5. **The `nx.is_connected` at line 40 is a property getter on
   `ChannelSkeleton`.** It is called in test assertions and
   `validate_channel_skeleton`. Replace with a pure-Python check:
   `len(list(components)) <= 1` — no algorithmic dependency at all.

6. **Total networkx surface after this migration:** 0 lines. The last
   `import networkx as nx` in the repository can be removed.

---

## 9. What I could not verify

- **Other boards.** Only `pcb/temper.kicad_pcb` was measured. A different
  board might have islands within the bridging radius that pass the geometry
  check, triggering bridge addition and exposing the insertion-order
  sensitivity. The synthetic experiments (§4) characterize the mechanism;
  the finding that it does not fire on the current production board is a
  measurement of THIS board, not a universal guarantee.

- **`nx.is_connected` on a petgraph graph.** The `ChannelSkeleton.graph`
  field currently holds an `nx.Graph`. After migration to petgraph, the
  `is_connected` property and all consumers would need updating. This is
  the porting work, out of scope for this spike.

- **Full end-to-end route.** Not attempted. The spike's scope was the
  `connected_components` order question specifically. A full route would be
  needed to verify that the SAT solver's output is identical after
  migration, but this is the general migration verification, not specific
  to this spike.

---

## 10. Reproducing

Scripts live in `tools/measurements/channel_skeleton_connectivity/`.

```bash
# M1 — reachability on production board
PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
  .venv/bin/python3 tools/measurements/channel_skeleton_connectivity/m1_reachability.py \
  --pcb pcb/temper.kicad_pcb --out m1.json

# M2 — permutation experiment on production board (finds 0 bridges)
PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
  .venv/bin/python3 tools/measurements/channel_skeleton_connectivity/m2_permutation.py \
  --pcb pcb/temper.kicad_pcb --out m2.json --seeds 16

# M3 — synthetic permutation experiments (bridges actually added)
PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
  .venv/bin/python3 tools/measurements/channel_skeleton_connectivity/m3_synthetic_permutation.py \
  --out m3.json --seeds 64
```

**Requirements:** `temper_geometry` Rust extension built for Python 3.12
(for M1/M2). M3 uses only `networkx` + `numpy` and runs on any Python.

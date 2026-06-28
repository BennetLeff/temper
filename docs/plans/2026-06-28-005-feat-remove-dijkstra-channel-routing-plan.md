---
title: "feat: Remove Dijkstra from Stage 4 channel mapping, use SAT solver output as primary path"
type: feat
status: active
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-remove-dijkstra-channel-routing-requirements.md
---

# Remove Dijkstra from Stage 4 Channel Mapping

## Summary

Delete the Dijkstra-based skeleton pathfinder from `channel_mapping.py:_map_net_to_channels` and make the Rust SAT solver's output the primary channel assignment path. Add `path_graph` reconstruction to the Rust `extract_topology` so Stage 4 receives the ordered channel edge walk directly.

---

## Problem Frame

Stage 4 currently runs Dijkstra on the skeleton graph before consulting the SAT solver's output. This was a workaround for a broken solver (the code comment says "the topological solver is currently a mock"). Now that the Rust solver produces correct, capacity-constrained assignments, Dijkstra overrides them — routing without capacity, diff-pair, or layer constraints. It must be removed.

(see origin: `docs/brainstorms/2026-06-28-remove-dijkstra-channel-routing-requirements.md`)

---

## Requirements

- R1. Delete the Dijkstra call (`_find_skeleton_path_for_net`) from `_map_net_to_channels`
- R2. SAT solver's `uses_channels` is the primary channel sequence
- R3. A* runs as fallback for nets absent from `TopologyGraph` (existing behavior at `pipeline.py:644`)
- R4. Rust `extract_topology` produces `path_graph` (ordered channel edges) — ships in same PR
- R5. Closure test completion rate does not regress

**Origin actors:** A1 (Router V6 Pipeline), A2 (Developer)
**Origin acceptance examples:** AE1 (SAT channels used directly), AE2 (A* fallback for unassigned), AE3 (path_graph populated), AE4 (completion rate regression gate)

---

## Scope Boundaries

- Does not change A*, occupancy grid, Stage 2, or Stage 5
- `skip_stage3=True` degrades to direct A* without skeleton guidance (acceptable — debugging bypass, not production path)

### Deferred to Follow-Up Work

- Removing `_find_skeleton_path_for_net`, `_extract_waypoints`, `_calculate_path_length` helpers if no remaining callers

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py:130-170` — `_map_net_to_channels()`, the function to modify. Dijkstra call at line 139-140.
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:636-641` — caller, passes `nets` and `components` (enables Dijkstra path)
- `packages/temper-rust-router/src/extraction.rs` — `extract_topology()`, to add `path_graph` reconstruction
- `packages/temper-rust-router/src/types.rs:362-369` — `NetTopology` struct, needs `path_graph` field
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:576-582` — Rust→Python `NetTopology` construction, sets `path_graph=None`, needs update

### Institutional Learnings

- The SAT solver produces correct, capacity-constrained assignments verified by constraint audit (`audit.rs`) and cross-validated against pysat
- The Rust `NetTopology` currently has only `uses_channels: Vec<String>` — unordered channel list. `path_graph` needs ordered edge walk through the skeleton graph

---

## Key Technical Decisions

- **Delete, don't gate.** Dijkstra is removed entirely from `_map_net_to_channels` — no feature flag, no conditional branch. The comment at line 136 ("bypass the mock solver") is the record of why it existed.
- **`path_graph` as ordered edge list in Rust.** The Rust solver's variable assignments encode which SAT variables are true. By walking the skeleton graph edges in order of SAT assignment, `extract_topology` can reconstruct the ordered path. This avoids a Python-side post-processing step.
- **`path_graph` shipped in same PR.** R4 is a prerequisite, not a follow-up. The Rust extraction and the Dijkstra removal land together.

---

## Implementation Units

### U1. Add `path_graph` to Rust `TopologyGraph` extraction

**Goal:** `extract_topology` produces ordered channel edge sequences for each net, matching the `uses_channels` list.

**Requirements:** R4

**Dependencies:** None

**Files:**
- Modify: `packages/temper-rust-router/src/types.rs`
- Modify: `packages/temper-rust-router/src/extraction.rs`

**Approach:**
- Add `path_graph: Vec<(String, String)>` to `NetTopology` in `types.rs` — an ordered list of (edge_src, edge_dst) tuples representing the walk through the skeleton graph.
- In `extract_topology`, after building `uses_channels`, reconstruct the ordered edge walk. The SAT variable assignments encode which channels are used. The `uses_channels` list is the channel ID order. For each consecutive pair of channels, emit an edge tuple. For single-channel assignments, the edge is `(pin_src, channel_id)`.
- The `path_graph` is a lossless ordered version of the same data in `uses_channels` — no new information, just ordering.

**Test scenarios:**
- Happy path: Net assigned to CH1,CH5 → path_graph = [(pin, CH1), (CH1, CH5)] matching uses_channels order
- Edge case: Net assigned to single channel CH1 → path_graph = [(pin, CH1)]
- Edge case: Net with zero channels → path_graph = [], uses_channels = []
- Integration: Python side reads `path_graph` from Rust result and constructs `NetTopology` with it

**Verification:**
- `cargo test extraction` — path_graph is populated when uses_channels is non-empty
- Python test: `solve_topology_rust` returns `path_graph` for each net in `topology_graph`

---

### U2. Wire `path_graph` into Python-side `NetTopology`

**Goal:** `pipeline.py` reads the Rust `path_graph` and populates the Python `NetTopology.path_graph` field.

**Requirements:** R2, R4

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`

**Approach:**
- In `_run_stage3`, replace `path_graph=None` with `path_graph=list(topo_data.get("path_graph", []))` from the Rust result.
- The Rust `path_graph` is a list of `(src, dst)` tuples. Convert to `nx.DiGraph` using `networkx` — add each edge to the graph, add nodes implicitly.
- If path_graph is empty or absent, fall back to None (existing behavior for skip_stage3).

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:576-582` — existing `NetTopology` construction from Rust output

**Test scenarios:**
- Happy path: Rust returns path_graph with 2 edges → Python `NetTopology.path_graph` is a DiGraph with 2 edges
- Edge case: Rust returns empty path_graph → `path_graph` is an empty DiGraph (no crash on `.edges()`)
- Edge case: `topology_graph` key missing → `path_graph` default None

**Verification:**
- `python -c "from temper_rust_router import solve_topology_rust; r = solve_topology_rust(...); assert 'path_graph' in r['topology_graph'][net_name]"` — passes

---

### U3. Delete Dijkstra from `_map_net_to_channels`

**Goal:** Remove lines 139–140 (the `_find_skeleton_path_for_net` call) and the `net_obj`/`comp_map` dependency in that function.

**Requirements:** R1, R2

**Dependencies:** U2 (path_graph available for Stage 4 to consume)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py`

**Approach:**
- Delete lines 135–140: the entire "Prefer Geometric Routing" block, the comment, and the Dijkstra call.
- Remove the `net_obj` and `comp_map` parameters from `_map_net_to_channels` — they exist only to feed Dijkstra.
- Update the caller `map_topology_to_channels` at line 101-108 — remove the `net_obj` and `comp_map` argument construction, pass only `net_name`, `net_topology`, `skeleton`.
- The remaining function is: try `uses_channels`, then try `path_graph.nodes()` for node-based sequences, then return None.
- The pipeline-level fallback at `pipeline.py:643-660` (direct A* for nets returning None) is unchanged — this is the A* fallback for unrouted nets.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py:130-170` — the function being simplified

**Test scenarios:**
- Happy path: Net with uses_channels=["CH1","CH5"] → channel_sequence = ["CH1","CH5"] via line 144 (Covers AE1)
- Happy path: Net with path_graph containing 2 nodes → channel_sequence extracted from nodes (Covers AE3)
- Edge case: Net absent from topology → returns None, pipeline falls through to A* (Covers AE2)
- Edge case: Net with empty uses_channels and empty path_graph → returns None (unchanged)
- Regression: `skip_stage3=True` produces topology=None → all nets return None → pipeline falls back to direct A* (documented degradation)

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_channel_mapping.py` — existing tests adapted for removed parameters
- Manual: closure test with `TEMPER_SAT_BACKEND=rust` — completion rate matches or exceeds baseline

---

### U4. Update `skip_stage3` documentation

**Goal:** Document that `skip_stage3=True` after Dijkstra removal routes via direct A* without skeleton guidance.

**Requirements:** R3 (implicit — the fallback behavior is unchanged, only the mechanism differs)

**Dependencies:** U3

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`

**Approach:**
- Update the docstring and inline comment at `skip_stage3` (lines 432-447) to note: "After Dijkstra removal (2026-06-28), skip_stage3 routes nets via direct A* on the occupancy grid without skeleton guidance. Previously used Dijkstra on the skeleton graph."
- No behavioral change — the flag already works this way after U3.

**Test scenarios:**
- Test expectation: none — documentation only

**Verification:**
- Docstring accurately describes post-Dijkstra behavior

---

## System-Wide Impact

- **Interaction graph:** `_map_net_to_channels` loses the Dijkstra code path. The caller (`map_topology_to_channels`) loses `nets` and `components` parameters (they only fed Dijkstra). Pipeline-level A* fallback unchanged.
- **Error propagation:** Nets without SAT assignment now reach A* directly (previously Dijkstra papered over them). No new error paths — A* already handles unroutable nets.
- **Unchanged invariants:** A*, occupancy grid, Stage 2, Stage 5, DRC verification are untouched.
- **skip_stage3:** Degrades from skeleton-guided routing to direct A*. Acceptable — debugging bypass, not production path.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Completion rate drops because SAT assignments don't map to valid skeleton paths | Closure test is the regression gate; if completion drops, the SAT solver's assignment quality needs improvement — Dijkstra is not the fix, it was masking the problem |
| `path_graph` reconstruction in Rust is incorrect (wrong edge order) | Cross-validate against `uses_channels` in the same Rust test — if they disagree, the test fails |
| `skip_stage3` debugging workflow broken | Direct A* is a worse but functional fallback; the flag's purpose (bypass SAT for debugging Stage 2/4) is still served |

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-06-28-remove-dijkstra-channel-routing-requirements.md`
- `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py:130-170`
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:432-447` (skip_stage3), 576-582 (Rust→Python NetTopology), 636-660 (caller + A* fallback)
- `packages/temper-rust-router/src/types.rs:362-369` (NetTopology struct)
- `packages/temper-rust-router/src/extraction.rs` (extract_topology)

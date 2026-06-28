---
date: 2026-06-28
topic: remove-dijkstra-channel-routing
---

# Remove Dijkstra from Stage 4 Channel Mapping

## Summary

Remove the Dijkstra-based skeleton pathfinder from `channel_mapping.py:_map_net_to_channels` (lines 139–140). The SAT solver's output becomes the primary routing path, with A* as the only fallback for nets the solver couldn't assign. Dijkstra was a workaround for a broken SAT solver — now that the solver is correct, it actively undermines it.

---

## Problem Frame

Stage 4's `_map_net_to_channels` tries Dijkstra on the skeleton graph before consulting the SAT solver's `uses_channels` output. The comment at line 136 explains why: *"The topological solver (Stage 3) is currently a mock that returns random edges. To ensure connectivity, we bypass it."*

Now that the Rust CDCL solver produces correct capacity-constrained, diff-pair-enforced, layer-restricted channel assignments, Dijkstra is actively harmful:

- It doesn't respect channel capacity — shortest-path routes two nets through the same narrow channel
- It doesn't enforce diff-pair constraints — paired nets take independent paths
- It ignores layer restrictions — a net restricted to L1 gets routed on L2
- It overrides the SAT solver's output entirely for any net where it finds a path, making the Rust rewrite a no-op for those nets

---

## Actors

- A1. **Router V6 Pipeline** — invokes `map_topology_to_channels` after Stage 3
- A2. **Developer** — runs the closure test, expects SAT-constrained routing

---

## Requirements

- R1. Remove `_find_skeleton_path_for_net()` from `_map_net_to_channels` — the Dijkstra bypass is deleted
- R2. The Rust solver's `uses_channels` output is the primary channel sequence for every net the solver assigned
- R3. For nets the SAT solver didn't assign (missing from `TopologyGraph`), A* runs directly on the occupancy grid as the sole fallback (existing behavior at `pipeline.py:644`)
- R4. The Rust `extract_topology` produces `path_graph` (ordered channel edge sequence) so Stage 4 doesn't need to reconstruct it from `uses_channels` — the walk through the skeleton graph is encoded in the SAT variable assignments
- R5. The closure test on `pcb/temper.kicad_pcb` with `TEMPER_SAT_BACKEND=rust` produces a completion rate at or above the current (Dijkstra-assisted) baseline

---

## Acceptance Examples

- AE1. **Covers R1, R2.** Given a SAT solver assignment with `uses_channels=["CH1", "CH5"]` for net "SIG1", when `_map_net_to_channels` runs, it uses those channels directly without running Dijkstra on the skeleton graph
- AE2. **Covers R3.** Given a net absent from the SAT solver's `TopologyGraph`, Stage 4 routes it via A* on the occupancy grid (unchanged fallback behavior)
- AE3. **Covers R4.** Given the Rust solver returns SAT, the `TopologyGraph` contains a `path_graph` for each net with ordered channel edges matching the `uses_channels` list
- AE4. **Covers R5.** Given the closure test runs on `pcb/temper.kicad_pcb` with the Rust solver, the completion rate (routed nets / total nets) is ≥ the rate recorded on the current main branch with Dijkstra active

---

## Success Criteria

- SC1. The closure test completion rate does not regress — Dijkstra removal does not reduce the number of successfully routed nets
- SC2. Channel capacity violations (measured by post-solve audit) reach zero after Dijkstra removal — the Rust solver's constraint audit already validates its own assignments; Dijkstra removal eliminates the remaining source of capacity violations
- SC3. `channel_mapping.py` is simpler — `_map_net_to_channels` has one fewer code path (the Dijkstra branch is deleted)

---

## Scope Boundaries

- **Does not change** the A* pathfinder in Stage 4 — only the channel assignment layer
- **Does not change** the occupancy grid or obstacle map — only how channels are selected
- **Does not affect** Stage 2 (channel analysis) or Stage 5 (DRC verification)
- `skip_stage3=True` after Dijkstra removal routes nets via direct A* without skeleton guidance (previously used Dijkstra). This is acceptable — the flag is a debugging bypass, not a production path.
- **Deferred**: removing the `_find_skeleton_path_for_net` function and `_extract_waypoints` / `_calculate_path_length` helpers if they have no remaining callers

---

## Key Decisions

- **Delete Dijkstra, don't reorder it.** If Dijkstra remains in the code at a lower priority, someone will reprioritize it. The cleanest fix is removal — the function and its call site are deleted.
- **Rust extraction produces `path_graph`.** Rather than having the Python side reconstruct the path from `uses_channels`, the Rust solver produces the ordered edge walk as part of topology extraction. This eliminates a post-processing step and keeps the SAT→A* handoff clean.

---

## Dependencies / Assumptions

- The Rust solver is the only solver backend (already true — Python solver removed in PR #49)
- The Rust solver's constraint audit (capacity, diff-pair, layer) passes with zero violations before Dijkstra removal — verified by the audit tests in `test_stage3_constraint_audit.py`
- The closure test (`ci_closure_test.py`) is the regression gate — any completion rate drop from Dijkstra removal is caught in CI
- R4 (`path_graph` extraction) must ship in the same PR as the Dijkstra removal — the SAT solver's output is the primary path, and Stage 4 needs the ordered channel walk to route correctly

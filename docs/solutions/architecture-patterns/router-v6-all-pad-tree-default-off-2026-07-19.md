---
title: "Router V6 all-pad routing: branch-aware trees must remain opt-in until full-board DRC closure"
date: 2026-07-19
category: architecture-patterns
module: router_v6
problem_type: architecture_pattern
component: pcb-routing
severity: high
applies_when:
  - "Adding physical connectivity for every pad on a multi-pad signal net"
  - "Exporting a routed tree to KiCad without converting it to a serial route"
  - "Evaluating experimental Router V6 topology changes against board-level DRC"
tags:
  - router-v6
  - all-pad-routing
  - terminal-tree
  - astar
  - kicad-drc
  - feature-flag
---

# Router V6 all-pad routing: branch-aware trees must remain opt-in until full-board DRC closure

## Problem and contract

The historical Router V6 route model used one serial `RoutePath` per net. For
a net with three or more pads, routing only the first and last pad can report
a success while leaving intermediate pads electrically disconnected. Appending
all pads to that serial route improves coverage, but it does **not** represent
a tree: flattening independent branches manufactures copper between a sibling
branch endpoint and the next sibling's start.

The all-pad experiment therefore has a narrow contract:

1. Every declared, physically extractable terminal is included in a
   deterministic connectivity plan.
2. Every emitted branch is a legal A* result; a failed branch never becomes a
   direct or forced segment.
3. A complete tree is emitted as separate branch geometry. The writer may not
   add serial bridges, pad stubs, or MST fallback geometry between branches.
4. Existing two-pad and default routing behavior remains unchanged.
5. The feature remains **default-off** until the canonical board's DRC is at
   least as good as the baseline and physical connectivity is independently
   audited.

This is a correctness feature, not an authorization to relax DRC thresholds
or accept new board failures.

## Architecture introduced

The implementation separates topology, execution, and output:

```text
Parsed PCB net pins
  -> ParsedTerminal (stable PadIdentity, center, declared layers)
  -> TerminalTreePlan (deterministic Prim-style edges)
  -> execute_terminal_tree (legal A* per edge, no forced fallback)
  -> TreeRouteGeometry (immutable branches, no serial flattening)
  -> CompiledTreeRoute -> KiCad branch segments
```

Important boundaries:

- `extract_net_terminals` does not invent pad shapes, layers, or transitions.
  SMD terminals must declare the selected layer; PTH terminals use declared
  signal/mixed stackup layers.
- `plan_terminal_tree` is deterministic: canonical pad identity selects the
  root and breaks Manhattan-distance ties.
- `TreeRouteGeometry.iter_segments()` yields consecutive nodes only within
  each branch. It cannot create an edge between sibling branches.
- Planned branches reserve accepted copper immediately with their `net_id`.
  The scoped 2D A* ownership predicate permits its own occupied cells and
  rejects all foreign occupancy, allowing later branches to attach to the
  same-net component without crossing another net.
- Width is a net property, not a path-shape property. Complete and partial
  tree net names participate in `assign_trace_widths`, so branch export uses
  the board-derived/default or net-class width rather than the old `0.127 mm`
  fallback.

The default flag is `RouterV6Pipeline(enable_all_pad_tree=False)`. Only the
opt-in dispatch constructs/executes `TerminalTreePlan`; the conventional
serial `RoutePath`, Numba route search, and writer behavior are preserved.

## Landed commits

The committed foundation is deliberately staged:

| Commit | Purpose |
|---|---|
| `503f425e` | Establish canonical all-pad connectivity foundation. |
| `d77e9804` | Bound experimental all-pad tree search. |
| `6d3db1c9` | Retain truthful safe partial-tree diagnostics. |
| `1c6df12d` | Emit safe experimental partial-tree prefixes. |
| `45751887` | Plan component-aware deterministic terminal trees. |
| `770e7ea7` | Test execution of planned trees through A*. |
| `329f1cdc` | Extract stable terminals from parsed PCB data. |
| `515b5e5d` | Represent all-pad route branches explicitly. |

Follow-on uncommitted integration work at the time of this note wires the
default-off dispatch, same-net occupancy, and branch width propagation. Keep
those changes separate from the measurement record until they are reviewed
and committed.

## Measured KiCad DRC record

The canonical KiCad measurement is the ship gate. Counts below are recorded
as observed; the all-pad variants are not improvements merely because they
route more terminals.

| Configuration | Unconnected items | Total DRC violations | Notes |
|---|---:|---:|---|
| Baseline/default routing | **149** | 953 | Reference. |
| Early all-pad experiment | **218** | 884 | Regressed; do not enable. |
| Partial-tree variant | **203** | 932 | Still worse than baseline. |
| Early branch-aware variant | **208** | 1101 | Included 194 track-width violations. |
| Latest branch-aware opt-in | **208** | **919** | Track-width is fixed to **0**; clearance is 39 and shorts are 113. It remains unshippable. |

The 208 count is preserved exactly as reported in the measurement record; do
not relabel it without the originating KiCad report. Re-run the canonical
board after integrating the width fix before claiming any new DRC result.

## Evidence and test discipline

Focused tests cover:

- connectivity audits for multi-terminal nets and truthful incomplete trees;
- deterministic Prim planning, including permutation/tie cases;
- synthetic A* branch execution with no direct/forced geometry;
- PBT that same-net occupied cells are traversable deterministically while
  foreign occupied cells are blocked;
- safe partial geometry that never claims an unreached terminal;
- branch geometry that cannot emit a sibling bridge;
- PBT over arbitrary declared board default widths, plus GND/HV net-class
  width propagation to complete and partial tree branches;
- writer output proving every branch uses the resolved width and emits no
  fabricated sibling segment.

The focused suite currently comprises 58 tests across terminal extraction,
planning, execution, branch geometry, all-pad routing, result compilation,
width assignment, and writer serialization. This evidence validates the local
contract; it does not substitute for the KiCad DRC gate.

## Non-goals

- Do not make `enable_all_pad_tree` true by default.
- Do not add direct segments, forced fallback geometry, or exporter pad
  stitches to make a tree appear complete.
- Do not alter DRC thresholds, waive shorts/clearance violations, or change
  the PCB merely to improve this experiment's counts.
- Do not infer a pad's routable layer or fabricate vias for an SMD terminal.
- Do not replace all conventional routing with the slower ownership-aware
  reference A*; it is scoped to the opt-in planned-tree execution path.

## Remaining blockers

1. **Board DRC closure:** the opt-in configuration remains far above the 149
   baseline, especially for shorts and clearance. Width propagation removes
   one known failure class but has not demonstrated a clean full-board run.
2. **Physical attachment model:** same-net occupancy permits branches to
   traverse committed copper, but attachment remains grid-cell based. Any
   future pad/track surface model needs an explicit geometry and clearance
   proof, not an inferred connection.
3. **Layer-transition semantics:** selected-layer eligibility is conservative.
   Multi-layer SMD trees require explicit legal via/transition planning before
   they can be generalized.
4. **Result consumers:** downstream DFM/quality checks that only iterate
   `compiled_routes` need deliberate branch-aware support before complete tree
   routes can be treated as production successes everywhere.

## Exact next steps

1. Commit the reviewed default-off dispatch, same-net ownership, and
   branch-width changes with their focused tests.
2. Re-run the canonical KiCad DRC with the exact opt-in configuration and
   record a new table row. Confirm track-width is zero and compare every
   remaining class against baseline 149.
3. Classify the 39 clearance and 113 short violations by emitted branch,
   net, and geometry. Fix only a demonstrated router invariant violation;
   create separate issues for architectural causes under the R22 bug-triage
   rule.
4. Add branch-aware adapters to every quality/DFM consumer that determines
   production success, then add tests proving they inspect each branch and do
   not synthesize sibling bridges.
5. Add a post-solve connectivity/DRC audit over emitted tree geometry. Only
   after that audit and a canonical DRC result no worse than baseline should
   the default-off gate be reconsidered.

## Related

- `packages/temper-placer/src/temper_placer/router_v6/terminal_tree.py`
- `packages/temper-placer/src/temper_placer/router_v6/terminal_tree_execution.py`
- `packages/temper-placer/src/temper_placer/router_v6/tree_route_geometry.py`
- `packages/temper-placer/src/temper_placer/router_v6/trace_width_assignment.py`
- `docs/physics-verification-methodology.md`

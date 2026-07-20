---
title: "All-pad routing connectivity foundation (APC1 U1-U4 preflight) — TDD + PBT + triple-review"
date: "2026-07-19"
category: docs/solutions/architecture-patterns/
module: router_v6
problem_type: architecture
tags:
  - all-pad-connectivity
  - tree-routing
  - truthful-completion
  - multi-layer
  - tdd
  - pbt
  - ce-code-review
  - netclass-assignment
---

# All-Pad Routing Connectivity — U1-U4 Preflight

## Problem

The router reported nets as "routed" after connecting two waypoints, but
KiCad DRC reported **149 `unconnected_items`** — a false-success condition
where multi-pad nets had disconnected islands.  Plan APC1 (2026-07-19-001)
addresses this with an all-pad connectivity contract: a net is successful
only when every conductive pad is in one copper component.

## What was built (this session, TDD + PBT)

Four implementation units, three PRs:

### U1-U2 — Foundation + multi-layer tree routing (PR #236, merged)

- **terminal_extraction.py** — stable parser-local terminal extraction
  (component/pad/net identity, world position, declared layer context)
- **terminal_tree.py** — deterministic Prim-style MST planner
- **terminal_tree_execution.py** — A* branch executor with same-net copper
  reservation and multi-layer shared-layer selection
- **tree_route_geometry.py** — immutable branch-preserving result type
- **astar_core.py** — same-net ownership predicate
- Pipeline dispatch wired behind `enable_all_pad_tree=False` (default-off,
  byte-identical to main)
- 37 focused tests across 5 test files

### U3 — Truthful completion reporting (PR #236, merged)

- `RoutingResults.success_count` and `failure_count` now derive from
  `NetDisposition` rather than raw path count
- Backward-compatible: falls through to path-count logic when
  `connectivity=None`
- 6 new tests (deterministic + PBT) covering ROUTED, INCOMPLETE, EXEMPT,
  PLANE_CONNECTED, and FAILED dispositions
- Triple-reviewed by ce-code-review (correctness + testing personas);
  all P0/P1/P2 findings addressed

### #222 — Production netclass assignments (PR #237, open)

- 43 production-board nets assigned to explicit net classes
- U8 SSOP-20 nets → FinePitch (14 nets, 0.635mm pitch)
- Gate drives → GateDrive, HV → HighVoltage, power rails → Power,
  PWR_RTN → GND
- Legacy corpus names corrected (PWM_H→PWM_HS, DC_BUS+→+340V_BUS)

### U4 preflight — Post-write connectivity verification (PR #238, open)

- **kicad_connectivity.py** — parses emitted `(segment ...)` entries and
  calls `verify_net_connectivity()` per net
- Results stored in `RoutingResult.connectivity` so U3's disposition-based
  completion reporting has real data
- Stitch/plane-MST workarounds preserved (measurement-only preflight)

## Testing discipline

| Layer | What | Count |
|-------|------|-------|
| Unit | Deterministic tests | 31 |
| Property | Hypothesis `@given` | 6 |
| Review | ce-code-review personas (correctness + testing + maintainability) | 3 × full |
| Mutation | B.Cu regression injection → connectivity guard fails in 0.16s | Verified |

## Key patterns

1. **Same-net copper reservation**: tree executor stamps `mark_path_blocked`
   per edge, A* ownership predicate (`cell_value == net_id` is traversable)
   enables branches to attach to previously routed copper
2. **Shared-layer selection**: `_pick_route_layer()` prioritizes the source
   terminal's first declared layer over alphabetical order
3. **The `_layer_names` attribute trap**: `execute_terminal_tree` originally
   accessed `getattr(source, "_layer_names", None)` but `ParsedTerminal`
   defines `layer_names` (public) — caught by three independent reviewers
   in a single review pass, fixed in `6e9fbb11`
4. **Default-off gate**: `RouterV6Pipeline(enable_all_pad_tree=False)` —
   all new behavior is gated; main's byte-identical router output is
   proven by the golden-test signature match (unconnected 0 / delta −84)

## Remaining

- U2: diagnose the 203→149 gap (tree routing produces more unconnected
  items than the legacy path) — blocked on slow KiCad DRC measurement
- U4 full (stitch deletion): blocked on #226 via-aware transitions
- U5-U7: zone policy, KiCad ratchet, traceability — deferred

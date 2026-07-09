---
date: "2026-07-08"
topic: single-layer-agnostic-route
status: requirements
tier: standard-feature
---

# Single-Layer-Agnostic Route — Prove the Router Routes at All

## Summary

Route 100% of nets on the placed temper board on a single layer (F.Cu). This proves the router functions end-to-end on this board before adding multi-layer complexity. Extend the golden-board DRC gate to routing: unconnected nets = 0, KiCad DRC = 0, ERC = 0.

## Problem Frame

The router (`router_v6`) has never been proven to route the temper board end-to-end on this machine. The golden-board DRC gate currently measures placement-only DRC. Before adding stackup, physics constraints, or 45° routing, the router must demonstrate it can route every net on the simplest possible configuration — a single signal layer.

## Requirements

### R1 — Route 100% of nets

Run `PlaceRouteLoop` on the temper board with netclass-aware placement + routing. Every net in the netlist must be routed (completion rate = 1.0).

Gate: `unconnected_items = 0` in the `kicad-cli pcb drc` output on the routed `.kicad_pcb`.

### R2 — KiCad DRC = 0 on routed board

The routed board must pass `kicad-cli pcb drc` with zero errors. This includes track-to-track clearance, track-to-pad clearance, and via annular ring violations introduced by routing.

Gate: `kicad-cli pcb drc` returns 0 errors of all types on the routed output PCB.

### R3 — ERC = 0

Electrical rules check must pass. All pins connected, no unconnected net segments, no single-pin nets with missing connections.

Gate: `kicad-cli sch erc` (or equivalent connectivity check) returns 0 errors.

### R4 — Extend golden-board gate to routing

Add a routed-board DRC decomposition to the existing `test_regression_drc.py`. The gate must run `solve_placement` → `route_pcb` → `kicad-cli pcb drc` → assert `unconnected_items = 0`.

Gate: CI breaks if routing introduces DRC violations beyond the placement baseline.

## Key Decisions

- **Single-layer first.** Prove correctness on the simplest configuration before adding multi-layer complexity. This isolates routing bugs from stackup bugs.
- **Route on F.Cu only.** The temper board has components on F.Cu. Routing on the same layer avoids via complexity for this first gate.
- **Reuse existing DRC decomposition harness.** The `test_regression_drc.py` pattern (parse kicad-cli JSON, count by violation type) is the measurement instrument.

## Scope Boundaries

- Multi-layer routing is out of scope (W2).
- Physics-constrained routing is out of scope (W3).
- 45° routing, via optimization, and aesthetic routing are out of scope (W4).
- Netlist completeness is the gate — completion rate is a means, not the metric.

## Dependencies

- **W0 (router build unblock).** `temper_rust_router` must import and run on this machine.
- **Placement SSOT chain.** Netclass-aware placement (U1-U6 from `2026-07-08-001`) must produce a valid placement.

## Success Criteria

1. `PlaceRouteLoop.run()` completes with `unconnected_items = 0`
2. `kicad-cli pcb drc` on routed output returns 0 errors
3. Golden-board gate extended to routing and passes in CI

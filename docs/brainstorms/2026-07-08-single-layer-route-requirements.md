---
date: "2026-07-08"
topic: single-layer-fcu-route
status: requirements
tier: standard-feature
---

# Single-Layer F.Cu Route — Prove the Router Routes at All

## Summary

Route 100% of nets on the placed temper board on a single layer (F.Cu). This proves the router functions end-to-end on this board before adding multi-layer complexity. Extend the golden-board DRC gate to routing: unconnected nets = 0, KiCad DRC = 0.

## Problem Frame

The router (`router_v6`) has never been proven to route the temper board end-to-end on this machine. The golden-board DRC gate currently measures placement-only DRC. Before adding stackup, physics constraints, or 45° routing, the router must demonstrate it can route every net on the simplest possible configuration — a single signal layer.

## Requirements

### R1 — Route 100% of nets

Run `PlaceRouteLoop` on the temper board with netclass-aware placement + routing. Every net in the netlist must be routed.

Gate: `unconnected_items = 0` in the `kicad-cli pcb drc` output on the routed `.kicad_pcb`.

### R2 — KiCad DRC = 0 on routed board

The routed board must pass `kicad-cli pcb drc` with zero errors. This includes track-to-track clearance, track-to-pad clearance, and via annular ring violations introduced by routing.

Gate: `kicad-cli pcb drc` returns 0 errors of all types on the routed output PCB.

### R3 — Extend golden-board gate to routing

Add a routing DRC decomposition to `test_regression_drc.py` that extends the existing placement gate. The CI test runs `solve_placement → route_pcb → kicad-cli pcb drc` and asserts `unconnected_items = 0` AND `total_errors = 0`.

Gate: CI breaks if the routed board has any DRC violation (error count > 0). Routing-introduced DRC = routed_errors - placement_errors. The golden-board gate tracks both.

## Key Decisions

- **Single-layer first.** Prove correctness on the simplest configuration before adding multi-layer complexity. This isolates routing bugs from stackup bugs.
- **Route on F.Cu only.** The temper board has components on F.Cu. Routing on the same layer avoids via complexity for this first gate.
- **Reuse existing DRC decomposition harness.** The `test_regression_drc.py` pattern (parse kicad-cli JSON, count by violation type) is the measurement instrument.

## Scope Boundaries

- Multi-layer routing is out of scope (W2).
- Physics-constrained routing is out of scope (W3).
- 45° routing, via optimization, and aesthetic routing are out of scope (W4).
- Netlist completeness is the gate.

## Dependencies

- **W0 (router build unblock).** `temper_rust_router` must import and run on this machine.
- **Placement SSOT chain.** The CP-SAT courtyard+edge constraints (plan `2026-07-08-001`, units U1-U6) must produce a DRC-clean placement with `placement_relevant_drc <= 22`.

## Success Criteria

1. `PlaceRouteLoop.run()` completes with `unconnected_items = 0`
2. `kicad-cli pcb drc` on routed output returns 0 errors
3. Golden-board gate extended to routing and passes in CI

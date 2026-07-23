---
title: "Generated-Safety Netlist-to-PCB Parity Gate Prevents Routing a Stale Board"
date: 2026-07-13
category: tooling-decisions
module: temper_placer.validation.real_board_inventory
problem_type: tooling_decision
component: board-flow
severity: high
applies_when:
  - "A generated schematic/netlist is the electrical source of truth but a KiCad PCB is maintained separately"
  - "Safety-critical components or nets were added to the generated design"
  - "A placement/routing flow could otherwise operate on an old PCB silently"
tags:
  - kicad
  - atopile
  - netlist
  - parity-gate
  - fail-closed
  - safety
  - pcb-routing
---

# Generated-Safety Netlist-to-PCB Parity Gate Prevents Routing a Stale Board

## Context

Atopile can generate the correct electrical design while the existing KiCad
board remains a previous revision. Routing that board may succeed technically,
but it produces a polished layout for circuitry that no longer represents the
safety design. A component-name-only check is insufficient because generated
reference designators and KiCad annotations can legitimately differ.

The critical failure mode is not a crash. It is an apparently successful route
or DRC run on a stale physical artifact.

## Decision

Put an explicit preflight before placement and routing:

```text
generated netlist ─┐
                   ├─ validate_kicad_safety_parity ── pass → place/route/DRC
KiCad PCB ─────────┘                              └─ fail → import board update
```

The gate verifies two independent dimensions:

1. **Required safety nets** exist in the generated netlist and in the KiCad
   board. This catches absent shutdown, fault, and sensor-interconnect nets.
2. **Minimum component-family counts** exist on the board. This catches a
   missing comparator/reference/logic path without coupling the check to an
   arbitrary generated reference designator.

`validate_kicad_safety_parity(netlist_path, pcb_path)` implements this in
`temper_placer.validation.real_board_inventory`; `scripts/run_clean_flow.sh`
runs it as Step 0.

## Why it fails closed

A missing safety net is not a routeability defect that a router can repair.
It is evidence that the input board is the wrong design revision. Returning a
warning, a partial score, or an empty DRC list would hide that fact. The gate
therefore raises `BoardParityError` and names every missing net and
component-family/count.

The gate is deliberately conservative: it does not certify correct placement,
creepage, footprints, or routing. It certifies only the prerequisite that the
board contains the newly generated safety design at all.

## Testing pattern

Use both examples and property-based tests:

- A legacy-board fixture must be rejected with the missing safety inventory.
- A complete fixture must be accepted.
- For every required net, removing that net must be rejected.
- For every component family, every count below the required minimum must be
  rejected.

The generated cases prevent the common regression in which a new requirement
is accidentally omitted from a curated negative fixture.

## Operational guidance

When this gate fails:

1. Do not tune placement or routing.
2. Open the KiCad project and perform **Tools → Update PCB from Schematic**.
3. Assign/verify footprints, placement, safety spacing, and isolation routing.
4. Re-run the parity gate before routing again.

`kicad-cli pcb import` is not an alternative. It imports external CAD formats,
not KiCad's native schematic-to-PCB update operation.

## Related

- `packages/temper-placer/src/temper_placer/validation/real_board_inventory.py`
- `scripts/run_clean_flow.sh`
- `AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md`
- `docs/solutions/architecture-patterns/dual-path-rtd-fault-containment-2026-07-13.md`

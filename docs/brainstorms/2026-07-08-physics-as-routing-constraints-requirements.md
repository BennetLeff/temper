---
date: "2026-07-08"
topic: physics-as-routing-constraints
status: requirements
tier: deep-feature
---

# Physics-as-Routing-Constraints — The Induction-Cooker-Critical Track

## Summary

Promote the physics oracle (`packages/temper-placer/src/temper_placer/physics/`) to a routing gate. Enforce four territory-level constraints: (1) commutation-loop area/inductance ceiling — route the power loop tight, (2) gate-drive loop tightness — keep the gate-drive traces short and adjacent to their return paths, (3) thermal pour + thermal vias under Q1/Q2 — provide a continuous copper path to the bottom-side heatsink, (4) copper creepage ≥ 6mm per IEC 60335-1 between HV and LV nets on the same layer. Gate: loop inductance < budget, thermal margin met, copper creepage ≥ 6mm — all in the oracle, all red-on-regression.

## Problem Frame

The physics oracle computes thermal, inductive, and creepage metrics from the board geometry but does not currently feed back into routing. A human designer routing an induction cooker would: (1) keep the commutation loop (DC_BUS+ → Q1 → SW_NODE → Q2 → DC_BUS−) as a tight polygon with minimal enclosed area, (2) pair gate-drive traces (GATE_H, GATE_L) with their return paths to minimize loop inductance, (3) place thermal vias and a bottom-side copper pour under Q1/Q2 to sink heat, (4) maintain 6mm creepage between HV and LV copper on every layer per IEC 60335-1 Table 16. None of these constraints are currently enforced during routing.

## Requirements

### R1 — Commutation-loop area ceiling

The commutation loop (the polygon formed by DC_BUS+ → Q1 → SW_NODE → Q2 → DC_BUS− traces) must have enclosed area ≤ 2000 mm². Loop inductance is proportional to area; the ceiling derives from the dv/dt limits of the IGBTs (IKW40N120H3: 2.5 kV/µs switching speed).

Gate: `commutation_loop_area_mm2 ≤ 2000`. On regression (>2000), the gate fails and the router must re-route the power loop tighter.

### R2 — Gate-drive loop tightness

Gate-drive traces (GATE_H from U_GATE to Q1, GATE_L to Q2) must be paired with their return paths and have loop area ≤ 500 mm². Gate-drive loops with high inductance cause ringing and false turn-on.

Gate: `gate_drive_loop_area_mm2 ≤ 500` for both GATE_H and GATE_L loops. Trace-to-return spacing ≤ 2mm.

### R3 — Thermal pour and via array

A solid copper pour on B.Cu under Q1 and Q2, connected to the IGBT collector pads through a thermal via array (3×3 grid of 0.6/0.3mm vias). The pour provides a low-thermal-resistance path to a bottom-side heatsink.

Gate: thermal via count ≥ 9 under each IGBT. Via array covers the device footprint. B.Cu pour area ≥ device footprint area.

### R4 — Copper creepage ≥ 6mm

HV nets (AC_L, AC_N, DC_BUS+, DC_BUS−, SW_NODE) must maintain ≥ 6mm creepage distance to LV nets (Signal, Power, GND) on every copper layer. This is the same IEC 60335-1 rule the placement already enforces for component separation.

Gate: `kicad-cli pcb drc` reports 0 creepage violations at the 6mm threshold. The oracle computes creepage on the actual copper geometry (not bounds boxes — territory, not map).

## Key Decisions

- **Physics-oracle integration, not a new DRC tool.** The existing physics oracle (`physics/thermal_potential.py`, `physics/loop_inductance.py`) already computes these metrics from geometry. The work is integrating it as a routing gate that feeds back into the place→route loop.
- **Territory gates, not model gates.** Creepage is measured on actual copper (kicad-cli DRC), not on bounds boxes. Thermal margin is measured on the actual via count and pour area, not on a simplified thermal model. The Chebyshev encoding lesson applies here: verify on the territory.
- **Loop area is a routing constraint, not a placement constraint.** Placement can set up the loop components (Q1, Q2, C_BUS1, C_BUS2) but routing determines the actual polygon area. The feedback loop tightens routing, not placement.

## Scope Boundaries

- Full thermal simulation (FEA) is out of scope — the via-count and pour-area gates are conservative proxies.
- EMI compliance testing is out of scope — the loop area ceiling is a design rule, not a certification.
- Per-layer creepage derating for internal layers (IEC 60664-1) is deferred to follow-up — apply the full 6mm on all layers.

## Dependencies

- **W0 (router build unblock).**
- **W1 (single-layer route).**
- **W2 (4-layer stackup).** The thermal pour on B.Cu and the plane layers for return paths require the stackup.

## Success Criteria

1. Commutation-loop area ≤ 2000 mm² on the routed board
2. Gate-drive loop areas ≤ 500 mm², trace-to-return spacing ≤ 2mm
3. Thermal via count ≥ 9 under each IGBT, B.Cu pour ≥ device footprint
4. Copper creepage ≥ 6mm between all HV/LV net pairs on all layers
5. All four gates integrated into the place→route loop (W5) as red-on-regression

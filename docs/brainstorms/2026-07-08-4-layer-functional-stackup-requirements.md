---
date: "2026-07-08"
topic: 4-layer-functional-stackup
status: requirements
tier: standard-feature
---

# 4-Layer Functional Stackup — Signal, Ground Plane, Power Plane, Signal

## Summary

Define a 4-layer PCB stackup (F.Cu signal / In1.Cu GND plane / In2.Cu PWR plane / B.Cu signal), assign nets to layers by function, compute IPC-2152 trace widths from per-net current, pour power planes, define via strategy, and route USB differential pair with controlled impedance. Gate: current-density check passes; no reference-plane split under any signal net; diff-pair skew/impedance within tolerance.

## Problem Frame

The temper board has 4 copper layers (F.Cu, In1.Cu, In2.Cu, B.Cu) but the router currently treats them as interchangeable. A human designer would: (1) assign high-current nets (DC_BUS+, AC_L) to wide traces on outer layers, (2) use inner layers as solid GND and PWR reference planes, (3) route the USB diff-pair with controlled impedance on F.Cu, (4) place thermal vias under Q1/Q2 to connect to a bottom-side heatsink pour. None of this is encoded as routing constraints.

## Requirements

### R1 — Stackup definition

Define the physical stackup: layer ordering, copper weight, dielectric thickness, prepreg type. This determines characteristic impedance for controlled-impedance traces and IPC-2152 current-carrying capacity.

Gate: stackup specification matches a JLCPCB 4-layer standard offering (e.g. JLC7628). Layer assignment is deterministic and documented.

### R2 — Net-to-layer assignment

Assign nets to layers by function:
- F.Cu: signal + high-current power (DC_BUS+, AC_L, AC_N, SW_NODE) + USB diff-pair
- In1.Cu: GND reference plane (solid pour, no signal traces crossing splits)
- In2.Cu: PWR reference plane (solid pour for +3V3, +5V, +15V regions)
- B.Cu: signal + gate drive + thermal pour under Q1/Q2

Gate: every net has exactly one assigned layer. No signal net crosses a reference-plane split.

### R3 — IPC-2152 trace widths

Compute minimum trace width for each net based on its expected current. Use the IPC-2152 standard (with derating for internal layers). High-current nets (DC_BUS+ at 16A peak) require wide traces or copper pours.

Gate: current-density check passes — every trace width ≥ IPC-2152 minimum for its net's current and layer.

### R4 — Power plane pours

Pour solid copper regions on the power plane layer for each power domain (+3V3, +5V, +15V). Connect power pins to their respective pours with thermal relief vias.

Gate: every power net has a continuous copper region on the power plane. No power pin is connected only by a thin trace.

### R5 — Via strategy

Define via types: signal via (0.6/0.3mm), power via (1.0/0.5mm), thermal via array (2×2 or 3×3 grid under Q1/Q2), stitching vias along plane edges. Assign vias by net class from the SSOT.

Gate: no via violates annular ring DRC. Thermal via arrays exist under Q1 and Q2.

### R6 — USB differential pair

Route the USB D+/D- pair with controlled impedance (90Ω differential). Match lengths within tolerance. Route on F.Cu with a solid GND reference on In1.Cu.

Gate: diff-pair length skew ≤ 0.5mm. Trace width/spacing produces 90Ω ±10% differential impedance per the stackup calculator.

## Key Decisions

- **JLCPCB JLC7628 stackup.** Standard 4-layer offering: 1.6mm total, 0.2mm prepreg between outer and inner layers, 1.1mm core between inner layers. Outer copper 1oz (35µm), inner copper 0.5oz (17µm). This gives deterministic impedance calculations.
- **GND plane on In1.Cu, PWR on In2.Cu.** This is the "signal-GND-PWR-signal" stackup. GND adjacent to the primary signal layer (F.Cu) gives the best signal integrity for the USB diff-pair and high-speed SPI.
- **Net-to-layer assignment derived from netclass SSOT.** The `netclass_rules.yaml` already carries `safety_category`, `voltage_v`, and `trace_width`. Layer assignment extends this schema.

## Scope Boundaries

- Octilinear/45° routing is out of scope (W4).
- Physics-as-constraints (loop inductance, creepage on copper) is out of scope (W3 — separate workstream, builds on the stackup).
- Aesthetic routing (track spread, corridor consolidation) is out of scope (W4).

## Dependencies

- **W0 (router build unblock).**
- **W1 (single-layer route).** Must prove the router works on one layer before adding three more.

## Success Criteria

1. 4-layer stackup documented and matched to JLCPCB JLC7628
2. Every net has a deterministic layer assignment from netclass SSOT
3. IPC-2152 current-density check passes for all nets
4. No reference-plane split under any signal net
5. USB diff-pair skew ≤ 0.5mm, impedance within 90Ω ±10%
6. Thermal via arrays exist under Q1 and Q2

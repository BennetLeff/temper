---
title: "Zone/Pour Connectivity for Power/Ground/HV Nets (R10 follow-on)"
type: feat
status: active
date: 2026-07-20
origin: docs/brainstorms/2026-07-20-router-tree-executor-resilience-and-zone-policy-requirements.md
---

# Zone/Pour Connectivity for Power/Ground/HV Nets

## Summary

Tree-executor resilience (plan 2026-07-20-001 U1-U5-U7) fixed solitary-edge
failure but did not close the 54-net gap measured on the production board.
All 54 failing nets exhibit "no legal tree edge" caused by grid congestion
on power/ground/HV nets with many pads — not single-edge failure.

The router currently has no zone/pour primitive.  A zone (filled copper
polygon overlapping pad shapes) is the correct RF/thermal/current-capacity
solution for these nets.  This plan adds a minimal zone-emission capability
gated behind an explicit feature flag, using the existing netclass SSOT
to determine which nets get zones.

## Evidence

Post-U2-U7 measurement on `pcb/temper.kicad_pcb` (kicad-cli 10.0.4):
- 54/95 nets fail with "no legal tree edge"
- All are power (PWR_RTN 88p, +3V3 40p, +15V 11p, vcc 13p),
  ground (DC_BUS_RTN 11p), HV (+340V_BUS 11p), or near-net
  interconnects with >3 pads
- U2 resilience fix showed zero improvement — failure mode is
  grid congestion, not solitary-edge failure
- Default-off path (U4 stitch/plane-MST deleted): 260 unconnected
  (worse than the 149 baseline that included the fabrications)

## Requirements

- R1. A zone/pour primitive exists that emits filled copper geometry
  into the KiCad PCB output, overlapping declared pad shapes.
- R2. Zone assignment is driven by the existing netclass SSOT
  (`TEMPER_NET_ASSIGNMENTS` → `required_layer`) — not hardcoded
  net-name heuristics.
- R3. Zone emission is gated behind an explicit feature flag
  (`enable_zone_pours=False`) — no production behavior change
  without measured evidence.
- R4. Zone-poured nets are counted as `PLANE_CONNECTED` disposition
  only when KiCad DRC confirms zero unconnected items for those nets.
- R5. The existing tree executor continues to handle non-zone nets;
  zone emission is additive, not a replacement.

## Implementation Units

### U1. Zone geometry primitive — filled polygon emission

**Goal:** Add a `(zone ...)` or `(filled_polygon ...)` emission primitive
to the KiCad PCB writer that covers a net's pads with filled copper.

**Files:**
- Create: `packages/temper-placer/src/temper_placer/router_v6/zone_emission.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/adapter.py`
  (`_write_routes_to_content`)

**Approach:**
- For each net assigned to zone/pour in the netclass SSOT, generate a
  convex hull (or bounding polygon) covering all of the net's pad centers,
  expanded by a margin to ensure pad-copper overlap.
- Emit as a KiCad `(zone ...)` s-expression with the correct net number,
  layer assignment, and fill parameters.
- Start with the simplest valid shape (axis-aligned bounding box expanded
  by pad radius) and iterate toward convex hull if needed.

**Test scenarios:**
- A 3-pad net with zone emission produces a `(zone ...)` entry in the
  PCB content.
- The zone's net number matches the net declaration.
- The zone is on the netclass-assigned layer.

### U2. Netclass-driven zone assignment

**Goal:** Use `TEMPER_NET_ASSIGNMENTS` and `required_layer` to determine
which nets get zone/pour treatment.

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`

**Approach:**
- Add `enable_zone_pours: bool = False` to `RouterV6Pipeline`.
- When enabled, consult `design_rules.net_classes` for each net's
  `required_layer` and `zone_strategy` (new optional field).
- Pass zone-eligible net names to the zone emission module.

### U3. Measurement — re-run DRC with zones enabled

**Goal:** Same pattern as U8 (via-aware) and U5 (tree-executor):
run KiCad DRC with zones enabled and record unconnected_items.

**Dependencies:** U1, U2

**Verification:** production unconnected_items < 149 with zones.
The 54-net gap should close almost entirely — power/ground/HV nets
are the primary consumers of zone/pour connectivity.

### U4. Promotion — enable zone pours by default

**Goal:** Once U3 measures below the 149 baseline, flip
`enable_zone_pours=True` and update the production routing gate.

## Scope Boundaries

- Multi-layer zone pours (e.g., pours on both F.Cu and B.Cu) — deferred.
  Start with pours on the netclass-assigned layer only.
- Thermal relief patterns — deferred.
- Zone keepout / clearance optimization — deferred.
- Full copper pour polygon intersection with pad shapes — deferred.
  Start with bounding-box emission; KiCad DRC validates connectivity.

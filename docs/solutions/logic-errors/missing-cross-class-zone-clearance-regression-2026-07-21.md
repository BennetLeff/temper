---
title: "Zone emission missing cross-class clearance, zone priority, and localized hull — fix for DRC shorting_items regression when filled with pcbnew.ZONE_FILLER"
date: "2026-07-21"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "`pcbnew.ZONE_FILLER` fill caused shorting_items to rise from mean 76.7 (zones off) to 84.9 (zones on) — a +10.7% DRC regression on the production board"
  - "A 0.25mm-clearance Power-class zone could legally abut a 6.0mm-clearance HighVoltage-class zone boundary — no cross-class clearance was enforced during zone emission"
  - "Emitted `(zone ...)` s-expressions carried no `(priority N)` field, making `ZONE_FILLER` fill ordering non-deterministic for overlapping zones with no class-ranked priority"
  - "Axis-aligned bounding boxes over all of a net's pad positions produced zones spanning 58-96% of the board for distributed nets (power/ground/HV rails)"
root_cause: config_error
resolution_type: code_fix
tags:
  - zone-emission
  - cross-class-clearance
  - netclass-clearance
  - class-pairs
  - zone-priority
  - convex-hull
  - drc
  - kicad
related_components:
  - temper_placer.router_v6.adapter
  - temper_placer.router_v6.zone_emission
---
# Zone emission missing cross-class clearance, zone priority, and localized hull

## Problem

Filling router_v6's emitted zone s-expressions with real copper via `pcbnew.ZONE_FILLER` caused a ~11% increase in `shorting_items` on the production board (mean 76.7 zones-off vs 84.9 zones-on). Three independent root causes combined: zones had no cross-class pairwise clearance enforcement, no deterministic fill-ordering priority, and axis-aligned bounding boxes spanning up to 96% of the board maximized conflict surface with every piece of copper.

Diagnosis documented in `docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md`.

## Symptoms

- **Measurable regression:** multi-sample measurement (4 seeds × 3 DRC runs each, deterministic routing) showed `shorting_items` mean rose from 76.7 (zones off) to 84.9 (zones on, filled) — the zones-on floor (83) and zones-off ceiling (81) barely overlapped.
- **Silent cross-class gap:** `_zone_params_for_net` checked only a zone's own netclass clearance. A 0.25mm Power-class vcc zone could legally sit directly against a 6.0mm HighVoltage +340V_BUS zone boundary — despite `class_pairs` overrides already being consumed by CP-SAT placement (`netclass_constraints.py:106-119`).
- **Oversized footprints:** axis-aligned bounding boxes spanning all pad positions per net produced zones covering 58–96% of the board for distributed nets (+340V_BUS 96%, DC_BUS_RTN 93%, SW_NODE 82%, PWR_RTN 78%, +15V 69%, +3V3 58%).
- **No zone priority:** KiCad `(priority N)` was absent from emitted s-expressions; `ZONE_FILLER` resolved overlapping zones arbitrarily between runs.
- **0 of 85 shorting violations named a zone** in the DRC report — KiCad attributes the violation to the other-net copper, making the zone's involvement invisible to description-text grep alone.

## What Didn't Work

- **Margin-to-clearance fix:** bounding zone margin from `trace_width * 10.0` to `max(trace_width, clearance)` was a principled improvement on its own merits but had zero effect on the shorting regression (0 of 85 violations involved a zone at all — all were track-vs-track or track-vs-pad pairs between ordinary signal/power nets).

- **The `result.pcb.design_rules` decoy trap:** `result.pcb.design_rules` is an instance of `stage0_data.DesignRules` (parsed from the `.kicad_pcb` file's `net_class` blocks) — a different, unrelated class with no `class_pairs` concept. Using this object would silently no-op the entire cross-class clearance fix because `getattr(design_rules, 'class_pairs', {})` would return `{}` for every lookup. The real `DesignRules` must be threaded from `route_pcb()` into `_write_routes_to_content` via a new parameter.

- **`--refill-zones` CLI flag on CI:** KiCad 10.0.4 supports it, but CI's KiCad 8.0.9 returns `Unknown argument`. The `scripts/kicad_fill_zones.py` script using `pcbnew.ZONE_FILLER` via the system Python was built to fill zones version-independently.

## Solution

The fix applies three independent changes to the zone emission path, implemented as units U1-U3 of `docs/plans/2026-07-21-001-fix-zone-pour-shape-clearance-plan.md`, plus a multi-sample verification test (U4). All landed in PR #267.

### U1 — Cross-class pairwise clearance resolution (`adapter.py`)

Thread the real `DesignRules` object (not `result.pcb.design_rules`) through `_write_routes_to_content`. Before the zone-emission loop, gather all zone-eligible netclasses present on the board, then pre-compute an effective clearance per netclass as `max(own_clearance, class_pairs override)` against every other present class.

```python
# Before — each zone got only its own netclass clearance
margin, clearance = _zone_params_for_net(net_name)
zd = ZoneDefinition(..., clearance=clearance, ...)

# After — effective clearance resolves cross-class
eff_clearance = effective_clearance.get(nc, clearance)
zd = ZoneDefinition(..., clearance=eff_clearance, ...)
```

```python
# Pre-computation — mirrors CP-SAT's pattern exactly
class_pairs = getattr(design_rules, 'class_pairs', {})
for nc in zone_netclasses:
    own_clearance = TEMPER_NET_CLASSES[nc].clearance
    eff = own_clearance
    for other_nc in zone_netclasses:
        if other_nc == nc:
            continue
        pair_key = tuple(sorted((nc, other_nc)))
        if pair_key in class_pairs:
            eff = max(eff, class_pairs[pair_key]["clearance"])
        else:
            eff = max(eff, own_clearance, TEMPER_NET_CLASSES[other_nc].clearance)
    effective_clearance[nc] = eff
```

### U2 — KiCad-native zone priority (`zone_emission.py` + `adapter.py`)

`ZoneDefinition` gains a `priority: int = 0` field. The authoritative `dru_priority` from each `TEMPER_NET_CLASSES` entry (lower = higher real-world priority) is inverted for KiCad's higher-wins scheme: `kicad_priority = MAX_DRU_PRIORITY - dru_priority`. Result: ACMains (dru=10) → KiCad 80, HighCurrent (dru=90) → KiCad 0.

```python
# ZoneDefinition dataclass
@dataclass(frozen=True)
class ZoneDefinition:
    ...
    priority: int = 0

# In emit_zone_s_expr — positioned between (hatch ...) and (connect_pads ...)
(hatch full 0.5)
(priority 80)
(connect_pads yes (clearance 6.0000))
```

### U3 — Localized pour shape via clustered convex hull (`zone_emission.py`)

Replace the axis-aligned bounding box with `shapely.geometry.MultiPoint(cluster).convex_hull`, buffered by the margin. Greedy distance-threshold clustering (2.5mm default) groups spatially-close pads; each cluster gets one hull, producing one `ZoneDefinition` per cluster instead of one board-spanning rectangle. 

**Continuity exemption:** GND, ACMains, and HighVoltage-class nets receive `cluster_distance=None` — a single hull over all pads — to avoid fragmenting return/ground planes crucial for EMI/loop-area control. Clustering only applies where fragmentation is electrically acceptable (Power, Signal, GateDrive rails).

### U4 — Multi-sample DRC verification (`test_zone_pour_shape_clearance_measurement.py`)

Standalone measurement test (not a CI gate) that routes 4 seeds × 3 DRC samples, compares `shorting_items`/`unconnected_items` distributions zones-on vs zones-off, and includes per-net diagnostic logging for priority-exclusion attribution. Reuses helpers from `test_zone_pour_production_measurement.py`.

## Why This Works

**Cross-class clearance** ensures zones respect each other's safety boundaries — a 6.0mm HighVoltage zone now stands off from a 0.25mm Power zone by the `class_pairs` override distance, not the weaker of the two. The `class_pairs` data already existed in `DesignRules` and was consumed by CP-SAT placement; this fix extends the same single source of truth into the zone emission path.

**Priority emission** makes fill ordering deterministic: higher-priority zones (e.g., ACMains at KiCad priority 80) are filled first, and lower-priority zones fill around them — replacing arbitrary `ZONE_FILLER` tie-breaking with class-ranked, reproducible ordering.

**Localized hulls** reduce conflict surface by decomposing distributed-net zones into per-cluster polygons instead of one board-spanning box. A net like +3V3 with pads concentrated in two regions gets two small hulls rather than one that bridges the gap between them.

**Together**, these three changes address the root cause: zones that respected no cross-class safety rules, had no deterministic priority ordering, and were geometrically oversized to the point of touching everything on the board.

## Prevention

- **SSOT consumption, not parallel lookups:** the `class_pairs` data existed and was consumed by CP-SAT placement. Extending `DesignRules` consumption into zone emission eliminated a second, incomplete rules table. Future zone/route features must consume the same `DesignRules` instance rather than building parallel per-netclass lookups.

- **Guard against silent name collisions:** `result.pcb.design_rules` (an unrelated `stage0_data.DesignRules`) and the real `DesignRules` share the same attribute name but wholly different semantics. A dedicated parameter name or type annotation would have surfaced the mismatch at the call site. Review any new `design_rules` access sites for this trap — the `getattr(..., 'class_pairs', {})` pattern silently returns `{}` when pointed at the wrong object.

- **Integration tests for post-fill DRC:** the multi-sample verification test (`test_zone_pour_shape_clearance_measurement.py`) provides reproducible before/after evidence for future promotion decisions. A regression of this kind, behind a default-off flag, would have been caught before release if a similar measurement existed during the original zone/pour feature work.

## Related

- `docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md` — the diagnosis doc this fix addresses
- `docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md` — the `class_pairs` SSOT pattern this fix extends to zone emission
- `docs/plans/2026-07-21-001-fix-zone-pour-shape-clearance-plan.md` — implementation plan (4 units)
- PR #267 (`fix/zone-pour-shape-clearance`) — the fix
- PR #264 — router nondeterminism fix that enabled reliable multi-sample measurement

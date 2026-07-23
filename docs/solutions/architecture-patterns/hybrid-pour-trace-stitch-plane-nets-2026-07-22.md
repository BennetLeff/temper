---
title: "Hybrid pour + trace-stitch pattern for high-fanout plane-style nets — data-informed clustering, cross-class clearance, geometric connectivity verification"
date: "2026-07-22"
category: architecture-patterns
module: temper_placer.router_v6
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - >-
    high-fanout plane-style nets (power, ground, HV rails) fail to complete
    via tree executor alone — pads are too many (40+) and too widely distributed
    (10-110mm inter-pad spacing) for point-to-point A* to close within
    iteration caps
  - >-
    a single-mechanism approach (board-spanning bounding box, fixed-distance
    clustering, pour-only without stitch) has been attempted and failed —
    the hybrid is the escalation path, not the starting point
  - >-
    cross-net-class clearance matters (HV/LV separation, power-vs-signal
    creepage) — the pour must respect class_pairs SSOT, not just its own
    net class clearance
  - >-
    connectivity verification needs to be geometric (shapely union-find over
    pad/track/via/zone touch predicates), not bookkeeping — a net is ROUTED
    only when every pad is in one connected copper structure
tags:
  - temper-placer
  - router-v6
  - zone-pour
  - hybrid-pour
  - trace-stitch
  - data-informed-clustering
  - cross-class-clearance
  - connectivity-verification
  - plane-nets
  - scipy-hierarchical-linkage
  - kicad
---
# Hybrid pour + trace-stitch pattern for high-fanout plane-style nets

## Context

Six high-fanout plane-style nets (`PWR_RTN` 88 pads, `+3V3`, `vcc`, `+15V`, `+340V_BUS`, `DC_BUS_RTN`) failed to complete via the tree executor even with resilience and correct multi-layer routing. Three prior single-mechanism approaches were tried and each failed for a different reason:

1. **Board-spanning bounding box** (still on `main`, flag-gated): `_bounding_box` produced an axis-aligned rectangle over ALL pad positions. Distributed nets got zones covering 58-96% of the board (+340V_BUS 96%, DC_BUS_RTN 93%, PWR_RTN 78%, +3V3 58%), maximizing conflict surface and causing a `shorting_items` regression when filled with real copper via `pcbnew.ZONE_FILLER`.

2. **Fixed-threshold clustering** (PR #267, closed): A single global 2.5mm distance threshold applied uniformly. On the production board, real inter-pad spacing ranges from ~0.6mm (adjacent pins on one component) to 70-111mm (median across scattered components). `+3V3`'s 40 pads were fragmented into 38 near-singleton clusters — the opposite of the intended effect.

3. **Cross-class clearance + priority** (PR #267): The clearance/priority mechanism was verified correct but was tied to the failing clustering. PR #270 re-creates the correct mechanism and replaces the clustering entirely.

## Guidance

The pattern is a four-layer hybrid composition rather than a single mechanism:

### Layer 1 — Data-informed per-net clustering (U1)

Use `scipy.cluster.hierarchy.linkage` + `fcluster` with a threshold derived from each net's own nearest-neighbour distance distribution. Find the largest relative gap in sorted NN distances (`gap / nn_dists[i]`). When no natural gap exists (all pads component-adjacent: `max_gap_ratio < 1.0`), fall back to the 95th percentile NN distance, resulting in one large cluster rather than fragmenting a dense group.

```python
# zone_emission.py — derive threshold from that net's own NN distances
for i, (xi, yi) in enumerate(positions):
    best = float("inf")
    for j, (xj, yj) in enumerate(positions):
        if j == i: continue
        d2 = (xj - xi) ** 2 + (yj - yi) ** 2
        if d2 < best: best = d2
    nn_dists.append(best ** 0.5)

nn_dists.sort()
max_gap_ratio = 0.0
for i in range(len(nn_dists) - 1):
    gap = nn_dists[i + 1] - nn_dists[i]
    ratio = gap / nn_dists[i]
    if ratio > max_gap_ratio:
        max_gap_ratio = ratio
        threshold = (nn_dists[i] + nn_dists[i + 1]) / 2.0

if max_gap_ratio < 1.0 or threshold < 0.5:
    idx = min(len(nn_dists) - 1, int(len(nn_dists) * 0.95))
    threshold = max(10.0, nn_dists[idx]) if nn_dists else 10.0

from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist
Z = linkage(pdist(positions), method="ward")
labels = fcluster(Z, t=threshold, criterion="distance")
```

### Layer 2 — Cross-class clearance + KiCad zone priority (U2)

Thread the real `DesignRules` object (not `result.pcb.design_rules`, which is an unrelated `stage0_data.DesignRules` decoy with no `class_pairs` concept) into `_write_routes_to_content`. Resolve effective clearance using the `class_pairs` SSOT already consumed by CP-SAT placement.

```python
# adapter.py — guard against both missing attr and None value
class_pairs = getattr(design_rules, 'class_pairs', {}) or {}

for nc in zone_netclasses:
    eff = own_clearance
    for other_nc in zone_netclasses:
        if other_nc == nc:
            continue
        pair_key = tuple(sorted((nc, other_nc)))
        if pair_key in class_pairs:
            eff = max(eff, class_pairs[pair_key].get("clearance", eff))
        else:
            eff = max(eff, own_clearance, TEMPER_NET_CLASSES[other_nc].clearance)
    effective_clearance[nc] = eff
```

Invert `TEMPER_NET_CLASSES.dru_priority` (lower = higher real-world priority) into KiCad's higher-wins zone priority scheme (`_MAX_DRU_PRIORITY - dru_priority`). Result: ACMains (dru=10) → KiCad 80, HighCurrent (dru=90) → KiCad 0.

### Layer 3 — Trace-stitching isolated pads (U3)

After zones are emitted, identify pads outside all pour polygons via shapely `contains`/`touches`, find the nearest pour boundary vertex via `scipy.spatial.cKDTree`, and emit straight-line trace segments. Reuse zone polygons from the emission loop rather than re-clustering independently.

```python
# adapter.py:_stitch_isolated_pads
from scipy.spatial import cKDTree
from shapely.geometry import Point as ShapelyPoint, Polygon

pour_polys = [Polygon(pts) for pts in zone_points.get(net_name, []) if len(pts) >= 3]
outside = [(x, y) for x, y in positions
           if not any(p.contains(ShapelyPoint(x, y)) or p.touches(ShapelyPoint(x, y))
                      for p in pour_polys)]
all_verts = [(float(x), float(y)) for poly in pour_polys
             for x, y in poly.exterior.coords]
tree = cKDTree(all_verts)
trace_layer = _zone_layers_for_net(net_name)[0]  # resolved, not hardcoded

for px, py in outside:
    _dist, idx = tree.query((px, py))
    # emit (segment ...) from pad to nearest pour boundary vertex
```

### Layer 4 — Zone-aware connectivity verification (U4+U5)

Extend the existing pad/track/via union-find in `connectivity.py` with `CopperZone` dataclass and touch predicates. Wire `verify_net_connectivity` into the production pipeline behind `enable_connectivity_verifier` (default off).

```python
# connectivity.py — zone-aware union-find predicates
@dataclass(frozen=True)
class CopperZone:
    polygon: ShapelyPolygon
    layer: int
    net: str = ""

def _zone_touches_pad(zone: CopperZone, pad: CopperPad) -> bool:
    if zone.layer not in pad.layers: return False
    pt = ShapelyPoint(pad.center.x, pad.center.y)
    return zone.polygon.contains(pt) or zone.polygon.touches(pt)

def _zone_touches_track(zone: CopperZone, track: CopperTrack) -> bool:
    if zone.layer != track.layer: return False
    seg = ShapelyLineString([(track.start.x, track.start.y),
                             (track.end.x, track.end.y)])
    return zone.polygon.intersects(seg)
```

### Emerging design principles

- **Data-informed thresholds, not fixed constants.** The distance that fragments one net's dense cluster may be appropriate for another net's scattered pads. Derive per-net.
- **Continuity exemption for EMI-critical nets.** GND/ACMains/HighVoltage-class nets are exempted from clustering (one hull over all pads) to preserve ground-plane continuity.
- **Decoy-trap guard.** Always use `getattr(design_rules, 'class_pairs', {}) or {}`. Never assume `result.pcb.design_rules` has `class_pairs` — it's a different, unrelated class.
- **Flag-gating.** All three new flags default off. Promotion is gated on multi-sample DRC measurement, not code-complete.
- **Duplicate-work elimination.** The stitch function reuses zone polygons from the emission loop — discovered during code review as a duplicate O(n²) clustering antipattern that was producing different pour polygons than the emission loop itself.

## Why This Matters

Three single-mechanism attempts failed because the right shape for one net class destroys another. A bounding box works for GND (EMI plane) but drowns signal nets in conflict surface. Fixed-threshold clustering works for scattered pads but fragments dense clusters into near-singletons. The hybrid is not a "cleverer algorithm" — it is a composition of different mechanisms for different net profiles.

The `class_pairs` data already existed in `DesignRules` and was consumed by CP-SAT placement — but the zone emission path built its own incomplete per-netclass lookup in parallel, silently producing weaker clearances. Extending the same SSOT into zone emission eliminates a duplicate rules table and the `stage0_data.DesignRules` decoy trap.

The `CopperZone` touch predicates close a verification gap: before U4+U5, `verify_net_connectivity` was never called in production, so net disposition fell back to raw path-count bookkeeping. A net reported `ROUTED` via hybrid pour+stitch is now verifiably, geometrically connected — not inferred.

## When to Apply

- **When zone-pour nets have heterogeneous pad distributions.** If some nets have dense clusters (adjacent pins on one component, 0.6-2.5mm spacing) and others are scattered across the board (50-110mm median spacing), a uniform algorithm will fail for at least one profile.
- **When consuming `class_pairs` in a new code path that could be reached via `result.pcb.design_rules`.** Explicitly thread the real `DesignRules` as a parameter and guard with `getattr(...).or {}`. The silent failure mode is a correct-appearing `{}` fallback.
- **When adding geometrically-aware connectivity verification to a union-find over emitted copper.** Follow the existing predicate-per-pair-type pattern rather than special-casing zone logic. Gate production wiring behind a default-off flag.
- **When measuring routing quality to gate a promotion decision.** Use multi-sample methodology (4+ seeds × 3+ DRC samples per board) with real `pcbnew.ZONE_FILLER`. Single-sample comparisons are indistinguishable from noise in this codebase.

## Examples

See the code snippets in each layer above.

## Related

- `docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md` — implementation plan (6 units)
- `docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md` — diagnosis of the bounding-box regression this pattern replaces
- `docs/solutions/logic-errors/missing-cross-class-zone-clearance-regression-2026-07-21.md` — prior-art clearance/priority mechanism and decoy-trap warning
- `docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md` — the `class_pairs` SSOT pattern extended by U2+U5
- `docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md` — the stub-fix that exposed the PWR_RTN/+3V3 gap PR #270 targets
- `docs/solutions/architecture-patterns/router-v6-all-pad-connectivity-verification-2026-07-19.md` — the connectivity verifier infrastructure PR #270 extends (U4+U5)
- PR #270 — the implementation this document describes

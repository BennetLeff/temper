---
title: "Zone/pour bounding-box shapes span most of the board — real fill causes a shorting_items regression"
date: "2026-07-21"
category: architecture-patterns
module: temper_placer
problem_type: logic_error
severity: high
symptoms:
  - "PR #263 measured shorting_items rising 58 -> 83 once router_v6's emitted zones were actually filled with real copper via pcbnew.ZONE_FILLER (kicad-cli's --refill-zones DRC flag doesn't exist in CI's KiCad 8.0.9, so plain DRC on an unfilled zone outline reports zero copper there regardless of any (fill yes ...) declaration)"
  - "Bounding margin by clearance instead of trace_width * 10.0 (a real, principled improvement on its own merits) had zero measurable effect on the shorting regression"
  - "0 of 85 shorting_items violations on the production board named a zone as either shorting item -- all were ordinary Pad-vs-Pad, Pad-vs-Track, or Track-vs-Track pairs, which made the zone's involvement look absent from the DRC evidence at first"
  - "Multi-sample measurement (deterministic routing + 3x DRC per board to average out kicad-cli's own +-2-3 violation run-to-run noise) confirmed the effect is real: shorting_items mean 76.7 (zones off) vs 68.6 (zones on, unfilled outline) vs 84.9 (zones on, pcbnew-filled) -- filled-zone floor (83) and zones-off ceiling (81) barely overlap"
root_cause: "compute_zone_for_net's _bounding_box (zone_emission.py) computes a simple axis-aligned rectangle spanning the full extent of a net's pad positions plus margin, not a polygon local to where that net's copper actually is. For any net with pads distributed across most of the board -- which is definitionally true of power/ground/HV rails on a real product board -- the resulting zone covers a huge fraction of total board area (measured: +340V_BUS 96%, DC_BUS_RTN 93%, SW_NODE 82%, PWR_RTN 78%, +15V 69%, +3V3 58%). With 8 net classes each producing such an oversized zone (x2 copper layers), these zones extensively overlap each other and nearly every routed track/pad on the board. The zone's own declared clearance (_zone_params_for_net, e.g. 0.25mm for Power-class vcc) is only checked against ITS OWN net class -- there is no cross-class clearance check analogous to the class_pairs SSOT already used by CP-SAT placement (see docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md), so a 0.25mm-clearance zone can sit directly against a 6mm-clearance zone's boundary with no enforcement."
resolution_type: document_and_scoped_fix
tags:
  - temper-placer
  - router-v6
  - zone-pour
  - drc
  - shorting-items
  - netclass-clearance
  - determinism
---

# Zone/pour bounding-box shapes span most of the board — real fill causes a shorting_items regression

## Context

PR #263 (`feat/zone-pour-u3-measurement`) built the U3 CI gate that measures
`enable_zone_pours=True` against real `kicad-cli pcb drc` output, using
`scripts/kicad_fill_zones.py` (`pcbnew.ZONE_FILLER`) to compute genuine
copper fill before DRC runs, since kicad-cli's `--refill-zones` flag doesn't
exist in CI's KiCad 8.0.9. That measurement showed a real improvement in
`unconnected_items` (238 vs the 260 no-zones baseline) but also a regression
in `shorting_items` (58 → 83). This document is the root-cause diagnosis of
that shorting_items regression, produced in a follow-up session
(2026-07-21) after fixing an unrelated router non-determinism bug that had
made the original measurement noisier than it needed to be (see
`docs/solutions/architecture-patterns/net-order-hash-determinism-2026-07-21.md`
if present, or the git history of `astar_pathfinding.py`'s `_compute_net_order`
around this date — `_compute_net_order`'s BFS traversal iterated a
`set[str]`, so its tie-breaking depended on `PYTHONHASHSEED`, making net
routing order and therefore final track geometry non-reproducible across
process runs even with a fixed `route_pcb` seed).

## Investigation Path (what didn't work, in order)

1. **Margin hypothesis (disproven).** `_zone_params_for_net`'s
   `margin = rules.trace_width * 10.0` produced 25-30mm margins for
   ACMains/HighVoltage on a ~100-150mm board. Bounding margin by the
   netclass's own `clearance` field instead (a real, principled fix, kept on
   its own merits) was tested and had **zero effect** on shorting_items —
   0 of 85 shorting violations on the production board named a zone as
   either shorting item, before or after the margin fix.
2. **Non-determinism confound.** Before drawing conclusions from the margin
   fix's before/after DRC numbers, two `route_pcb` runs differing only in
   `PYTHONHASHSEED` (same seed=42, same `enable_zone_pours=False`) produced
   different `shorting_items` sets (62 vs 69 unique net pairs, only 45
   shared). This invalidated single-sample DRC comparisons entirely — the
   noise floor was comparable to or larger than any effect being measured.
   Root cause found and fixed: `_compute_net_order`'s conflict-cluster BFS
   iterated `conflict[n]`, a `set[str]`, whose iteration order depends on
   `PYTHONHASHSEED`. Fixed by sorting the set before iterating.
3. **kicad-cli DRC's own noise.** Even after the router fix, byte-identical
   board files (verified via tstamp normalization) produced different DRC
   violation counts run to run (±2-3 violations) — `kicad-cli`'s DRC engine
   has its own irreducible measurement noise, independent of anything in
   this codebase.

With both noise sources controlled for (deterministic routing across
multiple seeds, 3x DRC samples per board), a clean multi-sample comparison
became possible.

## Clean Multi-Sample Measurement

4 seeds × 3 DRC samples each, on the production board
(`pcb/temper.kicad_pcb`), using the already-merged margin fix:

| Condition | shorting_items | unconnected_items |
|---|---|---|
| zones off | mean 76.7, range [72,81] | 260 (flat) |
| zones on, unfilled outline | mean 68.6, range [66,74] | 260 (flat — no copper yet) |
| zones on, **pcbnew-filled** (real) | mean **84.9**, range [83,86] | mean **255.0**, range [254,258] |

Filling zones with real copper buys a small `unconnected_items` win (~5
fewer, 260→255) at the cost of a much larger `shorting_items` regression
(+8.2 on average, 76.7→84.9); the ranges barely overlap (filled-zones floor
is 83, zones-off ceiling is 81), so this is a real effect, not noise.

Secondary finding: merely *enabling* zone routing (before any fill) already
changes shorting behavior on its own (68.6 vs 76.7 with zones off) — this is
the net-diversion effect (zone-eligible nets are routed differently /
excluded from ordinary A* competition), independent of zone geometry. The
filled-copper geometry itself is what then drives shorts up past baseline.

## Root Cause: Board-Spanning Zone Bounding Boxes

Track/net geometry was verified byte-identical before and after the
`pcbnew.ZONE_FILLER` fill step (all 63 routed segments matched exactly by
position, width, layer, and net across the fill boundary) — so the fill
step is not altering tracks. The only thing that changes is the zones
themselves gaining real `filled_polygon` data.

Extracting each zone's declared `(polygon (pts ...))` boundary (the shape
`compute_zone_for_net`/`_bounding_box` in `zone_emission.py` computed,
*before* `ZONE_FILLER` carves out keepouts) and measuring its footprint
against the board's ~170×260mm extent:

| Net | Clearance | Bounding box | % of board area |
|---|---|---|---|
| `+340V_BUS` | 6.0mm | 169×252mm | **96%** |
| `DC_BUS_RTN` | 6.0mm | 166×248mm | **93%** |
| `SW_NODE` | 6.0mm | 155×235mm | **82%** |
| `PWR_RTN` | 0.3mm | 148×232mm | **78%** |
| `+15V` | 0.25mm | 140×217mm | 69% |
| `+3V3` | 0.25mm | 119×218mm | 58% |
| `vcc` | 0.25mm | 91×189mm | 39% |
| `ac_n` | 6.0mm | 99×210mm | 47% |

8 net classes × 2 copper layers (F.Cu/B.Cu) = up to 16 zone instances, each
covering 6–96% of the board, extensively overlapping **each other** and
nearly every routed track/pad. `_bounding_box(positions, margin)` computes a
simple axis-aligned rectangle spanning the full extent of a net's pad
positions — for any net with pads scattered across most of the board (true
by definition for power/ground/HV rails feeding many components), the
"pour" is not a shape following that net's actual copper, it's most of the
PCB.

Spatial correlation confirms this is the mechanism, not a KiCad DRC
artifact: the "new" shorting pairs introduced by filling (comparing the
same seed's filled vs unfilled-outline DRC runs) cluster in two ways — (a)
a dense cluster of otherwise-unrelated net pairs (io0/io45/gpio35/gpio36/
sw/+15V/PWR_RTN) all newly shorting within a ~1×4mm area, located ~1.6mm
from a `SOT-23-6` footprint and ~10mm from the `ESP32-S3-WROOM-1` module,
both of which sit inside multiple board-spanning zones simultaneously; and
(b) long tracks (`GATE_HS` 74mm, `PWM_LS` 99mm) that pick up new violations
against pads far from either endpoint — consistent with a long track
passing through one or more oversized zone regions along its route.

No violation in the DRC report names a zone directly as one of the two
shorting items (`type: shorting_items` items are exclusively `Pad ...` /
`Track ...`), which is why the zone's involvement wasn't apparent from a
description-text grep alone (`"zone" in description` matched 0/85 and
0/86). The zone's presence produces the conflict; KiCad's DRC report
attributes it to whichever other-net copper ends up geometrically too close
once fill actually happens, not to the zone polygon itself.

A second, compounding factor: `_zone_params_for_net` only checks a zone's
declared clearance against **its own** net class's `TEMPER_NET_CLASSES`
entry (e.g. `vcc` → Power → 0.25mm). There is no cross-class check
analogous to `netclass_rules.yaml`'s `class_pairs` (e.g.
`HighVoltage-Signal: 6.0mm`), which CP-SAT placement already consults (see
`docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md`).
So a 0.25mm-clearance `vcc` zone can legally sit directly against a
6mm-clearance `+340V_BUS` zone's boundary — the zone-fill algorithm has no
signal that a stricter pairwise rule should apply there.

## Recommended Follow-up

Not implemented here — this document is the diagnosis. The fix is implemented
in PR #267 and documented in
`docs/solutions/logic-errors/missing-cross-class-zone-clearance-regression-2026-07-21.md`.

1. **(IMPLEMENTED)** Replace the bounding-box shape computation with a pour
   shape local to each net's actual copper (per-cluster convex hull instead
   of one box over all positions board-wide).
2. **(IMPLEMENTED)** Have zone clearance/fill consult cross-class pairwise
   rules (`class_pairs`), not just each zone's own net class — mirroring the
   pattern CP-SAT placement already uses.
3. **(PARTIAL)** Re-measure with the same multi-sample methodology
   (deterministic routing, 3x DRC per board) used here before promoting
   `enable_zone_pours` default-on. U4 verification test exists but is
   standalone/manual, not CI-wired — promotion is separately gated on the
   still-open U5 tree-executor completion work.

## Related

- `docs/plans/2026-07-20-001-fix-router-tree-executor-resilience-plan.md`
- `docs/brainstorms/2026-07-20-router-tree-executor-resilience-and-zone-policy-requirements.md`
- `docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md` — the `class_pairs` SSOT this fix should extend to
- `docs/solutions/architecture-patterns/u7-u8-w2-audit-shorting-diffpair-diagnosis-2026-07-18.md` — sibling shorting_items diagnosis (single-layer routing, different root cause)
- PR #263 (`feat/zone-pour-u3-measurement`) — original measurement
- PR #264 (`fix/router-net-order-hash-determinism`) — the routing non-determinism fix that made this clean measurement possible

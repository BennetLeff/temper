---
title: Rust Tier-3 physical via-envelope legality
date: 2026-08-26
status: measured
---

# Rust Tier-3 physical via-envelope legality

## Defect

Tier-3 Rust A* generated layer-change moves when the destination layer's
single center cell was free. Per-netclass via diameter and clearance reached
Python only after reconstruction, where `_mark_vias` stamped the result. Thus
search could accept a center-reachable via whose physical annulus or drill
collided with surrounding copper.

## Fix

Each occupancy family already represents the searching trace's half-width plus
clearance. Python now passes Rust only the additional radius required by the
via, `max(0, via_diameter/2 - trace_width/2)`, avoiding double-counting the
clearance already rasterized into the grid.

Rust maps a candidate transition into physical copper-stack order and checks
that additional disk on every available routed-signal grid spanned by the via.
The layer stack is explicit (`F.Cu < InN.Cu < B.Cu`), independent of dict order
and of the lexicographic name rank used solely for A* heap tie-breaking.

A Rust falsifier pins the former defect: two layers with only the center cell
open accept the legacy zero-extra-radius move and reject a physical-radius
move. The existing three-layer capability fixture also had to be corrected:
its one-cell apertures were not physically via-legal, and its B.Cu-to-F.Cu
through-via crossed a blocked inner layer. Widening the apertures and clearing
the spanned inner-layer disk makes the test prove a real route rather than
center-cell reachability.

The pinned Python differential remains unchanged. Calls that omit
`trace_width` retain zero-extra-radius oracle behavior; production explicitly
passes the real netclass trace width and therefore exercises the Rust-only
correctness fix. This follows the migration rule: fix Rust, retain the old
Python as a differential, do not weaken Rust to preserve unsafe parity.

## Production result at the unchanged 1M default

| metric | before | envelope-aware |
|---|---:|---:|
| fully pad-connected | 55 / 136 | 55 / 136 |
| A* declines | 70 | 70 |
| wall time | 209.7 s | 226.3 s |
| DRC errors, each of 3 samples | 425 | 425 |

Every DRC category was identical across all six samples. The unrouted-net set
was identical. The change is therefore acceptance-neutral on today's 1M route
while making via legality true by construction.

## Repeated 2M falsifier: improved, still rejected

With the bounded 2M floor applied temporarily and removed after measurement,
the fixed router again reached 58 connected nets. Runtime was 306.9 s. DRC
fell from the prior unsafe 2M run's 457 to 403, including shorting_items 29 to
15 and hole_clearance 28 to 14. The envelope check therefore removes real
invalid geometry, not merely a diagnostic label.

The 2M result is still rejected because it introduces 36 findings absent from
the 1M artifact, including one solder-mask bridge, one hole-to-hole violation,
six copper-edge findings, and recovered-net collisions with foreign pads and
vias. Inspection identifies the next defect: `_unblock_net_pads` clears the
current pad's whole access radius from occupancy, including any nearby foreign
pad. The caller restamps foreign HV creepage halos but not ordinary foreign-pad
occupancy. Rust cannot reject an obstacle erased before its search begins.

Decision: ship the envelope-aware Rust transition at the existing 1M budget.
Do not ship 2M. Next, make pad unblocking preserve or restore all foreign-pad
envelopes, then repeat the bounded experiment.

Certification-lab work remains the final project step and was not performed.

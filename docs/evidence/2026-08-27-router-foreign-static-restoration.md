---
title: Exact foreign-static restoration after pad access opening
date: 2026-08-27
status: measured
---

# Exact foreign-static restoration after pad access opening

## Defect and construction

The per-family occupancy grid stores every static obstacle as anonymous `-1`.
`_unblock_net_pads` opens the routing net's pad/via access circle by clearing
those cells, so it also erased any overlapping foreign pad, via, track, zone,
or creepage halo. The Rust A* then searched through an obstacle that no longer
existed in its input.

The existing family-halo inventory already pre-marshals the exact source
polygons and sends them to Rust's `rasterize_area_polygons_py`. It formerly
dropped zero-creepage pairs because the base grid already contained them. They
are now retained. After each access opening, the same Rust rasterization
re-stamps every foreign entry while filtering the searching net's own entries.
This restores pads, vias, tracks, and zones at the family's exact `W/2 + C`
inflation, plus pair creepage where applicable. No second geometry model was
introduced.

A unit falsifier proves a zero-creepage pad remains in the inventory, stays
open for its own net, and blocks a foreign net. The 60-test N-layer selection,
Rust differential, and decline-contract suite passes.

## Fixed 1M production measurement

| metric | before restoration | exact restoration |
|---|---:|---:|
| fully pad-connected | 55 / 136 | 53 / 136 |
| A* declines | 70 | 72 |
| wall time | 226.3 s | 232.1 s |
| DRC errors, each of 3 samples | 425 | 416 |
| clearance | 234 | 225 |

Every other DRC category was unchanged. The two-net connectivity reduction is
not accepted as evidence of a regression by itself: the former search input
had erased foreign copper, and the corrected result removes nine real
clearance findings. This is a fail-closed correction with a measured safety
improvement, not a placement or iteration-budget nudge.

## Bounded 2M follow-up remains rejected

A temporary 2M Tier-3 floor, removed immediately after measurement, reached
55/136 pad-connected in 312.8 s and reduced total DRC to 389. It is still not
promoted: copper-edge findings rose 30 to 32 and one new same-net
hole-to-hole finding appeared between two `safety.thermal-line` vias at
(137.35, 140.05). The edge findings expose a separate board-boundary C-space
gap; the duplicate vias expose reconstruction/deduplication, not insufficient
search budget.

Decision: ship exact foreign-static restoration at the existing 1M budget.
Next fix board-edge C-space and same-net via deduplication, then repeat 2M.
Certification-lab work remains the final project step and was not performed.

---
title: Rust intra-route via coordination and the final 2M budget verdict
date: 2026-08-27
status: measured
---

<!-- provenance: commit=bfa82cc315a9949848e2971b9cdeed6d0ad12819 dirty=false -->

# Rust intra-route via coordination

## Defect and construction

The production N-layer router handles a net as a chain of waypoint segments.
Each Tier-3 Rust search knew about static board holes, but not vias accepted for
earlier segments of the same route. Tier 2 likewise accepted its two endpoint
vias independently. A temporary 2M Tier-3 run exposed the consequence: two
distinct `safety.thermal-line` vias at `(137.35, 140.05)` were only 0.337 mm
apart and violated the generated DRU's unconditional 0.5 mm PTH hole-to-hole
edge gap.

The legality predicate now lives in `temper-rust-router-core`. Python passes the
route's accumulated via centers and the physical minimum center spacing: the
netclass drill diameter plus the DRU's 0.5 mm edge gap. Rust rejects a candidate
transition inside that envelope. It also validates all vias in a completed
Tier-3 path against each other before returning it, because an A* node does not
carry the search's full via history. Tier 2 calls the same Rust predicate before
publishing endpoint vias.

An identical center remains legal: it is reuse of one physical hole at a shared
waypoint, not a second hole. The existing downstream canonicalizer removes the
duplicate record. A distinct center inside the envelope always fails closed.

## Falsifiers

- Rust unit tests pin the Euclidean center-distance boundary, rejection of a
  distinct close center, acceptance at the boundary, and exact-center reuse.
- The Python acceptance test forces primary search to fail and alternate search
  to succeed, then proves Tier 2 checks its second endpoint against the first and
  publishes neither when spacing fails.
- The Rust/Python N-layer differential remains unchanged for callers that supply
  no prior vias; 42 targeted Python tests and both new Rust unit tests pass.

## Fixed 1M production measurement

The final implementation was routed from stripped copper through
`scripts/route_board.py`. The generated DRU was refreshed first and the routed
board remained beside the real `fp-lib-table` and footprint libraries. Three
independent DRC samples were identical.

| metric | accepted 1M before | coordinated 1M |
|---|---:|---:|
| fully pad-connected | 53 / 136 | 53 / 136 |
| wall time | 232.1 s | 235.6 s |
| DRC errors | 416 | 416 |
| clearance | 225 | 225 |
| copper edge | 30 | 30 |
| creepage | 95 | 95 |
| hole clearance | 26 | 26 |
| hole to hole | 0 | 0 |
| shorting items | 26 | 26 |

The change is neutral on accepted production geometry while making a distinct
too-close via pair impossible by construction.

## Final 2M follow-up remains rejected

The temporary Tier-3 floor was raised to 2M only for measurement and reverted
before this change was committed. With the final exact-reuse semantics it
reached 55/136 pad-connected in 310.9 s. Coordination cleared both structural
defects from the earlier probe: `hole_to_hole` stayed zero and copper-edge
findings stayed at 30 rather than rising to 32. But the extra routed copper was
not safe:

| metric | coordinated 1M | coordinated 2M |
|---|---:|---:|
| fully pad-connected | 53 / 136 | 55 / 136 |
| DRC errors | 416 | 425 |
| clearance | 225 | 234 |
| copper edge | 30 | 30 |
| hole clearance | 26 | 25 |
| hole to hole | 0 | 0 |
| shorting items | 26 | 27 |

Decision: ship via coordination at the existing budget. Do not promote 2M; its
remaining blocker is nine net new DRC errors in the copper it recovers, not a
via-spacing or board-edge modeling gap. Certification-lab work remains the
final project step and was not performed.

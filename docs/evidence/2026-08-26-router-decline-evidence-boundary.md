---
title: Router decline evidence survives the production result boundary
date: 2026-08-26
status: measured
---

# Router decline evidence boundary

## Problem

The production N-layer pathfinder already produced a `RoutingFailureReport`
for every declined net, including its reason, blocking nets, congestion
location, pin count, rule identifier, and domain. `route_pcb()` discarded
those reports while converting the pipeline result into its public
`RoutingResult`; `scripts/route_board.py` could therefore print only a flat
unrouted-net list. The next router change had to be guessed from aggregate
counts even though the explanation data already existed upstream.

## Change

`temper-orchestration` now extracts the real
`stage4.pathfinding_result.failure_reports` mapping at the same Rust-owned
boundary that already extracts unrouted nets, DRC reports, congestion regions,
and solved topologies. The Python adapter only wraps the returned tuples in the
existing `RoutingFailureReport` dataclass. `route_board.py` serializes the
records and prints deterministic reason and rule-ID counts.

The pinned six-field pre-migration oracle was not edited or re-pinned. Its old
fields remain differential-checked, and a separate test exercises the added
failure-evidence field with a production-shaped report.

## Production measurement

A fresh unchanged-board route used regenerated rules and 10/10 fresh
extensions:

| metric | measured |
|---|---:|
| wall time | 212.6 s |
| fully pad-connected nets | 55 / 136 |
| unrouted nets | 70 |
| failure reports preserved | 70 |
| reports with a rule ID | 70 |
| `no_path` reports | 70 |

Thus the prior 70-net aggregate is fully accounted for: no failed searched net
lost its decline record at the boundary. In this implementation the only
rule-attributed `no_path` producer is the fail-closed forced-segment refusal
(`RULE_ID_FORCED_SEGMENT_FAIL_CLOSED`), so the next router experiment belongs
at that refusal/search seam. It does not belong in another placement sweep or
in the plane-backbone one-bend fallback: those plane warnings are real, but
they do not explain the 70 Stage-4 A* decline reports.

## Validation caveat

The new boundary tests and pinned routing-result differential pass. Five other
tests in the wider adapter-marshalling file still fail on the branch's existing
via-diameter disagreement (Rust's netclass-aware 0.9/1.0 mm output versus the
pinned Python oracle's 0.6/0.8 mm values). This change does not alter that
field, and Rust was not changed to match the stale Python behavior.

Certification-lab work remains the final project step and was not performed.

---
title: Router forced-segment decline subcategories
date: 2026-08-26
status: measured
---

# Router forced-segment decline subcategories

## Question

The production result boundary now preserves 70 per-net decline reports, but
all 70 originally said only `no_path` / `forced_segment_fail_closed`. Which
actual refusal path dominates, and therefore which router seam should be
worked next?

## Contract

The router remains fail-closed. This change only replaces the ambiguous reason
string with facts already known at the refusal site:

- terminal-tree edge execution failed;
- a tree waypoint chain failed, with or without safe partial geometry;
- the legacy point-to-point path proposed a forced fallback; or
- every tier of the production N-layer cascade failed, with or without safe
  partial geometry.

The stable vocabulary and invalid-context rejection are Rust-owned in
`temper-rust-router`. Python supplies the local context and the result of the
existing `_has_safe_partial_geometry` predicate; it does not define a second
reason table. All categories retain the same
`forced_segment_fail_closed` rule ID and none permits forced copper.

`all_tiers_failed` is deliberate wording. The call site does not yet know
whether Tier 3 hit its iteration cap or exhausted its reachable frontier, so
calling it `budget_exhausted` or `no_geometric_path` would fabricate a cause.

## Production measurement

The same production command, unchanged board, regenerated DRU, and 10/10
fresh extensions produced:

| metric | before | after |
|---|---:|---:|
| wall time | 212.6 s | 212.0 s |
| fully pad-connected nets | 55 / 136 | 55 / 136 |
| decline reports | 70 | 70 |
| `forced_segment_all_tiers_failed_empty` | unavailable | 60 |
| `forced_segment_all_tiers_failed_partial` | unavailable | 10 |
| every legacy/tree context combined | unavailable | 0 |

The diagnostic split is route-neutral and accounts for every prior report.
The dominant problem occurs on the first unresolved segment: 60 nets have no
safe searched prefix at all. Ten get through at least one real segment before
a later segment fails.

## Decision

Do not spend the next router iteration on terminal-tree handling or another
placement nudge. Preserve Tier 3's Rust search termination evidence (actual
iterations and cap) through the thin Python adapter, then split the 60-net
bucket into cap-bound versus frontier-exhausted. Only the first supports a
budget/search-efficiency change; the second points to occupancy, net order, or
floorplan feasibility.

Certification-lab work remains the final project step and was not performed.

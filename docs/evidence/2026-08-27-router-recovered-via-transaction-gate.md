---
title: Rust physical-via acceptance for recovered routes
date: 2026-08-27
status: measured
---

<!-- provenance: commit=8c86b42ccbafbc164c03256aecf55e3b09b0abcb dirty=false -->

# Rust physical-via acceptance for recovered routes

## Defects and construction

The rejected 2M probe exposed two independent ways a route could be accepted
logically and become invalid when its vias were emitted physically.

First, the power-island pass checked new F.Cu-B.Cu drop vias against routed
F.Cu and B.Cu copper only. A through via also crosses In3.Cu and In4.Cu. Two
new In4.Cu routes therefore passed the signal router, then were shorted by
later +3V3 drop vias. Power-via placement now builds routed-copper obstacles
for every signal layer in the stackup capability SSOT and unions all of them.

Second, Tier 2 checked endpoint-via center spacing but not the via's physical
copper envelope. Its exact-world candidate is now passed to a Rust predicate
that checks prior-via spacing and the expanded envelope on every grid between
the two stack ranks before any route state is mutated. Tier 3 calls the same
Rust predicate, so the two tiers no longer maintain separate physical-via
models. Python remains a thin marshalling layer.

## Falsifiers

- A power-island unit test places foreign routed copper on In4.Cu and proves it
  appears in the through-via obstacle set while F.Cu remains empty.
- A Rust-boundary test blocks only an intervening In4.Cu cell and proves an
  F.Cu-B.Cu candidate is rejected, then clears it and proves acceptance.
- The Tier-2 transaction test forces its second endpoint candidate to fail and
  proves neither endpoint is published.
- 45 focused router tests passed. The only failure in the enclosing file is
  the pre-existing real-board assertion that the committed board contains no
  +3V3 copper; it already does and is unrelated to these changes.

## Controlled production-budget result

Both boards below were routed from the same stripped production board with the
same freshly rebuilt 10/10 extension set. The pre-fix board came from an
isolated worktree at `5aa19a206`; the corrected board came from `8c86b42cc`.
Three DRC samples per board were identical.

| metric | pre-fix 1M | corrected 1M | delta |
|---|---:|---:|---:|
| fully pad-connected | 53 / 136 | 50 / 136 | -3 |
| DRC errors | 416 | 318 | -98 |
| clearance | 225 | 201 | -24 |
| copper edge | 30 | 11 | -19 |
| creepage | 95 | 92 | -3 |
| hole clearance | 26 | 0 | -26 |
| shorting items | 26 | 0 | -26 |
| courtyards overlap | 4 | 4 | 0 |
| drill out of range | 10 | 10 | 0 |

The three-net reduction is accepted because the former completion depended on
physically illegal copper. Completion is not allowed to outrank zero shorts.
The connected-net set also churned rather than merely shrinking, so this is a
correctness result, not an optimizer-quality claim.

## Controlled 2M verdict

The same corrected tree was rerun with only the Tier-3 floor temporarily raised
from 1M to 2M; the source override was reverted immediately afterward.

| metric | corrected 1M | corrected 2M | delta |
|---|---:|---:|---:|
| fully pad-connected | 50 / 136 | 53 / 136 | +3 |
| DRC errors | 318 | 352 | +34 |
| clearance | 201 | 218 | +17 |
| copper edge | 11 | 28 | +17 |
| creepage | 92 | 92 | 0 |
| hole clearance | 0 | 0 | 0 |
| shorting items | 0 | 0 | 0 |

The gained set was `WDT_RESET_N`, `discharge.q_dis_drv-g`,
`safety.fault_any_or-y2`, and `y`; `fb` was lost. The physical-via gate works,
but extra search still trades 34 new DRC findings for three net connections.
Decision: keep the 1M production budget. The next router-quality step is a
whole-route acceptance objective that compares candidate DRC sets, not another
global iteration increase. Certification-lab work remains the final project
step and was not performed.

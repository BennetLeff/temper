---
title: Foreign-obstacle halos and escape-via policy falsely rejected legal router terminals
date: 2026-08-30
last_updated: 2026-08-30
category: logic-errors
module: temper_placer.router_v6
problem_type: logic_error
component: pcb_router
symptoms:
  - Legal Stage1 terminal attempts were rejected before useful search.
  - Escape-via generation added synthetic geometry when requires_escape was false.
  - Foreign-obstacle halo inflation over-constrained terminal admission.
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [router-v6, terminal-admission, escape-vias, foreign-obstacles, creepage, clearance, rust, pyo3]
---

# Foreign-obstacle halos and escape-via policy falsely rejected legal router terminals

## Problem

Router terminal admission rejected physically legal Stage1 attempts for two
independent reasons that enlarged the static obstacle scene without an
authoritative obligation. Escape-via generation ignored a dense package's
`requires_escape` decision, while foreign-obstacle configuration-space inflation
treated clearance and pair creepage as additive distances rather than simultaneous
minimum-spacing constraints.

## Symptoms

- A production-shaped U8 fixture proved that the historical escape path generated
  geometry even though the package reported `requires_escape = false`.
- The halo formula charged both clearance and pair creepage around the same foreign
  copper, creating a larger forbidden region than either rule required.
- A comparable mandatory production replay reduced terminal attempts rejected with
  reason `foreign_or_reblocked_cell` from 14 to 4, and all invalid-input attempts
  from 29 to 15 after both corrections.
- The replay did not improve the route count. Unrouted nets changed from 97 to 98,
  and the only net-result disposition change was `RTD_CS_N`, from `connected` to
  `failed/no_copper_emitted`. The comparison exposes a downstream route-quality
  regression; restoring synthetic escape geometry would require separate evidence
  that the package has a legitimate escape obligation.

The comparison used two retained, machine-local mandatory replay artifacts. Both
attempted the same 112 routes:

| measurement | before | after |
|---|---:|---:|
| `blocked_goal` invalid attempts | 15 | 11 |
| `foreign_or_reblocked_cell` invalid attempts | 14 | 4 |
| all invalid-input attempts | 29 | 15 |
| emitted segments | 346 | 336 |
| emitted vias | 139 | 139 |
| emitted zones | 157 | 157 |
| unrouted nets | 97 | 98 |

- Before: `/tmp/temper-failure-topology-aperture-lifecycle-final-20260829.json`
- After: `/tmp/temper-failure-topology-terminal-admission-mandatory-after-20260830.json`

These `/tmp` files are measurement evidence on the development host, not durable
repository artifacts.

## What Didn't Work

Adding clearance and creepage charged the same edge-to-edge separation twice. For
a 0.5 mm trace, 2.0 mm clearance, and 12.6 mm pair creepage, the correct inflation
is 12.85 mm; the additive formula produced 14.85 mm. The production-shaped
boundary test shows that this extended the tested foreign-pad halo to 31.35 mm
instead of 29.35 mm
(`packages/temper-placer/tests/router_v6/test_astar_nlayer.py`).

Changing the pinned Python oracle to match the corrected escape behavior would
also destroy useful migration evidence. The differential instead records the
intentional divergence: the historical oracle emits an escape for non-escaping
U8, while the Rust pipeline emits none
(`packages/temper-placer/tests/router_v6/test_router_pipeline_rust_differential.py`).

The implementation does not reopen every terminal after halo stamping. Its design
rationale is to correct the obstacle construction itself; a broad reopening would
need a separate falsifier proving that it preserves foreign-copper spacing.

A follow-up experiment also rejected changing the N-layer A* budget to count only
current-best frontier entries. That optimization was locally sound and recovered
one production route, but it recovered `safety.thermal-line`, not either regressed
terminal net. On the exact production regression path, `unconnected_items` stayed
at 345 and `shorting_items` rose from 15 to 17. The two new shorts were attributable
to the recovered copper:

- its F.Cu-to-In3.Cu blind via shorted pad 1 of
  `safety.thermal.comp-inp` at R59;
- its 28.3 mm In3.Cu track shorted a `+3V3` through-via.

The optimization was removed rather than allowing locally legal occupancy to
override KiCad's board-level verdict.

## Solution

Treat `requires_escape` as the admission fact for synthetic escape geometry and
check it before either dog-bone or via-in-pad generation:

```rust
if !pkg.getattr("requires_escape")?.is_truthy()? {
    continue;
}
```

Encode the physical halo rule once in the Rust router core:

```text
halo = trace_width / 2 + max(clearance, pair_creepage)
```

The core rejects negative or non-finite inputs and returns no value if the result
overflows. The PyO3 binding turns that rejection into `PyValueError`, and the
Python wrapper only marshals values to the Rust owner.

The halo builder memoizes the Rust result by pair-creepage radius for one routing
family. Width and clearance are fixed for that family, so repeated obstacles reuse
the same value without creating a second formula in Python.

Zero-creepage foreign entries remain in the halo inventory. Their ordinary
width-and-clearance polygon restores static cells that an adjacent own-pad opening
may have erased, while the stamping step still filters the searching net's own
entry.

## Why This Works

Clearance and pair creepage both constrain the minimum edge-to-edge distance
between the routed trace and the same foreign obstacle. Satisfying the larger
minimum also satisfies the smaller one, so `max(clearance, pair_creepage)` charges
the obligation exactly once. Adding them constructs a larger forbidden region
than either rule authorizes.

The same exactness applies to escape geometry. `requires_escape` already states
whether a dense package needs synthetic egress geometry. Honoring that decision
before generation keeps the occupancy graph aligned with the package's actual
routing obligation.

## Follow-up Routing Boundary

`WDT_RESET_N` and `io0` both originate at U27, but their production failures do
not prove that U27 needs the deleted synthetic vias. A target-only Stage 4 run on
the same clean board, with corrected halos, zero generated escape vias, and both
nets present together routed 2/2 successfully. This is both an isolation result
and a coexistence witness: legal geometry exists, and the two nets do not exclude
each other. Their failure in the full route is therefore an ordering/congestion
problem, not a placement impossibility and not evidence for restoring via-in-pad
geometry on the ESP32 module's castellated pads.

The production failures remain budget-shaped. `WDT_RESET_N` exhausts 500,000
iterations on U27.6 to U20.2; `io0` first completes U27.27 to R72.2, then exhausts
the same budget from R72.2 to SW2.1. Both terminals are admitted, all four signal
layers are available, and the retained failure topology finds neither a missing
layer transition nor a complete blocking cut. The next correction belongs in
negotiated congestion, with the production KiCad short and connectivity ratchets
as the acceptance authority.

Static priority was tested and rejected as the correction. These are full-board
routes from the same stripped production input, followed by the same external
KiCad DRC path; none changed the committed board:

| temporary order | target nets connected | `shorting_items` | `unconnected_items` | verdict |
|---|---:|---:|---:|---|
| corrected occupancy, unchanged order | 0/2 | 15 | 345 | regression witness |
| `WDT_RESET_N`, `io0` first | 2/2 | 15 | 343 | closest result; misses connectivity ratchet by 1 |
| six mutually-coexisting displaced/target nets first | 2/2 | 18 | 349 | rejected |
| `fb`, `WDT_RESET_N`, `io0` first | 3/3 | 10 | 349 | rejected |
| `io0`, `WDT_RESET_N` first | 2/2 | 23 | 344 | rejected |

The six-net set (`WDT_RESET_N`, `io0`, `PWM_LS`,
`discharge.k_dis1-no`, `fb`, and `safety-line-3`) routed 6/6 together on an
otherwise clean Stage 4 scene before its full-board priority run. Its full-board
failure is therefore not a pairwise coexistence impossibility. More importantly,
the permutations move unrelated connectivity and shorts non-monotonically. A
larger production-name priority list would tune one deterministic route by
coincidence instead of solving congestion. The next implementation should make a
failed net identify already-routed blockers, transactionally unstamp a bounded
set, attempt the legal route, and either reroute the displaced nets or restore the
previous occupancy exactly. The existing N-layer path reports
`attempted_ripups=0`; that missing negotiated pass is the live seam. A straight-line
intersection with routed copper is not sufficient blocker evidence: the failed A*
search may have had other legal detours or may simply have exhausted its budget.
The next implementation therefore needs counterfactual removal or a blocking-cut
certificate before it attributes a failure to a routed net and unstamps copper.

### Frontier-contact follow-up (2026-08-30)

The N-layer Rust search now reports a deterministic candidate ranking for failed
searches: positive dynamic owner IDs contacted at the explored frontier, counted
descending with owner-ID ascending as the tie-break. Static obstacles remain
excluded, and the failure report labels the result
`frontier_candidate_nets`—candidate evidence, not a causal `blocking_nets`
claim. On the production route the leading candidates were:

- `WDT_RESET_N`: `PWM_LS`, `i2c_scl_ui`, `PWM_HS`,
  `rtd_pan.high_window-out`, `safety-line-3`.
- `io0`: `PWM_HS`, `fb`, `i2c_scl_ui`, `DISCHARGE_CTRL`, `RTD_CS_N`.

Three bounded counterfactual designs were measured and removed rather than
shipped:

| experiment | target result | `shorting_items` | `unconnected_items` | finding |
|---|---:|---:|---:|---|
| remove the strongest owner, reroute both nets transactionally | 0/2 | 15 | 345 | one owner was not causal |
| remove up to five ranked owners by owner ID, then reroute all displaced nets | 1/2 | 77 | 347 | invalid instrument: clearing an overwrite-only owner cell erased older reservations beneath it |
| rebuild every family from its immutable baseline and replay accepted routes; remove up to twelve frontier/direct candidates | 0/2 | 16 | 345 | safe rollback, but neither target coexisted after 12/13 attempts |

The 77-short result exposed a structural constraint on negotiated routing: the
current occupancy grid stores one owner byte per cell, not an owner stack or
reference count. An in-place `grid[cell] = 0` inverse is therefore impossible by
construction after a later route overwrites an earlier reservation. Exact
reconstruction avoids that corruption, but the safe reconstruction experiment
still failed the production bar and was removed in full.

The first implementation of frontier-contact aggregation also counted contacts
from successful earlier waypoint segments when a later segment failed. That did
not change either target's corrected production ranking, but it made the report
claim a failed frontier had contacted owners that only the successful prefix had
seen. Aggregating contacts only after a Tier-3 segment fails keeps the diagnostic
scoped to the segment it describes. A three-waypoint regression now proves that
contacts from the successful first segment are excluded from the failed second
segment's candidates.

Four more static probes reinforced that router completion is not the board-level
objective:

| temporary order extension | target result | `shorting_items` | `unconnected_items` | finding |
|---|---:|---:|---:|---|
| cheapest one-frontier-owner candidate third | 2/2 | 15 | 343 | reported completion did not improve physical connectivity |
| one raw KiCad witness net third | 2/2 | 15 | 343 | reported completion did not improve physical connectivity |
| `PWM_LS` third | 2/2 | 12 | 345 | `PWM_LS` connected, but the physical forest lost two other connections |
| `safety-line-3` before both targets | 2/2 | 24 | 345 | the safety net connected, but shorts and connectivity both regressed |

The last two measurements are especially useful falsifiers. Promoting a newly
unconnected signal can make its own route succeed while worsening the global
forest, and a safety-first order can keep both target nets connected while
exceeding the shorting ratchet. Any future ordering change must therefore be
selected by physical connectivity and shorting outcomes, not by the count of
nets that returned a route object.

The remaining implementation seam is now narrower. Do not add owner-ID clearing
to this grid and do not expand production-name priority lists. A viable negotiated
router needs either (a) multi-owner/reference-count occupancy built into the
construction model, or (b) a connectivity-aware order selected before stamping,
then proven on the external 15-short/342-unconnected KiCad bars. Frontier contact
is useful for narrowing candidates, but budget exhaustion plus contact is not a
cut certificate.

## Prevention

- Model every physical obligation once. When rules are simultaneous lower bounds
  on the same distance, compose them with `max`, not addition.
- Keep physical arithmetic in the Rust owner. Python may transport inputs and
  cache an immutable result for one family, but it must not duplicate the formula.
- Preserve fail-closed validation across the PyO3 boundary. Invalid spacing inputs
  must raise rather than fall back to zero or a permissive halo.
- Test the numeric rule and the emitted occupancy boundary. Rust covers
  creepage-dominant, clearance-dominant, zero-creepage, negative, non-finite, and
  overflow inputs; Python checks the production-shaped max-versus-additive
  boundary and zero-creepage static restoration.
- Keep pinned migration oracles unchanged when the new owner intentionally fixes
  historical semantics. Add an explicit divergence test instead of making both
  implementations agree on the old bug.
- Evaluate routing fixes with comparable production replays. A lower invalid-input
  count can reveal a downstream route-quality regression even when the final
  routed-net count does not improve.

## Related Issues

- [Netclass clearance SSOT and consumer chain](../architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md)
  provides the broader rule-authority precedent for routing consumers.
- [Verify netclass clearance on the routing path](../conventions/verify-netclass-clearance-on-the-routing-path-2026-07-12.md)
  explains why configured spacing must be checked at its live consumer.

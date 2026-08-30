---
title: Foreign-obstacle halos and escape-via policy falsely rejected legal router terminals
date: 2026-08-30
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
  `failed/no_copper_emitted`. The comparison exposes a publication gap; restoring
  synthetic escape geometry would require separate evidence that the package has
  a legitimate escape obligation.

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
  count can reveal a downstream publication defect even when the final routed-net
  count does not improve.

## Related Issues

- [Netclass clearance SSOT and consumer chain](../architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md)
  provides the broader rule-authority precedent for routing consumers.
- [Verify netclass clearance on the routing path](../conventions/verify-netclass-clearance-on-the-routing-path-2026-07-12.md)
  explains why configured spacing must be checked at its live consumer.

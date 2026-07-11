---
title: "Share the Rust PCL IR before migrating placement and routing solvers"
date: 2026-07-11
category: architecture-patterns
module: "Rust PCL and DesignBundle boundary"
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "Placement, routing, DRC, and feedback stages consume the same authored constraints"
  - "A validated immutable input bundle must remain stable while algorithms migrate incrementally"
tags: [pcl, rust, design-bundle, cp-sat, router-v6, drc]
---

# Share the Rust PCL IR before migrating placement and routing solvers

## Context

A validated `DesignBundle` established a safe input boundary, but its
constraints were still represented separately from the existing Rust constraint
engine and Python PCL classes. Moving CP-SAT or Router V6 first would preserve
parallel models and create another opportunity for semantic drift.

## Guidance

Extract the canonical constraint representation into a dependency-light Rust
leaf crate, `packages/temper-pcl-ir`. The IR should contain the exhaustive PCL
kind enum, tier, origin, stable ID, rationale, and resolved references. Make
the DesignBundle own an immutable `ConstraintSet` of these values, and expose
the same types through the existing Rust constraint engine rather than copying
the enum.

Keep solver and DRC implementations as consumers of the IR. Do not put solver
variables, placement state, routing state, or mutable feedback results into the
IR. Feedback may be represented by a typed origin, but stage results belong in
later wrappers around the immutable bundle.

## Why This Matters

A shared IR makes constraint semantics compile-time visible to every Rust
consumer and keeps Atopile-derived safety floors distinguishable from authored
PCL rules. It also lets the project migrate consumers one at a time without
porting CP-SAT, Router V6, or DRC algorithms prematurely.

The DesignBundle remains the only construction boundary: PCL parsing and
Atopile safety derivation produce the shared IR, the strict merge occurs before
the bundle is returned, and downstream stages receive the normalized immutable
constraint set.

## When to Apply

- When a new Rust placement, routing, DRC, or feedback consumer needs PCL rules.
- Before adding a second backend for an existing PCL constraint variant.
- When a Python constraint class and Rust constraint enum begin to drift.

## Examples

The shared IR models an authored separation as a typed kind with stable
metadata rather than as a generic `{subject, metric, value}` record:

```rust
PclConstraint {
    id: "hv-lv-clearance-authored".into(),
    tier: ConstraintTier::Hard,
    origin: ConstraintOrigin::AuthoredPcl,
    kind: PclConstraintKind::Separated {
        a: "dc_bus_plus".into(),
        b: "MCU_ZONE".into(),
        min_distance_mm: 8.0,
        metric: "clearance".into(),
    },
    ..
}
```

A weaker authored value is rejected while merging with an
`AtopileDerived` floor. Identical subject/metric constraints use canonical
identity and deterministic ordering before serialization.

## Related

- `packages/temper-pcl-ir/src/lib.rs`
- `packages/temper-design-bundle/src/model.rs`
- `packages/temper-design-bundle/src/pcl.rs`
- `packages/temper-placer/temper-constraints/src/lib.rs`
- `docs/plans/2026-07-11-001-feat-atopile-pcl-rust-design-bundle-plan.md`

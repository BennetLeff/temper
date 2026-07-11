---
title: "Validated Atopile and PCL design bundle boundary"
date: 2026-07-11
category: architecture-patterns
module: "Rust design-bundle import boundary"
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "Electrical design intent and placement constraints arrive through separate import paths"
  - "A PCB pipeline must reject unresolved identity or weakened safety constraints before routing"
tags: [atopile, pcl, rust, pyo3, provenance, pcb-safety]
---

# Validated Atopile and PCL design bundle boundary

## Context

Atopile electrical and mechanical intent, KiCad identity data, and authored PCL
placement constraints were previously represented by separate parsing paths. A
missing mapping or unresolved constraint reference could therefore produce a
plausible-looking but incomplete pipeline input.

## Guidance

Introduce a versioned Rust `DesignBundle` as the boundary between source
artifacts and later placement, routing, and validation stages. Construct it
only from typed DTOs and return structured validation errors. Keep Atopile as
the source of derived safety floors and PCL as the sole authored constraint
source.

The boundary should:

- validate board geometry, canonical component/net IDs, and mapping entries;
- resolve every PCL reference before creating the bundle;
- record SHA-256 provenance for each source artifact;
- attach an origin to every normalized constraint; and
- reject an authored safety value below an Atopile-derived floor.

The implementation lives in `packages/temper-design-bundle`. The committed
Atopile export and mapping contract are under `elec/exports/`. Serialization is
normalized JSON for parity and golden tests, not a mutable pipeline context.

## Why This Matters

Failing at the import boundary is safer than allowing an optimizer or router to
interpret an empty or partially resolved constraint set. Provenance and origins
also make generated artifacts reviewable and make future migration from the
legacy Python path incremental rather than an all-at-once cutover.

## When to Apply

- Before adding a new placement, routing, or validation stage that consumes
  multiple design sources.
- When importing a new version of an Atopile export or net-name mapping.
- When merging authored rules with generated electrical safety constraints.

## Examples

An authored 4 mm clearance for a subject with an Atopile-derived 6 mm floor
must return a structured `safety_weakening` error. An authored 8 mm rule is
accepted. A mapping to a missing KiCad net returns an `unknown_mapping` error
with both the Atopile signal and expected KiCad name.

The optional PyO3 adapter exposes normalized output while keeping the Rust
bundle canonical; Python does not reconstruct constraint dictionaries between
pipeline stages.

## Related

- `docs/brainstorms/2026-07-11-atopile-pcl-rust-design-bundle-requirements.md`
- `docs/plans/2026-07-11-001-feat-atopile-pcl-rust-design-bundle-plan.md`
- `packages/temper-design-bundle/README.md`

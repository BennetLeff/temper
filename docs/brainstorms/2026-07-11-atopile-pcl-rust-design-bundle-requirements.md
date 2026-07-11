---
date: "2026-07-11"
topic: atopile-pcl-rust-design-bundle
status: requirements
tier: deep-feature
---

# Atopile + PCL → Typed Rust Design Bundle

## Summary

Create the first canonical Rust boundary for the PCB automation pipeline. It
imports Atopile-derived design artifacts, the KiCad board, and the authored PCL
YAML into one versioned, provenance-carrying `DesignBundle`. No placement,
routing, or validation stage may begin until this bundle has passed identity,
net-class, geometry, and constraint-reference validation.

Atopile remains the source of electrical and mechanical design intent; PCL
remains the single source of authored placement/routing intent. The result is a
single typed Rust representation rather than parallel Python dictionaries,
legacy `PlacementConstraints`, and unvalidated YAML.

## Problem Frame

`elec/src/constraints.ato` defines electrical safety, net class, thermal, and
mechanical intent. `docs/NET_NAME_MAPPING.md` separately maps Atopile names to
KiCad names. `configs/constraints/temper_induction_cooker.yaml` contains PCL
constraints, while the accepted PCL SSOT ADR requires PCL—not legacy YAML—to
be the canonical placement constraint format. Today these inputs are parsed by
different paths and failures can be warnings or silently empty outputs.

This is especially unsafe for an induction-cooker board: a constraint or
Atopile-to-KiCad identity that cannot be resolved must stop the run before a
solver can produce a plausible-looking unsafe layout.

## Requirements

### R1 — Canonical typed boundary

Define a Rust `DesignBundle` with versioned `BoardSpec`, `Component`, `Net`,
`NetClass`, `SafetyDomain`, `Stackup`, `ConstraintSet`, and `Provenance` types.
The public constructor accepts only validated inputs and returns
`Result<DesignBundle, DesignBundleError>`.

### R2 — Atopile importer contract

Define a versioned, machine-readable Atopile export contract. The importer must
accept the export plus the existing Atopile-to-KiCad mapping and produce typed
component, net, net-class, safety-domain, thermal, mechanical, and stackup
intent. The first milestone does not require implementing an Atopile compiler;
it requires a stable import artifact and a fixture generated from the Temper
Atopile project.

### R3 — PCL is the authored constraint SSOT

Authored PCL YAML is parsed into the Rust constraint enum. The import path must
not create a second hand-maintained constraint representation. The existing
Rust `Constraint` enum is extended only as required to represent the PCL schema
used by the Temper fixture, including stable IDs, `because`, tier, and origin.

### R4 — Explicit provenance

Every bundle records schema version and SHA-256 hashes for the Atopile export,
PCL YAML, KiCad board, and mapping file. Every imported or generated constraint
has an origin: `AtopileDerived`, `AuthoredPcl`, `DerivedValidation`, or
`RouterFeedback`.

### R5 — Hard-fail consistency checks

Bundle construction fails with structured diagnostics for unresolved or
ambiguous component/net/zone/loop references, unknown mapping entries, invalid
units or non-finite values, duplicate canonical IDs, incompatible board
geometry, and conflicting constraints. It must never downgrade these failures
to warnings or an empty constraint set.

### R6 — Constraint merge policy

Atopile-derived safety constraints and authored PCL constraints merge into one
canonical `ConstraintSet`. Identical constraints deduplicate by canonical ID.
An authored constraint may strengthen, but not weaken, an Atopile safety floor
unless a future explicit signed override mechanism is introduced. Conflicts
must identify both origins and values.

### R7 — Deterministic interchange artifact

Expose a deterministic serialized normalized bundle for Python compatibility,
golden tests, and future Rust pipeline stages. Serialization must preserve IDs,
units, origins, provenance hashes, and ordering. It must not be used as an
untyped mutable pipeline context.

### R8 — PyO3 boundary

Expose one narrow PyO3 entry point that accepts file paths or bytes, builds a
bundle, and returns either a normalized artifact or a structured error. Python
may orchestrate this milestone but must not reconstruct the bundle between
placement, routing, and validation stages.

### R9 — Verification ladder

Add Rust unit tests, `proptest` tests for identity and merge invariants, a
Temper golden fixture, and Python integration tests through the PyO3 boundary.
The fixture must prove that broken net mapping, unresolved PCL references, and
a weakening safety constraint all fail before routing starts.

## Acceptance Examples

- Given the committed Temper Atopile export, KiCad board, net-name mapping, and
  PCL YAML, bundle construction succeeds and produces deterministic output.
- Given `top.dc_bus_plus` mapped to a missing KiCad net, construction fails with
  both the Atopile signal and expected KiCad name.
- Given a PCL component/zone/loop reference not present in the canonical design
  graph, construction fails naming the PCL ID and reference.
- Given an authored 4 mm HV/LV clearance that conflicts with an Atopile-derived
  6 mm floor, construction fails; an authored 8 mm rule succeeds.
- Given the same inputs twice, serialized normalized bundles are byte-identical.
- Given the PyO3 API, the same structured errors are observable from pytest.

## Scope Boundaries

- No Atopile compiler implementation or changes to `.ato` source semantics.
- No CP-SAT, Router V6, or DRC algorithm port in this milestone.
- No legacy loader deletion in this change; the bundle is introduced beside it
  and must prove parity before it becomes the production entry point.
- No feedback-loop behavior beyond representing `RouterFeedback` as a typed
  future origin.

## Key Decisions

- Atopile is upstream design intent, not a parallel placement-constraint system.
- PCL is the sole authored constraint language.
- The Rust bundle is canonical after import; Python is an adapter/orchestrator.
- Unresolved identity and safety conflicts are fatal boundary errors.

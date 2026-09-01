---
title: "Isolation values need role-aware authority, not tier-label equality"
date: "2026-08-31"
category: architecture-patterns
module: pcb-hardware-design
problem_type: architecture_pattern
component: isolation-barrier
severity: critical
applies_when:
  - "Several clearance or creepage declarations share an insulation-tier label but serve different engineering roles."
  - "A repository-wide scanner finds numerically different safety values across generated rules, design targets, and production requirements."
  - "A bounded PCB topology campaign must consume the same safety contract as production validation."
tags:
  - isolation-authority
  - reinforced-insulation
  - clearance
  - creepage
  - rust-ssot
  - fail-closed
  - topology-identity
  - standards-review
---

# Isolation values need role-aware authority, not tier-label equality

## Context

Temper's broad declaration scanner grouped three reinforced-clearance values into one family and treated numerical equality as the consistency rule. That made a 2.0 mm generated `HighVoltage` fabrication projection conflict with two 6.0 mm HV-to-LV project/fabrication projections even though those values did not make interchangeable claims.

Blindly changing either side would have been unsafe. Raising the generated value could change routing and DRC behavior without establishing the applicable standard basis; lowering the 6.0 mm project target would silently weaken a conservative design constraint. Treating the mismatch as permanently accepted drift would preserve the ambiguity and allow future declarations to inherit the exception.

The production creepage role has a separate 12.6 mm PD3 requirement. Regional routing experiments had embedded that value as a free literal, so a safety-contract change and a topology campaign could drift independently even if each subsystem's tests stayed green.

## Guidance

Keep broad discovery and narrow adjudication separate:

1. Let the scanner continue finding candidate declarations by metric and coarse tier. Broad discovery is useful precisely because it does not need to understand every subsystem.
2. Send only a closed, exact identity set to a typed authority owner. The authority row must name the physical metric, boundary, insulation purpose, environmental basis, engineering role, source, review status, and applicable minimum relationship.
3. Require exact projection coverage. Missing, extra, renamed, duplicated, non-finite, or numerically changed declarations fail; a coincidentally unchanged distinct-value set is not enough.
4. Keep provisional provenance visible. A successful role resolution must still emit `REVIEW REQUIRED` until an attributed qualified standards review replaces the provisional source. Passing the consistency gate is not standards approval.
5. Make downstream topology logic consume the governing roles and their scoped digest from the same Rust authority. Candidate identities then become stale automatically when the board, generated inputs, declaration, or safety contract changes.

The Rust-owned contract lives in `packages/temper-design-bundle/src/isolation_authority.rs`. It exposes the three live reinforced-clearance projections without changing their values and exposes the 6.0 mm conservative project target plus the 12.6 mm PD3 production creepage role as a scoped topology authority. `scripts/check_creepage_clearance_drift.py` remains the discovery and reporting layer; it cannot manufacture a role mapping or suppress provisional review.

The regional quality oracle consumes those two roles through `packages/temper-quality-oracle/src/regional_feasibility.rs`. It retains raw clearance, creepage, and route-length measurements, attributes every safety veto to an authority key/value/source, and ranks only hard-veto survivors deterministically. The board-owning validator in `packages/temper-design-bundle/src/regional_topology.rs` separately binds topology identity, so quality scoring does not become a second board parser.

## Why This Matters

An insulation tier describes purpose, not provenance or enforcement role. A standards minimum, conservative design target, fabrication rule, and measured production requirement can legitimately differ while still forming one coherent contract. Conversely, two equal numbers can be unsafe if one is attached to the wrong metric, boundary, or environment.

Role-aware authority makes both errors observable. It permits justified differences only for registered identities, rejects unsafe movement by construction, and prevents a search campaign from continuing under stale safety assumptions. Retaining the review-required state also distinguishes repository consistency from appliance-safety approval.

## When to Apply

- When a consistency gate reports same-tier numerical drift across unlike artifacts.
- Before changing a safety value merely to make a repository-wide equality check green.
- When a generated fabrication rule, design target, and production requirement must coexist.
- Before freezing identities for a placement or routing campaign that depends on clearance or creepage.

## Examples

A role-aware row should answer questions that a bare number cannot:

```text
metric: clearance
boundary: high_voltage_to_low_voltage
role: conservative_design_target
value: 6.0 mm
applicable minimum: clearance.hv_lv.120v_ovc2.minimum
review status: current-edition review required
```

A topology candidate should bind the scoped authority digest alongside its board and declaration hashes:

```text
candidate identity = digest(
  declaration authority,
  production board,
  generated inputs,
  topology authority,
  complete route strategy,
)
```

Do not use an accepted-drift string as a substitute for this model, and do not describe a clean role-resolution result as qualified IEC approval.

## Related

- `docs/solutions/architecture-patterns/dense-creepage-repair-is-neighborhood-topology.md`
- `docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md`
- `docs/evidence/net41-route-layer-corridor-20260831/README.md`

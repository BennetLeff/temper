---
date: 2026-07-01
topic: adr-constraint-migration-governance
---

# ADR for Constraint System Migration + Pipeline Governance

## Summary

Establish MADR-format ADRs to document the dual-constraint-system problem and migration path, enforce a CI gate requiring an ADR for any DAG topology change, and build a bidirectional `@req`-tagged traceability matrix to surface orphaned decisions or undocumented code.

---

## Problem Frame

Dual constraint systems (1730-line legacy `io/config_loader.py` vs 752-line PCL `pcl/constraints.py`) coexist with no documented decision about which is canonical. Every new contributor must reverse-engineer intent from code. The silent-auto-discovery-skip bug is a direct consequence of forking the `optimize` path from `input_stage` without documenting which constraint system to use. Meanwhile, DAG topology changes — the system's most important architectural decision surface — happen with zero governance: any PR can add, remove, rename, or reorder stages without documenting why. ADRs + traceability solve the discoverability and governance problems.

---

## Actors

- A1. **Pipeline contributor**: Adds or modifies DAG stages, needs to document architectural decisions
- A2. **PR reviewer**: Reviews PRs, needs architectural decisions visible and linked from code
- A3. **New team member**: Onboards to the codebase, needs to understand which constraint system is canonical
- A4. **CI system**: Enforces ADR requirements and traceability integrity

---

## Key Flows

- **F1. DAG topology change with ADR**
  - **Trigger:** Contributor modifies DAG manifest or adds a stage
  - **Actors:** A1, A2, A4
  - **Steps:** PR includes ADR in `docs/adr/` explaining the topology change; ADR references the YAML manifest diff; CI verifies ADR exists and is linked; reviewer sees architectural intent alongside code
  - **Outcome:** Every DAG topology change has a documented, reviewable decision
  - **Covered by:** R4, R5, R6, R7

- **F2. Constraint system migration discovery**
  - **Trigger:** New team member encounters dual constraint systems
  - **Actors:** A3
  - **Steps:** Reads ADR for constraint migration; understands legacy vs PCL, which to use, and migration timeline; follows traceability matrix from ADR decision to implementing code
  - **Outcome:** New contributor knows exactly which constraint system to use without reverse-engineering
  - **Covered by:** R1, R2, R3, R8

---

## Requirements

### Constraint migration ADR

- **R1.** Write a MADR-format ADR at `docs/adr/YYYY-MM-DD-constraint-system-migration.md` documenting: current dual-system state, silent-skip bug impact, options considered, chosen migration path (PCL single-source-of-truth), sunset gates for legacy removal, and migration timeline.
- **R2.** The ADR must link to the specific code paths affected (`io/config_loader.py`, `pcl/constraints.py`, `pipeline/input_stage.py`, `pipeline/geometric_stage.py`).
- **R3.** The ADR must declare sunset conditions: legacy `PlacementConstraints` and `io/config_loader.py` will be deleted when all consumers have been ported to PCL APIs.

### DAG topology governance

- **R4.** A CI gate requires an ADR for any PR that adds, removes, renames, or reorders a Stage in the YAML pipeline manifest.
- **R5.** The ADR must reference the specific YAML manifest diff (stage name, data-key changes, dependency changes).
- **R6.** Parameter-only changes (timeout, skip_if, retry_count changes that do not modify stage name, requires, or provides fields) are exempt from the ADR requirement to avoid overhead on trivial tweaks. Renames are NOT exempt — they change the topological identity that other stages depend on.
- **R7.** The CI check verifies that the ADR exists, that it references the manifest diff, that it uses the MADR template (Context, Decision, Consequences sections), and that the Decision section contains at least 50 characters of substantive content after its heading (prevents empty-template ADRs).

### Bidirectional traceability

- **R8.** Generate a traceability matrix (as a CI artifact or checked-in file) mapping each ADR decision to its implementing code via existing `@req` annotations AND mapping each `@req` annotation back to its governing ADR.
- **R9.** CI gate ensures no orphaned ADRs (decisions with zero code evidence via `@req` tags). This check applies only to ADRs that claim code evidence by declaring a `plan-id` in their frontmatter and referencing `@req` annotations with that plan-id. ADRs that do not claim `@req` linkage (e.g., sunset timelines, format choices, process gates) are exempt from the zero-evidence check.
- **R10.** The traceability matrix is discoverable from `AGENTS.md` and `TRACEABILITY.md`.

### @req-to-ADR linkage convention

- **R11.** Every ADR that makes a decision with code evidence MUST declare a `plan-id` in its YAML frontmatter. `@req` annotations in code referencing that `plan-id` (e.g., `@req(2026-06-28-006, R03)`) are automatically linked to the ADR.
- **R12.** Existing `@req` tags referencing plan-IDs without ADR counterparts are grandfathered: they are exempt from orphan checks until their referenced plan-ID gains an ADR. The "no orphaned @req" bidirectional check is deferred to a follow-up phase — v1 scope checks orphaned ADRs only (R9).

---

## Acceptance Examples

- **AE1. (Covers R1, R2, R3.)** Given the constraint migration ADR exists at `docs/adr/`, when a new contributor asks "which constraint system should I use?", the ADR states unequivocally: "PCL is the canonical constraint system. Legacy `PlacementConstraints` is deprecated. Migration timeline: Q3 2026 complete."
- **AE2. (Covers R4, R5.)** Given a PR that adds a new `annealing_stage` to the DAG manifest, when CI runs, it fails because no ADR exists. The PR author creates `docs/adr/YYYY-MM-DD-add-annealing-stage.md` referencing the manifest diff. CI passes.
- **AE3. (Covers R6.)** Given a PR that changes the `timeout` parameter on `geometric_stage` from 300 to 600 (no name/requires/provides change), when CI runs, the ADR gate is skipped — parameter-only changes are exempt.
- **AE4. (Covers R8, R9, R11.)** Given the traceability matrix is generated, when a `@req(2026-06-28-006, R03)` annotation exists in `pcl/loss_bridge.py` and an ADR declares `plan-id: 2026-06-28-006` in its frontmatter, the matrix links annotation to ADR. If the ADR is subsequently deleted, CI fails with "orphaned ADR: plan-id 2026-06-28-006 has @req references but no ADR."

---

## Success Criteria

- New contributors can discover which constraint system is canonical within 5 minutes of reading the ADR
- DAG topology changes carry documented architectural rationale, visible to reviewers at PR time
- No orphaned architectural decisions (zero violations on ADR-evidence gate; orphaned @req annotation checks deferred to follow-up phase)

---

## Scope Boundaries

- ADRs are for pipeline architecture decisions only — not for every code change
- Traceability matrix covers `@req` annotations only — not all comments or documentation
- ADR CI gate applies to DAG manifest topology changes — not to Stage implementation changes
- Not auto-generating ADRs from code — ADRs are human-authored decisions
- R9 orphaned-ADR check applies only to ADRs that declare a `plan-id` and claim code evidence via `@req` annotations. ADRs for process-only decisions (sunset timelines, format choices, governance rules) without `plan-id` are exempt from the zero-evidence requirement
- Bidirectional orphaned-`@req` check (code annotations with no governing ADR) is deferred to a follow-up phase; v1 scope enforces orphaned-ADR checks only

---

## Key Decisions

- MADR template is the ADR format: Context, Decision, Consequences (not Nygard's longer template)
- DAG topology ADR requirement is a CI gate (blocking), not advisory
- Bidirectional traceability is a CI artifact (non-blocking initially, becomes blocking after calibration period)
- Renames are a topology change that triggers the ADR gate (same as add/remove/reorder). Parameter-only tweaks are exempt

---

## Dependencies / Assumptions

- `@req` annotation convention is consistently used for new code
- CI can detect YAML manifest changes and trigger the ADR gate only on affected PRs
- Team agrees that ADR overhead on DAG changes is acceptable given the architectural risk of undocumented topology changes
- All 100+ existing `@req` tags reference plan-IDs, not ADR identifiers, and are grandfathered until their plans gain ADR counterparts

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R6][User decision]** What is the exact exemption list beyond parameter-only — do defaults changes, description-only edits, or comment-only manifest changes qualify?

### Deferred to Planning

- **[Affects R5][Technical]** How to reliably detect YAML manifest changes and extract the diff in CI
- **[Affects R8][Technical]** Tooling for generating the traceability matrix — Python script scanning `@req` annotations vs CI script parsing ADR frontmatter
- **[Affects R12][Technical]** Mechanism and timeline for converting grandfathered `@req` tags to the plan-id-to-ADR linkage convention

---
title: Physics Soundness-Proof Register - Plan
type: feat
date: 2026-08-02
topic: physics-soundness-proof-register
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R20)
---

# Physics Soundness-Proof Register - Plan

## Goal Capsule

**Objective:** Every physics-gated constraint carries a Chebyshev-style soundness proof (conservative bound or classified approximation error) in one register; the R24 discipline becomes an inventory, not a policy.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none. The gap analysis (U2) determines how many proofs must be written; the register schema is defined in U1.

---

## Product Contract

### Summary

The R24 discipline (Chebyshev-style soundness proof, BMC-exhaustive validation on small N, post-solve audit) already applies to physics-gated CP-SAT constraints, but compliance is scattered across module docstrings and review memory. This plan turns it into an inventory: one machine-readable register lists every physics-gated constraint surface, its proof type (conservative bound or classified approximation error), where the proof lives, what it covers, and a gate that fails when a physics-gated surface has no register entry.

### Problem Frame

This idea exists for the unsound-encoding incident class: constraint encodings are trusted until a human reads them closely. The `weak-nooverlap2d`, `atmostk`, and `endpoint-bounding` failures each shipped with a plausible-sounding encoding and no standing proof. The R24 rule exists as policy in `AGENTS.md`; a policy is not an inventory, and nothing checks that a new physics-gated constraint carried its proof. A register with an enforcement gate makes the discipline structural.

### Requirements

- R20. **Soundness-proof register for physics encodings** (Formal / Physics / P1): every physics-gated constraint carries a Chebyshev-style soundness proof (conservative bound or classified approximation error) in one register — the R24 discipline becomes an inventory, not a policy. Seed: `docs/physics-verification-methodology.md`.
  - **Success signal:** a new physics-gated constraint encoder without a register entry fails CI; a cold reader can enumerate every physics-gated constraint and its proof coverage from the register alone.
  - **Covers portfolio flows:** F1 (pull-to-plan), via the seed and success signal as acceptance criteria.

### Key Technical Decisions

- KTD1. The register is machine-readable YAML keyed by encoder identity, with proof type (`conservative-bound` or `classified-error`), proof location, coverage scope, and exemption notes. Rationale: a prose inventory cannot be gated; an AST-scannable identity key lets a script verify coverage.
- KTD2. The proof artifact stays at the encoder (module docstring or adjacent comment) and the register links to it. Rationale: the single-owner-per-rule convention says the full proof lives at the code, and the register is the inventory that points to it — no second full copy to drift.
- KTD3. Enforcement is a new check script following the `bmc_adoption_gate.py` AST-scan pattern. Rationale: the repo's proven gate shape (scan class definitions, require coverage, exit non-zero with a named list) extends directly to register coverage.
- KTD4. A physics-gated surface is identified by its dependency on physics quantities (thermal fields, conductivity, convection, ampacity, inductance), not by its constraint type. Rationale: the same encoding mechanism can gate on physics in one call and pure geometry in another; classification is per-surface.

### Assumptions

- "Physics-gated" means a constraint whose encoded bound or penalty depends on a physics-derived quantity (thermal field, conductivity, convection coefficient, ampacity, parasitic inductance).
- Existing proofs in code are authoritative and are inventoried, not rewritten.
- Surfaces that cannot yet carry a proof are registered as `classified-error` with the approximation error stated, per the R24 discipline's second allowed form; a surface with neither form is a register gap that blocks merge.
- The register lives at `power_pcb_dataset/` alongside the other measured-provenance registers, unless the gap analysis shows a better home.

---

## Implementation Units

### U1. Register schema and initial population

**Goal:** Define the register schema and populate it from the proofs that already exist in code.

**Requirements:** R20, KTD1, KTD2.

**Dependencies:** none.

**Files:**
- `power_pcb_dataset/physics_soundness_register.yaml` (new register)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py` (inventory its existing proof)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/separated.py` (inventory its existing proof)
- `packages/temper-placer/tests/` register-loading tests

**Approach:**
1. Define the schema: one entry per physics-gated surface with identity key, proof type, proof location, coverage scope, exemptions, and last-verified date.
2. Inventory the known proofs first: `domain_clearance.py`'s box-vs-box implies copper-vs-copper proof, `handlers/separated.py`'s Chebyshev soundness case analysis, and the router-V6 sequential-counter induction documented in `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`.
3. Add a loader test that the register parses and every entry's proof location resolves to a real file.

**Patterns to follow:** the provenance convention of `power_pcb_dataset/drc_ceiling.json`; the `esl()`-style semantic declarations already present on router-V6 constraint classes.

**Test scenarios:**
- The register parses; every entry has a non-empty proof type and a resolvable proof location.
- Each populated entry's proof location file actually contains the named proof (substring check on the cited symbol).
- A register entry with an unknown proof type fails validation.

**Verification:** the register loads, and every entry resolves to a real proof in code.

### U2. Gap analysis across physics-gated surfaces

**Goal:** Enumerate every physics-gated surface, classify each against the register, and close the gaps (write missing proofs or register classified errors).

**Requirements:** R20, KTD4.

**Dependencies:** U1.

**Files:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/` (handlers and domain surfaces to classify)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py` (post-solve audit coverage notes)
- `power_pcb_dataset/physics_soundness_register.yaml` (gap entries)

**Approach:**
1. Enumerate constraint encodings whose bounds or penalties depend on physics quantities (thermal, conductivity, convection, ampacity, inductance).
2. For each, classify as `conservative-bound` (proof exists), `classified-error` (approximation error stated), or gap.
3. Write the missing proofs at the encoder and register them; record classified-error entries with the approximation error stated in the register.

**Patterns to follow:** the Chebyshev-style proof structure in `domain_clearance.py`'s module docstring (SAT ⇒ geometric quantity ⇒ validator quantity, with stated preconditions).

**Test scenarios:**
- Every physics-gated surface found by the enumeration has a register entry after the pass.
- A surface classified `classified-error` states its approximation error and its direction (conservative or not).
- A surface whose proof cites a precondition that the code no longer guarantees is flagged, not silently carried (the domain-clearance stale-proof class).
- Non-physics-gated encodings (pure geometry) are excluded from the register.

**Verification:** the enumeration and the register agree on the surface set; no gap remains.

### U3. Enforcement gate

**Goal:** Fail CI when a physics-gated constraint encoder has no register entry.

**Requirements:** R20, KTD3, KTD4.

**Dependencies:** U1, U2.

**Files:**
- `scripts/physics_soundness_register_gate.py` (new; requires a `scripts/manifest.yaml` entry)
- `scripts/manifest.yaml` (entry)
- `packages/temper-placer/tests/` gate-contract tests

**Approach:**
1. AST-scan the placer constraint surfaces and router-V6 constraint classes for physics-gated encodings, mirroring the `bmc_adoption_gate.py` scan shape.
2. Require a register entry for every surface found; exit non-zero naming the missing entries.
3. Add the gate to CI alongside the existing adoption gates.

**Patterns to follow:** the scan-and-report structure of `scripts/bmc_adoption_gate.py`; the import-linter gate's exit-code conventions.

**Test scenarios:**
- A deliberately added physics-gated encoder without a register entry fails the gate with the encoder named.
- Removing an entry for an existing surface fails the gate.
- Registering the surface clears the failure.
- The gate reports `OK` on the populated register with all surfaces covered.

**Verification:** the gate is green on the current tree and red on a synthetic unregistered surface.

### U4. Register discipline tests and documentation

**Goal:** Lock the register's behavior in tests and document the inventory as the R24 standing artifact.

**Requirements:** R20, KTD1, KTD2.

**Dependencies:** U3.

**Files:**
- `packages/temper-placer/tests/` register-behavior tests
- `docs/physics-verification-methodology.md` (link the register as the inventory artifact)
- `power_pcb_dataset/physics_soundness_register.yaml` (stabilized)

**Approach:**
1. Add tests covering register mutation rules (add requires proof type; edit requires provenance note; delete fails the gate).
2. Reference the register from the methodology doc so the R24 discipline points at its inventory.
3. Stabilize the register as the canonical artifact the gate and the docs both cite.

**Patterns to follow:** the `_march` log discipline of `power_pcb_dataset/drc_ceiling.json` for register edits.

**Test scenarios:**
- Adding an entry without a proof type fails validation.
- Editing a proof's coverage scope without a provenance note fails validation.
- The methodology doc links resolve to the register path.

**Verification:** the register is stable, tested, and cited by the methodology doc.

---

## Verification Contract

- Unit tests: `uv run pytest packages/temper-placer/tests/placer/cp_sat/ packages/temper-placer/tests/requirements/ -q` from `packages/temper-placer/`.
- Gate: `uv run python scripts/physics_soundness_register_gate.py` at repo root; must exit 0 on the populated register.
- Import boundary gate: `uv run python scripts/import_linter_gate.py`.
- Script manifest: the new gate requires an entry in `scripts/manifest.yaml`; refresh with `uv run python scripts/trace_invocations.py`.
- Coverage gate: new public functions in `temper_placer` need tests or an allowlist entry (run per the standard `--cov` invocation from `packages/temper-placer/`).

---

## Definition of Done

- The register lists every physics-gated constraint surface with proof type, proof location, and coverage scope.
- The enforcement gate fails on any unregistered physics-gated surface and is green on the current tree.
- Every gap found by the enumeration is closed: a proof written at the encoder or a classified-error entry with the error stated.
- The methodology doc cites the register as the R24 inventory.
- Abandoned experimental scan code is removed before the branch is complete.

---

## Scope Boundaries

- **In scope:** register schema, initial population, gap analysis, enforcement gate, doc linkage.
- **Out of scope:** writing new BMC-exhaustive batteries for surfaces that lack them (the R21 plan owns that); rewriting existing proofs; changing the R24 discipline itself.

### Deferred to Follow-Up Work

- BMC-exhaustive validation for surfaces that have a proof but no BMC battery (see the R21 plan).
- Promoting the register to a repo-wide constraint inventory beyond physics-gated surfaces.
- Post-solve audit coverage for every registered surface (see R24 in the portfolio).

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — origin (R20).
- `docs/physics-verification-methodology.md` — the seed discipline (R24 soundness form) and the fail-capable rule.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py` — the worked Chebyshev proof to inventory.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/separated.py` — a second existing proof to inventory.
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — the incident class and the sequential-counter induction proof.
- `scripts/bmc_adoption_gate.py` — the AST-scan gate shape KTD3 follows.
- `power_pcb_dataset/drc_ceiling.json` — the provenance-and-march register convention.

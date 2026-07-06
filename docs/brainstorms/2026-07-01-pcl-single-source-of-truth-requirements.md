---
date: 2026-07-01
topic: pcl-single-source-of-truth
---

# PCL Single-Source-of-Truth with Hard-Fail Discovery

## Summary

Replace the legacy `PlacementConstraints` return from `load_constraints()` / `input_stage` with PCL `ConstraintCollection`, eliminate the silent split between PCL parsing (which exists but is never called from the optimize path) and the legacy loader (which exclusively drives placement), and delete the legacy constraint loader once all consumers are ported.

---

## Problem Frame

The temper-placer optimize pipeline has a dual-constraint-system bug. `load_constraints()`, called by `input_stage` (`packages/temper-placer/src/temper_placer/pipeline/stages/input_stage.py:47`), returns only legacy `PlacementConstraints` parsed from `configs/temper_constraints.yaml`. The PCL parser (`parse_pcl_file()` in `pcl/parser.py`) exists, is exercised by `pcl_validate` and unit-tested, and can produce a correct `ConstraintCollection` — but it is never called by `input_stage`, `load_constraints()`, or any optimize-path code. The result: the actual constraint types supported by PCL (`AdjacentConstraint`, `SeparatedConstraint`, `EnclosingConstraint`, `AlignedConstraint`, `OnSideConstraint`, `AnchoredConstraint`, `LoopAreaConstraint`) are ghosts — they exist in the PCL type system and enrich correctly through `pcl_validate`, but are never wired into the optimize path that drives placement.

Legacy `PlacementConstraints` fields (zones, keepouts, net classes, board geometry) are consumed across ~60 files, but structural PCL constraint types that capture designer intent (adjacency, separation, enclosing, alignment, on-side placement, anchoring, loop-area limits) are absent from every placement the optimizer produces.

This is the same infrastructure-unwired failure mode documented as an anti-pattern: two parallel systems for the same concern, one wired to production and one not, with the unwired one never fired rather than failing loudly.

Stepping back, the root cause is the absence of a `.pcl.yaml` manifest — the file that `parse_pcl_file()` would consume — combined with the fact that no optimize-path code even attempts to call `parse_pcl_file()`. Currently, the `input_stage` exclusively delegates to `load_constraints()`, which knows only the legacy `PlacementConstraints` format. A developer who writes PCL constraint objects in code or tests sees correct output, then runs the optimize pipeline and sees no constraint effect — with no error to signal the disconnect. The dual path is not just redundant code; it is a correctness hazard that silently ignores PCL constraints.

---

## Prerequisites

- **R-NEW:** A `.pcl.yaml` manifest must be created from the existing `configs/temper_constraints.yaml` before PCL can become the single source of truth. Zero `.pcl.yaml` files currently exist in the repository. This is a blocking prerequisite: the legacy `PlacementConstraints` fields must be translated into equivalent PCL constraint types (`AdjacentConstraint`, `SeparatedConstraint`, `EnclosingConstraint`, `AlignedConstraint`, `OnSideConstraint`, `AnchoredConstraint`, `LoopAreaConstraint`), and any legacy category with no PCL equivalent must be explicitly documented as dropped with justification (per the Dependencies / Assumptions gap analysis).

---

## Requirements

**PCL as Single Source of Truth**

- R1. The `input_stage` pipeline stage returns a PCL `ConstraintCollection` as its primary constraint output. The legacy `PlacementConstraints` object is no longer produced by any stage in the optimize pipeline.
- R2. The PCL enrichment pipeline — the path already exercised by `pcl_validate` via `parse_pcl_file()` and verified correct — is the canonical constraint-production path for the optimize pipeline. No alternative constraint-production path exists; there is exactly one way to produce constraints from the `.pcl.yaml` manifest.
- R3. All PCL constraint types (`AdjacentConstraint`, `SeparatedConstraint`, `EnclosingConstraint`, `AlignedConstraint`, `OnSideConstraint`, `AnchoredConstraint`, `LoopAreaConstraint`) supported by PCL enrichment are applied during optimization. A constraint declared in `.pcl.yaml` that is silently absent from the optimizer's constraint set is a bug — not a "not yet implemented."

**Hard-Fail Discovery**

- R4. The optimize pipeline's constraint-loading path must detect absence of a `.pcl.yaml` manifest and fail hard. If the manifest is absent or cannot be parsed, the optimize pipeline exits with a diagnostic error naming the expected file path and the reason. "Silent skip" is not an available outcome.
- R5. The diagnostic message when a `.pcl.yaml` manifest is missing is actionable: it names the expected path, states that PCL constraints are required for correct placement, and provides the command to generate or locate a valid manifest.
- R6. If the `.pcl.yaml` manifest is present but contains parse errors, constraint validation failures, or enrichment errors, the optimize pipeline exits with a diagnostic that names the offending constraint and the validation rule it violated. Silent fallback to an empty or partial constraint set is not permitted.

**Enrichment Integrity**

- R7. Every PCL constraint type that enrichment can produce from a valid `.pcl.yaml` manifest is present in the `ConstraintCollection` consumed by the optimizer. A constraint type that exists in the PCL type system but is dropped during enrichment is a hard error, not a silent omission.
- R8. The loss bridge that converts PCL constraints to JAX loss terms receives the full enriched `ConstraintCollection`. No constraint filtering or downselection occurs between enrichment and loss-bridge invocation; the optimizer sees everything the manifest declares.

**Consumer Migration**

- R9. All consumers of the legacy `PlacementConstraints` object in the optimize pipeline are identified and ported to the PCL `ConstraintCollection` equivalent fields. A consumer that references a legacy `PlacementConstraints` field that has no PCL equivalent is a hard error at constraint-construction time, not a silent zero-value substitution.
- R10. The migration window between introducing PCL as the constraint output and deleting the legacy loader must not exceed 2 weeks (one release cycle). During the migration window, tests may bridge both paths; after the window closes, the legacy path is gone. No release ships with both legacy `PlacementConstraints` and PCL `ConstraintCollection` as parallel constraint outputs used by the optimize pipeline — the two may coexist only during the migration window in unreleased intermediate commits.

**Legacy Deletion**

- R11. Once all consumers are ported and verified, the legacy constraint loader is deleted in its entirety. No dead code, no `# TODO: remove after migration` comments, no soft deprecation warnings — the file is removed and imports that reference it fail at compile time.

**Verification**

- R12. A CI gate runs `pcl_validate` against the committed `.pcl.yaml` manifest on every push. A manifest change that fails validation blocks the pipeline before any optimization runs.
- R13. An integration test exercises the full `input_stage` -> enrichment -> loss bridge path and asserts that every constraint category declared in `.pcl.yaml` produces nonzero loss terms. A constraint category that enrichment produces but the loss bridge ignores fails this test.

---

## Acceptance Examples

- AE1. **Covers R4, R5.** Given no `.pcl.yaml` file exists in the expected location, when the optimize pipeline runs `input_stage`, it exits with an error message containing the expected file path and a statement that PCL constraints are required. The pipeline does not proceed to placement.
- AE2. **Covers R6.** Given a `.pcl.yaml` manifest that declares a `SeparatedConstraint` with a self-intersecting zone polygon (malformed geometry), when `input_stage` enriches the constraint collection, the pipeline exits with a diagnostic naming the offending constraint and the validation error. Placement does not begin.
- AE3. **Covers R1, R7.** Given a valid `.pcl.yaml` manifest declaring a `SeparatedConstraint` between tagged HV and LV component groups, two `EnclosingConstraint` zones, and an `AlignedConstraint` group, when `input_stage` completes, the `ConstraintCollection` returned contains all constraint categories with their full enriched geometry. The legacy `PlacementConstraints` object is not present in the stage output.
- AE4. **Covers R3.** Given the same manifest, when the optimizer runs to completion, the `EnclosingConstraint` zones affect component positions (components are not placed outside zone boundaries), the `SeparatedConstraint` loss terms are active (nonzero contribution to the loss), and the `AlignedConstraint` constrains component positions on the declared axis. Removing the `EnclosingConstraint` declaration from `.pcl.yaml` and re-running produces different component positions.
- AE5. **Covers R9.** Given a consumer of constraints in the optimize path accesses a constraint field that exists in legacy `PlacementConstraints` but not in PCL `ConstraintCollection`, when constraints are constructed, an error is raised naming the missing field and the consumer that requested it. The optimizer does not silently use a zero value.
- AE6. **Covers R11.** Given all consumers are ported and verified, when a developer attempts to `import` from the legacy constraint loader, the import fails with `ModuleNotFoundError`. No stale `PlacementConstraints` definition remains in the codebase.
- AE7. **Covers R12.** Given a developer edits `.pcl.yaml` and introduces a validation error (e.g., omitting the required `because` rationale from a constraint declaration), when they push, CI fails at the `pcl_validate` step with a diagnostic naming the error. The optimization step is not reached.
- AE8. **Covers R13.** Given a developer adds a new PCL constraint type (e.g., a new subclass of `BaseConstraint`) to the type system and enrichment pipeline, but forgets to add the corresponding loss term in the loss bridge, when CI runs the integration test, it fails with a message naming the constraint type that produced zero loss terms despite being present in the `ConstraintCollection`.

---

## Success Criteria

- Running the optimize pipeline without a `.pcl.yaml` manifest fails with a diagnostic error — a developer cannot accidentally ship a placement that omits adjacency, separation, enclosing, alignment, anchoring, on-side, or loop-area constraints.
- A constraint declared in `.pcl.yaml` is present in the optimizer's constraint set, and removing it changes placement output. All seven PCL constraint types are active in optimization, not ghosts.
- The `pcl_validate` CLI and the optimize pipeline use the same constraint-production path (`parse_pcl_file()`). A constraint that passes `pcl_validate` is guaranteed to be active in optimization.
- After the legacy loader is deleted, a grep for `PlacementConstraints` in the optimize path returns zero results. There is exactly one constraint type in the optimize pipeline.
- The CI gate (R12) prevents a manifest regression from reaching optimization. A manifest edit that breaks enrichment is caught at CI time, not at placement time.

---

## Scope Boundaries

- **SAT routing constraint forwarding is out of scope.** The bidirectional PCL IR (converting placement PCL constraints to SAT routing clauses) is a separate initiative. This initiative concerns only the optimize path's consumption of PCL constraints.
- **Constraint-aware initialization is out of scope.** The passthrough-init initiative (threading constraints to initializers) is a downstream consumer, not a prerequisite. This initiative ensures the constraints exist and are correct; it does not add new constraint-consuming behavior.
- **New PCL constraint types are out of scope.** This initiative wires the existing seven PCL constraint types (`AdjacentConstraint`, `SeparatedConstraint`, `EnclosingConstraint`, `AlignedConstraint`, `OnSideConstraint`, `AnchoredConstraint`, `LoopAreaConstraint`). Adding new constraint types (e.g., thermal, EMC) is independent work.
- **PCL schema migration is out of scope.** The `.pcl.yaml` manifest format is assumed stable. If the format changes, the enrichment pipeline is updated as a separate changeset.
- **Removing the entire `io/` package is out of scope.** Other modules in `io/` (e.g., netlist loading, board geometry) may remain. Only the legacy `PlacementConstraints` class and `load_constraints()` function are deleted.
- **DAG topology restructuring (stage ordering, dependency changes) is out of scope.** The pipeline YAML manifest's `data_keys` section type annotations may need updating (e.g., `constraints: { type: PlacementConstraints }` on `pipeline_default.yaml:75`). Adding new stages or restructuring the DAG topology is out of scope.
- **`constraints_to_design_rules()` migration is deferred to a separate brainstorm.** This function converts `PlacementConstraints` to `DesignRules` for routing and has 32 call sites across 11 files. PCL `ConstraintCollection` has no direct equivalent — its `SeparatedConstraint` semantics differ from `DesignRules` net class clearances. This initiative establishes PCL as the single source of truth for placement constraints; routing design-rule derivation from PCL is a separate piece of work.
- **`create_board_from_constraints()` extraction is deferred.** This function extracts board geometry from `PlacementConstraints` (width, height, keepouts, zones, layer stackup) and is called from 18 files. Board geometry is orthogonal to PCL constraint types and can be extracted from the legacy config or loaded independently.

---

## Key Decisions

- **Hard-fail, not soft-migration.** The absence of `.pcl.yaml` is a hard failure. There is no grace period where the absence is a warning. This is justified by the severity of the bug (placement is structurally wrong without constraints) and the fact that `parse_pcl_file()` and the PCL type system are already tested — there is no unknown migration risk.
- **PCL enrichment is the single constraint-production path.** The `pcl_validate` CLI and the PCL pipeline path already exercise `parse_pcl_file()`. Rather than maintaining two constraint-production paths (one for validation, one for optimization), this initiative eliminates the fork and makes enrichment the canonical path for all consumers.
- **Legacy deletion is a hard requirement, not a stretch goal.** Keeping the legacy loader after migration creates a permanent temptation to add new constraints to the legacy path. The file is deleted within the R10 migration window (max 2 weeks). The deletion is not gated on a grace period; it is part of the migration.
- **Consumer migration is exhaustive, not best-effort.** Every consumer of `PlacementConstraints` in the optimize path must be ported before the legacy loader is deleted. A partially-ported state where some consumers reference PCL and others reference legacy is not shipped — it would reintroduce the dual-constraint-system bug this initiative exists to fix.
- **CI validation gate (R12) is a migration prerequisite, not a follow-up.** The gate is the structural defense against the original failure mode: silent enrichment failures. It lands before or with the migration; the migration is not complete without it.

---

## Dependencies / Assumptions

- **PCL enrichment is production-grade.** The `pcl_validate` CLI path exercises enrichment end-to-end and produces correct `ConstraintCollection` output. This initiative depends on that path being structurally sound — no latent enrichment bugs that are masked because only the CLI exercises the path today.
- **All legacy `PlacementConstraints` fields have PCL equivalents or are explicitly excluded.** The domain-rule categories in the legacy loader (zones, component groups, HV/LV separation, thermal, critical loops, star grounds, clearances, keepouts, noise isolation, matched-length groups, fixed positions) must be representable as PCL constraint types. Reusable mappings include: zones -> `EnclosingConstraint`, HV/LV separation -> `SeparatedConstraint` with tag-based groups, critical loops -> `LoopAreaConstraint`, fixed positions -> `AnchoredConstraint`. If a category has no PCL equivalent, it must be explicitly documented as dropped with justification. **Risk:** an unported category silently drops rules that the legacy path enforced.
- **The DAG engine's YAML manifest type annotation for `constraints` must be updated.** `pipeline_default.yaml:75` currently types `constraints` as `PlacementConstraints`. This annotation must change to `ConstraintCollection`.
- **No external tooling depends on the legacy `PlacementConstraints` format.** Scripts, notebooks, or external consumers that import `PlacementConstraints` from the legacy loader will break when the file is deleted. A pre-deletion audit of import statements across the repo is required (~60 files currently import `PlacementConstraints`).
- **The existing test suite is sufficient to catch placement regressions.** The migration must not degrade placement quality. The assumption is that the existing optimization tests (loss values, convergence thresholds) are sensitive enough to detect a constraint wiring error. If the test suite only validates that the optimizer runs without crashing, a separate regression baseline must be added.

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R9][Technical]** What is the full set of consumers of `PlacementConstraints` in the optimize path? A comprehensive audit across the ~60 files that import `PlacementConstraints` is required before planning the migration. Each consumer must be mapped to its PCL equivalent fields. If any consumer accesses a field with no PCL equivalent, the PCL type system must be extended first.
- **[Affects R6][Technical]** What validation rules in the PCL enrichment pipeline currently fire? If enrichment has known unexercised validation paths (analogous to the dead DRC checks from the June 2026 sprint), those must be identified and tested before hard-failing on them.
- **[Affects R11][Deletion safety]** Are there any imports from the legacy `PlacementConstraints` outside the optimize pipeline? A repo-wide audit of the ~60 importing files is required. Imports in test files, other packages, scripts, or notebooks must be accounted for in the deletion plan.
- **[Affects R3][Gap analysis]** Which constraint categories in the legacy `PlacementConstraints` have no corresponding PCL type? Specifically: matched-length groups, thermal constraints, and star-ground assignments. If these are in active use, PCL types must be added before the migration.
- **[Prerequisite: R-NEW]** How is `configs/temper_constraints.yaml` translated into a `.pcl.yaml` manifest? A mapping from legacy YAML sections to PCL constraint types must be specified. For example: legacy `zones` with `net_classes` -> `EnclosingConstraint` or `SeparatedConstraint` with tag-based component groups. This translation is a blocking prerequisite.

### Deferred to Planning

- **[Affects R2][Technical]** How is `parse_pcl_file()` invoked from `input_stage`? Determine whether it replaces the `load_constraints()` call directly, is invoked alongside it during migration, or is factored into a shared module import. The chosen integration pattern affects dependency hygiene and testability.
- **[Affects R8][Technical]** Does the loss bridge need changes to consume `ConstraintCollection` directly, or does it already? If the loss bridge currently consumes legacy types, the bridge's interface must be updated in the same changeset.
- **[Affects R10][Process]** Should the migration PRs be stacked or monolithic? The migration window is bounded at 2 weeks (R10). Whether individual consumer-port PRs are stacked depends on the consumer audit results. Scheduling (stacked vs. monolithic within the 2-week window) is a planning detail, not a requirements concern.
- **[Affects R10][Testing]** What is the regression test strategy during migration? The existing optimization test suite exercises the legacy path. After migration, determine whether the same tests pass with PCL constraints producing equivalent (or improved) placement results, and whether a baseline snapshot test is needed to verify no placement regression.
- **[Affects R2][DAG manifest]** The pipeline YAML manifest's `data_keys.constraints.type` must change from `PlacementConstraints` to `ConstraintCollection` (`pipeline_default.yaml:75`). Determine whether the DAG engine enforces runtime type checking on data keys and whether that requires additional manifest changes.

(End of file)

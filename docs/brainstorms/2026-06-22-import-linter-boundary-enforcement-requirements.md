---
date: 2026-06-22
topic: import-linter-boundary-enforcement
---

# Import-Linter Module Boundary Enforcement

## Summary

A CI gate that declares and enforces import boundaries between Python packages so extracted modules physically cannot regress into the monolith during strangler-fig decomposition.

---

## Problem Frame

Temper's codebase has 7 Python packages and ~118 scripts with no guardrails on what imports what. Any module can reach into any other module's internals. During strangler-fig decomposition this is fatal: a freshly-extracted module can silently re-couple to the old monolith through an accidental import, and nothing catches it. The existing coverage gate only checks test coverage on `core/` (25 modules) -- it says nothing about architectural boundaries.

The seed idea references FreeRouting as a precedent: during their monolithic-to-modular decomposition, they used ArchUnit (Java) to enforce exactly these boundaries. Python's closest equivalent is `import-linter`. The codebase currently has no boundary enforcement of any kind.

Specific risks without this gate:
- **Silent coupling:** A developer adds `from temper_placer.monolith_internal import X` in an extracted package; nothing warns them, nothing blocks the PR.
- **Boundary erosion:** Over months, the extracted package drifts back toward depending on monolith internals. Reversing this later requires untangling a web of accidental dependencies.
- **Strangler-fig stall:** If extracted modules freely import from the old monolith, the monolith can never be deleted. Each extracted module just adds code without removing any.

---

## Requirements

**Boundary declarations**

- R1. Module boundaries are declared in a config file checked into the repo. Each boundary names source modules and the target modules they are permitted to import from.
- R2. The config supports a mutually-isolated (`⊥`) declaration: source modules that must not import from each other (e.g., `core/` and `router_v6/`).
- R3. The config supports package-level public-interface contracts: a package declares which submodules are public; all other submodules are implementation details that no external package may import.

**CI enforcement**

- R4. A CI check reads the boundary config and validates that all `import` statements in the repo comply. Violations block PR merge.
- R5. The check is CI-only -- local violations do not prevent running code, only merging to the protected branch. However, developers can run the same check locally with `uv run import-linter` for pre-push verification.

**Ratchet property**

- R6. Boundaries can only tighten, never loosen. The ratchet mechanism uses a committed baseline (`import-linter-baseline.yaml`) that records the current import graph. PR CI diffs the regenerated graph against the baseline; new edges are violations unless allowlisted. The baseline shrinks as violations are fixed. Removing or relaxing a boundary declaration requires explicit documented justification tracked in a monotonic-shrinking allowlist (analogous to `.coverage-allowlist` and `.loc-allowlist.txt` already in the repo).
- R7. When a new module is extracted and its boundary declared, the CI gate enforces it from that point forward. Previously-allowed imports crossing the new boundary become violations.

**Soft-launch and operational model**

- R14. The boundaries go through a 2-week WARNING-only phase on CI before becoming merge-blocking. During this period, violations are reported but do not block. This gives developers time to fix existing violations and adjust workflows.
- R15. Allowlist additions are self-serve: a developer adds an entry with justification and ticket reference; the entry is accepted by CI without separate review. Boundary config changes (adding, removing, or modifying boundary declarations) require PR review.
- R16. CI violation messages include the boundary rule violated and two concrete remediation options: (a) move the import to a permitted module, or (b) add an allowlist entry with justification.
- R17. The check completes in under 30 seconds on CI hardware for the full codebase.

**Script classification**

- R8. Each script in `scripts/` is classified as either: (a) ad-hoc tooling exempt from boundary enforcement via a monotonic-shrinking allowlist, or (b) subject to the boundary of the package it integrates with.
- R9. Scripts outside package source trees that import from packages must respect those packages' declared public interfaces. Imports of internal submodules from such scripts require an allowlist entry.

**Exception handling**

- R10. An allowlist mechanism permits violations with a documented justification and an expiry or reassessment date. The allowlist is monotonic-shrinking: entries may be removed on compliance, added only with justification and a ticket reference.
- R11. Integration tests that must cross boundaries to verify system behavior are explicitly allowlisted by path or pattern.

**False-positive prevention**

- R12. The CI gate must produce zero false positives against the existing test suite. Boundary declarations may use wildcard or regex patterns to avoid enumerating every internal implementation file.
- R13. Ambiguous cases (where intent cannot be determined) produce warnings, not violations. The warning includes a path to resolve the ambiguity by updating the boundary config.

---

## Acceptance Examples

- AE1. **Covers R2, R4.** Given a boundary config declaring `core/ ⊥ router_v6/`, when a PR adds `from temper_placer.router_v6.astar_pathfinding import ...` inside `temper_placer/core/board.py`, the CI gate fails and the merge is blocked.
- AE2. **Covers R6.** Given a boundary config with declared boundaries, when a PR attempts to remove one boundary declaration, the CI gate fails unless the removal is accompanied by a new entry in the monotonic-shrinking allowlist with justification and ticket reference.
- AE3. **Covers R10.** Given an integration test at `packages/temper-placer/tests/integration/test_end_to_end.py` that imports from both `temper_placer.core` and `temper_placer.router_v6`, the test is allowed via the allowlist with justification "integration test -- verifies cross-module behavior" and expiry "temper-xxx -- reevaluate when router_v6/ is extracted to own package."
- AE4. **Covers R12.** Given the existing test suite with all current imports as-is, the initial boundary config produces zero violations so the CI gate is green on the first commit that enables it.

---

## Success Criteria

- A PR that introduces a new import from `router_v6/` into `core/` is blocked at CI with a message naming the violated boundary.
- A PR that removes a boundary declaration without corresponding allowlist justification is blocked.
- Zero false positives on the existing codebase when the gate is first enabled.
- The boundary config and allowlist are human-readable enough that a developer can determine in under one minute whether a given import is allowed.

---

## Scope Boundaries

- Symptom-only: the gate detects violations but does not fix them. Refactoring violating imports is separate work.
- Static enforcement only (CI-time). Runtime import guards are out of scope.
- Python-only. The firmware C codebase is not subject to this gate.
- Inter-package and major subpackage boundaries only. Intra-module import hygiene (e.g., circular dependencies within one package) is deferred.
- The unification of the dual `temper-placer/` / `packages/temper-placer/` directory layout is separate work; the boundary gate accommodates the current layout.

---

## Key Decisions

- **Use import-linter over a custom script.** import-linter is the Python ecosystem's equivalent of ArchUnit, providing declarative YAML config, built-in contract types (`forbidden`, `layers`, `independence`), and CI integration. A custom checker would duplicate this and require ongoing maintenance.
- **Start with 2-3 boundaries, not comprehensive coverage.** Declaring `core/ ⊥ router_v6/` and package-level public interfaces for the extracted packages is sufficient to establish the ratchet. Additional boundaries are added as more modules are extracted.
- **Scripts default to allowlisted.** Given 118 scripts with heterogeneous import patterns and no clear boundary home, they start in the allowlist and migrate out as they are audited. This avoids blocking existing workflows.

---

## Dependencies / Assumptions

- **Assume: `import-linter` supports all boundary types required** (independence, forbidden, layers) and integrates with existing CI (GitHub Actions via `uv run`). The `import-linter` package supports YAML config, `independence` (⊥) contracts, `forbidden` imports, `layers` contracts, and wildcard module patterns — verified against the package index (v2.0+, maintained as of June 2026). A `uv run import-linter` invocation in `.github/workflows/` is sufficient for CI integration.
- **Assumption:** The existing import graph within `temper_placer` (where `core/` imports nothing from `router_v6/` but many subpackages import from `core/`) accurately reflects the intended architecture and won't produce a deluge of violations on first run.
- **Dependency:** CI must have access to the full Python environment (`uv sync`) to run the import analysis on the repo.

---

## Outstanding Questions

### Resolved Before Planning

- **[R1, R4][Resolved]** `import-linter` (v2.0+) supports `independence`, `forbidden`, and `layers` contract types with YAML config and wildcard patterns. Integration with `uv run` in GitHub Actions is confirmed.
- **[R6][Resolved]** The ratchet mechanism works via a committed baseline YAML file (`import-linter-baseline.yaml`) that records the current import graph's allowed edges. Each PR's CI check re-generates this graph from the current code and diffs against the committed baseline. New edges are violations unless added to the allowlist with justification. Removed edges that were in the baseline reduce the baseline — the ratchet. This mirrors the existing `.coverage-allowlist` monotonic-shrink pattern already proven in the repo.
- **[R8][Resolved]** Script audit approach: run `import-linter` in report-only mode across all `scripts/` files, capture the full import graph, categorize each script by its primary imports (package-level vs internal-submodule), and triage into a single batch PR. Scripts that only import package public interfaces stay exempt via allowlist. Scripts that import internal submodules are migrated to public-interface equivalents or added to the allowlist with ticket-anchored justification entries. The audit is a one-time upfront cost (estimated 2-3 hours for 118 scripts).
- **[R11][Resolved]** Allowlist is a separate file (`import-linter-allowlist.yaml`) consistent with `.coverage-allowlist` and `.loc-allowlist.txt` conventions. Each entry includes justification and ticket reference.

### Deferred to Planning

- **[R12][Technical]** How to handle the initial boundary config generation — run import-linter in report-only mode and mechanically translate the current import graph into a baseline.
- **[R10][Technical]** Allowlist expiry/reassessment process — whether expiry is date-based or trigger-based (ticket closure, module extraction milestone).

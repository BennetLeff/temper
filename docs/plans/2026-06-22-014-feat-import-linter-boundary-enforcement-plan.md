---
title: "feat: Import-Linter Module Boundary Enforcement CI Gate"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-22-import-linter-boundary-enforcement-requirements.md
---

# feat: Import-Linter Module Boundary Enforcement CI Gate

## Summary

A CI gate using `import-linter` v2.0+ that declares and enforces module boundaries between Temper's 7 Python packages. Starts with a `core/ ⊥ router_v6/` independence contract and package-level public-interface contracts for 2-3 extracted packages. Ships with a ratchet baseline (`import-linter-baseline.yaml`), a monotonic-shrinking allowlist (`import-linter-allowlist.yaml`), a one-time script audit, and a 2-week WARNING-only soft-launch before becoming merge-blocking. Composes with the existing Vulture dead-code gate (static reachability) and N3 coverage gate (dynamic coverage) as the architectural-boundary layer.

---

## Problem Frame

Temper has 7 Python packages (~36 subpackages within `temper_placer` alone) and ~118 scripts with zero guardrails on inter-module imports. During strangler-fig decomposition of the `temper_placer` monolith, a freshly-extracted module can silently re-couple to the old monolith through an accidental import and nothing catches it.

**Specific risks without this gate:**

- **Silent coupling**: A developer adds `from temper_placer.router_v6.astar_pathfinding import ...` inside `temper_placer/core/board.py`; nothing warns, nothing blocks.
- **Boundary erosion**: Over months, extracted packages drift back toward depending on monolith internals.
- **Strangler-fig stall**: If extracted modules freely import from the old monolith, the monolith can never be deleted.

**Precedent**: FreeRouting used ArchUnit (Java) for identical boundary enforcement during their monolithic-to-modular decomposition. `import-linter` is the Python ecosystem's equivalent.

**Current state**: The repo has two pre-existing monotonic-shrink patterns — `.coverage-allowlist` (function-level coverage exclusions) and `.loc-allowlist.txt` (LOC cap exceptions) — both enforced at CI. This gate mirrors that pattern: a committed baseline that only shrinks, an allowlist with ticket-anchored justifications, and a CI step that diffs and blocks on new violations.

---

## Scope Boundaries

### In scope

- Install `import-linter` as a workspace dev dependency
- Declare `core/ ⊥ router_v6/` independence contract (the seed boundary)
- Declare 2-3 package-level public-interface contracts (e.g., for `temper_placer.core`, `temper_placer.router_v6`)
- CI workflow step in `.github/workflows/python-tests.yml` running `uv run import-linter`
- Ratchet baseline generation (`import-linter-baseline.yaml`)
- Monotonic-shrinking allowlist (`import-linter-allowlist.yaml`)
- One-time script audit: classify 118 scripts, triage into batch PR
- Local pre-merge check documentation (`uv run import-linter`)
- 2-week WARNING-only soft-launch, then merge-blocking
- Under-30-seconds CI runtime

### Deferred

- Intra-package import hygiene (circular dependencies within one package)
- Runtime import guards
- Comprehensive boundary coverage across all 36 subpackages — added incrementally as more modules are extracted
- Unification of `temper-placer/` / `packages/temper-placer/` dual directory layout
- Firmware C codebase boundary enforcement

### Out of scope

- Fixing existing import violations — refactoring is separate work
- Adding new boundary contracts beyond the seed set (done in follow-up extraction PRs)
- The `import-linter` config itself is not a replacement for eventual package extraction; it enforces boundaries, it doesn't extract code

---

## Requirements

**Boundary declarations**

- **R1.** Module boundaries declared in committed YAML config (`import-linter.yaml`). Each boundary names source modules and the target modules they are permitted to import from.
- **R2.** Config supports `independence` (⊥) contracts: source modules that must not import from each other (e.g., `core/` and `router_v6/`).
- **R3.** Config supports `forbidden` contracts: a package declares which submodules are public; all other submodules are implementation details that no external package may import from.

**CI enforcement**

- **R4.** CI step reads the boundary config and validates all `import` statements in `packages/`. Violations block PR merge (after soft-launch period).
- **R5.** Developers can run the same check locally with `uv run import-linter` for pre-push verification.

**Ratchet property**

- **R6.** Boundaries can only tighten. The ratchet uses a committed baseline (`import-linter-baseline.yaml`) recording the current import graph. PR CI regenerates and diffs against baseline; new edges are violations unless allowlisted. The baseline shrinks as violations are fixed. Relaxing or removing a boundary declaration requires explicit documented justification in the allowlist.
- **R7.** When a new module is extracted and its boundary declared, previously-allowed imports crossing the new boundary become violations.

**Script classification**

- **R8.** Each of ~118 scripts is classified as: (a) ad-hoc tooling exempt via allowlist, or (b) subject to the boundary of the package it integrates with.
- **R9.** Scripts outside package source trees that import from packages must respect those packages' declared public interfaces. Imports of internal submodules require an allowlist entry.

**Exception handling**

- **R10.** Allowlist (`import-linter-allowlist.yaml`) permits violations with documented justification and ticket reference. Monotonic-shrinking: entries may be removed on compliance, added only with justification and ticket reference.
- **R11.** Integration tests that must cross boundaries to verify system behavior are explicitly allowlisted by path or pattern.

**False-positive prevention**

- **R12.** Zero false positives against the existing test suite on first gate enablement. Boundary declarations use wildcard or regex patterns to avoid enumerating every internal implementation file.
- **R13.** Ambiguous cases (where intent cannot be determined) produce warnings, not violations, with resolution guidance.

**Operational model**

- **R14.** 2-week WARNING-only phase on CI before merge-blocking. Violations reported but not blocking.
- **R15.** Allowlist additions are self-serve: developer adds entry with justification + ticket reference, accepted by CI without separate review. Boundary config changes (adding/removing/modifying contracts) require PR review.
- **R16.** CI violation messages include the boundary rule violated and two remediation options: (a) move the import to a permitted module, or (b) add an allowlist entry with justification.
- **R17.** Check completes in under 30 seconds on CI hardware for the full codebase.

---

## Acceptance Examples

- **AE1 (R2, R4).** Given a boundary config declaring `core/ ⊥ router_v6/`, when a PR adds `from temper_placer.router_v6.astar_pathfinding import ...` inside `temper_placer/core/board.py`, the CI gate fails and the merge is blocked.
- **AE2 (R6).** Given a boundary config with declared contracts, when a PR removes one `independence` contract, the CI gate fails unless accompanied by a new allowlist entry with justification and ticket reference.
- **AE3 (R10).** Given an integration test at `packages/temper-placer/tests/integration/test_end_to_end.py` that imports from both `temper_placer.core` and `temper_placer.router_v6`, the test is allowed via the allowlist with justification "integration test -- verifies cross-module behavior" and ticket "temper-xxx -- reevaluate when router_v6/ extracted".
- **AE4 (R12).** Given the existing test suite with all current imports as-is, the initial boundary config produces zero violations so the CI gate is green on the first commit that enables it.

---

## Key Technical Decisions

### 1. `import-linter` over custom script

`import-linter` v2.0+ provides declarative YAML config and built-in contract types (`independence`, `forbidden`, `layers`) — the Python ecosystem's equivalent of ArchUnit. A custom checker would duplicate this and require ongoing maintenance. The package is actively maintained as of June 2026 and integrates with `uv run` in CI.

### 2. Ratchet via committed baseline (mirrors `.coverage-allowlist`)

The existing `.coverage-allowlist` pattern — a committed file that records pre-existing debt, which CI diffs against and only shrinks — is proven in this repo. `import-linter` natively supports a contracts-based model (declare what _should not_ happen), but the ratchet property is enforced via an additional baseline capture of the current import graph:

1. `import-linter.yaml` declares boundaries (what is forbidden / independent)
2. `import-linter-baseline.yaml` captures the import graph the first time the gate lands (so existing code that already crosses boundaries doesn't fail)
3. PR CI runs `import-linter` in report mode, diffs against baseline — new edges are violations unless allowlisted
4. When a violation is fixed, the edge is removed from baseline — the ratchet tightens

### 3. Separate allowlist file

`import-linter-allowlist.yaml` is a separate file from the baseline, consistent with `.coverage-allowlist` and `.loc-allowlist.txt` conventions. Each entry includes:

- The import path that is allowed
- Justification (why it's permitted)
- Ticket reference (linking to the issue that will remove it)
- The boundary rule it violates

Entries are added by developers directly (self-serve) and removed when the violation is fixed.

### 4. Seed boundaries: `core/ ⊥ router_v6/` + public interfaces

Not comprehensive coverage at launch. The seed set:
- `core/ ⊥ router_v6/` — the primary strangler-fig seam; neither may import from the other
- Public-interface contracts for `core/` and `router_v6/` — external packages may only import from `__init__.py` re-exports (which both already declare `__all__`)

Additional boundaries are added incrementally as more modules extract from the monolith.

### 5. Scripts default to allowlisted

Given 118 scripts with heterogeneous import patterns and no clear boundary home, they start in the allowlist and migrate out as they are audited. This avoids blocking existing workflows. The one-time audit classifies each script and files ticket-anchored entries.

### 6. Soft-launch: 2 weeks WARNING-only

The CI step initially reports violations as warnings (non-blocking) for 2 weeks. This gives developers time to fix existing violations and adjust workflows before the gate becomes merge-blocking. The soft-launch period is controlled by a config flag (`mode: warn` vs `mode: block`) in the workflow or in a wrapper script, with an explicit cutover date.

### 7. Allowlist expiry is ticket-driven, not date-driven

Consistent with `.coverage-allowlist` pattern: each entry links to a ticket. Expiry happens when the ticket is closed (violation fixed). No arbitrary date-based expiry that would cause surprise CI failures. The ticket reference is the reassessment trigger.

---

## Implementation Units

### U1. Install `import-linter` as workspace dev dependency

**Goal:** Add `import-linter` to the workspace `pyproject.toml` dev dependencies.

**Files:**
- `pyproject.toml` — add `"import-linter>=2.0"` to `[dependency-groups] dev`

**Verification:** `uv sync` installs `import-linter`; `uv run import-linter --help` succeeds.

### U2. Create boundary config (`import-linter.yaml`)

**Goal:** Declare `core/ ⊥ router_v6/` independence contract and public-interface contracts for `core/` and `router_v6/`.

**Files (new):**
- `import-linter.yaml` — repo root

**Config structure:**

```yaml
# import-linter boundary configuration
# Each contract names source modules and the constraints on their imports.

contracts:
  # R2: core/ and router_v6/ must not import from each other.
  - name: core-isolated-from-router-v6
    type: independence
    modules:
      - temper_placer.core
      - temper_placer.router_v6

  # R3: External packages may only import from core/ public interface (__init__.py).
  - name: core-public-interface-only
    type: forbidden
    source: temper_placer
    forbidden:
      - temper_placer.core.board
      - temper_placer.core.decision
      - temper_placer.core.loop
      - temper_placer.core.loop_extractor
      - temper_placer.core.loop_ownership
      - temper_placer.core.manufacturing
      - temper_placer.core.net_types
      - temper_placer.core.netlist
      - temper_placer.core.state
      - temper_placer.core.topology
      # ... additional core submodules not in __all__
    # Imports from temper_placer.core (the package, i.e., __init__.py) are allowed.
    # All individual submodule imports are forbidden.

  # R3: External packages may only import from router_v6/ public interface.
  - name: router-v6-public-interface-only
    type: forbidden
    source: temper_placer
    forbidden:
      - temper_placer.router_v6.adapter
      - temper_placer.router_v6.astar_pathfinding
      - temper_placer.router_v6.constraint_model
      - temper_placer.router_v6.dense_package_detection
      - temper_placer.router_v6.diff_pair_inference
      - temper_placer.router_v6.escape_drc_validator
      - temper_placer.router_v6.escape_via_generator
      - temper_placer.router_v6.length_group_inference
      - temper_placer.router_v6.length_matching
      - temper_placer.router_v6.obstacle_map
      - temper_placer.router_v6.pad_escape_classification
      - temper_placer.router_v6.routing_failure_handler
      - temper_placer.router_v6.safety_pair_inference
      - temper_placer.router_v6.stage0_data
    # Imports from temper_placer.router_v6 (the package, __init__.py) are allowed.
```

**Rationale for listing individual submodules:** `import-linter`'s `forbidden` contract requires explicit module names. Since `core/` and `router_v6/` both have well-defined `__all__` exports in their `__init__.py`, listing the individual submodules as forbidden ensures external callers use the public re-exports. The future option of wildcard patterns (e.g., `temper_placer.core.*` excluding `temper_placer.core`) depends on `import-linter` version support — evaluated during implementation.

**Verification:** `uv run import-linter` reports current violations (captured in baseline in U5).

### U3. Generate ratchet baseline (`import-linter-baseline.yaml`)

**Goal:** Capture the current import graph as a committed baseline so existing cross-boundary imports don't fail CI at gate launch.

**Files (new):**
- `import-linter-baseline.yaml` — repo root

**Approach:**
1. Run `uv run import-linter` in report-only mode, capturing all violations
2. Serialize current violations into `import-linter-baseline.yaml`
3. The baseline records each edge: `{source_module: ..., target_module: ..., contract_broken: ...}`

**Design note:** `import-linter` does not have a native "baseline" feature. The ratchet mechanism works via a diff-wrapper script (U5) that:
- Runs `import-linter --report-only` (or equivalent exit-code-suppressed mode)
- Captures the violation list
- Compares against committed `import-linter-baseline.yaml`
- New violations (present in report, absent from baseline) → fail
- Resolved violations (absent from report, present in baseline) → allowed (baseline shrinks on next push)
- Allowlisted violations (U6) → suppressed

The baseline format mirrors the violation report structure:
```yaml
# import-linter baseline — monotonically shrinking
# Each entry is a pre-existing violation admitted at gate launch.
# Entries are removed when the violation is fixed.
violations:
  - source: temper_placer.optimizer.train
    target: temper_placer.router_v6.adapter
    contract: router-v6-public-interface-only
    ticket: temper-xxx
```

**Verification:** With baseline in place, `uv run scripts/import_linter_gate.py` (U5) exits 0.

### U4. Create CI workflow step

**Goal:** Add import-linter gate to `python-tests.yml`.

**Files:**
- `.github/workflows/python-tests.yml` — add a new step after the "Vulture dead-code gate" step

**New step:**
```yaml
      - name: Import boundary enforcement
        run: uv run python scripts/import_linter_gate.py
```

Also add path trigger entries to the `on.push.paths` and `on.pull_request.paths` lists:
```
      - 'import-linter.yaml'
      - 'import-linter-baseline.yaml'
      - 'import-linter-allowlist.yaml'
      - 'scripts/import_linter_gate.py'
```

**Soft-launch mode:** During the 2-week WARNING period, the step exits 0 regardless of violations, printing violations as warnings. After the cutover date (hardcoded or config-driven), violations cause exit 1, blocking the merge.

**Verification:** Push to a PR branch; workflow step appears in CI and reports results.

### U5. Write diff-wrapper script (`scripts/import_linter_gate.py`)

**Goal:** Run `import-linter`, diff against baseline, apply allowlist, and enforce the ratchet.

**Files (new):**
- `scripts/import_linter_gate.py`

**Script logic:**
1. Run `uv run import-linter` in violation-reporting mode, capturing output
2. Parse violations from `import-linter` output (structured YAML/JSON)
3. Load `import-linter-baseline.yaml`
4. Load `import-linter-allowlist.yaml`
5. Compute:
   - `new_violations` = violations present in report but absent from baseline and absent from allowlist
   - `resolved_violations` = violations present in baseline but absent from report
6. If soft-launch mode (before cutover date): print all violations as warnings, exit 0
7. If block mode: exit non-zero on `new_violations` with R16-style remediation messages
8. Print `resolved_violations` as informational ("baseline shrunk — commit the updated baseline to ratchet")
9. Never fail on resolved violations (baseline shrinking is automatic on next PR that regenerates baseline)

**R16 compliance:** Each violation message includes:
- The boundary rule violated (contract name from `import-linter.yaml`)
- Option (a): "Move the import to a permitted module (e.g., use the public interface at `temper_placer.router_v6` instead of `temper_placer.router_v6.astar_pathfinding`)"
- Option (b): "Add an allowlist entry to `import-linter-allowlist.yaml` with justification and ticket reference"

**Verification:** Run locally with `uv run python scripts/import_linter_gate.py`; confirm violations are reported with remediation guidance.

### U6. Create allowlist file (`import-linter-allowlist.yaml`)

**Goal:** Monotonic-shrinking allowlist for justified exceptions.

**Files (new):**
- `import-linter-allowlist.yaml` — repo root

**Format:**
```yaml
# Import-linter allowlist — monotonically shrinking
# Format: Each entry permits a specific import violation.
# Entries may only be removed when the violation is fixed.
# Entries may only be added with justification and ticket reference.
# See docs/plans/2026-06-22-014-feat-import-linter-boundary-enforcement-plan.md

allowlist:
  # Script audit entries (U7 populates these)
  # - source: tools/spice/sim_runner.py
  #   target: temper_placer.router_v6.adapter
  #   contract: router-v6-public-interface-only
  #   reason: "Script imports router adapter for end-to-end simulation"
  #   ticket: temper-xxx

  # Integration test entries
  - source: packages/temper-placer/tests/integration/.*\.py
    target: temper_placer\.(core|router_v6)\..*
    contract: .*
    reason: "Integration tests verify cross-module behavior by design"
    ticket: temper-xxx
```

**Self-serve process:** Developers add entries directly in PRs. No separate review required for allowlist additions (R15). Boundary config changes (`import-linter.yaml`) require PR review.

**Verification:** Allowlist file is valid YAML and consumed by `import_linter_gate.py` (U5).

### U7. One-time script audit

**Goal:** Classify ~118 scripts in `tools/`, `scripts/`, `experiments/`, `simulation/`, `router-experiments/` into allowlist entries, then triage into a batch PR.

**Time estimate:** 2-3 hours (confirmed in origin document).

**Approach:**
1. Run `import-linter` in report-only mode across all non-package Python files
2. Capture the full import graph for every script
3. Categorize each script by its primary imports:
   - **Package public-interface users**: scripts that only import from `__init__.py` re-exports (e.g., `from temper_placer import Board`) — stay exempt via allowlist
   - **Internal submodule importers**: scripts that import from non-public submodules (e.g., `from temper_placer.router_v6.adapter import route_pcb`) — add to allowlist with ticket-anchored justification, or migrate to public-interface equivalents
4. Each script gets an allowlist entry with:
   - Source file path (regex pattern for directories with many scripts)
   - Target module pattern
   - Reason ("ad-hoc tooling — re-evaluate in temper-xxx")
   - Ticket reference

**Files changed:**
- `import-linter-allowlist.yaml` — populated with ~118 entries (or consolidated patterns)

**Verification:** With allowlist populated, `uv run python scripts/import_linter_gate.py` exits 0 with no new violations.

### U8. Local check documentation

**Goal:** Document the local pre-push check in the developer workflow.

**Files:**
- `AGENTS.md` — add a section under "Quick Reference" or "Daily Workflow"
- `AGENT_INSTRUCTIONS.md` — add a section on import boundary enforcement

**Content:**
```markdown
### Import Boundary Check

Before pushing, verify your changes don't violate import boundaries:

```bash
uv run python scripts/import_linter_gate.py
```

If violations are reported:
1. Check `import-linter.yaml` for the boundary contract violated
2. Option A: Move the import to a permitted module (use public `__init__.py` exports)
3. Option B: Add an allowlist entry to `import-linter-allowlist.yaml` with justification + ticket reference

The same check runs in CI. After the soft-launch period, violations block PR merge.
```

**Verification:** Documentation is clear, examples are correct.

### U9. Soft-launch configuration

**Goal:** Enable 2-week WARNING-only phase, then transition to merge-blocking.

**Files:**
- `scripts/import_linter_gate.py` — contains mode logic

**Implementation:**
- Hardcoded cutover date (e.g., `CUTOVER_DATE = datetime.date(2026, 7, 6)`) in the gate script
- Before cutover: `mode = "warn"` — print violations, exit 0
- After cutover: `mode = "block"` — print violations, exit non-zero on new violations
- A CI log message states: "Import boundary enforcement is in WARNING-only mode until {CUTOVER_DATE}. After that date, violations will block PR merge."
- On cutover date, a PR removes the soft-launch flag and the gate becomes blocking

**Verification:** Before cutover, a deliberate boundary violation (e.g., adding `from temper_placer.router_v6 import ...` to a core file) produces a CI warning but not a failure. After cutover (or with the date adjusted for testing), the same violation produces a CI failure.

---

## Files Changed Summary

| File | Action | Unit |
|------|--------|------|
| `pyproject.toml` | Modify — add `import-linter>=2.0` to dev deps | U1 |
| `import-linter.yaml` | **Create** — boundary config | U2 |
| `import-linter-baseline.yaml` | **Create** — ratchet baseline | U3 |
| `.github/workflows/python-tests.yml` | Modify — add CI step + path triggers | U4 |
| `scripts/import_linter_gate.py` | **Create** — diff-wrapper script | U5 |
| `import-linter-allowlist.yaml` | **Create** — monotonic-shrinking allowlist | U6, U7 |
| `AGENTS.md` | Modify — document local check | U8 |
| `AGENT_INSTRUCTIONS.md` (if exists) | Modify — document import boundary enforcement | U8 |

---

## CI Performance Budget

| Component | Target | Rationale |
|-----------|--------|-----------|
| `import-linter` analysis | <20s | AST-based, no runtime execution |
| Diff-wrapper overhead | <5s | YAML parsing + set comparison |
| Total gate runtime | <30s | R17 requirement |

The existing CI already runs `uv sync` and `ruff check` in prior steps; `import-linter` reuses the same installed environment with zero additional setup cost beyond the `uv sync` that already installs it (U1 adds it as a dev dependency resolved during the existing `uv sync --all-packages` step).

---

## Dependencies

- **No upstream blockers.** `import-linter` is a standalone PyPI package installable via `uv add`.
- **Composes with existing gates**: Runs alongside Vulture dead-code gate, Ruff lint, coverage gate — no conflicts.
- **Assumes `core/` and `router_v6/` import behavior** matches the intended architecture (core does not import from router_v6, router_v6 imports from core). Verified in the origin document as an assumption that "won't produce a deluge of violations on first run."
- **CI Python environment** is already provisioned by `uv sync --all-packages` in the existing workflow.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `import-linter` produces unexpected false positives on the existing codebase | Medium | High — blocks unrelated PRs | R12 (zero false positives on launch) enforced via initial baseline capture; soft-launch period provides buffer |
| Script audit takes longer than 2-3 hours | Low | Low — delays allowlist population | Scripts default to allowlisted (U7 step 4); gate still functional even if audit incomplete |
| `import-linter` doesn't support wildcard exclusion patterns needed for public-interface contracts | Medium | Medium — requires explicit enumeration | List individual submodules (32 for core, 14 for router_v6). Manageable. Can also use `import-linter`'s `ignore_imports` or `layers` contract as fallback |
| Developers ignore WARNING messages during soft-launch | High | Medium — surprise failures at cutover | CI log message states cutover date prominently; AGENTS.md documentation; announcement in team channel |
| 30-second target not met on first implementation | Medium | Low — not a hard constraint for launch | Profile and optimize (limit analysis to `packages/` only, skip `node_modules`-style dirs). Existing gates (ruff, vulture) already run in <30s as precedent |

---

## Success Criteria

1. A PR that adds `from temper_placer.router_v6.astar_pathfinding import ...` to a file in `temper_placer/core/` is blocked at CI with a message naming the violated boundary contract (AE1).
2. A PR that removes the `core-isolated-from-router-v6` independence contract without a corresponding allowlist entry is blocked (AE2).
3. The initial boundary config produces zero violations on the existing codebase — CI is green on the commit that enables the gate (AE4).
4. The boundary config and allowlist are human-readable: a developer can determine in under one minute whether a given import is allowed.
5. `uv run python scripts/import_linter_gate.py` completes in under 30 seconds on CI hardware (R17).
6. During the soft-launch period, violations do not block PRs. After cutover, they do.
7. Allowlist additions in developer PRs pass CI without separate review (R15 self-serve).

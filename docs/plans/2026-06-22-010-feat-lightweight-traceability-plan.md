---
title: "feat: Lightweight Requirements-to-Code Traceability Convention"
type: feat
status: active
date: 2026-06-22
origin: docs/ideation/2026-06-22-design-validation-ideation.md
---

# feat: Lightweight Requirements-to-Code Traceability Convention

## Summary

A minimal, opt-in, CI-gated convention that links plan requirement IDs (R1, R2, …) to the source code that implements them via inline `@req()` annotations. Today, after landing N1–N9, the repo has ten structured plans in `docs/plans/` defining ~80 requirements — but there is no mechanical connection between a requirement ID in a plan document and the `# lines of code that satisfy it. A developer who encounters `# @req(R4): HighCurrent.safety_category="HV"` at `packages/temper-drc/temper_drc/checks/safety/_safety_keywords.py:26` can navigate back to the plan that defines R4 without grep-guessing which plan owns it. A CI gate ensures that every claimed `@req` tag corresponds to a live requirement in a plan document (R2) and that every plan's non-deferred requirement has at least one code-site annotation (R3), making orphaned requirements and stale annotations both CI failures. The system starts empty — no mass-annotate pass — and grows file-by-file as each plan's implementation opts in.

---

## Problem Frame

### The missing link

Consider a developer reading `packages/temper-drc/temper_drc/checks/safety/_safety_keywords.py:26-28`, the `resolve_safety_category` helper that was added in the N4 plan (`docs/plans/2026-06-22-004-feat-net-class-rules-fields-plan.md`). N4 defines four implementation units (U1–U5) mapping to requirements R1–R7. The function implements R4 ("migrate the three safety checks to `safety_category` with keyword fallback") and R5 ("`TEMPER_NET_ASSIGNMENTS` remains the authoritative net→class map"). Today, a developer reading this function has **no local signal** connecting it to those requirements. They must:

1. Know that a plan for N4 exists.
2. Know the plan is named `2026-06-22-004-feat-net-class-rules-fields-plan.md`.
3. Guess that the function implements R4 specifically, not R1 or R2.

This is not hypothetical. The ten active plans (`docs/plans/2026-06-22-00{1..9}-feat-*-plan.md` plus `2026-06-22-011-*`) define a collective set of implementation units with cross-references stated only in prose (e.g., N4 `U4 Step 1` refers to the `resolve_safety_category` helper; no grep for `R4` hits that file). Over time, plan count grows, requirements accumulate, and the signal that "this line exists because R4 said so" is available only via git-blame archaeology — which degrades as code is refactored and lines shift.

### The cost

The same structural problem that the SSOT initiatives (N2, N4, N8) solve for *data* — config values, net-class fields, firmware constants — applies to *intent*. A developer refactoring `resolve_safety_category` cannot mechanically determine whether removing the `# allow-safety-constant:` comment pattern would violate a plan requirement, because the plan requirement is not referenced at the code site. The outcome is conservative "don't touch it" behavior that compounds technical debt, plus CI gates that catch data drift but not intent drift.

### Known drift patterns this system would surface

| Pattern | Existing example | How `@req` would surface |
|---------|-----------------|--------------------------|
| A requirement in a plan has no code at all | N4 R5 ("`TEMPER_NET_ASSIGNMENTS` remains the authoritative net→class map") — no dedicated implementation unit exists for R5; it's satisfied implicitly by U1 not touching the dict | R3 gate flags R5 as uncovered |
| Code claims a requirement that was deferred | If a developer writes `@req(R4)` for the N3 plan's Phase 2 expansion (deferred), the R2 gate fails | R2 gate rejects annotations for deferred requirements |
| Code claims a requirement from a plan that was later superseded | N3 Part A (U1, U2) was declared obsolete by a `ce-doc-review` finding (`docs/plans/2026-06-22-003-feat-dead-path-coverage-gate-plan.md:13-14`) | R2 gate rejects annotations for obsolete-plan requirements (plan has `status: needs-revision`) |

---

## Scope Boundaries

### In scope

- R1: Define a comment-based annotation convention (`# @req(<plan-id>, <req-id>): <optional note>`) in a specification checked into `docs/`, then implement the two CI gates below.
- R2: A CI gate (pytest-script pair) that parses `@req(<plan-id>, <req-id>)` annotations from every opted-in file in `packages/` and `firmware/`, then checks that every claimed `(plan-id, req-id)` pair exists as a live (non-deferred) requirement in the referenced plan document. Failure is a hard CI block.
- R3: A CI gate (same script, `--check-coverage` mode) that parses every plan document in `docs/plans/` with `status: active` and checks that every non-deferred requirement has at least one `@req` annotation in the opted-in codebase. Failure is a hard CI block.
- R4: The system is opt-in per-file via a committed directory-level `TRACEABILITY` marker. Only files in directories containing a `TRACEABILITY` file (an empty sentinel or a YAML manifest listing the plan ID the directory opts into) are scanned for `@req` annotations. No mass-annotate pass is required; adoption is incremental.
- The annotation convention specification lives at `docs/TRACEABILITY.md` (or `docs/specs/traceability.md`), referenced from `AGENTS.md` under the "Documentation & Context Maintenance" section.
- A GitHub Actions `paths:` filter extension so that edits to `docs/plans/` and `TRACEABILITY` marker files trigger the gate workflow (`python-tests.yml` lines 7–23).

### Deferred

- Annotation of existing code. The system starts with zero annotations and zero `TRACEABILITY` markers. Each plan's implementation is responsible for adding the markers and annotations as a follow-up unit — this plan delivers the *mechanism*, not the *content*.
- Cross-referencing between plans. A plan's R7 referencing another plan's requirement (e.g., N4 R5 depends on N2 U2's `TEMPER_NET_ASSIGNMENTS` assert) is out of scope. This system links plan→code, not plan→plan.
- UI/dashboard visualization of requirement coverage. The two CI gates are the UI.
- Annotation of `docs/` prose, `scripts/` tooling, or `tests/` files. The gate scans only `packages/` and `firmware/` source code. Tests are consumers of requirements, not implementations of them; scripts are build tooling.
- Annotation of plan-brainstorm requirement IDs. Only requirement IDs in `docs/plans/*.md` (with `status: active`) are recognized. Requirement IDs in `docs/brainstorms/` are planning-phase artifacts and not gated.
- Automatic annotation of all past plan requirements. N10 delivers the mechanism; a follow-up changeset (or per-plan changesets as part of each plan's U-phase) adds the annotations.
- Enforcing annotation format in plan documents themselves. Plan authors define requirements in prose today (no structured `R1:` block). Adding structured requirement lists to plan YAML frontmatter is a separate docs-tooling initiative; this system uses the current convention (bullet-list requirements starting with `- R<num>` lines in the "Requirements" or "Scope Boundaries" sections).

### Out of scope

- A pre-commit hook. The gate runs in CI only. Local enforcement is not required for initial adoption; developers can run `uv run pytest packages/temper-drc/tests/test_traceability_gate.py` locally.
- Dependency graph of requirements. This system maps requirement→code; it does not encode "R2 depends on R1" relationships (which live in plan docs' Implementation Units dependency fields today).
- Versioned requirements. Changing a requirement ID (e.g., renumbering) requires updating annotations — a mechanical find-and-replace. There is no migration system.

---

## Key Technical Decisions

**Annotation format: `# @req(<plan-id>, <req-id>): <note>` at line scope.** The convention uses a single-line comment (Python `#`, C `//`) with a structured tag that is machine-parseable, human-readable, and ignores existing comments. The `(plan-id, req-id)` tuple is the authoritative key; the note is free-form for human readers. Example:

```c
// @req(N4, R4): safety_category fallback with model-first resolution
const char* resolve_safety_category(const char* net_class_str) {
```

```python
# @req(N2, R3): AST linter rejects bare float literals matching authority values
if isinstance(node, ast.Constant) and isinstance(node.value, float):
```

The plan-id is the short form used in plan prose (e.g., `N4` for `docs/plans/2026-06-22-004-feat-net-class-rules-fields-plan.md`). The mapping from short plan-ids to filesystem paths is maintained in a committed registry file (see U1). The req-id is as defined in the plan document (e.g., `R4`). Multiple annotations per line are permitted (a line can implement multiple requirements). Multiple lines can carry the same annotation (a requirement implemented across multiple sites). The `@req` keyword was chosen over alternatives:
- `@requirement` — too long, visually heavy, easy to typo.
- `@implements` — ambiguous (implements a protocol? an interface?). 
- `@satisfies` — same ambiguity. 
- `@R4` — not parseable without context (R4 from which plan?). The tuple explicitly links plan and requirement.

**Plan-id registry: `docs/traceability-registry.yaml`.** A committed YAML file mapping short plan-ids to plan document paths and listing the file-level scopes each plan covers (origin directories):

```yaml
plans:
  N1:
    path: docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md
    scope:
      - packages/temper-drc/tests/test_root_hygiene.py
      - .github/workflows/python-tests.yml
      - scripts/add_power_planes.py
      - .gitignore
      - .github/workflows/python-tests.yml
  N2:
    path: docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md
    scope:
      - packages/temper-placer/temper_placer/core/design_rules.py
      - packages/temper-drc/tests/test_safety_constant_lint.py
      - packages/temper-drc/tests/test_safety_constant_reconciliation.py
      - packages/temper-drc/tests/safety_constant_overrides.yaml
  N4:
    path: docs/plans/2026-06-22-004-feat-net-class-rules-fields-plan.md
    scope:
      - packages/temper-placer/temper_placer/core/design_rules.py
      - scripts/generate_kicad_dru.py
      - packages/temper-drc/temper_drc/checks/drc/layer_assignment.py
      - packages/temper-drc/temper_drc/checks/safety/_safety_keywords.py
      - packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py
      - packages/temper-drc/temper_drc/checks/safety/creepage.py
      - packages/temper-drc/temper_drc/checks/safety/isolation.py
  # ... remaining plans
```

The `scope` field serves two purposes: (1) the R3 gate checks for `@req` annotations only in these files (a requirement implemented in a file not listed in its plan's scope is flagged as a mismatch); (2) the scope definition acts as the source-of-truth for which files a plan touches, which is currently implied by the plan's "System-Wide Impact" sections but not machine-readable. The registry is maintained by plan authors at plan-landing time — each plan's U-implementation includes an append to this registry. A separate gate (`--check-registry-scope`) validates that a plan's `scope` entries name files that actually exist and are tracked by git, and that every file in `scope` has a `TRACEABILITY` marker in its directory (R4 opt-in enforcement).

**Opt-in model: `TRACEABILITY` sentinel files.** A file named `TRACEABILITY` (empty or containing a YAML list of plan-ids the directory opts into) at the directory root signals that files under that directory participate in traceability. Only directories containing a `TRACEABILITY` file are scanned for `@req` annotations. This prevents the gate from scanning directories that have not yet opted in and avoids the need for a global `.traceability-ignore`. Example:

```
packages/temper-drc/temper_drc/checks/safety/TRACEABILITY
```
Contents (optional; empty file means "all active plans can be annotated here"):
```yaml
plans: [N2, N4]
```

When a `TRACEABILITY` file lists specific plan-ids, annotations referencing plans not in the list are flagged as violations (wrong-directory check). When the file is empty, any active plan's annotations are accepted. A `TRACEABILITY` file is at the directory level only — it covers all files recursively in that directory. There is no per-file opt-in.

This design was chosen over:
- A global allowlist file (too many entries, easy to forget to update).
- Per-file comment markers (too much noise — every file needs a header).
- Auto-discovery of all `.py`/`.c`/`.h` files (R4 requires gradual adoption; a mass scan would produce thousands of false positives for R3).

**Gate implementation: a standalone pytest, matching existing convention.** The two gates live as a single pytest file at `packages/temper-drc/tests/test_traceability_gate.py`, following the pattern established by N2's `test_safety_constant_lint.py` (`docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md:136-179`) and N1's `test_root_hygiene.py` (`docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md:172-233`). The test is collected by the existing `Run temper-drc tests` CI step (`.github/workflows/python-tests.yml:60-62`). The test reads the `docs/traceability-registry.yaml` registry, walks opted-in directories, parses `@req` annotations, and performs the R2 and R3 checks. A separate helper script at `scripts/check_traceability.py` provides CLI sugar for local runs (`uv run python scripts/check_traceability.py --check-annotations`, `--check-coverage`) but delegates to the same logic; the CI step invokes the pytest directly.

**Plan requirement parsing: regex over markdown prose, not structured YAML.** Today, plan documents define requirements in prose bullet lists (e.g., `- R1. A single canonical authority record...` at `docs/brainstorms/2026-06-21-safety-constant-ssot-requirements.md:79`). Converting all plans to structured YAML requirement blocks is a docs-tooling change that would touch ten files and is outside N10's scope. Instead, the R3 gate regex-parses each plan document for:
1. Lines matching `- R<num>.` or `- R<num>:` or `* R<num>` in sections named "Requirements" or "Scope Boundaries" (non-deferred set).
2. Sentences containing "Deferred" near a requirement ID (deferred set).
3. Plan status from YAML frontmatter (`status: active`, `status: needs-revision`, etc.).

This is brittle but sufficient for the current plan corpus. If plan authors want a requirement to be gated by R3, they write it in the standard prose format. The parser emits warnings for ambiguous cases (e.g., a requirement ID appears in a sentence but doesn't match the bullet pattern). A follow-up (`temper-xxx`, out of N10 scope) may add structured requirement blocks to plan YAML frontmatter; the regex parser is versioned in a comment at the top of `test_traceability_gate.py` documenting the expected format.

**Deferred requirements: excluded from R3, rejected by R2.** A requirement is deferred if the plan document marks it as deferred in the "Scope Boundaries" section (the standard pattern: "### Deferred" followed by bullet items referencing requirement IDs, e.g. `docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md:51-55`). The R3 gate excludes deferred requirements from the "must have at least one annotation" check. The R2 gate rejects annotations that reference a deferred requirement — if the plan explicitly deferred something, annotating code for it is incorrect (the code either shouldn't exist or is implementing a different plan's requirement).

**CI wiring: `paths:` filter extension.** The `.github/workflows/python-tests.yml` `paths:` filter (lines 7–13, 17–23) must trigger the workflow when plan documents or traceability registry files change. Add to both `push` and `pull_request` paths:
```yaml
paths:
  - 'docs/plans/**'
  - 'docs/traceability-registry.yaml'
  - '**/TRACEABILITY'
```
This ensures that adding a new plan, editing an existing plan, adding `TRACEABILITY` markers, or updating the registry all trigger the gate. Since `@req` annotations live in source files under `packages/` and `firmware/`, which are already covered by existing path filters, no annotation-specific filter is needed.

**No separate CI job.** The test lives in `packages/temper-drc/tests/` and runs in the existing `Run temper-drc tests` step (`.github/workflows/python-tests.yml:60-62`). No new workflow, no new job. The runtime is O(seconds) — parsing ~10 plan documents and scanning opted-in directories.

---

## Implementation Units

### Phase 1 — Convention specification and registry

### U1. Define the `@req` annotation convention and create the plan-id registry

**Goal:** Write the annotation convention specification, create the `docs/traceability-registry.yaml` mapping plan-ids to document paths and scope files, and document the convention in `AGENTS.md`.

**Requirements:** R1, R4

**Dependencies:** None

**Files:**
- `docs/TRACEABILITY.md` (new — the specification document)
- `docs/traceability-registry.yaml` (new — plan-id to path mapping)
- `AGENTS.md` (append a "Traceability Convention" section referencing `docs/TRACEABILITY.md`)

**Approach:**

1. **`docs/TRACEABILITY.md`** defines:
   - The `# @req(<plan-id>, <req-id>): <note>` format (Python/C comment syntax).
   - The `TRACEABILITY` sentinel file convention (empty or YAML with a `plans:` list).
   - The `docs/traceability-registry.yaml` schema and how to add a new plan.
   - The two CI gates (R2 annotation validity, R3 requirement coverage).
   - Examples showing real-world usage against the N4 plan's `resolve_safety_category` function.
   - The semantics: one line can carry multiple `@req` tags; one requirement can appear on multiple lines; annotations are informational at the line level and machine-checked at CI time.

2. **`docs/traceability-registry.yaml`** maps each of the ten active plans to its document path and file scope. The scope is derived from each plan's "System-Wide Impact" section. Initial population (from the existing plan corpus):

   - **N1** (`docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md`): `packages/temper-drc/tests/test_root_hygiene.py`, `scripts/add_power_planes.py`, `.gitignore`, `.github/workflows/python-tests.yml`, `.git-blame-ignore-revs`
   - **N2** (`docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md`): `packages/temper-placer/temper_placer/core/design_rules.py`, `packages/temper-drc/tests/test_safety_constant_lint.py`, `packages/temper-drc/tests/test_safety_constant_reconciliation.py`, `packages/temper-drc/tests/safety_constant_overrides.yaml`
   - **N3** (`docs/plans/2026-06-22-003-feat-dead-path-coverage-gate-plan.md`): `scripts/check_coverage_gate.py`, `.coverage-allowlist`, `.github/workflows/python-tests.yml`, `pyproject.toml`, `packages/temper-placer/tests/core/test_design_rules_unified.py`, `packages/temper-placer/temper_placer/core/design_rules.py`, `docs/architecture/ROUTER_V6_STEP_VALIDATION.md`
   - **N4** (`docs/plans/2026-06-22-004-feat-net-class-rules-fields-plan.md`): `packages/temper-placer/temper_placer/core/design_rules.py`, `scripts/generate_kicad_dru.py`, `packages/temper-drc/temper_drc/checks/drc/layer_assignment.py`, `packages/temper-drc/temper_drc/checks/safety/_safety_keywords.py`, `packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py`, `packages/temper-drc/temper_drc/checks/safety/creepage.py`, `packages/temper-drc/temper_drc/checks/safety/isolation.py`
   - **N5** (`docs/plans/2026-06-22-005-feat-duplicate-script-consolidation-plan.md`): to be populated at implementation time.
   - **N6** (`docs/plans/2026-06-22-006-feat-cli-zoning-loc-cap-plan.md`): to be populated at implementation time.
   - **N7** (`docs/plans/2026-06-22-007-fix-cython-twin-cleanup-plan.md`): to be populated at implementation time.
   - **N8** (`docs/plans/2026-06-22-008-feat-firmware-ssot-codegen-plan.md`): `firmware/config.yaml`, `firmware/tools/gen_config.py`, `firmware/tools/config.h.j2`, `firmware/tools/check_config_matches_manifest.py`, `firmware/config.h`, `firmware/main/state_machine.h`, `firmware/main/state_machine.c`, `firmware/CMakeLists.txt`, `firmware/main/CMakeLists.txt`, `firmware/test/CMakeLists.txt`, `firmware/test/test_state_machine.c`, `firmware/tools/requirements.txt`, `firmware/README.md`, `AGENTS.md`, `.github/workflows/firmware-tests.yml`
   - **N9** (`docs/plans/2026-06-22-009-feat-vulture-ruff-deadcode-gate-plan.md`): `scripts/vulture_gate.py`, `deadcode-baseline.py`, `.github/workflows/python-tests.yml`, `pyproject.toml`

   Each entry has:
   ```yaml
   N2:
     path: docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md
     scope:
       - packages/temper-placer/temper_placer/core/design_rules.py
       - ...
   ```

   The scope is populated at implementation time by reading each plan's "System-Wide Impact" section. Unpopulated entries (plans where the scope is uncertain at planning time) are left as `scope: []` with a `# TODO: populate at implementation time` comment.

3. **`AGENTS.md`** gains a new section after "Documentation & Context Maintenance" (line 260):

   ```
   ### Traceability Convention

   Inline `# @req(<plan-id>, <req-id>): <note>` comments link code to plan
   requirements. Two CI gates enforce consistency: every claimed @req tag must
   correspond to a live requirement in a plan document, and every plan's
   non-deferred requirement must have at least one code annotation — but only
   in directories that have opted in via a `TRACEABILITY` sentinel file.

   See `docs/TRACEABILITY.md` for the full specification.
   ```

**Patterns to follow:** `docs/plans/` existing markdown formatting. YAML style mirrors `safety_constant_overrides.yaml` (N2 U3). `AGENTS.md` section style matches existing subsections (e.g., "Transition Table Regeneration" at line 224).

**Test scenarios (manual verification at U1 landing):**
- `docs/TRACEABILITY.md` exists and is referenced from `AGENTS.md`.
- `docs/traceability-registry.yaml` is valid YAML (`python3 -c "import yaml; yaml.safe_load(open('docs/traceability-registry.yaml'))"`).
- Every `path` entry in the registry points to a file that exists on disk (verified by `scripts/check_traceability.py --check-registry-scope` — see U2).
- Every `path` entry has a corresponding plan document whose YAML frontmatter `status` is `active` (non-active plans can be in the registry but their requirements are excluded from R3 coverage).

---

### Phase 2 — CI gates

### U2. Implement the two traceability gate tests

**Goal:** A single pytest module at `packages/temper-drc/tests/test_traceability_gate.py` that implements: (a) R2 — validate every `@req(<plan-id>, <req-id>)` annotation against the plan document(s), and (b) R3 — check that every active, non-deferred requirement has at least one annotation in an opted-in file. A companion CLI script at `scripts/check_traceability.py` provides local-run convenience.

**Requirements:** R2, R3, R4

**Dependencies:** U1 (registry and specification must exist)

**Files:**
- `packages/temper-drc/tests/test_traceability_gate.py` (new — the CI gate test)
- `scripts/check_traceability.py` (new — CLI wrapper for local development)
- `.github/workflows/python-tests.yml` (extend `paths:` filters at lines 7–13 and 17–23)

**Approach:**

`test_traceability_gate.py` follows the pattern of `packages/temper-drc/tests/test_safety_constant_lint.py` (N2 U2, `docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md:136-179`) and `packages/temper-drc/tests/test_root_hygiene.py` (N1 U3, `docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md:172-233`). It is a single pytest module with two test functions:

**`test_req_annotations_valid` (R2 gate):**

1. Resolve repo root: `REPO_ROOT = Path(__file__).resolve().parents[3]` (as in `test_root_hygiene.py:188`).
2. Load `docs/traceability-registry.yaml` via `yaml.safe_load`.
3. Walk `packages/` and `firmware/` directories, checking for `TRACEABILITY` sentinel files. Collect all opted-in directories (those containing a `TRACEABILITY` file).
4. For each opted-in directory, glob all `.py`, `.c`, and `.h` files (recursively). For each file, read line-by-line and regex-extract every `@req(<plan-id>, <req-id>)` annotation.
   - Python regex: `r'#\s*@req\((\w+),\s*(\w+)\):?(.*)'` (captures plan-id, req-id, optional note).
   - C regex: `r'//\s*@req\((\w+),\s*(\w+)\):?(.*)'`.
5. For each `(plan-id, req-id)` pair found:
   - Look up plan-id in the registry. If not found → violation: `@req({plan_id}, {req_id}): plan-id '{plan_id}' is not in the traceability registry (docs/traceability-registry.yaml)`. This catches typos and references to plans that haven't been registered.
   - Verify the plan document at `registry[plan_id].path` has `status: active` in its YAML frontmatter. If not → violation: `@req({plan_id}, {req_id}): plan '{plan_id}' has status '{status}', expected 'active'. Superseded plans cannot carry live annotations.`
   - Parse the plan document for requirement IDs using the regex `r'^- R\d+\.'` or `r'^- R\d+:'` (bullet-list requirement definitions). Build a set of all requirement IDs defined in the plan.
   - Check if `req_id` is in the plan's defined requirements AND is not in the plan's deferred set (parsed from "Deferred" sections). If `req_id` is not found → violation: `@req({plan_id}, {req_id}): requirement '{req_id}' is not defined in {path}`.
   - If `req_id` is found but is deferred → violation: `@req({plan_id}, {req_id}): requirement '{req_id}' is deferred in {path}. Deferred requirements must not carry annotations.`
   - If `TRACEABILITY` file lists specific plan-ids and `plan_id` is not in the list → violation: `@req({plan_id}, {req_id}): plan-id '{plan_id}' is not in the directory's TRACEABILITY opt-in list. Add '{plan_id}' to the directory's TRACEABILITY file or move the annotation to the correct directory.`
   - If the annotated file is not in `registry[plan_id].scope` → warning (not failure): `@req({plan_id}, {req_id}) in {file}: file is not in plan '{plan_id}'s scope. Consider adding to docs/traceability-registry.yaml if this is a legitimate implementation site.` This is a warning, not a failure, because a plan may have implicitly touched files not listed in its System-Wide Impact section.
6. Assert `violations == []`. On failure, print each violation with file:line, annotation text, and reason.

**`test_req_coverage_complete` (R3 gate):**

1. Load `docs/traceability-registry.yaml`.
2. For each plan with `status: active`:
   - Parse the plan document for all requirement IDs (bullet-list `R<num>` patterns).
   - Parse the plan's "Deferred" sections for requirement IDs (exclude from coverage).
   - Build `required = {all_requirement_ids} - {deferred_requirement_ids}`.
   - For each requirement ID in `required`, check if at least one `@req({plan_id}, {req_id})` annotation exists in any opted-in file under a directory in `registry[plan_id].scope`.
   - If no annotation is found → violation: `{plan_id} R{num}: no @req annotation found in any opted-in file within plan scope. Requirement '{summary from plan}' is uncovered.`
3. Assert no uncovered requirements. On failure, print each uncovered requirement with plan-id, requirement ID, and the first line of the requirement prose from the plan document.

**Opt-in enforcement (R4):** Both gates skip files in directories that do not contain a `TRACEABILITY` sentinel. A directory with a `TRACEABILITY` file listing `plans: [N4]` only accepts `@req(N4, ...)` annotations; annotations for other plans are rejected (R2 violation). This prevents accidental cross-plan annotation sprawl.

**`scripts/check_traceability.py`** is a thin CLI wrapper that:
- Resolves the repo root.
- Delegates to the same logic in `test_traceability_gate.py` (importable, no pytest dependency for CLI mode).
- Supports `--check-annotations` (R2), `--check-coverage` (R3), `--check-registry-scope` (validates that every `path` in the registry exists and is git-tracked), `--all` (all three checks).
- Uses `argparse` and `rich.console.Console` per the `scripts/check_regression.py` convention.
- Exits 1 on failure, 0 on success.

**`paths:` filter extension in `.github/workflows/python-tests.yml`:**
Add to both `push` (lines 7–13) and `pull_request` (lines 17–23) paths blocks:
```yaml
paths:
  - 'packages/**'
  - 'tests/**'
  - 'scripts/**'
  - 'pyproject.toml'
  - '.github/workflows/python-tests.yml'
  - 'deadcode-baseline.py'
  - 'scripts/vulture_gate.py'
  - 'docs/plans/**'                       # <-- added
  - 'docs/traceability-registry.yaml'     # <-- added
  - '**/TRACEABILITY'                     # <-- added
```

**Deferred-requirement parsing heuristic.** The R3 gate determines which requirements are deferred by parsing the plan's "Scope Boundaries" section. The heuristic:
1. Locate the `### Deferred` or `## Deferred` heading.
2. Read all bullet items and prose until the next heading of equal or higher level.
3. Extract all requirement IDs (`R<num>`) mentioned in the deferred section.
4. If a requirement ID appears only in the deferred section and not in any "In scope" or "Requirements" section, it is assumed fully deferred. If it appears in both, the plan is ambiguous — emit a warning and treat it as non-deferred (conservative: failures are better than silent gaps).

This heuristic is documented in `test_traceability_gate.py`'s module docstring as a known limitation. A follow-up (`temper-xxx`) may add explicit `deferred: true` fields to plan YAML frontmatter.

**Patterns to follow:** `packages/temper-drc/tests/test_safety_constant_lint.py` (pytest structure, `ast.walk` approach, failure message format). `scripts/check_regression.py` (argparse + rich console). `test_root_hygiene.py:188` (`Path(__file__).resolve().parents[3]` for repo-root resolution). `safety_constant_overrides.yaml` (YAML schema pattern for the registry).

**Test scenarios:**
- **R2 gate with empty registry and no annotations:** Both gates pass (no violations, no uncovered requirements since no opted-in directories exist).
- **R2 gate with a valid annotation:** Add `TRACEABILITY` to `packages/temper-drc/temper_drc/checks/safety/`. Add `# @req(N4, R4): safety_category fallback` to `_safety_keywords.py`. The R2 gate passes.
- **R2 gate with an invalid plan-id:** `# @req(N99, R4)` in an opted-in file → violation: plan-id `N99` not in registry.
- **R2 gate with a valid plan-id but invalid req-id:** `# @req(N4, R99)` → violation: requirement `R99` not defined in the N4 plan.
- **R2 gate with a deferred requirement:** `# @req(N3, R8)` (N3 R8 Phase 2 is deferred) → violation: requirement `R8` is deferred.
- **R2 gate with a superseded plan:** If N3's status becomes `needs-revision`, `# @req(N3, R5)` → violation: plan status is `needs-revision`.
- **R2 gate with a valid annotation in a non-opted-in directory:** A `@req` annotation in a directory without `TRACEABILITY` is silently ignored — the line is not scanned.
- **R2 gate cross-plan annotation in a scoped directory:** A `TRACEABILITY` file listing `plans: [N4]` rejects `# @req(N2, R3)` (N2 not in the list) → violation.
- **R3 gate with a covered requirement:** N4 R4 has `@req(N4, R4)` in `_safety_keywords.py` → R3 gate passes for N4 R4.
- **R3 gate with an uncovered requirement:** If N4 R5 has no `@req` annotation in any opted-in file → violation: `N4 R5: no @req annotation found. Requirement 'TEMPER_NET_ASSIGNMENTS remains the authoritative net→class map' is uncovered.`
- **R3 gate skips deferred requirements:** N3 Phase 2 requirements (R8) are excluded from coverage.
- **R3 gate skips non-active plans:** Plans with `status: needs-revision` are not scanned for uncovered requirements.
- **R2 gate with annotation outside plan scope:** `# @req(N4, R4)` in `packages/temper-placer/temper_placer/router_v6/pipeline.py` (not in N4 scope) → warning (not failure): file not in plan scope.
- **`--check-registry-scope` mode:** Validates that every `path` entry in the registry maps to a file tracked by git. Flags entries pointing to non-existent or deleted files.

**Verification:**
- `uv run pytest packages/temper-drc/tests/test_traceability_gate.py` passes on the current tree (no annotations, no `TRACEABILITY` markers → both gates pass vacuously).
- Creating a `TRACEABILITY` file, adding a valid annotation, and re-running passes.
- Adding an invalid annotation (wrong plan-id, wrong req-id, deferred req) causes the R2 gate to fail with a named violation.
- `uv run python scripts/check_traceability.py --all` exits 0 on the current tree.

---

### Phase 3 — CI wiring and documentation

### U3. Wire the gate into CI and document the workflow

**Goal:** The R2 and R3 gates run in CI on every push and PR; the workflow is documented in `AGENTS.md` and `docs/TRACEABILITY.md`.

**Requirements:** R2, R3 (CI integration)

**Dependencies:** U2 (test file must exist)

**Files:**
- `.github/workflows/python-tests.yml` (extend `paths:` filter — done in U2; no other changes needed as the test is collected by the existing `Run temper-drc tests` step at lines 60–62)
- `AGENTS.md` (already updated in U1; verify reference to `docs/TRACEABILITY.md`)
- `docs/TRACEABILITY.md` (already written in U1; verify it documents the CI gate behavior)

**Approach:**

No additional CI wiring is required beyond the `paths:` filter extension performed in U2. The `test_traceability_gate.py` file is in `packages/temper-drc/tests/`, which is collected by the existing `Run temper-drc tests` step (`.github/workflows/python-tests.yml:60-62`) that runs `uv run pytest tests/ -v --tb=short` with `working-directory: packages/temper-drc`. The `paths:` extension ensures the workflow triggers when plan documents, the registry, or `TRACEABILITY` markers change.

The `AGENTS.md` and `docs/TRACEABILITY.md` entries written in U1 are verified for completeness. The `AGENTS.md` reference is self-documenting; a developer who encounters a `@req` annotation in code can trace back to the specification.

**Patterns to follow:** Existing CI step format (`.github/workflows/python-tests.yml:60-62`). `AGENTS.md` section style.

**Test scenarios:**
- A PR adding a valid `@req` annotation: the `Run temper-drc tests` step runs the gate; the gate passes.
- A PR adding an invalid `@req` annotation: the step fails with a named violation in the CI log.
- A PR editing a plan document to add a new requirement without adding an annotation: the R3 gate fails, naming the uncovered requirement.
- A PR adding a `TRACEABILITY` marker: the workflow triggers (via the new `**/TRACEABILITY` path filter); the gate runs and the new directory is scanned.

---

## System-Wide Impact

- **`docs/TRACEABILITY.md`:** New specification document. Referenced from `AGENTS.md`. Defines the annotation convention, the `TRACEABILITY` sentinel pattern, the registry schema, and the CI gates.
- **`docs/traceability-registry.yaml`:** New committed registry mapping short plan-ids (`N1`–`N10`) to plan document paths and file-level scopes. Maintained by plan authors; validated by `--check-registry-scope`.
- **`packages/temper-drc/tests/test_traceability_gate.py`:** New CI gate test. Runs in the existing `Run temper-drc tests` step. Implements R2 (annotation validity) and R3 (requirement coverage).
- **`scripts/check_traceability.py`:** New CLI wrapper for local development. Follows the `scripts/check_regression.py` argparge+rich pattern.
- **`AGENTS.md`:** Gains a "Traceability Convention" section referencing `docs/TRACEABILITY.md` (appended after line 260, "Documentation & Context Maintenance").
- **`**/TRACEABILITY` (future files):** Opt-in sentinel files placed in directories by plan implementers. Empty by default; may contain a `plans: [N4]` list for scoped directories. Not created by this plan — each plan's future annotation follow-up creates them.
- **`.github/workflows/python-tests.yml`:** `paths:` filter extended with `'docs/plans/**'`, `'docs/traceability-registry.yaml'`, and `'**/TRACEABILITY'`. No new CI step or job.
- **`.` (repo root):** No new root-level files. The convention spec and registry live in `docs/`. The gate test lives in `packages/temper-drc/tests/`.
- **Existing code:** No changes. This plan delivers the mechanism; annotations are added in follow-up changesets.

### Developer workflow

1. **A developer working on a new plan** adds the plan to `docs/traceability-registry.yaml` (mapping plan-id to path and scope) as part of the plan's implementation.
2. **When implementing a requirement**, the developer places a `TRACEABILITY` sentinel in the directory (if none exists) and annotates the implementing code with `@req(<plan-id>, <req-id>): <note>`.
3. **CI catches** invalid annotations (reference to non-existent or deferred requirements) and uncovers requirements that were supposed to be implemented but lack annotations.
4. **A developer reading code** sees `@req(N4, R4)` and can jump to `docs/plans/2026-06-22-004-feat-net-class-rules-fields-plan.md` to understand the requirement context.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Plan requirement IDs change (renumbering during plan revisions) and annotations become stale | Medium | Medium | The R2 gate catches stale annotations (requirement ID not found in the plan). Renumbering requires a mechanical update of existing annotations — a find-and-replace that the plan author performs as part of the revision. The gate fails until all annotations are updated, which is the correct behavior (it surfaces the drift). |
| A plan's "Deferred" section uses prose formatting that the regex parser misreads, causing deferred requirements to be treated as covered (or vice versa) | Medium | Medium | The parser is conservative: it only identifies a requirement as deferred if it appears in a section headed `### Deferred` or `## Deferred`. If a plan uses different heading text or a different structure, the requirement is treated as non-deferred — a false positive (R3 gate fails for a requirement that is actually deferred), not a false negative. Document the expected format in `docs/TRACEABILITY.md` so plan authors know the contract. A follow-up (`temper-xxx`) may add structured `deferred_requirements:` to plan YAML frontmatter. |
| The `TRACEABILITY` sentinel model produces a scattered set of empty files across directories, cluttering `ls` output | Low | Medium | Sentinels are one per *directory*, not one per file. The maximum number of sentinels equals the number of opted-in directories, which is bounded by the number of source directories. The `N2` plan alone consolidated 4 registries into `_safety_keywords.py` — the number of directories is small and shrinking. If sentinel count becomes excessive, consolidate to a single `TRACEABILITY` file at the package root with per-directory overrides. |
| The gate script's regex for plan requirement parsing is brittle against plan format evolution | Medium | Medium | The regex is versioned in a code comment at the top of `test_traceability_gate.py`. If plan formats change, the regex is updated in the same PR. A separate test (`test_traceability_gate_parser.py`) can be added to validate against a golden set of expected outputs for each plan document — deferred to implementation. |
| Adding annotations increases line count and diff noise without changing behavior | Low | High | Accepted. The annotations are comment-only lines that add no runtime overhead. In-code annotations are analogous to docstrings — they communicate intent to readers and to CI. The value (navigable traceability) is deferred until annotations accumulate, which is the opt-in model's design. |
| A developer annotates a line that is later refactored or deleted; the annotation is lost and the R3 gate flags the requirement as uncovered | Medium | Medium | This is a feature, not a bug. If a refactor deletes the line implementing a requirement, the requirement *is* uncovered until the refactor adds an annotation at the new location. The R3 gate surfaces this. If the refactor correctly preserves the requirement implementation at a new location, the developer adds the annotation there in the same changeset. |
| The registry's `scope` field becomes stale as plans' file lists change | Medium | Medium | `--check-registry-scope` validates that all `scope` entries point to existing, git-tracked files. It does not catch missing files (a plan that newly touches a file but hasn't added it to scope). The R2 gate's warning for annotations outside scope provides a secondary signal. The `scope` field is advisory for the R3 coverage check; it is not the source-of-truth for which files contain annotations. |
| CI runtime increases as opted-in directories grow | Low | Low | Even with all directories opted in, the annotation scan is a regex over source files — comparable in cost to a `ruff` lint pass. The plan document parser reads ~10 documents totaling <200 KiB. Total runtime is well under 5 seconds for the full tree. |
| A `TRACEABILITY` sentinel file in a top-level directory (e.g., `packages/`) opts in the entire packages tree prematurely, before annotations are ready | Low | Medium | The R2 gate checks annotations individually; an annotation for a non-existent or deferred requirement fails. Opting in a large tree without adding annotations produces R3 failures (uncovered requirements) — the gate surfaces the gap rather than silently tolerating it. The developer can either add annotations or remove the sentinel. No silent bypass. |

---

## Test Strategy

- **U1 (spec and registry):** Manual verification: `docs/TRACEABILITY.md` exists and is syntactically valid markdown. `docs/traceability-registry.yaml` is valid YAML and every `path` entry points to an existing file. `AGENTS.md` contains a reference to `docs/TRACEABILITY.md`. `scripts/check_traceability.py --check-registry-scope` passes (all scope entries resolve to git-tracked files).
- **U2 (gate tests):** The test functions themselves are the verification. Test scenarios (documented in U2 above) cover: empty state (no annotations, no sentinels → pass), valid annotations (pass), invalid plan-id (fail), invalid req-id (fail), deferred requirement (fail), superseded plan (fail), uncovered requirement (fail), non-opted-in annotation (silently ignored), cross-plan annotation in scoped directory (fail). Each scenario is verified by creating a temporary file structure within the pytest (using `tmp_path` and monkey-patched `REPO_ROOT`) — the gate tests test themselves against synthetic inputs. Integration verification: creating a real `TRACEABILITY` file and `@req` annotation in the repo and running `uv run pytest packages/temper-drc/tests/test_traceability_gate.py` passes/fails as expected.
- **U3 (CI wiring):** The `Run temper-drc tests` step already collects `packages/temper-drc/tests/`. The `paths:` filter extension is verified by observing that a PR touching only `docs/plans/` triggers the workflow. The CI step log shows the traceability gate running (pytest test name in output).
- **Regression:** The existing `packages/temper-drc/tests/` suite continues to pass. The new test file is additive. No existing tests are modified. The `Run temper-placer tests (core only)`, `Run temper-workflow tests`, and `Run temper-tools tests` steps are unchanged.
- **Edge cases:**
  - A file with a `@req` annotation but no `TRACEABILITY` sentinel in any parent directory: the annotation is silently ignored (R4 — no opt-in, no scan). The R3 gate does not count the annotation as coverage, which is correct (the directory hasn't opted in).
  - A `TRACEABILITY` file in a directory that is not in any plan's scope: the directory is scanned for annotations, but the R3 gate's coverage check only looks in scope directories. Annotations in non-scope directories are validated by R2 but don't count toward R3 coverage. This is correct — a plan's requirement should be implemented in its scope files.
  - Multiple `@req` annotations on the same line: each is independently validated.
  - A `@req` annotation in a C header file: recognized via `// @req(...)` regex.
  - An annotation with whitespace variations: `# @req(N4,R4)`, `# @req( N4 , R4 )`, `# @req(N4, R4): some note` — all recognized by the regex with optional whitespace.
  - A requirement that appears in both "In scope" and "Deferred" (ambiguous plan): the parser treats it as non-deferred (conservative), so R3 expects an annotation. The R2 gate accepts annotations for it (since it appears in "In scope"). This is the safe default: an ambiguous requirement is assumed to need implementation.

---

## Deferred to Implementation

- **Populating `docs/traceability-registry.yaml` scope fields for N5, N6, N7.** These plans' System-Wide Impact sections must be read and their scope files enumerated. This is mechanical work (~10 minutes per plan) deferred to implementation time. Leave `scope: []` with a `# TODO` comment for now.
- **Regex tolerance for plan document variations.** The current plan corpus uses consistent `- R<num>.` bullet formatting for requirements and `### Deferred` for deferred sections. If a future plan uses a different format, the regex is extended. The implementation-time decision is whether to add a `test_traceability_gate_parser.py` that validates the regex against each existing plan document's golden expected output — this catches format drift early. Recommend adding it.
- **Annotation of existing N1–N9 code.** Each plan's follow-up changeset adds `TRACEABILITY` markers and `@req` annotations. This is separate work, not part of N10. The N10 plan delivers the gates; annotations are a per-plan unit.
- **`--check-registry-scope` CI wiring.** Currently scoped as a CLI-only mode for local development. Wiring it into CI as a separate step in `.github/workflows/python-tests.yml` is a one-line addition deferred to implementation time (confirm whether the `paths:` filter triggers it on registry edits).
- **Structured requirement blocks in plan YAML frontmatter.** The regex parser is a bridge solution. A follow-up `temper-xxx` may add `requirements: [{id: R1, summary: "...", deferred: false}]` to plan YAML frontmatter, making the parser trivial and the registry redundant for requirement discovery. This is not N10 scope.
- **`TRACEABILITY` file format with plan-id scoping.** The spec supports YAML content in `TRACEABILITY` files (`plans: [N4]`). The implementation may defer the plan-id-scoping logic to a follow-up if the initial adoption is small enough that the simpler "empty file = all plans" model suffices. The gate implementation includes the scoping check from day one (failing closed); the spec documents both modes.
- **Per-line vs. per-function annotation granularity.** The convention is per-line. If the community prefers per-function annotations (e.g., a single `@req` in the function docstring covering the entire function body), the spec can be extended without changing the gate logic (a regex on the docstring is still a regex on a line). This is a convention choice, not an implementation change.

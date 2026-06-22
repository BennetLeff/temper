---
date: 2026-06-21
topic: dead-path-coverage-gate
---

# Dead-Path Re-enablement and Exercise-or-Delete Coverage Gate

## Summary

A two-part hardening initiative. **Part A** re-enables the dead `export_design_rules` / `import_design_rules` / `load_design_rules` round-trip path in `packages/temper-placer/temper_placer/core/design_rules.py`, which is currently broken (reads nonexistent `_mm`-suffixed fields, passes nonexistent kwargs) and masked by a silent fallback to `create_temper_design_rules()` on missing files. The fix is verified by a round-trip property test using **real `DesignRules` instances**, not `Mock` objects — the existing test mocks the very fields the bug hides in. **Part B** adds a CI coverage gate that fails any public function with zero dynamic coverage, forcing either an exercising test or a deletion. The gate ships with a ticketed allowlist so the initial baseline does not block the merge, and shrinks over time.

Part A is the pilot that proves the gate's value: the dead path was "covered" by a Mock-based test that exercised none of the real dataclass contracts.

---

## Problem Frame

Three functions in `design_rules.py` form a serialization round-trip that has never worked:

- `export_design_rules` (lines 789–814) reads `rules.default_clearance_mm`, `rules.default_trace_width_mm`, `nc.clearance_mm`, `nc.trace_width_mm`. The `DesignRules` dataclass (line 173) declares `default_clearance`, `default_trace_width`; `NetClassRules` (line 114) declares `clearance`, `trace_width`. Any real call raises `AttributeError`.
- `import_design_rules` (lines 817–843) passes `clearance_mm=`, `trace_width_mm=`, `default_clearance_mm=`, `default_trace_width_mm=` to the dataclass constructors. None of these kwargs exist. Any real call raises `TypeError`.
- `load_design_rules` (lines 712–736) calls `import_design_rules` on the YAML-parsed dict, but wraps it in a `try/except Exception` that converts the `TypeError` into a `ValueError`, and additionally short-circuits missing files to `create_temper_design_rules()` (line 726) — so the broken path is never reached in production.

The existing test `tests/core/test_design_rules_unified.py::test_rule_export_import_for_debugging` (lines 108–126) constructs `Mock()` objects and sets `original_rules.default_clearance_mm = 0.5` and `nc.clearance_mm = 0.5` — i.e. it mocks the **wrong field names the bug produces**, so the test passes while the real function is broken. A second test, `test_rule_loading_error_handling` (lines 149–161), asserts `load_design_rules("nonexistent_file.yaml")` raises `FileNotFoundError`, but the implementation returns defaults instead — the test is wrong against the code, and the suite does not catch this because the silent fallback means the test never reaches the assertion path the test author intended.

Stepping back, the codebase has **784 public functions in `temper-placer` alone** (455 Python source files) and no coverage configuration in `pyproject.toml`, no `--cov` flag in `.github/workflows/python-tests.yml`, and no `fail-under` gate. `pytest-cov` is listed as a dev dependency in `temper-placer` and `temper-drc` but is never invoked. CI runs only `tests/core/` for the placer package. The combination means: a function can be entirely unexercised, or exercised only by Mock-based tests that validate no real contract, and nothing in CI notices. The dead round-trip path is the canonical example — it survived the June 2026 clean-base sprint.

This initiative converts "first real use reveals the bug" into "CI reveals the bug," and makes the absence-of-tests condition structural rather than opportunistic.

---

## Actors

- A1. **Developer** — writes or modifies public functions in `packages/*/src` and `packages/*/temper_placer`. Either adds a test or deletes the function when the gate fires.
- A2. **CI pipeline** — runs pytest with `--cov`, computes per-function coverage, diffs against the allowlist, fails on any new zero-coverage public function not on the allowlist.
- A3. **Triage maintainer** — owns the allowlist; files removal tickets; approves additions only with a ticket reference.

---

## Key Flows

- F1. **Developer fixes the dead round-trip path**
  - **Trigger:** A1 lands the Part A changeset.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 corrects the field names in `export_design_rules` and `import_design_rules` to match the dataclass declarations (`default_clearance`, `clearance`, etc.). (2) A1 removes the `if not path.exists(): return create_temper_design_rules()` fallback in `load_design_rules`, replacing it with `FileNotFoundError`. (3) A1 rewrites `test_rule_export_import_for_debugging` to construct a real `DesignRules` instance via `create_temper_design_rules()` and assert round-trip equality on every field. (4) A1 rewrites `test_rule_loading_error_handling` to assert that `load_design_rules` on a missing path raises `FileNotFoundError` (matching the new behavior, not the old test's intent). (5) A2 runs CI: the round-trip test exercises the real path; the Mock-masking pattern is gone.
  - **Outcome:** `export_design_rules(import_design_rules(export_design_rules(rules))) == export_design_rules(rules)` for the real `DesignRules` instance. A missing file is a `FileNotFoundError`, not a silent default.
  - **Covered by:** R1, R2, R3

- F2. **CI detects a new unexercised public function**
  - **Trigger:** A1 adds a public function to a module in the gate's scope and pushes without a test.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 pushes the branch. (2) A2 runs the coverage step: `pytest --cov=<package> --cov-report=json`. (3) A post-coverage script computes the set of public functions with zero executed lines, subtracts the allowlist, and fails if the diff is non-empty. (4) The failure message names each uncovered function with `file:line` and links to the allowlist-removal workflow.
  - **Outcome:** A1 either adds a test that invokes the function, adds the function to the allowlist with a ticket reference, or deletes the function. "Silently unexercised" is not an available state.
  - **Covered by:** R4, R5, R6

- F3. **Triage maintainer shrinks the allowlist**
  - **Trigger:** Recurring maintenance cadence or a sprint focused on hardening.
  - **Actors:** A3, A2
  - **Steps:** (1) A3 picks an allowlist entry, writes a test or deletes the function, removes the entry. (2) A2 runs CI: the gate must still pass. (3) If the entry cannot be removed (function is genuinely dead code), A3 deletes the function instead — the gate's purpose is exercise-or-delete, not exercise-or-allowlist-forever.
  - **Outcome:** The allowlist monotonically shrinks; dead code is deleted, not archived.
  - **Covered by:** R6, R7

---

## Requirements

**Part A — Dead path re-enablement (pilot)**

- R1. `export_design_rules` reads `rules.default_clearance`, `rules.default_trace_width`, `nc.clearance`, `nc.trace_width` — the actual dataclass field names. The emitted dict keys remain `default_clearance_mm` / `clearance_mm` (the serialization format is unchanged; only the source attribute access is corrected). A typo in this mapping is a test failure, not a runtime `AttributeError`.
- R2. `import_design_rules` passes `clearance=`, `trace_width=`, `default_clearance=`, `default_trace_width=` to the dataclass constructors — the actual kwargs. A round-trip property test asserts `import_design_rules(export_design_rules(rules))` reproduces every field of `rules` for the `create_temper_design_rules()` instance, including all net classes. The test uses a real `DesignRules` instance; `Mock` is not permitted as the primary argument for any assertion in this test file.
- R3. `load_design_rules` raises `FileNotFoundError` when `rules_path` does not exist. The silent fallback to `create_temper_design_rules()` is removed. The `try/except Exception` around `import_design_rules` is narrowed to `yaml.YAMLError` only — a `TypeError` from a malformed dict propagates as a test failure, not a `ValueError` that masks it. The existing `test_rule_loading_error_handling` is updated to match the new contract and uses a real temp file path, not a `patch("builtins.open")` mock.

**Part B — Exercise-or-delete coverage gate**

- R4. A coverage configuration block is added to `pyproject.toml` (`[tool.coverage.run]` with `branch = true`, source set to the gated packages, and `[tool.coverage.report]` with `show_missing = true`). The CI workflow runs `pytest --cov` with `--cov-report=json` for each gated package and emits a machine-readable coverage data file.
- R5. A post-coverage gate script (invoked from CI) computes the set of **public functions** (module-level `def` not prefixed with `_`, and methods of public classes not prefixed with `_`) with **zero executed lines** in the coverage report. The script subtracts the allowlist and fails CI if the diff is non-empty. The failure message lists each uncovered function as `package/module.py:line def_name` and includes a link to the allowlist-removal workflow documented in `CLAUDE.md`. The gate uses **line coverage** (zero executed lines) as its signal — not branch coverage, not assertion presence. The Mock-masking problem from Part A is addressed by R2's real-instance requirement at the test-quality layer, not by the coverage gate; the gate's job is to catch functions that are *never entered at all*.
- R6. The gate's initial scope is `packages/temper-placer/temper_placer/core/` only — the module containing the Part A bug and the highest-value pilot target. Expansion to additional packages is phased (see R8). The allowlist is a committed file (e.g. `.coverage-allowlist`) listing `package/module.py::function_name` entries, each with a trailing comment referencing a removal ticket (`# TODO: temper-xxx`). The allowlist is populated automatically on first run by the gate script's `--init` mode: every zero-coverage public function in scope is written to the file with a placeholder ticket. Additions to the allowlist after initial population require a ticket reference in the commit message and fail CI otherwise.
- R7. The allowlist monotonically shrinks. A separate CI check (or a gate-script subcommand) fails if an entry is removed without either (a) a test covering the function appearing in the same PR, or (b) the function being deleted in the same PR. Adding to the allowlist without a ticket and removing without test-or-deletion are both CI failures.

**Phasing**

- R8. **Phase 1** lands Part A and the gate scoped to `temper-placer/temper_placer/core/`. **Phase 2** expands the gate to all of `temper-placer/temper_placer/`. **Phase 3** expands to `packages/temper-drc/`, `packages/temper-tools/`, `packages/temper-workflow/`. Each phase begins with an `--init` run that repopulates the allowlist for the newly-scoped modules. A phase lands only when the prior phase's allowlist has shrunk by at least 50% (measured by entry count) — the gate does not sprawl faster than the codebase can pay down debt.

---

## Acceptance Examples

- AE1. **Covers R1, R2.** Given `rules = create_temper_design_rules()`, when `exported = export_design_rules(rules)` then `imported = import_design_rules(exported)`, then `export_design_rules(imported) == exported` and `imported.default_clearance == rules.default_clearance` for every net class. The test uses no `Mock`. A developer who reintroduces the `_mm` suffix in `export_design_rules` sees this test fail with `AttributeError: 'DesignRules' has no attribute 'default_clearance_mm'`.
- AE2. **Covers R3.** Given `load_design_rules("nonexistent.yaml")` is called, when the path does not exist, then `FileNotFoundError` is raised — not a silent return of `create_temper_design_rules()`. The `try/except` no longer catches `TypeError`; a malformed YAML dict that would cause `import_design_rules` to raise `TypeError` propagates the `TypeError`, not a wrapped `ValueError`.
- AE3. **Covers R5.** Given a developer adds `def new_helper(): ...` to `temper-placer/temper_placer/core/design_rules.py` and pushes without a test, when CI runs the coverage gate, the gate fails with `design_rules.py:NNN new_helper — zero coverage (not on allowlist; see CLAUDE.md §Coverage Gate)`. The developer adds a test, deletes the function, or adds an allowlist entry with a ticket.
- AE4. **Covers R6.** Given the gate is run in `--init` mode against `temper-placer/temper_placer/core/` for the first time, the script writes `.coverage-allowlist` with every zero-coverage public function in that directory, each with a `# TODO: temper-xxx` placeholder. CI passes on this commit. A subsequent commit that adds a new uncovered function without an allowlist entry fails.
- AE5. **Covers R7.** Given an allowlist entry `design_rules.py::export_design_rules` is removed in a PR, when CI runs, the gate checks that the same PR either adds a test exercising `export_design_rules` or deletes the function. If neither, CI fails: `allowlist entry removed without test or deletion: export_design_rules`.

---

## Success Criteria

- `export_design_rules` → `import_design_rules` → `export_design_rules` round-trips a real `DesignRules` instance with field-level equality. The path is the primary loader for YAML-stored rules, not a dead branch behind a fallback.
- A missing design-rules file is a `FileNotFoundError`, not a silent default — the silent-fallback class of bug that masked Part A is structurally impossible in `load_design_rules`.
- No `Mock` object appears as the primary argument to `export_design_rules` or `import_design_rules` in any test in `tests/core/test_design_rules_unified.py`.
- A new public function added to `temper-placer/temper_placer/core/` that is never invoked by any test fails CI with a named, actionable message — not a passing green build that hides the function.
- The allowlist shrinks monotonically; an entry cannot be removed without a test or a deletion in the same PR.
- After Phase 1 lands, no new zero-coverage public function enters `temper-placer/temper_placer/core/` without an allowlist ticket.

---

## Scope Boundaries

- **Mock-as-primary-argument ban** — R2 bans `Mock` as the primary argument for the round-trip test only. A repo-wide Mock ban is out of scope; Mocks remain valid for collaborator doubles. The Part A lesson is that Mocking the *function under test's primary data argument* validates no real contract; that specific pattern is banned in `test_design_rules_unified.py`, not globally.
- **Branch coverage gate** — R5 uses line coverage (zero executed lines) as the gate signal. Branch coverage is reported but not gated; a branch-coverage gate would flag the Mock-masking class of failures but requires per-branch triage that is too expensive at the current baseline. Revisit after Phase 3.
- **Assertion-presence check** — automatically verifying that a test *asserts on* the function's output (not just calls it) is out of scope; it requires AST-level test analysis. R2's real-instance requirement is the pragmatic proxy for the round-trip path only.
- **Static analysis overlap with idea #5** — Ruff `T201` and module-level `assert` (idea #5, Phase 1) are **complementary, not overlapping**. Static analysis catches typos in *constants and registries* at import time. This initiative's coverage gate catches *entirely unexercised functions* at CI time. The dead round-trip path evades idea #5 (no constant typo, no registry drift — the field names are wrong but the module imports fine) and is caught only by dynamic exercise. The two initiatives attack disjoint failure modes; both should land.
- **Gate scope = `temper-placer/temper_placer/core/` at Phase 1** — gating all of `packages/` on day one is out of scope. The 784-function placer baseline alone makes fail-and-fix-immediately infeasible; the allowlist with ticketed removal is the chosen mechanism, and phasing prevents the gate from sprawling faster than debt paydown.
- **Coverage threshold / `fail-under` percentage** — out of scope. The gate is binary per-function (zero coverage = fail), not a percentage threshold. A 90% threshold permits 10% of functions to be dead by hiding them in the long tail; the per-function gate does not.

---

## Key Decisions

- **The dead path becomes the primary loader, not a secondary path behind the fallback.** Keeping the fallback would preserve the masking behavior that made the bug latent. `load_design_rules` raises `FileNotFoundError` on missing paths; callers that want default rules call `create_temper_design_rules()` explicitly. The round-trip path is the only YAML load path.
- **The gate uses line coverage (zero executed lines), not branch coverage or assertion presence.** Line coverage is cheap, well-understood, and directly catches the Part A class of failure (a function whose body is never entered). Branch coverage would catch more (e.g., the `if not path.exists()` branch in the old `load_design_rules`) but triage cost at the 784-function baseline is too high. The Mock-masking failure mode is addressed at the test-quality layer (R2), not the coverage layer.
- **Allowlist with ticketed removal, not fail-and-fix-immediately.** The initial baseline is too large for immediate fix. The allowlist makes the gate mergeable on day one while making the debt visible and monotonically shrinking. Fail-and-fix would block all other work for weeks.
- **Initial scope is one directory, not all packages.** `temper-placer/temper_placer/core/` is the module containing the bug and the highest-concentration source of silent failures from the June sprint. Phasing (R8) with a 50% paydown gate prevents sprawl.
- **The gate is a post-coverage script, not a pytest plugin.** A standalone script reading `coverage.json` is easier to reason about, version, and bypass in emergencies than a pytest plugin hook. The script is invoked from `.github/workflows/python-tests.yml` as a separate step after the test run.

---

## Assumptions

- **A1.** `pytest-cov` is functional in the CI environment. It is already listed as a dev dependency in `temper-placer` and `temper-drc`'s `pyproject.toml`; the assumption is that `uv run pytest --cov` works without additional setup. Unverified for the workspace-root `uv` invocation — confirm during planning.
- **A2.** The coverage JSON report includes per-function line ranges sufficient to compute zero-coverage. `coverage.py`'s `--cov-report=json` emits `files.<path>.functions` with start/end lines; the gate script uses this. Assumption: the report is generated with `branch = true` so the `functions` block is populated (it is, regardless of branch mode, but confirm).
- **A3.** The initial allowlist for `temper-placer/temper_placer/core/` is manageable — on the order of tens of entries, not hundreds. The directory has ~27 modules; assuming 2–5 public functions each and partial existing coverage, a 30–80 entry allowlist is plausible. **This is the highest-risk assumption**: if the baseline is closer to 200 entries, the 50% paydown gate in R8 blocks Phase 2 indefinitely. The `--init` run during planning resolves this.
- **A4.** Removing the silent fallback in `load_design_rules` does not break production callers. The fallback fires when a path is missing; production code presumably passes a real path or relies on `create_temper_design_rules()` directly. **Unverified**: a grep of `load_design_rules` call sites is required during planning. The two known call sites are in `tests/` (which are being rewritten) and `docs/architecture/ROUTER_V6_STEP_VALIDATION.md` (a doc example). No production call site was found in the verification grep for this document, but the grep was not exhaustive across `scripts/` and `packages/*/src`.
- **A5.** The `Mock`-as-primary-argument pattern in `test_design_rules_unified.py` is isolated, not pervasive. The file has three tests using `Mock()` for the rules object (lines 113, 134, 138). The assumption is that this is a local pattern in one test file, not a repo-wide convention. If it is repo-wide, R2's ban cannot be extended without a larger cleanup.
- **A6.** `create_temper_design_rules()` (line 586) produces a `DesignRules` instance with at least one net class, so the round-trip test has non-trivial content to verify. Confirmed by reading line 586's context (defaults are set, net classes are populated); the round-trip test will assert against the actual net class set.

---

## Open Questions

### Resolve Before Planning

- **[Affects R3, A4][Technical]** What are all production call sites of `load_design_rules`? The verification grep found test and doc references only. A full `rg "load_design_rules\("` across `packages/`, `scripts/`, and `firmware/` is required before removing the silent fallback. If any production caller relies on the missing-file-returns-defaults behavior, that caller must be migrated to explicit `create_temper_design_rules()` first.
- **[Affects R6, A3][Technical]** What is the actual size of the zero-coverage baseline for `temper-placer/temper_placer/core/`? Run `pytest --cov=temper_placer.core tests/core/ --cov-report=json` during planning and count. If the baseline exceeds ~100 entries, the 50% paydown gate (R8) needs recalibration or the initial scope must narrow further (e.g., `core/design_rules.py` only for Phase 1).
- **[Affects R4][Technical]** Does the existing CI runner have disk/perf headroom for `--cov` across all gated packages, or does coverage collection meaningfully extend the 30-minute timeout? Measure during planning.

### Deferred to Planning

- **[Affects R5][Technical]** Should the gate script live in `tools/`, `scripts/`, or `.github/scripts/`? Follow the repo convention for CI helper scripts (check for existing precedent).
- **[Affects R6][Tooling]** Allowlist format — plain text `module::function` lines with trailing comments, or YAML/JSON? Plain text with comments is easier to diff in PRs; YAML is easier to parse. Decide based on whether the gate script needs structured metadata beyond the ticket reference.
- **[Affects R8][Process]** What is the cadence for allowlist paydown sprints? A specific ticket epic or a recurring hardening sprint. Without a cadence, the allowlist risks growing, not shrinking.

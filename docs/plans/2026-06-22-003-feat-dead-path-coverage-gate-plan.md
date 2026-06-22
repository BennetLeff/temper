---
title: "feat: Dead-Path Re-enablement and Exercise-or-Delete Coverage Gate"
type: feat
status: needs-revision
date: 2026-06-22 (revised 2026-06-22)
origin: docs/brainstorms/2026-06-21-dead-path-coverage-gate-requirements.md
---

# feat: Dead-Path Re-enablement and Exercise-or-Delete Coverage Gate

## Summary

**CRITICAL — ce-doc-review finding (2026-06-22):** The dead-path functions (`export_design_rules`, `import_design_rules`, `load_design_rules`) and the test file (`test_design_rules_unified.py`) were removed from the codebase during the June 2026 clean-base sprint (commit `3314d94a`). The file formerly at `packages/temper-placer/temper_placer/core/design_rules.py` is now at `packages/temper-placer/src/temper_placer/core/design_rules.py` and no longer contains these functions. **Part A (U1, U2) of this plan is obsolete.** Part B (U3, U4 — coverage gate) remains valuable and should ship independently. The implementer should verify the current `main` state before proceeding with any Part A unit.

A two-part hardening initiative. **Part A** re-enables the dead `export_design_rules` / `import_design_rules` / `load_design_rules` round-trip in `packages/temper-placer/temper_placer/core/design_rules.py`, which today reads `_mm`-suffixed attributes that do not exist on `DesignRules` (`default_clearance`, not `default_clearance_mm`) or `NetClassRules` (`clearance`, not `clearance_mm`), passes nonexistent kwargs (`clearance_mm=`) to the dataclass constructors, and is masked by a silent `create_temper_design_rules()` fallback on missing files plus a `try/except Exception` that converts `TypeError` into `ValueError`. The fix is verified by a round-trip property test using a **real `DesignRules` instance** — the existing test at `tests/core/test_design_rules_unified.py:108-126` mocks the very wrong field names the bug hides in. **Part B** adds a CI coverage gate that fails any public function in `packages/temper-placer/temper_placer/core/` with zero executed lines, forcing either an exercising test or a deletion. The gate ships with a ticketed, monotonically-shrinking allowlist so the initial baseline does not block the merge. Part A is the pilot that proves the gate's value: the dead path was "covered" by a Mock-based test that exercised none of the real dataclass contracts, and CI never ran that test anyway.

---

## Problem Frame

Three functions in `packages/temper-placer/temper_placer/core/design_rules.py` form a serialization round-trip that has never worked against a real `DesignRules`:

| # | Site | Bug | Mask |
|---|------|-----|------|
| 1 | `export_design_rules` (`design_rules.py:789-814`) | Reads `rules.default_clearance_mm` (line 801), `rules.default_trace_width_mm` (line 802), `nc.clearance_mm` (line 807), `nc.trace_width_mm` (line 808). The `DesignRules` dataclass declares `default_clearance` (`design_rules.py:173`) and `default_trace_width` (`design_rules.py:172`); `NetClassRules` declares `clearance` (`design_rules.py:114`) and `trace_width` (`design_rules.py:113`). Any real call raises `AttributeError`. | — |
| 2 | `import_design_rules` (`design_rules.py:817-843`) | Passes `clearance_mm=` (line 831), `trace_width_mm=` (line 832), `default_clearance_mm=` (line 838), `default_trace_width_mm=` (line 839) to the dataclass constructors. None of these kwargs exist. Any real call raises `TypeError`. | — |
| 3 | `load_design_rules` (`design_rules.py:712-736`) | Calls `import_design_rules` on the YAML-parsed dict (line 733). | Line 724-726: `if not path.exists(): return create_temper_design_rules()` short-circuits missing files to defaults. Line 735: `except Exception as e: raise ValueError(...)` converts the `TypeError` from (2) into a `ValueError`. The broken path is never reached in production. |

The existing test `tests/core/test_design_rules_unified.py::test_rule_export_import_for_debugging` (lines 108-126) constructs `Mock()` (line 113) and sets `original_rules.default_clearance_mm = 0.5` (line 115) and `nc.clearance_mm = 0.5` (line 114) — i.e. it mocks the **wrong field names the bug produces**, so the test passes while the real function is broken. A second test, `test_rule_loading_error_handling` (lines 149-161), asserts `load_design_rules("nonexistent_file.yaml")` raises `FileNotFoundError` (line 154-155), but the implementation returns defaults instead (line 726) — the test is wrong against the code, and neither the test author's intent nor the actual behavior is asserted.

A critical structural finding: **CI does not run this test file at all.** The CI workflow `.github/workflows/python-tests.yml:36-38` runs `working-directory: packages/temper-placer` then `uv run pytest tests/core/`, which resolves to `packages/temper-placer/tests/core/` — not the repo-root `tests/core/` where `test_design_rules_unified.py` lives. The root `pyproject.toml:29-37` `testpaths` also excludes the repo-root `tests/` directory. The `paths:` filter on the workflow (`.github/workflows/python-tests.yml:6-9, 12-15`) is `['packages/**', 'pyproject.toml', '.github/workflows/python-tests.yml']` — it does not include `tests/**`, so editing the repo-root test file does not even trigger CI. The dead-path test has been invisible to CI by construction.

Stepping back, `packages/temper-placer/temper_placer/core/` contains 27 `.py` modules. `pytest-cov>=4.1.0` is listed as a dev dependency in `packages/temper-placer/pyproject.toml:52` and `packages/temper-drc/pyproject.toml:39` but is never invoked — there is no `[tool.coverage.*]` block in the root `pyproject.toml`, no `--cov` flag in the workflow, and no `fail-under` gate. A function can be entirely unexercised, or exercised only by Mock-based tests that validate no real contract, and nothing in CI notices. The dead round-trip path is the canonical example — it survived the June 2026 clean-base sprint.

This initiative converts "first real use reveals the bug" into "CI reveals the bug," and makes the absence-of-tests condition structural rather than opportunistic.

---

## Scope Boundaries

### In scope

- R1–R7 from the origin requirements document: the Part A field-name fix, fallback removal, exception narrowing, real-instance round-trip test, and the Part B coverage configuration + post-coverage gate script + ticketed allowlist + monotonic-shrink check.
- R8 **Phase 1 only**: gate scoped to `packages/temper-placer/temper_placer/core/`. Phase 2 (all of `temper_placer/`) and Phase 3 (`temper-drc`, `temper-tools`, `temper-workflow`) are named in the plan as sequenced follow-ons gated on 50% allowlist paydown, but are not implemented in this plan.
- Moving the dead-path test from the CI-invisible repo-root `tests/core/` into `packages/temper-placer/tests/core/` so the rewritten assertions actually run in CI (required for R2/R3 to have any effect).

### Deferred

- **R8 Phase 2 and Phase 3 expansion.** Each phase begins with an `--init` run that repopulates the allowlist for the newly-scoped modules. A phase lands only when the prior phase's allowlist has shrunk by ≥50% by entry count. Phase 2/3 are tracked as follow-on tickets, not implemented here.
- **Branch-coverage gate.** R5 uses line coverage (zero executed lines) as the gate signal. Branch coverage is reported but not gated; triage cost at the 27-module baseline is too high. Revisit after Phase 3.
- **Assertion-presence check.** Automatically verifying that a test *asserts on* the function's output (not just calls it) requires AST-level test analysis and is out of scope. R2's real-instance requirement is the pragmatic proxy for the round-trip path only.
- **Repo-wide Mock-as-primary-argument ban.** R2 bans `Mock` as the primary argument for the round-trip test only. Mocks remain valid for collaborator doubles. The Part A lesson (Mocking the function under test's primary data argument validates no real contract) is documented but not globally enforced.
- **Coverage threshold / `fail-under` percentage.** The gate is binary per-function (zero coverage = fail), not a percentage threshold. A 90% threshold permits 10% of functions to be dead by hiding them in the long tail; the per-function gate does not.
- **Static-analysis overlap with N2 (Safety-Constant SSOT).** Ruff `T201` and module-level `assert` (N2's domain) are complementary, not overlapping. Static analysis catches typos in constants/registries at import time; this initiative's coverage gate catches entirely unexercised functions at CI time. The dead round-trip path evades N2 (no constant typo, no registry drift — the field names are wrong but the module imports fine) and is caught only by dynamic exercise. Both plans should land.

### Out of scope

- Remediation of any zero-coverage functions the gate discovers beyond the Part A pilot. The allowlist with ticketed removal is the mechanism; paydown is a recurring cadence (origin Open Question [Affects R8][Process]), not a deliverable in this plan.
- Rewriting the three other Mock-based tests in `tests/core/test_design_rules_unified.py` (`test_pipeline_consistency_validation` at lines 129-146, the `Mock()` at lines 134/138) — only the two tests covering the dead path (lines 108-126, 149-161) are rewritten. The remaining Mock usage is flagged in the plan's Risk Analysis for a follow-on cleanup ticket.

---

## Key Technical Decisions

**The dead path becomes the only YAML load path; the silent fallback is removed, not retained as a secondary branch.** Keeping the fallback preserves the masking behavior that made the bug latent. `load_design_rules` raises `FileNotFoundError` on missing paths (`design_rules.py:724-726` becomes `raise FileNotFoundError(...)`); callers that want default rules call `create_temper_design_rules()` (line 578) explicitly. A grep of `load_design_rules(` across the repo finds exactly three call sites: `tests/core/test_design_rules_unified.py:30,155,161` (all in the test file being rewritten) and `docs/architecture/ROUTER_V6_STEP_VALIDATION.md:161` (a doc example). **No production caller in `packages/*/src`, `scripts/`, or `firmware/` relies on the missing-file-returns-defaults behavior.** Resolves origin Open Question [Affects R3, A4] — the fallback removal is safe; the doc example is updated in U1 to call `create_temper_design_rules()` explicitly so the doc does not advertise the removed behavior. (resolves origin Open Question [Affects R3, A4])

**The `try/except Exception` is narrowed to `yaml.YAMLError`.** `design_rules.py:735` becomes `except yaml.YAMLError as e:`. A `TypeError` from a malformed dict (the bug in `import_design_rules`) now propagates as a `TypeError`, not a wrapped `ValueError` that masks it. `yaml.safe_load` raising `yaml.scanner.ScannerError` / `yaml.parser.ParserError` (both subclasses of `yaml.YAMLError`) is still caught and wrapped, preserving the malformed-YAML error contract. The existing `test_rule_loading_error_handling` invalid-YAML branch (lines 158-161) is updated to assert `yaml.YAMLError` (or the wrapped `ValueError` if the plan keeps the wrap) — decision: keep the `ValueError` wrap for `yaml.YAMLError` so callers catch one exception type for any malformed-file condition; a `TypeError` from a structurally-wrong dict propagates unwrapped.

**The round-trip test moves into `packages/temper-placer/tests/core/` so CI runs it.** The existing file `tests/core/test_design_rules_unified.py` is in the repo-root `tests/` directory, which is outside `pyproject.toml:29-37` `testpaths` and outside the CI `working-directory: packages/temper-placer` + `pytest tests/core/` invocation (`.github/workflows/python-tests.yml:36-38`). Leaving the rewritten test in place would preserve the invisibility. U2 moves the two rewritten tests into `packages/temper-placer/tests/core/test_design_rules_unified.py` (new file in the CI-collected tree) and deletes the repo-root file. The repo-root `tests/core/` directory retains `test_integration_monitor.py` and `test_loop_convergence.py` (unrelated to this plan); only `test_design_rules_unified.py` is moved.

**The gate uses line coverage (zero executed lines), not branch coverage or assertion presence.** Line coverage is cheap, well-understood, and directly catches the Part A class of failure (a function whose body is never entered). Branch coverage would catch more (e.g. the `if not path.exists()` branch in the old `load_design_rules`) but triage cost at the 27-module baseline is too high. The Mock-masking failure mode is addressed at the test-quality layer (R2's real-instance requirement), not the coverage layer. The gate's job is to catch functions that are *never entered at all*; R2's job is to catch functions that are *entered with a fake that validates no contract*.

**Allowlist with ticketed removal, not fail-and-fix-immediately.** The initial baseline is too large for immediate fix. The allowlist makes the gate mergeable on day one while making the debt visible and monotonically shrinking. Fail-and-fix would block all other work for weeks.

**Initial scope is one directory, not all packages.** `packages/temper-placer/temper_placer/core/` is the module containing the bug and the highest-concentration source of silent failures from the June sprint. Phasing (R8) with a 50% paydown gate prevents sprawl.

**The gate is a post-coverage script in `scripts/`, not a pytest plugin.** A standalone script reading `coverage.json` is easier to reason about, version, and bypass in emergencies than a pytest plugin hook. The repo convention for CI helper scripts is `scripts/check_regression.py` and `scripts/check_perf_regression.py` (both `#!/usr/bin/env python3`, argparse, `rich.console.Console`, sys.path manipulation) — the gate script follows this precedent at `scripts/check_coverage_gate.py`. It is invoked from `.github/workflows/python-tests.yml` as a new step after the placer test run. (resolves origin Open Question [Affects R5])

**Allowlist format: plain text `module::function  # TODO: temper-xxx` lines.** Plain text with trailing comments is easier to diff in PRs than YAML and sufficient for the `(function, ticket)` metadata the gate needs. The gate script parses `module::function` and ignores everything after `#`. The file lives at `.coverage-allowlist` at repo root so it is visible alongside `pyproject.toml` and discoverable by the gate script from any working directory. (resolves origin Open Question [Affects R6, Tooling])

**Coverage configuration in root `pyproject.toml`.** A `[tool.coverage.run]` block with `branch = true`, `source = ["temper_placer.core"]` (relative to `packages/temper-placer/`), and `[tool.coverage.report]` with `show_missing = true` is added to the root `pyproject.toml` after the existing `[tool.ruff.lint]` block. The CI step runs `uv run pytest tests/core/ --cov=temper_placer.core --cov-report=json --cov-report=term` with `working-directory: packages/temper-placer` so the `source` path resolves correctly and `coverage.json` lands in `packages/temper-placer/coverage.json` for the gate script to consume.

**CI perf headroom.** `--cov` adds ~10-20% overhead to pytest runtime. The placer core-only run is the fastest CI step today; adding coverage collection keeps it well under the 30-minute workflow timeout (`.github/workflows/python-tests.yml:20`). The gate script itself is O(seconds) — it reads one JSON file and one allowlist. (resolves origin Open Question [Affects R4])

**Allowlist paydown cadence.** No fixed cadence is mandated by this plan. The 50% paydown gate (R8) is the structural forcing function: Phase 2 cannot land until Phase 1's allowlist has shrunk by ≥50%. The triage maintainer (A3) files removal tickets as part of recurring hardening sprints. The plan's Risk Analysis flags "allowlist grows instead of shrinks" as the top process risk and recommends a quarterly hardening sprint as the cadence — recorded in `CLAUDE.md` §Coverage Gate. (resolves origin Open Question [Affects R8, Process])

**Documentation sync.** Per `AGENTS.md` "Documentation & Context Maintenance": the gate mechanism, the `--init` workflow, the allowlist format, and the monotonic-shrink rule are recorded in `CLAUDE.md` in the same commit as U4. Both `CLAUDE.md` and `AGENT_INSTRUCTIONS.md` exist at repo root; `CLAUDE.md` is the chosen target (the companion plan N2 also targets `CLAUDE.md`).

---

## Implementation Units

### Phase A — Dead-path re-enablement (pilot)

### U1. Fix `export_design_rules` / `import_design_rules` field names and remove the silent fallback in `load_design_rules`

**Goal:** Make the round-trip work against a real `DesignRules` instance and make `load_design_rules` raise `FileNotFoundError` on missing paths instead of silently returning defaults.

**Requirements:** R1, R2, R3

**Dependencies:** None

**Files:**
- `packages/temper-placer/temper_placer/core/design_rules.py` (fix `export_design_rules:789-814`, `import_design_rules:817-843`, `load_design_rules:712-736`)
- `docs/architecture/ROUTER_V6_STEP_VALIDATION.md:161` (update the doc example to call `create_temper_design_rules()` explicitly so the doc does not advertise the removed silent-fallback behavior)

**Approach:**

1. **`export_design_rules` (`design_rules.py:799-814`):** Change the four attribute reads to the real dataclass field names while **keeping the emitted dict keys unchanged** (the serialization format is stable; only the source attribute access is corrected):
   - Line 801: `rules.default_clearance_mm` → `rules.default_clearance` (dict key `default_clearance_mm` stays).
   - Line 802: `rules.default_trace_width_mm` → `rules.default_trace_width` (dict key `default_trace_width_mm` stays).
   - Line 807: `nc.clearance_mm` → `nc.clearance` (dict key `clearance_mm` stays).
   - Line 808: `nc.trace_width_mm` → `nc.trace_width` (dict key `trace_width_mm` stays).

2. **`import_design_rules` (`design_rules.py:827-843`):** Change the four kwargs to the real dataclass kwargs:
   - Line 831: `clearance_mm=nc_data["clearance_mm"]` → `clearance=nc_data["clearance_mm"]` (reads the serialized key, passes the dataclass kwarg).
   - Line 832: `trace_width_mm=nc_data["trace_width_mm"]` → `trace_width=nc_data["trace_width_mm"]`.
   - Line 838: `default_clearance_mm=data["default_clearance_mm"]` → `default_clearance=data["default_clearance_mm"]`.
   - Line 839: `default_trace_width_mm=data["default_trace_width_mm"]` → `default_trace_width=data["default_trace_width_mm"]`.
   - Add `name=name` is already present at line 830 — unchanged.

3. **`load_design_rules` (`design_rules.py:712-736`):**
   - Remove lines 724-726 (`if not path.exists(): return create_temper_design_rules()`). Replace with `if not path.exists(): raise FileNotFoundError(f"Design rules file not found: {rules_path}")`.
   - Narrow line 735 `except Exception as e:` to `except yaml.YAMLError as e:`. The `raise ValueError(...)` wrap is retained for `yaml.YAMLError` so callers catch one exception type for any malformed-file condition. A `TypeError` from `import_design_rules` (structurally-wrong dict) now propagates unwrapped.

4. **`docs/architecture/ROUTER_V6_STEP_VALIDATION.md:161`:** The example `rules = load_design_rules("fixtures/temper.kicad_pcb")` is a doc-only snippet. Update the surrounding prose to note that missing paths raise `FileNotFoundError` and that callers wanting defaults should call `create_temper_design_rules()` explicitly. No code change beyond the doc text.

**Patterns to follow:** Existing dataclass field declarations at `design_rules.py:112-127` (`NetClassRules`) and `design_rules.py:172-190` (`DesignRules`). The `getattr(rules, "version", "1.0")` defensive pattern at line 800 is retained (the `DesignRules` dataclass does not declare `version`, so the getattr fallback is correct).

**Acceptance:**
- `from temper_placer.core.design_rules import create_temper_design_rules, export_design_rules, import_design_rules; r = create_temper_design_rules(); e = export_design_rules(r); i = import_design_rules(e); export_design_rules(i) == e` is `True` for the real instance (no `AttributeError`, no `TypeError`).
- `load_design_rules("nonexistent.yaml")` raises `FileNotFoundError`.
- `load_design_rules(<path-to-malformed-yaml>)` raises `ValueError` (wrapped `yaml.YAMLError`).
- A YAML file whose top-level dict is structurally wrong (e.g. `net_classes` maps to a list, not a dict) causes `import_design_rules` to raise `TypeError` which propagates unwrapped from `load_design_rules` (not wrapped as `ValueError`).
- Covers R1, R2, R3.

---

### U2. Rewrite the round-trip and error-handling tests with a real `DesignRules` instance, and move them into the CI-collected tree

**Goal:** Replace the Mock-based tests that masked the bug with real-instance property tests, and relocate them from the CI-invisible repo-root `tests/core/` into `packages/temper-placer/tests/core/` so CI actually runs them.

**Requirements:** R1, R2, R3

**Dependencies:** U1

**Files:**
- `packages/temper-placer/tests/core/test_design_rules_unified.py` (new — the relocated + rewritten tests)
- `tests/core/test_design_rules_unified.py` (delete after relocation; the repo-root `tests/core/` directory retains `test_integration_monitor.py` and `test_loop_convergence.py`)
- `packages/temper-placer/tests/core/test_design_rules.py` (existing; confirm no name collision — grep confirms it contains no `export_design_rules`/`import_design_rules`/`load_design_rules` tests, so the new file is additive)

**Approach:**

1. **`test_rule_export_import_for_debugging` (was lines 108-126, rewritten):** Construct `rules = create_temper_design_rules()` (the real instance from `design_rules.py:578`, which populates `net_classes` from `TEMPER_NET_CLASSES` at line 589). Assert:
   - `exported = export_design_rules(rules)` is a `dict` with `"version"`, `"net_classes"`, `"default_clearance_mm"`, `"default_trace_width_mm"` keys.
   - `imported = import_design_rules(exported)` is a `DesignRules` instance.
   - `imported.default_clearance == rules.default_clearance` (R1/R2 field-level equality).
   - `imported.default_trace_width == rules.default_trace_width`.
   - `set(imported.net_classes.keys()) == set(rules.net_classes.keys())`.
   - For each `name, nc` in `rules.net_classes.items()`: `imported.net_classes[name].clearance == nc.clearance` and `imported.net_classes[name].trace_width == nc.trace_width`.
   - Round-trip property: `export_design_rules(import_design_rules(export_design_rules(rules))) == export_design_rules(rules)`.
   - **No `Mock` object appears anywhere in this test.** A repo-wide grep for `Mock` in this file returns zero hits.
   - A developer who reintroduces the `_mm` suffix in `export_design_rules` (e.g. reverts line 801 to `rules.default_clearance_mm`) sees this test fail with `AttributeError: 'DesignRules' object has no attribute 'default_clearance_mm'` — the failure mode the old Mock-based test swallowed.

2. **`test_rule_loading_error_handling` (was lines 149-161, rewritten):**
   - Missing-file branch: `with pytest.raises(FileNotFoundError): load_design_rules("nonexistent_file.yaml")` — matches the new U1 behavior. Use a real temp path (`tmp_path / "nonexistent.yaml"`), not `patch("builtins.open")`.
   - Malformed-YAML branch: write `tmp_path / "malformed.yaml"` with content `"invalid: yaml: content: [unbalanced"`, then `with pytest.raises(ValueError): load_design_rules(str(malformed_path))` — the `ValueError` wrap for `yaml.YAMLError` is retained per U1.
   - Structurally-wrong-dict branch (new): write `tmp_path / "wrong_struct.yaml"` with content `{"net_classes": [], "default_clearance_mm": 0.2, "default_trace_width_mm": 0.2}` (a list where a dict is expected), then `with pytest.raises(TypeError): load_design_rules(str(wrong_struct_path))` — confirms the `try/except` no longer swallows `TypeError` into `ValueError`.
   - No `patch("builtins.open")` mock; all branches use real `tmp_path` files.

3. **Relocate:** Create `packages/temper-placer/tests/core/test_design_rules_unified.py` with the two rewritten tests plus `test_pipeline_consistency_validation` (lines 129-146) copied verbatim (it is out of scope to rewrite, but it must move with the file to avoid losing coverage). Delete `tests/core/test_design_rules_unified.py`. The repo-root `tests/core/__init__.py` and the two unrelated test files remain.

**Patterns to follow:** `packages/temper-placer/tests/core/test_design_rules.py` (existing test style in the CI-collected tree). `pytest.raises` and `tmp_path` fixture usage.

**Acceptance:**
- `uv run pytest packages/temper-placer/tests/core/test_design_rules_unified.py` passes.
- The round-trip test fails (with `AttributeError`) if U1's line 801 fix is reverted — confirming the test exercises the real dataclass contract.
- The missing-file test fails if U1's `FileNotFoundError` is reverted to the silent fallback — confirming the test exercises the new behavior, not the old intent.
- `grep -r "Mock" packages/temper-placer/tests/core/test_design_rules_unified.py` returns no matches in the round-trip and error-handling tests.
- CI runs the tests (the `Run temper-placer tests (core only for CI speed)` step at `.github/workflows/python-tests.yml:36-38` collects `packages/temper-placer/tests/core/`).
- Covers R1, R2, R3.

---

### Phase B — Exercise-or-delete coverage gate

### U3. Add coverage configuration to `pyproject.toml` and wire `--cov` into CI

**Goal:** Add a `[tool.coverage.*]` block to the root `pyproject.toml` and a `--cov` invocation to the placer CI step so a machine-readable `coverage.json` is produced for the gate script.

**Requirements:** R4

**Dependencies:** None (independent of U1/U2; can land in parallel)

**Files:**
- `pyproject.toml` (add `[tool.coverage.run]` and `[tool.coverage.report]` after `[tool.ruff.lint]`)
- `.github/workflows/python-tests.yml` (modify the `Run temper-placer tests` step at lines 36-38 to add `--cov` flags; add the `tests/**` and `scripts/**` paths to the `paths:` filter at lines 6-9 and 12-15 so edits to the gate script and the moved tests trigger CI)
- `packages/temper-placer/pyproject.toml` (confirm `pytest-cov>=4.1.0` is present at line 52 — no change needed)

**Approach:**

1. **`pyproject.toml` (root):** Append after line 60 (`ignore = ["E501"]`):
   ```toml
   [tool.coverage.run]
   branch = true
   source = ["temper_placer.core"]

   [tool.coverage.report]
   show_missing = true
   ```
   The `source` is scoped to `temper_placer.core` (Phase 1 scope per R6). The CI step runs with `working-directory: packages/temper-placer`, so `temper_placer.core` resolves to `packages/temper-placer/temper_placer/core/`. `branch = true` is set per R4 (branch coverage is reported but not gated — the gate uses line coverage).

2. **`.github/workflows/python-tests.yml:36-38`:** Change the placer step `run` to:
   ```yaml
   run: uv run pytest tests/core/ -v --tb=short --cov=temper_placer.core --cov-report=json --cov-report=term
   ```
   `--cov-report=json` emits `coverage.json` in `packages/temper-placer/coverage.json` (the working directory). `--cov-report=term` gives human-readable output in the CI log.

3. **`.github/workflows/python-tests.yml:6-9` and `12-15`:** Add `'tests/**'` and `'scripts/**'` to the `paths:` filter so edits to the moved test file (U2) and the gate script (U4) trigger CI. The filter becomes:
   ```yaml
   paths:
     - 'packages/**'
     - 'tests/**'
     - 'scripts/**'
     - 'pyproject.toml'
     - '.github/workflows/python-tests.yml'
   ```

**Patterns to follow:** Standard `[tool.coverage.*]` TOML schema. The existing `addopts = ["-v", "--tb=short"]` in `pyproject.toml:47` is left untouched (the `--cov` flags are on the CI command line, not in `addopts`, so local `uv run pytest` without `--cov` continues to work).

**Acceptance:**
- `uv run pytest tests/core/ --cov=temper_placer.core --cov-report=json` (run from `packages/temper-placer/`) produces `coverage.json` with a `files.<path>.functions` block containing per-function start/end lines.
- The CI `Run temper-placer tests` step produces `coverage.json` as an artifact available to the next step.
- Local `uv run pytest` without `--cov` still works (no behavioral regression for developers not running the gate).
- Covers R4.

---

### U4. Post-coverage gate script with `--init` mode and monotonic-shrink check

**Goal:** A standalone script `scripts/check_coverage_gate.py` that reads `coverage.json`, computes the set of public functions (module-level `def` not prefixed with `_`, and methods of public classes not prefixed with `_`) with zero executed lines, subtracts the allowlist, and fails if the diff is non-empty. Supports `--init` to populate the allowlist on first run and a default-mode monotonic-shrink check.

**Requirements:** R5, R6, R7

**Dependencies:** U3 (`coverage.json` must be produced by CI)

**Files:**
- `scripts/check_coverage_gate.py` (new — the gate script)
- `.coverage-allowlist` (new — committed allowlist file at repo root)
- `.github/workflows/python-tests.yml` (add a new step after the placer test run that invokes the gate script)
- `CLAUDE.md` (document the gate mechanism, the `--init` workflow, the allowlist format, the monotonic-shrink rule, and the paydown cadence)

**Approach:**

The script follows the `scripts/check_regression.py` / `scripts/check_perf_regression.py` convention: `#!/usr/bin/env python3`, `argparse`, `rich.console.Console`, `sys.path` manipulation as needed.

**Public-function discovery:** The script uses `coverage.py`'s `files.<path>.functions` block from `coverage.json`, which gives `{name: [start_line, end_line]}` per file. To classify a function as "public," the script `ast.parse`s the source file and walks the tree:
- Module-level `FunctionDef` / `AsyncFunctionDef` nodes whose name does not start with `_` are public.
- `ClassDef` nodes whose name does not start with `_` expose their `FunctionDef` / `AsyncFunctionDef` methods (not starting with `_`) as public methods, qualified as `ClassName.method_name`.
- The `coverage.json` `functions` block names functions by their bare name (or `ClassName.method_name` for methods); the script joins the AST-derived public set with the coverage-derived zero-executed set by `(file, qualified_name)`.

**Zero-coverage computation:** For each public function, the script reads `coverage.json`'s `files.<path>.executed_lines` and `files.<path>.missing_lines`. A function is zero-coverage if **none** of its `[start_line, end_line]` range (excluding the `def` line itself and decorator lines) appears in `executed_lines`. This is the R5 signal: the function body was never entered.

**Allowlist format (`.coverage-allowlist`):**
```
# Format: temper_placer/core/<module>.py::function_or_Class.method  # TODO: temper-xxx
temper_placer/core/decision.py::decide_topology  # TODO: temper-101
temper_placer/core/loop.py::LoopNet.add_edge  # TODO: temper-102
```
- One entry per line. `#` starts a comment. The `# TODO: temper-xxx` trailing comment is **required** for every entry — the script's `--validate-allowlist` mode fails on any entry without a ticket reference.
- The module path is relative to the package root (`temper_placer/core/...`), matching `coverage.json`'s `files` keys after the `source` prefix is stripped.

**`--init` mode (R6):** `python scripts/check_coverage_gate.py --init --coverage-json packages/temper-placer/coverage.json --allowlist .coverage-allowlist` writes every zero-coverage public function in scope to the allowlist with a `# TODO: temper-xxx` placeholder ticket. CI passes on this commit. This is run once during U4 implementation to populate the initial baseline; the resulting `.coverage-allowlist` is committed.

**Default mode (R5):** `python scripts/check_coverage_gate.py --coverage-json packages/temper-placer/coverage.json --allowlist .coverage-allowlist`:
1. Compute the zero-coverage public set `Z`.
2. Load the allowlist `A`.
3. `new_uncovered = Z - A`. If non-empty, fail with one line per function: `temper_placer/core/<module>.py:<line> <function_name> — zero coverage (not on allowlist; see CLAUDE.md §Coverage Gate)`.
4. `stale_allowlist = A - Z`. If non-empty, warn (not fail): `temper_placer/core/<module>.py::<function_name> is on the allowlist but now has coverage — remove the entry`.
5. `additions_without_ticket = A.diff(prev_A).entries_without_TODO`. Fail on any. (See monotonic-shrink check below for the mechanism.)

**Monotonic-shrink check (R7):** The script's `--check-shrink` mode compares the current allowlist against the allowlist on `origin/main` (via `git show origin/main:.coverage-allowlist`). For any entry removed from the allowlist in this PR, the script checks that the same PR either (a) adds a test exercising the function (detected by the function appearing in `coverage.json`'s `executed_lines` for some file) or (b) deletes the function (detected by `git show origin/main:<module>` succeeding and `git show HEAD:<module>` either failing or no longer containing the function's `def`). If neither, fail: `allowlist entry removed without test or deletion: <function_name>`. For any entry added to the allowlist in this PR, the script requires a `# TODO: temper-xxx` ticket reference; additions without a ticket fail: `allowlist entry added without ticket reference: <function_name>`. (resolves R7)

**CI wiring (`.github/workflows/python-tests.yml`):** Add a new step after the placer test step:
```yaml
- name: Coverage gate (temper-placer/core)
  working-directory: packages/temper-placer
  run: python ../../scripts/check_coverage_gate.py --coverage-json coverage.json --allowlist ../../.coverage-allowlist
```
The step runs only if the placer test step succeeded (default GitHub Actions behavior). The gate is a hard block — no `continue-on-error`.

**`CLAUDE.md` documentation:** Add a `## Coverage Gate` section documenting:
- The gate's scope (Phase 1: `temper_placer/core/`), signal (zero line coverage), and binary per-function fail.
- The `--init` workflow for new phases.
- The allowlist format and the required `# TODO: temper-xxx` ticket reference.
- The monotonic-shrink rule: an entry cannot be removed without a test or a deletion in the same PR; an entry cannot be added without a ticket.
- The paydown cadence recommendation (quarterly hardening sprint) and the 50% paydown gate for phase advancement.
- The escape hatch: there is no env-var override; the allowlist IS the recorded justification. A reviewer sees allowlist additions/removals in `git diff`.

**Patterns to follow:** `scripts/check_regression.py` (argparse, rich console, sys.path setup). `coverage.py` JSON schema (`files.<path>.functions`, `files.<path>.executed_lines`, `files.<path>.missing_lines`). `ast.walk` stdlib usage (same pattern as the companion plan N2's linter).

**Acceptance:**
- `--init` mode against `packages/temper-placer/coverage.json` writes `.coverage-allowlist` with every zero-coverage public function in `temper_placer/core/`, each with a `# TODO: temper-xxx` placeholder. CI passes on this commit.
- A subsequent commit adding `def new_helper(): ...` to `temper_placer/core/design_rules.py` with no test fails the gate with `temper_placer/core/design_rules.py:NNN new_helper — zero coverage (not on allowlist; see CLAUDE.md §Coverage Gate)`.
- Removing an allowlist entry without a test or deletion in the same PR fails the `--check-shrink` mode with `allowlist entry removed without test or deletion: <function_name>`.
- Adding an allowlist entry without a `# TODO: temper-xxx` ticket fails with `allowlist entry added without ticket reference: <function_name>`.
- Covers R5, R6, R7. (AE3, AE4, AE5)

---

## System-Wide Impact

- **CI pipeline (`.github/workflows/python-tests.yml`):** The placer test step gains `--cov=temper_placer.core --cov-report=json --cov-report=term` (U3). A new `Coverage gate (temper-placer/core)` step runs the gate script after the test step (U4). The `paths:` filter gains `'tests/**'` and `'scripts/**'` so edits to the moved tests and the gate script trigger CI (U3). No new job; the gate runs inside the existing `test` job. Runtime impact: ~10-20% overhead on the placer core-only pytest run plus O(seconds) for the gate script — well within the 30-minute timeout (`.github/workflows/python-tests.yml:20`).
- **`pyproject.toml` (root):** Gains `[tool.coverage.run]` and `[tool.coverage.report]` blocks (U3). No existing config changes.
- **`packages/temper-placer/temper_placer/core/design_rules.py`:** Four attribute reads and four kwargs corrected; the `if not path.exists()` fallback removed; `except Exception` narrowed to `except yaml.YAMLError` (U1). The round-trip path is now functional and is the only YAML load path.
- **`tests/core/test_design_rules_unified.py`:** Deleted (U2). The two dead-path tests and `test_pipeline_consistency_validation` are relocated to `packages/temper-placer/tests/core/test_design_rules_unified.py` (CI-collected). The repo-root `tests/core/` directory retains `test_integration_monitor.py` and `test_loop_convergence.py`.
- **`packages/temper-placer/tests/core/test_design_rules_unified.py`:** New file (U2) containing the rewritten real-instance round-trip test, the rewritten error-handling test, and the verbatim-copied `test_pipeline_consistency_validation`.
- **`docs/architecture/ROUTER_V6_STEP_VALIDATION.md:161`:** Doc example updated to note `FileNotFoundError` on missing paths and explicit `create_temper_design_rules()` for defaults (U1).
- **`scripts/check_coverage_gate.py`:** New gate script (U4), following the `scripts/check_*.py` convention.
- **`.coverage-allowlist`:** New committed file at repo root (U4), populated by `--init` on first run.
- **`CLAUDE.md`:** New `## Coverage Gate` section documenting the gate mechanism, allowlist format, monotonic-shrink rule, and paydown cadence (U4).
- **Developer workflow:** A developer who adds a public function to `temper_placer/core/` and pushes without a test sees a named CI failure pointing at the function and `CLAUDE.md §Coverage Gate`. The developer adds a test, deletes the function, or adds an allowlist entry with a ticket. A developer who removes an allowlist entry must pair it with a test or a deletion in the same PR. "Silently unexercised" is not an available state for new code in `temper_placer/core/`.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| The initial zero-coverage baseline for `temper_placer/core/` is much larger than ~100 entries, making the 50% paydown gate (R8) block Phase 2 indefinitely | High | Medium | Run `uv run pytest tests/core/ --cov=temper_placer.core --cov-report=json` from `packages/temper-placer/` during U4 implementation **before** committing the allowlist. If the baseline exceeds ~100 entries, narrow Phase 1 scope to `temper_placer/core/design_rules.py` only and document the narrowing in `CLAUDE.md`. The `--init` run resolves origin Assumption A3. (origin Open Question [Affects R6, A3] — measurement deferred to implementation) |
| Removing the silent fallback in `load_design_rules` breaks an undiscovered production caller | High | Low | A grep of `load_design_rules(` across `packages/`, `scripts/`, `firmware/`, and `tests/` finds exactly three call sites in `tests/core/test_design_rules_unified.py:30,155,161` (all in the test file being rewritten) and one in `docs/architecture/ROUTER_V6_STEP_VALIDATION.md:161` (a doc example). No production caller relies on the missing-file-returns-defaults behavior. The doc example is updated in U1. Resolved. |
| The gate script's AST-based public-function classification disagrees with `coverage.json`'s `functions` block naming (e.g. nested classes, staticmethods, properties) | Medium | Medium | The script joins the AST-derived public set with the coverage-derived zero-executed set by `(file, qualified_name)`. For `@staticmethod` / `@classmethod` / `@property`, `coverage.py` names them by bare name within the class's `functions` block; the AST walk uses the same `ClassName.method_name` qualification. Disagreements surface as "function in coverage but not in AST" warnings during `--init` and are resolved before the allowlist is committed. |
| The gate's `--check-shrink` mode's git-diff against `origin/main` fails on a fresh checkout or force-push history | Medium | Low | The script uses `git show origin/main:.coverage-allowlist` and degrades gracefully: if `origin/main` ref is unavailable (e.g. detached HEAD local run), `--check-shrink` emits a warning and skips the shrink check (the default-mode zero-coverage check still runs). CI always has `origin/main`. |
| The Mock-based `test_pipeline_consistency_validation` (lines 129-146), copied verbatim into the new file, later masks a similar bug in `validate_pipeline_consistency` | Low | Medium | Out of scope for this plan. Flagged as a follow-on cleanup ticket: replace `Mock()` at lines 134/138 with real `DesignRules` instances. The plan's Scope Boundaries explicitly defer this; the Risk Analysis records it so it is not forgotten. |
| `coverage.json` is not produced when the placer test step fails, so the gate step does not run and the gate is bypassed | Medium | Medium | The gate step runs only on test success (default GitHub Actions behavior). This is acceptable: a failing test suite already blocks CI; the gate is not the only signal. If the test suite passes but `coverage.json` is missing (e.g. `--cov` misconfigured), the gate step fails with `coverage.json not found` — a hard block, not a silent bypass. |
| The `paths:` filter expansion to `tests/**` and `scripts/**` increases CI trigger frequency | Low | High | Acceptable — the filter expansion is necessary so edits to the gate script and the moved tests trigger CI. The additional triggers run the same `test` job; no new jobs. |
| Phase 2/3 never land because the allowlist does not shrink (no paydown cadence) | Medium | Medium | The 50% paydown gate is the structural forcing function — Phase 2 cannot land until Phase 1's allowlist shrinks by ≥50%. The `CLAUDE.md` documentation recommends a quarterly hardening sprint as the cadence. If the cadence is not established, the gate still delivers Phase 1 value (no new dead code in `temper_placer/core/`); the risk is stalled expansion, not regression. |
| `pytest-cov` version drift between local and CI environments | Low | Low | `pytest-cov>=4.1.0` is pinned in `packages/temper-placer/pyproject.toml:52` and `packages/temper-drc/pyproject.toml:39`. `uv sync --all-packages` (`.github/workflows/python-tests.yml:34`) resolves consistently. |

---

## Test Strategy

- **U1 (dead-path fix):** Verified by U2's real-instance round-trip test. No separate test for U1 — the fix is exercised by the relocated assertions.
- **U2 (rewritten tests):** The tests ARE the verification. Acceptance: `uv run pytest packages/temper-placer/tests/core/test_design_rules_unified.py` passes; reverting U1's line 801 fix causes `test_rule_export_import_for_debugging` to fail with `AttributeError`; reverting U1's `FileNotFoundError` causes `test_rule_loading_error_handling` to fail. `grep -r "Mock" packages/temper-placer/tests/core/test_design_rules_unified.py` returns no matches in the round-trip and error-handling tests (the copied `test_pipeline_consistency_validation` still uses `Mock` and is flagged as deferred cleanup).
- **U3 (coverage config):** Verified by `uv run pytest tests/core/ --cov=temper_placer.core --cov-report=json` (from `packages/temper-placer/`) producing a `coverage.json` with a populated `files.<path>.functions` block. CI log shows the `--cov-report=term` summary.
- **U4 (gate script):** The script's `--init` mode is verified by running it against the U3-produced `coverage.json` and confirming the allowlist is populated. The default mode is verified by temporarily adding `def new_helper(): ...` to `temper_placer/core/design_rules.py`, re-running coverage, and confirming the gate fails with a named message. The `--check-shrink` mode is verified by removing an allowlist entry without a test/deletion and confirming the gate fails. All three scenarios are documented in `CLAUDE.md §Coverage Gate` as the verification procedure.
- **CI integration:** The `Coverage gate (temper-placer/core)` step runs in the existing `test` job after the placer test step. No new job. The `paths:` filter includes `tests/**` and `scripts/**`.
- **Regression:** The existing `packages/temper-placer/tests/core/` suite continues to pass. The repo-root `tests/core/test_integration_monitor.py` and `tests/core/test_loop_convergence.py` are untouched. The `temper-workflow`, `temper-tools`, and `temper-drc` test steps are untouched.

---

## Deferred to Implementation

- **Baseline measurement (origin Open Question [Affects R6, A3]).** Run `uv run pytest tests/core/ --cov=temper_placer.core --cov-report=json` from `packages/temper-placer/` during U4 implementation **before** committing the allowlist. If the zero-coverage public-function count exceeds ~100 entries, narrow Phase 1 scope to `temper_placer/core/design_rules.py` only and record the narrowing in `CLAUDE.md`. This is the highest-risk unresolved measurement; it cannot be completed at planning time without running the coverage toolchain.
- **`CLAUDE.md` vs `AGENT_INSTRUCTIONS.md`.** Both exist at repo root. The plan targets `CLAUDE.md` (the companion plan N2 also targets `CLAUDE.md`). Confirm at implementation time that `CLAUDE.md` is the active convention; if `AGENT_INSTRUCTIONS.md` is the canonical AI-agent doc, target it instead.
- **`validate_pipeline_consistency` Mock cleanup.** The verbatim-copied `test_pipeline_consistency_validation` (lines 129-146) still uses `Mock()` at lines 134/138. Replacing those with real `DesignRules` instances is a follow-on cleanup ticket, not part of this plan. The ticket is filed during U2 implementation and referenced in the `CLAUDE.md §Coverage Gate` documentation as an example of the Mock-as-primary-argument anti-pattern the gate does not structurally catch (R2 catches it only for the round-trip test).
- **Allowlist paydown tickets.** Each `--init`-populated allowlist entry has a `# TODO: temper-xxx` placeholder. The implementation files real removal tickets for each entry (one per function or one per module, at the implementer's discretion) and replaces the placeholders with real ticket IDs in the same commit that introduces the allowlist. The ticket-filing cadence and ownership are recorded in `CLAUDE.md`.
- **Phase 2 / Phase 3 expansion.** Tracked as follow-on tickets gated on 50% allowlist paydown. Each phase begins with an `--init` run repopulating the allowlist for the newly-scoped modules. The `[tool.coverage.run] source` list in `pyproject.toml` is extended per phase. Not implemented in this plan.

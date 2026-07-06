---
date: 2026-07-01
topic: systematic-dead-code-elimination
---

# Systematic Dead-Code Elimination with Zero-Tolerance CI Gate

## Summary

Execute the proven 5-step deletion playbook against the 115+ dead-code baseline, starting with the 8 `# pragma: no cover` `PipelineOrchestrator` methods and their transitively unreachable imports, consolidate Router v6 from 92 source files to a documented core of <=15 files with >80% test coverage, and install a CI gate that blocks any PR that increases the dead-code count. Deletions are structural (import-graph driven), not speculative.

---

## Problem Frame

The temper-placer codebase carries 115 known dead-code entries (85+ unused variables in test validators, 15+ unused imports, 8 `# pragma: no cover` methods on `PipelineOrchestrator`, and multiple unreachable code blocks). Every contributor who opens the repo must construct a correct mental model of which code is alive and which is vestigial — and the dead code creates a second, wrong model. It hides bugs (unreachable branches that would fail if called), complicates refactors (grep returns false positives from 115 stale symbols), and blocks the Rust port (every dead module is a candidate for manual porting if not explicitly deleted).

The `PipelineOrchestrator` class in `pipeline/orchestrator.py` is the most acute example: all 8 phase-runner methods (`_run_input`, `_run_semantic`, `_run_topological`, `_run_preflight`, `_run_geometric`, `_run_routing`, `_run_refinement`, `_run_output`) are marked `# pragma: no cover` and superseded by the YAML-manifest-driven `dag_engine.py`. But the orchestrator is still instantiated in 9 consumer modules (`cli/pipeline_commands.py`, `cli/__init__.py`, `cli/andon_commands.py`, `io/dsn_boundary.py`, `profiling/timing_gate.py`, `cli/watch_commands.py`, `cli/pipeline.py`, `io/boundary_registry.py`, `adapters/orchestrator_adapter.py`) and has a 700+ line test suite that exercises only the manifest-parsing and callback-registration paths — not the phase runners themselves, which are dead. This creates a maintenance burden where contributors must update dead code to keep it importable.

Router v6 spans 92 source files and 165+ test files. The directory includes a Numba-compiled A* kernel (`astar_core_numba.py`), a SAT-based constraint solver (`sat_model.py`), a BMC encoding (`bmc.py`), and multiple wave-test files (`test_wave1_easy_wins.py` through `test_wave5_net_ordering.py`) that encode research-phase experiments. None of these are explicitly labeled "experimental" within the codebase — the directory presents all 92 files as production code. The consolidation target (<=15 core files) reflects the production routing pipeline: grid prep, occupancy, A* search, clearance, congestion, verifier, and manufacturing checks — the subset verified by the closure test and the CI parity gates.

The 5-step deletion playbook (`docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md`) was proven during the `routing/` -> `router_v6/` migration (66 files, 26K lines deleted across 17 atomic PRs). It has not been executed at the scale of the 115-entry baseline or against the Router v6 consolidation target.

---

## Requirements

### Deletion Execution

- **R1.** Delete all 8 `PipelineOrchestrator` phase-runner methods marked `# pragma: no cover` (`_run_input`, `_run_semantic`, `_run_topological`, `_run_preflight`, `_run_geometric`, `_run_routing`, `_run_refinement`, `_run_output`) along with their transitively unreachable imports. If the entire `PipelineOrchestrator` class becomes empty after phase-runner removal (no remaining callable methods), delete the class and its test suite (`test_orchestrator.py`, `test_orchestrator_integration.py`).

- **R2.** Deletions must follow the 5-step playbook from `docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md`: (1) Build import graph with `rg` — nodes = all target files, edges = directed imports, live roots = files imported externally. (2) Delete in reverse-topological order — zero-ref leaf files first, core last. (3) Build adapters to make consumer porting mechanical. (4) Port consumers and `git mv` salvageable utilities. (5) Final `git rm -r` after verifying zero external imports.

- **R3.** Import graph must be computed and verified before any deletion — no blind removal. The graph must be checked into the PR description or a tracking artifact so reviewers can confirm the deletion order is correct. Graph computation uses `rg "from temper_placer\."` and a BFS from live roots (any file imported from outside the target directory, or imported by a known-live test).

- **R4.** Consumers of deleted modules must be ported via adapter classes or re-pointed to the DAG engine equivalents before final deletion. For `PipelineOrchestrator`, the existing `orchestrator_adapter.py` pattern must be extended or a new adapter created so the 9 consumer modules (`cli/pipeline_commands.py`, `cli/__init__.py`, `cli/andon_commands.py`, `io/dsn_boundary.py`, `profiling/timing_gate.py`, `cli/watch_commands.py`, `cli/pipeline.py`, `io/boundary_registry.py`, `adapters/orchestrator_adapter.py`) switch to the DAG engine without logic rewrites. The `.importlinter` boundary contracts and `import-linter-allowlist.yaml` entries referencing `temper_placer.pipeline.orchestrator` must be cleaned up.

### Router v6 Consolidation

- **R5.** Router v6 is consolidated to a documented core of <=15 production source files with >80% test coverage per file (as measured by `pytest --cov` on the source file's dedicated test file). The 15-file core must include: the A* engine (`astar_core.py`, `astar_pathfinding.py`, `astar_grid.py`), occupancy grid, clearance engine, channel skeleton and widths, congestion analysis, constraints geometry, net classification, manufacturing checks (verifier, DRC), pipeline orchestration, and the public `__init__.py`. The exact list is refined during planning; the constraint is the file count ceiling.

- **R6.** Experimental and non-production routing variants (SAT solver `sat_model.py`, BMC encoding `bmc.py`, Numba A* kernel `astar_core_numba.py`, wave-test files, research-phase analyzers) are moved to a `routing-experiments/` directory outside the `router_v6/` DAG hot path. The `.importlinter` contracts must be updated to exclude the experiments directory from the `router-v6-public-interface-only` contract. Tests that exercise experimental variants move alongside their source modules. No new import boundary violations are introduced.

- **R7.** The core router files are documented with inline module-level docstrings identifying which routing strategy is production (the A*-based pipeline) and which moved files are research artifacts. The `router_v6/__init__.py` public interface must be pruned to export only production symbols; experimental exports are removed.

### CI Enforcement

- **R8.** A CI gate blocks any PR that increases the dead-code count above the established baseline. The gate is additive (ratcheting): it blocks new dead code but does not require immediate deletion of existing baseline entries. The mechanism: run Ruff `F401`/`F841` (already enforced) + a dead-code scanner against `packages/`, diff against the committed `.deadcode-allowlist.yaml` baseline, fail on net-new findings not present in the baseline. The `.deadcode-allowlist.yaml` is the canonical allowlist; the legacy `deadcode-baseline.py` (Vulture native format) is frozen at commit time and retired upon this gate's landing.

- **R9.** Dead code detection runs on every PR push using:
  - Ruff `F401` (unused imports) and `F841` (unused variables) — already enforced in `.github/workflows/python-tests.yml`, no new work.
  - A dedicated dead-code scanner (Vulture at `--min-confidence 80`, or a combination of Vulture + Ruff's `ARG` ruleset if that proves more actionable). The scanner runs over `packages/` and computes `detected - baseline`. A non-empty delta fails the gate.

- **R10.** A `.deadcode-allowlist.yaml` allows temporary deferral of dead-code entries with mandatory `owner` name and `delete_by` date. Format:
  ```yaml
  allowlist:
    - symbol: "some_dead_function"
      file: "packages/temper-placer/src/temper_placer/foo.py"
      owner: "username"
      delete_by: "2026-08-01"
      ticket: "temper-N7-123"
  ```
  Entries missing `delete_by` are immediate CI failures. Entries past their `delete_by` date fail CI with an escalation message — the `delete_by` date is the single binding gate. Entries without `ticket` references fail CI. A pre-escalation Slack reminder fires to the owner 7 days before the `delete_by` deadline; there is no independent 30-day counter that competes with the `delete_by` gate.

---

## Acceptance Examples

- **AE1. Covers R1, R2, R4.** Given `PipelineOrchestrator` is removed, when `rg 'PipelineOrchestrator'` runs against the `packages/` tree (excluding `.git/`), it returns zero hits. The existing `orchestrator_adapter.py` is either deleted (if all consumers ported) or reduced to a DAG-engine delegation shim with no reference to the deleted class.

- **AE2. Covers R5, R6.** Given Router v6 consolidation is complete, when `ls packages/temper-placer/src/temper_placer/router_v6/*.py` runs, it shows <=15 production files, and `ls packages/temper-placer/src/temper_placer/routing-experiments/*.py` shows the moved experimental modules (SAT, BMC, Numba kernel, wave-test files). `pytest --cov` reports >80% line coverage on each of the 15 core files.

- **AE3. Covers R8.** Given a PR adds a new module with an unused import chain that Ruff `F401` or the dead-code scanner detects and the baseline does not list, when the dead-code CI gate runs, the PR is blocked with a report listing the exact new entries, their file paths, and line numbers.

- **AE4. Covers R10.** Given a dead symbol is added to `.deadcode-allowlist.yaml` without `delete_by: YYYY-MM-DD`, when CI runs, the gate fails with "allowlist entry `symbol_name` missing `delete_by` date" — not a silent pass.

---

## Success Criteria

- `rg 'PipelineOrchestrator'` returns zero hits outside `.git/` in the `packages/` tree
- Router v6 production code fits in `ls router_v6/` (<=15 `.py` source files, excluding `__pycache__`)
- New dead code is blocked at PR time, preventing the 115+ baseline from growing
- `import-linter-allowlist.yaml` entries shrink by at least the number referencing deleted modules (4 entries reference `temper_placer.pipeline.orchestrator` transitively)
- Zero import-linter boundary violations after deletion and consolidation

---

## Scope Boundaries

- **Not deleting** Router v6 entirely — only consolidating to core production files plus moving experiments to `routing-experiments/`
- **Not deleting** test fixtures, golden data, or test infrastructure referenced by active tests (even if the source module moves to experiments)
- **Not deleting** scripts in `scripts/` unless proven unreachable from any documented workflow (CI, codegen, placer invocation)
- **Not requiring** immediate deletion of the 85+ `unused variable` entries in test validator files — these are low-priority, file-local, and caught by Ruff `F841`; they enter the baseline as acknowledged debt with `delete_by` dates
- **Not removing** `PipelineOrchestrator` if consumer porting reveals a hard dependency that the DAG engine cannot cover without breaking the closure test — in that case, the orchestrator is slimmed down to the minimum live subset
- Dead-code CI gate is **additive / ratcheting** (blocks increases, does not require immediate deletion of existing baseline)

---

## Key Decisions

- **Allowlist over inline suppression.** `.deadcode-allowlist.yaml` is the primary deferral mechanism rather than `# noqa` comments. Inline comments don't decay (they persist after the dead code is removed); the allowlist enforces `delete_by` dates and is reviewed weekly. `# noqa` is reserved for genuine false positives, not for deferred deletions.
- **Vulture at `--min-confidence 80`.** This threshold was validated during the `2026-06-22-009-feat-vulture-ruff-deadcode-gate` planning and catches high-confidence unreachable functions/classes without the long tail of false positives from dynamic dispatch patterns.
- **Ratcheting, not zero-target.** The gate blocks growth but does not set a deadline for eliminating the existing baseline. This avoids the trap where an overly ambitious cleanup deadline blocks feature work. Baseline entries have individual `delete_by` dates; escalation is entry-level, not baseline-level.
- **15-file ceiling for Router v6.** The ceiling is chosen as 2x the pipeline stage count (8 stages) — roughly one file per stage plus cross-cutting utilities (grid, clearance, constraints). It is a proxy for cognitive load, not a file-count optimization; the real goal is that every production routing file has a clear owner and documented purpose.
- **`.deadcode-allowlist.yaml` supersedes `deadcode-baseline.py`.** The existing gate plan (`docs/plans/2026-06-22-009-feat-vulture-ruff-deadcode-gate-plan.md`) established `deadcode-baseline.py` in Vulture's native whitelist format as the suppression file. This doc's `.deadcode-allowlist.yaml` (structured YAML with `owner`, `delete_by`, and `ticket` metadata) is the canonical allowlist. At gate landing, `deadcode-baseline.py` is frozen — its entries are migrated into `.deadcode-allowlist.yaml` and the file is retired (removed or reduced to a Vulture-native reference generated from the YAML source-of-truth).

---

## Dependencies / Assumptions

- The 5-step playbook (`docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md`) is correctly documented and reusable at scale for this target set
- The import-linter ratchet (`scripts/import_linter_gate.py`) is functional and will catch re-coupling after deletion — verified by the active CI gate
- Router v6 experimental variants (SAT, BMC, Numba) are not silently referenced by YAML DAG manifests or the deterministic pipeline stage graph — if they are, those references must be severed first
- The `dag_engine.py` YAML-driven pipeline is a complete functional replacement for `PipelineOrchestrator` for all 9 consumer modules — if gaps exist, they are filled by the adapter layer (R4)
- Vulture is available as a dev dependency and its `--min-confidence 80` output is stable enough for CI diffing
- The closure test (`tests/router_v6/ci_closure_test.py`) passes after consolidation with no route quality regression

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R5][User decision]** What is the exact list of 15 core router files? The candidate list is: `astar_core.py`, `astar_pathfinding.py`, `astar_grid.py`, `astar_monitor.py`, `occupancy_grid.py`, `clearance_engine.py`, `channel_skeleton.py`, `channel_widths.py`, `congestion_analysis.py`, `constraints_geometry.py`, `net_classification.py`, `pipeline.py`, `verifier.py`, `manufacturing_report.py`, `__init__.py`. Does this 15-file list match the intended core, or are there substitutions (e.g., `clearance_oracle.py` over `clearance_engine.py`, `route_stage.py` over `pipeline.py`)?
- **[Affects R6][User decision]** Which experimental variants are "active enough" to keep as documented research artifacts in `routing-experiments/` vs. delete entirely? The candidate experiments are: `sat_model.py`, `bmc.py`, `astar_core_numba.py`, `topology_solver.py`, `topology_extraction.py`. Should these be moved (preserving git history) or deleted (since they are research-phase and captured in git history)?
- **[Affects R10][User decision]** What is the maximum acceptable size for `.deadcode-allowlist.yaml` before it triggers an escalation? Suggested: 50 entries — above that, a weekly Slack notification to the #temper-eng channel with a link to an automated cleanup issue.

### Deferred to Planning

- **[Affects R8][Technical]** Which dead-code scanner configuration: Vulture alone (`--min-confidence 80`), Vulture + Ruff `ARG` rules, or `Deadcode` (which tracks symbol-level reachability via imports)? Vulture is the lowest-friction path (already in the dependency tree from the `2026-06-21` gate planning); `Deadcode` provides stronger guarantees but requires separate installation and configuration.
- **[Affects R4][Technical]** Are there any external consumers (one-off scripts, CI-only invocations, external tools) that import `PipelineOrchestrator` beyond the 9 identified consumer modules? A `uv tree --invert` or exhaustive `rg` over all non-`packages/` directories is needed before deletion.
- **[Affects R6][Technical]** Do the wave-test files (`test_wave1_easy_wins.py` through `test_wave5_net_ordering.py`) exercise production code paths or only research-phase benchmarks? If the latter, they move with the experiments. If they exercise production paths, they are renamed and kept.
- **[Affects R8][CI]** Should the dead-code gate run on every `push` and `pull_request` event, or only on `pull_request` to `main`? The existing Ruff step runs on both triggers with a `packages/**` path filter. Matching Ruff's trigger set avoids inconsistent enforcement between push and PR workflows.
- **[Affects R9][Tooling]** Should the dead-code scanner step be a shell one-liner (`vulture packages/ --min-confidence 80 --whitelist deadcode-baseline.py`) or a Python wrapper script that handles the `detected - baseline` diff, stale-baseline enforcement, and structured CI output? A wrapper script is preferred for the stale-baseline check (R5 from the parent `2026-06-21` requirements).

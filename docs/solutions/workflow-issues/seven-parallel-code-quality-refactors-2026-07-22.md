---
module: workflow
tags: [code-quality, refactoring, parallel-execution, compound-engineering, ce-ideate, ce-brainstorm, ce-plan, ce-work]
problem_type: workflow_issue
date: 2026-07-22
severity: informational
---

# Seven Parallel Code Quality Refactors in a Single Session

## Problem

The temper codebase accumulated quality debt across Python (type safety, monoliths, config parsing) and Rust (unwrap-heavy paths, clone proliferation, boundary serialization) with no systematic push to address it at scale.

## What Was Done

A full compound-engineering pipeline was executed in parallel for seven code quality improvement vectors:

| # | Topic | Pipeline |
|---|-------|----------|
| 1 | Encoder Decomposition — 1175-line monolith to 8 handler modules | ideate → brainstorm → plan → work |
| 2 | Unified PyO3 Bridge Framework with derive macros | ideate → brainstorm → plan → work |
| 3 | Rust Quality Sweep — unwrap/clone/dead_code elimination | ideate → brainstorm → plan → work |
| 4 | Cross-Language Domain Model Codegen (NetClassRules SSOT) | ideate → brainstorm → plan → work |
| 5 | Typed Configuration — 34 dataclasses to Pydantic | ideate → brainstorm → plan → work |
| 6 | Coverage Gate Phase 2 — full temper_placer scope | ideate → brainstorm → plan → work |
| 7 | Physics Parameter Provenance CI Gate | ideate → brainstorm → plan → work |

### Pipeline Metrics

- **Ideation**: 43 raw ideas across 6 frames → 7 survivors
- **Brainstorming**: 7 requirements documents (total ~111K)
- **Planning**: 7 implementation plans (total ~157K, 45 implementation units)
- **Execution**: 36 commits across 45 units, 0 test regressions

### Key Results

| Plan | Result |
|------|--------|
| PyO3 Bridge | New `temper-py-bridge` + `temper-py-bridge-derive` crates; 5 crates migrated; fixed `pins=[]` data-loss bug |
| Rust Quality Sweep | 3 unwraps → typed errors; clone reductions in 2 hot files; 5 dead_code sites resolved; workspace lint enforcement |
| Cross-Language Codegen | YAML manifest SSOT for 17-field NetClassRules; Jinja2 codegen for Python + Rust; CI enforcement via `git diff --exit-code` |
| Pydantic Config | 34 `@dataclass` types migrated to `BaseModel`; `config_loader.py` shrunk ~160 lines; 24 `_parse_*` functions eliminated |
| Coverage Gate Phase 2 | `temper_placer/core/` → full `temper_placer` scope; 1927 allowlist entries; Phase 1 paydown 62% (193→73) |
| Physics Provenance | AST-based CI gate enforcing `# source:` citations on physics constants; 0-allowlist baseline |
| Encoder Decomposition | 8 handler modules under `cp_sat/handlers/`; Protocol + decorator registration; `assert_never` exhaustiveness; `_encode_stub` + extra encoder dead code removed |

## Pattern: Compound Engineering Parallel Code Quality Pipeline

This session established a reusable pattern for accelerating code quality improvements:

1. **`ce-ideate`** — Generate many ideas, filter to highest-ROI survivors using adversarial critique with explicit basis requirements (`direct:`, `external:`, `reasoned:`)
2. **`ce-brainstorm`** (parallel) — Convert each survivor into a structured requirements document with actors, flows, acceptance examples, and scope boundaries
3. **`ce-plan`** (parallel) — Research the codebase, structure implementation units, specify test scenarios, define verification criteria
4. **`ce-code-review`** (post-execution) — Catch regressions introduced during parallel edits
5. **`ce-simplify-code`** (consolidation) — Identify cross-plan simplification opportunities (patterns that emerged across independently-implemented plans)

### When to Use

- When the codebase has accumulated quality debt across multiple dimensions
- When you have 3+ high-confidence improvement vectors identified through ideation
- When each improvement vector is independently scoped (minimal file overlap between plans)
- When the team is willing to invest in upfront requirements + planning to de-risk parallel execution

### Anti-Patterns

- **Over-collateralizing simple fixes**: Not every improvement needs the full pipeline. Single-file DRY fixes, trivial renames, or config changes with no behavioral impact should skip to `ce-work` directly.
- **Parallel execution on overlapping plans**: When two plans touch the same files (e.g., both modifying `pyproject.toml` or the same Rust crate), serialize them or merge into a single plan. Parallel execution on overlapping surfaces produces merge conflicts.
- **Skipping the synthesis step**: The cross-cutting synthesis in ideation catches combinations that individual frames miss. Running ideation without the merge+dedupe+axis-coverage step risks missing high-value compound ideas.

### Specific Lessons

1. **Pre-assign plan sequence numbers**: When dispatching parallel `ce-plan` sessions, pre-assign `NNN` sequence numbers to avoid filename collisions from racing git state reads.

2. **`.gitignore` Rust `target/` earlier**: New Rust crates created by `ce-work` compile to `packages/<crate>/target/`. Add `packages/*/target/` to `.gitignore` before creating new crates to avoid diff pollution.

3. **Verify keyword fallbacks survive SSOT migrations**: When migrating safety-critical string-matching code (e.g., `is_iso_component`, `resolve_safety_category`) to model-driven lookups, preserve the keyword fallback path so undeclared net classes still work. The change to require `BoardState` as a parameter (instead of just `&str`) is a broader interface change that must be verified against all callers.

4. **Protocol+decorator is sufficient for handler registration**: A generic `ConstraintHandler[T]` Protocol provides marginal benefit over `Callable[..., list[int]]` when the decorator already maps `ConstraintType` → handler and `assert_never` provides exhaustiveness. The typing is enforced at the handler function's own parameter annotation (`constraint: SeparatedConstraint`), not at the registry value type.

5. **Pydantic migration breaks positional `__init__` calls**: Migrating from `@dataclass` to `BaseModel` changes the constructor from accepting positional args to keyword-only. Auditing all call sites (especially in test files) is the most time-consuming part of the migration — budget for it.

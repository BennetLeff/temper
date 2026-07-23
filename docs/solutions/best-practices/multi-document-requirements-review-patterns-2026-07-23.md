---
title: "Multi-document parallel requirements review — recurring pitfalls and fix patterns"
date: 2026-07-23
category: best-practices
module: "docs/brainstorms"
problem_type: best_practice
component: "requirements-engineering"
severity: medium
applies_when:
  - "Writing requirements or brainstorm documents for cross-cutting refactoring initiatives"
  - "Reviewing multiple requirements documents in parallel for consistency and completeness"
  - "Defining scope boundaries in documents where multiple areas interact (e.g., circular deps, decomposition sequencing)"
  - "Applying systematic document review (persona-based) and incorporating findings"
tags:
  - requirements-engineering
  - doc-review
  - scope-boundaries
  - parallel-review
  - cross-cutting-refactoring
  - acceptance-criteria
  - tdd-pbt-methodology
  - safety-critical-firmware
---

# Multi-document parallel requirements review — recurring pitfalls and fix patterns

## Context

A session created 5 brainstorm requirements documents covering cross-cutting codebase refactorings (script consolidation, monster file decomposition, circular dependency resolution, CI pipeline consolidation, firmware transition table integration). Each document was then reviewed by 3-5 persona subagents (coherence, feasibility, scope-guardian, and adversarial where warranted). Across 86 findings, recurring patterns emerged that generalize to any multi-document requirements effort.

## Guidance

### 1. Scope boundaries need concrete lists, not open-ended clauses

Four of five documents contained unbounded scope escape hatches:

| Pattern | Example (before) | Fix (after) |
|---------|-----------------|-------------|
| "Any X that benefits" | "any script that benefits from the shared utilities" | "The following scripts: `check_coverage_gate.py`, `check_physics_provenance.py` (R5), `import_linter_gate.py`, `vulture_gate.py` (R6)" |
| "Any additional cycles discovered" | "Any additional cycles discovered during resolution" | "Any additional cycles discovered that involve `router_v6`, `deterministic`, `constraint_model`, `io`, or `constraints`" |
| "Remaining files are decomposed" | R7 delegates 6 files to "same principle" without a stopping condition | Added decision gate: "If a file is judged coherent despite >1,000 lines, it is explicitly waived with justification" |
| "Audit and repair" | R9 says "audit and repair scripts/manifest.yaml" | Narrowed to "repair YAML corruption only in manifest entries for scripts modified by this consolidation" |

**Rule:** Every scope boundary must name concrete items or define a decision gate. Open-ended clauses (`any`, `remaining`, `all`) are refactored to either a list, a bounded set, or an explicit waiver process.

### 2. "Identical results" vs "within tolerance" — pick one and standardize

Three documents used contradictory language for test regression guarantees:

- Monster files R10: "pass with identical results" vs AE3: "within tolerance"
- Circular deps Success Criteria: "produce identical results" vs CP-SAT non-determinism
- CI Pipeline: "gates are unchanged" vs "soft-launch gates now block instead of warn"

The root cause: CP-SAT solvers are non-deterministic. "Identical results" is infeasible for placement coordinates. The fix:

```diff
- pass with identical results after decomposition
+ pass with equivalent results (DRC count within ±0, deterministic placement
+ coordinates identical). If any variance is detected, it must be traceable
+ to a non-deterministic source (e.g., CP-SAT heuristic tie-breaking) and
+ documented.
```

**Rule:** Define a regression baseline, not identity. Use the existing CI tolerance band. For CP-SAT specifically, bit-identical results are never required — the existing tolerance/threshold in the test suite applies.

### 3. Unverified assumptions must be called out as prerequisites, not deferred to planning

Critical assumptions that gate whether a design approach works at all were marked as "Deferred to Planning" or left unverified:

| Document | Unverified Assumption | Consequence if Wrong |
|----------|----------------------|---------------------|
| Monster Files | Numba/OR-Tools seam in `loop.py` is clean enough to split | R4's sub-module split design is invalid |
| Circular Deps | `constraint_model` imports from `deterministic` are data-structures only | Protocol extraction may not break the cycle |
| Circular Deps | 20+ `__getattr__` symbols map 1:1 to importable submodules | Removing `__getattr__` breaks consumers |
| Firmware | `check_safety_interlocks()` is called globally, not per-state-handler | The doc mischaracterizes the current architecture |

The fix pattern: Promote these from "Deferred to Planning" to "Resolve Before Planning" or a new "Prerequisites" section. Add concrete verification steps:

```markdown
## Prerequisites (must be verified before implementation begins)

- **PREREQ-1.** Audit `constraint_model`'s imports from `deterministic`.
  Classify each as data-structure or orchestration. If orchestration
  imports exist, the protocol-only approach must be re-scoped.

- **PREREQ-2.** Before deleting `__getattr__`, replace with eager imports
  one symbol at a time in a draft branch. Verify `python -c 'from
  temper_placer.router_v6 import <symbol>'` succeeds for each.
```

**Rule:** Any assumption whose failure would invalidate the design approach is a prerequisite, not a deferred question. It must be verified before planning proceeds.

### 4. Every document needs abort criteria

Three of five documents had no defined stopping conditions. This is especially critical for:

- **Safety-critical firmware** — if a refactor surfaces an undocumented safety coupling, the implementer needs explicit permission to stop and escalate
- **Architectural changes** — if protocol extraction reveals the cycle is structural (not import-order), continuing to patch creates worse technical debt

The fix pattern:

```markdown
## Abort Criteria

If any of the following are discovered during implementation, stop and
escalate to architecture review:

1. `constraint_model` imports orchestration functions from `deterministic`
2. The router protocol requires >5 methods or involves types that cannot
   be extracted without restructuring `router_v6/`
3. Removing `__getattr__` reveals a second hidden cycle not documented here
```

**Rule:** Abort criteria must be specific, testable, and named. "Escalate if it looks broken" is not an abort criterion. "If >5 new import-linter violations can't be resolved within the PR" is.

### 5. Design decisions referenced by acceptance examples must be resolved first

Two documents had acceptance examples that presupposed unresolved decisions:

- Circular Deps AE2: "Given a protocol `RouterProtocol` exists in `core/interfaces.py`" — but the protocol location was an [Affects R1][User decision] open question
- CI Pipeline R4/R5 split decision: Listed as both "decided" in Key Decisions and "outstanding" in questions

**Rule:** Acceptance examples must be valid under any plausible resolution of outstanding questions, OR the question must be resolved before AE finalization. Use location-agnostic language: "Given a router protocol exists in a shared location (per the decision on R1)..."

### 6. Methodology sections need domain-specific verification strategies

Each document was given a methodology section matching TDD + PBT + inductive proof to its domain:

| Domain | Verification Strategy |
|--------|----------------------|
| Script library (stateless functions) | Hypothesis PBT: `find_repo_root()` generalizes by induction over directory depth |
| Monster file decomposition | PBT: decomposed modules' public API is indistinguishable from original for any input |
| Circular dependency (protocol extraction) | PBT: any conforming implementation succeeds through protocol on all call paths |
| CI pipeline (workflow YAML) | PBT: any valid parameter combination completes without error |
| Safety-critical firmware (state machine) | 207-cell BMC enumeration (9 states × 23 events) + induction: base cases hold → any transition sequence equivalent |

The firmware case is the most rigorous: the 207-cell enumeration mirrors the CP-SAT Physics Constraint Discipline (R24) BMC-exhaustive validation pattern already established in `docs/physics-verification-methodology.md`. The induction step — "if all base cases hold for single transitions, and event-detection logic is unchanged, then any sequence produces identical behavior" — is explicitly stated in the methodology.

**Rule:** Methodology sections must be domain-specific. "Use TDD" is not sufficient. Name the specific PBT invariant, the base cases being proven, and the induction principle that generalizes.

### 7. Cross-document sequencing dependencies must be explicit

Multiple documents had implicit sequencing requirements that contradicted each other:

- Monster Files: "No simultaneous dead-code removal"
- Circular Deps: "Must be sequenced after or alongside monster file decomposition for adapter.py"
- CI Pipeline: "Script consolidation into _lib/ (covered by separate brainstorm)"

The fix: Add a "Dependencies" or "Prerequisites" section naming the other doc and the specific dependency. The Circular Deps doc added:

```markdown
PREREQ-1: `router_v6/adapter.py` must be decomposed (per the
monster-file-decomposition requirements) before protocol extraction
begins.
```

## Why This Matters

Requirements documents that pass through a group chat or a single reviewer accumulate patterns of imprecision that don't surface until implementation. Unbounded scope clauses become "while I'm in here" refactors. "Identical results" gates fail in CI because CP-SAT is non-deterministic. Unverified assumptions become blocking discoveries mid-implementation. Parallel persona-based review (coherence, feasibility, scope-guardian, adversarial) surfaces these before planning.

The 86 findings across 5 documents followed a power-law distribution: 3 categories (scope boundaries, language precision, unverified assumptions) accounted for ~60% of findings. Targeting these categories during initial writing would prevent most review churn.

## When to Apply

- When producing >=3 requirements documents for a cross-cutting initiative where documents have sequencing dependencies
- When documents touch safety-critical, architectural, or non-deterministic systems (the "identical results" pattern only appears in these domains)
- When the initiative spans multiple languages or build systems (C firmware + Python + Rust + YAML CI)
- Before calling `ce-plan` on any document — resolve the "Resolve Before Planning" questions first

## Prevention Checklist

Before finalizing a requirements document, verify:

- [ ] Every scope boundary names concrete items or defines a decision gate — no "any X that benefits"
- [ ] "Identical results" is never used for non-deterministic systems; a tolerance-based regression baseline is defined
- [ ] All assumptions that would invalidate the design are promoted to prerequisites with verification steps
- [ ] Abort criteria exist: specific, testable, with an escalation target
- [ ] No acceptance example presupposes an unresolved decision
- [ ] Methodology section names the specific PBT invariant, base cases, and induction principle
- [ ] Cross-document sequencing dependencies are explicit (name the other doc and the specific dependency)
- [ ] Counts are exact (not "~2,500 estimated" but "2,797 lines measured 2026-07-23 via `wc -l .github/workflows/*.yml | tail -1`")

---
title: "Skill-Driven Multi-Pronged Refactoring with Parallel Subagents and Review Gate"
date: "2026-07-22"
category: workflow-issues
module: refactoring-workflow
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - Executing multi-file refactoring across a large codebase (C firmware + Python packages)
  - Using an external refactoring skill installed from LobeHub marketplace
  - Dispatching parallel subagents for independent, non-overlapping refactoring tasks
  - Needing review-gated quality assurance before merging parallel refactoring work
  - Collapsing multi-day manual refactoring into a single interactive session
tags:
  - skill-driven-refactoring
  - parallel-subagents
  - code-smell-analysis
  - review-gate
  - lobehub-marketplace
  - multi-language-cleanup
  - ce-code-review
  - ce-compound
related_components:
  - ce-code-review
  - ce-compound
  - market-cli
---

# Skill-Driven Multi-Pronged Refactoring with Parallel Subagents and Review Gate

## Context

A multi-language codebase (C firmware + Python packages, 292K+ lines) had accumulated structural debt across independent subsystems. No single developer had a systematic view of where refactoring would yield the highest return. Manual triage across 292K lines was impractical, and serial refactoring of one area at a time would bottleneck on context-switching and CI cycles.

**The discovery**: a community refactoring skill from the LobeHub marketplace (`danielsimonjr-claude-skills-refactoring-skill`) provided a structured 4-phase analysis pipeline (Torvalds/Carmack principles) that could survey the entire codebase, rank opportunities, and dispatch targeted agents — all within a single interactive session. When coupled with `ce-code-review` as a review gate and batched fix application, the pipeline collapsed what would be days of manual triage-and-refactor into a single session.

**Real results from this session (TEMPER induction cooker project, 17 files, +1802/-1187 lines):**
- `state_machine.c`: 1224 → ~550 lines (-55%), 680 duplicated handler lines removed
- God-function (102 lines) decomposed into 4 focused helpers
- 24 magic number call sites replaced with named constants
- 59 stubbed validator TODOs implemented, 10 deferred with `NotImplementedError`
- 3 pre-existing bugs discovered and fixed during extraction
- All tests: 60/60 C + 281/4 Python passing

## Guidance

### Stage 0: Install the refactoring skill from LobeHub

```bash
# Register (one-time per machine, creates credentials at ~/.lobehub-market/)
npx -y @lobehub/market-cli register \
  --name "YourAgentName" \
  --description "Brief personality description" \
  --source codex

# Install the skill into the local project
npx -y @lobehub/market-cli skills install <skill-identifier> --agent codex
```

The skill lands in `.agents/skills/<skill-identifier>/`. Read `SKILL.md` — it defines the analysis methodology, code smell taxonomy, refactoring process, and language-specific guidelines that all agents will follow.

### Stage 1: Codebase-wide code smell analysis

Dispatch a single explore agent that reads `SKILL.md` and surveys the entire codebase. Key measurements:

- Line counts per language/directory
- Functions exceeding 50 lines (god-function candidates)
- Deeply nested blocks (3+ levels)
- Magic number hotspots
- Long parameter lists (>5 params)
- TODO/FIXME/HACK markers indicating known technical debt
- Missing type hints in public APIs
- Dead/unreachable code
- Duplicated functions across files

**Explore agent prompt pattern:**

```
Read the SKILL.md at .agents/skills/<identifier>/SKILL.md.
Follow its Phase 1 methodology. Survey the entire codebase.
Produce a ranked top-N table with: file, function name, line count,
description of the smell, and a suggested surgical fix.
Do NOT apply any fixes yet.
```

Expected output: a ranked table with concrete file references and suggested operations. The agent should discover issues the user didn't know existed, not just confirm what was already suspected.

### Stage 2: Parallel dispatch of refactoring subagents

When the user approves all N ranks simultaneously, dispatch N subagents in parallel. The critical invariant: **each subagent gets identical output contract requirements and test-verification gates.** Non-overlapping file footprints (discovered during survey) enable true parallelism.

**Subagent instruction template for each rank:**

```
Apply the following refactoring:

FINDING: Rank <N>: <description>
FILES: <concrete paths>
SUGGESTED FIX: <surgical change>

CONTRACT:
1. Make only the changes described. Do NOT refactor unrelated code.
2. Read affected files before editing. Follow existing code conventions.
3. Build the relevant subsystem before reporting success.
4. Run the relevant test suite. Report pass/fail counts.
5. If tests fail, fix your changes — do not disable tests.
6. Report: (a) files changed, (b) lines added/removed, (c) test results,
   (d) any pre-existing bugs discovered during refactoring.

OUTPUT FORMAT:
  Files: <N> changed
  Diff: +<added> -<removed>
  Tests: <passed>/<total> passed
  Bugs found: <count> (list each with file:line and description)
```

**Real example — bugs discovered during handler extraction (Rank 1):**
Three divergences between `state_machine.c` and `state_handlers.c` were found:
- `state_preheat_update`: `check_safety_interlocks()` called without checking return value → fixed to `if (check_safety_interlocks()) { return; }`
- `state_heating_update`: Same safety check gap + incorrect `transition_to(STATE_FAULT)` instead of `enter_hardware_latched_fault(FAULT_THERMAL_RUNAWAY)`
- `state_cooldown_update`: Same fault path fix — `FAULT_COOLDOWN_OVERHEAT` was not using hardware-latched fault

These were fixed in the same pass and reported in the subagent's output contract.

### Stage 3: Review gate with ce-code-review

Run `ce-code-review` in interactive mode on the aggregated changes. The review dispatches 6+ personas in parallel (always-on: correctness, testing, maintainability, project-standards) plus conditional reviewers based on the diff:

```bash
# Start the review (from within the worktree with changes)
/ce-code-review interactive
```

For this session, 9 reviewers were selected:
- `correctness`, `testing`, `maintainability`, `project-standards` (always-on)
- `reliability` — firmware fault/safety interlock changes
- `adversarial` — diff exceeded 50 non-test lines, safety-critical embedded code
- `kieran-python` — Python visualization and validator code
- `ce-agent-native-reviewer`, `ce-learnings-researcher` (CE always-on)

Results: 14 findings (4 P0, 6 P1, 4 P2) across the aggregated changes.

**Critical P0 findings caught only by the review gate:**
- `sm_ctx` lost `static` linkage during extraction → globally mutable safety context (P0, adversarial)
- Watchdog starvation on early returns in `state_heating_update` (P0, adversarial)
- `intensity_level = 0` via zero-initialization → `intensity_max[-1]` UB (P0, adversarial)
- `assert_hardware_fault_cut()` returns void → undetected GPIO failure (P0, adversarial)

None of these were caught by the individual subagents — the review gate's adversarial persona was the only reviewer to identify them.

### Stage 4: Batched fix application

Dispatch a single fixer subagent to apply all review findings. For interactive mode, the user can choose "fix all" (best-judgment path) or walk through findings one by one:

```
Apply all review findings to the codebase.
Each finding has a file:line reference and suggested fix.

CONTRACT:
1. Apply each fix surgically. Do NOT refactor unrelated code.
2. If a fix conflicts with a pre-existing test, adapt minimally and note the conflict.
3. Build and run ALL test suites. Report pass/fail.
4. If any test fails that did NOT fail before, revert that fix and note the reason.

OUTPUT FORMAT:
  Applied: <N>/<total> clean, <M> adapted, <K> skipped
  C tests: <passed>/<total>
  Python tests: <passed>/<total>
  Adaptations: <list each with reason>
```

Real adaptation example: P0 finding #10 (add `check_safety_interlocks()` to COOLDOWN state) was adapted because the COOLDOWN_OVERHEAT test expects heatsink >100°C during normal cooldown, and adding the interlock would trigger false `FAULT_OVER_TEMP`. The fixer added `watchdog_feed()` to early-return paths in COOLDOWN but skipped the interlock call, documenting the pre-existing design condition.

### Stage 5: Single cohesive commit

All changes land on one branch with one commit. The message enumerates each operation:

```bash
git checkout -b refactor/skill-driven-cleanup
git add -A
git commit -m "refactor: multi-pronged codebase cleanup guided by refactoring SKILL

<enumerate each rank with files changed and lines +/->
<enumerate review findings applied with counts>
<list bugs discovered during refactoring>"
git push origin refactor/skill-driven-cleanup
```

## Why This Matters

**Serial approach:** 5 refactoring areas × ~45 min each (survey + impl + review + fix + commit) = ~4 hours. Context switching between C and Python adds cognitive overhead. Each area would be a separate PR, fragmenting narrative and requiring 5× review cycles.

**Parallel skill-driven approach:** ~1 hour total:
- Survey: one explore agent (~5 min)
- Parallel dispatch: 5 subagents (~15 min wall-clock)
- Review: 9 personas (~10 min)
- Fix application: 1 fixer (~10 min)
- Commit: 1 commit (~5 min)

The bottleneck shifts from serial implementation to subagent completion latency. The skill's `SKILL.md` provides a shared protocol every agent understands, eliminating coordination overhead.

**Review gate is the safety net.** Individual subagents make mistakes — removing `static` from a struct, skipping watchdog feeds on early returns, leaving magic numbers in newly-added code. The adversarial + correctness reviewers catch what individual subagents miss. Without the gate, 4 P0 firmware safety regressions would have shipped.

## When to Apply

- Codebase spans multiple languages or subsystems with independent refactoring targets
- A refactoring skill with a defined protocol (analysis → ranking → dispatch → cleanup) is available
- Subagent dispatch is available and subagents can run tests independently
- A review gate skill is available to catch cross-cutting issues
- File change footprints are non-overlapping (discovered during survey, not assumed)
- **NOT** when refactoring areas are tightly coupled — run sequentially with intermediate rebases
- **NOT** when the codebase is <50K lines — manual survey is faster and more accurate
- **NOT** when automated test coverage is absent in refactored areas — no safety net for parallel agents

## Examples

### Full command sequence

```bash
# Stage 0: Install skill
npx -y @lobehub/market-cli register --name "AgentName" --description "..." --source codex
npx -y @lobehub/market-cli skills install <identifier> --agent codex

# Stage 1: Explore (in-session agent dispatch)
# "Read .agents/skills/<id>/SKILL.md. Survey entire codebase for top 5 refactoring
#  opportunities. Produce ranked table. Do NOT apply fixes."

# Stage 2: After user approves all 5 ranks, dispatch 5 agents in parallel
# Each gets surgical instruction with test-verify contract

# Stage 3: Review gate
# In-session: run ce-code-review in interactive mode
# 9 personas produce 14 findings across P0-P2

# Stage 4: After user says "fix all"
# Single fixer subagent applies all findings, runs all tests

# Stage 5: Commit
git checkout -b refactor/skill-driven-cleanup
git add -A
git commit -m "refactor: skill-driven multi-pronged codebase cleanup

5 refactoring operations via parallel subagents,
14 review findings applied, 60/60 C + 281/4 Python tests passing"
git push origin refactor/skill-driven-cleanup
```

### Subagent output contract (real example from Rank 1)

```
[RANK 1 COMPLETE]
Files: 3 changed (state_handlers.c, state_handlers.h, state_machine.c)
Diff: +48 -697
Tests: 60/60 passed (C firmware test suite)
Bugs found: 3
  - state_preheat_update: safety interlock check ignored return value
  - state_heating_update: same interlock gap + wrong fault escalation path
  - state_cooldown_update: FAULT_COOLDOWN_OVERHEAT not using hardware-latched fault
```

## Related

- `docs/solutions/workflow-issues/parallel-worktree-sprint-pipeline.md` — Canonical six-stage pipeline for parallel subagent dispatch with worktree isolation and batch merging.
- `docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md` — Risk doc: silent file loss during parallel worktree merge batches. The manifest-verification pattern is essential for this workflow.
- `docs/solutions/design-patterns/decomposing-monolithic-stage-micro-stages-2026-06-22.md` — Eleven-step extraction pattern with golden fixture parity tests. Directly applicable to god-function decomposition (Stage 2).
- `docs/solutions/test-failures/refactor-breakage-test-imports-stale-references-2026-06-29.md` — Prevention rule: grep all call sites before committing extracted handlers or renamed constants.
- `docs/solutions/best-practices/safety-firmware-testing-patterns.md` — SIL fault injection testing and runaway boundary interlock ordering. Re-run before merging any PR that touches `state_machine.c`.
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — CI gate enforcement pattern (baseline + monotonic shrink). Provides the mental model behind the review gate constraint.

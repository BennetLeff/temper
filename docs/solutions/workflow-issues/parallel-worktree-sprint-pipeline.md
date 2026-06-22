---
title: Parallel Worktree Sprint Pipeline
date: 2026-06-22
category: workflow-issues
module: tooling/bd
problem_type: workflow_issue
component: tooling
severity: medium
applies_when:
  - Shipping 5+ independent tasks in a sprint with non-overlapping file changes
  - Parallelizing plan-to-merge throughput when human review is not the bottleneck
  - Automating doc-review + safe fix application across a batch of plans
tags:
  - parallel-worktree
  - sprint-pipeline
  - bd-workflow
  - subagent-dispatch
  - auto-merge
  - conflict-resolution
  - doc-review
---

# Parallel Worktree Sprint Pipeline

## Context

When shipping 15 plans across 3 sprints, sequential work on one task at a time becomes the bottleneck. Each plan requires its own worktree, implementation, verification, and merge. Running them serially wastes wall-clock time—especially when tasks have no overlapping file dependencies and the primary friction is merge throughput, not implementation complexity.

The parallel worktree pipeline replaces serial task execution with batch-parallel dispatch, doc review, and automated conflict resolution, collapsing what would be a week of serial merges into hours.

## Guidance

The pipeline has six stages. Run each stage to completion before starting the next.

### Stage 1: Doc review all plans in parallel (headless mode)

Submit every plan document through doc review in headless mode so no blocking prompts stall the batch. Collect review findings as structured output.

```bash
# For each plan doc in docs/plans/
for plan in docs/plans/plan-*.md; do
  /ce-doc-review "$plan" mode:headless &
done
wait
```

### Stage 2: Auto-apply safe_auto fixes

Extract and apply fixes flagged as `safe_auto` from review output. These are mechanical corrections (YAML formatting, broken links, missing required frontmatter fields) that carry no risk of semantic change.

```bash
# Apply safe_auto fixes to each plan doc
python3 tools/apply_safe_auto_fixes.py --from-review output/plan-*.review.json
git add docs/plans/ && git commit -m "chore: auto-apply safe_auto doc-review fixes across plans"
```

### Stage 3: Create worktrees for non-overlapping batches

Group tasks into batches where file changes do not overlap. Each batch runs in parallel; batches run sequentially. Use `bd-work` to create isolated worktrees from `main`.

```bash
# Batch 1: tasks temper-001, temper-002, temper-003 (disjoint files)
bd-work temper-001 &
bd-work temper-002 &
bd-work temper-003 &
wait

# Batch 2: tasks temper-004, temper-005, temper-006
bd-work temper-004 &
bd-work temper-005 &
bd-work temper-006 &
wait
```

Determine non-overlapping batches by diffing the planned file changes for each task:

```bash
# Map each task to its file footprint, then greedily pack batches
for task in temper-{001..015}; do
  echo "$task: $(bd show "$task" --json | jq -r '.planned_files[]')"
done | python3 tools/pack_non_overlapping_batches.py --batch-size 3
```

### Stage 4: Dispatch ce-work subagents in parallel

For each batch, dispatch `ce-work` subagents—one per worktree—to implement the plan. Subagents run independently since worktrees isolate filesystem state.

```bash
# In each worktree, dispatch a ce-work subagent
for wt in ~/worktrees/temper/temper-{001..003}; do
  (cd "$wt" && /ce-work "Implement plan $(basename $wt)" mode:headless) &
done
wait
```

Subagents commit and push within their worktrees. The orchestrator monitors status.

### Stage 5: Merge sequentially with auto-conflict resolution

After all subagents in a batch push, merge each branch into `main` sequentially. Non-overlapping branches merge cleanly. When a conflict does arise, resolve with `-X theirs` since each worktree's changes are independent and the later merge wins by recency.

```bash
git checkout main
for task in temper-001 temper-002 temper-003; do
  git merge "$task" -X theirs --no-ff -m "merge: $task (auto-conflict resolution)"
done
git push origin main
```

The `-X theirs` strategy is safe here because:
- Batches are constructed to have zero file overlap
- If a conflict still occurs (e.g., generated files, shared config), the later task's version is the authoritative one
- No human is in the loop to resolve interactively

### Stage 6: Cleanup and close

```bash
# Close completed tasks in bd
for task in temper-{001..015}; do
  bd close "$task" --reason "Done - parallel worktree pipeline" --json
done

# Remove merged worktrees
bd-cleanup-worktrees
```

## Why This Matters

**Serial pipeline (before):** 15 tasks × ~30 min each (impl + review + merge) = ~7.5 hours of wall-clock time, plus context-switching overhead between tasks.

**Parallel pipeline (after):** 15 tasks in 5 batches of 3 × ~30 min + merge overhead = ~3 hours. The bottleneck shifts from task execution to batch boundary synchronization.

The key insight: worktrees provide filesystem isolation, enabling true parallel implementation without cross-contamination. Paired with non-overlapping batching and `-X theirs` merge, the pipeline eliminates the serial merge queue entirely.

## When to Apply

- When shipping 5+ independent tasks where file change footprints are known or predictable
- When doc-review overhead is high and `safe_auto` fixes can be batched
- When subagent dispatch is available and subagents can operate in isolated worktrees
- When merge conflicts are expected to be minimal (non-overlapping file sets) or safely resolvable by recency
- **Not** when tasks share critical-path files that require careful human conflict resolution
- **Not** when only 1-3 tasks exist in the sprint (serial is simpler and the overhead of batching outweighs gains)

## Examples

### End-to-end sprint run (condensed)

```bash
# === PRE-FLIGHT ===
# 1. Review all plans in parallel
for plan in docs/plans/sprint-*.md; do
  /ce-doc-review "$plan" mode:headless &
done
wait

# 2. Apply safe_auto fixes
python3 tools/apply_safe_auto_fixes.py --from-review output/*.review.json
git add docs/plans/ && git commit -m "chore: auto-apply safe_auto fixes"

# 3. Batch tasks by file footprint
python3 tools/pack_non_overlapping_batches.py \
  --tasks temper-001 temper-002 temper-003 temper-004 temper-005 \
  temper-006 temper-007 temper-008 temper-009 temper-010 \
  temper-011 temper-012 temper-013 temper-014 temper-015 \
  --batch-size 3 > batches.json

# === BATCH LOOP ===
for batch in $(jq -c '.[]' batches.json); do
  tasks=$(echo "$batch" | jq -r '.[]')

  # 4. Create worktrees in parallel
  for task in $tasks; do
    bd-work "$task" &
  done
  wait

  # 5. Dispatch subagents
  for task in $tasks; do
    (cd ~/worktrees/temper/"$task" && /ce-work "Implement $task" mode:headless) &
  done
  wait

  # 6. Merge into main with auto-conflict resolution
  git checkout main
  for task in $tasks; do
    git merge "$task" -X theirs --no-ff -m "merge: $task (batch auto-merge)"
    # Recover and continue if a subagent failed to push
    if [ $? -ne 0 ]; then
      echo "WARNING: merge conflict in $task, using theirs strategy"
      git checkout --theirs . && git add . && git commit --no-edit
    fi
  done
  git push origin main
done

# === POST-FLIGHT ===
# Close all tasks
for task in temper-{001..015}; do
  bd close "$task" --reason "Done - parallel worktree pipeline" --json
done
bd-cleanup-worktrees
```

### Worktree creation detail

```bash
# bd-work handles: claim validation, branch checkout, worktree creation
# Isolated worktrees live under $BD_WORKTREE_ROOT (default ~/worktrees)

$ bd-work temper-001
Creating new worktree for temper-001 from main
✓ Now working on temper-001 in ~/worktrees/temper/temper-001
  Run 'bd-done' when task is complete

$ bd-worktrees
Active worktrees for temper:
  temper-001 → ~/worktrees/temper/temper-001  (5 minutes ago)
  temper-002 → ~/worktrees/temper/temper-002  (4 minutes ago)
  temper-003 → ~/worktrees/temper/temper-003  (3 minutes ago)
```

### Merge fallback when `-X theirs` is insufficient

```bash
# If -X theirs fails (rare: binary files, renames), fall back to manual strategy
git merge "$task" -X theirs --no-ff -m "merge: $task" || {
  # Attempt checkout-theirs on conflicted files
  git diff --name-only --diff-filter=U | while read f; do
    git checkout --theirs "$f" && git add "$f"
  done
  git commit --no-edit || git merge --abort
}
```

## Related

- `docs/guides/GPBM_WORKFLOW.md` — Gather-Plan-Build-Measure loop integrated with bd and worktrees
- `tools/bd-worktree-helpers.sh` — `bd-work`, `bd-done`, `bd-cleanup-worktrees` implementations
- `tools/bd-multiagent.sh` — Multi-agent coordination helpers (claims, takeover, heartbeat)
- `AGENTS.md` — Worktree commands and multi-agent coordination reference
- `/ce-work` — Subagent dispatch for isolated implementation
- `/ce-doc-review` — Parallel document review with safe_auto fix extraction

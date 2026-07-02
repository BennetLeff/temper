---
title: Silent source code loss during parallel worktree merge batches
date: 2026-07-01
category: workflow-issues
module: git-merge-workflow
problem_type: workflow_issue
component: development_workflow
severity: critical
applies_when:
  - Multiple feature branches are merged to main in rapid succession
  - Merge conflict resolution is performed across parallel worktrees
  - A feature touches files that overlap with other features in the merge queue
symptoms:
  - Source files silently dropped from merge commits during conflict resolution
  - Subset of PR files survive the merge; others vanish without error
  - Lost code recoverable only from git reflog or surviving worktrees
  - Tests pass but features are non-functional because source code is absent
root_cause: missing_workflow_step
resolution_type: workflow_improvement
tags:
  - git-merge
  - worktree
  - conflict-resolution
  - silent-data-loss
  - verification
related_components:
  - ci-pipeline
  - code-review
---

# Silent Source Code Loss During Parallel Worktree Merge Batches

## Context

Six initialization features (#108-#113) were implemented in parallel worktrees, reviewed, and merged to main in rapid succession. During merge conflict resolution for PRs #109, #111, and #112, entire source files were silently dropped:

- **Thermal anchoring** (PR #111): `thermal_potential.py`, `thermal_anchoring_stage.py`, `pipeline_default.yaml` DAG entry — all lost. Only `config_loader.py` survived the merge commit.
- **Constraint-weighted Laplacian** (PR #109): `test_constraint_weights_unit.py`, `test_constraint_weights_properties.py`, `test_constraint_weights_ablation.py` — all lost. The source module (`constraint_weights.py`) survived, but 74 tests were dropped.

The loss was discovered through a post-merge audit, not through CI (tests passed because the missing code had no import chain test), and recovery required manual file extraction from remaining worktrees and git history (`git show <merge-commit>^2:<path>`).

## Guidance

### Before merging a feature branch

1. **Collect the expected file manifest** from the feature branch against the merge base:
   ```bash
   BASE=$(git merge-base HEAD origin/main)
   git diff --name-only --diff-filter=ACMR $BASE...HEAD > /tmp/expected-files.txt
   ```

2. **After the merge completes**, verify every expected file exists in the merged tree:
   ```bash
   while read f; do
     git show HEAD:"$f" >/dev/null 2>&1 || echo "MISSING: $f"
   done < /tmp/expected-files.txt
   ```

3. **For parallel batch merges**, verify the UNION of all batch branches' manifests exists in HEAD AFTER the final batch merge completes. Do not rely on the merge commit's `--name-only` — it only shows files touched by the merge diff, not files that were correctly carried through.

### Retroactive check (when you suspect loss)

```bash
# Compare files added by a merged PR against current HEAD
MERGE_COMMIT=<sha>
git diff --name-only --diff-filter=A ${MERGE_COMMIT}^1...${MERGE_COMMIT}^2 | while read f; do
  git show HEAD:"$f" >/dev/null 2>&1 || echo "LOST: $f"
done
```

### Recover lost files

Files are recoverable from the second parent of the merge commit (the feature branch tip):
```bash
git show ${MERGE_COMMIT}^2:path/to/missing_file.py > path/to/missing_file.py
```

## Why This Matters

Silent file loss is worse than a merge conflict — conflicts are visible and demand resolution. When a merge completes without error but drops files, the only detection mechanisms are:

1. **Import chain tests** — if module A imports from missing module B, import fails at test collection. But if the missing file is a new module with no importer in the merged tree, nothing breaks.
2. **Post-merge audit** — the manifest check described above.
3. **Feature smoke test** — actually running the feature through its activation path.

Without these, lost code can remain undiscovered indefinitely, wasting the original implementation effort and creating false confidence that a feature is live.

## When to Apply

- **Always** when merging a batch of 2+ parallel worktree branches that share overlapping file targets (config.py, train.py, initialization.py are common overlap points in the temper-placer optimizer).
- **When a merge conflict was resolved manually** — the resolution may have accepted one side's version and dropped the other's additions rather than merging both.
- **When a branch was rebased before merge** — rebase can silently drop commits that conflict.
- **When CI passes but the feature doesn't work** — suspect silent loss.

## Examples

### The merge that lost thermal anchoring

```bash
# PR #111 merge commit
$ git show --name-only 1a49607a
packages/temper-placer/src/temper_placer/io/config_loader.py  # ONLY file preserved

# Recover from second parent
$ git diff --name-only 1a49607a^1...1a49607a^2 | grep -v config_loader
packages/temper-placer/src/temper_placer/physics/thermal_potential.py
packages/temper-placer/src/temper_placer/pipeline/stages/thermal_anchoring_stage.py
packages/temper-placer/tests/physics/test_thermal_potential.py
packages/temper-placer/tests/pipeline/stages/test_thermal_anchoring_stage.py
packages/temper-placer/configs/pipeline_default.yaml
# ... all lost
```

### The merge that lost constraint_weights tests

```bash
$ git show --name-only e712568b | grep test_constraint
# (no output — no test files in merge commit)

$ git diff --name-only e712568b^1...e712568b^2 | grep test_constraint
packages/temper-placer/tests/test_constraint_weights_unit.py
packages/temper-placer/tests/test_constraint_weights_properties.py
packages/temper-placer/tests/test_constraint_weights_ablation.py
# All three recovered: git show e712568b^2:packages/temper-placer/tests/...
```

## Related

- `docs/solutions/workflow-issues/parallel-worktree-sprint-pipeline.md` — canonical worktree pipeline doc; describes batch merge strategy but doesn't cover verification
- `docs/solutions/workflow-issues/infrastructure-components-unwired-2026-06-28.md` — similar pattern of code merged but unreachable; different cause (missing wiring vs merge loss)
- `docs/solutions/workflow-issues/2026-07-01-001-dead-code-from-features-with-no-activation-surface.md` — companion doc covering the config-flag activation surface problem discovered in the same audit

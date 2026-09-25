# Storage options 52

This is a read-only storage triage. I did not delete, prune, hash, or
decompress simulation artifacts, and I did not inspect personal folders. The
filesystem currently has 12,166,168 KiB free, about 11.60 GiB, on the volume
shared by the project and `/private/tmp/temper-pkgs-1-4`.

The ordinary regenerable build locations are small in the inspected trees:

- `/Users/bennet/Desktop/temper/.venv`: 76 KiB; `.pytest_cache`: 24 KiB.
- `/private/tmp/temper-pkgs-1-4/.venv`: 8.4 MiB.
- The inspected `source-build-*/build` directories in the temper package
  worktree are 4–48 KiB each.
- `.opencode/node_modules` in the main checkout is 61 MiB.

There is no multi-gigabyte `target-shared` directory in the main checkout or
the package worktree. The repository's report-only gate did find one concrete
regenerable Cargo candidate in another registered worktree:

```text
/Users/bennet/Desktop/temper-drc-publishing/target-shared  785.5 MiB
```

The supported route is the repository's
`scripts/check_no_worktree_target_dirs.py --clean` (or the corresponding
`make check-worktree-target-dirs CLEAN=1`) after verifying its `CACHEDIR.TAG`
safety predicate. I did not run the cleaning mode. This candidate is below the
30 GiB shortfall and is outside the two requested roots.

The only concrete multi-gigabyte items found in the inspected project tree are
generated simulation/evidence outputs inside two registered, dirty worktrees:

- `/Users/bennet/Desktop/temper/.worktrees/codex/ar-erc-contract` is 6.5 GiB.
  Its `zapote/power-entry/shunt-assembly` subtree is 3.6 GiB across many
  run directories. The worktree is on branch `codex/ar-erc-contract`, has
  modified and untracked source files, and was modified 2026-09-18.
- `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`
  is 16 GiB. `harness-lab/audits` is 8.6 GiB: `buck-20260909` is 6.7 GiB
  and `buck-final-20260910` is 2.0 GiB. These contain generated
  `waveform.raw` evidence files (the largest observed was about 720 MB).
  Its `zapote/power-entry/shunt-assembly` is another 3.6 GiB. This worktree
  is seven commits ahead of its remote and has many modified source files.

Those outputs are reproducible in principle, but they are evidence rather
than identified caches. The worktrees are registered and dirty, so deleting
their run directories or removing either worktree could destroy uncommitted
work or evidence. The documented cleanup route for a completed worktree is
`git worktree remove <path>` followed by branch cleanup, after its owner
confirms the work is merged; it is not safe to apply here. I did not infer that
these branches are abandoned.

The main checkout's `.git` is 3.6 GiB, but it is the shared object database,
not disposable cache; manual pruning would affect all worktrees. No safe
multi-gigabyte reclaim target was found that can be removed without an owner
decision. This limited project-tree inspection did not identify a safe
automatic reclaim route large enough for the roughly 30 GiB shortfall. The
repository's Cargo-cache cleaner alone cannot provide it. Other user-managed
storage was not inspected; these findings do not require deleting either
worktree's evidence.

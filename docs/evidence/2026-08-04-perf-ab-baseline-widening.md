<!-- provenance: commit=f2b09d84673b3a18d8fabe454230f1b240148f3d dirty=false -->
# The performance A/B baseline could not grow: root cause, capture path, and the widened baseline (2026-08-04)

Companion to `2026-08-04-perf-ab-harness-noise-floor.md`, which set the margins.
This document is about the *other* side of the comparison — the baseline they
are measured against — and it closes follow-up "reason 2" in that document.

## Summary

`PR Performance Comparison` became a required context in #686 and immediately
began failing PRs that changed nothing the benchmark measures. The margins were
not the problem; the baseline was.

`scripts/pr_perf_compare.py` medians the trailing **5** rows per
`(module, board, stage)`. `power_pcb_dataset/metrics/perf_ab_baseline.jsonl`
held **1** row per stage. A one-row median is that row, so no smoothing was
applied at all and the full CI spread landed against the 20% margin.

The reason it held one row is structural, not an oversight:
`.github/workflows/pr-perf-check.yml` triggered on **`pull_request` only**.
Rows are measured on the branch under test, and a PR's rows are never
committed. No row could ever be measured on `main`, so the file had no growth
path — while `benchmarks/perf_ab.py`'s own capture instructions read "prefer
several runs from main once they exist." They could not exist.

Fixed by (1) adding a capture path on `main`, (2) harvesting the CI rows that
already existed in workflow logs, and (3) pinning both in tests. **No margin was
changed:** `TIMING_MARGIN` is still `0.20`.

---

## 1. The false positive, reproduced

PR #544 (`fix/drc-regression-baseline`, merged as `ebf9326ff`) contributes
exactly one hunk over `main`:

```
packages/temper-placer/src/temper_placer/router_v6/channel_widths.py | 8 +++++++-
1 file changed, 7 insertions(+), 1 deletion(-)
```

a `typing.cast()` around an existing local, which compiles to `return val` — a
runtime no-op — in `router_v6/channel_widths.py`, a module the
bottleneck-geometry benchmark does not import. Run `30929524197` reported:

| stage | metric | baseline | PR | delta |
|---|---|---|---|---|
| `hard_blocked_batch` | `rust_over_oracle_ratio` | 0.328949 | 0.416550 | **+26.6% REGRESSION** |

The informational wall times in the same run say what actually happened — the
runner was slower, and the ratio did not fully normalise it:

| stage | metric | baseline | PR | delta |
|---|---|---|---|---|
| `cell_capacity_batch` | `rust_wall_us` | 287.984 | 410.402 | +42.5% |
| `hard_blocked_batch` | `rust_wall_us` | 90.687 | 143.095 | +57.8% |

## 2. The lone row was biased, not merely unsmoothed

Six CI readings now exist for the same unmodified kernels. Every one of the five
taken after the baseline row sits **above** it:

| stage | n=1 baseline | 5 later CI readings | spread vs the lone row |
|---|---|---|---|
| `cell_capacity_batch` | 0.157191 | 0.166645 – 0.171824 | +6.0% … +9.3% |
| `hard_blocked_batch` | 0.328949 | 0.343520 – 0.416550 | +4.4% … +26.6% |

Mean offset ≈ **+10.5%**. That is a constant bias, not symmetric noise: the
baseline was captured at 15:23Z on what was evidently a fast, uncontended
runner, and every later reading pays a fixed penalty against it. A biased
baseline spends half the 20% margin before any real variance is measured,
leaving ~10 points of working headroom against a measured worst CI excursion of
9.9%. The margin was saturated by construction.

## 3. Leave-one-out over the widened baseline

Each reading scored against a 5-row median built from the other five
(`scripts/pr_perf_compare.py` unmodified, `TIMING_MARGIN = 0.20`):

| commit | stage | ratio | vs n=1 baseline | vs leave-one-out n=5 |
|---|---|---|---|---|
| `5b3d98933` | `cell_capacity_batch` | 0.157191 | +0.0% | −7.6% |
| `5b3d98933` | `hard_blocked_batch`  | 0.328949 | +0.0% | −10.4% |
| `548d12936` | `cell_capacity_batch` | 0.169852 | +8.1% | −0.2% |
| `548d12936` | `hard_blocked_batch`  | 0.368897 | +12.1% | +2.4% |
| `2787565de` | `cell_capacity_batch` | 0.171824 | +9.3% | +1.2% |
| `2787565de` | `hard_blocked_batch`  | 0.416550 | **+26.6% REGRESSION** | **+15.7% OK** |
| `a950a691c` | `cell_capacity_batch` | 0.170148 | +8.2% | +0.2% |
| `a950a691c` | `hard_blocked_batch`  | 0.343520 | +4.4% | −6.4% |
| `7a6ec0577` | `cell_capacity_batch` | 0.166645 | +6.0% | −2.1% |
| `7a6ec0577` | `hard_blocked_batch`  | 0.360175 | +9.5% | −1.9% |
| `f7179a469` | `cell_capacity_batch` | 0.171498 | +9.1% | +1.0% |
| `f7179a469` | `hard_blocked_batch`  | 0.367011 | +11.6% | +1.9% |

Excluding the baseline commit's own rows: **1 of 10 readings trips the 20%
margin against n=1; 0 of 10 against leave-one-out n=5.**

The #544 row is *out of sample* in its leave-one-out cell, so +15.7% is not a
circular result. Against the baseline exactly as committed (n=6, which includes
#544's own rows) the same reading scores +13.5%.

**Honest caveat.** +15.7% clears 20% but is not comfortable. `hard_blocked_batch`
is the noisier of the two stages — it is the shorter benchmark (rust arm ~90–190
µs versus ~290–610 µs), so fixed per-call overhead is a larger fraction of it.
More rows will shrink this; if a clean PR trips it again, the answer is more
rows or a longer benchmark, **not** a wider margin.

## 4. Row provenance — every accepted run, and why

A row is a usable baseline sample only if the commit that produced it does not
modify the code the benchmark measures. Verified per row by diffing each commit
against `origin/main` restricted to: `packages/temper-geometry/src/{bottleneck_geometry,bridge,lib}.rs`,
`packages/temper-geometry/Cargo.toml`,
`packages/temper-placer/src/temper_placer/router_v6/bottleneck_geometry.py`,
`packages/temper-placer/tests/router_v6/test_bottleneck_geometry_rust_differential.py`
(the oracle arm),
`packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py`
(the fixture), and `benchmarks/perf_ab.py`.

| run | conclusion | branch | commit | verdict |
|---|---|---|---|---|
| `30923554749` | failure | `feat/wave4-phase0-perf-ab-gate` | `5b3d98933` | **ACCEPT** (already committed) — the harness PR; the benchmark it added is the code under measurement, and nothing else in the diff is. |
| `30924144720` | failure | `feat/wave4-phase0-perf-ab-gate` | `548d12936` | **ACCEPT** — same branch, one commit later. `git diff 5b3d98933 548d12936 -- benchmarks/perf_ab.py` is a **docstring-only** change; the benchmark bodies and fixture are byte-identical, and `perf_ab.py` at `548d12936` equals `origin/main`. |
| `30929524197` | failure | `fix/drc-regression-baseline` (#544) | `2787565de` | **ACCEPT** — branch contribution over `main` is one `typing.cast()` in `router_v6/channel_widths.py`. No benchmark-relevant path touched. |
| `30929518954` | success | `p1/drc-ceiling-contract` | `a950a691c` | **ACCEPT** — touches DRC ratchet, ceiling-approval scripts, workflow. No benchmark-relevant path touched. |
| `30930070072` | success | `fix/close-vacuous-gate-violations` | `7a6ec0577` | **ACCEPT** — touches `placer/cp_sat/fixed_copper.py` and its differential test. No benchmark-relevant path touched. |
| `30930971919` | success | `fix/board-defect-corpus-uncovered-classes` | `f7179a469` | **ACCEPT** — touches board-defect corpus scripts, `validation/_drc_api.py`, workflow. No benchmark-relevant path touched. |
| `30930124978` | failure | `exp/barrier-corridor-feasibility` | `6b785eb31` | **REJECT — no rows exist.** |
| `30930324129` | failure | `feat/wave4-phase3-loaders-rust` (#688) | `30ea9f6f6` | **REJECT — no rows exist.** |

Three of the accepted runs concluded `failure`. That does not disqualify them:
each failed **on the perf gate itself**, downstream of the measurement, and the
NDJSON the benchmark printed is a valid reading of unmodified code either way.

### The two rejected runs are a different bug

Neither produced any NDJSON. Both failed at the measurement step with:

```
/__w/temper/temper/.venv/bin/python3: can't open file
'/__w/temper/temper/benchmarks/perf_ab.py': [Errno 2] No such file or directory
##[error]Process completed with exit code 2.
```

Their branches were cut before the harness landed and had not merged `main`
since (`git merge-base --is-ancestor 5b3d98933 30ea9f6f6` → false;
`git cat-file -e 30ea9f6f6:benchmarks/perf_ab.py` → absent).

**This means #688's failure is not a margin false positive.** It never reached
the comparison. Widening the baseline does not fix it, and neither would a wider
margin. The fix for #688 is to merge `main` into the branch so the harness
exists in its checkout. Recorded here because it looks identical to a perf
failure from the outside — same job, same red X, `failure` conclusion — and the
distinction determines which fix applies.

## 5. The capture path

`.github/workflows/pr-perf-check.yml` now also triggers on
`push: branches: [main]` (same paths as the PR trigger) and `workflow_dispatch`.

**Capture on main, gate on PRs.** The comparison step is
`if: github.event_name == 'pull_request'`. On `main` it is skipped, for three
reasons:

1. There is no PR to block, so a failure is pure noise on the trunk-health
   signal — and this repo has no push-side protection, so a red `main` run is
   inherited as a false alarm by every branch cut from it.
2. It would be self-referential. `main`'s rows *are* the baseline; comparing a
   `main` run against them asks a sample whether it matches the median of its
   own population. It can only report runner variance, and it would fail
   precisely when a sample is most valuable — the tail readings are what make
   the median robust.
3. A regression that reaches `main` is a post-merge fact. The gate meant to
   stop it is this same job on the PR; the answer to one that got through is a
   revert, not a second red X.

`Post PR comment` also gains an event guard — `context.issue.number` is
undefined on a push event and the step would hard-error.

**Rows are not auto-committed**, and that is a decision. A bot with write access
to `main` is a separate risk surface with its own review; this repo's one
existing such path (`metrics-record.yml`'s "Auto-tighten timing baselines")
ships default-**off** behind the `FEATURE_AUTO_BASELINE_TIGHTEN` repo variable,
which is the precedent. It is also the wrong default for *this* file
specifically: the baseline is the bar a hard merge gate measures against, every
appended row moves it, and §4 above is a judgement no unattended push can make.
An automated appender that silently ratchets the bar on a bad row is strictly
worse than a stale baseline, because the stale one is visible in the diff.
Instead the job publishes rows twice — inline in `$GITHUB_STEP_SUMMARY`
(copy-paste ready) and as the `perf-ab-baseline-rows-<run>-<attempt>` artifact —
and the append happens in a reviewed PR. If auto-commit is ever wanted, the
right shape is `metrics-reconcile.yml`'s: a separate workflow that globs these
artifacts and opens a PR.

`scripts/check_workflow_pr_triggers.py` passes: the workflow already had a
`pull_request` trigger, so adding `push` needs no `# no-pr-trigger:` opt-out.

## 6. What is pinned in tests

`scripts/tests/test_pr_perf_compare.py`:

- `test_single_row_baseline_reports_a_runtime_no_op_as_a_regression` — the false
  positive, reproduced from the verbatim CI numbers (+26.6%, REGRESSION).
- `test_five_row_baseline_absorbs_the_same_reading` — same reading, same margin,
  full window (+15.7%, OK), and asserts `TIMING_MARGIN == 0.20` so the fix
  cannot be quietly restated as a loosened margin.
- `test_committed_baseline_fills_the_rolling_window` — reads the real committed
  baseline and fails if any `(module, board, stage)` carries fewer than
  `DEFAULT_WINDOW` rows. A new benchmark necessarily lands with one row; this is
  the reminder that the capture path has to fill it in before the key is
  trusted.

## Reproduction

```sh
# harvest rows from a run's logs (gh run view --log is slow; use the API)
gh api "/repos/BennetLeff/temper/actions/runs/<run_id>/logs" > run.zip
unzip -p run.zip "0_PR Performance Comparison.txt" | grep -o '{"schema_version": 2.*'

# per-row validity check
git diff --name-only "$(git merge-base <sha> origin/main)" <sha> -- \
  packages/temper-geometry/src packages/temper-geometry/Cargo.toml \
  packages/temper-placer/src/temper_placer/router_v6/bottleneck_geometry.py \
  packages/temper-placer/tests/router_v6/test_bottleneck_geometry_rust_differential.py \
  packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py \
  benchmarks/perf_ab.py

# the gate's own tests, including the two false-positive pins
python3 -m pytest scripts/tests/test_pr_perf_compare.py -q
```

## Sources

- Margins and noise floor: `docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md`.
- Capture instructions and platform bias: `benchmarks/perf_ab.py` module docstring.
- Runs harvested: `30923554749`, `30924144720`, `30929518954`, `30929524197`,
  `30930070072`, `30930971919` (all `pr-perf-check.yml`, 2026-08-04).
- Runs rejected for having no rows: `30930124978`, `30930324129`.

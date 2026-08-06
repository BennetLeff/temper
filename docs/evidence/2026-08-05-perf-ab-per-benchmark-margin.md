# The performance A/B margin is per benchmark, and five benchmarks cannot be gated at all (2026-08-05)

**Date:** 2026-08-05
**Scope:** `scripts/pr_perf_compare.py`, the Wave 4 performance A/B gate (R1b / R2).
**Supersedes, in part:** [`2026-08-04-perf-ab-harness-noise-floor.md`](./2026-08-04-perf-ab-harness-noise-floor.md)
— its 20% figure stands as the default and the floor; what does not stand is
applying it to every benchmark.
**Measured on:** linux/x86_64, the `ghcr.io/bennetleff/temper-ci` container, via
the workflow's own capture path. Ten runs, two commits, no local measurement.

---

## Summary

The 20% timing margin was derived from **two** benchmarks and then applied to
**seventeen**. For seven of the arms added since, a benchmark's own run-to-run
noise *at a fixed commit* exceeds the margin meant to sit above it. Those arms
have been failing PRs that could not have touched them.

The fix is a per-benchmark margin derived from fixed-commit noise, plus an
explicit finding that **five benchmarks cannot be gated at all today** — their
noise is comparable to the smallest real regression on record, so no band
separates signal from noise. They are measured and reported, never gated, and
named in source with the measurement that excused them.

| | before | after |
|---|---|---|
| False regressions, leave-one-out over 10 CI runs at 2 commits | **2 in 10 folds** | **0 in 10 folds** |
| Benchmarks gated | 17 (nominally) | 12 |
| Benchmarks gated at the 20% default | 17 | 9 |
| Benchmarks gated wider, with measurement | 0 | 3 (22%, 24%, 30%) |
| Benchmarks reported but not gated | 0 | 5 |
| +50.7% regression caught on a gated benchmark | yes | **yes** (asserted per benchmark, every test run) |

---

## The measurement

### Why the committed baseline's spread is not the answer

The obvious move — set each margin to the spread of that benchmark's own
baseline rows — is circular. Baseline rows are captured at different commits, so
their spread mixes measurement noise with real performance change between those
commits. Using it as the margin would absorb genuine regressions into the band
and make the gate weakest exactly where it is already weakest.

What is needed is noise **at a fixed commit**: repeated runs of identical code.

### Group 1 already existed in the repo

It was not obvious, because it is not labelled as such. Commit `2f47e1f8d`
appended 65 rows described as "13 arms x 5 runs" from **five independent CI runs
of one commit**:

> baseline rows for the 11 Wave-4 NO_BASELINE arms from CI runs
> 30970211854, 30970236354, 30970261963, 30970288072, 30970312573
> … measured on main @ `db89355a60076e1e28012d6d22410b862445d3dc`

Five runs, one commit, one container image, no code difference between them. The
spread across those rows is noise by construction. The same holds for
`drc-geometry`, whose rows come from four capture runs of `2b8a3414` (commit
`0718a0943`, PR #757).

The "5 rows per benchmark, captured at different commits" premise does not hold
for this file: 13 of 17 benchmarks have all five rows at `db89355a`, and
`drc-geometry`'s four are at `2b8a3414`. `bottleneck-geometry` additionally
carries six older single-commit rows, but the gate only ever reads the trailing
five — all of which are at `db89355a`.

### Group 2 was captured for this change

Resting on one commit would have been a mistake, and measurably so — see
"What doubling the sample changed" below.

Five fresh CI captures were taken on main tip `516b0e1d` using the on-demand
path that PR #734 made usable in parallel: the push-trigger run **31042192814**
plus four `workflow_dispatch` runs **31044917804**, **31044922828**,
**31044927415**, **31044932232**. All five succeeded and all five ran the
complete 17-arm harness.

`516b0e1d` is a valid capture commit: it touches only
`packages/temper-placer/stubs/temper_design_bundle_python/__init__.pyi` (a type
stub, no runtime effect) and `scripts/check_typecheck_gate.py`. It modifies no
benchmarked module.

**Baseline rows added by this change:** 85 rows (5 runs × 17 arms), appended
verbatim from those runs' `perf-metrics.jsonl` artifacts to
`power_pcb_dataset/metrics/perf_ab_baseline.jsonl`. Append-only — **no existing
row was edited or removed**.

### The statistic

The same one the 2026-08-04 doc reports as "worst rolling delta", computed with
the gate's own arithmetic: **leave-one-out** — score each row against the median
of the other rows in its commit group, and take the worst absolute excursion
over every row of every group. That is what a PR run actually faces: one fresh
sample against a trailing-window median.

Reproduce with:

```sh
python3 scripts/pr_perf_compare.py --derive-margins \
    --baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl
```

### Result

`rust_over_oracle_ratio`, worst fixed-commit leave-one-out excursion over both
groups (n=10, or n=9 for `drc-geometry`):

| benchmark | n | worst excursion | 2× | verdict |
|---|---|---|---|---|
| `physics-emi/predict` | 10 | **42.8%** | 86% | **UNGATEABLE** |
| `parse-engine/parse_kicad_pcb` | 10 | **32.5%** | 66% | **UNGATEABLE** |
| `board-netlist/contracts_construction` | 10 | **30.9%** | 62% | **UNGATEABLE** |
| `drc-geometry/point_rect` | 9 | **26.0%** | 53% | **UNGATEABLE** |
| `physics-heat_removal/build_h_field` | 10 | **24.4%** | 49% | **UNGATEABLE** |
| `physics-safety/filter_delay` | 10 | 14.7% | 30% | margin **30%** |
| `bottleneck-geometry/hard_blocked_batch` | 10 | 11.5% | 24% | margin **24%** |
| `loaders/loaders` | 10 | 10.9% | 22% | margin **22%** |
| `physics-tj_cross_check/device_cross_check` | 10 | 8.4% | 17% | default 20% |
| `drc-geometry/segment_rect` | 9 | 6.7% | 13% | default 20% |
| `physics-parameter_bounds/classify` | 10 | 6.6% | 13% | default 20% |
| `physics-copper_coverage/copper_masks` | 10 | 5.4% | 11% | default 20% |
| `drc-geometry/segment_segment` | 9 | 5.0% | 10% | default 20% |
| `bottleneck-geometry/cell_capacity_batch` | 10 | 3.7% | 7% | default 20% |
| `config-loader/preprocess_config` | 10 | 3.5% | 7% | default 20% |
| `drc-geometry/point_segment` | 9 | 1.8% | 4% | default 20% |
| `footprint-library/from_yaml_string` | 10 | 1.0% | 2% | default 20% |

The 2026-08-04 figure (7.72% worst excursion on `cell_capacity_batch` /
`hard_blocked_batch`, n=20 local) is **confirmed** for `cell_capacity_batch`
(3.7% on CI) and slightly exceeded for `hard_blocked_batch` (11.5%). The doc's
reasoning was right about the benchmarks it had. The harness then grew arms
whose timed region is tens of microseconds, and the figure did not travel with
them.

### What doubling the sample changed — read this before trusting the table

Going from n=5 (one commit) to n=10 (two commits) moved **five** arms across a
threshold:

| benchmark | at n=5 | at n=10 |
|---|---|---|
| `parse-engine/parse_kicad_pcb` | 6.7% → default 20% | **32.5% → UNGATEABLE** |
| `drc-geometry/point_rect` | 3.8% → default 20% | **26.0% → UNGATEABLE** |
| `bottleneck-geometry/hard_blocked_batch` | 9.4% → default 20% | **11.5% → margin 24%** |
| `physics-emi/predict` | 42.8% (oracle arm) | 42.8%, and the second group's excursion hit the **rust** arm |
| `physics-heat_removal/build_h_field` | 24.4% | 24.4% (confirmed, second group 8.3%) |

**These margins are lower bounds on each arm's true noise.** n=10 samples the
tail thinly; expect further captures to widen margins, not narrow them. The
honest reading of this table is not "seven arms are noisy" but "this harness is
noisier than the gate has ever assumed, and we have only just started measuring
it".

### Derivation

```
margin = max(TIMING_MARGIN, ceil_to_1pct(NOISE_HEADROOM × worst_excursion))
ungateable if margin > MAX_GATEABLE_MARGIN
```

- `NOISE_HEADROOM = 2.0` — **the doc's own standard, not a new one**: it set 20%
  against a worst measured excursion of 9.9% (2.02×), and 20% against 7.72%
  (2.59×).
- Floor at `TIMING_MARGIN = 0.20`. No benchmark is gated tighter than 20%,
  because 20% is the only figure validated across the whole harness; tightening
  on this sample would manufacture a new class of false positive.
- `REAL_REGRESSION_FLOOR = 0.507` — the smallest genuine regression in the repo's
  metric history (the regime shift the 2026-08-04 doc measured at +50.7% to
  +72.4%).
- `MIN_SEPARATION = 1.5`, so `MAX_GATEABLE_MARGIN = 33.8%`.

### The two-sided choice — and the measurement that settled it

The gate only fires on an *upward* delta, so one could use the worst **positive**
excursion instead of the worst absolute one, which would have kept
`physics-emi` and `board-netlist` gated at the 20% default.

**The second capture group settles this empirically.** The two arms run back to
back in one process, so a scheduling excursion lands on whichever arm happens to
be running. For `physics-emi/predict`:

| group | excursion hit | `rust_wall_us` | `oracle_wall_us` | ratio moved |
|---|---|---|---|---|
| `db89355a` fold 3 | **oracle** arm | 59.13 (normal) | 247.5 (vs ~140) | **down** −42.8% |
| `516b0e1d` run 31044927415 | **rust** arm | 66.97 (vs ~59) | 146.7 (normal) | **up** +9.6% |

Same benchmark, same container, opposite directions. The excursion is
arm-agnostic, exactly as the single-process design implies. A one-sided band
would have been fitted to which arm happened to get unlucky in the first five
samples.

`parse-engine` shows the same pattern in the second group: run 31042192814 has
`rust_wall_us` 24443 against ~17 000–19 000 in the other four, with
`oracle_wall_us` flat — a one-run excursion on the rust arm, pushing the ratio
**up** 32.5%.

### `MIN_SEPARATION = 1.5` is a judgement, and is named as one

Everything above comes out of measurement. This one number does not.

`physics-heat_removal/build_h_field` derives a 48.7% margin, which is *below* the
50.7% real-regression floor — so a purely mechanical rule would gate it. But
50.7% is a single observed value, and a gate that only fires above ~49% catches
nothing the one historical example did not already contain: it would let a
genuine +45% regression through while looking like a gate. Requiring the margin
to sit at least 1.5× below the real-regression floor excludes it.

At `MIN_SEPARATION = 1.0` it would be admitted at 49% — nominally gated,
practically inert. Naming it as ungateable is the more honest report.

---

## Alternatives considered and rejected

**A distribution-aware comparison (z-score against per-benchmark variance).**
Rejected, though it is the most attractive of the alternatives, for two reasons.

1. *The sample does not support it.* n=10 per benchmark gives an sd with roughly
   24% relative standard error, and the tail is exactly what matters — the
   preceding section shows the tail moving five arms when the sample merely
   doubled. Worse, the sd of `physics-emi` is dominated by a single excursion,
   so a z-threshold would inherit that outlier as an unbounded band and quietly
   produce the same detects-nothing outcome — but without saying so.
2. *It removes the widening from review.* A margin computed at runtime from the
   baseline widens silently whenever a noisy capture is appended. That is the
   "do not widen a margin to make this pass" failure with the diff removed. A
   committed table makes every widening a reviewed line.

The chosen design keeps the distribution-awareness — the numbers *are* derived
from the per-benchmark distribution — and puts the output in source, with
`--derive-margins` to regenerate it and a test that re-derives it from the
committed baseline on every run. A hand-edited margin the measurement does not
support fails `test_committed_margins_match_the_measurement`.

**N consecutive regressing samples before failing.** Rejected as a *gate*
mechanism. A PR gets one run; there is no "consecutive" to count without either
re-running the benchmark k times per job (k× cost on a CI that is capacity-bound
at ~24 concurrent jobs against ~40 requested per push) or deferring the verdict
across pushes, which changes the gate from "blocks this PR" to "blocks
eventually". **But the in-process form of this idea is the right fix for the
five ungateable arms** — see the recommendation below.

**Comparing against the baseline distribution rather than a median ± constant.**
This is what the derivation does, once, offline. Doing it per-run is the z-score
option above.

**Widening the single global constant to cover the worst benchmark.** Rejected
outright: 86% is above the real-regression class, so it would disable the gate
everywhere to accommodate one arm.

---

## The five ungateable benchmarks: recommendation

`physics-emi/predict`, `parse-engine/parse_kicad_pcb`,
`board-netlist/contracts_construction`, `drc-geometry/point_rect`, and
`physics-heat_removal/build_h_field` are **reported as advisory, not gated**, and
appear in the PR comment on every run — passing or failing — with their delta and
the measurement that excused them. An exclusion nobody sees is an exclusion
nobody revisits.

**Advisory, not excluded**, deliberately. Dropping them from the harness would
make the omission invisible; an ADVISORY row keeps the number in front of a
reviewer and keeps the arm's parity assertion running.

**The fix is to reduce their variance, not to widen their margin.** Every one is
dominated by single-shot scheduling excursions, and the pattern is legible: the
noisiest arms are the ones whose timed region is smallest.

| arm | `rust_wall_us` | noise |
|---|---|---|
| `build_h_field` | ≈ 1.6 | 24.4% |
| `predict` | ≈ 59 | 42.8% |
| `contracts_construction` | ≈ 98 | 30.9% |
| `point_rect` | ≈ 51 | 26.0% |
| `cell_capacity_batch` | ≈ 590 | **3.7%** |
| `from_yaml_string` | ≈ 12 600 | **1.0%** |

The concrete change is in `benchmarks/perf_ab.py`: raise `DEFAULT_REPEATS`
(currently 9) for these arms, or increase their inner batch factor — `predict`
and `device_cross_check` already loop 500×, while the 1.6 µs `build_h_field`
does not batch at all. `parse_kicad_pcb` is the exception to the size rule
(≈ 18 ms) and needs its own investigation: its excursion was a single run 35%
slow on the rust arm only.

That is a change to the harness with its own measurement, not to the gate, so it
is deliberately **not** in this PR.

When their variance drops below `MAX_GATEABLE_MARGIN`,
`test_ungateable_set_matches_the_measurement` **fails** and forces them back into
the gated set. The exclusion cannot outlive the condition that justified it.

---

## Demonstrations

### 1. The false positive, reproduced and fixed

Leave-one-out over each group of five CI runs: hold out one run as "the PR", use
the other four as the baseline, for every benchmark at once. **Identical code in
every fold**, so any REGRESSION is a false positive by construction.

```
Leave-one-out over 5 CI runs of main @ db89355a (13 benchmarks x 5 folds):
  origin/main     folds failing gate=1  false regressions=1
    fold 3: physics-heat_removal/synthetic/build_h_field:
            rust_over_oracle_ratio regressed +24.4% (baseline 0.051869 -> PR 0.06451)
  per-benchmark   folds failing gate=0  false regressions=0

Leave-one-out over 5 CI runs of main @ 516b0e1d (17 benchmarks x 5 folds):
  origin/main     folds failing gate=1  false regressions=1
    fold 0: parse-engine/synthetic/parse_kicad_pcb:
            rust_over_oracle_ratio regressed +32.5% (baseline 0.052978 -> PR 0.070209)
  per-benchmark   folds failing gate=0  false regressions=0
```

**A 20% per-run false-failure rate on unmodified code**, reproduced independently
at two commits, on two different benchmarks. This understates the real rate: the
`physics-emi` and `board-netlist` excursions in group 1 happened to be downward,
where the old gate labelled them a spurious 🟢 IMPROVED rather than a red X.

### 2. The gate still bites

A +50.7% regression — the real-regression floor — injected into a real
CI-captured metrics stream (run 31042192814), one benchmark at a time, run
against the real committed baseline with the real script:

```
CONTROL (unperturbed): exit=0  failures=0  advisories=4

bottleneck-geometry/cell_capacity_batch    20% default, 3.7% noise   exit=1  CAUGHT
drc-geometry/point_segment                 20% default, 1.8% noise   exit=1  CAUGHT
physics-copper_coverage/copper_masks       20% default, 5.4% noise   exit=1  CAUGHT
physics-tj_cross_check/device_cross_check  20% default, 8.4% noise   exit=1  CAUGHT
loaders/loaders                            22% WIDENED, 10.9% noise  exit=1  CAUGHT
bottleneck-geometry/hard_blocked_batch     24% WIDENED, 11.5% noise  exit=1  CAUGHT
physics-safety/filter_delay                30% WIDENED, 14.7% noise  exit=1  CAUGHT
physics-heat_removal/build_h_field         UNGATEABLE                exit=0  advisory only
drc-geometry/point_rect                    UNGATEABLE                exit=0  advisory only
board-netlist/contracts_construction       UNGATEABLE                exit=0  advisory only
physics-emi/predict                        UNGATEABLE                exit=0  advisory only
```

All three **widened** benchmarks still catch the real-regression class. That is
the condition on which widening was admissible at all.

This is not a one-off demonstration:
`test_a_real_scale_regression_still_fails_every_gated_benchmark` is parametrised
over **every** gated benchmark and asserts +50.7% fails, on every test run.
`test_the_widened_benchmarks_still_bite_just_above_their_margin` additionally
pins each widened arm just above and just below its new margin.

### 3. Fail-closed behaviour is unchanged

`NEW_BENCHMARK` vs `NO_BASELINE` (PR #696) is untouched — an unbaselined
benchmark that exists on main still fails, a genuinely new one still does not,
and an absent registry still degrades to the strict behaviour. Missing baseline,
empty baseline, empty PR metrics, and a corrupt stream all still exit 1. An
uncharacterised benchmark key gets the **20% default**, not a wide band:
`test_default_margin_still_applies_to_an_uncharacterised_benchmark`.
`--derive-margins` itself fails closed when the baseline carries no fixed-commit
group, rather than printing an empty table someone might paste over a real one.

Suite: **56 tests pass** (was 30).

---

## Named follow-ups (not fixed here)

1. **Reduce the variance of the five ungateable arms** (see the recommendation
   above) so they can be re-gated. `benchmarks/perf_ab.py`, not the gate. This
   is the highest-value follow-up: it is what turns five advisory rows back into
   five gates.
2. **`parse-engine/parse_kicad_pcb` deserves its own look.** It is the one
   ungateable arm whose noise is not explained by a small timed region (≈ 18 ms
   on the rust arm). Its excursion was a single run 35% slow on the rust arm
   with the oracle arm flat.
3. **The baseline has no automatic path to fixed-commit groups.** Every capture
   that fills one was harvested by hand (`2f47e1f8d`, `0718a0943`, and this
   change). The margins derived here are only as fresh as the last such harvest,
   and the preceding section shows how much a single extra group can move them.
4. **The sample is still thin.** n=10 per arm, two commits. Doubling it again is
   cheap (five parallel `workflow_dispatch` runs) and, on this evidence, likely
   to widen further margins.

---

## Reproduction

```sh
# the derivation
python3 scripts/pr_perf_compare.py --derive-margins \
    --baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl

# the gate's own tests, including the bite proof
python3 -m pytest scripts/tests/test_pr_perf_compare.py -q

# capture more fixed-commit samples (do NOT capture locally: darwin measures
# ~-11% against the Linux CI container on identical code)
gh workflow run pr-perf-check.yml --ref main   # repeat; #734 made these parallel
gh run download <run-id> -R BennetLeff/temper  # perf-metrics.jsonl artifact
```

## Sources

- Prior noise floor and the 20% derivation: `docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md`.
- Baseline widening and the n=1 defect: `docs/evidence/2026-08-04-perf-ab-baseline-widening.md`.
- Fixed-commit CI captures, group 1: commit `2f47e1f8d` (runs 30970211854, 30970236354, 30970261963, 30970288072, 30970312573 @ `db89355a`); `drc-geometry` from commit `0718a0943` (@ `2b8a3414`, PR #757).
- Fixed-commit CI captures, group 2 (added by this change): runs 31042192814, 31044917804, 31044922828, 31044927415, 31044932232 (@ `516b0e1d`).
- Observed false positives: PR #722, PR #760, and the PR #778 triage bucket (#721, #731, #737, #755).
- `NEW_BENCHMARK` / `NO_BASELINE` distinction: PR #696.
- Parallel dispatch capture: PR #734.

# Wave 4 Phase 0: the performance A/B as a real hard gate — CI noise floor, gate-bite demonstrations, and the required-context decision (2026-08-04)

<!-- provenance: commit=c60825861f337fa7d7c6d0ec8e9240c5aa97c74a dirty=true (base=origin/main c60825861f337fa7d7c6d0ec8e9240c5aa97c74a; worktree .claude/worktrees/agent-a724926621caba9a6, branch feat/wave4-phase0-perf-ab-gate; dirty=true because the measurements below were taken from the working tree that this commit introduces) -->

**Date:** 2026-08-04
**Scope:** Wave 4 Phase 0 (`docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`, R2 and the Phase 0 row of the Phased Migration Path).
**Measured on:** darwin/arm64, Python 3.12, quiescent machine. CI-side figures are read from the repo's own committed metric history.

---

## Summary

The performance A/B was not a weak gate. **It was not a gate at all**, and had
not been one for at least 35 days.

`.github/workflows/pr-perf-check.yml` carried `continue-on-error: true` citing
`temper-N6-U8` — a placeholder ticket id shared across 27 masks and documented
as a stub in `docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md:37`.
The mask's stated reason was "JSON parse race in PR comments". That is not what
it was hiding. It was hiding a **traceback on every single run**.

Four independent defects, all confirmed against production CI run
[30885725905](https://github.com/BennetLeff/temper/actions/runs/30885725905)
(2026-08-04T07:15Z, job 91916381279), which reported **success**:

| # | Defect | Effect |
|---|---|---|
| D1 | `profile_router_benchmark` printed progress to **stdout**, the same stream `--json` writes NDJSON to | Corrupted the metrics file |
| D2 | `load_pr_metrics` used `json.load` (a JSON *array*) against an **NDJSON** stream | `JSONDecodeError: Expecting value: line 2 column 1` — every run |
| D3 | `main()` returned `0` unconditionally | A regression could never fail the job |
| D4 | `continue-on-error: true` | The traceback was swallowed; the job went green |

Two further defects make the *data* vacuous even when parsing succeeds:

| # | Defect | Effect |
|---|---|---|
| D5 | `profile_pipeline` times the construction of a `ClosureResult` **dataclass**, not the pipeline | Emits `wall_time_ms: 0` on every run |
| D6 | `profile_loss_functions` emits an all-zero record from its `except` branch | Fabricated data indistinguishable from a measurement |

Verbatim from the run log, both records at the moment the job reported success:

```
{"schema_version": 2, ..., "stage": "closure",  "module": "pipeline", "metrics": {"wall_time_ms": 0, "completion_pct": 0.0, ...}}
{"schema_version": 2, ..., "stage": "loss-fn",  "module": "loss-fn",  "metrics": {"overlap_ms": 0, "spread_ms": 0, "wirelength_ms": 0, "boundary_ms": 0, "total_step_ms": 0}}
...
json.decoder.JSONDecodeError: Expecting value: line 2 column 1 (char 1)
##[error]Process completed with exit code 1.
```

D1–D4 are fixed by this change. D5 and D6 are **not** fixed here; instead the
gated path no longer consumes them (see "What the gate now measures"), and they
are recorded below as named follow-ups. A gate that reports a fabricated zero as
a 100% improvement is worse than no gate.

---

## The CI noise floor, measured

R2 requires a "no regression beyond noise" comparison and says the noise floor
must be quantified in Phase 0. Two independent measurements.

### 1. CI wall-clock series (the repo's own history)

`power_pcb_dataset/metrics/pipeline_metrics.jsonl` holds 135 main-branch
records; 27 carry a non-degenerate `wall_time_ms`. Each was produced by a
distinct commit on CI, so successive values are the CI's own repeated
measurements. Applying **the gate's exact arithmetic** — each sample against the
median of the prior 5, which is what `load_main_baselines` computes:

| Regime | n | range (ms) | mean | sd | cv |
|---|---|---|---|---|---|
| 0 | 18 | 27261–31030 | 28541 | 1056 | **3.70%** |
| 1 | 9 | 42296–48803 | 44382 | 2285 | **5.15%** |

Rolling-window deltas, n = 22:

- median \|delta\| = **3.1%**
- excluding the genuine regime shift: n = 19, sd = **4.6%**, worst excursion = **9.9%**
- the genuine regression between the regimes measured **+50.7% to +72.4%**

**This is the key separation.** A 20% margin sits cleanly between the worst
noise excursion (9.9%) and the smallest real regression the series contains
(50.7%). It is not a guess.

### 2. The gated ratio metric (`rust_over_oracle_ratio`)

20 fresh processes of `benchmarks/perf_ab.py`:

| Benchmark | metric | n | median | sd | cv | worst rolling delta |
|---|---|---|---|---|---|---|
| `cell_capacity_batch` | `rust_over_oracle_ratio` | 20 | 0.17629 | 0.00512 | **2.92%** | **7.72%** |
| `cell_capacity_batch` | `rust_wall_us` (raw) | 20 | 357.2 | 9.42 | 2.64% | — |
| `hard_blocked_batch` | `rust_over_oracle_ratio` | 20 | 0.37018 | 0.00508 | **1.37%** | **3.28%** |
| `hard_blocked_batch` | `rust_wall_us` (raw) | 20 | 123.4 | 3.29 | 2.68% | — |

The ratio is tighter than either raw arm, which is the point of measuring it:
running both arms in one process cancels machine speed and container
contention, leaving only scheduling jitter.

### Verdict on the existing margins

| Constant | Value | Verdict |
|---|---|---|
| `TIMING_MARGIN` | 0.20 | **Justified.** ~2.0x headroom over the worst CI excursion (9.9%) and ~2.6x over the worst ratio excursion (7.72%); separated from the smallest observed real regression (50.7%) by a factor of 2.5. Keep. |
| `COMPLETION_MARGIN` | 0.10 | **Justified, by a different argument.** `completion_pct` in the history takes only the discrete values {0.0, 0.9} — within a regime its noise floor is exactly 0%. Any movement is real. Keep. |
| `IMPROVEMENT_THRESHOLD` | 0.10 | **Marginal, but harmless today.** The worst measured noise excursion is 7.72%, so a 10% threshold will occasionally label noise as "IMPROVED" (1.3x headroom). It only *labels* — it never fails a gate — so this is cosmetic. If it is ever used as a ratchet input, raise it to 0.15 first. |

No margin was loosened. All three are unchanged.

---

## What the gate now measures

`temper profile run --module all` is no longer on the gated path: given D5 and
D6 it produced no honest numbers. In its place, `benchmarks/perf_ab.py` runs the
**dual-arm A/B the discipline contract actually asks for** (R1b) — the verbatim
pre-migration Python oracle and the Rust kernel that replaced it, back to back
in one process — and gates their **ratio**.

Three properties this buys:

1. **Machine-independent.** A ratio measured in one process survives a
   baseline captured on one machine and compared on another.
2. **One oracle, both gates.** The harness imports the oracle *from the
   differential test that pins it* rather than copying it. The behavioral and
   performance A/Bs cannot drift apart: edit or delete the oracle and both
   gates change together.
3. **Parity is asserted inside the perf harness.** A performance number for an
   implementation that no longer agrees with its oracle is meaningless, so the
   benchmark refuses to report one.

Only `rust_over_oracle_ratio` is gated. `rust_wall_us` / `oracle_wall_us` are
emitted for diagnosis under names that carry no gated suffix, precisely because
absolute times are not comparable across runners.

### Fail-closed paths

Every path where the comparison cannot be *made* now exits non-zero, because a
comparison that degrades to "no news" is indistinguishable from a passing one:

- no PR records at all
- baseline file missing or empty
- a PR record with no baseline row (`NO_BASELINE`) — an unbaselined module is
  not covered by the A/B, so adding one without a baseline fails the gate
- a corrupt metrics stream (the D1/D2 failure mode) — named, not skipped
- any metric beyond its margin

Covered by 24 tests in `scripts/tests/test_pr_perf_compare.py`.

---

## The Phase 0 gate: both gates demonstrated to bite

Retrofit target: **`router_v6/bottleneck_geometry.py`** (Wave 3 #2 — the
bottleneck geometry migration from `6ccb581ca`). It already carried the
behavioral A/B (`test_bottleneck_geometry_rust_differential.py`, 17 tests); this
change adds the performance A/B over the same kernels and the same oracle.

Baseline, all 17 behavioral tests green and the perf gate green:

```
$ pytest .../test_bottleneck_geometry_rust_differential.py -q
17 passed in 0.05s

$ python scripts/pr_perf_compare.py --pr-metrics pr.jsonl \
      --baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl
✅ Performance A/B gate passed — no regression beyond noise.
EXIT=0
```

### Demonstration 1 — the behavioral A/B bites

Perturbation (one character), in `_resolve_current_category` — a plausible
None-handling bug in a migration, changing the R4 "category-HIGH on
category-LOW" discount sentinel:

```diff
-    return -1 if current_category is None else current_category
+    return 0 if current_category is None else current_category
```

Result — **2 of 17 tests fail**:

```
E   AssertionError: mismatch on grid 5x4x2 cells=[(0, 4, 1), (0, 1, 2), ...]
E   assert [1, 0, 0, 0, 0, 2, ...] == [0, 0, 0, 0, 0, 2, ...]
E     At index 0 diff: 1 != 0

E   AssertionError: node insertion order differs

FAILED test_capacity_batch_matches_reference_on_randomized_inputs
FAILED test_graph_kernel_matches_reference_on_randomized_inputs
2 failed, 15 passed
```

Reverted; 17 passed.

### Demonstration 2 — the performance A/B bites

Perturbation, in `_compute_cell_capacity_batch` — a plausible "forgot the
vectorised conversion" regression that leaves behaviour identical:

```diff
-        trace.tolist(),
-        pad.tolist(),
-        ranks.ravel().tolist(),
+        [int(v) for v in trace],
+        [int(v) for v in pad],
+        [int(v) for v in ranks.ravel()],
```

Result — **gate fails, exit 1**:

```
| bottleneck-geometry | synthetic | cell_capacity_batch | rust_over_oracle_ratio | 0.176739 | 0.256873 | +45.3% 🔴 | REGRESSION |
| bottleneck-geometry | synthetic | cell_capacity_batch | rust_wall_us          | 361.292  | 523.667  | +44.9%    | OK |
| bottleneck-geometry | synthetic | hard_blocked_batch  | rust_over_oracle_ratio | 0.368986 | 0.361063 | -2.1%     | OK |

### 🔴 Performance A/B gate FAILED
- bottleneck-geometry/synthetic/cell_capacity_batch: rust_over_oracle_ratio regressed +45.3% (baseline 0.176739 -> PR 0.256873)
EXIT=1
```

**+45.3% against a 20% margin and a 7.72% measured noise floor** — an
unambiguous trip, and the untouched benchmark stayed at −2.1%, so the gate
localises the regression rather than smearing it.

Under this same perturbation the behavioral A/B stayed **17 passed**, which is
the cross-check that matters: the two gates are independent, and the
performance gate catches exactly what the behavioral gate cannot see.

Reverted; gate green, exit 0.

### Demonstration 3 — fail-closed on a missing baseline

`test_main_fails_closed_on_absent_baseline`,
`test_main_fails_closed_on_empty_baseline`,
`test_main_fails_closed_on_unbaselined_module`,
`test_main_fails_closed_on_empty_pr_metrics`, and
`test_main_fails_closed_on_corrupt_pr_stream` all assert `main(...) == 1`. Each
of these was a silent pass before this change.

---

## Decision: the required status check is NOT registered

R2 asks for a required status check. **This change deliberately does not
register one**, and wires everything else. Three independent reasons; the first
alone is decisive.

### 1. Structural — registering it today would fail *every* PR

`scripts/check_required_checks.py::required_contexts_for_files` returns **all**
of `manifest.required_contexts` whenever **any** of the manifest's ~90
`trigger_paths` match. Every context in that list today comes from
`python-tests.yml`, whose trigger paths the manifest is drift-checked against by
`validate_trigger_manifest`.

`pr-perf-check.yml` is a **different workflow with a narrower path set**. A PR
touching only `docs/plans/**` or `pcb/*.kicad_pro` matches the manifest, so the
aggregator would require `PR Performance Comparison` — but the perf workflow
never fires, so **no check run is created at all**. That is `missing`, not
`skipped`: `verify_skips` can only rescue a context that actually reported a
`skipped` conclusion. The aggregator would poll for `timeout_seconds` (2700) +
`backlog_grace_seconds` (7200) — **2h45m** — and then return 1.

Result: a guaranteed red required check on every docs-only PR, blocking every
open PR at once. This is the failure mode that has broken `main` before.

**Prerequisite for registration:** `check_required_checks.py` needs a
per-context workflow-trigger gate (e.g. a `context_triggers` manifest section
mapping a context to its own workflow's `paths:` list, drift-checked the same
way `validate_trigger_manifest` checks the python-tests list) so a context can
be dropped from the required set when its own workflow legitimately does not
fire. That is a change to the single most `main`-breaking file in the repo and
belongs in its own PR with its own tests.

### 2. The committed baseline is not yet CI-measured

`power_pcb_dataset/metrics/perf_ab_baseline.jsonl` was captured on
darwin/arm64. The ratio cancels machine *speed*, but not the relative scaling of
CPython versus Rust across architectures, and CI is linux/x86_64 in a container.
Until a CI-side baseline exists on `main`, the cross-platform offset is
unmeasured and could exceed 20% in either direction. The first PR runs of this
workflow will measure it; the baseline should then be re-captured from a CI run
before the context is ever required.

### 3. Headroom is adequate to report on, thin to wedge every PR on

2.0–2.6x headroom, from n = 19 (CI) + n = 20 (local) samples. That is enough to
block one PR whose author can re-run, and enough to make the comparison
believable. It is not enough confidence to make **every open PR unmergeable** on
a single flake, against a ~24-job concurrency ceiling with ~40 jobs requested
per push.

### What "registered" would look like

Once (1) is built and (2) is re-measured, registration is: add
`"PR Performance Comparison"` to `required_contexts` **and** a `context_triggers`
entry naming `.github/workflows/pr-perf-check.yml` and its `paths:` list. A note
recording this is in `.github/required-checks.json` under
`_perf_ab_context_note`.

A well-evidenced "not yet" is the honest outcome here. The gate is real — it
fails the job, it fails closed, and both halves have been shown to bite. It is
simply not yet wired to branch protection.

---

## Named follow-ups (not fixed here)

1. **D5 — `profile_pipeline` measures nothing.** It times the construction of a
   `ClosureResult` dataclass. Either make it invoke `ClosureTest.run()` (~42s
   per run × 4 = ~3 min added to CI, duplicating what `ci_closure_test.py`
   already measures) or delete it. It must not keep emitting `wall_time_ms: 0`.
2. **D6 — `profile_loss_functions` fabricates all-zero records** from its
   `except` branch. Returning `[]` is honest; a zero is not.
3. **`pipeline_metrics.jsonl` is a dead series.** Last entry
   `2026-06-30T00:22:35Z` — 35 days stale at the time of writing. Nothing on
   `main` appends to it. Any gate reading it is comparing against a
   five-week-old world. This is the exact staleness mode the new baseline must
   avoid; re-capture instructions are in `benchmarks/perf_ab.py`.
4. **`context_triggers` in `check_required_checks.py`** — the prerequisite for
   registering any context from a second workflow (see Decision, reason 1).
5. **Pre-existing, unrelated, observed while verifying:**
   `scripts/tests/test_classify_changed_paths.py` has 5 failures on
   `origin/main` (`c60825861`) — its synthetic manifest omits
   `backlog_grace_seconds`, and `_positive_int` rejects the default `0`.

---

## Reproduction

```sh
# The A/B harness
python3 benchmarks/perf_ab.py --list
python3 benchmarks/perf_ab.py --json

# The gate
python3 benchmarks/perf_ab.py --json > pr.jsonl
python3 scripts/pr_perf_compare.py \
    --pr-metrics pr.jsonl \
    --baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl
echo "exit=$?"

# The gate's own tests
python3 -m pytest scripts/tests/test_pr_perf_compare.py -q

# The behavioral A/B
python3 -m pytest \
    packages/temper-placer/tests/router_v6/test_bottleneck_geometry_rust_differential.py -q
```

## Sources

- Program plan: `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` (R1a–R1h, R2, Phase 0).
- Stub-ticket requirement: `docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md:37`.
- Production evidence: GitHub Actions run 30885725905, job 91916381279 (2026-08-04T07:15Z).
- Historical metric series: `power_pcb_dataset/metrics/pipeline_metrics.jsonl` (135 records, 2026-06-23 → 2026-06-30).
- Retrofit target: `6ccb581ca` (Wave 3 migrations), `router_v6/bottleneck_geometry.py`.

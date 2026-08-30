---
title: DSN exporter oracle regime drift invalidates ratio baselines
date: 2026-08-29
category: performance-issues
module: PR performance comparison
problem_type: performance_issue
component: tooling
symptoms:
  - An unrelated PR fails dsn-exporter/export_pcb on rust_over_oracle_ratio while both timed arms are faster
  - Repeated PR runs exceed the ratio threshold even though no changed file reaches the exporter
root_cause: config_error
resolution_type: workflow_improvement
severity: medium
tags: [performance-gate, fixed-commit, dsn-exporter, oracle-drift, baseline]
---

# DSN exporter oracle regime drift invalidates ratio baselines

## Problem

PR #1535 failed the `dsn-exporter/export_pcb` ratio gate by 23.0–23.9% against a committed median of 0.519916. The Rust arm was about 7–8% faster than the old baseline, but the comparison arm was about 25% faster, so the ratio increased despite no exporter regression.

## Symptoms

- The PR does not change the DSN exporter, its performance harness, or its baseline.
- Rust wall time improves while `rust_over_oracle_ratio` is reported as a regression.
- Recent `main` captures occupy a different ratio regime: 0.598184–0.617822, with median 0.612681. The PR's 0.644020 result is about 5.1% above that comparable median.

## What Didn't Work

- Rerunning the PR job reproduced the failure. This was useful evidence that the result was not a one-off scheduling excursion, but it could not repair a stale baseline regime.
- Widening the 20% margin would make this instance pass without measuring fixed-commit noise. The gate explicitly forbids that: margins must be derived from groups of at least three rows sharing one commit, using leave-one-out excursions (`scripts/pr_perf_compare.py:107-132`).
- Treating the frozen exporter file as a fully independent Python timing oracle is no longer valid. Its header documents that DSN primitive imports now resolve through the Rust-backed delegation shim (`packages/temper-placer/tests/io/_dsn_exporter_py_oracle.py`, lines 10–19 and 35–42).

## Solution

Treat a performance oracle implementation change as a measurement-regime change:

1. Select one post-migration `main` commit.
2. Capture at least 3, preferably 5 or more, independent CI rows for that exact commit.
3. Append the reviewed rows to `power_pcb_dataset/metrics/perf_ab_baseline.jsonl` with their real commit identity and provenance.
4. Run the repository's prescribed derivation:

   ```bash
   python3 scripts/pr_perf_compare.py \
     --derive-margins \
     --baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl
   ```

5. Update a per-benchmark margin only if the fixed-commit derivation requires it. Do not hand-edit a threshold to clear a PR.
6. Rerun the PR comparison against the reviewed post-migration baseline.

The migration that created the new regime is documented in the current oracle header: after the pure-Python DSN primitive oracle was retired, imports were redirected to `temper_placer.io.dsn`, whose primitives are Rust-backed (`packages/temper-placer/tests/io/_dsn_exporter_py_oracle.py`, lines 10–19).

## Why This Works

`rust_over_oracle_ratio` measures two implementations, so changing either implementation changes the metric's meaning. Old rows compare Rust against the pre-retirement Python primitive path; new rows compare the exporter against an oracle that delegates its primitives to Rust. Mixing those regimes makes a speedup in the denominator look like a regression in the numerator.

The gate's fixed-commit construction separates noise from code changes by design: variation within one commit is noise, while variation across commits may be a real performance shift (`scripts/pr_perf_compare.py:110-124`). Recapturing a same-commit group after the oracle migration restores a comparable baseline without weakening the gate.

## Prevention

- Any benchmark-oracle migration must either preserve timing independence or deliberately invalidate and recapture affected ratio baselines.
- Baseline records should carry a measurement-regime identifier derived from both timed implementations, so incompatible rows cannot silently share a rolling median.
- Add a gate that rejects a baseline window spanning an oracle implementation fingerprint change.
- Keep margin changes mechanically tied to `--derive-margins`; the existing tests already reject unsupported hand edits (`scripts/pr_perf_compare.py:128-132`).

## Related Issues

- PR #1535 exposed the stale DSN ratio regime while changing unrelated PCB placement and CI workflow code.
- `docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md`
- `docs/evidence/2026-08-05-perf-ab-per-benchmark-margin.md`

---
title: "Fixed-commit performance capture bootstrap"
date: 2026-08-29
status: reviewed-bootstrap
---

<!-- provenance: commit=049f5ea2daa437114940d0a0420a768c6f5faa25 dirty=false -->

# Fixed-commit performance capture bootstrap

Five independent \`PR Performance Check\` \`workflow_dispatch\` runs captured
the exact PR head
\`049f5ea2daa437114940d0a0420a768c6f5faa25\`:

- [33281175832](https://github.com/BennetLeff/temper/actions/runs/33281175832)
- [33281177002](https://github.com/BennetLeff/temper/actions/runs/33281177002)
- [33281178023](https://github.com/BennetLeff/temper/actions/runs/33281178023)
- [33281178967](https://github.com/BennetLeff/temper/actions/runs/33281178967)
- [33281180153](https://github.com/BennetLeff/temper/actions/runs/33281180153)

Each run succeeded and produced 21 rows. The five artifacts have identical
benchmark key sets and all 105 rows carry the requested immutable commit SHA.
The rows' measurement-regime source digests validate against the capture
commit, and the baseline update is append-only: the file grows from 434 to
539 rows. The exact 105-row candidate append has SHA-256
\`3a20aa58167b4978fa0d34b7cdcffb43e18f5c5510a4d1f2c37cdc7cb3c13cf4\`.

The rows were appended to
\`power_pcb_dataset/metrics/perf_ab_baseline.jsonl\` without editing or
reordering existing history.

## Margin derivation

\`python3 scripts/pr_perf_compare.py --derive-margins --baseline-jsonl
power_pcb_dataset/metrics/perf_ab_baseline.jsonl\` completes and derives the
fixed-commit observations. The frozen margin tables in
\`scripts/pr_perf_compare.py\` now match the derivation exactly. The five-row
bootstrap adds gateable entries for \`dsn-exporter/export_pcb\` (23%),
\`topological/constraint_propagation\` (31%), and
\`topological/force_refinement\` (22%), and an ungateable entry for
\`config-loader/preprocess_config\` (126%). The focused comparator and capture
validator suites pass (96 tests). No margin was widened silently: every
non-default value is the documented \`ceil(2 x worst fixed-commit excursion)\`
result, and the 126% config-loader result is reported as advisory because it
exceeds the 33.8% maximum gateable margin.

## Bootstrap evidence contract

The captures used the old default-branch \`pr-perf-check.yml\` workflow. Each
run publishes one \`perf-metrics.jsonl\` artifact and no metadata sidecar, so
the refresh manifest records the five real run/artifact pairs directly. The
committed evidence files under
\`power_pcb_dataset/metrics/perf_ab_baseline_refresh/\` are the exact extracted
artifact bytes; the manifest records their SHA-256 digests. The PR workflow
queries GitHub for every run and artifact, checks completion, success, exact
capture SHA, ownership, expiry, and downloaded-byte equality before invoking
the reviewed validator.

An independent different-SHA capture is intentionally not required for this
bootstrap. The validator rejects any change between the capture SHA and the
candidate HEAD under \`benchmarks/\`, \`packages/\`, or the harness dependency
manifests/configuration. This is the conservative source-identity proof that
makes the five fixed-commit rows sufficient; future captures may use the newer
sidecar-producing workflow when a second-SHA comparison is useful.

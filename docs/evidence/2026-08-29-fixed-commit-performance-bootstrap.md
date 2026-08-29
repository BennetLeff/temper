---
title: "Fixed-commit performance capture bootstrap"
date: 2026-08-29
status: reviewed-bootstrap
---

<!-- provenance: commit=65f14a652afc2110a6ad74b194e23ddb9c51f397 dirty=false -->

# Fixed-commit performance capture bootstrap

Five independent \`PR Performance Check\` \`workflow_dispatch\` runs captured
the exact PR head
\`e1747634f615bf8c1b203032dec42d1961ab32dd\`:

- [33270300259](https://github.com/BennetLeff/temper/actions/runs/33270300259)
- [33270301615](https://github.com/BennetLeff/temper/actions/runs/33270301615)
- [33270302948](https://github.com/BennetLeff/temper/actions/runs/33270302948)
- [33270304247](https://github.com/BennetLeff/temper/actions/runs/33270304247)
- [33270305655](https://github.com/BennetLeff/temper/actions/runs/33270305655)

Each run succeeded and produced 21 rows. The five artifacts have identical
benchmark key sets and all 105 rows carry the requested immutable commit SHA.
The rows' measurement-regime source digests validate against the capture
commit, and the baseline update is append-only: the file grows from 434 to
539 rows. The exact 105-row candidate append has SHA-256
\`53dc83dd557d14e4b3df4fbcbbb87d5f3b4f1f956110a99f38881fec79c389ff\`.

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

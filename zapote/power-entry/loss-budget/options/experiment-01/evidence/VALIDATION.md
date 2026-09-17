# Experiment 01 verification

Coordinator checkout: `codex/buck-harness-experiment-plan`, based on
`225dfaca03e0d069d938269a4cf1cf8a1da03086`. The experiment was built and run from
the integrated working tree. Content hashes in `provenance.json` identify those
inputs; the base commit alone does not identify the new implementation.

## Authoritative run

Commands ran from the repository root, with
`CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target`:

```sh
cargo build --manifest-path zapote/Cargo.toml --release --offline --locked \
  -p zapote-harness --bin zapote-pfc-mosfet-experiment
/private/tmp/zapote-rtd-target/release/zapote-pfc-mosfet-experiment \
  zapote/power-entry/shunt-repair/candidate/source-manifest.json
```

Stdout is `report.json`; stderr is `run.stderr`; `run.exit-code` contains **2**.
This is the expected overall INDETERMINATE status. Numerical checks pass,
physical applicability and qualification remain INDETERMINATE. All 4,374 cases
contain the exact simulation inputs and separate event/RMS current values.
The coordinator report is byte-identical to the independently executed worker
report. This demonstrates reproducibility, not physical correctness.

The standalone Rust audit was compiled with `rustc --edition=2021 -O` and fed
`audit-input.tsv`, transported from the JSON exactly as documented in the parent
README. `audit-result.json` records all 4,374 cases and maximum relative error
1.0340641280770064e-11 (tolerance 1e-7). The independent continuous-phase integral
is compared with the production phase quadrature; the audit imports no
production moment or switching functions.

## Tests and review

The following release/offline/locked library test filters passed:

| Package / filter | Passed | Log |
| --- | ---: | --- |
| zapote-harness / pfc_mosfet_experiment | 4 | experiment-tests.log |
| zapote-harness / model_assurance | 8 | assurance-tests.log |
| zapote-harness / pfc_loss_budget | 8 | loss-budget-tests.log |
| zapote-erc / pfc_switching | 8 | switching-tests.log |
| Standalone independent audit (`rustc --test`) | 2 | audit-tests.log |

Mutations cover changed source identity, non-PDF bytes even with a matching
claimed digest, changed PDF bytes, missing/duplicate/off-grid scenarios,
non-finite partial total, changed configured Qgd, and altered independent-audit
results. Grid validation recomputes actual values and source/configuration/term
relationships rather than trusting retained `finite` or accounting flags.

Luna implemented the module in an isolated sparse worktree. A separate Luna
review returned no concrete blockers (`luna-review.md`). Root checked the exact
datasheet inputs, reviewed and integrated the implementation, and independently
audited every output. The review pins the pre-rustfmt worker module; integration
only formatted that code and inserted its registration. Canonical source hashes
are retained separately in `provenance.json`.

Package-scoped clippy passed with warnings denied:

```sh
cargo clippy --manifest-path zapote/Cargo.toml --release --offline --locked \
  -p zapote-harness --lib --bin zapote-pfc-mosfet-experiment --no-deps -- -D warnings
```

The first clippy invocation included dependencies and failed on existing
zapote-erc/zapote-drc warnings. Both logs are retained; no dependency edits or
lint suppression were introduced. Repository regeneration, regeneration check
and import-boundary results are retained in their named logs.

## Limits

This run adds a diagnostic comparison CLI, not a new board-acceptance adapter.
No authored/native/manufacturing inputs or production loss-model logic changed.
No fresh KiCad, seven-unit common runner, Gmsh/Elmer or hardware qualification
result is claimed for this experiment. Prior board receipts remain historical.
The prior common runner's physical-applicability and qualification gates remain
required; these diagnostic numerical passes cannot waive them.

The standalone audit verifies mathematical implementation under the stated
waveform assumptions. It cannot certify the applicability of typical datasheet
charge points, driver behavior, temperature transfer, commutation or cooling.

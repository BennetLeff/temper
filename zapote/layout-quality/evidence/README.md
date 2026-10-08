# Validation record — 2026-10-02

Base: `f11ca939f73e869e6745d33badcf6cc1acc818b2`,
`origin/codex/power-stage-120v-build`. Implementation and test content identities
are in `source-sha256.txt`. Runtime: rustc 1.92.0, arm64 macOS 26.6.2;
proptest 1.11.0. Work performed by Codex/GPT-6, locally, without external review
or telemetry. PCB geometry and source schematics were unchanged.
Text logs have only trailing whitespace and extra final blank lines normalized.

## Tests

`PROPTEST_CASES=2048 cargo test --manifest-path zapote/Cargo.toml --workspace
--all-targets --locked --offline`: **374 passed, zero failed**. Full output:
`workspace-tests.txt`.

After adding the asymmetric 3D exhaustive-pair property, the five layout-quality
integration suites were rerun with the same 2,048-case setting: **46 passed**.
Together with the four CLI tests in the workspace run, there are **50 new tests**,
including **15 properties / 30,720 generated cases** in the final focused run.
`focused-tests.txt` records the final tests. This count is software coverage;
it does not validate external field/thermal models or board qualification.

## Performance

`cargo bench --manifest-path zapote/Cargo.toml -p zapote-drc --bench layout_quality
--locked --offline`; full output in `release-benchmark.txt`.

| Workload, including validation and allocated object reports | Mean per iteration |
|---|---:|
| 64-node chain factorization; 100 iterations | 59.5 µs |
| Reused 64-node factor, solve; 10,000 iterations | 12.3 µs |
| 1,000 aggressor + 1,000 victim sparse patches; 1,000 output pairs | 602.8 µs |
| 1,000 sparse assembly envelopes; 999 output pairs | 208.5 µs |

These are single-run wall-clock microbenchmarks, not latency guarantees. Dense
overlap remains quadratic. Removing eager formatting on successful validation
reduced the same copper workload from 634.2 to 59.5 µs for preparation and
45.9 to 12.3 µs for solving; these runs were not an isolated statistical study.

## Lint and repository gates

- New Rust files pass `rustfmt --edition 2021 --check`.
- DRC package and CLI/test Clippy pass with `-D warnings`, allowing only existing
  lint categories in unchanged code: `iter_overeager_cloned`,
  `items_after_test_module`; harness dependencies additionally need
  `needless_borrow` and `manual_range_contains`. No lint suppressions were added
  to source. Commands and output are documented in the review receipt/logs.
- Strict workspace Clippy and workspace formatting are **not clean** on the
  base: `strict-workspace-clippy.txt` and `workspace-format-baseline.txt` retain
  the unchanged-file diagnostics.
- `make regen` and `make regen-check` pass and create no tracked changes.
- The legacy Python import-boundary gate is **unavailable**, not passed:
  `lint-imports` is absent from this isolated environment. Its failed invocation
  is retained in `import-gate-unavailable.txt`. No Python/import changes exist.

Scoped lint invocations:

```sh
cargo clippy --manifest-path zapote/Cargo.toml -p zapote-drc \
  --all-targets --all-features --locked --offline -- -D warnings \
  -A clippy::iter_overeager_cloned -A clippy::items_after_test_module
cargo clippy --manifest-path zapote/Cargo.toml -p zapote-harness \
  --bin zapote-layout-quality --test layout_quality_cli --locked --offline -- \
  -D warnings -A clippy::iter_overeager_cloned -A clippy::items_after_test_module \
  -A clippy::needless_borrow -A clippy::manual_range_contains
```

## Native example

The actual CLI command in the parent README emitted
`native17-unit-slew-report.json`, exit **2**, because eight requested families
are absent. It verifies the saved native-17 board hash and evaluates the
documented gate-coupling sensitivity as **6.8372 V induced EMF**, unscored.
This is not a measured slew, a VGS waveform, or a board acceptance result.

The input-byte hash is in the report. Preparing complete source-derived inputs
for all families remains native-adapter/model integration work; that software
coverage gap is separate from physical qualification.

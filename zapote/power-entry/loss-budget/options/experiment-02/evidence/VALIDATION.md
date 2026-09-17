# Experiment 02 verification

Run on 2026-09-17 from `codex/buck-harness-experiment-plan`, based on
`c27abe974`. Content hashes identify the tested dirty sources; the base commit
alone does not. Requested implementation/review model: `gpt-5.6-luna`.
No provider-level model receipt is available.

## Numerical and compatibility evidence

`report.json` contains 2,916 candidate cases plus two direct-drive controls.
Generation exits **2**: numerical checks PASS, physical applicability,
interface realization and qualification INDETERMINATE. This is a diagnostic
comparison CLI, not a new board-acceptance adapter. The common runner retains
its mandatory applicability and qualification checks.

The independent standalone Rust audit imports no production model functions.
It analytically integrates current moments and calculates asymmetric triangular
switching energies. Its maximum relative discrepancy is below 1.035e-11 over
all cases (tolerance 1e-7). It verifies the stated mathematics, not semiconductor
model applicability. See `audit-result.json` and the reproduction commands in
`../README.md`.

`legacy-byte-comparison.json` records a byte-for-byte comparison of a newly
executed experiment-01 report with its retained 4,374-case report. The old API,
model label and serialization remain unchanged. New asymmetric results carry
both applied path resistances and a distinct model-variant label.

## Tests and common runner

With `CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target`:

```sh
cargo test --manifest-path zapote/Cargo.toml --release --offline --locked --workspace
cargo clippy --manifest-path zapote/Cargo.toml --release --offline --locked \
  -p zapote-harness --lib --bin zapote-pfc-drive-experiment --no-deps -- -D warnings
```

The full workspace run completed **545 passed, 0 failed, 1 ignored**. The ignored
case is a live Gmsh meshing check; retained FEM replay tests ran. This full run
preceded the review's diagnostic replay-command fix; subsequent focused test
results are recorded below. The shared solver has not changed since that run.

The seven-unit common run is retained at
`zapote/validation/runs/pfc-drive02-20260917-01/`. Its manifest was
`zapote/power-entry/shunt-repair/units.json`; invocation used `zapote-unit-run`
with `--all`, KiCad's CLI and bundled Python. Exact argv, input hashes, binary
hashes and tool version are retained in the run directory. KiCad reports
**10.0.4** on this machine. All seven units have native ERC/DRC/parity checks
PASS, zero failed finding objects, and overall INDETERMINATE. Exit code 2 is
expected. Buck and MCU remain deferred by that registry. No hardware tests ran.
The common run preceded the isolated diagnostic replay-command fix; it did not
exercise that new command. `common-verification.json` summarizes actual results.

`make regen`, `make regen-check`, and the import-boundary gate passed. Logs are
retained. Regeneration made no unrelated tracked changes. Native KiCad required
the already-authorized escalated runtime. No CAD or procurement input changed.

## Review and follow-through

The actual `ce-code-review mode:agent` receipt is under
`docs/reviews/pfc-drive02-20260917/` with status `complete`. Two local Luna
reviewers covered correctness and adversarial scenarios. Cross-model egress
was not attempted following an earlier automatic approval rejection; the
receipt explicitly lists omitted reviewers. It is not independent cross-model
coverage. The pre-fix verdict was Not ready with two P1 findings; keep it intact.
Final dispositions and regression evidence are in `review-resolution.md`.

Separate Luna reuse, quality and efficiency passes found no necessary cleanup.
The small duplicate resistance expression/checks are negligible; caching three
line moments is optional for this bounded grid. A suggested deletion of config
normalization was rejected: equality permits roundoff, so normalization ensures
the serialized value is the exact applied value. No simplification edits were
made merely to satisfy the review count.

During implementation recursive rustfmt touched six unowned Rust files.
The worker restored only its own formatting changes; the coordinator verified
that none remained. This incident produced no shipped unrelated edits.

## Limits and monitoring

These safeguards reject the tested stale, corrupted, missing and duplicate
inputs; they are not a proof against every future modeling error. DC driver
resistance/typical peak ratings do not establish dynamic behavior, and Qg/Rds
at 10 V do not bound operation at 12 V. Supply producers, hardware EN sequencing,
commutation, overshoot and installed cooling still require separate work.

No additional operational monitoring required: this change adds an offline
diagnostic experiment and preserves the legacy solver results. On replay,
unexpected source/report mismatch is a failure to investigate; never refresh
pins or relax tolerances simply to obtain PASS.

## Post-review focused verification

The final replay module tests passed **5/5**, including retained JSON scalar,
missing-case, duplicate-case and source identity mutations. `replay-tests.log`
retains the worker's actual focused execution. The coordinator independently
ran the real CLI twice: original saved report matched and exited 2; a modified
first-case total was rejected with exit 1 (`replay-validation.json`). Final
package-scoped clippy passed (`clippy-final.log`). No shared solver or common
runner behavior changed during these replay/audit fixes, so the full workspace
and native runs above were not repeated solely for this isolated command.

The final standalone audit passed **5/5 tests** and all **2,916 retained cases**.
The coordinator corrected a test that had kept old TSV column indices, and
made the renumbered-duplicate fixture actually renumber its copied row. A
plateau-reflection probe initially used a case whose energy difference was less
than its 1 W assertion; `audit-probe-failure.log` preserves that failure. The
probe now uses an explicit asymmetric 10 V setup. No production equation or
acceptance tolerance changed to address that test-fixture issue.

Final authored-source/artifact whitespace check passed. The unfiltered git
whitespace check reports spaces in raw Fontconfig stderr and unified-diff
context lines; these original evidence bytes are deliberately preserved.

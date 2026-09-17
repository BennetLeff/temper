# Integrated verification, 2026-09-17

Base: `80ae56830d9cc679b280736fde62461573bcafdd`, on
`codex/buck-harness-experiment-plan`. Code and option reports were authored in
separate Luna worktrees and integrated into the canonical coordinator checkout.
The final code-review receipt's hashes match the integrated production code.
One later test-only runner amendment is explicitly recorded in `provenance.json`.

## Rust and repository checks

All Cargo commands used `--manifest-path zapote/Cargo.toml --release --offline
--locked` with `CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target`.

- `cargo test --workspace -- --test-threads=1`: **534 passed, 0 failed,
  1 ignored**, retained in `workspace.log`.
- The final production-config binding amendment followed that full-suite
  compilation. Re-ran `cargo test -p zapote-harness pfc_loss_budget::tests
  -- --test-threads=1`: **8 passed**, `final-loss-tests.log`. This includes
  self-consistent wrong bus/frequency/Qgd cases and the valid control.
- `cargo build -p zapote-harness --bin zapote-unit-run --bin zapote-pfc-loss`:
  passed from the canonical checkout, `build.log`.
- `cargo clippy --workspace --all-targets`: passed with warnings in unchanged
  DRC/ERC code; no warnings reported in the changed harness files. This was not
  a `-D warnings` run. See `clippy.log`.
- `make regen` and `make regen-check`: passed using writable
  `UV_CACHE_DIR=/private/tmp/zapote-loss-uv-cache`; all derived artifacts
  consistent. See `regen.log` and `regen-check.log`.
- Import boundary gate: **5 contracts kept, 0 broken, 0 new violations**,
  `import-boundary.log`. Used `PYTHONPATH=packages/temper-placer/src` and the
  existing `/private/tmp/zapote-pfc-loss-correction/.venv` with the writable UV
  cache; no package/dependency manifests changed.
- Whitespace checks pass for Rust, Markdown and JSON. The unrestricted check
  flags verbatim PDF bytes and captured Fontconfig stderr whitespace; those
  evidence files were preserved byte-for-byte rather than normalized.

The worker's sparse-checkout full harness attempt lacked runtime FEM fixtures;
it was not authoritative. The integrated full suite above used the complete
canonical checkout. Worker-focused results remain in `../harness/TEST-EVIDENCE.md`.

## Reports and research evidence

`zapote-pfc-loss zapote/power-entry/shunt-repair/candidate/source-manifest.json`
exited **2 (INDETERMINATE)** and produced `loss-report.json`:

- numerical verification: PASS;
- physical applicability and hardware qualification: INDETERMINATE;
- complete loss and cooling margin: absent;
- 54 switching sensitivities: all numerical simulation values equal the
  retained corrected report; the added explicit transfer-charge label matches
  each simulation input (`numeric-comparison.json`).

The three standalone Rust arithmetic receipts were compiled and run locally.
The replacement-FET turn-off regression passed. Their stdout is in the three
`*-arithmetic.log` files and `fet-arithmetic-test.log`. These reproduce bounded
arithmetic, not an independent semiconductor simulator. The replacement-pair
receipt embeds a reference-report digest; the coordinator separately checked
that digest against the actual retained report bytes.

`source-audit.json` records SHA-256, PDF header and successful text extraction
for all six candidate PDFs. Independent review checked the claimed parameters
and source revisions. Pair A's Infineon PDF is still uncaptured and explicitly
not frozen evidence. Cached stock observations were not converted into live
availability claims. All candidate JSON parsed successfully.

## Common runner

Both invocations used `zapote/power-entry/shunt-repair/units.json`, `--all`,
KiCad's `kicad-cli` and its Framework Python runtime. The first run
`pfc-options-20260917-01` exited 1 because sandboxed macOS display initialization
prevented native manufacturing extraction on every unit. Its small failed
receipt and stderr remain retained; this was not a board-validation result.

The rerun `pfc-options-20260917-02` used the necessary macOS runtime access.
It exited **2: seven INDETERMINATE units, zero failed findings, clean native
ERC/DRC/unconnected/parity checks, no suite change during the run**. All three
new assurance rules were both required and emitted for power-entry. Its result
is recorded in `common-verification.json` and `common-run-02.log`.
Source identity is captured by each run; historical run output was not replaced.

After that run, one line extended the existing required-rule omission regression
to iterate the three assurance rules too. This changes only `cfg(test)` code;
the common run's production code is identical. The targeted test result is
retained in `required-rule-test.log`. The pre-amendment reviewed hash and final
hash are both recorded, rather than rebinding the historical run to new bytes.

No powered test, purchase, part substitution, circuit edit or PCB edit occurred.
The remaining engineering evidence is listed in `../RESULTS.md` and each option
report. Numerical PASS does not release hardware for manufacture or operation.

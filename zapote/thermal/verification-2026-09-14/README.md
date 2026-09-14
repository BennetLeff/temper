# Bridge-neck model and copper repair verification

The [assessment](../bridge-necks.md) retains all four bridge-neck current
findings. Numerical validity is established for the declared local model;
assembly thermal acceptance is not established.

The common seven-unit run used KiCad CLI 10.0.6, its Framework Python runtime,
and the current Rust harness. All seven native ERC/DRC/connectivity/parity
checks passed. Six units remain INDETERMINATE; power-entry remains FAIL with
four `DRC.PFC.BRANCH_COPPER` findings. Its thermal numerical rule passes and
thermal applicability remains INDETERMINATE. The command's exit code 2 records
that unresolved suite outcome, not an execution failure.

`common-units.tar.gz` contains the complete run, including native commands,
raw reports, input hashes and source identity. `summary.json`, `power-entry.json`
and `suite-identity.json` are also available directly. This was a dirty working
tree measurement before committing; the source revision and dirty flag are
retained honestly, and the recorded source hashes were checked against the
files being committed. No qualification record was rewritten as a clean run.

Validation receipts:

- `workspace-tests.log`: full Zapote workspace, 360 tests passed before the
  final command-receipt and exact-segment-ID regressions.
- `focused-tests.log`: final thermal and harness crate tests, including the
  retained 40-case replay, rehashed evidence mutations and real PFC-current
  integration.
- `clippy.log`: thermal and harness crates, all targets, no dependency linting,
  warnings denied; passed.
- `import-boundaries.log`: repository import gate passed.
- `regen-check.log`: generated repository artifacts consistent.
- `review/`: completed local code review and finding dispositions. External
  cross-model review was not run because automatic approval review rejected
  sending the diff; local adversarial review ran.

The source-format whitespace check passed. Raw solver outputs retain their
original whitespace. Package-wide formatting also reports existing formatting
in the PFC modules; those files were not changed for this task.

Reproduce the common run from the repository root, with a new output directory:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target make -C zapote check-units \
  KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli \
  KICAD_PYTHON=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 \
  RUN_DIR=/private/tmp/zapote-neck-common-new
```

The first sandboxed attempt could not initialize KiCad's macOS GUI runtime;
the retained run used the required native session access. The 40-case thermal
bundle remains separate and unchanged under `../evidence/bridge-necks-2026-09-14`.

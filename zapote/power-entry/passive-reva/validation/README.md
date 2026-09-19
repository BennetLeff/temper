# Passive checkpoint verification

Final common-suite receipt: [baseline-04/summary.json](baseline-04/summary.json).
Seven maintained units evaluated; all **INDETERMINATE**. Exit code 2 represents
that disposition. `suite_changed_during_run` is false. The power-entry report
declares 74 checked rule IDs against 70 required IDs; it contains no failing
rule findings. This is not a PASS for protection or installed thermal behavior.

The run uses `shunt-repair/units.json`, the maintained passive source/native
contract. Its power-entry board bytes are identical to the new passive working
copy. The new source entry has a separate Rust binding test; the common runner
was not modified to recognize an additional entry.

## Commands and identity

From repository root:

```sh
cargo build --release --locked --offline --manifest-path zapote/Cargo.toml -p zapote-harness --bin zapote-unit-run
/Users/bennet/Desktop/temper/target-shared/release/zapote-unit-run \
  zapote/power-entry/shunt-repair/units.json \
  zapote/power-entry/passive-reva/validation/baseline-04 \
  /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli \
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 --all
```

For a replay choose a new output directory; do not overwrite retained evidence.
The binary/input/source hashes and raw native commands are retained in the run.
This run used KiCad 10.0.4 and required native display access for pcbnew.

## What passed, and what it does not establish

- Fresh native ERC/DRC and existing source/native, connectivity and stackup
  checks report no failing findings on the power-entry baseline.
- Existing GBJ joint and physical-model replays pass their numerical checks.
  Existing shunt local and assembly replays verify 15 and 19 retained solves.
  These are replays of retained FEM outputs, not fresh solver executions or
  powered tests. The existing checker explicitly permits the historical
  geometry-only transfer across the documented boost-device property change;
  it does not transfer other-device heat or cooling qualification.
- Cooling applicability, current sharing in finite-width/parallel contacts,
  high-frequency loop geometry/inductance, external HOT bias and supervisor,
  input foldback, controller timing and physical protection remain unresolved
  in the actual report. Some are missing model/coverage inputs; they must not
  all be relabeled as merely awaiting a bench test.
- A conditional cooling-budget PASS checks the old declared 110.6 W allowance.
  It does not establish that this is the actual heat load. The new
  [cooling checkpoint](../cooling/README.md) records why that allowance cannot
  currently support installed-temperature acceptance.

## Focused checks and review

- Existing Rust `Circuit::parse` / `bind_native`: 1 integration test passes,
  including exact native-evidence PCB text versus candidate bytes.
- Cooling arithmetic: 3 tests pass. Film-reservoir arithmetic: 2 tests pass.
  These tests verify the finite equations, not physical applicability.
- Five referenced source-file SHA-256 values verified.
- Raw test outputs and source hashes: [coordinator](coordinator/).
- Luna's final bounded review found no remaining acceptance-changing defects
  in the checkpoint. Its scope and corrected earlier findings are recorded in
  [review.json](coordinator/review.json).

## Retained non-final attempts

- `baseline-01`: native adapter could not access the macOS display inside the
  sandbox. The resulting failures are execution failures, not circuit findings.
- `baseline-02`: incomplete debug run; stopped before power-entry completion
  and replaced with an optimized build of the same implementation.
- `baseline-03`: incomplete optimized run; stopped after the scoped test source
  changed during execution. It is not used as a stable-suite receipt.
- `baseline-04`: final completed stable-suite run described above.

No attempt is silently discarded or counted as a full pass.

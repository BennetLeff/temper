# Replaying RTD model qualification

Run from the repository checkout containing this Zapote subproject. A complete
model-qualification replay leaves the original RTD board and historical bundle
unchanged. It writes the new report under `qualified-input/`.

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo fmt --manifest-path zapote/Cargo.toml --all --check
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo build --manifest-path zapote/Cargo.toml --bin zapote-rtd
python3 zapote/rtd/model-correctness/qualification/full_network_bound.py
python3 zapote/rtd/model-correctness/qualification/spice_cases.py
python3 zapote/rtd/model-correctness/root-review/reference_calculation.py
python3 zapote/rtd/model-correctness/root-review/sample_inequalities.py
cp /private/tmp/zapote-rtd-target/debug/zapote-rtd zapote/rtd/model-correctness/qualified-input/zapote-rtd
python3 zapote/rtd/model-correctness/root-review/bind_qualification.py zapote/rtd/model-correctness/qualified-input/zapote-rtd
zapote/rtd/model-correctness/qualified-input/zapote-rtd --unit-input zapote/rtd/model-correctness/qualified-input/input.json --output zapote/rtd/model-correctness/qualified-input/report.json
python3 zapote/rtd/model-correctness/root-review/replay_mutations.py zapote/rtd/model-correctness/qualified-input/zapote-rtd
```

The unit command deliberately exits **1** while device applicability and
brownout timing remain INDETERMINATE; inspect the JSON findings rather than
interpreting that exit as a solver crash. The mathematical gate should pass.
The mutation script requires expected rule-specific verdicts and rejects crashes.
The checked-in executable is a local replay artifact; rebuild it for another
host or after any Rust source change, then rebind its SHA-256.

Python 3.14.7, ngspice 45.2 and cargo 1.92.0 were used for this replay. The
SPICE model assumes ideal internal force paths and constant bounded sources;
see [applicability review](applicability-review.json). The capacitor/source/
comparator conditions are not hardware measurements.

`cargo clippy --all-targets` completes with the pre-existing
`manual_range_contains` warning in `zapote-drc/src/lib.rs:135`.
Treating all warnings as errors therefore fails on that unchanged code; the
qualification implementation introduces no outstanding Clippy warning.

Evidence identity is recorded in `closeout-receipt.json`. A replay that changes
artifact bytes must issue a new receipt; it must not silently reuse the old one.

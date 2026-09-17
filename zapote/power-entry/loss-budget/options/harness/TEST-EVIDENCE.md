# PFC model assurance harness evidence

The focused checks were run from the isolated checkout with the shared release
target and locked offline dependencies:

```text
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml --release --locked --offline -p zapote-harness model_assurance::tests -- --nocapture
8 passed
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml --release --locked --offline -p zapote-harness pfc_loss_budget::tests -- --nocapture
8 passed
```

The tests cover the numerical pass, unresolved applicability, malformed or
stale provenance, missing or mismatched independent reference, wrong RMS and
current, assumed gate drive, omitted/duplicated term ownership, and the
production report's required assurance rules.  The retained fixed fixture is
`triangle-anchor.json` (SHA-256
`a59dafc68342b497615a6a94eb806e4721b43fb9cb9f8feb62b4b2a90e289a70`); the
model result is compared with its 100 µJ value for 400 V, 10 A, 20 ns current
transfer and 30 ns Miller time.

This remains a sensitivity model.  The production report intentionally leaves
physical applicability and hardware qualification indeterminate: the adapter
has no measured gate waveform, hot switching capture, installed cooling
evidence, or importer that can verify those claims.

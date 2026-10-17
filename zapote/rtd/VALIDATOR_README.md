# Zapote RTD validator

This is the compact Rust validation boundary for the RTD sensing milestone.
The JSON input is `zapote-rtd.v1` and is deliberately source-derived: the
board snapshot carries native connectivity clusters, pad positions, copper
geometry, and component identities. The validator never treats a component
name or a file being present as proof of a connection.

Run it with:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target \
  cargo run --manifest-path zapote/Cargo.toml -p zapote-harness --bin zapote-rtd -- \
  --input zapote/fixtures/rtd-valid.json --no-telemetry
```

`--no-telemetry` is the offline path; the output remains a local evidence
record and includes the canonical input hash and all identities.


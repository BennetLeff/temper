# SYNTHETIC ONLY parent fixture

This directory contains a fake five-argument tracked producer for bounded
runner integration tests. It is not ngspice, not a circuit model, and not
operating evidence. Do not use its output as an accepted baseline or as a
hardware/protection result.

## Producer contract

`synthetic_normal15_producer.rs` accepts the same five user arguments used when
`--first-invalid-snapshot` is enabled:

```text
synthetic_normal15_producer DECK WALL_SECONDS TARGET_SECONDS EXPORT_PATH SNAPSHOT_PATH
```

The deck argument is intentionally ignored. `TARGET_SECONDS` must be exactly
0.65 s. The producer writes a complete little-endian `ngspice-real-native`
normal15 header and row-major binary64 payload directly to `EXPORT_PATH`, which
may be a FIFO. It emits 1,300,002 rows: 500 ns samples from 0 through 0.65 s,
plus one deliberate equal-time duplicate at 0.620000 s. That duplicate is
harmless for transport but must preserve the legacy strict-checker rejection
(`time not strictly increasing`) after decoding/normalization.

The synthetic values are fixed for the LL01 contract (108 V RMS, Rload
416.460488957 ohm, v(load)=v(vb)=v(vd)=389.6 V, v(sw)=20 V,
v(gate)=10 V, q/en=5 V, fault=0). `i(Vac)` is a 60 Hz in-phase sinusoid with
negative ngspice source-current sign so the maintained normalizer computes
positive real input power (`Pload=389.6²/416.460488957`, about 364.5 W).
All values are finite and below engineering stress screens by construction;
this is only a pipeline fixture.

The producer also writes local `progress.tsv`, `stop.txt`,
`first-invalid.tsv`, and `capture-metadata.json`. Metadata is explicit:
`diagnostic_only=true`, `accepted=false`, `synthetic_fixture=true`,
`export_format=ngspice-real-native`, `byte_order=little`, normal15 schema,
65535 name masks, 1,300,002 points, `solver_stopped`, `first_invalid=true`,
and `duplicate_count=1`. The metadata note says that it is not ngspice or
electrical evidence.

## Bounded checks

```text
rustc --edition=2021 -D warnings --test synthetic_normal15_producer.rs
2 tests passed
rustc --edition=2021 -D warnings -O synthetic_normal15_producer.rs \
  -o /tmp/matrix07-synthetic-normal15-producer
```

A direct FIFO smoke used the binary producer and `pigz`, then the reviewed
normal15 native decoder. No runner or electrical simulation was launched:

```text
producer_rc=0 gzip_rc=0 adapter_rc=0
rows=1,300,002 compressed_bytes=28,268,703
```

The smoke receipts were temporary and removed after the check. Parent may invoke
the `/tmp` binary as the tracked executable in an explicitly synthetic output
folder; retain the obvious synthetic labels and keep the resulting reports
separate from production artifacts.

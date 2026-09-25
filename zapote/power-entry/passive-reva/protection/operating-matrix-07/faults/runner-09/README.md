# Fault runner 09: bounded single-case supervisor

This directory contains a preparation-only supervisor for one already
materialized fault case. It does not select a grid or decide whether the
hardware protection is adequate. The maintained fault adapter and checker
remain unchanged and authoritative.

The supervisor runs two bounded stages:

1. `tracker DECK WALL TSTOP host.raw.fifo first-invalid.tsv` writes through an
   owned FIFO to `pigz -c`, retaining exactly one `raw.trace.tsv.gz`.
2. `gzip -cd raw.trace.tsv.gz` feeds the maintained adapter through a FIFO.
   The adapter writes its checked 17-column stream to a checker FIFO. Its
   supplemental stream goes to `/dev/null` because the raw gzip is the
   complete retained vector source. The checker report, adapter report, and
   every stdout/stderr stream are retained.

Every child is supervised and reaped. Missing executables, FIFO/type errors,
tracker/compressor/decoder failures, adapter rejection before opening outputs,
checker rejection, and timeouts fail closed. A checker `PROTECTION_GAP` is
recorded as `expected_checker_protection_gap`; it is not converted to PASS.
Other checker failures return an error classified as
`checker_rejected_or_parse_failure`.

The five-argument tracker protocol is fixed. The CLI is:

```text
supervisor CASE TRACKER ADAPTER CHECKER PIGZ TSTOP ADAPTER_KIND CHECKER_KIND MUTATION_S EVENT_WINDOW OBSERVATION_S MAX_GAP WALL_SECONDS EXPORT_TIMEOUT
```

For a real case, invoke only after the campaign runbook's accepted-normal
gate and phase/event receipts pass. No campaign was launched while preparing
this directory.

## Bounded checks

```sh
rustc --edition=2021 -D warnings --test supervisor.rs \
  -o /tmp/matrix07-fault-supervisor-tests
/tmp/matrix07-fault-supervisor-tests
rustc --edition=2021 -D warnings -O supervisor.rs \
  -o /tmp/matrix07-fault-supervisor-09
```

The host was exercised against a synthetic 42-column, 20 us, 1001-row
physical-shaped trace using the actual compiled adapter and checker. The run
produced `SCHEMA_AND_EVIDENCE_OK`, checker classification `checker_pass`, and
no FIFOs left behind. A failing adapter fixture exits promptly and leaves no
FIFO; a failing compressor fixture is rejected before any stage-2 launch.
These are transport checks, not electrical evidence.

The runner refuses any pre-existing output, records SHA-256 hashes for the
complete supported local `.include` closure (deck, manifest, and nested
include files) plus every executable, rechecks that closure after transport,
and uses `pigz -p 4 -c` for the retained raw stream. Unsupported include forms
and escapes fail closed. This prevents a rerun from silently mixing receipts
or source bytes.

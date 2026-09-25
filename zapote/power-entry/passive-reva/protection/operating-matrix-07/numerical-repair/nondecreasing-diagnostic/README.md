# Raw 31-column timestamp/event audit

`audit.rs` is a diagnostic-only streaming reader for the raw 31-column TSV
traces produced by the operating-matrix harness.  It reads stdin, requires a
31-field header whose first field is exactly `time` and whose names are unique,
then validates every data field as finite.  It rejects backward timestamps but
accepts exact-equal timestamps as event groups so their structure can be
reported instead of hidden by deduplication.

Build and run it directly:

```text
rustc --edition=2021 -D warnings audit.rs -o audit
audit < trace.tsv > audit.txt
```

The output is bounded: total rows, equal-group/duplicate counts, first and last
ten equal groups, the largest equal group, maximum **adjacent** value change per
column within an equal group, and per-column extrema with row/time locations.
The adjacent-change label is deliberate; it does not claim a full group range
or invent a tolerance.  All 31 columns participate in the extrema scan,
including rows inside duplicate groups.  A duplicate group at EOF is rejected
because it has no following positive time progress.  On rejection, the tool
also prints the rows seen, the active equal group, and all partial per-column
extrema to stderr, so an invalid trace does not discard the evidence collected
before the fault.

No engineering metric, integral, acceptance threshold, waveform tolerance, or
qualification verdict is computed.  The summary is intended to distinguish an
isolated repeated timestamp from persistent duplicate events and to preserve
the raw event deltas for later interpretation.

`tests.rs` compiles as a standalone Rust test binary with `-D warnings` and
covers exact-equal groups, adjacent per-column deltas, duplicate-row extrema,
widely spaced groups, backward time, non-finite values, and an equal group at
EOF.  The tests use only small synthetic 31-column traces; they do not alter or
rewrite any simulation trace.  A bounded host-smoke receipt is in
[`host-smoke-audit.txt`](host-smoke-audit.txt): 51,075 rows were streamed from
the existing trace, with zero equal groups and no acceptance claim.  Source and
receipt hashes are in [`SHA256SUMS`](SHA256SUMS).

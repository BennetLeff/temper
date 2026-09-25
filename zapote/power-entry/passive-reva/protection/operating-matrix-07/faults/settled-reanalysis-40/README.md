# Settled reanalysis 40: global-gap binding correction

The completed F2-CREST38 capture reported 32,237,324 fault42 rows, host/pigz
exit 0, 5,297,726,667 bytes, and raw SHA-256
`d78e8e2f7c28b8ba9c10ce499af2813202ede8b2e173c39cfdc0ee3d650484fd`. This
folder does not read or decompress that raw file and does not launch a new
simulation. It is a worker-review fork of `faults/reanalysis-23/supervisor.rs`.

## Root cause

`faults/event-aware-adapter-13/README.md` defines the adapter's campaign-wide
positive-gap bound as 1 us; the 25 ns value belongs to local fault-deck pacing.
The adapter rejects any `dt > cfg.max_gap` at
`event-aware-adapter-13/fault_normalize.rs:358-360`. Reanalysis-23 read
`run-parameters.json.max_gap_s` (the capture's 25 ns pacing value) and passed it
to both the adapter and validator. The completed trace therefore failed at
row 165 with “time moves backwards or gap exceeds max_gap” even though the
global contract permits up to 1 us. This is a transport-bound propagation bug,
not a reason to relax any local fault timing or electrical screen.

## Candidate correction

`supervisor.rs` keeps the immutable capture parameter for provenance and
requires the prepared campaign’s exact 25 ns bound, but passes the explicit
`GLOBAL_MAX_GAP_S = 1e-6` to both stage-2 adapter and validator. The capture's
25 ns value is never silently rewritten in its source metadata. The parent also corrected the inherited manifest binding for `SW-SHORT`: its
manifest key maps to the `switch-short` CLI spelling. F2-CREST’s mapping remains
unchanged. The frozen inner event/retained-off check still enforces 25 ns.

The rest of reanalysis-23 is unchanged: source/manifest/tool/raw hash binding,
fresh output directory, child timeout and kill/reap, disk floor, row counts,
and diagnostic-only receipt. A validator exit 0 remains `acceptance:false`.

## Verification

```text
rustc --edition=2021 -D warnings --test supervisor.rs -o /tmp/matrix07-settled-reanalysis40-tests
/tmp/matrix07-settled-reanalysis40-tests
# Parent suite now6 tests; worker originally5 passed: finite-positive args, global-gap mapping, JSON controls, FIFO verification, timeout kill/reap

rustc --edition=2021 -D warnings -O supervisor.rs -o reanalysis40-supervisor
```

Source and binary SHA-256 are in `candidate-receipt.json`. No real reanalysis
was launched by this candidate; parent review must bind the completed capture
and choose a new empty output directory before executing it.

Parent correction: the triggering38 failure was in runner29; reanalysis23 inherited the same argument propagation bug. Original worker source is retained.

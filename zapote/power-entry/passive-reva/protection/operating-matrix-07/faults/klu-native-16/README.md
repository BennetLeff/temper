# KLU native fault-host validation (bounded 10 ms probe)

This one-run native-host probe validates the reviewed 42-vector export path
with the KLU-selected deck.  It is diagnostic only and does not authorize a
long fault launch or a solver/model change.  The deck is copied from
`faults/startup-candidate-13/case.cir`: only `TSTOP` is changed from
`8.900000000000e-2` to `1.000000000000e-2`, and one `.options klu` line is
added.  Fault time remains 75 ms, outside this 10 ms startup window.  All five
include files are byte-identical copies; `input-sha256.txt` binds them and the
probe deck.  `tool-sha256.txt` binds the existing reviewed native host and
decoder.

## Command and host result

The host was run from this directory so relative includes resolve:

```text
SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts \
  /private/tmp/matrix07-fault-native-host-parent case.cir 30 0.01 \
  raw.fifo first-invalid.tsv > host.stdout 2> host.stderr
```

`pigz -p 2 < raw.fifo > raw.trace.raw.gz` consumed the FIFO concurrently.
The host and pigz both exited zero.  `host.stdout` reports
`last_callback_time_s=1.00000000000000002e-2`, 142,428 points, and
`first_invalid=false`; `host.stderr` includes `Using KLU as Direct Linear
Solver`.  Capture metadata records fault42, both name masks 65535, little
endian native format, zero duplicate/backward/nonfinite timestamps, and
`accepted=false`/`diagnostic_only=true` as required for this diagnostic.

## Decoder and validation

The retained raw gzip was decoded with:

```text
pigz -dc raw.trace.raw.gz \
  | /private/tmp/matrix07-fault-native-decoder-parent \
      --schema fault42 --byte-order little > decoded.tsv 2> decoder.stderr
```

The decoder exited zero and emitted the exact 42-name header plus 142,428
rows.  The Rust `validate42.rs` checker (source and binary hashes are in
`artifact-sha256.txt`) validates every row has 42 finite fields, nondecreasing
time, first time `2.00000000000000007e-10 s` (within 1 ns), and endpoint
`1.00000000000000002e-2 s` (within 1 fs).  It reports
`max_positive_gap=5.00000000000500044e-7 s`, `repeats=0`, and exits zero.  The
initial validator report that accidentally included an infinite first gap is
retained as `validate42-pre-fix-superseded.txt`; it was a checker initialization
defect, not a simulation output, and is excluded from the final receipt.

The complete raw gzip, decoded 42-column text, metadata, command logs, source
and tool hashes are retained under this directory.  This demonstrates that the
shared native host honors `.options klu` through the 10 ms startup window and
that all42 transport remains finite and ordered.  It does not demonstrate
75/89 ms fault completion, protection timing, energy closure, or hardware
qualification; parent review must decide whether a longer source-bound KLU
comparison is warranted.

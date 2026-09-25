# Full first-invalid capture for the finite driver threshold probe

This is a prepared diagnostic capture for the authored finite-driver
threshold model (`pwm_input` transitions from 2.1 V to 2.3 V). The electrical
deck and four include files are copied from `../host-run`; only the `.save`
line is expanded with the sixteen first-invalid diagnostic vectors. The
capture does not establish a normal operating point or a hardware claim.

The exact callback source is copied from
`../../../first-invalid-capture/run/progress.rs`. It requires five arguments
after the host binary, including the snapshot path:

```text
./matrix07-finite-driver-capture-host cold.cir 600 0.5 trace.fifo first-invalid.tsv
```

The parent launch protocol is therefore: create `trace.fifo`, start a gzip
reader, then run the command above with the ngspice library and script paths
set. This directory has no full-run FIFO, gzip output, or full-run result.

The host was compiled as `/private/tmp/matrix07-finite-driver-capture-host`
with `rustc --edition=2021 -D warnings -O progress.rs -L /opt/homebrew/lib
-l ngspice`. `inputs.json` records all source, include, callback, and binary
hashes. The separate `smoke/` directory ran the same host for a two-second
wall limit and exported a trace whose header contained all sixteen diagnostic
names; it stopped at 7.9975 ms simulation time with `first_invalid=false`.


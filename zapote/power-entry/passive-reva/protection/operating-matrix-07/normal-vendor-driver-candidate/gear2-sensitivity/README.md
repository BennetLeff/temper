# Gear-2 solver sensitivity (diagnostic, unexecuted)

This is a bounded numerical diagnostic for the vendor-driver candidate. It
starts from the exact `normal-vendor-driver-candidate/tracked/run` deck and
its complete local include closure, including `vendor/UCC27511A.lib`. The
only candidate changes are:

```text
.options method=trap ...  ->  .options method=gear maxord=2 ...
.param ... TSTOP=500m ... -> .param ... TSTOP=110m ...
```

The 110 ms endpoint crosses the previously observed approximately 97 ms
solver boundary. This case is diagnostic evidence about integration-method
sensitivity. It is not a normal operating-point acceptance run, and it must
not create a baseline receipt or be used to claim protection behavior.

`inputs.json` records the exact source/include/host hashes. `verify.rs`
performs the inverse deck replacement and byte-compares every nested include.
Run it from this directory:

```sh
rustc --edition=2021 -D warnings -O verify.rs -o /tmp/matrix07-gear2-verify
/tmp/matrix07-gear2-verify
```

The existing tracked host is the provenance-matched
`/tmp/matrix07-vendor-tracked-host`; its four arguments are `cold.cir 600
0.11 trace.fifo`. The parent workflow owns starting the FIFO reader and host.
This directory intentionally contains no FIFO, gzip output, or simulation
result.
# Completed host result

The subsequently launched run failed at57.498293288 ms, before its110 ms
target, after36.625509 wall seconds. ngspice reported timestep6.25e-19 and
`vac#branch`. Producer97282 and compressor52463 both finished; the host's
strict inspector rejected the endpoint after checking658,685 finite,
strictly increasing rows. See `execution.json` and `inspection.txt`.
The method change is not adopted, and the simulator's named branch does not
by itself identify the causal element. The preparation receipt below records
the state before launch.

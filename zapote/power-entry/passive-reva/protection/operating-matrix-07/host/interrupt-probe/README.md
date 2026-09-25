# Disposable ngspice interrupt probe

This directory tests only a short, isolated circuit with a known subprocess
PID. It does not inspect, signal, attach to, or kill the active normal batch.

Run:

```sh
python3 run_probe.py
cat result.txt
cat probe.log
```

The harness starts `ngspice-45.2 -b`, waits one second, sends `SIGINT` to that
exact PID, and gives it eight seconds to exit. It does not write `\x03` to
stdin: terminal Control-C and a signal sent to a batch subprocess are distinct
operations. The probe's `meas`, `resume`, and `wrdata` commands are deliberately
after the long `tran`; the result therefore distinguishes an interrupt that
returns to the control interpreter from one that terminates batch execution.

`result.txt`, `probe.log`, and the captured transport streams are evidence from
the disposable probe. A partial file is useful only if ngspice actually wrote
it and its last timestamp is inspected; absence means there is no safe partial
export from this invocation. Do not infer that an interrupted production run
can be resumed from an arbitrary output file.

Observed result on ngspice 45.2: the exact child PID received SIGINT and exited
with return code -2 after about 1.013 s. The batch log contains only the initial
operating point; no `meas`, `resume`, or `wrdata` command after `tran` ran, and
no partial TSV was created. This is a termination, not a graceful return to the
control interpreter.

## State snapshots

ngspice's `write`/`save` commands save vectors and raw data, not a generally
restartable nonlinear solver state. The separate `snapshot_probe.cir` test
used a stop breakpoint and successfully wrote `probe.snap` (4.6 KB) with
`snsave`; this is a controlled breakpoint, not SIGINT. The companion restore
script did not produce a resumed TSV because `snload` requires the original
circuit/script loading arrangement; that is evidence to fix and retest before
using it operationally. The official ngspice 45 manual documents `snsave` and
`snload` as the intended breakpoint snapshot/resume mechanism:
https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf (sections 13.5.84–85).
They are not a promise that an arbitrary SIGINT can continue at the same
internal timestep. A future batch design may checkpoint deliberately at a
known `.control` boundary and prove restore equivalence, but this probe does
not alter the active run or claim that capability.

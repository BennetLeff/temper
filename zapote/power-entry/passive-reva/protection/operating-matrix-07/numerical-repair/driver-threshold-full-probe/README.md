# Controlled full-plant driver-transfer probe

Only the Bdriver_req PWM transfer changed: the hard 2.2 V comparison became
a linear transition from 2.1 to 2.3 V. Disable/AUX guards and every other
circuit equation, parameter, initial condition and saved signal are unchanged.
The host verified the inverse single-line replacement against normal-tracked.
This is a diagnostic sensitivity, not an adopted model or circuit change.

The successful execution is in `host-run/`. Its `inputs.json` binds actual
source files and the dedicated host-compiled executable. The `source/`
folder is an earlier delegated preparation; its tracker copy was not the
correct runtime source and must not be cited as the source of this run.
Two failed launches exited before simulation: an incompatible executable
argument contract, then an extra argument to the correct executable. Their
logs are retained in `host-run/failed-launch-*.log`. Orphan FIFO shells were
stopped before the successful run.

Correct command, with four arguments after the executable:

```
SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts \
/private/tmp/matrix07-normal-tracker-host-20260920 cold.cir 60 0.5 trace.fifo
```

The producer and compressor both exited zero. A separate full-trace
inspector found 1,420,780 finite, strictly increasing rows through
0.0663267728431966713 s. Minimum positive step was 5.0306980803e-17 s.
The earlier unchanged 60-second probe reached 0.06616456597578449 s with
1,412,803 finite strict rows and minimum step 1.3877787808e-17 s.

These wall-limited probes do not demonstrate a meaningful speed improvement.
Very small time steps remain. Neither probe reached the prior first-invalid
time at 0.256990362 s, so the experiment neither proves nor disproves removal
of that later failure. No normal operating point was accepted. Prefer the
separately validated vendor-driver candidate as the next source-supported
model test rather than adopting this arbitrary voltage transition width.

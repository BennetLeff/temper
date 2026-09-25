# XSPICE snapshot/restore probe result

Fixture: copied `pwm-hold-capture.cir` and `ucc28180-pwm-latch.inc` from the
normal worker's shared-capture output. The only local fixture edit changes the
include path to the copied model in this directory; no device or IC values
were changed. ngspice reports version 45.2.

Commands run:

```sh
ngspice -b -o baseline.log baseline.cir
ngspice -b -o save.log save.cir
ngspice -b -o restore.log restore.cir
```

The uninterrupted baseline reaches `2.00000000e-05 s` and writes
`uninterrupted.tsv` (20,509 rows). The controlled-stop run reaches the exact
10 us breakpoint, then `resume` reaches 20 us and writes
`resumed-same-process.tsv` (20,511 rows). The two extra rows are the exact
10 us breakpoint and the restarted step sequence. The pre-10-us rows are byte
identical between baseline and same-process output. The resumed output starts
at exactly `1.00000000e-05 s`, ends at `2.00000000e-05 s`, and its post-10-us
gate maximum is 15 V, matching the baseline post-10-us maximum.

The snapshot attempt is unsupported for this XSPICE circuit. `save.log`
contains the exact ngspice diagnostic:

```text
Warning: snsave not implemented for XSPICE A devices.
Command 'snsave' will be ingnored!
```

No snapshot file was created. A fresh-process `snload` attempt consequently
reported:

```text
Error: Couldn't open "pwm-hold-10us.snap" for reading
```

and exited with return code 139; it produced no restored waveform. This is
reported as unsupported, not as a restore proof. The same-process
`stop`/`resume` path works, but it cannot avoid repeating startup in a fresh
process for this XSPICE model.

The ngspice 45 manual documents `stop`/`resume` and `snsave`/`snload` as the
general snapshot mechanism, but the runtime diagnostic above is authoritative
for this XSPICE `A`-device fixture. Reference:
https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf, sections 13.5.67
and 13.5.84–85.

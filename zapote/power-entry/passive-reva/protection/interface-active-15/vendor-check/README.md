# Manufacturer-model functional check

`SN74HCS74.CIR` is copied byte-for-byte from the earlier official TI SCEM774
archive in f2-shutdown-03/vendor. Two instances represent the two halves of the
existing dual latch: Q2 authorizes D1, and both clears share the hardware trip.
Ideal5V rails, ideal pulse sources and50pF output loads isolate logical behavior.

The TI model contains an internal10nF input capacitor that is not a physical
pin-capacitance model. Directly cascading the models produced a misleading
slow Q2 waveform. `initial-unbuffered.log` preserves it. A zero-delay unity
voltage source transports Q2 to the second model's D input without imposing
that artificial load. It is a simulation adapter, not a proposed hardware
buffer. This fixture establishes neither delay nor actual driver loading.

Ten assertions check premature START rejection, first authorization/start,
asynchronous clearing of both halves, held-high recovery, stale START rejection,
fresh authorization without a new START edge, and eventual fresh START.
The `rejected-fixed-d1.cir` mutation keeps D1 tied high as in revision11;
the same checker must fail. This demonstrates that the test observes the
proposed wiring change, not merely whether a simulator completed.

Reproduce from this directory:

```sh
ngspice -n -D ngbehavior=ps -b two-latch.cir > two-latch.log 2>&1
rustc --edition=2021 check.rs -o /tmp/temper-interface15-check
/tmp/temper-interface15-check two-latch.log
ngspice -n -D ngbehavior=ps -b rejected-fixed-d1.cir > rejected-fixed-d1.log 2>&1
/tmp/temper-interface15-check rejected-fixed-d1.log # expected nonzero
```

The log and TSV are the authority for this functional experiment. This is not
an LT4363 simulation, full protocol integration, MCU implementation, physical
reset-timing measurement or hardware qualification. No claim that a nominal
SPICE trace proves a datasheet maximum follows.

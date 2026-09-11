# Startup protocol resolution instrument

This bounded native ngspice instrument isolates the startup load contract from
the switching model. It starts both 44 uF output nodes discharged and applies a
0.5 A requested load. `B_IDEAL` is an ideal current sink; `B_COMPLIANT` uses the
same 0.1 V compliance law as the load-step deck and therefore supplies zero
current at a discharged output. The resulting voltage and current measurements
show why requiring 0.5 A from the VIN ramp start is physically incompatible
with a voltage-compliant sink unless the output rail is already established.

This is protocol evidence only. It is not buck qualification evidence and does
not modify the model, margins, authoritative requirements, or trusted
registry.

Run with:

```sh
/opt/homebrew/bin/ngspice -n -b instrument.cir > instrument.log 2>&1
```

The implemented validator contract retains the 0 A / 0.5 A startup intent,
but define the 0.5 A requirement as a post-rail load condition: before the
output reaches the declared compliance voltage, the allowed load is bounded by
`max(0, min(1, VOUT/0.1 V)) * 0.5 A`; after that point the measured load must
remain within 2% of 0.5 A through the existing capture window. The existing
VIN ramp, final 3.3 V regulation, 8 ms rise, and 100 mV overshoot limits remain
unchanged. A focused Rust regression should exercise a discharged-output
waveform and assert that startup validation does not demand impossible current
before compliance, while still rejecting a post-compliance under-load.

The instrument measured 0.4999998 A ideal current and 0 A compliant current
through the first 1 ms. At 1 ms the ideal sink drove its discharged capacitor
to -11.36363 V, while the compliant sink remained at 0 V. These are stimulus
measurements only.

The adopted full schedule is 13 cases: six startup cases (VIN 13.5, 15.0, and
16.5 V, each at 0 A and 0.5 A), six load cases (the continuous 0.05-to-0.5 A
and 0.05-to-1 A profiles at each of those three VIN values), and one input
variation case. The current 30 s / 32 MiB / 1 M-row limits are suitable for
the harness protocol, but a 20 ms datasheet-model run can produce roughly 3–4 M
rows, so it needs a separate resource budget or an explicitly file-backed
collector path before full-resolution qualification runs.

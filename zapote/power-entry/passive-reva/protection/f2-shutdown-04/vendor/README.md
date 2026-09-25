# Independent driver check

`slvmcj6.zip` was retrieved on 2026-09-19 (local date) from TI's official
https://www.ti.com/lit/zip/slvmcj6. Its extracted `UCC27511A.lib` is unchanged.
The model is TI's transient model version 1.00, 12 January 2018. Ngspice45.2
runs it with PSpice compatibility selected by the retained `.spiceinit`.

`driver-bounded-interface.cir` exercises default-off, positive enable,
explicit disable, absent auxiliary supply and supply return while disarmed.
Separate10Ω gate resistors connect OUTH and OUTL to an authored12nF load.
IN− has the circuit's external10kΩ pullup; a small MOSFET sinks it through
RUN control, with1kΩ series gate and100kΩ gate pulldown.

The small transistor is an **authored surrogate**, not Nexperia's BSS138
manufacturer model. Its explicit60pF gate-source,10pF gate-drain and15pF
drain-source capacitances are declared fixture assumptions. No worst-case
BSS138, full power-MOS current cessation, or component-temperature guarantee
is inferred from this run. The independent oracle here is the unchanged TI
**driver** model, including its input polarity, default state and output stage.

All five state observations pass. Observed RUN falling50% to gate4V is
0.259501µs; observed IN−2.2V rising to OUTL13.5V falling is0.011020µs.
The strict Rust checker rejects absent, duplicate and nonfinite measurements
and a failed positive-enable control. Its two tests pass.

Earlier `driver-default-check` and `driver-nmos-check` attempts are retained.
The NPN attempt did not reach its asserted positive-enable window; it is not
a passing result. The first NMOS attempt omitted meaningful discrete
capacitances and is superseded by `driver-bounded-interface`.

Reproduce from this directory:

```sh
ngspice -b -o driver-bounded-interface.log driver-bounded-interface.cir
rustc --edition=2021 check_driver.rs -o /tmp/f2b-check-driver
/tmp/f2b-check-driver driver-bounded-interface.log
```

## Final integrated revision (supersedes the10k pullup attempt above)

The authoritative fixture is `driver-final-interface.cir`, with **1kΩ** IN−
pullup and separate10Ω gate resistors. Loaded RUN-to-gate4V delay is0.211801µs.
Two additional tests leave the logic output high impedance with its actual10k
pulldown while holding PWM high, then ramp AUX0→15V in1ns or1µs. Peak gate
voltages are18.47mV and2.29mV. The previous10k IN− pullup produced3.726V in
the1ns test and is rejected by the same checker (`rejected-10k-check.txt`).
This caused the circuit change to a1kΩ pullup, sized for0.324W at18V.

`run_checks.sh` reruns the final three fixtures and strict checks. The early
NPN and unbounded-capacitance trials remain diagnostic attempts only.

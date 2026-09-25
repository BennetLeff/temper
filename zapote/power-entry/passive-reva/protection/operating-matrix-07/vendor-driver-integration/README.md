# UCC27511A vendor-driver integration fixture

This fixture compares the retained TI UCC27511A transient model with the
normal-tracked matrix-07 protection disable path. It is deliberately short and
isolates the gate-driver interface; it is not a hardware qualification or a
claim that the vendor model is equivalent to the normal-tracked surrogate.

Run it from this directory:

```sh
ngspice -b -o vendor-driver-interface.log vendor-driver-interface.cir
rustc --edition=2021 -D warnings -O check_vendor_driver.rs -o /tmp/check_vendor_driver
/tmp/check_vendor_driver vendor-driver-interface.log vendor-driver-interface.tsv
```

The fixture uses the unchanged model at
`../../f2-shutdown-04/vendor/UCC27511A_TINA_TRANS/UCC27511A.lib` (SHA-256
`eb78c0ce0d9cf2dd5bbc5f937bbfc6cc38c95215e035feaeb3950672e8c05c6d`) and the
local `.spiceinit` `set ngbehavior=ps`. The model's SPICE pin order is
`INM INP VDD GND OUTH OUTL`; this differs from the physical KiCad symbol pin
number order and is stated at the `Xdriver` line to make accidental pin-order
changes visible.

The normal-tracked protection values are retained exactly in the fixture:

* `run -> 1 kΩ -> smallgate`, with `100 kΩ` smallgate-to-ground pull-down;
  `Mdisable` is the existing `DISABLE_FET` model (`VTO=1.5`, `KP=.1`,
  `RD=2`, `RS=2`), with the existing `60 pF`, `10 pF`, and `15 pF`
  parasitics.
* `aux15 -> disable` is the existing `1 kΩ` pull-up.
* PWM isolation is the existing `1 kΩ` series resistor and `10 kΩ` pull-down.

The vendor interface adds the model's split outputs: `OUTH -> 10 Ω -> gate`
and `OUTL -> 10 Ω -> gate`, with the `10 kΩ` gate-to-ground pull-down and
`12 nF` gate load. The normal-tracked surrogate has its own output abstraction;
the two circuits therefore have different internal drive behavior even when
their external gate waveform is similar.

The run is staged as follows: PWM is asserted at 1 µs, toggled low from 5–8 µs,
and asserted again; RUN is disabled at 12 µs while AUX is healthy, then
re-enabled at 15 µs. AUX is dropped at 20 µs while the gate is active, RUN is
lowered at 24 µs while AUX is absent, AUX is restored at 27 µs while disarmed,
and RUN is asserted again at 30 µs. The scalar and full-trace checks require a
default-off gate, sustained greater-than-14 V enabled plateaus, independent PWM
and RUN disable, AUX collapse while active, no AUX-return restart while
disarmed, and a fresh restart after RUN is asserted.
The checker also rejects non-finite values, malformed rows, non-monotonic time,
missing windows, time gaps above 1 ns, and a trace that does not end exactly at
35 µs (within 2 ps). Falling-crossing delays from the AUX collapse to
`OUTL=13.5 V` and gate `4 V` are measured directly from the full trace and
must each be positive and below 1 µs.

Measured with ngspice 45.2 on 2026-09-20:

* default-off maximum gate: `1.53e-10 V`;
* PWM-enabled minimum gate: `14.97333 V`; PWM-disabled maximum: `4.69 mV`;
* RUN-disabled maximum after settling: `8.72 mV`;
* AUX-active minimum gate before collapse: `14.98442 V`;
* AUX-drop maximum after settling: `1.38 mV`, AUX-return while disarmed:
  `5.33 µV`;
* AUX collapse to `OUTL=13.5 V`: `11.1 ns`; AUX collapse to gate `4 V`:
  `90.9 ns`;
* re-armed minimum gate: `14.98442 V`.

This fixture drives the small-gate path directly from the `run` source to
exercise the driver. In the complete design that source is the qualified,
latched `enable_good` signal; this fixture does not replace that latch, test
fast-drop qualification while RUN stays high, or prove no-restart behavior for
every controller state.

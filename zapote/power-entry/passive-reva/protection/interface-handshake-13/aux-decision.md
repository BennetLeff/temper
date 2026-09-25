# AUX protection decision — blocked at the dynamic boundary

No cutoff or clamp is accepted for circuit integration in this round. Stopping
switching does not protect the UCC27511A supply pin from an AUX overvoltage.
The design target remains below its 18 V recommended maximum.

## TPS26601 review

Luna rechecked the proposed downstream cutoff against the conditional A5 load.
Parent arithmetic remains executable in `../command-protocol-12/aux_budget.rs`.
With a 130 kΩ / 10 kΩ divider, ±1% **total** resistance error and ±100 nA OVP
pin leakage, the static trip range is 16.065942–17.484847 V. At 15.75 V the
worst-case OVP pin voltage is 1.147010 V, 22.990 mV below the minimum threshold.
These are static numbers, not a bound on the protected output peak.

The datasheet's 6 µs OVP-to-FLT timing is not a guaranteed OVP-to-FET-off time.
Its typical/max column assignment was not established by the extracted table;
no timing guarantee is inferred from that figure. The 120 kΩ ILIM setting has
an 85 mA minimum active limit and 45 mA minimum breaker threshold, below the
conditional downstream load of 111.630037 mA (75 mA direct plus a 5 V / 75 mA
buck load at assumed 70% efficiency and 14.625 V input). New isolation and
startup current are additional, unbounded loads. A 56 kΩ setting remains
unselected; a nominal limit is insufficient. Factory UVLO can require 15.75 V
at startup, above the producer's 14.625 V static minimum; external UVLO is needed.

Primary source: [TI TPS2660 Rev G](https://www.ti.com/lit/ds/symlink/tps2660.pdf).

## A relevant alternative, screened but not selected

[ADI LT4363 Rev C](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf)
regulates an external MOSFET to an adjustable output ceiling. Its -1 variant
latches off after the fault timer expires. The specified FB servo range is
1.25–1.30 V with ±1 µA input current. A conditional 60.4 kΩ / 4.99 kΩ,
±1% total-error divider gives 16.020855–17.414363 V; see
`aux-clamp-screen.rs` and its CSV. This leaves only 0.585637 V for dynamic
excursion at the upper corner. The datasheet requires gate compensation and
MOSFET SOA analysis against the input transient. Neither the source waveform,
MOSFET, compensation nor downstream effective capacitance is established here.
This is a more relevant architecture than TPS26602's fixed 36–40 V clamp,
but the static screen does not establish protection below 18 V.

## Exact acceptance inputs

For the proposed cutoff, require a demonstrated worst-case inequality:

`Vbefore,max + Qnet,max / Cdownstream,min + Vparasitic,max < 18 V`

`Qnet,max` is the positive net charge delivered after the fault starts through
actual interruption, accounting for the source, path, FET behavior, and load.
At 15.75 V with zero parasitic allowance, the budget is 2.25 µC per effective
µF. Those are hypothetical capacitances, not installed capacitor guarantees.
The existing A5 47 µF LDO output capacitor is upstream of a new downstream
cutoff and cannot be counted as protected-output capacitance.

| Missing input | Required evidence / responsibility |
| --- | --- |
| Failed-LDO source | Supply design: max voltage, source impedance/current, rise rate and duration for normal raw input and specified input faults |
| Charge through cutoff | Protection design: guaranteed switching envelope or bounded application evidence including selected device and source |
| Effective output C | Exact downstream capacitor BOM, tolerance, DC-bias/temperature/aging minimum, placement |
| Peak parasitic voltage | Circuit/layout parasitics and bounded transient model, then hardware check |
| Load/startup/thermal | Full simultaneous steady/startup loads, guaranteed ILIM range, UVLO tolerances and thermal limits |
| Restart interaction | Rail-fault latch and command-session reset wiring; recovered power must not replay a start |

The LT4363 alternative requires an equivalent peak bound plus external MOSFET
SOA and timer qualification. These inputs are engineering work, not a request
for permission. Repeating nominal simulations or changing the part count
cannot supply the absent limits. No new physical parts, firmware, or PCB were
adopted on the strength of this screen.

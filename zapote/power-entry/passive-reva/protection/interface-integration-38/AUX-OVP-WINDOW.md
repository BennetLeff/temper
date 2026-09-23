# Rev38 TPS26601 AUX cutoff window

Status: **static divider screen only; protected AUX selection OPEN**. This
checks the proposed TPS26601RHFT after the TPS7A4701 15 V regulator. It does
not bound a regulator pass-through transient, the eFuse output peak, or the
driver voltage. The historical supply and Rev38 loads have not been joined.

The current Rev38 rail contract is 14.25–15.75 V during normal operation. The
18.0 V value below is the prior *screen* for a proposed driver supply limit,
not a qualified maximum or a substitute for the applicable part ratings.
For the eFuse to recover from OVP at any normal rail voltage, its **lowest**
falling input threshold must exceed 15.75 V. For it to cut off before the
screen under a slow ramp, its **highest** rising input threshold must be below
18.0 V. Both conditions are necessary, and neither guarantees the output
peak during a fast fault.

Let `q = Rtop/Rbottom`, and let each resistor independently vary by `±t`.
TI specifies 1.085 V minimum OVP falling threshold, 1.225 V maximum rising
threshold, and ±100 nA OVP input leakage. Ignoring leakage initially, the
two necessary inequalities are:

```text
15.75 < 1.085 × (1 + q × (1 − t)/(1 + t))   [worst recovery]
1.225 × (1 + q × (1 + t)/(1 − t)) < 18.0     [worst trip]

q > (15.75/1.085 − 1) × (1 + t)/(1 − t)
q < (18.0/1.225 − 1) × (1 − t)/(1 + t)
```

| Independent resistor tolerance | Minimum `q` for recovery | Maximum `q` for trip | Result |
| --- | ---: | ---: | --- |
| ±1% | 13.789182 | 13.422712 | **No possible divider**, even before leakage or transients |
| ±0.1% | 13.543188 | 13.666517 | Static window exists, but has little headroom |

For the earlier preliminary 130 kΩ/10 kΩ ±1% divider (`q=13`), the minimum
falling input threshold is **14.91069 V** before leakage. After an OVP event,
a healthy 15.75 V rail can therefore remain cut off. Its maximum rising
threshold is **17.47172 V** before leakage. Those numbers show why the
preliminary trip calculation alone was insufficient.

A 136 kΩ/10 kΩ ±0.1% divider (`q=13.6`) is an illustrative static candidate,
**not an adopted selection**. It gives 15.81152 V minimum recovery and
17.91835 V maximum trip before leakage. For leakage `I` defined as current
entering the OVP pin, the input threshold is
`Vthreshold × (1 + Rtop/Rbottom) + I × Rtop`. Applying ±100 nA at the adverse
resistor endpoints gives approximately **15.79793 V** minimum recovery and
**17.93197 V** maximum trip. That leaves only 47.93 mV over normal high and
68.03 mV under the 18.0 V screen. These are algebraic input thresholds; they
do not include extra leakage from board contamination or attached circuits.

TI describes TPS26601 MODE-open latch behavior for **overload**. The OVP
function cuts off and resumes on its own falling threshold; the overload
latch must not be treated as an OVP latch. The datasheet's OVP timing entry
is measured from an OVP-pin excursion to **FLT** assertion. It does not bound
the output peak after a regulator failure or the charge already on downstream
capacitors. The Rev38 AUX OV detector has a separate nominal 16.5 V threshold;
its corner, capture, and shutdown path have not been qualified against this
cutoff or its recovery.

The eFuse's **default UVLO is also unsuitable as an assumed startup setting**.
With UVLO connected to RTN, TI specifies a 14.25–15.75 V rising input
threshold. The historical TPS7A4701 15 V setting has a 14.625 V minimum
static output, and the wider AUX operating window extends down to 14.25 V.
At those valid source voltages, a TPS26601 at its high UVLO corner need not
turn on. An external UVLO divider must be selected and checked against the
actual protected-rail run and trip windows, startup ramp, leakage, and
the HOT rail detectors. Tying the UVLO pin to RTN is not a valid joined
candidate default.

**Decision:** do not join the 130 kΩ/10 kΩ part or label TPS26601 a qualified
protected-AUX source. The ±1% static window is impossible under the present
15.75/18.0 V screens. The illustrative ±0.1% window is too small to claim a
fast-fault bound without source impedance, regulator pass-through waveform,
downstream effective capacitance/ESL, eFuse disconnect behavior, and the
actual load/startup budget. Supply design must either establish a different
qualified protection approach or demonstrate the complete static, dynamic,
restart, and thermal margins for a selected part and passive set. A wider
accepted supply ceiling would need its own device and system derivation; it
cannot be inferred from this divider exercise.

Sources: [TI TPS2660x datasheet, pin functions and §§7.5–7.6, 9.3–9.4](https://www.ti.com/lit/ds/symlink/tps2660.pdf),
[earlier supply selection review](../../../../../docs/evidence/2026-09-22-power-entry-selection-review/supplies.md).

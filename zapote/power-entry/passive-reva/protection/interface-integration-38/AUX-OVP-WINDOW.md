# Rev38 TPS26601 AUX cutoff window

Status: **static divider screen only; protected AUX selection OPEN**. This
checks the proposed TPS26601RHFT after the TPS7A4701 15 V regulator. It does
not bound a regulator pass-through transient, the eFuse output peak, or the
driver voltage. The historical supply and Rev38 loads have not been joined.
The separate [direct 15 V source evaluation](AUX-SOURCE-CANDIDATE.md)
considers IRM-20-15 in place of the historical IRM-10-24/LDO; it likewise
does not establish a protected producer or a safe output peak.

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

The allowable resistor variation is much smaller than “0.1% parts” might
suggest. Solving the two inequalities above for their common boundary gives
**0.32663% maximum independent deviation of each resistor from nominal**,
even before pin leakage, board leakage, aging, or voltage transient margin.
At a 125 °C resistor temperature, a 25 °C reference and a specified
±25 ppm/K TCR permit another ±0.25% per resistor. Added to ±0.1% initial
tolerance, that is ±0.35%. The necessary ratio interval then closes:
`q > 13.61107` for recovery but `q < 13.59835` for trip. For example,
[Vishay TNPW e3](https://www.vishay.com/docs/28758/tnpw_e3.pdf) offers
±0.1% and ±25 ppm/K 0603 variants, but that combination cannot establish
this full-temperature static window if the two TCR errors oppose. Its
load-life resistance drift also needs an explicit ratio/lifetime budget.
This does not reject every precision divider: a specified matched-ratio
network or sufficiently tighter individual TCR and drift limits could be
evaluated. It rejects selecting a pair on initial tolerance alone.

## TPS2663x alternative: static range exists, with little system margin

The [TPS2663x cutoff variants](https://www.ti.com/lit/ds/symlink/tps2663.pdf)
have a wider guaranteed OVP hysteresis window: 1.090 V minimum falling,
1.224 V maximum rising, and ±150 nA OVP-pin leakage. These figures apply to
TPS26630/TPS26631 adjustable **cutoff**, not the clamp variants. The same
15.75/18.0 V screens give an independent-resistor deviation limit of about
0.472% before leakage. Their factory UVLO still rises as high as 15.9 V and
would have the same valid-source startup problem; it cannot be selected by
grounding UVLO. TI permits tying UVLO to IN_SYS when the function is not
needed. That is only a candidate because the separate AUX window would then
own the low-rail response.

[Vishay TNPU e3](https://www.vishay.com/docs/28779/tnpue3.pdf) lists
16.7 kΩ and 1.23 kΩ within its E192, ±0.02%, ±2 ppm/K range. Its rated-power
resistance-change limit is ±0.3% at 225,000 h. Treating initial tolerance,
100 K from a 25 °C reference, and that full drift as independent adverse
terms gives `t = 0.0002 + 0.0002 + 0.0030 = 0.0034` per resistor. For this
illustrative divider, `q = 16.7/1.23 = 13.57723577`. Including the adverse
±150 nA OVP input leakage and ±t resistor endpoints gives:

```text
minimum falling input = 1.090 × (1 + q × (1−t)/(1+t)) − 150 nA × 16.7 kΩ × (1+t)
                      = 15.78638 V  (36.38 mV above 15.75 V)
maximum rising input = 1.224 × (1 + q × (1+t)/(1−t)) + 150 nA × 16.7 kΩ × (1+t)
                     = 17.95844 V  (41.56 mV below 18.0 V)
```

This shows **algebraic feasibility only**. The 18.0 V upper figure is still
provisional; neither 36 mV nor 42 mV can be spent without a board-leakage,
regulator-ripple, common-mode, transient, and threshold-to-output budget.
The top resistor dissipates about 64 mW if a failed LDO passes 35 V, so its
footprint and film temperature need a fault/ambient calculation. The eFuse's
minimum programmed current limit is 0.54 A at its 30 kΩ example, above the
[IRM-10-24](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF)'s
nominal 0.42 A output rating; it cannot be credited as a
0.42 A source-overload protector without a separate source and conductor
analysis. No orderable resistor pair or eFuse is selected, and this screen
does not qualify fast-fault output peak, startup, recovery, or lifetime.

## LTC4368 controller alternative: wider static window, external FET work

The [ADI LTC4368 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf)
specifies 2.5–60 V operation, a full-temperature OV rising threshold of
492.5–507.5 mV, 20–32 mV OV hysteresis, and ±10 nA OV leakage at its stated
test condition. Its UV and OV inputs are independently set. Its 60 V
operating ceiling includes the historical supply's *assumed* 35 V raw
pass-through contract. It controls external back-to-back MOSFETs and a
current-sense path; those parts and their fault/thermal behavior are not in
Rev38.

For a **mathematical-only** 339 kΩ/10 kΩ OV divider, let each resistance
have independently adverse fractional deviation `t = 0.0034`. This matches
the earlier illustrative precision-film budget of ±0.02% initial,
±2 ppm/K over 100 K, and ±0.30% life drift; it is not a selected pair.
Treating the minimum falling threshold as `492.5 − 32 = 460.5 mV` and
using adverse ±10 nA pin leakage gives:

```text
minimum OV recovery = 0.4605 × [1 + 33.9 × (1−t)/(1+t)]
                      − 10 nA × 339 kΩ × (1+t) = 15.9623 V
maximum OV trip     = 0.5075 × [1 + 33.9 × (1+t)/(1−t)]
                      + 10 nA × 339 kΩ × (1+t) = 17.8325 V
```

The static headroom is 212 mV above the 15.75 V normal-high screen and
167 mV below the provisional 18.0 V limit. Those margins still may be too
small for a fast LDO pass-through event. ADI specifies up to 6 µs for fast
GATE turn-off with its 2.2 nF test load, plus the FET's own turn-off and
downstream stored charge. The 1–2 µs OV-to-FAULT entry has a 50 mV
overdrive fixture and is not an output-peak limit. The circuit needs an
actual input slew/source-impedance envelope, selected FET gate charge and
SOA, sense resistor and short-circuit behavior, output effective C/ESL,
startup/recovery analysis, and measured peak at the UCC27624 VDD pin.
Until then LTC4368 is only a stronger **static** candidate, not a protected
AUX source or a U4 PASS.

## TPS26601 behavior and decision

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
15.75/18.0 V screens. The illustrative ±0.1% window also needs specified
ratio tracking over temperature and life, and is too small to claim a
fast-fault bound without source impedance, regulator pass-through waveform,
downstream effective capacitance/ESL, eFuse disconnect behavior, and the
actual load/startup budget. Supply design must either establish a different
qualified protection approach or demonstrate the complete static, dynamic,
restart, and thermal margins for a selected part and passive set. A wider
accepted supply ceiling would need its own device and system derivation; it
cannot be inferred from this divider exercise.

Sources: [TI TPS2660x datasheet, pin functions and §§7.5–7.6, 9.3–9.4](https://www.ti.com/lit/ds/symlink/tps2660.pdf),
[earlier supply selection review](../../../../../docs/evidence/2026-09-22-power-entry-selection-review/supplies.md).

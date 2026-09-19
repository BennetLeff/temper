# F2-open diode-side transient assessment

This is a bounded calculation for the proposed feedback change: U20.1 senses
`BOOST_DIODE_POSITIVE`, while F2 separates that node from the 2240 uF bank.
It is not a controller qualification or a claim about an actual fault current.
The pre-ECO board and controller PDF are byte-bound in `raw/input-sha256.txt`.
The old board/schematic are retained at commit `a2536ee140c8bd368a4bb16a464e36620df2858f`;
those hashes identify the inputs, not the later feedback-ECO board. Component
values used here are unchanged by that ECO.
The stressed nodes are U9/U10 (650 V silicon), U40 `B32672P6474K000`
(`BOOST_DIODE_POSITIVE` to `PFC_BUS_MINUS`, the authored 630 VDC film part),
and U20--U25's divider. The 630 V capacitor rating is an authored part
property; a retained manufacturer curve for its pulse current/ESR is still
missing. Each 200 kOhm divider resistor sees about 78 V at 390 V; its pulse
and working-voltage rating is likewise not used as a qualification here.

## Circuit question

With F2 open, the bank is no longer the energy sink. The local diode-side
capacitor is U40, 470 nF, and the boost path still contains U8, 180 uH, U10
and U9. For a healthy U9 commanded off while an inductor current `I0` is
flowing, the ideal commutation model is:

```
L di/dt = Vin - Vc       C dVc/dt = i
Vpeak = Vin + sqrt((V0 - Vin)^2 + L/C * I0^2)
```

`Vin` is held at the rectified line value during the roughly 10 us event. This
includes line-source work (`Vin * C * (Vpeak-V0)`), rather than reporting only
`L I²/2`. The Rust program also checks the energy identity and the first
zero-current time. The CSV is reproducible with:

```sh
rustc -O f2_open.rs -o /tmp/f2_open
/tmp/f2_open > raw/immediate-off.csv
```

The [retained ngspice cross-check](../../evidence/f2-open-oracle-01/README.md)
checks the commutation equation with a synthetic diode; it is not controller
or hardware qualification. The same nominal current case gives 674.289 V,
versus the ideal 674.741 V. The small difference includes synthetic diode loss.

## Results

At the retained same-phase model input (`Vin=169.706 V`, `V0=389.615 V`,
`I0=23.2318 A`), with the nominal 180 uH inductance:

| case | immediate-off peak |
| --- | ---: |
| 470 nF | 674.7 V |
| 1.0 uF | 551.2 V |
| 1.5 uF | 506.0 V |

For a separate **assumed** sensitivity, set L=216 uH and C=90% of each
nominal value. The resulting peaks are 738.9 V, 591.5 V and 536.7 V for
470 nF, 1.0 uF and 1.5 uF respectively. This is not a tolerance bound: the
inductor's saturation and temperature curve and the capacitor tolerance are
not retained as qualified inputs. The retained power-entry model reports the
23.2318 A peak from its phase sweep. At the line crest, its fundamental RMS
14.9701337898 A gives mean current 21.1709662361 A; the calculated 4.1217441668 A
peak-to-peak ripple adds 2.0608720834 A. Thus the stated line voltage and
current coexist at the switching-ripple peak in that retained CCM model.
This establishes a consistent model case, not a measurement or a prediction
of when the fuse opens.

## Controller and restart implications

The retained TI UCC28180 datasheet (hash in the input manifest) specifies
`VOVP_H = 109% VREF` typical, PWM disabled until `VSENSE < 102% VREF`, and
standby/OLP below 0.82 V. With five 200 kOhm top resistors and 13 kOhm bottom,
the divider ratio is 13/1013. The typical OVP point is approximately 425 V and
the 107--111% threshold range combined with VREF=4.93--5.07 V at 25 °C gives
411--439 V. Using VREF=4.87--5.15 V over −40 to +125 °C instead gives
406--445 V. Both use the nominal divider ratio and exclude resistor tolerances.
The actual 680 pF VSENSE filter and nominal divider Thevenin resistance
(1 MΩ parallel 13 kΩ) also give an approximately 8.7 µs small-signal time
constant; neither this filtering nor comparator/gate delay is in the model.
The datasheet commands gate-off at the VSENSE threshold, but does not provide a
complete external fault-to-gate latency or an energy guarantee for this
topology.

For a **healthy** U9, the immediate-off calculation is the optimistic lower
latency case. Controller delay, gate discharge, and any subsequent restart
remain unknown. For a **failed-short** U9, no gate command interrupts the
path; this calculation does not qualify F2 clearing or semiconductor survival.
The local divider discharges the diode-side capacitor, potentially allowing
OVP reset and further switching; that no-load F2-open restart sequence is not
modeled. An independent latched
diode-side inhibit is a candidate option if the product requirement forbids
restart; no such requirement or part has been adopted.

## Decision

1. The result is a **conditional immediate-off screen**, not completed F2
   protection. Existing 470 nF exceeds the authored 630 VDC U40 rating in the
   retained model case; controller delay and parasitics are not included.
2. Compare 1.0 and 1.5 uF film candidates after sourcing their pulse/dv/dt,
   ESR, dimensions and availability data. This assessment does not select one
   or call either adequate.
3. Cold start, controller delay, and no-load restart are explicitly outside
   this model and remain open.

No CAD, BOM, common harness, or generic validator was changed by this
assessment.

## Fuse-location alternative

Relocating F2 into the U9 branch while reconnecting the bulk bank directly to
the boost-diode output would put the fuse in the internal bank-short path and
leave the full feedback capacitor attached. That is a real alternative, but
its high-frequency fuse inductance, pulsed RMS current and clearing curve are
unresolved. It is not a second-fuse claim or a CAD decision here.

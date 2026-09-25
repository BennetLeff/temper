# AUX active protection prototype — parent corrected

Use LT4363HMS-1#PBF (MSOP12 latch-off variant) and the FDB33N25 pass transistor
from ADI's application circuit as the reference prototype. This is a pin/value
design for evaluation, not a production BOM or compiled schematic. Raw below
means the existing regulated 15 V output, **not** the upstream 24 V module.

Normal design envelope is 14.625–15.75 V; protected output must be at least
14.25 V in normal operation and below 18 V during the specified fault. The
35 V fault ceiling, source impedance and rise time remain assumptions requiring
qualification. The 114.473684 mA load allocation is conditional and incomplete.

## Connections and initial values

`AUX_RAW → Q1 drain; Q1 source → SNS → R_SENSE → AUX_PROTECTED`

| LT4363 MSOP pin | Prototype connection |
| --- | --- |
| 1 FB | 59.0 kΩ from AUX_PROTECTED, 4.99 kΩ to HOT_GND; each ≤0.1% **total** error |
| 2 OUT | AUX_PROTECTED, Kelvin at load side of R_SENSE |
| 3 SNS | Q1 source, Kelvin at upstream side of R_SENSE |
| 4 GATE | 10 Ω to Q1 gate |
| 5 VCC | AUX_RAW, local 100 nF/50 V bypass to HOT_GND |
| 6 /SHDN | Normally open; local service contact/open-drain reset to HOT_GND |
| 7, 9 GND | HOT_GND; pin7 is GND on the -1 variant, not OV |
| 8 UV | 91.0 kΩ to AUX_RAW, 10.0 kΩ to HOT_GND, ≤1% total error |
| 10 /FLT, 11 ENOUT | Test points only in this prototype; no connection to existing reset net |
| 12 TMR | 100 nF ±10% effective to HOT_GND |

R_SENSE=0.22 Ω, ≤1% total error. Q1=FDB33N25, D2PAK; use the manufacturer's
terminal functions when capturing its symbol/footprint. No gate-source
pulldown is added: a 100 kΩ resistor would draw more than the charge pump's
minimum current at the intended gate voltage.

Follow LT4363 Figure 5: from the MOSFET-gate node, connect 100 Ω to node CG;
470 nF effective ±10%, rated at least 63 V, connects CG to HOT_GND. Place
1N4148W across the 100 Ω with **anode at gate and cathode at CG**. It allows
the capacitor to charge through the diode while isolating it through the
resistor during gate pull-down. Do not reverse it as a supposed fast-discharge
diode. These gate-network values require fault-step and stability validation;
the capacitor is not a substitute for a maximum propagation/charge bound.

Provide a nominal 47 µF/50 V downstream bulk capacitor plus local decoupling.
For this screen require **35–100 µF total effective downstream capacitance**,
including all buck/driver/controller input capacitors over bias, temperature,
tolerance and aging. These are acceptance limits for later exact capacitor
selection. The old LDO output capacitor is upstream and is excluded. Larger
actual capacitance requires recalculating the startup screen.

/SHDN resets AUX protection only. It is deliberately independent of command
permission, so the HOT decoder and reset circuitry can remain powered while
permission is low. Otherwise a HOT-powered latch could cut its own supply and
create a restart deadlock. For the 100 nF timer, use a service reset low interval
of at least 120 ms before releasing, covering the datasheet's 1 s/µF cooldown
interruption rule with the stated +10% capacitor limit. The shorter 100 µs
rule only applies once cooldown is complete. Verify release slew ≥10 V/ms and
the actual reset waveform; the internal pullup alone is not a measured slew.
Resetting AUX does not grant RUN or restore a previously valid session.

## Electrical screens

`corners.rs` produces all numbers in `results.csv`. Static clamp range is
**15.941089–16.760573 V**, using specified FB servo/input-current extrema and
the stated total resistor errors. That leaves 191 mV above normal maximum and
1.239 V below the driver limit. A nominal 0.1% resistor without a temperature/
aging allocation does not establish 0.1% total error; at 1% this divider fails
the normal-maximum screen. Static headroom is not output-peak protection.

The 12 V and 48 V current-sense table rows span 45–58 mV. Using that as a
**conditional application envelope** yields 202.520–266.299 mA. Its applicability
through 14.625–35 V must be established; it is not an interpolation guarantee.
The analogous short-circuit foldback screen is 67.507–165.289 mA (15–36 mV).
Never present 25 mV typical foldback as a maximum fault-current bound.

At the existing load plus OUT bias and divider allowance, the sense drop is
25.610 mV. Q1's 94 mΩ maximum datum at 10 V gate drive/25°C adds about 11 mV
at this current, leaving substantial room within the 375 mV path budget.
That resistance datum is not an all-temperature bound. VCC bias is drawn
upstream; OUT bias and divider are downstream and included in this screen.

Using 65 µA (largest specified gate-current test value), 100 µF downstream
and 423 nF gate-cap minimum gives a 15.366 mA capacitive ramp-current screen.
Adding the conditional operating load and support current gives 130.622 mA,
below 202.520 mA, with 71.899 mA left in this **screen**, not an accepted new
load budget. Below 3 V the minimum foldback current is smaller: prototype
startup must hold relay and PWM off and show total current below 67.507 mA
through that region. Buck startup, its capacitor charging and all additional
receiver loads need explicit measurements. Gate-current voltage dependence,
Miller effects and nonlinear loads limit the formula's applicability.

The 100 nF timer gives illustrative 10 VDS times of 11.354 ms in OV and
2.500 ms in OC using the datasheet's application examples. They are different
modes and **neither is a maximum shutdown time**. Gate-charge recovery before
timer start and pre-existing capacitor charge also count toward FET stress.
The prototype test must record from fault onset, not merely from /FLT.

## Pass-device screen and evidence limits

The worker's IRLR2908 proposal was replaced: its ±16 V absolute VGS rating
meets the LT4363's 16 V maximum gate-drive datum with no transient margin.
FDB33N25 has ±30 V VGS, 250 V VDS, and is used in ADI's reference application.
This choice favors a reviewable first prototype over package minimization.

At 35 V and the conditional 266.299 mA upper current, a conservative full
VDS/current rectangle is **9.320 W**. OV regulation alone screens at at most
5.075 W using the **minimum** clamp voltage. The larger rectangle covers
output charging/short phases after current regulation is established; initial
uncontrolled overshoot is additional and unbounded until measured.

Parent visually inspected onsemi Rev3 Figure9. At TC=25°C, the point
100 V/1 A lies below the plotted DC boundary; the proposed 35 V/0.267 A
regulated-fault point is lower on both axes. Thus the published room-temperature
graph provides a useful SOA screen even before choosing a particular millisecond
pulse. It does not qualify hot-case operation or a PCB's heat removal. Figure9
is published in the typical-characteristics section; do not convert the visual
screen into an unqualified production guarantee. The 0.53°C/W RθJC datum
requires actual case control and does not describe free-air/PCB temperature.
Fault duration, temperature, repeated events, source transients and initial
current overshoot remain part of the acceptance test.

At 35 µF, the 1.239 V static headroom stores only 43.380 µC of additional
charge. This is a budget after reaching the high clamp corner, not a guaranteed
delivered charge. LT4363's 1 µs OV delay datum uses FB=0→1.5 V and OUT=0;
it does not bound this nearly-threshold, loaded rail transient.

The pass MOSFET shorted drain-to-source bypasses protection. No single-fault
coverage is claimed for that fault. /FLT's weak sink also prevents connecting
it directly to the existing 10 kΩ/5 V reset net: 0.1 mA has an 0.8 V maximum
low datum, while the 2 mA datum permits 9 V. Existing local AUX-window sensing
continues to clear permission; /FLT is observational in this prototype.

Primary sources: [LT4363 Rev C](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf),
[onsemi FDB33N25 Rev3](https://www.onsemi.com/download/data-sheet/pdf/fdb33n25-d.pdf),
[IRLR2908](https://www.infineon.com/assets/row/public/documents/24/49/infineon-irlr2908-datasheet-en.pdf).
The saved onsemi PDF and rendered page5 are under ../sources/.

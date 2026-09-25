# A5 HOT15/5V supply candidate (corrected)

This is a standalone integration artifact for Temper/Zapote revision
`5dde29ab3e2f1223c2d33c129ced2cf647238307`. It does not edit the frozen
`f2-shutdown-04/source-07` source or claim a production qualification.

## Decision and boundary

Use **Mean Well IRM-10-24 -> TPS7A4701RGWR set to 15 V -> TPS54202DDCR set
to 5 V**. The 5 V converter is fed from the regulated `AUX15` output. It is
never connected to the IRM raw output: the TPS54202 recommended input limit
is 28 V, while the IRM-10-24 protection trigger range reaches 32.4 V.
`AUX15` is the only producer port that feeds the gate-driver VDD.

The IRM datasheet gives 24 V, 0.42 A, ±2.5% output tolerance and an OVP
*trigger range* of 27.6--32.4 V. That range is not a guaranteed transient
clamp. The integration contract therefore assumes **35 V maximum raw input**
for the LDO interface, with source overshoot still unbounded and requiring a
separate transient qualification. The TPS7A4701 has a 3--35 V recommended
input range and 36 V absolute maximum; operation at the 35 V contract edge
has only 1 V absolute-rating margin.

The LDO's 15 V setting has a published ±2.5% overall-accuracy bound, so the
static regulated range calculated from that bound is **14.625--15.375 V**
(15 V × 0.975/1.025). The wider 14.25--15.75 V `AUX15` run window remains
an interface requirement covering wiring, ripple and load transients; it is
not presented as a measured regulator result. No invented dropout or
transient measurement is used.

The IRM's nominal raw range from its tolerance is 23.4--24.6 V. The deck also
exercises 32.4 V (the upper OVP trigger value), 35 V (the assumed raw input
contract), and 15 V as a deliberate negative dropout case. A raw source above
35 V or an overshoot waveform is outside this candidate's evidence.

## Netlist and physical pin map

```text
IRM-10-24 +V  -> AUX_RAW (external AC branch protection is separate)
IRM-10-24 -V  -> HOT_GND / PFC_BUS_MINUS

AUX_RAW -> TPS7A4701 VIN pins 15,16
TPS7A4701 EN pin 13 -> AUX_RAW
TPS7A4701 OUT pins 1,20 -> AUX15
TPS7A4701 FB/SENSE pin 3 -> OUT
TPS7A4701 exposed pad EP pin 21 -> HOT_GND
TPS7A4701 NR pin 14 -> 1 uF -> HOT_GND

AUX15 -> TPS54202 VIN pin 3
TPS54202 GND pin 1 -> HOT_GND
TPS54202 SW pin 2 -> 15 uH -> LOGIC5
TPS54202 FB pin 4 <- 98.2 kOhm (LOGIC5 to FB), 13.3 kOhm (FB to HOT_GND)
TPS54202 EN pin 5 <- 820 kOhm (AUX15 to EN), 100 kOhm (EN to HOT_GND)
TPS54202 BOOT pin 6 -> 100 nF -> SW
```

The TPS7A4701 ANY-OUT setting for 15 V is `1.4 + 6.4 + 6.4 + 0.8 = 15.0 V`.
The **1.4 V is the device's internal base**, not a separate program pin; the
6.4 V, 6.4 V and 0.8 V program pins are tied to HOT_GND and the other program
pins are open. The **physical EP pin 21 is tied to HOT_GND**; this is a
separate package connection from signal GND pin 7.

The LDO input capacitor is 10 uF nominal. The LDO output candidate is 47 uF
nominal, with an explicit assembly requirement that its effective capacitance
after tolerance, DC-bias and temperature remain **at least 10 uF**. This is
the required effective output-capacitance condition, not a claim that all
47 uF remains effective. The buck input and output capacitors are 10 uF and
22 uF nominal respectively; their effective values must be checked against
the TPS54202 data sheet and layout.

The TPS54202 feedback reference used for the arithmetic is **0.596 V typical**
from its data sheet. `VOUT = 0.596 × (1 + 98.2 k / 13.3 k) = 4.997 V` nominal;
the 0.596 V figure is a typical reference, so 4.75--5.25 V remains the
interface acceptance window pending tolerance and load verification.

The EN divider has one 820 kOhm top resistor and one 100 kOhm bottom resistor.
At the minimum static `AUX15` value (14.625 V), the ideal EN voltage is
`14.625 × 100/(820+100) = 1.589 V`. With a conservative 1 uA EN bias
current sinking through the 89.13 kOhm Thevenin resistance, it remains
1.500 V, above the 1.28 V maximum rising threshold used by the source check.
At 15.375 V it is 1.671 V. There are no parallel 100 kOhm resistors.

## Load, current and thermal budget

The interface defines `AUX15` load as **75 mA maximum excluding the buck** and
`LOGIC5` load as **75 mA maximum**. For a conservative 0.7 buck efficiency,
the 5 V load draws at most `5 V × 0.075 A / (0.7 × 14.625 V) = 36.74 mA`
from the 15 V rail at its low corner. Including the 75 mA auxiliary load and
a 4 mA TPS7A4701 quiescent-current budget gives an LDO total budget of
**115.74 mA**. This is a design-budget calculation, not a measured load.

At 32.4 V raw and a 14.625 V low regulated output, the LDO dissipation screen
uses the correct separate quiescent term:
`(32.4 - 14.625) × 0.11174 + 32.4 × 0.004 = 2.116 W`. With a 40 °C
assumed local ambient and a conditional 125 °C junction target, the required
board-level `RthetaJA` is no greater than `(125-40)/2.116 = 40.2 °C/W`.
At the explicit 35 V raw contract edge the corresponding screen is 2.417 W
and 35.2 °C/W. These are conditional thermal screens only: package data,
copper area, airflow, and thermal characterization are not established by
this document and no board thermal qualification is claimed. The 40 °C inlet target does not establish a 40 °C local ambient; temperature rise inside the product remains unbounded.

## Source evidence and limits

- [Mean Well IRM-10 specification](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF): IRM-10-24 output, tolerance, efficiency and OVP trigger range.
- [TI TPS7A4700/TPS7A4701 data sheet](https://www.ti.com/lit/ds/symlink/tps7a47.pdf): input/absolute ratings, 15 V ANY-OUT table, pin map and accuracy.
- [TI TPS54202 data sheet](https://www.ti.com/lit/ds/symlink/tps54202.pdf): 4.5--28 V input, pin map, EN threshold and 0.596 V typical feedback reference.
- [TI UCC27511A data sheet](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf): retained driver VDD requirement (4.5--18 V recommended).

The OVP range above is a trigger specification; it is not a clamp waveform or
an allowed transient. The source's overshoot, startup, overload hiccup and AC
branch protection remain open qualification items. The LDO is the only
barrier between raw source and gate-driver VDD. The former auxiliary
overvoltage-monitor port was removed: shutdown alone cannot protect a driver
VDD fault, and an unqualified monitor would suggest a protection guarantee.
The host retains the existing dominant interlock/shutdown path and must
remove run permission when either regulated rail is outside its window.

## Evidence boundary and commands

`ngspice/supply_interface.cir` is a deliberately reduced-order screening
surrogate. It checks cold startup, nominal 24 V, the 32.4 V OVP-trigger point,
the 35 V interface maximum, a raw-collapse/recovery sequence, a 75 mA logic5
load step, and a 15 V input dropout negative control. It is not a vendor
transient model, a clamp proof, or a qualification of the IRM, TPS7A4701 or
TPS54202. It writes a tab-separated trace consumed by the Rust validator.

```text
ngspice -b ngspice/supply_interface.cir -o /tmp/a5-supply-ngspice.log
cargo test --manifest-path rail-contract/Cargo.toml
./run_supply.sh
```

The validator reads the generated trace itself. It fails closed for missing or
duplicate columns, non-finite values, non-monotonic or truncated time,
undervoltage while the declared state is `RUN`, and a missing source-part map
or required capacitor contract.

The behavioral voltage sources do not conserve input power through the regulator ports. This trace is a rail-state screen; input-current and thermal estimates are separate conditional arithmetic. It does not establish regulator transient response. The validator also rejects missing startup, gaps over 20 us, missing excitation/collapse/dropout witnesses, and a missing 75 mA load step.

Pinned offline Atopile 0.2.69 compiled the candidate and exported its resolved
component graph under `source-build/build/`. The wrapper is a module; all four
LDO NC pins have distinct unconnected nets, both input/output pins are joined
correctly, EP is grounded, and buck VIN is on AUX15. Generic passive identities
and stock footprints permit a connectivity build; they are not an exact sourced
BOM or package/layout qualification. The IRM is still the named external raw
producer port of this regulator module.

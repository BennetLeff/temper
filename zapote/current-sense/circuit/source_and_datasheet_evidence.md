# Source and datasheet evidence

## Legacy graph audit

The existing `elec/src/modules.ato::CurrentSensing` connects
`r_bias_top` from +3V3 to `i_sense.line`, `r_bias_bot` from `i_sense.line` to
`i_sense.reference`, and the 4.99 Ω burden from the same line to the same
reference. Thus the two 10 kΩ parts do not establish a 1.65 V source: the
burden is 2004 times lower resistance than either divider leg. Ignoring CT
winding resistance, the high bound is

```
Vline = 3.3 * (4.99 || 10,000) / (10,000 + (4.99 || 10,000))
      = 1.645 mV
```

The canonical pre-fix counterexample is retained at
`zapote/current-sense/evidence/legacy-bias-upper-bound.json`. The standalone
source removes that topology by putting the CT secondary and burden between
S1 and the separately bypassed VBIAS midpoint. This is an intentional source
change in the new proposal; the legacy cooker modules remain untouched.

## Coilcraft CST3015-100ED

Primary source: [Coilcraft CST3015 data sheet, document 1608-1](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf), revised 2025-09-08.

The table identifies CST3015-100ED as 1:100, 3.20 mH nominal secondary
inductance, 0.0001 Ω maximum primary DCR, 1.54 Ω maximum secondary DCR,
0.78 kHz to above 1 MHz frequency range, 638 V-µs secondary volt-time
product, 88 A sensed current, 1 Ω terminating resistance at the specified
1 V/100 A condition, and 5000 Vrms one-minute winding isolation. The notes
state that sensed current is the 40 °C rise point at 25 °C ambient, not an
absolute continuous-current guarantee. The standalone envelope therefore
uses 20–100 kHz as a source requirement and 0–88 A as an analytical limit,
with CT thermal/saturation characterization still open.

At 47 kHz and 88 A peak with 1.50 Ω burden, the ideal secondary square-wave
half-cycle volt-time upper bound is approximately
`(88/100*1.50)*(1/(2*47 kHz)) = 14.0 V-µs`, far below 638 V-µs. This is a
topology check, not a full transient/saturation proof.

## TI TLV3201AIDBVR

Primary source: [TI TLV3201/TLV3202 data sheet SBOS561C](https://www.ti.com/lit/ds/symlink/tlv3201.pdf), revised 2024-05.

The DBV SOT-23-5 top view and pin table give OUT=1, GND=2, IN+=3, IN−=4,
VCC=5. The device is specified from 2.7 V to 5.5 V, with input common-mode
range VEE−0.2 V to VCC+0.2 V. Switching characteristics specify 55 ns maximum
low-to-high and high-to-low propagation over −40 °C to 125 °C at the stated
test conditions (2.7/5 V supply, 20 mV overdrive, and 15 pF load); 40 ns is a
typical feature value. This supports using two comparators at the 3.3 V biased
node, but does not prove the complete `<1 us` host latch path.

## Panasonic threshold parts

Primary source: [Panasonic ERA3AEB3741V product page](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA3AEB3741V).

The page identifies ERA3AEB3741V as 3.740 kΩ, 0.1%, ±25 ppm/K, 0.100 W,
0603. The source uses the same Panasonic family for the thresholds and
[`ERA3AEB102V`](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA3AEB102V)
1 kΩ, 0.1%, ±25 ppm/K, 0.100 W, 0603 parts for the bias divider. Exact
distributor availability and final placement remain a coordinator BOM check.

## TI CD74HC4075M96 output OR

The previous donor MPN `SN74HC4075DR` is not retained as an orderable
identity. TI lists [CD74HC4075M96](https://www.ti.com/product/CD74HC4075/part-details/CD74HC4075M96)
as active, 14-pin SOIC (D package), with three independent 3-input positive
logic OR gates. TI's [CD74HC4075 data sheet](https://www.ti.com/lit/gpn/CD74HC4075)
maps 1A=pin 1, 1B=2, 1C=5, 1Y=6, GND=7, 2C=8, 2Y=9, 3Y=10, 3A=11,
3B=12, 3C=13, and VCC=14; the source uses the existing donor symbol names
`A1/B1/C1/Y1`, which map to the same physical pins. The SOIC body is
8.70 x 3.90 mm, matching the donor `Package_SO:SOIC-14_3.9x8.7mm_P1.27mm`
footprint.

The device operates from 2–6 V, so the 3.135–3.465 V host rail is inside its
operating range. Its data-sheet propagation characterization is given at 2,
4.5, and 6 V with a 50 pF load (and an 8 ns typical point at 5 V/15 pF), not
as a guaranteed 3.3 V maximum. The current-sense Rust model is unchanged by
this drop-in logic MPN because it models trip thresholds only; complete timing
remains **INDETERMINATE** until the actual 3.3 V comparator/OR/latch load is
measured.

## Bias/filter capacitor and leakage bounds

The source uses Murata `GRM31C5C1H104JA01L`, a 0.1 µF, 50 V, C0G part in
1206, for both the burden filter and the bias midpoint bypass. The reviewed
Murata data sheet is [GRM31C5C1H104JA01L](https://search.murata.co.jp/Ceramy/image/img/A01X/G101/ENG/GRM31C5C1H104JA01-01A.pdf).
The earlier 0603 `GRM1885C1H104JA01D` suggestion is not retained because an
exact source was not established.

The bias divider is 1 kΩ/1 kΩ, so its Thevenin resistance is 500 Ω. For the
25 °C analytical corner, the two BAT54H clamps contribute a conservative 4 µA
total reverse-leakage bound. The model applies clamp leakage, host monitor
load, and SENSE_MON comparator input current through the 500 Ω bias Thevenin
resistance and the 1 kΩ + burden source path. The reported host-load drop is
0.35 µA × (500 Ω + 1 kΩ + 1.50 Ω) = 0.000525525 V; it includes the bias
Thevenin leg, not only the series path; clamp leakage alone can move the
midpoint by up to 2 mV. The model also includes ±5 nA per TLV3201 input and
±10 nA combined at SENSE_MON. TI specifies the
5 nA maximum over −40 °C to 125 °C at VCM=VCC/2 in the same [TLV3201 data
sheet](https://www.ti.com/lit/ds/symlink/tlv3201.pdf). Nexperia's leakage data
is a 25 °C condition; no hot-enclosure claim is made until a
temperature-qualified leakage value is supplied. TI specifies 4 mV maximum
TLV3201 VOS over temperature at VCM=VCC/2; the model adds a 1.2 mV CMRR
contribution from the 56 dB minimum to cover the non-midpoint waveform. That
combined offset is conditional at 3.3 V and requires validation at the actual
common-mode trajectory; comparator hysteresis is not treated as a guaranteed
maximum.

## Isolation and physical connection

Coilcraft's 5000 Vrms and ≥8 mm winding creepage/clearance figures do not by
themselves establish the whole-cooker PD3 12.6 mm reinforced barrier. The
source selects `temper:CST3015_Datasheet2025`, the corrected local footprint
reviewed against the official drawing. Native readback records primary pads
at x=±5.58 mm, y=-11.55 mm (4.8 x 9.0 mm) and secondary pads at x=±6.88 mm,
y=13.75 mm (3.0 x 4.6 mm), an 18.5 mm copper edge gap between rows. This
supports the footprint geometry, but does not prove a routed board. Physical
isolation therefore remains **INDETERMINATE** until the completed routed
barrier, slot, solder-mask exclusions, wire lands, and enclosure are measured
against the 12.6 mm PD3 requirement. The primary series conductor, terminal,
copper cross-section, and any slot/barrier construction remain unqualified
and are owned by the coordinator.

## Model scope

`current_sense_model.rs` is the sole numerical rule implementation in this
deliverable. `model_output.json` is a replay from that Rust source. It checks
both polarities, divider/burden corners, the bounded 25 °C clamp leakage,
10 MΩ host load, comparator input loading, the 1% input-series-resistor corner,
VOS and CMRR error, the 45–55 A trip window, and the nominal 0.33–2.97 V monitor envelope at 88 A. The
resulting conditional bounded DC corner band is 46.175–54.157 A. It does not
promote model output to a physical PASS; the overall 45–55 A requirement
remains **INDETERMINATE** because CT ratio/magnetizing-current/frequency
behavior, hysteresis, and unspecified component tolerances are outside the
model. It
does not model a faulted open, comparator delay distribution, clamp pulse,
winding saturation, or board parasitics.

## Nexperia BAT54H,115

Primary sources: [Nexperia BAT54H data sheet](https://assets.nexperia.com/documents/data-sheet/BAT54H.pdf) and [Nexperia product page](https://www.nexperia.com/product/BAT54H).

BAT54H is a two-lead SOD123F Schottky clamp diode. The source assigns the
`Diode_SMD:D_SOD-123F` footprint. The data sheet gives 30 V
reverse voltage, 200 mA forward current, 300 mA repetitive peak current, and
600 mA non-repetitive peak current for the stated short-pulse condition. The
source uses a 1 kΩ input resistor so these figures are not treated as an
unbounded surge guarantee; the actual clamp pulse remains untested.

## Host and bypass components

The low-voltage host boundary reuses the existing source component
`JST_XH_B4B_XH_A` / `B4B-XH-A(LF)(SN)`, already verified in the donor source as
a 2.50 mm four-position through-hole header. Each comparator and the OR gate
receives its own 100 nF `C0603C104K5RACTU` bypass, the same active KEMET part
used by the existing design. The source uses the active CD74HC4075M96
triple 3-input OR because it is already available in `elec/src`; unused channels
are tied to GND explicitly, and a smaller OR can replace it only after a
separate footprint/BOM review. The primary boundary is a single two-pad
`PrimaryWireLands` source component using `lib:LitzPad_15A`, marked
`NON_PURCHASED_BARE_LANDS`; it is a wire/busbar solder interface, not a
purchased connector or an ampacity certificate. Root must qualify the actual
conductor, solder joint, terminal construction, and thermal rise.

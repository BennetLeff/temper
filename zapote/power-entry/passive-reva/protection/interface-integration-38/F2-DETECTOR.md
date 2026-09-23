# Rev38 VD/VB fault producer candidate

Status: **compiled four-channel detector and trip join; electrical and
physical response acceptance OPEN**. This module detects an intended window
between local VD and bank VB. It does not sense the fuse mechanically, prove
that F2 has opened, or interrupt stored capacitor energy.

`f2_detector.ato` carries the two Rev35 high-voltage divider shapes into
Rev38. Each has four 200 kΩ and one 187 kΩ 1206 resistors in series above a
200 Ω step and 5.62 kΩ bottom resistor, with 47 pF from the high tap to
HOT0. The two [TLV3202 push-pull dual comparators](https://www.ti.com/lit/ds/symlink/tlv3202.pdf)
share a [2.5 V LM4040 reference](https://www.ti.com/lit/ds/symlink/lm4040.pdf)
bias from HOT logic5. Eight 22 kΩ input resistors separate the divider and
reference nodes from comparator pins. Four intended healthy-high outputs
enter one [SN74HCS21](https://www.ti.com/lit/ds/symlink/sn74hcs21.pdf):

| Channel | Positive input | Negative input | Low-output hypothesis |
| --- | --- | --- | --- |
| VD absolute OV | REF25 | VD high tap | VD above its reference crossing |
| VD/VB relative window | VD high tap | VB low tap | VD too low relative to VB |
| VB absolute OV | REF25 | VB high tap | VB above its reference crossing |
| VB/VD relative window | VB high tap | VD low tap | VB too low relative to VD |

The first AND output combines the four VD/VB channels. Its second gate
requires the separate [AUX window](AUX-WINDOW.md) output high; a 10 kΩ local
pull-down holds that input low if the producer is absent. The second AND
output `HOT_FAULT_N` joins AVR PC2/8 and the retained
`HOT_PREP_TRIP_OK` fan-in; a receiver-local 10 kΩ resistor holds it low when
the detector output is missing. A qualified low therefore clears the HOT
session and RUN through the existing hardware path and enters preparation
abort memory. A rising comparator output after recovery cannot set those
memories. The standalone and joined netlists pass exact part/pin checks and
negative divider, comparator, AUX-window, summary-output, rail and trip-join
mutations.

The trip points are **not accepted**. The actual VD/VB allowed ranges,
divider tolerance and voltage rating per resistor, LM4040 current and startup,
TLV3202 input offset/hysteresis and common-mode range, filter rise/fall delay,
22 kΩ input injection during HOT logic5 loss, output pulse minimum, HCS21
thresholds and propagation, retained-clear minimum, loaded gate turnoff and
switch-current cessation all require corner analysis or physical evidence.
Rev35's values were candidate inputs, not transferable Rev38 limits. The
local 47 pF and reference 100 nF values are selected for this candidate but
their transient behavior is unproven. `TBD_REVIEW_ONLY` footprint keys avoid
Atopile 0.2.69's same-footprint MPN collision and require native package and
creepage review before placement. The VD/VB ports now join the separate
[PFC power candidate](PFC-POWER.md): VD to the boost diode and local film
reservoir, VB to the bank beyond F2. The AC input, fault timing and physical
F2 behavior remain unqualified.

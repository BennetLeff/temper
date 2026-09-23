# Rev38 HOT rail-health candidate

Status: **compiled pin topology; threshold, power-order and response acceptance OPEN**.
The two [TPS3890 adjustable supervisors](https://www.ti.com/lit/ds/symlink/tps3890.pdf)
monitor HOT logic5 and protected driver AUX from HOT logic5 power. Their
open-drain RESET_N pins share `HOT_RAILS_OK`, a 10 kΩ pull-up to HOT logic5,
and the receiver's 100 kΩ local low default. The shared node enters the
retained preparation-trip fan-in. Nominal high with a 5.0 V source and ideal
resistors is 5 × 100/(10 + 100) = 4.545 V; a valid digital high at all
corners has not been established. The receiver's old 10 kΩ low default was
changed because it would form a nominal half-supply divider.

| Monitor | Supply / sensed rail | Divider and series element | Nominal falling input rail threshold | CT |
| --- | --- | --- | --- | --- |
| `sup_logic` | HOT logic5 / HOT logic5 | 294 kΩ top, 100 kΩ bottom, 47 kΩ to SENSE | 1.15 × (1 + 294/100) = 4.531 V | 100 pF C0G |
| `sup_aux` | HOT logic5 / AUX_PROTECTED | 1.02 MΩ top, 100 kΩ bottom, 47 kΩ to SENSE | 1.15 × (1 + 1020/100) = 12.88 V | 100 pF C0G |

The 1.02 MΩ AUX part is a selected Rev38 candidate in place of the
unselected 1.03 MΩ Rev35 value. Both MR pins are tied high; each supervisor
has its own 100 nF supply bypass. These are undervoltage detectors. They do
not detect AUX overvoltage or a dip too brief for their sensing/filter path.
The 47 kΩ SENSE series resistors may add error from input current and
back-drive; their effect needs the complete corner calculation.

An illustrative static threshold calculation using the data sheet's 1.15 V
threshold, ±1% threshold accuracy, the selected ±1% resistors, and an
assumed bidirectional ±100 nA SENSE current gives 4.372–4.694 V for logic5
and 12.369–13.405 V for AUX. The calculation is
`Vrail = Vth × (1 + Rtop/Rbottom) + Isense × (Rtop + 47k × (1 + Rtop/Rbottom))`.
These are **screening numbers**, not accepted thresholds: verify the exact
TPS389001 option's full-temperature specifications and current direction,
divider loading, tolerance/aging, supply dependence, and the permitted HOT
logic5/AUX operating envelopes. A 4.694 V upper logic5 trip corner could
leave little margin at a low logic rail, depending on its actual requirement.

The supervisors need a valid HOT logic5 supply before their outputs have
specified control. Their RESET outputs cannot alone prove default-off when
AUX powers UCC27624 while HOT logic5 ramps or collapses. Prove the ENA shunt
and its release logic over that interval, including leakage, LVC1G06 output
state, PMBT3904 base bias and saturation, and UCC27624 EN input behavior.
Also establish TPS3890 CT and propagation extrema for rail slew, brownout,
and pulsed faults; an open-drain RESET low pulse must be long enough to clear
the retained memory at its physical pin. The 100 pF CT value is not a
response-time approval.

The `hot_rails` and `integrated` Atopile targets compile. `audit.rs` checks
part identity, both sense dividers, open-drain sharing, power/ground, the
AUX-to-driver and RESET-to-trip joins, and mutations that break those paths.
This is connectivity evidence only. No native footprint, rail waveform,
fault capture, or loaded switch-current result has been approved.

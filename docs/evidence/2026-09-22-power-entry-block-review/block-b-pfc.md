# PFC power stage and controller: block B

Luna research handback, reviewed and condensed by the parent on 2026-09-22.
Twenty-one compiled instances; see [component ownership](component-ownership.json).
Review only; no current, loss, stability or hardware acceptance.

## Contract

Block A provides rectified power. Block E provides HOT AUX15. Block B drives
PWM into D; D returns the physical MOS gate drive and controls the VSENSE
standby clamp. B delivers diode-side VD to the external F2/local reservoir
boundary owned by C. The bank is VB, a separate node.

B owns the choke, MOSFET, dual-die boost diode, shunt, UCC28180, current-sense
filter/clamp, frequency resistor, feedback divider and compensation.
[Current source](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/source-candidate/elec/src/power_entry_pfc_control_candidate.ato),
especially lines 384–394 and 436–468.

## Findings

UCC28180 provides regulation, current limiting, overvoltage response and
standby control. Those functions do not establish bank-voltage observation
when VSENSE measures VD, nor fuse clearing or failed-short MOS interruption.
[TI datasheet](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).
Keep independent VB observation in the candidate.

The BAV23C clamp topology is corrected, but its selected part remains
provisional. Existing hot assumed-model loading failures cannot establish a
real diode failure, and another nominal sweep cannot supply missing
guaranteed low-current/temperature behavior.
[Clamp evidence](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/clamp-evidence.md).

The 16.2 kohm frequency resistor is explicitly bound to approximately 129 kHz
in the authored model. It is not a discovered arithmetic mismatch. Frequency
tolerance, compensation and the local-VD plant still need a coherent design
record. Choke saturation/AC loss, hot switching loss, diode sharing and shunt
thermal limits remain unqualified.

The current power budget is 1800 W appliance input, with a 15 A RMS screen and
low-line foldback. Efficiency, PF and auxiliary allocations remain assumptions.
Older loss-budget cases are not current converter requirements or measurements.
[Current budget](../../../zapote/power-entry/passive-reva/protection/reference-revision-08/power-budget.md).

## Simplification gate and next unit

Do not collapse series divider resistors without checking voltage/pulse
rating and tolerance. Do not replace D's external driver with the controller
output without comparing loaded turn-off, default-off and retained restart
behavior. No B component deletion is established here.

The next feasible unit is a source-bound frequency/current/loop design table:
bind the exact FREQ equation and tolerance, shunt/filter/clamp limits, VD
feedback and compensation to the 108/120/132 VAC input budget. Define the short
startup/normal fixture and its load/auxiliary assumptions from that table.
Report unknown physical/model bounds rather than marking them passing.

Hardware double-pulse, magnetic and thermal tests are later qualification
work. They are not available in this simulation-only session.

## Parent review

Removed historical 1796 W output and 126 W modeled overlap figures from the
current recommendation. Narrowed B's inputs to its direct interfaces and
separated later hardware tests from work achievable now. EVM-573 and
TIDA-00779 remain wiring references, not qualification of Temper's low-line
power target.

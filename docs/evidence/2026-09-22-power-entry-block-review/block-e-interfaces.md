# Supplies and system interfaces: block E

Luna research handback, reviewed and condensed by the parent on 2026-09-22.
Six existing compiled instances: aux, control, permit, output,
protection.logic_bleed and protection.cmp_bypass.
[Exact inventory](component-ownership.json).

This small count does not represent completed supplies or system integration.
The four connectors are interfaces, not power/control producers.

## Current boundaries

| Net or boundary | Required authority and consumers | Current status |
|---|---|---|
| AUX15 / HOT return | Supply producer → B controller, D gate driver/standby, A relay drive | Header exists; physical producer/assembly and bounded startup/dropout/load contract unresolved |
| logic5 / HOT return | Logic supply → C detectors/reference and D supervisors/buffers/latch | Bare external port; producer and connectorization unresolved |
| hot_arm | Sequencing authority → D buffered latch clock | Bare external port; fresh-edge protocol required |
| hot_permit | Sequencing/interlock authority → D qualified clear logic | Header exists; HOT producer/crossing unresolved |
| relay_ctrl | Precharge sequencer → A relay driver | Header exists; HOT producer/crossing unresolved |
| local_vd / VB / return | B, external F2/reservoir assembly, C and downstream load | Source has distinct ports; physical assembly unresolved |
| health/rails/clear/run/fault observation | C/D → internal checks or a selected system consumer | Internal observation nets; no mandatory new telemetry hardware |

All consumers of a driven net must be named; fanout is permitted. One defined
authority owns each command. HOT-to-HOT input buffers and damping resistors
are not galvanic isolation. Any MCU/SELV crossing needs an explicit barrier
or a separately powered HOT producer. Multiple commands may share one
multichannel device. Existing interlock functions may be reused only after
the actual crossing and startup/fault behavior are connected and verified.

Source: [current integration map](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/integration-map.md),
[RevB source](../../../elec/src/power_entry_f2_shutdown_revb.ato).

## Concrete corrections to carry into the next source revision

The comparator comment says a 1 kohm logic bleeder, but actual source and
resolved BOM specify 220 ohm at lines 534–539. Budget from the real component.
This is a confirmed documentation mismatch, not a circuit change made here.

Older [interface design](../../../zapote/power-entry/passive-reva/INTERFACE-DESIGN.md)
discusses UCC27624; RevB actually uses UCC27511A. Do not inherit the old
driver's enable pin, power range or timing claims.
[Actual driver datasheet](https://www.ti.com/lit/gpn/ucc27511a).

Keep direct logic5 loads separate from direct AUX15 loads. Include gate
charging, relay coil/drop resistor, pullups and startup capacitor charging.
Only transfer logic5 demand onto AUX15 after a supply architecture is chosen.
The provisional auxiliary allocation is not a proved rail-load budget.

## Next bounded deliverable

Complete a producer/consumer contract and assembly ledger: domains, pins,
polarity, default states, current/voltage ranges, rail ramps/dropouts,
fresh-ARM sequence and ownership of precharge/continuity checks. Unknown
bounds must remain explicit. Name the exact interface or part whenever one
has been selected; do not count an unselected isolator or supply as installed.

Completion requires all top-level nets classified, all consumers named,
no assumed direct SELV/HOT connection, and a separate list of external
assembly additions. Diagnostics remain internal unless a system requirement
needs them. Source/domain graph checks establish connection boundaries, not
insulation or hardware certification.

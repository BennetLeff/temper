# Host integration and consolidation review

Reviewed source revision5dde29ab3 plus the source-bound uncommitted F2 revisionB
experiment. Research only; no schematic, PCB, firmware or model edits.

## Interfaces that must become real

| Interface | Current source fact | Required integration work |
|---|---|---|
| Power graph | `elec/src/power_entry_passive_reva.ato:370` connects diode directly to bulk bank; source has no F2/VD split | Create a separate integration candidate with F2 between VD/VB, local reservoir and discharge path; trace every fault loop |
| PWM | Same source:422 drives MOS gate directly from UCC28180 | Insert accepted driver at the actual gate interface; model controller stop/restart instead of free-running synthetic PWM |
| Controller standby | Same source:405 has a HOT_PERMIT-controlled VSENSE clamp | Connect latched fault to controller standby while preserving an independent fast driver-disable path |
| Auxiliary15V | Same source:433 requires external HOT-referenced supply | Name producer, ripple/startup/dropout/load and fault-voltage envelopes; the IRM proposal is not an installed producer |
| Logic5V | `power_entry_f2_shutdown_revb.ato:211` is an input port | Select/design and bound its producer; account for regulation, rise/fall, reverse current and partial power |
| ARM/PERMIT | Shutdown revisionB:214–216 are stimulus inputs | Define real isolated producer and fresh-edge protocol, no automatic retry; integrate system sequencing |
| Precharge/continuity | `ARCHITECTURE-REDUCTION.md:16–28,64–79` assigns them to system control | Implement producer/observations and derive deadline; equal VD/VB is not fuse continuity |
| Downstream load permit | Interface proposal:140–144 requires withdrawal on fault | Define actual bank-side ready measurement and load inhibit; existing250V-range voltage unit is not sufficient for this bank |
| Current limiting | Retained source:426 connects UCC ISENSE through actual shunt/filter | Bind tolerance, delay and inductor saturation to actual attainable trip current;15Arms input is not peak boost current |
| Cooling | `MILESTONE.md:19–22,33–40` retains GBJ-specific40°C inlet target | Bind actual losses, installed heat paths and fan-failure behavior;40°C is not a junction limit |

The interlock's PERMIT is3.3V/SELV-domain behavior with its own fresh falling
RESET_N protocol (`zapote/interlock/INTERFACES.md`). The local protection ARM
uses a rising edge and HOT reference. A matching signal name does not connect
these domains or reconcile the two protocols.

## Current79-part experiment by function

Counted from every instance in
`f2-shutdown-04/source-07/resolved-components.json`; each component appears once.

| Function | Count |
|---|---:|
| Two HV tapped dividers and filters |16|
| Reference and bias |2|
| Two bus comparator packages, eight input resistors, two bypass caps |12|
| Detector health gate and bypass |2|
| Two rail supervisors, dividers, CT, reset combining and pulls |17|
| Fast auxiliary-loss comparator and network |5|
| Latch plus ARM/PERMIT input buffers and support |8|
| Qualified enable AND and support |3|
| Driver, discrete disable interface, PWM conditioning, gate resistors and bypass |12|
| Shared logic bleeder and extra bypass |2|
| Total |79|

This is the standalone protection experiment, not the whole power board.
The retained power-entry board has54 parts. Combining them requires explicit
replacement/retention mapping and still needs producer/connector/fuse/reservoir
accounting. The previous133-part rejected construction and this79-part
experiment have different scopes;79 alone does not establish a reduced board.

## Consolidation sequence

1. Freeze a combined functional netlist and whole-assembly census before choosing
   a numerical component-count target. Separate installed, replaced, new and
   offboard parts without dropping offboard cost from the total.
2. Audit repeated filtering/bypass/input conditioning against exact datasheet
   and isolation requirements. The extra shared bypass is an investigation
   candidate, not permission to remove local decoupling.
3. Compare combining the rail-supervision and fast aux-loss functions, or using
   fewer logic packages, only against measured response, power-off behavior,
   voltage ranges and fresh-edge recovery. An integrated monitor's pin named
   LATCH does not imply the required restart semantics.
4. Preserve both bus OV channels, bidirectional mismatch until justified otherwise,
   direct default-off drive and retained fault. Do not remove discrepancy
   detection merely because an ideal-PWM experiment passes.
5. Compile one chosen alternative, verify physical pins and rerun all existing
   fault/supply/driver/current negative controls plus the new controller-coupled
   scenarios. Count reduction is accepted only with preserved behavior.
6. Move to layout once the electrical interface and model decisions are fixed.
   Layout changes need fresh saved-byte native/Rust checks and physical loop
   assumptions. Numerical model completion does not close installed qualification.

The frozen revisionB source contains stale descriptive comments (12.9V rather
than nominal12.995V, and an old1kΩ bleeder comment despite actual220Ω). The
compiled parts and latest device contract are authoritative. Fix comments only
in a new source revision; do not mutate the receipt-bound04 experiment.

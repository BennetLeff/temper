# Rev11 / Rev16 control binding audit

**Status: review recommendation; not a changed or qualified circuit.** This
note traces the Rev11 source through its exported Atopile netlist and compares
its local control with the Rev16 reset fixture. The Rev11 export is the
136-instance candidate and is not manufacturing output. Source references and
exported `U` designators below are both given because Atopile aliases some
`libsource` metadata by footprint; use `resolved-components.json` for exact
part identity. The export hashes are recorded in
[`artifact-hashes.json`](../interface-defaults-11/artifact-hashes.json).

## Rev11 source-to-netlist map

Source is in
[`power_entry_f2_shutdown_revb.ato`](../interface-defaults-11/source-candidate/elec/src/power_entry_f2_shutdown_revb.ato)
and instantiated by
[`power_entry_pfc_control_candidate.ato`](../interface-defaults-11/source-candidate/elec/src/power_entry_pfc_control_candidate.ato).
The checked export is
[`build/default.net`](../interface-defaults-11/source-candidate/build/default.net);
the instance-to-MPN authority is
[`resolved-components.json`](../interface-defaults-11/source-candidate/resolved-components.json).

| Function | Atopile source instance / module | Export ref and verified part | Pin/net connection |
|---|---|---|---|
| Maintained external permission input | `permit_buf: F2IsoBuf` (`SN74LVC1G17DBVR`), raw `permit` is the candidate's `hot_permit` top-level port | U47, SN74LVC1G17DBVR | U47.2 is `HOT_PERMIT_EXTERNAL`; U47.4 is `permit_safe`. |
| Raw PERMIT default | `permit_input_pd: F2R`, 10 kΩ from `permit` to GND | U48 | U48.1 shares `HOT_PERMIT_EXTERNAL`; U48.2 is GND. This biases an open/high-impedance input low. |
| Buffered PERMIT default | `permit_pd: F2R`, 10 kΩ from `permit_safe` to GND | U50 | U50.1 shares U47.4 / `permit_safe`; U50.2 is GND. |
| ARM edge input | `arm_buf: F2IsoBuf` (`SN74LVC1G17DBVR`), raw `arm` is the candidate's `hot_arm` top-level port | U64, SN74LVC1G17DBVR | U64.2 is `hot_arm`; U64.4 joins U62.3 and U67.1 on `clk1`. |
| Raw ARM default | `arm_input_pd: F2R`, 10 kΩ from `arm` to GND | U65 | U65.1 shares `hot_arm`; U65.2 is GND. |
| Buffered ARM default | `arm_pd: F2R`, 10 kΩ from the latch clock to GND | U67 | U67.1 is `clk1`; U67.2 is GND. |
| Retained local RUN latch | `latch: F2Dff` = TI SN74HCS74PWR | U62, resolved MPN SN74HCS74PWR | FF1: pin 1 `/CLR1` = `clear_ok`, pin 2 D1 = logic5, pin 3 CLK1 = `clk1`, pin 4 `/PRE1` = logic5, pin 5 Q1 = `run`, pin 6 `/Q1` = `fault_clear_n`. Pin 14 VCC = logic5 and pin 7 GND = `PFC_BUS_MINUS` / control ground. |
| Unused second latch half | same U62 | U62 | FF2 D2 pin 12, CLK2 pin 11, `/PRE2` pin 10, `/CLR2` pin 13 are held at the stated fixed values in source; Q2 pin 9 and `/Q2` pin 8 are not used. It is not a ready-made rearm state machine. |
| Health/clear aggregation | `health: F2And4` = SN74HCS21PWR | U29 | `clear_ok` is U29.8 and feeds U62.1 `/CLR1` and U68.2. PERMIT contributes at U29.12 from `permit_safe`; AUX UV/OV, rail/watchdog conditions also feed this logic. |
| Final logic enable qualification | `enable_and: F2IsoAnd` = TI SN74LVC1G08DBVR | U68, verified from resolved per-instance attributes (netlist library alias is misleading) | U68.1 = `run`, U68.2 = `clear_ok`, U68.4 = `enable_good`; the latter drives the local gate-driver/PFC permit network. |

The latch is a **set-on-rising-ARM edge**: D1 is held high, and a rising edge
at CLK1 sets Q1 while `/CLR1` is inactive. PERMIT is a maintained health
condition; loss makes `clear_ok` false, asynchronously clears RUN and also
forces the final `enable_good` low. ARM low by itself is not a stop command.
The two 10 kΩ pulldowns establish defaults for open/high-impedance inputs; they
do not make the circuit distinguish a deliberate ARM transition from a wire
that reconnects already high. Rev11 retains a dedicated counterexample for
that case: `after/arm_reconnect_high` fails as expected. Its own
[`INTERFACE-CONTRACT.md`](../interface-defaults-11/INTERFACE-CONTRACT.md)
requires the producer to hold ARM low across fault/reset/reconnection and
issue a fresh edge only after permission is valid. That requirement cannot
protect against an uncontrolled high-level reconnection by itself.

## What Rev16 adds, and what it does not bind

The [Rev16 reset fixture](../interface-capture-16/reset.kicad_sch), its
[independent expected pin/net table](../interface-capture-16/reset-expected.tsv)
and [review notes](../interface-capture-16/README.md) are a separate KiCad
review drawing. Its U designators are local to that fixture; they are not
Rev11 designators and no hierarchy or electrical connection joins the two
exports.

| Rev16 reference | Fixture function | Relationship to Rev11 |
|---|---|---|
| U1 / U2, SN74LVC1G08 | SELV source-reset/watchdog/interlock health conjunctions | Introduce source-side health concepts absent as implemented producer circuits in Rev11. Outputs are fixture boundaries, not Rev11 nets. |
| U3, SN74HCS74 | SELV source-permission/rearm state; receives `SOURCE_REARM_PULSE` and produces `PERMIT_TX` after `SOURCE_HEALTH` | Could define policy for the maintained permission, but its pulse source and power-up behavior remain external. It is not already bound to Rev11's `hot_permit`. |
| U4, ISO7741FDWR | SELV/HOT isolation. Pin 4 `PERMIT_TX` maps through channel B to pin 13 `HOT_PERMIT_RX`; pin 3 `COMMAND_TX` maps to pin 14 `HOT_COMMAND_RX`. | Provides a proposed isolation boundary for Rev11 PERMIT/command. Rev11 source itself specifies no isolation device for these two input ports. U4 is only in a fixture; the command receiver / frame decoder is absent. |
| U5, SN74LVC1G08 | HOT `CLEAR_OK_EXISTING` and `HOT_WATCHDOG_GOOD` combine into `CLEAR_OK_HW` | Candidate way to include independent HOT watchdog health in a combined clear condition. Rev11 has watchdog/rail qualification, but not this external producer contract. |
| U6, SN74HCS74 | Two HOT latch stages; both `/CLR` pins 1 and 13 take `CLEAR_OK_HW`. Q2 pin 9 produces `ARM_AUTHORIZED` and feeds D1 pin 2; D2 pin 12 is tied to `HOT_LOGIC5`. CLK pins 3 and 11 receive separate `VALIDATED_START_5V` and `SESSION_ARM_5V`; Q1 pin 5 produces `RUN`. | A session-qualified command concept, not a pin-compatible substitute as drawn. It uses the same part family as Rev11 U62 but different external semantics and fixture-local wiring. Its two pulses have no implemented producer in the fixture. |
| U7, SN74LVC1G08 | AND of `RUN` and `CLEAR_OK_HW` produces `ENABLE_GOOD` | Functional analogue of Rev11 U68 (`run AND clear_ok`), but it is not electrically connected to U68 or the Rev11 driver permit net. |

Rev16 is useful as a contract and pin-level proposal, but it does **not** close
the control path: expected-net entries for `SOURCE_REARM_PULSE`,
`HOT_WATCHDOG_GOOD`, `COMMAND_TX`, `HOT_RESPONSE_TX`,
`SESSION_ARM_5V`, and `VALIDATED_START_5V` are fixture ports. The Rev16 README
explicitly says their producers/decoder are not implemented. In particular,
the Rev16 latch cannot simply be wired in parallel with Rev11 U62: that would
create two RUN authorities and an unanalysed enable path.

## Minimal fail-safe binding recommendation

Keep one HOT-side retained RUN latch and one final dominant enable gate. Bind
the Rev16 isolation/interface **through an implemented HOT command receiver**
as follows:

1. Route isolated `HOT_PERMIT_RX` to Rev11 `hot_permit` / U47.2. Keep the
   maintained permission default-low, and require it to remain low until
   source-health, watchdog, and reset sequencing have completed.
2. Do **not** wire a maintained command level or `HOT_COMMAND_RX` directly to
   Rev11 `hot_arm` / U64.2. The HOT receiver must validate a fresh post-reset
   command session and emit one bounded, low-idle `VALIDATED_START_5V` pulse
   into that ARM input only after PERMIT is valid. After a source fault, it
   must stay low until deliberate re-arm has been acknowledged. This makes a
   bare high level or conductor reconnection insufficient to clock U62.
3. Keep Rev11 U29 `clear_ok` connected to U62 `/CLR1` and U68; do not let
   software/session state mask a hardware fault. The reset/rearm producer must
   demonstrate that the clear path was observed before it can emit a new
   validated pulse. Preserve the independent final AND of retained RUN and
   hardware health.
4. Leave Rev16 U6/U7 as the **alternative replacement implementation** if
   selected after full integration review; do not install them alongside
   Rev11 U62/U68 as an unanalysed second latch/enable layer.

This requires a real receiver/stateful protocol source, output pulse bounds,
power-up reset state, watchdog behavior and isolation-channel implementation.
Those parts and the pulse producer are not presently selected or built. Until
that boundary exists, the only safe commissioning rule is to hold the external
ARM and PERMIT inputs low; the Rev11 pulldowns alone do not prove safe recovery
from high-level reconnection. The recommendation follows the existing design
principle that hardware faults dominate and software may sequence recovery but
may not bypass the retained latch; see
[`dual-path-rtd-fault-containment`](../../../../../docs/solutions/architecture-patterns/dual-path-rtd-fault-containment-2026-07-13.md)
and the repository guidance on not treating unused latch pins or gates as
available fault capacity in
[`fault-latch-fan-in-capacity-budget`](../../../../../docs/solutions/best-practices/fault-latch-fan-in-capacity-budget-2026-07-26.md).

## Evidence and limits

Validated mapping evidence: Rev11 Atopile instance wiring, `build/default.net`,
`resolved-components.json`, and the build artifact hash receipt; Rev16 mapping
evidence: `reset-expected.tsv`, the native schematic, and the Rev16 capture
auditor described in its README. No source fixture, schematic or PCB was
edited by this audit, and no hardware behavior was established. The
recommendation is an integration requirement, not a claim that the command
receiver, pulse generator or full fail-safe binding exists.

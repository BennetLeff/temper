# Revision 24 control integration audit

Read-only integration map for the current compiled power-entry candidate and
the isolated control fixtures. This audit does not adopt a source topology,
select parts, or claim hardware qualification. The latest compiled full
candidate remains Revision 11, 136 instances. Revision 16's reset sheet is a
28-component *reference fixture including existing circuits*, and Revision 19
is a corrected 14-component clamp prototype; neither is a full-candidate
revision.

## Evidence basis

- [Revision 11 candidate and producer contract](../interface-defaults-11/README.md)
  and [contract](../interface-defaults-11/INTERFACE-CONTRACT.md).
- [Revision 16 native reset/clamp fixtures and ERC disposition](../interface-capture-16/README.md),
  [reset pin map](../interface-capture-16/reset-expected.tsv),
  [historical Revision 16 clamp pin map](../interface-capture-16/clamp-expected.tsv), and
  [capture receipt](../interface-capture-16/receipt.json).
- [Revision 13 logical handshake](../interface-handshake-13/command/design.md),
  [Revision 14 reset timing contract](../interface-physical-14/reset/design.md),
  [Revision 17 producer/watchdog and capacitance audit](../interface-integration-17/README.md),
  [watchdog handback](../interface-integration-17/watchdog-handback-unaccepted.md),
  [Revision 19 corrected clamp pin map](../interface-dynamics-19/clamp-expected.tsv),
  [Revision 19 corrected clamp receipt](../interface-dynamics-19/receipt.json),
  and [Revision 19 reset qualification](../interface-dynamics-19/verification-contract.md).
- Project solutions read for this audit: [electrical model acceptance](../../../../../docs/solutions/best-practices/electrical-model-acceptance-rules-2026-09-18.md),
  [claimed isolation versus connectivity](../../../../../docs/solutions/best-practices/claimed-isolation-vs-actual-connectivity-2026-07-26.md),
  [net names are claims](../../../../../docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md),
  and [fault latch fan-in budget](../../../../../docs/solutions/best-practices/fault-latch-fan-in-capacity-budget-2026-07-26.md).

## Pin and net map

### Compiled Revision 11 boundary

The Atopile top-level explicitly comments that these are external interfaces,
not installed components or validated producers:

| Revision 11 net/interface | Current function and integration consequence |
|---|---|
| `aux_15v`, `aux_15v_return` | External AUX producer and return. This is the prospective clamp input boundary; source identity, fault waveform, and source impedance are unresolved. |
| `logic5` | External 5 V rail source. Its topology is coupled to the unresolved AUX/source choice. |
| `hot_arm` | External edge request to the existing ARM input/buffer and retained RUN latch. A low/open ARM does not clear a running latch. |
| `hot_permit` | External maintained permission to the existing PERMIT buffer/health logic. Loss clears RUN; return alone does not rearm. |
| `local_vd`, `hv_plus`, `hv_minus`, `control_gnd` | External PFC/power-stage boundaries; F2/HV/reservoir integration is deliberately incomplete. These are not SELV MCU ports. |
| `relay_ctrl` | External HOT relay command. The reset fixture exposes its corresponding isolated signal but does not implement the producer/decoder. |

Revision 11 adds raw 10 kΩ pulldowns on ARM and PERMIT and Ioff-rated input
buffers. Its 13-group topology audit is not full ERC or proof of a physical
source. In the nominal fixture, PERMIT open/reconnect and producer reset work;
ARM open alone intentionally leaves RUN set; reconnecting ARM while its source
is already high creates a new edge and can restart. The producer must hold ARM
low through reset/reconnect. See `interface-defaults-11/README.md` scenario
table and `INTERFACE-CONTRACT.md` sequencing.

### Revision 16 reset fixture pin/net assignments

These are the exact captured pins. `HOT_*` and `SELV_*` name domains, but do not
by themselves prove galvanic isolation; U4 is the only drawn cross-domain
component in this fixture.

| Ref/pins | Net(s) | Declared role / missing physical source |
|---|---|---|
| U1.1 / U1.2 | `SOURCE_RESET_GOOD` / `SOURCE_WATCHDOG_GOOD` | Independent SELV health producers, each with R1/R2 default-low pulldown. Neither is implemented by the captured sheet. |
| U1.3, U1.5 | `SELV_GND`, `SELV3V3` | External SELV supply/return. |
| U1.4 → U2.1 | `RESET_WD_OK` | AND of source reset-good and watchdog-good. |
| U2.2 → U3.1 | `INTERLOCK_PERMIT` → `SOURCE_HEALTH` | Existing interlock PERMIT is a candidate source; its output/load/domain binding is conditional and not yet integrated. U2 combines it with `RESET_WD_OK`. |
| U3.2/U3.4, U3.7/U3.11–13 | SELV rails/ground | Power pins for the source permission latch; U3.3 is `SOURCE_REARM_PULSE`; U3.5 emits `PERMIT_TX`. Rearm pulse producer and power-on sequencing are absent. |
| U4.3, .4, .5 | `COMMAND_TX`, `PERMIT_TX`, `RELAY_CMD` | Three SELV-to-HOT forward channels. `COMMAND_TX` encoder and `RELAY_CMD` producer are absent. `PERMIT_TX` is from U3. |
| U4.6 / U4.11 | `SELV_RESPONSE_RX` / `HOT_RESPONSE_TX` | Reverse HOT-to-SELV response channel. HOT response source/encoder and SELV frame receiver are absent. |
| U4.12, .13, .14 | `HOT_RELAY_CMD`, `HOT_PERMIT_RX`, `HOT_COMMAND_RX` | HOT-side channel outputs. A HOT decoder/command state machine must consume command, qualify permission, and drive relay control. |
| U5.1, .2 → U5.4 | `CLEAR_OK_EXISTING`, `HOT_WATCHDOG_GOOD` → `CLEAR_OK_HW` | U5 combines existing permission/health clear with independent HOT watchdog-good. U5.1 and U5.2 have 10 kΩ default-low bias, but neither producer is implemented in the fixture. |
| U6.1, .13 | `CLEAR_OK_HW` | Both halves of the existing HOT latch clear path; source health/watchdog loss must reach this path. |
| U6.2, .9 | `ARM_AUTHORIZED` | Both latch data/control authorization inputs. Pin 2 is deliberately not tied high. Authorization must only be established after observed clear and a fresh session. |
| U6.3 / U6.11 | `VALIDATED_START_5V` / `SESSION_ARM_5V` | Distinct HOT 5 V pulses into the two existing latch halves. The fixture has pulldowns but no decoder/framer/level translator that creates valid pulses. |
| U6.5 → U7.1 | `RUN` | Existing retained latch output into existing enable logic. |
| U7.2 / U7.4 | `CLEAR_OK_HW` / `ENABLE_GOOD` | Existing final enable AND inputs/output. The downstream BSS138/UCC27511A disable network is referenced, not duplicated in the fixture. |
| U4.9/.15, U5.3, U6.7, U7.3 | `HOT_GND`; U4.10/.16, U5.5, U6.4/.10/.12/.14, U7.5 | `HOT_LOGIC5` | HOT supply/return are external. No SELV/HOT ground short is drawn. |

U4 is explicitly ISO7741FDWR, which has a three-forward/one-reverse allocation;
the pin map consumes all four channels. The four source nets listed in the
fixture (`COMMAND_TX`, `PERMIT_TX`, `RELAY_CMD`, `SELV_RESPONSE_RX`) therefore
cannot be treated as spare channels for a separate reset wire. Reset and health
are combined upstream into `PERMIT_TX` in this mapping, with the corresponding
loss of individual HOT-side fault diagnostics. A different channel allocation
is an architecture decision, not a wire-only correction.

### Revision 19 clamp boundary

Revision 19 changes only the two gate-network endpoints from Revision 18:
R7.1 and D1 anode/D1.2 join `GATE_DRV`; D1 cathode/D1.1 remains `CG`. The
corrected 14-component clamp pin map is in
`interface-dynamics-19/clamp-expected.tsv`; the Revision 16 map is superseded
for these endpoints. Revision 19 verification is recorded in
`interface-dynamics-19/receipt.json`. External rails/ports are:

| Clamp port | Role and unresolved producer |
|---|---|
| U1.5 `AUX_RAW`, Q1.2 | Input from the eventual 15 V source. Source transient/impedance are unchosen. |
| U1.2 `AUX_PROTECTED`, R1.2, C4.1 | Protected consumer rail. It can feed downstream only after C4/load/ceramic/startup constraints and transient voltage are resolved. |
| U1.7/.9, Q1.3, C1–C4 returns | `HOT_GND`, external return. |
| U1.6 `SERVICE_RESET_N` | Local manual service contact only. It is not source permission or product reset. Its /SHDN input is not driven by an ERC output symbol. |
| U1.10 `FLT_TP`, U1.11 `ENOUT_TP` | Observation-only labels; no fitted test point or pullup. |

Revision 19 leaves the part count/BOM unchanged from Revision 18, reports 7
clamp ERC findings, and its passive probes omit controller, FET, and load
models. The 120 ms value is LT4363 timer reset only; it does not bound gate
turn-off, output discharge, or restart. Revision 20–23 dynamics do not resolve
the physical source/load contract.

## ERC status: explicit open boundaries

Revision 16 KiCad 10.0.4 records **17 total findings**, none excluded: clamp 7,
reset 10. The audited native netlist and pin-function checks pass, including
mutations rejecting a shorted sense pin and fixed-high authorization. ERC remains
open for the following named boundaries:

- Clamp: 1 `pin_not_driven` at U1.6 `/SHDN` (service contact/pull-up is not an
  active output symbol); 3 `power_pin_not_driven` at `AUX_PROTECTED`, `AUX_RAW`,
  `HOT_GND`; 3 one-pin labels (`SERVICE_RESET_N`, `FLT_TP`, `ENOUT_TP`).
- Reset: 2 `pin_not_driven`: U5.1 `CLEAR_OK_EXISTING` and U4.11
  `HOT_RESPONSE_TX`; 4 `power_pin_not_driven`: SELV3V3, SELV_GND, HOT_GND,
  HOT_LOGIC5; 4 one-pin labels: `CLEAR_OK_EXISTING`, `HOT_COMMAND_RX`,
  `HOT_RESPONSE_TX`, `ENABLE_GOOD`.

The native reset ERC excerpt identifies `U4.11` as an undriven input (`IND`),
so the HOT response producer is a real open port, not just a dangling label.
Default-low pulldowns make selected logical inputs fail low but do not implement
their producers. Do not silence these reports with power flags, ERC exclusions,
or additional pulldowns. No fresh full-candidate ERC is present for Revision 11.

## Sequencing and race audit

1. **Boot:** hold `SOURCE_REARM_PULSE`, ARM/session-arm and START low. SELV and
   HOT supplies, returns, source health, interlock permission and HOT watchdog
   must reach valid states first. Revision 14 model starts only after its
   assumed HOT clear; actual supply settling and minimum pulse widths are not
   measured.
2. **Permission:** source reset-good and source watchdog-good are distinct
   prerequisites. `INTERLOCK_PERMIT` may use the existing standalone interlock
   PERMIT path, but its heartbeat, output loading and true source-reset
   detection must be integrated. The existing TPS3823 combines its own rail
   monitor and missed-WDI result; it does not prove the separate source MCU
   reset condition. Directly loading its diagnostic RESET output with the
   fixture's 10 kΩ health pulldown is unsupported by the cited 30 µA VOH test
   condition. HOT watchdog-good is a separate, unimplemented producer.
3. **Clear before rearm:** fault/permission loss must be observed at HOT and
   clear both existing latch halves through `CLEAR_OK_HW`. Only after the low
   has reached/been recognized by HOT may a new source rearm/session proceed.
   `SOURCE_REARM_PULSE` currently has no producer or acknowledgement. It is not
   an LT4363 `TMR` reset acknowledgement.
4. **Fresh command:** Revision 13 handshake requires persistent monotonic
   session identity, fresh local intent, challenge/request/ACK/START matching,
   fixed deadline, duplicate/stale rejection and retries that do not extend the
   deadline. Its Rust model accepts already-decoded frames; framing, persistence,
   watchdog clock and physical decoder are absent. The fixture's 1 µs pulse
   separation is only a test stimulus, not setup/hold evidence.
5. **Fault during START:** Revision 14 preserves a same-time ordering witness:
   START can be processed before a later-arriving reset clears RUN. A finite
   in-flight window remains; do not describe this as zero-delay or globally
   race-free. Bound detection, isolation, logic, gate-driver and MOSFET turnoff
   from measured worst cases. A failed-high reset/permission conductor also
   remains outside the one-path model.
6. **Recovery:** AUX clamp auto-recovery cannot authorize switching; source and
   HOT latch state must independently require fresh authorization. Revision 11
   demonstrates an ARM-high reconnection edge can restart. Producer sequencing
   must actively hold ARM low through reset/reconnect; one-bit pull bias cannot
   distinguish reconnection from intent.

These are model-level contracts and counterexamples. They do not constitute a
timing guarantee or hardware pass.

## What can be prepared without a product/source decision

- Freeze the Revision 11 source candidate and verified Revision 16/19 reference
  graphs by their existing hashes; preserve their independent local reference
  numbers and do not count fixture context components as new fitted parts.
- Map the existing Revision 11 latch and enable *instances* to the contextual
  U6/U7 functions in the Revision 16 fixture before attempting a native join.
  Keep SELV and HOT returns separate. The fixture reference numbers alone are
  not an identity map.
- Carry the corrected Rev19 R7/D1 pin nets into a future source candidate and
  preserve the `AUX_RAW`/`AUX_PROTECTED` distinction. The clamp must sit ahead
  of **every** Rev11 AUX consumer if selected; a connector-only join would
  bypass protection for on-board loads.
- Reserve U4's documented 3-forward/1-reverse channels and map all 16 pins to
  the Revision 16 expected table. Keep the raw command, reverse response,
  maintained permission, relay control and reset/health ownership explicit.
- Keep the existing interlock as the conditional producer reference for
  `INTERLOCK_PERMIT`; no duplicate watchdog is needed merely to reproduce that
  existing aggregate permission path.

These steps produce a reviewable binding specification. The
[Revision 25 feasibility check](../interface-integration-25/README.md) found
that a compiled native shell cannot honestly be assembled from the retained
inputs alone: Revision 11 is Atopile source, while Revisions 16/19 are separate
KiCad fixtures; the producer boundary, exact part identities and control
architecture require an authoritative new source candidate.

## What is blocked on source/product decisions or physical evidence

- Binding `AUX_RAW`, `AUX_PROTECTED`, `HOT_LOGIC5`, and their returns to the
  actual supply topology requires selecting the source path and deciding
  whether the LT4363 clamp is in the product path. It changes converter startup
  current, rail capacitance and fault exposure.
- The external AUX source's fault waveform, source impedance, maximum voltage,
  and continuity/recovery contract require manufacturer or bench evidence.
  Revision 20–23 synthetic fixtures cannot supply these.
- Choosing Revision 11's simple ARM/PERMIT interface versus Revision 13's
  challenge/ACK/session handshake is a product/control architecture decision.
  The Revision 16 fixture assumes the latter's decoded pulses but has no
  decoder, frame persistence, MCU, or selected level translation.
- A physical `SOURCE_RESET_GOOD` producer must detect MCU reset even when MCU
  power stays valid. A separate source watchdog-good binding, HOT watchdog, HOT
  response driver, protocol encoder/decoder and `SOURCE_REARM_PULSE` generator
  require actual chosen devices/logic and power-on behavior.
- Exact passive MPN/package selection, protected-rail capacitor max/min/ESR,
  18 V driver-pin compliance, Q1 hot SOA, reset propagation and stop-time
  acceptance depend on components, product criteria and/or bench measurements.

## Bounded native candidate build order after bindings are fixed

1. **Freeze inputs:** verify Revision 11 build/resolved-component identities and
   the Revision 16/19 schematic, netlist, expected TSV, BOM and ERC hashes. Keep
   all existing source artifacts immutable; no PCB change.
2. **Author a new integration shell** under a fresh revision directory. Pull in
   the compiled Rev11 control/PFC blocks once; add the corrected 14-part Rev19
   clamp graph at the external AUX boundary; reuse the Rev16 reset fixture only
   as a pin/net integration specification. Do not paste its contextual 28 parts
   wholesale or duplicate the Rev11 latch/enable gates.
3. **Join established nets only:** preserve `CLEAR_OK_EXISTING` as the already
   available permission/health path, join `CLEAR_OK_HW` to both latch clear
   inputs, `RUN` through the existing `ENABLE_GOOD` gate, and use U4's exact
   forward/reverse allocation. Keep every unresolved producer as a typed
   connector/sheet port with a low/default contract where supported.
4. **Keep unchosen power nets external:** do not select or draw in an AUX source
   implementation, HOT5 generator, extra watchdog or analog limiter. Mark
   external supply ports and source impedance/fault behavior as unresolved.
5. **Check the resulting graph:** native KiCad export; all-pin connectivity and
   manufacturer pin-function audit; assert no SELV/HOT connection, no tied
   push-pull outputs, no fixed-high latch data/authorization, correct R7/D1
   endpoints, clear to both latch halves, and no unconnected internal nets.
   Run ERC and retain the open boundary findings by producer/rail; no broad
   waivers. Render and visually check whole sheets and crowded connection areas.
6. **Stop at the boundary:** issue the result as an integration fixture with an
   explicit unresolved-port ledger. Do not call it an adopted full candidate,
   clean ERC, electrically complete source design, or hardware-qualified
   product. A later revision can bind the rails and implement producers after
   source and control choices are supplied.

The smallest productive follow-on is to settle the source insertion and
control-architecture bindings, then author this graph in the project's
Atopile source of truth and run its native export checks. Revision 25 records
the current build-tool obstacle and the exact wiring decisions still needed.

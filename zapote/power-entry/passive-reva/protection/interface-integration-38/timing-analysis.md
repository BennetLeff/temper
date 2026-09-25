# Rev38 timing analysis — first engineering package

Status: **candidate method recorded; numerical safety acceptance OPEN**. This
document starts the authorized per-fault derivation. It does not turn Rev35/37
fixture timing, typical data, or a simulation screen into an accepted limit.
The final source/native circuit, installed power-stage envelope, and
prototype captures do not yet exist. The joined Atopile candidate contains
the AVR64DA32, the joined ISO7741FQ/ISO6742FQ DWW isolator pair, source and HOT TPS3431 devices,
retained source/HOT memories, dual HOT TPS3890 undervoltage supervisors,
four TLV3202 VD/VB channels, two AUX window channels, the UCC27624/STW
driver stage, and the selected AC/AUX/PFC stages. Their presence does not
close a complete response path.

## Acceptance relationship and endpoints

For each gate-interruptible fault class `f`, establish two independent sides:

```text
T_implementation_worst(f) + T_margin(f) <= T_allowable(f)
```

`T_allowable` comes from the affected node's current, voltage, stored energy,
thermal/interconnect limits, operating envelope, and derating. It is never
chosen from the parts' measured speed. `T_implementation_worst` begins at a
defined fault or unfiltered threshold and ends at sustained current cessation
in the controllable STW channel. It includes detection/filtering, qualified
capture, retained clear, isolation when applicable, UCC27624 EN and output,
loaded STW gate discharge, and commutation. State the margin and uncertainty
method separately. A low EN, low gate voltage, or momentary zero-current
sample is not the end point. Gate-off does not mean VD/VB is de-energized.

For a failed-short switch or another fault the gate cannot interrupt, this
inequality is not a valid containment argument. Use F1/F2/interconnect and
stored-energy analyses instead, under their separate scope.

## Selected unexpected-reset candidate

One pre-reset committed, unexpired first START may set RUN at most once while
the current session and independent hardware permission remain valid. It
cannot be generated or retransmitted by rebooted source code. Already-running
and first-start cases share the same execution-loss deadline; accepting START
cannot give the watchdog another interval. A deliberate software restart
requires physical disarm acknowledgement before the restart request.

```text
T_reset_to_off_worst = T_postreset_feed_tail_worst
                     + T_watchdog_worst
                     + T_watchdog_trip_to_current_zero_worst

T_reset_to_off_worst + T_reset_margin
    <= min(T_allowable_first_start, T_allowable_already_running)
```

The historical `source-build-04` changed the GPIO21 request pull-down from
100 kΩ to 10 kΩ. Espressif gives a **typical**, not minimum, 45 kΩ internal
pull-up for ESP32-S3. Against that typical value at 3.3 V, the old divider
could sit at 2.28 V, inside TI's SN74LV221A-Q1 0.3–0.7 × VCC uncertain
input band; 10 kΩ gives about 0.60 V, below the specified low-input
limit. Neither a guaranteed ESP pull-up minimum nor ROM/boot pad behavior
is established, so this resistor change reduces one credible spurious-edge
path but **does not bound the feed tail**. Capture GPIO21, LV221A B2 and
Q2_N/WDI for CPU-only reset, `esp_restart`, panic/watchdog, brownout and
forced boot loops; correlate STOP_N/GPIO13, GPIO48, permit Q and TCA P0–P2.
Repeated boot-created WDI edges would make the tail unbounded. The selected
contract permits a proven finite post-reset tail; it does not require a
physically impossible edge.

The feed-tail term is zero only after the actual ESP owner, other core,
bootloader, reset loops, queued writes, and timer/DMA/RMT paths are proved
incapable of another qualifying WDI edge. Otherwise it needs a finite maximum;
an unbounded feed tail fails the candidate. The watchdog term needs selected
CWD effective capacitance, leakage, temperature, SET1/EN state, and device
corners. The selected source and HOT watchdogs each have Murata
`GRM1885C1H102JA01D` 1 nF C0G CWD parts. Applying only Murata's initial
±5% tolerance to TI's ideal-capacitor equation gives a **conditional**
116.320–149.216 ms device interval: `0.905 × (77.4 × 0.95 + 55)` to
`1.095 × (77.4 × 1.05 + 55)` ms. This is not an installed maximum: capacitor
temperature/lifetime effects, leakage, PCB contamination, device supply
excursions and effective C at the pin still need a corner budget. The final
term includes WDO assertion through source-latch clear,
physical PERMIT crossing, HOT retained clear, EN, loaded gate, and sustained
switch-current cessation. Rev35's 119.82–144.98 ms ideal-1-nF device range
is not the complete term and is not an allowable interval.

The selected source WDI adapter uses the spare `SN74LV221A-Q1` B2
rising-trigger channel with 10 kΩ/10 nF and its active-low Q2 output. TI's
3.3 V ±0.3 V, −40 to 125 °C table gives **90–110 µs** output-pulse duration
for 10 kΩ/10 nF and 50 pF load. The TPS3431 requires a **minimum 50 ns WDI
pulse** and a falling edge. Thus the nominal selected topology has ample
fixture-level pulse width, but the 90 µs lower number is not a Rev38
guarantee: the installed X7R capacitor's effective capacitance, resistor
corners, output loading, SELV rail and WDI thresholds must be verified.
Neither the one-shot nor its pulse width bounds how many qualifying edges
boot code can create after reset. TI also specifies WDO low for
**170–230 ms** after watchdog expiry while the device remains in its
operating conditions; the retained source clear must capture that pulse,
and a rail collapse cannot be credited with this WDO pulse without a
separate partial-power proof.

The new `firmware/main/power_entry_authorization.c` host core starts in
lockout without a WDI request and issues no START after reinitialization.
Its synchronous `power_entry_source_runtime.c` adapter drives STOP low,
drains UART, and leaves the heartbeat-request GPIO untouched at boot. A
retained-high request pad is
not driven low by that host sequence. The joined circuit now puts a
rising-trigger SN74LV221A-Q1 between the ESP heartbeat request and WDI: a
high-to-low request-pad transition on CPU reset cannot become TPS3431's
qualifying WDI falling edge. The first deliberate request rise waits for
physical disarm and local progress. The new `app_main` source task binds the
adapter to candidate ESP pins and owns the intended UART/I²C/GPIO path. It
remains locked out with zero target timing bounds and unqualified UART
final-bit, reset feed-tail and independent monitor progress. Reset-time pad
reconfiguration, bootloader activity, or another owner may still create a
**rising request** before this task runs; partial rail collapse may also alter
the one-shot output. No bootloader,
other-core, GPIO-retention, queue-to-pin, or peripheral-autonomous-edge
evidence exists, so the post-reset feed tail remains **UNBOUNDED** for
numerical acceptance. The full ESP-IDF v5.3.6 diagnostic lockout image now
links; production mode still fails at image link on unresolved cooker hooks.
Neither host tests nor a locked diagnostic image close the reset path.
The source service now accepts a sticky, atomic monitor-fault request from
another task. Its sole source owner polls that latch before PERMIT, WDI,
START and restart actions, then requests STOP low and drains UART. Focused
host tests cover a fault injected during the final sample before each
authorization edge; all 17 firmware CTests and a refreshed ESP32-S3
source-task target link pass. The cooker monitor still has no completed
safety check or accepted sensor-age policy, so it does not yet issue that
request or earn progress credit. An in-flight I/O action and source-task
response latency require physical bounds; these tests do not shrink the
implementation-worst term.
The joined source now has a separate `SOURCE_PREWATCHDOG_OK` gate from
reset-good, interlock and rail-good without WDO. It can support a pre-feed
software sample without making watchdog recovery depend on WDO already being
high. Its ESP sampling pin is joined. The cooker-mate derivative now has
compiled reset-good and interlock producer circuits, but GPIO14 open-drain
ownership and physical startup/reset behavior are OPEN; this logical path
does not reduce the unbounded reset-time feed tail.

The two allowable reset times need system hazard analysis of continued PFC
operation and the first START during source execution loss, including relay,
downstream load permission, capacitor energy, and absence of UI control.
The present artifacts give no accepted values for either.

## Retrieved power-stage and component inputs

These are inputs to calculations, with their evidence class preserved. The
retained 54-part baseline has no F2, local reservoir, independent voltage
detector, or UCC27624; those are proposed additions, so their values cannot be
treated as installed measurements.

| Input | Available evidence | Use and unresolved parameter |
| --- | --- | --- |
| Line and load | 108–132 Vac, 15 Arms and 40 °C cooling inlet are requirements; 1.8 kW is an AC-input class. The nominal single bus is 389.615 V. | Obtain source impedance/transients, line and load waveforms, temperature at the parts, permissible PFC continuation and downstream permission before deriving reset or link allowable time. |
| Current path | Baseline UCC28180D, HCSM2818FT10L0 10 mΩ shunt, Würth 760800301 180 µH nominal inductor, STW65N65DM2AG switch and C3D20065D diode. | Actual `L(I,T)` over the fault trajectory, sense-filter initial state and transient current at detector assertion are unknown. The 43 A saturation figure is typical at 30% L reduction, not a guaranteed fault-current bound. |
| PCL threshold | UCC28180 input-referred PCL magnitude: 0.400 V typical, 0.438 V maximum. The F2 audit calculates 44.242 A with 1% shunt initial tolerance and a conditional 44.562 A with assumed −40 to +100 °C shunt body and ISENSE-bias behavior. | These are threshold calculations, not peak current. Obtain applicable controller blanking/PCL-to-gate maximum and shunt temperature/bias applicability or add an independent bounded detector. |
| Voltage/energy nodes | VB has four 450 V-rated electrolytics. A 22 µF ±10%, 630 V VD reservoir and F2 are proposed. VD's 500 V screen and 19.8 µF nominal-tolerance floor are conditional. STW and diode are 650 V-rated. | Derive **separate** derated VD, VB, VDS and diode-reverse limits, actual effective C/ESR/ESL, overshoot, and energy after gate disable. The 450 V VB rating does not authorize a 500 V bank waveform, and a 650 V switch rating does not by itself authorize a 650 V switching peak. |
| Driver and protection | Rev38 selects HCS21 permission fan-in, LVC1G06 open-drain shunt release, PMBT3904 AUX-biased ENA shunt, UCC27624DDAR, 10 Ω series gate resistor, 10 kΩ gate pull-down, and STW65N65DM2AG in a compiled partial stage. The HOT TPS3431 WDO and dual TPS3890 rail RESET outputs join the retained trip fan-in. The latter use 294 kΩ/100 kΩ and 1.02 MΩ/100 kΩ dividers for nominal 4.531 V logic5 and 12.88 V AUX falling thresholds, respectively. UCC28180 PWM, boost, F2 and local/bank capacitors now join the same candidate. Published delays use different fixtures; STW turnoff is typical at a different gate drive. Rev35 instead uses UCC27511A. | Establish AUX and HOT rail ranges, supervisor threshold/CT/delay corners, shunt OFF clamp at temperature, base/open fault behavior, watchdog low-pulse capture, filter, loaded gate discharge and complete fault-to-current-zero maximum. A fused-board-terminal/CMC/NTC/relay AC-entry topology is now joined, but the off-board F1 assembly, protected AUX source, and thermal/interrupting design remain unqualified. Do not sum incomparable published numbers into a guarantee. |
| AC entry and precharge | Rev38 now joins `1714984` PCB fused-L/N/PE terminal, TDK `B82726S2163N030` CMC, `SL32 10015` NTC, `RT33K012` bypass relay, X2/MOV and one HOT0-to-PE Y1 capacitor to the bridge. The receiver PA2/32 relay output is gated with retained HOT RUN Q in the spare HCS21 channel before the switch; the MOSFET gate has a local pull-down and the coil has a flyback diode. A 20 A Class CC fuse and off-board block are nominated for review; the external inlet harness is not in the Atopile PCB source. | Build and electrically qualify the actual fuse/block/harness and protected AUX source; derive inrush/precharge/relay timing, repeated-start thermal behavior, F1/F2 clearing and MOV coordination. The relay cannot be treated as a fault-current interrupter. See `AC-INPUT.md` and `F1-SCREEN.md`. |
| Source/HOT watchdogs | Both joined TPS3431 instances use Murata `GRM1885C1H102JA01D` 1 nF C0G CWD. TI's 119.82–144.98 ms applies to an ideal 1 nF; initial ±5% C alone widens the conditional calculation to 116.320–149.216 ms. CPU-only reset may retain ESP GPIO/peripheral state. | Complete effective-C/leakage/rail corners and one-shot WDI pulse qualification; prove a finite source post-reset feed tail and receiver last-credit behavior; bound every WDO-to-STW stage. No accepted reset allowance exists. |

Sources: `operating-envelope-05/envelope-contract.md`,
`f2-timing-02/README.md` and `constraints.json`,
`interface-source-reset-32/README.md`, and
`interface-integration-35/README.md`. Each source labels its own modeled,
proposed, typical, and requirement values; this table does not upgrade them.

### Manufacturer timing entries that do not yet bound the installed path

These entries were checked against current manufacturer data sheets for the
selected parts. They are useful for selecting test corners and exposing a
missing bound. They must not be added as though their test fixtures were
the loaded, mixed-supply Rev38 circuit.

| Selected part | Published conditional entry | Gap to Rev38 response bound |
| --- | --- | --- |
| [TLV3202](https://www.ti.com/lit/ds/symlink/tlv3202.pdf) VD/VB channels | At VCC = 5 V, 20 mV input overdrive and 15 pF load, the data sheet lists 55 ns maximum propagation delay over −40 to +125 °C for each output direction. | The actual divider/filter ramp may spend time below 20 mV overdrive; the real fan-in load, valid supply and minimum captured pulse still need bounds. The 55 ns is not a fault-to-clear maximum. |
| [ISO7741FQ](https://www.ti.com/lit/gpn/ISO7742-Q1) / [ISO6742FQ](https://www.ti.com/lit/gpn/iso6742-q1) DWW source/HOT paths | The ISO774x 5 V/5 V table lists 17 ns maximum propagation delay; the 3.3 V/3.3 V table lists 18.5 ns. ISO7741F default-output timing begins after **input** supply falls below 1.7 V; ISO6742F uses a **1.2 V** threshold and has a separate valid-data startup condition. | Rev38 uses 3.3 V on SELV and 5 V on HOT. Same-supply rows do not directly bound that mixed condition. The intermediate rail-decay interval to 1.2 V, output-side loss of drive, local pulls, startup and rail-order captures are unbounded. |
| [UCC27624](https://www.ti.com/lit/ds/symlink/ucc27624.pdf) driver | The March 2026 data sheet lists 27 ns maximum disable propagation from EN low threshold to 90% of output fall, with 1.8 nF load, 12 V VDD, 0–3.3 V switching input, 500 kHz and 125 °C fixture. | Rev38 uses an AUX-biased EN shunt, 10 Ω gate resistor and actual STW gate charge. That entry does not bound shunt release, loaded gate discharge, switch-current fall or supply-collapse behavior. |
| [LTC4368](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf) protected-AUX cutoff | UV/OV to FAULT is 1–2 µs at 50 mV overdrive and VIN = 12 V; UV/OV GATE turn-off is 2–6 µs with 2.2 nF CGATE. UV/OV-to-reconnect delay is 22–45 ms at VIN = 12 V. Overcurrent fault to GATE = 0 V is 3–18 µs with 2.2 nF CGATE and the specified sense overdrive. | Rev38 has 10 nF CGATE, a 22 kΩ series gate resistor, FDS3992 gate charge and 30.6 µF nominal downstream AUX capacitance. The published fixtures cannot bound driver VDD peak, FET turnoff, shunt current, logic5 decay or STW current cessation; measure each event under actual slew/load. |
| [TPS3431](https://www.ti.com/lit/ds/symlink/tps3431.pdf) source/HOT watchdogs | The manufacturer's 1 nF **ideal capacitor** calculation is 119.82–144.98 ms for device timeout. | Selected CWD tolerance/effective value, pin leakage, boot/last-edge behavior and WDO-to-current-zero remain outside this calculated interval; it is not an allowable reset time. |
| [SN74LV221A-Q1](https://www.ti.com/lit/ds/symlink/sn74lv221a-q1.pdf) source WDI one-shot | At 3.3 V ±0.3 V, −40 to 125 °C, 10 kΩ/10 nF and 50 pF output load, Q/Q_N pulse width is 90–110 µs. [TPS3431](https://www.ti.com/lit/ds/symlink/tps3431.pdf) requires at least 50 ns WDI pulse duration. | Rev38's X7R effective C, resistor corners, actual WDI load, input thresholds and rail transients remain unbounded. This establishes neither a boot-edge count nor a post-reset feed-tail maximum. |
| [TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf) source/HOT rail supervisors | Recommended VDD operating range begins at 1.5 V. The SENSE-to-RESET timing entries assume 5% input overdrive and specified supply; MR requires at least 1 µs low to guarantee RESET. | Rail-slew time before the threshold, narrower overdrive, divider/filter response, powered downstream pull-ups, output behavior as VDD falls below 1.5 V and actual latch capture remain outside a whole-path bound. |

The ISO774x supply distinction and the UCC27624 loaded-gate distinction
must stay explicit in every later timing sum. Where a selected part lacks a
guaranteed maximum at the installed condition, obtain a supported bound or
leave `T_implementation,worst` OPEN. A prototype capture can test a design
but cannot by itself manufacture a missing production-corner guarantee.

The wider-package pair now joined in the `source-build-05` BOM is
`ISO7741FQDWWRQ1` plus `ISO6742FQDWWRQ1`. This is a source candidate, not
a physical timing or PD3 insulation qualification. The latter specifies up to
0.3 µs after its input VCC falls below **1.2 V**, whereas ISO7741F uses
**1.7 V**. The rail-decay time between those thresholds and the actual HOT
output defaults are unbounded; no 0.3 µs figure can be inserted directly
into a Rev38 fault-response sum. The ISO6742 also has a specified startup
valid-data delay from UVLO. See `INSULATION-BASIS.md` and the
[TI ISO6742-Q1 data sheet](https://www.ti.com/lit/gpn/iso6742-q1).

## Per-fault work ledger

| Fault class | Independent allowable-time derivation | Candidate implementation path and missing bound | Required closure evidence |
| --- | --- | --- | --- |
| ESP execution loss; control-link loss | Bound consequences of a first START and continued RUN, plus downstream interfaces and stored energy; define the earliest unacceptable state. | Source watchdog/receiver liveness, source PERMIT clear, isolated loss observation, HOT latches, EN, loaded STW. WDI feed tail, selected timing parts, communication detection and complete shutdown are unset. | ESP reset/queue/other-core tests; selected-part corner analysis; synchronized source WDO, PERMIT, HOT clear, EN, gate and current capture. |
| Overcurrent that requires latched stop | Derive from actual sense threshold/error, maximum current at the evaluated threshold, line voltage, guaranteed incremental `L(I,T)` during growth, switch/shunt/inductor/interconnect derated current and energy limits. | The selected UCC28180 PCL terminates the **active PWM cycle** subject to leading-edge blanking; the Figure 26 300 ns annotation is not a guaranteed maximum. SOC adjusts its current loop. Neither is a physical retained HOT trip producer in the joined source. A separate qualified producer or a demonstrated safe nonlatched current envelope is still needed before there is a retained-clear timing path. PCL-to-gate maximum and loaded current fall are unset. | Decide whether overcurrent is session-invalidating from the independent hazard envelope; then join and audit its retained producer if required. Obtain current-sense corner calculation, source-backed `L(I,T)`, worst-phase waveform and sustained current-cessation evidence. |
| F2 opening, VD/VB mismatch, absolute OV | Derive permissible delay from installed VD reservoir effective C, `Lmin/Lmax` over trajectory, current at threshold, maximum rectified input, initial VD/VB, derated voltage ceiling, and commutation/remaining line energy. | Divider/filter, TLV3202 outputs, HCS combining/retained clear, UCC27624, loaded STW. Applicable filter ramp delay, pulse capture, and loaded current fall are unset. | Recompute envelope at accepted corners; synchronized VD/VB, inductor current, detector, latch, EN, gate and switch-current traces, including F2-open startup and RUN. |
| HOT logic or driver rail failure; isolator partial power | Determine the last supply level at which each output has guaranteed control and the rail slew/ripple/hold-up envelope; require inhibition before control guarantee is lost or a default-off path through the gap. | TPS3890/AUX fast comparator, POR, local EN bias, isolation defaults, driver UVLO. The TPS3890's normal VDD range starts at 1.5 V; UCC27624 can remain active on its independent AUX rail (4.5 V minimum recommended VDD) while HOT logic5 is absent. Intermediate-supply behavior and rail-order propagation are unset. | Selected rail/source envelope, device corner limits, powered-driver/unpowered-logic test, every relevant rail order and isolator-power permutation. |
| Physical PERMIT loss, STOP, receiver abort/reset | Derive the permitted continuation time from the function of the command/interlock and current power-stage state; distinct from a voltage-only detector limit. | Source readback-seen clear, HOT PERMIT-seen clear, `RECEIVER_ABORT_N`, retained latches, EN, loaded STW. Pulse/capture and reset-to-abort maxima are unset. | Exact-pin joined clear path, adverse pulse/reset/clock tests, synchronized hardware permission and current capture. |
| Failed-short STW, failed-short boost diode, stored-bank discharge | Gate disable cannot interrupt a failed-short channel or discharge VD/VB. Derive F1/F2 and interconnect interruption/withstand and stored-energy containment instead. | No valid gate-to-current-zero path for the failed device. | Separate fuse/interconnect/thermal/energy qualification; do not record a passing gate timing for this row. |

### Missing-input owners and evidence class

These are engineering owners of the missing input, not an approval delegation.
Every gate-interruptible row still needs its own independently supported
`T_allowable`, `T_implementation,worst`, and margin. A part maximum applies
only at its stated test conditions. `fault-response.tsv` identifies the
individual physical producer and clear for each event; the groups below
assign the remaining measurements and calculations.

| Fault-response event IDs | Allowable-time input owner | Implementation-time input owner | Evidence now / needed |
| --- | --- | --- | --- |
| `VD_OV`, `VB_OV`, `VD_GT_VB`, `VB_GT_VD`, `F2_OPEN` | Power-stage design: separate derated VD/VB/VDS limits, effective C, `L(I,T)`, fault current and line/source envelope; F2/interconnect owner for noninterruptible paths | Analog-protection design: divider/filter and capture corners; driver design: loaded EN/gate/current fall; bench owner: coincident F2/voltage/current traces | Joined pins and a conditional F2 model; no direct F2 continuity observation, accepted installed limits or complete path capture |
| `PFC_PCL_OVERCURRENT` | Power-stage safety owner: determine whether current beyond PCL is a session-invalidating fault from derated switch/diode, shunt, inductor and interconnect limits over the complete line phase and controller cycle | PFC/protection owner: obtain an actual maximum for PCL blanking/response and any additional threshold/filter/driver time; if retained shutdown is required, join an independent physical producer into HOT trip fan-in; bench owner: shunt/current/PWM/retained-Q/EN/gate/current capture | UCC28180 internal cycle termination is joined; Figure 26's 300 ns blanking annotation is not a guaranteed maximum; no retained overcurrent producer or end-to-end bound |
| `AUX_UV_FAST`, `AUX_OV`, `AUX_UV_SLOW`, `LOGIC5_UV`, `SELV_RAIL_UV`, `SOURCE_HEALTH_LOSS` | Supply design: qualified AUX, logic5 and SELV operating envelopes, rail slew, hold-up and last guaranteed control voltage | Supply/protection design: joined source, regulator, cutoff, logic5 converter, supervisors and window thresholds/delays; bench owner: rail-order and loaded-disable traces | AUX/logic5 Atopile pins joined and audited; SELV producer, physical source envelope, fast-fault peak and complete current-cessation response absent |
| `INTERLOCK_LOSS`, `HOT_PERMIT_LOSS_BEFORE_HIGH`, `HOT_PERMIT_LOSS_AFTER_HIGH`, `SOURCE_READBACK_LOSS`, `HOT_FAULT_DURING_PREP`, `REVALIDATION_RACE` | System safety owner: permitted continuation in each power-stage state | Interface-logic design: pulse/capture, retained clear, isolator and reset dominance; bench owner: adverse edge order and current trace | Pin-level joins and mutation tests; no minimum captured pulse or maximum physical response |
| `RECEIVER_STOP_READY`, `RECEIVER_STOP_RUNNING`, `RECEIVER_RESET`, `RECEIVER_EXECUTION_LOSS`, `PROTOCOL_ABORT`, `PREPARATION_TIMEOUT`, `START_TIMEOUT`, `LINK_LOSS` | System safety owner: permitted continuation for each command/interlock state | Receiver firmware and AVR adapter owner: reset default, decoder/timer/queue-to-pin bound, WDI stop; interface/bench owner: retained clear and loaded-current response | Host logic and runtime tests; AVR pin, fuse, watchdog, and physical capture absent |
| `SOURCE_EXECUTION_LOSS`, `ESP_CPU_RESET_RUNNING`, `ESP_CPU_RESET_FIRST_START` | System safety and power-stage owners: independently derive first-start and already-running allowable time | ESP driver owner: last post-reset WDI edge, boot/other-core/queued writes; hardware/bench owners: TPS3431 corners through source/HOT clear and current cessation | Host source core plus partial pin paths; feed tail and both allowable times unbounded |
| `ISOLATOR_PARTIAL_POWER`, `DRIVER_WITHOUT_LOGIC` | Supply/driver safety owners: last voltage at which output control is guaranteed and tolerable continuation | Isolation, rail and gate-driver owners: partial-power default, clamp strength, EN/gate/current response; bench owner: every rail-order permutation | Partial topology and conditional data; no intermediate-rail or physical path proof |

For every row the margin owner is the system safety review: choose an
uncertainty method only after the hazard and implementation evidence exists.
The acceptance test remains `T_implementation,worst(f) + T_margin(f) <=
T_allowable(f)`. No row has a numerical PASS. A missing producer or an
unbounded input makes its row OPEN regardless of a fast device-only number.

The fault/event rows in `fault-response.tsv` keep individual detector and
transaction cases visible. This ledger groups them only where they share a
hazard model; it does not merge their electrical producers or capture minima.

The event ledger's evidence-status column now reflects the joined Rev38
pin paths. Its `UNSET` capture and cessation columns still mean that a
compiled path has no established analog response bound. In particular,
the F2-open row has no direct continuity sensor; equal VD/VB after opening
can precede a later voltage fault without producing a mismatch now.
The new `PFC_PCL_OVERCURRENT` row makes an existing gap explicit: a
controller-internal cycle limit is not a HOT retained fault. If the
independent current/energy envelope requires a latched stop, the candidate
must gain a physical retained producer and its own threshold-to-current-zero
bound. No current fault may be marked covered by borrowing the voltage-trip
path while that producer is absent.

## AUX producer decision gate

The protected AUX and HOT logic5 ports now have a joined Atopile producer
candidate, but no installed or physically qualified producer. The new
[cutoff record](AUX-CUTOFF-CANDIDATE.md) identifies its divider, FET,
shunt, inrush and measurement gates; its static endpoint screen cannot be
used as a fault-to-current-cessation bound.
The historical `controller-integration-06/supply` proposal uses
IRM-10-24 → TPS7A4701 15 V → TPS54202 5 V. The later Rev19/20
LT4363-1 clamp is a separate downstream proposal, not an interchangeable
substitute for choosing and qualifying that raw source. The
`interface-dynamics-23` model latches off for its artificial 150 mA,
20 ms startup pulse while its 5 ms pulse recovers. The later
`docs/evidence/2026-09-22-power-entry-selection-review/supplies.md`
selects **evaluation** of TPS26601 after the 15 V regulator as a different
cutoff proposal. [The Rev38 OVP window screen](AUX-OVP-WINDOW.md) now shows
that no ±1% divider can both recover at the 15.75 V normal-rail high end
and trip below the provisional 18.0 V screen. The suggested 130 kΩ/10 kΩ
divider fails recovery at a healthy 15.75 V rail. A static window exists
with ±0.1% parts, but its leakage-inclusive example leaves only about
48 mV recovery and 68 mV trip headroom before dynamic effects. No OVP
divider is adopted or qualified. The [Rev38 source comparison](AUX-SOURCE-CANDIDATE.md)
now places IRM-20-15 direct output beside the joined IRM-20-24 raw source
and LMR36015BRNXT 15 V pre-cutoff buck candidate; the LTC4368 disconnect
and TPS54202 5 V converter are now joined engineering candidates.
The direct path's conditional 50 °C screen has only 62.5 mV on each side
of the normal window before cutoff-path loss. The regulated path has about
388/411 mV of low/high feedback-only static margin in an illustrative
100 K adverse resistor-temperature screen; its full dynamic and fault
envelope is unknown. The joined candidate and remaining proposals require the
actual converter and relay startup loads and a bounded raw/regulator fault
waveform before one protection path can be adopted. The 20 ms model outcome is not a measured failure of
a selected assembly.
The divider's maximum independent resistor deviation is only 0.32663%
before leakage. A common ±0.1%, ±25 ppm/K discrete-resistor pairing can
reach ±0.35% per resistor at 125 °C from a 25 °C reference, closing the
static window; ratio tracking and lifetime drift must be specified before
such a candidate is joined as a selected cutoff.
The same TPS26601 also has a factory UVLO rising range of 14.25–15.75 V;
the historical 15 V LDO's specified low static output is 14.625 V. The
factory UVLO connection may never start at that valid output corner. A
joined candidate needs an external UVLO threshold checked with the OVP,
HOT rail detectors, and startup behavior; it cannot use the factory setting
as an unreviewed default.

Select one source chain and prove its normal and fault output envelope,
current limit, startup ordering, and thermal behavior at the Rev38
consumers. Then evaluate the selected cutoff's delay, OVP/UV threshold,
downstream overshoot and restart behavior, plus the LTC4368 external FET
sense, gate drive, and SOA if it is selected,
the 13.25/16.50 V nominal AUX-window thresholds, both TPS3890 rail
thresholds, and the driver's intermediate-supply OFF condition. The AC
input's 15 Arms route does not independently define the low-voltage AUX
fault waveform or permissible supply-loss interval.

One joined AUX load can now be bounded conditionally: the selected
[RT33K012 relay](https://www.te.com/en/product-2-1393240-3.html) has a
published **360 Ω nominal** coil. Through Rev38's 91 Ω series resistor,
an ideal 14.25–15.75 V AUX rail yields `I = V/(360 + 91)`, or
**31.60–34.92 mA** while energized. This is not a worst-case load or
pickup proof: coil/resistor tolerance and temperature, the actual AUX
envelope, flyback/release behavior, and the separate gate-charge, PFC
controller, logic5 buck, comparator, pull-up and capacitor-startup loads
are not yet included. The TPS26601 current limit and startup ramp cannot
be chosen from the historical 115.74 mA budget alone.
Command deadlines are separate authorization limits derived from the hazard
and communication envelope. A healthy heartbeat cannot extend START expiry.

Rev38 receiver revalidation now waits for a fresh physical
`HOT_SESSION_CLEAR_N` sample after abort release. This avoids requesting a
clock while the clear is known low; it does not replace the asynchronous
fault-to-clear path or add a supported time bound. The UCC27624 ENA corner
gap is tracked in `gate-enable-corners.md`: the new AUX-biased shunt is a
pin-level default-off candidate, but PMBT3904 hot/cold saturation, the
UCC's internal EN pull-up maximum, and intermediate HOT-rail collapse still
prevent an analog OFF proof.
The joined Atopile candidate also has a finite-edge preparation-abort
reset, a six-input HOT trip fan-in, physical-PERMIT-loss detection, separate
SESSION/RUN retained latches with raw request clocks, and a separate physical-PERMIT-seen
memory. The latter's asynchronous preset is asserted by PERMIT high even
during its reset pulse, subject to an unproved minimum pulse width and
rail/logic corners. The history-reset D input now requires post-trip
disarm Q high, RUN/PERMIT low, healthy trip fan-in and asserted receiver
abort at the raw clock edge. ACK remains a receiver-firmware prerequisite;
the electrical setup/hold and coincident-trip cases remain open. These paths provide no
numerical implementation bound until missing producers, selected-part
corners and physical response are established.

`F2-DETECTOR.md` records the four-channel VD/VB topology and its open
threshold, pulse and power-state analysis. The VD/VB nodes now join
`PFC-POWER.md`'s boost, F2, 22 µF local film reservoir and 450 V bulk bank.
The off-board fuse/holder and terminal, thermal path and physical response are not
qualified; the earlier F2-open screen remains conditional.
`PFC-CONTROL.md` records the newly joined UCC28180 PWM and VSENSE inhibit
topology. Its clamp resistance, controller open-loop-protection delay,
cycle-by-cycle current-limit behavior and physical commutation are not a
retained overcurrent trip or an accepted response bound.
`AUX-WINDOW.md` records the separately joined fast-dip and OV candidate,
whose 13.25 V and 16.5 V nominal crossings and part delays do not establish
an allowable AUX range or qualified fault response.
`HOT-RAILS.md` records the selected HOT undervoltage producer topology and
an illustrative static threshold screen. Its 100 pF CT values and nominal
trip points do not establish rail-failure detection or capture time. The
IRM-20-24, LMR36015, LTC4368/FDS3992 and TPS54202 supply path is now
joined as an engineering candidate. Effective capacitance, startup load,
fast-fault peak, FET SOA and rail-order response remain unqualified. The
Rev38-side controller header and a separate cooker-mate source derivative
have an exact-pin digital join. `SELV-PORT-CONTRACT.md` defines candidate
voltage and load-allocation requirements, but the cooker rail, native harness,
startup and partial-power behavior are not qualified.

## Existing conditional F2 screen — not an accepted limit

`f2-timing-02/constraints.json` records null for actual fault-current bound,
end-to-end shutdown bound, `Lmin/Lmax`, and installed voltage ceiling. Its
illustrative screen assumes 132 Vac crest, 410 V bank, 19.8 µF local
capacitance, 50 A at the evaluation threshold, `Lmin=100 µH`, `Lmax=216 µH`,
and a provisional 500 V ceiling. After a 20 mV comparator-overdrive reserve,
it calculates 2.526807 µs of conditional delay; 2 µs is only a provisional
design target. The circuit's detector/filter, loaded STW turnoff, and physical
fault current are not bounded. No one may copy those values into
`T_allowable` or mark this ledger PASS.

That model starts **at a voltage evaluation threshold**, with 50 A already
assumed there. It does not bound the time from the physical F2 opening to the
first detected VD/VB crossing. For an F2-open response claim, record both
`t_open → t_threshold` (including an initially equal VD/VB pair, light-load
or startup operation) and `t_threshold → sustained current zero`; include
the intervening current and capacitor energy in the initial state for the
second interval. If no qualified threshold crossing is guaranteed before a
hazardous state, a fast downstream comparator cannot close detection
coverage. The power-stage owner must either show every hazardous F2-open
case generates a timely voltage/current observation or add a direct
continuity/independent startup-inhibit mechanism. This distinction is also
required for an overcurrent model: a PCL threshold crossing after a fault
onset cannot erase the prethreshold energy.

For the selected F2-open model, the engineering calculation to repeat with
supported limits is:

```text
I_end = I_at_threshold + V_in_max / L_min * T
V_end = V_at_threshold + I_end / C_min * T
V_peak = V_in_max + sqrt((V_end - V_in_max)^2 + L_max/C_min * I_end^2)
T_allowable = greatest T for which V_peak plus uncertainty stays below
              the derated installed voltage limit at every accepted corner
```

This model assumes a healthy controllable switch and boost diode and excludes
ringing, wiring spikes, fuse arcing, and failed-short energy paths. If those
terms matter at the chosen limit, expand the model or qualify them separately.

## Next evidence to collect

### Synchronized capture definitions for the later physical campaign

The following is a measurement design, **NOT RUN**. Use the Rev38
[bench-capture procedure](bench-capture.md) for article identity, fixture,
simultaneous-channel and verdict records. Use an assembled, isolated
low-voltage fault-injection fixture before any mains evaluation.
The final joined schematic and native board must name accessible test points
and injection points; a simulated node or an ESP log timestamp cannot stand
in for a physical transition. Record the injected waveform, probe loading,
channel skew, trigger uncertainty, supply/temperature corner, component
identities, and source/board/runtime hashes with each capture.

For a gate-interruptible event, mark `t0` at the physical fault crossing or
execution-loss stimulus, `t1` at the qualified detector/watchdog output,
`t2` at retained HOT clear, `t3` at driver EN inhibit, `t4` at the loaded STW
gate's OFF crossing, and `t5` at **sustained switch-current cessation**. The
implementation bound is `t5−t0` at accepted worst-case corners; a single
fast trace only supplies an observation. State separately whether capacitor
or inductor energy continues elsewhere after `t5`.

| Fault path | Stimulus and synchronized channels beyond `t1`–`t5` | Necessary distinction |
| --- | --- | --- |
| ESP execution loss, already RUNNING | External CPU-loss marker; heartbeat-request pad; one-shot active-low WDI; TPS3431 WDO; source PERMIT Q; HOT physical PERMIT, SESSION Q and RUN Q; loaded gate and current. | Measure the last *qualifying* WDI edge after `t0`, including boot/other-core and retained-pad behavior. Preserve the original watchdog interval. |
| ESP loss with first START pending | The same channels, plus TX FIFO-empty indication, physical final TX stop bit, isolated command RX, receiver START acceptance and RUN-set request. | Distinguish `uart_wait_tx_done()`'s documented FIFO-empty condition from final wire-bit completion. Show at most one pre-reset committed START before its fixed deadline; a first RUN transition cannot restart the reset-to-off clock. |
| Source preparation edge timing | Physical P0 challenge and P1 history-reset request edges, I²C SDA/SCL transactions and acknowledgements, STOP_N, local permit and HOT feedback, and receiver abort. | Runtime reserves a configured bound before requesting the edge; measure the complete sample-to-positive-edge path, including prior write/readback transactions, to validate that bound. A post-edge check cannot retract a late pulse; the candidate 5 ms transaction timeout is not a measured edge bound. |
| Link loss or receiver execution loss | Last valid complete frame, receiver WDI/WDO, AVR RESET and abort_N, physical PERMIT, SESSION/RUN Q, EN, gate and current. | Distinguish no traffic, malformed traffic, and a stalled decoder; determine the actual last liveness credit. |
| VD/VB overvoltage, mismatch, or F2 opening | VD_LOCAL, VB_BANK, inductor current, F2 voltage/continuity, actual comparator inputs and outputs, HOT trip fan-in, retained Q, EN, gate and current. | Use the first physical voltage/current violation as `t0`; capture input filtering and any energy-driven peak after gate disable. |
| Overcurrent | Shunt differential voltage, controller ISENSE/PCL behavior, inductor and STW current, PWM, HOT retained Q, EN and gate. | A cycle-by-cycle PWM limit is not automatically a latched trip; only a demonstrated retained producer gets a retained-clear timing row. |
| AUX/logic/SELV rail loss or partial isolation power | AUX raw/protected, HOT logic5, SELV3V3, both TPS3890 RESET nodes, AUX-window output, isolator output, AVR reset/abort, EN, gate and current. | Sweep rail order and slew through each device's last guaranteed operating region; check powered driver with absent HOT logic. |
| Physical PERMIT break, STOP or receiver abort | Source local Q and STOP_N, both sides of the relevant isolator, HOT physical PERMIT, seen memories, SESSION/RUN Q, EN, gate and current. | Test before first PERMIT high and after seen-high, plus short pulses and coincident reset/clock edges. |
| Failed-short switch/diode or stored-bank discharge | F1/F2 terminal currents/voltages, interconnect temperature, VD/VB energy and enclosure-relevant paths. | There is no valid `t5` from gate disable for the failed channel; use separate interruption and containment criteria. |

Derive each `T_allowable` from the independently accepted operating envelope
and component limits **before** comparing it with these implementation
captures. The F1/AC, AUX, AVR and ESP work streams provide candidate parts,
pin ownership and corner conditions; their findings do not fill a timing
cell until the final joined circuit and physical evidence support it.

1. From the retained power-stage design and actual source/part data: accepted
   separate VD/VB/VDS and current/energy/temperature envelopes; effective
   local C over voltage/temperature; guaranteed incremental L range at fault
   current; actual shunt temperature, ISENSE bias applicability, controller
   delay, line/source impedance and operating phase. Record any datum that is
   only typical or modeled.
2. From the joined Rev38 circuit: selected comparator/filter/latch/isolator/
   watchdog/driver parts and values; pulse and clear/clock minima; rail order;
   loaded gate path; exact fault-to-EN and watchdog-to-EN topology.
3. From firmware and protocol tests: reset-time WDI ownership, last-edge
   bound, queue-to-pin behavior, single pre-reset START acceptance, timeout
   nonextension, and physical disarm before deliberate restart.
4. From an assembled isolated low-voltage fixture: simultaneous fault,
   detector, retained-state, PERMIT, EN, loaded gate and current records, with
   measurement uncertainty. Physical status stays NOT RUN until these exist.

Numerical timing acceptance remains OPEN wherever either side of the
inequality or its applicability is unsupported. Engineering may continue on
the separate candidate without treating this ledger as permission to
energize mains.

## Sources

- [TI TPS3431, §§5–8](https://www.ti.com/lit/ds/symlink/tps3431.pdf): WDI minimum pulse, WDO reset duration and ideal-CWD timeout equation/table.
- [TI SN74LV221A-Q1, timing and switching tables](https://www.ti.com/lit/ds/symlink/sn74lv221a-q1.pdf): source B2/Q2_N one-shot reference-fixture pulse.
- [Murata GRM1885C1H102JA01 reference sheet](https://search.murata.co.jp/Ceramy/image/img/A01X/G101/ENG/GRM1885C1H102JA01-01A.pdf): 1 nF C0G, initial ±5% tolerance; [Murata product listing](https://ds.murata.com/simsurfing/mlcc.html?oripartnumbers=%5B%22GRM1885C1H102JA01J%22%5D&partnumbers=%5B%22GRM1885C1H102JA01%22%5D) confirms family identity.
- [TI TPS3890, §§7.3–7.6](https://www.ti.com/lit/ds/symlink/tps3890.pdf): supply and SENSE/MR timing conditions.
- [TI UCC28180, §8.3.12](https://www.ti.com/lit/ds/symlink/ucc28180.pdf): cycle-by-cycle PCL and leading-edge blanking.
- [TI UCC27624, §§5.5, 7.2.2](https://www.ti.com/lit/ds/symlink/ucc27624.pdf): separate AUX-supplied driver operating/UVLO range.
- `docs/superpowers/specs/2026-09-23-power-entry-hot-receiver-design.md`
- `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md` and `constraints.json`
- `zapote/power-entry/passive-reva/protection/f2-open-01/README.md`
- `zapote/power-entry/passive-reva/protection/operating-envelope-05/envelope-contract.md`
- `zapote/power-entry/passive-reva/protection/interface-source-reset-32/README.md`
- `zapote/power-entry/passive-reva/protection/interface-integration-35/README.md`

# Power-entry supply and control contract

Prepared 2026-09-22 from Luna's bounded Block E research and parent source
review. This is a proposed integration contract for comparing circuit
revisions. It is not a completed supply selection or electrical acceptance.
The unchanged candidate has 131 compiled instances; E owns six.
[Previous block review](../2026-09-22-power-entry-block-review/README.md).

**Known** means source wiring or a stated component specification;
**proposed** means behavior or an envelope to design against;
**unknown** means evidence or a decision is still required. Proposed behavior
below must not be read as something RevB already guarantees.

## Source and port ownership

[Candidate ATO](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/source-candidate/elec/src/power_entry_pfc_control_candidate.ato)
lines 221–245 declare all thirteen external signals. Its lines 357–482 wire
them. [RevB ATO](../../../elec/src/power_entry_f2_shutdown_revb.ato) defines
the protection consumers. Both copies and the export are bound in
[source identity](source-identity.json).

HOT0 denotes `control_gnd = hv_minus = aux_15v_return`. It is hazardous bus
negative on the controller side of the shunt. Do not return the auxiliary
assembly to `bridge.MINUS`, which is on the other side of the shunt.

| Source port | Physical interface / domain | Producer or authority → consumers; default or limit |
|---|---|---|
| `ac_l` | mains pin 1, Phoenix 1714984; mains | Line → F1, EMI/inrush/bridge path. Gate-off does not disconnect it. |
| `ac_n` | mains pin 2; mains | Neutral → EMI/bridge return; not a logic ground. |
| `pe` | mains pin 3; protective earth | Protective-earth connection → Y1/chassis boundary. No DC HOT0 bond is present. |
| `aux_15v` | aux pin 1, 61300211121; HOT | External bias producer → UCC28180 VCC, UCC27511A VDD, IN− pullup, standby network, relay path, AUX sensing. Invalid bias must inhibit operation. |
| `aux_15v_return` | aux pin 2; HOT0 | Bias return → HOT0. External isolated producer remains unselected. |
| `logic5` | Bare signal; HOT | One external supply or chosen AUX-derived regulator → three TLV3202 packages, reference/bias, two TPS3890, HCS21/HCS74, two LVC1G08, two LVC1G17, bleed/pullups/bypass. Invalid rail must inhibit. |
| `hot_permit` | permit pin 1, 61300211121; HOT | Named system interlock authority through a defined crossing → permit_buf.A. Active high qualifies clear; required default low. |
| `hot_arm` | Bare signal; HOT | Named sequencing authority through a defined crossing → arm_buf.A/latch clock. Fresh rising edge requests RUN; required idle/default low. |
| `relay_ctrl` | control pin 1, 61300211121; HOT | Named precharge sequencer through a defined crossing → relay-driver gate through 1 kΩ, with local 100 kΩ gate pulldown. High energizes NTC bypass. |
| `control_gnd` | control/permit pin 2; HOT0 | Common control return → controller, driver, logic, sensors and relay driver. Never direct-connect MCU/SELV ground. |
| `local_vd` | Bare signal; HOT high voltage | Boost diode → controller feedback and VD sensing; external F2/reservoir assembly attaches here. |
| `hv_plus` | output pin 1, Phoenix 1714971; HOT high voltage | External F2 from VD → bulk bank, VB sensing, bleeders and downstream load. Distinct from VD. |
| `hv_minus` | output pin 2; HOT0 | Bulk bank/downstream return → controller-side shunt connection and other HOT returns. |

The candidate has five physical connectors including mains; four belong to E.
Bare ports need an assembly connection decision, not necessarily individual
new headers. One authority must own each command; every consumer must be
named. Fanout and a shared multichannel isolator are permitted.

PWM, gate, health_ok, rails_ok, clear_ok, run, fault_clear_n and enable_good
are internal signals. They do not require external telemetry hardware unless
a chosen system function needs it. The controller GATE drives the driver's
input network; UCC27511A drives the power MOSFET gate.

**Known disconnect gap:** RevB lines 385–399 and 440–452 place ARM/PERMIT
pulldowns on buffer outputs. Raw buffer inputs have no explicit local bias.
A disconnected producer therefore has no established fail-low state.
Specify receiver-side input bias and crossing defaults, including unpowered
producer, broken conductor, MCU reset and rail return. Producer-only bias
does not cover a disconnected cable. LVC Ioff behavior at VCC=0 is neither
galvanic isolation nor a complete brownout guarantee.
[TI SN74LVC1G17](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf).

The existing [standalone interlock](../../../zapote/interlock/INTERFACES.md)
uses SELV 3.3 V and a fresh falling RESET_N edge. PFC ARM is a HOT rising-edge
input. Reuse requires a named sequencing coordinator, isolation and verified
logic levels; it is not a direct wire or an automatic transfer of timing limits.

## Rail envelopes and direct loads

**Logic5 known:** the nominal IC supply-range intersection is 2.7–5.5 V:
TLV3202 2.7–5.5 V, HCS logic 2–6 V, LVC logic 1.65–5.5 V and TPS3890
1.5–5.5 V. This excludes reference-bias adequacy and circuit thresholds, so
it is not the valid RUN range. The LM4040 bias loses headroom at low supply.
The 294 kΩ/100 kΩ supervisor divider gives a nominal 4.531 V threshold
using nominal 1.15 V SENSE. Tolerance and delay must be included.
[TLV3202](https://www.ti.com/lit/ds/symlink/tlv3202.pdf),
[HCS21](https://www.ti.com/lit/ds/symlink/sn74hcs21.pdf),
[HCS74](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf),
[LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf),
[TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf).

**Logic5 proposed:** nominal 5 V. Producer tolerance, accepted RUN window,
ramp, dropout, discharge, source impedance and current limit remain unknown.
No intermediate-voltage logic state is assumed valid.

**AUX known:** current UCC27511A recommends 4.5–18 V; UCC28180 recommends
VCCOFF+1 V to 21 V, with turn-on threshold 10.8–12.1 V and turn-off threshold
9.1–10.3 V. These bounds are not a complete assembly envelope. The actual
driver differs from the old UCC27624 proposal.
[UCC27511A](https://www.ti.com/lit/gpn/ucc27511a),
[UCC28180](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).

**AUX proposed:** retain 14.25–15.75 V at the device pins during RUN,
including ripple, cable drop and transients, from the earlier
[interface proposal](../../../zapote/power-entry/passive-reva/INTERFACE-DESIGN.md).
Its IRM-10-15 is a producer candidate only. RevB detects AUX undervoltage
(12.995 V nominal supervisor, 13.25 V nominal fast comparator) but has no AUX
overvoltage channel. Thus the proposed window is not enforced by this source.
Define whether upper excursions are prevented by the selected supply
architecture or independently detected; no deletion may assume that solved.

The following terms are nominal calculations, not a maximum-current budget.
Source: RevB lines 234–245, 311–383, 481–552; candidate lines 419–434 and
470–482. [Arithmetic record](nominal-load-terms.json).

| Direct rail load | Static/state-dependent term | Dynamic/startup terms still needed |
|---|---|---|
| Logic bleeder | V5/220 Ω: 22.73 mA and 0.114 W at 5 V | Resistor tolerance/derating. The source comment's 1 kΩ is stale. |
| Reference and logic divider | (V5−2.5)/10 kΩ while reference regulates: 0.25 mA at 5 V; divider V5/394 kΩ | Reference bias minimum, loads and settling |
| Logic ICs/pullups | Sum state-specific IC currents; each asserted 10 kΩ reset pullup adds about 0.5 mA at 5 V; driven output pulldowns also consume current | Switching current, actual fanout; capacitor charge C×dV/dt |
| Driver disable pullup | Approximately VAUX/1 kΩ while enabled: 15 mA and 0.225 W at 15 V | Transistor voltage, internal pullup, tolerance and transient behavior; not a fixed OFF load |
| Relay coil plus 91 Ω | With nominal 360 Ω coil: 15/451 = 33.26 mA, coil 11.97 V, drop resistor 0.101 W | Coil tolerance/temperature, pickup/dropout, duty and flyback; no relay acceptance implied |
| Controller/driver | State-dependent controller and driver bias; standby/sense-divider and PWM/gate pulldown loads | Driver gate charge Qg×f, controller input-network drive, actual waveform, capacitor charging |

Relay nominal resistance is from [TE RT33K012](https://www.te.com/en/product-2-1393240-3.html).
UCC28180's 8.8 mA maximum operating-current datum uses a 4.7 nF GATE load;
it is not quiescent current to which another full output-load term can blindly
be added. Current candidate frequency has a nominal model value around
129 kHz, not a qualified tolerance bound. Use actual MOSFET charge and drive
conditions for UCC27511A. Include gate/pwm pulldown average current as well
as switching charge. Keep direct logic5 and AUX demand separate until a
regulator architecture is selected, then include conversion losses.

## Required sequencing and faults

These are interface phases, not new firmware states or proof of present
behavior. No numeric rail-dip width, shutdown deadline or startup timeout is
invented here.

| Phase | Proposed behavior and authority |
|---|---|
| OFF | Commands low; gate inhibited and controller standby where bias permits. Mains can still charge VD/VB through bridge, NTC, inductor and diode. Gate-off and an open bypass relay do not isolate mains. |
| QUALIFY | External sequencer keeps ARM low and bypass released while rails/detectors become valid. Supervisor CT is release qualification; nominal ~132 µs is not a guaranteed dropout response. |
| PRECHARGE | Passive charging may already be occurring. Sequencer validates precharge, F2 continuity and residual-charge conditions before bypass/ARM. Equal VD/VB alone does not prove F2 continuity. |
| ARMED | Ready to accept an edge, not a separate hardware latch state. With clear_ok high, a fresh ARM rising edge sets RUN immediately. |
| RUN | enable_good = run AND clear_ok enables the driver and releases VSENSE standby. The named sequencer owns bypass timing. |
| FAULT | Required detector/permit/rail faults dominate ARM, clear retained RUN, disable gate drive and reassert standby. Crossing design must make reset/disconnect request that response. Current source does not prove all brownout/disconnect cases. |
| RECOVERY | Rail return or a previously held-high ARM must not restart. Require renewed qualification and a deliberate fresh edge. No automatic re-arm policy. Check startup edges introduced by powered-down buffers as well as ARM held high during a powered fault. |

Specify relay release timing during faults separately: immediate gate disable
does not justify interrupting current with an unrated bypass contact. A failed-short
MOSFET cannot be cleared by gate command. Local VD energy is outside F2;
stored-energy and fuse coordination remain separate requirements.

## Assembly ledger and next comparison

| Category | Count/status |
|---|---|
| Current exported source | 131 instances, including E's six support components. No reduction in this work. |
| External assembly still needed | Replaceable F1 link, F2/holder/interconnect, local VD reservoir and discharge/treatment, AUX producer/branch protection, logic5 producer, command producer/crossing, necessary raw-input bias and assembly connections. |
| Conditional additions | Diagnostic/test connections only if selected; shared connectors/isolators are allowed. Cooling/mechanical hardware lies outside this electrical census. |

The finished assembly count is unknown. Do not silently count external
assemblies as already installed or require one new connector per bare port.

Before selecting a simpler D circuit, define: (1) accepted rail windows and
disturbance/shutdown timing envelope; (2) raw input bias and command crossing
defaults; (3) who owns precharge, continuity checks and fresh ARM; (4) upper
rail-excursion handling. Physical waveforms, loading, isolation and interruption
qualification remain evidence dependencies.

Next develop **one** D rail/enable consolidation candidate against this
contract. A small loaded-gate fixture should compare rail order, absent rails,
rail loss/return, permit loss, ARM held high, simulated MCU reset/disconnect,
one bus-fault stimulus and a valid fresh ARM edge. Include negative controls
and observe gate, standby and retained RUN. Numeric sweeps stay exploratory
until their bounds are justified. No full-converter run, component deletion or
PCB adoption follows from writing this contract.

## Verification

Parent checked all thirteen source ports, the disconnect wiring, actual device
identity, nominal load arithmetic and primary specifications; seven source
hashes are recorded. Luna completed read-only drafting and was stopped after
handback. No circuit edits, simulation, hardware test, commit or publication
occurred. Existing dirty source documents were preserved.
[Review receipt](review-receipt.json).

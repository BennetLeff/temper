**FAIL for integration: native-17 J4 agrees with its source/netlist and retains the local CT burden, but there is no complete controller/harness counterpart, and 280 V exceeds the bus amplifier's specified linear input range.**

# 06 Controller interface — current native-17 cross-check (D-10)

## Method and evidence identity

Reviewed at `f9b13b483d6d4ed52439d4da419c7670bab6966c` on 2026-10-02.
This is a read-only desk audit of all eight task-06 checks, not permission to
connect or energize an assembly. Source, frozen netlist and native-17 pad-net
assignments agree on all 16 J4 pins and every endpoint on the selected nets.
No PCB, schematic, firmware, old task-01 result or licensed model was changed.
The native-09/native-11 CT record is preserved verbatim below the separator.

- [Extraction script](scripts/interface_check.py) → [complete connector/endpoint evidence](outputs/interface_check.json).
  The JSON records input SHA-256 identities, native pad line numbers, frozen
  netlist entries, the root controller pins, and the last commit changing those inputs.
  It rejects source/netlist/native disagreement instead of treating absent data as success.
- [Arithmetic script](scripts/interface_numbers.py) → [numbers and assumptions](outputs/interface_numbers.json).
  These are explicit resistor/DC calculations; quantities depending on unselected
  hardware or harnesses remain unknown. Python is used only for the requested
  extraction/report arithmetic, not to introduce a production engineering rule.
- Structural references below are repo-relative paths at the review commit;
  `PS` means `zapote/power-stage-120v/`. Every board path and pin reference is
  also present with exact line numbers in the JSON. Component identities come
  from `PS/frozen/default.csv`, corroborated by the native footprint values.

## All 16 pins

Directions are relative to the power board. The verdict covers the complete
interface, not merely the matching local pad label. **NO COUNTERPART** means
no routed/declared receiver or producer/harness for this role; **INDETERMINATE**
means an appropriate candidate exists but its integration conditions are unproved.
**FAIL** means an identified requirement mismatch. The whole assembly fails
acceptance while required counterparts are absent.

All source joins are `PS/elec/src/power_stage_120v.ato:541–556`; frozen netlist
entries are named below, with exact lines in the output. Native J4 starts at
`PS/native-17/section.kicad_pcb:4753`.

| J4 | Actual net / local endpoint | Counterpart and direction | Verdict and one-line reason |
|---:|---|---|---|
| 1 | `v15_selv`, PS1.4 | OUT; root U3.3/.5 (`+15V`) is a possible buck input, not a connector | **NO COUNTERPART** — no selected 15 V receiving connector, cable or complete load budget; do not tie two existing supply outputs together. |
| 2 | `selv_gnd` | Return; potential interlock J2.2/J1.1, current J2.2, thermal J3.2, RTD J2.2/.3, gate-drive J1.4/J5.2 | **INDETERMINATE** — common logic return roles agree; cable assignment, current and second PE bonds unqualified. |
| 3 | `v3v3`, U1.3/.8, U2.3/.8, U4.8, U9.14, CT circuit | IN; root buck U3 is the candidate producer via inductor/output rail; all standalone units consume 3.3 V | **NO COUNTERPART** — no controller supply connector or assembled-system load/power-sequence contract. |
| 4 | `selv_gnd` | Return; same candidates as pin 2 | **INDETERMINATE** — no one-to-one harness mapping. |
| 5 | `pwm_ha`, U1.1 (INA) | IN; root U27.4 (`PWM_HS`, GPIO4); gate-drive J1.1 is another receiver | **NO COUNTERPART** — root half-bridge signal is only a candidate, with no full-bridge phase allocation/harness. |
| 6 | `pwm_la`, U1.2 (INB) | IN; root U27.5 (`PWM_LS`, GPIO5); gate-drive J1.2 is another receiver | **NO COUNTERPART** — same missing allocation/harness and verified dead time as pin 5. |
| 7 | `pwm_hb`, U2.1 (INA) | IN; no second root PWM pair | **NO COUNTERPART** — no leg-B producer or GPIO assignment. |
| 8 | `pwm_lb`, U2.2 (INB) | IN; no second root PWM pair | **NO COUNTERPART** — no leg-B producer or GPIO assignment. |
| 9 | `permit`, R6.1/R14.1 → Q1/Q4 | IN; interlock J2.6 (`permit`) OUT | **INDETERMINATE** — polarity and local pulldowns agree; gate-high guarantee, capacitive fanout, harness and SENSOR_LIVE producer remain open. |
| 10 | `bus_fault`, U13.4 | OUT; candidate interlock J1.2/.3/.8 are active-high fault inputs | **INDETERMINATE** — no input selected; U13 low-level contract is unproven at the interlock pullup load. |
| 11 | `vbus_p`, U4.7 | OUT; root U27.38 (`V_BUS_SENSE`, GPIO2) is single-ended, with its own existing source | **FAIL** — no differential receiver and 280 V falls outside U4's linear input range. |
| 12 | `vbus_n`, U4.6 | OUT; no differential ADC minus input/receiver | **FAIL** — a driven amplifier output, not ground; same range mismatch as pin 11. |
| 13 | `ct_zc`, U12.1 | OUT; no root controller or standalone current-unit input | **NO COUNTERPART** — local zero-cross output exists; no capture pin/firmware consumer or idle-noise policy. |
| 14 | `ct_mon`, R47.2 | OUT; root U27.39 (`I_SENSE`, GPIO1) is only a candidate, already sourced by its own CT | **NO COUNTERPART** — requires a new high-impedance receiver allocation; standalone current J2.4 is an output, not an input. |
| 15 | `selv_gnd` | Return; same candidates as pin 2 | **INDETERMINATE** — no one-to-one harness mapping. |
| 16 | `selv_gnd` | Return; same candidates as pin 2 | **INDETERMINATE** — no one-to-one harness mapping. |

### Every counterpart, including signals not carried by J4

Native connector maps were extracted independently, not inferred from matching names.
These are potential logical correspondences, **not instructions to wire boards**.

| Board and authoritative snapshot | Relevant connector pins | Relationship to J4 |
|---|---|---|
| `zapote/interlock/candidate/section.kicad_pcb`, J1 line 578, J2 line 5842; `INTERFACES.md`, `interface-contract.json` | J2.1 VCC, .2 GND, .3 WDI, .4 RESET_N, .5 SENSOR_LIVE, .6 PERMIT, .7 LATCHED_FAULT, .8 WDT good; J1.2 OCP, .3 OVP, .4 HS, .5 coil, .6 RTD, .7 runaway, .8 AUX; .1 GND | J4.9 has a producer. J4.10 needs one designated fault input. WDI/reset/live and remaining fault wiring need separate harness branches; they are absent from J4. No power-stage independent HOT5/live-valid signal exists here. |
| `zapote/gate-drive/candidate/section.kicad_pcb`, J1 line 4256, J5 line 1196; `INTERFACES.md` | J1.1 PWM_H, .2 PWM_L, .3 PERMIT, .4 CTRL_GND; J5.1 3V3, .2 CTRL_GND; J2.1 isolated 15 V, .2 gate-L Kelvin | This unit duplicates one on-board bridge driver. PWM/PERMIT are inputs on both boards. Its HOT-side J2 supply must **not** be identified with J4.1 SELV 15 V. No VBUS/CT/BUS_FAULT input. |
| `zapote/current-sense/candidate/section.kicad_pcb`, J2 line 2429; `INTERFACES.md` | J2.1 3V3, .2 GND, .3 OCP_FAULT OUT, .4 SENSE_MON OUT; J1 primary-current lands | No CT secondary or CT_MON input. Its own transformer/burden measures a separate primary path. Never join J2.3 or J2.4 to the power-stage outputs. |
| `zapote/thermal-sense/candidate/section.kicad_pcb`, J3 line 6475; `INTERFACES.md` | J3.1 3V3, .2 GND, .3 HS_FAULT OUT, .4 COIL_FAULT OUT, .5/.6 analog monitors | Only shared supply/return roles map to J4. Thermal faults belong on interlock J1.4/.5 via a branch. Do not wire push-pull faults together on BUS_FAULT. |
| `zapote/rtd/unit/candidate/section.kicad_pcb`, J2 line 4730; `unit/HANDOFF.md:24` | J2.1 3V3, .2/.3 GND, .4 SCK, .5 SDI, .6 SDO, .7 CS_N, .8 DRDY, .9 HW_FAULT, .10 REF_2V5 | Only supply/return roles map to J4. SPI/DRDY require a controller branch; HW_FAULT needs interlock J1.6; shared reference needs an explicit consumer/load contract. The older circuit proposal is not the final unit authority. |
| `pcb/temper.kicad_pcb`, U27 line 7757, U3 line 7847; `elec/src/modules.ato:3580`, `elec/src/main.ato:808` | U27.4/.5 two PWMs; .38 bus ADC, .39 current ADC; .2 3V3; U3.3/.5 15 V | Integrated half-bridge controller, not a separate connectorized four-PWM board. Existing ADC nets already have sources (`main.ato:833,871`). Root J1 is the RTD probe and J2 the fan, neither a J4 mate. Read-only throughout. |

`zapote/ports.toml:3` onwards is a **software donor-port ledger**, not an
inter-board electrical harness manifest. `zapote/project.toml:13` onwards
only points to shared project directories. Neither declares a J4 cable,
net mapping, rail owner, return allocation or missing controller producer.

## Checks 1–4: mating, power, levels and defaults

**Mating.** J4 is Molex 0430451612. The Molex
[430250000-SD Rev A, sheet 1](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/430/43025/430251600_sd.pdf)
shows circuit identifiers and names the 43045 mating family (notes 5/6/11).
A 43025-1600 housing is a possible mate, not a selected cable assembly.
No cable part number, crimp/AWG choice, drawing or far-end 16-pin mate is
committed. Therefore a claim that a “straight 2 × 8 cable” maps pin 1 to
pin 1 is **INDETERMINATE**: mating-face and wire-entry views reverse the
viewing direction. Build a numbered continuity schedule from both drawings;
never infer it from row appearance or the photograph.

**Supply ownership/current.** PS1 alone generates `v15_selv`; its only
other net endpoint is J4.1. PS2 supplies the separate HOT-side gate rail.
[Mean Well IRM-20 specification, 2025-11-21, p2](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF)
rates IRM-20-15 at 15 V, 1.4 A / 21 W, subject to p3 derating.
The existing root controller's LMR51430 is a possible downstream converter
([TI SLUSEF4A, pp1,4](https://www.ti.com/lit/ds/symlink/lmr51430.pdf):
4.5–36 V, 3 A), but silicon rating does not establish usable board capacity.
Its full-board 15 V rail already has supply owners (`main.ato:690–703`).
No approved reconnection/isolation of those owners, external load census,
converter temperature/efficiency, inrush or cable current budget exists.
Thus neither the 15 V total load nor the controller's spare 3.3 V capacity
has a defensible system bound.

J4.3 also powers the new CT comparators/bias/OR, omitted from the old task
text. The selected **DC allocation subtotal is 41.657 mA on native-20** (27.445 mA on native-19), using 3.465 V
and resistor minima. Components of that subtotal (mA): U1/U2 9.6, U4 7.2,
U9 1.2, U10–12 0.18, U13 0.010, both DIS pullups 21.212 (330 Ω, native-20; 7.0 at 1 kΩ), bias divider 1.734,
references 0.521. Device conditions are in the source table below. This
subtotal is **not a full-board upper bound**: PWM/supply dynamics, driver DT
current, cable charging, output loads, clamps, startup and all other boards
are not bounded by it. A controller allocation must explicitly include them.

**PWM logic.** UCC21550 thresholds require high ≥2.3 V and low ≤0.8 V;
its 50 kΩ minimum pulldown draws at most 69.3 µA per input at 3.465 V.
ESP32's high-impedance output limits give 2.508 V high and 0.3465 V low
at the supply corners by applying its fractional-voltage limits. Its table
is specified at 3.3 V, 25 °C. These clear the thresholds as a conditional
screen, not an all-temperature loaded guarantee. The ESP table specifies high-impedance loading, so this is a
compatibility screen, not a guarantee at arbitrary harness/loading. Qualify
all four actual outputs, ground offsets and edge rates; no extra signal
buffer exists on the power-board PWM nets.

**PERMIT.** Interlock J2.6 is active-high from the SN74LVC1G74 Q output
(`source-build-02/elec/src/interlock_unit.ato:305`). Both receivers have
100 Ω series, 100 kΩ gate pulldown and 1 kΩ DIS pullup. Static receiver
load is ≤69.93 µA; including the interlock's own 10 kΩ pulldown it is
≤419.93 µA at the adopted resistor/rail corners. Two AO3400A gates add
capacitive turn-on current. AO3400A specifies RDS(on) at VGS=2.5 V
(48 mΩ maximum, 25 °C), not at its threshold. LVC1G74's 3 V rail
VOH guarantee at −16 mA is 2.4 V; the VCC−0.1 V row applies only to
−100 µA. The actual lightly loaded output will likely be higher, but the
published rows do not directly prove ≥2.5 V at this combined load.
This is an **unclosed guarantee**, not evidence the FET fails to turn on.
Do not use threshold voltage as a guaranteed on-resistance specification.

**BUS_FAULT.** The header is driven by **U13**, not U9. The ISO7710's
VCC−0.3/0.3 V limits quoted in `FAULT-INTERFACE.md` apply at the U13 input.
U13's 3 V table guarantees VOL≤0.4 V at 16 mA, whereas the interlock
contract requires ≤0.3 V and its worst pullup load is 350 µA. Its 0.1 V
row stops at 100 µA. Interpolating a typical curve cannot close that gap.
High state is compatible conditional on the contract's ≤20 µA leakage:
U13's VCC−0.1 V at 100 µA gives ≥3.035 V, above 2.7 V, and the far-end
pullup assists the high state. A broken conductor rises to ≥2.933 V under
that leakage contract. These statements do not cover missing common return
or arbitrary partial power. Polarity is correct; low-level and system timing
remain **INDETERMINATE**.

### Default-state table

| State | Local power-board result | Complete bridge-off verdict |
|---|---|---|
| Controller unpowered; power board live | If J4.3 is truly at zero, UCC input UVLO inhibits the drivers. PERMIT pulldowns turn Q1/Q4 off. CT/voltage/fault outputs are not valid telemetry. | **Conditional local PASS; system INDETERMINATE.** Residual rail/back-power paths through the eventual powered interlock/sensors are undefined; UVLO turn-off is not instantaneous. |
| Entire J4 unplugged | V3V3 absent, PERMIT locally pulled down; PWM internally pulled down. Gate-source holdoffs remain local. CT burden remains connected. | **PASS for the defined steady unplugged state**, with no alternative external feed; hot-unplug transient and broken-return-only cases unqualified. |
| V3V3 present; controller reset/Hi-Z | PWM internal pulldowns hold inputs low. PERMIT is driven by interlock, not directly by MCU; it may remain latched until watchdog/live logic clears it. | **INDETERMINATE for every reset mode.** Must prove GPIO reset states/glitch-free shutdown plus interlock reset/watchdog/live policy; static floating inputs alone are safe. |
| Interlock missing/unpowered, V3V3 present | Local PERMIT pulldowns bias disable; external output power-off leakage/back-power and rail ramps not established. | **INDETERMINATE dynamically**; require loss-of-live inhibition and qualify the actual unpowered producer. |
| Fault conductor open, supplies/return healthy | Far-end interlock pullup asserts fault within the specified leakage envelope. | **Conditional PASS for conductor open only**; no claim for ground open, fault driver stuck low or power loss. |

UCC21550 §7.4 and its functional-mode tables document input/disable/UVLO behavior;
its VCCI falling threshold is 2.35–2.65 V and UVLO-off delay reaches 7 µs
under §5.8 conditions. Floating safety must not be restated as a bound on
shutdown speed. `FAULT-INTERFACE.md`'s unresolved HOT5 brownout still applies.

## Check 5: CT fix retained, receiver missing

Native and frozen endpoint sets match: `ct_s1` joins T1.3/R39.1/C42.1/R42.1;
`ct_s2` joins T1.4/R39.2/C42.2 and the bias network/U12 input. Neither CT
secondary net reaches J4. R39 is **1.5 Ω**, C42 100 nF; D4/D5 are now
**BAS116H**, not the historical BAT54H. J4.13 is U12's digital CT_ZC;
J4.14 is the biased, clamped monitor via R47=1 kΩ. Therefore unplugging
J4 does **not** open the CT secondary. This structural safety question is
closed on native-17. It does not prove safety if R39 itself fails open.

For an ideal 1:100 CT and no receiver loading, gain is 15 mV/A around
1.65 V. At ±37 A, CT_MON is nominally 1.095–2.205 V; at ±71 A it is
0.585–2.715 V. Including only the stated rail, 0.1% midpoint-resistor and
1% burden corners gives 1.005–2.295 V and 0.490–2.810 V respectively.
These are **conditional circuit ranges**, excluding CT transfer error,
frequency response, leakage, acquisition current and transients. The 18.7 A
rms operating assumption gives R39 average dissipation 52.45 mW.

CT_ZC is rail-referenced push-pull. TLV3201's output limits at 4 mA over
its temperature range are VCC−0.350 V and 0.325 V, compatible with a
suitably loaded ESP32 input. Its idle output may be either level and may
chatter; the controller must ignore it until switching and sensor validity
are established. Existing [task-02 analysis](../02-protection-timing/README.md)
explains offset/hysteresis, filtering and pending bench work. No board in
the counterpart census consumes either new signal; the standalone CT unit
is not such a receiver. J4.13/14 now have defined local signal types and
conditional operating ranges, **not an unconditional transient bound**.

## Check 6: bus range and ADC code

U4 is **AMC1311BDWVR**. Source R26–R29 total 1.88 MΩ; R30=15.8 kΩ.
Use the full divider denominator: VIN=VBUS×15.8/1895.8, not 15.8/1880.
[TI SBAS786C §7.9 and §8.3.3, pp10,22](https://www.ti.com/lit/ds/symlink/amc1311.pdf)
specifies the linear input region through 2 V, nominal differential gain
1 and output common mode 1.39–1.49 V. Above 2 V the transfer has reduced
linearity; that is not an absolute-maximum violation claim.

| Bus | VIN nominal; resistor-only range | Ideal output pair at 1.44 V common mode | Actual ADC code |
|---:|---|---|---|
| 0 V | 0 V | P=N=1.44 V | **Undefined** — no receiver/ADC transfer selected |
| 198 V | 1.65017 V; 1.63235–1.66835 V | P=2.26509 V, N=0.614913 V | **Undefined** — existing controller ADC is single-ended and already driven |
| 280 V | 2.33358 V; 2.30837–2.35929 V | **Not assigned** — outside guaranteed linear region | **Undefined / FAIL range requirement** |

The resistor-only bus level corresponding to VIN=2 V is nominally
239.975 V, with corners 237.360–242.595 V (1% top, 0.1% bottom). Even the
favorable corner fails to keep 280 V in range. These corners omit temperature
coefficient, voltage coefficient, amplifier input current, offset and gain
error; they suffice to show the range issue, not to bound accuracy.

No numerical ADC code is defensible at **any** of the three inputs without
choosing receiver gain/common-mode handling, channel/attenuation, acquisition
loading and calibration. An ideal 12-bit/3.3 V code would invent hardware.
The ESP32 peripheral is single-ended; grounding VBUS_N would load a driven
output. Owner must decide whether to change divider/receiver requirements,
restrict the accurate range, or add a validated overrange policy. Stop any
280 V linear-accuracy approval pending that decision.

## Checks 7–8: timing, returns and earth

**Dead time:** [D-5 at commit 7548c1534](https://github.com/BennetLeff/temper/blob/7548c153487e0e3b1e9544eba0eea1d735e0b7eb/zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D5/README.md)
establishes **UNKNOWN min/max for both switching directions on both legs**.
The 500 ns firmware comment is unverified: the application does not configure
MCPWM, the init path imposes no such minimum, conflicting edge-delay requests
are not handled as fatal, and the guard reads cached requested timing. The
root controller has only the two-output binding shown above. The UCC21550
DT requirement and incoming PWM gap take the longer interval, not their sum.
D-5's hypothetical verified 500 ns input gap produces 488.5–511.5 ns at the
specified unloaded cold-test conditions; it is not a board/gate guarantee.
Retain the 307 ns stress case. Firmware owner must supply the deployed
binary/configuration, correct the API/error handling in a separate change,
and verify all four waveforms before claiming a floor.

**PERMIT/BUS_FAULT latency:** existing task-02 results remain conditional,
not a system bound. Native-17 retains the faster 100 Ω/1 kΩ PERMIT network,
but two AO3400A gates, their voltage-dependent capacitance and the unselected
harness prevent a guaranteed sum from the source comment. U13's 4.5 ns
maximum applies at 3.3±0.3 V, 15 pF and −40..85 °C (6.2 ns to 125 °C at the separate 30/50 pF test load,
SCES489E p5); it is not the whole BUS_FAULT→interlock→PERMIT→gate path.
Task 02 also has assumed harness capacitance/delay, comparator overdrive
and gate-discharge terms. Require a complete measured/corner-qualified path,
including lost-supply default delay and CT threshold crossing, before using
it as protection evidence.

**Returns:** J4 has **four**, not five, ground contacts: 2,4,15,16. Their
net matches every local SELV return. Contact count alone does not prove
adequacy: total external current, wire/contact resistance, current sharing,
missing-contact case and PWM/analog ground offset have no defined harness.
Keep signal returns close to PWM/analog conductors and allocate the 15 V
power return explicitly; all four are one net, not isolated analog grounds.
`R38` is the local 0 Ω functional-earth link between PE and SELV_GND
(`power_stage_120v.ato:558–564`, netlist PE entry). “D5” in the task's earth
wording refers to a design decision; physical D5 is now the CT clamp diode.
This audit proves the local link, not that a future cable, USB host, test
instrument or another board introduces no second PE bond. System grounding
is **INDETERMINATE** until that connection inventory is specified.

## Ranked findings and owner requirements

1. **High: full-bridge enable/control not integrated.** Select a controller
   board/connector and four PWM pin assignments (J4.5–8, input to power stage),
   with 3.135–3.465 V supply, ≥2.3/≤0.8 V input levels including cable drops,
   input current and edge-rate loads, reset-low defaults, and D-5-qualified
   dead time. Establish SENSOR_LIVE, HOT5 validity, watchdog and deliberate
   restart policy; a two-PWM half-bridge source is insufficient evidence.
2. **High: inaccurate bus reading above the linear range.** J4.11/.12 need a
   differential receiver, common-mode and power-off input contract, calibrated
   transfer and defined treatment of 280 V/overrange. Existing analog outputs
   must never be connected together. Range remediation is an owner decision.
3. **High: protection interface guarantees incomplete.** Assign J4.10 to
   exactly one interlock fault input; qualify ≤0.3 V at the actual worst
   pullup/leakage load, fault-high and supply-loss behavior. J4.9 must drive
   both FETs and the interlock pulldown with justified gate-high and transient
   current, discharge latency and no reset/startup enable pulses. Do not promote
   old ISO7710 output levels or assumed capacitance sums to header guarantees.
4. **Medium: new CT signals lack consumers.** Allocate J4.13 digital capture
   and J4.14 analog input, common ground and 3.3 V reference. Require high
   impedance (the analogous current unit requires ≥10 MΩ), bounded acquisition
   current/capacitance and no extra burden. Ignore idle zero-cross chatter;
   calibrate phase/filter delay and validate unpowered-input injection.
5. **Medium: harness and supply contract missing.** Select receiving pin for
   J4.1 15 V OUT and J4.3 3.3 V IN, a single owner per rail, all consumers and
   maximum steady/inrush currents versus converter/connector/thermal ratings.
   Number all four return contacts at both ends. Select mating parts and
   document mating-face vs wire-entry continuity; verify no extra earth bond.
6. **Documentation correction:** task06's pin13/14 and five-return statements
   are stale. The historical CT record remains an accurate record of earlier
   boards, not the current pinout or clamp MPN.

A future **Rust** electrical cross-board rule should consume an explicit
harness schema, not reinterpret the current software `ports.toml`. Bind
board hashes and native connector/pad identities; require a unique producer
per supply/output, receiver levels and load budgets, default/power-off
states, and qualified timing. Reject output-to-output joins, missing PWM
channels, missing CT consumers and a stale J4 pin map. Electrical range and
part-limit certificates belong alongside topology. Do not implement it in
this task; a machine-readable electrical harness is itself currently absent.

## Vendor sources and limits used

Vendor documents were checked 2026-10-02. Page numbers below are printed pages.

| Part | Source / revision / pages | Use and limitation |
|---|---|---|
| UCC21550 | [TI SLUSE89C, Aug 2024, pp9–10, §7.4](https://www.ti.com/lit/ds/symlink/ucc21550.pdf) | Input thresholds/pulldowns, UVLO, selected supply-current rows; no blanket dynamic-current bound |
| AMC1311B | [TI SBAS786C, Jun 2022, pp10–12,22](https://www.ti.com/lit/ds/symlink/amc1311.pdf) | Linear range, output common mode, low-side current |
| SN74LVC1G332 | [TI SCES489E, Dec 2013, pp4–5](https://www.ti.com/lit/ds/symlink/sn74lvc1g332.pdf) | Header output voltage/current and delay, including load/temperature conditions |
| ISO7710 | [TI SLLSER9E, Dec 2024, p12, §7.4](https://www.ti.com/lit/ds/symlink/iso7710.pdf) | DC output-side current and isolator default-high; not U13's output specification |
| TLV3201 | [TI SBOS561C, May 2024, pp5–6](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) | IQ≤60 µA, output swing and comparator limits |
| AO3400A | [AOS Rev 3.1, Jul 2023, p2](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf) | Guaranteed RDS(on) test gate voltage vs typical capacitance |
| SN74LVC1G74 | [TI SCES794G, Sep 2021, p7 electrical table](https://www.ti.com/lit/ds/symlink/sn74lvc1g74.pdf) | Interlock PERMIT driver; load-dependent VOH |
| ESP32-S3 | [Espressif v2.2, p65 Table 5-4](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf) | High-impedance GPIO VOH/VOL only; not loaded harness qualification |
| IRM-20-15 | [Mean Well 2025-11-21, pp2–3](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF) | Supply rating/derating, not assembled load census |
| LMR51430 | [TI SLUSEF4A, Nov 2022, pp1,4](https://www.ti.com/lit/ds/symlink/lmr51430.pdf) | Existing root buck capability, not a new controller supply contract |

Resistor corner inputs are the selected RC `F` (1%) and RT `B` (0.1%)
tolerance codes; values/identities trace to the cited source and frozen BOM.
No temperature coefficient or voltage coefficient correction is included.
CT turns ratio is the ideal assumption retained from the earlier CT analysis,
not a newly measured transformer tolerance. No powered/harness/bench test was run.

## Reproduce

From repository root, using standard-library Python 3.12 (recorded run: 3.12.12):

```sh
python3.12 zapote/power-stage-120v/validation-results/06-controller-interface/scripts/interface_check.py > /tmp/interface-check.json
python3.12 zapote/power-stage-120v/validation-results/06-controller-interface/scripts/interface_numbers.py > /tmp/interface-numbers.json
diff -u zapote/power-stage-120v/validation-results/06-controller-interface/outputs/interface_check.json /tmp/interface-check.json
diff -u zapote/power-stage-120v/validation-results/06-controller-interface/outputs/interface_numbers.json /tmp/interface-numbers.json
```

Verification: both outputs replayed byte-for-byte; the historical CT record is
byte-identical to the base. Import-linter reported 5 kept / 0 broken; read-only
`regen_derived.py --check` reported all derived artifacts consistent. See
[validation receipt](outputs/validation.txt). Mutating `make regen` was not
run because writes are restricted to this task folder and no drift was found.

A different Python runtime changes the recorded runtime string; changed input
bytes change the hashes and may require re-review. The parser reads native
pad assignments, not routed copper continuity; prior native verification is
separate. No Rust workspace, native bridge, ngspice or vendor model is needed.

---

# Historical CT record (preserved)

# 06 Controller interface: CT burden check (partial result)

- Board: `native-09/section.kicad_pcb`, copper identical to SHA-256
  `ccaa385921f686d6d08859cf4e81fb2e93014c434a935996a85257a1f3594112`; source `frozen/default.net`
- Date: 2026-09-26. Operator: Claude Opus 5.5
- Scope: check 5 of [task 06](../../validation-plan/06-controller-interface.md)
  (CT secondary) only. The other 15 pins are not yet checked.
- Evidence class:
  - netlist and connectivity facts: **exact structural**
  - voltages: **simulation/model-based**, first-order
- **Verdict: FAIL on native-09, escalated. Resolved in native-11** (owner approved
  the fix 2026-09-27): the CT is terminated on this board. See "Resolution" below.
  The native-09 finding is kept as recorded.

## Summary

- T1 (CST3015-100ED, 1:100) connects its secondary **only** to J4.13/J4.14:
  - `ct_s1`: T1.3 ↔ J4.13
  - `ct_s2`: T1.4 ↔ J4.14

  There's no burden, clamp or other part on either net on this board.
- The design intends the burden to be on the current-sense board
  (`README.md` J4 table: "The burden and OCP/phase comparators are on the
  current-sense board; retune its burden for the full-bridge peak";
  `elec/src/power_stage_120v.ato` header). **That board doesn't implement
  it.** `zapote/current-sense` is a standalone CT unit: its own CST3015 takes
  the *primary* current on J1 and has its own 1.50 Ω burden. It has no input for
  another CT's secondary, and it was designed for a different operating point
  (44–50 kHz, 45–55 A trip). A repo-wide search finds no other consumer of
  `CT_S1`/`CT_S2`.
- So whenever the tank runs without a burden across J4.13/14, T1's secondary
  is effectively open-circuit. That means the cable is unplugged, the
  receiving board is absent or unpowered, or its burden is open. A
  first-order estimate puts the resulting secondary voltage at roughly
  **120–350 V peak spikes** on SELV header pins. A 1 Ω burden limits it to
  **< 1 V**.

## Method

`scripts/ct_open_secondary.py` → `outputs/ct_open_secondary.json`.

Datasheet values for the CST3015-100ED are taken from
`docs/evidence/2026-08-13-tank-fault-sizing-inputs.md`, which records their
retrieval and hash:

| Value | Datasheet figure |
| --- | --- |
| Secondary inductance | 3.2 mH |
| Turns ratio | 1:100 |
| Volt-time product | 638 V·µs |
| Terminating resistance | 1.0 Ω |
| Secondary DCR | 1.5 Ω |

With the secondary open, the referred primary current (I_p/100) must flow as
magnetizing current. The voltage follows ω·L·I_s until the core reaches its
volt-time limit, then collapses; that happens every half-cycle in every case
here. The script reports the linear value and the value at the moment of
saturation.

| Case | Primary peak | f | Open: linear | Open: at saturation | Terminated 1 Ω |
| --- | --- | --- | --- | --- | --- |
| Full power | 37 A | 35 kHz | 260 V | **231 V** | 0.37 V |
| Full power | 37 A | 33 kHz | 246 V | 218 V | 0.37 V |
| OCP nominal trip | 61 A | 35 kHz | 429 V | **317 V** | 0.61 V |
| OCP trip + 10 A spread | 71 A | 35 kHz | 500 V | **347 V** | 0.71 V |
| Light load | 10 A | 60 kHz | 121 V | 121 V | 0.10 V |

### Assumptions and limits

- The model is linear magnetizing inductance with an abrupt saturation at the
  volt-time limit, applied as the half-cycle swing.
- It ignores the real B-H curve, winding capacitance and ringing, and
  cable capacitance. Those can make spikes **higher or lower**.
- Treat the numbers as order of magnitude, not a bound. Tens of volts would
  already exceed SELV; these estimates are hundreds.
- Even a burden that goes open for one cycle (a connector intermittent)
  produces the same spikes, and the core then saturates the remaining cycles.

## Consequences

1. **Safety:** voltages far above SELV limits on SELV-domain pins J4.13/14 and
   on the cable to the controller side. They could stress or destroy whatever
   receiving input is connected, and pose a touch hazard on an unplugged
   harness.
2. **Function:** without a defined burden and receiver, the CT phase
   information and the tank over-current sense it was meant to provide don't
   exist. POWER-SECTION.md §7 item 4 already lists "CT phase inhibit" as
   unverified.
3. **Interface definition gap:** J4.13/14 have no qualified counterpart.

## Recommended fix (owner decision; not implemented)

Terminate the CT **on this board**, at T1, and send a low-impedance voltage
across J4 instead of a current-source secondary:

- **Burden:** a 1.0 Ω burden (the datasheet terminating value; `power_section.rs`
  already assumes 1.0 Ω: 0.72 V at 72 A) across T1.3–T1.4, placed at the
  transformer.
  - Use a pulse-rated resistor sized for the secondary current
    (I_s,rms ≈ 0.19 A → ~40 mW; size ≥ 0.25 W).
- **Clamp (recommended):** a bidirectional clamp across the burden, such as a
  low-voltage bidirectional TVS or antiparallel diodes. It keeps the node
  within a few volts if the burden fails open.
- **Receiver:** the receiving board becomes a high-impedance voltage input and
  must not add a second burden. The current-sense board as designed does not
  fit this role; either adapt it or define a new receiver. Record the
  contract in the J4 interface table.
- **Layout feasibility (checked, not verified):** the SELV-side area between
  T1.3 and T1.4 (about x 173–181 mm, y 64–77 mm) currently holds only the two CT
  traces. A 1206/2512 burden and a small clamp appear to fit there with short
  stubs, far (> 15 mm) from HOT copper.

A source change is required: new parts in `elec/src/power_stage_120v.ato`,
then re-freeze, a new native projection and re-route. The whole verification
pipeline follows, and the change needs renewed D4 review.

## Open items and confirming physical test

- Owner decision on the fix above.
- After the fix: a bench check with a low-energy primary current injection,
  measuring the burden voltage with the cable unplugged. It must stay
  < 1 V typical and within the clamp level on a simulated burden open.
- The remaining task-06 checks (the other 15 J4 pins and the default states)
  are not started.

## Reproduce

```sh
python3 validation-results/06-controller-interface/scripts/ct_open_secondary.py
python3 - <<'EOF'   # connectivity: every node on the CT nets
import re; net = open("frozen/default.net").read()
for n in ("ct_s1", "ct_s2"):
    m = re.search(r'\(net \(code "?\d+"?\) \(name "' + n + r'"\)(.*?)\)\s*\(net ', net, re.S)
    print(n, re.findall(r'\(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(1)))
EOF
git grep -n -i "ct_s1" -- ':!*.kicad_pcb' ':!*.net' ':!*.json'   # consumers
```

## Resolution (native-10/11, 2026-09-27)

The owner approved the senior-designer fix: terminate the CT at T1 and
condition it on this board.

- **Source:** 21 parts added at the end of `PowerStage120V`, so no existing
  designator renumbered. They are:
  - the floating 1.5 Ω burden with 100 nF across it (R39, C42)
  - the 1 k/1 k bias midpoint with its bypass (R40, R41, C43)
  - the 1 k series input and BAT54H rail clamps (R42, D4, D5)
  - the ≈55 A bipolar comparators (U10 positive, U11 negative) with 0.1 %
    references (R43–R46)
  - the zero-cross comparator (U12)
  - the 3-input OR of the isolated bus fault and both CT trips onto BUS_FAULT (U13)
  - the 1 k monitor output (R47)
  - bypass capacitors (C44–C47)

  J4.13/14 are now CT_ZC and CT_MON.
- **Model:** `tools/ct_detector/` holds the current-sense unit's reviewed Rust
  model, with the references retuned to 3.32 k/10 k. Nominal trip is 55.2 A.
  The bounded DC corner band is 50.9–59.5 A. Its 6 tests pass.
- **Audit:** `audit.rs` now fails if either CT secondary net reaches J4, if the
  burden is missing, or if the OR is bypassed. The fault-path tests are
  updated, and the CSV parser now handles quoted commas
  (`"BAT54H,115"`). There are 53 tests.
- **Board:** native-10 is the placement; the 114 existing poses are unchanged.
  native-11 is routed, and its gates are in `native-11/verification/README.md`.
  The CT nets now join only the burden, its capacitor, the series input and
  the bias network.

The open item is renewed D4 review of the placement change. Bench
qualification from the detector's own list also remains:
- CT transfer and saturation
- clamp leakage when hot
- comparator hysteresis and offset
- zero-cross behaviour at idle
- the complete trip-to-gate-off timing (task 02)

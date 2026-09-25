# Failed-short interruption boundary

Status: read-only source/model review. This note does not select a new part,
qualify the fuse, or claim that a gate-off waveform interrupts a failed-short
power device.

## What is physically connected

The campaign source is `PowerEntryPassiveReva`; it defines `hv_plus`,
`hv_minus` and `control_gnd` as the bus and controller-side returns
([`power_entry_passive_reva.ato:215-226`](../../../../../../../elec/src/power_entry_passive_reva.ato#L215)).
Its boost path is bridge-plus to `l_boost`, then `q_boost.D`; the MOS source
returns through `control_gnd` and the shunt to bridge minus
([`power_entry_passive_reva.ato:370-380`](../../../../../../../elec/src/power_entry_passive_reva.ato#L370)).
The SiC diode's cathode is on `hv_plus` and both anodes are on the MOS drain
([`power_entry_passive_reva.ato:375-377`](../../../../../../../elec/src/power_entry_passive_reva.ato#L375)).
The four bulk capacitors, local HF bypass, output and bleeder chain are all
connected from `hv_plus` to `control_gnd`
([`power_entry_passive_reva.ato:387-403`](../../../../../../../elec/src/power_entry_passive_reva.ato#L387)).
This source has no F2 component or F2 series net. F2 is a reserved next-passive
schematic path in the retained disposition
([`DISPOSITION.md:21-31`](../../../DISPOSITION.md#L21)) and architecture proposal
([`INTERFACE-DESIGN.md:110-128`](../../../../INTERFACE-DESIGN.md#L110)).

Those source connections, combined with the **proposed** F2 reservation, give
the intended simultaneous-short path. The current passive ATO has no VD/VB
split: `d_boost.K`, the bulk capacitors and `output.plus` share `hv_plus`.
The VD/VB split below is therefore a next-schematic interface, not a claim
about the present ATO netlist:

```text
bulk-bank+ (proposed VB) -> F2 -> proposed VD / boost-diode side
  -> U10 diode short -> U9 MOS drain/channel short
  -> control_gnd / rectifier return -> bulk-bank-
```

The U9/U10 names above follow the retained fault disposition: U9 is the
boost-switch MOSFET and U10 is the boost diode. The source uses the concrete
`q_boost`/`d_boost` names; the mapping is an interpretation of that retained
architecture, not a new netlist claim.

## Which actuator can interrupt which case

These are source facts plus the narrow consequence of the topology:

| State | Available actuator in the retained design | Boundary |
| --- | --- | --- |
| Healthy U9, healthy U10, overvoltage/fault detected | Gate controller can remove the U9 controlled channel; the F2 detector/latch can inhibit the controller | This can stop the modeled controlled channel after detector and gate delays. It does not establish an installed device turn-off delay or remove stored energy. |
| U9 failed short, U10 healthy | Gate command cannot open a shorted U9. U10's reverse blocking may prevent the bank from feeding the failed path; the line-side F1 is the only retained line-fault interrupter | F1 coordination and the diode's actual reverse stress are unestablished. A gate-off signal is not credit for interruption. |
| U10 failed short, U9 still controllable | Gate-off can remove the **controlled** U9 channel if the MOSFET remains functional; the diode short itself has no gate | The passive source has only the direct controller gate path and 10 ohm gate resistor/10 kohm pulldown; the proposed interface says no turn-off diode is selected ([`power_entry_passive_reva.ato:422-425`](../../../../../../../elec/src/power_entry_passive_reva.ato#L422), [`INTERFACE-DESIGN.md:88-92`](../../../../INTERFACE-DESIGN.md#L88)). A surviving U9 body path, parasitics and current commutation still need evidence. |
| U9 and U10 both failed short | F2 is the only actuator in series with the bank discharge path | No gate command or VSENSE standby can open this path. F2 clearing, arc, let-through and withstand are all open. |

The retained architecture review states the same boundary directly: for a U10
and U9 simultaneous short, “only proposed F2 can interrupt it,” while no
buffer command opens the loop and local `CLOCAL` energy bypasses F2
([`INTERFACE-DESIGN.md:235-242`](../../../../INTERFACE-DESIGN.md#L235)).
The protection disposition repeats that the F2-only case is unestablished and
that a gate command cannot clear a failed-short U9
([`protection/DISPOSITION.md:31-44`](../../../DISPOSITION.md#L31)).

## What the plant model does and does not represent

The live operating-matrix-07 cold plant has an explicit 120 V RMS, 60 Hz
bridge source, 0.25 ohm source resistance, a 10 ohm NTC, and a 50 mΩ relay
bypass across that NTC ([`cold.cir:7-20`](../../normal-hysteretic-driver-candidate/cold.cir#L7)).
It then retains 20 mΩ winding resistance and a 180 µH boost inductor
([`cold.cir:22-25`](../../normal-hysteretic-driver-candidate/cold.cir#L22)),
two 45 pF diode legs and an authored level-1 MOS/body network
([`cold.cir:27-39`](../../normal-hysteretic-driver-candidate/cold.cir#L27)).
The local and bank capacitors are 19.8 µF and 2240 µF, respectively, and the
F2 element remains an ideal controlled switch with `Ron=15 mΩ` and
`Roff=1e12` ([`cold.cir:40-51`](../../normal-hysteretic-driver-candidate/cold.cir#L40)).
This live source therefore includes a bounded AC/source/NTC path; it must not
be described as an ideal-DC-line plant.

The earlier f2-shutdown-04 plant is retained as historical evidence. That
fixture used an ideal DC line and the same nominal 180 µH, 19.8 µF, 2240 µF,
45 pF-per-leg and scripted F2-switch assumptions
([`normal_arm.cir:40-60`](../../../f2-shutdown-04/plant/raw/normal_arm.cir#L40)).
Its finite level-1 MOS/body branch and explicit 8 ns body-diode assumption are
documented separately ([`normal_arm.cir:62-87`](../../../f2-shutdown-04/plant/raw/normal_arm.cir#L62)).
Neither plant supplies hot I/V, nonlinear capacitance, avalanche, layout-loop
parasitics, fuse arcing, or DC clearing bounds; the model note calls these
nominal anchors and limitations
([`models.md:10-19`](../../../f2-shutdown-04/plant/models.md#L10)).

F2 in the plant is not a fuse model. It is an ideal controlled switch:

```spice
VfuseCtl f2ctl 0 PWL(... T_OPEN ...)
Sfuse vd vb f2ctl 0 SWF2
.model SWF2 SW(Ron=15m Roff=1e12 Vt=2.5 Vh=.1)
```

([`normal_arm.cir:58-60`](../../../f2-shutdown-04/plant/raw/normal_arm.cir#L58)).
The control waveform schedules the topology opening; it does not calculate
thermal melting, arc voltage, current-dependent clearing time, restrike,
minimum breaking current, or let-through I²t. Therefore a passing “F2 open”
trace means only that the scripted switch was opened in that model. It cannot
be used to claim that a real F2 interrupts a U9/U10 simultaneous short.

The live model does provide a bounded numerical experiment: two diode paths,
the explicit body branch, the 0.25 ohm source resistor, the 10 ohm NTC and the
20 mΩ winding resistor are visible, while channel current and
source/inductor/capacitor states are saved. It still omits measured tolerances,
holder/cable loop R/L, capacitor ESR/ESL, installed F1 behavior and any fuse
arc. The historical f2-shutdown-04 model used an ideal `Vline` and only the
constant 180 µH series element; that limitation applies to that older fixture,
not to the live AC bridge above. The historical fixture's `Rlocal=450 kΩ` and
`Rbank=10 MΩ` are bleeders, not source impedance; the live-07 source has no
`Rbank` element.

## Installed fuse and source evidence

The passive ATO identifies a single PCB fuse holder, MPN **0031.2510**, and
describes its replaceable **0034.3129** link in the input path
([`power_entry_passive_reva.ato:20-22`](../../../../../../../elec/src/power_entry_passive_reva.ato#L20), [`power_entry_passive_reva.ato:355-363`](../../../../../../../elec/src/power_entry_passive_reva.ato#L355)).
The retained disposition instead identifies Mersen **A70QS50-14F + UltraSafe
US141/Z331153** as an offboard candidate. It records 50 A nominal current,
280 A²s maximum pre-arcing I²t and 1,500 A²s maximum clearing I²t at 700 Vac,
but no A70QS minimum-breaking-current value or 890 Vdc capacitor-discharge
let-through curve ([`protection/DISPOSITION.md:50-104`](../../../DISPOSITION.md#L50)).
Those catalogue facts do not establish DC capacitor-fault interruption or
that the candidate is installed on the current PCB.

F1 is separate: the passive source places the holder ahead of the EMI choke,
NTC, bypass and bridge ([`power_entry_passive_reva.ato:355-369`](../../../../../../../elec/src/power_entry_passive_reva.ato#L355)).
The BOM identifies Schurter 0034.3129 as a 16 A/250 V time-lag **link** and
0031.2510 as its separate holder, while the holder footprint is not yet the
real mechanical drilling pattern. The repository has no coordinated F1
time-current/I²t result for the actual line source and NTC/relay sequence
([`docs/evidence/2026-08-12-f1-fault-protection.md:7-13`](../../../../../../../docs/evidence/2026-08-12-f1-fault-protection.md#L7)).
F1 therefore cannot be substituted for F2 in the bank-short path, and its
presence does not provide a measured source-impedance bound.

## Minimum prototype/schematic closure

No part change is proposed by this review. Before a protection claim is
possible, the next artifact should:

1. Keep an explicit, physically separate `VD-out -> F2 -> VB-return` path
   and show the holder/interconnect, terminal insulation and loop R/L. The
   F2 candidate must be treated as the sole interrupter for the U9/U10
   simultaneous-short case.
2. Keep the gate shutdown as a **damage-limiting** action for a still-
   controllable U9, never as the failed-short interrupter. Preserve the
   detector/latch path and fresh-arm contract separately from F2 opening.
3. Obtain manufacturer capacitor-discharge clearing data covering the
   maximum bank voltage, capacitance tolerance, loop R/L, short residual and
   minimum-breaking-current regime. The retained 700 Vac I²t value cannot be
   reused as a DC-bus value.
4. Instrument a current-limited prototype with F2 current, both F2 terminal
   voltages, local diode-side capacitor voltage and MOS/diode current. Prove
   arc extinction, no restrike and post-open discharge; a gate waveform or
   ideal-switch simulation alone is insufficient.
5. Close F1 separately against measured mains/source impedance and the
   bridge/NTC/bypass path. Do not merge that line-fault result with the
   stored-energy F2 result.

Until those records exist, the honest conclusion is: the latch and gate path
can request controlled U9 turn-off, while only a qualified F2 assembly can
interrupt the bank-to-failed-short-U10/U9 loop. The current ideal SWF2 model
cannot establish that qualification.

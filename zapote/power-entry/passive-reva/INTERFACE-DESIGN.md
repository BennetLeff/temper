# Passive Rev A: auxiliary, gate drive and F2-open interface proposal

Status: **REVIEW DRAFT — architecture proposal, not an implemented ECO.**
The [architecture reduction](protection/ARCHITECTURE-REDUCTION.md) supersedes
the discrete sequencing partition below. The rejected 133-part implementation
is archived, and the canonical candidate is restored to the baseline described
in section 1. Fault coverage and qualification requirements remain open.
The [current and timing audit](protection/f2-timing-02/README.md) records why
40 A is not a maximum and why the complete shutdown delay remains unbounded
by the available evidence. Its faster detector/latch proposal is not yet wired
into this interface or the baseline.
Prepared 2026-09-19 from `12c09c5fac551cf5ac70e2a13bd35e2995db12e0`.
The [milestone](MILESTONE.md) remains NOT MET. This document makes the next
circuit decision reviewable; it does not authorize or describe a powered test.

## 1. Identity and decision

The source is `elec/src/power_entry_passive_reva.ato:PowerEntryPassiveReva`.
Its SHA-256 is
`dd31c0addd5a5a5764955efca44d50d6fe89747f88c937e4c127398349b701d8`.
The retained [PCB](candidate/section.kicad_pcb) SHA-256 was rechecked:
`34e6fba9e6d323d795bba5bfe7ddfbcb5d158630cd2eb8cf95253b8e0263b2b9`.
It has no F2, independent voltage detector or gate buffer. Its UCC28180D
drives STW65N65DM2AG through 10 ohms with a 10 kohm gate pulldown. U43
receives external HOT-referenced auxiliary power. Those are present facts;
everything below describing additional circuitry is proposed.

Recommend a line-fed external auxiliary module, the same controller and STW
switch, one UCC27624DR buffer channel with hardware enable, diode-side
regulation, separate diode/bank observation, and a latched protection supervisor.
F2 remains between the boost diode and bank. This joins the drive and protection
interfaces without restarting device/frequency optimization.

| Approach | Benefit | Unresolved cost | Recommendation |
|---|---|---|---|
| Existing direct drive; protection through VSENSE standby | Least circuit change | Complete UCC standby-to-switch-off timing and loaded drive remain unidentified | Retain as the loss-investigation baseline |
| Buffer with direct hardware disable; VSENSE standby also asserted | A separately controllable gate-off path and a defined driver supply port | Added buffer, supervisor and sequencing; new loss and stability evidence needed | Develop this one circuit |
| Fuse in the U9 branch, bank continuously connected to diode | Avoids the particular small-capacitor F2-open plant | Fuse/cable inductance in the switching path, pulsed heating and different interruption stresses | Do not pursue in this ECO |

The buffer is proposed for fault control. No switching-loss reduction is
claimed. Existing C7/12 V results do not transfer to STW at the proposed supply.

## 2. Auxiliary producer and gate interface

Preserve U43 as an **input**, fed by a separate enclosed auxiliary assembly.
Use **Mean Well IRM-10-15** as the concrete producer candidate. Feed its AC
input from the post-F1/post-EMI-choke line and neutral, upstream of the NTC
and bypass contact. This lets bias exist before precharge or PFC operation.
The auxiliary assembly needs its own reviewed branch protection and mains
interconnect; the existing F1 rating is not proof of that branch's protection.

Return the auxiliary output to `PFC_BUS_MINUS`/controller ground, not the
rectifier side of U12. The output becomes HOT-referenced when connected.
The MCU/SELV domain needs a separate insulation boundary. The active-bridge
experiment's onboard source and renamed output header are not copied here.

**Proposed operating requirement:** 14.25–15.75 V at U11 VCC and the buffer
VDD pins, including ripple, cable drop and load transients while run permission
is asserted. This is a chosen interface envelope, not a measured property.
An independent window supervisor must remove permission before either port
leaves its accepted run envelope, accounting for threshold tolerance and delay.
Loss of the supervisor supply must also disable the driver.

The IRM catalogue specifies 15 V, 0.67 A, ±2.5% tolerance and 200 mVpp ripple
under its stated conditions. The ripple fixture includes external 0.1/47 µF
capacitors. Overload hiccup can restart the supply; its overvoltage protection
range is 17.25–20.25 V. Consequently it is a producer candidate, not the
protection supervisor or a guaranteed port waveform. Review temperature,
108–132 Vac loading, startup and dropout on this assembly.
[Manufacturer datasheet](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF).

The load inventory must include U11, buffer plus actual STW gate charge,
bypass relay and 91-ohm series resistor, reference/supervisor, permit circuitry
and capacitor charging. The active bridge's bootstrap loads are absent. No
total-current acceptance is inferred from the 0.67 A rating. The installed
producer/cable impedance and transient current remain unmeasured.

Proposed drive connections:

```text
U11.GATE -> input damping -> UCC27624DR.INA
supervised RUN_PERMISSION -> UCC27624DR.ENA (external default-low network)
UCC27624DR.OUTA -> existing 10-ohm gate resistor -> STW.G
STW.G -> existing 10-kohm pulldown -> STW.S / PFC_BUS_MINUS
UCC27624DR.VDD -> AUX_15V_IN; GND -> local STW source return
unused INB and ENB -> GND; OUTB unconnected
```

Keep 10 ohms initially to establish the changed-driver baseline. Gate-loop
overshoot, turn-off energy and EMI determine whether a resistor change is
needed; neither a smaller value nor a turn-off diode is selected here.
The STW's three-lead source package still has common-source inductance.

TI specifies independent EN control, a default-enabled internal EN pullup,
and 4.5–26 V recommended VDD. Use a defined external pulldown and active
permission drive; size them against leakage, pullup and threshold limits.
Provide the recommended local 0.1 µF and at least 1 µF bypass. The published
disable delay is under a test load and is not the full detector-to-STW-current
cessation delay. Do not model peak current or DC output resistance as a
guaranteed Miller-plateau drive.
[UCC27624 Rev E](https://www.ti.com/lit/ds/symlink/ucc27624.pdf), §§4–6;
[retained interface audit](../loss-budget/options/experiment-02/SOURCE-AUDIT.md).

The supervisor/reference/latch must use a supply arrangement whose ratings
cover the auxiliary fault envelope. Do not copy the experimental CD4000 logic
directly onto the raw rail: its 18 V recommended ceiling is below the IRM
overvoltage range's high end. Selecting its regulated logic supply, supervisor
and exact thresholds is a circuit-design dependency before schematic release.

## 3. One F2-open circuit architecture

```text
rectifier -> U8 -> switching node -> U10 -> VD -> F2 -> VB -> output/bulk bank
                  |                       |          |
                  U9                      CLOCAL     existing bank bleeder
                  |                       |          |
                  +-----------------------+----------+---- PFC_BUS_MINUS

VD -> UCC28180 regulation divider
VD -> independent observation ------------------+
VB -> independent observation ------------------+-> fault supervisor/latch
AUX valid + HOT_PERMIT + sequencing state -------+      |            |
                                                       ENA low     VSENSE low
```

`VD` is proposed `BOOST_DIODE_POSITIVE`; `VB` remains
`PFC_BUS_PLUS_390V`. Keep output, bank bleeder and bank-voltage observation
on VB. CLOCAL and its discharge provision are VD-side. Sense both against
the controller-side return. Protection observation must remain available
when the separate regulation VSENSE node is clamped low.

The supervisor has four functions:

1. Independent diode-side overvoltage detection.
2. Independent bank-side overvoltage and bank-ready observation.
3. Bidirectional VD/VB discrepancy detection, with tolerance and filtering
   derived from normal fuse/interconnect ripple and permissible fault energy.
4. Rail/startup/run-permission supervision and a dominant fault latch.

Any latched fault disables ENA directly, also commands UCC standby, and removes
downstream load permission. A slow controller stop is not in series with the
fast buffer-disable path. Comparator, logic, EN, gate and commutation delays
still need a complete budget. Firmware may report a fault but is not the sole
fast trip path. An OV channel cannot detect every collapsing-bus fault.

**Do not rely on the existing 505 V detector alone.** The controller can
stop and restart below that threshold, so the independent latch may never set.
Nor is lowering its threshold blindly sufficient: under the retained ±1%
divider assumption, the 4.87–5.15 V reference range and 107% minimum OVP ratio
permit a maximum static regulation point of 409.307 V and a minimum OVP point
of 398.112 V across different devices/corners. These screening corners overlap;
a single absolute threshold cannot be assumed both above all normal points
and below every controller trip. Dynamic ripple further constrains the choice.
[UCC28180 Rev D](https://www.ti.com/lit/ds/symlink/ucc28180.pdf), §7.5.

Equations for that arithmetic, with resistances in ohms:

```text
VREG,max = 5.15 * (1e6*1.01 + 13000*0.99) / (13000*0.99)
VOVP,min = 4.87*1.07 * (1e6*0.99 + 13000*1.01) / (13000*1.01)
```

Discrepancy sensing is an additional trip mechanism, not a fuse-continuity
test. Immediately after F2 opens, VD can equal VB because both capacitors retain
charge. An open fuse with two discharged nodes also gives equality. Reset and
precharge logic must never promote either observation to proven continuity.

## 4. Startup and restart contract

The following states are proposed hardware/interface behavior, not the cooker
firmware's existing eight-state machine and not implemented logic.

| State | Gate permission | Exit condition |
|---|---|---|
| Unpowered or invalid bias | Inhibited | Valid supervisor/reference and controller/driver rails; no automatic run edge |
| Disarmed | Inhibited | Deliberate arm after verified precharge path, F2/interconnect integrity and no latched fault |
| Precharged / start permitted | One controlled startup attempt | Existing HOT_PERMIT plus valid bank precharge, bypass sequencing and both-node checks |
| PFC ramp | Permitted while all interlocks hold; downstream load disabled | Bank-ready established bank-side within a justified startup deadline |
| Run | Permitted while all interlocks hold | Fault, loss of permit, or stop removes permission |
| Fault latched | Driver disabled; controller standby; load disabled | Service/re-arm after fault correction and both-node residual-charge checks |

Full regulated bank voltage cannot be a prerequisite for beginning the PFC
ramp: that would deadlock startup. Bank-ready for the downstream load is a
separate signal from permission to start PFC. Residual charge cannot bypass
precharge/fuse checks. The existing bypass relay shorts the NTC; opening it
does **not** disconnect mains.

No periodic retry is allowed after a detected F2/discrepancy/OV fault. Loss
and return of AUX or a stuck-high HOT_PERMIT must return to disarmed, not
create a fresh start permission. The implementation must require a new,
deliberate arm event after qualification; an RC delay is not this mechanism.
Before any prototype powered procedure, F2/interconnect continuity must be
independently checked. The eventual automatic continuity-test mechanism and
its diagnostic coverage are still design work; equal voltages are insufficient.

Startup deadline and discrepancy thresholds remain unestablished because
controller large-signal response, normal ripple and capacitor/precharge
tolerances are not bounded. They must be derived before this state contract
is converted into accepted hardware. An arbitrary timeout cannot certify
energy containment during that interval.

## 5. Reservoir and fuse installation candidates

Use **TDK B32776P6226K000** as the single 22 µF reservoir candidate for the
combined-circuit evaluation, replacing U40 in that proposed variant. If a
separate small HF bypass is retained, include it explicitly in both the
transient and stored-energy models. TDK lists ±10%, 630 VDC, 35 V/µs, a maximum
42 × 28 × 42.5 mm body and 37.5 mm lead spacing. It requires new placement
and footprint review; it is not a replacement fitting U40's present footprint.
Temperature derating, ripple heating, ESL and pulse conditions must be applied
from the series data before acceptance.
[Exact part](https://product.tdk.com/en/search/capacitor/film/dc-link/info?part_no=B32776P6226K000);
[series data](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/mkp_mfp/data_sheet/20/20/db/fc_2009/b3277xp.pdf).

The existing immediate-off equation at Vin=169.705627485 V, V0=424.68 V,
L=180 µH and I0=40 A gives 449.174 V at 22 µF but **451.765 V at 19.8 µF**.
Thus the nominal <450 V screen has no tolerance margin. These are algebraic
screens, with zero assumed detection delay; they do not select a safe capacitor.
At +10% capacitance and 500 V, stored local energy is 3.025 J. That energy is
outside F2 and requires a separate failed-short/discharge disposition.
The existing 630 V part rating is not a desired transient operating point.

Keep **Mersen A70QS50-14F + US141/Z331153** as the series fuse/holder
candidate under the [existing disposition](protection/DISPOSITION.md).
Reserve a dedicated VD-out/VB-return interconnect to the offboard DIN holder,
with independently reviewed terminals, cable, touch protection and routing.
The existing output connector remains the load output. Normal pulsed heating,
interconnect R/L, fuse arcing and capacitor-discharge clearing must be reviewed
together. Average bus current and the holder rating do not establish these.

If the combined reservoir/timing circuit exceeds its justified stress envelope,
this candidate fails. Do not insert another MOV or increase C merely to produce
a passing plot. Any clamp then needs its own V-I/energy/repetition assessment.

The fault cases retain their different interrupters:

| Fault | Actual path / actuator | What this proposal does not establish |
|---|---|---|
| F2 open, U9 healthy | Buffer may turn U9 off; U8 current still commutates through U10 into CLOCAL | Peak voltage, total latency, later mains inflow or safe restart |
| U9 short, U10 healthy | U10 blocks reverse bank discharge; F1 lies in the line-fed fault path | Gate shutdown cannot clear a failed-short U9; F1 coordination is still open |
| U10 short, U9 healthy/on | VB → F2 → shorted U10 → U9 → bank return | Independent detection plus U9 survival/turn-off is unproved; U12 is outside this loop |
| U10 and U9 short | Same bank path; only proposed F2 can interrupt it | No buffer command opens it; fuse clearing/withstand remain open and CLOCAL energy bypasses F2 |

## 6. Exact-part loss evidence and finite next checks

ST's [STW65N65DM2AG product listing](https://www.st.com/en/power-transistors/stw65n65dm2ag.html)
lists a PSpice model, version 1.0 dated 2016-01-13. This is new source discovery,
not model validation. Direct retrieval failed (HTTP/2 error, then HTTP/1.1
timeout); no model bytes or simulation are retained. The prior conclusion
that no independent exact-STW model was found *in the repository* still holds.

The next loss step is to retrieve that exact model, inspect its terminals,
temperature/charge behavior and restrictions, and compare applicable curves
with the retained ST datasheet. Evaluate the direct-drive baseline and proposed
buffer separately at matched current, voltage and temperature. A vendor model
is an independent device reference, not a guaranteed production corner or a
replacement for the unknown assembled driver/parasitic waveform. Explicitly
separate overlap, output-capacitance and gate-supply energy.

Before source/CAD implementation, complete these circuit-design checks:

- Select the exact supervisor/reference/latch and logic supply; derive diode
  OV, bank OV/ready, discrepancy and rail thresholds with tolerances. Verify
  observation while VSENSE is inhibited and all rail ramp/dropout states.
- Bind real EN-to-gate timing and capacitor characteristics to the retained
  plant model; replace its scheduled gate law where controller behavior matters.
  Check F2-open startup, opening in run, line/PWM phase, first peak, continued
  input and restart as one circuit, with energy balance and refinement.
- Establish precharge and continuity diagnostics, intentional re-arm and
  downstream load permission. An initial equal-voltage state is an explicit
  adversarial case. A collapsed reference, disconnected sense lead and missing
  auxiliary return also need explicit dispositions.
- Finish the auxiliary load/impedance budget and offboard holder/interconnect
  specification. Obtain applicable F2 clearing and loop-withstand evidence;
  F1 line-fault coordination is a separate retained obligation.

These are bounded engineering dependencies, not new generic checkers. The
existing native/Rust suite is run when source/CAD changes, on the saved bytes.
Physical qualification remains owned by the existing
[cooling protocol](cooling/qualification-protocol.md) and protection disposition.

## 7. Review receipt and limits

This review used the electrical-model-review procedure. It checked current
source connections, exact branch/PCB identity, source conditions and fault
states. New arithmetic was evaluated directly from the written equations.
Local UCC27624 PDF SHA-256 was verified as
`b42590ddafb28a608aae30f5a2c333851cf11ded63daa03fbdef6df93ecb8a51`;
the retained IRM PDF as
`1aab6b30492328818e4d0900416676891eeb1076f409d56dc2277d7119ed208a`.
TDK facts were read from the manufacturer's web part page and parsed PDF;
the raw PDF download returned HTTP 403, so no retained local TDK PDF is claimed.
No evidence ledger was promoted, no new acceptance rule was introduced and no
native suite or powered experiment was run. The prior seven-unit INDETERMINATE
receipt remains historical.

The only new artifact is this proposed interface design. Current source, PCB,
BOM, firmware and cooling status are unchanged. Review approval would select
the architecture for detailed circuit design; it would not claim that its
unselected supervisor, missing model or unqualified protection already work.

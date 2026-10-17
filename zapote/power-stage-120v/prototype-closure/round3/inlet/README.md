# Inlet design I3 — engineering prototype candidate, 2026-10-04

**Select a guarded external inlet pod with resistor precharge, an electrically
verified bypass, and two independent normally-open source contactors.** This is
a schematic-level design proposal for the first 120/127 V, 60 Hz engineering
unit. It is not a fabrication package or authorization to energize. Native19
board SHA256 remains `3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`;
no existing board, source, round2 evidence or protection threshold is changed.

The existing enclosure has no demonstrated room for this function. The external
pod is a deliberate prototype instrument: it makes the interruption and startup
behavior observable before miniaturizing it. See [packaging](../packaging/) and
[control/energy](../control-energy/) when those concurrent handoffs are complete.

## Decision and alternatives

| Option | Useful property | Reason for decision |
|---|---|---|
| NTC alone | Few parts; cold-start resistance | Rejected: hot reclose has much less resistance; no independent disconnect or welded-bypass evidence. Its temperature-dependent resistance would invalidate the deterministic precharge budget. |
| Resistor, bypass, two monitored contactors | Bounded cold/hot resistance; normally-off source path; direct fault injection | **Selected for prototype.** Larger and slower than a final appliance solution, but distinguishes gate shutdown, source interruption and stored-energy absorption. |
| Back-to-back MOSFET or triac controlled inlet | Could control connection phase and avoid contact bounce | Deferred: adds a live gate supply, surge/SOA/short-failure coordination and a new switching EMI source. A semiconductor short still needs mechanical isolation. Zero-cross turn-on alone does not establish fault interruption or hot-reclose safety. |

The 11 ohm value below is a NEW selected candidate, not a relabeling of the
round2 ideal 10 ohm/20 ms experiment. No new nonlinear simulation has yet
qualified this exact pod, auxiliary supply, proof load and catch-capacitor
combination. [Round2 evidence](../../round2/d22/README.md) supplies the failure
mechanism, not the new circuit's result.

## Power circuit

```text
Plug L -- F0 -- S0 poleL -- L_AUX ------ F2 -- PS_AUX.L
                              |
                              +-- K1 1L1/2T1 -- K2 1L1/2T1 -- L_SER --+-- TF1 -- RP1 --+-- L_PRE --> D22.Lin
                                                                    +-- TF2 -- RP2 --+
                                                                    +-- KB 1L1/2T1 -+

Plug N ------- S0 poleN -- N_AUX ------- PS_AUX.N
                              |
                              +-- K1 3L2/4T2 -- K2 3L2/4T2 -- N_PRE --------------------> D22.Nin

L_PRE -- FT -- KT NO -- RTEST -- (one insulated turn through CT_TEST) -- N_PRE

Plug PE -- dedicated PE stud -- pod/enclosure/sink bonds -- D22.PE -- appliance PE
          NEVER switched, fused, or used as a control/current return
```

F0 is a proposed **KLDR015.TXP, 15 A Class CC** replacing the previous 20 A
candidate for this pod; holder LPSC0001Z. This is an engineering coordination
choice, not a claim that a 15 A fuse enforces a 15 A RMS operating limit. S0
retains Schurter 4435.0002, two-pole manual supplemental switch. F2 is
KLDR002.TXP in its own LPSC0001Z for the auxiliary branch. FT is a separate
KLDR001.TXP/LPSC0001Z for the proof-load wiring; its cold pulse/reclose behavior
requires coordination. The three fuse branches must be shown separately in
the assembly, not silently combined into a single holder.

The packaging handoff selects **Southwire 55808799, Royal SJOOW 12/3**
and **Lapp 53111020** gland candidates. Retain their temperature/ampacity,
strand termination, bend and strain-relief checks. **Hubbell HBL5266C** is
a 15 A/125 V plug candidate for the nominal 120 V setup; its nameplate is
not a 140 V qualification. The 127 V operating proposal and 140 V abnormal
test source need a reviewed connection arrangement within their component
and installation ratings. Do not use the simulated input range as a cord
assembly rating. The cord and gland detailed BOM remains in packaging.

K1, K2 and KB are **Schneider LC1D18BD**, 24 V DC. K1 and K2 each switch L and
N with separate NO poles; their unused third main poles remain unconnected.
KB uses one NO main pole only; do not parallel poles. K1/K2 are independent
series interruption channels; neither a KB opening nor native gate disable is
credited as mains isolation. NC mirror contacts 21–22 from all three devices
are individually monitored. NO auxiliaries 13–14 provide position information
only. An open NC contact does not prove power-contact closure. The selected
family has integrated coil suppression: **do not add a simple flyback diode**
and then reuse its published opening time. Primary product evidence gives
63 ms ±15% closing and 20 ms ±20% opening under its specified conditions;
installed wiring, rail collapse, bounce and load still require measurement.
[Schneider product specifications](https://eshop.se.com/eg/tesys-d-contactor-3p-3-no-ac-3-440-v-18-a-24-v-dc-coil-lc1d18bd.html).

RP1/RP2 are **Ohmite HS200 22R F**, parallel, 22 ohm ±1% each, 200 W *when
properly mounted*, giving 11 ohm nominal. Do not substitute an NTC, mount
them on plastic, or treat 200 W as an unmounted pulse qualification.
TF1/TF2 are candidate **Cantherm SDF DF128S**, one in series with each
resistor branch and thermally coupled through an electrically insulating
mount. These bodies are live. The source's application warning about direct
heater connection and the actual resistor/cutoff arrangement require
manufacturer clarification before this TCO arrangement is accepted. A
disconnected, poorly coupled, or bridged TCO is not a validated last resort.
Nominal functioning temperature is 128 C; that is not the permitted resistor
case or nearby-plastic temperature. [Cantherm SDF](https://www.cantherm.com/product_post_type/sdf-15-amp-250v/).

No fault containment claim depends on TF opening within 500 ms. Electrical
timeout and K1/K2 perform the fast source withdrawal; TCOs address a different,
slower sustained-heating failure. If either TCO/resistor branch opens, the
remaining branch becomes 22 ohm: fail the precharge resistance/charge-time
POST and latch a service fault rather than silently operate degraded.

RTEST is **Ohmite HS100 220R F**. KT is **G5Q-1A-EU DC24**, SPST-NO,
with 24 V coil, on the inlet control board. The test branch is wholly inside
the pod and **upstream of D22**. It must not bring a postfilter mains loop
back out of the appliance. Manufacturer catalogue confirms the resistor
MPNs; the live HS family HTML has shifted electrical columns and its linked
PDF returned HTML. Therefore no numeric pulse curve or heatsink claim was
copied from those malformed fields. The dimensional table remains a
candidate envelope only. [Ohmite catalogue](https://www.ohmite.com/catalog/hs-series/HS200_22R_F),
[proof resistor](https://www.ohmite.com/catalog/hs-series/HS100_220R_F),
[G5Q datasheet](https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5q.pdf).

## Bootstrap and coil drive

PS_AUX is **Mean Well HDR-60-24**, upstream of K1/K2 but downstream of S0/F2.
Set it to 24.0 V. Its 60 W/2.5 A output supplies the supervisor, all three
5.4 W contactor coils, proof relay, isolated voltage interfaces and control
logic. Allocate 25 W total for this pod; no fan or appliance load may be added
without updating the budget. The 52.5 x 90 x 54.5 mm supply needs the
manufacturer's mounting/derating conditions. Its own 30 A typical cold inrush
at 115 V bypasses RP1/RP2. Thus the pod does **not** promise an 18 A total
plug-in peak. Fuse, S0 and source coordination must include this separate
capacitive load. Its 12 ms typical hold-up at 115 V is not a guaranteed
sequencing delay. [HDR-60 specification](https://www.meanwell.com/Upload/PDF/HDR-60/HDR-60-SPEC.PDF).

Use one **IRL540NPBF** low-side coil transistor per K1/K2/KB/KT, driven at
5 V through **SN74AHCT125PWR** (one channel each), 1 kohm series gate and
22 kohm gate-to-source default-off resistor. Gate drive is not directly
3.3 V; that would not use the specified 4.5 V Rds(on) condition. The
contactor coil A1 goes to the hardware-enabled 24 V rail and A2 to the
individual MOSFET drain; sources return to AUX_0V. KT has its own correctly
polarized suppression diode because its timing is separately qualified.
The coil driver is low-frequency; the 1 kohm gate resistor deliberately
limits the logic buffer's transient current. [IRL540N](https://www.infineon.com/part/IRL540N),
[AHCT125](https://www.ti.com/product/SN74AHCT125/part-details/SN74AHCT125PWR).

The supervisor's independent fault latch removes a **separate high-side
coil enable** and asserts PERMIT low. Proposed high-side part is
**TPS1H100AQPWPRQ1**, one per K1/K2 coil, not a shared software output;
the controlled low-side outputs remain separately commanded. Its input
defaults low with 10 kohm to AUX_0V and is hardware-ANDed with rail-good and
the latched safety chain. No 40 V switch rating is credited against a
surge without the upstream supply/clamp evaluation. Exact current-limit,
diagnostic and board net implementation belongs in the new supervisor
schematic and is an explicitly unfinished implementation item.
[TPS1H100-Q1](https://www.ti.com/product/TPS1H100-Q1).

Each K1/K2 coil has its own 24 V branch and driver; route their returns and
command wires independently. One shorted low-side transistor must not keep
both source contactors energized. Do not claim a safety integrity level:
shared supply, fault-latch, wiring and common environmental failures require
review. The supervisor's regulator must tolerate HDR's fault output range;
a 28 V-maximum buck is rejected against its 30–36 V OVP range.
Select **RECOM R-78HB5.0-0.5/W**, 9–72 V input, 5 V/0.5 A output, for this
pod's 5 V rail; it is a non-isolated regulator after the isolated HDR, not
another mains isolation barrier. Account for its 10 mA minimum load and
output-capacitance/startup conditions. Reserve <=0.35 A for the three AMC
channels, logic and analog frontend; the actuator coils stay on 24 V.
[RECOM specification](https://recom-power.com/pdf/Innoline/R-78HB-0.5_W.pdf).

Native19 **J4.1 is an output from downstream PS1**, not an auxiliary supply
input. Do not connect HDR-derived 15 V to it. Keep the new AUX-powered
supervisor independent and isolate communication as needed. Native19 PS1,
PS2/HOT5 and their original net remain unchanged. They can require much
longer startup than the precharge window; the sequence below avoids a
bootstrap deadlock without permitting PWM during rail qualification.

The local pod has **three independent operators: START PRECHARGE, RESET FAULT
and STOP**. The independent AUX-powered supervisor accepts cold start locally,
not through HEAT_REQUEST from the unpowered cooking controller. START and
RESET are separate momentary normally-open dry contacts connecting POD_5V
to `POD_START_RAW` and `POD_RESET_RAW`; each has its own 10 kohm pull-down to
AUX_0V. Released, disconnected and unpowered defaults are low. Never OR the
two inputs together. STOP is a separate normally-closed hardware healthy
chain: opening the operator or a wire removes `POD_STOP_HEALTHY`, trips the
fault latch, inhibits gates and withdraws the source channels independently
of a software poll. Its receiving node defaults low with a pull-down. This
is **not a certified emergency-stop function**.

Inputs require appropriate debounce, transient protection and any necessary
5 V-to-logic-domain translation; no unqualified 3.3 V GPIO connection is
implied. Exact operator MPNs, supervisor pins and STOP-chain circuitry remain
native-capture implementation items. The operator positions and labels are
in [the panel proposal](../packaging/operator-panel.md).

START must first be observed released after power-up. Only a fresh positive
edge while OFF, after completed manual prototype checks and satisfied
OFF/POST conditions, may request precharge. START is ignored outside OFF;
a held button, short, reboot or restored AUX rail must not start it. RESET
requires a fresh edge and may acknowledge/reset only after every resettable
cause has cleared, discharged-node and mirror/sensor/cooldown checks pass,
STOP is healthy and the required manual inspection record is complete. A
welded contact or service-required fault cannot be reset away. RESET only
returns to OFF; a separate subsequent fresh START edge is required to
energize K1/K2. Releasing STOP alone cannot reset or restart the unit.

After bypass, downstream PS1 boots the native cooking controller through its
existing power arrangement. Its later HEAT_REQUEST is a separate request;
it cannot grant PERMIT before rail qualification and all other interlocks.
The pod-only AUX budget includes neither an upstream cooking-controller
converter nor an AUX-to-J4.1 connection.

## Sensing and electrical proof

Provide three independent **AMC3330DWE** isolated voltage channels in the
pod: **VLINE across L_AUX/N_AUX, upstream of K1/K2**, VPRE across
L_SER/L_PRE and VOUT across L_PRE/N_PRE. VLINE stays available with both
source contactors open, after S0 is switched on. It must qualify the incoming
line before the first coil command. Use four series 249 kohm, 0.1%, suitably voltage/pulse-rated
resistors (**TNPW1206249KBEEA**) and a 4.02 kohm, 0.1% low leg
(**TNPW12064K02BEEA**) for each input divider. The 200 V operating limit
of the 1206 family exceeds the approximately 49.5 V nominal share per upper
resistor; surge sharing, layout and single-fault voltage still need checking.
[Vishay TNPW e3](https://www.vishay.com/docs/28758/tnpw_e3.pdf). Nominal scale
is 0.0040199 V/V; 198 V peak produces about 0.796 V, within the ±1 V input
range. Preserve each high-side reference separately: VLINE high-side ground
is N_AUX, VPRE is L_PRE, and VOUT is N_PRE. None is AUX_0V. With the source
contacts closed, VOUT and VPRE must be compared against upstream VLINE with
allowance for both line and neutral contact/wiring drops; do not assert the
exact signed identity VLINE = VOUT + VPRE across different neutral references.
With the contacts open, upstream VLINE is expected while VOUT must decay;
this is a meaningful source-path observation that a downstream-only monitor
could not provide. Duplicate raw DC bus sensing in the power
stage is owned by the control/energy handoff, not inferred from the AC
output peak. [AMC3330 pin and supply data](https://www.ti.com/lit/gpn/AMC3330).

AMC pins: 1 to 3; 2/7/8 to that channel's high reference; 6 to divider tap;
4 NC; 5 locally decoupled high LDO output; 9/15 AUX_0V; 12 regulated 5 V;
13 to 16; 10/11 differential output; 14 individual DIAG with pull-up.
Follow the manufacturer's recommended capacitors/layout, not just these
connections. Divider open/short, saturation and DIAG failures must inhibit
startup. A grounded oscilloscope on any high-side reference is not allowed.

CT_TEST is **Talema AC1005** with one insulated primary turn in the test
branch only, permanently burdened by two 200 ohm resistors in parallel
at secondary pins 1–2. Pin 3 is mechanical support, not a winding terminal.
Add secondary voltage limiting and a buffered ADC frontend; ADC/front-end
part selection and its full tolerance budget remain supervisor schematic
work. A current-transformer reading is required: **VTEST / 220 ohm alone
would falsely report current when the proof resistor is open**. The primary
sheet specifies 0.096 V/A at 0.5 A/100 ohm, versus 0.100 V/A at 5 A; do not
calibrate this low-current test using only the rated-current ratio.
4 kV rms hi-pot is not by itself an installed insulation qualification.
[AC1005 datasheet](https://talema.com/wp-content/uploads/datasheets/AC-1005.pdf).

Before KB is ever energized, test all three NC mirror input circuits for
open and short faults and demand the expected OFF state. Electrical
observations must corroborate mirror transitions; permanently shorted
feedback wires must not satisfy the next startup. Test-plug fault injection
and independent channel continuity checks are part of assembly inspection.

## Proposed timing contract (requirements, not measured performance)

1. **OFF/POST:** gates hard disabled, KT/KB/K1/K2 off. Input and DC bus
   sensors valid; incoming VLINE must remain within the proposed 100–140 V rms
   window for two complete mains cycles before either K1 or K2 coil command.
   Apply the sensor uncertainty inward at both boundaries; an unavailable,
   clipped, saturated or inconsistent reading must fail admission. In
   particular, a wrong 240 V source is not allowed to connect and then be
   classified. The nominal divider's ±1 V linear range is not permission to
   accept an out-of-range waveform. No unexpected downstream voltage or test
   current is permitted. Three
   mirror NC inputs report open main contacts. At least 60 s since any
   aborted startup and resistor cases below the proposed 60 C admission
   limit. Cooling time is a conservative engineering rule pending thermal
   qualification, not evidence of recovery.
2. **PRECHARGE:** command K1/K2, keep KB/KT/gates off. Start a non-retriggerable
   hardware 300 ms budget at the first source-coil command. For two complete
   mains cycles demand the control handoff's input/output/bus tracking,
   settled charging current and VPRE criteria. Proposed values are 95%
   output/input peak, no bus above 110% of input peak, settled crest current
   below 0.5 A and |VPRE| below 5 V. Absolute bus OVP, input fault current,
   resistor overtemperature/energy, sensor failure and source-disconnect
   faults remain active during this state.
3. **BYPASS:** command KB within the same 300 ms budget; observe its mirror
   transition. This is not proof of conduction. Native BUS_FAULT may still
   indicate unready HOT5; it is not allowed to enable gates or suppress the
   independent inlet protections. KB may close only after the independent
   precharge conditions above, while PERMIT is held low in hardware.
4. **BYPASS_PROVE:** after KB response, energize KT for at most 100 ms and
   collect two complete mains cycles. Demand actual proof current
   >=0.40 A rms, within ±10% of measured VOUT/220 ohm, and |VPRE| peak <1 V.
   These are proposed error-budget limits. A missing source, open RTEST,
   failed KT or open bypass cannot pass on NC state alone. Turn KT off;
   verify proof current falls below the established zero-current threshold.
   A welded KT or persistent test load blocks RUN. On failure withdraw K1/K2.
5. **RAIL_QUALIFY:** with KB proven and PERMIT still low, allow up to 2 s
   for downstream supply/logic startup. Require authentic BUS_FAULT low,
   explicit downstream rail-valid, native sensor validity and all other
   interlocks before RUN. Timeout drops K1/K2. A stuck-low BUS_FAULT is not
   a rail-valid signal. Existing firmware does not implement this sequence.
6. **STOP:** gate inhibit first. Retain KB until K1/K2 are commanded open
   and electrically confirmed de-energized/current-free, then open KB.
   A fault/rail loss can cause different contactor drop-out ordering; rate
   RP1/RP2 for the resulting 500 ms fault-pulse allocation and test it.
7. **FAULT:** latch, withdraw both source channels, gate inhibit, no automatic
   retry. A reboot is not permission to bypass OFF/POST or cooldown.

Concrete timeout candidates are three **LTC6993HS6-1#TRMPBF** rising-edge,
non-retriggerable one-shots. On the S6 package: pin 5 to 5 V with 100 nF
local bypass, pin 2 AUX_0V, pin 3 RSET to AUX_0V, pin 4 divider midpoint,
pin 1 qualified start edge, pin 6 timed permissive. Use 0.1% RSET; shield
SET/DIV from switching edges. UT_START uses 54.2 kohm and DIVCODE 6
(1 Mohm upper/681 kohm lower), yielding 284.164 ms nominal. UT_PROOF uses
140 kohm and DIVCODE 5 (1 Mohm/523 kohm), yielding 91.750 ms. UT_TOTAL uses
81.1 kohm and DIVCODE 6, yielding 425.198 ms. These are distinct packages,
not two names for a single firmware timeout. [ADI Rev F, pp. 10–13](https://www.analog.com/media/en/technical-documentation/data-sheets/LTC6993-6993-1-6993-2-6993-3-6993-4.pdf).

A provisional inclusive ±5% timing budget makes the three upper limits
298.372, 96.338 and 446.458 ms. The native schematic review must establish
that budget across device grade, resistor drift, rail variation and startup;
it is not a new manufacturer accuracy claim. UT_START allows transition to
BYPASS_PROVE only after KB response; UT_PROOF directly limits KT coil drive;
UT_TOTAL starts with the first source command and must latch a fault unless
electrical bypass proof completed by its expiry. Its upper allocation plus
24 ms contactor opening is 470.458 ms, leaving 29.5 ms inside the 500 ms
resistor fault allocation for logic and bounce. The fault latch must prevent
a later trigger from creating a new attempt. An open SET resistor can hold
a pulse indefinitely: retain independent total timeout and test timer faults.

The timer interconnect/state latches, high-side pin network, monitored rail
comparators, ADC and independent input-current channel are **not yet a
reviewed native supervisor circuit**. This proposal freezes component choices
and behavioral interfaces; do not call it a completed PCB or a single-fault
qualified controller.

For the first guarded prototype, precharge resistance POST also has a
concrete manual fallback: unplug, verify all DC/catch/filter nodes discharged,
isolate both resistor branches, record each four-wire resistance against
22 ohm ±1% plus instrument uncertainty, then verify 11 ohm parallel with KB
physically open. Check TF continuity separately, restore wiring with a second
inspection, and attach the measurements to that individual power-up attempt.
No powered low-voltage injection circuit into the mains nodes is designed
here. Therefore automatic resistor-short detection remains unimplemented and
must not be credited by a software state called POST.

## Fault dispositions

| Single event | Required response / remaining limitation |
|---|---|
| KB welded at start | Its mirror NC cannot assert the correct OFF state; refuse K1/K2. Also validate feedback wiring. A simultaneous mirror-wire short needs diagnostic coverage, not trust in the contactor label. |
| KB refuses to close | Proof branch creates measurable VPRE; fail proof, gates remain off, drop sources before resistor fault allocation is exceeded. |
| KB opens in RUN | Independent VPRE window faults above proposed 10 V, gate inhibit immediately, K1/K2 withdrawal. Mechanical delay means resistor pulse energy remains; qualify it. |
| K1 or K2 main contact welded | Other source contactor opens both conductors; fault remains latched. No subsequent reclose with a wrong mirror state. Both welded is outside single-fault containment. |
| Controller or AUX rail lost | Low/high-side defaults remove coil drive; gate PERMIT defaults low. No claim that contact ordering follows software after rail loss. Stored energy persists. |
| Source short downstream of RP | Precharge current can be only ~13 A rms, so a 15 A fuse may never clear promptly. Hardware timeout/independent source contactors must act. |
| Resistor/TCO open | Charge dynamics/POST fail; no degraded automatic startup. |
| Resistor short | Reduced R is detectable by low-energy resistance POST; it otherwise defeats the selected inrush bound. Do not infer continuity/resistance from steady precharged voltage. |
| Damper open, capacitor short, diode short | Independent voltage/current screens and line withdrawal, plus prospective-fault fuse coordination; no blanket survival claim. |
| Power FET already shorted | Gates cannot interrupt it. K1/K2 remove new line energy with millisecond delay; local bus/tank absorber and fuse/SOA coordination remain separate. |
| KT welded | Test current remains after OFF command; fault. RTEST mounted thermal rise and fuse must survive until source withdrawal. |
| Thermal cutoff poorly coupled | Cannot be credited as last-resort protection; validate hotspot, insulation and post-opening temperature physically. |

## Calculated budgets and release gates

Run `rustc --edition=2021 calculations.rs -o /private/tmp/temper-inlet-calc`
from this directory, then the binary. Tests are `rustc --edition=2021 --test
calculations.rs -o /private/tmp/temper-inlet-calc-tests` followed by that binary.
This standalone calculation does not touch the shared PyO3 build cache.

Worst resistance at the selected ±1% tolerance is 10.89 ohm. At 140 V rms,
an ideal short after RP gives 18.18 A crest, 12.86 A rms and 1.800 kW total.
The proposed 500 ms conservative withdrawal allocation is **900 J total,
450 J in each resistor**, before stored-energy additions. These are demands,
not accepted HS200 ratings. Winding inductance, contact arcs/bounce, mains
source impedance and voltage tolerance must be included in the actual model.

Allocate another 100 J total for a non-sinusoidal/residual-energy allowance:
the proposed qualification test is >=500 J per RP at the declared hot case
temperature, with the actual 60 Hz pulse train and the selected mount, plus
reclose abuse. A successful Joule calculation is not a pulse-curve approval.
Obtain the correct manufacturer's pulse/temperature/mounting limits or change
the selected resistor before release; do not use the HS400 family's 10x/5 s
overload statement for HS200.

The newly proposed diode-isolated 47 uF catch capacitor adds up to 56.4 uF
using a deliberate +20% allocation (not its selected part tolerance) and
approximately 1.106 J on charging to 198 V. Including 5.8 uF
native bus and 13.6 uF line/filter capacitance at +10% gives a deliberately
simple all-capacitance bound of 77.74 uF and 1.524 J at 198 V. Rectifier,
resonance, filter bleeds and auxiliary startup make an RC model incomplete;
this is an initial energy screen, not proof that precharge is complete.

The 15 A operating allocation includes **all** inlet current: bridge, AUX,
filter reactive current and any test load. RUN never permits KT. Real RMS
measurement/control with a valid window is required; a fuse and a tank
current trip do not implement this limit. Cord, source, switch, contactor,
fuse, TCO and wiring coordination needs actual prospective fault current,
temperature and installation evidence. Native TVS/fuse ratings are not a
universal protection guarantee.

Remaining build gates are concrete: new supervisor native schematic/ERC and
board; exact timer/ADC/rail and input-current circuits; resistor pulse proof;
TCO application eligibility; source fuse/contact coordination; closed-pod
thermal/earthing/insulation; fault-injected cold POST; exact-model nonlinear
startup/reclose/bypass simulations including the catch branch; measured first
unit correlation. None is replaced by the round2 simulated 18.02 A result.

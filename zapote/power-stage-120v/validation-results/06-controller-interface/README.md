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

---

# D10: all J4 pins, native-17 (2026-10-02)

**Verdict: FAIL to establish a complete compatible interface.** The power-board
source, frozen netlist and native-17 agree on all sixteen J4 nets, and the CT
burden survives unplugging. However, there is no defined cross-board harness;
the existing controller implements a half-bridge interface, not this four-PWM
full bridge; and the bus-sense divider exceeds the AMC1311B specified input
range before the requested 280 V case. Several electrical/default-state
contracts remain indeterminate. This is a completed desk audit with open
integration findings, not hardware qualification or permission to energize.

The historical CT section above is preserved byte-for-byte, including its
then-current dates, parts and open items. This section supersedes its current
status only. In particular native-17 uses **BAS116H**, not the historical BAT54H,
and J4.13/.14 are **CT_ZC/CT_MON**, not raw secondary wires.

## Identity, method and evidence

- Native-17 PCB SHA-256: `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
- Operator: GPT-6 Astra. All design inputs frozen at
  `587447466ba1fbf04eab29d8d099a2cacc9b2726`; no design files changed.
- [Extraction and calculations](outputs/interface-check.json) contains full
  SHA-256 identities for native-17, the frozen netlist/BOM, all counterpart
  candidates, the root controller PCB/source, firmware pin header and manifests.
  It also records the historical README hash and preservation check.
- [interface_check.py](scripts/interface_check.py) reads S-expressions directly,
  compares J4 source/netlist/native pad net assignments and extracts each
  counterpart's physical connector pins. It emits the full membership of relevant
  CT, supply, fault and ground nets. This proves **exact structural net assignment**;
  it does not prove copper continuity, cable assembly, parasitics or powered behavior.
- Numeric arithmetic is in `calculations` in that output. Datasheet facts and
  scope are indexed in [sources](sources/datasheets.json). Conditional examples
  are explicitly separate from guaranteed specifications. No simulation, native
  build, Rust build, firmware modification or bench operation was performed.
- Correspondence absence is a **review finding**, not an automatic proof from
  net-name equality. The script deliberately emits null cable counterparts.
  Reviewed the unit READMEs/INTERFACES, RTD HANDOFF, connector/source inventories,
  `zapote/ports.toml`, `zapote/project.toml`, root `elec/src/main.ato` and
  `firmware/components/hal/include/temper_pins.h`. `ports.toml` is a registry of
  software ports; `project.toml` declares shared directories. Neither defines an
  electrical harness. Archived source-build copies are used where the standalone
  README's root `elec/src/*_unit.ato` link no longer exists at this commit.

All paths in the evidence are repository-relative at the cited commit. Source
line excerpts include their exact file and line. Netlist entries below identify
physical `reference.pin`, not a name guessed from a schematic label.

## One verdict per J4 pin

Directions are relative to the power board. **PASS** would mean the complete
specified correspondence is proved; no row earns that verdict merely from
local net agreement. **FAIL** identifies a concrete incompatibility with the
stated task. **NO COUNTERPART** means no implemented receiving/producing boundary
for that role; **INDETERMINATE** means candidate circuitry exists but its mapping
or required electrical contract is missing. Every row's source evidence is
`power_stage_120v.ato:541–556`, frozen net membership and native J4 in the JSON.

| Pin | Native net / direction | Exact local endpoint | Other-board evidence and verdict |
|---|---|---|---|
| 1 | v15_selv / OUT | PS1.4 | Root +15V/buck circuitry is a possible consumer, with its own aux source still present. No external controller supply connector/load list. **NO COUNTERPART** for an integrated supply harness; do not parallel supplies. |
| 2 | selv_gnd / return | common SELV net | Possible interlock J2.2/J1.1, current J2.2, thermal J3.2, RTD J2.2/.3, gate-drive J1.4/J5.2; no assigned cable splice. **INDETERMINATE**. |
| 3 | v3v3 / IN | U1.3/.8, U2.3/.8, U4.8, U9.14, U10–U13.5 and passives | Root U27.2 is a consumer; root buck exists in source, but there is no qualified standalone controller power output. **NO COUNTERPART** for supply ownership/current/sequence. |
| 4 | selv_gnd / return | common SELV net | Same candidate returns as pin 2; cable allocation and bond architecture absent. **INDETERMINATE**. |
| 5 | pwm_ha / IN | U1.1 | Root U27.4 = PWM_HS = GPIO4 is a candidate signal, not an exported connector. Which full-bridge leg it drives is undeclared. **INDETERMINATE**. |
| 6 | pwm_la / IN | U1.2 | Root U27.5 = PWM_LS = GPIO5 is a candidate signal; no harness or full-bridge phase assignment. **INDETERMINATE**. |
| 7 | pwm_hb / IN | U2.1 | No second PWM pair in root source/firmware contract. Standalone gate-drive J1.1 is another input, not a producer. **NO COUNTERPART**. |
| 8 | pwm_lb / IN | U2.2 | No second PWM pair. Standalone gate-drive J1.2 cannot supply it. **NO COUNTERPART**. |
| 9 | permit / IN, high enables | R6.1/R14.1 → Q1/Q4 → DIS | Interlock J2.6 = permit, U4.5; matching role/polarity, but unmapped harness, load/level and reset qualification remain. **INDETERMINATE**. |
| 10 | bus_fault / OUT, high faults | U13.4 | Any designated interlock fault input J1.2–.8 is a candidate, none is assigned. U13 final-stage low-level guarantee does not establish the interlock's ≤0.3 V contract. **INDETERMINATE** (specification gap, not measured wrong voltage). |
| 11 | vbus_p / OUT analog | U4.7 | No differential receiver; root U27.38 = V_BUS_SENSE is a different single-ended divider input. At 280 V the transmitter itself is outside its specified linear range. **FAIL** for task-06 voltage-monitoring range. |
| 12 | vbus_n / OUT analog | U4.6 | No second ADC/receiver boundary. This is an active analog output, not ground. Same transmitter range failure. **FAIL**. |
| 13 | ct_zc / OUT logic | U12.1 | No CT_ZC consumer in the reviewed controller interface. Current-sense J2.3 is its own OCP output, not a zero-cross input. **NO COUNTERPART**. |
| 14 | ct_mon / OUT analog | R47.2; R47.1 = ct_sense_mon | Root U27.39 = I_SENSE has its own CT/bias/burden; current-sense J2.4 is an output from another CT. Neither is a drop-in receiver. **NO COUNTERPART**. |
| 15 | selv_gnd / return | common SELV net | Candidate returns above, no cable assignment or current-sharing proof. **INDETERMINATE**. |
| 16 | selv_gnd / return | common SELV net | Candidate returns above, no cable assignment or current-sharing proof. **INDETERMINATE**. |

## Counterpart inventory and wiring exclusions

These are existing native boards, not missing designs. What is missing is their
integration boundary to this J4. The JSON extracts every connector pin from each
listed native PCB, and the corresponding source lines/interface documents are
hashed alongside it.

| Existing board | Native candidate and relevant boundary | Integration consequence |
|---|---|---|
| Interlock | `zapote/interlock/candidate/section.kicad_pcb`: J1.2 OCP, .3 OVP, .4 heatsink, .5 coil, .6 RTD, .7 runaway, .8 AUX; J2.1 supply, .2 ground, .3 WDI, .4 RESET_N, .5 SENSOR_LIVE, .6 PERMIT | Assign BUS_FAULT to one fault channel explicitly. Do not tie push-pull fault outputs together. Other faults, watchdog, live status and reset are still necessary; J4 does not carry them all. |
| Gate-drive | `zapote/gate-drive/candidate/section.kicad_pcb`: J1.1/.2 PWM inputs, .3 PERMIT input, .4 ctrl_gnd; J5.1/.2 3V3/ctrl_gnd | This is another driver unit, not a controller. Its J2.1 15V is referenced to J2.2 gate_l_kelvin/HV return: **not** a load to attach to J4.1 SELV 15V. Native-17 already contains its two drivers. |
| Current-sense | `zapote/current-sense/candidate/section.kicad_pcb`: J1.1/.2 primary current; J2.1 3V3, .2 gnd, .3 OCP_FAULT, .4 SENSE_MON | Own transformer/burden, no external-secondary, CT_MON or CT_ZC input. Its analog output must not be tied to power-board CT_MON. |
| Thermal-sense Rev B | `zapote/thermal-sense/candidate/section.kicad_pcb`: J3.1 3V3, .2 gnd, .3 HS_FAULT, .4 COIL_FAULT, .5/.6 analog sense | Faults can serve interlock J1.4/.5 only through an authored harness. No direct thermal input on J4. Analog monitors may approach the supply rail; receiver loading remains open. |
| RTD | `zapote/rtd/unit/candidate/section.kicad_pcb`: J2.1 3V3, .2/.3 gnd, .4 SCK, .5 SDI, .6 SDO, .7 CS_N, .8 DRDY, .9 HW_FAULT, .10 shared reference | None of SPI/DRDY/reference is on J4. RTD fault is a candidate for interlock J1.6, not a pin already wired to J4. No extra reference output is required by native-17's local reference. |
| Controller in root full board | `pcb/temper.kicad_pcb`: U27.4/.5 PWM, .38 bus ADC, .39 current ADC, .2 supply, .1 gnd. Root connectors J1/J2 serve RTD/fan, not J4 | `elec/src/main.ato:808–811,833,870–871` wires local half-bridge and local sensors. Firmware pin assignments are explicitly provisional. Reusing the MCU does not create the missing connector, second PWM pair or analog receiver. |

**Cable orientation is unresolved.** The exact header is Molex 43045-1612.
Native pad coordinates/numbers are retained in the extraction. The manufacturer's
[header drawing](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/430/43045/430451612_sd.pdf)
and [43025-1600 housing drawing](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/430/43025/430251600_sd.pdf)
are the correct drawing family to review, but no selected cable assembly,
crimp contacts, wire gauge or termination schedule exists in these inputs.
“Straight 2×8 cable” does not specify whether wire-side or mating-face views
are being compared. Do not infer pin 1 → pin 1, or a row reversal, from that
phrase. A production drawing must identify both views and every numbered
cavity; continuity-check all sixteen conductors, absence of cross-shorts and
return continuity before connecting any supply. This check is **not closed**.

## Levels, currents and supplies

**PWM:** TI UCC21550 SLUSE89C p9 specifies input high threshold up to 2.3 V,
low threshold down to 0.8 V, and input pulldowns 50–185 kΩ. At the proposed
3.465 V upper rail a pin loads its source by up to 69.3 µA before cable effects.
Espressif module datasheet v1.8 pp27–28 gives VOH ≥0.8 VDD and VOL ≤0.1 VDD
at 3.3 V/25°C **with high-impedance load**: the arithmetic is 2.64/0.33 V,
compatible with the TI thresholds under those conditions. Its source/sink
current figures are typical, not full-temperature loaded VOH/VOL guarantees.
The selected pad drive, loaded cable levels, edge rate, rail/drop extremes and
reset configuration must be qualified; this is not a guaranteed complete link.

**PERMIT:** Q1/Q4 are AO3400A. Two 100 Ω series resistors feed two 100 kΩ
pulldowns; two 1 kΩ DIS pullups draw at most 7.000 mA under the stated rail
and resistor tolerances when enabled. With a *specified* 2.7 V PERMIT high,
the worst divider gate voltage is 2.69725 V; AOS Rev3.1 p2 specifies 48 mΩ
maximum RDS(on) at VGS=2.5 V, ID=3 A, 25°C. That demonstrates nominal-condition
drive plausibility, not a hot guarantee from a threshold voltage.
The two remote pulldowns alone demand up to 69.93 µA. Interlock R11 adds
its own 10 kΩ load: the total high-state load is about 419.93 µA before
cable capacitance. Its SN74LVC1G74 SCES794G p7 specifies rail-minus-0.1 V
only at 100 µA; the 3 V/16 mA row gives 2.4 V. Thus the actual interlock does
not yet prove the assumed 2.7 V high or the 2.5 V RDS(on) condition at this
load over temperature. This is a qualification gap, not evidence that it
physically fails to turn on. Low/open behavior is addressed below.

**BUS_FAULT:** U9.13 feeds U13.1; only **U13.4** reaches J4.10. The
ISO7710's VCC2−0.3 V/0.3 V figures cannot be substituted for header levels.
At interlock's 3.135–3.465 V rail, its 10 kΩ ±1% pullup draws up to 350 µA;
including the full 20 µA interface allowance gives a conservative 370 µA
sink requirement. SN74LVC1G332 SCES489E p4 guarantees VOL≤0.1 V at 100 µA,
and VOL≤0.4 V at 3 V/16 mA. Neither row proves ≤0.3 V at this intermediate
load across corners; do not linearly interpolate worst-case limits. The
2.3 V/8 mA row is a different supply condition. High-state sourcing with the
same-rail pullup and ≤20 µA external leakage can use the 100 µA VOH≥VCC−0.1 V
row; receiver rail differences/overshoot remain a harness constraint.
Polarity is correct. The strict low-level interlock contract remains unproved.

**Supply ownership:** PS1's V15_SELV has only PS1.4 and J4.1 on native-17.
Mean Well IRM-20, 2025-11-21 p2, rates IRM-20-15 at 15 V/1.4 A (21 W);
p3 derating/installation conditions still apply. There is no committed total
external load/efficiency/inrush schedule, so capacity margin cannot be reported.
The root design has its own auxiliary source; a reuse plan must prevent source
paralleling/backfeed. Gate power comes from the separate HOT PS2 path, not J4.1.

J4.3 supplies **more than U1/U2/U4/U9**: the CT bias/references, U10/U11/U12,
U13 and DIS pullups are also present. The script totals a **31.860 mA conditional
component allowance**: two driver 4.8 mA entries, AMC output side 7.2 mA,
ISO output side 5.6 mA switching allowance, three comparator 65 µA entries,
OR 10 µA plus actual resistive branches. It is not a guaranteed system maximum:
the tabulated IC entries have distinct stimulus/supply conditions; logic
transition current, CT clamp injection, external output loads, supply charging,
cable transients and thermal limits need a joint envelope. It also excludes
all other boards and the ESP32. The root source's LMR51430-based buck
(`elec/src/modules.ato:1422 onward`) is not a qualified standalone regulator
assembly or reserved 3.3 V export. Neither its part headline nor 31.860 mA
establishes controller headroom. Specify one 3.135–3.465 V producer at the
**loaded board pins**, aggregate every consumer, and verify startup/brownout.

## CT and analog receiver checks

The frozen/native nets retain R39=1.5 Ω and C42=100 nF directly across T1.3/.4.
T1.3 reaches R42, not J4; T1.4 reaches its locally bypassed midpoint. Removing
J4 therefore **does not open the CT secondary**. This resolves the historical
unplugged-secondary hazard structurally with the installed burden intact.
R42=1 kΩ feeds BAS116H D4/D5 rail clamps and the three comparators; R47=1 kΩ
feeds CT_MON. CT_ZC comes from U12's push-pull output, high when the sensed
polarity exceeds the midpoint (offset/hysteresis and idle chatter remain).

An ideal 1:100 CT with the nominal burden/midpoint gives CT_MON =
1.65 V ±0.015 V/A × Ipeak, before loading/filter/frequency effects:

| Ipeak | Nominal CT_MON excursion |
|---|---|
| 0 A | 1.650 V |
| 37 A | 1.095–2.205 V |
| 61 A | 0.735–2.565 V |
| 71 A | 0.585–2.715 V |

The nominal burden dissipation at 18.7 Arms primary is 52.45 mW. These are
**conditional operating examples**, not guaranteed fault limits. BAS116H Rev3,
Table7 p3 specifies VF at named currents/25°C; it is not a 0.3 V rail clamp.
R42 isolates the clamps from the actual secondary. A failed-open burden, rail
loss while current persists, clamp injection into an unpowered/non-sinking
3.3 V rail, and clamp/resistor energy are not bounded by this audit. In
particular no claim that all faults remain within an ESP32 ADC absolute limit
is justified. The CT exports are defined signals but lack a qualified bounded
receiver contract. CT_MON is not a raw CT input and needs no second burden.
Use a high-impedance buffered receiver with an explicit loading/acquisition
budget; the separate current-sense unit's ≥10 MΩ assumption is useful context,
not proof it applies to this new receiver. CT_ZC needs qualified loaded levels,
cable drive and idle/timeout policy; it cannot assert sensing validity by itself.

For bus sense, R26–R29 total 1.88 MΩ and R30 is 15.8 kΩ. Exact BOM U4 is
**AMC1311BDWVR**. TI SBAS786C pp10–11 specifies VIN −0.1…2 V, nominal unity
differential gain and common mode 1.39…1.49 V (1.44 V typical). The
nominal linear arithmetic below deliberately stops outside that input range.

| Bus | U4 input nominal | VBUS_P / VBUS_N nominal | Actual ADC code |
|---|---|---|---|
| 0 V | 0 V | 1.440 / 1.440 V | Unknown; receiver, reference and calibration absent |
| 198 V | 1.650174 V | 2.265087 / 0.614913 V | Unknown |
| 280 V | 2.333579 V, outside specified range | No guaranteed linear result | Unknown; must not extrapolate |

The 2 V boundary is 239.975 V nominal. Resistor-only corners use the selected
1% upper string and 0.1% bottom resistor; see JSON for the earlier boundary
and the minimum possible input at 280 V (still above 2 V). These do not include
temperature coefficients or AMC errors. Datasheet clipping voltage is typical,
not a permission to extrapolate its specified linearity. A hypothetical ideal
12-bit ADC measuring the differential voltage against exactly 3.3 V would give
0 and 2048 at the first two cases; **that is not the ESP32's physical ADC
contract**. Root U27.38 expects a single-ended signal from its own divider and
has no declared subtraction/buffer/reference. Never ground VBUS_N or connect
the outputs to two unqualified ADC sample capacitors.

## Default states: the three requested cases

These are explicit prerequisites, not a claim that a nonexistent harness has
passed. UCC21550 p9/§7.3.1 specifies input-supply UVLO; p25 describes DIS.
Outputs held low means commanded gate-off, not measured absence of Miller
turn-on or zero tank current.

| Signal group | Controller unpowered, power board live | Whole J4 unplugged | V3V3 present, controller reset |
|---|---|---|---|
| 15V supply / grounds | PS1 still produces 15V; loads/backfeed depend on unimplemented controller. Return must remain valid. | Header pin1 stays powered relative to local return. No remote return/supply assumed. | Supply remains; reset is not supply isolation. |
| V3V3 | If it truly collapses below driver UVLO, outputs go low after specified UVLO response; independently powered/backfeeding peers can invalidate this premise. | No intended producer, driver input rail loses power; stored charge/CT injection and discharge time must be qualified. | Fully powered; UVLO supplies no reset interlock. |
| PWM5–8 | Undriven inputs have internal pulldowns; external clamp/backfeed levels remain to be bounded. | Internal 50–185 kΩ pulldowns; no PWM source. | GPIO reset behavior is not qualified for four signals. Explicitly configure safe inactive state before enabling. |
| PERMIT9 | Receiver 100 kΩ pulldowns tend to disable when producer loses power; check leakage and rail sequencing. | Q1/Q4 gates discharge through local pulldowns; powered DIS pulls high, or UVLO disables. Finite delay remains. | An independently powered interlock can retain PERMIT until watchdog timeout. Firmware reset is not proved to clear permission immediately. |
| BUS_FAULT10 | U13 supply may be absent, so no driven-high guarantee. Receiver pullup/Ioff cannot replace SENSOR_LIVE. | No receiving fault conductor; an independently powered interlock input pulls high under its leakage contract. | Comparator/OR chain can operate, but HOT rail/bias validity must be enforced separately. |
| VBUS11/12 | Unpowered U4 output behavior is not a valid ADC sample; injection into other powered rails unqualified. | No receiver; no ADC conclusion. | Outputs can be active; reset ADC impedance/sequence unqualified. |
| CT_ZC13 / CT_MON14 | Burden remains; bias/clamps depend on V3V3. Residual tank current may inject into the rail. Neither signal proves readiness. | Burden remains; no remote consumer. Rail-off monitor voltage is not guaranteed within ADC limits. | Bias may be valid after settling; CT_ZC at zero current may chatter. Receiver/reset policy absent. |

Thus clean steady-state unplugging has a local commanded-off mechanism, but
**all three system-level “bridge remains off” cases are not proven**. The
interlock explicitly has no qualified SENSOR_LIVE producer. Its WDI timeout
is 0.9…2.5 s, and deliberate reset requires a fresh falling edge after at least
1 ms healthy, held at least 1 µs (`INTERFACES.md`, hashed contract). These are
not substitutes for immediate reset shutdown or power-valid qualification.
HOT5 brownout remains the known fault-chain gap: U9 default high is specified
only after input supply goes below 1.7 V, with up to 0.3 µs thereafter; TLV3201
operation is not specified throughout the preceding collapse. Do not equate a
missing controller, missing sensing supply and a normal logic fault.

## Timing, return and ranked findings

Dead-time ownership is covered by immutable
[D5, commit 2d6492da](https://github.com/BennetLeff/temper/blob/2d6492da239f0af65822a02c40a2b318bf01f606/zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D5/README.md)
([PR1622](https://github.com/BennetLeff/temper/pull/1622)). No actual per-edge
minimum at the gates was established. Firmware's “500 ns minimum” comment
is not a guarantee; preserve the 307 ns simulation cases. Hardware DT and
controller edge spacing cannot simply be added.

The actual fault chain is comparator/filter → U8/U9 or CT comparators →
U13 → chosen interlock input/filter/latch → J2.6 → cable → Q1/Q4 → DIS →
driver → gate. TI UCC21550 p10 gives DIS response 27…80 ns under its test
conditions. U13 p5 gives 4.5 ns maximum only at the stated 15 pF/−40…85°C
condition (6.2 ns at the separate 30/50 pF, −40…125°C table). ISO7710 p14
3.3 V table gives up to 18.5 ns propagation under its stated conditions.
None bounds the unselected cable, interlock filtering, AO3400A gate dynamics,
comparator overdrive/ramp or MOSFET gate discharge. Existing task02
`round3/b2-gate-off/README.md` remains BLOCKED; no total BUS_FAULT→gate-off or
PERMIT→gate-off bound is invented here.

There are **four**, not five, SELV_GND contacts: J4.2/.4/.15/.16. The actual
return allocation and current sharing need selected contacts, wires, ambient,
rail loads and a permitted voltage-drop budget. Contact count cannot establish
ampacity. Molex's part page headline rating does not qualify an assembled
multi-contact harness. R38 is the local 0 Ω functional PE bond; **D5 is now a
CT clamp**, not the functional earth link. Root `main.ato:753` directly joins
gnd and PE; if that circuitry/bond is retained in a controller reuse, it creates
a second path. That is a **conditional integration conflict**, not proof a
future standalone controller already contains the root monolithic bond.
Verify the final system's one intended functional bond separately from
protective-earth conductors and never rely on J4 for protective earth.

Ranked by safety consequence, not likelihood:

1. **High: unimplemented complete shutdown/default chain.** No qualified
   SENSOR_LIVE, reset-to-PERMIT behavior, rail-loss/backfeed or HOT5 collapse
   contract. No complete shutdown latency. Keep heating inhibited until closed.
2. **High: controller/topology and receiver gaps.** Two PWM sources do not
   define a four-switch full bridge. CT_ZC has no consumer; CT_MON and VBUS
   have no qualified analog receivers. Wiring existing outputs together would
   create contention, not integration.
3. **High: bus monitoring range mismatch (demonstrated calculation).** The
   requested 280 V case exceeds U4's guaranteed input range. This does not
   prove hardware OVP itself fails; it invalidates a linear ADC claim there.
4. **High: cable/supply/return identity absent.** Pin mirroring, source
   paralleling, use of HOT gate-drive supply as SELV and second PE bonds must
   be excluded by the actual assembly. These are prospective errors to prevent,
   not claims an unspecified cable was built incorrectly.
5. **Medium: level guarantees incomplete.** U13's header VOL does not prove
   the strict interlock input contract; the loaded interlock PERMIT high does
   not yet prove the assumed FET gate drive over corners.
6. **Medium: CT export envelope remains conditional.** The local burden fixes
   unplugging, but fault-energy, rail-off injection, ADC loading and CT_ZC idle
   behavior remain unqualified. Historical CT-fix and fault-level prose must
   not be promoted to these stronger claims.

## Requirements for missing counterparts and closure

| Boundary to implement | Required pin/direction/level/current/default/timing contract |
|---|---|
| Controller/supply adapter | Map every J4 cavity to a named connector pin. Pin1 accepts PS1 15V with a bounded external load/derating/inrush schedule and no supply paralleling. Pin3 produces 3.135–3.465V at loads, with full assembled current/thermal budget and power-off isolation. Pins2/4/15/16 have an authored return/bond schedule. |
| Full-bridge PWM producer | Four named outputs for pins5–8, each guaranteed high≥2.3V/low≤0.8V at the receiver with pulldown/cable load, over rails/temperature. Define phase relationship and both gate dead times; inactive on boot/reset/unpowered. Validate D5's unresolved edge path, not just configured register values. |
| Interlock adapter | Pin9 high explicitly qualified for Q1/Q4 load/corners; low/unpowered/reset disables and cannot autonomously restart. Assign pin10 to one active-high interlock fault input; establish ≤0.3V healthy and ≥2.7V fault including actual load/drop. Independently supply WDI, RESET_N, SENSOR_LIVE and remaining fault channels. Bound the complete trip→gate-off time against task02's current/survival requirement. |
| Differential bus receiver | Pins11/12 are both inputs to a receiver with guaranteed common-mode/differential range, loading, acquisition, rail-off behavior and calibrated transfer/reference. Resolve the 280V transmitter range before specifying ADC codes; detect fail-safe output and invalid supply. No arbitrary ground connection to pin12. |
| CT receiver | Pin13 is a logic input with defined thresholds/load, edge timing, zero-current hysteresis/chatter/timeout policy. Pin14 is a high-impedance analog input through the existing output resistor, with acquisition/loading/rail-clamp and fault-energy budgets; no duplicate burden. Missing/invalid sensing must inhibit permission independently. |
| Thermal/RTD/current units | Author their separate supply/return/fault/SPI harnesses to the controller/interlock. Do not force these signals onto occupied J4 cavities. Qualify powered-off fault-driver behavior and live status; preserve separate push-pull outputs. |

A future permanent **Rust** cross-board rule should consume an electrical
connection manifest (not today's software-port list): revision/hash-bound
board+connector+pin identities, domain/return, direction/driver type, supply
owner, level/current/load corners, powered-off leakage, cable cavity views,
latency and fail-safe state. It should reject output-output joins, absent
producers/consumers, HOT/SELV supply confusion, missing return/bond contracts,
out-of-range analog transfer, and a claimed guarantee supported only by
nominal/typical data. Unknown assembly or timing must remain an explicit
indeterminate finding. No permanent rule is implemented in this desk script.

Closure needs a reviewed harness drawing and unpowered continuity/polarity
check first, then isolated low-energy powered interface measurements across
supply/reset/unplug/rail-loss cases with recorded loads and waveforms. Confirm
local CT burden and residual-current behavior, actual four-gate edges, fault
latency, analog acquisition and supply/return drop before the separate power
bench procedure. All physical checks are **NOT RUN**.

## Reproduce D10

From repository root, using Python standard library only:

```sh
python3 zapote/power-stage-120v/validation-results/06-controller-interface/scripts/interface_check.py --output /tmp/d10-interface-check.json
cmp /tmp/d10-interface-check.json zapote/power-stage-120v/validation-results/06-controller-interface/outputs/interface-check.json
```

The script rejects changed cited inputs and altered historical CT text. It is
an extraction/evidence replay, not a physical acceptance gate. Null counterpart
and ADC fields are deliberate unresolved findings, never silently passing data.

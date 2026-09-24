# U2 topology screen — no circuit selected

This is a bounded comparison using the Rev38 source snapshot in [energy-islands.md](energy-islands.md). The product discharge voltage/time limit, initial voltage envelope, inverter capacitance, mains-isolation behavior and single-fault rule are open. Consequently, no resistor, relay, semiconductor or safety rating is selected here. Run the source-contained arithmetic fixture in `evidence/discharge_screen.rs` to reproduce the nominal and mutation screens.

## What the historical target would cost

The earlier split-bus plan targeted <34 V in <60 s from roughly 170 V per half-bus. That target is neither a Rev38 requirement nor proof of an allowed bus voltage. As a **hypothetical 400 → 34 V sensitivity example**, an ideal 2688 µF tolerance-high VB bank must see total equivalent resistance at most

```text
R ≤ 60 / [0.002688 × ln(400/34)] = 9054.96 Ω.
I at 400 V = 44.17 mA; P if continuously energized = 17.67 W.
Initial stored energy at 400 V = 215.04 J; at 450 V = 272.16 J.
```

A path meeting that example must handle the bank's pulse energy on power removal and its **continuous** dissipation if engaged while mains is still present. At 450 V and the same 9.055 kΩ, continuous resistor power is about 22.36 W; 450 V is a bank rating-edge calculation, not permitted operation. A real design needs resistor tolerance, derating, hot enclosure, DC switching, inrush, timing margin and physical clearance. The proposed value is not a part selection. At tolerance-high VD C, either existing ladder alone takes 60.49–61.72 s for the same illustrative 400 → 34 V drop even before resistor tolerance; both intact take about 30.55 s. Thus a single-open path can cross that historical target, and the existing ladders cannot be declared fault-qualified.

The same source C-high and illustrative 400 → 34 V interval show how the unadopted time criterion changes the topology choice. These are **maximum equivalent R** and **minimum continuous passive heat at 400 V** if the full bus remains energized, with no inverter C or margin:

| User-supplied time | Maximum VB R | Minimum passive heat |
| ---: | ---: | ---: |
| 30 s | 4.53 kΩ | 35.34 W |
| 60 s | 9.05 kΩ | 17.67 W |
| 120 s | 18.11 kΩ | 8.84 W |
| 300 s | 45.27 kΩ | 3.53 W |
| 1800 s | 271.65 kΩ | 0.59 W |

Thus the architecture recommendation depends materially on the adopted time, continuous heat allowance, and whether source recharging can be removed. Even the original VB paths' C-high time is about 2052 s for this illustrative interval, before resistance tolerance or a failure.

## Alternatives

| Architecture | Nominal benefit | Failure and cost to prove |
| --- | --- | --- |
| Existing paths only | No new parts; both islands have some passive conductance with F2 open. | VB is roughly 28.5 min nominal to historical 34 V target with all paths, over 91 min if the bank bleeder opens. VD has no dedicated bleeder. None of these paths has accepted safety status or observation. |
| New passive paths on both VD and VB | Physical power-off behavior independent of logic; avoids DC switch action. | VB continuous dissipation becomes substantial for a short target. Each path must survive maximum energized bus, temperature, failed-short and single-open cases. Parallel redundancy may be needed. VD and VB still require separate measurement. |
| Normally engaged active path plus passive backup **per island** | Potentially low normal-run loss with faster discharge after supply loss. | AUX can disappear while mains still feeds the rectifier through NTC and boost diode. An engaged path may see continuous live-bus power. NC relay contacts need verified high-voltage **DC** make/break and coil collapse timing, or semiconductor SOA and default bias. A stuck-open contact falls back to the passive path's time; a stuck-closed device faces prolonged heat. |
| One active path on VB only | Fewer devices. | **Rejected as complete topology:** F2-open VD retains its own capacitor, and a later inverter disconnect can strand another reservoir. It cannot satisfy the island requirement. |

The legacy `BusDischarge`'s 170 V relay, snubber and resistor evidence does not establish DC operation at this bus voltage. Neither a catalog AC contact rating nor a resistor's continuous wattage by itself proves pulse, contact arc or hot enclosure behavior.

## Negative cases to carry into circuit selection

| Case | Required result in a future model/test |
| --- | --- |
| F2 open and both islands charged | Independently compute VD and VB decay; fail if only VB is drained. |
| F2 open and both VD ladders open | Current source has no VD-to-HOT0 resistor; require a new independent path or explicit failed-service disposition. |
| One bank bleeder resistor open | Existing detector-only path is very slow; fail any fast nominal target. |
| Active contact fails open or resistor fails open | Use remaining passive path, not nominal active time; report whether normal criterion still holds. |
| Active contact welded closed, mains live | Compute continuous power and component temperature with source-fed bus, not a finite-energy pulse only. |
| AUX collapses while mains remains | Do not solve an isolated RC; passive bridge/inductor/diode can replenish VD and, with F2 intact, VB. |
| Partial charge | Evaluate from each allowed initial voltage, including a restart request before discharge completes. |
| `VD = VB > 0` | Equal readings do not prove either safe charge or F2 continuity. Deny restart until absolute and continuity/precharge requirements are independently met. |
| Inverter local input capacitor disconnects | Model it as another isolated capacitor and require its own path/measurement. |
| Inverter bridge shorts VB | Do not credit F2 as a bank-side interrupter; assess bank energy and available source fault current. |

The Rust fixture checks the source-derived nominal topology and several negative mutations. It deliberately contains no assertion that a service limit is met. Circuit selection waits on the six decisions in [interface-contract.md](interface-contract.md).

## Decision-ready conditional candidate, September 23

**Recommendation for the next design experiment:** use separate, redundant **passive VD strings** and a **normally closed, switched VB resistor bank** in parallel with the existing VB bleed/divider paths. Advance this as a bench and digital candidate only after the gates below are answered. This split is grounded in energy: tolerance-high VB holds 215 J at the 400 V screen, while VD holds under 2 J, so fast passive VB bleeding causes much more continuous heat than passive VD bleeding. A bank-only active path remains excluded.

The candidate topology for the parametric screen is:

```text
VD--[4 x 200 kΩ TNPW1206]--HOT0   (string A)
VD--[4 x 200 kΩ TNPW1206]--HOT0   (string B, independent)

VB--[NC Coto 5504 contact]--+--[7.5 kΩ RH50]--[7.5 kΩ RH50]--HOT0
                            +--[7.5 kΩ RH50]--[7.5 kΩ RH50]--HOT0
VB--[Rev38 existing 3 x 150 kΩ and detector divider]---------HOT0
```

The two 7.5 kΩ resistors in each VB branch ensure one resistor short leaves **at least 7.5 kΩ** between the bank and HOT0 when the contact closes. A single NC contact still defeats both fast branches if it fails open; this is a known architectural failure, not a hidden pass. The two VD strings are independent of the existing detector/VSENSE ladders and each alone can discharge the local source capacitance in the historical sensitivity window at initial-tolerance-high C. A single short within a VD string leaves three 200 kΩ parts; at 450 V they each see nominally 150 V, below the 200 V element operating limit, subject to resistance tolerances and installation. Any one VD string open leaves the other.

**Manufacturer screen, not selected BOM:** Vishay [TNPW e3](https://www.vishay.com/docs/28758/tnpw_e3.pdf) lists 1206 operation at 200 V and the 200 kΩ value within the series range; a 1% option exists. Vishay Sfernice [RH50](https://www.vishay.com/docs/50013/rh.pdf) covers 7.5 kΩ, with a 1285 V RMS voltage limit and 50 W mounted rating at 25 °C, **40 W mounted at 70 °C only under the datasheet's 536 cm² chassis fixture, versus 9.6 W unmounted at 70 °C**. The [Coto 5504-12-1](https://www.cotorelay.com/reed-relays-bga-relays/) is a 12 V Form B (normally closed) load-switching reed relay; its [5500 series datasheet](https://www.cotorelay.com/datasheets/Coto%20Technology%205500%20Reed%20Relay.pdf) lists for 5504 a 3500 V DC resistive switching-voltage maximum, 3 A switch-current maximum, 200 W resistive contact rating, 85 °C operating maximum, 12 V coil option with 175 Ω ±10% at 25 °C, and **typical** 3 ms release. These individual catalog values do not establish its loaded release maximum, 390–450 V cycle life, insulation class, package creepage, availability, or required coil-drive rail. Its 12 V coil draws about 69 mA / 0.82 W nominal, and its Form B bias magnet requires correct polarity and placement review. Rev38 has only an unresolved `AUX_PROTECTED` source, so even the coil hold supply is not yet assigned.

| Conditional bound | Intact candidate | One adverse element |
| --- | ---: | ---: |
| VD effective dedicated R at +1% tolerance | 404 kΩ | 808 kΩ after one string opens |
| VB effective fast R at +1% tolerance | 7.575 kΩ | 15.15 kΩ after one 7.5 kΩ element opens |
| 400 → 34 V time at source C-high, with 1 s active release allowance | VD 24.62 s; VB 51.19 s | VD 49.23 s; VB 101.39 s |
| F2 open: 450 → 34 V, +100 µF direct inverter C, 5 s active release allowance | VD 25.79 s; VB 59.55 s | VD 51.58 s; VB 114.10 s |
| Intact VB fast-path power with mains still attached | 21.33 W at 400 V; 27.0 W at 450 V | One 7.5 kΩ resistor short: **21.33 W or 27.0 W in the surviving series resistor alone**; total 32.0 W or 40.5 W |

The timing table evaluates **F2-open independent islands**. If F2 stays closed, VD's 24.717 µF tolerance-high reservoir joins the bank. At the 450 V/+100 µF/5 s edge, VB fast branches alone would then take **60.03 s**. The two candidate VD strings also conduct across the joined bus and reduce the coupled result to **59.02 s** in the ideal RC fixture. Thus the 0.45 s F2-open VB margin is not a whole-network margin; even the coupled 0.98 s ideal margin is too narrow for a part selection without actual contact and tolerance data. The fixture prints and tests both cases.

The 450 V row is a **rating-edge sensitivity**, not an allowed VB operating state. The 34 V/60 s values are historical inputs to a screening calculation, not accepted Rev38 criteria. The stated times conservatively give no credit to the original Rev38 resistor paths or to capacitor leakage and use source capacitor initial tolerance only. They do not include resistor temperature drift/aging, capacitance variation with use, installation thermal impedance, coil release distribution, mains-fed recharging or software delay. The normal candidate at 450 V with +100 µF and 5 s release has only **0.45 s** of screen margin; it is too close to treat as a selection.

At 450 V a short in one VB resistor puts approximately 27 W into the surviving 7.5 kΩ resistor and about **181 J** of the 272 J bank discharge into it, while the other branch's two resistors receive about 45 J each. The per-resistor steady power is below RH50's 40 W **mounted at 70 °C** figure, but above its 9.6 W unmounted figure. Thus the housing/heatsink, contact location and airflow are mandatory parts of this candidate. The RH50 catalog's mounted rating uses a 536 cm² chassis fixture for RH50; four resistors sharing one actual enclosure need an equivalent measured thermal path and aggregate temperature analysis, including fan-off AUX loss. The catalog does not grant an installed 181 J pulse rating from its printed wattage; thermal impedance and repeated events need manufacturer or measured evidence. At intact 450 V, each RH50 starts at 6.75 W, with roughly 68 J of bank energy per resistor if the fast paths dominate. Exact contact switching voltage × current is about 27 W intact and 40.5 W under the single-short case at 450 V, below the 5504's 200 W resistive nameplate, but DC switching life and temperature require application evidence.

### Why power-loss default alone does not close the case

Rev38 `ac_input.ato` leaves the NTC in series when its bypass relay opens. The bridge, boost inductor and diode form a passive route from live mains to VD even if gate drive and AUX stop. If F2 conducts, VB can also be maintained. A normally closed discharge contact would then insert the resistor network across a live source indefinitely. The screen above therefore computes **continuous** dissipation for AUX-loss/mains-attached faults and refuses any finite isolated-RC completion claim in that state. It does not claim the source will sit at exactly 400 or 450 V; those are user-supplied screening voltages. A product architecture must choose whether the contact remains closed while mains remains, whether an independent upstream isolation element exists, or whether the resistors and enclosure are rated for indefinite powered operation.

### Selection gates

1. **Requirement:** Adopt service and restart voltage/time, which nodes are accessible, and what a single open actuator or resistor must accomplish. If a single open must still meet the normal fast time, this one-contact/two-branch VB candidate **fails** and needs independently switched redundant paths or a different topology.
2. **Rev38 and inverter boundary:** Freeze maximum VD/VB voltages and transients, C over life, direct inverter C, its disconnect, and F2/source behavior. Replay the hash-pinned source check on any change. The active Rev38 checkout is separate and uncommitted; this candidate uses only the committed source snapshot.
3. **AUX/mains behavior:** Declare coil hold rail and its voltage/load budget, guarantee de-energization when required, bound release time, and rate sustained resistor temperature for AUX absent with mains attached. A single Coto contact has no claimed minimum or maximum loaded release from the typical 3 ms entry.
4. **Exact parts and assembly:** Confirm specific RH50 value/order codes, mounting surface and its equivalence to the datasheet's 536 cm² chassis, aggregate four-resistor heating without fan, case temperature, 181 J single-short and repeated pulse endurance, lead/copper current and voltage, resistor body-to-chassis insulation and spacing, relay coil polarity/interference, 390–450 V low-current make/break endurance and winding-to-contact isolation. A board-only construction cannot claim a chassis-mounted RH50 rating without the chassis.
5. **Coupled cooling loss:** Treat AUX loss with mains attached as a common-mode event: the NC contact closes while the selected fan rail may disappear. Hand the 21.33/27.0 W intact and 32.0/40.5 W one-short sustained screen to the cooling owner with resistor/chassis coordinates. Do not use forced-air mounted RH50 ratings for that condition unless an independent fan supply and airflow are demonstrated.
6. **Observation and fault handling:** Give VD, VB and any disconnected inverter C independent powered-off verification; distinguish contact stuck open, one resistor open/short and F2 open. Equal VD/VB remains insufficient for restart.

The bounded decision is **advance the per-island passive-VD / active-plus-existing-passive-VB architecture to exact-part and thermal experiments if single-open fast discharge is not required**. If that single-fault deadline is required, redesign the VB path before schematic capture. No source circuit or manufacturing acceptance is authorized by this screen.

### Reproduce

From the worktree root:

```sh
shasum -a 256 -c zapote/discharge/evidence/source-inputs.sha256
rustc --edition=2021 --test zapote/discharge/evidence/discharge_screen.rs -o /tmp/zapote-discharge-screen-test
/tmp/zapote-discharge-screen-test
rustc --edition=2021 zapote/discharge/evidence/discharge_screen.rs -o /tmp/zapote-discharge-screen
/tmp/zapote-discharge-screen 400 34 60 0 1
/tmp/zapote-discharge-screen 450 34 60 100 5
```

Arguments are initial voltage, target voltage, target time, direct inverter input capacitance in µF, and allowed NC-contact release delay in seconds. They are **scenario inputs**, not encoded appliance requirements. Mains must be absent for the calculated decay time to apply; the fixture explicitly rejects a decay-time claim while mains can supply the bus.

# Single faults, section flashover, and the BNC boundary

Research, 2026-10-20; no circuit, BOM or board changes. Basis: Rev B `README.md`, `design.md`, `circuit-revb.md`, `qualification.md`, `tools/build.rs` and exported netlist. Probe PCB SHA-256: `b0c15add2b69967cee0593962e1b3b22795725ed36ccbfc408b05c3fb4002b65`; netlist: `b06d2c6f8a2a2578d247a0bdb5bf0724eac674574c7086e6b8be750d408b7a64`. Stage53 remains `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`, verified unchanged. The repository baseline check separately passed for stage15b; no stage15b fault source is transferred here.

**Verdict:** surviving four sections have useful voltage margin after an ideal single-section short. That is not evidence that a flashover stops there, or that the BNC/USB remains safe after a whole-ladder bypass. The present circuit has attenuation and overload clamps, without an independent galvanic output barrier.

## Component fault matrix

**Observed topology; calculated ideal responses**, identical for either input. Each upper section is `2 MΩ || 33 pF`; the bottom is `5002.501 Ω || 13.1934 nF`. Ratios below are tip/tap, before amplification. They assume intact earth, supplies and remaining components; “HF” excludes parasitics and device clipping.

| Fault, either leg | Result and consequence |
|---|---|
| Any one R1–R10 / R21–R30 short | DC ratio **1800.1:1**, 1.667 V tap at 3 kV; HF ratio remains approximately 2000:1. Compensation and CMRR fail. DC current 333.15 µA; unaffected whole sections see 666.3 V. |
| Any upper resistor open | DC tap tends toward ground through the bottom; the affected 33 pF still passes AC. At DC the failed resistor and its section capacitor can approach the full input voltage; a quiet output is not proof of intact insulation. |
| Any C1–C5 / C21–C25 short; whole section bridged | Both its resistors are bypassed: **1600.2:1** across ideal frequency range, 1.875 V tap at 3 kV. Signal increases approximately 25%; other leg remains unchanged. |
| Any upper capacitor open | DC ratio stays 2000:1. HF attenuation increases and that section can approach the full applied AC voltage; its two resistors then share approximately half each under ideal symmetry. |
| Entire section open, including capacitor | Conductive signal path interrupted; stray capacitance and leakage determine remaining response. No calibrated ratio. |
| R11/R31 open, or trim track/end connection open | DC return disappears; D1/D2 must carry approximately 0.30 mA at 3 kV through the intact upper ladder. Low-leg capacitors still provide AC return. |
| R11/R31 short | Only nominal 12.501 Ω trim remains: DC ratio approximately **799,921:1**. Loss of response; HF compensation also fails. |
| RV1/RV2 short / wiper contact open | Short gives **2005.01:1**. Wiper-only open retains the full 50 Ω track through the tied end: **1985.13:1**; track rupture is the open-return case above. |
| Any bottom capacitor or CT1/CT2 short | Tap grounded; no useful signal from that leg. Upper loading remains present. |
| Any bottom capacitor / AC trim open | DC ratio unchanged; reduced bottom capacitance increases HF gain. Losing the 10 nF part leaves 3.1934 nF: HF ratio approximately **484.8:1**, demanding 6.19 V at 3 kV before clamping. Losing nominal 35.4 pF trim alone increases HF gain approximately 0.27%. |
| R12/R32 open / short | Open loses signal; short removes 220 Ω local isolation. Upper ladder remains the principal source impedance. |
| Buffer input/output/rail short or open; feedback open | Invalid, railed or missing output; possible rail injection. An intact divider still limits input energy. Neither amplifier is an insulation barrier. |
| Clamp diode open / short; TL431/feed open / short | Lost polarity protection, erroneous clipping, reference collapse or rail coupling. Shared references couple faults into both legs, warnings and D3. |
| One/both rails absent, regulator failed, ground/shield bond open | Output and warning invalid; clamp bias or earth reference lost. Ground/shield opening can leave accessible metal floating. |

## What the 750 V result establishes

With one section shorted, `I=3000/(8 MΩ+5002.501 Ω)=374.77 µA`. Each remaining section sees **749.53 V**, each resistor approximately 374.77 V and **0.1405 W** at 3 kV DC. The effective top capacitance becomes 8.25 pF, so ideal capacitive and resistive ratios still match. At 3 kVpk/60 kHz, input current becomes approximately **6.60 mArms**, 25% above nominal.

The archived [KEMET selected-part sheet](../../sources/C1812C330JHGACTU.pdf), p.1, specifies **3000 VDC**, with 3600 VDC dielectric withstand. Those numbers support substantial steady-state voltage margin at 750 V. They do not establish repetitive 60 kHz endurance, post-arc insulation, transient redistribution, or a safe failure mode. A component short is a useful bounded fault model; carbon tracking, contamination or an arc crossing several nodes is a separate physical/common-cause scenario. A single initiating event can bypass many components without requiring five independent capacitor failures.

## What actually limits BNC and USB exposure

D1/D2 connect buffer inputs through BAV199 junctions to ±2.495 V TL431 references; R12/R32 are 220 Ω. D3 connects the BNC centre **directly to those same references**, after 49.9 Ω R70. Reference-feed 1 kΩ resistors are supply feeds, not series HV barriers. [BAV199](https://assets.nexperia.com/documents/data-sheet/BAV199.pdf), p.2, permits 160 mA continuous per single loaded diode and specified pulse currents; [TL431](https://www.ti.com/lit/ds/symlink/tl431.pdf), pp.5,18, specifies 1–100 mA operating cathode current and load-dependent stability. Neither promises arbitrary fault-energy absorption. The overload LED interrupts nothing.

Normal protection relies on **intact upper impedance and insulation**, bounded amplifier supplies, local clamps, and the BNC/earth bond. A whole-upper bypass removes the first protection. HV can then enter the input/clamp/reference/ground network; D3 is not independent containment. A direct HV-to-shield arc additionally bypasses signal clamps. USB would add another conductive return into its host; an isolated USB power converter alone leaves the BNC path intact. Tektronix's [P5200 grounding notice](https://www.tek.com/en/services/safety/p5200-high-voltage-differential-probe-notice) demonstrates why a grounded BNC is integral to some differential-probe architectures; it does not qualify this assembly's bond as protective earthing.

Bound energy explicitly. The nominal upper 6.6 pF stores only **29.7 µJ** at 3 kV; an external source can replenish it. For an illustrative **3 kV, 100 kΩ Thevenin source, 1 ms pulse**, whole-upper bypass, intact bottom and an assumed 3.2 V input clamp, `Vth=142.93 V`, `Rth=4764.17 Ω`: clamp current is **28.03 mA**, R12 energy **0.173 mJ**, aggregate clamp energy **0.0897 mJ**. This is a calculation example, **not stage53's source** or a survival test. Current, pulse width, source capacitance/inductance and interruption time remain required inputs. No guarantee is possible with unbounded fault energy.

## Pods and protection choices

A pod with its bottom in the box can charge an unplugged centre toward HV. A complete local bottom preserves attenuation relative to its shield, but an open shield allows both conductors to float; shrouding and connection sequencing remain necessary.

Prefer two investigations: physically separated, independently rated impedance sections with coordinated shunts and a defined fault-current return; or a floating front end with optical signal/power isolation, as demonstrated by [Tektronix IsoVu](https://download.tek.com/datasheet/TIVP-Datasheet-51W616554.pdf). Adding TVS/GDT devices alone needs pulse, follow-current and failure coordination: [Littelfuse's GDT guide](https://www.littelfuse.com/assetdocs/gas-discharge-tubes-catalog?assetguid=c1597a5f-aedf-4ea0-8ca3-d2eadd0de6a5) explains sustained conduction after sparkover. [AMC3330](https://www.ti.com/lit/ds/symlink/amc3330.pdf), pp.6,8, illustrates reinforced isolation, but its 1200 Vrms/1700 VDC working limits and 375 kHz typical bandwidth exclude a direct 3 kV/5 MHz substitution.

Next: define the actual source envelope and acceptable accessible voltage/current, model fault transients including floating/disconnected cables and unpowered clamps, then design controlled component-fault and arc-containment qualification. Current evidence is topology plus calculations and datasheets; **no single-fault survival has been measured**.

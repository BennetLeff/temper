# Revision 18 — exact capacitor candidates and revised prototype allocation

PCBParts is connected. The user authorized packages chosen to meet electrical
limits and requested Luna delegation. Three Luna research blocks and one
follow-up produced the retained handbacks; the parent corrected and integrated
them. This is a **prototype design selection**, not an accepted production BOM.
The full compiled circuit remains revision11 / 136 components.

The [new clamp schematic](clamp.kicad_sch) and [PDF](clamp.pdf) carry exact
C2/C3/C4 MPN, Manufacturer, LCSC where available, and Datasheet fields. Native
connectivity is unchanged: 14 components, 39 pins. Frozen revision16 is intact.
`source-bindings/` contains proposed Atopile copies for three downstream
capacitors, with MPN and footprint assignments. These copies have **not** been
compiled into the full candidate and are not manufacturing identity authority.
The existing PFC capacitor is retained, not substituted.

## Parts carried into this review

| Function | Exact candidate | Package / procurement identity | Status |
|---|---|---|---|
| C2 timer | TDK C3216C0G2A104JT000E | 100nF, 100V, C0G, ±5%, 1206; C338111 | Selected for prototype schematic |
| C3 gate | KEMET R75GN415050H0J | 1.5uF, 160V, polypropylene, ±5%, 22.5mm pitch; Mouser 80-R75GN415050H0J | Selected for prototype schematic; no LCSC match claimed |
| C4 bulk | Rubycon 63ZLJ330M10X20 | 330uF, 63V, ±20%, radial 10×20mm nominal, 5mm pitch; C437643 | Selected for revised prototype allocation |
| Buck VIN | TDK C3225X7R2A106KT000E | 10uF, 100V, X7R, ±10%, 1210; C49296968 | Proposed source binding; effective minimum unresolved |
| PFC VCC | KEMET C0805C105K5RACTU | Existing 1uF, 50V, X7R, ±10%, 0805; C3018567 | Existing identity retained |
| Driver local bulk | Samsung CL32B105KBHNNNE | 1uF, 50V, X7R, ±10%, 1210; C40708 | Proposed source binding; existing package size retained |
| Driver HF | Samsung CL31B104KBCNNNC | 100nF, 50V, X7R, ±10%, 1206; C24497 | Proposed source binding |

`pcbparts-selected.json` preserves the lookup results. Indexed stock is a dated
search observation, not an order reservation. C3 was independently found through
PCBParts' Mouser lookup, so it is not the unconfirmed ordering hypothesis in the
Luna follow-up. No parts were ordered.

## Why the allocations changed

The old 220uF/300uF-total combination does not cover the selected Rubycon series'
separate initial tolerance and post-endurance capacitance change. At 220uF,
those factors give 132–330uF before adding bypass capacitance. Even the
tolerance-only bypass maximum, 13.31uF, needs 133.1uF bulk under the conservative
10× rule. The old combination fails both ends of that screen.

For 330uF, the same explicitly separate test factors give **198–495uF**.
Revision18 proposes an **18uF maximum for all direct downstream bypasses** and
a **520uF maximum total**: 198≥180uF and 495+18=513≤520uF. The 18uF number is an
acceptance allocation still to be demonstrated, not a measured or guaranteed
property of the chosen MLCCs. Their 12.1uF nominal sum becomes 13.31uF with
initial tolerance alone, or 15.3065uF after additionally applying X7R's ±15%
temperature class. Neither calculation establishes their combined DC-bias,
temperature, aging, frequency and assembly behavior. No optional buck capacitor
has been added.

These Rubycon limits describe initial and post-endurance tests. Multiplying
their extrema is a conservative screen, not a manufacturer guarantee of
simultaneous endpoint values or **in-operation full-temperature/lifetime
capacitance**. The 520uF
allocation replaces 300uF only in this prototype proposal. It does not pass a
physical qualification gate by changing its threshold.

C3's former 1.35–1.65uF target also needed reconciliation. The proposed PET
part, R82DC4150AA60J, reaches 1.655325uF at +105°C using the published maximum
positive temperature coefficient and initial tolerance, before storage drift.
It was rejected. The orderable R75H polypropylene part has a negative
temperature coefficient. Conservatively stacking ±5% initial tolerance,
−(200±100)ppm/°C over −40…+105°C relative to +20°C, the specified 0.5% storage
change and the separate 3% endurance-test change gives **1.340268–1.659708uF**.
The revised prototype acceptance allocation is **1.30–1.70uF**. This stack is
a sensitivity screen using separate specified conditions, not a guarantee that
the endurance test predicts appliance life. In particular, harsh-humidity tests
permit larger drift; the actual environment and service life remain undefined.

With 520uF output and 1.30uF gate minimum, the inherited 65uA gate-current test
datum gives a **26mA capacitive ramp screen**. Including the inherited operating
load, support estimate and 0.208mA allowance for C4's catalog leakage gives
141.463mA, below the conditional 202.520mA non-foldback current minimum.
Below the foldback region, the 67.507mA screen leaves 41.299mA after capacitive
ramp and C4 leakage, **before other loads**. Full operating load still cannot
be assumed during startup. Gate-current conditions, Miller charge, converter
startup, source impedance and added decoder loads remain unresolved.

Increasing C3's upper allocation can affect fault response and discharge.
Neither the ramp arithmetic nor a capacitor's pulse rating proves the driver
rail remains below18V during a surge. The existing fault-peak, turn-off,
stability and MOSFET SOA bench requirements remain mandatory.

## Manufacturer evidence and mechanical review

- [TDK C2 characterization](https://product.tdk.com/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c3216c0g2a104j160ac.pdf),
  dated 2019-05-22, names C3216C0G2A104J160AC and item description
  C3216C0G2A104JT****. PCBParts identifies the ordered T000E variant. C0G
  ±30ppm/°C plus initial tolerance screens to94.75775–105.26775nF over the
  provisional range. The5Gohm insulation datum is not an all-temperature
  leakage bound. Board leakage and full timer-current limits remain separate.
  Direct PDF downloads returned403; the official text was available through
  web retrieval. Its curves are not promoted to guaranteed limits.
- [KEMET R75H](https://content.kemet.com/datasheets/KEM_F3121_R75H.pdf),
  2025-05-05, retained locally: p2 decodes packaging50 as25mm long leads;
  p4 gives dimensions; p5 temperature/storage conditions; p11 endurance;
  p12 the1.5uF/160V row. Nominal body26.5×10×18.5mm; maximum26.8×10.2×18.6mm,
  pitch22.5±0.4mm, wire0.8±0.05mm. Leads must be trimmed for assembly.
  The standard26.5×10.5mm/22.5mm KiCad footprint is a land-pattern candidate,
  despite its MKS4 name; its generic3D model does not certify the KEMET body.
  The row specifies70V/us and7.26Arms at100kHz/90°C under its thermal condition,
  not a105°C application rating. Voltage derating starts above105°C.
- [Rubycon ZLJ](https://www.rubycon.co.jp/wp-content/uploads/catalog-aluminum/ZLJ.pdf),
  retained locally, p1: ±20% at20°C/120Hz, ±25% post-endurance,10,000h for the
  selected10×20mm case. P2: maximum body diameter10.5mm and length22mm,
  pitch5±0.5mm,0.6mm wire. P3: selected63V/330uF/10×20mm row gives2Arms at
  105°C/100kHz and maximum impedance42mohm at20°C,130mohm at−10°C. Impedance
  is not a frequency-independent ESR guarantee. The0.55 factor gives1.1Arms
  at120Hz. The sheet does not provide a full hot/cold capacitance surface.
- [TDK buck capacitor](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C3225X7R2A106K250AC),
  [Samsung driver bulk](https://product.samsungsem.com/mlcc/CL32B105KBHNNN.do),
  [Samsung HF](https://product.samsungsem.com/mlcc/CL31B104KBCNNN.do), and
  [existing KEMET PFC part](https://search.kemet.com/component-documentation/download/specsheet/C0805C105K5RACTU)
  are the exact-family evidence routes. Their effective minimum values at the
  protected rail are not closed by this review. The TPS54202 recommendation for
  more than10uF remains an application-review item; a nominal10uF part is not
  claimed to meet a guaranteed10uF effective minimum.

−40…+105°C is a provisional part-screening range, not a newly asserted appliance
environment. No PCB placement, clearance, height/cover fit, thermal solution,
surge waveform or assembly qualification was performed.

## Verification and next step

Nine focused Rust checks pass, including rejection of the old allocations,
non-finite-input rejection, the bulk-ratio counterexample and foldback limit.
The unchanged revision16 auditor verifies the newly exported39-pin clamp graph
alongside its unchanged106-pin reset reference, including its mutation checks.
Native clamp ERC retains the same seven external-boundary findings; none is
waived. The schematic was exported and visually inspected. These checks verify
the recorded proposal, not the remaining physical claims.

`clamp-review-bom.csv` was generated directly by KiCad from the schematic;
its three populated capacitor identities match the table above. Other blank
MPN fields remain explicit. This is not a complete purchasing BOM.
An independent Luna review is retained in `review-handback.md`; parent
corrections and dispositions are in `review-resolution.md`.

Next, obtain exact biased MLCC curves/limits and bound converter startup and
gate discharge with these candidate values. Then integrate the proposed source
bindings and the reset/watchdog producers into one compiled circuit. Keep the
revision15 bench worksheet, now using520uF output and1.30–1.70uF gate corners.
Do not purchase or release manufacturing outputs from this review fixture.

No commit, push, production-source adoption or PCB change was made. Raw Luna
handbacks are advisory; this parent-reviewed document supersedes their proposed
part choices, dimensions, lifetime interpretation and incomplete tolerance sums.

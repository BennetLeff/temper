# Rev C placement-library audit

The part-specific orientation check is complete for all 19 unique keyed SMT part numbers in this design, plus the new 1210 capacitors and 0805 ferrite beads. **This is not assembly release approval.** All previously open manufacturer mechanical checks are now resolved. The hand-fit J2 jack corrections documented below are now applied by the native generator. Final JLC placement preview remains the normal order-review step.

Use `sources/placement-rev-c.json`, specifically `rotation_offsets_by_ref`, for Rev C CPL generation. The older `placement-audit.md` and `cad/placement-offsets.json` describe Rev A and must not be reused as the Rev C authority.

## Evidence and method

Read-only public records were retrieved on 2026-10-20 from the [JLCEDA / EasyEDA Official Library](https://easyeda.com/) through each exact LCSC part's `/api/products/C.../components` record. The JSON includes the source URL, SHA-256 of the complete response, library owner/UUID, original numbered pad coordinates, native KiCad pad coordinates and source footprint SHA-256. Source information is from [EasyEDA](https://easyeda.com/) / [JLCEDA](https://lceda.cn/); library geometry was inspected as evidence, not copied into CAD.

Native coordinates were obtained from KiCad's own `pcbnew.FootprintLoad` at zero orientation. J1 uses the actual project-local manufacturer-corrected footprint; other footprints use the same unmodified KiCad 10 library files copied by `build_cad.py`. A fit compares every common numbered pad after removing only a common translation. Candidate rotations are exactly 0°, 90°, 180° and 270°. In the downward-positive board coordinate system, a positive CPL counterclockwise angle applies `R(-angle)` to the vendor pose. The result is:

`CPL rotation = (KiCad board rotation + verified offset) mod 360`

Small residuals reflect different land sizes/centers between libraries. They are not tolerance measurements or proof of solderability. USB combined supply/ground contact labels are matched to their corresponding native contacts; its shell pad numbering is different and is excluded from the signal fit. No reflection or scale change is permitted. Library origin offsets are **not** automatically applied to CPL positions.

## Verified keyed-part offsets

| References | Exact LCSC | MPN | Add CCW |
|---|---|---|---:|
| U1 | C2040 | RP2040 | 0° |
| U2 | C131025 | W25Q16JVSSIQ | 270° |
| U3 | C51118 | AP2112K-3.3TRG1 | 270° |
| U4 | C9652 | AD9833BRMZ-REEL7 | 270° |
| U5 | C2833513 | OPA810IDBVR | 0° |
| U6, U7 | C2864204 | OPA2810IDGKR | 270° |
| U8, U9 | C2869590 | THS4551IRGTR | 270° |
| U10 | C2670866 | ADS9224RIRHBR | 0° |
| U11 | C16430 | TPS7A4901DGNR | 270° |
| U12 | C33835 | TPS7A3001DGNR | 270° |
| U13 | C87663 | TPS65131RGER | 0° |
| Q1 | C15127 | AO3401A | 180° |
| D2, D3 | C2480 | MDD SS14 | 0° |
| L1, L2 | C167963 | FNR5040S4R7MT | 0° |
| Y1 | C20625731 | ABM8-272-T3 | 0° |
| SW1, SW2 | C231329 | B3U-1000P | 0° |
| D4 | C22371297 | PSC-1608U52GC-G4 | 0° |
| J1 | C165948 | TYPE-C-31-M-12 | 0° |
| D1 | C7519 | USBLC6-2SC6 | 270° |

The OPA810 SOT-23-5 and AP2112 SOT-23-5 have different library zero poses. The QFN parts likewise do not share a universal offset. Applying package-family defaults would misorient components here.

The LED library symbol and manufacturer drawing both identify pad 1 as cathode and pad 2 as anode. The SS14 library identifies the same polarity. AO3401A is 1=G, 2=S, 3=D. Abracon's top-view drawing has crystal pin 1 bottom-left, pin 2 bottom-right ground, pin 3 top-right and pin 4 top-left ground. Its chamfer can vary and is not a reliable independent pin-1 marker.

Inductors, switches, MLCCs and ferrite beads are nonpolar; 180° is electrically equivalent, but a 90° axis error is not. The exact C337485/C21397 1210 capacitor and C79382 ferrite records confirm a horizontal pad axis at zero, matching native KiCad. Existing archived library evidence covers the standard R0603/C0603/C0805 axes; not every new resistor/capacitor MPN has received a separate feeder-pose audit. Hand-fit headers and barrel jack are outside the SMT CPL.

## Manufacturer dimension comparison

The JSON records each part's dimension-review status. These checks distinguish an exact manufacturer land pattern from a compatible package/pitch with different IPC lands; neither the EasyEDA nor KiCad library alone is treated as the manufacturer's authority.

- **FNR5040S:** The [Cjiang FNR family drawing, page 2](https://datasheet.lcsc.com/datasheet/pdf/a0b12ba9dfe6b9e66b6bb852b7c71c03.pdf?productCode=C167960) gives a 2.3 mm gap, 1.4 mm pad width and 4.2 mm pad height, hence centers at ±1.85 mm. Native KiCad matches this. The EasyEDA 1.8 mm-wide pads at ±2.15 mm are larger and must not replace the verified native pattern.
- **AD9833:** [ADI Rev G Figure 32](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9833.pdf) confirms RM-10, 3 × 3 mm body, 0.5 mm pitch and 4.65–5.15 mm lead span. Native MSOP-10 matches the package. The drawing lists BRMZ and BRMZ-REEL7 with the same package.
- **TI packages:** The local official datasheets provide OPA810 DBV0005A, OPA2810 DGK0008A, THS4551 RGT0016C, ADS9224R RHB0032E, TPS7A49/30 DGN0008 and TPS65131 RGE0024B land examples. Native pitch and exposed-pad dimensions match the selected packages: THS4551 1.68 mm EP, ADC 3.45 mm EP, LDOs 1.57 × 1.89 mm EP, TPS65131 2.45 mm EP. **Native edge lands are IPC variants rather than exact TI land-example copies.** For example OPA810 native pads are 1.325 × 0.6 mm at 2.275 mm row centers; TI suggests 1.1 × 0.6 mm at 2.6 mm centers. OPA2810 native pads are 1.625 × 0.5 mm at 4.225 mm row centers; TI suggests 1.4 × 0.45 mm at 4.4 mm centers. Exact comparisons for every TI part are in the JSON. These differences require deliberate acceptance by the layout owner; this audit does not silently call them exact reference-conformant lands.
- **AP2112:** [Diodes DS39724 page 14](https://www.diodes.com/assets/Datasheets/AP2112.pdf) suggests 0.8 × 0.55 mm lands, 2.4 mm row centers and 0.95 mm pitch. Native has the same pitch and larger lands, with different row centers.
- **AO3401A:** [AOS package PO-00001N](https://www.aosmd.com/sites/default/files/res/package/SOT23.pdf) confirms the 2.9 mm body, 2.6–3.0 mm lead span and 0.95 mm pitch. The native SOT-23 has that pin pattern; its land dimensions differ from the manufacturer's recommendation.
- **USBLC6:** [ST DS4260 Rev 7 pages 12–13](https://www.st.com/resource/en/datasheet/usblc6-2.pdf) specifies the SOT23-6L 0.95 mm pitch and 1.2 × 0.6 mm recommended lands at 2.3 mm row centers. Native uses 1.325 × 0.6 mm lands at 2.275 mm centers.
- **Crystal:** [Abracon drawing 456603 Rev B](https://abracon.com/datasheets/ABM8-272-T3.pdf) confirms the body and numbered terminal arrangement. Native/library pad centers agree within 0.0002 mm. This drawing shows package contacts, not a recommended PCB land pattern.
- **Switches:** [Omron B3U page 2](https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3u.pdf) gives a 4.2 mm outer span, 2.6 mm inner gap and 1.7 mm pad height: 0.8 mm lands at ±1.7 mm. Native centers and height match, with 0.9 mm-wide lands.
- **LED:** [Honglitronic B-24-A-0131 A/0 page 2](https://datasheet.lcsc.com/datasheet/pdf/de88fdeb30c1981a89300325510ce32e.pdf?productCode=C22371297) confirms 1K/2A and 1.6 × 0.8 mm body. Recommended lands are 1 × 1.1 mm at ±0.8 mm; native lands are 0.875 × 0.95 mm at ±0.7875 mm. The package fits, but the land pattern is not an exact manufacturer copy.
- **USB connector:** The project-local adaptation in `build_cad.py` applies the already reviewed HRO 2020 drawing to signal lands, shell slots and locating holes. Its 12 unique signal centers agree with the current library within 0.0003 mm after a common translation. The library origin differs from the connector body center; vendor preview must check the body, shell holes and PCB edge, not only the contact row.

## Completed primary checks and procurement decisions

The following manufacturer PDFs and exact distributor records are saved under `sources/new/`; their hashes and findings are recorded in the JSON.

| Part | Primary mechanical result | Procurement decision |
|---|---|---|
| RP2040 C2040 | Official Raspberry Pi Figure 167, printed page 608: 0.875 × 0.20 mm edge lands, 0.40 mm pitch, 7.75 mm outer copper span, 6.00 mm inner span and 3.20 mm EP. Native footprint reproduces these dimensions. | Keep RP2040 / C2040. |
| Winbond C131025 | Manufacturer W25Q16JV Rev H §11.3: SS package body 5.18–5.38 mm, lead span 7.70–8.10 mm, pitch 1.27 mm. Native 1.625 × 0.65 mm lands at ±3.5875 mm cover the specified terminal envelope. Correct 208 mil SS package; not the narrower 150 mil SN. | **Keep W25Q16JVSSIQ / C131025.** The current LCSC product title and structured MPN both specify this exact name. The EasyEDA `TR` suffix does not override the procurement record. |
| MDD SS14 C2480 | Manufacturer SS12–SS1200 page 1 identifies SS14/SMA, cathode band, 4.70–5.30 mm overall lead span, 0.75–1.55 mm terminal length, 1.30–1.70 mm terminal width. Native 2.5 × 1.8 mm pads at ±2 mm cover that terminal envelope. Native/library pad 1 is cathode. | Keep MDD SS14 / C2480. |
| AD9833 C9652 | Existing ADI Rev G RM-10 package review remains valid; packing variants share the package. | **Keep AD9833BRMZ-REEL7 / C9652.** The current LCSC product title and structured MPN include `-REEL7`; EasyEDA merely omits that suffix. |

Package-terminal coverage is a mechanical fit check. For Winbond and MDD, the reviewed manufacturer pages provide package outlines rather than recommended PCB lands; the audit does not label the native footprints as exact manufacturer land-pattern copies.

Primary sources: [Raspberry Pi RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf), [Winbond manufacturer PDF supplied for C131025](https://datasheet.lcsc.com/datasheet/pdf/abc83bb7f5b7f022c50f4fddf07136a0.pdf?productCode=C131025), [MDD manufacturer PDF supplied for C2480](https://datasheet.lcsc.com/datasheet/pdf/9977bb85cd7e349115b7bcb7054cfa0d.pdf?productCode=C2480), [LCSC C131025](https://www.lcsc.com/product-detail/C131025.html), [LCSC C9652](https://www.lcsc.com/product-detail/C9652.html).

## J2 DC-005 2.0: required mechanical correction

The exact [C16214 manufacturer drawing dated 2018-08-14](https://datasheet.lcsc.com/datasheet/pdf/7818bb2983211780d108ec1de5e9436f.pdf?productCode=C16214) is saved as `sources/new/DC005-C16214.pdf`. Its PCB layout is explicitly a **top view**. Manufacturer numbers are 4=tip, 3=sleeve spring, 2=normally closed sleeve-switch contact. The original generic footprint used 1, 2, 3 respectively. The final schematic and PCB use the manufacturer numbers: **4=5VIN, 3=GND, 2=unconnected**.

With native tip pad 1 kept at the origin:

| Original generic pad | Function | Original center, mm | Final manufacturer center, mm | Board slot |
|---|---|---|---|---|
| 1 | Tip; manufacturer 4 | (0, 0) | (0, 0) | 1 × 3 mm |
| 2 | Sleeve; manufacturer 3 | (−6.0, 0) | **(−6.3, 0)** | 1 × 3 mm |
| 3 | Switch; manufacturer 2 | (−3.0, 4.7) | **(−3.0, 4.6)** | Keep 3 × 1 mm; manufacturer drawing shows 3 × 0.8 mm |

The 0.3 mm pad-2 displacement is large enough relative to the tab/slot clearance that it must be corrected; do not treat the generic footprint as an exact fit. Keeping the existing 1 mm short dimension on pad 3 gives 0.2 mm more slot width than the manufacturer recommendation and is a deliberate insertion-clearance allowance. Retain adequate annular ring.

The manufacturer's body is 14.2 × 9 × 11 mm. Relative to tip pad 1, its mouth is x=−13.8 mm and rear x=+0.4 mm; the generic Fab outline is −13.7/+0.8 mm. Update the outline accordingly, including the shoulder at x=−10.5 mm. At the reviewed board position (64,125), rotation 0°, the actual mouth is x=50.2 mm, 0.2 mm inside the PCB's x=50 edge. This is accessible on an open bench board; enclosure clearance must use the actual body, not the generic model. J2 remains hand-fit and is excluded from SMT CPL.

**Resolution applied:** `build_cad.py` now moves the slot centers, uses the manufacturer’s actual pad numbers 4=tip, 3=sleeve, 2=switch, and updates the Fab front/rear/shoulder dimensions. The comparison above records the original generic-footprint findings. Final native pad geometry is recorded in `sources/placement-rev-c.json`. All primary mechanical checks are closed.

## Assembly interpretation

The layout owner accepts the documented IPC land variants for this prototype based on the reviewed package-terminal coverage, correct pitch/pin numbering, exposed-pad dimensions and native clearance checks. These remain explicit differences from the manufacturer land examples. Generic footprint metadata links sometimes point to unrelated example devices (for example the ADC footprint links to CC1201 and OPA2810 to REF5020); those links were not used as selected-part datasheet authority. Final JLC preview should compare numbered pads, connector body and shell positions using the supplied offsets. Product-linked EasyEDA pose does not establish a particular machine's feeder orientation. No upload or order was performed.

## Final passive change

C74/C75 are Samsung CL10A105KB8NNNC, C15849, 1 µF 50 V X5R in standard 0603 lands, replacing the original 0805 parts to shorten the ADC reference connections. The catalog snapshot is `sources/catalog-c15849.json`; the nonpolar standard0603 placement axis remains unchanged. The original orientation-audit identity and the final component-identity hash are separately named in the JSON.

## Revision C changes

All keyed MPNs, pin numbering and zero-angle offsets remain unchanged. New C104, C106–C109 and R90–R93 are symmetric nonpolar0603 passives with zero extra rotation correction. The exact added/changed MPN, footprint and manufacturer dimensions are recorded in `sources/rev-c-source-audit.md`. Current native coordinates and rotations are regenerated in `manufacturing/orientation-audit.csv`; source metadata now covers175 fitted parts.

JP4 retains the specified Samtec header, lands and drills, but uses a manufacturer-body courtyard with0.28mm nominal allowance. The matching SNT shunt envelope and local C104 routing are documented in `validation/feedback-routing/README.md`; native courtyard/footprint parity checks pass. C41/C105 are removed from the final circuit.

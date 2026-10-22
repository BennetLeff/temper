# Revision E cost estimate

This complete meter occupies one PCB. Budget for obtaining one usable instrument while paying the manufacturer's minimum batch. No checkout quote, reservation or purchase has been submitted, and no file has been uploaded to JLC.

## Five assembled boards at JLC

`manufacturing/order_estimate.py 5` (KiCad Python) reproduces these figures and writes `manufacturing/order-estimate-5.json`. Inputs:
- JLC assembly-library snapshot, read 2026-10-21 by `manufacturing/prices/fetch_jlc_parts.py` (`manufacturing/prices/jlc-parts-2026-10-21.json`): price tiers, stock, library class, attrition (`lossNumber`) and minimum quantity (`leastPatchNumber`) per part;
- board counts: 193 placements, 601 SMT joints per board, leadless parts U1, U13 and U14, and 26 THT joints on J3–J9;
- the published fee table;
- the 2026-10-20 fabrication instant quote, for the 140 × 100 mm outline. The board is now 140 × 105 mm and has not been re-quoted; if the "Board" line ($8.70) scaled with area it would become about $9.14, but that scaling is an assumption, not a quote. Re-quote at upload.

Each line buys max(5 × per-board quantity + attrition, minimum). That is our reading of JLC's library fields; the quote from the uploaded BOM is authoritative. Every line has stock for this order. The thinnest are OPA2810 (251 in stock against 10 needed), the BNC jack (319 against 20) and TAC5112 (136 against 5, down from 181 the day before).

| Item | USD |
|---|---:|
| SMT parts (61 lines; attrition and minimums add $8.10) | 227.76 |
| Extended-part fee, 28 × $3.07 | 85.96 |
| Setup + stencil | 9.71 |
| SMT joints, 5 × 601 × $0.0016 | 4.81 |
| X-ray, 15 leadless parts × $0.82 | 12.30 |
| Confirm placement | 0.45 |
| PCB fabrication, 5 pcs (detail below) | 80.98 |
| **Economic PCBA total** | **421.97** |
| JLC fits J3–J9: parts $30.34 (four BNCs $25.83), 130 manual joints $2.13, labour $3.58 | 36.05 |
| **Five complete boards, before shipping and taxes** | **458.02** |

That is $91.60 per board, against $613.44 ($122.69 per board) for Rev D. Standard PCBA would cost $512.94 before hand fitting: higher setup and stencil fees, feeder loading on all 61 lines, and fixtures. Shipping, sales tax/VAT, import duty and coupons are excluded.

**Five boards with two assembled** (`order_estimate.py 2`, five bare PCBs in the fabrication quote): Economic PCBA $295.68 plus JLC hand fitting $18.69 = **$314.37**.

**What the 2026-10-21 accuracy upgrades added: +$36.87 for five boards** (from $416.59).
- Four BNC jacks for four-terminal (Kelvin) connection, against one 2-pin header: +$25.83 in parts and +$1.48 in manual joints. Hand fit, so no extended-part fee.
- K4 reference relay on the existing TQ2SA line: +$10.10.
- Its driver (AO3400A, 1N4148WS, 100 Ω, 100 kΩ), R107 on the existing 0.1 % line, and R105/R106 on the new basic 1 kΩ line (C21190): about $0.77, with no new extended line.
- The calibration-kit card is a separate order ([calkit/README.md](../calkit/README.md)): about $117.70 for five (r2, 38 × 191 mm, with the 1 MΩ standard; fabrication still quoted at r1's 38 × 193 mm). Kelvin clip leads are bought separately: $13–35 generic, $72 Tonghui TH26011AS, $169 B&K TL889A.

**USB-C power (2026-10-21): +$4.56 for five boards** (from $453.46). U16 (TPS2553, extended: $0.54 each plus the $3.07 line fee) and R110 (24 kΩ, basic) replace Q1 (AO3401A) and the DC jack, which JLC hand-fitted. The part snapshot was refetched for this change, so stock and prices are from later the same day.

**Where Rev E saves, against Rev D's $613.44** (before the BNC/K4 additions above).
- Parts −$136.68. The codec front end removes ADS9224R, AD9833 and both THS4551s and adds a TAC5112, three TQ2SA relays and their drivers.
- Fabrication −$35.75. Every via is now 0.3 mm (see below).
- Extended-part fees −$9.21. 27 extended lines instead of 30, after the basic-library swaps in [rev-e-plan.md](rev-e-plan.md).
- X-ray −$8.20. Three leadless packages instead of five.
- Hand fitting −$7.12. The relays replace JP1–JP6.

**Fabrication quote.** 4 layers, 140 × 100 mm (quoted before the 105 mm outline), 1.6 mm, 1 oz outer and 0.5 oz inner copper, ENIG 1 µin, epoxy filled and capped vias, 3–4-day build.

| Line | USD |
|---|---:|
| Engineering fee | 25.00 |
| POFV | 18.28 |
| ENIG | 18.20 |
| TG155 material | 7.32 |
| Board | 8.70 |
| Horizontal electroless via plating | 3.48 |
| **Total, 0.3 mm vias** | **80.98** |

- Every via on Rev E has a 0.3 mm drill and a 0.45 mm or larger pad, JLC's standard "0.3mm/(0.4/0.45mm)" option. The 0.2 mm option that Rev D needed added "Min via hole 0.2 mm" ($18.28) and a 4-wire Kelvin test ($17.47); the same quote page gave $80.98 without them. Re-quote at upload: the lines above are the 2026-10-20 quote less those two.
- JLC leaves vias over 0.5 mm unfilled. Every via on this board is 0.30 mm.

**Where the money goes.** Parts at $1 or more are $182.30, 81 % of the SMT parts: OPA2810 $45.40, TQ2SA relays $40.41, TAC5112 $29.64, OPA810 $15.48, TPS65131 $14.38, W25Q128 $14.26, TPS7A3001 $10.10, TPS7A4901 $7.25, RP2040 $5.38. The 28 extended-line fees ($85.96) are now the largest single item after the parts. The extended lines that remain are ICs (including the U16 USB power switch), the crystal, the inductor, the USB connector, the 0.1 % network resistors, the C0G stability and anti-alias capacitors, the 1.62 MΩ/1.74 MΩ rail dividers and the 10 µF 1210; [rev-e-plan.md](rev-e-plan.md) gives the reason each one stays.

## BOM arithmetic checkpoint

Catalog snapshot checked 2026-10-21:

| Item | Quantity | USD |
|---|---:|---:|
| All components for one instrument | 200 | 52.78 |
| Machine-placed components per PCB | 193 | 46.72 |
| Hand-fitted components per PCB | 7 | 6.06 |

Both `SMT` and `JLC SMT` source tags count as machine placements. Hand fitting is three two-pin headers and four BNC jacks. The 61 unique SMT lines comprise 28 extended, 30 basic and three preferred lines (BAT54S, SRV05-4 and the 27 Ω resistor). Catalog stock and prices do not guarantee eventual availability or the PCBA purchase price.

**Epoxy-filled and copper-capped vias (POFV) are kept** for the exposed pads (U1, U11, U12, U13, U14: 33 vias, 4–9 per pad) and R3 pad 2 (34 via-in-pad locations, `validation/via-in-pad-process.json`). No other via sits in an SMT pad. The four-layer board does not qualify for JLC's free 6–20-layer POFV offer. The quote above includes it.

Add shipping and taxes. Supplier pack sizes and loss allowances can exceed simple BOM multiplication.

## Cash budgets

| Route | USD allowance | Assumptions |
|---|---:|---|
| Bare-board batch; hand assemble one | 140–220 | One component set, four-layer fabrication and ordinary shipping; reflow/rework tools already available |
| Five JLC assemblies (Economic), JLC fits the headers | 420–500 | The estimate above plus shipping |
| Supply/cable/fixture/shunts/standards | Add 30–100+ | Excludes a reference meter, oscilloscope and enclosure |

Use the full batch cost when deciding to build one instrument. Dividing it by two does not reduce the first payment. Taxes/import fees, special sourcing and a possible respin are outside these allowances.

JLC advertises two-board prototype assembly, ordinarily with at least five bare PCBs. RP2040 C2040 is listed for Economic and Standard service; its 0.4 mm pitch alone does not force Standard. Other parts/options can change eligibility.

Sources checked 2026-10-20 (part snapshot 2026-10-21): [assembly prices](https://jlcpcb.com/help/article/pcb-assembly-price), [capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities), [prototype minimum](https://jlcpcb.com/solutions/pcb-prototype-assembly), [fabrication/assembly quantities](https://jlcpcb.com/blog/reduce-pcb-assembly-cost-prototype), [RP2040 eligibility](https://jlcpcb.com/partdetail/RaspberryPi-RP2040/C2040). [JLC via finishes](https://jlcpcb.com/blog/five-via-finishes) and [POFV layer eligibility](https://jlcpcb.com/news/free-via-in-pad-6-20-layer-pcbs-pofv) establish the required process; the uploaded BOM/CPL/fabrication quote is authoritative.

## Useful upgrades

| Investment | Benefit | Required work |
|---|---|---|
| Characterized standards and rigid shielded fixture | Better calibration/repeatability; first priority | Bound AC parasitics; validate after fixture changes |
| Remote Kelvin sensing | Less lead/contact error | Done in Rev E: four BNC jacks (HCUR/HPOT/LPOT/LCUR) |
| Four-wire DC resistance channel | Addresses 1 mΩ shunt/winding DC resistance | New current source, offset/thermal-EMF control and calibration |
| Relay state sensing | Confirms the latched range | Latching relays have no spare pole ([range-switching §3.4](rev-e-range-switching.md)) |
| USB isolation | Breaks computer-ground loops | New interface/power design and noise qualification; no energized-DUT rating implied |
| Display/local controls | Computer-free operation | Firmware/interface work; no automatic accuracy improvement |

Revision E keeps Rev D's simultaneous voltage/current acquisition, R_iso for fixture-capacitance stability, ±12 V rail monitors and the shared 100 pF feedback compensation, and adds a codec with a coherent source and firmware-selected relay ranges. These features are included in the present BOM. No added component establishes an accuracy number without measurement evidence.

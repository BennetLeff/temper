# coil-r1: order list (2 coils + practice; no purchases made, no suppliers contacted)

Reads are dated **2026-10-18** unless stated otherwise. "Snapshot" means a search-engine index or listing excerpt, not a live product page: confirm before ordering. Lead times marked *est.* are planning guesses, not quotes. Quantities cover two coils, one practice winding and the termination qualification samples.

## 1. Litz wire

Per coil: 9.27 m of winding, plus 0.4 m of leads, plus 0.73 m for the spare turn, about **10.4 m** (`coil_geometry.Winding.length_m`). The modelled R values are on R1 (`model/results/free_air.json` `litz_alternatives_80uH`, in mΩ).

| Use | Item | Read | R_dc 25 °C / R_ac 40 kHz 25 °C / R_ac 40 kHz 100 °C | Qty | Lead time |
|---|---|---|---|---|---|
| **First coils (recommended)** | **RM Cybernetics 12 A Litz, 1000 × 0.05 mm, OD 2.55 mm**. Solderable enamel strands (strip ~400 °C), USTC polyester-silk serve. Datasheet max 8.9 Ω/km. [shop](https://www.rmcybernetics.com/shop/litz-wire/litz-wire), [datasheet](https://www.rmcybernetics.com/files/pdf/Litz-Wire-Datasheet.pdf) | Size table read live. The per-size price is not shown: the range across sizes is £1.89–17.89/m, with 10 % off over 10 m. Stock and temperature class are not stated, so **ask for both** | 89.8 / 90.6 / 116.1, passes rows 4 and 5 | 30 m | stock size; ship UK *est.* 1 week |
| First coils (alternative) | **Elecify 1050/44 (1050 × 0.05 mm)**, sold per 1 m piece; multiples ship as one length. [Elecify](https://www.elecify.com/products/litz-wire-200-38awg-200-strands-x-0-1mm) ("we also recommend" list) | $3.82 per 1 m. OD and temperature class not listed: **ask before buying**, because the former notch follows the OD | 85.6 / 86.4 / 110.6, passes | 30 m | US *est.* 1–2 weeks |
| Do not use | Elecify 200/38 (200 × 0.10, OD 2.05, polyester yarn serve, $1.69/m) | read live | 112.0 / 114.5 / 146.0, **fails row 4 (≤ 0.100 Ω)** | — | — |
| Do not use | NEWT NELC270/40SPSN | earlier read | 0.08 mm strands, polyurethane strand insulation, nylon serve: too little copper, too low a class | — | — |
| Qualification coil (spec row 8/11) | **270 × 0.10 mm, type 2, class-200 enamel, Nomex or PTFE serve, ~Ø2.4**. Custom from RM Cybernetics (earlier read: ~6 weeks, MOQ £1000), [New England Wire](https://www.newenglandwire.com/product/custom-litz-wire-options) (RFQ) or Elektrisola (RFQ) | no stock found | 83.2 / 86.6 / 109.6 | 40 m | 4–8 weeks *est.*, after RFQ |

The temperature class of the stock wire is the open item. Solderable polyurethane enamel is typically class 155 and polyester silk around 130–155, but neither page states it. Until a datasheet says otherwise, run class-155 limits: winding ≤ 130 °C (README D4).

## 2. Ferrite (10 bars per coil; 30 bought = 2 coils + 10 spare)

| Option | Item | Read | Qty | Lead time |
|---|---|---|---|---|
| A (R43's choice) | PC95 bars 90 × 15 × 5 mm, induction-cooker stock, [eBay 135111122358](https://www.ebay.com/itm/135111122358) | **Unverified.** The page returned 403 to this study. The 2026-10-10 review saw $16.74 with no size selected, which cannot be assigned to the 90 × 15 × 5 variant. Ask the seller for the PC95 datasheet; check bars on arrival (BUILD-AND-MEASURE M1) | 30 | China post *est.* 2–4 weeks |
| B (traceable backup) | **TDK PC95SP100X100X5** plate, 100 × 100 × 5 mm PC95, Mouser 810-PC95SP100X100X5. Cut into 15 mm strips (6 per plate) with a wet diamond saw, then trim to 90 mm | **Snapshot:** 379 in stock, ₹2,322 each (mouser.in index). Not a live read | 5 plates (10 bars per coil + spare) | Mouser stock *est.* < 1 week |
| Not recommended without a re-solve | Fair-Rite 3595000501 plate, 100 × 100 × **3** mm, 95 material, µi 3000 | earlier read | — | — |
| Production | 85–90 × 20 × 5 PC95 custom from Feiteng or ChaoNeng (R43 links) | no public price | — | weeks |

Cutting MnZn ferrite makes conductive dust: cut wet, wear a mask, and wash the bars. Strips cut from the plate are the same material. Edge chips do not matter magnetically at this size, but a crack does: re-run M1 on every strip.

## 3. Former (one route; README D6)

| Route | Item | Qty | Lead time |
|---|---|---|---|
| A CNC | G11/FR5, 10 mm plate, 2.5D both sides, from `cad/out/former_R1_cnc.step` (regenerate with `--bundle <measured OD>` first). Any online CNC service that machines G10/G11 | 3 | 1–3 weeks *est.* (not quoted) |
| B print | `cad/out/former_R1_print_seg1..5.stl` in **PC, PA-CF or ASA** (not PLA or PETG: winding heat). About 70 cm³ (~90 g) per former. Pins: 3 mm G10 or bamboo rod × 5 per former | 2–3 | days |
| C no printer | **FR4/G10 unclad sheet, 1.0 mm, ≥ 270 × 270 mm**, cut to `cad/out/roof_sheet_R1.dxf`. Template `cad/out/template_R1_1to1.pdf` printed on A3 at 100 %. Monofilament spacer cord, **(3.815 − OD) and (3.311 − OD) mm** | 2 sheets | days |

## 4. Jig (`cad/out/jig_cutlist.csv`; no metal above the top plate)

| Item | Qty |
|---|---|
| Birch plywood 18 mm (about 0.75 m² in all) and 12 mm (one 220 × 30 strip, two Ø43.6 boss rings) | — |
| Hardwood dowel Ø25 × 400 (spindle), Ø12 × 260 (axle) and × 150 (tamper), Ø10 × 80 (crank peg), Ø8 × 200 (lead mast) and × 60 (pivot, peg) | 1 each |
| PTFE tube 4 mm ID / 6 mm OD, 60 mm (3D-printer Bowden tube) | 1 |
| Nylon M3 × 30 screws and nylon wing nuts (former to platter) | 4 |
| Nylon M6 × 40 screw and wing nut (guide block) | 1 |
| UHMW-PE or PTFE disc, Ø25 × 3 (thrust); wool felt 5 mm, 30 × 40 (brake pad); rubber bands; wax | — |
| Hand tally counter; digital luggage scale 0–10 kg | 1 each |

Lead time: hardware store, days.

## 5. Adhesives, tapes, sleeving, terminals

| Item | Spec | Qty |
|---|---|---|
| High-temperature silicone RTV (bars, turn bonding) | rated ≥ 200 °C continuous, e.g. a 315 °C heat-resistant RTV sealant class (DOWSIL 736 or equal). Product not price-checked | 2 tubes |
| Potting silicone (coil-NTC pad, route A/B) | as R43: ≥ 200 °C, vacuum-degassed | 1 kit |
| Polyimide (Kapton) tape, 10 mm | temporary hold of turns and crossover | 1 roll |
| Braided fibreglass sleeving, ≥ 200 °C, ID 3 mm | leads | 2 m |
| Ring terminals | **non-insulated, tinned copper, M4 stud, barrel for 1.5–2.5 mm²**, plus the matching ratchet crimper for non-insulated terminals. Barrel sized for 1.96–2.12 mm² of copper, not R26's 12–10 AWG | 10 (6 + scrap qualification) |
| Solder pot | small, to ≥ 420 °C, for stripping solderable enamel | 1 |
| Coil NTC (route A/B) | Semitec 104GT-2 plus R43's PTFE micro-tube and silicone-glass sleeve | 3 |

Lead time: distributors, *est.* < 1 week.

## 6. Instruments (if not already on the bench)

| Item | Read | Note |
|---|---|---|
| LCR meter **TH2830** (50 Hz–100 kHz), [eleshop.eu](https://eleshop.eu/techmize-th2830-lcr-meter.html) | about €899 excl. VAT (earlier read 2026-10-18) | covers 20–60 kHz; Kelvin clips |
| TH2832 (to 200 kHz) | €1,690 (same read) | only if you want harmonics |
| 4-wire milliohm meter | — | R_dc, termination qualification |
| PP film capacitor 0.22 µF 630 V; function generator; oscilloscope | — | M5 ring-down R_ac |
| K-type thermocouples with glass-fibre insulation, plus a logger | — | first power: winding and bar temperatures |

## Budget

The 2026-10-10 manufacturing review gives $200–500 per prototype coil with its pigtails, as a planning estimate. The Litz options above put the wire at roughly $40 (Elecify) to £20–190 (RMC, depending on the unlisted per-size price) per coil. Everything here is to confirm at order time.

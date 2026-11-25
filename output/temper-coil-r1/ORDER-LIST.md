# coil-r1: order list (2 coils + practice; no purchases made, no suppliers contacted)

Reads are dated **2026-10-18** unless stated otherwise. "Snapshot" means a search-engine index or listing excerpt, not a live product page: confirm before ordering. Lead times marked *est.* are planning guesses, not quotes. Quantities cover two coils, one practice winding and the termination qualification samples.

## 1. Litz wire

Per coil (fit study 2026-10-21, `fit/litz_order.py`): 9.25 m of winding, plus 0.73 m for the spare turn, plus 0.46 m of bench leads (J2 160 mm, J5 305 mm), plus 0.11 m for strip, one re-termination per lead and handling: **10.56 m**. **Order** for 2 coils + 3 × 1 m W9 qualification samples + a practice start: **25.2 m**. The modelled R values are on R1 (`model/results/free_air.json` `litz_alternatives_80uH`, in mΩ).

| Use | Item | Read | R_dc 25 °C / R_ac 40 kHz 25 °C / R_ac 40 kHz 100 °C | Qty | Lead time |
|---|---|---|---|---|---|
| **First coils (recommended)** | **RM Cybernetics 12 A Litz, 1000 × 0.05 mm, OD 2.55 mm**. Solderable enamel strands (strip ~400 °C), USTC polyester-silk serve. Datasheet max 8.9 Ω/km. [shop](https://www.rmcybernetics.com/shop/litz-wire/litz-wire), [datasheet](https://www.rmcybernetics.com/files/pdf/Litz-Wire-Datasheet.pdf) | Size table read live. The per-size price is not shown: the range across sizes is £1.89–17.89/m, with 10 % off over 10 m. Stock and temperature class are not stated, so **ask for both** | 89.8 / 90.6 / 116.1, passes rows 4 and 5 | 30 m | stock size; ship UK *est.* 1 week |
| **First coils, US source (recommended for a US order)** | **Remington Industries 260/38LITZ** (14 AWG, 5 × 52 × 38 AWG = 260 × 0.1007 mm, unserved, solderable polyurethane + polyamide, NEMA MW 80-C, 155 °C; OD 0.090 in = 2.29 mm; max 0.00281 Ω/ft at 20 °C). [product page](https://www.remingtonindustries.com/magnet-wire/litz-wire-14-awg-unserved-single-build-5x52-38-stranding-ideal-for-100-khz-applications-7-spool-sizes/), sales@remingtonindustries.com, +1 815 385 1987 | Read 2026-10-21: spools 2 oz/9 ft … 1 lb/76 ft, 2.5 lb/189 ft …; per-spool price not shown (range $33.25–1,434.06); listed in stock. Unserved: handle the bundle gently on the comb. **Re-cut the former for the measured OD** (`cad/former.py --bundle <OD>`), since the notches follow the bundle | 85.2 / 88.6 / 112.1, passes rows 4 and 5 (`run_free_air.py`, added 2026-10-21) | **2.5 lb (189 ft = 57.6 m, $455.20, read 2026-10-21)**: the order + 3 more coils, one lot. 1 lb (76 ft = 23.2 m, $187.65) does **not** cover 2 coils + qualification (`fit/litz_order.py`). Cheapest that covers it: 1 lb + 8 oz (34.7 m, $290.51, maybe two lots) | US stock *est.* days |
| First coils (alternative) | **Elecify 1050/44 (1050 × 0.05 mm)**, sold per 1 m piece; multiples ship as one length. [Elecify](https://www.elecify.com/products/litz-wire-200-38awg-200-strands-x-0-1mm) ("we also recommend" list) | $3.82 per 1 m. OD and temperature class not listed: **ask before buying**, because the former notch follows the OD | 85.6 / 86.4 / 110.6, passes | 30 m | US *est.* 1–2 weeks |
| Do not use | Elecify 200/38 (200 × 0.10, OD 2.05, polyester yarn serve, $1.69/m) | read live | 112.0 / 114.5 / 146.0, **fails row 4 (≤ 0.100 Ω)** | — | — |
| Do not use | NEWT NELC270/40SPSN | earlier read | 0.08 mm strands, polyurethane strand insulation, nylon serve: too little copper, too low a class | — | — |
| Qualification coil (spec row 8/11) | **270 × 0.10 mm, type 2, class-200 enamel, Nomex or PTFE serve, ~Ø2.4**. Custom from RM Cybernetics (earlier read: ~6 weeks, MOQ £1000), [New England Wire](https://www.newenglandwire.com/product/custom-litz-wire-options) (RFQ) or Elektrisola (RFQ) | no stock found | 83.2 / 86.6 / 109.6 | 40 m | 4–8 weeks *est.*, after RFQ |

The RM Cybernetics datasheet (read 2026-10-19, text extracted from the PDF) lists **thermal class 155** for the 12 A, 1000 × 0.05 mm, OD 2.55 mm wire (class 130 only for the 3 A, 75 × 0.1 wire). Stock for that size is still unconfirmed. The Elecify class is still unstated. Run class-155 limits: winding ≤ 130 °C (README D4). Hot limits of the other housing materials are in [HOT-LIMITS.md](HOT-LIMITS.md).

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
| B print | `cad/out/former_R1_print_seg1..5.stl` (regenerated 2026-10-21 at bundle 2.29), resin-printed: **Formlabs Rigid 10K, UV + thermal post-cure** (HDT 218 °C at 0.45 MPa / 110 °C at 1.8 MPa, 10 GPa; TDS Rev 04), or High Temp. Not PLA or PETG. About 70 cm³ per former. Pins per former: **3 mm G10 rod × 5 (rim) and 2 mm G10 or glass-fibre rod × 5 (hub)**, ~10 mm each; structural two-part epoxy for the joints (`fit/README.md` §5). Print one spare segment 5 | 2–3 | days |
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
| Lead sleeving | **Varflex Varglas Silicone Rubber, Grade C-1, size No. 9** (ID 2.90–3.15 mm, wall ≥ 0.20, 200 °C, 2500 V min avg / 1500 V min indiv.; read 2026-10-21). Sleeved OD ≤ 3.55 is what the fit used. Part number for No. 9 to confirm at order (the No. 10 listings read were VARSHC1RU.10, out of stock; in stock at No. 10: Suflex Flexicone 200 Grade C APHC1.10, $130 per 250 ft). No. 10 (ID 2.59 min) is the fallback: tighter to slide on, 0.3 mm thinner at the crossing | 2 m (0.47 m per coil + spare) |
| Lug insulation | **Alpha Wire FIT-350 PVDF heat-shrink**, UL 224 150 °C / 600 V, −55 to 175 °C: **3/16 in** (inner layer: barrel + 10 mm of sleeve) and **1/4 in** (outer layer: sleeve, barrel, bend to the ring edge) | 0.5 m each |
| J2/J5 hardware | ISO 7045 M4 × 8 A2 pan head + DIN 125-A M4 washer + DIN 127-B M4 spring washer; 1.2 N·m (7466004R) | 4 sets + spares |
| Ring terminals | **Panduit P14-8RHT6-C** (Pan-Term high-temperature, non-insulated: 18–14 AWG, #8/M4, ring OD 7.9, tongue 0.8, barrel ID 2.3, brazed, nickel-plated copper, 343 °C, cULus; pack of 100; DigiKey 0 in stock on 2026-10-21, $0.90). Formed 90° up at W9 and insulated with the FIT-350 above (`fit/README.md` §3). Crimp tool: Panduit's tool for this barrel, confirm the number at order. **If unobtainable:** Würth WA-CLUG 55804025 (2.5 mm², ID 2.3, W 7.5, 125 °C tin; DigiKey 1,199 in stock, $0.96). Not TE 1577639-1 on J2 (its PEEK sleeve touches CT T1, `fit/results/lug_board.json`) | 1 pack (4 per coil + scrap qualification + forming trials) |
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

# Bench sink r1: sources

Tags as used in `scripts/bench_params.py`. All web reads are dated 2026-10-18. The SHA-256 values are for the files committed here or at the repo path given.

## Datasheets and catalogues

| tag | document | file | SHA-256 | pages used |
|---|---|---|---|---|
| [IPW] | Infineon IPW65R018CFD7 Rev 2.0 | repo `validation-results/03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf` | c364050a04a434bd173da6486fd51f4baf540ee9e4e1ebbe07aed57e279943f2 | p.3 RthJC 0.28 °C/W max, Tj 150 °C, M3 60 Ncm; p.12 TO-247 outline |
| [GBJ] | Diodes Inc. GBJ2510 DS21221 Rev 11-2 | repo `validation-results/03-loss-thermal-budget/round3/sources/gbj2510.pdf` | c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02 | p.1 case dielectric 2500 Vrms, #6 screw 5.0 in-lb max; p.2 RthJC 1.0 °C/W typ per element; p.4 outline |
| [HNK] | Henkel/Bergquist Thermal Interface Materials Selection Guide (2017) | repo `validation-results/03-loss-thermal-budget/round3/sources/henkel-tim-guide.pdf` | 6a739a3ee70ba1be1a08d71953e6eda79b58cf5426e7fa101ac40e3f6e80c502 | SIL PAD 900S p.65, 2000 p.71, K-10 p.75: thickness, breakdown, impedance against pressure |
| [WAK] | Wakefield Thermal bonded-fin heat sinks data sheet (2021); <https://wakefieldthermal.com/content/data_sheets/2021_data_sheets/Wakefield-Thermal-Bonded-Fin-Heat-Sinks-Data-Sheet.pdf> | `wakefield-bonded-fin.pdf` | d7f9c8636915b10c858c0df9940547f51925ed9fe30d7a6416e192928f3d5952 | 510/511/512 table: 511-3M 132.33 × 76.2 × 59.7 mm, 0.90 °C/W natural, 0.120 °C/W at 100 CFM; base 0.220 in milled; flatness |
| [CAN] | Cantherm SDF thermal cut-off (June 2016); <https://www.cantherm.com/wp-content/uploads/2017/05/SDF_JUNE_2016.pdf> | `cantherm-sdf-june-2016.pdf` | 2c396e6e53976001b7d82ec47afe6b5f2e98597fe6d863399596730de2043f4c | DF110S: Tf 110 °C, Th 86 °C, tolerance +0/−5 °C, 250 V AC 10 A; metal case live |
| [NTC] | Vishay NTCALUG01A, doc 29092; <https://www.vishay.com/docs/29092/ntcalug01a.pdf> | `vishay-ntcalug01a.pdf` | a14f8704e47b483de359bbfc3195d9a2be002215fef82dfd00326cd2f717189b | M3 lug; 1500 V AC terminals to lug; 100 MΩ at 500 V DC; −55 to 150 °C |
| [3M] | 3M polyimide film tape 5413 TDS; <https://multimedia.3m.com/mws/media/136011O/3m-polyimide-film-tape-5413-tds.pdf> | `3m-5413-tds.pdf` | 109103d4d692eea01ab781ab81cd296adf84e861dd03ee9f7c5972d9df5f17de | dielectric breakdown 7000 V per layer (ASTM D149) |
| [LEE] | Lee Spring LC 055E 03 S product page; <https://www.leespring.com/product/compression-spring-lc055e03s-stainless-steel> | not saved (HTML) | – | L0 14.3 mm, rate 18.512 N/mm, solid 8.36 mm, OD 9.14 mm, hole 9.53 mm, load at solid 113.94 N; $8.04 each at 1–19 |

## Repo inputs

- `[M11]` `owner-items/m11/RECOMMENDATION.md`, `board-sink-geometry.json`, `stack_calc.py` / `stack-calc.txt`: tab plane, pad edges, edge copper, BR1 back face, insulation floors, clamp target.
- `[T03]` `validation-results/03-loss-thermal-budget/round3`: TO-247 exposed tab area 151.2–240.1 mm².
- `[CPL]` `validation-results/08-manufacturing-package/native-21/fab/cpl-jlcpcb-order.csv`: device centres.
- Loss models: the device study's `thermal.py` (bases D and A), imported by `bench_thermal.py` with value asserts. Line current 13.5 A is read from `b3/run_study.py`.
- Trip ladder: `firmware/config.yaml` (OVER_TEMP_THRESHOLD 95 °C, hardware comparator band 98.3–104.6 °C).
- Die-voltage bound: power-stage `OPEN-ITEMS.md` S3 (435.7 V worst die VDS).
- Hole rules: native-21 `FAB-NOTE.md`; hole coordinates: `native-21/layout/board_only21.json`.
- Clamp acceptance 45–102 N per TO-247: `DECISIONS.md` 2026-10-09 R32 item 3.

## Engineering estimates (EST) used

- Gap-bridging width X = 1.5 mm (PD3) and 1.0 mm (PD2), from IEC 60664-1 / IEC 60335-1 clause 29.2. Quoted from memory; the standard was not re-read.
- 6063 / 6061 conductivity, 6061 modulus, FR-4 thickness tolerance, grease bond line, device x play, the SOD-128 height under the bar, and the hand-placement tolerances of the strip. Each is labelled EST in `bench_params.py`.
- The BR1 seated height and the position of its screw hole. The GBJ drawing gives no seating shoulder, so both are set from the part on assembly.

## Distributor reads (2026-10-18)

These are the raw values as read. "Stock" is the distributor's on-hand quantity shown on the search or product page.

| part | site / number | stock | price | note |
|---|---|---|---|---|
| Wakefield-Vette 511-3M | DigiKey 345-1205-ND | 25 | $40.69 at 1 | |
| Bergquist SP2000-0.010-00-1212 | DigiKey | 28 | $171.85 at 1 | 12 × 12 in sheet |
| Bergquist 2165804 (K-10, 0.006 in) | DigiKey | 295 | $39.74 at 1 | alternative, not chosen |
| Bergquist SP900S-0.009-AC-1212 | DigiKey | 465 | $38.53 at 1 | alternative, not chosen |
| Bergquist SP1500ST sheets | DigiKey | 0 | – | MOQ 20+, not chosen |
| Cantherm SDF-DF110S | DigiKey 317-1131-ND | 1,377 | $0.87 at 1 | |
| Vishay NTCALUG01A104GA | DigiKey 56-NTCALUG01A104GA-ND | 770 | $2.19 at 1 | |
| RAF M0539-4-AL (10 mm M4 round spacer, aluminium) | DigiKey | 223 | $1.29 at 1 | |
| 3M 5413 1/2 in × 36 yd | DigiKey | 1,396 | $73.73 | |
| 3M 5413-0.5-5 (1/2 in × 5 yd) | DigiKey | 23 | $33.04 | preferred size |
| Wakefield 120-SA grease | DigiKey 345-1006-ND | 4,984 | $5.55 | |
| USA Industrials BULK-CS-GFR4-54 (G-10/FR-4, 6 × 6 in) | DigiKey | 3 | $15.53 | marketplace |
| Remington 0.375X1.0FLT6061T6511-6 (3/8 × 1 in 6061 bar, 6 in) | DigiKey | 50 | $11.83 | marketplace; 6 in = 152 mm is longer than the 130.5 mm bar |
| Cooltron FD1225B12W2-61-2NC1 (120 mm, 12 V) | DigiKey | 36 | $22 at qty 2 | marketplace |
| JST VHR-3N | DigiKey | not shown | $0.10 | J3 mate (pins 1 and 3) |
| JST SVH-21T-P1.1 | DigiKey | not shown | $0.042 | crimp for VHR |
| Lee Spring LC 055E 03 S | leespring.com | not shown | $8.04 at 1–19 | buy direct |

## Sites that blocked the agent or returned nothing

- **McMaster-Carr:** product pages are JS-rendered and returned no text, through both the fetch tool and Chrome (`/products/aluminum-angles/`). No McMaster part numbers were read. The aluminium angle, shim sheet, nylon standoffs, fasteners, loop clamp and PE stud are specified by description in the README BOM.
- **Mouser:** 403 or timed out.
- **Farnell / Newark:** timed out. This includes the Microtemp G4A page `ie.farnell.com/thermodisc/g4a01121c/...`.
- **datasheets.com:** 403.
- **DigiKey product-detail URLs guessed by ID** returned unrelated parts. Every DigiKey read above came from a keyword search page or a product page reached from one.
- **Microtemp (Thermodisc) G4A:** no DigiKey listing. The only rating seen was in a search-result snippet (G4A01121C: Tf 121 °C, Th 106 °C). It was not used for any number.

## Revision 2 reads (2026-10-18): JLC process and the soldered-row tolerance stack

| tag | page | what was read |
|---|---|---|
| [JLC] | <https://jlcpcb.com/capabilities/pcb-capabilities> | Plated through-hole diameter tolerance +0.13 / −0.08 mm. Hole position ±0.075 mm. Routed-edge tolerance ±0.2 mm. Board thickness ±10 % (≥ 1.0 mm). No bow/twist figure on the page. |
| [JLC] | <https://jlcpcb.com/capabilities/pcb-assembly-capabilities> | THT parts are wave soldered. Unused through-holes are protected from solder ingress. Wire soldering and stacked parts are handled through order remarks. **No THT seating, lean or coplanarity rule.** |
| [JLCF] | <https://jlcpcb.com/help/article/98-PCB-Assembly-FAQs> | Parts marked "wave soldering" are assembled manually; the hand-soldering labour fee and the per-joint fee apply. Consigned parts are allowed. No IPC-A-610 class is stated. |
| [JLCB] | <https://jlcpcb.com/blog/pcb-warpage-control> (via search result) | Quotes the IPC limits: 0.75 % for boards with SMT and 1.5 % without. This is a JLC blog, not a guarantee. The study uses 0.75 % of the diagonal. |
| – | Web searches for JLC's THT tilt/seating policy and for IPC-A-610's vertical-part tilt figure | Nothing citable was found. Both are treated as unknown: the lean is an inspection limit, not a JLC promise. |

**Other revision-2 inputs.**
- **TO-247 footprint.** `Package_TO_SOT_THT:TO-247-3_Vertical` (KiCad library, as in `native-21/layout/parts.json`), pads 2.5 × 4.5 mm, drill 1.5 mm. Copy read: `.claude/worktrees/sensor-manifest/.../native-09/candidate-libs/Package_TO_SOT_THT.pretty/TO-247-3_Vertical.kicad_mod`, sha256 cac3a8e7…
- **[IPW] p.12, read again.** b1 1.60–2.41, b2 2.57–3.43, L 19.80–20.40.
- **[GBJ] p.4, read again from the rendered drawing.**
  - N 3.10–3.40 is the mounting-hole diameter. Revision 1 wrongly took M (3.40–3.80) as the hole; M is a thickness.
  - S 10.80–11.20 is the hole centre above the body bottom (side view).
  - R 0.60–0.80 is the lead thickness, I 0.90–1.10 the lead width.
  - H 2.00–2.40 is a lead feature wider than the 1.6 mm hole, whose position along the lead is not dimensioned.
- **Board size.** 290 × 190 mm, from `fab/FAB-NOTE.md` 'Size'.

## Revision 3 reads (2026-10-18): per-device sinks and gap pad

| tag | page | what was read |
|---|---|---|
| [DKS] | <https://www.digikey.com/en/products/filter/thermal-heat-sinks/219?keywords=TO-247> (default order) | 362 results; the first 25 rows were read. The manufacturer column was not shown, so the "Ohmite" prefix comes from the part-number family. Rows used are in `bench_params.CATALOG_TO247` (PN, DigiKey product ID, attachment, width/length/fin, R natural, R forced at LFM, stock, unit price). The narrowest TO-247 sink in the read is 19.4 mm (Wakefield-Vette 657-15ABPE, no R given); the narrowest with an R is 22.8 mm (HSK-045-xx). |
| [DKS] | <https://www.digikey.com/en/products/result?keywords=TO-247%20heat%20sink%20clip> | The page returned only category counts (182 results), no rows. |
| [HNK] p.28 | GAP PAD 5000S35 (repo Henkel guide) | k 5.0 W/mK; fibreglass carrier; 0.020–0.125 in; breakdown > 5000 Vac; Young's modulus 121 kPa; 0.040 in impedance 0.37 / 0.32 / 0.29 °C·in²/W at 10 / 20 / 30 % strain. |
| – | `study/commission-s53` @ 77baeaa03, `firmware/components/power/COMMISSIONING.md` | Bring-up with BR1 not fitted. DC supply on C6.1 / C6.3; hv_ret tied to PE at one point in steps 2–4 and removed before step 4b (BR1 fit). |

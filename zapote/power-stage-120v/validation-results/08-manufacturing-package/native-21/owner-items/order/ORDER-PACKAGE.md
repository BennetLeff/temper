# Native-21 prototype lot at JLCPCB: order package for owner approval

> **Current for s52 (2026-10-16). Prepared, NOT ordered.** Nothing was ordered, carted, logged into or submitted. The order plan is
> `../../PROTOTYPE-LOT.md`. This package supplies its files:
> - `proto-stock-s52-20boards.csv`: every fitted BOM line against 20 boards, 0 short, on the scorecard's stock-gate rules
>   (`scripts/proto_stock.py`);
> - `CPL-PREVIEW-CHECKLIST.md`: the 23 NEEDS-PREVIEW parts to confirm in JLC's CPL preview (`scripts/cpl_preview_checklist.py`);
> - board `5e7c12c144b6…` (SHA-256 `5e7c12c144b6c1c3137fa27cfbfe1cc8cd40f8ad7756231a8b2bc1c2692fcc34`), gerbers
>   `fab/native-21-gerbers.zip` SHA-256 `ad585c16167e33a8cdd87b8bc9f2e1ca718432fd8fa09390f0c9849fe43797e2` (FAB-NOTE.md);
> - consigned or hand-assembled: the bank (TDK B32643H8104J000, DigiKey 306 against 100) and L1 (B82726S2243A020, Mouser 62 /
>   DigiKey 29 against 20), with F1, C1 / C2, C5 / C6, J3 / J11, D3 / D17 and U41 / U42.
>
> The text below is the stage 11/12 survey of 2026-10-08, kept as history: its stock tables, part choices and "NO-GO" verdict
> are not the s52 state. Ordering is a purchase and needs the owner.

Prepared 2026-10-08 (US time; fetches stamped 2026-10-09 04:29 UTC). **Nothing was ordered, carted, logged into or submitted.** This is preparation only. The owner approves and places the order.

- Board: power-stage-120v native-21 stage 11, SHA-256 `e85a4c82…98ac`.
- Gerbers: `fab/native-21-gerbers.zip`, SHA-256 `abd1e100…3f21`. I re-hashed it today, and it matches FAB-NOTE.md.
- Lot (from PROTOTYPE-LOT.md): **5 bare PCBs, 2 assembled by JLC (top side SMT)**. THT and consigned parts are hand-soldered in house. Stock is checked against the quantity for 2 boards. The CSV also gives the quantity for 5 boards.
- Files:
  - `bom-stock-2026-10.csv`: one row per BOM line, 96 rows;
  - `raw/`: the JSON from LCSC and JLC for every C-number, plus `findchips-2026-10-08.jsonl` (distributor stock).

**Bottom line: NO-GO today.** The board data is ready. The order is blocked by:
- the CTI confirmation (the inquiry is drafted but not sent);
- the open native-21 FEM corrections;
- owner item M11;
- **parts.** Fourteen BOM lines and three consigned lines had no in-stock source that I could see. The largest problems are C5/C6 (TDK MOQ 360, no distributor lists it) and R34 (no stock anywhere).

---

## 1. Stock re-check

### How stock was read

| Source | Method | Notes |
| --- | --- | --- |
| LCSC | `wmsc.lcsc.com/ftps/wm/product/detail?productCode=Cxxxx`, the JSON behind each `lcsc.com/product-detail/Cxxxx.html` page | Stock and USD ladder. 3 C-numbers are JLC-only (no LCSC listing) |
| JLC | `cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode=Cxxxx`, the data behind `jlcpcb.com/partdetail/Cxxxx` | **JLC stock is what assembly draws from.** Also gives Basic/Extended, MOQ and ladder. Alternates were searched with JLC's public parts search |
| Distributors | findchips.com (Supplyframe aggregator) search pages, USD | Covers Newark, Avnet, RS, TME, Sager, Heilind, Interstate, Rochester, Richardson and brokers. **Newark prices come back in CAD.** |
| Digi-Key | Search page via fetch | Prices sometimes shown. **Stock was never shown.** Most requests returned 403 |
| Mouser, Arrow | Not readable | Mouser: "Access denied" bot wall. Arrow: connection refused. The Chrome extension was not connected, so there was no browser fallback |

**Limit:** I could not read Digi-Key or Mouser stock. "No stock found" below means none at JLC, LCSC or any Findchips-listed distributor on 2026-10-08. **Check Digi-Key and Mouser before you decide**; some of these lines may well be stocked there.

### 1a. LCSC-numbered lines (88). Price at quantity is for 2 boards, in USD, from JLC's ladder

Result: **71 OK, 2 low, 1 short, 14 zero at JLC.** This is unchanged from the 2026-10-08 survey, apart from the swaps below. The JLC part cost for every LCSC line at the 2-board quantity, using JLC's MOQs, is $581.72. That figure includes THT parts you would buy and not have JLC place (CSV `jlc_ext_usd`).

**Proposed swaps.** Each is a true equivalent per the JLC/LCSC parametric listing:

| Line | From | To | JLC stock | Why it is equivalent |
| --- | --- | --- | ---: | --- |
| J4 | C17616543 (0430451612, stock 0) | **C491447** | 7,797 | Same Molex part. LCSC lists it as "430451612" (leading zero dropped), with identical attributes: 2×8, 3 mm, vertical THT, tin, with posts, 8.5 A, 600 V |
| R87, R105, R120 | C861111 RT0603BRD07133KL (0) | **C1509631 Viking ARG03BTC1333** | 2,365 | 0603, 133 kΩ, ±0.1 %, ±25 ppm/°C, 100 mW, 75 V thin film: every attribute matches. The survey had already named it; it was not yet applied |
| U35 | C5122398 SN6507DGQR (0) | **C7528027 SN6507DGQRQ1** | 64 | Same device, AEC-Q100 grade, same DGQ HVSSOP-10. It costs $13.69 against $5.24. **Check the SN6507-Q1 datasheet pinout before applying.** JLC placement is preferred: U35 is 0.5 mm pitch with capped EP vias, which is a poor hand-solder job |

**Not equivalent, so not proposed:**
- VOL628A-2X001T (172 in stock): its CTR bin is 63–125 %, against 100–200 %.
- ISO7710DW (tube): also 0 in stock.
- 6SVPC220MV (875 in stock): it looks like a packaging variant of 6SVPC220M, but I did not check it against the Panasonic datasheet. The 13 at JLC cover 2 boards anyway.

**Short, low or zero lines after the swaps** (Findchips / TI, 2026-10-08):

| Line | MPN | Need (2 boards) | JLC | Best other source seen | Disposition |
| --- | --- | ---: | ---: | --- | --- |
| Q2, Q3, Q5, Q6 | IPW65R018CFD7(XKSA1) | 8 | 6 | Newark: 222 at CAD 15.01 @10 | Buy 10 from Newark, one lot (D-8) |
| C3, C4 | DE1E3RA222MA4BP01F | 4 | 6 | Newark: 7 | Enough for 2 boards; buy all 6 now |
| C126–C129 | 6SVPC220M | 8 | 13 | n/a | Enough for 2 boards |
| U9, U32–U34 | ISO7710DWR | 8 | 0 | TI direct: "Out of stock" (ti.com part page). Brokers only (Win Source 13,350) | Distributor buy, then hand-solder or JLC pre-order |
| U36 | VOL628A-3X001T | 2 | 0 | TME: 1,621 (reel breaks) | Distributor buy, hand-solder |
| R5 | WSK25121L000FEA | 2 | 0 | Newark: 723 + 3,394 at CAD 1.35 @1 | Distributor buy, hand-solder |
| R77, R95, R110 | RT0603BRD076K12L (6.12 kΩ 0.1 %) | 6 | 0 | **None found.** Every 6.12 kΩ 0.1 % 0603 at JLC is 0; Avnet 0 | **Blocker:** check Digi-Key/Mouser, or make a design call |
| C1, C2 | R463N410000N1M | 4 | 0 | **None found** (Avnet 0, Newark 0) | **Blocker:** check Digi-Key/Mouser |
| L1 | B82726S2203A020 | 2 | 0 | **None found** (Newark 0, TME 0) | **Blocker** |
| J2, J5, J7–J10 | 74650074(R) | 12 | 0 | **None found** (Newark 0, RS 0) | **Blocker.** These are also THR (paste-in-hole) parts that need preheat if soldered in house |
| C21, C22 / C23 | 942C12P22K-F / 942C12P1K-F | 4 / 2 | 0 | **None found** (Richardson 0) | **Blocker** |
| D3 | MRT130KP295CV | 2 | 0 | **None found** (Avnet, Newark, Microchip 0). Digi-Key list price $46.22 | **Blocker** |
| J6 | Phoenix 1704004 | 2 | 0 | Authorized distributors 0; brokers only | **Blocker** (or a broker) |

### 1b. Consigned and hand-assembled lines, with their mating parts

| Line | Part (verified on the maker's page) | Source seen 2026-10-08 | Buy |
| --- | --- | --- | --- |
| F1 | Eaton MDA-25-R | [Digi-Key](https://www.digikey.com/en/products/detail/eaton-electronics-division/MDA-25-R/1877889): $4.642, stock not shown. [RS 70149587](https://us.rs-online.com/product/eaton-electronics/bk-mda-25-r/70149587/): BK/MDA-25-R, 35 at $6.56 @5. TME BK-MDA-25-R: 653 (100-piece break). BK/ is the boxed pack of the same cartridge | 5 |
| F1 clips | Littelfuse 01220088Z | [RS 70184419](https://us.rs-online.com/product/littelfuse/01220088z/70184419/): 179 at $0.93 @10. Newark 18AC0717: 24,259. Digi-Key: $1.04 | 10 |
| C5, C6 | TDK **B32656G0275J000**. The code is valid: TDK MKP B32651–658 datasheet p.29 gives 2.7 µF ±5 %, 1000 VDC, 33 × 48 × 42 mm, P1 20.3, **untaped MOQ 360** | **Not on Digi-Key, nor at any Findchips distributor** | **Blocker:** ask TDK for samples, or make a design call |
| U1, U2 | TI **UCC21550BDWKR**: ACTIVE, SOIC DWK-14, 2,000/reel ([ti.com part page](https://www.ti.com/product/UCC21550/part-details/UCC21550BDWKR)) | TI direct: "Out of stock". No Findchips listing. Digi-Key: 403 | 4. Check Digi-Key/Mouser |
| T1 | Coilcraft **CST3015-100ED**: 1:100, 3.2 mH (Doc 1608, rev 09/08/25; "D" = 13″ reel of 90, cut tape available) | Not on Digi-Key or Findchips. coilcraft.com returned 403 | 2. Order from Coilcraft direct or as a sample |
| T2, T3 | Würth **750320775**: WE-PPTI EP7 HV, rev 001.002, dated 2026-07-29, status "Valid" (we-online datasheet PDF) | New part, no distributor listing | 4. Ask Würth Midcom for samples |
| R34 | Yageo RT0603BRD0710K6L (10.6 kΩ 0.1 %) | **None found** at JLC (all 10.6 kΩ 0.1 % 0603 at 0), on Findchips or on Digi-Key ("no results") | **Blocker:** R34 sets the shunt-OCP band (RELAYOUT L2) |
| J3 | JST **B2P3-VH(LF)(SN)** | Brokers only on Findchips (Bristol 589; Greenchips 753 at $0.07). No authorized listing seen | 3 |
| J3 mate | **VHR-3M** (or VHR-3N) | Heilind: VHR-3M 12,425 at $0.0746. Newark: VHR-3N 478,989 | 4 |
| J3 crimps | **SVH-21T-P1.1** (AWG 22–18) or **SVH-41T-P1.1** (AWG 20–16), in positions 1 and 3; cavity 2 stays empty | Heilind: SVH-21T-P1.1 30,549 at $0.0587. TME: SVH-41T-P1.1 61,401 | 10 |
| J4 | Molex 0430451612. **Use JLC C491447** (above) | JLC 7,797. [Sager](https://www.sager.com/product/0430451612-molex/80496): 3,802 at $1.71 | 2 |
| J4 mate | **Molex 43025-1600 (0430251600)**, Micro-Fit 3.0 receptacle, 2 × 8 ("MICRO-FIT 3.0 REC 02X08P") | Sager: 3,630 at $0.5329 | 2 |
| J4 crimps | **Molex 43030-0007 (0430300007)**: tin, 20–24 AWG, loose. Tin matches the tin header. 43030-0001 is the same terminal on a 12,000-piece reel | Sager: 75,298 at $0.0988 | 40 |
| J2/J5 lugs (M6) | TE **2-34853-1**, the insulated M4 ring the M6 decision names as candidate | Newark: 6,541 at CAD 0.40. Heilind: 1,125 | 4 |

**J3 mate: the brief says VHR-3N, the repo says VHR-3M. Both fit.** JST's VH datasheet (eVH.pdf):
- p.6, item 3①: B2P3-VH is the doubled-pitch header (posts in circuits 1 and 3), so it takes a 3-circuit VH housing.
- Housing table: VHR-3N and VHR-3M are both 3-circuit. In the M type, "the exposed contact lances … are covered by resin … further improving electrical safety".
- Line voltage appears across J3 when the TCO opens, so **use VHR-3M**, as F1-J3-PARTS.md says.

### 1c. J4: is Molex 0430451612 real, and does it match the board?

- **It is a real, current part.** It is listed and stocked at:
  - JLC: C491447, 7,797; C17616543, 0;
  - Sager: 3,802;
  - Avnet, as 43045-1612: quoted at 17 weeks lead time;
  - Newark (on Findchips): "MICRO-FIT 3.0 HDR 02X08P VT".
- LCSC parameters for C491447:
  - Micro-Fit 3.0, 2 × 8 = 16 pins, 3.00 mm pitch and row spacing;
  - vertical through-hole, tin over brass;
  - "With column" (PCB posts);
  - 8.5 A, 600 V, black UL94V-0, −40 to +105 °C.
- **Footprint:** J4 uses `Molex_Micro-Fit_3.0_43045-1612_2x08_P3.00mm_Vertical`. That is KiCad's pattern for this exact MPN, with the local override that grows the pads to 1.6 mm.
  - 16 plated holes of 1.02 mm: pins 1–8 on one row and 9–16 on the second, 3.0 mm apart.
  - 2 NPTH of 1.02 mm at (−3, 3.94) and (24, 3.94) mm.
- **Pinout:** `power_stage_120v.ato` connects all 16 pads, from p1 V15_SELV to p16 LINE_ZC. The pinout is consistent with a 16-circuit Micro-Fit header.
- **Not verified:** the two NPTH post holes against Molex drawing `430451612_sd.pdf`. molex.com refused every automated fetch. Open the drawing in a browser and check:
  - post diameter against the 1.02 mm NPTH;
  - post position (−3, 3.94);
  - circuit-1 orientation.

  A post that doesn't fit stops the header from seating.

---

## 2. JLC order parameters (enter these exactly)

**PCB** (jlcpcb.com quote page)

| Field | Enter | Source |
| --- | --- | --- |
| Base material | FR-4 | |
| Layers | **4** | |
| Dimensions | **290 × 190 mm** (L outline; enter the bounding box) | README, review.json |
| PCB qty | **5** | PROTOTYPE-LOT |
| Different designs | 1 | |
| Delivery format | Single PCB | |
| PCB thickness | **1.6 mm**. **Order note: finished thickness 1.6–1.76 mm (+10/−0 %); please confirm, otherwise build at 1.8 mm** | FAB-NOTE (REDCUBE needs ≥ 1.6) |
| Specify stackup | **JLC041622-7628** | FAB-NOTE, D3 |
| Material type | **Pick whatever JLC's CTI answer names** (for example TG155 if they confirm NP-155F). The default "FR4-Standard TG135-140" has no stated laminate | CTI-JLC.md |
| Outer copper | **2 oz** | |
| Inner copper | **2 oz** | |
| Surface finish | **ENIG** | FAB-NOTE |
| Solder mask / silkscreen | Green / White | |
| Via covering | **Epoxy filled & capped (POFV)**. Order note: "all 767 × 0.3 mm vias filled and capped, no exceptions; the ten 0.8 mm vias stay tented" | FAB-NOTE |
| Min via hole / diameter | 0.3 / 0.6 mm | |
| Mark on PCB | **Remove mark** (remove order number) | FAB-NOTE |
| Impedance control | No | |
| Confirm production file | **Yes** | FAB-NOTE |
| Electrical test | Flying probe (default) | |
| Castellated, gold fingers, edge plating | No | |
| Material/CTI note (order remark) | "Laminate CTI ≥ 175 V (IEC 60112 material group IIIa) required. Please confirm the laminate and state its CTI on the CoC." | FAB-NOTE, CTI-JLC.md |

**Check in the quote page before paying:**
- that POFV can be selected together with 2 oz outer and inner copper on 4 layers;
- that the 1.6–1.76 mm note is accepted.

If either option is greyed out, ask JLC; don't drop the requirement.

**PCBA**

| Field | Enter |
| --- | --- |
| Assembly | Yes. PCBA type: **Standard** (the estimate below assumes it) |
| Assembly side | **Top** (all 357 CPL rows are Top) |
| PCBA qty | **2** |
| Tooling holes | Added by JLCPCB. The board has 3 fiducials |
| Confirm parts placement | **Yes**. Check every rotation (FAB-NOTE, M9) |
| Files | `fab/bom-jlcpcb.csv` and `fab/cpl-jlcpcb.csv` |
| BOM confirmation step | Apply the 3 swaps in 1a. **Untick every THT line** (hand-soldered in house) and every zero-stock or consigned SMD line (U1/U2, T1, T2/T3, R34, ISO7710 ×4, VOL628A, WSK R5, the 6.12 kΩ parts) |

## 2a. Cost estimate (ESTIMATE, not a JLC quote)

I did not run JLC's price calculator, because it is part of the order flow. Enter section 2 on the quote page to get the real number (no login needed).

| Block | USD | How it was derived |
| --- | ---: | --- |
| Bare PCB, 5 pcs, all options | **180–380** | 5 × 0.0551 m² = 0.276 m². The 4-layer base for this area is about $40–70. Adders: 2/2 oz about +$40–80, ENIG about +$20–60, POFV on 4 layers about +$50–100, mark removal and confirmation small. **Judgement from JLC's usual pricing, not a quote** |
| PCBA service, 2 boards | **≈ 245** | Standard setup about $25; stencil for a 290 × 190 board about $15–20; **66 Extended part types × $3 = $198** (64 in-stock Extended lines plus 2 swaps; AO3400A and CC0805KRX7R9BB104 are Basic now); about 1,700 SMT joints × $0.0017 ≈ $3 |
| JLC-placed parts, 2 boards | **≈ 147** | 66 in-stock SMD lines (64 Extended, 2 Basic) at JLC's ladder and MOQ = $119.77 (CSV). Plus the U35 Q1 swap, $27.38, and the 133 kΩ swap, about $0.15 |
| Shipping, JLC to US | 40–80 | Estimate: about 1.5–2 kg of 2 oz boards. **Import duties are not included and may be material** |
| **JLC order subtotal** | **≈ 610–850** | |
| In-house parts at known prices | ≈ 205 | LCSC THT in stock, $40 (CSV), plus distributor buys at the prices above. FETs ×10 ≈ $108 (CAD at about 0.72). MDA-25-R ×5 $33, clips $9, J3/J4 mates and crimps $7, R5 $4, lugs $1 |
| In-house parts with unknown prices (estimates) | ≈ 340 | UCC21550 ×4 about $16; CST3015 ×2 about $20; 750320775 ×4 about $24; **C5/C6 ×4 about $60 (sample price unknown)**; ISO7710 ×8 about $20; CMC ×2 about $24 (Newark list CAD 12.81); REDCUBE ×12 about $28; 942C ×6 about $28; **MRT130KP295CV ×2 ≈ $92** (Digi-Key list); 1704004 ×2 about $6; X2 ×4 about $3; R34 and 6.12 kΩ about $2 |
| **Total for the lot** | **≈ $1,150–1,400** | Excludes import duties, distributor shipping, M3 nylon fixings, and any TDK MOQ-360 charge if samples are refused |

---

## 3. Go / no-go

### Ready

- Gerbers and drill: the zip hash matches FAB-NOTE, and the JLC DFM check passes (`jlc-dfm.json`, 0 failures).
- Independent outer-copper probe: 889/889. Negative control re-run.
- BOM/CPL: 357 placements, all top side, pad-centre centroids. Assembly drawing exported.
- Review: no open BLOCKER. MAJORs are closed or decided, except M11 (REVIEW-TRIAGE, stage 10/11 re-review: "No new BLOCKER or MAJOR").
- **M6 and M10 are decided by the owner** (commit `d39280a28`, 2026-10-08 22:43). J2/J5 stay at 15 mm with insulated M4 ring lugs. The L outline is recorded, with J4 on the tongue. FAB-NOTE.md still lists them as open gates; it is stale on this point.
- Enclosure fixings: the holes are frozen at the positions the enclosure adopted (REVIEW-TRIAGE M4).

### Blocks the order

1. **CTI written confirmation from JLC.** `sourcing/inquiries/CTI-JLC.md` is a **draft, not sent**. Every laminate JLC lists with a findable datasheet is PLC 3 (175–249 V). That is exactly the floor, with no margin.
2. **FEM corrections for native-21** (task 01, FINDINGS M11 OPEN). The provisional matrices pass 252/252 on both legs with F6. Native-21's own crop and low-height corrections and the fine extraction are still running on the remote box (`a21corr`, `campA21`; leg B in progress).
3. **Owner item M11:** the HOT↔PE stack at the heatsink (sink, insulator, clamp) is not modelled. It is open in D5-AUDIT.
4. **Parts with no in-stock source found.** Check Digi-Key and Mouser first:
   - C5/C6 B32656G0275J000 (MOQ 360);
   - R34 10.6 kΩ and R77/R95/R110 6.12 kΩ, both 0.1 %;
   - L1 B82726S2203A020; C1/C2 R463N410000N1M; C21–C23 942C;
   - J2/J5/J7–J10 74650074R; D3 MRT130KP295CV; J6 1704004;
   - U1/U2 UCC21550BDWKR (TI out of stock); U9/U32–U34 ISO7710DWR (TI out of stock, brokers only).

   Ordering boards before these are secured parks the lot.
5. **Owner approval of the spend** (PROTOTYPE-LOT gate 4).

### Also found (fix or decide before ordering)

6. **The two gate lists disagree.**
   - FAB-NOTE.md says the package "isn't released for ordering" until insulation and thermal qualification and the F1 certifier confirmation close.
   - PROTOTYPE-LOT.md says insulation qualification does not gate a bench lot on a current-limited isolated supply.
   - The owner should say which list governs this lot. As written, FAB-NOTE blocks it.
7. **Stale counts in PROTOTYPE-LOT.md:**
   - "42 in-pad vias": FAB-NOTE says 79 fully in pad and 63 overlapping.
   - "87 lines with checked LCSC numbers": FAB-NOTE says 88.
   - "M3 nylon … H2–H8": the board has 7 fixings, H1–H7, with H2–H7 nylon. Buy hardware for 7 holes.
8. **J4 post holes** (1.02 mm NPTH) are not yet checked against Molex drawing 430451612_sd (section 1c).
9. **REDCUBE studs are THR parts** (FAB-NOTE: paste-in-hole reflow). The lot plan has them hand-soldered in house, and they are zero stock at JLC. In-house soldering into 2 oz pours needs a preheated board. Alternatively, buy them and have JLC place them once they are in stock.
10. **J3 has no authorized-distributor stock** on Findchips; brokers only. Check Digi-Key.

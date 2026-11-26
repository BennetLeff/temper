# jlc-max-r1: what else can move onto JLC (native-21 s57 power board)

Scope study, 2026-11-26 (owner direction 2026-11-25: "JLCPCB to solder and build as much of the system as possible, leaving
near-zero hand-soldering on my bench"). Baseline: `claude/native21-s55-unified` @ `efafdfc77` (DECISIONS 91), board
`25596d8e…`, 92 of 95 BOM lines JLC-assembled. **Nothing was ordered, carted, logged into, sent or pushed. No board, BOM, CPL
or order file was changed by this study.** The controller (C51) half is `controller-c51:zapote/controller/evidence/c51/jlc-max-r1/`.

Evidence (all re-readable):
- JLC public parts API, read 2026-11-26 04:11–04:18Z: `reads/jlc/*.json` (`scripts/jlc.py detail|search`, no login).
- Octopart public search pages, read 2026-11-26 04:14–04:15Z: `reads/octopart-2026-11-26.json` (`scripts/octopart_fetch.sh`,
  `scripts/octopart_parse.py`, copied from consign-r1; the raw HTML is not committed, same as consign-r1).
- Board pad geometry: `board-of-record-s57/section.kicad_pcb` (sha256 `25596d8e…`), read directly.
- JLC footprint models: `08-manufacturing-package/native-21/cpl-rotation-audit/sources/easyeda-footprints.json` (committed).
- JLC policy text: `../consign-r1/reads/pages/` (pages "Last updated on Sep 09, 2026").

Lot sizes used: 5, 10, 20 assembled boards (PROTOTYPE-LOT: stock gate sized at 20).

## Bottom line

1. **F1 clips can go to JLC with no copper change at all.** Add two CPL rows (F1A, F1B) at the clip centres and one BOM line
   (01250003H, C223911). The Gerbers and board file stay byte-identical, because the slots are already in F1's footprint and
   JLC's own C223911 model has the same 2 pads, 10.80 mm apart on the same axis. **Stock has fallen to 32 (101 on 10-18)**, so
   JLC stock covers up to 15 boards. A 20-board lot needs Global Sourcing for all 42 (Future 3,868, Newark 1,233), and you can't
   top up JLC's 32 from another source in the same order.
2. **RV1: no JLC-stocked alternative exists.** TMOV20RP175E (C1527834, 109) is the only 175 V thermally protected MOV JLC
   stocks. Every in-line or crimped lead variant (`…175M`, `…ML2B7`, `…EL2T7`, `…ML4B7`) has 0 stock, and the TMOV14 and TDK
   ThermoFuse options have 0 too. JLC publishes a "Bending Pins Soldering" service ($0.0157/pin, "lying down orientation") and
   says it supports "a wider range of personalized services in actual production" by order note. But no JLC page offers the
   in-plane jog that RV1 needs, so a lead-form remark is **unconfirmed**. Clean fix for the next copper revision: a land that
   takes the bulk-pack offset lead as delivered. Until then, RV1 is the one line that needs a JLC answer.
3. **J6 is the highest-risk line on the board.** The only authorised stock anywhere is Amar Radio (48 + 43, offer stamped
   2026-11-02). TME, Sager, RS and Omnical show 0, and JLC shows 0. No JLC-stocked drop-in exists for the 15.24 mm 2-pin KDS 3
   land. **For this revision, consign it** (C5481600 is a JLC number) in the FET parcel. That avoids the $20 Global Sourcing
   inspection fee and the risk that Global Sourcing has no supplier. For the next revision, use a JLC-stocked PE termination
   on a new land.
4. **BR1 for boards #2 and up:** JLC holds 110 (C526644, `manualWeld`). The clean route is a **second PCBA order** with BR1
   fitted, placed after board #1 passes COMMISSIONING step 4. The cost and the commissioning consequence are below.
5. **Global Sourcing has two new high-risk lines since 10-18:**
   - **U41 / U42:** JLC's record for C9900245652 now carries `noBuyReason: "This product is no longer manufactured."` RECOM's
     distributors still list it as Active (DigiKey) and Mouser holds 988.
   - **L1:** Mouser and DigiKey now show 0. The only authorised stock is Newark (84).

   No JLC-stocked equivalent passes the gates without margin loss on any of the eight lines.

## 1. F1 clips: consign-r1 candidate (c)

| Item | Finding | Evidence |
|---|---|---|
| Live stock | C223911 01250003H: **32** (presale 31), Extended, `manualWeld` / THT; $1.82 @1, $1.40 @30 | `reads/jlc/detail_C223911.json` |
| Need | 2 per board + attrition: 12 (5 boards), 22 (10), 42 (20) | — |
| Distributors | Future 3,868 (MOQ 10, $2.00), Newark 1,233 (MOQ 1), Arrow/Verical 600, Master 300 | `reads/octopart-2026-11-26.json` |
| Board pads (s57) | F1 at (246.35, 7.25), rot 0. Pads `1` at x +10.08 / +20.88, pads `2` at −10.08 / −20.88; each is an oval 2.4 × 3.7 with a 1.2 × 2.5 oval drill (long axis ⟂ fuse axis) | `board-of-record-s57/section.kicad_pcb` |
| JLC's model | `BAT-TH_01250003H`: 2 OVAL pads 1.9 × 3.2, **10.80 mm apart along x**, long axis y, round 1.2 mm hole (EasyEDA draws the slot as a round hole; our Gerber slot governs) | `cpl-rotation-audit/sources/easyeda-footprints.json` |
| Clip centres | **F1A** (pads 1) = (261.83, 7.25); **F1B** (pads 2) = (230.87, 7.25); rotation 0. In `cpl-jlcpcb-order.csv` (y negated): (261.830, −7.250) and (230.870, −7.250) | derived: 246.35 ± 15.48 |
| Orientation | The clip is a symmetric ear-style clip (F1-RECOMMENDATION: "ear style"; pin 0.70 × 2.00 in the 1.2 × 2.5 slot), so 0° and 180° fit the same. Confirm in JLC's 3D preview that the ears face the fuse (inward) | — |
| JLC rules | THT marked wave soldering is "assembled manually"; $3.5 labour + $0.0173 per joint (4 joints per board). Plated slots are fabricated now: they are already in the s57 Gerbers and pass DFM | consign-r1 pages |

**How to land it (no copper):**
- `bom_cpl_jlc.py` emits two extra CPL rows (F1A, F1B) from F1's placement and the footprint's pad pairs, so they move if F1
  moves.
- `apply_lcsc.py` replaces the `F1-CLIP` hand-assembly row with a BOM line `01250003H, "F1A,F1B", C223911`. Its assembly
  note: "JLC hand-solders; 2 oz/2 oz slots: bottom preheat; fill barrel".
- `hand-assembly-extras.csv` keeps the F1 cartridge note only.
- Gates to extend:
  - the CPL rotation audit gets a row type for a "sub-placement of a multi-part footprint" (pads = a named subset of F1's);
  - `check_order_docs.py` counts 93 JLC lines;
  - the scorecard's consign/owner-line counts drop by 1.
- Board, Gerbers and `section.kicad_pcb` hashes do not change.
- The order remark gains: "F1A/F1B fuse clips: solder both slots per clip with bottom preheat (2 oz inner/outer); ears face the
  fuse; leave the F1 cartridge out."

Why not the full footprint split (three components in ato)? It would change the board file hash and the netlist, which means a
chain re-run and a new board of record. That is worth doing only when copper changes anyway; fold it into the next copper
stage.

**Sourcing by lot:**

| Lot | Route |
|---|---|
| ≤ 10 boards | JLC stock (reserve it by pre-order on the order day) |
| 11–15 boards | JLC stock is exactly enough or short |
| 20 boards | Global Sourcing the full 42 from Future or Newark: fuseholder, so $20 inspection fee; JLC's "same-MPN stock from different sources must go in separate PCBA orders" rule rules out a top-up. Or add 42 to the FET consignment parcel (C223911 is a JLC number) |

**Reverses if:** JLC's BOM step refuses a designator that has no footprint in the board file (JLC's matching is file-based, so
this is expected to pass, but it is unproven). Fallback: the ato split above.

## 2. RV1 (TMOV20RP175E, C1527834)

| Candidate | JLC | Notes |
|---|---:|---|
| TMOV20RP175E (C1527834, fitted) | **109** | bulk E leads are offset (`e1` 1.5–4.0, FOOTPRINTS F4); JLC's own model is `RES-TH_…-P8.50-…-S4.25`, pads 8.5 apart along the body and 4.5 mm offset, **not** our in-line 7.5 mm land |
| TMOV20RP175M (C1527896) | 0 | — |
| TMOV20RP175ML4B7 / ML2B7 / ML2T7 / EL2T7 | 0 / 0 / 0 / 0 | crimped/in-line lead forms, the natural fit for an in-line land |
| TMOV14RP175E / M / L-forms | 0 | 6 kA / 70 J, also a rating loss |
| TDK B72220T2… (ThermoFuse) | 0 at every voltage | — |
| KNSCHA iTMOV20M431K… | 134 | 431 V class and a JLC house brand; not 175 V, UL 1449 file unverified. Rejected |

Distributor stock of the fitted part: Newark / Verical / Master / Onlinecomponents 1,200 each, Arrow 800. Stock is not the issue.
The issue is the lead form.

**Options, best first:**
1. **This revision:** ask JLC whether it will joggle lead 2 into line for RV1 at the 7.5 mm land (the "Bending Pins Soldering"
   row is the nearest published service). Draft question below. If yes: route RV1 to JLC from its own stock (109 ≥ 22 at 20
   boards). If no: RV1 stays the owner's last hand-solder job. It is a low-current, spoked-pad THT part, so no preheat is needed.
2. **Next copper revision:** redraw F4 so lead 2 sits in a plated slot that covers the delivered offset range (1.5–4.0 mm from
   lead 1's line, with lead diameter and tolerance added). JLC can then insert the bulk part as delivered. **Re-read the
   datasheet p.6 drawing before drawing copper**: the ledger copy is Rev 10/01/19, and FOOTPRINTS cites rev GD. JLC's own model
   (8.5 pitch, 4.5 offset) disagrees with both and must not be trusted. Low-current net, HOT creepage to re-check.

## 3. J6 (Phoenix 1704004, PE branch)

| Candidate | JLC | Fit to the s57 land (2 pins Ø1.4 at 15.24 mm) | Notes |
|---|---:|---|---|
| Phoenix 1704004 (C5481600, fitted) | 0 | native | authorised: Amar Radio 48 + 43 (stamped 2026-11-02); TME / Sager / RS / Omnical 0 (MOQ 50) |
| Phoenix GMKDS 3/2-7,62 (C5183940) | 18 | no (2-pole pluggable) | not a PE single-potential part |
| Keystone 7770 (C5272782) | 252 | no (4-pin screw terminal, M3) | next-revision candidate: ring lug on an M3 screw; check the UL file (unverified) |
| Keystone 8191 (C238175) | 69 | no | as above |
| TE 63824-1 (C575074) | **9,009** | no (2-pin 6.35 mm PCB tab) | next-revision candidate: 0.250 in Faston PE tab, $0.054; TE store 609,508. UL file unverified |

**Decision for this revision:** buy J6 from Amar Radio (or any authorised seller in stock at order time) and put it in the FET
consignment parcel (C5481600 is a JLC number, so it can be consigned). JLC then hand-solders it. Global Sourcing stays the
fallback, at $20 inspection fee plus the risk that no supplier is listed. The owner hand-solders J6 only if both fail.
**Next revision:** pick between TE 63824-1 and Keystone 7770 with the certifier (PE branch only; the cord-to-chassis bond does
not depend on it, per the footprint spec), then draw its land.

## 4. BR1 (GBJ2510-F, C526644): boards #2 and up

- JLC holds 110 (`manualWeld`), and distributors hold plenty (Mouser 821, Verical 3,600). Stock covers 20 boards.
- Board #1 stays BR1-DNP for COMMISSIONING steps 2–4. Its empty BR1 holes are the bench-bus landings, and step 4b is the
  owner's fit with the sink (`bench-sink-r1` §6.3). This is unchanged.
- **Clean second-batch option, PCBA order B:**
  - Order B is placed after board #1 passes step 4. It uses the same Gerbers and BOM, with the BR1 line ticked "JLC
    hand-solders" from JLC stock.
  - Order remark for BR1: "seat fully on the body, perpendicular within 1°, leads not bent above the board".
  - The sink's BR1 hole is then drilled from the **as-soldered** seat height measured on the board, not a loose part's. The BR1
    shim is still selected at dry fit. bench-sink-r1 already does this for the FETs. Its −0.610 … 1.490 mm shim range assumed a
    loose BR1 that leans 0.0362 rad in its holes, so **re-derive that range for a soldered part** before order B.
- **Consequence:**
  - A BR1-fitted board has no bench-DC landing. Its AC holes are diode-coupled to the bus, so the "BR1 absent, no continuity"
    check in ASSEMBLY.md cannot be done.
  - Boards #2 and up therefore skip the floating-bench-bus steps and start at the isolation-transformer mains step. That is
    only right once board #1 has proven steps 2–4.
  - It is a COMMISSIONING change: write it there when order B is placed.
- **Cost (estimate from JLC's published fee structure, not a quote):** a second PCBA order repeats the setup, stencil and
  Extended-part loading fees: about $25 setup, $15–20 stencil, and 74 × $3 = $222 Extended loading. That is roughly $260–270 per
  extra order. Order B also carries the consigned FET lot rules (one recorded lot), so size the first FET buy for both orders.
- **Alternative, rejected:** one order with BR1 fitted on every board. Board #1 would lose its bench landings and the no-back-feed
  check that steps 2–4 rely on.

## 5. Global Sourcing audit (the 8 lines)

Ranked by risk of JLC cancellation or fees. "GS" is Global Sourcing. JLC stock is 0 on every line below (reads 04:11–04:18Z).

| Rank | Line | Authorised stock now (Octopart 11-26) | Risk | Fees | JLC-stocked equivalent? | Recommendation |
|---:|---|---|---|---|---|---|
| 1 | **J6** 1704004 | Amar Radio 48/43 only | **High**: GS may list no supplier; offer is 3 weeks old | $20 inspection (connector) | none for this land (§3) | **Consign** in the FET parcel |
| 2 | **U41/U42** R24C2T25/R-R (C9900245652) | Mouser 988 (MOQ 1); TME/Sager/Newark 0 (MOQ 750) | **High**: JLC record says "This product is no longer manufactured"; DigiKey lists the part Active | up to 30 % duty (module) + MSL 3 bake $8 | none: UCC14240QDWNRQ1 (C7089349, JLC 6) fails 17 V and is short (consign-r1); THT modules fail (consign-r1) | Ask JLC to clear the EOL flag; else **consign** Mouser cut tape; confirm RECOM's lifecycle before the buy |
| 3 | **L1** B82726S2243A020 | Newark 84 only (Mouser / DigiKey 0 now) | **High**: GS supplier coverage of Newark unknown | none (inductor) | B82726S2183N020 (C3211792, JLC 28): 18 A / 5 mΩ vs 24 A / 3.2 mΩ: **fails** the 24 A rating | Buy Newark's stock and **consign** (C7084710 is a JLC number) |
| 4 | **F2** 3403.0279.23 | Master / Onlinecomponents 1,450 (MOQ 25), Rutronik / Future MOQ 1,500; **DigiKey not listed** (was 7,183 on 10-13) | Medium–high: GS supplier coverage of the distributors left is unknown | $20 inspection (fuse) | none (UMT-H land, `.11` variant also 0) | GS; else consign a 25-piece Master buy |
| 5 | **D3/D17** 30KPA150CA Good-Ark | DigiKey 1,911 (MOQ 1) + 1,750 reel | Medium: no public JLC number for the Good-Ark part (private library; engineer approval) | none | all JLC 30KPA150CA variants 0 | GS (DigiKey) as planned |
| 6 | **C5/C6** B32676G1905K000 (C3802167) | DigiKey 547 | Medium: single source; **JLC's record calls it `smtWeld` / SMT** although it is THT | none | B32676G1905J000 (C3810091) 0 | GS (DigiKey); at the BOM step check it goes to hand-solder, not SMT |
| 7 | **Bank** B32643H8104J000 | Mouser 1,726, DigiKey 1,336, Newark 241 | Low–medium: no public JLC number (private library) | none | none listed at JLC | GS (Mouser) as planned |
| 8 | **J2/J5** 7466004R (C6708126) | DigiKey 8,856 + 8,773, Mouser 2,800 | Low | $20 inspection (connector) | 7466004 (C5523879) 0 | GS as planned |

**One parcel, not many.** The FET lot is consigned anyway (DECISIONS 91). Adding J6, L1 and, as a fallback, U41/U42, F2 and the
F1 clips to the **same** parcel costs little extra: consign-r1 read about $85–170 per parcel over 5,000 CNY, and "70USD/50 items
service fee" on the T&C page. In return it takes three single-source lines off GS supplier coverage. It also removes the $20
inspection fees for J6 and F2, **provided** consigned connectors and fuses are not inspected the same way (unverified; ask in the
same JLC message).

### Stock drift on JLC-stocked lines (thin at 20 boards)

| Line | JLC now | 10-18 | Need at 20 | Note |
|---|---:|---:|---:|---|
| C1/C2 R463N410050N1K (C3299886) | 46 | 46 | 40 (+2) | still 1.1×: pre-order on the order day |
| T1 CST3015-200ED (C50132500) | 52 | 64 | 20 | fine |
| U5 LM4050AEM3-2.5 (C2156518) | 34 | 50 | 20 | falling: pre-order |
| J3/J11 B2P3-VH-H (C160900) | 3,639 | 5,610 | 40 | fine |
| Q2–Q6 FETs (consigned) | JLC 4 | — | 84 | **Octopart shows no DigiKey offer today** (Mouser 470, Newark 222, Arrow 100). PROTOTYPE-LOT plans "one DigiKey lot", so check DigiKey directly or re-point the lot to Mouser |

## 6. What this changes, and what needs the owner

**Decided here (no owner input needed; nothing applied yet):**
- (c) is a BOM/CPL-only change and needs no copper stage. Apply it to the order package once the owner says go.
- J6 and L1 are consigned in the FET parcel. U41/U42 and F2 are consigned if Global Sourcing refuses them.
- RV1 and J6 get new lands in the next copper stage, and the F1 three-component split rides along with them.

**Needs the owner** (contacting JLC is outward-facing). One message to JLC support, draft:

> Order prep question (no order yet), PCBA, 4-layer:
> 1. Varistor C1527834 (TMOV20RP175E) on a 7.5 mm in-line land: the bulk part's second lead is offset 1.5–4.0 mm. Can your
>    THT line form lead 2 into line before hand-soldering (order note), and at what fee?
> 2. C9900245652 (RECOM R24C2T25/R-R) shows "This product is no longer manufactured", but the manufacturer still lists it as
>    active and Mouser stocks it. Can it be Global Sourced or consigned?
> 3. Global Sourcing supplier coverage: are Newark, Master Electronics and Amar Radio among your suppliers?
> 4. Do consigned fuses and connectors attract the $20 commodity inspection fee that Global Sourcing charges?

If JLC says yes to 1, the only parts left on the owner's bench are BR1 on board #1 (by design) and inserting the F1 cartridge.

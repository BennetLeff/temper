# consign-r1: what can leave the consign / hand-solder list, and THT options for the rest

Analysis lane, 2026-10-18. Board of record: native-21 **s53** (integration board `82af7bd93e62…`, BOM = s52, `fab/bom-jlcpcb.csv`
95 lines). Controller: `controller-c1-crs:zapote/controller/ORDER.md`. **Nothing on the board, BOM, netlist or copper was
changed.** Nothing was carted, ordered, logged into or sent. No supplier or lab was contacted, and no bot check was bypassed.

Lot: 20 boards, so the need is qty/board × 20 and the alternate target is 2× that. Brokers and unauthorised sellers count 0.
Same-MPN copies sold under another maker's name (EVISUN / YLPTEC "MGJ2D24…", "R24P2…", "QA…") also count 0.

## Bottom line

1. **Almost every consigned or hand line can go into the JLC order without changing a part.** JLC's own parts records give
   `assemblyMode = manualWeld` for every THT part on this board that it lists (BR1, J1, C1/C2, C3/C4, C38–C41, L1, D3,
   RV1, Q2–Q6, J3, J4, J6, R130, PS2, the KNSCHA bank, the F1 clips). JLC already hand-solders THT. What kept the lines
   off the JLC order was **stock, not process**. JLC's Global Sourcing (JLC buys from distributors) closes the stock gap
   for every line except the FETs.
2. **U41 / U42 (RECOM R24C2T25/R-R, SSOP-36): JLC should place them.** No hot-air gear is needed. Mouser holds 1,006,
   which is 25× the need. Two THT module families were checked against this barrier's recorded requirements, and both
   fail at least one. An adapter board adds a layout stage and still needs JLC to place the same SSOP-36. **No THT
   option is acceptable.**
3. **The FETs are the one line to consign.** JLC's pre-order terms do not accept customised lot numbers, and its Global
   Sourcing terms cannot promise one production batch. Either would break D-8's one-recorded-lot rule.
4. **Owner's hand-solder list after this package: BR1, RV1 and the two F1 clips. All are THT, and no SMD is left.** J6
   joins the list only if Global Sourcing can't supply it. The owner also inserts the F1 cartridge (no soldering). The power pins are solid in 2 oz copper on four layers, and FAB-NOTE says to rework them only on a
   board preheated to at least 100 °C. So the owner needs a bottom preheater, not hot air (open question 1).

## JLC policy, read verbatim 2026-10-18 (pages "Last updated on Sep 09, 2026"; text in `reads/pages/`, times in `_fetch.log`)

| Lever | What JLC says (quoted) | Consequence here |
|---|---|---|
| Hand-soldered THT | "The part's assembly type marked with "wave soldering" in our assembly parts library will be assembled manually." Cost: "$3.5 hand-soldering labor fee + $0.0173 manual assembly fee per joint" (`pcb-assembly-faqs.txt`). The capabilities FAQ says THT parts "are assembled using wave soldering", and that "Unused through-holes are protected from solder ingress" (`pcb-assembly-capabilities.txt`) | Every THT part we use reads `manualWeld` in JLC's API (`results/consign-table.csv`). The five open x 190.5 bank holes stay open |
| Global Sourcing | "sources and stocks parts from global distributors … only for PCB assembly orders"; "If the part doesn't support assembly, this part will be canceled"; "we can't promise parts purchased from the same production batch"; lead time "Normally it's 9-20 business days" (`60-…global-sourcing….txt`, `global-sourcing-parts-order-terms-conditions.txt`) | It works for in-stock distributor parts, but JLC's review can refuse a part. It is wrong for the FET lot. Which suppliers JLC offers per MPN is only visible when logged in, at order time |
| Global Sourcing fees | "modules … may require an additional 3% -30% fees for customs duty. Switches, fuses, … connectors … require commodity inspection and 3C certification fees. The commodity inspection fee is $20 for each kind of part" | RECOM: up to 30 % duty. F2, J2 / J5 and J6: $20 each per kind |
| Mixing rule | "consign parts can only be used together with global sourcing parts, instead of JLCPCB parts" (consignment terms 1); the pre-order terms add that same-MPN stock from different sources must go in separate PCBA orders | **Q2–Q6:** consign all 80 plus attrition. JLC's 6 in stock can't be topped up with consigned parts |
| Pre-order (reservation) | "In-stock extended parts can be pre-ordered, no minimum quantity required"; the parts go to the private library (`what-is-jlcpcb-parts-pre-order-service.txt`); "JLCPCB does not accept customised lots number" (pre-order terms 8) | It reserves thin JLC lines today: C1/C2 46 of 40, T1 64 of 20, U5 50 of 20 |
| Consignment of parts with no JLC number | "only parts with JLC number can be consigned to us. If the part is not with the part number yet, please submit the consigned part. The engineer will approve it if it is workable for our assembly." "Loose components can be accepted; however, an additional handling fee will apply." (`important-note…`, `246-…`) | It is the fallback for the bank or the RECOM if Global Sourcing refuses them |
| Consignment cost (overseas) | "around 45USD for parcel value less than 5000CNY and 85USD for parcel value more than 5000CNY"; the T&C page gives "70USD/50 items service fee+ 15USD handling fee". Taxes and duties are borne by the customer | One FET shipment is about $914 of parts (> 5,000 CNY): about $85–170 in fees plus duty and VAT. **Put every consigned line in one parcel** |
| SSOP-36 from consigned or sourced stock | Standard PCBA "Minimum IC Pin Spacing 0.35mm" (`pcb-assembly-capabilities.txt`); "moisture-sensitive LEDs, Modules ect. we will suggest customer to bake the parts around 48hours" for $8 | 0.65 mm pitch is inside the capability. RECOM is MSL 3 (datasheet p.8): pay for the bake |
| Timing | "we can only proceed after all components have been fully received and stored in our warehouse" (`component-matching-guidelines….txt`) | Place the sourcing orders first, then the PCBA order. Allow about 3–4 weeks |
| Unassembled parts | "Unassembled consigned parts cannot be shipped with PCBs" | Consign only what JLC fits, plus attrition. Keep the spare FETs at home |

## Ranked table

Stock is from JLC's parts API, read 2026-10-18 19:29–19:43Z (`reads/jlc-raw/`), and from Octopart public pages read
19:39–19:44Z (`reads/octopart-2026-10-18.json`). Octopart's own offer stamps are DigiKey 2026-10-18T12:16Z and Mouser
2026-10-16T21:15Z, so the Mouser figures are two days old. digikey.com returned 403 and mouser.com a bot wall
(`reads/distributors/_fetch.log`). `scripts/consign_table.py` rebuilds every number offline.

| # | Line | Current part | Why it was off the JLC order | Best alternate or process lever | Drop-in? | Margins touched | Approval basis | Stock evidence (2026-10-18) | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | U41, U42 (2) | RECOM R24C2T25/R-R | SSOP-36 0.65 mm, not in JLC stock. JLC C9900245652 is a placeholder with 0 stock. The owner has no hot air | **Global Sourcing from Mouser + JLC SMT.** Fallback: consign Mouser cut tape. **Do not accept JLC's auto-match C22466894 "R24C2T25-R"**: that is the non-/R series, a different product (ledger note). THT: rejected (§U41/U42) | no change | none | HOT-to-HOT functional barrier. The UL E542996 logo (p.1) is not relied on | JLC 0; Mouser 1,006 (MOQ 1) ≥ 80 | **JLC places** |
| 2 | Q2, Q3, Q5, Q6 (4) | IPW65R018CFD7XKSA1 | JLC 6 against 80; D-8 needs one recorded lot | **Consign the DigiKey lot of 120** (PROTOTYPE-LOT's plan). Send 80 + about 4 to JLC and keep the rest. All 80 must be consigned (mixing rule). Not Global Sourcing (no batch promise) | no change | none | n/a | JLC 6; DigiKey 459; Mouser 470 | **Consign, JLC hand-solders** |
| 3 | Bank C21–C23, C151, C152 (5) | TDK B32643H8104J000 | No JLC / LCSC listing | **Global Sourcing**: Mouser holds 1,736 (new: the s52 plan used DigiKey 306). Fallback: consign the distributor buy (engineer approval needed: no JLC number) | no change | none (owner's 24 A choice, DECISIONS 74, kept) | per ledger (not a mains-safety part) | Mouser 1,736, DigiKey 306, Newark 233 ≥ 200 | **JLC hand-solders.** Owner ticks H |
| 4 | C5, C6 (2) | TDK B32676G1905K000 | JLC 0 | **Global Sourcing** (DigiKey) | no change | none | n/a (DC link) | JLC 0; DigiKey 547 ≥ 80 | **JLC hand-solders** |
| 5 | L1 (1) | TDK B82726S2243A020 | JLC C7084710 at 0 | **Global Sourcing** (Mouser) | no change | none | EN 60938-2 only, no UL file (existing certifier gap) | Mouser 62, DigiKey 29 ≥ 40 on Mouser alone | **JLC hand-solders** |
| 6 | D3, D17 (2) | Good-Ark 30KPA150CA | JLC C19111562 (Littelfuse-branded) at 0 | **Global Sourcing**, picking DigiKey's **Good-Ark** offer (the ledger maker) | no change | none | n/a | DigiKey 164 (MOQ 1) + 1,750 (reel, MOQ 250) ≥ 80 | **JLC hand-solders.** The P600 lead-bend check (ledger gap, hole 1.8 mm from the body) stays a first-article item |
| 7 | J3, J11 (2) | JST B2P3-VH(LF)(SN) | Consign line. JLC held 983 on 10-15 and **0 today** | **BOM-only: B2P3-VH-H(LF)(SN), C160900.** It is the same JST standard header in grey; JST eVH.pdf (sha d51e669c, the ledger's copy) model-number key: "Color: No indication…Natural (White), … H…Gray". Same PA body, 250 V AC/DC, −40…+105 °C | **BOM only** (same footprint and drawing) | none (rating identical) | UL E60389 (JST family; file still unread, existing gap) | JLC 5,610 ≥ 80 (also -B PBT-GF 10,635 and -R 1,567) | **Swap (a); JLC hand-solders** |
| 8 | C1, C2 (2) | KEMET R463N410050N1K | Listed "consign". JLC C3299886 holds 46 | **Keep the part and reserve JLC's 46 by pre-order** (in stock, no minimum). Fallback, BOM only: **TDK B32923C3105M189** (C3299462) | fallback is BOM only (same P22.5, d 0.8, width and length; height 20.5 vs 20.1 mm max: re-run the 3D fit gate) | fallback: ±20 % against ±10 %. The s19b "X caps −20 %" corner becomes a real tolerance edge (1.57 dB with today's module, ≥ 6.95 dB with the ≥ 100 µH module). No S1 effect (X caps, no PE) | KEMET: UL 60384-14 / CSA E97797. TDK: "UL 60384-14:2014 … E97863 (approved by UL)", CSA E60384-14, ENEC, CQC (TDK June 2023 p.2) | KEMET JLC 46 (1.15×), Newark 1,298; TDK JLC 1,000 | **JLC places the KEMET**; TDK only if JLC < 42 at order |
| 9 | J1, C38–C41, C3/C4, R130, PS2, J4 | as BOM | Already JLC lines. FAB-NOTE's prose still says "J1 … the film caps" are hand-soldered in house | **Process: let JLC solder them** (JLC stock ≥ 2× on all of them) | no change | none | as ledger | J1 159, C38 309, C3 104, R130 225, PS2 5,047, J4 7,748 | **JLC hand-solders; fix the FAB-NOTE text** |
| 10 | F2 (1) | Schurter 3403.0279.23 (SMD) | JLC 0 | **Global Sourcing + JLC SMT**: $20 inspection fee (fuse). DigiKey's 7,183 (10-13) is not visible on today's Octopart | no change | none | UL 248-14, cURus E41599 | Master / Onlinecomponents 1,475 (MOQ 25); Rutronik / Future 1,500 (MOQ 1,500) | **JLC places** (check supplier coverage at order) |
| 11 | J2, J5 (2) | Würth 7466004R (SMD) | JLC 0 | Unchanged plan: Global Sourcing + JLC SMT ($20 fee, connector) | no change | none | n/a | DigiKey 8,856, Mouser 2,920 | **JLC places** |
| 12 | J6 (1) | Phoenix 1704004 | JLC 0 | Global Sourcing if JLC lists a supplier; otherwise owner THT (low current) | no change | none | UL E60425 / CSA 13631 | Amar Radio 48, Master 31 (MOQ 50); 2× = 40 only on Amar | **Conditional** |
| 13 | F1 clips (2 × 01250003H) | Littelfuse 01250003H | No CPL row (the clips are inside F1's footprint), so JLC rejects a BOM line | **Layout / source candidate (c):** make the two clips their own components (pads = today's slots) so JLC can hand-solder them | source + footprint split; copper identical | none if the pads are byte-identical | UL Recognized E14721 (existing gap: no voltage rating) | JLC C223911 101 ≥ 80 | **Owner until (c) lands** |
| 14 | RV1 (1) | TMOV20RP175E | Deselected 2026-10-17: the bulk leads are offset and must be formed (FOOTPRINTS F4); JLC's model did not match | Keep the decision. JLC 114 would cover it if JLC accepts a "form lead 2 in line" remark | no change | none | UL 1449 E320116 | JLC 114 ≥ 40 | **Owner** (THT, spoked low-current pads) |
| 15 | BR1 (1) | GBJ2510-F | Not consigned. ASSEMBLY.md makes fitting BR1 a heatsink step, and bench-bus boards run with BR1 absent | none | — | — | — | JLC 1,579 | **Owner** (THT, needs preheat) |
| 16 | F1 cartridge (1) | Littelfuse KLDR025.TXP | Inserted into the clips after cleaning, not soldered. JLC doesn't ship unassembled parts | none: owner buys and inserts | — | — | UL Listed E81895, CSA LR29862 | Future 300 (MOQ 10), Standard Electric 246 | **Owner (no solder)** |
| 17 | T1 (1) | Coilcraft CST3015-200ED | Old records call it a no-stock buy | Already a JLC line; **reserve it by pre-order** | no change | none | per ledger | JLC 64 ≥ 40 | **JLC places**; fix FAB-NOTE's pre-order list |
| C | Controller R39 (1) | Susumu RG2012V-431-W-T1 (0805, 0.05 %, 5 ppm/K) | JLC 0; only reels were seen before | No 5 ppm/K source. Octopart lists RG2012V-431-B/-W/-P/-D/-C and TNPU0805430R* with **no authorised stock at all**. The RT0805 0.1 % / 25 ppm part stays rejected (CR-2 budget, ORDER.md C37) | — | RTD accuracy if anything weaker is fitted | n/a | JLC 0; Octopart: no offers | **Consign if a source appears; otherwise DNP**, and the owner fits the 0805 with a plain iron (no hot air) |

Controller hand-placed parts otherwise: none. J11 (TC2050) is copper only, and the ESP32's U.FL coax and antenna board
are plug-in items.

## U41 / U42 in detail: what the module does and why there is no THT option

**What it does here.** One module per high side: HS-A on SW_A, HS-B on SW_B. The primary runs from V24_RAW / N_LS on the
TCO-switched PS2 domain, enabled by the shared CTRL divider at 5.10 V. The secondary gives a single 17.0 V span, set by
0.1 % feedback resistors, into the TLVH431 split (+15 / −2 V), the reservoir and the rail monitor that feed the
2EDR8259X high-side driver (DECISIONS stage 14; ALT-BIAS A1).

**The barrier is HOT-to-HOT and functional**, not a SELV barrier. It is not one of the five parts the audit allows across
HOT↔SELV, and it is not in the S1 touch-leakage budget (`07-conducted-emi/leakage/leakage_budget.py` counts Y caps, coil
to PE and the supplies). So the 8.8 µA S1 margin does not depend on the choice here. **Barrier capacitance does matter**:
charge injected at the partner leg's edge costs about 6–25 mV per pF on a high-side bank, against a 78.6 mV margin.
ALT-BIAS derived a requirement of "barrier capacitance ≤ ≈ 4 pF *maximum*", and "typ" doesn't meet it.

The requirements for any replacement, all from the ledger or ALT-BIAS:
- 21–27 V input;
- 17 V into the existing split, or a circuit change;
- ≥ 1.4 W output at the 80 kHz allocation;
- functional barrier 520 Vpk (≤ 50 % of the rating);
- CMTI ≥ 68.16 V/ns at maximum Qrr (absolute), ideally ≥ 1.5×;
- coupling ≤ about 4 pF maximum;
- Tj or ambient rating covering the B3 release case (U42 Tj 133.2 °C body model).

| Candidate | Form | Datasheet facts (read 2026-10-18) | Fails | Stock |
|---|---|---|---|---|
| RECOM R24C2T25/R-R (fitted) | SSOP-36 | "Less than 3.5pF isolation capacitance"; 150 kV/µs CMTI; 1.4 kVp repetitive; MSL 3; -R reel of 750 or -CT 10-pcs moisture barrier bag (Rev 1-2024 pp.1, 8, 16, sha 2e8133d2) | — | Mouser 1,006 |
| Murata MGJ2D242005SC (ALT-BIAS rank 2, "A3") | SIP-7 THT | 24 V rows list "4" pF isolation capacitance with no maximum (ALT-BIAS read the same as "4 pF typ" from KDC_MGJ2_U01); "Characterised CMTI >200kV/µS"; spec −40…100 °C; outputs +15/−5, +17/−9, +18/−2.5, +20/−5 only, no 17 V single (KDC_MGJ2_I01, Farnell copy) | coupling has no maximum, and ALT-BIAS puts 4 pF typ at 24–101 mV of the 78.6 mV margin; needs the HS TPS7A47 LDO back (removed at stage 14); layout stage | Newark 107, DigiKey 48 (genuine Murata) |
| RECOM R24P21503D / R24P22005D | SIP-7 THT | "Isolation Capacitance 1.5pF min. / 10pF max."; "Qualified with 65kV/µs"; working voltage "250VACrms", "basic" (RxxP2xx datasheet) | CMTI 65 < 68.16 V/ns; 10 pF max; 250 Vrms (354 Vpk) < 520 Vpk barrier | Sager 1,184 / Arrow 623 |
| JLC-stocked "MGJ2D24…", "R24P2…", "QA0x / QA151…" | SIP | sold under YLPTEC / EVISUN with the Murata / RECOM / Mornsun numbers | not the maker's part, no traceable approval or coupling data | excluded |
| TI UCC14240QDWNRQ1 (in-stock pin-compatible) | SSOP-36 (SMD) | basic isolation, VDD–VEE 18–25 V (ALT-BIAS) | not THT; can't make 17 V (FB change and split re-validation); JLC 33 < 40 | Mouser 3,056 |
| THT adapter carrying the RECOM | daughterboard | — | still needs JLC to source and place the same SSOP-36, then adds pins, loop inductance, creepage and a layout stage | — |

**Decision:** JLC places U41 / U42 from Global Sourcing (Mouser). If JLC's review refuses the module, consign Mouser cut tape
or -CT bags to JLC (C9900245652 is a JLC number, so it can be consigned) and pay the MSL 3 bake. Hand-soldering it with an
iron or hot air is not on the plan: flux under a 0.20 mm-gap barrier part is a poor bet, and JLC can do it.
**Reverses if:** JLC refuses the RECOM both as Global Sourcing and as consignment. In that case the fallback is ALT-BIAS A3
(MGJ2D242005SC + TPS7A47) as its own stage, re-running the F6 edge campaign with the 4 pF coupling. It is THT, but it is a
circuit change.

## Recommended package

**(a) BOM-only swaps for the next stage**
1. **J3 / J11 → JST B2P3-VH-H(LF)(SN), LCSC C160900** (grey, colour only). Re-key the ledger entry; ratings unchanged.
   Reverses if: the natural part is back at ≥ 80 at JLC when the order is placed (either part is fine), or the certifier
   wants the natural colour named.
2. Nothing else. C1 / C2 stay KEMET (the TDK B32923C3105M189 fallback in row 8 costs real tolerance margin). Every other
   consigned part is a process change, not a part change.

**(b) Process changes for the order** (owner actions; ordering is the owner's)
1. **Global Sourcing**, before the PCBA order: U41/U42 (Mouser; reject the C22466894 auto-match), the bank (Mouser),
   C5/C6 (DigiKey), L1 (Mouser), D3/D17 (DigiKey Good-Ark), F2, J2/J5, J6 if offered. Buy attrition spares (+1–2 per
   line). Budget the $20 inspection fees (F2, J2/J5, J6), up to 30 % duty on the RECOM, and 9–20 business days.
2. **Consign the FET lot:** buy 120 from DigiKey and ship 84 to JLC in one parcel with any other consigned parts. All 80
   placements are consigned (mixing rule). The other 36 stay home.
3. **Pre-order (reserve) thin JLC lines** on the order day: C1/C2 C3299886 (46 against 40), T1 C50132500 (64), U5
   C2156518 (50).
4. **Order remarks:**
   - "Hand-solder THT power pins with bottom preheat; solid connections in 2 oz / 2 oz copper";
   - "Trim all THT leads to ≤ 2.5 mm below the board";
   - "Bank: fit the 22.5 mm holes; leave the five x 190.5 holes open";
   - "Do not fit BR1, RV1, J6 (if not sourced)".
5. **First article:** barrel fill and top fillet on the Q, bank, L1, C5/C6, J1 joints; the D3/D17 lead bend. Then the
   existing first-article list (FAB-NOTE).
6. **Fix the records the integration session owns:** FAB-NOTE's hand-solder sentence (J1 and the film caps are JLC lines),
   T1 in the pre-order list, PROTOTYPE-LOT's "8 consigned" count and its U41/U42 hot-air plan.

**(c) Layout-change candidates worth a stage**
1. **F1 clips as their own BOM components** (two clip footprints with today's slot pads, F1 left as the cartridge). JLC C223911
   holds 101 against 80. It takes the last heavy-copper solder joints off the owner's bench. The copper must come out
   byte-identical (DRC / chain parity), and only the BOM and CPL change.
   Reverses if: JLC's preview can't take a slot-pad clip as a manualWeld part.
2. No layout change for U41/U42 (see above). No other line needs copper.

**(d) Parts that stay consigned or owner-fitted, and why**
- **Q2–Q6:** consigned for lot traceability (D-8). JLC can't guarantee a batch.
- **BR1:** owner. Fitting it is the heatsink step, and the bench-bus build runs with BR1 absent (ASSEMBLY.md).
- **RV1:** owner. Its formed lead (F4) and the 2026-10-17 decision stand. Reverses if JLC accepts the forming remark.
- **F1 cartridge:** owner, inserted after cleaning, no solder.
- **F1 clips:** owner until (c).
- **J6:** owner only if Global Sourcing has no supplier.
- **Controller R39:** consign if a 0.05 % / 5 ppm source appears; otherwise DNP and hand-fit later (0805, iron).

**(e) The owner's hand-solder list after this package (power board)**

| Part | Joints | Tool |
|---|---|---|
| BR1 GBJ2510-F (when a board goes to mains with its heatsink) | 4 THT | iron + bottom preheat ≥ 100 °C (solid power pins) |
| RV1 TMOV20RP175E (lead 2 formed in line) | 2 THT | iron |
| F1 clips 2 × 01250003H (until (c)) | 4 slot joints | iron + preheat |
| J6 1704004 (only if not sourced) | 2 THT | iron |
| Not soldering: F1 cartridge insert, lead-trim inspection | — | hand tools |

That is down from 29 placements, including two hot-air SSOP-36s, to 4–5 THT placements. The before count is FAB-NOTE's
list: Q×4, BR1, C1/C2, C5/C6, C38–C41, the bank ×5, L1, J1, J3/J11, the clips ×2, RV1, D3/D17, U41/U42.

## Open questions for the owner
1. **Preheater:** is a bottom preheater acceptable as "through-hole gear"? BR1 and the clips need one under FAB-NOTE's own
   rule. Without one, BR1 can go on JLC's list for boards that run on mains, as a second PCBA order with BR1 fitted.
2. **JLC's review** of Global Sourcing for the large THT parts (bank 14.5 × 29.5 × 26.5 mm, C5/C6, L1): JLC's terms let it
   cancel a part that "doesn't support assembly". It is visible only in the logged-in Parts Manager. If refused, the
   fallback is consignment, which needs engineer approval for the bank (it has no JLC number).
3. **Heavy-copper THT quality at JLC:** nothing JLC publishes covers preheat for solid pins. The first article decides.
4. **D-8 lot rule:** confirm that consigning one DigiKey lot meets it (it is the PROTOTYPE-LOT plan).

## Re-run and evidence
- `python3 -I scripts/consign_table.py` → `results/consign-table.csv` (offline, from the cached reads).
- Online refetch (JLC API, datasheets, Octopart): `scripts/jlc_fetch.py`, `scripts/fetch_ds.py`, `scripts/octopart_fetch.sh`
  then `scripts/octopart_parse.py reads/octopart reads/octopart-2026-10-18.json`; `scripts/html_text.py` for the JLC pages.
- Not committed (size): raw HTML and PDFs. Their sha256s are in `reads/*/_fetch.log`; text extracts are committed.
- Datasheets read: TDK B3292xC/D (June 2023), JST eVH, RECOM R24C2T25/R Rev 1-2024, RECOM RxxP2xx, Murata
  KDC_MGJ2_I01. murata.com returned HTTP 500 for its own copy, so the Farnell-hosted copy was read.

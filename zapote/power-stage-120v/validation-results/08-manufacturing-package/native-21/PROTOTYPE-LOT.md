# Native-21 prototype lot: order plan (prepared, NOT ordered)

Re-pointed to stage 56 on 2026-11-24 (board `27f20b786d52aea937f52bfbeb0af43e93ee06f0ff08572fd50ef835b26f8263`, copper key `cf4d7c896672`; DECISIONS 85, 86). `owner-items/order/scripts/check_order_docs.py` fails if this file, the order package or the CPL checklist drifts from the board of record: run it before ordering. Sources, one per block:

| Block | Committed source |
| --- | --- |
| Board, fab, via covering, laminate, finish | `fab/FAB-NOTE.md`, `../../../native-21/stackup.json`, DECISIONS 40, 41, 44 |
| BOM and CPL | `fab/bom-jlcpcb.csv` (95 lines), **`fab/cpl-jlcpcb-order.csv`** (374 rows, the file to upload to JLC: rotation-corrected and Y-negated), `fab/cpl-jlcpcb.csv` (the uncorrected positive-Y source), `cpl-rotation-audit/audit.csv` |
| Stock at 20 boards | `owner-items/order/proto-stock-s56-20boards.csv`, from `owner-items/order/scripts/proto_stock.py` (asserts agreement with the scorecard's `bom_lines_short_proto`); dated reads `sourcing/STOCK-2026-10-18-consign-r1.csv` (the consign-r1 lines), `STOCK-2026-10-16.csv`, `STOCK-2026-10-16-bank-s52.csv` over `SNAPSHOT-2026-10-15.csv` |
| Assembly routes | consign-r1 package, owner 2026-10-18 (`../../11-candidates/consign-r1/README.md`, `../../11-candidates/consign-r1/DECISIONS-DRAFT.md`); written into the BOM by `scripts/apply_lcsc.py` (ORDER_PLAN, ORDER_VARIANT) |
| Bank, L1, Y caps, EMI, 24 A ceiling | DECISIONS 74; `../../11-candidates/s52-proto-bom/README.md` |
| Scorecard | `../../10-benchmark/scorecard-native21s56.json` |
| Owner decisions | OWNER 2026-10-16: lot of 10–20 boards, stock gate sized at 20; prototype bank B32643H8104J000; certifier-driven provisions go in s53 (`S53-SCOPE.md`) |
| Bench plan | `../../../COMMISSIONING.md`, D-8, `native-21/BRINGUP-PROBES.md`, `owner-items/CERTIFIER-CHECKLIST.md`, OPEN-ITEMS S1, S6, S14, S15 |

A first build to answer the bench questions simulation cannot (the list is under "Bench plan"). **Ordering is a purchase
and needs the owner's approval.** Supplier and lab outreach is the owner's job. This file is the ready-to-place plan; nothing
is carted or ordered. `owner-items/order/ORDER-PACKAGE.md` holds the supporting files.

## What to order

| Item | Choice | Source |
| --- | --- | --- |
| Bare PCBs | **10 to 20** from `fab/native-21-gerbers.zip` (SHA-256 `81b391a921e510b83a088885419fdba3e6b9004a2309e6002de7b693c75de86d`); the stock gate is sized at 20 | owner decision 2026-10-16; FAB-NOTE |
| Size / layers | 290 × 190 mm L outline, **4 layers** (six layers was accepted on the data and not adopted on price, DECISIONS 40) | FAB-NOTE; DECISIONS 40 |
| Stack-up | JLCPCB **JLC041622-7628**, 1.6 mm nominal; no thickness remark (DECISIONS 44) | FAB-NOTE; `stackup.json` |
| Copper | **2 oz outer and 2 oz inner** | FAB-NOTE |
| Laminate | Material Type **"KB6164 - TG135"** (Kingboard KB-6164, CTI PLC 3 = group IIIa); never the unnamed "FR4 TG135". Remark: "Material KB-6164 core with KB-6064 prepreg throughout; please state the laminate on the shipment documents" | FAB-NOTE; DECISIONS 41; B4 |
| Laminate open point | S12: KB-6164 (35 µm) and KB-6165 (54 µm) UL rows do not cover 61 µm (2 oz) inner copper; KB-6164F / 6165F / 6167F list 102 µm. The answer may change the material and the remark above | OPEN-ITEMS S12 |
| Finish / mask | **ENIG**, green mask, white silk, no impedance control, order number removed, Confirm production file | FAB-NOTE |
| Via covering | **Epoxy-filled and capped (POFV) for every 0.3 mm via, no exceptions**; the ten 1.6/0.8 mm current vias stay tented | FAB-NOTE |
| Stencil | J2 / J5 want 150 µm paste; fine-pitch stencil not chosen (B6, decide at order) | OPEN-ITEMS B6 |
| Quoted bare board | $17.28 per board at 500 (4 L, JLC041622-7628 pinned); no prototype-quantity figure on record for the s52 spec | DECISIONS 40 |
| SMT assembly | From `fab/bom-jlcpcb.csv` + `fab/cpl-jlcpcb-order.csv` (upload this one: `fab/cpl-jlcpcb.csv` previews mirrored off the board in JLC's viewer): **95 BOM lines, 374 CPL rows.** **91 lines are assembled by JLC** (18 Basic, 73 Extended), every fitted THT part included; **4 are left to the owner**: Q2 / Q3 / Q5 / Q6 (Do Not Place, DECISIONS 86), BR1 and RV1 (Do Not Place at JLC) and the F1 cartridge, plus the F1 clips (`fab/hand-assembly-extras.csv`). Nothing is consigned; the 91 come from JLC stock, JLC pre-order or JLC Global Sourcing (below). How many boards JLC assembles is the owner's choice inside the lot; the stock bound is 20 | BOM Assembly column |
| CPL | OK 296 / CORRECTED 33 / NEEDS-PREVIEW **31** / excluded 14 (Q2 / Q3 / Q5 / Q6, BR1, RV1, F1, and the bank and D3 / D17, which carry no LCSC number). Confirm the 31 in JLC's preview, and place the bank and D3 / D17 by hand in it, with `owner-items/order/CPL-PREVIEW-CHECKLIST.md` before confirming the order | `cpl-rotation-audit/audit.csv` |
| Order remarks | "Q2, Q3, Q5, Q6 (TO-247) and BR1 are Do Not Place: leave their holes open and unsoldered. Trim every through-hole lead to 2.5 mm or less below the board bottom after soldering. The bank C21–C23/C151/C152 goes in the 22.5 mm holes (pad 2 at x 185.5); leave the five x 190.5 holes open and unsoldered. Leave RV1 and the F1 clips unfitted. Tick H on the bank-fit silk mark." | FAB-NOTE, Assembly |

**Assembly routes (consign-r1 package, accepted by the owner 2026-10-18: "JLC does as much as possible; through-hole hand work is fine when it can't be avoided").**
- **JLC Global Sourcing** (JLC buys from the named distributor; each part must be in JLC's warehouse before the PCBA order; no batch
  promise, and JLC can cancel a part it can't assemble): U41 / U42 RECOM R24C2T25/R-R (C9900245652; **reject the auto-match
  C22466894**, a different non-/R product; MSL 3, have JLC bake it), the bank **TDK B32643H8104J000** (no public LCSC number:
  select the private-library stock at the BOM step), C5 / C6, L1, D3 / D17 (**Good-Ark** 30KPA150CA; not JLC's Littelfuse-branded
  C19111562), F2, J2 / J5, and J6 if JLC lists a supplier (else J6 is Do Not Place and the owner fits it).
- **Do Not Place, kept by the owner (DECISIONS 86):** Q2 / Q3 / Q5 / Q6 IPW65R018CFD7, the single 120-piece DigiKey lot (D-8 lot
  traceability): 80 for the boards, 40 for D-8 and rework. None go to JLC.
- **Reserved by JLC pre-order** (JLC's own stock; no custom lot numbers): C1 / C2, T1, U5.
- **Order-file variant:** J3 / J11 are ordered as the grey JST **B2P3-VH-H(LF)(SN)**, C160900 (JLC 5,610), the same header in a
  grey housing; the frozen netlist keeps B2P3-VH(LF)(SN).
- **JLC hand-solders** every fitted THT part, J1 and the film caps C38–C41 included. The bank goes in the 22.5 mm holes (pad 2 at
  x 185.5); the x 190.5 holes stay open. Tick **H** on the silk fit mark. All THT leads are trimmed to ≤ 2.5 mm below the board.

**Owner hand assembly (through-hole only; the owner's bench has no SMD gear, and none is needed now: U41 / U42 are JLC's).**
On a board preheated from below to ≥ 100 °C (heavy copper):
- **Q2 / Q3 / Q5 / Q6 (DECISIONS 86), Do Not Place at JLC:** soldered with all four tabs clamped on the M11 seating fixture (coplanar
  within 0.05 mm). The fixture is not designed yet (OPEN-ITEMS S32).
- **BR1 (GBJ2510-F), Do Not Place at JLC; the owner fits it before mains.** It is the only mains-to-bus path. With it out, PS2 runs
  from mains while the bus is fed from a bench DC supply, so nothing back-feeds PS2's output (bring-up with BR1 not fitted:
  `firmware/components/power/COMMISSIONING.md`, commission-s53).
- **RV1 (TMOV20RP175E), Do Not Place at JLC** (decision 2026-10-17, from the JLC viewer check). JLC's part page for C1527834 lists it
  as wave-soldered and its EasyEDA package has an 8.5 mm lead pitch with a 21 x 9 mm body; our footprint (Littelfuse TMOV/iTMOV
  datasheet rev GD, FOOTPRINTS.md F4) is 7.5 mm pitch, and the bulk leads are offset (e1 1.5-4.0 mm) and must be formed. Buy the
  datasheet part (Newark 1,200 on 2026-10-18), form lead 2 into line and fit it by hand. The BOM line has no LCSC number, so
  JLC cannot match it.
- **F1** with its two 01250003H clips (`fab/hand-assembly-extras.csv`; C223911): solder the clips, insert the cartridge after
  cleaning. Splitting the clips into BOM components so JLC solders them (consign-r1 candidate (c)) is deferred: the owner needs a
  bottom preheater for BR1 anyway.
- **J6**, only if JLC Global Sourcing offers no supplier.

Cost reference: `parts_usd_at_500_v2` is 175.47 per board on s56 (174.99 on the s53 order BOM; 175.04 on the s52 BOM before the J3 / J11 variant;
s51: 169.77; DECISIONS 74: bank $6.83 against $1.52, L1 −$0.67, Y caps +$0.64, +$5.27 per board at 500). No prototype-lot parts
total is claimed here, and Global Sourcing prices are only known at order; re-price at order.

## Parts to buy before ordering

Basis: `owner-items/order/proto-stock-s56-20boards.csv` (no new stock read: s56's dates are below): every fitted line against qty_per_board × 20 boards, on the scorecard's
stock-gate rules (buildable = the larger of JLC library stock and one authorised distributor, never a sum; brokers count 0).
**Short lines at 20 boards: 0.** Dated reads are 2026-10-18 for the consign-r1 lines (`sourcing/STOCK-2026-10-18-consign-r1.csv`:
JLC part API plus Octopart's public distributor pages; F2's DigiKey figure is a browser read of DigiKey's product page), 2026-10-16
for C3 / C4 and D6–D9; every other line is the 2026-10-15 snapshot. **Re-check stock at order**; a distributor read is not a
reservation, and a Global Sourcing line is only secured once the part is in JLC's warehouse.

| Line | Part | Need (20 boards) | JLC | Buildable source (read 2026-10-18 unless noted) | Plan |
| --- | --- | ---: | ---: | --- | --- |
| C21–C23, C151, C152 | **B32643H8104J000** (TDK) | 100 | 0 | Mouser 1,736 / DigiKey 306 | **JLC Global Sourcing**, JLC hand-solders (22.5 mm holes, x 190.5 open, tick H). Record the fitted part per board |
| L1 | **B82726S2243A020** | 20 | 0 (C7084710) | Mouser 62 / DigiKey 29 | **JLC Global Sourcing**, JLC hand-solders. Production part stays B82726S2203A020 (owner pre-order, 29 weeks) |
| U41, U42 | R24C2T25/R-R (RECOM) | 40 | 0 (C9900245652) | Mouser 1,006 | **JLC Global Sourcing**; reject C22466894; MSL 3 bake. No hot-air gear needed |
| C5, C6 | B32676G1905K000 | 40 | 0 (C3802167) | DigiKey 547 | **JLC Global Sourcing**, JLC hand-solders |
| D3, D17 | 30KPA150CA (**Good-Ark**) | 40 | 0 | DigiKey 164 (1,750 on reel, MOQ 250) | **JLC Global Sourcing** of the Good-Ark part (not C19111562, Littelfuse-branded); JLC hand-solders |
| F2 | 3403.0279.23 | 20 | 0 (C3163739) | DigiKey 7,183 (browser read) | **JLC Global Sourcing**; JLC places |
| J2, J5 | 7466004R | 40 | 0 (C6708126) | DigiKey 8,856 | **JLC Global Sourcing**; JLC places (THR, paste in hole) |
| J6 | 1704004 | 20 | 0 (C5481600) | Amar Radio 48 (Octopart; MOQ not shown) | **JLC Global Sourcing if offered**; else Do Not Place and the owner hand-solders |
| Q2, Q3, Q5, Q6 | IPW65R018CFD7 | 80 | 6 | DigiKey 459 (2026-10-17) / Mouser 470 | **Buy 120 from DigiKey in one recorded lot; none to JLC** (DNP, DECISIONS 86); the owner solders them on the M11 seating fixture. Pricing below |
| C1, C2 | R463N410050N1K | 40 | 46 (C3299886) | Newark 1,298 | **JLC pre-order reserve**; JLC hand-solders |
| T1 | CST3015-200ED | 20 | 64 (C50132500) | JLC (Coilcraft direct has no distributor listing) | **JLC pre-order reserve** |
| U5 | LM4050AEM3-2.5/NOPB | 20 | 50 (C2156518; 2026-10-15) | JLC | **JLC pre-order reserve**; 500 boards need the owner pre-order |
| J3, J11 | B2P3-VH-H(LF)(SN), ordered for B2P3-VH(LF)(SN) | 40 | 5,610 (C160900) | JLC | JLC hand-solders; mate VHR-3M. The natural part had 0 at JLC on 2026-10-18 |
| C3, C4 | **DE1E3RA222MJ4BH01F** (Y1 400 V) | 40 | 104 (C7170908; 2026-10-16) | JLC | JLC assembles |
| D6–D9 | PMEG6030EP,115 | 80 | 9,298 (2026-10-16) | JLC | JLC assembles |
| BR1 | GBJ2510-F | 20 | 1,579 | JLC (but DNP) | **Owner buys and fits before mains** (DNP at JLC) |
| RV1 | TMOV20RP175E | 20 | 114 (C1527834, not the drawing) | Newark 1,200 | **Owner buys and hand-solders** (DNP at JLC) |
| F1 | KLDR025.TXP + 2 × 01250003H | 20 | 0 | Future Electronics 300 (MOQ 10) | **Owner buys**; solders the clips, inserts the cartridge |

**IPW65R018CFD7 purchase decision.** DigiKey 448-IPW65R018CFD7XKSA1 (IPW65R018CFD7XKSA1), read live 2026-10-17: in stock 459,
standard lead 8 weeks, tube of 30. USD ladder: 1 $19.72, 30 $12.30267, 60 $11.42050, 120 $10.67925, 510 $10.17612 (tariff may
apply when shipping to the US; shipping not priced). JLC's own BOM-review page the same day priced the same line at $412.864 for
20 parts (about $20.64 each) with 6 in JLC stock and 14 short, for 5 boards.

- The lot needs 80 (4 per board x 20 boards). 80 at the 60-break is $11.4205 each = $913.64. Buying 120 costs $1,281.51, so the
  extra 40 cost $367.87 ($9.20 each, below the 80-part price). Recommended: the MOSFETs are the parts most likely to be destroyed
  in bring-up and the D-8 double-pulse bench, and the lot guidance asks for one recorded lot (D-8 lot traceability).
- All 120 stay with the owner (DECISIONS 86, replacing the 2026-10-18 consignment of 84): 80 for the boards, 40 for D-8 and rework.
- The saving against JLC's $20.64 is about $37 per board at 80 parts (4 x ($20.64 - $11.42)).

Every other line is covered by JLC stock at 20 boards (CSV). **Fixings:** M3 nylon (UL94 V-0) screws, washers and standoffs for
H2–H7 (R43 numbering; the board uses H1 and H3–H8 and H2, H9, H10 stay empty, DECISIONS 76), the whole chain insulating (BRINGUP-PROBES.md, FAB-NOTE); one metal M3 for H1 (chassis / PE).

## Bank variant and commissioning rule

(DECISIONS 74, OPEN-ITEMS S28, COMMISSIONING.md.)
- **Record the fitted bank part on every board.**
- **A board marked H, or with no mark, is never commissioned above 24 A** (strict ladder: vendor ratio 0.844 at 24 A, 0.85 at 24.17 A).
- A **B** board (B32643B8104J000, 28 A, same holes) has its 26 / 28 A steps **bench-gated per step**; the mark raises nothing.
- A KNSCHA board (the 27.5 mm hole) stops at **22 A**.
- The S25 pre-lot gate on C22, the hottest interior B32643H, can send the lot back to KNSCHA (DECISIONS 74, "Reverses if").

## EMI: inlet module requirement

L1 2243's 8 µH stray loses the board DM pole. With today's 2 × 41 µH inlet module the margins are 6.03 / 1.57 dB: INCONCLUSIVE.
With **≥ 100 µH DM per line at 21 A** they are 11.14 / 6.95 dB (PASS). **Ask the module supplier for it** (MODULE-REQUEST.md
item 3; no part is selected yet). If the prototype module cannot carry it, the lot runs as a recorded EMI deviation and bench
pre-compliance decides; fitting the 2203 (12.37 dB) is the fallback.

## Gates before placing the order

1. Independent design review (`REVIEW-TRIAGE.md`): every BLOCKER / MAJOR closed. Statuses re-read 2026-10-17: B1, B2 and
   M1-M14 are fixed, covered or owner decisions; M11 (stack count) and M13 (this buy plan) are the open owner decisions. M2's F6
   evidence was refreshed on the s51 matrices (252/252 on both legs). Not an independent re-review.
2. **Enclosure bosses: closed by decision (DECISIONS 76).** The board has 10 mounting holes; R43 supports seven (H1, H3–H8, 0.00 mm
   offset, `c53-astra-results/local/bosses/`). H2, H9 and H10 stay empty: no hardware, no board change.
3. JLC's laminate answer (S12, asked 2026-11-24), then fix the order remark and `stackup.json` together.
4. FAB-NOTE's pre-order tier: F6 and S3 re-run on the native-21 FEM corrections (done, DECISIONS 77), M11
   heatsink stack parts sourced, and the parts above secured: every **Global Sourcing** line in JLC's parts warehouse, and the **C1 / C2, T1, U5 pre-orders** placed, all before the PCBA order (JLC needs the
   parts in its warehouse first). Global Sourcing can cancel a part it judges unassemblable: re-plan that line (consign it, or
   leave it Do Not Place for the owner) rather than order without it.
4a. **Owner bench:** a bottom preheater (≥ 100 °C) for the FETs, BR1, RV1 and the F1 clips, and the M11 seating fixture (OPEN-ITEMS S32).
5. **Module:** the inlet module with ≥ 100 µH DM per line, or the EMI deviation accepted in writing.
6. **CPL:** the 31 NEEDS-PREVIEW parts confirmed in JLC's preview, and the bank and D3 / D17 placed in it (`CPL-PREVIEW-CHECKLIST.md`).
7. **Bank stock re-read** (≥ 100 at one distributor before the Global Sourcing request, else KNSCHA). **S25 timing changes with
   consign-r1 (open for the integration session):** DECISIONS 76 made the S25 test on C22 a pre-build gate because the bank was
   consigned and outside the JLC order. With JLC now buying and soldering the bank, the bank is part of the PCBA order. Draft
   handling (`../../11-candidates/consign-r1/DECISIONS-DRAFT.md` D9): run S25 on the first JLC-built board before the rest of the lot
   is powered; if it fails, the owner reworks the lot to KNSCHA in the x 190.5 holes, which stay open for that reason (through-hole,
   preheated board). The alternative is to order the bank line Do Not Place and fit it after S25 (`c53-astra-results/bank-s25/`
   protocol).
8. **Controller side: not an order gate (DECISIONS 76); it gates powering the board together with the controller.** The J13 merge and
   the J4.1 drop (`c23-supply-topology/CONTROLLER-REQUEST.md`) landed on controller branch `controller-j13-merge` (C49, DECISIONS 79, 2026-10-18); they are not on any other controller branch. A stage-38+ board does not
   power that controller (benign), so bring-up runs the power board on bench supplies with no controller until they land.
9. Firmware: the controller image must ship the **17.5 A tank ceiling** (DECISIONS 61, which supersedes 56's 18 A; `TEMPER_POWER_TANK_CEILING_DA=175`, the Kconfig default, verified 2026-10-17) and the RMS-increment aux allowance
   (B11). The ladder above 17.5 A follows COMMISSIONING.md and the bank-variant rule above.
10. **Bench equipment and the plan for first power** (`BRING-UP.md`): isolation transformer, Variac, dim-bulb tester, differential probe, TC2050 cable. The coil is
    measured (L, Q, DCR) before it is used. Without the isolation chain the board is not powered from mains.
11. Owner approval of the spend.

Insulation qualification (PD3, IEC 60664-4, hipot) does **not** gate a bench prototype run on a current-limited, isolated
supply. It gates any mains-connected or unattended operation (FAB-NOTE).

## Bench plan (what the lot is for)

**A bench unit always runs behind an external, hand-operable series mains cut. Nothing on the board opens mains.**

Bring-up (full procedures in D-8 and `native-21/BRINGUP-PROBES.md`):

1. Bare board: continuity and isolation spot checks across the barrier (megger at a low voltage), no copper shorts on the
   rails.
2. Logic and bias only (no bus): SELV 15 V / 3.3 V, then the bias supplies. Check +15 / −2 V on every domain at the TP pairs;
   BIAS_BAD and DIS behaviour; the monitor windows (−2.206 / −1.799 V).
3. Gate drive with no bus: PWM in, driver outputs at the TP pairs; dead time (R9 / R17 49.9 kΩ).
4. Bus from a current-limited isolated supply, rising in steps: Vgs ringing on all four FETs at the leads (D4 condition 3),
   `ocp_node` during hard switching (D4 condition 2), the S4 commutation shot (D-24).
5. Resonant operation at reduced power, then nominal, with IR thermal (task 04). The **17.5 A tank ceiling applies from the
   first powered test**; raising it follows COMMISSIONING's ladder (gate 0: a passing B3 basis at the new ceiling plus the
   bench R_on reading) and the bank-variant rule.

**S6 (CMTI, closed with no layout change; the bench confirms it):**
- D-8 double pulse with max-Qrr parts: SW_A ≤ 100 V/ns (predicted 68.2 V/ns chord, about 91 V/ns peak).
- HV_RET–SELV_GND dv/dt ≤ 66.7 V/ns on the full assembly.
- Glitch capture through a 370–740-edge S4 burst on U43 / U44 OUTB, U32 HB_RX and U9 BUS_FAULT_FLT.
- U36 EFT / surge.

**Stuck-on injection (S15):** jumper DIS off, run to the ceiling, and time the TCO opening. This also sets S15's trip temperature.

**First-article and ratings:**
- Touch current at first article (S1 design value 0.2412 mA, margin 8.8 µA).
- C3 / C4 surface temperature on the B3 run.
- F1 clip temperature at 15 / 16 A.

Measurements the lot must deliver (OPEN-ITEMS §5 items 8–9, B8, B10, B11, S2, S8, S14):

- **First:** the gate-row IR reading (the R_on 0.217 W bound behind the +0.7 K release margin); D-8 double pulse for max Qrr
  (S14); BENCH-RMS for the aux allowance (`output/temper-aux-load-r1/BENCH-RMS.md`, B11); B10's UL 858 cases (59.6 iron bar,
  fork / spoon / knife on pan detection, 47.8 off within 30 s of vessel removal, the bad-pan set); the end-of-line veto test
  (force MON_GOOD_HA low, then MON_GOOD_HB low; BIAS_GOOD must drop within its hold time, B8).
- **Then:** coil / pan L / R with real pans; the bank hot spot (record H / B per board); C5 case temperature (S8); terminal
  pull, torque and temperature; module temperatures; bay air and board copper at R5 in an enclosure soak (S2); the jet-h
  measurement if the R45 enclosure with the push-hood jets is built (change set:
  `git show sensor-c1-impulse-mining:output/temper-airflow-r1/HANDOFF.md`, temper-8d airflow-r1; no ceiling raise until the
  jet h is measured, S2).

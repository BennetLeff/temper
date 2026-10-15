# Native-21 prototype lot: order plan (prepared, NOT ordered)

Regenerated for s43 (board 61447816) on 2026-10-15 from `fab/FAB-NOTE.md`, `../../../FAB-JLCPCB.md`,
`../../../native-21/stackup.json`, `fab/bom-jlcpcb.csv` + `fab/cpl-jlcpcb.csv` (s43),
`sourcing/SNAPSHOT-2026-10-15.csv` + `sourcing/study-2026-10-15/README.md` §4, and
`../../../OPEN-ITEMS.md` (B1, B2, B4, B6–B11, S2, S3, S8, S12, §5). DECISIONS 40, 41, 44, 54–57 are the decision basis.

A first build to answer the bench questions simulation cannot (the list is under "Bench plan"). **Ordering is a purchase
and needs the owner's approval.** This file is the ready-to-place plan; nothing is carted or ordered.

## What to order

| Item | Choice | Source |
| --- | --- | --- |
| Bare PCBs | **5** from `fab/native-21-gerbers.zip`: 2 assembled, 1 rework or partial bring-up, 2 spare | this plan |
| Size / layers | 290 × 190 mm L outline, **4 layers** (six layers was accepted on the data and not adopted on price, DECISIONS 40) | FAB-NOTE; DECISIONS 40 |
| Stack-up | JLCPCB **JLC041622-7628**, 1.6 mm nominal; no thickness remark (DECISIONS 44) | FAB-NOTE; `stackup.json` |
| Copper | **2 oz outer and 2 oz inner** | FAB-NOTE |
| Laminate | Material Type **"KB6164 - TG135"** (Kingboard KB-6164, CTI PLC 3 = group IIIa); never the unnamed "FR4 TG135". Remark: "Material KB-6164 core with KB-6064 prepreg throughout; please state the laminate on the shipment documents" | FAB-NOTE; DECISIONS 41; B4 |
| Laminate open point | S12: KB-6164 (35 µm) and KB-6165 (54 µm) UL rows do not cover 61 µm (2 oz) inner copper; KB-6164F / 6165F / 6167F list 102 µm. The answer may change the material and the remark above | OPEN-ITEMS S12 |
| Finish / mask | **ENIG**, green mask, white silk, no impedance control, order number removed, Confirm production file | FAB-NOTE; B4 |
| Via covering | **Epoxy-filled and capped (POFV) for every 0.3 mm via, no exceptions**; the ten 1.6/0.8 mm current vias stay tented | FAB-NOTE |
| Stencil | J2 / J5 want 150 µm paste; fine-pitch stencil not chosen (B6, decide at order) | OPEN-ITEMS B6 |
| Quoted bare board | $17.28 per board at 500 (4 L, JLC041622-7628 pinned); no 5-board figure on record for the s43 spec | DECISIONS 40 |
| SMT assembly | **2 boards**, from `fab/bom-jlcpcb.csv` + `fab/cpl-jlcpcb.csv`: 93 BOM lines, 351 CPL rows. 87 lines are marked JLC (19 Basic, 68 Extended); 6 are marked consign or hand-assemble. Check every CPL rotation in JLC's preview (R5 and J2 / J5 especially) | BOM Assembly column; FAB-NOTE |

Hand-solder in house (heavy copper wants a hot iron or selective solder; trim every THT lead to ≤ 2.5 mm below the board,
C1 / C2's 25 mm leads to 4 mm before insertion): TO-247s (Q2, Q3, Q5, Q6), BR1, the film caps, L1, J1, J3 / J11, F1 with its
two 01250003H clips (`fab/hand-assembly-extras.csv`; C223911), and any THT part JLC cannot place. Power pins stay solid; rework
them only on a board preheated to ≥ 100 °C. Source: FAB-NOTE, Assembly.

Cost reference: parts $186.54 per board at 500 on the 2026-10-15 snapshot (OPEN-ITEMS §3). No prototype-lot parts total is
claimed here; re-price at order.

## Parts to buy before ordering

Basis: `sourcing/SNAPSHOT-2026-10-15.csv` (JLC read 2026-10-15 ~06:40Z; distributor columns 2026-10-15 where read, else the
2026-10-13 survey, marked "survey"). Needs are for the 2-board build, with the 5-board need in brackets.
**Re-check at order** every line marked read gap (B2: DigiKey bot check, Octopart 403, not proven shortages).

| Line | Part | Need 2 [5] | JLC | Best source in the snapshot | Plan |
| --- | --- | ---: | ---: | --- | --- |
| L1 | B82726S2203A020 | 1 [1] | 0 | none authorised (DigiKey 0); **29 week lead, sets the build date** (B1) | Pre-order first (study §4). Alternate B82726S2243A020 needs the c29 / D-22 EMI re-run first |
| Q2, Q3, Q5, Q6 | IPW65R018CFD7 | 8 [20] | 4 | DigiKey 459 (survey), 8 week | Buy 10 or more from one recorded lot (D-8 asks for lot traceability) |
| D6–D9 | PMEG6030EP,115 | 8 [20] | 7 in snapshot; 3 per B9 | read gap | Add to the pre-order list or qualify an alternate (B9); JSMSEMI C53114006 is not qualified |
| C3, C4 | DE1E3RA222MA4BP01F | 4 [10] | 6 | read gap | Enough for 2 boards; buy all 6 now |
| C5, C6 | B32676G1905K000 | 4 [10] | 0 | DigiKey 547, 27 week; $8.02 each at 5 | Consign. Study alternate B32676G1106K ("Z 1" at DigiKey) once confirmed as the catalogue part (S8) |
| C1, C2 | R463N410050N1K | 4 [10] | 46 (library) | DigiKey 945, 24 week | Consign (BOM marks it so) |
| F1 | KLDR025.TXP | 2 [5] | 0 | Future 300 (692 across Future, Standard, Master, Sager); $34.45 each at 5 | Consign |
| F2 | 3403.0279.23 (Schurter UMT-H 1.5 kA) | 2 [5] | 0 | DigiKey 7,183 (survey), 18 week | Consign from Digi-Key (FAB-NOTE) |
| J2, J5 | 7466004R (WP-SMBU, SMT) | 4 [10] | 0 | DigiKey 8,856, 26 week | Distributor buy; JLC places it from consign |
| J6 | 1704004 | 2 [5] | 0 | Amar Radio 48, 7 week | Distributor buy |
| D3, D17 | 30KPA150CA (Good-Ark) | 4 [10] | 0 | DigiKey 1,750, MOQ 250 | Consign |
| U41, U42 | RECOM R24C2T25/R-R | 4 [10] | 0 | DigiKey 1,185 (survey) | Consign or hand-assemble (BOM marks it so) |
| J3, J11 | JST B2P3-VH(LF)(SN) | 4 [10] | 983 | DigiKey 42,437 (survey) | Hand-assemble (BOM marks it so); mate VHR-3M (F1-J3-PARTS.md) |
| C21–C23, C151, C152 | B32654A1104J000 | 10 [25] | 104 | DigiKey 881, 23 week | JLC stock covers the lot |

Other lines are covered by JLC stock for 5 boards in the snapshot. U1 / U2 are Infineon 2EDR8259XXUMA1 (C17455725), U9 / U32
CA-IS3720HW, U43 / U44 ISO6721FBDR, R5 Bourns CSS2H-2512R-1L00F (C4175647), T1 CST3015-200ED, U36 VOL628A-2X001T, J4
0430451612 (C491447), PS2 MPM-20-24; all are on JLC lines of the BOM. T1 has no distributor listing (Coilcraft direct, lead
unknown); JLC holds 64, enough for this lot. Pre-order the long-lead lines in the order given by `study-2026-10-15/README.md`
§4: L1 first, then PMEG6030EP (B9).

**Fixings:** M3 nylon (UL94 V-0) screws, washers and standoffs for H2–H7, the whole chain insulating (BRINGUP-PROBES.md,
FAB-NOTE); one metal M3 for H1 (chassis / PE).

## Gates before placing the order

1. Independent design review (`REVIEW-TRIAGE.md`): every BLOCKER / MAJOR closed. Re-confirm; this regeneration did not
   re-verify it.
2. Enclosure bosses agreed for H1–H8 against the enclosure revision used (D5-AUDIT.md), or the holes moved to match.
3. JLC's laminate answer (S12): which recognised construction covers 4 L, 2 oz inner, CTI ≥ 175 V. Then fix the order remark
   and `stackup.json` together (it still says Nan Ya NP-155F).
4. FAB-NOTE's pre-order tier: F6 re-run on the native-21 FEM corrections (S3 is blocked, the remote box is offline), M11
   heatsink stack parts sourced, and the no-stock parts above procured.
5. Controller side before any stage-38+ board is powered: the J13 merge and J4.1 dropped
   (`c23-supply-topology/CONTROLLER-REQUEST.md`; OPEN-ITEMS §5 item 3).
6. Firmware: the controller image must ship the **18 A tank ceiling** (DECISIONS 56; trips at 18 A: RMS 18.9, crest 27,
   peak 42.06 A) and the RMS-increment aux allowance (B11). Bring the board up on that firmware only.
7. Owner approval of the spend.

Insulation qualification (PD3, IEC 60664-4, hipot) does **not** gate a bench prototype run on a current-limited, isolated
supply. It gates any mains-connected or unattended operation (FAB-NOTE).

## Bench plan (what the lot is for)

Bring-up (full procedures in D-8 and `native-21/BRINGUP-PROBES.md`):

1. Bare board: continuity and isolation spot checks across the barrier (megger at a low voltage), no copper shorts on the
   rails.
2. Logic and bias only (no bus): SELV 15 V / 3.3 V, then the bias supplies. Check +15 / −2 V on every domain at the TP pairs;
   BIAS_BAD and DIS behaviour; the monitor windows (−2.206 / −1.799 V).
3. Gate drive with no bus: PWM in, driver outputs at the TP pairs; dead time (R9 / R17 49.9 kΩ).
4. Bus from a current-limited isolated supply, rising in steps: Vgs ringing on all four FETs at the leads (D4 condition 3),
   `ocp_node` during hard switching (D4 condition 2), the S4 commutation shot (D-24).
5. Resonant operation at reduced power, then nominal, with IR thermal (task 04). The **18 A tank ceiling applies from the
   first powered test**; raising it follows COMMISSIONING's ladder (gate 0: a passing B3 basis at the new ceiling plus the
   bench R_on reading).

Measurements the lot must deliver (OPEN-ITEMS §5 items 8–9, B8, B10, B11, S2, S8, S14):

- **First:** the gate-row IR reading (the R_on 0.217 W bound behind the +0.7 K release margin); D-8 double pulse for max Qrr
  (S14); BENCH-RMS for the aux allowance (`output/temper-aux-load-r1/BENCH-RMS.md`, B11); B10's UL 858 cases (59.6 iron bar,
  fork / spoon / knife on pan detection, 47.8 off within 30 s of vessel removal, the bad-pan set); the end-of-line veto test
  (force MON_GOOD_HA low, then MON_GOOD_HB low; BIAS_GOOD must drop within its hold time, B8).
- **Then:** coil / pan L / R with real pans; the bank hot spot; C5 case temperature (S8); terminal pull, torque and
  temperature; module temperatures; bay air and board copper at R5 in an enclosure soak (S2); the jet-h measurement if the
  R45 enclosure with the push-hood jets is built (no ceiling raise until it is measured, S2).

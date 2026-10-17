# Native-21 prototype lot: order plan (prepared, NOT ordered)

Regenerated for s52 on 2026-10-16 and re-pointed to s53 (integration board `82af7bd93e62…`, copper key `b7a0bc5790b9`; the s53 BOM is the s52 BOM). Sources, one per block:

| Block | Committed source |
| --- | --- |
| Board, fab, via covering, laminate, finish | `fab/FAB-NOTE.md` (s52), `../../../native-21/stackup.json`, DECISIONS 40, 41, 44 |
| BOM and CPL | `fab/bom-jlcpcb.csv` (95 lines), `fab/cpl-jlcpcb.csv` (372 rows), `cpl-rotation-audit/audit.csv` |
| Stock at 20 boards | `owner-items/order/proto-stock-s52-20boards.csv`, from `owner-items/order/scripts/proto_stock.py` (asserts agreement with the scorecard's `bom_lines_short_proto`); dated reads `sourcing/STOCK-2026-10-16.csv`, `STOCK-2026-10-16-bank-s52.csv` over `SNAPSHOT-2026-10-15.csv` |
| Bank, L1, Y caps, EMI, 24 A ceiling | DECISIONS 74; `../../11-candidates/s52-proto-bom/README.md` |
| Scorecard | `../../10-benchmark/scorecard-native21s53.json` |
| Owner decisions | OWNER 2026-10-16: lot of 10–20 boards, stock gate sized at 20; prototype bank B32643H8104J000; certifier-driven provisions go in s53 (`S53-SCOPE.md`) |
| Bench plan | `../../../COMMISSIONING.md`, D-8, `native-21/BRINGUP-PROBES.md`, `owner-items/CERTIFIER-CHECKLIST.md`, OPEN-ITEMS S1, S6, S14, S15 |

A first build to answer the bench questions simulation cannot (the list is under "Bench plan"). **Ordering is a purchase
and needs the owner's approval.** Supplier and lab outreach is the owner's job. This file is the ready-to-place plan; nothing
is carted or ordered. `owner-items/order/ORDER-PACKAGE.md` holds the supporting files.

## What to order

| Item | Choice | Source |
| --- | --- | --- |
| Bare PCBs | **10 to 20** from `fab/native-21-gerbers.zip` (SHA-256 `a6afd37a…ddc`); the stock gate is sized at 20 | owner decision 2026-10-16; FAB-NOTE |
| Size / layers | 290 × 190 mm L outline, **4 layers** (six layers was accepted on the data and not adopted on price, DECISIONS 40) | FAB-NOTE; DECISIONS 40 |
| Stack-up | JLCPCB **JLC041622-7628**, 1.6 mm nominal; no thickness remark (DECISIONS 44) | FAB-NOTE; `stackup.json` |
| Copper | **2 oz outer and 2 oz inner** | FAB-NOTE |
| Laminate | Material Type **"KB6164 - TG135"** (Kingboard KB-6164, CTI PLC 3 = group IIIa); never the unnamed "FR4 TG135". Remark: "Material KB-6164 core with KB-6064 prepreg throughout; please state the laminate on the shipment documents" | FAB-NOTE; DECISIONS 41; B4 |
| Laminate open point | S12: KB-6164 (35 µm) and KB-6165 (54 µm) UL rows do not cover 61 µm (2 oz) inner copper; KB-6164F / 6165F / 6167F list 102 µm. The answer may change the material and the remark above | OPEN-ITEMS S12 |
| Finish / mask | **ENIG**, green mask, white silk, no impedance control, order number removed, Confirm production file | FAB-NOTE |
| Via covering | **Epoxy-filled and capped (POFV) for every 0.3 mm via, no exceptions**; the ten 1.6/0.8 mm current vias stay tented | FAB-NOTE |
| Stencil | J2 / J5 want 150 µm paste; fine-pitch stencil not chosen (B6, decide at order) | OPEN-ITEMS B6 |
| Quoted bare board | $17.28 per board at 500 (4 L, JLC041622-7628 pinned); no prototype-quantity figure on record for the s52 spec | DECISIONS 40 |
| SMT assembly | From `fab/bom-jlcpcb.csv` + `fab/cpl-jlcpcb.csv`: **95 BOM lines, 372 CPL rows.** 87 lines are marked JLC (19 Basic, 68 Extended); **8 are consigned or hand-assembled**: F1, C1 / C2, **L1**, C5 / C6, **the bank C21–C23 / C151 / C152**, J3 / J11, D3 / D17, U41 / U42. How many boards JLC assembles is the owner's choice inside the lot; the stock bound is 20 | BOM Assembly column |
| CPL | OK 300 / CORRECTED 32 / NEEDS-PREVIEW **23** / excluded 17. Confirm the 23 in JLC's preview with `owner-items/order/CPL-PREVIEW-CHECKLIST.md` before confirming the order | `cpl-rotation-audit/audit.csv` |

**Consigned or hand-assembled in this lot.**
- **Bank C21–C23 / C151 / C152: TDK B32643H8104J000** (100 nF, 2000 V DC, P22.5), into the 22.5 mm holes (pad 2 at x 185.5).
  The x 190.5 holes stay open. It has no JLC or LCSC listing. Tick **H** on the silk fit mark. The bank leads protrude
  3.35–4.35 mm: trim to ≤ 2.5 mm below the board.
- **L1: TDK B82726S2243A020**, consigned / hand-assembled (JLC C7084710 holds 0 on 2026-10-16).

**Hand-assembly note (owner decision 2026-10-16).** The owner's bench has through-hole soldering gear only. Of the 17 consigned
designators, 15 are through-hole. The two SMD ones, **U41 / U42 (RECOM R24C2T25/R-R, SSOP-36, 0.65 mm pitch, ENIG pads)**, are
hand-soldered with **hot-air (or similar) rework gear that still has to be obtained** before the first board is built. Plan:
no JLC consignment request for them; check the 0.20 mm pad-to-pad gap (FAB-NOTE, first-article inspection) for bridges after
soldering; run the bias checks (bench plan step 2) before anything else is powered.

Hand-solder in house (heavy copper wants a hot iron or selective solder; trim every THT lead to ≤ 2.5 mm below the board,
C1 / C2's 25 mm leads to 4 mm before insertion): TO-247s (Q2, Q3, Q5, Q6), BR1, the film caps, the bank, L1, J1, J3 / J11, F1
with its two 01250003H clips (`fab/hand-assembly-extras.csv`; C223911), and any THT part JLC cannot place. Power pins stay
solid; rework them only on a board preheated to ≥ 100 °C. Source: FAB-NOTE, Assembly.

Cost reference: `parts_usd_at_500_v2` is 175.04 per board on the s52 BOM (s51: 169.77; DECISIONS 74: bank $6.83 against
$1.52, L1 −$0.67, Y caps +$0.64, +$5.27 per board at 500). No prototype-lot parts total is claimed here; re-price at order.

## Parts to buy before ordering

Basis: `owner-items/order/proto-stock-s52-20boards.csv`: every fitted line against qty_per_board × 20 boards, on the scorecard's
stock-gate rules (buildable = the larger of JLC library stock and one authorised distributor, never a sum; brokers count 0).
**Short lines at 20 boards: 0.** Dated reads are 2026-10-16 for the bank, L1, C3 / C4 and D6–D9; every other line is the
2026-10-15 snapshot. **Re-check stock at order**; a distributor read is not a reservation.

| Line | Part | Need (20 boards) | JLC | Buildable source | Plan |
| --- | --- | ---: | ---: | --- | --- |
| C21–C23, C151, C152 | **B32643H8104J000** (TDK) | 100 | 0 | DigiKey 306 (read 2026-10-16T18:35Z) | **Consign.** Record the fitted part per board |
| L1 | **B82726S2243A020** | 20 | 0 | Mouser 62 / DigiKey 29 (read 2026-10-16T19:12Z) | **Consign / hand-assemble.** Production part stays B82726S2203A020 (owner pre-order, 29 weeks) |
| C3, C4 | **DE1E3RA222MJ4BH01F** (Y1 400 V) | 40 | 104 (C7170908) | JLC | JLC assembles |
| D6–D9 | PMEG6030EP,115 | 80 | 9,298 | JLC | JLC assembles (read 2026-10-16) |
| Q2, Q3, Q5, Q6 | IPW65R018CFD7 | 80 | 4 | DigiKey 459 | Buy 80 or more from one recorded lot (D-8 asks for lot traceability) |
| C5, C6 | B32676G1905K000 | 40 | 0 | DigiKey 547, 27 week | Consign |
| C1, C2 | R463N410050N1K | 40 | 46 | DigiKey 945, 24 week | Consign |
| F1 | KLDR025.TXP | 20 | 0 | 300 distributor | Consign |
| F2 | 3403.0279.23 | 20 | 0 | DigiKey 7,183 | Consign; LCSC C3163739 carries no stock |
| J2, J5 | 7466004R | 40 | 0 | DigiKey 8,856 | Distributor buy; JLC places it from consign |
| J3, J11 | B2P3-VH(LF)(SN) | 40 | 983 | DigiKey 42,437 | Hand-assemble; mate VHR-3M |
| D3, D17 | 30KPA150CA | 40 | 0 | distributor 1,750 | Consign |
| U41, U42 | R24C2T25/R-R | 40 | 0 | distributor 1,185 | **Hand-solder with hot air** (owner decision 2026-10-16): SMD, SSOP-36 at 0.65 mm pitch, so buy and keep them; JLC does not place them |
| T1 | CST3015-200ED | 20 | 64 | JLC | Coilcraft direct has no distributor listing; JLC covers the lot |
| U5 | LM4050AEM3-2.5/NOPB | 20 | 50 | JLC | Covers the lot; 500 boards need the owner pre-order |

Every other line is covered by JLC stock at 20 boards (CSV). **Fixings:** M3 nylon (UL94 V-0) screws, washers and standoffs for
H2–H7, the whole chain insulating (BRINGUP-PROBES.md, FAB-NOTE); one metal M3 for H1 (chassis / PE).

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

1. Independent design review (`REVIEW-TRIAGE.md`): every BLOCKER / MAJOR closed. Re-confirm; this regeneration did not
   re-verify it.
2. Enclosure bosses agreed for H1–H8 against the enclosure revision used (D5-AUDIT.md), or the holes moved to match.
3. JLC's laminate answer (S12), then fix the order remark and `stackup.json` together.
4. FAB-NOTE's pre-order tier: F6 re-run on the native-21 FEM corrections (S3 re-run on the remote box is pending), M11
   heatsink stack parts sourced, and the no-stock parts above procured.
5. **Module:** the inlet module with ≥ 100 µH DM per line, or the EMI deviation accepted in writing.
6. **CPL:** the 23 NEEDS-PREVIEW parts confirmed in JLC's preview (`CPL-PREVIEW-CHECKLIST.md`).
7. **Bank pre-lot gate** S25 on C22, and the DigiKey bank stock re-read (≥ 100 before purchase, else KNSCHA).
8. Controller side before any stage-38+ board is powered: the J13 merge and J4.1 dropped
   (`c23-supply-topology/CONTROLLER-REQUEST.md`; OPEN-ITEMS §5 item 3).
9. Firmware: the controller image must ship the **18 A tank ceiling** (DECISIONS 56) and the RMS-increment aux allowance
   (B11). The ladder above 17.5 A follows COMMISSIONING.md and the bank-variant rule above.
10. Owner approval of the spend.

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
5. Resonant operation at reduced power, then nominal, with IR thermal (task 04). The **18 A tank ceiling applies from the
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

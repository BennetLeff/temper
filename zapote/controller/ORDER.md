# Controller prototype order package (JLC PCB + PCBA)

Board: C1 + CR-8, committed board = C47 convergence run 3 (`pcb/controller.kicad_pcb` sha256
`77ed3751d0f430d07b774af649e3defea2f1aa25154bb6ddfe88e444f462e097`), branch `controller-c1-crs`.

**Nothing has been ordered, uploaded or paid. Ordering is the owner's decision.**

Prepared 2026-10-17 using only `python3 tools/verify_controller.py` (PASS, 233 checks) and `python3 layout/make.py --no-route` (ALL GATES PASS: DRC 0 errors / 0 unconnected / parity 0, 34 warnings; JLC DFM PASS; 13/13 layout checks; gerbv PASS). No routing was run.

The fab files `--no-route` regenerated were compared with the committed ones:
- **Gerbers, drill files, Gerber zip, assembly PDF:** only the creation-date lines differ. They were not re-committed, so the hashes below are the convergence run's files.
- **`evidence/drc.json`:** the same 34 warnings in a different order, plus the date. Not re-committed.
- **BOM and CPL: one real change (C48).** `layout/fab.py` used to call a footprint THT if it had any plated hole, so the ESP32-S3-WROOM-1U module U4 went out as `THT`. Its 12 plated holes are thermal vias in its ground pad, and it is an SMD footprint. `fab.py` now takes the footprint's own type, so the BOM and CPL list U4 as `SMD` (9 THT placements, not 10). Nothing else in either file changed. The CPL audit was rerun (same DB, sha256 `fce26b89…`): 16 CORRECTED, 224 OK, 44 NEEDS-PREVIEW; U4 is OK at rotation 0.

## 1. What to upload to JLC

| File | Path | sha256 |
|---|---|---|
| Gerbers + drill (zip, 16 files) | `fab/controller-gerbers.zip` | `b3b9a37e1fc3bf9b1058699e93b422f7df405edafa6711d4b342cdde6c1b245d` |
| BOM (87 lines) | `fab/bom-jlcpcb.csv` | `3966d8783e1ca8c40a5930cf7eb0a8075c0660f91f453ace4488a93e8dc5398b` |
| CPL (284 placements, 275 SMD / 9 THT, all top side) | `fab/cpl-jlcpcb.csv` | `4799a8e7a3e31eaec2dcb152f03badbfe01833aa04a5d71dab4a2948ca92c377` |
| Assembly drawing (reference, not uploaded) | `fab/assembly-top.pdf` | `a73ec3b013a0ae710db84d33a3c834c12befec87dc06028679299ec1d6518377` |

The JLC "Mount" column in the BOM/CPL is informational. JLC decides SMT or THT from its own part library.

**Board parameters** (from `fab/fab-notes.md` and `LAYOUT.md`):

| Option | Value |
|---|---|
| Size | 206.0 × 76.0 mm (single board, no panel) |
| Layers | 4 |
| Stack-up | **JLC04161H-7628**: F.Cu signal / In1.Cu solid selv_gnd plane / In2.Cu v3v3 pour + signals / B.Cu signal |
| Thickness | 1.6 mm |
| Copper | 1 oz outer, 0.5 oz inner |
| Surface finish | HASL lead-free |
| Mask / silk | green / white |
| Via covering | tented (vias carry no mask opening; gerbv review counts 2019 tented via sides) |
| Minimum features | track 0.15 mm, clearance 0.15 mm, via 0.6 / 0.3 mm, PTH ring ≥ 0.20 mm (all at or above JLC's standard capability; `evidence/jlc-dfm.json`) |
| Impedance control | **none**. No controlled-impedance nets: the SPI, UI and PWM lines are slow, and the RTD analog nets are DC. |
| Holes | six Ø4.0 mm non-plated support holes, milled from Edge.Cuts; 5 NPTH drill hits (J4's 2 pegs, J11's 3 TC2050 holes) |
| Assembly | top side only, Standard PCBA (THT connectors and consigned parts) |

## 2. Consigned and hand-sourced parts

Stock source: the repo's latest JLC reads, with no new network read.
- 75 BOM lines come from `evidence/fab-loose-ends/consignment/stock-snapshot.json`, read **2026-10-12**.
- 12 lines come from `evidence/c1-crs/new-parts-snapshot.json`, read **2026-10-15**.
- `python3 evidence/order/order_table.py --boards N` re-derives the table (`evidence/order/order-table.json`).
- JLC stock moves daily. Re-check at the JLC BOM step.

**Against a 5-board build** (2 × quantity rule), only one line is short:

| Part | Ref | JLC stock (read) | Action |
|---|---|---|---|
| **RG2012V-431-W-T1** (Susumu, 430 Ω 0805, 0.05 %, ±5 ppm/K per the CR-2 budget; LCSC C4260028) | R39, MAX31865 Rref | **0** (2026-10-15) | **Consign**: 1 per board + 2 spares. Build 3 → 5 pcs; build 5 → 7 pcs |

**Distributor part numbers:** not in the repo's evidence. Look up the Digi-Key and Mouser numbers.
- The only distributor record (`distributor_records.json`, 2026-10-12) is a Digi-Key search page. It showed no stock and only a 3,000-piece reel at USD 1.23745 each, factory lead time 22 weeks. Mouser could not be read.
- A cut-tape or small-quantity source has not been found yet. Check Digi-Key, Mouser and Susumu's distributors for RG2012V-431-W-T1 and RG2012V-431-W-T5 cut tape.

**Why the 0.1 % substitute is rejected (C37):** RT0805BRD07430RL (C865488, 0.1 %, ±25 ppm/K, in JLC stock) was the C35 prototype swap. The sensor-r3 CR-2 accuracy budget (`evidence/sensor-r3-checks/checks-as-built.json`, item 1b) puts its tempco error at **0.80 K at 250 °C** (0.55 K at 100 °C). The RG2012V gives 0.16 K, and the budget assumes the 0.05 % / 5 ppm part, so C37 reverted the swap.

**If no consignment source arrives in time:** in JLC's BOM step, mark R39 "do not place", and hand-fit an RG2012V when it arrives (0805, R39 near the MAX31865, rotation 180 in the CPL). The board is fully usable except the pan-RTD channel until R39 is fitted. Do not fit the RT0805 part in its place for any measurement that the 250 °C accuracy matters to.

**Lines that are thin, but cover a 5-board build ×2:**

| Part | Ref | JLC stock (2026-10-12) | Per board | Note |
|---|---|---|---|---|
| TPS3703A4330DSERQ1 | U3 | 18 | 1 | Enough for 9 boards; short at 10 or more |
| SWRB1205S-100MT | L2 | 65 | 1 | Enough |
| AD8436ARQZ-R7 (owner-approved A grade, C35) | U14 | 106 | 1 | Enough |
| 74HC30PW,118 | U22 | 144 | 1 | Enough |
| TLV9031DBVR | U19, U26 | 167 | 2 | Enough |

No other part is consigned. The ESP32-S3-WROOM-1U-N8's U.FL coax and chip-antenna board are separate items, not on this BOM (fab notes).

## 3. Manual checks before paying

1. **NEEDS-PREVIEW CPL lines:** 44 placements under 23 LCSC codes. The task's figure of 37 was the 248-part board of 2026-10-12. Check one designator per code in JLC's 3D placement preview: the rest of a code follows it, and the CPL carries KiCad's rotation for them. Pin 1 / polarity is what to look at. Codes and designators are in `fab/fab-notes.md`.
   - **SOT-23-5 logic and comparators:** SN74LVC1G32 (U27), TLV3201 (U10), SN74LVC1G38 (U35), TLV9031 (U19), SN74LVC1G86 (U43; geometry says 180°, DB says 270°), SN74LVC1G08 (U11), SN74LVC1G14 (U12), REF2025 (U29).
   - **SOT-23 parts:** TLV76050 (U16), BAT54S (D8), 2N7002 (Q1), LM4040 (U13).
   - **SOD-523 TVS:** ESD5Z3.3 (D1), ESD5Z5.0 (D7); the cathode band goes to the signal.
   - **Power:** TPS3703 WSON-6 (U3), TPS62933 SOT-583 (U1, U2), AD8436 QSOP-20 (U14), EEE-FK1E101P electrolytics (C1, C9; polarity).
   - **THT connectors:** JST XH (J1, J3, J7), Molex Micro-Fit J4.
2. **J4 (Molex 43045-1600, right-angle Micro-Fit 2×8):**
   - The Molex sales drawing is **still unread**: molex.com refused this network (`evidence/fab-loose-ends/README.md` §3).
   - The footprint is KiCad's `Molex_Micro-Fit_3.0_43045-1600_2x08_P3.00mm_Horizontal`, but its source note cites the 43045-0201 drawing.
   - **[UNVERIFIED]:** the mated height (10.29 mm, Molex's figure for 43045-2001), and the plug's −X overhang past the board edge (R31: to X −50).
   - Before paying, open the 43045-1600 drawing and compare the pad grid, peg positions, body outline and overhang with the footprint and `evidence/fab-loose-ends/j4/j4-interface.svg`.
   - A mismatch in pegs or pads is a fab blocker; a height or overhang difference is an enclosure item.
3. **DNP / no-fit:**
   - **J11** is a copper-only Tag-Connect TC2050-IDC-NL land: 10 pads and 3 NPTH, excluded from BOM and CPL (C41). Nothing is fitted; programming uses the TC2050 cable.
   - No other DNP. R39 becomes DNP only if consignment misses the order (above).
4. **U4 at JLC's BOM step:** check that the WROOM module appears as an SMT placement (C48 above).
5. **JLC BOM matching:** all 87 lines carry an LCSC code (`fab-notes.md`: "missing: none"). Accept JLC's match for each, but reject any "similar part" substitution, especially R39 and the 0.1 % thin-film resistors.

## 4. Open board items (DECISIONS "Open items") that do not block a prototype order

**None blocks fab.** Each needs either the assembled board or a decision that does not change copper.

| # | Item | What closes it |
|---|---|---|
| 5 | AD8436 settling with CAVG = 100 nF; envelope-tracking error over a half line cycle | Bench: step and 120 Hz-modulated tank-current input on U14, scope RMS output vs a true-RMS reference |
| 15 | 2EDR8259X DIS-to-output delay (capmode veto ≤ 190 ns), CT_ZC polarity and first edge | Bench with the power stage: D-8 double-pulse set-up, DIS edge to gate edge; low-current CT_ZC capture (strap R72 if reversed) |
| 16 / 21 | Rim maximum under a 250 °C hold; CR-5 rim-trip resistor stays **86.6 k** (fitted) | Bench T3: glass temperature beside the rim NTC under a 250 °C hold. ≤ 244.5 °C means change to 76.8 k (a one-resistor rework, rerun `rim_trip()`); otherwise 86.6 k stays |
| 22 | Firmware `adc_gain` 0.85507 for HS_ADC (CR-8) | Firmware constant; bench check of HS_ADC at room temperature vs the NTC |
| 18 | MAX31865 words 35544 / 12844, manual fault cycle ≥ 5.5 ms per step; bursts at or above resonance; RUN_EN only with PWM idle; WDI from the supervisor task | Firmware |
| 19 | J12 harness third (drain) contact; J11 is a flush TC2050 land | Enclosure / harness |
| 1, 2, 3 | D-18 fan supply confirmation; M12 probe type and pin map; UI board parts and STOP | Owner and UI board. Each affects a harness or another board, not this copper |
| 4 | Runaway band 298.8–323.1 °C | Owner acceptance; a band change is one resistor |
| 6 | J4 harness ≤ 1 m AWG22 default | Power stage; `harness_sensitivity()` shows the design does not depend on it |
| 7 | Procurement list (stale: AD8436B, ERA-3AEB1652V, CD74HC30 were swapped in C35/C36) | Superseded by §2 of this file |
| 8 | Firmware items (ADC pattern, BIAS sequence, WDI heartbeat, UI bus driver, pins.h) | Firmware |
| 9 | Native KiCad ERC and the Rust stackup gate; TPS389001 footprint library | Layout tooling; DRC/DFM pass now |
| 10 | Supervisor nuisance trips, v3v3 decay, open-return and whole-J4 cases, fan start at PS1 low corner, D-11 accuracy | Bench with native-21 |
| 11 | Enclosure connector-vs-hole and height checks (`ENCLOSURE-HANDOFF.md`) | Enclosure session with the as-built board |
| 14 | RTD SPI return over the v3v3 plane (validator W4) | Accepted for the prototype; RTD unit owner's profile change |
| 17 | Rref consignment | §2 |

The block-validator waivers W1–W7 (`evidence/block-validators/WAIVERS.md`) are also open by design. They cover the physical fault tests NOT RUN, device qualification, and the C37 filter accepted outside the RTD unit contract. These are bench and contract items, not fab items.

## 5. Quantity recommendation

**Order 5 bare PCBs (JLC's minimum for 4 layers) and assemble 3** (JLC PCBA minimum 2).
- Board 1: bring-up and firmware.
- Board 2: integration with native-21 and the enclosure.
- Board 3: the physical fault-injection tests the validators list as NOT RUN, which can be destructive.
- The 2 spare bare boards cover rework or a later CR without re-ordering.

Consign R39 for that plan as 5 pcs (3 + 2 spares).

**Cost from the BOM data** (`evidence/order/order-table.json`): **USD 65.32 per board** in parts at JLC's quantity-1 unit prices of 2026-10-12 / 15, all 87 lines priced.
- Largest lines: AD8436ARQZ-R7 12.10, MAX31865 8.87, TLV3201 × 6 5.84, ESP32-S3-WROOM-1U-N8 4.81, TPS3703-Q1 4.10.
- **Not included, and not in the repo's evidence:**
  - PCB fabrication;
  - SMT and THT assembly fees;
  - JLC's per-type fee for extended-library parts (82 of the 87 lines are "expand" in the snapshots);
  - consignment duty, VAT and handling (13 % VAT plus a 2 % handling fee, minimum USD 10, per the consignment sheet);
  - shipping.

  Read them off JLC's quote.

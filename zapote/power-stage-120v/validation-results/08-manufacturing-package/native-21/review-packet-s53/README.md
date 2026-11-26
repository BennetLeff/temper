# Reviewer packet: Temper 120 V induction power board, native-21 stage 53 (section 0: now stage 57)

For a professional power-electronics PCB designer. Written 2026-10-18. Nothing here has been built or bench-tested.
Every number names its source file. Paths are relative to PS = `zapote/power-stage-120v` in this repository, unless they
start with `firmware/` (repository worktree root) or `runs-native21/` (the build directory beside the worktree, outside
git). `VR` = `PS/validation-results`. `FILES.md` (this folder) lists every path.

## 0. Read first: the board of record is now stage 57 (updated 2026-11-25)

Sections 1–9 are the stage-53 packet, written 2026-10-18. Three stages have landed since. Where this section and a later one
disagree, this section wins.

- **Stage 54** (`PS/DECISIONS.md` item 81, `VR/11-candidates/c54-board/README.md`), the c54 lanes the s53 text calls "running":
  - R10 / R12 / R18 / R20 moved to UniRoyal PS12 2 W (same 2512 land).
  - The split bleed moved to Panasonic ERJ-PA3 anti-surge parts.
  - R44 / R45 became 11 k and the firmware peak-trip max 62.5 A.
  - J1.2 gained an ac_n_in F.Cu strip with 8 stitch vias.
  - 9 track-cleanup edits were made inside the existing locks.
- **Stage 55** (item 82, `VR/11-candidates/c55-findings/README.md`):
  - U47 SN74LVC1G17 Schmitt buffer + C179 between the R134 / C167 CMTI filter and U13.A, because U13.A's 10 ns/V
    input-transition limit was exceeded.
  - The SELV-spine lock was reissued on the new board.
  - The C2 X2 ripple rating was re-read from KEMET's graph: 1.97 A for 1 µF, not 1.5 A.

- **Stage 56** (item 85, `VR/11-candidates/c56-s56-scope/README.md`): R127 / R129, the U41 / U42 CTRL dividers, 27 k → 16 k. BOM only;
  copper is s55's, so the s55 column below holds. Item 86 (Q2 / Q3 / Q5 / Q6 DNP at JLC) was reversed by item 91: JLC hand-solders consigned Q2 / Q3 / Q5 / Q6.

| Section 5 row | s53 (below) | s55 / s56 | Source |
|---|---|---|---|
| Release thermal margin | +1.3 K, R10 binding | **+3.8 K**, now bound by the laminate 1 mm-block copper peak; R10 +12.9 K | item 81; card `b3_release_margin_K` |
| J1 cord terminal | 103.1 / 105 °C on a scaled curve | **94.8 / 105 °C, +10.2 K** (two-node clamp model, 14 AWG lead; gated B3 row) | item 81; `VR/11-candidates/c54-j1-thermal/` |
| CT band vs firmware peak trip | 0.05 A | band 67.36–79.32 A, `TANK_PEAK_TRIP_MAX_A` 62.5 A: **4.86 A** | item 81; COMMISSIONING board table B9 / B17 |
| Touch current | 0.2412 / 0.25 mA | unchanged. The governing limit is recorded as 0.5 mA (UL grounded portable); first article measures it | item 81; `VR/11-candidates/c54-touch-current/` |
| Datasheet ledger | 3 / 92 / 0 | still 3 VERIFIED / 92 PARTIAL / 0 VIOLATION. Every SIGNAL line now carries electrical ratings. The two desk findings are resolved: U13.A edge fixed at s55; C2 ripple 0.874 of rating at the release case, 28 A open | items 81–82; `VR/11-candidates/c54-ledger-desk/results/gap-classes.md` |

**Files for s57** (s56 with the TO-247 holes at 1.8 mm, DECISIONS 87; they replace the section 2 rows for the routed board, 3D model and Gerbers):
- **Routed board:** now in git at `VR/08-manufacturing-package/native-21/board-of-record-s57/` (`section.kicad_pcb`,
  `.kicad_sch`, `.kicad_dru`, `board.step`, `SHA256SUMS`). Board SHA-256
  `25596d8eff460eabab3c538c83daea0d88eb1135fd7ae1519d8cc30a4f32421a`, copper key `a4a2e176134f`.
- **Gerbers:** zip SHA-256 `f91513c5ce1163b758912ec1e4899f406645d0471d9a5bce69a232e08157cea9`.
- **Card:** `VR/10-benchmark/scorecard-native21s57.json`.
- **Counts:** 95 BOM lines, 374 placements, 786 vias (771 POFV 0.3 mm), 885 plated holes, DRC 0, JLC DFM PASS.

**Section 9 items now fixed:** the FAB-NOTE via and hole counts (s55 census), the `PS/README.md` header and the
`OPEN-ITEMS.md` header (both name s57).

## 1. What the board is

- A **full-bridge series-resonant induction-heating power stage** for a countertop, cord-and-plug cooktop, 120–127 V~
  60 Hz, NEMA 5-15P (nameplate decided 2026-10-08; `sourcing/inquiries/F1-CERTIFIER.md`). Target standard UL 858
  (or UL 1026; not yet confirmed with a lab, `owner-items/CERTIFIER-CHECKLIST.md` entry 0).
- Chain: cord terminal J1 → F1 (Class CC, 25 A) → X caps, L1 CM choke, Y caps → BR1 bridge → film bus (C5 / C6) →
  four IPW65R018CFD7 650 V CFD7 MOSFETs (Q2 / Q3 / Q5 / Q6) on a PE-bonded heatsink (production insulation: AlN tiles, M11; DECISIONS 80) → resonant bank (5 × 100 nF,
  2000 V film, C21–C23 / C151 / C152) → coil studs J2 / J5. Tank current sensed by CT T1 (1:200); bus shoot-through
  OCP on shunt R5 (Kelvin). Gate drive: two Infineon 2EDR8259X isolated half-bridge drivers (U1 / U2), bias from two
  RECOM R24C2T25 modules (U41 / U42) and an LDO (U26), gate supply PS2 (MEAN WELL MPM-20-24) switched by the TCO loop J3.
  The controller (ESP32-S3, separate board) connects through one SELV header J4.
- **Size and stack:** 290 × 190 mm L-shaped, 4 layers, 1.6 mm nominal, **2 oz outer and 2 oz inner**, JLCPCB stack
  JLC041622-7628, ENIG, all 0.3 mm vias epoxy-filled and capped (`fab/FAB-NOTE.md`; `native-21/stackup.json`).
  In1 is the HV_RET / leg-return reference plane, In2 the BUS_P plane, 0.5 mm core between them (`stackup.json`).
- **Counts (s53 card):** 95 BOM lines, 372 placements, 777 vias, 4385 tracks, 99 plated pads, minimum track 0.2 mm
  (`VR/10-benchmark/scorecard-native21s53.json` cost block; `VR/08-manufacturing-package/native-21/jlc-dfm.json`).
- **Shipped operating point:** tank ceiling 17.5 A in still air (DECISIONS 61). Above that needs board-face airflow
  (section 6).
- **Prototype lot:** 20 boards, JLC assembly, through-hole hand work only where unavoidable (`fab/FAB-NOTE.md` Assembly;
  DECISIONS 72 addendum, 74). Bring-up plan: `BRING-UP.md`, procedure `firmware/components/power/COMMISSIONING.md`.

## 2. Files to open

| What | Path | Note |
|---|---|---|
| Routed board (s53) | `runs-native21/s53/c53int/section.kicad_pcb` | **Outside git.** SHA-256 `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27` (checked 2026-10-18). KiCad 10 format (version 20260206; built with KiCad 10.0.4). We send you this file. |
| 3D model | `runs-native21/s53/c53int/board.step` | Outside git, same build |
| Gerbers, drill, BOM, CPL | `VR/08-manufacturing-package/native-21/fab/` | Gerber zip SHA-256 `a6afd37a4f4e0039de8de7fd86755ff65328f21e43501a23d0904e78ffbd4ddc` (`fab/FAB-NOTE.md`). Upload `cpl-jlcpcb-order.csv`, not `cpl-jlcpcb.csv` |
| Fab note (order requirements) | `VR/08-manufacturing-package/native-21/fab/FAB-NOTE.md` | Some counts in it are stale (section 9) |
| **Resolved BOM (use this)** | `native-21/frozen/resolved-components.json`, `native-21/frozen/default.csv` | The true parts per designator |
| Netlist | `native-21/frozen/default.net` | **Warning: its part / libsource fields are stale or aliased** (atopile 0.2.69). R135 shows 0603WAF1000T5E (is 100 k 0603WAF1003T5E), U46 SN74LVC1G00DBVR (is SN74LVC1G132DBVR), R146 100 k (is 220 k) (OPEN-ITEMS B14). Earlier aliases fooled an outside reviewer (`VR/13-external-review-2026-10-13/FINDINGS.md`, "Netlist trap"). Read connectivity from the net file, parts from `default.csv` |
| Schematic (generated) | `native-21/section.kicad_sch` | Generated by `prototype-closure/pcb/build_schematic21.py`; last committed at s52 (the s53 BOM is s52's) |
| Circuit source | `elec/src/` (atopile) | Build steps in `PS/README.md` "Build and verify" (that README's board description is old) |
| Layer stack | `native-21/stackup.json` | Single source for the board stack and every physics model |
| Insulation basis | `D5-BASIS.md`; DECISIONS 7 / 18 | 8.0 mm HOT↔SELV / PE floor, 12.6 mm for RES_A |
| Decision log / open items | `DECISIONS.md` (items 50–80 cover s38–s53), `OPEN-ITEMS.md` | OPEN-ITEMS header still says s51; the scorecard row says s53 |
| Scorecard of record | `VR/10-benchmark/scorecard-native21s53.json` | 19 gates, performance margins, cost |

## 3. How the layout is made (please read before editing anything)

- The copper is **generated**. `native-21/layout/copper.json` (tracks, vias, zones) plus `placement.json` and the
  board-only parts (`native-21/layout/board_only21.json`) are turned into the KiCad board by scripts. KiCad is not the
  source.
- Rebuild the board from the committed sources (macOS, KiCad 10 at `/Applications/KiCad`, run from PS):
  `sh native-21/layout/incr_iter.sh native-21/layout/copper.json - OUTDIR` (place, build, rules, apply copper, test
  points, labels, DRC with zone refill). The full chain with every gate is
  `TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s53 PASSDIR BUILDDIR`; the exact stage-53 sequence is in
  `VR/11-candidates/c53-cert-provisions/stage53/README.md` "Reproduce". Compare the result's SHA-256 with the one above.
  We did not re-run the build for this packet.
- **Send findings back as a numbered list, not as KiCad edits**, unless we agree that you take over the layout. A KiCad
  edit cannot flow back into `copper.json`, and it would bypass the gates. For each finding please give:
  an ID; the location (designator, net and x, y in mm in the KiCad frame: origin top-left, y down, board 0–290 × 0–190);
  severity (would-not-ship / should-fix / suggestion); what is wrong; your suggested fix.

## 4. What has already been checked, and by which gate (s53 values)

All 19 gates pass on s53 (`scorecard-native21s53.json` "gates"). Gate code: `native-21/layout/gates/scorecard.py`
`gates()`. Outputs: `runs-native21/s53/c53int/` unless another file is named.

| # | Gate | What it checks | s53 value |
|---|---|---|---|
| 1 | `drc_errors_0` | KiCad DRC errors | 0 errors (accepted warnings listed in `fab/FAB-NOTE.md`) |
| 2 | `drc_unconnected_0` | KiCad unconnected items | 0 |
| 3 | `drc_parity_0` | board ↔ generated schematic parity | 0 |
| 4 | `barrier_8mm` | Rust barrier gate: HOT ↔ SELV / PE ≥ 8.0 mm plan view, every layer, no cross-layer case | 0 violations (`barrier-gate-rust.json`) |
| 5 | `res_a_outer_12p6mm` | RES_A (tank, 297 V rms at 28 A) ≥ 12.6 mm to SELV / PE on outer layers | 0 violations; F.Cu min 18.993, B.Cu 13.375 mm (`barrier.txt`) |
| 6 | `jlc_dfm` | JLC capability rules (2 oz annular ring 0.254 mm, track / space, via sizes) | PASS, 0 failures (`jlc-dfm.json`) |
| 7 | `return_path19` | each fast signal has a reference pour or a coupled return within limits | PASS, 21 signals, 0 failures; 4 opens reported, not asserted (OPEN-ITEMS S10); worst asserted 2.72 mm (card) |
| 8 | `bypass` | local bypass distance for comparators, Schmitt buffers, rail monitors | 16 / 16 pass (`bypass-check.json`) |
| 9 | `pi_distances` | RECOM U41 / U42 and LDO U26 caps ≤ 3.0 mm from their power pins | 7 rows, 0 failures (`pi-distances.json`) |
| 10 | `res_a_creepage18` | per-layer RES_A to SELV / PE census from the copper dump | 0 violations (`res-a-creepage.json`) |
| 11 | `cu_temp_basis` | every copper-loss consumer declares its copper temperature | 0 errors, 39 registered (`cu-temp-basis.json`) |
| 12 | `pin_absmax` | every IC pin's worst voltage against its absolute maximum | 0 failures; 97.1 % of 315 connected pins covered, 184 voltage-checked; 5 warnings, 9 undeclared (`pin-absmax.json`; OPEN-ITEMS S22) |
| 13 | `d5` | D5 audit of HOT–SELV and HOT–PE copper distance | 8.047 / 8.507 mm against 8.0 (card; `native-21/verification/d5-audit.json`) |
| 14 | `enclosure_fit` | board in the R43 enclosure, real pose, exact solids | 425 bodies, 4 known pairs under 1 mm, 0 new (`validation-plan/enclosure-fit/native21-in-r43.json`) |
| 15 | `jet_strip_height` | nothing over 4.0 mm under the future airflow jet box | max 1.72 mm (C19) (`validation-plan/enclosure-fit/native21-jet-strip.json`) |
| 16 | `audit_rs` | Rust netlist audit of the frozen export (SELV and barrier tables, stage checks) | PASS (`audit.rs`) |
| 17 | `kelvin_floor` | OCP band low corner after the Kelvin shift ≥ 64.17 A | 69.18 A (band 69.18–114.57 A) (card; `VR/02-protection-timing/kelvin/budget-native21s53.json`) |
| 18 | `b3_ratings` | board thermal model against part ratings and laminate MOT 130 °C at the release case (18.375 A tank = 1.05 × 17.5 A, bay air 61 °C, still air h 10, line 13.5 A) | PASS, **+1.3 K**; binding row R10 (2512 gate resistor terminal derating at 0.217 W) (card; `VR/04-board-current-thermal/round5-native21/b3-ratings/margins.json`) |
| 19 | `bom_buildable_proto` | every BOM line in stock for 20 boards | 0 short lines (card) |

Also on the card or run by the chain, not counted above:
- Datasheet ledger ratchet: 0 violations, 0 unaudited SAFETY / POWER lines; 3 VERIFIED / 92 PARTIAL
  (`native-21/verification/datasheet-ledger/`; section 6).
- Stranded vias: 0 of 3108 on s53; per-net copper baseline: 0 failures s52 → s53 (DECISIONS 78).
- EMI (desk model s19b): 11.1 dB minimum margin **only with ≥ 100 µH DM per line in the off-board inlet module**;
  6.03 / 1.57 dB (inconclusive) with today's 41 µH module (card `emi_min_margin_dB`, source note; DECISIONS 74).
- F1 clearing I²t against the narrowest board copper: 0.993 (fails by 0.7 %) (`VR/02-protection-timing/shoot-through-f1/s53_necks.json`).
- CMTI: minimum gate-command ratio 2.201 (card).
- Switching parasitics: F6 grid on the s51 FEM loop matrices, 640 / 640 cases pass at typical and maximum Qrr; worst
  die VDS 435.7 V (S2 fault); leg A power loop −3.7 nH, leg B +0.5 nH against round 17 (DECISIONS 77; OPEN-ITEMS S3).
- Independent design review 2026-10-18: no BLOCKER or MAJOR on the power board's PERMIT, gate-drive or barrier circuits
  (`INDEPENDENT-REVIEW-2026-10-18.md`).

## 5. Thin margins and known limits

| Item | Value | Source |
|---|---|---|
| Release thermal margin | +1.3 K at 17.5 A (×1.05), bay 61 °C, still air; binding row R10 2512 terminal | card `b3_release_margin_K`; `b3-ratings/margins.json` |
| J1 cord terminal temperature | 103.1 °C against 105 °C at the release case (+1.9 K, ratio 0.982). OPEN-ITEMS S21 quotes +0.4 K (104.6 °C) from the s42 / s48 re-base. Either way the own rise is scaled from Phoenix's 6 mm² curve, so with the 14 AWG cord it is larger: not a demonstrated pass | ledger entry 1714971 (`ledger-report.json` at HEAD); OPEN-ITEMS S21 |
| Touch current | 0.2412 mA against a 0.25 mA budget (50 % of 0.5 mA), margin 8.8 µA, datasheet-maximum module leakage | `VR/07-conducted-emi/leakage/result.json` DESIGN row; DECISIONS 50 |
| CT band vs firmware peak trip | firmware `TANK_PEAK_TRIP_MAX_A` 64.5 A sits **0.05 A** below the CT comparators' low corner 64.55 A (reference network at a uniform 85 °C; R40–R46 have no thermal rows) | OPEN-ITEMS S29; `VR/11-candidates/commission-s53/README.md` |
| Still-air ceiling | 17.5 A tank. 22, 24 and 28 A need board-face airflow (jets plus a both-face base flow, h ≥ 16 W/m²K at 61 °C for 28 A) and a bench h measurement. At c22 / c28 the laminate margin is −50.8 K and the rated-part margin −51.0 K in still air | DECISIONS 61, 66; OPEN-ITEMS S24; card `b3_laminate_margin_K`, `b3_rated_part_margin_K` |
| Bank ceiling | The prototype bank (TDK B32643H8104J000) caps the ladder at **24 A strict** (vendor ratio 0.844 at 24 A); 28 A needs B32643B8104J000 (28-week) on the same holes | DECISIONS 74; OPEN-ITEMS S28 |
| Bank self-heating, still air | hottest interior cap C22: 0.871 with radiation / 1.133 without at 18.375 A; pre-lot bench gate | OPEN-ITEMS S25 |
| FET reverse-diode dv/dt, maximum Qrr | 68.16 V/ns = 0.97 of the 70 V/ns rating (over the 56 V/ns 80 % screen); bench D-8 decides | ledger IPW65R018CFD7; OPEN-ITEMS S14 |
| FET Tj at 28 A / 50 kHz | 128.7 °C on the K1 contingency sink against 125 °C design | ledger IPW65R018CFD7 gaps |
| PS2 local air | ledger ratio 0.948 at the release case; the 60 kHz window top is a PS2 rating limit; a 78 °C stacked bay fails PS2 at any load | ledger MPM-20-24; OPEN-ITEMS S18, S27 |
| Bus TVS standoff | D3 / D17 0.9587 of standoff at the 287.62 V OVP band top | OPEN-ITEMS S20 |
| OCP comparator CM term | Kelvin band low corner 69.18 A; bench run of 30 TLV3201 pending | OPEN-ITEMS S23 |
| Line-current limit | firmware estimate only; F1 does not open at 15–25 A; hardware R5 trip designed, deferred | DECISIONS 75; `VR/11-candidates/c53-r5-trip/DESIGN.md` |
| Return-path opens | 4 HOT-side opens left (bus_fault_hot ×3, monitor_ls-good), reported, not asserted | OPEN-ITEMS S10; DECISIONS 75 |
| EMI | prototype L1 (B82726S2243A020) is inconclusive (6.03 / 1.57 dB) unless the inlet module adds ≥ 100 µH DM per line | DECISIONS 74 |

**Datasheet ledger: 92 PARTIAL / 3 VERIFIED / 0 VIOLATION of 95 lines** (card `sources.ledger`;
`native-21/verification/datasheet-ledger/ledger-report.json` at HEAD). PARTIAL means at least one recorded gap, not a
failed rating. Our keyword count of the gap texts in that file (this packet's count, not a gate output):
- 74 of 92 note that the temperature is a B3 model estimate, not a measurement;
- 52 are SIGNAL lines audited for temperature only ("Not audited (outside SAFETY/POWER)"); 50 lines do not yet carry
  their electrical ratings in the ledger;
- of the 30 SAFETY / POWER PARTIALs, 27 list a bench measurement as the closing step, and 19 list an approval or
  certifier question (UL / CSA file not read, approval basis to confirm).
So most PARTIALs close on the bench or with the certifier, not with more desk work. A ledger lane (`c54-ledger-desk`) is
running, so these counts may move.

## 6. Open certification items

The ranked list is `owner-items/CERTIFIER-CHECKLIST.md`; the question index is `owner-items/CERTIFIER-PACKET.md`
(refreshed to s53 on 2026-10-18). The ones that touch the layout:
- Working voltage on the tank: line-cycle RMS or carrier-crest RMS. Crest RMS means about 7.4 mm on the coil lanes and
  6.3 mm RES_A to HV_RET / N_LS / BUS_P: a board-wide re-layout (packet A3 #11; DECISIONS.md:257).
- Inner layers as solid insulation (2 mm reinforced, IEC 60335-1 29.3). Closest inner case: C152.1 rings 8.328 mm from
  the SELV v3v3 plane (packet A3 #10; `fab/FAB-NOTE.md`).
- Laminate: KB-6164's UL multilayer row allows 35 µm inner copper; the board has 2 oz (61 µm). KB-6164F / KB-6165F
  allow 102 µm. CTI PLC 3 (group IIIa, zero margin to 175 V) (packet A3 #25; `owner-items/JLC-LAMINATE-QUESTION.md`).
- Stuck-on stage (UL 858 25.3.1): the TCO loop is the only firmware-independent cut, and it removes gate drive, not the
  power path (packet A4 #26; OPEN-ITEMS S15).
- F1 in open PCB clips with no voltage rating; abnormal test with firmware defeated (packet A2 #6, #9).
- Supply modules (MPM-20-24 / MPM-65-15ST) with IEC 60601-1 approvals and no UL file (packet A3 #14).
- UL files of the barrier parts (U1 / U2, U4, U9 / U32, U36) and T1's working voltage (packet A3 #15).

## 7. Questions we want answered

Power loop and switching
1. Look at the two half-bridge power loops (bus caps C5 / C6 and the snubbers to Q2 / Q3 and Q5 / Q6, through the In1 /
   In2 plane pair). Is the commutation loop as small as this package set allows? Where would you cut inductance first?
2. The bus shoot-through OCP uses R5 (CSS2H-2512R-1L00F, Kelvin sense fingers 1.5 mm west of the body; `fab/FAB-NOTE.md`)
   in the return. Is the Kelvin pickup clean, and are the sense traces safe from the switching field?
3. Our F6 grid gives worst die VDS 435.7 V on 650 V parts. Does anything in the layout make you doubt the FEM-derived
   loop values (leg A −3.7 nH, leg B +0.5 nH change against our reference)?

Gate drive
4. U1 / U2 (2EDR8259X) drive the two legs. Gate network (`INDEPENDENT-REVIEW-2026-10-18.md`, "Gate network"): 68 Ω turn-on, 1 Ω + PMEG6030 turn-off, 10 k gate–source,
   4.7 nF C0G Cgs. Are the gate loops and the Kelvin-source return routing right for 50–70 V/ns edges?
5. The 0.3 mm driver output necks run under the 0805 VDD–VSS caps with 0.30 mm to the pads (`fab/FAB-NOTE.md`
   first-article list). Would you ship that?
6. U41 / U42 (RECOM SSOP-36, 0.65 mm pitch, 0.20 mm pad gaps) feed the high-side drivers. Any concern with their local
   decoupling (gate 9, ≤ 3.0 mm) or with the land pattern (an outside review asked for a pad-by-pad check)?

Isolation, creepage and clearance (UL 858, pollution degree, material group)
7. We use 8.0 mm HOT ↔ SELV / PE (PD3, group IIIa, reinforced, ≤ 250 V rms) and 12.6 mm for RES_A on outer layers
   (`D5-BASIS.md`). Do you agree with the pollution degree and material-group basis for a cooktop interior? Would you use
   slots anywhere?
8. Barrier parts sit at exactly 8 mm package creepage (2EDR8259X, CA-IS3720HW, VOL628A). Is that enough on a PD3
   board, or would you add slots or conformal coat?
9. Do you see any path we have missed: vias near the barrier, test pads, silk, mounting holes (H3–H8 are nylon-only),
   lead protrusions (trimmed to ≤ 2.5 mm), or the heatsink stack?
10. Would you treat same-layer inner-copper gaps as solid insulation, or as creepage?

Thermal (17.5 A, still air)
11. Is a +1.3 K model margin at 61 °C bay air believable for shipping 17.5 A? What would you measure first?
12. The hot spots are the FET-row and R5 strip (R10 / R12 2512 gate resistors, laminate near R5) and J1. Would you
    change copper, part placement or packages before the first lot?

DFM, assembly, rework and test
13. Any DFM issue with 2 oz inner layers, 0.2 mm minimum track, all 0.3 mm vias filled and capped, via-in-pad, the plated
    1.2 × 2.5 mm slots for F1's clips, or the coil studs J2 / J5 (Würth 7466004R) on a 1.6 mm ±10 % board?
14. Rework: power pins are solid to 2 oz pours (rework only on a ≥ 100 °C preheated board). Acceptable?
15. Test access: 39 bring-up pads, no pad on `monitor_ls-ov` or U26.6. What would you add for production test and
    for the end-of-line veto test (OPEN-ITEMS B8)?
16. Assembly order: BR1, RV1 and the F1 clips are hand-fitted by the owner; the FETs are consigned. Anything you would
    change before a 20-board lot?

Overall
17. Is there anything on this board you would never ship? Please list it first.

## 8. What we will do with your answers

Each finding becomes an OPEN-ITEMS row and, if adopted, a layout candidate built through the scorecard (one lane per
isolation island). We will tell you which findings we adopt and why.

## 9. Stale facts we know about (do not trust these lines)

- `fab/FAB-NOTE.md`: "765 vias (stage 44)", "750 × 0.3 mm vias", "859 plated" drills and "Plated holes 876" disagree
  with each other and with the s53 DFM census (777 vias, 99 plated pads); its pre-order list still asks for the FEM
  matrices to land (closed, DECISIONS 77); it names U44 as a CA-IS3720LW, but U43 / U44 are ISO6721FBDR since stage 40.
- `PS/README.md` describes an old 240 × 160 mm board with UCC21550 drivers.
- `OPEN-ITEMS.md` header names s51 as the board of record; s53 is (DECISIONS 75).
- `native-21/frozen/default.net` part fields (section 2).

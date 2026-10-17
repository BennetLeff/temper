# Candidate 23: supply and filter topology, built as stage 38 (native21s38)

**Verdict: ACCEPT against s35** (`results/compare.txt`). It is cheaper on parts, lines, placements, extended, hand
and zero-stock lines. It is better on the EMI margin, the touch current and three track-geometry metrics, and worse
on nothing. Board `b5bf428d`; chain `native21s38` CHAIN_DONE with `SPINE_OWNER=selv`.

This builds the DECISIONS 47 change set on the board of record s35 (integration head 0aecdc56f, branch
`claude/native21-c23-supply`):

| # | DECISIONS 47 item | Stage 38 |
|---|---|---|
| 1 | Delete PS1; the logic runs from PS3 over J13 | Done. `ps_selv` and V15_SELV are gone. J4.1 sits on the single-pin SELV net `j4_nc1` (section 2) |
| 2 | PS2 IRM-20-24 → MPM-20-24 (JLC C6675337) | Done, on the unchanged Case 219A footprint (section 4) |
| 3 | L1 → SCF31X if it fits and is buildable, else keep it and record why | **Kept: TDK B82726S2203A020.** The SCF31X body does not fit without compaction (section 3) |
| 4 | C3 / C4 stay 2.2 nF; the D-22 module changes are off-board but used in leakage / EMI | Done: module Y removed and SCF31X 5.68 mH module choke in both models (section 5); `MODULE-REQUEST.md` |
| 5 | This lane owns the SELV spine | Chain run with `SPINE_OWNER=selv`. Lock re-issued in `--owner selv` scope (section 6) |
| 6 | Use the freed area sensibly; no compaction; don't move parts outside SELV / PS1 / L1 | Area kept clear. The L_FILT / N_FILT feeds were re-laid shorter; no part moved (section 3) |

## 1. Results (chain native21s38, board b5bf428d)

| Gate / metric | s38 | s35 |
|---|---|---|
| DRC errors / unconnected / parity | 0 / 0 / 0 | 0 / 0 / 0 |
| Barrier 8 mm; RES_A outer 12.6 mm (min B.Cu) | 0; 0 (13.375 mm) | same |
| D5 HOT-SELV / HOT-PE | 8.047 / 8.507 mm | same |
| Rust barrier; JLC DFM | 0; PASS (747 vias) | 0; PASS (750 vias) |
| FIT (board-only) | 400 / 0 / 0 / 402 / 0 | 401 / 0 / 0 / 403 / 0 |
| SPINE_LOCK (owner selv) | PASS (after the re-issue, section 6) | PASS |
| Bypass, return path, PI distances, RES_A creepage 18 | PASS | PASS |
| Kelvin band | 67.77–116.44 A | 67.77–116.44 A |
| Task 04 | 39 scenarios / 0 failed; bus_p span 2.835 % | same |
| B3 peaks: c28_h25 / nominal_h10 / c28_h10 / extreme_h10 | 135.0 / 162.1 / 192.4 / 247.1 °C | 135.0 / 162.1 / 192.3 / 247.1 |
| **B3 ratings** (c22_h10, c28_h10, bay 55 °C) | laminate **−56.4 K**, rated part **−38.9 K**, advisory −41.4 K; worst: laminate 1 mm-block copper peak (FAIL, the release gate) | −56.4 / −38.9 / −41.4 |
| CPL audit / BOM-CPL designators | 348 / 348 (OK 275, NEEDS-PREVIEW 54, CORRECTED 8); PASS | 349 / 349 (55 NEEDS-PREVIEW) |
| Necks (`shoot-through-f1/s38_necks.json`) | min ratio 0.993 | 0.993 |
| OCP pickup (`coil-pickup/s21b/result-s38.json`) | pan-60 stack 4.17 A | 4.17 A |
| Ledger gate | PASS: 93 lines, 3 VERIFIED / 31 PARTIAL / 59 UNAUDITED / 0 VIOLATION | PASS (94 lines) |

- **B3 ratings:** the margins are unchanged because the binding copper (R5 / the FET row) is untouched.
- **Parts near the old PS1 site:** with PS1's heat gone, the ZC-string resistors R67–R70 run 1.4–2.0 K cooler
  (`b3-ratings/margins.json` against 0aecdc56f).
- **ERC (not gated):** a new `power_pin_not_driven` error on U4 pin 5 (GND2). PS1's −V pin was the only power-output
  pin on SELV_GND. That net is now driven only through J4, whose pins are passive. This is a schematic-pin-type result
  only; the controller supplies SELV_GND as before.
- **Isolated pin labels:** 48 → 49, the new single-pin `j4_nc1`.

**Scorecard** (`../../10-benchmark/scorecard-native21s38.json`):

| Metric | s35 → s38 |
|---|---|
| leakage_touch_mA | 0.974 → **0.241** |
| emi_min_margin_dB | 10.5 → **12.4** |
| parts_usd_at_500 | 206.44 → **202.24** |
| parts_usd_at_5 | 311.47 → 306.87 |
| bom_lines | 94 → 93 |
| placements | 349 → 348 |
| jlc_extended_lines | 68 → 67 |
| hand_or_consign_lines | 20 → 19 |
| tht_lines | 18 → 17 |
| zero_stock_lines | 8 → 7 |
| single_source_lines | 19 → 18 |
| vias | 750 → 747 |
| track acute / right-angle corners | 206 / 104 → 205 / 103 |
| track_any_angle_mm | 704.4 → 678.5 |
| jlc_assemblable_share_500 | 0.851 → 0.849 |

`jlc_assemblable_share_500` falls only because the line count shrinks. `build_lead_wk_500` stays 29 weeks; L1 sets
the build date, as before.

Compare line: `ACCEPT native21s38 vs scorecard-native21s35.json: cheaper ['parts_usd_at_500', 'bom_lines',
'placements', 'jlc_extended_lines', 'hand_or_consign_lines', 'zero_stock_lines'], better ['emi_min_margin_dB',
'leakage_touch_mA', 'track_acute_corners', 'track_right_angle_corners', 'track_any_angle_mm']`.

## 2. Source (item 1, 2)

**Source changes:**
- `elec/src/power_stage_120v.ato`: `ps_selv` and V15_SELV removed; `signal J4_NC1`, `j_selv.p1 ~ J4_NC1`.
- `parts.ato`: the Irm20_15 component is gone.
- `f6_parts.ato`: HotSupply24 → MPM-20-24, with a docstring that gives the pages.

**Freeze:** rebuilt (`tools/build_source.py`; paths normalised as before), giving 348 components and 188 nets.
`verify_source.py` asserts that `ps_selv` is absent, that no MPN starts with `IRM-`, and that `ps_gate` is MPM-20-24
on the IRM-20 footprint.

**`audit.rs` updates:**
- SELV nets: v15_selv → j4_nc1, with a single-member check.
- `ps_selv` removed from the barrier and identity lists; `ps_gate` = MPM-20-24.
- New test `stage38_supply_topology_holds`.
- In `audit_f6.rs` the bias-source mutation test now rewires to v3v3.
- 83 / 83 tests pass; PASS on both frozen netlists.

**J4.1 decision:** J4.1 is not connected (`j4_nc1`), not re-pinned. A controller that has not been updated sees an
open pin and nothing is back-fed. The J4 re-pin (g06-g08-g10 P5) stays a separate step, as the controller request
allows (`CONTROLLER-REQUEST.md` item 2, addendum 2).

## 3. L1, the freed PS1 area, and the feeds (items 3, 6)

**The SCF31X fails on footprint; the rest fits:**

| Check | Result | Source |
|---|---|---|
| Rating | 22 A at 15 A inlet = 68 % (80 % rule OK) | SCF31X-220-2R1A011JH spec sheet (YAGEO, generated 10/15/2026; sha256 2fe4dbb96bae7eb3): 5.68 mH, 4.39 mΩ, 500 VAC, ΔT max 45 K, −40 / +130 °C, 91.9 g |
| Height | 33 mm max vs the TDK body's z 42.1 mm, fits | same sheet |
| **Footprint** | **does not fit**: body D 45 × T 42 mm max; the L1 slot is 47.96 × 32.81 mm | `scripts/l1_slot.py` → `results/l1_slot.json` |

**Footprint detail:**
- The slot is bounded by C1 (y ≤ 25.995), C5 (y ≥ 58.805), C2 and PS2.
- The body is too deep for the slot in either orientation. Even the PS1 area freed at stage 38 (53.0 × 27.8 mm) is
  shallower than the body, and it lies off the L_FILT / N_FILT path.
- Fitting the SCF31X needs C1 / C5 / F1 to move: compaction, which item 6 rules out.
- No pin drawing exists for the exact part. The sibling SCF31B-200-2R0A020JH, in KEM_LF0079_SCF-J_JH (09/25)
  p.4 Fig. 5 (sha256 3a692f8f8e90df54), is 48 × 42 × 35 mm with pitch a 17 / b 30 mm, "reference only, not
  guaranteed".

**Approvals:** no UL / CSA listing on either part. The SCF31X shows only a UL 94 V-0 base / cap. The TDK sheet cites
only EN 60938-2.

**Stock (2026-10-15, public pages):**

| Source | Result |
|---|---|
| DigiKey 399-SCF31X-220-2R1A011JH-ND | 68 in stock, 13-week lead; $12.82 at 1 … $7.725 at 560 |
| JLC parts API | no listing |
| Mouser | "Access denied" (unread) |
| Farnell | 403 (unread) |

68 parts cannot cover 500 boards plus 500 modules.

**Decision:** keep the TDK B82726S2203A020 at L1. The robust variant (DECISIONS 47: 11.51 dB) stays open for a later
re-layout. L1 keeps setting the 29-week build date.

**Freed PS1 area:** kept clear. The area is the PS1 courtyard at s35, [206.5, 112.1, 259.5, 139.9]. The only parts
that wanted to use it were the SCF31X, which is too deep, or a compaction, which is forbidden. Leaving it empty keeps
the J11 / F2 / R130 / D3 / D17 poses and the mains–SELV spacing as they were.

**Feeds re-laid** (`native-21/layout/patches21.py` `edit_base`, applied to the frozen stage-35 copper by `incr21.load`):
- **L_FILT:** one 1.0 mm F.Cu run from the C3 via through the R67 junction, east at y 121.7, and up at 45° onto
  stage 35's approach line to F2.1.
  - Length: 40.5 mm, against 60.5 mm through PS1.1.
  - Clearance: 3.6 mm to the N_FILT via (HOT functional 3.2 mm).
  - The 42° corner at PS1.1 is gone (track acute corners 206 → 205).
- **N_FILT:** the B.Cu run ends on the via that takes it to J11.2 on In1. That via was a 0.6 / 0.3 via inside
  PS1.2's pad. Standing alone, its 0.15 mm F.Cu ring split in two on task 04's 0.125 mm grid. Chain run 1 failed on
  that: kit topology preflight `n_filt/F.Cu`, 6 grid components vs 5 physical.
  - Fix: a 0.85 / 0.3 via moved 0.28 mm down the same 45° line to (256.8, 116.6). It keeps 3.375 mm to F2.1 (a
    0.85 via in the old spot would have had 3.175 mm).
  - Task 04 then passes 39 / 0.
- **Removed:** the v15_selv tracks and vias, about 250 mm across B.Cu and F.Cu with three vias, and
  the selv_gnd PS1.3 stub.
- **Unchanged:** the selv_gnd via at (210.8, 98.2), which keeps U36's return on the In2 pour.

The passes (`passes38.sh`) were clean on j1: unconnected 0, errors 0, barrier 0.

## 4. PS2 MPM-20-24 (item 2)

**Datasheet:** MPM-20-SPEC 2024-10-30 (meanwell.com, sha256 24d3a6bb642d74ea). Ledger entry `MPM-20-24`, PARTIAL.

**Ratings:**

| Rating | Value | Page |
|---|---|---|
| Output | 24 V 0.9 A, 21.6 W | p.2 |
| Input | 80–264 VAC (113–370 VDC); 0.75 A typical at 115 VAC | p.2 |
| Touch current | < 80 µA at 264 VAC, measured primary to DC output (Note 7) | p.2 |
| Withstand / isolation | I/P-O/P 4 kVAC; 2 × MOPP | p.2 |
| Working temperature | −35 … +85 °C | p.2 |
| Efficiency | 87 % typical (IRM-20-24: 85 %) | p.2 |
| Derating (12–24 V, horizontal) | 100 % to 55 °C, 70 % at 60 °C, 50 % at 70 °C, 30 % at 80 °C | p.3 |

**Approvals, verbatim:** "IEC 60601-1:2005+A1,TUV BS EN/ EN 60601-1:2006+A1+A12+A2,ANSI/AAMI ES60601-1:2005/A2:2021,
CAN/CSA C22.2 No. 60601-1:2014+A2,IEC 60335-1:2010/AMD2:2016, Dekra BS EN/ EN 60335-1:2012+A11+A13+A1+A14+A2+A15
,EAC TP TC 004 approved". No UL file is listed: a certifier item.

**Footprint:** p.4 Case 219A (52.4 × 27.2 × 24 mm; pins 3.4 / 45, 3.2 / 20.8 / 8 mm) is identical to IRM-20-SPEC
2025-11-21 p.3 (sha256 aa1afdbcdf0bf6db). Differences:
- pin Ø 1.04 mm, against 1.0 mm in the 1.5 mm drill;
- pin length 3.5 +1 / −0.5 mm (IRM: ±1);
- neither sheet gives keep-outs.

The KiCad `Converter_ACDC_MeanWell_IRM-20-xx_THT` footprint stays. Pad map: 1 AC/L, 2 AC/N, 3 −V, 4 +V
(`audit.rs:891`).

**Stress checks:**

| Check | Result |
|---|---|
| Bias allocation 9.59 W vs 21.6 W | 44 % (≤ 50 %) |
| 90 % of the p.3 derated curve | holds to **70.3 °C local air** (100 % to 72.8 °C) |
| Input 139.7 VAC vs 264 VAC | 53 % |

PS2's local air is unmeasured; that is the ledger gap. B3 keeps the IRM efficiencies (0.84 / 0.80), which is
conservative.

**Sourcing** (STOCK addendum s38; snapshot `study-2026-10-15/snapshot/s38/`):

| Source | Result |
|---|---|
| JLC C6675337 (part API 2026-10-15, cached in `study-2026-10-15/scripts/jlc-raw/detail_C6675337.json`) | 5,047 in stock, $9.7843 |
| DigiKey 1866-5337-ND | box ladder $14.30 at 1 / $13.60 at 5 / $13.00 at 10 / $12.60 at 25; 17-week lead; stock not shown (the page offers substitutes) |

**Price basis:** the card prices PS2 on the DigiKey basis that the IRM rows used: $13.60 at 5 boards and $12.60 at
500, the highest break shown. JLC's $9.78 would make it $2.82 cheaper.

**CPL:** C6675337 has no rotation-DB rule and no EasyEDA footprint, so PS2 is NEEDS-PREVIEW, as before.
`apply_lcsc.py` maps MPM-20-24 → C6675337.

## 5. Leakage and EMI with the s38 parts (item 4)

The scorecard inputs are written by their own scripts: `07-conducted-emi/leakage/leakage_budget.py` → `result.json`
and `07-conducted-emi/s19b/emi_s19b.py` → `results.json`. `scripts/s38_leakage_emi.py` re-solves both on the
co-design cores as a cross-check (→ `results/s38_leakage_emi.json`; CONTROLS ALL OK).

### Touch current (132 V, 60 Hz, +20 % Y, supplies at datasheet maximum)

**DESIGN 0.2412 mA, PASS:**

| Contribution | mA |
|---|---|
| Y (board 2.2 nF / line) | 0.1314 |
| Coil 31 pF | 0.0019 |
| MPM-20-24 | 0.0480 |
| MPM-65-15ST | 0.0600 |
| **Total** | **0.2412** |

- **Limits:** 0.25 mA budget (portable 0.5 mA, 50 %); margin **+8.8 µA**; 48 % of the 0.5 mA limit.
- **Sweep worst:** 0.2472 mA at 134.6 V, frequency factor 1.2, +20 % Y and a 51 pF coil.
- **It fails with:** +0.15 nF Y per line, or the supply maxima × 1.081.
- **Controls:**
  - +10 nF Y gives 0.838 mA, FAIL;
  - +0.2 nF gives 0.253 mA, FAIL;
  - the s35 reference row reproduces 0.9741 mA, FAIL.
- **Dependencies:** the result needs the D-22 module Y removed (with it kept, 0.653 mA) and PS3 = MPM-65-15ST (with
  an IRM-60-15ST in PS3, 0.324 mA).
- **HF estimate** (`hf_touch.py`, outside the rule): RSS ≤ 0.2456 mA IEC 60990 at every corner. The UL-style network
  reads up to 0.2991 mA at the chokes −30 % corner, unverified.

### s19b conducted EMI

The nominal module is now `MODULE_S38`: no Y; SCF31X 5.68 mH, 4.39 mΩ; DM leakage 1 % = 56.8 µH, unpublished. The
part-value sensitivities are now relative to the nominal parts.

| | s38 | s35 |
|---|---|---|
| Nominal | **12.37 dB** | 10.48 dB |
| Sensitivity minimum | **8.19 dB** (coil + board 51 pF) | 6.50 dB (X −20 %) |
| X −20 % | 9.86 dB | 6.50 dB |
| 22 A sensitivity minimum | 9.51 dB | 8.39 dB |
| Pan earthed (information) | 3.32 dB | 2.62 dB |

- **Verdict:** PASS.
- **Agreement:** the study's committed numbers for this filter are 12.3745 / 8.1863 dB.
- **Aux-supply CM bound:** 27.3 dB over 2 modules. It falls 10.5 dB per module because no module Y shunts the
  supplies' CM current.

**Co-design study (`leakage/co-design-2026-10-15`):** its repo copies are now checked against `git show 0aecdc56f:`.
Stage 38 changed `leakage_budget.py` / `emi_s19b.py` for the s38 system, and the study's numbers are for the s35
inputs. This is not a loosening: the copies still must match byte for byte, now against the base the study was made
on. `run_all.py --reuse --procs 4` passes all controls. Incidental timing / skipped-datasheet rewrites of
`results/` were restored.

## 6. SELV spine (item 5)

Chain run 1 (board 6f080b0d) failed only `SPINE_LOCK`, with the expected differences (`--owner selv` scope):
- J4.1's four pad keys move from v15_selv to j4_nc1;
- selv_gnd In2.Cu and v3v3 In1.Cu each fill 2.374 mm² where the v15_selv via antipads were.

Nothing else in the region changed. The selv lane re-issued the lock, `native-21/layout/selv_spine_lock.json`:
- baseline → `native-21/verification/spine-baseline-native21s38-all-copper.json.gz`, the run-1 export kept under its
  own name because the chain overwrites `<tag>-all-copper`;
- its board sha;
- a `reissued` record with the previous baseline (s32, 2fb346dc).

The final board differs from run 1 only outside the region (the N_FILT via). Chain run 2: SPINE_LOCK PASS
(owner selv). `gates/test_spine_lock.py` PASS.

**Other lanes:** a lane running without `SPINE_OWNER` compares the whole region by every net, so a non-owner chain on
this branch sees the new baseline. Lanes that branched before stage 38 keep the s32 baseline until they merge.

## 7. Process notes

- **Chain fix cherry-picked:** ea9093c49, b3-ratings exit status ignored in the thermal block (commit a3e16d6b6 on
  this branch). It was not the cause of run 1's failure, which was the task-04 topology preflight above.
- **B3 inputs:**
  - `make_heat_sources.py`: PS1 row removed; 40 parts; nominal 9.138 W, worst 18.629 W.
  - `thermal_body.spec_for`: maps MPM-20 to the meanwell class.
  - `b3-convergence/inputs/part-bodies.json`: minimal edit only (PS1 out, PS2 mpn).
  - A full re-extraction on the s38 board also picks up other lanes' later MPN changes (U1 / U2, R10 / R12 / R18 /
    R20, R39, bank grade). That is left to the B3 owner and recorded in the file's `edits` field.
- **Workers:** the chain ran with `TASK04_WORKERS=4`. `regate.sh` now reads that variable (default 6, as before).
- **Tests run:**
  - `audit.rs` (83);
  - `verify_source.py`;
  - ledger `gate.py` and `tests/test_gate.py` (0 failures);
  - `gates/test_spine_lock.py`, `test_track_geometry.py`, `test_trim_tails.py`;
  - `layout/test_layers21.py`, `b3/test_layers.py`;
  - the leakage and s19b controls;
  - co-design `run_all.py` controls;
  - `study-2026-10-15/run_all.sh` (every other output unchanged).
- **Builds:** under `worktrees/runs-native21/s38/` (outside the repo); the run-1 build and the superseded passes were
  deleted.

## 8. Requests and open items

- **`CONTROLLER-REQUEST.md` addendum 2:**
  - J4.1 is not connected on s38, so the J13 merge and removal of the J4.1 path must come first;
  - PS2 is MPM-20-24;
  - PS3 must be the MPM-65-15ST for the leakage pass.
- **`MODULE-REQUEST.md` (D-22 module owner):**
  - remove the four Y caps;
  - SCF31X choke, stock 68 at DigiKey;
  - measure the SCF31X DM leakage on a sample.
- **`ENCLOSURE-REQUEST.md`:**
  - PS1 volume freed;
  - PS2 envelope unchanged;
  - PS3 bay air ≤ 58 °C;
  - the module choke body.
- **Certifier:**
  - the MPM approval basis (IEC / ES / CSA 60601-1 and IEC 60335-1, no UL file);
  - the 8.8 µA leakage margin on datasheet maxima.
- **Bench:**
  - PS2 local air (70.3 °C limit for 9.59 W);
  - SCF31X DM leakage;
  - the measured supply leakage, which would widen the 8.8 µA margin.

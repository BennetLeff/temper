# Candidate 39: S4 gate network (68 Ω 2512 R_on + Cgs 4.7 nF), built as stage 42 (native21s42)

**Verdict: card REJECT against s41, on `b3_laminate_margin_K` only** (−25.2 → −30.6 K; tolerance 1.0 K). Board native21s42
`9e075b4b`, chain CHAIN_DONE with no spine owner (SPINE_LOCK PASS). Every other gate matches s41.
- The regression is the gate network's own heat, not the layout. With the stage-41 heat file on the s42 copper, the
  laminate rows read −26.5 / −22.8 K (section 4).
- The network adds +0.68 W of board heat at the c28 heat basis. Most of it sits at the FET row: R_on 0.140 → 0.217 W ×4,
  R_off 0.036 → 0.063 W ×4.
- `b3_rated_part_margin_K` improves −64.1 → −33.4 K: the gate resistors now have a 1 W 2512 rating.
- **The bay-55 °C still-air ceiling falls 21.1 → 20.0 A** (laminate + film). For the first time it is also a ceiling for
  every gated row: s41's 1206 gate resistors failed even with no tank current.
- **The datasheet-ledger violation moves:** IPW65R018CFD7 (S4 diode limits, DECISIONS 49) becomes PARTIAL.
  25121WF680JT4E (the new R_on) is a VIOLATION at the 22 A c22 ceiling: 109 % of its derated power against the 80 % rule.

```
REJECT native21s42 vs validation-results/10-benchmark/scorecard-native21s41.json: cheaper ['jlc_assemblable_share_500', 'jlc_assemblable_share_5'], better ['b3_rated_part_margin_K', 'track_right_angle_corners', 'track_any_angle_mm']; b3_laminate_margin_K worse: -30.6 vs benchmark -25.2 (tolerance 1.0)
```

Built on the board of record s41 (`d4b2445c`, DECISIONS 53, integration `18187575d`) on branch
`claude/native21-c39-gate-network`, as DECISIONS 54 specifies. The design call (adopt, override the laminate reject,
commission 20 A still air at bay 55 °C) is in `DECISIONS-DRAFT.md`. The hardware capacitive-mode detector request is in
`CONTROLLER-REQUEST.md` (requirement only).

## 1. Results (card and gates)

| Metric | s41 | s42 | Note |
|---|---|---|---|
| Board sha256 | `d4b2445c` | `9e075b4b` | chain `$R/c42b`, `R=worktrees/runs-native21/s42` |
| DRC errors / unconnected | 0 / 0 | 0 / 0 | `passes42.sh` j1 clean |
| Barrier / RES_A creepage | PASS / 13.375 mm | PASS / 13.375 mm | |
| D5 min (HOT-SELV / HOT-PE) | 8.047 / 8.507 mm | 8.047 / 8.507 mm | |
| SPINE_LOCK | PASS (no owner) | PASS (no owner) | |
| Enclosure fit | 403 / 0 / 0 / 405 / 0 | 403 / 0 / 0 / 405 / 0 | RUST 0 |
| JLC DFM | PASS, 754 vias | PASS, **753** vias | R10's redundant sw_a stub via removed |
| Bypass / return path | PASS / 15 opens | PASS / 15 opens | |
| Kelvin band low / high | 67.77 / 116.44 A | 67.77 / 116.44 A | shift −2.123 A, unchanged |
| OCP pickup (F8, any-phase ×1.5) | 4.17 A | 4.17 A | `coil-pickup/s21b/result-s42.json` |
| Fuse-copper min ratio | 0.993 | 0.993 | `s42_necks.json`; leg-A row 2.869 → 3.882 mm (section 3) |
| Task 04 | 39 / 0 failed | 39 / 0 failed | bus_p span 2.835 → 2.857 %; leg_a 18.7 A 0.510 → 0.487 W |
| **B3 laminate margin** | **−25.2 K** | **−30.6 K** | `b3_ratings` FAIL on both; section 4 |
| **B3 rated-part margin** | **−64.1 K** | **−33.4 K** | worst row R12 terminal derating, c28, 1206 → 2512 |
| B3 advisory margin | −6.9 K | −7.1 K | |
| B3 peaks (legacy, not compared) | 165.1 / 126.5 °C | 165.3 / 147.2 °C | nominal_h10 / c28_h25. The legacy c28_h25 peak is now R10's 2512 (61.5, 15.5): the legacy model has no package network and puts 0.217 W into the pad cells |
| BOM lines / placements | 92 / 351 | 93 / 351 | −RS-06L8R20FT, +25121WF680JT4E, +GRM1885C1H472JA01D |
| Parts $ at 5 / 500 boards | 306.62 / 202.21 | 306.76 / 202.32 | +$0.14 / +$0.11 |
| JLC extended lines | 66 | 67 | both new parts JLC extended, in stock |
| Buildability (assemblable share 5 / 500) | 0.967 / 0.848 | 0.968 / 0.849 | `sourcing/SNAPSHOT-2026-10-15.csv` gains the two rows |
| Ledger (VERIFIED / PARTIAL / UNAUDITED / VIOLATION) | 3 / 29 / 59 / 1 | 3 / 31 / 58 / 1 | violation IPW65R018CFD7 → 25121WF680JT4E (section 5) |
| Track corners / any-angle | 101 / 680.3 mm | 100 / 675.0 mm | |

**B3 rows near the gate network** (`b3-ratings/margins.json`, bay 55 °C, K; s41 is restated on the updated model and is
bit-identical to its committed margins):

| Row | c22 s41 | c22 s42 | c28 s41 | c28 s42 |
|---|---|---|---|---|
| Laminate, 1 mm block | +1.2 | **−6.8** (at R12's gate pad, 45.5 / 15.5) | −25.1 | −30.6 (at R5.4) |
| Laminate, FET row | +1.1 | −3.5 | −25.2 | −30.6 |
| C40 (MKP Top,max 110 °C) | −2.7 | −6.0 | −24.6 | −27.8 |
| C38 / C41 / C39 | +0.1 / +2.4 / +5.8 | −2.0 / −1.2 / +4.6 | −22.2 / −15.1 / −15.1 | −24.1 / −18.8 / −16.2 |
| R_on terminal derating (worst; 1206 0.140 W → 2512 0.217 W) | −39.6 (R12) | −6.2 (R10) | −64.1 (R12) | −33.4 (R12) |
| R_on element (worst) | +18.3 (R12) | +11.5 (R10) | −8.0 (R12) | −16.3 (R12) |
| R_off terminal derating (R58, 0.036 → 0.063 W) | +19.4 | +1.8 | −7.7 | −25.4 |
| R_off element (R58) | +34.3 | +26.7 | +8.1 | +0.6 |
| R5 terminal / element | +31.0 / +36.2 | +25.4 / +31.6 | −9.1 / −0.3 | −14.6 / −4.8 |
| U26 / U41 / U42 Tj | +12.3 / +30.2 / +24.7 | +9.4 / +25.3 / +19.3 | +7.6 / +28.1 / +20.0 | +4.8 / +23.2 / +14.6 |

## 2. The parts (DECISIONS 54)

- **R10 / R12 / R18 / R20 → 68 Ω 1 % 1 W 2512, UniRoyal 25121WF680JT4E** (JLC C50371, 3,131 in stock 2026-10-15). It
  replaces RS-06L8R20FT (8.2 Ω 1206). Ratings are from UniRoyal Thick Film Chip Resistors V.3, Feb.12,2019:
  - 1 W at 70 °C (p.4/9);
  - derating to 0 at 155 °C, and −55 to +155 °C (p.5/9);
  - 200 V working voltage (p.5/9);
  - short-time overload 2.5 × RCWV (p.6/9).
- **C55 / C56 / C62 / C63 → 4.7 nF 5 % 50 V C0G 0603, Murata GRM1885C1H472JA01D** (JLC C85980, 76,738 in stock). It
  replaces C0603C102J5GACTU (1 nF) on those four. Ratings are from Murata catalog C02E: PDF p.88 (rated voltage) and p.8
  (5C = C0G, −55 to 125 °C).
- Source: `elec/src/parts.ato` gains `R68Gate2512` / `C4n7C0G0603`, and `power_stage_120v.ato` uses them. Compiled with
  atopile 0.2.69 offline and refrozen to `frozen/` and `native-21/frozen/`.
  - Only R10 / R12 / R18 / R20 and C55 / C56 / C62 / C63 change.
  - 183 nets, identical; 351 components, designators kept.
- `audit.rs`:
  - the identities move to the new MPNs;
  - new test `stage42_gate_network_holds`;
  - 84 / 84 tests pass, audit PASS on the build and on frozen.
- `native-21/verification/verify_source.py` asserts the new MPNs, footprint and Cgs (`source-check.json`).
- The footprint is KiCad `Resistor_SMD:R_2512_6332Metric` (IPC land, pads 1.5 × 3.35 mm). UniRoyal's recommended land is
  8.2 / 3.3 / 1.6 mm, but the IPC land is kept for the library and the CPL audit. That audit passes R10–R20 at 270°
  (JLC chip models, 0° = pads along X).

## 3. Layout (stage 42, `patches21.edit_base42`, `place.py` STAGE42 block)

Method:
- The frozen s41 copper (`INCR21_FROZEN`; base `git show 18187575d:…/native-21/layout/copper.json`, sha 77f3e994) is
  edited before load by `edit_base42`. `incr21.load` calls it after `edit_base41`.
- Then the usual open-pair passes run (`passes42.sh`). j1 was clean: 0 unconnected, 0 errors, barrier 0.

**Why the gate is re-laid.**
- The 2512 sits on the old 1206 axis (x = g, the FET gate pin's x). Its pads (1.5 × 3.35 mm, x g ± 1.675) cover the old
  gate run at x g − 1.35.
- A run down the resistor's west side, to y 20, would come within 3.2 mm of the other potential group's R_off / OUT
  copper (R54 / R57 at x g − 5.5).
- A B.Cu jumper was rejected: its two vias would cut 3.2 mm antipads into the In1 hv_ret / In2 bus_p planes under the
  FET row.

**Edits** (groups g = 62.6 / 44.6 / 4.5 / 22.5: R10 / R12 / R18 / R20):
1. **R_on turned 180° on the same axis.** Rotation 270, centre y 12.6 → 12.4: pad 1 (OUT) north at y 9.4375, pad 2
   (gate) south at y 15.3625. The 0.2 mm move north keeps the 2512 courtyard 0.08 mm clear of the PMEG (D6–D9) courtyard.
2. **Gate run.**
   - The FET pin's 0.8 mm stub stops at y 6.2.
   - Then 0.4 mm on a 45° step to x g − 2.15, down to y 14.55, and into pad 2's north-west corner.
   - Every point keeps ≥ 3.4 mm from the other group's R_off pad and OUT track.
   - Below pad 2 the old run (x g − 1.35, to the PMEG anode and Cgs) is unchanged.
3. **OUT run.** The old run along y 14.3 now turns north at x g + 2.4 and runs up x g + 1.0, under the resistor body, to
   pad 1. Along y 14.3 it would have passed 0.15 mm from pad 2.
4. **Pull-downs R11 / R13 / R19 / R21** move 0.5 mm west (to open the channel) and 0.5 mm north. Moving north keeps their
   gate pad 3.2 mm from the other group's OUT run. The pull-down branch joins the channel at the gate pad's y.
5. **Pull-down source vias.**
   - R19 (sw_b) and R21 (leg_ret) move 0.5 mm west with their pull-downs. R21's In2 leg_ret run follows its via.
   - **R11 (leg A high side) is turned 180°** (gate pad north) and its sw_a via goes to (59.6, 13.3), south-east of the
     pad. The first build left that via at (59.4, 9.7). There, its 3.5 mm In1 antipad narrowed the "Q3 source → R5"
     leg_ret neck from 2.869 to 2.415 mm, and `s42_necks.json` read min ratio 0.882 against s41's 0.993.
   - At (59.6, 13.3) the via clears the gate channel by 0.35 mm and the other group's OUT run by ≥ 3.4 mm. The leg-A neck
     is 3.882 mm (wider than s41), min ratio 0.993 again, and task 04's leg_a loss falls 4.6 %.
6. **R10's second sw_a via** at (60.925, 11.275), a redundant stub of R11.2, is removed because it sits in the new channel.

Other passes that changed:
- The first build (`$R/c42`, board `5edb711a`) had R11's via at (59.4, 9.7). Its B3 rows are within 0.4 K of the built
  board.
- Two earlier pass attempts failed and were fixed before j1:
  - placement-stage29.json overrode the put()-section rotation, so the rotation moved to the STAGE42 block;
  - R21's In2 run dangled until it followed the moved via.

## 4. Thermal

**Model changes (s41 rows unchanged).**
- `b3/make_heat_sources.py` reads R_on and Cgs from `native-21/frozen/resolved-components.json`.
  - The FET's own charge stays 382.6 nC (deck worst S2).
  - Cgs 4.7 nF adds 61 nC per edge. That is the gate-network study's figure (01-switching-parasitics/gate-network-2026-10-15
    README section 3a, "R_on power"). An unlisted Cgs value raises instead of extrapolating.
  - The extra charge is split without Rg,int, because Cgs is on the board side of it.
- `b3-convergence/thermal_body.py` gains a `chip2512` package network.
  - r_pad 37.6 K/W, from UniRoyal V.3 p.4/9 and p.5/9.
  - `part-bodies.json` carries the four 2512 bodies.
- `b3-ratings/b3_ratings_gate.py` is package-aware: 2512 → 1 W line; 1206 → 0.25 W and the stage-29 strings unchanged.
  An unrated package stops the gate.
- `b3-ratings/run_basis.py` gains `--bay-c / --runs / --out`; the defaults are unchanged.
- **Control:** s41 re-solved on the updated model gives margins bit-identical to the committed s41 margins
  (`results/margins/s41-updated-model.json`), so the s41 card does not move.
- **Control:** `scripts/gate_pkg_control.py` passes on s41 and s42 runs (`results/gate_pkg_control_s4{1,2}.json`).
  - It checks P1 package strings, P2 limit formula, and P3 that relabelling 1206 → 2512 gains exactly 85 P (1/0.2 − 1/0.8) K.
  - P4: an unrated package raises.

**Heat at the c28 basis** (`b3/inputs/native21-board-heat-sources-c28.json`, 60 kHz window top, +0.684 W):

| Rows | s41 | s42 |
|---|---|---|
| R_on R10 / R12 / R18 / R20 (each) | 0.140 W | 0.217 W |
| R_off R53 / R54 / R57 / R58 (each) | 0.036 W | 0.063 W |
| Driver U1 / U2 (each) | 0.113 W | 0.103 W (more of the charge energy now goes to the external R_on) |
| RECOM U41 / U42 (each) | 0.953 W | 1.029 W (+16 % gate charge) |
| U26 / PS2 | 0.852 / 1.262 W | 0.903 / 1.348 W |

R_on at 0.217 W is the charge-split upper bound. The gate-network study's simulated R_on power is ~0.17 W at 444 nC.

**Copper vs heat** (`scripts/heat_swap.sh`: s42 copper with the s41 heat file; `results/margins/s42-copper-s41-heat.json`):

| Row (K) | s41 | s42 copper, s41 heat | s42 |
|---|---|---|---|
| c22 laminate block / FET row | +1.2 / +1.1 | +4.3 / +4.0 | −6.8 / −3.5 |
| c28 laminate block / FET row | −25.1 / −25.2 | −26.5 / −22.8 | −30.6 / −30.6 |
| c22 / c28 C40 | −2.7 / −24.6 | −3.0 / −24.9 | −6.0 / −27.8 |
| c22 / c28 R_on terminal derating (worst) | −39.6 / −64.1 | +15.1 / −6.7 | −6.2 / −33.4 |

- **The layout is not the cause.** The copper alone moves the FET row +2.4 K and the c22 block +3.1 K. The 2512's larger
  pads spread R_on's heat better than the 1206.
- The c28 block row moves −1.4 K. Its raw 0.25 / 0.5 mm peaks are within 0.2 K of s41's (146.0 / 144.6 against 146.1 /
  144.4 °C); the shift is the mesh extrapolation.
- **The heat is the cause:**
  - c22 −11.1 K at the block. With the gate heat on, the c22 peak moves to R12's gate pad (45.5, 15.5): R12's own 0.217 W.
  - c28 −4.1 / −7.8 K (block / FET row).

**Still-air ceilings** (`scripts/ceilings.py`, c36's method: each row is linear in I_trip² between c22 and c28; the
ceiling is the zero crossing). Control: on c36's s40 margins it gives 21.5 / 21.0 A, as c36 reports.

| Bay | Board | Laminate | Laminate + film | Gate R_on | Gate R_off | All gated rows |
|---|---|---|---|---|---|---|
| 55 °C | s41 | 22.3 A | 21.1 A | 0.0 A (1206 fails with no tank current) | 26.4 A | 0.0 A |
| 55 °C | s42 copper, s41 heat | 22.9 A | 21.0 A | 24.6 A | 26.2 A | 21.0 A (C40) |
| 55 °C | **s42** | **20.0 A** (block) | **20.0 A** | **20.0 A** (R10) | 22.4 A (R58) | **20.0 A** |
| 61 °C | **s42** (solved at bay 61, not shifted; `results/margins/s42-bay61.json`) | 18.5 A | 18.4 A (C40) | 18.3 A (R10) | 21.4 A | **18.3 A** |

- The bay-61 rows come from `run_basis.py --bay-c 61`, a full four-solve basis with the FET case tie at bay 61. That is the
  construction c36's control asked for in place of a flat shift.
- The package control (`gate_pkg_control.py`) was run at bay 55 only.

## 5. Ledger and sourcing

- `native-21/verification/datasheet-ledger/ledger.json`:
  - **IPW65R018CFD7 VIOLATION → PARTIAL.** The S4 stresses are now 49.7 V/ns and 244 A/µs
    (gate-network-2026-10-15/results/full.md:15). The maximum-Qrr basis (106 V/ns on the nearest tested network,
    s4screen.md:80) is a failing gap-severity check until the D-8 bench. The history rows are renamed "as built
    s29–s41".
  - **25121WF680JT4E (new, POWER): VIOLATION.**
    - c22 derated-power check: R10's terminal is at 138.1 °C (B3 c22_h10, bay 55 °C), where the curve allows 0.199 W.
      0.217 W is 1.09 × that, against the 0.8 rule. This is the same rule as the B3 row R10 −6.2 K.
    - Element at c22: 143.5 / 155 °C, passes.
    - c28 element 171.3 °C is a gap: c28 is not a supported ceiling (DECISIONS 53), and the c28 terminal (165.3 °C) is past
      the curve's zero-power point.
    - Working voltage 17 / 200 V passes.
    - Edge step against the 5 s overload is a gap (no pulse rating is published).
  - **GRM1885C1H472JA01D (new, SIGNAL): PARTIAL.** 17 V / 50 V passes the 50 % rule. The cap's own temperature is not
    modelled: its only bound is the c22 FET-row copper (133.5 °C against 125 °C), recorded as a failing gap.
  - RS-06L8R20FT is removed, and C55 / C56 / C62 / C63 leave C0603C102J5GACTU.
  - `gate.py`: 93 / 93 lines, 3 / 31 / 58 / 1. `tests/test_gate.py` KNOWN_VIOLATIONS → ["25121WF680JT4E"], 0 failures.
- Sourcing:
  - `08-manufacturing-package/native-21/scripts/apply_lcsc.py` maps the two MPNs to C50371 / C85980.
  - `sourcing/STOCK-2026-10-13-addendum-s42.csv` adds the two stock rows.
  - The JLC part-API records are in `sourcing/study-2026-10-15/scripts/jlc-raw/` (detail_C50371, detail_C85980).
  - `study-2026-10-15/run_all.sh` builds `snapshot/s42/SNAPSHOT-s42.csv` and merges it into `../SNAPSHOT-2026-10-15.csv`,
    keeping every earlier row the s42 BOM no longer has. Every row of an MPN common to s41 is unchanged.
- Datasheets read (not committed):
  - UniRoyal V.3 (LCSC copy, sha256 11cd644d…);
  - Murata C02E (sha256 9a8a89cd…).

## 6. Records

**Files:**
- Source: `elec/src/parts.ato`, `power_stage_120v.ato`, `frozen/*`, `native-21/frozen/*`, `audit.rs`,
  `native-21/verification/verify_source.py`.
- Layout: `native-21/layout/place.py` (STAGE42 block), `parts.json`, `patches21.py` (`edit_base42`, `S42_*`), `incr21.py`.
- Kelvin scripts: native21s42 DIVIDER / BAND_BEFORE / FLOOR and the pinned board. `b3/run_study.py` GEOM points at s42.
- Thermal model: `b3/make_heat_sources.py`, `b3-convergence/thermal_body.py`, `b3-convergence/inputs/part-bodies.json`,
  `b3-ratings/b3_ratings_gate.py`, `b3-ratings/run_basis.py`.

**Scripts** (`scripts/`, study aids, not gates):
- `ceilings.py`: still-air ceilings with the gate rows.
- `gate_pkg_control.py`: package-aware gate-row controls.
- `heat_swap.sh`: the copper-vs-heat separation.

**Results** (`results/`):
- `margins/s42.json` (= the committed margins);
- `margins/s42-bay61.json`;
- `margins/s42-copper-s41-heat.json`;
- `margins/s41-updated-model.json`;
- `gate_pkg_control_s41.json`, `gate_pkg_control_s42.json`.

**Open items:**
- **D-8 bench:** S4 dv/dt and diF/dt at maximum Qrr (DECISIONS 54). It decides the maximum-Qrr basis.
- **Gate-row heat:** at c22 the hottest laminate is R12's own gate pad. The levers are local spreading copper on the R_on
  pads (both nets are low-voltage to their own group), airflow over the FET row, or a lower window top. None is built
  here.
- **R_on power basis:** the heat file's charge split (0.217 W) against the study's simulated ~0.17 W. At 0.17 W the c22
  derating limit rises to 136.9 °C, against today's 138.1 °C estimate, which would itself fall with the lower heat. That
  case is not solved here. A bench gate-row IR reading settles it.

## 7. Reproduce

```
R=/Users/bennet/Desktop/temper/worktrees/runs-native21/s42
git show 18187575d:zapote/power-stage-120v/native-21/layout/copper.json > $R/base-s41.json     # sha 77f3e994
sh validation-results/11-candidates/c39-gate-network/passes42.sh $R/base-s41.json $R/p42b
TASK04_WORKERS=4 bash native-21/layout/gates/chain.sh native21s42 $R/p42b/j1 $R/c42b
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s42)
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=$PWD/../../../../native-21/verification/native21s42-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s42.json && git checkout -- result.json)
(cd validation-results/04-board-current-thermal/round5-native21/b3-ratings && \
    python3 run_basis.py --bay-c 61 --runs $R/runs-bay61 --out ../../../11-candidates/c39-gate-network/results/margins/s42-bay61.json)
bash validation-results/11-candidates/c39-gate-network/scripts/heat_swap.sh $R/runs-swap \
    $PWD/validation-results/11-candidates/c39-gate-network/results/margins/s42-copper-s41-heat.json
python3 -I validation-results/11-candidates/c39-gate-network/scripts/gate_pkg_control.py \
    validation-results/04-board-current-thermal/round5-native21/b3-ratings/runs
python3 -I validation-results/11-candidates/c39-gate-network/scripts/ceilings.py validation-results/11-candidates/c39-gate-network/results/margins/*.json
(cd native-21/verification/datasheet-ledger && python3 -I gate.py; python3 -I tests/test_gate.py)
(cd validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15 && bash run_all.sh)
python3 -I native-21/layout/gates/scorecard.py native21s42 $R/c42b --audit PASS --json validation-results/10-benchmark/scorecard-native21s42.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s42.json \
    --compare validation-results/10-benchmark/scorecard-native21s41.json
```
The s41-on-updated-model control: check out s41's copper export and a4 fields, then run `run_basis.py --runs DIR --out
FILE`. The result was saved before the s42 chain overwrote the a4 fields.

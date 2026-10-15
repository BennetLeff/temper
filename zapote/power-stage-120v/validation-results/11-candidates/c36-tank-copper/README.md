# Candidate 36: tank / FET-row copper at R5, built as stage 41 (native21s41)

**Verdict: ACCEPT against s40** (`results/compare.txt`). Board native21s41 `d4b2445c`, chain CHAIN_DONE with no spine
owner (SPINE_LOCK PASS). Every gate matches s40. `b3_laminate_margin_K` improves from −38.3 to −25.2 K. `b3_ratings` still
fails on both boards. On s41 it fails only on candidate 39's gate-resistor derating row (−64.1 K, unchanged) and on c28
rows that no outer-copper change on this stack-up can reach (section 3). Parts, BOM, cost and vias are identical to
s40. Ledger violations stay at 1 (IPW65R018CFD7).

```
ACCEPT native21s41 vs validation-results/10-benchmark/scorecard-native21s40.json: cheaper [], better ['b3_laminate_margin_K']
```

Built on the board of record s40 (`33ed17f3`, DECISIONS 52, integration `30773ebe5`) on branch
`claude/native21-c36-tank-copper`. The first build was on s38 (the brief's base). Section 5 shows it, as a cross-check.
Scored against `../../10-benchmark/scorecard-native21s40.json`. DECISIONS 51 set the targets (tank-copper Joule factor
f ≤ 0.895 at c22 and ≤ 0.369 at c28, laminate and film rows, bay 55 °C).

| Goal (DECISIONS 51) | Stage 41 |
|---|---|
| c22 laminate (1 mm block, FET row) ≥ 0 K | **Met.** −2.6 / −1.7 → **+1.2 / +1.1 K** |
| c22 film caps C38–C41 ≥ 0 K | **C40 not met** (−3.2 → −2.7 K). C38 −0.2 → +0.1, C39 / C41 pass |
| c28 laminate and film ≥ 0 K | **Not met:** laminate −38.3 → −25.2 K, C40 −24.6 K. No 2 oz outer-copper layout reaches it (section 3) |
| Still-air ceiling (laminate / + film) | 21.5 / 21.0 A → **22.3 / 21.1 A** (bay 55 °C; `scripts/ceilings.py`) |
| 0.5 mΩ shunt (DECISIONS 51 second column) | **Evaluated, not adopted:** OCP pickup and band fail without an OCP front-end rework (section 4) |
| Gate resistors (R12 1206 derating) | Candidate 39's. Reported apart: −39.7 → −39.6 K (c22), −64.1 → −64.1 K (c28) |

## 1. Results (card and gates)

| Metric | s40 | s41 | Note |
|---|---|---|---|
| Board sha256 | `33ed17f3` | `d4b2445c` | chain `$R/c2`, `R=worktrees/runs-native21/s41` |
| DRC errors / unconnected | 0 / 0 | 0 / 0 | `passes41.sh` j1 clean |
| Barrier / RES_A creepage | PASS / 13.375 mm | PASS / 13.375 mm | |
| D5 min (all / HV) | 8.047 / 8.507 mm | 8.047 / 8.507 mm | |
| SPINE_LOCK | PASS (no owner) | PASS (no owner) | SELV side untouched |
| Enclosure fit (in / collide / ... ) | 403 / 0 / 0 / 405 / 0 | 403 / 0 / 0 / 405 / 0 | RUST 0 |
| JLC DFM | PASS, 754 vias | PASS, 754 vias | two vias moved, none added |
| Bypass check | PASS | PASS | same rows |
| Return-path open changes | 15 | 15 | |
| Kelvin band low / high | 67.77 / 116.44 A | 67.77 / 116.44 A | shift −2.123 A, unchanged (Kelvin copper untouched) |
| OCP pickup (F8, any-phase ×1.5) | 4.17 A | 4.17 A | `coil-pickup/s21b/result-s41.json` |
| Fuse-copper min ratio | 0.993 | 0.993 | `s41_necks.json`; the hv_ret row is in section 2 |
| Task 04 | 39 / 0 failed | 39 / 0 failed | bus_p span 2.835 % |
| **B3 laminate margin** | **−38.3 K** | **−25.2 K** | `b3_ratings` FAIL on both; worst gated row R12 derating (candidate 39) |
| B3 rated-part margin | −64.1 K | −64.1 K | R12 1206 terminal derating, c28 |
| B3 peaks (legacy, not compared) | 165.4 / 136.7 °C | 165.1 / 126.5 °C | nominal_h10 / c28_h25 |
| EMI / touch / CMTI, parts, BOM, cost | | unchanged | no part or netlist change |
| Ledger | 3 / 29 / 59 / 1 | 3 / 29 / 59 / 1 | no part change, so no ledger change |

**B3 ratings rows near R5** (`b3-ratings/margins.json`, bay 55 °C, K; `results/variants.json`):

| Row | c22 s40 | c22 s41 | c28 s40 | c28 s41 |
|---|---|---|---|---|
| Laminate, 1 mm block | −2.6 | **+1.2** | −38.3 | −25.1 |
| Laminate, FET row | −1.7 | **+1.1** | −28.2 | −25.2 |
| C40 (MKP Top,max 110 °C) | −3.2 | −2.7 | −25.4 | −24.6 |
| C38 | −0.2 | +0.1 | −22.5 | −22.2 |
| C41 | +1.8 | +2.4 | −16.1 | −15.1 |
| C39 | +5.6 | +5.8 | −15.4 | −15.1 |
| R5 terminal | +23.6 | +31.0 | −20.8 | −9.1 |
| R5 element | +31.1 | +36.2 | −8.6 | −0.3 |
| *Gate R (candidate 39):* R12 1206 element | +15.7 | +18.3 | −10.2 | −8.0 |
| *Gate R (candidate 39):* R12 1206 terminal derating | −39.7 | −39.6 | −64.1 | −64.1 |

**Still-air ceiling** (`scripts/ceilings.py`, bay 55 °C). Each row's margin is linear in I_trip² between c22 and c28;
the ceiling is the zero crossing. Control: on s38 / s40 this gives 21.5 A (laminate) and 21.0 A (laminate + film),
the same as `refine-2026-10-15/results-s38/targets.json` (DECISIONS 51).
- **Laminate: 21.5 → 22.3 A.** The FET row limits (22.28 A), then the 1 mm block (22.31 A).
- **Laminate + film: 21.0 → 21.1 A.** C40 limits (21.14 A), then C38 (22.03 A).
- Gate-R element rows: 25.8 → 26.3 A. The gate-R derating row has no ceiling with 1206 parts (candidate 39).
- Bay 61 °C is not computed: a flat −6 K shift misses the control (19.9 against 20.4 A). That needs `targets.py` on an
  s41 superposition basis.

**Task 04 (power copper, s40 → s41).**
- leg_a 18.7 A: 1.72 → 1.46 mΩ, 0.600 → 0.510 W. The In1 neck and the B.Cu leg_ret pour do this.
- leg_b: 0.078 → 0.071 W.
- sw_b high / low: 2.286 / 2.260 → 2.259 / 2.234 W.
- hv_mixed a / b: 1.712 / 1.076 → 1.778 / 1.138 W (+3.9 / +5.8 %), and hv_dc +2.6 %. This is the cost of moving two
  R5.4 vias north-west, so the hv_ret current runs further on In1 to the trunk. That heat lands away from the FET row
  and C40, and the c22 / c28 rows above include it.
- bus_p span 2.835 %, unchanged.

## 2. Layout (stage 41 copper, `patches21.edit_base41`)

Method:
- The frozen s40 copper (`INCR21_FROZEN`) is edited before load by `edit_base41`, which reads
  `native-21/layout/stage41_pours.json`. `scripts/pours41.py --variant move` generates that file from the s40 all-copper
  export and `copper.json`, keeping every other-net item and zone outline at its rules21 clearance.
- Then the usual open-pair passes run (`passes41.sh`). j1 was clean: 0 unconnected, 0 errors, barrier 0.
- Nothing changes in the LS pocket, the HS-B band, the gate-driver output networks or the gate resistors. None of the
  stage-40 copper edits touches this area: they are the n_hb bank at y ≥ 30.6 and the U41 / U42 pours at y 45–65.

**Where the heat came from** (s38, c22; `results/adjoint-s38.json`; reciprocity solve, 0.5 mm):
- Hot spot at R5.4 (38.5, 15.5): R5's own 0.53 W gives 15.2 K, the sw_b B.Cu lane 12.7 K, hv_ret 8.5 K, leg_a In1
  4.3 K, sw_a_low 3.0 K, bus_q5 2.5 K.
- The FET-row maximum sits at R12's pad (45.25, 11.25).
- C40's drivers: sw_b 11.9 K, hv_ret 5.3 K, R5 4.2 K, its own heat 3.85 K.
- So the copper had to spread R5's heat and take sw_b's pinch away from R5.4. Before, the sw_b lane passed 4.4 mm wide
  between R5.4 and C40.2's antipad.

**Edits:**
1. **F.Cu hv_ret spreader.** The 3.8 × 3.6 mm island at R5.4 becomes an 86 mm² pour (x 34.3–43, y 13.3–25.5) between
   the LOW-group gate runs at x 35.95 and x 43.25. It stops 1.5 mm short of C40.2. A version reaching C40.2 warmed C40
   by 0.75 K, because C40's lead was then tied to R5.4's heat.
2. **F.Cu leg_ret.** R5.1's pour reaches east to Q3.1 (y ≤ 10.4, 145 mm²).
3. **B.Cu leg_ret (new, 106 mm²).** It covers R5.1's via field and Q6.3, 3.2 mm from the sw_b / sw_a outlines.
4. **In1 leg_ret neck.** The leg-A neck under Q3.2's antipad, 2.83 mm wide at (50.05, 11.07), held task 04's hottest
   In1 cells. It widens to y 14.7 between the Kelvin run (x 42.2) and x 58.
5. **Two R5.4 hv_ret vias move north-west**, (37.05, 15.6) → (34.95, 14.6) and (37.95, 15.0) → (35.75, 16.25), and the
   **sw_b B.Cu lane rises over R5** (outline unioned with box x 33–42, y 15.7–19.4). The drill count in R5.4's field
   stays at six, so the F1 fusing row keeps its via-field I²t (2341.5).

**Fuse-copper rows.**
- Row "R5 → BR1−" (hv_ret): neck 3.103 → 2.888 mm, at the new via positions. Conductor I²t 2492 → 2159 A²s against
  F1's 1710 clearing I²t, ratio 1.26.
- Row "Q3 source → R5" (leg A, leg_ret): neck 2.834 → 2.869 mm, I²t 2080 → 2130 A²s.
- min ratio 0.993 (BR1+ → Q2, terminal-limited), unchanged.

## 3. Variants and what-ifs (all on the s40 base, `scripts/basis_variant.py`, `results/margins/*.json`)

Every variant ran the full B3 basis: four solves, c22 / c28, 0.25 / 0.5 mm, and the gate. The task-04 rows on the
nets the stage touches were re-solved on the variant's copper (`scripts/task04_variant.py`).

| Variant | c22 laminate min | c22 C40 | c28 laminate min | c28 C40 | ceiling lam / +film |
|---|---|---|---|---|---|
| s40 | −2.6 | −3.2 | −38.3 | −25.4 | 21.5 / 21.0 A |
| pours (edits 1–4, vias and sw_b lane as s40) | +0.3 | −2.7 | −25.3 | −24.6 | 22.1 / 21.1 A |
| add (pours + two more R5.4 vias) | +0.3 | −2.7 | −25.4 | −24.5 | 22.1 / 21.1 A |
| **move (built, = s41)** | **+1.1** | **−2.7** | **−25.2** | **−24.6** | **22.3 / 21.1 A** |
| move + R5 0.5 mΩ (what-if; `basis_variant.py ... --r5 0.5`) | +2.0 | −0.4 | −18.8 | −20.8 | 22.7 / 21.9 A |
| move + 3 oz outer (what-if, not orderable; `NATIVE21_STACKUP=scripts/stackup-3oz.json`, task 04 re-solved) | +11.1 | +4.0 | −9.6 | −13.4 | 25.4 / 23.5 A |

**Decision: build "move".** It is best on the c22 block (+1.2 against +0.3) and on the c28 laminate minimum, and its
cost is only the hv_mixed loss above.

**Why the c28 and C40 targets are not met on this stack-up.**
- **3 oz outer copper is not offered on this build.** Even that what-if leaves c28 at −9.6 K.
  - JLC capabilities page, fetched 2026-10-15 (https://jlcpcb.com/capabilities/pcb-capabilities): multilayer outer
    copper "1 oz / 2 oz".
  - JLC copper-weight article (https://jlcpcb.com/help/article/jlcpcb-copper-weight): 2.5 / 3.5 / 4.5 oz is "2-layer
    FR4 only"; inner 0.5 / 1 / 2 oz.
- **C40's remaining c22 gap (−2.7 K)** is mostly sw_b's lane loss (11.9 K of its rise) and its own 3.85 K. Only more
  sw_b copper area moves it: +4.0 K with 3 oz.
- **The 0.5 mΩ shunt** gives +2.3 K at C40. It is rejected in section 4.
- So on 2 oz outer copper, c22 C40 and all of c28 need what DECISIONS 51 leaves open: a lower commissioned ceiling, or
  airflow.
- The adjoint data (`results/adjoint-*.json`) shows no other copper lever. Outside the sw_b lane, the remaining rise at
  the block is spread over six sources of 2.5–15 K.

## 4. 0.5 mΩ shunt (evaluated, not adopted; `scripts/shunt_half.py`, `results/shunt_half.json`)

The part is Bourns CSS2H-2512R-L500F, 0.5 mΩ. The datasheet is the one already in the ledger: CSS2H, REV 06/17/20 p.1,
sha ae54630a. It is the same footprint. Its ratings are 6 W at 70 °C (terminal) / 3 W at 130 °C, ±100 ppm/K and
−55 to 170 °C. The board gains +0.9 K at the c22 laminate and +6.4 K at c28 (table above). It fails on protection:
- **OCP pickup 4.17 → 8.35 A**, over the 6.5 A gate. Halving the shunt voltage doubles the pickup referred to amps.
- **OCP band.**
  - Divider re-chosen for the same nominal trip (E192 12.1 k / 11.7 k): 41.4–129.1 A before the Kelvin shift, low
    corner 37.2 A after it. That fails the 64.17 A floor.
  - Divider chosen to hold the floor (12.7 k / 12.1 k): 77.2–167.3 A. The upper edge rises 51 A.
- **Kelvin shift −2.12 → −4.16 A.** Comparator offset ±4 mV becomes ±16 A.

Adopting it needs an OCP front-end rework (comparator offset class, divider, pickup loop), outside this candidate. R5
stays CSS2H-2512R-1L00F. `CONTROLLER-REQUEST.md` lists what the controller owner would change if a later candidate
adopts it. Today no controller constant reads R5.

## 5. Records

**Stage 41 on s38 (first build, superseded by the s40 rebase).** Board `ee8ad504`, CHAIN_DONE, SPINE_LOCK PASS (no
owner), every gate PASS. Laminate −38.0 → −24.9 K; card ACCEPT against s38. Logs and card are in `$R`:
`chain-s41-on-s38.log`, `card-s41-on-s38.json`, `margins-s41-on-s38.json`. On s40 the result is within 0.3 K of this.

**Files:**
- `native-21/layout/patches21.py` (`edit_base41`), `incr21.py` (calls it after `edit_base`), `stage41_pours.json`.
- Kelvin scripts: native21s41 DIVIDER / BAND_BEFORE / FLOOR and the pinned board.
- `b3/run_study.py` GEOM points at s41.
- Datasheet ledger: no change.

**Scripts** (`scripts/`; layout and study aids, not gates):
- `pours41.py`: generates the outlines.
- `variant.sh`: builds a variant (`S41_RUNS` = run root).
- `task04_variant.py`, `basis_variant.py`: variant task-04 rows and B3 basis.
- `adjoint.py`: reciprocity influence.
- `whatif.py`, `s41geo.py`: zone what-ifs on the body model.
- `rank.py`: task-04 heat near R5.
- `variants_table.py`: produces `results/variants.json`.
- `ceilings.py`: still-air ceilings.
- `shunt_half.py`: the 0.5 mΩ evaluation.

## 6. Reproduce

```
git show 30773ebe5:zapote/power-stage-120v/native-21/layout/copper.json > $R/base-s40.json     # sha 41674a55
python3 -I validation-results/11-candidates/c36-tank-copper/scripts/pours41.py --variant move
sh validation-results/11-candidates/c36-tank-copper/passes41.sh $R/base-s40.json $R/p41
TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s41 $R/p41/j1 $R/c2
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s41)
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=$PWD/../../../../native-21/verification/native21s41-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s41.json && git checkout -- result.json)
python3 -I native-21/layout/gates/scorecard.py native21s41 $R/c2 --audit PASS --json validation-results/10-benchmark/scorecard-native21s41.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s41.json \
    --compare validation-results/10-benchmark/scorecard-native21s40.json
python3 -I validation-results/11-candidates/c36-tank-copper/scripts/ceilings.py validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json
```

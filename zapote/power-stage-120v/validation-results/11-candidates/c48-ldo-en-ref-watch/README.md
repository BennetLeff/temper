# Candidate 48: LDO EN dividers, Q1 TPS70950, REF25 watchdog, BIAS_GOOD to J4.1, end-of-line pads (native21s48)

**Card: REJECT against s47 on cost alone** (parts_usd_at_500_v2 173.99 → 175.68, +$1.69 / board). Every gate passes,
including `pin_absmax` (0 failures: the four EN violations are gone, so it is now an ordinary gate) and `b3_ratings`
(release margin +1.0 K, R10, unchanged). Return-path opens 7 = 7, acute corners 22 = 22, fuse copper 0.993 = 0.993.
Board **23209767** (copper key 659ccad1), chain run 6 CHAIN_DONE (`runs-native21/s48/chain6.out`, `SPINE_OWNER=selv`).
Proposed: adopt with a cost override, as for stages 45 and 47.

Branch `claude/native21-s48-ldo-en-ref-watch` (one-writer layout lane, worktree `ps-selv`). Scope: OPEN-ITEMS S19 (TPS70950
EN tied to IN on all four LDOs), the U3 B3 heat row, and the B13 hooks H1 (REF25 watchdog), H2 (BIAS_GOOD readback) and
H3-H5 (end-of-line pads) from `11-candidates/fmea-s47-2026-10-15/README.md` section 6. The integrator decides
(`DECISIONS-DRAFT.md`, item 67).

```
REJECT native21s48 vs validation-results/10-benchmark/scorecard-native21s47.json: cheaper [], better []; costlier on ['parts_usd_at_500_v2'] with no performance gain; neither cheaper/simpler nor better than the benchmark
```

## 1. S19: EN of U3 / U37 / U38 / U39 from a divider, on the Q1 grade

**Finding (u3-286 analysis, S19):** all four TPS70950s had EN tied to IN, 15.46 V (U3) and 17.43 V (U37-U39), against
the 7 V EN absolute maximum. TI says "Do not connect EN to VIN" (SBVS186H 7.4 p.13).

**Floating EN was rejected**, although both datasheets allow it (SBVS186H 7.4 p.13; SLVSCE6D Table 4-1 p.3: "can be
left floating to enable the device. The maximum voltage must remain below 6.5 V"). The pull-up is 300 nA typical
(SLVSCE6D 5.5 p.5, no limit given). A leakage path of a few megohms to GND then pulls EN under VEN(HI) 0.9 V, which turns
the LDO off. That path is ordinary contamination on uncoated PD3 laminate, and this board is not coated. A divider of a
few tens of kilohms does not care.

**Divider: 100 k (0603WAF1003T5E) over 27 k (0603WAF2702T5E) on every LDO**, from its own IN to its own GND. Both are
existing BOM lines and JLC Basic parts. The arithmetic is in `audit.rs` `stage48_checks` and repeated in
`scripts/ledger48.py`:
- ±1 % plus 100 ppm/K over 100 K (25 °C to the 125 °C corner), adverse and untracked;
- plus a 1 µA pull-up bound times the divider's Thevenin resistance (21.3 k, +21 mV).

| LDO | IN (V) | EN at IN min | EN at IN max | EN at the span-OV corner | IN for EN = 6.5 V |
|---|---|---:|---:|---:|---:|
| U3 (HOT5) | V15_LS − OCP_KELVIN_P, 14.50–15.46 (16.68 at the corner) | 2.987 V | 3.413 V | 3.681 V | 29.5 V |
| U37 (LS monitor 5 V) | LS span, 16.575–17.43 (18.643) | 3.414 V | 3.845 V | 4.111 V | 29.5 V |
| U38 (HS-A) | HS-A span, same | 3.414 V | 3.845 V | 4.111 V | 29.5 V |
| U39 (HS-B) | HS-B span, same | 3.414 V | 3.845 V | 4.111 V | 29.5 V |

Every EN sits between VEN(HI) 0.9 V and the 6.5 V recommended maximum, with ≥ 2.1 V each way. The IN ranges are the S16
rail model (`s16-fmea-b-2026-10-15/scripts/bands.py:35-37`, `s20-286v-recite/README-analysis.md:149-151`).

**Grade: TPS70950QDBVRQ1 (TI SLVSCE6D rev. D, Aug 2025; LCSC C485909) on all four.**
- The plain part specifies ±1 % only to TA 85 °C (SBVS186H 6.5 p.5). The Q1 part holds ±1 %, 10 mV line and 50 mV load
  over −40 ≤ TJ, TA ≤ 125 °C (SLVSCE6D 5.5 p.5). That closes the U3 accuracy gap at 107 °C local.
- Same DBV pinout, IN 1 / GND 2 / EN 3 / NC 4 / OUT 5 (Table 4-1 p.3), and the same pads.
- Abs max VIN 32 V, VEN 7 V, TJ 150 °C (5.1 p.3). Recommended VIN 2.7–30 V, VEN 0–6.5 V, IOUT ≤ 150 mA, COUT 2–47 µF,
  TJ ≤ 125 °C (5.3 p.4). DBV ψJB 40.7 K/W (new chip; 38.4 legacy, 5.4 p.4). ICL ≥ 200 mA (5.5 p.5).
- Capacitors: COUT 10 µF 1210 on each (in 2–47 µF). CIN 100 nF: an input cap is not needed for stability, and 0.1–2.2 µF
  is good practice (7.1.1 p.17).
- JLC Extended, **11,607 in stock** against 2,000 for 500 boards, $0.961 at 20 pcs and $0.682 at 2,000
  (`sourcing/study-2026-10-15/scripts/jlc-raw/detail_C485909.json`). C96028 was $0.31: about +$1.48 per board.
  Why not only U3: U37 sits at 99 °C local at release, also over the plain part's 85 °C accuracy range, and one MPN on
  four sockets keeps the BOM a line shorter.

**U3's heat row (B3).** U3 now deposits its bound, 0.160 W = (15.46 − 4.89 V) × 15.1 mA (the HOT5 loads of the Kelvin
census at their maxima, U9 CA-IS3720HW side A at 4.1 mA), not 0.1 W (`b3/make_heat_sources.py`). It is a **gated B3
row on TJ**: pad copper + 0.160 W × ψJB 40.7 K/W against TJ 125 °C (`b3_ratings_gate.py` MONITORS / MONITOR_GRADES /
MONITOR_SELF).

**U3's heat goes into pads 1, 2, 3 and 5 only.** Pin 4 is NC, "No internal connection" (SLVSCE6D Table 4-1 p.3), so no
die heat enters it. This is the same treatment as R5's sense fingers. Heated, the isolated NC pad floated to the junction
node, and its cell became U3's "pad copper". That swung with how the 0.25 mm mesh drew the GND run passing 0.21-0.4 mm
from it:

| Run (board) | Copper | NC pad heated | U3 release | Mesh term, 3 × (0.25 mm − 0.5 mm) |
|---|---|---|---:|---:|
| 3 (596ba3bf) | p3, 0.25 mm GND | yes | 124.8 °C (+0.2 K) | 15.5 K |
| 4 (577b315c) | p4, 0.4 mm GND both ways | yes | 116.4 °C (+8.6 K) | 9.6 K |
| 5 (57083935) | p5, the same, east run 0.375 mm further from pin 4 | yes | 124.1 °C (+0.9 K) | 15.3 K |
| **6 (23209767)** | **p5** | **no** | **109.7 °C (+15.3 K)** | 4.0 K |

**Final row (run 6): c17.5 @ 61 (release) 109.7 °C, +15.3 K; c22 @ 55 109.6 °C, +15.4 K; c28 @ 55 121.6 °C, +3.4 K
(ratchet only).** Self-heat is 6.51 K (0.160 W × 40.7 K/W).

Cross-check: the body model's own DBV network (RthJB 39.5 K/W, `thermal_body.SPECS["dbv5"]`) puts U3's junction at
93.7 / 92.1 °C on the two meshes. That is 109.2 °C at release on the same basis, 0.5 K under the gated row.

U5 (REF25) reads 91.8 °C (89.1 at s47; +33.2 K). The ledger's TPS70950QDBVRQ1 TJ rows are keyed to these margins
(`ledger48.py`).

The legacy 1 mm point-deposit peaks (on the card, not compared since 2026-10-15) now sit on U3's single heated cell:
nominal_h10 171.3 → 177.6 °C, nominal_h25 131.7 → 154.7 °C. `b3-convergence/inputs/part-bodies.json` takes U3's new pose
and the Q1 MPN (only the FET lead links and the gap sensitivity read body positions).

## 2. H1: the REF25 watchdog on U14's second channel

**Circuit.** R144 63.4 k (RT0603BRD0763K4L, 0.1 % 25 ppm) from REF25 to U14 INB− (pin 4), R145 11.7 k (TNPW060311K7BEEA,
0.1 % 25 ppm) to OCP_KELVIN_P. Both are existing BOM lines (the analysis lane's 54.2 k / 10 k are not). U14 OUTB (pin 6)
joins OUTA (pin 1) on HOT5_UV_RAW, so a trip shares R50's pull-up, the Schmitt buffer and the NAND, and raises BUS_FAULT.
U5's REF25 rises when U5 opens (it is then only the R31 divider of HOT5).

TPS3700 (SBVS187G): INB− is the overvoltage input; OUTB goes low when INB− rises above VIT+ 396–404 mV (6.5 p.6, Table 1
p.10). I(INB−) ±15 nA.

| Quantity | Value | Basis |
|---|---:|---|
| Trip window (REF25 at which OUTB falls) | **2.526–2.610 V** | (VIT+ ∓ I·Rth) / ratio, ratio at 0.1 % + 25 ppm × 100 K adverse (`audit.rs` `s48_trip_window`) |
| REF25 maximum in service | 2.5162 V | LM4050AEM3 ±15 mV + 1.2 mV (SNOS455H 5.6 p.7): **9.7 mV** under the trip floor |
| REF25 with U5 open, minimum | **2.845 V** | HOT5 at the 4.632 V UV no-trip ceiling through R31 5.6 k (+1 %) into all REF25 loads (+0.1 %): 235 mV over the trip top |
| Watchdog load on REF25 | 33.5 µA | 2.5162 V / 75.1 k |
| U5 cathode current, minimum | 0.1075 mA | ≥ IRMIN 65 µA (`audit.rs` reference_current) |

It catches U5 open in 100 % of cases, and U5 drifting above 2.61 V. Drift between 2.516 and 2.526 V stays silent, as
before.

**U14 VDD (pin 5) and C48 moved from V15_LS to HOT5.** INB− (pin 4) is next to VDD (pin 5). With VDD on V15_LS, a pin
4–5 solder bridge puts ~15 V on a 7 V abs-max input (SBVS187G 6.1 p.5). On HOT5 it puts ≤ 5.5 V there and trips OUTB
(announced). The HOT5-UV supervisor still works over a sagging HOT5:
- VIT± are specified the same at VDD 1.8 V and 18 V (6.5 p.6), so the 4.54 / 4.60 V UV thresholds do not move;
- below UVLO, OUTA is driven low, a fault (note 3 p.6);
- below V(POR) 0.8 V the OUTA pull-up, the Schmitt buffer and U9 side A are unpowered together, and U9 defaults high;
- a regulator that fails high (HOT5 → V15_LS ≤ 15.46 V) stays inside VDD 18 V (abs max 20 V).
`FAULT-INTERFACE.md` (the reviewed HOT5-UV supply record) is updated with this. The Kelvin census counts U14's IDD on HOT5.

## 3. H2: BIAS_GOOD to J4 pin 1

**Isolation class: SELV.** BIAS_GOOD is U40's output, on the SELV side of the rail-monitor crossings (`rules21.domain`
SELV; it already runs to TP19 and the PERMIT logic). J4 is the SELV controller connector, and pin 1 has been spare since
stage 38. No barrier is crossed: the D5 barrier gate and the RES_A outer check read 0 violations.

**Circuit.** R146 220 k (RC1206FR-07220KL, existing BOM line) from BIAS_GOOD to J4.1, at (33.0, 173.5) next to the
connector. 220 k, not the analysis lane's 1 k, because J4.1 neighbours PERMIT_GATE's J4.9 in the harness. A J4.1–J4.9
short then holds PERMIT_GATE at 3.6 V × 50 k / (50 k + 218 k) = **0.68 V**, under VIL 0.8 V with its two 100 k pull-downs
(`audit.rs`: R ≥ 160 k).

**Copper.** BIAS_GOOD branches from U40's feed via (68.463, 133.0) and is hand-laid (`patches21.S48_TRACKS`, the
router's stage-48 run-1 path with its last via moved): B.Cu to (60.6, 140.8), F.Cu diagonal to (43.6, 153.2), B.Cu to
(37.0, 172.0) beside C174, F.Cu to R146.1. BIAS_GOOD_J4 runs on F.Cu from R146.2 to J4.1.

Each of the three new layer changes needed a SELV return-path transfer cap within 3.0 mm (`return_path19`). Without
them, run 2 read 11 return-path opens against s47's 7. So the stage adds **C176-C178** (CC0603KRX7R9BB104, 100 nF X7R
50 V 0603, the same BOM line as C169-C175), v3v3 to selv_gnd, each pad on its own plane via 0.85 mm away:

| Layer change | Cap | Cap at | Distance |
|---|---|---|---:|
| (68.463, 133.0) | C176 | (66.06, 133.4) | 1.68 mm |
| (60.6, 140.838) | C177 | (61.7, 141.94) | 1.15 mm |
| (43.6, 153.238) | C178 | (44.3, 152.14) | 1.10 mm |
| (37.0, 172.0) | C174 (stage 44) | (36.5, 175.4) | 2.67 mm |

Return-path opens are back to 7. C176-C178 join the spine lock's `frozen_refs`.

**Firmware requirement (not implemented here).** J4.1 is a new controller input. The controller must read it high-Z: a
pull-down of ≥ ~1 MΩ, or none, because 220 k into a 100 k pull-down only reaches 1.0 V. The power-on check:
1. before the heartbeat starts, BIAS_GOOD (J4.1) must read **low** (the monitors are not yet up);
2. after the bias rails are up and the heartbeat runs, it must read **high** before PERMIT is requested;
3. while PERMIT is requested it must stay high; a low is a trip.
This needs a controller GPIO assignment (`controller_pins.h`) and controller-board copper, so it is not a small,
host-testable firmware change and `firmware/` is unchanged. Firmware host tests: 31 / 31.

## 4. H3–H5: end-of-line test pads

Planned by `layout/plan_board_only21.py` (new `SIGNALS_EOL` list), each on existing copper of its net with a reference pad
on its own island return within 10 mm. They are numbered after the stage-47 pads, so TP1–TP40 keep their numbers.

| Pad | Net | At (mm), side | Reference pad |
|---|---|---|---|
| TP41 | monitor_ls-uv | (105.75, 107.835) B | TP53 n_ls (107.526, 105.923) |
| TP42 | monitor_ls-spanuv | (106.846, 84.319) B | TP54 n_ls (105.125, 82.395) |
| TP43 | monitor_ls-spanov | (116.926, 110.361) B | TP55 n_ls (119.175, 109.535) |
| TP44 | bias_ha.monitor-uv | (52.3, 111.085) B | TP56 n_ha (53.637, 108.822) |
| TP45 | bias_ha.monitor-ov | (52.154, 115.289) B | TP56 |
| TP46 | bias_ha.monitor-spanuv | (47.2, 109.265) B | TP56 |
| TP47 | bias_ha.monitor-spanov | (51.174, 79.196) B | TP57 n_ha (50.735, 76.474) |
| TP48 | bias_hb.monitor-uv | (9.2, 104.535) B | TP58 n_hb (8.337, 108.172) |
| TP49 | bias_hb.monitor-ov | (8.196, 98.796) F | TP59 n_hb (11.879, 94.774) F |
| TP50 | bias_hb.monitor-spanuv | (5.4, 105.365) B | TP58 |
| TP51 | bias_hb.monitor-spanov | (7.354, 110.149) B | TP58 |
| TP52 | ref25 (H5) | (115.75, 56.85) B, on the REF25 via | TP28 ocp_kelvin_p (111.2, 55.4) |

**11 of the 12 monitor taps (H3) and REF25 (H5) have pads.** `BRINGUP-PROBES.md` lists 34 signal pads (22 at s47)
and 25 reference pads.

**No pad (probed at a part instead):**
- `monitor_ls-ov`: no legal spot on its copper. Probed at C67.1 (the tap capacitor, 0603), ground C67.2.
- `p6`, U26.6 (TPS7A4700 3P2V, H4): the pin is open, so it has no copper. A pad needs a 4 mm stub under U26.7–U26.10
  (0.23 mm from four GND pins) on a node of the regulator's internal resistor network. The fixture contacts U26.6's pad toe
  instead, 0.87 mm outside the VQFN body, and grounds it to U26.5 / U26.7 to raise the LS span by 3.2 V.

**Moved:** TP6 (HOT5) and TP28 (its OCP_KELVIN_P reference) overlapped U3's and R137's new spots. They are now on the
bottom side at (110.5, 57.6) and on R145's ground via (111.2, 55.4). `native-21/BRINGUP-PROBES.md` is regenerated by the
chain (`probe_map21.py`).

## 5. Layout

The U3 / U14 cluster could not be routed in place. The corridor at y 54.4–56.5 is blocked on every layer: F.Cu
ovp_ok_hot at y 56.1; B.Cu ocp_ok_hot and the HOT5 diagonal; In2 hot5_ok_hot at y 54.0 plus its V-dip; In1 the Kelvin
pour and V15_LS. Vias are not allowed below y 54.0 (the bus_p In2 3.2 mm rule).

So **U3 moved** to rotation 0 at (118.3, 61.75), beside its output cap C26, and **C48** to (121.3, 61.9). U3's old slot
takes the watchdog pair R144 / R145. U3's input cap C25 stays where it was, ~12 mm away on V15_LS (as at s47). TI's
"close to the pins" (7.4.1 p.19) is good practice for an input cap that stability does not need (7.1.1 p.17). It is
recorded as UNCHECKED layout guidance in the ledger.

Hand copper is in `native-21/layout/patches21.py` (`S48_*`, `edit_base48`, hooked into `incr21.py` after stage 44):
21 base tracks and 6 vias out, 39 tracks and 15 vias in, and bus_fault_hot re-laid at y 59.75 above U3. Poses are in
`S48_PARTS` / `S48_MOVES`, applied by `place.py`. Every pose and track was pre-checked with `scripts/fit_check.py`
(rules21 clearance on every layer, courtyards 0.1 mm).

Passes (`passes48.sh`, frozen s47 copper plus edit_base48):
- `p1` j1: 11 errors (U14.2's ground diagonal crossed pin 4, now REF25_WD; TP6 / TP28 under the new parts);
- `p1` j2 routed the 6 router opens; fixed in edit_base48 and the test-pad plan;
- `p2` j1: 0 errors, 6 opens; j2: unconnected 0, errors 0, barrier 0. Chain runs 1-2 on it (boards 9daf7d7d, 53d0c89c);
  the run-2 card rejected it on 11 return-path opens and 24 acute corners;
- `p3`: the H2 transfer caps C176-C178 and two acute-corner fixes (HOT5 off the C48 run at (120.6, 60.8), not U3.5; R137.2
  level with its via). j2 clean; chain run 3 (board 596ba3bf) put U3's B3 row at +0.2 K;
- `p4`: U3's heat copper (below). j2 clean; chain run 4 (board 577b315c): 23 acute corners, the east run meeting C48.2's
  via run at 47°;
- `p5`: the east run enters C48.2 at 45° from (120.375, 61.75) (92° to the via run). j1: 0 errors, 4 opens; **j2:
  unconnected 0, errors 0**, barrier 0. Chain run 5 (board 57083935) and run 6 (board 23209767, the same copper key
  659ccad1, after U3's NC-pad heat fix) both reached CHAIN_DONE.

**U3's heat copper (p4).** The DBV's heat leaves by pin 2 (GND). SLVSCE6D 7.4.1.2: "Using heavier copper increases the
effectiveness in removing heat from the device. The addition of plated through-holes to heat-dissipating layers also
improves the heat sink effectiveness." U3.2's track to its Kelvin drop via is now 0.4 mm (was 0.25), and a second
0.4 mm run leaves U3.2 east under the body (the DBV has no pin opposite pin 2) to (120.375, 61.75), then 45° into C48.2
and its drop via (120.25, 63.65).
U3.5's HOT5 run to (120.6, 60.8) is 0.4 mm. Pre-checked with `fit_check.py` (0 problems).

## 6. Chain

`SPINE_OWNER=selv TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s48 runs-native21/s48/p5/j2 runs-native21/s48/c48`
(run 6, CHAIN_DONE):
- DRC 0 errors / 0 unconnected. Barrier 0, RES_A outer 0 (min F.Cu 20.393 mm), D5 8.047 / 8.507 mm, DFM PASS (777 vias).
- FIT 424 / 0 / 0, jet strip 1.72 mm. `pin_absmax` 0 failures. ERC 1 error (power_pin_not_driven, as at s47; it was 2
  before `pin_functions21` learned the Q1 part).
- **SPINE_LOCK PASS** (owner selv). It was reissued on run 3's board 596ba3bf: the bias_good path, J4.1's net,
  C176-C178 in `frozen_refs` (`selv_spine_lock.json` `reissued[-1]`).
- BYPASS PASS. Kelvin band after 66.46-117.45 A (s47 66.75), floor 64.17 A; 15.505 mA returned (U14 IDD, the watchdog).
- `b3_ratings` PASS, release +1.0 K (R10).
- BOM 94 lines, 372 placements. CPL audit OK 298 / CORRECTED 32 / NEEDS-PREVIEW 31, covering 372 / 372. U3's control
  passes at 180°. BOM / CPL designators PASS.
- After the chain: `s21_necks.py s48` (min ratio 0.993 / conductor 1.021, = s47); coil pickup `result-s48.json` (stack
  4.17 A, = s47); `snapshot/s48` + `run_all.sh`; `ledger48.py`, `recite48.py`.

## 7. Gates and tests

- Ledger gate PASS: 3 VERIFIED / 91 PARTIAL / 0 UNAUDITED / 0 VIOLATION (TPS70950QDBVRQ1 PARTIAL); `tests/test_gate.py`
  0 failures.
- `audit.rs` PASS (372 components, 187 nets), `--test` 90 / 90. `verify_source.py` (372) PASS.
- `test_track_geometry`, `test_spine_lock`, `test_track_cleanup21`, `test_jet_strip_height`, `test_bom_pricing`: PASS.
- `scoped/test_scoped.py` 16 / 16, `depmap_check` PASS.
- `test_cu_temp_basis` all controls, and `cu_temp_basis --fail-waived` PASS (0 waived).
- `test_b3_hot_copper` 0 failures (U3 row, and U3's heat on pads 1 / 2 / 3 / 5); `test_b3_airflow` 0 failures.
- Firmware host tests 31 / 31 (unchanged firmware).
- Scorecard `10-benchmark/scorecard-native21s48.json`. Against s47:
  - kelvin_band_low_A 66.75 → 66.46 (tolerance 0.5);
  - right-angle corners 49 → 53 (allowance 5), any-angle 272.6 → 281.6 mm (allowance 25);
  - vias 765 → 777, placements 358 → 372;
  - parts_usd_at_500_v2 +$1.69, the only counted move.

## 8. What did not match the brief

- **H1 divider 63.4 k / 11.7 k, not 54.2 k / 10 k.** Both are existing 0.1 % BOM lines; 54.2 k is not. The window is
  computed at 0.1 % + 25 ppm/K adverse (section 2).
- **R146 is 220 k, not 1 k**, so a J4.1-J4.9 harness short cannot hold PERMIT_GATE above VIL (0.68 V < 0.8 V).
- **Three more parts than the brief: C176-C178**, the SELV transfer caps that keep return-path opens at 7 (section 3).
- **U3 moved, and its row needed two fixes.** It reads 109.7 °C against the brief's 112.8 °C catalog figure, but only
  with its NC pad unheated (section 1). U3 had to move beside C26 (section 5), next to the hot RES_A copper, because its
  old slot had no routable corridor. Its GND copper was widened (p4 / p5). U5 rose 89.1 → 91.8 °C pad as a side effect.
- **ψJB is 40.7 K/W** (SLVSCE6D 5.4 p.4, new chip; the legacy chip is 38.4), not 38.7.
- **11 of 12 monitor taps have pads.** `monitor_ls-ov` has no legal spot; it is probed at C67.1. **No pad for U26.6
  (TPS7A4700 3P2V, H4)**: the pin has no copper and a stub would pass 0.23 mm from four GND pins; probed at the pin toe.
- **No firmware change** for H2: J4.1 needs a controller GPIO assignment first (section 3). Host tests 31 / 31.
- **One EasyEDA GET** (C485909, into `runs-native21/s48/dl/ee-raw/`) to give the CPL rotation audit U3's land record.

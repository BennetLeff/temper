# Task 05 round 6: reaching the 1239 W input hold (tank ceiling, inductance, bank, frequency rule)

> **ASSUMED / PRE-MEASUREMENT.** The coil, pans and coupling are round 4's published-anchor basis with round 5's
> FEM ratios. The capacitor limit is TDK's own p.57 curve, digitized here. Coil, sink and copper temperatures are
> the enclosure and task-04 models scaled to new currents. Every number is a model result, not a bench result.
> **Analysis only:** no board, layout, `elec/` or firmware file was changed.

- **Unit:** native-21, stage 14 (`codex/power-stage-integration`). The bank is 5 × TDK B32654A1104K000 (0.50 µF).
- **Coil:** R34 as modelled by the enclosure (`d228_gap84`, the gap at r 84–92). 70 µH free is 66.5 µH installed; 80 µH is 76; 90 µH is 85.5 (×0.95).
- **Date / tools:** 2026-10-10; ngspice 45.2; Miniforge Python 3.12; Claude Opus 5.5.
- **Method:** round 4's ngspice solver and deck, imported unchanged. Each case uses the **lowest legal frequency** in [max(35 kHz, 1.05 f_res), 60 kHz] that meets the line-cycle tank RMS ceiling and P ≤ 11.1 A × 0.93 × V.
  - **Grid:** 55 configurations × 45 cases = 2475 cases at 4 workers (`outputs/grid6-*-cases.csv`, summary in `outputs/config-summary6.csv`).
  - **Monte Carlo:** first-harmonic (FHA), calibrated on all grid cases (`outputs/calibration6.json`): P ×1.0020 (range 1.0012–1.0032), I ×1.0010. Each class gets 4000 uniform draws over its kl and r ranges, L0 ±10 %, C ±10 % and R_ac 0.168–0.25 Ω.
  - **Required current:** for each draw the MC finds **I_req**, the line-cycle tank RMS needed to reach full power. The yield at a ceiling is P(I_req ≤ ceiling).
  - **Full power:** ≥ 99 % of 1239 W at 120 V (1115 W at 108 V).
  - **Pooling:** "pooled" means the five classes and the 180/220/260 mm bases at equal weight.

## Verdict

1. **The firmware cannot reach full power on any pan today, whatever the ceiling.**
   - **One fixed frequency.** `power_service_frequency()` accepts only the single commissioned `frequency_hz`. The phase is fixed at 180° and burst is disabled, so nothing regulates power or tank current.
   - **Trips latch.** Tank RMS above 23.1 A and tank peak above 45 A latch faults.
   - **Best single frequency:** 0.2 % yield, and 41–51 % of pans trip (`fstrat-d-fixed-frequency.csv`).
   - **The RMS trip reads the wrong quantity.** It compares each AD8436 sample against 23.1 A. With CAVG 100 nF the AD8436 tracks the 120 Hz envelope (controller README: 3.4 ms settling), so a sample at the crest reads about 1.41× the line-cycle RMS. A 22 A line-RMS ceiling would therefore trip near 16 A.
   - **Fix:** the trip belongs on the half-cycle RMS that `input_limits_half_cycle()` already computes.
   - **The 45 A peak trip binds first.** The tank peak is 2.10–2.17 × the line RMS on the unsmoothed bus (ngspice), so 45 A peak caps the line RMS at about 21 A.
2. **Ceiling sweep, 70 µH / 0.50 µF (today's tank), 120 V** (`yield-pooled.csv`):

   | Ceiling | 22 A | 24 A | 26 A | **28 A** | 30 A |
   |---|---|---|---|---|---|
   | 180 mm | 3 % | 22 % | 52 % | 75 % | 89 % |
   | 220 mm | 15 % | 47 % | 73 % | **89 %** | 97 % |
   | 260 mm | 20 % | 53 % | 76 % | 91 % | 98 % |
   | Pooled | 13 % | 40 % | 67 % | **85 %** | 95 % |
   | Pooled, 108 V | 27 % | 57 % | 79 % | **92 %** | 98 % |

   - **80–90 % of pan cases needs about 28 A.** The pooled I_req percentiles are p80 27.4 A and p90 28.9 A at 120 V; on 220 mm pans they are 26.8 / 28.3 A (`ireq-percentiles.csv`).
   - **ngspice deterministic grid, 120 V:** full power in 2 / 6 / 11 / 12 / 15 of 15 cases at 220 mm (`config-summary6.csv`).
   - **Per class at 220 mm, 28 A** (`yield-by-class.csv`): cast iron 99 %, 18/10 100 %, thin stainless 90 %, enamelled steel 79 %, clad multiply 75 %.
3. **Frequency strategy.**
   - **Constant frequency: no gain.** The round-4/5 solver already picks the maximum-power frequency at the ceiling: the lowest legal frequency, and with the ceiling binding there is only one.
     - Above resonance |Z| rises with f faster than R_pan ∝ f^0.6 rises, so a higher constant frequency always delivers less.
     - Example, enamelled steel at its nominal corner (`fstrat-a-power-vs-f.csv`): 932 W at 46.1 kHz. Holding 22 A at 50 kHz instead would need 152 V line.
   - **Smaller bank.** It raises f_res, so the ceiling is met where R is larger. At 220 mm and 26 A, 0.50 → 0.40 µF lifts the yield from 73 % to 82 % at 70 µH, and from 74 % to 88 % at 80 µH (`fstrat-b-bank-sweep.csv`). The bank's current capacity limits this (item 5).
   - **Line-synchronous crest clipping (firmware only).** The firmware raises f near the line crest so that the peak stays at 45 A, and lowers it elsewhere.
     - **Yield, 70 µH / 220 mm / 120 V:** 13 % → **44 %** full power, and **71 %** at ≥ 95 % power, with today's OCP.
     - **Its limit is inlet power factor.** The unsmoothed bus draws p(θ)/v(θ). The PF falls to 0.95 at the margin of the ≥ 95 % set, so the 11.1 A hold is reached below 1239 W.
     - **Check against ngspice** (FM deck, `fstrat-c-fm-spice-check.csv`): line RMS within 0.5 %, P within 0.8 %, peak conservative by 1.5 A.
     - **Recommendation:** use it as a fallback, not as the main fix.
4. **Inductance: 70 µH stays.**
   - **More turns help only with a smaller bank.** On the 0.50 µF bank, 80 and 90 µH push resonance down until the 35 kHz window floor costs power. Floor-limited draws: 70 µH 0.7 %, 80 µH 13 %, 90 µH 39 %. Pooled 28 A yield: 85 / 81 / 59 %.
   - **With a smaller bank they do better:** 80 µH / 0.40 µF gives 95 %, and 90 µH / 0.40 µF gives 93 %, both at 28 A.
   - **ZVS margin holds everywhere:** f/f_res ≥ 1.17 and FHA phase ≥ 50° (all 2475 grid cases).
   - **But no 0.40–0.45 µF arrangement that fits the C21–C23 slot carries more than about 22 A** on TDK's 85 °C curve (item 5). The ngspice grid puts the worst part at 1.19–1.23× the curve at 26 A on 0.40–0.45 µF banks (`config-summary6.csv`). With R ∝ N² in the same window, the coil also runs hotter at the same current.
5. **Bank.** Tank RMS at which the worst-share part (±10 %) reaches TDK p.57 at 85 °C (`board-side-bank.csv`):

   | Bank | 35 kHz | 40 kHz | 45 kHz | 50 kHz | Fits slot |
   |---|---|---|---|---|---|
   | **5 × B32654A1104 (0.50 µF, today)** | 24.8 A | 25.3 A | 26.1 A | 27.3 A | yes |
   | 4 × B32654A1104 (0.40 µF) | 20.0 A | 20.5 A | 21.1 A | 22.0 A | yes |
   | 3 × B32654A1154 (0.45 µF) | 20.5 A | 20.9 A | 21.6 A | 22.3 A | yes |
   | 4 × B32654A1154 (0.60 µF) | 26.9 A | 27.4 A | 28.3 A | 29.2 A | yes (76 mm) |
   | 6 × B32654A1104 (0.60 µF) | 29.5 A | 30.2 A | 31.1 A | 32.5 A | no (90 mm against about 81.8 mm) |

   - **Current per µF is the constraint.** Small parts carry more current per µF, so 0.50 µF from 5 parts is the best slot bank.
   - **0.60 µF does not pay.** It carries more current but drops the yield (59 % at 26 A).
   - **Today's bank against its curve:**
     - the grid's worst part is at **0.89× at 22 A** (this digitization; the bank decision's by-eye figure was 0.86×);
     - **1.05× at 26 A** and **1.12× at 28 A**.
     - At an assumed 60 °C local ambient (I² ∝ 105 − T_a, an ESTIMATE) it would carry about 38 A.
     - The bench hot-spot measurement already listed in DECISIONS 2026-10-09 decides this.
   - **B32654A1154K000:** DigiKey had 200 in stock on 2026-10-10 (495-75752-ND, $3.56 @1). It is not needed for the recommendation.

## Recommendation

| | Recommended | Stage A (fewer changes) | Firmware-only fallback |
|---|---|---|---|
| Tank RMS ceiling | **28 A** | 26 A | 22–26 A, peak held at 45 A |
| Coil | **70 µH** (66.5 installed), R_ac ≤ **0.23 Ω** @100 °C | 70 µH, R_ac ≤ 0.25 Ω | 70 µH |
| Bank | **5 × B32654A1104 (0.50 µF), unchanged** | unchanged | unchanged |
| Frequency rule | per-pan closed loop, lowest legal f (below) | same | same + crest clipping |
| Yield to the hold, 120 V pooled / 220 mm | **85 % / 89 %** (108 V: 92 %) | 67 % / 73 % | 220 mm: 44 % full, 71 % ≥ 95 % |

**Firmware frequency rule.** Every half cycle, set f to the lowest frequency that satisfies all of:
- f ≥ max(35 kHz, 1.05 f_res), with f_res from the CT_ZC phase (min_lag);
- half-cycle tank RMS ≤ ceiling;
- inlet estimate ≤ 11.1 A;
- tank peak ≤ the peak trip less 3 A of pickup margin;
- f ≤ 60 kHz, else burst.

Approach f from above, from 60 kHz, by stepping down. Above resonance, P and I fall monotonically with f, so this is the maximum-power point.

Further firmware changes:
- **RMS trip:** move it to the half-cycle RMS (`input_limits` already computes it) and set the trip to 1.05 × the ceiling.
- **Retire** the fixed-frequency path (`power_service_frequency`) and the old PLL table (44–50 kHz).
- **Crest clipping (fallback):** f(θ) = max(f_b, f_c(θ)), where f_c holds the local peak at the trip margin. The inlet estimator must then use the RMS of p/v per sample, not P/V, because the PF falls below 1.

**What the board needs at 28 A** (26 A in brackets; `board-side-*.csv`):
- **OCP thresholds.** All of them move, because the envelope peak is 59.2 A (55.4 A) against today's 45 / 47.33 / 50.56 A.
  - **Trip floor:** ≥ 64 A (60 A), allowing 3 A of coil pickup and 2 A of margin.
  - **CT comparator band:** about 64–76 A (60–72 A), a divider value change.
  - **Shunt band:** low corner ≥ 64 A; scaling the divider puts its high corner near 133 A. Check that against the FET pulsed rating and task 02's fault energy.
  - **Firmware peak trip:** about 62 A, which also lifts `config_ok()`'s 50.9 A cap.
  - **CT T1 is fine:** 0.32× its 88 A rating, 0.89 V secondary peak, CT_MON headroom 51 A.
  - **R5 is fine:** 0.79 W (0.68 W) against its 1 W rating.
- **Tank copper** (IPC-2221, 2 oz, 20 K screen):
  - **SW_A F.Cu**'s 7.0 mm section goes to **≥ 9.8 mm** (8.8 mm); at its present width it rises 35 K (29 K).
  - **SW_B B.Cu**'s 8.1–8.5 mm long sections go to **≥ 9.8 mm** (8.8 mm); today they rise 25–27 K (21–23 K).
  - **SW_B's 3.1–6 mm necks** are 4–6 mm long; task 04's fin estimate scales to about 1.7 K.
  - **Copper loss:** SW_A + SW_B rise from 5.4 W at 22 A to 8.8 W.
  - **Room for SW_A:** stage-13/14 copper shows free F.Cu on SW_A's lower-left at its narrow step (x 85–98, y 24–37) and right of its vertical leg (x 148–160, up to the bank's pad clearance).
  - **Room for SW_B:** it is boxed in the FET region by the SW_A B.Cu link pour and the gate-drive islands. This needs a layout pass to confirm; it is not shown feasible here.
- **Bank:** no part change. It runs at 1.12× (1.05×) the TDK 85 °C curve, so the release condition is the bench hot-spot measurement (rise ≤ 20 K at the enclosure ambient) or airflow over the bank.
- **Coil cooling** (R33 `coil_thermal.py`, R34-as-modelled variant, full blower, 50 °C inlet, 45 kHz):
  - With R_ac 0.25 Ω the winding holds **27.2 A** at the model's heat-transfer coefficient h, and 23.0 A at its 0.6 h lower case. At 26 A it reaches 141 °C (178 °C at 0.6 h).
  - **28 A needs R_ac ≤ about 0.23 Ω**, or more jet flow. The 0.6 h case is not met at any ceiling above 23 A, so the coil-NTC derating loop (DECISIONS R32 item 8) must stay.
- **MOSFETs and sink:**
  - **Basis A** (D-18 conservative switching proxy, 45 kHz): Tj 134.5 °C at 28 A (128.7 °C at 26 A), against 125 °C at R_SA 0.29. It needs R_SA ≤ 0.233 °C/W (0.266).
  - **Basis B** (ZVS conduction estimate): 82 °C (78 °C).
  - Conduction per FET, hot: 14.5 W (12.1 W), against 8.3 W at 22 A.
  - The basis-A excess is the switching proxy's, so measure the switching loss on the bench before changing the sink.

**Why not the alternatives.**
- **80 or 90 µH on a 0.40–0.45 µF bank** yields more (95 % at 28 A for 80 µH / 0.40 µF), but no such bank in the slot carries more than about 22 A at 85 °C. Revisit only if the bench shows the bank ambient is ≤ about 60 °C.
- **Crest-clipping FM alone** keeps today's OCP, but the inlet PF caps it near 44 % full / 71 % ≥ 95 % at 220 mm.

## Files

| Number | Script → output |
|---|---|
| Ceiling × L × C × pan grid (ngspice) | `scripts/run_grid6.py` → `outputs/grid6-*-cases.csv`, `grid6-configs.json`, `grid6.log` |
| Yields, I_req percentiles, calibration, per-config stresses | `scripts/analyze6.py` (uses `fha6.py`, `common6.py`) → `yield-pooled.csv`, `yield-by-class.csv`, `ireq-percentiles.csv`, `calibration6.json`, `config-summary6.csv`, `coil-loss-mc.csv`, `summary6.json` |
| Frequency strategy (P vs f, bank sweep, crest-clip FM + ngspice check, fixed-frequency firmware) | `scripts/freq_strategy.py` → `fstrat-*.csv` |
| Copper, OCP/CT/R5, bank capability, coil cooling, FETs/sink | `scripts/board_side.py` → `board-side-*.csv`, `board-side.json` |
| Coupling ratios (frozen from round 5 + addendum) | `scripts/snapshot_inputs.py` → `coupling-factors.json` (with source SHA-256) |
| TDK p.57 curve | `scripts/digitize_tdk_p57.py <MKP_B32651_658.pdf>` → `tdk-p57-1600v.csv/.json` (PDF SHA-256 `c32e3754…`; 99 kHz end within 1 % of the p.22 table) |

**Reproduce** (from this folder; needs the sim-kit vendor model, as in round 4; ≤ 4 ngspice workers):

```sh
python3 scripts/snapshot_inputs.py
python3 scripts/digitize_tdk_p57.py <MKP_B32651_658.pdf>
python3 scripts/run_grid6.py --set all --workers 4      # ~70 min
python3 scripts/analyze6.py
python3 scripts/freq_strategy.py                         # ~2 min, includes 3 ngspice FM runs
python3 scripts/board_side.py                            # imports enclosure R33 coil_thermal.py / requirement.py read-only
```

## Limits and what the bench must settle

- **No measured coil or pan.** I_req scales with the reflected R, so the first R34 sample on the five class pans (round 5 §6) moves every yield here. Every ceiling and yield figure above is conditional on that measurement.
- **Peak ratio.** Peak/RMS uses an ngspice fit against Q, plus its largest residual (+0.078).
- **FM check.** The FM spice check holds L at the weighted-mean frequency (it moves ≤ 1.5 %), and its PF is quasi-static.
- **Copper widths** are task 04's measured sections. Feasibility of the widening is a layout question, not answered here.
- **Bench order:**
  - bank hot-spot at 26–28 A;
  - coil winding temperature at 26–28 A at full blower;
  - switching loss at 45–50 kHz (basis A against B);
  - the real CT and shunt trip points after any divider change;
  - the AD8436 envelope tracking.

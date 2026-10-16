# B3 on hot copper (2026-10-15)

OPEN-ITEMS S17: the B3 copper loss was not temperature-corrected. Board s42 (9e075b4b), I_line 13.5 A, film-cap air at
bay + 15 K (ff921e889). Until now, every A4 field was 20 °C DC copper. The copper under the tank current runs at
100–176 °C, so its resistance was 30–60 % low.

```
python3 ../run_basis.py --workers 3                     # hot BASIS (the default now) -> ../margins.json
python3 ../run_basis.py --workers 3 --copper-tcr 0 --runs DIR --out FILE   # 20 C copper control (gated with --allow-cold-copper)
python3 ../run_basis.py --workers 3 --cases c16_h10@61,c17_h10@61,c17.25_h10@61,c17.5_h10@61,c17.75_h10@61,c12_h10@61,c8_h10@61 \
        --runs ../runs/hot-bisect2 --out margins-bay61.json
python3 ../run_basis.py --workers 3 --cases c19_h10@55,c20_h10@55 --runs ../runs/hot-bisect2-55 --out margins-bay55.json
python3 -I scripts/summarize.py                         # -> hot-copper.json
python3 ../test_b3_hot_copper.py                        # closed form, Picard equivalence, runaway, gate refusals, probe rows
```

`margins-cold-copper.json` is the ff921e889 `margins.json`, the same BASIS on 20 °C copper, kept as the record.
`margins-bay61.json` and `margins-bay55.json` are the direct solves.

## Method

- **Loss law.** Every A4 heat cell carries q = q20·(1 + α(T − 20 °C)), with α = 0.00393 /K. That is
  `sheet_solver.ALPHA_CU`; both thermal modules assert it against that source.
- **Absolute T.** T = bay + rise: each case is solved at its own bay. `body_runs` takes `copper_tcr = {alpha, air_c}`,
  and `run_basis` passes air_c = the case's bay. The gate refuses a hot run file whose air_c is not the bay it is asked
  for: hot copper is not shift-invariant, so there is no shifting.
- **Solve.** q is affine in T, so the fixed point is linear. It is solved exactly by folding −α·q20 onto each cell's
  diagonal (`thermal_body.solve_system(tcr=)`, `thermal.solve_stack(tcr=)`).
  - Then Picard steps run on the unmodified operator until max|ΔT| < 1e-3 K. Every BASIS solve settled in one step
    (max|ΔT| 0.0 K).
  - A Rayleigh loop gain x'Dx / x'M0x ≥ 1, a non-positive diagonal or a CG failure each raises "thermal runaway".
  - Gains: 0.035 at c18 @ 61, 0.060 at c22 @ 55, 0.124 at c28 @ 55, and 0.14–0.29 on the legacy binary-copper model.
- **Fixed J.** The current distribution is held at the 20 °C A4 solution, and this is conservative. The cold J satisfies
  Kirchhoff's current law, so by Thomson's principle Σ R_hot·I_cold² ≥ the true hot loss: the fixed-J total loss is an
  upper bound.
  - Rough size: two parallel paths at temperatures ΔT apart carry an excess of (α·ΔT/2)² / (1 + e)² of their loss.
  - With the whole copper range as the path-to-path ΔT, that is ≤ 1.3 % of copper loss at c18 @ 61 (≤ 0.11 W of
    8.33 W), ≤ 2.5 % at c22 and ≤ 5.7 % at c28 (≤ 1.2 W of 21.3 W).
  - Locally, the hottest cells would shed current to cooler parallel copper, which also makes fixed J conservative at
    the hot spots.
  - A uniform-temperature sheet_solver re-solve would give exactly zero redistribution, because a uniform scale does not
    change the distribution.
- **Records.** Every run file carries `copper_temp_model`: model, α, air_c, Picard steps, max ΔT, loop gain, hottest
  heated copper, loss at 20 °C and hot, multiplier, and multiplier per A4 case. The legacy `thermal.py` receipt records
  the same.
  - The gate copies `{model, alpha, max copper T, multiplier, max dT}` into `basis.cases[c].copper`.
  - It refuses run files that are cold-20C, or that have no record, unless `--allow-cold-copper` is given (controls
    only: `gate_control.py`, `jet_sweep.py`).
- **Control.** `run_basis.py --copper-tcr 0` reproduced the ff921e889 `margins.json` byte for byte (`cmp`). It still
  does through the gate after the S16 probe rows (`../monitor-probes-2026-10-15`), which are part of the hot basis only.

**Temperature-dependent part heats.**
- **Included:** none beyond copper.
- **Left out, deliberately:**
  - L1's winding copper: its row is the fixed (I/11.1)² datasheet-based figure, it is the only real copper part, and
    its row is advisory.
  - R5 (CSS2H, ±75 ppm/K: ≤ 0.9 % at 145 °C).
  - The thick-film gate, R39 and R22–R25 resistors (about ±100–200 ppm/K, ≤ 2 %).
  - Film-cap ESR(T): PP tan δ is roughly flat to falling with temperature.
  - RECOM / U26 / PS2 / driver efficiency vs temperature.
  - FET R_DS(on)(T) is not a board row here: the FET heat goes to the sink through fet_case, with its own basis.

## BASIS: 20 °C copper → hot copper (margin, K)

| Row | c18 @ 61 (release) | c22 @ 55 | c28 @ 55 |
|---|---|---|---|
| R10 2512 terminal derating | +3.6 → **−2.9** | −2.1 → −13.1 | −21.7 → −46.0 |
| R20 / R18 derating | +4.9 / +5.5 → −0.6 / +0.7 | −0.1 / +1.6 → −9.1 / −6.4 | −17.0 / −13.0 → −35.9 / −28.8 |
| R12 derating | +9.6 → +2.3 | +0.4 → −12.0 | −25.2 → **−52.4** |
| Laminate block / FET row | +8.1 / +10.2 → +0.8 / +3.0 | −1.2 / +0.9 → −13.6 / −11.3 | −22.5 / −24.1 → **−51.6** / −48.8 |
| R5 terminal derating | — | — | −6.5 → −36.7 |
| Copper loss, W (×) | 6.34 → 8.33 (×1.314) | 9.21 → 12.40 (×1.346) | 14.60 → 21.31 (×1.459) |
| Hottest heated copper | 119.6 °C | 134.6 °C | 176.0 °C |

- **Per-case multipliers at c18 @ 61:**
  - leg_a / leg_b 18.7: 1.37 / 1.38;
  - hv_mixed: 1.34 / 1.35;
  - sw_*: 1.29–1.32;
  - bus_mixed: 1.32 / 1.33;
  - res_a / coil_feed: 1.26 / 1.28;
  - ac_l / ac_n: 1.21 / 1.29.
- **At c28 @ 55:** the legs reach 1.57 / 1.58. The full list per mesh is in `hot-copper.json`.
- **Energy.** Balance closes to ≤ 4e-11 relative on the hot loss.

**Metrics** (card `scorecard-native21s42.json`):

| Metric | Before | After |
|---|---|---|
| `b3_release_margin_K` | +3.6 (R10) | **−17.9** (U29 LM339B, the S16 probe rows) |
| Same, without the monitor rows (the copper effect alone) | +3.6 | **−2.9** (R10; R20 −0.6) |
| `b3_laminate_margin_K` | −24.1 | **−51.6** |
| `b3_rated_part_margin_K` | −25.2 | **−52.4** (R12, c28) |
| `b3_advisory_margin_K` | −7.3 | −17.5 (C21 Top, c28) |
| Legacy single-cell peak `b3_c28_h25_peak_C` | 147.2 | 163.6 |
| Legacy single-cell peak `b3_nominal_h10_peak_C` | 165.3 | 171.5 |
| `gates.b3_ratings` | True | **False** |

**Release verdict at c18 @ 61: FAIL.**
- As built, it fails at −17.9 K, bound by U29.
- On the copper alone, it fails at −2.9 K, bound by R10, then R20 at −0.6 K. The copper effect at the release case is
  −6.5 K.
- At c28 it is −24 to −30 K on every hot row.

## Ceilings

**Bay 61, by direct solves.** Worst gated margin, with I_trip = 1.05 × ceiling:

| Ceiling (A) | 8 | 12 | 16 | 17 | 17.25 | 17.5 | 17.75 | 18 |
|---|---|---|---|---|---|---|---|---|
| As built (85 °C monitors) | −13.3 | −14.7 | −16.7 | −17.3 | −17.4 | −17.6 | −17.8 | −17.9 |
| Monitors at the 125 °C grades / no monitor rows | +9.8 | +8.3 | +3.3 | **+0.3** | **−0.4** | −1.2 | −2.1 | −2.9 |

- **As built: no tank ceiling passes at bay 61.** U29 fails at every solved current, −13.3 K at c8. Its heat is U26 /
  the bias, not tank copper.
- **On the copper rows: 17.0 A.** c17 passes at +0.3 K and c17.25 fails at −0.4 K, so the ceiling is resolved to
  0.25 A. R10 binds, and U26 binds below c12.
- The earlier release ceiling of 18.0 A does not hold on hot copper.

**ceilings.py (bay 55, c22 / c28 chord).**
- Hot results:
  - laminate 19.4 A;
  - gate R_on 19.1 A;
  - gate R_off 21.1 A;
  - all gated 0.0 A (U29).
- Cold results: 21.6 / 21.3 / 23.9 A.
- **The I² assumption no longer holds.** On hot copper, margin is concave in I²: copper loss grows faster than I².
  - So a ceiling inside [22, 28] A is conservative, and one outside it is optimistic.
  - ceilings.py now marks each result `bracketed` or `warning`, and all of these are unbracketed.
- **Direct check at bay 55.** c19 @ 55: R10 −1.1 K, laminate +1.4 K. c20 @ 55: R10 −4.8 K, laminate −3.3 K.
  - So the extrapolated R_on 19.1 A is optimistic: R10 already fails at 19.0 A.
  - The laminate's 19.4 A is consistent: it passes at 19 A and fails at 20 A.
  - Use direct solves for any ceiling below 22 A.

## G6 (R5 derating) and the R5 vias on hot copper

`stage17-r5/g6_r5_derating.py --tag native21s42` was rerun. It calls `b3/thermal.py`, now hot by default, at c28,
0.25 mm, h 25, 50 °C. `--copper-tcr 0` gives the 20 °C record on the same board. `r5_vias17.py` now takes ρ(T) at the
via mid-wall.

| | s17b record (`g6.json`) | s42, 20 °C copper | s42, hot copper |
|---|---|---|---|
| R5 pad-cell max / mean | 134.87 / 126.03 °C | 123.59 / 120.42 °C | **144.34** / 139.45 °C |
| `g6_margin_pct` (20 % needed; bound 148.39 °C) | 50.8 | 62.7 | **32.6** — PASS, 4.05 K below the bound |
| Worst (1 % tol, 75 ppm) | 49.9 | 62.1 | 31.4 |
| Heat on all four pads (sensitivity) | 51.5 | 59.9 | 26.8 (146.37 °C, 2.0 K below the bound) |
| Pad ≤ 160 °C / trip floor | PASS / 67.48 A | PASS / 67.6 A | PASS / 67.5 A |
| Copper multiplier / hottest copper / gain | — | — | 1.336 / 155.9 °C / 0.137 |
| Via wall max (bound 148.39 °C) | 133.31 | 120.69 | **140.75** (worst via 137.89, barrel 0.028 W at ρ 2.52e-8) |

- **G6 still passes, but it was close.** Hot copper adds 20.8 K to R5's pad maximum, against 24.8 K of headroom on the
  same board.
- The four-pad sensitivity is 2.0 K from the bound.
- New files:
  - `stage17-r5/g6-native21s42-{hot,cold}.json`;
  - `stage17-r5/r5_vias17-native21s42-{hot,cold}.json`.
- The s17b `g6.json` / `r5_vias17.json` are kept as the s17b records.

## What this changes elsewhere

- **The chain recomputes task 04 and B3.** `b3/thermal.py` is in `model_key.py`, so the next chain run misses both
  caches (DECISIONS 38: one shared key). The task-04 recompute is harmless but costs its full time once.
  `b3/outputs/*` are regenerated here on hot copper; `cache.json` keeps the old key.
- **Cold records.** `jet-2026-10-15/jet-sweep.json` and `cap-air.json` are 20 °C copper records.
  - `jet_sweep.py` runs the gate with `--allow-cold-copper`.
  - The required h_top (45.1 W/m²K at 28 A, bay 55; 59.2 W/m²K at bay 61) will rise on hot copper. It has not been
    re-solved.
  - Its still-air 21.3 A ceiling is superseded by the direct numbers above.
- **Files that carry copper loss, changed:**
  - `b3/thermal.py`;
  - `b3-convergence/thermal_body.py`;
  - `b3-convergence/body_runs.py`;
  - `b3-ratings/run_basis.py`;
  - `b3-ratings/b3_ratings_gate.py`;
  - `stage17-r5/r5_vias17.py` (barrel ρ(T));
  - `stage17-r5/g6_r5_derating.py` (pass-through and record).
- **Cold-allowed readers:**
  - `gate_control.py`;
  - `jet_sweep.py`;
  - `test_b3_airflow.py`;
  - `c39-gate-network/scripts/ceilings.py` (flags).

## DECISIONS draft

> **S17 hot copper.** B3 copper loss is now iterated to its own temperature:
> - q = q20·(1 + 0.00393·(T − 20)), at the case's bay, with the current paths of the 20 °C solve. This is conservative
>   by Thomson's principle, by ≤ 1–6 % of the copper loss.
> - It is the B3 default, and the gate refuses 20 °C run files except in controls. The control reproduces the old
>   `margins.json` byte for byte.
>
> On s42 (+15 K cap air), copper loss rises ×1.31 at c18 @ 61 and ×1.46 at c28 @ 55:
> - The release case fails on copper alone: R10 −2.9 K, against +3.6 K before.
> - The ratchets fall to laminate −51.6 K and rated parts −52.4 K.
> - The bay-61 ceiling on the copper rows is 17.0 A by direct solves (c17 +0.3 K, c17.25 −0.4 K), so the 18.0 A release
>   ceiling (DECISIONS 55) no longer holds.
> - With the S16 probe rows, the LM339B / TL431A monitors fail at bay 61 at any tank current (U29 −13.3 K at c8,
>   −17.9 K at c18). On the 125 °C grades of the same pinouts (LM2901BIDR, TL431BQDBZR) they pass with ≥ +19 K.
> - G6 still passes on hot copper: 32.6 %, R5 pad 144.3 °C against the 148.4 °C bound.
> - ceilings.py's I² extrapolation is optimistic below 22 A on hot copper. Ceilings come from direct solves.
>
> Open: the ceiling or bay decision; the monitor grades (a BOM change); PS2's 85 °C working rating against its
> 112 °C pads, and U5 (LM4040A25I) −4.5 K, both from the sweep; re-solving the jet h_top on hot copper.

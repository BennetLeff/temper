# R5 derating at the 28 A ceiling case (DECISIONS item 14, "Still open")

## Question

DECISIONS.md item 14 leaves open: at the 0.25 mm B3 mesh R5's pad cell is 149 C at 28 A, and R5 runs at
0.86 W of its 1 W rating. Is R5 within its datasheet derating? What does its TCR do to the OCP trip band
(66.37-118.74 A; floor 64.17 A)?

## Pass criterion (stated before the results were computed)

Evaluated at the B3 c28 case (firmware RMS trip 1.05 x 28 A = 29.4 A), 50 C ambient / design inlet, h 25.

- **(a) Power:** dissipation <= 0.80 x the datasheet-derated power evaluated at the modelled R5 pad (terminal)
  temperature, i.e. >= 20 % margin. Derated power = 1.0 W x (170 - T)/100, clipped to 0..1 W.
  The pad-cell maximum is the reference temperature. The datasheet derates against *ambient*, not terminal
  (see below), so this is a deliberately conservative surrogate: the board copper at the pad is the nearest
  modelled quantity to the part's mounting temperature.
- **(b) Temperature:** modelled pad temperature <= 170 C - 10 K (datasheet maximum operating temperature).
- **(c) Trip floor:** low edge of the OCP band >= 64.17 A after the Kelvin shift (all-at-max-transfer bound,
  kelvin_budget.py convention) and R5's TCR, using task-02 round-3 `thresholds.py` exact corners at -10 / +85 C
  ambient with R5's rise above ambient taken from B3 (replacing the committed +50 K).
- **Verdict:** PASS only if (a), (b) and (c) all hold. Controls must pass or the script aborts.

## Part

- Schematic `elec/src/parts.ato` `Shunt1m`: **Vishay Dale WSK25121L000FEA**, 1 mOhm, 1 %, 4-terminal 2512
  (T = 2.21 mm), designator R5 (`power_stage_120v.ato`: `r_shunt.designator = "R5"`). Native-21 fab BOM
  (`08-manufacturing-package/native-21/fab/bom-jlcpcb.csv`): same MPN, LCSC C4248455.
- The B3 heat file and round-3 `thresholds.py` label it `WSK2512R0010FEA`: an older MPN spelling for the same
  1 mOhm / 1 % WSK2512 line (same datasheet row). Rating and TCR rows are identical; label only.

## Datasheet (Vishay WSK2512, Document Number 30108, Revision 11-Dec-2023; downloaded to scratch, not committed)

| Item | Value | Page |
| --- | --- | --- |
| Power rating | 1.0 W at P70C | p.1, Standard Electrical Specifications |
| Derating | 100 % up to **70 C ambient**, linear to **0 % at 170 C** (graph x-axis "Ambient Temperature") | p.3, Derating |
| Terminal / solder-point rule | **none given** | pp.1-3 |
| Operating temperature range | -65 to +170 C | p.2, Technical Specifications |
| TCR | +/-250 ppm/C for 0.001-0.0029 ohm (the 1 mOhm row) | p.2 |
| High-temp exposure | 1000 h at +170 C, drift <= +/-1.0 % + 0.0005 ohm | p.3, Performance |

The TCR reference temperature is not stated on the pages read; the project convention (25 C,
`thresholds.py`) is used.

## Method

`r5_derating.py` (rerun below):

1. Reads R5's heat row from the committed c28 heat file and checks it equals 29.4^2 x 1 mOhm.
2. Re-runs the committed B3 solver `round5-native21/b3/thermal.py` at 0.25 mm, h 25, c28 copper scaling
   (`run_study.cases("c28")`), on the stage-16 geometry `native-21/verification/native21s16-all-copper.json.gz`
   (board `e9481ed6`, equal to `round5-native21/inputs/power_copper.json.gz`'s hash), and reads R5's pad-cell
   max and mean.
3. Applies the datasheet derating to the pad temperatures.
4. Recomputes the shunt OCP band with the task-02 exact-corner code (`thresholds.py`, stage-15 divider
   R34 12.6 k / R35 11.7 k as in `ocp_bands.py`), then adds the Kelvin shift from
   `kelvin/budget-native21s16.json` and `plane-native21s16.json`.

## Inputs (repo commit `3b515aade`)

- `round5-native21/b3/thermal.py`, `b3/run_study.py`, `b3/inputs/native21-board-heat-sources-c28.json`
- A4 heat arrays `round5-native21/outputs/*-heat.npz` (gitignored; regenerate with `run_cases.py`;
  the committed case JSONs are the same as the ones the arrays came from)
- `native-21/verification/native21s16-all-copper.json.gz`
- `stage15b/out/mesh_study.json` (committed 149.1 / 149.2 C reference)
- `02-protection-timing/round3/thresholds.py`, `kelvin/budget-native21s16.json`, `kelvin/plane-native21s16.json`

## Results (all from `results.json`)

**Controls (all pass):**
- C1: R5 heat row 0.86436 W = 29.4^2 x 1 mOhm.
- C2: B3 p 0.25 R5 pad-cell max **149.16 C** (committed 149.1 c2h / 149.2 c0, tolerance 0.5 K). It is also the
  board peak at this mesh (39.875, 16.375 F.Cu). Balance -4e-9 W.
- C3: the band code reproduces the committed 68.58-118.74 A before and 66.37-118.74 A after the Kelvin shift.

**Dissipation.** 0.864 W is at the **29.4 A firmware RMS trip**, not at 28 A. At 28 A it is 0.784 W. With the
1 % tolerance and the TCR limit at the pad temperature it would be 0.900 W.

**Derating.**

| Reference temperature | T (C) | Derated power (W) | 0.864 W as fraction | Margin |
| --- | ---: | ---: | ---: | ---: |
| pad-cell max | 149.16 | 0.208 | 4.15 | -315 % |
| pad-cell mean (261 cells) | 122.74 | 0.473 | 1.83 | -83 % |
| design inlet ambient (datasheet's own axis) | 50 | 1.000 | 0.864 | +13.6 % |

- 0.864 W is allowed only up to a reference temperature of **83.6 C** (28 A, 0.784 W: 91.6 C; with the 20 %
  margin: 62.0 C).
- DECISIONS item 4 (D-18) gates R5 on "local ambient <= 100 C": at 100 C the part is derated to 0.70 W,
  below even the 28 A dissipation (0.784 W). That gate is too loose for 28 A.
- Pad max is 20.8 K below the 170 C operating limit. The element runs hotter than its pad by an amount the
  datasheet does not give.

**TCR.** At 149.2 C, +/-250 ppm/C is +/-3.10 % (committed model: 2.75 % at its 135 C). Nominal trip 92.59 A
moves -3.01 % / +3.20 % with R5 +/-3.1 %.

| Band, low-high (A) | R5 temp (C) | before Kelvin | after Kelvin (census) | after Kelvin (bound) |
| --- | --- | --- | --- | --- |
| committed convention (-10/+85 C, +50 K) | 40-135 | 68.58-118.74 | 66.37-118.74 | 66.30 |
| same ambients, B3 rise (+99.2 K) | 89-**184** | 67.77-120.26 | 65.56-120.26 | **65.49** |
| 50 C inlet only, B3 rise | 149 | 72.56-114.47 | 70.35-114.47 | 70.28 |

The hotter shunt moves the low edge by -0.81 A. The bound still clears the 64.17 A floor by **1.32 A**.
At 85 C ambient R5 would reach 184 C, above its 170 C limit (this assumes the same 99 K rise, a
simplification).

**Criteria:** (a) FALSE, (b) TRUE (149.2 <= 160), (c) TRUE.

## Verdict: **FAIL**

Under the pre-stated criterion R5 is not within derating. The 0.864 W is 4.1 x the power the datasheet curve
allows at the modelled pad temperature, and 1.8 x at the pad mean. The trip floor and the 170 C limit hold.

## Limitations

- The datasheet derates against ambient. Its graph does not say how far the terminals or element sit above
  ambient on its test board, so the verdict depends on the pad temperature being a fair surrogate. At the
  design inlet (50 C) the datasheet axis alone gives 0.864 of 1.0 W (13.6 % margin, below the 20 % asked).
  The truth lies between the two readings; the FAIL is the conservative reading and it is not a measurement.
- B3 puts R5's whole heat into its F.Cu pad cells, with conduction through copper and convection from the board
  faces only: no body-to-air path. Round 5's README flags this as pessimistic for parts (a 0.87 W LDO reads
  136 K against about 31 K from its datasheet theta-JA). The max cell is a local peak (mean is 26 K lower).
- A4 copper heat is scaled to the 29.4 A point; R5 is at its trip level, not a sustained 28 A (0.784 W).
- The 85 C ambient corner with a fixed rise is an extrapolation; R5's real rise is not independent of ambient.
- TCR is applied as the +/-250 ppm limit in both signs; real alloy TCR is typically smaller and one-signed.
- Not a bench measurement; no IR data exists.

## Recommendation (proposal only; no schematic or board edits made here)

1. Bench IR of the R5 terminals at 28 A (the existing bench list has FET-row IR only). Accept the part if the
   terminal reference reads <= 62 C (20 % margin) or the vendor (ww2bresistors@vishay.com) confirms a
   terminal-based curve for the WSK2512 at the T2.21 mm footprint. Otherwise go to step 2.
2. Take D-18's own fallback now: a >= 2 W 1 mOhm four-terminal part with OCP, parasitic and layout review
   (Kelvin pads and footprint change). The TCR check above shows the band tolerates the hotter shunt, so the
   band is not the driver; the power rating is.
3. Tighten D-18's gate: "local ambient <= 100 C" allows 0.70 W; for 0.784 W use <= 91.6 C, for the
   29.4 A trip <= 83.6 C.
4. Cosmetic: correct the heat-file note `WSK2512R0010FEA` to `WSK25121L000FEA`, and DECISIONS item 14's
   "0.86 W at 28 A" to "0.86 W at the 29.4 A trip (0.78 W at 28 A)".

## Reproduce

```sh
# unit root; needs round5-native21/outputs/*-heat.npz (WORKERS=6 python3 round5-native21/run_cases.py to regenerate)
python3 validation-results/04-board-current-thermal/round5-native21/r5-derating/r5_derating.py
```

About 3 minutes. Writes `results.json` next to the script and exits non-zero if a control fails.

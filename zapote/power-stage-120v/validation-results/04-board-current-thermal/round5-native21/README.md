# Task 04 round 5: board current screen on native-21 (stage 6)

The round-4 A4 experiments (same imposed currents and pad names, plus the two mains-entry
cases), run on native-21 copper: the enclosure re-layout's new current paths, which D4's
conditions require screening before fabrication.

- **Board:** native-21 stage 6, SHA-256 `387b753a…` (`inputs/power_copper.json.gz`,
  `tools/export_power_copper.py`). Stage 6 = stage-5 copper + the R5 current-pad vias below.
- **Evidence class:** simulation/model-based. These are conditional DC experiments with imposed
  currents, not operating waveforms. The thermal B3 solve still waits for task 03's heat
  sources.

## Checks before solving

- Topology (`outputs/kit_topology_p0125.json`, `kit_topology_p00625.json`): 0 false joins at
  either pitch. At 0.125 mm the 0.15 mm rings of native-21's 0.6/0.3 vias fragment on leg_ret,
  sw_a, sw_b and hv_ret, so those nets run at **0.0625 mm**, where grid and physical components
  match on every layer (`run_cases.FINE`). The other nets run at 0.125 mm.
- 37/37 cases complete, 0 uncovered contacts, energy balance within the kit's tolerance.
- BUS_P mesh convergence (J8 → Q2, 15 A): 3.640 / 3.544 / 3.494 mΩ at 0.25 / 0.125 / 0.0625 mm.
  The spread is 4.2 %, above the 3 % criterion (`summary.json` records the failure). The steps
  halve (0.096, then 0.050 mΩ): first-order convergence from above. So the 0.125 mm values
  overstate R and loss by about 3 %, which is conservative for heating. Not a model defect.
- Vias inside a same-net SMD pad are modelled filled (one node per layer, plating-only vertical
  resistance), because they are ordered epoxy-filled and copper-capped (DECISIONS.md
  2026-10-08). Without that the kit refused to inject at R5.4's centre.

## Finding and fix: the R5 shunt current vias

The first pass on stage-5 copper (same scripts) found the shunt fed through **two 0.3 mm vias
on HV_RET and three on LEG_RET**. Up to **18.1 A in one via** in the coherent HV_RET case, and
10.8 A in leg A's 34 A case. Native-17 had three 0.8 mm vias per side (worst 13.8 A, about 5.5 A
per mm of barrel circumference). Stage 6 (`native-21/layout/patches21.py`) adds legal 0.6/0.3
vias: 7 in R5.4's pad and 10 at R5.1 (5 in the pad). A phantom SW_B B.Cu outline under R5 had
blocked R5.4; its fill there was 0 mm². Result:

| Case (18 µm) | worst via, stage 5 | worst via, stage 6 | vias > 3 A |
| --- | ---: | ---: | ---: |
| hv_dc 15 A | 7.99 A | 3.21 A | 1 |
| hv_mixed_a 34 A coherent | 18.12 A | 7.27 A | 6 |
| leg_a_18p7 | 5.92 A | 3.26 A | 1 |
| leg_a_34 coherent | 10.77 A | 5.93 A | 3 |

The >3 A flag is the task's screening flag, not a via rating. The remaining worst value is in the
deliberately pessimistic coherent 34 A experiment, at about 7.7 A per mm of barrel
circumference (native-17's coherent case: 5.5). The realistic 18.7 A leg cases are at about
3 A per via.

## Native-21 against native-17 (`compare_native17.py`, `outputs/compare_native17.json`)

| Path (18 µm) | R native-17 → native-21 (mΩ) | Loss native-21 | Note |
| --- | --- | ---: | --- |
| BUS_P J8 → Q2, 15 A | 7.92 → **3.54** | 0.80 W | shorter trunk; 4 flagged vias → 0 |
| BUS_P J8 → Q5, 15 A | 6.92 → 5.90 | 1.33 W | |
| BUS_P local HF, 19 A | 0.87 / 0.95 → 1.60 / 1.49 | 0.58 W | film row further out (FINDINGS M11) |
| HV_RET R5 → J10, 15 A | 3.63 → **6.18** | 1.39 W | longer west return to the link block |
| LEG_RET leg A / B, 18.7 A | 1.88 / 0.84 → 1.73 / **0.25** | 0.61 / 0.09 W | |
| SW_A tank path, 18.7 A | 4.95 → 4.15 | 1.45 W | |
| **SW_B tank path, 18.7 A** | 4.97 / 6.39 → **7.39 / 7.42** | **2.58 / 2.60 W** | the largest copper loss on the board |
| RES_A, COIL_FEED | 0.66 → 0.73, 0.83 → 0.41 | ≤ 0.26 W | |
| Mains entry N / L, 15 A | 1.61 → 2.65, 0.61 → 0.64 | 0.60 / 0.14 W | |

Peak sheet densities are grid-local contact values (largest 75.8 A/mm at a SW_A pad edge,
38.5 A/mm COIL_FEED). As in rounds 3–4, they are not IPC width limits.

**What this means.** No path fails a screen, because the task has no acceptance rule for these
experiments. Two paths cost more copper loss than on native-17:
- SW_B's tank path: about 2.6 W at 18.7 A, +0.8 W;
- HV_RET's west return: 1.4 W at 15 A, +0.6 W.

Both are spread over long pours. Whether they matter is the thermal question (B3), which needs
task 03's board heat sources. Until then they are carried as findings, not verdicts.

## Reproduce (unit root)

```sh
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
MP=/Users/bennet/Miniforge3/bin/python3
R=validation-results/04-board-current-thermal/round5-native21
$KP tools/export_power_copper.py <stage-6 board> $R/inputs/power_copper.json.gz
$MP validation-results/04-board-current-thermal/round3/scripts/kit_topology_native13.py $R/inputs/power_copper.json.gz $R/outputs/kit_topology_p0125.json 0.125
$MP validation-results/04-board-current-thermal/round3/scripts/kit_topology_native13.py $R/inputs/power_copper.json.gz $R/outputs/kit_topology_p00625.json 0.0625
cd $R && WORKERS=6 $MP run_cases.py
$MP run_board.py --net bus_p --source J8.1:15 --sink Q2.2 --pitch 0.25 --plating 18 --name bus-dc-q2-p025-pl18
$MP run_board.py --net bus_p --source J8.1:15 --sink Q2.2 --pitch 0.0625 --plating 18 --name bus-dc-q2-p00625-pl18
$MP summarize.py && python3 compare_native17.py
```

Heat-field arrays (`*.npz`) are ignored by git, as in rounds 3–4.

## Tank-path width screen and the SW_B neck fix

Each tank path rides on one copper layer and carries the full tank current: SW_B on B.Cu, SW_A on
F.Cu. Section widths are measured by cutting the filled copper every 2 mm along each run. The
screen is the project's width screen (IPC-2221B, 70 µm, 20 K rise; as for D4 condition 1), with the
tank RMS from task 05 / task 03: **21.47 A nominal** (120 V, 1710 W cast iron) and **44.70 A at the
108 V low-R grid extreme**.

- **Before:** SW_B had a ~16 mm section at **4.4–5.6 mm** (x 58–74). That is a ~16 A screen, so
  ~39 K at the nominal 21.5 A: **failed**. Cause: the SW_A B.Cu link pour above it (3.2 mm HOT
  spacing) and C38/C39's antipads below.
- **Fix** (`native-21/layout/patches21.py`, stage 6): the SW_A link pour, which only parallels SW_A's
  F.Cu path, is trimmed to y ≤ 12.5. SW_B's lane top is raised to y 15.7 over x 57–79.7. The
  high-side Cgs/R71 return via moves 0.6 mm, to (73.1, 15.2), with a 3.7 mm keep-out round it.
  It ties that F.Cu island to SW_A's B.Cu pour (removing the via split the SW_A pour, so it stays).
  The section is now **7.2–9.3 mm**, and SW_B R goes from 7.39 to 7.00 mΩ.
- **After, at nominal 21.5 A:** SW_B's long sections (8.1–8.5 mm) ≈ 15 K. SW_A's 12 mm section at
  7.0 mm ≈ 18.8 K (22.0 A screen): passes, without much margin.
- **Short constrictions remain** on SW_B at x 36–48: 3.1–6 mm over 4–6 mm, bounded by the low-side
  Cgs return via and C40's pins, both gate/power-loop items. A 1-D fin estimate between the wide
  sections gives ≈ 1 K local rise at 21.5 A. A long-trace screen does not apply to them.
- **At the 44.7 A extreme every tank section fails** (≈ 60–72 K), and so do parts: R5 dissipates
  2.0 W against its 1 W rating, and C21/C22 carry 18.2 A RMS against CDE's 10.3 A at 70 °C. So
  44.7 A RMS is not a supported operating point for this board. The interim decision (DECISIONS.md
  2026-10-08) is a firmware tank-RMS ceiling of 22 A, set by the copper screen.

## B3 thermal solve (`b3/`)

`b3/make_heat_sources.py` builds native-21's board heat (46 parts). It takes task 03's quantified
parts by reference and adds bias_sizing.py's gate-drive, push-pull and LDO losses plus stated
estimates for the AC-DC modules, bus capacitors and small rails. Board share: **8.9 W nominal /
18.3 W worst**. `b3/run_study.py` adds the copper Joule heat of every power net, scaled to the
operating point by (I_op / I_case)²: 8.6 W nominal, 35.3 W at the extreme.

`b3/thermal.py` is round 4's solver with three changes:
- several A4 cases with I² scales;
- the board-hash check against round 5's export;
- a fix: sub-cell SMD pads fell back to one B.Cu cell, possibly bare FR-4, a false hot spot (U3).

| Run (50 °C ambient) | Source | Peak 1 mm grid | Peak 0.5 mm grid |
| --- | ---: | ---: | ---: |
| nominal, h 10 / 25 W/m²K | 17.5 W | 176 / 152 °C at U26 | 139 / 111 °C at the mains entry |
| extreme, h 10 / 25 | 53.6 W | 353 / 237 °C | 392 / 263 °C at R5 |

**These peaks are not temperatures to decide on.** They move 30–50 K and change place between
grids. Each part's heat goes into its pad copper only: no conduction through the package to air,
and convection only from the board faces. So a 0.87 W 5 × 5 mm LDO reads 136 K hotter than ambient,
where its datasheet θJA (~35 °C/W) gives about 31 K. That is round 3–4's limitation, unchanged.
What the solve does show: board heat is concentrated in the power core and the LS bias block, and
the extreme case puts ~54 W into a board cooled by its faces. Part temperatures use datasheet
ratings, as above.

### Stage 8 re-run (2026-10-08, board `d4468ffd…`)

Stage 8's independent-review fixes ran through task 04 and B3 again. `inputs/power_copper.json.gz`
and `outputs/` now hold the stage-8 results; the stage-6 tables above are kept as the record.
- **Copper screen:** 37 scenarios; the tank paths are unchanged. SW_A 4.146 mΩ, SW_B high / low
  6.980 / 7.010 mΩ and coil feed 0.410 mΩ are identical to stage 6. The HV_RET mixed case moved
  2.013 → 2.020 mΩ.
- **BUS_P mesh span:** 4.109 %, the same as stage 6, so it's not new.
- **B3:**

| Run (50 °C ambient) | Peak 1 mm grid | Peak 0.5 mm grid |
| --- | ---: | ---: |
| nominal, h 10 / 25 W/m²K | 162 / 138 °C at U26 (stage 6: 176 / 152) | 132 / 108 °C (R5 / L1) |
| extreme, h 10 / 25 | 363 / 237 °C | 402 / 268 °C at R5 |

U26's pad cell falls 14 K, which is consistent with its new 3 × 3 exposed-pad vias (review B2). The
caveat above stands: these are grid-sensitive pad-cell values, not part temperatures. The extreme
runs rise 1–10 K and remain outside the 22 A envelope.

### Stage 9 re-run (2026-10-08, board `e9d1cc4f…`)

`inputs/` and `outputs/` hold stage 9.
- **Copper screen:** 37 scenarios; the tank paths are identical to stage 8 (SW_A 4.146, SW_B 6.980 / 7.010, coil feed 0.410 mΩ).
- **BUS_P mesh span:** 4.110 %, as before.
- **B3:** U26's pad cell is 167 / 143 °C nominal at h 10 / 25 (stage 8: 162 / 138), with the same grid caveat. The extreme runs are 352 / 236 °C at 1 mm and 392 / 263 °C at 0.5 mm.

**Verdict, task 04 on native-21:** nominal operation passes the copper width screen after the SW_B
fix (SW_A at 18.8 K is the tightest). The board needs a tank-current ceiling (22 A RMS interim).
Bench IR at nominal power remains the physical gate (D4).

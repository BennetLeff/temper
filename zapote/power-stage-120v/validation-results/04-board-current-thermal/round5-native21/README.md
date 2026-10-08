# Task 04 round 5: board current screen on native-21 (stage 6)

The round-4 A4 experiments (same imposed currents and pad names, plus the two mains-entry
cases), run on native-21 copper: the enclosure re-layout's new current paths, which D4's
conditions require screening before fabrication.

- **Board:** native-21 stage 6, SHA-256 `e7b8fe77…` (`inputs/power_copper.json.gz`,
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

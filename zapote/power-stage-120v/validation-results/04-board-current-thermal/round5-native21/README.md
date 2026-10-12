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

### Stage 10 re-run (2026-10-08, board `ef993141…`)

- **Copper screen:** SW_A and the coil feed are unchanged (4.146 / 0.410 mΩ). SW_B high / low are 7.000 / 7.031 mΩ, +0.3 %, from routing near the LS block.
- **BUS_P mesh span:** 4.110 %.
- **B3:** U26's pad cell is 171 / 146 °C nominal at h 10 / 25 (stage 9: 167 / 143), within the grid caveat above.

### Stage 11 re-run (2026-10-08, board `e85a4c82…`)

- **Copper screen:** tank paths as stage 10; BUS_P mesh span 4.110 %.
- **B3:** U26's pad cell is 178 / 150 °C nominal at h 10 / 25. The peak has drifted up over stages 8–11 (162 → 167 → 171 → 178 at h 10) as re-routes cut U26's In1 n_ls spreading plane, measured within 12 mm: 181 → 171 → 165 → 162 mm² (stage 7: 154 mm², with 9 n_ls vias against 21 now).
- The grid caveat above stands, and U26 is a ~0.9 W part with a datasheet θJA of ~35 °C/W. This is a watch item: IR-check U26 at first power-up.

### Stage 12 re-run (2026-10-09, board `fc386321…`)

- **F1 change:** F1 is now a Class CC fuse in 10 × 38 clips with **plated slots**. `run_board.py` and `summarize.py` model a slot as the equal-area round filled barrel (1.2 × 2.5 mm becomes ⌀1.85 mm), slightly below the equal-perimeter 2.03 mm, so it is conservative for the layer transfer.
- **Line entry:** ac_l_main (J1 → F1, 15 A) is **0.313 mΩ** (stage 11: 0.644), because F1 now sits closer to J1.
- **Tank paths:** as stage 11.
- **BUS_P mesh span:** 4.111 %.
- **B3:** U26's pad cell is 162.8 / 138.4 °C.

### Stage 13 re-run (2026-10-09, board `d7baa28a…`)

- **Change:** the resonant bank is now 5 × TDK B32654 radials in the C21–C23 slot. The B.Cu res_a strip is re-cut, and the sw_b band's lower edge rises from y 50 to 46.8 over x 150–188.
- **Tank paths:** res_a is **0.668 / 0.771 mΩ** (18 / 12 µm plating; stage 12: 0.731 / 0.819). sw_b high is 7.08 / 7.32 mΩ (+1.2 / +1.0 %) and sw_b low is 6.88 / 7.10 mΩ (−2.2 / −1.9 %). Every other row changed by less than 0.5 %.
- **BUS_P mesh span:** 4.111 % (unchanged).
- **B3:** 162.2 / 138.0 °C at U26, within 0.6 K of stage 12.

### Stage 14 re-run (2026-10-10, board `3eb54216…`)

- **Change:** one RECOM R24C2T25/R-R module per high side (U41/U42) replaces the SN6507 / T2 / T3 bias. Each module has N_LS / N_Hx heat-spread pours on F.Cu and B.Cu with stitching vias, and U42's primary also spreads on In1 / In2. C5/C6 are now 9 µF, and D3/D17 are a series clamp pair. Tank copper is untouched.
- **Heat sources:** U41/U42 are 1.09 W each to the board. That is the 40 kHz module-loss allocation (ALT-BIAS 3.2), and it applies to the nominal case too, so it is conservative there. The SN6507 / T2 / T3 / LDO-split sources are gone (`b3/make_heat_sources.py`).
- **BUS_P mesh span:** 4.130 % (stage 13: 4.111 %).
- **B3, nominal h 10 / 25:**
  - U42's pad cell is **161.9 / 128.9 °C** and U41's is **135.6 / 102.6 °C**. The board peak at h 10 equals stage 13b's (U26, 162.2 °C).
  - With U42's primary pour on F.Cu only, U42 was 175.6 °C. Adding B.Cu gave 175.2 °C, because SW_B's B.Cu link cuts that pour. Adding In1 / In2 brought it to 161.9 °C.
  - Watch item: the module is rated −40…100 °C, and the B3 pad cell is not its case temperature. Measure U41/U42 case temperature at first power-up in the enclosure, at 33 and 80 kHz (ALT-BIAS bench gate).

### Stage 15 re-run (2026-10-10, board `5b9dbd61…`): 28 A tank hardware

- **Copper:**
  - SW_A's F.Cu leg to T1 is widened past J5's bite (P-A1, from y 55).
  - SW_B gains the y 46.8–50 band at the bank (P-B1) and 0.4–3.8 mm off l_filt (P-B1b, P-B3).
  - Proposals and widths: `../../02-protection-timing/stage15-28A/`.
- **New A4 case `sw_a_low`** (Q3 → the B.Cu leg-A link → T1, the A low-side state): **6.69 / 7.00 mΩ** at 18 / 12 µm, against sw_a 3.82 mΩ. B3 now splits SW_A 0.5 / 0.5 like SW_B.
- **Bank cases:** the bank cases now share across all five TDK parts (C21–C23, C151, C152).
- **Heat-source fixes** (`b3/make_heat_sources.py`):
  - The bank rows are TDK B32654: ESR_typ 19.3 mΩ (data sheet p.23) and tan δ limits (p.35), with a board fraction of 0.3.
  - The `extreme` case is the 29.4 A firmware RMS trip; round 3's 44.7 A grid extreme can no longer be reached.
  - New `c28` case: 29.4 A tank, 11.1 A line.
- **B3:**
  - Nominal h 10 / 25: 163.0 / 133.3 °C.
  - c28: 202.7 / 142.0 °C. At h 25 the peak is the FET-row tank copper (76.5, 9.5).
  - `b3/ceiling_sweep.py` (h 25, at 1.05 × ceiling): 22 / 24 / 26 / 28 A → 133.4 / 133.7 / 133.9 / **142.0 °C**. Up to 26 A the peak stays at nominal's parts; at 28 A the FET-row copper takes over.
  - **Supported commissioned ceiling: 26 A**. 28 A needs the FET-row rework (stage 15b) or bench IR (DECISIONS item 13).
- **BUS_P mesh span:** 4.130 %.

### Stage 15b re-run (2026-10-10, board `9a9c43c6…`): 28 A supported

- **Study:** `stage15b/` (PLAN-15b.md; `run_all.sh` reruns it).
- **Stage 15's 142.0 °C peak:** mostly a mesh artefact. A copper-less 1.0 mm cell received A4 pour-edge heat.
  - `stage15b/b3-model/thermal_snap.py` conserves energy onto copper cells; with it, the FET row is 136.6 °C at 1.0 mm and 126.9 / 128.6 °C at 0.5 / 0.25 mm.
  - Gating stays on the committed thermal.py.
- **Fix c2h:** the B.Cu leg-A link is raised to y 13.5 over x 50.5–70, SW_B's lane drops to 16.7, and the Q2.3 / BR1.1 F.Cu corner is filled.
- **Paths:** sw_a 3.75, **sw_a_low 6.37** (was 6.69), sw_b_high 6.65 mΩ (+1.2 %).
- **Ceiling sweep** (h 25, committed model): 22 / 24 / 26 / 28 A → 133.4 / 133.7 / 133.9 / **134.1 °C**, all at U26. **28 A is supported.**
- **h 10** (fan failure) at 28 A is 198.0 °C, which the controller's blower-stall derate has to own.

### Stage 16 re-run (2026-10-12, board `e9481ed6…`)

- **Change:** the F2 / J11 blower-supply mains tap beside PS1; tank copper is unchanged.
- **BUS_P span:** 4.129 %.
- **B3 ceiling sweep** (h 25): 133.2 / 133.4 / 133.7 / **133.9 °C** at 22 / 24 / 26 / 28 A, all at U26.

### Stage 17 re-run (2026-10-12, board `e40f1e27…`; R5 = Bourns CSS2H-2512R-1L00F)

- **Change:** R5's land only (`stage17-r5/`): pads 1 / 4 1.8 × 3.4 mm, two sense fingers west; the Kelvin pair
  is re-laid under R5 on In1; LEG_RET keeps 10 in-pad / pour vias, HV_RET has 6 (was 9: the pad's east half is
  within 3.2 mm of SW_B's B.Cu lane, and the N finger takes the old north row).
- **R5 heat** (`b3/make_heat_sources.py`, `thermal.py` `pad_numbers`): 0.864 W at the 29.4 A trip on the
  current pads 1 / 4 only; the CSS2H sense fingers are land, not part terminals.
- **Worst R5 via** (34 A coherent, hv_mixed_a pl18): 8.78 A (was 7.27) at (38.1, 15.0).
- **BUS_P span:** 4.129 %.
- **B3 ceiling sweep** (h 25): 130.2 / 131.1 / 132.1 / **135.9 °C** at 22 / 24 / 26 / 28 A; 22–26 A at U42,
  28 A at R5.4 (39.5, 14.5). Nominal h 10 / h 25: 163.2 / 129.1 °C.
- **U26 reads 7 K lower than in stage 16** (126.1 against 133.0 °C, nominal h 25) with identical copper.json near it:
  the In1 `n_ls LS block` and `ocp_kelvin_p protection` pours have the same priority and abut at y 75.3, and this
  build filled the 0.3 mm boundary strip to n_ls. Rebuild fill order, not a stage-17 change; until the priorities
  differ, read U26 as up to 133 °C.
- **G6 (R5 derating, go/no-go):** PASS. Pad-cell max 134.81 °C / mean 125.99 °C (0.25 mm, c28, h 25); CSS2H
  5 W at 70 °C terminal → 1.759 W derated, **margin 50.9 %** against the 20 % rule. Controls: the WSK FAIL
  (0.864 W against 0.2084 W at 149.16 °C) and the stage-16 solve (149.16 °C) reproduce. Sensitivity: heat on
  all four pads 134.34 °C (51.5 %); the stage-16 WSK board with heat on its current pads only is 123.43 °C, so
  most of stage 16's 149 °C was its isolated sense pad (the WSK still fails there: 0.47 W derated). `stage17-r5/g6.json`.

### Stage 17b re-run (2026-10-12, board `96501e7d…`; deterministic pour fill)

- **Change:** pour priorities only (`patches21.ZONE_WINNERS` / `resolve_zone_priorities`, gate
  `native-21/layout/gates/zone_priority_gate.py`). Seven different-net pour pairs sat closer than their clearance at
  equal priority, and three more exactly at it; KiCad's fill order gave the contested copper to either side. Between
  stages 14 and 17 that flipped In1 n_ls / ocp_kelvin_p (3.5 mm²), B.Cu sw_b / res_a at the bank (48 mm²), sw_a / sw_b,
  l_filt / sw_b and res_a / coil_feed. Winners: In1 n_ls (review call); the rest keep stage 15b's fill, the board
  DECISIONS 14 accepted for 28 A. Three builds (one after deleting every build product) agree within 0.04 mm² per
  net (`stage17-r5/fill17b.txt`).
- **B3 ceiling sweep** (h 25): 130.2 / 131.1 / 132.1 / **136.0 °C** at 22 / 24 / 26 / 28 A (22–26 A at U42, 28 A at R5.4).
  **U26 126.3 / 126.6 / 127.0 / 127.4 °C**; R5 115.5 / 121.8 / 128.6 / 136.0 °C. Nominal h 10 / h 25: 163.2 / 129.1 °C (U26 126.1).
- **G6:** PASS, R5 pad cells 134.87 °C max / 126.03 °C mean, 1.757 W derated, **margin 50.8 %**; controls reproduce.
- **R5 vias** (`stage17-r5/r5_vias17.py`; criterion `validation-plan/04-board-current-thermal.md:114`: report current and
  rise, > 3 A is a flag, no rated limit): worst 8.78 A at 34 A coherent (9.32 A/mm of barrel; stage 6 accepted 7.27 A,
  7.7 A/mm), 7.59 A at the 29.4 A trip, barrel Joule 0.029 W, mid-wall rise 0.28 K over its planes, B3 cell 133.04 °C,
  wall estimate 133.31 °C, under the R5 pad maximum and G6's 148.39 °C terminal bound. 10 of 18 R5 vias are flagged.

**Verdict, task 04 on native-21:** nominal operation passes the copper width screen after the SW_B
fix (SW_A at 18.8 K is the tightest). The board needs a tank-current ceiling (22 A RMS interim).
Bench IR at nominal power remains the physical gate (D4).

# Rev G jack protection study (started 2026-11-08)

Rev F has no protection on its four BNC jacks (audit AFE-01 to AFE-04). `../charged-dut/` measured the gap: 7 V with Kelvin clips when powered and 0.5–1 V when unpowered, against 1 J for a Keysight E4980A.

This study designs the Rev G protection while Rev F is built. Some final values wait for Rev F bring-up: the real ESD knee, the 3V3A rise, the switch's off capacitance and the clamps' C(V) (see "Open items").

**Target** (charged-dut README, "Rev G requirements"):
- **Minimum:** within every datasheet rating (class A) for 1 µF at 30 V, powered and unpowered, on every connection pattern.
- **Stretch:** 1 J.
- **Constraints:** no loss of accuracy, stability or low-impedance signal.

## Decision

**`parts_jackside`** (definition in `protection_screen.py` `CANDIDATES`):

| Where | Part | Per jack |
|---|---|---|
| At each BNC centre pin | H4V5HD3B TVS (C20615803, preferred) | ×4 |
| Jack → board, normally open | TLP172AM photoMOS (C2152276) | ×4 |
| In series after the switch | CRCW0805-HP 10 Ω on HCUR / LCUR, CRCW0603-HP 100 Ω on HPOT / LPOT | ×4 |
| At DUT_HI, HPOT, LPOT | H3V3LD5B TVS (C20615817, preferred); + 1 nF C0G on HPOT / LPOT (C106246) | ×3, ×2 |
| At DUT_LO | BAV99 as an antiparallel pair (C2500, basic) | ×1 |
| **Moved to the jack side** | R105 / R106 (CUR–POT 1 kΩ) and the K4 + R107 reference branch | — |
| HCUR and LCUR jacks | residual-voltage sense, 1 MΩ to an ADC pin biased at mid-scale | ×2 |

What it achieves, each from the section below:

| Requirement | Result |
|---|---|
| Surge, 1 µF at 30 V, every pattern and meter state | class A; class A up to 50 V (unpowered) and 200 V (powered) |
| Part ratings at 30 V | all covered; thinnest are the jack TVS (25.8 A vs 40 A) and the LCUR switch (0.61 A vs 1.5 A) |
| Accuracy (LCR-6100 verdicts over the map) | 144 / 22 / 43, the same as Rev F, with drift; 143 / 23 / 43 with amplitude dependence too |
| Stability (360-case full-chain matrix) | no margin lost: drive 47.76° (Rev F 47.76°), TIA 69.92° (57.28°), HIGH 57.90° (57.57°), LOW 57.17° (56.61°) |
| Signal | 1.06 dB less current into a short on the 100 Ω range; added noise ≤ 0.33 % of the codec floor |
| USB | 0.476 A typical with the switch drive, under 0.5 A |
| 1 J stretch | not met (the jack TVS would need about 1 kA); see "Part stress" |

The two layout moves come from phase 3:
- **R105 / R106 on the jack side.** On the board side, the board POT nodes see the current path's drop through the 1 kΩ: about 100/1100 of the switch and series-R voltage.
- **K4 + R107 on the jack side.** Channel B measures LOW − TIA, which on Rev G includes the LCUR switch and 10 Ω. With the reference on the jack side, the per-session reference check passes through the same switch and resistor, so it tracks the photoMOS on-resistance drift (≈0.6 %/°C).

The cost of the move is surge margin. Class A ends at 50 V instead of 200 V in the unpowered `h_to_gnd` pattern, where U6A's ESD cell reaches its 10 mA limit through the open switches' 20 pF. That is still above the 30 V target, and accuracy is the harder constraint.

## Phases

| Phase | What | Status |
|---|---|---|
| 1 | Surge screen of candidate topologies with parametric clamps, in the charged-DUT model | done |
| 2 | Real parts, rerun of the screen with their datasheet models | done (`part-selection/`) |
| 3 | Normal operation: signal loss, phase and drift, leakage at DUT_LO, noise | done |
| 4 | Stability: the full-chain matrix with the network | done |
| 5 | Accuracy map and noise rows | done (with 3) |
| 6 | Isolation switch drive, residual-voltage sense, power budget, firmware sequencing | done; schematic and layout wait for Rev F bring-up ("Open items") |

```sh
python3 validation/rev-g-protection/protection_screen.py --jobs 10   # ~20 min for all 12 candidates -> protection-screen.json
python3 validation/rev-g-protection/protection_screen.py --check-readme
python3 validation/rev-g-protection/normal_operation.py              # ~1 min -> normal-operation.json
python3 validation/rev-g-protection/normal_operation.py --check-readme
python3 validation/rev-g-protection/normal_operation.py --rust parts_jackside   # -> ../stability-full-chain/revg_network.rs
sh validation/rev-f-floorplan/run_matrix.sh revgcng100 8             # ~2 min -> matrix-final_revgcng100.md
(cd validation/stability-full-chain && python3 kelvin_summary.py matrix-final_revgcng100.md > summary-revgcng100.md)
python3 validation/rev-g-protection/drive_budget.py                  # -> drive-budget.json; exits 1 on a failed check
```

## Phase 1: surge screen

**Method.** `../charged-dut/charged_dut_spice.py` `deck()` takes a protection network (`prot=`). The leads then land on jack nodes, and the network connects those to the Rev F board nodes DUT_HI, HPOT, LPOT and DUT_LO. Every case is judged by the same `judge()`: all the OPA2810, LDO (including OUT beyond IN), TAC5112, BAT54S and passive ratings of Rev F. The screen runs:
- every connection pattern;
- all six meter states;
- 1 µF, at 0.5 V to 1000 V in both polarities.

**Harness checks.**
- Without a network, `deck()` writes byte-identical circuits; 720 sample circuits were compared by hash.
- The `links` candidate (zero-ohm links) reproduces all 30 baseline rows of `charged-dut.json` exactly.

**Parametric clamps (phase 1 only):**
- **TVS5:** BV 6.4 V, 0.06 Ω, 2 nF (a 5 V-standoff 400 W-class TVS).
- **TVS3:** BV 4 V, 0.1 Ω, 0.5 nF.
- **Schottky pair:** 0.31 V at 10 mA, 0.5 V at 1 A.
- **Isolation relay:** open (1 pF) when unpowered, 0.1 Ω when powered.

<!-- generated:screen -->
| Candidate | Lowest class-A voltage, 1 µF, any pattern and state | Powered | Unpowered | 30 V target | What ends it |
|---|---|---|---|---|---|
| `links` | 0.5 V | 3 V | 0.5 V | no | h_to_gnd unpowered/100R: u6b input 72.6 mA > 10 |
| `tvs_all` | 0 V | 3 V | 0 V | no | h_to_gnd unpowered/100R: u6b input 21.1 mA > 10 |
| `tvs_all_r1k_pot` | 0.5 V | 3 V | 0.5 V | no | l_to_gnd unpowered/100R: u7a input 31.9 mA > 10 |
| `iso_tvs` | 3 V | 3 V | 1000 V | no | l_to_gnd powered/5k: u7a Vdiff 7.16 V > 7 |
| `two_stage` | 1 V | 1000 V | 1 V | no | kelvin unpowered/100R: u6b input 10.6 mA > 10 |
| `iso_two_stage` | 1000 V | 1000 V | 1000 V | met | nothing up to 1000 V |
| `iso_two_stage_sum` | 400 V | 400 V | 1000 V | met | kelvin powered/100R: C78/C104 > 50 V; R106 57.9 V > 50 working |
| `parts` | 200 V | 200 V | 200 V | met | kelvin unpowered/100R: u6a input 10.2 mA > 10; u6a input 14.4 mA > 10 |
| `parts_ron_max` | 200 V | 400 V | 200 V | met | kelvin unpowered/100R: u6a input 10.2 mA > 10; u6a input 14.4 mA > 10 |
| `iso_tvs2_lo` | 400 V | 400 V | 1000 V | met | current_only powered/5k: u7a Vdiff 7.11 V > 7; u7a Vdiff 7.12 V > 7 |
| `parts_rcp_jack` | 50 V | 200 V | 50 V | met | h_to_gnd unpowered/100R: u6a input 10 mA > 10 |
| `parts_jackside` | 50 V | 200 V | 50 V | met | h_to_gnd unpowered/100R: u6a input 10 mA > 10 |
<!-- /generated -->

Candidates (full definitions in `CANDIDATES`):
- **`tvs_all`:** a TVS5 at each jack.
- **`tvs_all_r1k_pot`:** the same, plus 1 kΩ at HPOT and LPOT.
- **`iso_tvs`:** the jack TVSs plus a normally-open isolation relay on all four jacks.
- **`two_stage`:** jack TVSs; 10 Ω on HCUR and LCUR, 100 Ω + 1 nF C0G on HPOT and LPOT; a TVS3 second stage on HCUR, HPOT and LPOT, and a Schottky pair at DUT_LO.
- **`iso_two_stage`:** both.
- **`iso_two_stage_sum`:** the Schottky pair at the TIA summing node, behind R94, instead of at DUT_LO.
- **`iso_tvs2_lo`:** a TVS3 at DUT_LO instead of the Schottky pair.
- **`parts`, `parts_ron_max`, `parts_rcp_jack`, `parts_jackside`:** phase 2 parts (below).

### What the screen shows

1. **Unpowered, clamps alone cannot do it.** With the rails at 0 V, any current that reaches an op-amp pin charges the ±12 V rails past the LDOs' 0.3 V OUT-to-IN limit, or exceeds 10 mA in an ESD cell. HCUR and LCUR carry the measurement current, so they cannot take the kilohms that would stop it without losing signal on low-impedance parts. `two_stage` holds 1000 V powered but only 1 V unpowered.
2. **Powered, a jack clamp alone is not enough at the TIA.** Any jack clamp at ~7 V or more leaves LCUR high enough to exceed U7A's 7 V differential input on the 5 kΩ and 100 kΩ ranges. `iso_tvs` stops at 3 V for this reason. The fix is a low-voltage second stage at DUT_LO.
   - **Correction (phase 3).** The first version of this README called DUT_LO a virtual ground, on which a Schottky pair would never conduct. That is wrong. R94 (22 Ω) sits between DUT_LO and the summing node, so DUT_LO carries I × 22 Ω: about 0.25 V on the 100 Ω range with a short. A Schottky pair conducts there in use. Phase 3 measures what that costs, and phase 2 replaces it with a silicon pair.
3. **The follower differential limit needs the step slowed, not just clamped.** On HPOT and LPOT, 100 Ω + 1 nF slows the contact step enough for the followers to follow. This is why option A (1 kΩ into a few pF) did nothing powered.
4. **The isolation switch is what makes unpowered work.** It also only sees the jack clamp's voltage, not the DUT's. That opens up a photoMOS (normally open, a few mA of LED current, no contact wear) instead of a relay.

### Part stress, parametric `iso_two_stage` (sized phase 2)

<!-- generated:stress -->
| Part | At 1 µF, 30 V (the target) | Worst case in the screen (up to 1000 V) |
|---|---|---|
| `tvs1_hcur` | 24.1 A peak, 204 µJ | 1.06e+03 A peak, 186 mJ |
| `tvs2_hcur` | 0.527 A peak, 16 µJ | 12.5 A peak, 0.24 mJ |
| `tvs1_hpot` | 24.1 A peak, 207 µJ | 1.06e+03 A peak, 189 mJ |
| `tvs2_hpot` | 0.056 A peak, 10.8 µJ | 1.3 A peak, 0.0529 mJ |
| `tvs1_lpot` | 24.1 A peak, 207 µJ | 1.06e+03 A peak, 189 mJ |
| `tvs2_lpot` | 0.0516 A peak, 0.403 µJ | 1.29 A peak, 0.0248 mJ |
| `tvs1_lcur` | 24.1 A peak, 204 µJ | 1.06e+03 A peak, 186 mJ |
| `sch2_lcur` | 0.97 A peak, 3.4 µJ | 13.1 A peak, 0.0305 mJ |
| `r_hcur` | 5.29 V, 2.8 W peak, 5.17 µJ | 125 V, 1.55e+03 W peak, 2.04 mJ |
| `r_hpot` | 9.97 V, 0.993 W peak, 1.47 µJ | 129 V, 167 W peak, 0.222 mJ |
| `r_lpot` | 11 V, 1.21 W peak, 1.47 µJ | 129 V, 167 W peak, 0.222 mJ |
| `r_lcur` | 9.66 V, 9.34 W peak, 31 µJ | 131 V, 1.72e+03 W peak, 2.43 mJ |
<!-- /generated -->

- Each clamp's energy is its current times its own node voltage: the jack, the second-stage node or tia_sum. Before 2026-11-08 every clamp used the jack voltage, which overstated the second-stage energies.
- **The 1000 V rows** are a 1 µF tank cap at 1000 V. They put about 1 kA through each jack TVS and kilowatt peaks into the series resistors. That is the 1 J stretch, and no single SMA or SOD part covers it.

## Phase 2: parts

`part-selection/PARTS.md` and `part-selection/parts.json` list every pick with its datasheet URL, SHA256, the quoted rating rows, the JLC stock and price, and the SPICE fit points. The fits are ngspice DC solves against the datasheet points, with errors of ≤ 2 % (TVS) and ≤ 0.6 % (BAV99). The datasheets are not committed; the hashes are the record.

The screen runs the parts with those models (`H4V5HD3B`, `H3V3LD5B`, `BAV99`, `TLP172AM` in `protection_screen.py`):
- **`parts`:** class A to 200 V. The real clamps sit above the parametric ones, which costs headroom against the phase-1 1000 V.
- **`parts_ron_max`:** the same at the switch's 2 Ω maximum RON.
- **`parts_jackside`:** class A to 50 V, as explained in "Decision".

### Part stress against ratings, `parts_jackside`

<!-- generated:stress_parts -->
| Part | At 1 µF, 30 V | Rating (part-selection/PARTS.md) | Margin |
|---|---|---|---|
| `tvs1_hcur` | 25.7 A peak | H4V5HD3B IPP 40 A (8/20 µs) | ×1.6 |
| `tvs2_hcur` | 0.295 A peak | H3V3LD5B IPP 8 A (8/20 µs) | ×27 |
| `tvs1_hpot` | 25.8 A peak | H4V5HD3B IPP 40 A (8/20 µs) | ×1.6 |
| `tvs2_hpot` | 0.0356 A peak | H3V3LD5B IPP 8 A (8/20 µs) | ×225 |
| `tvs1_lpot` | 25.8 A peak | H4V5HD3B IPP 40 A (8/20 µs) | ×1.6 |
| `tvs2_lpot` | 0.0356 A peak | H3V3LD5B IPP 8 A (8/20 µs) | ×225 |
| `tvs1_lcur` | 25.8 A peak | H4V5HD3B IPP 40 A (8/20 µs) | ×1.6 |
| `sch2_lcur` | 0.595 A peak | BAV99 IFSM 4 A (1 µs) | ×6.7 |
| `r_hcur` | 0.891 W peak | CRCW0805-HP ~450 W at 1 µs | ×505 |
| `r_hpot` | 1.15 W peak | CRCW0603-HP ~250 W at 1 µs | ×217 |
| `r_lpot` | 1.15 W peak | CRCW0603-HP ~250 W at 1 µs | ×216 |
| `r_lcur` | 3.71 W peak | CRCW0805-HP ~450 W at 1 µs | ×121 |
| LCUR switch (TLP172AM, in series with `r_lcur`) | 0.609 A peak | IONP 1.5 A (100 ms) | ×2.5 |
<!-- /generated -->

- The resistor pulse ratings are read off the CRCW-HP single-pulse curves (±10–20 %), at 1 µs; the screen's pulses last ~1–3 µs.
- The photoMOS current is `r_lcur`'s peak voltage over 10 Ω.

## Phases 3 and 5: normal operation and the accuracy map

**Method** (`normal_operation.py`).
- Each candidate is linearized with the meter powered and the switches closed:
  - per jack, c1 + g1 at the BNC, r in series, and c2 + g2 at the board node;
  - the clamps with their full junction C and conduction.
- `../rev-e-improvements/revE_front.py` takes the network as `PROT`, and optionally puts R105 / R106 (`rcp_at_jack`) and the reference branch (`ref_at_jack`) on the jack nodes. With `PROT = None` the model is unchanged: the committed accuracy map, variants and attribution, and the improvements study, rerun byte-identical.
- `../rev-e-accuracy-map/accuracy_map.py` `run_map()` then reruns the map with the network, in three steps:
  - **linear:** the network at 0 V, fixed;
  - **drift:** plus temperature drift between calibration and measurement, at the map's own ±5 °C typical / 15 °C corner. The TCs are estimates:
    - junction C: 0.1 %/°C;
    - C0G: 30 ppm/°C;
    - photoMOS RON: 0.6 %/°C;
    - resistors: 100 ppm/°C;
    - junction leakage: doubles every 10 °C.
  - **level:** plus amplitude dependence, each clamp's fundamental C and G at its node amplitude for that DUT. TVS C(V) follows the Nexperia PESD3V3L1BSL curve shape, because the HJC datasheets give none.
- **Self-check:** zero-ohm links reproduce the committed map, with the same verdicts and every cell within 1e-3 of its own value (`normal-operation.json` `selfcheck`).
- **Usable cells:** the "worst added error" columns count only cells the committed map has within 1 %. The 10 MΩ / 85 kHz cells are already 100× off and are ill-conditioned.

<!-- generated:normal_map -->
| Candidate | Mode | LCR-6100 (1 m) ✓ / ~ / ✗ (without the network: 144 / 22 / 43) | Worst added error, corner, usable cells | Where |
|---|---|---|---|
| `iso_two_stage` | linear | 141 / 24 / 44 | 0.39 % (×1.53 of the cell) | 100 range, 50 Hz, 100 mΩ, phase |
| `iso_two_stage` | drift | 85 / 79 / 45 | 1.8 % (×5.55 of the cell) | 100k range, 85k Hz, 31.6 kΩ, |Z| |
| `iso_two_stage` | level | 38 / 97 / 74 | 12 % (×20.64 of the cell) | 100 range, 85k Hz, 1 kΩ, phase |
| `iso_two_stage_sum` | linear | 141 / 24 / 44 | 0.39 % (×1.53 of the cell) | 100 range, 50 Hz, 100 mΩ, phase |
| `iso_two_stage_sum` | drift | 86 / 78 / 45 | 1.8 % (×5.53 of the cell) | 100k range, 85k Hz, 31.6 kΩ, |Z| |
| `iso_two_stage_sum` | level | 86 / 80 / 43 | 1.8 % (×16.20 of the cell) | 100k range, 85k Hz, 1 kΩ, |Z| |
| `iso_tvs2_lo` | linear | 141 / 24 / 44 | 0.39 % (×1.53 of the cell) | 100 range, 50 Hz, 100 mΩ, phase |
| `iso_tvs2_lo` | drift | 86 / 78 / 45 | 1.8 % (×5.54 of the cell) | 100k range, 85k Hz, 31.6 kΩ, |Z| |
| `iso_tvs2_lo` | level | 86 / 80 / 43 | 1.8 % (×16.21 of the cell) | 100k range, 85k Hz, 1 kΩ, |Z| |
| `parts` | linear | 142 / 24 / 43 | 0.4 % (×1.54 of the cell) | 100 range, 50 Hz, 100 mΩ, phase |
| `parts` | drift | 133 / 33 / 43 | 0.42 % (×1.54 of the cell) | 100 range, 200 Hz, 100 mΩ, |Z| |
| `parts` | level | 132 / 34 / 43 | 0.42 % (×1.54 of the cell) | 100 range, 200 Hz, 100 mΩ, |Z| |
| `parts_ron_max` | linear | 142 / 24 / 43 | 0.41 % (×1.56 of the cell) | 100 range, 50 Hz, 100 mΩ, phase |
| `parts_ron_max` | drift | 125 / 41 / 43 | 0.46 % (×1.60 of the cell) | 100 range, 200 Hz, 100 mΩ, |Z| |
| `parts_ron_max` | level | 124 / 42 / 43 | 0.46 % (×1.60 of the cell) | 100 range, 200 Hz, 100 mΩ, |Z| |
| `parts_rcp_jack` | linear | 142 / 24 / 43 | 0.12 % (×1.16 of the cell) | 100 range, 50 Hz, 100 mΩ, phase |
| `parts_rcp_jack` | drift | 128 / 38 / 43 | 0.2 % (×8.54 of the cell) | 100 range, 85k Hz, 31.6 Ω, phase |
| `parts_rcp_jack` | level | 127 / 39 / 43 | 0.2 % (×2.82 of the cell) | 5k range, 85k Hz, 10 kΩ, phase |
| `parts_jackside` | linear | 144 / 22 / 43 | 0.066 % (×1.08 of the cell) | 100 range, 200 Hz, 100 mΩ, phase |
| `parts_jackside` | drift | 144 / 22 / 43 | 0.17 % (×5.14 of the cell) | 5k range, 85k Hz, 3.16 kΩ, phase |
| `parts_jackside` | level | 143 / 23 / 43 | 0.18 % (×2.57 of the cell) | 5k range, 85k Hz, 10 kΩ, phase |
<!-- /generated -->

<!-- generated:normal_grid -->
`parts`, level mode: worst added corner error over the usable cells (max of |Z| and phase), %; — = no usable cell

| Range | 50 | 100 | 200 | 500 | 1k | 2k | 5k | 10k | 20k | 50k | 85k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 0.4 | 0.38 | 0.42 | 0.26 | 0.35 | 0.27 | 0.37 | 0.34 | 0.07 | 0.1 | 0.16 |
| 5k | 0.0039 | 0.0027 | 0.0017 | 0.0019 | 0.002 | 0.0032 | 0.011 | 0.025 | 0.051 | 0.12 | 0.17 |
| 100k | 0 | 0 | 0 | 0 | 0.0015 | 0.0015 | 0.0053 | 0.019 | 0.044 | 0.11 | 0.15 |

`parts_jackside`, level mode: worst added corner error over the usable cells (max of |Z| and phase), %; — = no usable cell

| Range | 50 | 100 | 200 | 500 | 1k | 2k | 5k | 10k | 20k | 50k | 85k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 0.059 | 0.06 | 0.066 | 0.059 | 0.059 | 0.061 | 0.056 | 0.065 | 0.021 | 0.058 | 0.096 |
| 5k | 0.0051 | 0.0033 | 0.0026 | 0.0017 | 0.0022 | 0.0034 | 0.012 | 0.025 | 0.053 | 0.12 | 0.18 |
| 100k | 0.0033 | 0.0017 | 0.0011 | 0.0009 | 0.0018 | 0.0016 | 0.0053 | 0.02 | 0.046 | 0.12 | 0.16 |
<!-- /generated -->

<!-- generated:normal_signal -->
| Candidate | Short-circuit current, 100 Ω / 5 kΩ / 100 kΩ range (mA, without → with) | SNR loss, 100 Ω range | Added noise vs the codec floor: POT series R / LCUR series R (worst range) | Summing-node clamp drift, worst (corner) |
|---|---|---|---|---|
| `iso_two_stage` | 10.1 → 8.99 / 0.335 → 0.334 / 0.017 → 0.017 | 0.98 dB | 0.33 % / 0.075 % | no summing-node clamp |
| `iso_two_stage_sum` | 10.1 → 8.99 / 0.335 → 0.334 / 0.017 → 0.017 | 0.98 dB | 0.33 % / 0.075 % | 0.24 % (100k range, 85k Hz) |
| `iso_tvs2_lo` | 10.1 → 8.99 / 0.335 → 0.334 / 0.017 → 0.017 | 0.98 dB | 0.33 % / 0.075 % | no summing-node clamp |
| `parts` | 10.1 → 8.9 / 0.335 → 0.334 / 0.017 → 0.017 | 1.06 dB | 0.33 % / 0.078 % | no summing-node clamp |
| `parts_ron_max` | 10.1 → 8.81 / 0.335 → 0.334 / 0.017 → 0.017 | 1.15 dB | 0.34 % / 0.082 % | no summing-node clamp |
| `parts_rcp_jack` | 10.1 → 8.9 / 0.335 → 0.334 / 0.017 → 0.017 | 1.06 dB | 0.33 % / 0.078 % | no summing-node clamp |
| `parts_jackside` | 10.1 → 8.9 / 0.335 → 0.334 / 0.017 → 0.017 | 1.06 dB | 0.33 % / 0.078 % | no summing-node clamp |
<!-- /generated -->

What it shows:
1. **Capacitance on HPOT loads the reference check.**
   - The parametric 2 nF clamps lose 58 of the map's 144 ✓ cells to drift. Zeroing the TVS-capacitance TC restores 140.
   - With 2 nF on one jack at a time, the HPOT jack costs 59 cells; HCUR, LPOT and LCUR cost 5–6 each.
   - **Mechanism:** the per-session reference check runs with the leads unplugged, so HPOT is fed only through R105's 1 kΩ. Any capacitance on the HPOT side shifts that reading's phase. Calibration takes out the shift, but not its drift, and every measurement is corrected by the check. LPOT sits near 0 V, so its capacitance barely matters.
   - The H4V5HD3B's 100 pF (against an SMAJ's 1.15 nF) keeps this small. What remains in `parts_jackside` is the 1.1 nF of mostly C0G on HPOT: about 0.1–0.2 % at 50–85 kHz in the corner (the grid above).
   - If that residual matters, two options remain: K4's second pole shorting HCUR to HPOT during the check (`revE_front.measure(bypass=True)`), or a smaller POT capacitor at some cost in surge slowing. Neither is tested here.
2. **A Schottky pair at DUT_LO is unusable.** At the I × 22 Ω DUT_LO carries, its conduction is level-dependent: `iso_two_stage` drops to 38 ✓ in level mode. A pair at the summing node instead (`iso_two_stage_sum`) does not conduct, but its leakage drifts against the TIA's finite loop gain (0.24 % at 85 kHz on the 100 k range). The BAV99 silicon pair at DUT_LO does neither.
3. **The switch on-resistance drifts, and two board moves absorb it.**
   - `parts` holds 133 ✓, but zeroing the RON TC alone restores 142. The drift reaches the result twice:
     - through R105 / R106 into the board POT nodes;
     - through channel B, which measures LOW − TIA and so includes the LCUR switch and its series resistor.
   - Moving R105 / R106 to the jacks removes the first: the 100 Ω-range worst cell drops from 3.4 % to 0.7 %.
   - Moving the K4 + R107 reference to the jacks removes the second, because the per-session reference check then measures the same path. `parts_jackside` is back to Rev F's 144 / 22 / 43.
4. **Signal and noise are not the problem.**
   - The 10 Ω + 1 Ω on each CUR path lowers the 100 Ω range's short-circuit current from 10.1 to 8.9 mA, a 1.06 dB SNR loss. The map already includes it.
   - The 100 Ω POT resistors add 0.33 % of the codec noise floor.
   - The LCUR series R adds 0.08 % (it is in the current loop, so the TIA sees e_n divided by the loop impedance).
   - The `../rev-e-codec/` noise rows therefore stand as they are, less the 1.06 dB.
5. **Leakage at DUT_LO.**
   - The BAV99 pair is ~33 MΩ at 25 °C from its fit (the datasheet IR gives 1.5–3 MΩ typical, and ~60 kΩ at 85 °C). Against R94 that is a ≤ 4e-4 divider at 85 °C, mostly calibrated.
   - There is no DC across the DUT: the source is AC and the codec legs are AC-coupled. The sense bias's 1.6 µA is the only DC, below.

## Phase 4: stability

`loop_matrix.rs` mode `revgcng{C}` is the `revfcng{C}` grid on the extracted Rev F board, with the Rev G network from `revg_network.rs`:
- **Nodes:** the leads, the DUT and the fixture strays land on jack nodes jhc / jhp / jlp / jlc, and the network's small-signal elements join them to hi / hpot / lpot / low.
- **Element sets:** the nominal set on the nominal board, the HIGH set on the high board. HIGH is junction C ×2 (the H3V3LD5B's 25 pF maximum against 12.5 pF typical), leakage ×10 and RON ×2 (the TLP172AM maximum).
- **Jack side:** R105 / R106 and K4 + R107 sit on the jack nodes.
- **Regression:** rerunning `revfcng100` after the change rewrote all 720 committed Rev F decks and `matrix-final_revfcng100.md` byte-identical.

| Loop | Rev F `revfcng100` | Rev G `revgcng100` |
|---|---|---|
| drive | 47.76°, \|1+T\| 0.594 | 47.76°, 0.596 |
| TIA | 57.28°, 0.494 | **69.92°**, 0.707 |
| HIGH | 57.57°, 0.201 | 57.90°, 0.712 |
| LOW | 56.61°, 0.650 | 57.17°, 0.704 |
| upward unity crossings | 10 | **0** |

- The series resistors damp the lead resonances, which removes Rev F's multiple crossings.
- The 1 nF on HPOT / LPOT is behind 100 Ω, so the followers see an RC, not a capacitive load.
- `summary-revgcng100.md` has every row.

## Phase 6: drive, sense, budget and firmware

**Drive and sense** (`drive_budget.py`, all checks PASS):
- **Drive:** two strings of two TLP172AM LEDs from the switched 5 V, 300 Ω each, sunk by one AO3400A on GPIO 12 (the Q6 pattern, 100 kΩ gate pull-down). The switches are open from power-up until the firmware closes them, and open within 0.5 ms of losing VBUS. `part-selection/PARTS.md` suggested about 400 Ω; that gives 3.8 mA at the lowest rail, below the 5 mA RON is specified at, so it is 300 Ω here.
  - 5.07 mA per LED at 4.32 V and VF max (≥ 5 mA recommended, IFT ≤ 3 mA);
  - 11.0 mA at 5.5 V and VF min (≤ 25 mA);
  - 16.4 mA total typical.
- **Sense:** HCUR and LCUR jacks, each through 1 MΩ to an ADC pin biased by 200 kΩ to 3V3 and 249 kΩ to ground, with 100 nF. R105 / R106 on the jack side tie each POT jack to its CUR jack, so two senses cover all four jacks.
  - Full scale is ±16.5 V. The pin stays at 0.65–2.65 V over the TVS clamp range (±10 V).
  - The bias pushes 1.6 µA into a jack at 0 V. On LCUR that is 0.16 V DC at the TIA output on the 100 k range, against about ±11 V of swing.
  - The filter time constant is 10 ms; settling from a clamped jack to half the close threshold takes 30 ms.
  - The pins are GPIO 28 / 29 (ADC2 / ADC3), so the optional UART header goes away on Rev G.
- **USB:** 0.46 A (Rev F at attach) + 16.4 mA = 0.476 A typical, 0.482 A worst, under 0.5 A.

**Firmware** (`../../firmware-rev-e/src/jackguard.{h,c}`, built with `LCR_REV_G=1`):
- **Close:** only with the rails up and both jacks below 1.0 V for 6 polls (30 ms). The 1.0 V threshold is below the second stage's 3.3 V standoff, so closing never makes it conduct.
- **Settle:** captures wait out the switch's 2 ms tON (5 ms).
- **Trip:** while closed, open on a rail fault or a jack above 3.0 V. The source is at most 1.7 V peak, and the filter passes 0.56 V of the lowest 46 Hz tone.
- **Re-arm:** after 1 s of quiet jacks.
- **Commands:** every analog command (RANGE, TONE, WAVE, RAW, CAPTURE, REFCAPTURE) polls the guard first and replies `ERR jacks_<state>` if the jacks are not connected. `JACKS` reports the state and both readings.
- **VBUS loss:** the switches open in hardware, and the guard starts over.

Verification:
- The host test (`test/test_host.c`) covers conversion, the close gate, settling, trip, re-arm and rail faults.
- Four mutants are killed: no trip, no stable polls, no rail check, re-arm timed from the wrong instant.
- The Rev G image builds with `-Werror`; the hot loop is unchanged (209 cycles per frame against 640).
- The Rev E/F images do not include the module. Built at one path, HEAD and this tree give byte-identical UF2s.
- `drive_budget.py` checks the thresholds and divider constants against `jackguard.h`.

## Schematic delta for Rev G (input to the CAD step)

Against Rev F (`cad/design.json`). The BNCs are J3 / J7 / J8 / J9 = HCUR / HPOT / LPOT / LCUR. New nets: JK_HCUR, JK_HPOT, JK_LPOT, JK_LCUR (the BNC centre pins), ISO_x (switch to series R), SNS_HC / SNS_LC and ISO_DRV.

| Part | Value / MPN | LCSC | Connection |
|---|---|---|---|
| D (×4) | H4V5HD3B | C20615803 | JK_x – GND, at the BNC pin |
| U (×4) | TLP172AM | C2152276 | output: JK_x – ISO_x; LEDs in two series strings (below) |
| R (×2) | 10 Ω CRCW0805-HP | C844598 | ISO_HCUR – DUT_HI, ISO_LCUR – DUT_LO |
| R (×2) | 100 Ω CRCW0603-HP | C844725 | ISO_HPOT – HPOT, ISO_LPOT – LPOT |
| D (×3) | H3V3LD5B | C20615817 | DUT_HI, HPOT, LPOT – GND |
| C (×2) | 1 nF C0G 0603 | C106246 | HPOT, LPOT – GND |
| D | BAV99 | C2500 | pin 3 DUT_LO; pins 1, 2 GND |
| R105 / R106 (moved) | 1 kΩ | (Rev F) | JK_HCUR – JK_HPOT, JK_LCUR – JK_LPOT |
| K4 COM2 / R107 (moved) | (Rev F) | (Rev F) | COM2 to JK_HCUR; R107 REF_A – JK_LCUR |
| R (×2) / R (×2) / R (×2) / C (×2) | 1 MΩ / 200 kΩ / 249 kΩ / 100 nF | | JK_HCUR (JK_LCUR) – SNS_HC (SNS_LC); SNS – 3V3; SNS – GND; SNS – GND; SNS_HC → GPIO 28, SNS_LC → GPIO 29 |
| R (×2) | 300 Ω | | 5V – LED string 1 (U1, U2), 5V – LED string 2 (U3, U4), both strings to ISO_DRV |
| Q | AO3400A | (Rev F line) | drain ISO_DRV, source GND, gate GPIO 12 through 100 Ω, 100 kΩ gate – GND |
| UART header | removed | | GPIO 28 / 29 are the senses |

C78 (100 pF, DUT_LO) and R94 stay where they are. The setup fee is 4 extended lines, about $12 per order (`PARTS.md`).

## Open items

- **Schematic and layout wait for Rev F bring-up.** Bring-up measures the numbers that size this network:
  - the ESD knee (charged-dut README §10);
  - the 3V3A rise;
  - the TLP172AM's COFF against voltage, which ends the unpowered margin and has no datasheet curve;
  - the jack and second-stage TVS C(V), estimated here from another part's curve.

  A hand-routed layout before those measurements would likely be redone. The table above is the input to the CAD step; layout is hand-routed, never autorouted.
- **Human ESD on the centre pins** (IEC 61000-4-2): add it to the screen as a test case.
- **The 1 J stretch.** It needs SMC-class jack TVSs, 2512 pulse resistors and a higher-current switch. It costs capacitance on LCUR, which item 1 above shows matters. Not pursued.
- **A trip during a capture.** The guard runs between commands, not inside the capture's hot loop. A charged DUT touched mid-capture is handled by the hardware network alone, which is what the surge screen judges.

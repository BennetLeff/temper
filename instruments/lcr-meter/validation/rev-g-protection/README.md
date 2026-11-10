# Rev G jack protection study (started 2026-11-08)

Rev F has no protection on its four BNC jacks (audit AFE-01 to AFE-04). `../charged-dut/` measured the gap: 7 V with Kelvin clips when powered and 0.5–1 V when unpowered, against 1 J for a Keysight E4980A.

This study designs the Rev G protection while Rev F is built. The values it once left to Rev F bring-up (the real ESD knee, the 3V3A rise, the switch's off capacitance and the clamps' C(V)) are now covered by a sensitivity run (phase 7): the network meets its targets across them, so bring-up confirms these values rather than sets them.

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
| HCUR and LCUR jacks | residual-voltage sense, 1.5 MΩ to an ADC pin biased at mid-scale | ×2 |
| K4 pole 1 (unused on Rev F) | shorts the HCUR and HPOT jacks during the reference check | — |

What it achieves, each from the section below:

| Requirement | Result |
|---|---|
| Surge, 1 µF at 30 V, every pattern and meter state | class A; class A up to 50 V (unpowered) and 200 V (powered). The screen judges the downstream parts, not the jack TVS's own pulse rating: that rating limits the envelope to about 1 µF at 50 V, 10 µF at 30 V (G100 audit PROT-02, `../datasheet-audit-rev-g100/protection.md`) |
| Part ratings at 30 V | all covered; thinnest are the jack TVS (25.8 A vs 40 A) and the LCUR switch (0.61 A vs 1.5 A) |
| Accuracy (LCR-6100 verdicts over the map) | 144 / 22 / 43, the same as Rev F, with drift; 144 / 23 / 42 with amplitude dependence too |
| Stability (360-case full-chain matrix) | no margin lost: drive 47.76° (Rev F 47.76°), TIA 69.92° (57.28°), HIGH 57.90° (57.57°), LOW 57.17° (56.61°) |
| Signal | 1.06 dB less current into a short on the 100 Ω range; added noise ≤ 0.33 % of the codec floor |
| USB | 0.476 A typical with the switch drive, under 0.5 A |
| ESD, IEC 61000-4-2 contact on each centre pin | see phase 7 (the tables there) |
| Sensitivity: switch COFF ×2, TVS C ×2, stronger ESD cell, RON max | 30 V target still met in every case; accuracy within one cell of the above |
| 1 J stretch | not met (the jack TVS would need about 1 kA); see "Part stress". Not pursued (decision, "Open items") |

The two layout moves come from phase 3, and the K4 bypass from phase 7:
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
| 6 | Isolation switch drive, residual-voltage sense, power budget, firmware sequencing | done |
| 7 | Sensitivity to the bring-up unknowns, IEC 61000-4-2 ESD, the HPOT reference residual, the in-capture trip | done (2026-11-09) |
| — | Schematic and layout | started 2026-11-09 by owner decision, ahead of Rev F bring-up; laid out and hand-routed (`../../docs/rev-g-plan.md`) |

```sh
python3 validation/rev-g-protection/protection_screen.py --jobs 10   # ~20 min for all 12 candidates -> protection-screen.json
python3 validation/rev-g-protection/protection_screen.py --esd --jobs 10   # ~10 min, IEC 61000-4-2 sweep -> protection-screen.json "esd"
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
| `jackside_coff2x` | 30 V | 200 V | 30 V | met | h_to_gnd unpowered/100R: u6a input 14.5 mA > 10; u6a input 14.6 mA > 10 |
| `jackside_tvs_c2x` | 50 V | 200 V | 50 V | met | h_to_gnd unpowered/100R: u6a input 11.4 mA > 10; u6a input 11.9 mA > 10 |
| `jackside_esd_alt` | 100 V | 200 V | 100 V | met | kelvin unpowered/100k: u7a input 10.1 mA > 10 |
| `jackside_pot470p` | 50 V | 200 V | 50 V | met | h_to_gnd unpowered/100R: u6a input 10.9 mA > 10; u6a output ESD 10.6 mA > 10 |
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
| `iso_hcur` | 10.3 V off-state | 135 V off-state |
| `iso_hpot` | 10.3 V off-state | 135 V off-state |
| `iso_lpot` | 10.3 V off-state | 135 V off-state |
| `iso_lcur` | 10.3 V off-state | 135 V off-state |
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
| `iso_hcur` | 8.71 V off-state | TLP172AM VOFF 60 V | ×6.9 |
| `iso_hpot` | 8.6 V off-state | TLP172AM VOFF 60 V | ×7 |
| `iso_lpot` | 8.62 V off-state | TLP172AM VOFF 60 V | ×7 |
| `iso_lcur` | 8.71 V off-state | TLP172AM VOFF 60 V | ×6.9 |
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
| `parts_jackside` | drift | 144 / 22 / 43 | 0.078 % (×3.91 of the cell) | 100 range, 85k Hz, 31.6 Ω, phase |
| `parts_jackside` | level | 144 / 23 / 42 | 0.078 % (×2.19 of the cell) | 100 range, 85k Hz, 100 Ω, phase |
| `jackside_no_bypass` | linear | 144 / 22 / 43 | 0.066 % (×1.08 of the cell) | 100 range, 200 Hz, 100 mΩ, phase |
| `jackside_no_bypass` | drift | 144 / 22 / 43 | 0.17 % (×5.14 of the cell) | 5k range, 85k Hz, 3.16 kΩ, phase |
| `jackside_no_bypass` | level | 143 / 23 / 43 | 0.18 % (×2.57 of the cell) | 5k range, 85k Hz, 10 kΩ, phase |
| `jackside_ron_max` | linear | 144 / 22 / 43 | 0.072 % (×1.09 of the cell) | 100 range, 200 Hz, 100 mΩ, phase |
| `jackside_ron_max` | drift | 144 / 22 / 43 | 0.12 % (×5.57 of the cell) | 100 range, 85k Hz, 31.6 Ω, phase |
| `jackside_ron_max` | level | 143 / 23 / 43 | 0.12 % (×2.87 of the cell) | 100 range, 85k Hz, 100 Ω, phase |
| `jackside_tvs_c2x` | linear | 143 / 23 / 43 | 0.066 % (×1.08 of the cell) | 100 range, 200 Hz, 100 mΩ, phase |
| `jackside_tvs_c2x` | drift | 143 / 23 / 43 | 0.095 % (×5.23 of the cell) | 100 range, 50k Hz, 31.6 Ω, phase |
| `jackside_tvs_c2x` | level | 144 / 23 / 42 | 0.095 % (×2.58 of the cell) | 100 range, 50k Hz, 100 Ω, phase |
| `jackside_pot470p` | linear | 144 / 22 / 43 | 0.066 % (×1.08 of the cell) | 100 range, 200 Hz, 100 mΩ, phase |
| `jackside_pot470p` | drift | 144 / 22 / 43 | 0.08 % (×3.96 of the cell) | 100 range, 85k Hz, 31.6 Ω, phase |
| `jackside_pot470p` | level | 144 / 23 / 42 | 0.079 % (×2.21 of the cell) | 100 range, 85k Hz, 100 Ω, phase |
<!-- /generated -->

<!-- generated:normal_grid -->
`parts`, level mode: worst added corner error over the usable cells (max of |Z| and phase), %; — = no usable cell

| Range | 50 | 100 | 200 | 500 | 1k | 2k | 5k | 10k | 20k | 50k | 85k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 0.4 | 0.38 | 0.42 | 0.26 | 0.35 | 0.27 | 0.37 | 0.34 | 0.07 | 0.1 | 0.16 |
| 5k | 0.0039 | 0.0027 | 0.0017 | 0.0019 | 0.002 | 0.0032 | 0.011 | 0.025 | 0.051 | 0.12 | 0.17 |
| 100k | 0 | 0 | 0 | 0 | 0.0015 | 0.0015 | 0.0053 | 0.019 | 0.044 | 0.11 | 0.15 |

`jackside_no_bypass`, level mode: worst added corner error over the usable cells (max of |Z| and phase), %; — = no usable cell

| Range | 50 | 100 | 200 | 500 | 1k | 2k | 5k | 10k | 20k | 50k | 85k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 0.059 | 0.06 | 0.066 | 0.059 | 0.059 | 0.061 | 0.056 | 0.065 | 0.021 | 0.058 | 0.096 |
| 5k | 0.0051 | 0.0033 | 0.0026 | 0.0017 | 0.0022 | 0.0034 | 0.012 | 0.025 | 0.053 | 0.12 | 0.18 |
| 100k | 0.0032 | 0.0016 | 0.0011 | 0.00091 | 0.0018 | 0.0016 | 0.0053 | 0.02 | 0.046 | 0.12 | 0.16 |

`parts_jackside`, level mode: worst added corner error over the usable cells (max of |Z| and phase), %; — = no usable cell

| Range | 50 | 100 | 200 | 500 | 1k | 2k | 5k | 10k | 20k | 50k | 85k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 0.059 | 0.06 | 0.066 | 0.059 | 0.059 | 0.061 | 0.056 | 0.061 | 0.032 | 0.074 | 0.078 |
| 5k | 0.0051 | 0.0033 | 0.0026 | 0.0019 | 0.0016 | 0.0018 | 0.002 | 0.0019 | 0.0051 | 0.0088 | 0.014 |
| 100k | 0.0032 | 0.0016 | 0.001 | 0.00094 | 0.0013 | 0.0016 | 0.0051 | 0.0047 | 0.014 | 0.024 | 0.024 |
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
| `jackside_no_bypass` | 10.1 → 8.9 / 0.335 → 0.334 / 0.017 → 0.017 | 1.06 dB | 0.33 % / 0.078 % | no summing-node clamp |
| `jackside_ron_max` | 10.1 → 8.81 / 0.335 → 0.334 / 0.017 → 0.017 | 1.15 dB | 0.34 % / 0.082 % | no summing-node clamp |
| `jackside_tvs_c2x` | 10.1 → 8.9 / 0.335 → 0.334 / 0.017 → 0.017 | 1.06 dB | 0.33 % / 0.078 % | no summing-node clamp |
| `jackside_pot470p` | 10.1 → 8.9 / 0.335 → 0.334 / 0.017 → 0.017 | 1.06 dB | 0.33 % / 0.078 % | no summing-node clamp |
<!-- /generated -->

What it shows:
1. **Capacitance on HPOT loads the reference check.**
   - The parametric 2 nF clamps lose 58 of the map's 144 ✓ cells to drift. Zeroing the TVS-capacitance TC restores 140.
   - With 2 nF on one jack at a time, the HPOT jack costs 59 cells; HCUR, LPOT and LCUR cost 5–6 each.
   - **Mechanism:** the per-session reference check runs with the leads unplugged, so HPOT is fed only through R105's 1 kΩ. Any capacitance on the HPOT side shifts that reading's phase. Calibration takes out the shift, but not its drift, and every measurement is corrected by the check. LPOT sits near 0 V, so its capacitance barely matters.
   - The H4V5HD3B's 100 pF (against an SMAJ's 1.15 nF) keeps this small. Without phase 7's K4 bypass (`jackside_no_bypass`), what remains is the 1.1 nF of mostly C0G on HPOT: about 0.1–0.2 % at 50–85 kHz in the corner (the grid above).
   - Phase 7 tested the two options. K4's free pole shorting the HCUR and HPOT jacks during the check (`revE_front.measure(bypass=True)`) takes the HPOT side's capacitance out of the check: the 5 k and 100 k ranges' worst 85 kHz cells drop from 0.18 / 0.16 % to 0.014 / 0.024 % (grid above, `jackside_no_bypass` against `parts_jackside`). It is adopted, at no part cost. A 470 pF POT capacitor instead of 1 nF makes it slightly worse (0.2 %), so the 1 nF stays.
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
- **Jack side:** R105 / R106 and K4 + R107 sit on the jack nodes. With `ref_bypass` (phase 7), K4's pole 1 joins jhc to jhp when set, and leaves its open-contact C there otherwise (`k4_bypass`).
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
- **Drive:** two strings of two TLP172AM LEDs from VRLY (the switched 5 V through R101, 1 Ω, which the relay coils share), 300 Ω each, sunk by one AO3400A on GPIO 15 (U1 pin 18, next to K4's GPIO 14; GPIO 12 has no escape under USB_SENSE; the Q6 pattern, 100 kΩ gate pull-down). The switches are open from power-up until the firmware closes them, and open within 0.5 ms of losing VBUS. `part-selection/PARTS.md` suggested about 400 Ω; that gives 3.8 mA at the lowest rail, below the 5 mA RON is specified at, so it is 300 Ω here.
  - 5.03 mA per LED at 4.32 V and VF max (≥ 5 mA recommended, IFT ≤ 3 mA). Both strings drop 10 mV on R101, which is most of the margin; the minimum assumes the Rev F rail floor (4.32 V at VBUS 4.40 V);
  - 4.59 mA during the RESET pulse (112 mA of coil current on R101, rail at 4.30 V), above IFT, so the switches stay closed through a range change; the coils still get 4.17 V against their 3.75 V must-operate;
  - 10.9 mA at 5.5 V and VF min (≤ 25 mA);
  - 16.3 mA total typical.
- **Sense:** HCUR and LCUR jacks, each through 1.5 MΩ to an ADC pin biased by 240 kΩ to 3V3 and 240 kΩ to ground, with 100 nF. These are lines already on Rev F's BOM (R111, R83, C116); the study's 1 MΩ / 200 kΩ / 249 kΩ needed three new ones. `drive_budget.py` reads them from `cad/design.json`. R105 / R106 on the jack side tie each POT jack to its CUR jack, so two senses cover all four jacks.
  - Full scale is −20.6 to +23.9 V, about 11 mV per code. The pin stays at 0.79–2.27 V over the TVS clamp range (±10 V).
  - The bias pushes 1.0 µA into a jack at 0 V. On LCUR that is 0.10 V DC at the TIA output on the 100 k range, against about ±11 V of swing.
  - The filter time constant is 11.1 ms; settling from a clamped jack to half the close threshold takes 33 ms, inside the firmware's 35 ms stable window (checked).
  - The pins are GPIO 28 / 29 (ADC2 / ADC3). Rev G drops the optional UART header (J6): GPIO 0 / 1 have no escape from U1 on the Rev G board (`../../docs/rev-g-plan.md`).
- **USB:** 0.46 A (Rev F at attach) + 16.3 mA = 0.476 A typical, 0.482 A worst, under 0.5 A.

**Firmware** (`../../firmware-rev-e/src/jackguard.{h,c}`, built with `LCR_REV_G=1`):
- **Close:** only with the rails up and both jacks below 1.0 V for 7 polls (35 ms). The 1.0 V threshold is below the second stage's 3.3 V standoff, so closing never makes it conduct.
- **Settle:** captures wait out the switch's 2 ms tON (5 ms).
- **Trip:** while closed, open on a rail fault or a jack above 3.0 V. The source is at most 1.7 V peak, and the filter passes 0.51 V of the lowest 46 Hz tone.
- **Re-arm:** after 1 s of quiet jacks.
- **During a capture** (phase 7): the guard is not polled inside a capture, which can last 60 s, so the capture loop takes one conversion per jack every 5 ms. Above 3.0 V it opens the switches, ends the capture with `ERR jacks_tripped` and leaves the guard tripped (it re-arms as above). That covers a source connected mid-capture, which would otherwise drive the 10 Ω CUR resistor and the second-stage clamp until the capture ended.
- **Commands:** every analog command (RANGE, TONE, WAVE, RAW, CAPTURE, REFCAPTURE) polls the guard first and replies `ERR jacks_<state>` if the jacks are not connected. `JACKS` reports the state and both readings.
- **VBUS loss:** the switches open in hardware, and the guard starts over.

Verification:
- The host test (`test/test_host.c`) covers conversion, the close gate, settling, trip, re-arm, rail faults and the in-capture trip.
- Seven mutants are killed: no trip, no stable polls, no rail check, re-arm timed from the wrong instant; in the in-capture check, `>=` for `>`, one polarity dropped, and the trip not timed from its own instant.
- The Rev G image builds with `-Werror`. The per-frame hot loop is unchanged (209 cycles against 640); the in-capture check runs between ring drains, about 4 µs per 5 ms against a ring that holds 22 ms.
- The Rev E/F images do not include the module. Built at one path, HEAD and this tree give byte-identical UF2s.
- `drive_budget.py` checks the thresholds, the divider constants and the stable window against `jackguard.h`, and `../firmware-pins/` traces the drive and both dividers from the firmware pins through `cad/design.json`.

## Phase 7: the open items, resolved in the box (2026-11-09)

### Sensitivity to what bring-up was to measure

Variants of `parts_jackside` (`protection_screen.py` `SENSITIVITY`; surge rows in the phase 1 table, accuracy rows in the phase 3 table):

| Unknown | Variant | Surge, lowest class-A voltage (target 30 V) | Accuracy, LCR-6100 ✓ / ~ / ✗ (drift; level) |
|---|---|---|---|
| (none) | `parts_jackside` | 50 V | 144 / 22 / 43; 144 / 23 / 42 |
| Switch COFF, no C(V) curve | `jackside_coff2x`: 40 pF, 2 × typical, at every voltage | 30 V | (switch closed in use) |
| TVS capacitance, no max and no C(V) | `jackside_tvs_c2x`: both TVSs × 2 | 50 V | 143 / 23 / 43; 144 / 23 / 42 |
| The real ESD knee | `jackside_esd_alt`: the stronger ESD cell (IS 1e-12) | 100 V | (no effect) |
| Switch RON spread | `jackside_ron_max`: 2 Ω | (more R only helps) | 144 / 22 / 43; 143 / 23 / 43 |
| TVS C(V) shape | linear mode (flat C) against level mode (the borrowed curve) | — | 144 / 22 / 43 against 144 / 23 / 42 |

- The target holds across all of them. The tightest is COFF: at 40 pF the unpowered margin is the 30 V target exactly. The datasheet's 20 pF is at 0 V, which is the top of a falling C(V) (the AQW212EH's published curve falls from 80 to 30 pF between 0 and 10 V, and the open switch sees at most the jack clamp's ~10 V). So 40 pF at every voltage is pessimistic.
- The 3V3A rise never ends class A in any variant. The limits are the op-amp ESD cells and, above 200 V, the working voltage of R105 / R106.
- So the values are fixed now. Bring-up confirms them with three checks, listed under "Open items"; it no longer sizes them.

### ESD on the centre pins (IEC 61000-4-2)

`protection_screen.py --esd`: the gun (`charged_dut_spice.GUN`) in contact discharge on each centre pin. No leads are plugged in. Every meter state and both polarities are run, from 2 to 30 kV, judged as above. Class B means only the OPA2810's 10 mA ESD-cell current is exceeded, by a pulse inside the HBM pulse the cell is rated for (charged-DUT `judge()`).

<!-- generated:esd -->
Gun into the standard's 2 Ω target, per kV: first peak 3.78 A (3.75 ± 15 %), rise 0.77 ns (0.8 ± 25 %), 1.82 A at 30 ns (2 ± 30 %), 0.93 A at 60 ns (1 ± 30 %): all inside the IEC 61000-4-2 table.

| Candidate | Class A, powered | Class A, unpowered | A or B (nothing past the HBM pulse), any state | Where class A ends first |
|---|---|---|---|---|
| `links` | below 2 kV | below 2 kV | below 2 kV | hcur powered at 2 kV: R104 209 V > 50 working; R105 1.52e+03 V > 50 working |
| `parts_jackside` | 30 kV (the sweep top) | below 2 kV | 30 kV (the sweep top) | hcur unpowered at 2 kV: u6a input 10.4 mA > 10; u6a output ESD 10.2 mA > 10 |
| `jackside_coff2x` | 30 kV (the sweep top) | below 2 kV | 30 kV (the sweep top) | hcur unpowered at 2 kV: u6a input 14.5 mA > 10; u6a input 14.6 mA > 10 |
| `jackside_esd_alt` | 30 kV (the sweep top) | below 2 kV | 30 kV (the sweep top) | hcur unpowered at 2 kV: u6a input 11.2 mA > 10; u6a input 11.3 mA > 10 |
<!-- /generated -->

`parts_jackside` part stress at the target and at the sweep top:

<!-- generated:esd_parts -->
| Part | At 8 kV | At 30 kV | Rating |
|---|---|---|---|
| `tvs1_hcur` | 30.5 A peak | 114 A peak | H4V5HD3B ±30 kV contact |
| `tvs2_hcur` | 0.486 A peak | 0.945 A peak | H3V3LD5B ±20 kV contact |
| `tvs1_hpot` | 30.4 A peak | 114 A peak | H4V5HD3B ±30 kV contact |
| `tvs2_hpot` | 0.0134 A peak | 0.0331 A peak | H3V3LD5B ±20 kV contact |
| `tvs1_lpot` | 30.4 A peak | 114 A peak | H4V5HD3B ±30 kV contact |
| `tvs2_lpot` | 0.0134 A peak | 0.0331 A peak | H3V3LD5B ±20 kV contact |
| `tvs1_lcur` | 30.5 A peak | 114 A peak | H4V5HD3B ±30 kV contact |
| `sch2_lcur` | 0.588 A peak | 1.13 A peak | BAV99 IFSM 4 A (1 µs) |
| `r_hcur` | 2.39 W peak | 8.99 W peak | CRCW0805-HP ~450 W at 1 µs; a ns pulse is allowed more |
| `r_hpot` | 0.797 W peak | 2.6 W peak | CRCW0603-HP ~250 W at 1 µs; a ns pulse is allowed more |
| `r_lpot` | 0.797 W peak | 2.6 W peak | CRCW0603-HP ~250 W at 1 µs; a ns pulse is allowed more |
| `r_lcur` | 4.25 W peak | 14.6 W peak | CRCW0805-HP ~450 W at 1 µs; a ns pulse is allowed more |
| `iso_hcur` | 7.65 V off-state | 13.9 V off-state | TLP172AM VOFF 60 V |
| `iso_hpot` | 8.54 V off-state | 14.9 V off-state | TLP172AM VOFF 60 V |
| `iso_lpot` | 8.54 V off-state | 14.9 V off-state | TLP172AM VOFF 60 V |
| `iso_lcur` | 8.34 V off-state | 15.6 V off-state | TLP172AM VOFF 60 V |
<!-- /generated -->

- **Bare Rev F jacks fail at 2 kV on every jack.** R104 / R105 go past their working voltage, and U6B / U7B take amps into their inputs.
- **With `parts_jackside`, nothing goes past the HBM pulse up to 30 kV contact,** on every jack, state and polarity. Class A holds to 30 kV whenever the meter is powered.
- **Unpowered, HCUR is class B from 2 kV.** The gun's edge couples through the open switch's COFF into U6A's input cell, at about 10 mA for nanoseconds.
- **Against the standard.** IEC 61326-1 (laboratory equipment) asks 4 kV contact at criterion B, and 8 kV is the standard's top contact level.
- **The jack TVS takes the whole gun** (114 A at 30 kV). It is rated ±30 kV contact, the second stage ±20 kV (datasheets, `part-selection/parts.json` URLs; H4V5HD3B SHA256 as recorded there).

### The HPOT reference residual

K4's pole 1, unused on Rev F, shorts the HCUR and HPOT jacks while K4 is set (`ref_bypass`). This is adopted in `parts_jackside` (phase 3, item 1):
- **Accuracy:** the 5 k / 100 k ranges' worst 85 kHz cells drop from 0.18 / 0.16 % to 0.014 / 0.024 %, and the level-mode verdicts improve from 143 / 23 / 43 to 144 / 23 / 42.
- **Stability:** the matrix adds the pole's contact R and L when K4 is set, and its open-contact C otherwise (`loop_matrix.rs` `k4_bypass`). The headline margins are unchanged, and the K4-closed drive margin rises from 53.97° to 54.18°.
- **The alternative:** a 470 pF POT capacitor makes the residual slightly worse, so the 1 nF stays.

### Firmware and pins

- **In-capture trip:** see phase 6, "During a capture".
- **UART:** the UART header moves to GPIO 0 / 1, not removed. Superseded at layout (2026-11-09): GPIO 0 / 1 have no escape on the Rev G board, so J6 is dropped (`../../docs/rev-g-plan.md`).
- **Switch drive:** it moves from GPIO 12 to GPIO 15 (U1 pin 18). `../../firmware-rev-e/README.md` records that GPIO 12 has no escape on this board, because USB_SENSE runs over U1 pin 15. GPIO 15 sits next to K4's GPIO 14, whose driver is already near the jacks.
- **Images:** Rev E / F are byte-identical to HEAD, built at one path.

## Schematic delta for Rev G (input to the CAD step)

Against Rev F (`cad/design.json`). The BNCs are J3 / J7 / J8 / J9 = HCUR / HPOT / LPOT / LCUR. New nets: JK_HCUR, JK_HPOT, JK_LPOT, JK_LCUR (the BNC centre pins), ISO_x (switch to series R), JACK_HC / JACK_LC (the senses, named after the firmware pins) and ISO_SINK (the LED strings' common cathode end); GPIO 15's net is ISO_DRIVE. This was the CAD input; the board as built, with reference designators, is in `../../docs/rev-g-plan.md`. Two rows changed at layout and are shown as built: the sense divider values and J6.

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
| R (×2) / R (×2) / R (×2) / C (×2) | 1.5 MΩ / 240 kΩ / 240 kΩ / 100 nF (Rev F lines R111 / R83 / C116) | C4172 / C4197 / (Rev F) | JK_HCUR (JK_LCUR) – JACK_HC (JACK_LC); JACK – 3V3; JACK – GND; JACK – GND; JACK_HC → GPIO 28, JACK_LC → GPIO 29 |
| R (×2) | 300 Ω | C23025 | VRLY – LED string 1 (HPOT, HCUR switches), VRLY – LED string 2 (LPOT, LCUR switches), both strings to ISO_SINK |
| Q | AO3400A | (Rev F line) | drain ISO_SINK, source GND, gate GPIO 15 (U1 pin 18, net ISO_DRIVE) through 100 Ω, 100 kΩ gate – GND |
| K4 pole 1 (added use) | (Rev F) | (Rev F) | COM1 (pin 3) to JK_HCUR, NO1 (pin 4) to JK_HPOT: shorts them while K4 is set |
| J6 UART header (removed) | | | GPIO 28 / 29 are the senses; GPIO 0 / 1 have no escape from U1 on the Rev G board |

C78 (100 pF, DUT_LO) and R94 stay where they are. The setup fee is 4 extended lines, about $12 per order (`PARTS.md`).

## Open items

Resolved 2026-11-09 (phase 7): human ESD on the centre pins, a trip during a capture, the HPOT reference residual, the UART header, and the sensitivity of every value bring-up was to measure.

- **Schematic and layout started 2026-11-09, ahead of Rev F bring-up (owner decision).** This overrides the 2026-11-08 sequencing. Its reason still stands: Rev G sits on Rev F's most sensitive nodes, and bring-up can move other parts of the board, so a bring-up finding on those nodes is applied to Rev G before it is ordered. Layout is hand-routed, never autorouted, and gets an independent review before it is called orderable (`../../docs/rev-g-plan.md`).
- **Bring-up confirms three numbers; it does not size them.** Each pass limit is the value phase 7 shows still meets the target:
  - the TLP172AM's COFF at 0 V, 40 pF or less;
  - the H4V5HD3B's C at 0 V, 200 pF or less, and the H3V3LD5B's, 25 pF or less;
  - the unpowered ESD knee, against `../charged-dut/bench-esd-knee.json`.
- **The 1 J stretch: not pursued (decision).** It needs SMC-class jack TVSs (about 1 kA), 2512 pulse resistors and a higher-current switch. Their nanofarads on LCUR and HPOT cost the accuracy that phases 3 and 7 protect. The bench rule (discharge below 0.5 V) covers that range.
- **USB: closed.** 0.476 A typical and 0.482 A worst, under the 0.5 A the descriptor declares.

# Fixture and lead envelope (2026-10-20)

**Finding.** On the 100 Ω range, the range Temper's coil and capacitor measurements use, the Rev C TIA loses phase margin as fixture capacitance grows on the DUT terminals. The 45° criterion fails above roughly 300 pF per terminal. It also fails with 2 m of RG-174-class coax (41.0°). The fixedgrid evidence stopped at 100 pF (49.7°), so this limit was outside the tested envelope. The 5 kΩ and 100 kΩ ranges, the source driver and both sense followers are unaffected.

| 100 Ω range, TIA, DUT open | 0 pF | 100 pF | 220 pF | 470 pF | 1 nF | 0.5 m coax | 1 m coax | 2 m coax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Rev C | 57.8° | 49.7° | 46.4° | **39.0°** | **29.9°** | 50.6° | 48.5° | **41.0°** |
| Candidate: 22 Ω isolation | 57.8° | 62.9° | 72.2° | 81.9° | 92.2° | — | — | 55.4° (worst lead case) |

**Cause.** LO is the TIA summing node. On the 100 Ω range RF = 100 Ω is not swamped by the 100 pF C104 at the 20–60 MHz crossover (100 pF is 80 Ω at 20 MHz). Capacitance from the summing node to ground therefore forms a pole with RF inside the loop. On the 5 kΩ and 100 kΩ ranges C104 dominates RF at crossover, so the same capacitance only forms a real capacitive divider. That lowers the crossover and *raises* the margin.

**Candidate fix (Rev D).** Put a resistor R_iso between the J3 LO pin and the summing node (U7A −IN, RF, C104). Leave the LOW sense follower on the connector side of R_iso, so channel A remains the DUT voltage.
- 22 Ω: the 42-case grid and 84 paired corners rerun with it give a minimum of 57.78° / 57.75°. The fixture, stray and lead sweeps give a minimum of 55.3° over every loop, and |1+T| ≥ 0.66 everywhere. Without R_iso the minimum is 0.47.
- 10 Ω is weaker (56.3° at 100 pF; margin dips before it recovers). 47 Ω is similar to 22 Ω, but more of the drive voltage is dropped outside the DUT.

**Measurement consequences of R_iso**, to be handled before adopting it:
- Channel B becomes LO − TIA = I·(R_iso + RF‖CF). The host's nominal feedback model must add R_iso on every range. The per-frequency bilinear calibration absorbs its tolerance.
- LO is no longer a virtual ground: it sits at I·R_iso. Cable capacitance at LO now diverts a fraction ≈ R_iso·ωC of the DUT current. That is 0.17% for 22 Ω, 200 pF and 60 kHz. It is a fixed linear error that the three-standard calibration removes, but it changes if the leads are moved or swapped after calibration.
- Available drive across the DUT falls by R_iso/(RG + R_iso + Z). That costs about 15% on the 100 Ω range for a 15 Ω DUT, which the virtual-instrument noise study should include.

**Without a board change**, the operating limit on the 100 Ω range is at most about 220 pF on each DUT terminal (46.4°). That means no more than about 1 m of RG-174 or a short twisted pair (1 m twisted pair: 54.5°), and no relay multiplexer whose capacitance pushes past that.

## With extracted board parasitics (`final_fixedextracted`)

`../layout-parasitics/extracted.json` (high corner) adds board copper the earlier cases left out:
- 5.6 pF on the summing node and 5.2 pF on HI;
- 0.16 pF HI–LO, 0.40 pF LO–TIA out and 0.17 pF LO–LOW buffer;
- 10.5 pF from TIA out to ground;
- extracted branch inductances: C104 4.87 nH (10 nH stress retained), RF 21.7 / 50.5 / 33.1 nH by range.

For the R_iso variant the summing side keeps 1.28 pF and the J3 side 3.8 pF, from the proposed placement in `../layout-parasitics/geometry_riso.json`. Cable capacitance is added on top.

| Variant (TIA, worst DUT and C104 lead) | 0 pF cable | 100 pF | 220 pF | 470 pF | 1 nF |
|---|---:|---:|---:|---:|---:|
| Rev C, 100 Ω | 51.3° | 46.9° | 46.5° | **39.9°** | **29.5°** |
| 22 Ω R_iso, 100 Ω | 51.7° | 60.7° | 72.1° | 83.5° | 94.2° |
| 22 Ω R_iso, 5 kΩ / 100 kΩ | 52.5° / 52.3° | — | — | — | 130.8° / 131.9° |
| **Rev D as built**, 100 Ω | **51.3°** | 60.9° | 72.2° | 83.5° | 94.2° |
| Rev D as built, 5 kΩ / 100 kΩ | 52.5° / 52.3° | — | — | — | 130.8° / 131.9° |

- **The as-built Rev D board** (`rev_d_board` in `extracted.json`, board `eb2b4cf8…`) reproduces the proposed placement: every capacitance is within 1 % of `geometry_riso.json`. Its rows use the high corner, worst over ranges: J3 side 5.67 pF, summing side 1.27 pF, 0.12 pF across R94, TIA out 10.53 pF. The proposed rows above used the J3-side nominal (3.8 pF). Minimum over all 64 as-built cases: **51.3°**, |1+T| ≥ 0.573 (Rev C 0.498).
- **The board's own copper costs about 6° on every range at zero cable.** Almost all of it comes from the 10.5 pF on the TIA output trace: dropping that element alone restores 56.4°, while every other element moves the margin by under 1° (`extracted-attribution.md`).
- **The minimum with R_iso and extracted parasitics is 51.7°.** That passes the 45° criterion but is below the 60° preferred nominal. It sits at zero cable, the condition R_iso does not help.
- **Shortening the TIA-output copper is the lever for recovering margin there.** The TIA output runs to RF, the jumpers, C104 and the FDA input resistor.

## Method and limits

- `loop_matrix.rs` modes `final_fixedfixture` (lumped stray 0–1000 pF on both DUT terminals), `final_fixedleads` (lossless LC-ladder leads, 20 sections/m: coax 50 Ω, 101 pF/m, 252.5 nH/m, shield grounded at the board; unshielded twisted pair 0.7 µH/m loop, 50 pF/m between wires, 10 pF/m to ground), `final_fixedriso` and `final_fixedrisoleads` (R_iso option `_risolo<Ω>`), and `final_fixedrisogrid` / `final_fixedrisocorners` (the existing fixedgrid and fixedcorners cases with 22 Ω). Every case keeps the 5 nH C104 lead and the 100 nH RF lead. The heaviest 100 Ω-range cases also cut the driver, HIGH and LOW follower loops.
- Same strict true-DC operating point, bilateral Tian return ratio and crossing enumeration as the rest of this directory. Tables: `python3 fixture_envelope.py` → `fixture-envelope-tables.md`. Raw matrices: `matrix-final_<mode>.md`.
- Lossless cable models give less damping than real cable. Coax cases show extra up/down crossing pairs near the line resonances; the reported minimum takes every downward crossing, and |1+T| is reported as the trajectory-independent distance from −1.
- Typical vendor macromodels at 27 °C; small-signal only. The transient disturbance tests were not rerun with R_iso. Layout placement of R_iso and its parasitics are not yet extracted.

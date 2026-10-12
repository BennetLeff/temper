# M6 coil-terminal working voltage re-run at the 28 A tank ceiling

> **ASSUMED / bounded calculation, pre-measurement.** Fundamental-harmonic (FHA) model plus a time-domain KVL check. No board, schematic or copper file was read for editing or changed. Gap distances are the stage-11 measurements already in `../evidence.txt`.

**Rerun:** `python3 zapote/power-stage-120v/validation-results/08-manufacturing-package/native-21/owner-items/m6m10/coil-voltage-28a/coil_voltage_28a.py` (stdlib only, about 25 s, writes `results.json` beside it, asserts the controls).

## Question

DECISIONS "2026-10-08, coil-stud spacing (review M6)" and ASSEMBLY.md (J2/J5) rest on a coil-terminal working voltage of at most 333 V rms (at most 667 V pk) at the 22 A tank ceiling, covered by the board-wide 5.0 mm tank rule (Table 18, PD3, IIIa, up to 400 V rms). The design now runs a 28 A ceiling. What are the real working voltages at 28 A, and do the 5.0 mm tank rule, the J2/J5 insulated lugs and the SW_A/RES_A and RES_A/COIL_FEED gaps still hold?

## Pass criterion (fixed before the results)

For every gap under the tank rule: **required creepage (Table 18, PD3, IIIa, linear interpolation) at the 28 A worst corner, under the convention the repo adopted (line-cycle time RMS, which is carrier-crest peak / 2 for the sinusoidal line envelope), is at most the actual copper or lug distance.** The worst corner is the M6 envelope-bound method evaluated on the *current* tank: bank 0.50 uF -10 % (0.45 uF), firmware floor 35 kHz, 140 V line (the M6 screen), no-pan coil allowed. The carrier-crest-RMS result (V pk / sqrt 2) is reported in parallel. Clearance is checked against the repo's 1.3 mm.

## Method

- **M6 bound** (`../coil_voltage.py`): |V_coil| <= |V_drive,1| + |V_C|, with V_C <= I * Xc at the lowest frequency, V_drive,1 = (4/pi) * sqrt2 * V_line at line crest. Time RMS = I_rms * Xc + 0.9 * V_line; peak = 2 * I_rms * Xc + 252 V at 140 V (I_pk = 2 * I_rms). M6 used C = 0.54 uF at f = 31.3 kHz (Xc 9.43 ohm). The current tank is 0.50 uF +/- 10 % (round 6) with a 35 kHz firmware floor (DECISIONS item 14), Xc 10.1 ohm.
- **Corner sweep:** 108/120/132/140 V line, C 0.45/0.50/0.55 uF, unloaded coil L 59.9/66.5/73.2 uH (70 uH free = 66.5 uH installed, +/-10 %) with R 0.168 and 0.25 ohm, and loaded L_eq 30-72 uH with R_eq 0.5-5 ohm. For each point f is solved so the line-cycle current equals the ceiling, with f >= max(35 kHz, 1.05 f_res) and f <= 60 kHz. Node voltages come from a 1024-point carrier-cycle time-domain evaluation (ideal 0/Vbus switch nodes, sinusoidal tank current, V_RES_A = V_SW_B + V_C, V_coil = V_SW_A - V_RES_A), so square-wave harmonics are included. Line-cycle RMS = carrier-crest RMS / sqrt 2 (every term scales with |sin| of the line).
- **Pan cases:** the round-6 FHA/ngspice grid rows at I28 (`05-resonant-tank-envelope/round6-full-power/outputs/grid6-*-I28-*-cases.csv`), V_coil = I * |R_eq + j w L_eq|.
- **Controls (asserted by the script):**
  - **C1:** the M6 bound at 22 A gives 326.2 V rms / 652.5 V pk (132 V) and 333.4 V rms / 666.9 V pk (140 V), Table 18 4.20 mm.
  - **C2:** the nine task-05 retained cases give 304.7-320.5 V rms (1710 W cases), 636.2 V pk, and 5.65 mm at the crest-RMS reading.
  - **C3:** the stage-15 bank peak is **483.72 V pk / 243.11 V rms at 28 A** (470.7 / 235.54 at 22 A) in `board-side-protection.csv`; recomputed here from the case rows as I_pk/(w C) it is 492.4 V (FHA, 1.8 % high, conservative).
- **Why 483.72 V and ~424 V are not in conflict.** 483.72 V is the **capacitor-bank voltage (RES_A to SW_B)** of the nine 28 A pan configs, not the coil voltage. `fault_check.py`'s bank peaks (1247-2038 V) are OCP-fault bank peaks, a third quantity. Linear scaling of 333 V (x 28/22 = 424 V) is wrong because only the I * Xc part of the bound scales with current: 28 * 9.43 + 126 = 390 V, not 424 V.
- **Standard values.** The IEC text is not readable here (the sample-PDF extract cited by M6 is not committed). Table 18 rows used are the ones the repo cites: PD3, IIIa, 250 V = 3.2 mm, 400 V = 5.0 mm, 500 V = 6.3 mm, interpolated linearly (NOTE 3 as quoted in `../RECOMMENDATION.md`). Above 500 V the repo cites no row: the script extrapolates the 400-500 V slope, flagged `extrapolated`. Verdicts do not depend on that extrapolation, because 6.3 mm at 500 V already exceeds every 5.0 mm gap. IEC 60664-4 Table 2 (above 30 kHz) is **unverified**, as in M6.

## Results at 28 A

### Coil voltage (J2-J5 = SW_A to RES_A), 140 V line

| Basis | Time (line-cycle) RMS | Peak | Crest RMS | Table 18 (line / crest) |
|---|---:|---:|---:|---:|
| 22 A, M6 bound (control) | 333.4 | 666.9 | 471.6 | 4.20 / 5.93 mm |
| **28 A, M6 corners** (0.54 uF, 31.3 kHz) | 390.0 | 780.1 | 551.6 | 4.88 / 6.97* mm |
| **28 A, current design worst** (0.45 uF, 35 kHz) | **408.9** | **818.0** | 578.4 | **5.12** / 7.32* mm |
| 28 A, same corner, time domain with square-wave harmonics | **412.2** | 762.4 | 583.0 | **5.16** / 7.38* mm |
| 29.4 A (RMS trip), current design worst | 423.1 (416.7 time domain) | 846.3 | 598.4 | 5.30 (5.22) / 7.58* mm |
| 27.2 A (effective cap until calibration), design worst | 400.9 | 801.8 | 567.0 | 5.01 / 7.17* mm |
| 28 A, round-6 pan cases, L70 design tank, worst (I x Z fundamental; time domain 352.3) | 344.5 | 697.0 | 492.9 | 4.33 (4.43) / 6.21* mm |
| 28 A, round-6 pan cases, all L (70/80/90 uH), worst | 361.9 | 732.3 | 517.8 | 4.54 / 6.53* mm |

\* extrapolated beyond the 500 V row. The worst design corner is physically reachable: an unloaded coil (about 66 uH, 0.17 ohm, phase 88 deg) at 35.1 kHz, bank at -10 %, 140 V line, I = 28 A. Real pans lower it (R_eq about 2 ohm, phase about 60 deg).

Sensitivity of the bound (design worst corner, time-RMS): 28 A is 390.9 V at 120 V line, 401.7 V at 132 V, 408.9 V at 140 V. The bound stays at or below 400 V rms for a ceiling of 27.1 A at 140 V line (27.8 A at 132 V, 28.9 A at 120 V), or for line voltage up to 130 V at 28 A. A 280 V-class bus is not in the M6 bound; as the D-31 OVP fault screen it would give 922 V pk at 28 A (`bus280_screen` in `results.json`) and is not a working voltage.

### Other nodes (28 A, design worst corner; line-cycle RMS / crest RMS / peak, V)

| Pair | Line RMS | Crest RMS | Peak | Note |
|---|---:|---:|---:|---|
| SW_A or SW_B to HV_RET | 99.0 | 140.0 | 198.0 | ideal 0/Vbus node; ringing overshoot not modelled |
| SW_A to SW_B (bridge output, COIL_FEED to SW_B) | 140.0 | 198.0 | 198.0 | |
| RES_A to SW_B (bank voltage) | 282.8 | 399.9 | 565.6 | pan model 483.72 pk (control C3) |
| RES_A to HV_RET / N_LS / BUS_P | 353.3 | 499.6 | 762.4 | DC half-bus plus V_C plus SW_B |
| SW_A to RES_A (coil voltage, T1 drop neglected) | 412.2 | 583.0 | 762.4 | same as COIL_FEED to RES_A |

### Per-gap verdicts

Actual distances: stage-11 measurements (`../evidence.txt`: `tank_pairs.py`, `stud_copper.py`, `lug_rotation.py`); the 5.0 mm rule is held by the DRC rules (`native-21/layout/write_rules21.py`). No newer copper dump is committed, so these stand as the figures of record. Clearance requirement is 1.3 mm (repo); all gaps clear it.

| Gap | Actual | Req. creepage, line RMS (worst) | Verdict, repo convention | Req. creepage, crest RMS | Verdict, crest RMS | Pan-model (L70) |
|---|---:|---:|---|---:|---|---|
| RES_A-COIL_FEED (J5/J2 copper, F/B.Cu) | 5.000 | 5.16 | **FAIL** (0.16 mm short) | 7.38* | FAIL | PASS (4.43) |
| RES_A-SW_A (F.Cu lane, 74 mm of edge) | 5.000 | 5.16 | **FAIL** (0.16 mm short) | 7.38* | FAIL | PASS (4.43) |
| J2-J5 insulated ring to ring, any rotation | 5.000 | 5.16 | **FAIL** (0.16 mm short) | 7.38* | FAIL | PASS (4.43) |
| J2-J5 REDCUBE body to body (15 mm pitch) | 8.000 | 5.16 | PASS | 7.38* | PASS | PASS |
| RES_A-SW_B (B.Cu, bank voltage) | 5.002 | 3.59 | PASS | 5.00 | PASS (knife-edge, 0.002 mm) | PASS (3.20) |
| RES_A-N_LS (In1, LOW group) | 5.002 | 4.44 | PASS | 6.29 | FAIL | PASS (3.76) |
| RES_A-HV_RET (In1) | 5.900 | 4.44 | PASS | 6.29 | FAIL | PASS (3.76) |
| RES_A-BUS_P (In2) | 5.900 | 4.44 | PASS | 6.29 | FAIL | PASS (3.76) |
| COIL_FEED-SW_B (B.Cu) | 30.000 | 3.20 | PASS | 3.20 | PASS | PASS |

At the M6 corner set (0.54 uF, 31.3 kHz) the three coil-voltage lanes need 4.88 mm and pass with 0.12 mm margin, so the M6 conclusion survives 28 A only on its original, less severe corners. At the current design corners with a 140 V line it does not. At a 132 V line it fails by 0.02 mm (5.02 mm); it passes at 130 V or below. At the 27.2 A effective cap it fails by 0.01 mm at 140 V and passes at 132 V.

The verdict for the three coil-voltage lanes is therefore **FAIL, marginal**, under the stated criterion. It is a worst-case envelope, not a predicted operating point: it needs an unloaded coil running at the full 28 A ceiling at 35 kHz with a low-side bank tolerance and a 140 V line. With any of the round-6 pan loads the same lanes need 4.3-4.6 mm and pass.

Under the crest-RMS convention, the coil lanes, RES_A-N_LS, RES_A-HV_RET and RES_A-BUS_P all **FAIL** (at least 6.3 mm, which does not rely on extrapolation). The 5.0 mm tank rule fails board-wide under that convention, as M6 already warned for 22 A (5.65 mm); at 28 A it is 6.2-7.4 mm.

Clearance: PASS for every gap (5.0 mm and above against 1.3 mm). The recurring peak is now up to 0.82 kV, above the 0.67 kV M6 quoted. IEC 60664-4 Clause 4 is unverified; a PD3 floor of 0.8 mm governs in any case at this peak, and nothing here approaches it.

## Recommendation

1. **Do not claim "at most 333 V rms" for the 28 A design.** The bound is 391-409 V rms at 28 A (423 V at the 29.4 A trip), the peak is 780-818 V (not 667 V). Update DECISIONS 2026-10-08, ASSEMBLY.md and `F1-CERTIFIER.md` item 7 when the owner agrees (not edited here: study only).
2. **Smallest fix, no copper:** keep 5.0 mm and hold the bound at or below 400 V rms by one of: the firmware frequency floor 36.2 kHz instead of 35 kHz (`f_floor_for_400V_28A_140V_C0p45_kHz` = 36.14); bank minimum 0.465 uF (about -7 % tolerance, not -10 %); or a line-dependent ceiling (27.1 A at 140 V, 27.8 A at 132 V). Each costs some round-6 yield (not quantified here); the 27.2 A effective cap already shipped until calibration gives 400.9 V at 140 V, i.e. it is on the limit, not clear of it.
3. **Or widen the coil-voltage lanes:** set the tank rule on RES_A-COIL_FEED and RES_A-SW_A to **5.3 mm** (covers 5.16 mm at 28 A and 5.22-5.30 mm at the 29.4 A trip). That moves 74 mm of F.Cu/B.Cu pour edge by 0.3 mm, which looks like a pour-clearance change rather than a re-layout but is **unverified on the board** (the board owner must run DRC). The ring-to-ring distance of 5.0 mm (15 mm pitch minus the 10 mm ring) needs the pitch to 15.3 mm, or insulation over the ring edge, or a lab ruling. RES_A to HV_RET/BUS_P in the inner layers (5.9 mm) and RES_A-N_LS (5.002 mm) already clear 4.44 mm.
4. **Lab question (F1-CERTIFIER item 7 now has different numbers):** ask the certifier whether the Table 18 working voltage for a line-modulated 35-60 kHz tank is the time RMS (about 412 V worst, 345-362 V with pans) or the carrier-crest RMS (about 583 V worst, 493-518 V with pans), and what IEC 60664-4 Table 2 gives above 30 kHz. If crest RMS applies, the tank rule must go to at least 6.3 mm on the coil, inner-layer and N_LS lanes (about 7.4 mm if the table continues linearly), a board-wide re-layout.
5. **Bench:** measure V(J2-J5), V(RES_A-HV_RET) and V(RES_A-SW_B) at 28 A with an unloaded and a loaded coil (R25 BENCH-PLAN P-series); this replaces the bound.

## Files

- `coil_voltage_28a.py`: the script (controls, bound, sweep, pan cases, verdicts).
- `results.json`: all numbers, sorted keys; `analytic_bound`, `sweep`, `pan_cases`, `gap_verdicts`, `ceiling_for_400V_rms`, `line_for_400V_rms_design_worst`, `bus280_screen`, `controls`.

## Limits

- FHA current with ideal 0/Vbus switch nodes; ngspice tank peaks run up to 5.8 % above the FHA fundamental (checked, asserted below 8 %). Switch-node ringing is not modelled.
- The 5.0 mm gap figures are stage-11 and are assumed unchanged through stages 12-17 (rule-enforced); nothing newer is committed.
- Table 18 rows are the repo's citations, not read from the standard. IEC 60664-4 not checked.
- The sweep assumes the ceiling is reachable by frequency alone (fixed 180 deg phase, no phase shift, DECISIONS D-27).

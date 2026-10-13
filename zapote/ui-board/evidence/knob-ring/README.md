# Knob rim ring (option (a), geometry A0): angle error, field, torque and the standoff conflict

2026-10-12, temper-bc, for the enclosure session. Request: `KNOB-SIMPLIFICATION.md` and `data/rim_ring_screen.json` of the owned-controls evidence (read-only inputs). Everything below comes from `ring_study.py` (deterministic) and is in `results.json` (`headline` first), `plots/` and `raw/`; the tables here are generated from `results.json`. A physics screen of the A0 geometry as defined by the request, not an installable design and not a measurement.

## 1. Question

With the stationary 1010 steel detent ring (outer r 27.5, tooth root 26.5, tips 25.5, w -4..-3, 24 teeth, 15 deg pitch, 7.5 deg wide) behind the fascia and 24 SmCo 35E rim magnets (1 x 2 x 2 mm, r 26.5, w +1..+3, all +w) on the knob, how much angle error does the ring add to the Ø10 x 5 diametral 35E sensing magnet read by the TMAG5170 at (110, 53, w -4), against the ring's share of the 0.6 deg pool? Secondary: |B| range, steel saturation and hysteresis, drift with push / tilt / tolerance, total with the existing coil allowance, torque and pull, and whether the three standoffs and J9 can clear the ring.

## 2. Pass criterion (fixed before the run; constants `POOL_DEG`, `RING_SHARE_DEG`, `CRITERIA` in the script)

**Budget.** `ui_calcs.py` (U24) leaves "at least 0.6 deg of the 1 deg" after the 0.40 deg non-repeatable error (3.5 sigma noise, stray field, quantisation, 0.057 deg gain residual) and allocates none of it. The pool is shared by calibration residual, magnet and mechanism. Equal thirds give 0.20 deg to the mechanism; the ring is one mechanism part, so it may use half of that third: **ring share = 0.10 deg.**

**Measure.** *D*, the ring-attributable calibrated residual: the angle error with the ring minus the angle error of the same unit without the ring, each after its own fixed cold calibration (released, 20 C, nominal gap, fitted on 35 angles 0.5 + 10.25 k deg, none on a detent centre; calibration = offset + gain + skew + 4 error harmonics of the measured angle, `harm4`; the affine and `harm4_24` variants are also reported). Validation uses every other angle of the cold run (0.25 deg grid) and every other condition. Sensor drift at the hot die temperature is applied identically to both and cancels in D.

| | Criterion |
|---|---|
| P1 | D <= 0.10 deg over every condition and every material variant (linear mu_r 200..2000, representative saturating 1010, soft and hard curves, hysteresis Hc 160 and 400 A/m), after the mesh-uncertainty factor of the convergence study |
| P2 | absolute calibrated residual with the ring <= 0.60 deg (the whole pool) |
| P3 | the field magnitude stays inside 80 % of the +/-100 mT range with the ui_calcs tolerances (<= 80 mT) and the ring changes it by < 1 % |
| P4 | all controls pass, halving the element size changes the peak angle error by < 10 % |
| verdict | PASS if P1..P4 hold and D (and the uncalibrated ring part) <= 0.05 deg; FAIL if P1 fails; **INCONCLUSIVE if P1..P4 hold but D lies within a factor 2 of the share**, because the B-H curve, the coercivity and the mount are not measured |

## 3. Bottom line

**Angle-error budget: INCONCLUSIVE.** P1 to P4 hold, but the worst modelled ring-attributable calibrated residual is **D = 0.084 deg** (0.072 deg as computed, times the 1.17 mesh-uncertainty factor of section 5.9) against the 0.10 deg share: a margin of 1.18, under the factor 2 the criterion asks for. That worst case is entirely the **assumed steel hysteresis** (vector play, coercive field 400 A/m, a cold-worked bound; 0.039 deg after the mesh factor for 160 A/m): a lag of the steel's magnetisation behind the rotating field that reverses with the direction of rotation, so no static calibration removes it. **Without hysteresis D <= 0.0072 deg (14 times inside the share)** for every linear mu_r from 200 to 2000, the saturating 1010 curve and its soft and hard variants, every push, gap, temperature, offset, tilt and ring-offset condition. The ring is nearly invisible to the angle: by symmetry the 24 rim magnets and the 24-fold ring produce only Bz on the axis, and the ring's response to the sensing magnet is a gain (0.6 % of |B|), not a rotation.

**Detent function: FAIL for A0 as defined.** The model supports torque and pull. The peak detent torque of the 24 rim magnets against the ring is **4.1 uN*m** (energy ripple 0.33 uJ peak to peak, independent of mu_r), against SPEC 18 to 30 mN*m average, 25 to 45 mN*m peak: **about 4 400 times too small**; the axial pull on the knob is about **5 mN** (3.5 to 5.8 mN over mu_r 200 to 2000), toward the ring. The cause is geometry, not the steel: 4 mm^3 blocks 4 to 5 mm from a 1 mm thick ring, through the 3 mm fascia. Both numbers were cross-checked by a second route (control 4, agreement within 2 % and 0.1 %). Torque scales roughly with the square of the rim-magnet moment: blocks twice as large in every dimension (8 times the moment, 64 times the torque, and already more than the 3 mm radial space holds) would still give only about 0.26 mN*m, 70 times short (a scaling estimate, not computed). **The fallback, option (b) (magnet-pair detents, nonmagnetic retention, no panel-side steel), is the only route this study supports for the detent.** The ring was worth screening: had it carried the detent, its angle error would have been acceptable if the steel's coercivity is low.

| Item | Result |
|---|---|
| Peak uncalibrated angle error | ring present: **0.072 deg** worst over everything (ideal unit, Hc 400 A/m hysteresis; 0.084 deg with the mesh factor on the ring part); without hysteresis the ring adds at most **0.013 deg** (tilt 1 deg, saturating curve) on top of the 0.0285 deg that the as-built unit's own offset and tilt cause without any ring; the ideal coaxial unit gives 0 (linear steel) or 5e-5 deg (saturating: the sin 24 theta term) |
| Worst residual after one fixed cold calibration, validated on non-fit angles and conditions | **ring-attributable D 0.084 deg** (hysteresis, Hc 400 A/m, direction dependent); **0.0072 deg without hysteresis**; absolute residual of the worst as-built unit with the ring (tolerances and conditions, no hysteresis) 0.062 deg at the hot sensor (sensor gain residual 0.057 deg, present without the ring), 0.0086 deg cold |
| Field magnitude at the die | **49.5 mT** weakest (hot magnets, gap +0.2 mm) to **67.8 mT** strongest (cold, push 0.5 mm, gap -0.2 mm), ring present; the ring lowers the magnitude by at most 0.58 %; with the ui_calcs tolerances 47.1 to 72.7 mT (ui_calcs: 47.3 to 73.0), inside 80 % of the +/-100 mT range |
| Saturation | representative 1010: highest cell 1.37 to 1.42 T, at the knee but below 1.5 T, in the root annulus at +/-v where the sensing magnet's field runs along the ring (peak internal H about 1.0 kA/m); the soft curve reaches 1.57 T with 10 % of the cells above 1.5 T; constant mu_r 2000 would imply 1.8 T, so linear overstates; saturation changes the ring part of the error by 11 to 15 % and gives the ideal unit a 24th harmonic of 4.4e-5 deg |
| Hysteresis | direction-dependent offset **+/-0.034 deg (Hc 160 A/m), +/-0.072 deg (Hc 400 A/m)**, nearly constant over the pitch (plots/hysteresis.png) |
| With the existing coil allowance | D 0.084 (hysteresis) plus 0.173 (worst bare no-pan 60 kHz) = **0.257 deg linear, 0.192 deg RSS**; 0.112 deg linear with the base and roof; without hysteresis 0.180 deg linear; pool left for calibration, magnet and the rest of the mechanism 0.516 deg; non-repeatable 0.403 + ring 0.084 = 0.487 deg of the 1 deg |
| Geometry conflict | **Real**: the three standoff bodies (w -4.78 to -3.0) overlap the ring slab (w -4 to -3) and their heads end 0.85 to 2.0 mm inside the ring's outer radius in plan. They **can** move outward: three standoffs at (80.85, 40.35), (80.85, 65.65), (141.65, 53.0) clear r 29 (heads 29.15 to 29.28 mm from the axis, 1.65 to 1.78 mm of clearance) if the sensor tab grows from 64 x 32 to 67.5 x 32 mm (u 77.5 to 145). J9 is not in the way if it is on the tab's rear face (section 6) |


## 4. Method

- **Permanent magnets.** Sensing magnet: magpylib `Cylinder` (analytic diametral solution). Rim blocks: an exact cuboid field kernel (closed-form face-charge formulas, numba), checked against magpylib to 1e-10. 35E: Br 1.19 T at 20 C, -0.035 %/K reversible (ui_calcs), so 1.0 x at 20 C and 0.945 x at 176 C for all 25 magnets. Torque and axial force: energy method, W = -mu0/2 sum V M.H_ext over the steel cells, cross-checked by the direct force on the magnets (control 4).
- **Steel.** Volume-integral method of moments. The ring is meshed in annular-sector cells aligned with the tooth pitch (the mesh has the exact C24 symmetry of the ring); each cell is a uniformly magnetised rotated cuboid with the exact cuboid field kernel and collocation at the cell centre; cell-cell interaction matrix A (self terms included) is dense. Production mesh 0.5 mm radially and axially, 1.875 deg in phi: 1152 cells, 251.33 mm^3 (equal to the analytic ring volume). Coarse (144 cells, 1 mm) and fine (9216 cells, 0.25 mm) levels for the convergence study.
- **Materials.** (i) Linear mu_r = 200, 500, 1000, 2000 (**a material-sensitivity study, not an acceptance bound**). (ii) A **representative** saturating 1010 normal-magnetisation curve (mu_r initial 318, mu_r max 2200, 1.0 T at 400 A/m, 1.5 T at 1.5 kA/m, 1.9 T at 12 kA/m, J_s 2.1 T): handbook-typical anchors, **not a measured curve** (`steel_curve_*` in `results.json`); solved by damped Newton with a GMRES / reused-LU inner solve. Soft and hard variants scale the H axis x2 and x0.5; the 176 C case uses H axis x1.3, J_s x0.97 [ASSUMED]. (iii) Hysteresis: vector play operator on the field inside each cell (smoothed, p = 8) with coercive field Hc 160 A/m (annealed 1010) and 400 A/m (cold-worked bound) [ASSUMED], run clockwise and counter-clockwise for 4 tooth pitches, the last pitch recorded (it differs from the previous pitch by 0.6 % of the ring field at Hc 160 and 2.9 % at Hc 400, `periodic_regime_check_T`). This is a rate-independent lag model, not a measured loop.
- **Conditions.** Group A: the ideal coaxial unit, C24-symmetric (one 15 deg pitch at 0.25 deg is the full turn; verified against a direct 360 deg run to 1e-14): cold, push 0.5 mm, gap error -0.2 / +0.2 mm, push + gap -0.2, hot (176 C magnets), hot + gap +0.2, hot + push + gap -0.2. Group B: a worst-tolerance as-built unit (knob offset (0.1, 0.1) mm, tilt 1 deg about u, ring offset (0.1, 0) mm) with the same eight conditions on top (full turn at 0.25 deg). Group C: single tolerances released and cold (knob offset +/-0.1 mm in u and v, tilt 1 deg about u and v, ring offset 0.1 mm in u and v). The tilt (1 deg, pivot at the sensing magnet's near face) and the ring offset are assumptions; the request listed face gap, lateral offset, push and temperature.
- **Sensor.** Angle = atan2 of the X/Y pair (axes reversed: on-axis return flux is antiparallel to the magnetisation). Hot cases: die 120.2 C (ui_calcs `sensor_thermal`); X/Y sensitivity mismatch drift 4.0 %/100 K (SBASAF4 p.7, U23) is 3.81 % uncorrected and 0.2 % (= the 0.057 deg of ui_calcs) after the TEMP_RESULT correction; both reported, D is unaffected. Offset drift: not modelled (no sourced number).
- **Grids.** 0.25 deg for the ideal unit, every linear material and every group B/C unit. The saturating solves on asymmetric units are direct at 2 deg (group B), 4 deg (the others and the soft/hard curves) and the hysteresis runs at 0.5 deg; their increment over the reference material (lin1000, then the saturating curve) is interpolated to 0.25 deg with a periodic cubic spline (`increment_interpolated` in the code; the increment is small and smooth, and for the ideal unit nothing is interpolated except the hysteresis increment). Extremum refinement re-solves at 0.0625 and 0.03125 deg around the three largest ring errors of the worst case, linear and saturating (section 5.9).

## 5. Results

### 5.1 Controls (all asserted in the script)

| # | Control | Result | Limit |
|---|---|---|---|
| 1 | Ring absent: sensing magnet at the die against `ui_calcs.magnet_b_mT` | 55.7278 mT against 55.7278 mT at 20 C (error 0.0e+00); 52.6851 against 52.685 mT at 176 C (1.6e-06); with the 24 rim magnets present the total magnitude is 55.7292 mT (they add only Bz) | 2 % |
| 2a | Cuboid kernel against magpylib (rotated block, random points) | 1.3e-10 | 1e-6 |
| 2b | Diametral cylinder on axis against the closed form at 5, 9, 15 mm | 55.728, 20.106, 6.384 mT, errors <= 2e-15 | 1 % |
| 2c | The moment-method solver against a linear sphere in a uniform field, M = 3(mu-1)/(mu+2) H0 (R 5 mm, 4139 cubic cells of 0.5 mm, mu_r = 3) | mean M 1.0056, moment 1.0056, on-axis field at 3R 1.0005, equatorial 1.0080 of the closed form (mu_r = 10 for information: 1.020, 1.013, 1.024; a voxelised sphere's demagnetising factor is about 1.5 % off 1/3 and this is amplified at high mu_r) | 1 % (asserted on mu_r = 3: mean, moment, axial) |
| 3 | Halving the element size (0.5 to 0.25 mm), peak angle error of the as-built unit | total peak error 2.8 % (coarse to production 0.56 %); **the ring-attributable part changes 17 %, see 5.9** | 10 % (total: pass) |
| 4 | Energy-method torque and axial force against the direct force on the magnets from the steel's own field (frozen M; rim blocks as 27 dipoles, sensing magnet as a 9 x 9 x 5 grid) | torque -3.94 against -3.86 uN*m (ratio 0.979); axial -5.24 against -5.24 mN (ratio 0.9991) | 0.9 to 1.1 |
| 5 | Periodicity: one 15 deg pitch tiled to 360 deg against a direct 360 deg run (ideal unit, mu_r 1000) | 1.2e-14 of the peak field | 1e-8 |
| 6 | Constants against the unit's `floorplan.py` (knob axis, die plane w -4, keep-out 25 mm, magnet diameter and near face) and the mesh volume against the analytic ring volume | equal; 251.33 mm^3 against 251.33 mm^3 | exact |

### 5.2 Raw Bx, By, Bz against angle

`raw/<case>.csv` (0.25 deg steps, full turn, ring present with the saturating steel where it was run and without the ring, the ring's own contribution in uT and the uncalibrated error) for A_cold, A_strong, A_weakhot, B_cold, B_strong, B_hotstrong, C_tiltx, C_offpx; `plots/raw_field_vs_angle.png`. At the nominal seat (ideal unit, released, 20 C, saturating steel), theta = 0: **(Bx, By, Bz) = (-55.397, 0.000, -0.393) mT** with the ring, (-55.728, 0.000, -0.386) mT without; the steel adds (+331.1, 0, -7.1) uT, and at theta = 3.75 deg (+330.4, +21.7, -6.8) uT, which is the same 0.6 % of the field rotated with the magnet. The sign is negative because the on-axis return flux of a diametral magnet is antiparallel to its magnetisation. The rim magnets alone give Bz = -0.386 mT and exactly zero X and Y on the axis (24-fold symmetry), so they do not touch the angle and only enter |B|.

**Weakest and strongest |B| (3-axis, ring present): 49.5 mT** (A_weakhot: 176 C magnets, gap +0.2 mm; saturating 49.5 mT) **to 67.8 mT** (B_strong: cold, push 0.5 mm, gap -0.2 mm). Without the ring 49.8 to 68.1 mT. With the ui_calcs tolerances (Br +/-5 %, -40 C): 47.1 to 72.7 mT, against ui_calcs 47.3 to 73.0.

### 5.3 Uncalibrated angle error (raw atan2 of X and Y, sensor ideal, deg)

Group A (ideal coaxial unit; with no ring the error is exactly 0):

| case | field magnitude, mT (saturating where run) | peak error, no ring, deg | peak error with ring, linear 1000 / saturating | ring-attributable, linear 1000 / saturating | max steel B, T |
|---|---|---|---|---|---|
| A_cold | 55.40 to 55.40 | 0.0000 | 0.0000 / 0.0001 | 0.0000 / 0.0001 | 1.37 |
| A_gapm | 58.64 to 58.64 | 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 1.38 |
| A_gapp | 52.36 to 52.36 | 0.0000 | 0.0000 / 0.0001 | 0.0000 / 0.0001 | 1.37 |
| A_hot | 52.37 to 52.37 | 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 1.39 |
| A_hotstrong | 64.01 to 64.01 | 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 1.40 |
| A_push | 63.91 to 63.91 | 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 1.39 |
| A_strong | 67.71 to 67.71 | 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 1.39 |
| A_weakhot | 49.49 to 49.49 | 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 1.39 |

Group B (worst-tolerance as-built unit; its own offset and tilt cause 0.028 to 0.0285 deg without any ring):

| case | field magnitude, mT (saturating where run) | peak error, no ring, deg | peak error with ring, linear 1000 / saturating | ring-attributable, linear 1000 / saturating | max steel B, T |
|---|---|---|---|---|---|
| B_cold | 55.40 to 55.48 | 0.0285 | 0.0330 / 0.0335 | 0.0104 / 0.0116 | 1.39 |
| B_gapm | 58.68 to 58.76 | 0.0284 | 0.0332 / - | 0.0107 / - | - |
| B_gapp | 52.39 to 52.47 | 0.0285 | 0.0327 / - | 0.0102 / - | - |
| B_hot | 52.41 to 52.48 | 0.0285 | 0.0330 / - | 0.0104 / - | - |
| B_hotstrong | 64.01 to 64.11 | 0.0282 | 0.0341 / 0.0350 | 0.0114 / 0.0129 | 1.42 |
| B_push | 63.95 to 64.04 | 0.0283 | 0.0336 / - | 0.0111 / - | - |
| B_strong | 67.71 to 67.82 | 0.0282 | 0.0341 / 0.0349 | 0.0114 / 0.0127 | 1.41 |
| B_weakhot | 49.53 to 49.60 | 0.0285 | 0.0327 / - | 0.0102 / - | - |

Group C (single tolerances, released, cold):

| case | field magnitude, mT (saturating where run) | peak error, no ring, deg | peak error with ring, linear 1000 / saturating | ring-attributable, linear 1000 / saturating | max steel B, T |
|---|---|---|---|---|---|
| C_offmx | 55.42 to 55.45 | 0.0076 | 0.0076 / - | 0.0001 / - | - |
| C_offmy | 55.42 to 55.45 | 0.0076 | 0.0076 / - | 0.0001 / - | - |
| C_offpx | 55.42 to 55.45 | 0.0076 | 0.0076 / - | 0.0001 / - | - |
| C_offpy | 55.42 to 55.45 | 0.0076 | 0.0076 / - | 0.0001 / - | - |
| C_ringpx | 55.43 to 55.43 | 0.0000 | 0.0001 / - | 0.0001 / - | - |
| C_ringpy | 55.43 to 55.43 | 0.0000 | 0.0001 / - | 0.0001 / - | - |
| C_tiltx | 55.39 to 55.43 | 0.0074 | 0.0170 / 0.0182 | 0.0104 / 0.0117 | 1.39 |
| C_tilty | 55.43 to 55.46 | 0.0074 | 0.0170 / - | 0.0104 / - | - |

The ring-attributable error of the tolerance cases (0.010 to 0.013 deg) is the tilt: 11 to 15 % larger with the saturating curve than with mu_r = 1000. It is a first harmonic (0.0113 deg of 0.0116 deg; 2nd harmonic 8e-5, 24th harmonic 4e-5 deg), so a static calibration removes it. The 24-fold term the request worried about is, for the ideal unit, **4.4e-5 deg** and exists only with the saturating steel (linear steel: 1e-13 deg): the rim magnets and the ring are both exactly C24, so the ring can only add a gain and a state-dependent phase to the sensing magnet's field at the die.

### 5.4 Calibration and validation (cold fit, one calibration, deg)

Representation: offset, gain, skew and 4 error harmonics of the measured angle (`harm4`), fitted on 35 angles of the released cold unit with the reference steel (linear 1000); the other 1405 angles of that run, and all other conditions and all other steel models, are validation. R = absolute calibrated residual with the ring, D = ring-attributable (with ring minus no ring, each calibrated cold with its own fit). Hot cases carry the sensor gain residual of ui_calcs (0.057 deg, identical with and without the ring). Maxima over all 1440 angles; `R_at_detent_centres` is in `results.json` (for the as-built unit the maximum over all angles exceeds the detent-centre value by up to 30 %, e.g. 0.0010 against 0.0008 deg for B_gapp, which is why every angle is judged).

| case (sensor) | no ring: R | linear 1000: R / D | linear 200: R / D | linear 2000: R / D | saturating: R / D |
|---|---|---|---|---|---|
| B_cold (ideal) | 0.0000 | 0.0002 / 0.0002 | 0.0060 / 0.0060 | 0.0016 / 0.0016 | 0.0014 / 0.0014 |
| B_gapm (ideal) | 0.0009 | 0.0012 / 0.0004 | 0.0067 / 0.0059 | 0.0025 / 0.0018 | - |
| B_gapp (ideal) | 0.0008 | 0.0010 / 0.0003 | 0.0068 / 0.0061 | 0.0021 / 0.0014 | - |
| B_hot (corrected) | 0.0570 | 0.0572 / 0.0002 | 0.0614 / 0.0060 | 0.0581 / 0.0016 | - |
| B_hotstrong (corrected) | 0.0558 | 0.0566 / 0.0011 | 0.0596 / 0.0057 | 0.0576 / 0.0026 | 0.0577 / 0.0027 |
| B_push (ideal) | 0.0023 | 0.0027 / 0.0008 | 0.0078 / 0.0058 | 0.0041 / 0.0023 | - |
| B_strong (ideal) | 0.0032 | 0.0039 / 0.0012 | 0.0086 / 0.0057 | 0.0053 / 0.0027 | 0.0051 / 0.0025 |
| B_weakhot (corrected) | 0.0577 | 0.0577 / 0.0004 | 0.0620 / 0.0061 | 0.0586 / 0.0013 | - |
| A_cold (ideal) | 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 0.0001 / 0.0001 |
| A_hotstrong (corrected) | 0.0570 | 0.0570 / 0.0000 | 0.0570 / 0.0000 | 0.0570 / 0.0000 | 0.0570 / 0.0000 |
| A_strong (ideal) | 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | 0.0000 / 0.0000 |

Material variants (maximum D over groups A and B, `harm4`):

| material | max D, deg | at |
|---|---|---|
| lin1000 | 0.0012 | B_strong |
| lin200 | 0.0061 | B_weakhot |
| lin2000 | 0.0027 | B_strong |
| lin500 | 0.0030 | B_weakhot |
| nl | 0.0027 | B_hotstrong |
| nl_h160_ccw | 0.0335 | A_cold |
| nl_h160_cw | 0.0335 | A_cold |
| nl_h400_ccw | 0.0719 | A_cold |
| nl_h400_cw | 0.0719 | A_cold |
| nl_hard | 0.0006 | B_cold |
| nl_soft | 0.0018 | B_cold |

Calibration variants:

| calibration | max D without hysteresis | max D saturating, no hysteresis | max D all variants |
|---|---|---|---|
| affine | 0.0072 | 0.0043 | 0.0719 |
| harm4 | 0.0061 | 0.0027 | 0.0719 |
| harm4_24 | 0.0061 | 0.0027 | 0.0719 |

The uncorrected sensor drift (X/Y sensitivity mismatch 3.81 % at the 120.2 C die) leaves R = 1.09 deg with or without the ring (D 0.0008 deg): the temperature correction of U23 is mandatory and is not a ring effect.

### 5.5 Saturation

Highest flux density in any ring cell over all angles (share of cells above 1.5 T in brackets):

| case | linear 200 | linear 1000 | linear 2000 | saturating | soft curve | hard curve |
|---|---|---|---|---|---|---|
| A_cold | 0.34 T (0 %) | 1.22 T (0 %) | 1.81 T (12 %) | 1.37 T (0 %) | 1.56 T (10 %) | 1.13 T (0 %) |
| A_strong | 0.35 T (0 %) | 1.25 T (0 %) | 1.85 T (13 %) | 1.39 T (0 %) | 1.57 T (10 %) | 1.15 T (0 %) |
| A_hotstrong | 0.34 T (0 %) | 1.18 T (0 %) | 1.75 T (11 %) | 1.40 T (0 %) | - | - |
| B_cold | 0.35 T (0 %) | 1.26 T (0 %) | 1.86 T (13 %) | 1.39 T (0 %) | 1.57 T (10 %) | 1.15 T (0 %) |
| B_strong | 0.37 T (0 %) | 1.30 T (0 %) | 1.92 T (14 %) | 1.41 T (0 %) | - | - |
| B_hotstrong | 0.35 T (0 %) | 1.23 T (0 %) | 1.82 T (12 %) | 1.42 T (0 %) | - | - |
| C_tiltx | 0.35 T (0 %) | 1.26 T (0 %) | 1.87 T (13 %) | 1.39 T (0 %) | - | - |

The representative curve reaches 1.37 to 1.42 T, always in the **root annulus at +/-v (phi about 85 and 275 deg)**: there the sensing magnet's in-plane field is tangent to the ring and the 1 mm x 1 mm root section guides it along its length (internal H about 1.0 kA/m), while the tooth tips carry 0.03 T on average and the rim magnets' own fields are weak at 4 to 5 mm. It is at the knee, not in deep saturation (J_s 2.1 T, no cell above 1.5 T); a thinner root would saturate. A softer curve (higher permeability) does cross 1.5 T in 10 % of the cells; constant mu_r of 2000 would imply 1.8 T and is not physical. What saturation does to the angle is small (5.3). Not modelled: the steel's response in the 31 to 55 kHz coil field (section 7).

### 5.6 Hysteresis (ideal unit, released, cold)

| Hc, A/m | clockwise error, deg | counter-clockwise, deg | cw minus ccw (peak), deg | ring field cw minus ccw, uT | regime check (pitch 3 vs 4) |
|---|---|---|---|---|---|
| 160 | +0.0335 | -0.0335 | 0.0670 | 64.8 | 2.1 uT |
| 400 | +0.0719 | -0.0719 | 0.1423 | 137.7 | 9.6 uT |
A vector play model, rate independent, on the field inside each cell. The steel's magnetisation lags the rotating sensing-magnet field by an angle of the order of Hc over the internal field (a few hundred A/m), which rotates the ring's 0.6 % contribution by that lag: an error of +/-0.034 deg (Hc 160) or +/-0.072 deg (Hc 400), nearly constant over the pitch (`plots/hysteresis.png`) and reversing with the direction of rotation: a **backlash-like offset of +/-0.04 to +/-0.07 deg that the cold calibration cannot remove**, only a direction-aware correction could. It scales roughly with Hc. This is the study's largest ring effect and it rests on an assumed Hc; the coercivity of the actual steel lot is the measurement that would close the verdict.

### 5.7 Total with the existing coil allowance

The ring's D (mesh-adjusted, 0.084 deg with hysteresis, 0.0072 deg without) added to the worst stray-field angle error of ui_calcs U24 (computed without any ring):

| coil allowance case | allowance, deg | with hysteresis: linear / RSS | without hysteresis: linear / RSS |
|---|---|---|---|
| nopan_60000_bare | 0.1726 | 0.257 / 0.192 | 0.180 / 0.173 |
| nopan_60000_base_roof | 0.0272 | 0.112 / 0.089 | 0.034 / 0.028 |
| pan_31000_bare | 0.0511 | 0.135 / 0.099 | 0.058 / 0.052 |
| pan_31000_base_roof | 0.0015 | 0.086 / 0.084 | 0.009 / 0.007 |
Pool left for calibration, magnet and the rest of the mechanism: 0.516 deg; non-repeatable 0.403 deg + ring 0.084 deg = 0.487 deg of the 1 deg.

### 5.8 Torque and pull (the model supports them)

| steel | detent torque peak, uN*m | energy ripple p-p, uJ | axial force, mN (negative: toward the ring) |
|---|---|---|---|
| lin1000 | 4.1 | 0.327 | -5.2 |
| lin200 | 4.1 | 0.326 | -3.5 |
| lin2000 | 4.1 | 0.328 | -5.6 |
| nl | 4.1 | 0.327 | -5.8 |
Torque = -dW/dtheta of the induced-steel energy -mu0/2 sum V M.H_ext (exact for the linear steel; an estimate for the saturating curve; no hysteresis loss). Peak at about a quarter pitch; the same 4 uN*m for mu_r 200 to 2000 because a 1 mm plate under a normal field is demagnetisation-limited. SPEC: 18 to 30 mN*m average, 25 to 45 mN*m peak (SPEC.md). Axial force from the angle-averaged energy over gap error -0.2 to +0.2 mm, includes the sensing magnet's own pull. These are model numbers and **not a measurement**; a fixture measurement is still needed, but the gap to the spec is almost four decades.

### 5.9 Convergence and extremum refinement

Element size (case B_cold, 6 deg grid, linear mu_r 1000):

| level | element, mm | cells | peak total error, deg | peak ring-attributable (linear 1000), deg | ring-induced field peak (linear 1000), uT |
|---|---|---|---|---|---|
| coarse | 1.0 | 144 | 0.0331 | 0.0108 | 323 |
| prod | 0.5 | 1152 | 0.0329 | 0.0104 | 307 |
| fine | 0.25 | 9216 | 0.0339 | 0.0122 | 355 |
Control 3 is on the peak angle error and passes (2.8 % total on halving). The **ring-attributable part is converged more slowly**: the ring's induced field is 322 / 307 / 355 uT on the coarse / production / fine meshes (non-monotone; a thin, high-permeability plate with piecewise-uniform magnetisation converges slowly), and the ring-attributable peak changes 17 % from production to fine; coarse to production 3 % (linear 1000), 5 % (200), 16 % (2000), 17 % (saturating). The fine mesh was not run with the saturating steel. The verdict therefore multiplies every ring-attributable number by **1.173** (fine over production). A further halving is not available here (dense matrix 6 GB at 0.25 mm); the ring part may still be under-estimated by an unknown amount, which is one more reason the angle verdict is INCONCLUSIVE and not PASS.

Extremum refinement (worst ring-attributable case B_strong, deg): re-solving at 0.0625 and 0.03125 deg around the three largest errors moves the peaks by < 0.4 % of the peak (0.0003 deg at most) and halving the step changes them by < 1e-5 deg, so the 0.25 deg grid resolves the extrema.

| material | extremum at, deg | 0.25 deg grid | 0.0625 deg | 0.03125 deg |
|---|---|---|---|---|
| lin1000 | 180.00 | 0.01140 | 0.01140 | 0.01140 |
| lin1000 | 0.00 | 0.01132 | 0.01132 | 0.01132 |
| lin1000 | 183.25 | 0.01115 | 0.01118 | 0.01118 |
| nl | 179.75 | 0.01270 | 0.01270 | 0.01270 |
| nl | 0.00 | 0.01262 | 0.01262 | 0.01262 |
| nl | 183.00 | 0.01243 | 0.01247 | 0.01247 |

### 5.10 If the standoffs stay: a ring with cut-outs

Removing the five pitches that contain the three present standoff directions (0, 158, 202 deg; 75 deg of the ring, the other 19 teeth kept), ideal unit, released, cold: ring-attributable uncalibrated error **0.0788 deg** (linear 1000) / **0.0881 deg** (saturating), almost all of it a 2nd harmonic (0.0784 deg, the ring is no longer axisymmetric); after a static fit of harmonics 1 to 4 (what the cold calibration does) 0.0002 / 0.0003 deg remain. So cut-outs are acceptable for the angle (0.08 to 0.09 deg raw, 0.0003 deg calibrated) but five of 24 detents would then have no steel and the detent torque is already ~4 uN*m: this does not rescue option (a).


## 6. Geometry conflict: standoffs and J9

**Is it a real conflict? Yes for the standoffs, no for J9 (if J9 is on the rear face).**

- **Ring slab:** w -4 to -3, r 25.5 to 27.5 (outer envelope 27.5). Sensor tab: front face w -4.78, rear face w -6.38 (floorplan U26), fascia rear w -3.0. The standoffs are 1.78 mm tall (w -4.78 to -3.0): **their bodies overlap the ring slab axially over its whole 1.0 mm**, so wherever they stand inside r 27.5 (plus the head radius 2.5 mm used in the floorplan) they collide with the ring. In plan the heads reach 26.655 mm (83, 42), 26.655 mm (83, 64) and 25.5 mm (138, 53) from the axis: 0.84, 0.84 and 2.00 mm inside the ring's outer envelope, at 202, 158 and 0 deg.
- **Front-face parts under the ring:** the ring bottom (w -4) is only 0.78 mm above the tab's front face, so any front-face part inside r 25 to 28 must be under 0.7 mm tall (0402 passives are; the SRV05-4 U7 SOT-23-6 at about 1.1 mm is not; keep it outside r 28 or on the rear face).
- **J9** (82, 53), body 4.25 x 13 mm, nearest point 25.875 mm from the axis (inside the ring's footprint by 1.62 mm). Its face is not stated in the unit. A SM10B-SRSS-TB (side entry) is several millimetres tall (datasheet not fetched, unverified), more than the 1.78 mm between the tab's front face and the fascia, so it can only be on the **rear face**, where it is at least 2.38 mm below the ring's underside (w -6.38 against -4): plan overlap with no axial overlap is harmless and **J9 does not move**. Record "J9 on the rear face" in `floorplan.py`. If J9 had to be on the front face it could only clear r 29 with the tab's -u edge at u <= 75.75 (2.25 mm beyond today's 78), which this proposal does not do.
- **The standoffs can move outward.** Clearance rule used: standoff envelope (head radius 2.5 mm, the floorplan's `FASTENER_HEAD_R`) at r >= 29 mm from the axis = ring outer 27.5 + 1.5 mm for ring position, adhesive fillet and assembly. Minimum change: tab 64 x 32 -> **67.5 x 32.0 mm (u 77.5 to 145.0, v 37.0 to 69.0: 0.5 mm more on the -u side, 3.0 mm on the +u side)** and three standoffs at

| standoff | centre (u, v) | distance to axis | head nearest to axis | clearance to the ring | wall to tab edge |
|---|---|---|---|---|---|
| 1 | (80.85, 40.35) | 31.776 mm | 29.276 mm | 1.776 mm | 2.0 mm |
| 2 | (80.85, 65.65) | 31.776 mm | 29.276 mm | 1.776 mm | 2.0 mm |
| 3 | (141.65, 53.0) | 31.65 mm | 29.15 mm | 1.65 mm | 2.0 mm |

 Walls are the floorplan's 2 mm (hole r 1.35). The Hall point (110, 53) lies inside the support triangle, so three standoffs stay statically determinate and the sensor is supported on all sides; J9 stays at (82, 53) with 2.375 mm to the new tab edge and 4.8 mm from the nearer holes (floorplan rules: >= 1 mm). The standoffs sit at 31.7 to 31.8 mm from the axis instead of 28 to 29: the supported spans grow about 10 %, which matters for the 5.0 +/- 0.2 mm face-to-die gap only through the tab's flatness (specify bow <= 0.1 mm over the 60 mm and check it; not computed here). The +3 mm beyond u = 142 needs an **enclosure check** (nothing on the UI board is there; the enclosure was not read). The steel keep-out (r 25) is untouched, the fasteners stay non-magnetic and insulating, and the knob (envelope r 28, in front of the fascia) is not involved.
- **If they cannot move:** cut the ring around them (5.10): acceptable for the angle, costs five detents.
- **Even with the standoffs moved, A0 does not become a detent** (5.8): option (b) is the route for the detent.


## 7. Limitations

- **The B-H curve is representative, not measured**, and the hysteresis is a play model with an assumed Hc (160 and 400 A/m): the verdict's only soft spot. A measured normal-magnetisation and minor-loop curve of the actual 1010 lot (as cold-rolled or annealed) at 20 and 176 C would settle D; the 176 C steel behaviour is assumed (H x1.3, J_s x0.97).
- **Mesh:** the ring-induced field is not mesh-converged (322 / 307 / 355 uT); handled by the 1.17 factor, which is an extrapolation of one halving, not a bound. Point collocation with uniform-M cells is first-order near the thin plate's edges.
- **Idealised ring (A0):** perfect teeth and pitch, no tooth variation, no thickness, flatness or concentricity tolerance beyond the 0.1 mm ring offset, no mounting features, notches or fasteners, no adhesive, no bracket steel, no steel in the standoffs or J9, the 5052 fascia treated as vacuum (no eddy currents at DC, none computed at 31 to 55 kHz). The angle error depends on the steel volume and position; a mounted ring will differ and needs the A1 installed-geometry model.
- **The coil field:** the existing coil allowance (0.173 deg worst) was computed without the ring. A 1 mm steel ring 26 mm from the die in the 31 to 60 kHz field (45 A) concentrates AC flux, heats (eddy and hysteresis loss) and distorts the stray field at the die; this is **not modelled** and the linear sum with the old allowance (5.7) is not a result for the combined case. It needs its own eddy-current solve before any acceptance.
- **Tilt and ring offset** are assumptions (1 deg about u and v with the pivot at the sensing magnet's near face; 0.1 mm ring offset): the request listed face gap, lateral offset, push and temperature. Larger tilt scales the first-harmonic ring term roughly linearly (0.010 deg per degree of tilt).
- **Sensor:** offset drift and the TMAG5170's own angle error (+/-0.4 deg at 25 C, 50 mT range, calibratable) are not modelled; X/Y gain drift is the ui_calcs allowance. Noise is not simulated.
- **Interpolation:** the saturating solves on asymmetric units (2 to 4 deg) and the hysteresis runs (0.5 deg) are interpolated to 0.25 deg as increments over the linear / saturating reference; linear materials and the ideal unit are direct. The hysteresis result is for the ideal unit only (one tooth pitch in the periodic regime); in the as-built unit it is assumed additive.
- **Torque and pull** are energy-method model numbers (cross-checked, but with a representative curve and no loss); a measurement is needed for the feel target, though the gap to the spec is about four decades.
- **Not done:** magnetisation of the 5052 and of the sensor tab FR-4 (nonmagnetic), the knob's own steel (none assumed), magnet-to-magnet detents (option (b) is not modelled here), temperature dependence of the magnets other than Br.


## 8. Files and rerun

| File | What |
|---|---|
| `ring_study.py` | the whole study (deterministic): controls, sweeps, calibration, analysis, plots; asserts controls 1, 2, 4, 5, 6 |
| `results.json` | every number in this README (`headline` first), criteria stated before the run, controls, per-case tables, calibration parameters, convergence, refinement, geometry, verdict |
| `plots/` | `raw_field_vs_angle.png`, `angle_error_vs_angle.png`, `calibrated_residual.png`, `material_sensitivity.png`, `hysteresis.png`, `steel_flux_density.png`, `mesh_convergence.png` |
| `raw/*.csv` | Bx, By, Bz (mT), the ring's own contribution (uT) and the uncalibrated error at 0.25 deg steps, full turn, eight key cases |
| `requirements.txt` | pip packages (numpy, scipy, matplotlib, magpylib, numba, threadpoolctl; Python 3.12) |

Rerun (from `zapote/ui-board/evidence/knob-ring`; the venv lives outside the repo):

```sh
python3 -m venv /private/tmp/venv-knob && /private/tmp/venv-knob/bin/pip install -r requirements.txt
/private/tmp/venv-knob/bin/python ring_study.py --workers 5 --cache-dir /private/tmp/knob-ring-cache   # full study, about 1.5 h on 5 cores (sweeps 1 h 25, convergence 25 min)
/private/tmp/venv-knob/bin/python ring_study.py --tiny --skip-convergence --out /private/tmp/knob-ring-tiny   # 1 min plumbing check on coarse grids, not the study
```

`--cache-dir` keeps one pickle per finished sweep so an interrupted run resumes; delete it to recompute everything. The inputs read from the unit are `tools/ui_calcs.py` (magnet closed form, stray-field and sensor-thermal numbers) and `tools/floorplan.py` (constants checked in control 6); the request files were read-only and not modified. The geometry reproduces `rim_ring_screen.py`'s A0 data (ring, magnets, Hall point, standoff and J9 envelopes).


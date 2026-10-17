# Coil stray-field pickup in native-21's sense loops (stage 13b = stage 14 in these loops)

**Bottom line: no loop needs a fix.**
- **Shunt OCP: bounded.**
  - The model shift is ≤ 0.6 A at any instant.
  - At the tank-current peak, where a nuisance trip would happen, it is ≤ 0.25 A.
  - The harshest stack still leaves 0.3 A of the 3.32 A margin to the ≥ 44 A requirement. That stack is: every sub-loop added in magnitude, field +50 %, and an arbitrary pan phase.
  - One optional, cheap copper change halves the Kelvin loop: move KELVIN_N's last 30 mm under the KELVIN_P pour.
- **CT detector: negligible.** The worst case is ≤ 0.35 A of tank current and ≤ 0.6° (57 ns) of zero-cross shift.
- **LINE_ZC: negligible.** Errors are at the nA, ns and tens-of-mV level, against mA, a ±250 µs allocation and the Schmitt hysteresis.

All numbers are **peak EMF at 31.1 A peak tank current (22 A rms)**, scaled linearly from the map's 45 A peak (× 0.691), at 31 kHz.

## 1. Method (scripts beside this file)
| step | script | notes |
|---|---|---|
| Field profiles from the map CSV | `field.py` | The map is axisymmetric about board (141, −25); the residual from a pure f(r) is 0.01 µT. Bz changes sign at r = 126.5 mm (pan) and 129 mm (no pan). Br's sign relative to Bz is fixed by div B = 0 between the two z planes (correlation 0.99995). |
| **Phase** of the field vs the tank current | `field_phase.py` | Re-solves study 06's two map cases with its own `fem_axi`/`study` modules, imported read-only. Output goes only to `field_phase.json` here. Magnitudes reproduce the CSV, e.g. 66.0 µT at (140, 0). **With the pan, B lags the tank current by 21°. With no pan, it lags by 1–2°.** The no-pan Bz has a second null at r ≈ 215 mm, which the CSV's magnitude-only data cannot show, so the phasor (FEM) results are used for the verdicts. |
| Loop geometry | `loops.py`, `run_loops.py` | Each loop is a closed 3-D polyline built from `s13b/copper-dump.json`: Dijkstra over each net's tracks and vias, with pad positions from KiCad 10 (`dump_fp.py` → `fp.json`). Component bodies, pour and plane closures are explicit and named per loop. |
| Flux | `loops.py:flux` | Flux = ∮ A·dl with A_φ(r, z) = A₀(r) − (z − z₀)·Br(r). One integral therefore captures both the planar (Bz) pickup and the layer-change (Br) pickup. Layer z: F 26.8, In1 −0.47, In2 −1.03, B −1.50 mm. `selftest.py` checks this against direct integration for a planar rectangle and a vertical strip; both match to 0.1 %. EMF = jωΦ, and phase is referenced to i_tank. |
| OCP combination | `ocp_combine.py` | Combines the loops into an equivalent shunt-current trip shift, with phase, image-return variants and a section breakdown. |
| Requirement check, ±50 % | `sensitivity.py` | |

Plots: `loops_*.png` (the loop polygons), `kelvin_in1.png` (In1 pours with the Kelvin pair) and `ct_in2.png`. Logs: `run_loops.log`, `sensitivity.log`. JSON: `loops_result.json`, `ocp_combine.json`, `sensitivity.json`.

To rerun: `python3 field_phase.py && python3 run_loops.py && python3 ocp_combine.py && python3 sensitivity.py`. `fp.json` needs KiCad's python: `dump_fp.py <pcb> fp.json <refs>`.

## 2. Loops: geometry, area and EMF
"Pan" is the baseline. "No pan" is the envelope, which normal firmware does not run. Area is the projected polygon area, with closures as stated.

| loop (signal / return, layers) | area mm² | centroid (x, y) | EMF pan / no pan, mV pk |
|---|---:|---|---:|
| **OCP Kelvin pair**. R5.3 → KELVIN_N (141.7 mm: F → In1 → In2 → In1 run → F at R33.2) against KELVIN_P (118.3 mm of trace, then the In1 KELVIN_P pour) back to R5.2. Same-layer pair at 0.8–0.9 mm pitch. **A:** pour closure straight to R35.2. | 213.7 | (64, 40) | **1.14 / 2.75** |
| Same loop, **B:** pour return hugging KELVIN_N | 136.4 | (67, 42) | 0.70 / 1.70 |
| Kelvin A by section: R5 breakout / pair run (y 31 → x 107) / cluster end | 29.7 / 67.5 / 116.1 | — | 0.22 / 0.28 / **0.64** (pan) |
| OCP_NODE: U6.3 → trace → C30, closed via the KELVIN_P pour to U6.2 | 27.8 | (108, 62) | 0.35 / 0.79 |
| OCP_THRESH: U6.4 → F/B/F trace → C31, closed via the pour to U6.2 | 36.7 | (108, 64) | 0.07 / 0.19. The Bz and Br parts are 0.22 and 0.15 and partly cancel. |
| REF25: U5.1 → R32/R34, closed via the pour to U5.2 | 6–10 | (113, 64) | 0.05 / 0.13 |
| **CT comparator loop (U12, ZC):** U12.3 → CT_SENSE_MON (118 mm, F then B) → R42 → CT_S1 → R39 → CT_S2 (112 mm, B then F, In1 at the end) → U12.4 | 159.5 | (85, 130) | 0.05 / 0.001. The Bz and Br parts are each 0.5 (pan) and 1.1 (no pan) and cancel, because the two lines swap F/B at x ≈ 90, which acts as a twist. |
| CT comparator loop (U10/U11, over-current): as above to C43, then the SELV_GND plane to the R44/R46 reference | 172.2 | (71, 131) | 0.05 / 0.01 |
| CT_MON to J4.14: the analog chain above plus 61 mm of CT_MON, returned at J4.15. The plane closure is drawn straight, which overstates the area. | 791.7 | (72, 136) | 0.79 / 1.07 |
| CT secondary → burden: T1.3 → R39 → T1.4 | 40.1 | (134, 127) | 0.13 / 0.28 |
| CT_ZC (digital) to J4.13 | 374.5 | (35, 156) | 0.21 / 0.04 |
| **LINE_ZC input string**: L_FILT → R67 → R68 → U36 LED → R69 → R70 → N_FILT | 94.1 | (233, 98) | 0.33 / 0.69 |
| LINE_ZC_RAW: U36.4 → 272 mm F/B route → U24.2. Return drawn **straight** across the plane, which is an upper bound. | 3652 | (93, 127) | 8.8 / 17.6 |
| LINE_ZC_RAW with the return **under the trace** on the In2 SELV_GND plane, which is realistic | ~0 planar | — | 0.37 / 0.80 |
| LINE_ZC out (digital) to J4.16 | 67.6 | (36, 162) | 0.20 / 0.64 |

The CSV-map results and the FEM-phasor results agree to 0.1 % everywhere except beyond r ≈ 215 mm in the no-pan case, where the second null sits: CT_MON and CT_ZC are near J4.

## 3. Protection error

### Shunt OCP (R5 1 mΩ, U6 TLV3201)
**Transfer.**
- OCP_NODE = 1.25 V + 0.5·V(KELVIN_N), so INP moves 0.5 mV per amp.
- The node filter is 5 k‖100 pF, with its pole at 318 kHz: |H(31 kHz)| = 0.995, so it does not attenuate the pickup.
- C31 (1 nF, 6.0 k, 26 kHz) only filters EMF that enters ahead of C31. The local OCP_THRESH loop is taken from C31 to the pin, unfiltered.

**Equivalent current shift.** With the loop orientations in `ocp_combine.py`:

ΔI = 1.03·E_Kelvin − 2·E_node + 2·E_thresh + 0.03·E_ref25 (A per mV).

The Kelvin sensitivity is ≈ 1 A per mV; the 1.03 used here is the same factor as the kelvin/ README's −1.03 A/mV at R35.2.

| case | \|ΔI\| (model) | ΔI at the tank-current peak | sub-loops added in magnitude |
|---|---:|---:|---:|
| pan, closure A, cluster as drawn | 0.62 A | 0.24 A | 2.00 A |
| pan, closure B, image returns | 0.03 A | 0.03 A | 1.42 A |
| no pan, A, as drawn | 1.64 A | 0.08 A | 4.80 A |
| no pan, B, image returns | 0.24 A | 0.04 A | 3.28 A |

**Phase decides it.**
- A nuisance trip happens at the tank-current peak: the bus current is |i_tank| during conduction, and its peak is the tank peak.
- The pickup is jωB·A. With no pan, B is in phase with i_tank (≤ 2°), so the EMF is in **quadrature**. At the peak it contributes only E²/(2·I_pk): 0.21 A even at +50 %, with every sub-loop added in magnitude.
- With the pan, B lags 21°, so sin 21° = 0.36 of the EMF lands on the peak.
- The bridge rectifies the shunt current but not the EMF. The in-phase part therefore **adds at one of the two peaks in every cycle**: one polarity raises the apparent current, the other lowers it.

Against the requirement, at 31.1 A peak, the low corner is **47.32 A** and the required minimum is ≥ 44 A, so the static margin is 3.32 A:

| case | shift at the peak | margin left |
|---|---:|---:|
| model, pan, +50 % | 0.37 A | 2.95 A |
| sub-loops in magnitude, FEM phase, +50 %, pan / no pan | 1.28 / 1.16 A | ≥ 2.0 A |
| sub-loops in magnitude, **arbitrary pan phase** (fully in phase), +50 % | 3.00 A | **0.32 A** |

The no-pan "any phase" row in `sensitivity.log` (7.2 A) is not physical: with no lossy load, the field cannot shift its phase. It is listed only for completeness.

**Fault trip (shoot-through or tank OC at any instant).** The shift is ±|ΔI|: at most 1.6 A (model) and at most 7.2 A (no-pan stack, +50 %) on the 97.77 A upper corner. Against D-31's 330 A turn-off capability, and a shoot-through rise of about 9 A/ns, that is less than 1 ns of trip delay. **Negligible.**

**Verdict: bounded.** The OCP needs no fix: the margin survives every stack, and only the most pessimistic combination gets close.

**Optional improvement** at the next copper touch:
- **What dominates.** 56 % of the Kelvin EMF comes from the **cluster-end hook**, which is 116 mm². KELVIN_N runs down x = 106.6 and then 13 mm east along y = 72.4 to R33.2. Its return enters the KELVIN_P pour at (107.6, 53.5).
- **The change.** Drop KELVIN_N to In2 directly under the In1 KELVIN_P pour for that run, or place R33 at the pour entry. Either collapses the hook to about 0. The Kelvin EMF falls from 1.14 / 2.75 to **0.50 / 1.21 mV**: −56 %, or −1.6 A in the no-pan magnitude stack.
- **Also worth doing.** Place C30 and C31 at U6's pins 3 and 4. Today OCP_NODE crosses the cluster for 15 mm (28 mm²) before its 100 pF. Moving the caps removes most of the node and threshold loop terms, up to 1.6 A in the stack.

The R5 breakout (30 mm²) and the run itself (0.85 mm pitch, 68 mm²) are already tight.

### CT detector (T1 1:100, R39 1.5 Ω, 15 mV/A)
- **Over-current comparators U10/U11.** The model gives ≤ 0.05 mV, because the F/B swap acts as a twist. The worst case is 1.5 × (|Bz part| + 2·|Br part|), which takes the Br parts as doubled at the top-side plane surface. It comes to ≤ 5.2 mV, or **≤ 0.35 A** of tank current, against the 50.56–60.01 A band. Like the OCP, the error is in quadrature at the trip instant with no pan, and 0.36 × with the pan. **Negligible.**
- **CT_ZC (U12, sense vs CT_S2).** The zero crossing is where the quadrature EMF peaks. The shift is Δθ = E/(15 mV/A · I_pk); the ratio is independent of current because both scale with i_tank. The model gives about 0.006°; the worst case is **0.63° = 57 ns**. **Negligible.**
- **CT secondary → burden (0.13–0.28 mV).** This loop is in series with a current source, so only R_b/|R_b + jωL_m| of it reaches the burden. Even taken in full, it is 0.03 A. **Negligible.**
- **CT_MON to J4.**
  - The worst case is 2.8 mV against 466 mV at 31 A: 0.6 % of amplitude, 0.34°. **Negligible on the board.**
  - The controller harness loop beyond J4 is not in this model. Study 06 change 9 already asks for twisted SELV pairs there.
  - CT_ZC and LINE_ZC are 3.3 V push-pull digital signals: ≤ 1.2 mV of pickup. **Negligible.**

### LINE_ZC (U36 VOL628A, 4 × 16.5 k string, 33 k pull-up, U24 Schmitt)
- **Input string.** 1.0 mV worst case, in series with 120 V rms and 66 k: 16 nA, against about 2.6 mA peak of LED current. At the line slew of 64 V/ms, the zero-cross shift is 16 ns. **Negligible.**
- **LINE_ZC_RAW (272 mm route).**
  - With the realistic under-trace plane return: 0.4–1.2 mV.
  - With the straight-closure upper bound: 28 mV.
  - Both are far below the LVC1G17's hysteresis of hundreds of mV, so there is no chatter. On a ~66 mV/µs opto edge, 28 mV moves the edge by ≤ 0.43 µs, against the ±250 µs allocation. **Negligible.**

## 4. Sensitivity

**±50 % field (ferrite bars).** Every EMF scales linearly. All the rows above already carry the +50 % case. Every verdict holds at +50 %; the OCP is the only one that gets close, and only in the stacked arbitrary-phase row.

**Air-core coil (2–5×, from study 06).** This is outside the ±50 %.
- The OCP model shift at the peak would be 0.5–1.3 A (pan), which still meets the requirement.
- The stacked bound would not.
- Specifying the ferrite (study 06 change 3) is therefore also an OCP-margin item.

**Tank current.** The map's own 45 A peak is × 1.45 on everything here. The pan model shift at the peak would be 0.36 A.

**Solid planes (no board copper in the model).**
- The thin-sheet screening number is ωμ₀σtL/2. For 61 µm inner copper at 31 kHz it is about 43 for a 100 mm plane.
- So the large planes expel Bz: In2 BUS_P under the whole hot region, In1 HV_RET, F SW_A, B SW_B, and In1 V3V3 with In2 SELV_GND under the SELV region.
- The Kelvin pair runs on In1, sandwiched between these layers. The CT and ZC lines run over or under the SELV planes.
- The free-field planar (Bz) numbers are therefore an **upper bound** for interior runs. The realistic Bz pickup is likely a fraction of it.
- **Two exceptions:**
  1. Flux expelled from a plane crowds at its edges and slots, locally up to about 2×. The Kelvin run follows the In1 HV_RET edge along y ≈ 43, but In2 BUS_P is continuous beneath it.
  2. Tangential Br on the coil-facing (F.Cu) side of a plane rises up to 2×. That is why the CT worst case doubles the Br term.

  Neither changes a verdict.

**Phase model.** The 21° pan lag comes from study 06's linear steel pan (μ = 100). A real pan is non-linear, and its phase will differ. That is why the pan arbitrary-phase row is kept, and it passes.

## 5. Limits
- **Pour and plane closures.** These are geometric choices: straight versus hugging (A vs B) and drawn versus image returns. Both are reported, and the bounds add sub-loops in magnitude.
- **Board copper.** Real eddy-current redistribution in the board copper is not solved here; it needs a 3-D solve or a bench measurement.
- **Not covered:**
  - the shunt's own power-loop di/dt coupling into the R5 breakout. This is board self-field, not coil field, and it is outside this task;
  - component-internal pickup. T1 is a toroid; the opto and the ICs are small.
- **Bench confirmation.**
  - Run the coil at 22 A rms with a pan, with the bridge driven from an isolated source if possible.
  - Record U6 INP−INN differentially, CT_SENSE_MON−CT_S2 and LINE_ZC_RAW.
  - Expected at 31 kHz on U6 INP−INN: about 0.3 mV pk differential (model, ΔI ≈ 0.6 A), and ≤ 2.4 mV at the stacked bound.
  - Expected on the CT pair: ≤ 0.1 mV.
- **Scope.** Read-only on the repo. Nothing was written outside this folder; study 06's modules were imported with bytecode writing off.

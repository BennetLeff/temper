Identity check: `shasum -a 256 /Users/bennet/Desktop/temper/worktrees/hw-baseline-guard/hardware/native21-stage19b/section.kicad_pcb` returned `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662`, which equals the pinned hash in `hardware/CURRENT.tsv` line 55 and the task statement. `elec/src/power_stage_120v.ato` (sha `94260996...19142`) and `elec/src/parts.ato` (sha `017fae35...af08`) in this worktree are byte-identical to the pinned `source/elec/src/` copies (shasum of both pairs, verified).

# Trilogy of Magnetics rubric (MAG-01..29) scored against native-21 stage 19b

Rubric: `/Users/bennet/.codex/worktrees/pcb-resource-rubrics-oct13/temper/docs/hardware/pcb-reference-rubrics-2026-10-13/trilogy-magnetics.md`. Its text names stage15b; the target here is stage 19b (the rubric's ato/T1/L1 descriptions still hold). Scoring contract from the rubric and `README.md`/`tradeoffs.md`: 0 demonstrated failure, 1 evidenced concern, 2 supported but validation pending, 3 verified margin (needs measurement), U unknown, NA with reason. No hardware exists, so no 3 is possible. Paths below are relative to `zapote/power-stage-120v/` unless absolute. Magnetics on this board: L1 (TDK B82726S2203A020 CM choke), T1 (Coilcraft CST3015-100ED CT), PS1/PS2 (Mean Well IRM-20 modules), U41/U42 (RECOM R24C2T25 bias modules); the coil and the inlet filter module are off-board but define the tank and the filter.

## Tally

| Score | Count | IDs |
|---|---:|---|
| 3 | 0 | none (no measurements exist) |
| 2 | 19 | 01 02 03 04 05 07 10 12 13 14 15 16 18 21 22 24 25 26 29 |
| 1 | 4 | 09 17 23 28 |
| 0 | 0 | none |
| U | 5 | 06 08 11 19 27 |
| NA | 1 | 20 |

## Findings (every 0/1 and every U)

**MAG-09 (1): neighboring heat and thermal margin for L1, PS1, PS2.** Mechanism: the integrated thermal model (`validation-results/04-board-current-thermal/round5-native21/b3-convergence/`) heats L1 with 1.2287 W (`inputs/heat_der14.json`; implies 11.68 A through 2 x 4.5 mohm, command C5) while the owner-approved envelope is 15 A on the NEMA plug (`DECISIONS.md:168`), for which the repo's own loss budget gives 2.025 W typical and 2.700 W with the 6 mohm hot planning value (`validation-results/03-loss-thermal-budget/round3/outputs/losses.csv:34`, `validation-results/01-switching-parasitics/round17/delegation/out-D22/PARTS.md:34`). Linear scaling of the model's 15.1 K/W (reviewer calc, C5) puts L1 at about 81 to 91 C at 50 C ambient versus an unverified 125 C limit and a 60 C-ambient rating basis (`PARTS.md:22`). PS1/PS2 modeled case 86.2/98.2 C against an 85 C *ambient* rating (`b3-convergence/README.md:74-75`, margins -1.3 K and -13.4 K); the study itself says this can only be judged against measured local air. Also the TDK datasheet was not retrievable, so the L1/IRM package paths are ASSUMED (`thermal_body.py:97,102`). Action: rerun the b3 model with L1 at 2.7 W (15 A, 6 mohm); add local-air thermocouples next to PS1, PS2 and L1 to the bench IR list (`b3-convergence/README.md` sec 5 items 4 and 9) and make them a gate for the 22 -> 28 A raise; obtain the IRM-20 derating curve and apply it at the measured air temperature; if PS2 (at (163.7, 3.6)) is over its derated limit, lower its load or add airflow.

**MAG-17 (1): shunt-capacitor (Y) return path.** Mechanism: C3/C4 (2.2 nF Y1, `elec/src/power_stage_120v.ato:346-351`) sit at (225, 102.8)/(225, 109.1), about 72 mm from L1 at (232, 31), and the only PE route on the board is a ~96 mm, 0.4 mm-wide F.Cu track to J6 at (150.6, 134.5) (appendix C4). That trace is about 125 nH by the thin-strip formula, so each Y cap is series-resonant near 9.6 MHz and inductive above; the board filter alone is only 1.0 dB at 26 MHz (`validation-results/07-conducted-emi/s19b/README.md` sec 5 note) and the s19b model carries only 15 nH ESL plus a 100 nH bond and is not trusted above 0.5 to 3 MHz (sec 3, sec 8). The sensitivity rows 'Y-cap ESL x3' and 'PE bond 200 nH' (sec 6) show no change below 5 MHz, which is consistent but does not test this path. Action: add the 125 nH PE-track series inductance to `emi_s19b.py` and rerun the 5-30 MHz rows; at the re-spin place the spare Y2 pair the study already recommends (`DECISIONS.md:806` item 5) adjacent to L1 and shorten or widen the PE track; confirm with BENCH steps B3 and B5.

**MAG-23 (1): tank device stress (resonant film bank).** Mechanism: hardware is sized for 28 A (envelope peak 59.2 A, `DECISIONS.md:527`), but the five-part B32654 bank runs at 1.05x the TDK 85 C RMS-current curve at 26 A and 1.12x at 28 A (`validation-results/05-resonant-tank-envelope/round6-full-power/README.md:69`; 0.89x at 22 A, `DECISIONS.md:354-375`), and 0.40-0.45 uF alternatives reach 1.19-1.23x (`README.md:54`). Inputs are the ASSUMED coil/pan basis and a digitized curve. The multi-fault 1702 V pk case (1.064 x V_R, `owner-outbox/2026-10-12.md` section 2, TDK question unsent) is a third fault and is held below 1600 V by the 35 kHz floor, so it is not scored against. Containment exists: firmware ships 22 A and raises only after a bank hot-spot rise <= 20 K gate. Action: keep 28 A locked behind that gate; evaluate a sixth parallel cap, bank airflow, or an 80 uH coil that lowers circulating current (round6 `README.md:113,124`); send the TDK inquiry.

**MAG-28 (1): coil stray field into the R5 Kelvin / OCP path.** Mechanism: `validation-results/02-protection-timing/coil-pickup/PICKUP.md:12` states all figures are 'peak EMF at 31.1 A peak tank current (22 A rms) ... at 31 kHz' on stage-13b copper; `DECISIONS.md:502-508` carries them (0.25 A model shift, 3.0 A for the most pessimistic stack). The envelope has since moved to 59.2 A peak at 35-60 kHz and R5/Kelvin was rerouted at stage 17. EMF = jw*flux scales with both, so linear scaling (command C6) is x1.90 current and x1.93 frequency: nominal 0.25 A becomes about 0.9 A and the stacked bound 3.0 A becomes about 11 A, against 8.5 A between the 59.17 A normal peak and the 67.72 A shunt band low corner (`DECISIONS.md:527-530`, `COIL-SPEC-ELECTRICAL.md` row 7). Nominal is harmless; the arbitrary-phase +50 % stack is not bounded. This is a reviewer extrapolation, not a committed result. Action: rerun `field_phase.py`, `run_loops.py`, `ocp_combine.py`, `sensitivity.py` on the 19b copper at 59.2 A pk and 60 kHz (needs KiCad python for `fp.json`); adopt the optional KELVIN_N-under-KELVIN_P pour move (`DECISIONS.md:508`) if the stack exceeds about 4 A.

**MAG-06 (U): bias-dependent L1 inductance/impedance.** Evidence missing: Lcm(I,T) and leakage Ldm(I,T) at 15 A hot and at rectifier-peak/startup bias, and the same for the unspecified module DM inductors. TDK page 4 only gives <10 % L drop at rated current at 20 C and page 5 a typical curve for parallel windings at 20 C (`validation-results/07-conducted-emi/sources/tdk-b82726s2203a020.json`; `out-D22/PARTS.md:34-36` says no hot leakage-vs-peak-current curve exists). The -30 % sensitivity keeps margins >= 6.5 dB (s19b sec 6) but is not bias data. Action: LCR-with-DC-bias sweep of an L1 sample or a TDK Z(f,I,T) request.

**MAG-08 (U): core loss with the real flux waveform.** Evidence missing: coil ferrite B_pk and loss (enclosure `coil_thermal.py`, 'ferrite loss is added on top by the enclosure', `COIL-SPEC-ELECTRICAL.md:225,257`, not in this tree) and any L1 core-loss estimate (`losses.csv:34` is copper only). T1 alone is covered (20.8 uV*s of 638, 30.7x, `02-protection-timing/stage15-28A/out/fault_check.json`). Action: import the enclosure ferrite loss output at 28 A / 59.2 A pk with N87/N97 data, and measure L1 case temperature at 15 A.

**MAG-11 (U): insulation basis of T1 and coil.** Evidence missing: Coilcraft working voltage, CTI/material group, PD test and 35-60 kHz rating for CST3015-100ED (`validation-results/08-manufacturing-package/native-21/stage18-res-a-creepage/README.md:87`; `ORACLE-ANSWER.md:162-171`: 99 V rms is 'not a bound under bus pumping' and T1 'cannot be mapped onto PD3'); Coilcraft question drafted but unsent (`owner-outbox/2026-10-12.md` section 9); coil 12b levels and PS1 clearance basis are open certifier questions (sections 6, 8, 10). Action: send the Coilcraft draft; obtain the certifier ruling on PD2/PD3 and IEC 60664-4 above 30 kHz; measure the SW_A voltage T1 actually sees (bench).

**MAG-19 (U): X/Y capacitor and PE system.** Evidence missing: an explicit leakage/touch-current allocation (board Y 2 x 2.2 nF, module Y 2 x 6.9 nF, three IRM modules, blower supply, single-fault PE-open), stated as still required in `out-D22/PARTS.md` ('Bleed, leakage and thermal allocation') and `s19b/README.md` sec 9.2 ('touch-current budget is the real cap'); IRM isolation capacitance is 'not in any repo datasheet' (sec 3). Action: write the allocation with IRM-20/60 datasheet leakage; measure touch current on the assembled unit.

**MAG-27 (U): leakage versus interwinding capacitance.** Evidence missing: T1 interwinding capacitance and leakage inductance (listed as bench items in `02-protection-timing/README.md:57` and `ORACLE-ANSWER.md:164`), IRM-20 isolation capacitance, and an in-circuit CM current = C * dV/dt for T1 on the SW_A edge. RECOM U41/U42 are bounded (3.5 pF max, `DECISIONS.md:447`) but the barrier-coupled charge is not yet in the edge campaign (`DECISIONS.md:428-430`), and `s19b/README.md` sec 3 still lists 'F6 bias transformers' that stage 14 replaced with the RECOM modules (stale input). Action: LCR-measure a T1 sample primary-to-secondary; add the T1/IRM/RECOM Cps paths to the s19b CM model and the rail campaign.

**Non-scored observations worth keeping.** (a) `s19b/README.md` line 4 still reads 'Verdict: INCONCLUSIVE' while `results.json` (`verdict` PASS, nominal 10.48 dB, minimum sensitivity 6.50 dB) and `DECISIONS.md:792` say PASS after the 2026-10-13 update; fix the header. (b) The board filter cannot pass without the off-board inlet module (board-only -39 dB, README sec 6), whose DM inductors are 'not specified' (sec 8); module definition is a prerequisite for any MAG-13..15 upgrade. (c) The CT_MON top-corner headroom to the 2.85 V ADC limit is 0.059 V (3.9 A) at 76.09 A (`fault_check.json` ct/sense; C2); the trip uses comparators, but any firmware use of CT_MON near the top corner clips.

## Per-criterion rationale

**MAG-01 (2).** `power_stage_120v.ato:338-342` puts L1 in both mains conductors (windings 1-4, 2-3, `parts.ato:90-102`); `:421-426` places the T1 primary on SW_A to COIL_FEED with the comment that it sits on the switch node; PS1/PS2 take `L_FILT` / `TCO_L` (`:466-489`). Roles are mapped and separated (CM choke, CT, module magnetics, off-board coil). No measured current paths in fault or start, so not 3.

**MAG-02 (2).** The envelope is explicit: line <=15 A (`DECISIONS.md:168`), tank 22 A shipped / 28 A hardware, 59.2 A peak, OCP floor >=64 A, RES_A 297 V rms (`:483-487`, `:509-532`). The pan and coil basis is ASSUMED (`COIL-SPEC-ELECTRICAL.md:7`; item 10 title), so margin cannot be claimed.

**MAG-03 (2).** The s19b table separates CM and DM per band (`s19b/README.md` sec 5): 9-150 kHz is CM at 60 kHz (7.8 dB QP at 28 A), above 150 kHz is DM at 150 kHz (22.3 dB AV). Cures are modeled. No measured spectra.

**MAG-04 (2).** Three passbands are considered, but the LINE_ZC phase shift through the filter and the ~16 kHz resonance damping are still open (`DECISIONS.md:478`). CT passband: corner R/(2*pi*L) = 3 ohm / 3.2 mH = 149 Hz, 0.24 deg or 19 ns at 35 kHz (C2).

**MAG-05 (2).** L1 rating (20 A, 4.5 mohm, 60 C basis) is recorded from dated TDK page 4 and operated at <=15 A; T1 at 0.318 of 88 A. Saturation and hot definitions are not in the repo (PDF hash only), hence not 3.

**MAG-06 (U).** See Findings.

**MAG-07 (2).** Coil R_ac 113 to 136 mohm at 40 kHz (`coil-litz/out-28A.txt`) with proximity from the FEM winding field, against an acceptance limit of 0.23 ohm hot; L1 is DC-only I2R at line frequency. No hot AC measurement.

**MAG-08 (U).** See Findings.

**MAG-09 (1).** See Findings.

**MAG-10 (2).** L1 is modeled with winding C and a TDK curve fit; reliable to about 0.5 MHz, with 150-500 kHz margin >= 10 dB in every declared sensitivity. Not measured installed.

**MAG-11 (U).** See Findings.

**MAG-12 (2).** `FOOTPRINTS.md:14,16` mark the L1 and T1 footprints verified against dated drawings; PDFs are hash-only; the T1 3D model is 'provisional'; `REVIEW-2026-10-08.md:125` records zero L1 stock at survey. Procurement and fit sample remain open.

**MAG-13 (2).** Installed-termination MNA model with LISN, controls reproducing D-22 to 1e-9 dB, sensitivity grid; results PASS with 6.5 dB minimum. Unmeasured and module-dependent.

**MAG-14 (2).** A damping branch exists and was modeled; closed-loop interaction with the rectified-bus tank, inrush and the 20 s burst mode is explicitly untested (`s19b/README.md` sec 8).

**MAG-15 (2).** Both modes modeled with exact-part values (Lcm 1.6 mH, leakage 18 uH, 4.5 mohm). DM depends on the module; no mounted test.

**MAG-16 (2).** Reviewer geometry analysis (appendix C3): unfiltered/filtered overlap is 0.3 pF, same-layer gaps are 3.2 to 3.6 mm, and unfiltered copper has no overlap with any switching, bus or coil copper on other layers. Inlet module and chassis routing are not designed, so board-only evidence stops at 2.

**MAG-17 (1).** See Findings.

**MAG-18 (2).** Same geometry data; L1 is on the board's mains corner, 65 mm or more from LINE_ZC parts and about 100 mm from the coil studs; input pins 1,2 and output pins 3,4 are on opposite rows. No scan or A/B.

**MAG-19 (U).** See Findings.

**MAG-20 (NA).** No ferrite bead, cable ferrite or bead part exists in the pinned netlist (only L1 and T1 magnetics, appendix C1). Becomes applicable if a bead is added.

**MAG-21 (2).** Core choice is from the exact TDK curve and emission-band modeling, with a 3.2 mH choke held as a modeled reserve. No immunity band identified (not claimed) and no installed measurement.

**MAG-22 (2).** FEM and pan-class Monte Carlo model plus a defined loaded-inductance acceptance test (`COIL-SPEC-ELECTRICAL.md` rows 1-3b); every coil/pan number is ASSUMED and no coil has been wound or swept. RFQ not yet sent.

**MAG-23 (1).** See Findings. Normal-use RES_A is 297 V rms / 656 V pk (362 V rms / 791 V pk at trip), within the stated coil insulation spec but certifier-pending.

**MAG-24 (2).** 270 x 0.10 mm Litz chosen over 420 x 0.08 mm with a proximity-aware model (skin depth 0.379 mm at 100 C); winding model supports selection, hot R_ac and thermography are acceptance tests not yet possible.

**MAG-25 (2).** Burden 1.5 ohm (DCR 1.5 ohm) gives 15 mV/A, flux 20.8 uV*s of 638 at the top trip corner, 1.65 +- V range clipped by BAS116H clamps. Calibrated waveform comparison and CT leakage/Cps above 100 kHz are bench items.

**MAG-26 (2).** Reset is trivially safe (series resonant capacitor, 46.3 uV*s at 160 A / 33 kHz). The open-secondary hazard that forced the burden onto the board is closed on 19b (`06-controller-interface/README.md:164-170`). Residual R39-open case is uncommitted; my estimate is 26.9 V pk (59.17 A) to 34.6 V pk (76.09 A) across C42 at 35 kHz (C2) versus the 42.4 V pk SELV reference. Action: commit an R39-open ngspice run.

**MAG-27 (U).** See Findings.

**MAG-28 (1).** See Findings.

**MAG-29 (2).** TP1-TP36 (CT_ZC, CT_MON, OCP node), bench procedure and IR list exist (`native-21/BRINGUP-PROBES.md`, `s19b/BENCH-PRECOMPLIANCE.md`). Gaps: no PE test point, no CT burden-node pad, no probe window at J2/J5, no unfiltered/filtered tap at L1; `DECISIONS.md:806` defers these to the next re-spin.

## Appendix: commands run (reviewer calculations)

All Python was read-only (`python3 -I`), no builds.

- **C1** footprint scan of the pinned PCB: regex over `(footprint ...)`/`(property "Reference" ...)` in `hardware/native21-stage19b/section.kicad_pcb` gives magnetic parts L1 (232, 31, `B82726S2_ReviewOnly`) and T1 (135, 110, `CST3015`) plus TP1..TP36; coordinates quoted above (J1, F1, C1, C3, C4, J6, PS1, PS2, BR1) come from the same scan.
- **C2** `python3 -I -c` with R = 1.5 + 1.5 ohm, L = 3.2 mH: f_c = R/(2 pi L) = 149.2 Hz; phase at 35 kHz = atan(R/(2 pi f L)) = 0.244 deg = 19.4 ns; |Z(C42=100 nF, 35 kHz)| = 45.5 ohm; V = (I_pk/100) * 45.5 = 26.9 V (59.17 A) and 34.6 V (76.09 A); ADC headroom (2.85 - 2.791)/0.015 = 3.9 A; flux margin 638/20.8 = 30.7.
- **C3** shapely 2.1.2 (`python3 -I`): parsed `filled_polygon` of each zone and all `segment` records by net and layer from the pinned PCB, unioned per (net, layer), then (a) same-layer `distance()` and (b) cross-layer `intersection().area` between {l_f, ac_n_in} and {l_filt, n_filt, hv_ret, bus_p, rect_p, rect_n, sw_a, sw_b, res_a, coil_feed, n_ha, n_hb}. Results: l_f(F.Cu) vs l_filt(B.Cu) overlap 10.6 mm2, C = eps0 * 4.4 * A / d (d = 1.44 mm from the stackup: 0.4355 + 0.5 + 0.4355 mm) = 0.3 pF; same-layer gaps l_f-n_filt 3.5, ac_n_in-n_filt F 3.57, ac_n_in-l_filt B 3.2, l_f-hv_ret 19.4, ac_n_in-hv_ret 22.1 mm; no cross-layer overlap with any noisy net.
- **C4** PE net: 21 segments (17 at 0.4 mm), Dijkstra on segment endpoints from (215, 102.8) to (150.6, 134.5) gives 96.1 mm; thin-strip L = 2 * l[cm] * (ln(2 l / (w + t)) + 0.5) nH with l = 9.6 cm, w = 0.4 mm, t = 0.07 mm gives 125 nH; f = 1/(2 pi sqrt(L * 2.2 nF)) = 9.6 MHz.
- **C5** `python3 -I` on `b3-convergence/inputs/heat_der14.json`: L1 watts_nominal 1.2287 W, implied I = sqrt(W / (2 * 0.0045)) = 11.68 A; 15 A: 2.025 W typ, 2.700 W at 6 mohm; model rise (68.6 - 50) / 1.2287 = 15.14 K/W gives 80.7 C (2.025 W) and 90.9 C (2.7 W).
- **C6** pickup scaling: I ratio 59.17 / 31.1 = 1.903, f ratio 60 / 31.1 = 1.929, product 3.67; 0.25 A -> 0.92 A, 3.0 A -> 11.0 A (linear, quadrature structure ignored).
- Grep for ferrite/bead parts: `grep -n -i "bead\|ferrite\|BLM\|choke\|inductor" elec/src/*.ato` returned only the L1 choke and unrelated hits.

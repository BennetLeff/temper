Identity check (shasum -a 256, run 2026-10-13): `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662  /Users/bennet/Desktop/temper/worktrees/hw-baseline-guard/hardware/native21-stage19b/section.kicad_pcb` -- matches the pin in `hardware/CURRENT.tsv:55` (`board hardware/native21-stage19b/section.kicad_pcb b19a4553...0756662`). Scored board: native-21 stage 19b, NOT stage15b as the rubric text says.

# Ott, Electromagnetic Compatibility Engineering: rubric scored against native-21 stage 19b

Rubric: `pcb-reference-rubrics-2026-10-13/ott-emc.md` (OTT-01..OTT-35), scoring contract from its 'Common scoring contract', `README.md` (0/1/2/3/U/NA) and `tradeoffs.md`. Design tree = `zapote/power-stage-120v/` (paths below are relative to it unless they start with `section.kicad_pcb`, which means the pinned snapshot). Status: no hardware built, no EMI measurement; so no criterion can reach 3 and nothing scored 3.

## Score tally

| 0 | 1 | 2 | 3 | U | NA |
|---|---|---|---|---|---|
| 0 | 8 | 19 | 0 | 7 | 1 |

- Score 1 (8): OTT-06, OTT-15, OTT-18, OTT-19, OTT-20, OTT-23, OTT-25, OTT-27
- Score 2 (19): OTT-01, OTT-02, OTT-03, OTT-04, OTT-05, OTT-07, OTT-08, OTT-09, OTT-10, OTT-11, OTT-12, OTT-13, OTT-14, OTT-16, OTT-17, OTT-21, OTT-22, OTT-29, OTT-31
- U (7): OTT-24, OTT-26, OTT-28, OTT-32, OTT-33, OTT-34, OTT-35
- NA (1): OTT-30

Not an average or readiness verdict. The conducted-EMI desk study reads PASS (nominal 10.5 dB, minimum 6.5 dB over its sensitivity set), but see OTT-18/19/20: the filter that produces that PASS is a module that exists only as a requirement.

## Findings (every 0/1 and every U)

### OTT-06 (1): Layer-change returns are only enforced for pwm_hb and ct_zc.
- Mechanism: pwm_ha changes reference 7.59 mm and pwm_la 5.11 mm from the nearest v3v3/selv_gnd cap (C54); PERMIT has five changes at 4.33-20.89 mm (C154 12.21, C156 20.89) and bias_bad up to 15.76 mm with a 22.25 mm unreferenced run. Return current for ns-class edges detours by that length: radiation and common-impedance pickup on the gate PWM and on the shutdown chain. The 3.0 mm gate asserts only `{bus_fault_hot, pwm_hb, ct_zc}`.
- Evidence: stage19-pi-si/return-path19b.json signals.pwm_ha / pwm_la / permit / bias_bad (`transfer.mm`); native-21/layout/gates/return_path19.py:61-65; DECISIONS.md:774-789.
- Proposed action / check: Give pwm_ha, pwm_la and permit the C153-C156 treatment (transfer cap within 3 mm of each via, or move the vias); extend `ASSERT_TRANSFER` to all J4 signals; check = `return_path19.py` lists no `open_reference_changes` for them.

### OTT-15 (1): Bulk capacitors are remote from the FET row and the bulk-path inductance is an unextracted estimate.
- Mechanism: C5/C6 are 140-245 mm from Q2-Q6 and ~130 mm from BR1. DECISIONS.md:426 ties S4 die VDS to bulk-path L (+~5 V/nH, failures from ~28-32 nH) with an estimate of ~20 nH +/-50 % (upper end 30 nH inside the failure band); the F6 decks pinned the bulk node with an ideal source. The 'Action: extract or measure the native-21 bulk path' (DECISIONS.md:427) has no closing entry through 19b.
- Evidence: section.kicad_pcb footprint positions; DECISIONS.md:425-427, 456-457, 823; ALT-C5C6.md:153.
- Proposed action / check: Extract FET-row-to-C5/C6 loop L on the 19b copper (remote FEM box); re-run explicit-bulk F6 with the result; bench: bus overshoot at the FETs and C5/C6 case temperature at 22 A.

### OTT-18 (1): The EMI PASS rests on an inlet module that is a specification, not a parted design; the only parted version fails.
- Mechanism: In the same model: nominal 10.5 dB; D-22 module as specified (18 uH DM) -5.1 dB; board only -39.3 dB (9-150 kHz QP, 70 kHz 2fs DM line). Passing needs >=100 uH DM from two discrete 41 uH inductors (8 mOhm, 30 pF assumed) that have no MPN in PARTS.md or the BOM. 80 uH gives 8.7 dB, so the margin to the shortfall is one inductor tolerance or bias droop.
- Evidence: emi_s19b.py:638; results.json scenarios; D22 PARTS.md:3-30; DECISIONS.md:477, 802.
- Proposed action / check: Select MPNs (Isat > 15 A x 1.4 hot, SRF, DCR) for the DM inductors or a >=100 uH-leakage CMC; update PARTS.md and the BOM; rerun `emi_s19b.py` with their Z(f)/bias data; measure insertion loss (BENCH B8) before treating 10.5 dB as a design margin.

### OTT-19 (1): No total touch-current budget.
- Mechanism: Y capacitance is 9.1 nF per line (0.48 mA at 140 V/60 Hz from Y alone; module Y pairs 0.437 mA/conductor at +20 %). IRM-20-15, IRM-20-24 and IRM-60 internal Y leakage is in no repo datasheet, R38/PE and single-fault cases are unsummed, and the governing standard (UL 1026 vs 858) and limit are unselected. A Y1 or module-Y tolerance stack could exceed whatever the limit is without anyone noticing.
- Evidence: D22 PARTS.md:48, :58; s19b/README.md:50, :133; sourcing/inquiries/F1-CERTIFIER.md:82-83.
- Proposed action / check: Write the leakage allocation (all Y + three supplies + wiring at 140 V, 60 Hz, +20 % C, single-fault) against the certifier's limit; measure with a leakage meter before any B9 Y change.

### OTT-20 (1): DM inductors have no hot/bias characterisation.
- Mechanism: PARTS.md:36: no guaranteed hot leakage-inductance vs rectifier-peak-current curve for L1 (tested down to 9 uH); the module's two 41 uH inductors are unselected; module heat (8 W allowance vs 3.6 W DM inductors + 2.7 W choke) is 'tight'; the model's L1 fit is unqualified above ~850 kHz. A saturating or hot-derated DM inductance moves the 70 kHz line directly.
- Evidence: PARTS.md:36; s19b/README.md:80, :138; results.json (module_DM_80uH 8.7 dB).
- Proposed action / check: Collect L vs I/T curves; bench L at 15 A DC hot; thermocouples on L1 and module chokes in the 28 A soak.

### OTT-23 (1): Cables are not modelled or tabulated.
- Mechanism: Coil leads J2/J5, the J3 TCO loop to off-board cutouts (mains-referenced, runs to the coil/glass), J11/J13 blower leads (292/322 mm, in a 453-573 uT coil field at PS3) and the J4 harness (74 mm, no cable PN/AWG/drawing) have no cable table, routing or CM-current model; the EMI model has only a lumped coil-to-PE C. BENCH clamps L, N and PE only.
- Evidence: 06-controller-interface/README.md:80-84; DECISIONS.md:260, 677, 679; README.md:116; BENCH-PRECOMPLIANCE.md:20.
- Proposed action / check: Cable table (conductor, length, routing, return, shield); add clamp sweeps on J2/J5, J3, J4, J11/J13 to BENCH; reserve the J2/J5 probe window (DECISIONS.md:806).

### OTT-25 (1): J4 pin map gives 12 signals three return pins and puts analog beside fast digital.
- Mechanism: J4 (Micro-Fit 2x8, 3 mm): row 1 v15_selv, GND, v3v3, GND, pwm_ha, pwm_la, pwm_hb, pwm_lb; row 2 permit, bus_fault, vbus_p, vbus_n, ct_zc, ct_mon, GND, line_zc. ct_mon (analog CT monitor via 1 kOhm) is directly across from pwm_la; line_zc across from pwm_lb; pwm_la has no ground neighbour in its row. Over a 74 mm harness: crosstalk into the CT measurement and a larger PWM loop. (The 06 audit table still lists J4.16 as GND: it is native-17.)
- Evidence: section.kicad_pcb J4 pads (appendix A); BRINGUP-PROBES.md; 06-controller-interface/README.md:57.
- Proposed action / check: Define the harness as twisted pairs (pwm+GND, ct_mon+GND) with a continuity schedule, or re-pin J4 at the next spin (GND between PWM and analog); check = ct_mon error with 60 kHz PWM on a mock harness.

### OTT-27 (1): J4 and PERMIT inputs have no RF/ESD diversion at the boundary.
- Mechanism: PWM_HA/LA/HB/LB go straight from J4 to UCC21550 INA/INB; PERMIT has 100 Ohm series + 100 kOhm pulldown only; CT_MON has 1 kOhm and no capacitor; no immunity data. RF pickup on a 74 mm lead can rectify in the driver/comparator inputs (spurious drive near shoot-through) or offset CT_MON.
- Evidence: elec/src/power_stage_120v.ato:81-82, 95-105, 673-676, 855-858; FINDINGS.md:22.
- Proposed action / check: Reserve DNP series-R/shunt-C footprints at INA/INB/permit/ct_mon within the D-31 latency budget; RF/BCI injection on J4 with firmware logging; confirm UCC21550 input filter vs the PWM min pulse.

### OTT-24 (U): No shield/cable choice.
- Evidence: DECISIONS.md:805; 06 README:83-84
- Proposed action / check: Evidence needed: J4 harness and coil-lead construction, 360-degree termination to sink/chassis, shield-current analysis.

### OTT-26 (U): No enclosure seam/aperture/bond evidence in the tree.
- Evidence: (none; enclosure study 16 report is outside the pinned tree)
- Proposed action / check: Evidence needed: current enclosure revision material, seam/vent map, bond straps, H-field seam scan, 30 m field result.

### OTT-28 (U): No ESD analysis.
- Evidence: (none; R38 is the single SELV-PE bond, D5-BASIS.md:9-14)
- Proposed action / check: Evidence needed: touch-point map, IEC 61000-4-2 level/criterion, discharge path through R38/PE/J4, TVS placement, indirect-discharge test.

### OTT-32 (U): No cable CM-current measurement exists or is planned for the coil leads/J4.
- Evidence: BENCH-PRECOMPLIANCE.md:20
- Proposed action / check: Evidence needed: calibrated clamp sweeps on every cable, assembled, with background and repeat-after-mitigation.

### OTT-33 (U): No near-field scan exists or is planned.
- Evidence: BENCH-PRECOMPLIANCE.md (no H-field step)
- Proposed action / check: Evidence needed: fixed-distance H-field scans of C38-C41/FET row, L1/module, coil leads, seams, per switching state, A/B.

### OTT-34 (U): No conducted-emission trace; model not predictive 1-30 MHz.
- Evidence: s19b/README.md:127; BENCH-PRECOMPLIANCE.md:71
- Proposed action / check: Evidence needed: LISN L/N traces 9 kHz-30 MHz (peak prescan, QP/AV), C1-C6 incl. earthed pan, LISN calibration, ambient trace; lab confirmation of Canada/Mexico limits (README:22).

### OTT-35 (U): No immunity test plan, levels or results.
- Evidence: ALT-D3.md:114; FINDINGS.md:24
- Proposed action / check: Evidence needed: certifier-selected levels/criteria, injection points, firmware event logs at max heating.

### Other observations (not scored separately)

- Stale input in the EMI model: `emi_s19b.py:194` uses CBULK = 5.4 uF; the 19b BOM has C5/C6 = B32676G1905K000 (9 uF each, 18.4 uF) at `native-21/frozen/default.csv:10` (stage 14). ALT-C5C6.md:153 says the DM line falls with 18.4 uF, so this is likely conservative, but ALT-D3.md:222 lists the re-run as pending and the model was not updated. Also `emi_s19b.py` has no 30KPA150CA (D3/D17, default.csv:60) capacitance, and README:50 still cites the F6 bias transformers that stage 14 replaced with RECOM U41/U42 (3.5 pF max barrier, DECISIONS.md:447; cm_screen.json used 3.0 pF, effect < 0.1 dB).
- The conducted model is not predictive above ~0.5-3 MHz (no ring, no board/harness parasitics: README:80,127), yet the FCC limit runs to 30 MHz and the leg A commutation loop is 37.6 nH (FINDINGS.md:39). That band has neither prediction nor measurement; it is where layout (OTT-03/11) governs.
- Board Y1 caps C3/C4 reach PE through 74.6-80.9 mm of 0.2-0.6 mm track (appendix A; ~45-80 nH by my estimate) against the model's 15 nH; the model's Y_caps_ESL_x3 and PE_bond_200nH scenarios do not move the < 70 kHz result, but this limits the board Y caps in the MHz range (module Y bond directly to PE).
- Worst low-margin cases are all from coil-to-PE capacitance: 31 pF pan floating (study 16) gives 10.5 dB; pan earthed 91-102 pF gives 2.6/1.7 dB (INFO, not a compliance setup); a one-sided 100:0 100 pF coil gives -0.8 dB (excluded from the verdict, results.json).
- Limit set outside the US (Canada ICES-001 / CISPR 14-1 / Mexico) is unverified (s19b/README.md:22).

## Per-criterion rationale

### OTT-01: Draw each fast-current loop, including the return -- score 2
- Evidence: validation-results/01-switching-parasitics/STATUS.md:8 and FINDINGS.md:39 (M11: native-21 leg A parallel commutation loop 24.9->37.6 nH, leg B 29.1->24.5 nH, coarse reference, status OPEN); native-21/FLOORPLAN.md:21; validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.txt (reference under every 0.25 mm of 18 fast/protection nets; 0 samples over another net); validation-results/08-manufacturing-package/native-21/stage19-pi-si/README.md:25-31; DECISIONS.md:709 (commutation FEM not re-run since stage 14-15 copper)
- Rationale: Commutation loops (FEM), gate loops (FEM, through the bias cap) and fast-signal returns (return_path19) are drawn from routed copper. Not drawn: DC-link recharge and aux-converter (U41/U42, PS2, SN6507-class) edge returns state by state; FEM predates 19b copper. No scope/current-probe captures (no hardware). Capped at 2.

### OTT-02: Partition noisy and susceptible functions before routing -- score 2
- Evidence: native-21/FLOORPLAN.md:18-26 (zone table: sink row, power core, HS bias islands, SELV island with 8 mm moat, HOT protection, mains, tank); DECISIONS.md:790 (barrier21 0, RES_A outer 0, Rust gate 0 over 5,829 items, plane splits 0); my plan-view query on native21s19b-all-copper.json.gz (see md appendix A): CT sense nets (ct_s1/s2, ct_sense_mon, ct_oc_*, ct_mon, ct_zc), vbus_*, pwm_*, permit stay >=10.4 mm (CT) / >=8.7 mm (others) same-layer from SW_A, SW_B, RES_A, COIL_FEED with 0 mm2 cross-layer overlap
- Rationale: Source/victim zones are separated and gated. Exceptions that are deliberate: ocp_kelvin_p/n 3.7 mm from SW copper, with SW_A (F.Cu) over the In1 Kelvin pour (8.15 mm2, ~0.7 pF by my parallel-plate arithmetic, ~5 mA at 170 V/24 ns), CM to both Kelvin legs; magnetic pickup is covered by PICKUP.md, electric coupling is not. No hot-spot/immunity test, so not 3.

### OTT-03: Minimize differential-mode switching-loop area -- score 2
- Evidence: validation-results/01-switching-parasitics/FINDINGS.md:39 (M11), STATUS.md:8; DECISIONS.md:144 (+51 % leg A loop accepted for F6 network; 252/252 cases pass), DECISIONS.md:709 (R5 land span 8.26->7.0 mm, no re-extraction; 'F6 stays closed on that basis'); PROTOTYPE-POWER-LOOP.md (C38-C41 local film caps); validation-results/07-conducted-emi/s19b/README.md:127 (conducted model has no ring or board parasitics above ~1-3 MHz)
- Rationale: Routed loop + FEM matrix + passing switching decks support the design (2). Concerns that stop short of 1: leg A loop is the larger (37.6 nH, coarse, M11 OPEN) and no extraction has been run on stage 17-19b copper; the effect of this loop on 1-30 MHz conducted/radiated emission is not predicted anywhere. Needs ringing capture at U1/U2 sources and a near-field scan.

### OTT-04: Keep fast signal references continuous -- score 2
- Evidence: validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.txt and return-path19b.json (signals.*: wrong_reference_samples 0 for all 18 nets; longest_no_reference_run_mm pwm_ha 0.25, pwm_hb 0.25, ct_zc 0.25, bus_fault_hot 1.25, permit 6.0, bias_bad 22.25); native-21/stackup.json:3 (outer layers 0.4355 mm over In1/In2); native-21/layout/gates/return_path19.py:61,64-65 (asserted set, 3.0 mm)
- Rationale: Each routed fast net has a traced reference under it. Not asserted by any gate: permit (6.0 mm unreferenced run on F.Cu at (79.4,119.1)) and bias_bad (22.25 mm run on B.Cu at (66.5,127.2), DECISIONS.md:789 argues fail-safe direction). pwm_lb crosses a 0.76 mm reference gap at (32.6,59.9-61.4). No waveform/emission test.

### OTT-05: Treat slots, cutouts, and antipad rows as return obstructions -- score 2
- Evidence: native-21/FLOORPLAN.md:152-165 (accepted slot table for In1 HV_RET / In2 BUS_P) and :23 (every moat-crossing part straddles the edge); DECISIONS.md:790 (plane splits 0, DRC 0/0); my query (appendix A): around J4 (x31-59,y176-187) In1 v3v3 keeps 251.4 of 308 mm2 and In2 selv_gnd 249.6 of 308 mm2 with 1.02 mm drills, i.e. individual clearances not a broad cutout; board has 4 routed slots (DECISIONS.md:790 'Gerber review 869 + 4 slots')
- Rationale: Slots are listed with a reason and the zone-to-zone split count is 0 on every build. Power-core slot effect on loop L rests on the pre-19b FEM (not re-extracted). Isolation moat is respected by design (route around, not bridge).

### OTT-06: Supply a return when changing signal layers -- score 1
- Evidence: validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.json signals.pwm_ha.transitions[0].transfer (C54, 7.59 mm), signals.pwm_la (C54, 5.11 mm), signals.permit (C154 12.21, C47 6.94, C142 4.33, C61 5.88, C156 20.89 mm), signals.bias_bad (C138 15.76/14.65/14.58/13.77/9.75, C61 7.15 mm); native-21/layout/gates/return_path19.py:61-65 (3.0 mm assertion applied only to pwm_hb and ct_zc); DECISIONS.md:774-789
- Rationale: Mechanism: stage 19/19b enforced <=3.0 mm transfer-cap distance for pwm_hb and ct_zc only. The same J4 PWM class (pwm_ha 7.59 mm, pwm_la 5.11 mm from C54) and the PERMIT shutdown line (up to 12.21 and 20.89 mm) change reference far from any v3v3/selv_gnd cap, so return current takes a detour of that length at ns-class edges (loop area -> radiation + common-impedance pickup on the gate PWM and the fault-chain input). Fix: add transfer caps or move the vias for pwm_ha/pwm_la/permit (same C153-C156 treatment) and extend ASSERT_TRANSFER to every J4 signal; check: return_path19.py reports 'open_reference_changes' empty for those nets.

### OTT-07: Choose stackup by field and return goals, not layer count alone -- score 2
- Evidence: native-21/stackup.json:3 (JLC041622-7628, 4 layers 2 oz, 0.4355 mm prepreg outer, 0.5 mm core, NP-155F, total 1.653 mm, +/-10 %, CTI to be confirmed on order); native-21/FLOORPLAN.md:3 (2 oz all layers); HV_RET on In1 / BUS_P on In2 stacked across the 0.5 mm core; SELV signals on F/B over In1 v3v3 / In2 selv_gnd islands
- Rationale: Constraints and trade-offs documented; stack gives a 0.5 mm HV loop pair. Caveat: stackup.json:3 takes the thicknesses from a third-party scrape (gsuberland/jlcpcb_autogenerated_stackups, 2025-05), and JLC may substitute laminate/prepreg; no as-built stackup or coupon exists. Confirm on the order and re-run FEM if the 0.5 mm core or 0.4355 mm prepreg changes.

### OTT-08: Prefer continuous ground for mixed-signal areas, with disciplined routing -- score 2
- Evidence: validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.txt (SELV nets reference In1 v3v3 / In2 selv_gnd, transfer caps listed); validation-results/08-manufacturing-package/native-21/stage19-pi-si/bypass-check-native21s19b.txt (11/11 ICs, supply/return within limits 2.0-4.5 mm); D5-BASIS.md:9-26 (single removable R38 functional bond near J6); DECISIONS.md:790 (plane splits 0)
- Rationale: SELV island has local v3v3/selv_gnd plane pair, IC pin returns are gated, galvanic splits are real (D5). The sensitive converter inputs are mostly isolated (AMC1311/ISO7710). Pending: ADC/comparator noise under switching is not measured; ct_s2 is a ~202 mm net with 32 vias (my length sum) feeding comparators U10-U12.

### OTT-09: Keep external connector returns intact -- score 2
- Evidence: my query (appendix A) of native21s19b-all-copper.json.gz around J4: In1 v3v3 251.4/308 mm2, In2 selv_gnd 249.6/308 mm2 copper retained under the 16 pins; J4 pin map from section.kicad_pcb (v15_selv, GND, 3V3, GND, pwm_ha, pwm_la, pwm_hb, pwm_lb / permit, bus_fault, vbus_p, vbus_n, ct_zc, ct_mon, GND, line_zc); native-21/BRINGUP-PROBES.md (J4 ground pins 2/4/15); FLOORPLAN.md:25-26 (J1/J2/J5 positions)
- Rationale: Board-side return copper at the connectors is intact (individual antipads). The remaining return question is the cable side (3 ground pins for 12 signals): scored under OTT-25. Mating harness unknown (OTT-23).

### OTT-10: Ground copper pours deliberately -- score 2
- Evidence: kicad-cli/pcbnew query on the pinned section.kicad_pcb (appendix A): 53 filled zones, every one assigned to a net, island_removal_mode = 0 (always remove) on all; the 40 net-less zones are unfilled rule areas (keepouts); DECISIONS.md:790 (zone priority gate 25 contested, 0 equal; DRC 0/0; library tables 0 violations 0 warnings); DECISIONS.md:781 (19: K6 dangling stubs closed)
- Rationale: No floating islands by construction and no unconnected stubs per DRC. Large switch-node pours (SW_A 1.93e-3 m2, SW_B 3.31e-3 m2, EMI README:47) are intended; their capacitance is modelled (0.28/0.12 pF to pedestals, 1.1/1.95 pF to chassis ASSUMED). No A/B emissions comparison.

### OTT-11: Control clock routes and high-edge-rate control signals -- score 2
- Evidence: validation-results/07-conducted-emi/s19b/README.md:32 (edge times from D-19 census: 10-90 % 26.8/19.5 ns at 170 V, 24.0/18.6 ns at 198 V at 37 A ZVS, scaled with commutating current) and :36 (source model within 0.25 dB of D-22 FFT); DECISIONS.md:68 (200 ns controller gap), DECISIONS.md:789 (bias_bad driven by SN74LVC1G17, tpd 1.5-4.6 ns); validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.txt
- Rationale: Edge-rate x current ranked for the power switches (simulation-derived, not measured) and for the aux digital nets. The J4 PWM edge rate from the controller is not stated anywhere in this tree (U for that input). Gate-side damping is function-sized (F6 network, R9/R17 dead time).

### OTT-12: Keep sensitive inputs and feedback loops compact -- score 2
- Evidence: validation-results/02-protection-timing/coil-pickup/PICKUP.md:3-9 and :31-43 (Kelvin pair loop 213.7 mm2 -> 1.14/2.75 mV pk, CT comparator loop 159.5 mm2, CT_MON to J4.14 791.7 mm2 -> 0.79/1.07 mV pk; 'no loop needs a fix'; OCP shift <=0.6 A vs 3.32 A margin); validation-results/02-protection-timing/kelvin/budget-native21s19b.md; my length sums (appendix A)
- Rationale: Magnetic pickup from the coil field is computed per loop from FEM field maps. Gaps: study is on stage 13b copper (= stage 14); stage 19 re-routed ct_zc, bus_fault_hot and the Kelvin return (to In2), so run_loops.py should be rerun on the 19b dump. RF rectification of comparator/ADC inputs is not evaluated; filtering vs the 0.81 us protection chain budget is per D-31 only. No near-field scan.

### OTT-13: Model decoupling as an installed L-C network -- score 2
- Evidence: validation-results/08-manufacturing-package/native-21/stage19-pi-si/bypass-check-native21s19b.txt (11 ICs: supply 1.70-4.38 mm, return 2.12-7.61 mm, plane vias); validation-results/08-manufacturing-package/native-21/stage19-pi-si/pi19b.txt (RECOM/TPS7A47 pins to caps 1.61-2.93 mm, returns up to 6.97 mm); native-21/FLOORPLAN.md:198-203 (stage 9: UCC21550 VDD stacks, loops 2.07-2.2 mm no vias); DECISIONS.md:155 (HS 10 uF 7.9-8.6 mm, LS 10 uF ~16 mm from VDDB; 'DC-bias capacitance loss ... not credited')
- Rationale: Distance gates and datasheet placement rules support the layout; rail transients are covered in time domain by the F6/bias campaigns (DECISIONS.md:448, 128/128 pass). No installed-impedance (ESL+via+plane) model or X7R bias derating of the 10 uF parts, and no measured local rail, so 2 not 3.

### OTT-14: Examine antiresonance and source interaction -- score 2
- Evidence: validation-results/01-switching-parasitics/FINDINGS.md:17 (F3: 5-port explicit bulk path); validation-results/08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/ALT-C5C6.md:153 and DECISIONS.md:456 (explicit-bulk F6 deck 168/168, bulk ESL 12 nH); validation-results/07-conducted-emi/s19b/README.md:38 (lumped bulk/local DC-link in the EMI network); DECISIONS.md:426 (S4 sensitive to bulk-path L, ~20 nH +/-50 %)
- Rationale: Bulk-vs-local interaction is simulated in the time domain on the power loops. No frequency-domain PDN sweep for the 9-18 uF + 0.1 uF film + resonant-bank DC link or the 100 nF/1 uF/10 uF driver stacks; no rail-noise capture. Supported intent, verification pending.

### OTT-15: Put bulk energy where recharge current enters -- score 1
- Evidence: section.kicad_pcb footprint positions (appendix A): C5 (205.2,65.5), C6 (248.2,73.8) vs Q5/Q6/Q3/Q2 x=4.5-62.6, BR1 (81.7,4.6), C38-C41 x=2.4-82.8 on the FET row, J1 (281,7.5), L1 (232,31); DECISIONS.md:425-427 ('F6 decks pin the bulk node with an ideal source'; S4 die VDS +~5 V per nH of bulk-path L, failures from ~28-32 nH; estimate ~20 nH +/-50 % (ALT-C5C6); 'Action: extract or measure the native-21 bulk path (the FET row to C5/C6)' - no later entry closes it); DECISIONS.md:457 (C5/C6 about 80 % of TDK self-heating allowance at 85 C case, bench), :823 (C5/C6 27 K margin depends on bench IR)
- Rationale: Mechanism: the bulk caps are 140-245 mm from the FET row and ~130 mm from BR1 (the rubric's '1' geometry). Local film caps C38-C41 serve the edges and the trunk is a 0.5 mm HV_RET/BUS_P plane pair, but the bulk-path L is only an estimate whose upper end (30 nH) reaches the S4 failure band (28-32 nH), and the extraction DECISIONS.md:427 asks for has not been run on 19b copper. Action: FEM/PEEC-extract FET-row-to-C5/C6 L on the 19b dump (remote box), re-run the explicit-bulk F6 deck with it; bench: scope the bus and measure C5/C6 case temperature at 22 A.

### OTT-16: Separate common-mode from differential-mode conducted noise -- score 2
- Evidence: validation-results/07-conducted-emi/s19b/README.md:72-75 (CM-dominant 9-150 kHz at 60 kHz; DM-dominant 150 kHz-30 MHz) and results.json scenarios.nominal (198V/pan_28A lo_9k_150k CM 62.8 dBuV vs DM 75.5 dBuV at 70 kHz); validation-results/07-conducted-emi/s19b/BENCH-PRECOMPLIANCE.md:16 (CM/DM discriminator) and B5; DECISIONS.md:792-806 (item 20)
- Rationale: Modes are predicted per band and the mitigations match (module CM choke/shield held in reserve). No measured L/N spectra, no mode separation yet. Model-only; PS1-PS3 emissions are an assumed bound (README:52).

### OTT-17: Locate the mains filter at the entry boundary and prevent bypass -- score 2
- Evidence: my plan-view query of native21s19b-all-copper.json.gz (appendix A): line-side nets (ac_l_in, ac_n_in, l_f) vs load-side nets (l_filt, n_filt, rect_*, bus_p, sw_*): min same-layer gap 3.35 mm F.Cu; B.Cu 0.2 mm at (234.0,33.0) between L1.1 (l_f) and the l_filt pour; F.Cu l_f over B.Cu l_filt overlap 10.6 mm2 (~0.27 pF parallel-plate, ~8-11 mm of B.Cu within 0.5-1 mm); native-21/FLOORPLAN.md:25 (mains at rear, L1 -> BR1); validation-results/01-switching-parasitics/round17/delegation/out-D22/PARTS.md:3-14 and DECISIONS.md:70 (inlet module 'keep filtered and unfiltered conductors apart')
- Rationale: On-board bypass capacitance is small (<~1 pF est.) against the 11.1 pF per-winding L1 model and the L1_winding_C_x2 sensitivity stays 10.4 dB. Not yet real: the primary filter is the off-board inlet module (mandatory per DECISIONS.md:802); its harness routing, chassis bond and separation from J1/F1 wiring are undefined. Filtered L_FILT/N_FILT run ~150 mm to BR1 along SW_A/SW_B (3.2 mm gaps for 15-26 mm, 17.7 mm2 overlap) - small, but unmeasured.

### OTT-18: Match filter topology to measured mode and terminal impedances -- score 1
- Evidence: validation-results/07-conducted-emi/s19b/results.json scenarios['module_DM_18uH_only (D-22 as specified)'] min margin -5.1 dB and ['board_only_no_module'] -39.3 dB (9-150 kHz QP, 70 kHz, 198V/pan_28A), vs nominal 10.5 dB; validation-results/07-conducted-emi/s19b/emi_s19b.py:638 (MODULE_NOM LNEW=41e-6: 2 x 41 uH discrete inductors, 8 mOhm, 30 pF assumed); validation-results/01-switching-parasitics/round17/delegation/out-D22/PARTS.md:3-14, :20-30 (only parted module: CMC + X + Y, DM from 18 uH leakage; no 41 uH inductor MPN); DECISIONS.md:802 ('module mandatory at >=100 uH DM; D-22's 18 uH misses 9-150 kHz by 5.1 dB'); README:34 / DECISIONS.md:477
- Rationale: Mechanism: the PASS verdict is for a module that exists only as a requirement (>=100 uH DM, >=80 % at 15 A, 20 A). The one module with MPNs (D-22) fails the 9-150 kHz band by 5.1 dB in the same model; board-only fails by 39 dB. DM inductors' Isat/SRF/temperature are unselected and the 2fs (70 kHz) line is the nominal worst case. Action: choose MPNs for the 2x41 uH (or a >=100 uH leakage CMC), put them in D22 PARTS.md/BOM, re-run emi_s19b.py with their Z(f)/bias curves, and measure insertion loss per BENCH step B8.

### OTT-19: Treat X/Y capacitor roles and safety constraints explicitly -- score 1
- Evidence: validation-results/01-switching-parasitics/round17/delegation/out-D22/PARTS.md:48 (0.437 mA per conductor from the added Y pairs) and :58 ('complete appliance still needs an explicit leakage-current allocation, including its existing filter and both supplies, wiring and single-fault cases'); validation-results/07-conducted-emi/s19b/README.md:133 (Y 9.1 nF per line = 0.48 mA/line at 140 V/60 Hz from Y alone; 'touch-current budget is the real cap'); native-21/frozen/default.csv:5,8 (C1/C2 X2 1 uF R463N410050N1K; C3/C4 DE1E3RA222MA4BP01F 2.2 nF); DECISIONS.md:161 (M14 PE branch); D5-BASIS.md:21-26
- Rationale: Roles are explicit (X across L-N, Y to PE; no DC-bus Y by decision, README:133) and parts are rated classes, but there is no total leakage budget: IRM-20-15/-24 and IRM-60 Y-caps (not in any repo datasheet, README:50), the module Y (6.9 nF/line), R38 bond and single-fault cases are unsummed, and the product standard/limit (UL 1026 vs 858, F1-CERTIFIER.md:82-83) is unselected. Action: sum worst-case leakage (all Y + module + 3 supplies) at 140 V, 60 Hz, +20 % C, against the certifier's limit; measure with a leakage meter before the Y changes in B9.

### OTT-20: Characterize chokes and ferrites at actual frequency and current -- score 1
- Evidence: validation-results/01-switching-parasitics/round17/delegation/out-D22/PARTS.md:36 ('does not give a guaranteed hot leakage-inductance-versus-rectifier-peak-current curve'; leakage tested down to 9 uH); validation-results/07-conducted-emi/s19b/README.md:38 (L1 curve fit 11.1 pF + 12.7 kOhm per winding from TDK, 'choke fit unqualified above ~850 kHz' at README:80); results.json scenarios L1_minus30pct_and_module_choke_minus30pct 10.7 dB, module_DM_80uH 8.7 dB; validation-results/07-conducted-emi/s19b/README.md:138 (module heat: 8 W allowance vs 3.6 W DM inductors + 2.7 W choke, 'tight')
- Rationale: Mechanism: DM inductance of L1 (18 uH typical leakage, Isat at hot rectifier peaks unguaranteed) and of the unselected 2x41 uH is what sets the 70 kHz DM margin; a drop to ~80 uH still passes (8.7 dB) but there is no bias/temperature curve for any DM element, and L1's local air temperature (rated 20 A at 60 C) is unknown. Action: pull Z/L vs I and T curves from the chosen parts, bench-measure module DM L at 15 A DC and hot (BENCH B1/B8), put thermocouples on L1 and module chokes in the 28 A soak.

### OTT-21: Inventory parasitic common-mode paths from switch nodes -- score 2
- Evidence: validation-results/07-conducted-emi/s19b/README.md:44-50 (Q3/Q6 tab->PE 5.4-8.6 pF nominal 7.0 pF; Q2/Q5 2x7.0 pF; pour->pedestal 0.28/0.12 pF; pour->chassis 1.1/1.95 pF ASSUMED; BR1 case 10 pF ASSUMED; coil 25+25 pF, updated to 15.7/15.3 pF at :151-160); validation-results/07-conducted-emi/s19b/README.md:151-165 (enclosure study 16: 31.0 pF pan floating, 91.4 pF pan earthed); validation-results/07-conducted-emi/native21/cm_screen.json (transformer 3.0 pF; <=0.05 dB); command: 7.0 pF x 170 V / 26.8 ns = 44 mA peak per switch-node tab
- Rationale: Path inventory and sensitivity set are thorough and the dominant uncertainty (coil-to-PE) now has a geometric solve (board copper treated as air, +20 pF bound). Remaining: HOT-to-SELV capacitance of PS1-PS3 is in no datasheet; the screen used 3.0 pF where the stage-14 RECOM U41/U42 carry 3.5 pF max (DECISIONS.md:447 barrier note; effect negligible); pan-earthed case leaves 1.7-2.6 dB (INFO only). No measurement of any path.

### OTT-22: Distinguish protective earth, chassis, circuit return, and isolation -- score 2
- Evidence: D5-BASIS.md:9-26 (cord PE to chassis/heatsink stud; J6 PE branch; R38 single removable functional bond; earthed-ELV domain); DECISIONS.md:161 (M14), DECISIONS.md:806 (item 20 dec.5: reserve PE test point, spare Y2, removable R38, current-probe window at next spin); my Dijkstra over the pe net of the 19b dump (appendix A): C3.2->J6.2 80.9 mm, C4.2->J6.2 74.6 mm of 0.2 mm track (F.Cu 49 mm straight run), net total 260 mm
- Rationale: Architecture is safety-first and RF returns are drawn; no choke/resistor in PE. Observation, not a score driver: the board Y1 caps (C3/C4) return to J6 through ~75-81 mm of 0.2 mm track (~45-80 nH, my estimate), versus 15 nH ESL in the model; sensitivity Y_caps_ESL_x3 and PE_bond_200nH both stay 10.5 dB at <=70 kHz, but above ~5 MHz this path limits the board Y caps (the module Y bond directly to PE). No safety verification or bond-impedance measurement.

### OTT-23: Make connector and cable paths part of the EMC model -- score 1
- Evidence: validation-results/06-controller-interface/README.md:1 and :80-84 (FAIL for integration; 'No cable part number, crimp/AWG choice, drawing or far-end mate' - native-17 audit); native-21 J4 pin map (J4.16 is now line_zc, not GND as the 06 table says); DECISIONS.md:260 (J4 lead 74 mm), DECISIONS.md:677 (J13 2xUL1007 292 mm, J11 2xUL1015 322 mm), DECISIONS.md:679 (453-573 uT rms coil field at PS3); README.md:116 (J3 TCO loop to off-board cutouts, mains-referenced); validation-results/07-conducted-emi/s19b/BENCH-PRECOMPLIANCE.md:20 (current probes only on PE, L, N)
- Rationale: Mechanism: the cables that dominate induction-cooker CM emission/pickup (coil leads J2/J5, J3 TCO loop to the glass/sink cutouts, J11/J13 blower leads, J4 harness) are not collected in one cable table with lengths, routing, returns, or CM-current modelling; the model carries only a lumped coil-to-PE C. The bench plan clamps only L/N/PE, not the coil leads or J4. Action: write a cable table (conductor, length, routing, return, shield), add clamp measurements on J2/J5 leads, J3, J4, J11/J13 to BENCH, and reserve the J2/J5 current-probe window as item 20 proposes.

### OTT-24: Terminate shields to a meaningful enclosure boundary -- score U
- Evidence: No shielded cable is specified: 06-controller-interface/README.md:83-84 (no cable assembly selected), DECISIONS.md:805 (coil-side electrostatic shield 'held in reserve' only)
- Rationale: Anchor: 'U = cable/shield choice absent'. Evidence needed: J4 harness drawing (shield or not), coil lead construction, backshell/360-degree bond to the sink/chassis, and an RF-vs-50/60 Hz loop analysis if any shield is adopted. Becomes NA only if the owner decides all cables are unshielded.

### OTT-25: Give each cable signal a nearby return -- score 1
- Evidence: section.kicad_pcb J4 pad nets (appendix A): row1 v15_selv, GND, v3v3, GND, pwm_ha, pwm_la, pwm_hb, pwm_lb; row2 permit, bus_fault, vbus_p, vbus_n, ct_zc, ct_mon, GND, line_zc (3 mm pitch; GND only at pins 2, 4, 15); native-21/BRINGUP-PROBES.md (pwm_lb/line_zc probed 'ground J4.2/J4.4/J4.15'); 06-controller-interface/README.md:80-84
- Rationale: Mechanism: 12 signal pins share 3 return pins and the pin order puts ct_mon (analog CT current monitor, 1 kOhm series only) directly across from pwm_la, line_zc across from pwm_lb, and ct_zc across from pwm_ha, with pwm_la having no ground neighbour in its row; over a 74 mm harness this is a crosstalk/CM-conversion path into the CT measurement and a larger radiating loop for the gate PWM. Action: harness definition with twisted pairs (pwm+GND, ct_mon+GND) and verify continuity schedule; if not feasible, re-pin J4 in the next spin (GND between PWM and analog) or add series R/shunt C at the receivers; check: ct_mon error with PWM running at 60 kHz on a mock harness.

### OTT-26: Analyze enclosure seams, apertures, and nearby metal -- score U
- Evidence: No enclosure seam/aperture/bond analysis in the power-stage tree (grep of DECISIONS.md/README.md/D5-BASIS.md finds only the PE-bonded sink and 8 mm barrier items); enclosure study 16 (coil-to-PE C) is quoted at DECISIONS.md:793 but its report is outside the pinned tree
- Rationale: Evidence needed: current enclosure revision (R43) material, seams/vents/aperture map near the coil and the board, bond straps, and an H-field seam scan. The 30 m field limit is mentioned (DECISIONS.md:480, seat ring closed) but no result is committed here.

### OTT-27: Filter susceptible inputs at the appropriate boundary -- score 1
- Evidence: elec/src/power_stage_120v.ato:81-82,391-392,673-676 (PWM_HA/LA/HB/LB straight from J4 to UCC21550 INA/INB, no series R/shunt C), :95-105 (PERMIT: 100 Ohm series + 100 kOhm pulldown only), :855-858 (CT_MON: 1 kOhm series, no capacitor); 06-controller-interface/README.md:80-84; FINDINGS.md:22 (F8 floating PWM pins on failed init)
- Rationale: Mechanism: J4 inputs/outputs have no RF/ESD diversion at the connector and no immunity data; a 74 mm harness picks up coil/switch-node fields and rectifies into comparator/driver inputs (PWM glitches -> shoot-through risk; CT_MON error). Latency budget (D-31 chain <=0.81 us) bounds how much filter is allowed. Action: footprint-reserve DNP 22-100 pF + series R at INA/INB/permit/ct_mon, then an RF/BCI injection on J4 with firmware event log; confirm UCC21550 input glitch filter against the PWM min pulse (datasheet not committed).

### OTT-28: Divert ESD current before it reaches sensitive ground -- score U
- Evidence: No ESD/IEC 61000-4-2 analysis anywhere in the tree (grep ESD/61000-4-2 over DECISIONS.md, README.md, D5-BASIS.md, elec/src/*.ato: no immunity hits); R38 is the single SELV-PE bond (D5-BASIS.md:9-14); no TVS on J4
- Rationale: Evidence needed: accessible-touch map of the enclosure (knob/front panel/service points), selected discharge levels and criterion, discharge path through R38/PE and J4, TVS or spark-gap placement, indirect-discharge test.

### OTT-29: Design surge/EFT protection as an energy and return-path network -- score 2
- Evidence: validation-results/08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/ALT-D3.md:95-114 (IEC 61000-4-5 combination-wave generator fit, 1.998 ohm source, 18 uF line coupling, RV1 power-law, CMC 18 uH; 1/2/4 kV DM: bus 439-488 V with Option A string; lab level 'still to be chosen'); validation-results/08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/ALT-D3.md:206-215; DC-LINK-CLAMP.md:53; owner-items/f1cc/F1-RECOMMENDATION.md:65 (12.2 A2s RV1 surge through F1); DECISIONS.md:331 (inlet fuse deleted); native-21/frozen/default.csv:4,60 (RV1 TMOV20RP175E; D3/D17 30KPA150CA)
- Rationale: Differential-mode surge is modelled with a fitted generator and part curves; fuse I2t coordination exists. Not covered: line-to-earth (CM) surge, EFT, ring wave, the inlet module's X caps/damper in the surge path, and the lab-selected level; D3/D17 sit 32 mm from C6 (254,106 vs 248,74). Capped at 2: no test; 'bench bus <=150 V until clamp qualified' (DECISIONS.md:437).

### OTT-30: Suppress relay/contact and inductive-load transients locally where applicable -- score NA
- Evidence: native-21/frozen/default.csv (93 BOM lines; grep for relay/contactor/solenoid/motor: none); README.md:116 (TCO cutouts are off-board, thermal bimetal in the PS2 mains input loop); DECISIONS.md:286 (blower is a self-commutated fan on a SELV supply, 'D-18(3)')
- Rationale: NA reason: topology has no board-switched inductive load. The coil is driven resonantly by the bridge; the blower is a brushless unit behind PS1/PS3; only the TCO contacts interrupt a (small, SMPS-input) mains current off-board. Revisit if a relay/contactor or an AC blower drive is added (D-31 contactor study is a vendor question, not in BOM).

### OTT-31: Treat harmonic current and flicker as separate mains questions -- score 2
- Evidence: validation-results/07-conducted-emi/flicker/README.md:1-25 (IEC 61000-3-3 Annex B screen with 230 V reference impedance as proxy; burst period >=2.5 s at 160 W, 20 s default); BUS-CAP-SCREEN.md:29-33 ('0.95 power factor is an assumed input'); owner-items/f1cc/F1-RECOMMENDATION.md:55-62 (plug-in at crest inrush 0.24-0.99 A2s, 145-396 A peak); validation-results/08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/ALT-D3.md:222 (re-validation list: PF and harmonics, inrush)
- Rationale: Topology (unfiltered bus, |sin| line current, no PFC) and inrush are analysed; flicker is screened by analytical method. Harmonic current content and the applicable US/CA/MX requirement are unassessed; the flicker method uses a 230 V lamp curve. Pending a power-analyser run and a 120 V flickermeter run.

### OTT-32: Measure cable common-mode current, then rescan all cables -- score U
- Evidence: No measurement exists (no hardware built). validation-results/07-conducted-emi/s19b/BENCH-PRECOMPLIANCE.md:20 plans current probes on PE, L and N only
- Rationale: Evidence needed: calibrated clamp sweeps on J2/J5 coil leads, J1 cord, J3, J4 harness, J11/J13, in the assembled enclosure with the production coil gap, background-off trace, repeat after each mitigation.

### OTT-33: Use near-field scans for localization, not far-field certification -- score U
- Evidence: No scan exists; BENCH-PRECOMPLIANCE.md has no H-field probe step (grep near-field/H-field: no hits)
- Rationale: Evidence needed: fixed-distance H-field scan fixture over commutation loops (C38-C41/FET row), L1/module, coil leads and seams for each switching state, with before/after A/B for any layout change.

### OTT-34: Run conducted-emission tests with a valid setup and mode separation -- score U
- Evidence: validation-results/07-conducted-emi/s19b/BENCH-PRECOMPLIANCE.md:1-46 (procedure only, pass line = limit - 6 dB) and README.md:151-165 (model PASS, nominal 10.5 dB, min 6.5 dB at X caps -20 %); DECISIONS.md:792-806; README.md:22 (Canada/Mexico/CISPR limits unverified)
- Rationale: Anchor: 'U = no test'. The model is predictive only below ~0.5-1 MHz; 1-30 MHz is covered by no prediction and no trace. Evidence needed: LISN-based L/N traces 9 kHz-30 MHz (peak prescan, QP/AV finals) in C1-C6 configurations incl. earthed-pan run, with LISN calibration and ambient-off trace; lab confirmation of the limit set.

### OTT-35: Verify immunity, functional behavior, and margin together -- score U
- Evidence: No immunity test plan or results in the tree; surge level unselected (ALT-D3.md:114), ESD none, RF injection none; fault chain timing is a ledger (FINDINGS.md:24 F10, 'chain timing awaits bench')
- Rationale: Evidence needed: selected test levels and acceptance criteria (with the certifier), injection points on mains/J4/coil leads, firmware event logs during ESD/EFT/surge/RF at max heating power, repeated on several units.

## Appendix A: queries run (read-only)

All run from the design tree; KiCad python = `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`; system python 3 with shapely 2.1.2 for the dump.

1. Identity: `shasum -a 256 /Users/bennet/Desktop/temper/worktrees/hw-baseline-guard/hardware/native21-stage19b/section.kicad_pcb` -> `b19a4553...0756662`.
2. Zones (OTT-10): `pcbnew.LoadBoard(section.kicad_pcb)`; for z in `b.Zones()`: net, layers, `GetIslandRemovalMode()`, `GetIsRuleArea()`. Result: 93 zones = 53 filled/net-assigned (mode 0 = always remove islands) + 40 unfilled rule areas with no net.
3. Positions (OTT-15) and J4 pad nets (OTT-09/25): `for f in b.GetFootprints(): print(ref, value, pos)`; `for p in J4.Pads(): p.GetNumber(), p.GetNetname(), pos`.
4. Copper geometry (OTT-02/05/09/12/17/22): load `native-21/verification/native21s19b-all-copper.json.gz` (keys `primitives[]` with kind zone/pad/track/via, net, layer, shell/holes/start/end/width_mm/centre/diameter_mm). Build shapely geometry per (net-set, layer) (`Polygon(shell, holes)`, `LineString(start,end).buffer(width/2)`, `Point(centre).buffer(d/2)`; vias on all four layers), then: `A[layer].distance(B[layer])` for same-layer gaps, `A[l1].intersection(B[l2]).area` for plan-view overlap, `A[l].buffer(w).intersection(B[l]).area / w` for parallel-run length, and a Dijkstra over the `pe` net's track endpoints for C3.2/C4.2 -> J6.2 (80.86 / 74.56 mm). Parallel-plate C = 8.854e-12 x eps_r x A / d with eps_r 4.3-4.4 and d from `native-21/stackup.json` (0.4355 mm F.Cu-In1, 1.49 mm F.Cu-B.Cu); switch-node displacement current = C x 170 V / 24-26.8 ns. Per-net track length sums (ct_s2 = 128.8 F + 64.8 B + 8.9 In1 = 202.5 mm, 32 vias).
5. EMI scenarios: python read of `validation-results/07-conducted-emi/s19b/results.json` -> minimum `margin_dB` per scenario (committed output; the 5-minute study script was not rerun).

Scratch files lived in the shared session scratchpad, which other agents overwrite; nothing from it is cited as evidence.

## Appendix B: committed, re-runnable scripts (each run once with `python3 -I`; every self-computed number above comes from these)

- `scripts/ott_copper_queries.py native-21/verification/native21s19b-all-copper.json.gz` (system python, shapely): OTT-17 gaps/overlap/0.269 pF, OTT-02/12 proximity table, SW_A over Kelvin (8.15 mm2, 0.71 pF, 5.0 mA), ct_s1/ct_s2 lengths (30.0 / 202.5 mm, 32 vias), J4 window copper (251.4 / 249.6 of 308 mm2), PE net (260.0 mm; C3.2/C4.2 to J6.2 = 80.86 / 74.56 mm).
- `scripts/ott_kicad_queries.py hardware/native21-stage19b/section.kicad_pcb` (KiCad python): zone island mode (53 filled, mode 0; 40 rule areas), C5/C6/Q/BR1/L1/J1/D3/D17 positions, J4 pad nets and coordinates (OTT-25 adjacency: pin n is across from pin n+8 at 3 mm).
- `scripts/ott_arith.py validation-results/07-conducted-emi/s19b/results.json`: 9.1 nF x 2pi x 60 Hz x 140 V = 0.480 mA; 7.0 pF x 170 V / 26.8 ns = 44.4 mA; minimum margin per scenario (nominal 10.5, module_DM_80uH 8.7, 18 uH-only -5.1, board-only -39.3, X caps -20 % 6.5, pan earthed 2.6/1.7, one-sided 100 pF -0.8 dB).
- Appendix A items 2-4 are superseded by these scripts. Distances quoted in OTT-15 (140-245 mm) are differences of the printed x positions.

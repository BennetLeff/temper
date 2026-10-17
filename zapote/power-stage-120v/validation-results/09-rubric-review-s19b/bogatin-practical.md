Identity check: verified with `shasum -a 256 /Users/bennet/Desktop/temper/worktrees/hw-baseline-guard/hardware/native21-stage19b/section.kicad_pcb` -> `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662` (matches the requested pin; the board_sha256 key inside `native-21/verification/native21s19b-all-copper.json.gz` and `native-21/verification/final-manifest.json` is the same value). Gerber ZIP `fab/native-21-gerbers.zip` also verified `c9eaf0d96091662cd25d0ef5a2d78e972f6123e1a1b4cb1c6d85804922e80ea3`.

# Bogatin practical rubric (BP-01..BP-28) scored against native-21 stage 19b

Reviewer: Claude (Sonnet 5.5), 2026-10-13, read-only desk review. Rubric: `docs/hardware/pcb-reference-rubrics-2026-10-13/bogatin-practical.md` (the rubric text names stage15b; the target here is the pinned 19b board). Scoring contract: 0 failed, 1 serious concern, 2 analysed but pending physical verification, 3 verified margin, U evidence absent, NA justified. No hardware exists, so 3 is unavailable for every criterion that needs a prototype.

`PS/` below means `/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/`. The tree's own `native-21/section.kicad_pcb` is an untracked, differently-hashed build artefact (sha256 f11c4b15..., 1.5 MB, not the pin), so I scored the pinned snapshot and evidence files that name board b19a4553 (manifest, copper dump, DECISIONS item 19b). Evidence for other stages is called out where used and judged against what changed per stage in DECISIONS.

## Tally

| Score | Count | IDs |
|---|---:|---|
| 0 | 0 | - |
| 1 | 6 | BP-03, BP-04, BP-07, BP-08, BP-14, BP-20 |
| 2 | 22 | BP-01, BP-02, BP-05, BP-06, BP-09, BP-10, BP-11, BP-12, BP-13, BP-15, BP-16, BP-17, BP-18, BP-19, BP-21, BP-22, BP-23, BP-24, BP-25, BP-26, BP-27, BP-28 |
| 3 | 0 | - |
| U | 0 | - |
| NA | 0 | - |

28 criteria scored. Not totalled into a readiness number (the rubric forbids it). There is no 0, no 3, no U and no NA: the 0 bar needs a violated applicable requirement and I did not find one that is not already waived by a recorded decision; the 3 bar needs a built board; every criterion had enough committed evidence to score.

## Independent checks I ran (read-only)

- `shasum -a 256 .../hardware/native21-stage19b/section.kicad_pcb` -> b19a4553... (identity).
- `kicad-cli pcb drc --format json --severity-all --schematic-parity --output <scratchpad>/drc19b.json <pinned board>` -> 0 violations, 0 unconnected, 0 schematic-parity (agrees with DECISIONS.md:790).
- Barrier recompute with shapely on `native-21/verification/native21s19b-all-copper.json.gz` (SELV set from `native-21/layout/domains.py`, NC-pad nets excluded; script `barrier2.py` in the scratchpad): min plan-view SELV-HOT 8.047 mm, PE-HOT 8.507 mm, RES_A to SELV/PE same-layer F.Cu 20.393, B.Cu 13.375, In1/In2 9.694 mm. Reproduces D5 8.047 / 8.507 and the stage-18 distances.
- Gap census (script `coupling.py`): switch-node (sw_a/sw_b/res_a/coil_feed) to victim nets; In1 Kelvin pour under F.Cu sw_a pour 4.69 mm2; ocp_ok_hot 3.49 mm from sw_b.
- Pour census: 63 fills; B.Cu sw_b 3307.9 mm2, F.Cu sw_a 1702.3, In2 bus_p 8079.2, In1 v3v3 8474.2, In2 selv_gnd 8503.8 (copper dump zones).
- Pad geometry: HF film cap pads to FET bus pins 25.0-28.16 mm (python math on dump pad centres); test-point pair distances 2.2-9.5 mm (pcbnew read of the pinned board, script `tp.py`).
- `grep -c '(gr_arc'` on the pinned board = 0 (sharp outline corners); `grep -o '(zone_connect [0-9])'` = 33 thermal, 1 solid.

## Findings (every 0, 1 and U)

There are no 0 and no U scores. Six criteria score 1.

### BP-03 - Qualify each exact MPN for its actual duty: 1
- **Mechanism:** Four exact parts carry an identified stress that has no worst-case proof. (a) F2 (Schurter UMT 3.15 A, blower tap) has a breaking capacity below the prospective fault current at 127 V + 10 %: a short beyond its rating can leave it arcing while the upstream F1 clears it. (b) The five-cap resonant bank is driven to 1702.4 V in the CT-failed double fault against a 1600 V DC rating, and TDK gives no single-event figure. (c) PS1/PS2 modelled case temperatures are 86.2/98.2 C against an 85 C ambient rating (-1.3 / -13.4 K) with an assumed path. (d) HF film caps C38-C41 sit 5.0 K below their 105 C category on an assumed lead path and heat from the FET-row copper. F1 (MDA-25-R) has a 10 kA rating only up to 125 Vac, and the 127 V corner is unbounded.
- **Evidence:** PS/DECISIONS.md:634; :160; :575-579; PS/validation-results/04-board-current-thermal/round5-native21/b3-convergence/README.md:71-75; PS/DECISIONS.md:715-721.
- **Proposed action:** Close with a short qualification table per part (rating, worst stress, source, margin): (1) get the building's prospective short-circuit current assumption written down, then either replace F2 by a fuse with a breaking rating above it or move F2 behind a current-limiting element, and get the certifier ruling; (2) send the TDK single-event overvoltage question (already an owner item) and decide whether to add a bank clamp; (3) measure local air at PS1/PS2 and C38-C41 by bench IR before any enclosure release, and pre-decide the move-or-uprate response (IRM-30 class) at a stated air temperature; (4) get the Bourns rating-basis answer.

### BP-04 - Verify value under operating bias, heat and tolerance: 1
- **Mechanism:** X7R/X5R MLCCs lose capacitance with DC bias, temperature and tolerance. The -1.6 V gate-bias rail that keeps the S4 hard-turn-on safe, and the driver local bulks, are verified at a generic -20 % allowance, while the committed record says the exact curves were not read and that the 0805 10 uF bulk's bias loss is not credited. If real effective C at 17 V is well below the allowance, the rail droop during the partner-edge window is larger than the 256-corner campaign assumed.
- **Evidence:** PS/native-21/ECO.md:51-55; PS/validation-results/08-manufacturing-package/native-21/bom-simplification/EQUIVALENCE.md:56-59; PS/DECISIONS.md:155; PS/DECISIONS.md:129.
- **Proposed action:** Pull the exact-MPN effective-capacitance-vs-bias-and-temperature curves (Murata SimSurfing, Samsung, TDK) for every ceramic in the F6 reservoirs, driver VDDA/VDDB bulks, RECOM output caps and the TPS7A47 caps; tabulate nominal -> effective at operating bias and -40/+85 C with tolerance; rerun `out-D33/rail_qualification.py` with those values (replace the generic -20 %). Add the result to ECO.md as the acceptance numbers, then bench-capture VSS-to-rail at the edge.

### BP-07 - Match package to assembly, repair and force: 1
- **Mechanism:** C5/C6 (48 mm tall, four-pin film), C21-C23 (26.5 mm axial, two leads), L1 and PS1/PS2 are heavy parts in a fan-cooled, handled appliance. Without adhesive, tie or bracket the weight and any shock load go into plated-through leads and the 2 oz pads, and cyclic flex can crack a joint or lift a pad; the review also noted no fixing within about 50 mm of C5/C6. Sharp outline corners (no arcs in the Edge.Cuts) are stress risers for depaneling and handling.
- **Evidence:** PS/validation-results/08-manufacturing-package/native-21/REVIEW-2026-10-08.md:142-144,300-303; PS/FOOTPRINTS.md:29-30; PS/ASSEMBLY.md:48; grep -c '(gr_arc' = 0 on the pinned board.
- **Proposed action:** Add a restraint callout (RTV/adhesive dot or cable-tie with anchor) for C5/C6, C21-C23, L1, PS1/PS2, T1 to the assembly drawing and FAB-NOTE.md; add a >= 1 mm inside and 0.5 mm outside Edge.Cuts radius (a copper-free change); decide a drop/vibration check (e.g. a 10-30 Hz sweep and a 0.5 m handled drop with the bank populated) for the first unit.

### BP-08 - Size every current path from worst-case heating and loss: 1
- **Mechanism:** Three different thermal limits are in play and none is declared the governing one. The task-04 plan accepts Joule-only copper rise <= 20 C above local board temperature; the converged model puts the FET-row copper-Joule field alone at 111.9-114.9 C with 50 C ambient at 28 A h25 (about 62-65 K above ambient; the row says 'local board temperature', so this comparison is indicative, not exact). The restated acceptance (DECISIONS item 21) uses laminate Tg 150 C (21 K margin), but the only laminate datasheet cited gives a 130 C maximum operating temperature for NP-155F, against a predicted 129.1 C copper peak at R5.4 (about 1 K), and the laminate JLC will use is unspecified. A continuous laminate temperature above its rating is a long-term insulation/delamination issue on the board that holds the HOT/SELV barrier. Everything is model-only; no bench IR.
- **Evidence:** PS/validation-results/04-board-current-thermal/round5-native21/b3-convergence/README.md:34,77-79; PS/validation-plan/04-board-current-thermal.md:112-114; PS/validation-results/08-manufacturing-package/native-21/sourcing/inquiries/CTI-JLC.md:37; PS/DECISIONS.md:148,152,808-826.
- **Proposed action:** Write the governing limit down as a requirement: decide whether the 20 K Joule-only rise row is waived for 28 A (record it) and which laminate maximum operating temperature applies (ask JLC for the UL file class and RTI/MOT of the specific laminate; choose TG155 or JLC-1/NP-155F in the order). Run the model at the shipped 22 A default and at 50 C and 40 C ambient to see the margin against 130 C. Make the bench IR of FET-row copper and R5.4 at 22 A and 28 A the gate for raising the ceiling (already listed as points 1 and 7 in the bench list).

### BP-14 - Review layer changes as two coupled transitions: 1
- **Mechanism:** When a 3.3 V logic signal changes layer and its reference plane changes between In1 v3v3 and In2 selv_gnd, the return current has to cross between planes. If no transfer capacitor or stitching via is near, the return takes a remote route, the loop grows and the field couples into neighbours. 19b fixed this for pwm_hb and ct_zc (all changes <= 2.72 mm) but pwm_ha and pwm_la (hot 60 kHz gate commands, same edge class as pwm_hb) change reference 7.59 and 5.11 mm from the nearest cap, and the permit and bias_* nets, which share the B.Cu fan with pwm_ha, have transitions 4-22 mm from any cap. Consequences: edge coupling from bias_bad/permit into pwm_ha and EMI from the larger loop; permit is the interlock line to the gate drivers.
- **Evidence:** PS/validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.txt:7,8,10,17 (and :5-6 for the fixed signals); PS/native-21/layout/gates/return_path19.py docstring; PS/DECISIONS.md:788-789.
- **Proposed action:** Extend `return_path19.py` to assert pwm_ha, pwm_la and permit (<= 3.0 mm to a transfer cap or a stitching via at each reference change), then close the gap the way 19b did for pwm_hb: a 100 nF v3v3-selv_gnd cap with its own plane vias beside each change, or a re-route that keeps pwm_ha/la over one plane. For bias_bad, either move it to F.Cu as 19b notes or add the ~6 caps, or record the analytic bound on the loop it creates and its coupling into pwm_ha. Bench: capture pwm_ha/permit victim waveforms with bias_bad toggling.

### BP-20 - Match stackup to routes, returns, voltage domains and fab: 1
- **Mechanism:** The creepage and clearance numbers (8.0 mm HOT-SELV, 12.6 mm RES_A, 5.0 mm tank) assume laminate material group IIIa (CTI >= 175 V). JLC's raw stackup API names no laminate, the NP-155F label comes from a third-party repository, and JLC's order default is an unspecified TG135-140 FR-4. If the delivered laminate were group IIIb the distances are invalid above 50 V working voltage (IEC 60335-1 Table 17 footnote cited in D5-BASIS). Separately, finished thickness could land at 1.44 mm, below the 1.6 mm minimum of the REDCUBE THR studs that carry the tank current.
- **Evidence:** PS/native-21/stackup.json:3; PS/validation-results/08-manufacturing-package/native-21/sourcing/inquiries/CTI-JLC.md:8-13; PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:31,33.
- **Proposed action:** Send the drafted CTI inquiry (CTI-JLC.md, still 'draft, not sent') and add the thickness question; place the order with an explicit material (FR-4 TG155, UL class JLC-1 / Nan Ya NP-155F if the flow allows) and obtain JLC's written confirmation of the laminate, its CTI/PLC document and finished thickness (+/-) before ordering. Replace stackup.json's 'designed to' status with the fab's signed stackup and keep both in the manifest.

## Watch list: scored 2 but fragile

These are not 0/1/U, but each is a place where the 2 rests on a stale basis, an unmet layout rule, or an unchecked mechanism.

- **BP-11 (2, stale basis):** The FEM behind the loop verdict is the coarse/provisional stage-6 native-21 matrix (leg A 24.9 -> 37.6 nH, L5 'at least as tight as native-19' waived). Stages 15/15b/17/19 changed copper near the loop (SW_A/SW_B widening, R5 land span 8.26 -> 7.0 mm) without re-extraction, and the a21corr/campA21 runs that FAB-NOTE.md:13 makes a pre-order gate are not recorded as landed. S4 die VDS 470 V vs 520 V (50 V) exists only with F6. Action: land the fine extraction on b19a4553 copper and rerun the 252 cases; if VDS margin < 30 V use the SMD C0G bus decoupler lever recorded at DECISIONS.md:144.
- **BP-10 / BP-12 (2):** The Kelvin return rule L4 (lead <= 50 mOhm, or star return) is not met: R35.2 sits 158.08 mOhm above R5.2 and all returning supplies share that lead (U4.3 transfer 153.5 mOhm). The budget is DC only; AMC1311 modulator and comparator edge currents on a ~140 mm return are not estimated. Margin to the trip floor is 3.5 A. Action: a 20-50 MHz small-signal estimate of the lead (L about 0.5-1 nH/mm) against the OCP_NODE filter, or move AMC1311/ISO7710 returns to a separate pad on R5.2's finger as the L4 text offers.
- **BP-15 (2):** No estimate of dv/dt capacitive injection from SW_A/SW_B into ocp_ok_hot (3.49 mm from sw_b, 14.7 mm of track within 6 mm), hot5_uv_raw (3.9 mm from sw_a) or the Kelvin pair (3.7 mm from sw_b; In1 Kelvin pour under the F.Cu sw_a pour, 4.69 mm2). The magnetic pickup study (stage 13b) predates the stage-19 Kelvin/bus_fault_hot re-lay. Action: a two-line Cdv/dt check per victim, and rerun coil-pickup/run_loops.py on 19b copper.
- **BP-28 (2, conditional):** Depends on BP-20 (laminate group), the certifier's same-layer inner-path ruling (C152 inner rings 9.694 mm from SELV islands, DECISIONS.md:756), IEC 60664-4 distances above 30 kHz (D5-BASIS.md), and T1's missing HF/CTI/PD rating (Coilcraft). Gates already listed at FAB-NOTE.md:17-22.
- **BP-06 / BP-27 (2):** 47 CPL lines (28 of them SOT-23 family) still NEEDS-PREVIEW and R5's project land has not been compared to JLC's C4175647 footprint; both are cheap to close in JLC's preview before ordering (cpl-rotation-audit/README.md:15-32; FAB-NOTE.md:58).
- **BP-16 / BP-17 (2):** Long return legs remain (U29-U31 returns 7.3-7.6 mm, AMC1311 C149 about 27 mm, LS bulks 16 mm) with no asserted limit on the return side, and no explicit anti-resonance plot between C38-C41 and C5/C6.
- **BP-09 (2):** R5 shunt vias run up to 8.78 A each at the 34 A coherent case with no per-via acceptance limit (flag only, 10 of 18 flagged). Action: set a limit (barrel I^2R and temperature with the real plating minimum) and include the vias in the bench IR list.

## Per-criterion rationale

### BP-01 - Define the function and risk before geometry: **2**
Operating envelope, fault bands, failure consequence (S4 shoot-through, D-31 turn-off) and a plan exist and were reviewed; nothing is measured and the coil/pan basis is assumed. Some records lag 19b: 01/STATUS.md:8 stops at the stage-6 FEM, and 06-controller-interface/README.md is a native-17 audit with a FAIL verdict. No hardware, so 2 is the ceiling.

Evidence: PS/DECISIONS.md:152 (tank <= 22 A RMS envelope, owner-approved); :548-579 (item 13: 28 A ceiling, OCP band 68.58-118.74 A, floor 64.17 A); :509 (item 10: yield study on an 'ASSUMED basis: no measured coil or pan'); PS/RELAYOUT-REQUIREMENTS.md:22-23 (L4/L5 rows); PS/validation-plan/00-MASTER-PLAN.md; PS/validation-results/01-switching-parasitics/FINDINGS.md:16-39 (risk register with status).

### BP-02 - Classify nets by the harm their parasitics can cause: **2**
Each family has its own method: isolation groups in the DRU, tank copper (task 04), Kelvin budget (02/kelvin), loops by FEM (01), return-path and bypass gates. There is no single net-class table and KiCad carries one Default class, so the classification lives in scripts, and only three fast signals are asserted. Predicted margins exist; no waveforms.

Evidence: PS/native-21/layout/rules21.py:1-60 (SELV/PE-vs-HOT 8.0, tank 5.0, HOT potential groups 3.2, RES_A 12.6 outer); PS/native-21/section.kicad_dru:5-27 (6 rules); hardware/native21-stage19b/section.kicad_pro net_settings.classes = ['Default'] only (python json read); PS/native-21/layout/gates/return_path19.py docstring (asserts pwm_hb, ct_zc, bus_fault_hot; 'other fast signals are reported, not asserted'); PS/validation-results/07-conducted-emi/s19b/README.md (edge times from D-19 census, 24-27 ns 10-90 %).

### BP-03 - Qualify each exact MPN for its actual duty: **1**
Most critical MPNs are datasheet-checked and frozen (357 parts, audit 80/80), but at least four exact parts have an identified stress without worst-case proof: F2 fault duty, bus-cap single-event overvoltage, PS1/PS2 ambient rating, and HF film caps at 5 K margin on an assumed lead path. No sample or representative test exists, and the vendor answers (Bourns, TDK, certifier) are not obtained. 1 until those are closed.

Evidence: PS/DECISIONS.md:634 (F2 Schurter UMT breaking capacity 'under the prospective fault at 127 V + 10 %'; F1 only a backup; certifier item); :160 (F1 MDA-25-R 10 kA only <= 125 Vac, 1.5 kA at 250 V); :575-579 (bank TDK B32654A1104K000: 1702.4 V single-event vs 1600 V DC rated, TDK gives no figure); PS/validation-results/04-board-current-thermal/round5-native21/b3-convergence/README.md:71-75 (C38-41 5.0 K to 105 C; PS1 -1.3 K / PS2 -13.4 K against an 85 C ambient rating; film-cap and IRM class values 'assumed'); PS/DECISIONS.md:715-721 (Bourns CSS2H rating basis, element-to-terminal Rth open); PS/validation-results/01-switching-parasitics/FINDINGS.md:16 (S4 diode recovery WAITING). Positive: PS/DECISIONS.md:790 (audit.rs 80/80, verify_source 357 parts).

### BP-04 - Verify value under operating bias, heat and tolerance: **1**
Resistor and reference corners are done well (REFERENCE-BIAS, band calc with 75 ppm/C R5). Ceramic effective capacitance, which sets the -1.6 V gate-bias rail that guards S4, rests on a generic -20 % allowance and on 'to be read' curves, not on the exact MPN at bias, temperature and tolerance. That is nominal-plus-allowance, so 1.

Evidence: PS/native-21/ECO.md:51-55 (driver-bank 'effective minima' are acceptance conditions; 'obtain the selected MLCC curves and verify ... before release'); PS/validation-results/08-manufacturing-package/native-21/bom-simplification/EQUIVALENCE.md:56-59 (ceramic DC-bias derating 'not in the listings'; Samsung 0402 curve 'should be read'); PS/DECISIONS.md:155 (10 uF 0805 c_hs_bulk: 'DC-bias capacitance loss at the rail voltage is not credited'); PS/DECISIONS.md:129 (rail model uses a generic -20 %/DC-bias corner). Positive: PS/REFERENCE-BIAS.md (REF25 corner calc, 0.1 % strings, LM4040 80 uA floor); PS/validation-results/02-protection-timing/kelvin/budget-native21s19b.md:14.

### BP-05 - Make alternatives genuinely interchangeable: **2**
Substitutes are compared on spec, stress and circuit effect by committed scripts, with the worse attributes argued rather than ignored. Desk qualification only: no assembled substitution and the stock snapshot is partial (Mouser, Newark, Arrow, TTI unreadable per ALTERNATES). 2.

Evidence: PS/validation-results/08-manufacturing-package/native-21/sourcing/ALTERNATES-2026-10-09.md (blocked-part alternates, lot quantities, stock caveats); PS/validation-results/08-manufacturing-package/native-21/bom-simplification/EQUIVALENCE.md:1-50 (equivalence.py: 357 parts / 218 nets unchanged, 124 MPN swaps all on the reviewed list; spec_dominance.py 25 pairs x 147 attributes, 12 worse attributes each with a circuit reason); PS/validation-results/08-manufacturing-package/native-21/sourcing/README.md.

### BP-06 - Tie symbol, footprint and physical sample to one part: **2**
Independent drawing-to-library checks exist for the authored footprints and the new R5 land, and netlist/pin parity is gated (audit 80/80). No physical sample or 1:1 print, and 47 CPL lines (28 SOT-23 family) have unresolved rotation/polarity. 2.

Evidence: PS/FOOTPRINTS.md (F1-F10 checked against cited drawings; 'PROVISIONAL' on pitch/restraint for CDE, TMOV, MRT130KP); PS/DECISIONS.md:686 (item 17: R5 CSS2H land measured from datasheet p.2 at 600 dpi, net-tie fingers); PS/DECISIONS.md:720 (JLC placement preview of C4175647 on the project land still open); PS/validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/README.md:15 (280 OK / 10 corrected / 47 NEEDS-PREVIEW); PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:58.

### BP-07 - Match package to assembly, repair and force: **1**
Connectors and studs have a considered process (THR reflow, 4-spoke reliefs, preheat for rework). The heavy radial/axial parts (C5/C6 are 48 mm tall four-pin film caps; C21-C23 on two leads) have no restraint callout in the fab/assembly package, the review's m9/m13 are not shown closed, and no vibration or shock check exists. Plausible but unproven, so 1.

Evidence: PS/validation-results/08-manufacturing-package/native-21/REVIEW-2026-10-08.md:142-144 (m9: C21-C23, C5/C6, L1, PS1/PS2 'unrestrained ... fan-cooled appliance'; fix = adhesive/RTV/tie callout); :300-303 (no fixing within ~50 mm of C5/C6; mains and coil-lead strain relief; m13 sharp outline corners); PS/FOOTPRINTS.md:29-30 ('heavy capacitors require adhesive or a strap'); PS/ASSEMBLY.md:48 (no vibration-proof claim); hardware/native21-stage19b/section.kicad_pcb: 0 gr_arc / 6 gr_line (grep -c). PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md has no restraint callout (grep adhesive|RTV|strap|retention). Positive: FAB-NOTE.md:51-57 (lead trim, THR reflow, hand-rework preheat).

### BP-08 - Size every current path from worst-case heating and loss: **1**
Path resistances, necks and a converged thermal model exist at 28 A. But the accepted limit changed without a record: the plan's own 20 K Joule-only rise row is exceeded about 3x by the model at 28 A (measured against 50 C ambient; the row says 'local board temperature', so indicative), the limit used is Tg 150 (21 K margin), and the only laminate datasheet cited gives MOT 130 C against a 129 C predicted copper peak. Which limit governs is undecided, and the laminate itself is unspecified (BP-20). Model-only, no bench IR. 1.

Evidence: PS/validation-results/04-board-current-thermal/round5-native21/b3-convergence/README.md:34 (copper-Joule field alone peaks 111.9/114.1/114.9 C in the FET-row copper at 28 A, h25, 50 C ambient: ~62-65 K rise); :77-79 (board copper peak 129.1 C at R5.4; limit used = laminate Tg 150); PS/validation-plan/04-board-current-thermal.md:112-114 (acceptance: Joule-only copper rise <= 20 C above local board temperature); PS/validation-results/08-manufacturing-package/native-21/sourcing/inquiries/CTI-JLC.md:37 (NP-155F datasheet MOT 130 C; laminate not actually specified); PS/DECISIONS.md:148,152 (22 A ceiling set by the 20 K IPC width screen); :808-826 (item 21). PS/validation-results/04-board-current-thermal/round5-native21/README.md:59-66 (SW_B 7.4 mOhm, 2.6 W at 18.7 A). Model controls: README.md:8 (C1-C3 pass).

### BP-09 - Treat via and pad transitions as path bottlenecks: **2**
Via barrels, shunt pads and tank necks are modelled with filled-via plating-only resistance and tied to a thermal solve; the R5 via defect was found and fixed. The weakness is the acceptance rule: no per-via current or temperature limit exists (flag only), and the 18 um plating is an assumption until a cross-section or bench IR. 2, not 3.

Evidence: PS/validation-results/04-board-current-thermal/round5-native21/README.md:28-40 (R5 shunt vias: 18.1 A -> 7.27 A worst via after stage-6 fix); PS/DECISIONS.md:736-741 (stage 17b: worst R5 HV_RET via 8.78 A at 34 A coherent, 7.59 A at the 29.4 A trip, barrel 0.029 W / 0.28 K, 10 of 18 vias > 3 A); PS/validation-plan/04-board-current-thermal.md:114 ('> 3 A is a flag, not a fail; there's no rated limit'); PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:38 (all 0.3 mm vias POFV; ten 1.6/0.8 current vias tented); PS/DECISIONS.md:548-612 (SW_A/SW_B neck widening, FET-row corner fills).

### BP-10 - Calculate DC drop and sense error along the real return path: **2**
A full DC budget exists against a stated floor, with reciprocity solve of the sheet copper and an independent track-bound check, re-run each stage including 19b. Margin is 3.5 A (about 5 %) and the L4 layout rule (<= 50 mOhm, or star) is not met: 158 mOhm, and U4.3 (AMC1311) transfers 153.5 mOhm into the same node. Transient/HF returns are explicitly not bounded. 2.

Evidence: PS/validation-results/02-protection-timing/kelvin/budget-native21s19b.md:14 (13.648 mA returned, 2.09 mV at R35.2, trip shift -2.167 A); kelvin/README.md:96-98 (stage 19/19b: R35.2 158.08 mOhm, band 67.72-116.44 A, floor 64.17 A met at the bound); kelvin/README.md:36 ('DC only'); PS/DECISIONS.md:702 (band 67.72-116.44 A, floor 64.17 A met +3.49 A), :781 (re-solved on stage 19); PS/RELAYOUT-REQUIREMENTS.md:22 (L4: lead <= 50 mOhm or star return).

### BP-11 - Trace each fast power loop and its return: **2**
Loops are drawn, extracted (4-port FEM) and run through SPICE decision cases, which is real analysis. But the matrices are coarse/provisional on stage-6 copper, the corrections never landed in the record, later stages (15b, 17, 19) changed copper near the loop without re-extraction, and the loop is 51 % larger than the L5 rule allowed (waived, DECISIONS.md:144). S4 margin is 50 V and exists only with F6. 2 on a stale basis; see Watch list.

Evidence: PS/native-21/FLOORPLAN.md:21 (leg A parallel loop 24.9 -> 37.6 nH, leg B 29.1 -> 24.5 nH); PS/validation-results/01-switching-parasitics/FINDINGS.md:39 (M11 OPEN: provisional matrices, 252/252 cases under F6); PS/DECISIONS.md:144 (S4 die VDS 470 V vs 520 V limit, S2 446 V vs 585 V; without F6 S4 reaches 550 V); :709 (stage 17 R5 land change not re-extracted); PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:13 (a21corr/b21corr must land before ordering); PS/RELAYOUT-REQUIREMENTS.md:23 (L5: 'at least as tight as native-19'). My geometry, python math on native-21/verification/native21s19b-all-copper.json.gz pad centres: C38.1 to Q2.2 25.0 mm, C39.1 to Q2.2 28.16 mm, C40.1 to Q5.2 27.9 mm, C41.1 to Q5.2 25.15 mm.

### BP-12 - Keep sensitive return currents out of shared narrow segments: **2**
The one critical shared segment (the R5.2 lead) was identified, quantified and budgeted per returning pad, and the gate-bias recharge path is kept off it. Sharing is not limited: every returning supply uses the same lead, and AC/HF currents on it (AMC1311 modulator, comparator edges) are not estimated. 2.

Evidence: PS/validation-results/02-protection-timing/kelvin/budget-native21s19b.md:1-14 (every HOT-side supply return shares the R5.2 lead: 148.96-153.54 mOhm transfer at 11 pads); kelvin/README.md:36 (DC only); PS/validation-results/02-protection-timing/coil-pickup/PICKUP.md:3-9 (shared-loop pickup <= 0.6 A equivalent at any instant); PS/DECISIONS.md:702 (floor 64.17 A met by 3.49 A); PS/native-21/ECO.md:65-67 (HOT5 LDO ground to R5.2; no bias recharge through the Kelvin island).

### BP-13 - Preserve a nearby uninterrupted return for fast signals: **2**
The 60 kHz-class signals (pwm_ha/la/hb/lb, ct_zc, bus_fault_hot) sit over a legal plane or coupled return along their whole route. Two safety-related low-rate nets (permit, bias_bad) have multi-mm runs with no reference copper at all, accepted by argument. Reference-plane gaps are shown in geometry for the critical set, so 2; the transitions are scored under BP-14.

Evidence: PS/validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.txt:1,5-8 (bus_fault_hot, pwm_hb, ct_zc, pwm_ha, pwm_la: 0 samples over another net, longest unreferenced run <= 1.25 mm); :10 (permit longest unreferenced run 6.0 mm); :17 (bias_bad 22.25 mm); PS/DECISIONS.md:789 (bias_bad left, argued fail-safe); PS/native-21/stackup.json:3,9-45 (F/In1 0.4355/In2/B, In1 v3v3 8474 mm2 and In2 selv_gnd 8504 mm2 in SELV region by my zone census of native21s19b-all-copper.json.gz).

### BP-14 - Review layer changes as two coupled transitions: **1**
pwm_hb and ct_zc get transfer caps within 3 mm. The sibling gate commands pwm_ha/pwm_la (same 60 kHz-class 3.3 V edges, running beside the permit/bias_bad B.Cu fan) change reference with the transfer cap 5-8 mm away, and permit and bias_* are 12-22 mm away. Their return is assumed to find a remote route. 1 until analysed or closed.

Evidence: PS/validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.txt:7 (pwm_ha: reference change at (75.9,56.3), nearest v3v3-selv_gnd cap C54 7.59 mm); :8 (pwm_la: C54 5.11 mm); :10 (permit: 5 transitions, nearest cap 4.33, 5.88, 6.94, 12.21, 20.89 mm); :17 (bias_bad: 7 transitions, nearest cap 2.81-15.76 mm); PS/native-21/layout/gates/return_path19.py docstring (SI2 asserts only pwm_hb <= 3.0 mm and ct_zc; 'other fast signals reported, not asserted'); PS/DECISIONS.md:788-789 (19b closes pwm_hb only; bias_bad left, recorded). Positive: return-path19b.txt:5-6 (pwm_hb and ct_zc every change <= 2.72 mm from a transfer cap).

### BP-15 - Keep unrelated fast aggressors away from quiet victims: **2**
Magnetic pickup from the coil is quantified for the sense loops and the geometry keeps the OCP node/threshold nets >= 8 mm from switch nodes. Capacitive dv/dt injection from SW_A/SW_B (SW_B B.Cu pour is 3308 mm2) into the nearer HOT5/ok/Kelvin nets is not estimated, and the pickup study predates the stage-19 Kelvin/bus_fault_hot re-lay. Failures in the ok-line direction are nuisance trips. 2.

Evidence: PS/validation-results/02-protection-timing/coil-pickup/PICKUP.md:3-9,33 (magnetic pickup of Kelvin/CT/LINE_ZC loops, stage 13b: OCP shift <= 0.6 A, 0.3 A margin left in the harshest stack); my gap census (scratchpad coupling.py on native21s19b-all-copper.json.gz): ocp_ok_hot 3.49 mm from sw_b on B.Cu (14.7 mm of its 20.6 mm track within 6 mm), hot5_uv_raw 3.9 mm from sw_a, ocp_kelvin_p/n 3.7 mm from sw_b and 4.84 mm from sw_a, In1 Kelvin pour overlaps F.Cu sw_a pour by 4.69 mm2, ocp_node/ocp_thresh >= 8.4 mm; PS/validation-results/08-manufacturing-package/native-21/stage19-pi-si/return-path19b.txt:1 (bus_fault_hot referenced to the Kelvin return).

### BP-16 - Place local bypass by total loop, not centroid distance: **2**
Both sides of each loop are measured by committed gates, and the gate-drive loops are inside the FEM. Several loops are still long (U29-U31 returns 7.3-7.6 mm, C149 about 27 mm, LS bulks 16 mm) with no limit asserted on those return sides. No pin-level rail waveform; 2.

Evidence: PS/validation-results/08-manufacturing-package/native-21/stage19-pi-si/bypass-check-native21s19b.txt:1-11 (11/11 PASS; supply sides 1.70-4.38 mm, return sides 2.12-7.61 mm, plane vias up to 6.18 mm); PS/validation-results/08-manufacturing-package/native-21/stage19-pi-si/pi19b.txt:1-7 (U41/U42/U26 pad-to-cap 1.61-2.93 mm supply, 2.81-6.97 mm return); PS/DECISIONS.md:155 (VDDA/VDDB 100 nF at 4.3 mm, 10 uF at 7.9/8.6 mm; LS 10 uF bulks ~16 mm); PS/validation-results/08-manufacturing-package/native-21/REVIEW-TRIAGE.md:72-79 (C149 1 uF loop ~27 mm recorded as compromise); PS/validation-results/01-switching-parasitics/round17/native21-setup/README.md (gate loops closed through the bias caps in FEM).

### BP-17 - Select decoupling as an impedance network: **2**
The gate-bias rail is designed as a damped network and verified over 256 corners. For the DC bus the bulk film path is only tested with a 5-port perturbation and I found no explicit anti-resonance plot between C38-41 (100 nF, 1.06 nH) and C5/C6; mounted ESL is bench-only. 2.

Evidence: PS/validation-results/01-switching-parasitics/round17/delegation/out-D33/README.md:93 (loop gain, phase margin 51.62 deg; effective capacitance and ESL stay bench conditions); PS/validation-results/08-manufacturing-package/native-21/bom-simplification/EQUIVALENCE.md:43-44 (256/256 periodic corners, worst -1.898 V; hot load 128/128); PS/native-21/ECO.md:42-55 (ceramic + 220 uF polymer through 0.68 Ohm damping); PS/validation-results/01-switching-parasitics/FINDINGS.md:17 (F3 5-port bulk path +-0.3 V), :34 (M4 ESL 1.06 / 19.2 nH).

### BP-18 - Separate source filtering from local transient supply: **2**
Source-side filtering (inlet module, board filter, LDOs) and load-side bulk are treated as separate mechanisms with calculations, and the sensitive reference/Kelvin node has a corner analysis. There is no rail-noise budget for AMC1311/HOT5/comparator supplies, and the RECOM module's spread-spectrum noise is an open bench item. 2.

Evidence: PS/REFERENCE-BIAS.md (REF25 corner current 273.5 uA vs 120.8 uA at LM4040, 80 uA floor); PS/validation-results/08-manufacturing-package/native-21/stage19-pi-si/pi19b.txt:1-7 (converter-local caps per RECOM p.13 / TI SBVS204 9.1); PS/DECISIONS.md:449-452 (RECOM U41/U42 10-16 MHz spread-spectrum emissions and module startup open, bench); PS/validation-results/07-conducted-emi/s19b/README.md:4 (line-side filter study, INCONCLUSIVE then PASS item 20, PS/DECISIONS.md:792-795).

### BP-19 - Evaluate copper pours by function and boundary: **2**
Every fill belongs to a declared net with a declared winner, orphan pieces are gated (DRC unconnected 0), and the large switch-node pours are costed for EMI and heat. There is no single table stating each pour's role (return, power, spreader), and SW_B's 3308 mm2 pour is a deliberate large dv/dt surface whose chassis capacitance is assumed. 2.

Evidence: PS/DECISIONS.md:726-727 (zone_priority_gate: 25 contested pairs, 0 at equal priority; three builds agree within 0.038 mm2/net); native21s19b-all-copper.json.gz zone census (my python): 63 fills, e.g. B.Cu sw_b 3307.9 mm2, F.Cu sw_a 1702.3, In2 bus_p 8079.2, In1 hv_ret 4959.2 + 3526.6, In1 v3v3 8474.2, In2 selv_gnd 8503.8; PS/validation-results/07-conducted-emi/s19b/README.md:47 (switch-node pour area to chassis 1.1/1.95 pF, ASSUMED); PS/validation-results/04-board-current-thermal/round5-native21/b3-convergence/README.md:34 (pours included in thermal).

### BP-20 - Match stackup to routes, returns, voltage domains and fab: **1**
The 4-layer allocation (In1 HV_RET / In2 BUS_P at the core, v3v3 / selv_gnd in the SELV band) suits the loops and the plan-view barrier is enforced on all layers. But the whole 8.0/12.6 mm creepage basis assumes laminate group IIIa, and the stackup is a third-party capture with an assumed laminate. Neither CTI nor finished thickness is confirmed by the fab, so a serious open requirement remains. 1.

Evidence: PS/native-21/stackup.json:3 ('Thicknesses from ... gsuberland/jlcpcb_autogenerated_stackups'; laminate named 'Nan Ya NP-155F ... JLCPCB may substitute KB or Shengyi, so the CTI must be confirmed'); PS/validation-results/08-manufacturing-package/native-21/sourcing/inquiries/CTI-JLC.md:8-13 (the NP-155F label is the third-party repo's assumption; JLC's order default is 'FR4-Standard TG 135-140', material unspecified; inquiry 'draft, not sent'); PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:31 (finished thickness 1.6-1.76 mm, REDCUBE studs need 1.6-2.0 mm, JLC +-10 % allows 1.44 mm), :33 (CTI >= 175 'hard order condition'); PS/DECISIONS.md:756 (inner layers treated as solid insulation).

### BP-21 - Protect solderability without sacrificing electrical purpose: **2**
Relief-versus-solid is chosen per net on current and heat duty, with the assembly route (THR reflow, hand-solder with preheat) stated. No reflow profile, joint inspection or temperature test exists yet. 2.

Evidence: PS/native-21/layout/pad_reliefs21.py:1-26 (0.5 mm x 4 spokes on low-current THT pads; power nets SOLID); hardware/native21-stage19b/section.kicad_pcb: 33 pads with (zone_connect 1), 1 with (zone_connect 2) (grep -o); PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:57 (REDCUBE THR reflow; power pins solid; rework only on a >= 100 C preheated board); PS/validation-results/08-manufacturing-package/native-21/REVIEW-TRIAGE.md:19-20 (M3).

### BP-22 - Review board-edge placement and physical service access: **2**
A solid-model all-pairs fit check plus lug/barrier studies support the fit, and connector sides were decided. Gaps are approximations for a few parts (R5, F2, PS3) and no physical mockup. 2.

Evidence: PS/DECISIONS.md:790 (fit 409 solids / 0 overlaps / 411 bodies / 0 hits, R4); :700 (R5 modelled as a 0.78 mm envelope, no 3D model); :636 (F2 height a 4.0 mm estimate); :659 (PS3 DC-block margin 1.0 mm from a drawing-scaled block); PS/native-21/FLOORPLAN.md:21-36 (zones, connector edges); PS/ASSEMBLY.md:52-58 (J2/J5 lug constraints from R26); PS/validation-results/08-manufacturing-package/native-21/REVIEW-2026-10-08.md:295-300 (J4/J6 location decision, mains and coil strain relief).

### BP-23 - Verify DRC, schematic intent and artwork independently: **2**
Reproduced the headline gates myself with different code, and the package has an independent gerbv/hole review and a negative control. The DFM check is the repo's own script, not a JLC response, and 47 CPL lines are still NEEDS-PREVIEW (BP-06). 2.

Evidence: My run: kicad-cli pcb drc --format json --severity-all --schematic-parity on hardware/native21-stage19b/section.kicad_pcb gave 0 violations / 0 unconnected / 0 parity (scratchpad drc19b.json); my barrier recompute (scratchpad barrier2.py on native21s19b-all-copper.json.gz): min SELV-HOT 8.047 mm, PE-HOT 8.507 mm, RES_A to SELV/PE 20.393 (F.Cu) / 13.375 (B.Cu) / 9.694 (In1, In2) mm; PS/validation-results/08-manufacturing-package/native-21/README.md:24-40 (gerbv independent render, hole/mask/silk review, JLC rules script); PS/DECISIONS.md:790 (audit.rs 80/80, Rust barrier gate 0 over 5,829 items); PS/validation-results/08-manufacturing-package/native-21/REVIEW-2026-10-08.md, REVIEW-TRIAGE.md (independent pre-fab review: 2 blockers, 14 majors closed or decided).

### BP-24 - Provide intentional probe points and references: **2**
Test points are bare pads with a nearby reference pad per domain, isolation warnings, and a D-8 procedure with instrument limits. There is no per-pad expected range column, bridge-level nodes (VDS, bus, tank current) rely on lead adapters, and the D-8 plan was written on native-17. 2.

Evidence: PS/native-21/BRINGUP-PROBES.md:15-35 (21 signal pads each with a ground pad; FET VGS/VDS at TO-247 leads by D-8 adapters); my pair distances from the pinned board (scratchpad tp.py, pcbnew): all 21 signal-to-ground pad pairs 2.2-9.5 mm (limit written as <= 10 mm); PS/validation-results/01-switching-parasitics/round17/delegation/out-D8/README.md:70-103 (current ladder, shot limits, abort rules); PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:40 (36 bring-up pads).

### BP-25 - Make staged bring-up and fault isolation possible: **2**
Staged energisation, removable power links and a stepped current ladder with abort rules are written. Stop conditions and current limits are not tabulated for every step of the 19b sequence (PROTOTYPE-LOT is a summary) and nothing has run. 2.

Evidence: PS/ASSEMBLY.md:74-107 (J7-J10 removable straps, floating 30-60 V bench bus, continuity checks); PS/validation-results/08-manufacturing-package/native-21/PROTOTYPE-LOT.md:46-60 (5-step sequence: bare board, logic/bias, gate drive with no bus, stepped current-limited bus, resonant at 22 A ceiling); PS/native-21/BRINGUP-PROBES.md; PS/validation-results/01-switching-parasitics/round17/delegation/out-D8/README.md:70,103; PS/validation-results/07-conducted-emi/s19b/BENCH-PRECOMPLIANCE.md:3.

### BP-26 - Define what a pass means and retain the evidence: **2**
Tests have stimuli, instruments, predicted values and numeric bounds, tied to board identity in several places, but none has been run. 2 by definition.

Evidence: PS/validation-results/07-conducted-emi/s19b/BENCH-PRECOMPLIANCE.md:3-10 (limit - 6 dB pass line, configurations, instruments); PS/validation-results/01-switching-parasitics/round17/delegation/out-D8/README.md:99-103 (VDS <= 520 V, off-gate < 3.0 V / 1.9 V hot, abort rules); PS/validation-plan/bench_verdict.py + bench-verdict.md; PS/prototype-closure/manufacturing/first-unit.md (holds H01-H09, 'NOT_RUN physically'); PS/validation-results/04-board-current-thermal/round5-native21/b3-convergence/README.md:81-90 (IR points with predicted values).

### BP-27 - Keep release identity and fab process explicit: **2**
Hash-tied manifest, reproducible rebuild and a fab note with order requirements exist. Vendor review is not done (CTI, thickness, CPL preview) and the package states it is not released. 2, held back from 3 by the missing first article.

Evidence: PS/native-21/verification/final-manifest.json (board b19a4553..., copper.json ce49f200..., schematic e6993fa4..., netlist 8a7e1c4a..., status DIGITAL_CANDIDATE_NOT_MANUFACTURING_RELEASE); my shasum -a 256: fab/native-21-gerbers.zip = c9eaf0d9... (matches FAB-NOTE.md:8) and pinned section.kicad_pcb = b19a4553...; PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:12-22 (pre-order gates still open), :58, :63-66; PS/validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/README.md:15; hand-assembly-extras.csv.

### BP-28 - Review domain separation independently of return continuity: **2**
Domains, crossings (isolators, transformers, PS modules) and barrier geometry are mapped and gated on all layers, and the stage-18 move put the highest-voltage net at 12.6 mm outer. All of it is conditional on the unconfirmed laminate group (BP-20), the certifier's inner-layer ruling, and HF distance checks at 60 kHz. 2.

Evidence: PS/native-21/layout/rules21.py:1-60 and PS/native-21/section.kicad_dru:5-27; my recompute (scratchpad barrier2.py): SELV-HOT 8.047 mm, PE-HOT 8.507 mm, RES_A outer 13.375/20.393 mm; PS/DECISIONS.md:744-756 (item 18: RES_A 297 V rms, 12.6 mm; inner copper 9.694 mm to SELV/PE treated as solid insulation); PS/D5-BASIS.md (8.0 mm is provisional, 60664-4 above 30 kHz open); PS/validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md:17-22 (PD3 / IEC 60664-4 / hipot / CTI / T1 HF rating gates).

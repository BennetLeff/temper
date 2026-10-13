# Resolution plan for the stage 19b rubric findings (2026-10-13)

There is one section per theme in [FINDINGS.md](FINDINGS.md). Every step names its input, the command or file it touches, the **pass criterion, fixed before the work**, and the output.

The work sequence is listed at the end. "Design" means me, "owner" means you, and anything sent outside the project goes through the owner.

Each closed item gets:
- a DECISIONS.md entry;
- its rubric rows rescored in the per-rubric CSV, with the new evidence cited.

---

## F1: laminate CTI, thickness and the barrier margin (pre-order)

1. **Owner:** send `sourcing/inquiries/CTI-JLC.md` to JLC support. Ask them to confirm three things for a JLC041622-7628 order:
   - the laminate brand and grade;
   - CTI ≥ 175 V (PLC 3 / group IIIa) in writing;
   - that they can hold **finished thickness ≥ 1.6 mm**.
2. **Design:** if JLC names a grade, check its datasheet CTI and MOT and record them in FAB-NOTE's laminate row.
   - If JLC can't hold 1.6 mm, re-stack at 1.8 mm, as FAB-NOTE already says.
   - Then rerun `stackup.json`, the Kelvin plane and the B3 chain, because dielectric thickness feeds the thermal and loop models.
3. **Pass:** written CTI ≥ 175 V, and minimum thickness ≥ 1.6 mm. The order stays blocked until both are in hand. This is already a hard condition in FAB-NOTE.
4. **Design, at the re-spin:** widen the HOT–SELV barrier from 8.047 to **≥ 8.3 mm**.
   - Move the zone n_ha / via leg_a-dis pair at (67.46, 42.32), which sets the minimum.
   - Rerun `d5_audit.py` and the Rust barrier gate.
   - Pass: D5 HOT–SELV ≥ 8.3 mm, with every other gate unchanged.
5. **Rescore:** AOE-24, BP-20, BP-28.

## F2: shoot-through containment record vs the build (pre-mains)

1. **Design:** confirm which containment the board actually has.
   - grep the schematic for any catch or crowbar circuit; the reviewer found none;
   - read `PROTOTYPE-POWER-LOOP.md` and `ASSEMBLY.md` for what the J7–J10 positions are meant to hold.
2. **Design:** calculate F1-only containment. Write `02-protection-timing/shoot-through-f1/f1_containment.py`:
   - Bus-cap dump energy: ½·C·V² with C = 18.8 µF + 10 % and V = 280 V peak at 127 V + 10 %.
   - FET single-pulse avalanche or SOA: is the device destroyed, and does it fail short?
   - Prospective follow-on current: through BR1 into a short behind L1, with the line impedance from the s19b EMI model's source.
   - F1's (KLDR025) melting and clearing I²t at that current, compared with BR1's I²t rating and the PCB track fusing I²t of the RECT / BUS path, using the narrowest copper from the copper dump.
   - **Pass:** F1 clearing I²t < 0.5 × BR1 I²t, and < the fusing I²t of every series copper segment.
3. **Decide:**
   - **(a) If step 2 passes:** record F1-only containment in DECISIONS. Supersede D-31's "FC1 and the catch circuit" wording, and keep FC1 as an optional bench-only part.
   - **(b) If it fails:** put FC1 in the normal build, via the J7–J10 loop or a board-mount DC fuse at the re-spin. Then the Mersen DC-clearing question becomes an owner send.
4. **Rescore:** AOE-15 (the containment part).

## F3: bank at 1702 V in the CT-blind double fault (pre-28A)

1. **Owner:** send outbox §2 (TDK B32654) with an added question: the single-event or short-time over-voltage rating at 1700 V for ≤ 10 ms.
2. **Design, in parallel:** prototype a **hard 35 kHz timer floor** in firmware.
   - Clamp the LEDC/MCPWM period register so it can never go below 35 kHz, independent of the control loop.
   - Rerun `02-protection-timing/bank-ov-double-fault/` with that floor.
   - **Pass:** the CT-failed + loop-runaway case peaks ≤ 1600 V in both the time-domain and quasi-steady models.
3. **If both fail:** design a resonant-node clamp, a TVS string across the bank sized from the same study. Placing it needs a re-spin.
4. **Rescore:** AOE-15 (the over-voltage part), BP-03.

## F4: F2 breaking capacity and coordination (pre-mains)

1. **Design:** `02-protection-timing/f2-coordination/f2_coord.py`.
   - Prospective fault at J11 (blower tap) at 127 V + 10 %: source impedance as in F2, plus L1 and the trace.
   - F1's let-through peak current and I²t at that fault, from the KLDR025 curves.
   - F2 (Schurter UMT 250, 3.15 A T): its pre-arc I²t.
   - **Pass:** F1's let-through current ≤ F2's breaking rating (200 A at 250 VAC), or F1 clears before F2 starts arcing (F1 clearing I²t < F2 pre-arc I²t).
2. **If it fails:** replace F2 with a high-breaking-capacity 5 × 20 fuse (≥ 1500 A at 250 VAC, ceramic body, the same 3.15 A T rating). Check the footprint and height envelope in the fit gate.
3. Add the result to the existing certifier item (DECISIONS:634), and rescore AOE-25.

## F5: leakage and touch-current budget (pre-mains)

1. **Design:** pick the governing standard and limit with the certifier question set. The candidates are UL 858 / UL 1026 for a portable cooking appliance. Add the question to outbox §6 if it's not already settled.
2. **Design:** `07-conducted-emi/leakage/leakage_budget.py`.
   - Sum every capacitance to PE per line: board Y (C3/C4), module Y, IRM-20 ×2 / IRM-60 primary–secondary–PE leakage from MEAN WELL datasheets, the blower supply, and coil–PE (31 pF, from study 16).
   - Evaluate it at 132 V / 60 Hz, normal and single-fault (open PE / open neutral).
   - **Pass:** total ≤ 50 % of the chosen limit (for example 0.5 mA if the limit is 0.75 mA/1.0 mA class), leaving room for production spread.
3. **Bench:** measure touch current on the first assembly to the standard's network (owner, at the lab or with a leakage tester).
4. **Rescore:** OTT-19, MAG-19.

## F6: isolator dv/dt immunity vs 95 V/ns (pre-mains)

1. **Design:** `06-controller-interface/cmti/cmti_table.py`, with one row per isolation crossing: ISO7710 ×n, UCC21550 ×2, digital isolators and opto parts, if any.
   - Columns: the datasheet minimum CMTI (static and dynamic) with its page reference, the dv/dt that crossing actually sees (95 V/ns hard, 10 V/ns ZVS, from ALT-BIAS), the ratio, and what an upset does (a false gate command, or a filtered fault line).
   - **Pass:** CMTI ≥ 1.5 × the max dv/dt for every crossing whose upset produces a gate command. Crossings whose output is time-filtered (≥ 10 µs) may pass on the filter, with the filter's rejection shown.
2. **If a gate-command crossing fails:** require ZVS-only operation in firmware (no hard switching above the bench-verified voltage) until a part swap at the re-spin.
3. **Bench:** probe each driver output during the S4/S5 hard edges for glitches. This joins the bring-up list in `BRINGUP-PROBES.md`.
4. **Rescore:** AOE-29.

## F7: stale loop parasitics, the bulk path and switch-node capacitance (pre-mains)

1. **Design, export:** run `extract_geometry.py` on the 19b board to get `native21s19b-all-copper.json.gz` (it already exists). Regenerate `closures-legA-n21.json` / `closures-legB-n21.json` for the 19b R5 positions and check them with `check_ports.py`.
2. **Design, mesh gates on the Mac:** coarse `mesh25d_hybrid.py` for legs A21 and B21. **Pass:** the campaign gates (no PEC columns, zero port leakage, every port a closed loop).
3. **Design, extraction on the remote box:**
   - Run `campaign.py ... --export native21s19b-all-copper.json.gz --cases 1:0.35 2:0.35 3:0.35 1:0.5 1:0.7` for both legs.
   - Add a **bulk-path port**: FET row to C5/C6 through bus_p In2 / hv_ret In1, a new closure file.
   - Delete field files after each matrix (Mac disk budget).
   - Follow the remote-box rules: zsh login, never `pkill -f`.
4. **Design, switch-node capacitance:** add the sw_a to hv_ret (45.8 pF) and sw_b to bus_p (181.9 pF) plane capacitances from `scripts/an139_switchnode_caps.py` as lumped C in the F6 decks. Later, replace them with a field-solver value if the campaign gives one.
5. **Design, decision grid:** rerun the round-17 d2 F6 decks on the new matrices **with the bulk node modelled explicitly**, not as an ideal source. Use ALT-C5C6's bulk model with the extracted inductance.
   - **Pass, fixed now:** all 252 cases on both legs, die VDS ≤ 520 V, off-gate ≤ 1.9 V, at Tj 27/100/150 °C, with the PMEG at −1.6 V.
   - Also report the margin. Below 20 V of VDS margin, the item is flagged as a bench-watch item.
6. **If the bulk path fails (≥ 28 nH):** add local bulk, a 1–2 µF film pair at the FET row between bus_p and hv_ret, at the re-spin, or as a 19c change if a footprint fits. Rerun the decks.
7. **Rescore:** SI-03, SI-06, AN139-19, OTT-15, and BP-11 (watch).

## F8: OCP Kelvin pickup (pre-28A)

1. **Design:** rerun `02-protection-timing/coil-pickup/` on the 19b copper. Write it to `coil-pickup/s19b/` and leave the 13b results in place.
   - `dump_fp.py <19b pcb> fp.json R5 U6 T1 ...` (KiCad python).
   - Edit `run_loops.py` so it reads its copper dump from an argument rather than a hard-coded path.
   - Scale the field to **59.2 A peak at 35, 45 and 60 kHz** (EMF ∝ ω·I).
   - Then run `field_phase.py`, `run_loops.py`, `ocp_combine.py` and `sensitivity.py`.
2. **Pass (fixed now):** the any-phase +50 % stack ≤ the band margin, 67.72 − 59.17 = 8.55 A, less 2 A reserve, so **≤ 6.5 A**. Nominal must be ≤ 1 A.
3. **If it fails:** take the recorded KELVIN_N-under-KELVIN_P move (−56 % EMF) as a 19c copper patch, then rerun. If it still fails, raise R34 one step and recheck the band against T1's 88 A and the ≥ 64 A floor.
4. **Design, board self-field and dv/dt injection:** `coil-pickup/s19b/self_field.py`.
   - **Self-field:** the commutation-loop di/dt (from F7's waveforms) through the R5 breakout's mutual inductance, which comes out of F7's FEM as an extra port.
   - **dv/dt injection:** the sw_a / sw_b to Kelvin overlap capacitance (8.6 mm², about 0.7 pF, from `sipi_adjacency.py`) × 95 V/ns into the Kelvin node impedance and U6's input filter.
   - **Pass:** the injected error, after the filter, is below 0.25 A equivalent at the comparator.
5. **Rescore:** MAG-28, AN139-11, SI-29, BP-15.

## F9: layer-change returns on the other J4 nets (pre-order, as stage 19c)

1. **Design, gate first:** extend `return_path19.py`.
   - Add `ASSERT_TRANSFER` for pwm_ha, pwm_la, pwm_lb, permit and bus_fault: every reference change ≤ 3.0 mm from a v3v3↔selv_gnd transfer cap.
   - Add `ASSERT_PLANE` for the same nets: longest unreferenced run ≤ 1.0 mm.
   - Run it on 19b and confirm it **fails** on pwm_ha (7.59 mm), pwm_la (5.11 mm) and permit (20.89 mm), which is the negative control. Commit the gate.
2. **Design, copper:** a stage 19c, using the 19b pattern.
   - Add 100 nF caps (`c_ref_xfer_5..n`, the C47 part, LCSC C14663) to `power_stage_120v.ato`.
   - Place them in `place.py STAGE19C_XFER` beside each failing change.
   - Give each pad its own `plane_via` (≤ 1.6 mm).
   - Reroute permit's 6 mm unreferenced run over a plane if a slot allows; otherwise give it a cap at each end.
3. **bias_bad:** stays reported, not asserted (DECISIONS 19b rationale: fail-safe direction, not repetitive). Add that rationale as a code comment beside the gate's exclusion.
4. **Chain:** `chain.sh native21s19c ...` runs every gate, including bom_cpl_check, D5, fit, DFM, Kelvin, B3 and audit.rs (which gets a new test). Then regenerate the fab package and the CPL rotation audit.
   - **Pass:** every 19b gate is unchanged or improved, the extended return_path gate passes, and audit.rs passes.
5. **Rescore:** SI-08, OTT-06, BP-14.

## F10: inlet module parts and the EMI condition (pre-compliance)

1. **Design:** select real parts for the module's 2 × 41 µH DM inductors (≥ 15 A RMS, rated at 132 V, ≤ 20 mΩ, with a saturation curve). Candidates come from DigiKey/Mouser parametric search. Record the MPN, Isat, the L(I) curve and temperature rise.
2. **Design:** rerun `07-conducted-emi/s19b/emi_s19b.py` with `MODULE_NOM` set to the chosen parts' L at 15 A and hot (not nominal), and with the PE-path inductance from F11 as a sensitivity.
   - **Pass:** worst margin ≥ 6 dB nominal, and ≥ 3 dB in every sensitivity, the coil–PE split included.
3. **Design:** add the L1 / module DC-bias and hot data to `out-D22/PARTS.md`. Get the TDK L1 Z(f, I, T) through the TDK draft (owner sends).
4. **Bench:** measure the coil–PE capacitance **per terminal** with an LCR at 100 kHz, coil in the enclosure, pan floating and earthed. Add it to `BENCH-PRECOMPLIANCE.md`.
5. **Rescore:** OTT-18, OTT-20, MAG-06.

## F11: cable and connector EMC (model now, copper at the re-spin)

1. **Now, design:** add the Y-cap PE path (75–81 mm, about 125 nH) as an EMI sensitivity. It's covered by F10 step 2.
2. **Now, design:** `06-controller-interface/j4_coupling.py`. Estimate the crosstalk from pwm_la into ct_mon at the J4 header and harness (adjacent-pin mutual C/L from the Molex pitch, a 150 mm harness, pwm_la edges) against ct_mon's error budget.
   - **Pass:** coupled error < 10 % of the CT_MON LSB-equivalent threshold, or below its RC filter's rejection.
3. **Re-spin, design plus controller:** re-pin J4 with a ground between every fast/analog pair. Keep 16 positions: drop a redundant supply pin or use the 2 × 10.
   - Move ct_mon next to selv_gnd.
   - Add RC or ferrite filtering at the power-board end of PWM/permit if F6/F9 show it's needed.
   - Change both boards together: controller LAYOUT J4 and the R44 harness.
4. **Re-spin, design:** C3/C4 to J6 as a ≥ 2 mm-wide, ≤ 30 mm PE path, or move J6 next to C3/C4. Check the D5 HOT–PE distance after the move.
5. **Bench:** clamp CM current on the coil leads, J4 harness and J11/J13 during pre-compliance. Add these to `BENCH-PRECOMPLIANCE.md`.
6. **Rescore:** OTT-23, OTT-25, OTT-27, MAG-17.

## F12: 28 A thermal margins (pre-28A; the 22 A gate stays)

1. **Design:** set L1's heat in `b3-convergence/inputs/heat_der14.json` to the 15 A envelope:
   - 2.03 W DC copper (losses.csv:34), plus AC copper and core loss from TDK if available. Otherwise use 2.7 W, the reviewer's upper figure.
   - Rerun B3. **Pass:** L1 ≤ 125 °C (its rating) with ≥ 15 K margin, and the neighbours C5/C6/PS2 not pushed past their limits.
2. **Design:** declare **MOT 130 °C** as the governing laminate limit in DECISIONS item 21. Compare B3's 129.1 °C copper peak at 28 A against it. Below 5 K of margin, 28 A also requires a bench IR point at R5.4.
3. **Bench, already planned:** IR at 22 A, then 28 A: film bank hot-spot, C38–41, FETs (with switching loss measured), PS1/PS2 case and local air, C5/C6, L1, R5.4.
   - **Pass:** each part within its datasheet limit at 40 °C ambient, extrapolated.
   - 28 A unlocks only if every part passes. This is unchanged.
4. **Rescore:** AOE-02, AOE-14, SI-10, MAG-09, MAG-23, BP-08, after the bench.

## F13: parts and assembly (pre-order)

1. **BP-04:** read the exact-MPN DC-bias curves (Murata SimSurfing / Samsung / Yageo) for every MLCC on the −1.6 V and gate-driver rails. Recompute effective C at bias and 85 °C.
   - **Pass:** each rail keeps ≥ 70 % of the design capacitance. Otherwise upsize.
2. **BP-07:** add an "adhesive/restraint" row to FAB-NOTE for C5/C6, C21–C23, L1, PS1/PS2 (RTV corner staking after reflow, hand step). Close review m9 and m13. For m13, add outline arcs if the enclosure wants them; check this with temper-f7.
3. **AOE-05:**
   - J1: read the inlet's UL file for its use group at 15 A / 125 V (owner, if a login is needed).
   - Coil lug: choose it with temper-f7, matched to the M6 upturned-terminal decision, then add the stud-temperature IR point to the bench list.
   - Straps J7–J10: specify them as 14 AWG / 105 °C with ring lugs, or as a copper bar with a rating.
4. **AOE-36:** the lead-time and stock survey on the 19b BOM (92 lines) plus the controller, UI board, coil materials and knob magnets.
   - Output `sourcing/STOCK-2026-10-13.csv`: MPN, JLC/LCSC stock, DigiKey/Mouser stock, lead time, alternates, check date.
   - Then replace `ORDER-PACKAGE.md`'s "NO-GO / regenerate from stage 13" with the 19b result.
5. **Rescore:** BP-04, BP-07, AOE-05, AOE-36.

---

## Sequence

| Order | Work | Who | Runs where | Rough size |
|---|---|---|---|---|
| 1 | Send CTI-JLC (F1), TDK §2 with the 1700 V question (F3), Coilcraft §9 | owner | email | today |
| 2 | F9 gate extension and negative control, then **stage 19c** copper and chain | design | Mac | 1 session |
| 3 | F13 stock survey (one Sonnet agent, read-only), in parallel with step 2 | design | web | 1 session |
| 4 | F2, F4, F5, F6 desk calculations (four independent scripts; one agent each, none builds Rust) | design | Mac | 1 session |
| 5 | F12 step 1–2 (B3 with L1 at 15 A, MOT limit) | design | Mac | short |
| 6 | F8 coil-pickup rerun on 19c copper | design | Mac + KiCad python | short |
| 7 | F7 FEM re-extraction plus the bulk port, then the F6 decision grid | design | remote box | longest; days of solver time |
| 8 | F10 module part selection and EMI rerun; F11 model items | design | Mac | 1 session |
| 9 | Prototype order: after F1 confirmation, 19c, the F13 survey and the JLC placement previews | owner | JLC | after 1–3 |
| 10 | Bench: F5 touch current, F6 edge probing, F10 coil–PE split, F11 CM clamps, F12 IR | owner + design | bench | after the build |
| 11 | Re-spin items: F1 step 4, F11 steps 3–4, any F3/F7 hardware fixes | design | — | next copper revision |

Steps 4–8 can run while the prototype boards are in fab. Only F1, F9 (if it's done as 19c) and F13 gate the order. F7 gates the first mains power-up, not the order: a bad bulk-path result changes firmware limits or adds a re-spin part, and the prototype can still run on the 30–60 V bench bus.

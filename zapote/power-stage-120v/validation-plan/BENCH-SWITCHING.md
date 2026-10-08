# First-board switching bench procedure — R5-B

**Status:** procedure for review only; no board has been powered or qualified by this document. Evidence class: **physical-test requirement**, with exact structural circuit mapping from native-17. This is not a fabrication, mains, or powered-operation release. The independent R5-D1 copper extraction and R5-D2 board-inductance waveforms are pending; no model/bench agreement or switching-stress pass can be claimed yet.

**Identity:** Temper commit `91888bb29e318eef09c0a292245de88b9016d250`; `native-17/section.kicad_pcb` SHA-256 `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`. Recheck the hash, assembly revision, parts, and fixture before use. The component identities below come from `frozen/default.csv`; connections were checked against `frozen/default.net` and the native-17 board. The source dossier, including manufacturer PDF revisions and hashes, is [bench-plan/sources/README.md](../validation-results/01-switching-parasitics/round5/bench-plan/sources/README.md).

## Circuit and fixture

The required matrix is **both switches of leg A**. Q2 is high side (drain `bus_p`, source `sw_a`), Q3 low side (drain `sw_a`, source `leg_ret`); U1 drives them through R10/R12, R11/R13 hold their gates off, and C12/C13 are their D–S snubbers. The fitted series resistors are 3.9 Ω, hold-offs 10 kΩ, and snubbers 1 nF. Leg B uses Q5/Q6, U2, R18/R20, R19/R21 and C19/C20 correspondingly; it stays disabled during this matrix and its gates are verified off. C38/C39 are the local BUS_P–HV_RET capacitors beside leg A; C40/C41 serve leg B. R5 lies between `leg_ret` and `hv_ret`, so the bench source negative belongs on **J10 HV_RET**, never on LEG_RET. J8 is BUS_P. J7/J9 are the rectifier-side studs. R3/R4 are the 220 kΩ series bus bleed resistors. T1 primary is in series between `sw_a` and J2 `coil_feed`; J5 `res_a` goes through C21–C23 to `sw_b`.

Use a **removable, insulated, characterized non-saturating inductor**, with a short, guarded lead path and a single-turn current-sensing window. For the **Q3 low-side** pulse connect it between J8 BUS_P and J2; Q2's body diode carries freewheel current. For the **Q2 high-side** pulse, after full discharge and fixture change, connect it between J2 and J10 HV_RET; Q3's body diode carries freewheel current. J5 has no external coil connected. The route through T1 and the retained C21–C23 to the disabled, floating leg B means this is a board-specific fixture, not an ideal textbook half bridge. Before power, verify physical wiring, freewheel polarity, T1 burden, inductor saturation/current/voltage/thermal rating, cable insulation and clearances, and lack of an unintended path through leg B. Record the fixture schematic and hashes. **Stop** if that inspection cannot establish a safe current path. A clip-on sensor on the external inductor lead reads *load* current; it does not resolve a switch's terminal drain current during commutation. Provide a separately qualified drain-lead Rogowski sensor or an engineered low-inductance series current-viewing resistor at the measured device. If this cannot be done without changing the commutation loop materially, record `ID unavailable` and do not evaluate drain-current timing, switching energy, or D2 current-branch agreement.

An optional later repeat on leg B requires a separately reviewed direct `sw_b` fixture. **J5 is not a direct SW_B terminal** because C21–C23 intervene; do not reuse the J2 hookup by renaming J5. The optional repeat needs its own fixture schematic, attachment, current path, added-inductance assessment and approval before energization. It is outside the R5-B required matrix and does not hold this procedure draft.

U1/U2 normally receive HOT 15 V from **PS2 IRM-05-15, whose primary is on mains**. For this no-mains test, an independently isolated, current-limited 15 V auxiliary harness must power `v15_ls` relative to `leg_ret` **only after** its connection, isolation, back-feed into PS2, return and shutdown behavior are reviewed on the assembled board. Do not infer that unplugging J1 powers the drivers. The controller/interlock side needs a separately qualified SELV supply and J4 harness: J4.3 V3V3, J4.2/4/15/16 SELV_GND, J4.5–8 PWM, J4.9 PERMIT, J4.10 BUS_FAULT. J4.1 V15_SELV is normally supplied by PS1 and needs an explicit no-back-feed disposition. With PWM low and PERMIT withheld, verify U1.5/U2.5 DIS high and all four physical VGS low. TI UCC21550 Rev C §7.3.2/Table 7-3 says DIS high forces both outputs low; its UVLO tables do not close the known HOT5 brownout or controller/interlock loss case. Thus the fixture requires a **hardware independent inhibit** that removes pulses and the bus on loss of any auxiliary rail, PERMIT, controller heartbeat, fault signal, or operator enable. Demonstrate that shutdown with the bus at 0 V before any bus charge. U1's high-side bootstrap (D1, C10/C11) must be measured between U1.16 and U1.14 before Q2 pulses; if it has no valid charge path in the chosen fixture, stop rather than improvising a gate supply. Do not rely on firmware OCP or the nominal 61 A trip to contain a double-pulse fault.

## Instruments and connections

Use one timebase for **simultaneous** Q2 and Q3 VDS, Q2 and Q3 gate-to-source VGS, the tested device's *external* drain current, and local bus voltage across C38/C39. This takes at least six independent analog channels (seven if load current is saved separately); choose a synchronized acquisition system with enough channels. Save the four voltage traces and current at full bandwidth for at least 1 µs after each command, plus the whole two-pulse event. Record driver OUTA/OUTB commands or a common digital trigger and the actual local bus. The waveform at package leads is a **proxy** for die VDS/VGS; package inductance means it is not a die measurement.

| Quantity | Probe connection and minimum capability | Limitation to record |
| --- | --- | --- |
| Both VDS | Separate high-voltage differential probes directly across each tested TO-247 drain (pin 2/tab) and source (pin 3) with a rigid, very short insulated two-tip/loop adapter. Example Tektronix THDP0200 at 500×: ±1500 V differential and common mode, 1000 V CAT II input-to-earth, 200 MHz; select lead accessories whose ratings are no lower. | The 150 V range is invalid here. Check both terminal-to-earth and differential transient ratings against the *possible* peak, including a prequalified fault estimate. Long flying leads can invent or hide ringing. The lower-range TMDP0200 (±750 V) leaves only 26 V above the heuristic 724 V event and is not the default for this uncertain first-board test. |
| Both VGS | Isolated high-CMRR probe from gate pin 1 to *that device's* source pin 3; shielded MMCX solder-in tip adapter placed immediately at each pair. Example TIVP1 + TIVPMX10X: 1 GHz, ±50 V differential range, ±200 V **differential offset adjustment** and 92 dB typical CMRR at 100 MHz. The offset adjustment is not the common-mode rating; verify the actual tip and cable working-voltage rating separately. | High-side source slews with `sw_a` or `sw_b`; an ordinary earth-referenced ground clip there shorts the switch node. Confirm high-frequency CMRR, tip rating, noise floor and dynamic range with a common-mode null check before accepting a 3 V result. |
| Drain current | Calibrated isolated Rogowski around **one** accessible device drain conductor, with full pulse integration and no adjacent return enclosed; or low-inductance series CVR with an isolated shunt probe, only in an independently reviewed fixture. Bandwidth target ≥100 MHz and peak range above the abort level. | Rogowski has no DC; establish zero baseline and compare its integral to load current. A CVR changes loop L/R. Tektronix's TCP0030A is a possible insulated-conductor example (120 MHz, 50 A peak), but its 30 A DC and 500 A·µs limits and 150 V bare-wire rating must be checked for *each* pulse; it cannot be assumed suitable at every 50 V/37 A dwell. |
| Local bus | Differential probe across C38/C39's actual BUS_P/HV_RET pads, short tip pair, with rating as above; do not substitute supply-front-panel voltage. | Capture bus droop/rebound and compare with the setpoint. |

The earth-referenced scope chassis stays earthed. **Never float the scope or defeat PE. Never attach a standard passive probe ground clip to BUS_P, either switch node, a high-side source, or an unverified floating return.** A grounded passive low-side gate probe is allowed only if an approved single earth reference to LEG_RET has been established and doing so does not short the floating bench return or bypass R5; the default is isolated probes for all voltage channels. Probe bodies, leads, adapter pads and shields must remain clear of the PE-bonded heatsink and HOT metal. This follows Tektronix DPT pp. 10–14 and Keysight *Eight Hints* hint 5; the manufacturer examples are **candidate instrument capabilities, not proof of this assembled fixture's safety**.

Before the first pulse, calibrate probe gain/offset, current polarity and deskew on a low-energy reference edge with the **same tips, ranges, leads and channels**. Record correction values and both raw and corrected traces. Do not use VDS×ID energy or edge ordering until VDS/current deskew is verified; Tektronix DPT PDF pp. 16–17 documents that error. At zero bus, verify each gate channel's zero and polarity. For the first low-bus switched trace, repeat with the high-side VGS probe's two inputs temporarily tied to the **same high-side source point** by an insulated, unpowered-installed short-tip adapter; it should report common-mode pickup rather than gate voltage. Restore the actual gate-source connection only after discharge, then compare a second physically independent short-tip placement. If an alleged >3 V off-gate excursion changes substantially with probe placement, saturates a channel, or tracks the null trace, classify it **measurement indeterminate** and stop escalation. Preserve all traces; do not average away the discrepancy. Quote VDS peak with probe accuracy, bandwidth, tip-loop and repeat-placement uncertainty; a near-threshold result remains unresolved rather than rounded to pass.

## Preparation and controlled sequence

1. Two-person bench review of the exact assembled board, populated part values, snubbers, gate resistors, heatsink/PE insulation, fixture schematic, probe ranges, barriers and an accessible emergency power-off. No mains cable is present at J1 and both rectifier straps **J7–J8 and J9–J10 are removed and secured**. Check no continuity from either rectifier-side stud to either bus stud, no accidental enclosure bridge, and the R5 current/Kelvin connections. The no-mains rule applies throughout this procedure.
2. With all supplies isolated, measure BUS_P–HV_RET and the resonant capacitor bank J5–SW_B (the latter at an inspected C21–C23 `sw_b` pad) with a rated, known-working meter; verify **below 1 V**, wait 60 seconds and recheck below 1 V before touching or moving a fixture. Prove the meter on a known source before and after the zero checks. Verify R3/R4 bleed continuity and measured discharge curve at a low safe test charge. Calculate and record `E = ½ ΣC V²` for measured DC-link capacitance **plus supply-output and fixture capacitance** and `½ L I²` for the load. At nominal 5.8 µF the *board* bus alone stores about 0.084 J at 170 V; the external supply may dominate. Current limiting controls recharge, **not** the energy already in capacitors or inductors. Provide a rated, controlled discharge path independent of R3/R4 and repeat the physical voltage checks after every stop.
3. Set the isolated bus supply to 0 V with output inhibited, current limit at the lowest value that can charge the capacitors, and its output leads on **J8 positive/J10 negative** via insulated M4 lugs. Charge only after the auxiliary and controller off-state checks above. Verify the DC source is floating relative to earth and each scope input configuration is rated for its possible common mode. A bus current limit cannot substitute for a fast pulse-energy/current abort. Energize behind a guard; do not adjust live clips or reach over exposed metal.
4. Validate at a very low bus and low-current pulse. Confirm intended current path, freewheel polarity, no leg-B switching, accurate Q2/Q3 VGS, local-bus reading, no probe overrange, independent inhibit and discharge. Fit/verify baseline **C12/C13 = 1 nF and R10/R12 = 3.9 Ω**. For Q3, hold Q2 commanded off and deliver one short pulse to prove current polarity before a pair. For Q2, refit the discharged fixture, prove U1 bootstrap voltage and hold Q3 off. Both inputs of both drivers and all gates have explicit default-low states.
5. For **Q3 and Q2 separately**, use 50, then 100, then 170 V measured at C38/C39. At each bus, start with a few amperes and increase pulse width in reviewed increments to at most **37 A measured peak**, never the separate 42 A tank-analysis ceiling. Compute `t₁ ≈ L·I_target/V_bus` from the measured fixture inductance, then choose it conservatively from the first trace; do not assume ideal V/L when bus droops or inductor saturates. Use a first pulse to build current, an off interval long enough to expose the partner-diode commutation and gate ringing, and a short second pulse to inspect turn-on; terminate and inhibit before current can exceed the limit. Capture first turn-off, freewheel and second turn-on. Determine actual current from the recorded current trace. Re-arm only after saved-waveform review and bus/discharge checks. Document cooldown and any pulse repetition limit from measured device/inductor temperature.
6. After each row, inspect **both** devices' VDS/VGS and local bus before raising voltage or current. If any abort gate below fires, inhibit pulses, turn off and isolate DC/aux supplies, discharge via the rated path, meter-check bus and resonant bank, preserve raw captures, and investigate before a changed fixture or part is considered. Do not automatically retry a faulted row.

Suggested case order for Q3, then Q2: 50 V / low I → 50 V / increasing I ≤37 A → 100 V / low I → 100 V / increasing I → 170 V / low I → 170 V / increasing I. Record each actual (`V_bus`, `I_D,pk`, inductor current, temperature, pulse widths, off interval) pair. No result at a different voltage/current is substituted for a missing point.

## Comparison and falsification

The source of **520 V** is the project normal-switching design target `0.80 × 650 V` from the IPW65R018CFD7 650 V class and `01-switching-parasitics.md`/`DC-LINK-CLAMP.md`; it is an **absolute VDS peak target** for S1/S3, not an observed clamp voltage. To satisfy ROUND-5's requested staged-voltage comparison, plot the explicitly *diagnostic* proportional line `V_screen = 520 V × (V_bus,local immediately before edge / 170 V)` (152.9 V at 50 V, 305.9 V at 100 V, 520 V at 170 V). This normalization assumes peak stress scales with bus voltage at the **same current and edge conditions**; fixed `L·di/dt`, recovery and gate dynamics can violate it. A point below that line is **not** a pass on the 170 V target; a point above it stops escalation for diagnosis. Record both `VDS,pk − Vbus,local at peak time` and `VDS,pk / Vbus,local before edge` and apply the **unscaled 520 V design target** at all rows as a separate hard stop. Also stop well before any plausible approach to the 650 V device rating once measurement uncertainty is included. The 585 V fault criterion at 280 V is outside this ≤37 A bench campaign and receives no verdict here.

Record the off device's maximum positive VGS through its partner's turn-off, diode interval and turn-on; **3.0 V is the bench stop threshold**, 0.5 V below Infineon's 3.5 V minimum threshold (datasheet Table 4). Also record negative and positive VGS extremes against Infineon's Table 2 static ±20 V and dynamic ±30 V limits, taking account of the actual transient definition. Any correlated off-gate current or apparent simultaneous conduction requires an independent current-path check; a 3 V screen alone does not prove it did or did not happen. Compare actual edge time, dv/dt, di/dt, VDS overshoot/ringing, off-gate response, local-bus droop and drain-current timing with R5-D2 **only at the same measured bus, current, switch, direction, snubbers and gate resistance**, after R5-D1 and D2 deliver accepted native-17 inputs and raw waveforms. Mark comparison **PENDING** until then. D2's historical 723.9 V was a heuristic scalar-inductance model on native-15, beyond the device design range, and is not a prediction or acceptance baseline for this board.

**Abort/invalidate the row** on any probe/channel overrange or saturation, lost common-mode validity, unexplained trace discontinuity, unverified deskew for current timing, >3.0 V off-device VGS, approach to VGS or VDS absolute ratings with uncertainty, crossing the proportional screen or unscaled 520 V target, `|I| > 37 A`, inductor saturation, unexpected opposite-leg gate activity, loss of DIS/inhibit/aux rail, fault indication, anomalous bus rise/droop, heating, arcing, or inability to discharge and independently meter-check. Classify whether the cause is circuit behavior, probe artifact, or unresolved; missing data are **indeterminate**, never a pass.

If a valid waveform fails, change **one reversible control at a time after discharge**. First evaluate the affected leg-A gate resistor (R10/R12) for turn-off behavior (larger series resistance may reduce di/dt and VDS overshoot but delay turn-off); then for turn-on behavior (larger resistance may suppress partner Miller pickup but increase switching loss). The single fitted series resistor affects both directions, so separate on/off control would require an explicit designed resistor/diode option and a fresh source/board review; do not pretend it exists on native-17. Restore/document each tested value and check U1 drive, dead time, loss and protection timing. Next evaluate the affected snubber (C12/C13), with its voltage/current/thermal stress and loss measured. Finally consider only the layout changes R5-D2 identifies after D1: those require a new board revision, extraction, simulations, fabrication review and a new bench baseline. R18/R20 and C19/C20 are the corresponding leg-B parts, not knobs for the required leg-A test. Any proposed change to native copper, assembly or source is reported to the owner; this plan changes none.

## Review additions (Claude, 2026-09-28)

These add to the procedure above; they don't relax any of it.

1. **T1 carries the fixture current.** The load path runs J2 → T1 primary →
   `sw_a`, so the current transformer sees a DC pulse. Its secondary voltage
   is about `I/100 × (R39 1.5 Ω + DCR 1.5 Ω)`, and the Coilcraft table gives
   638 V·µs (the values in `validation-plan/sim-kit/02-chain/ct_frontend.cir`).
   Keep each shot's integral, ramp plus freewheel plus second pulse, at or
   below **320 V·µs** (half the rating). At 37 A the ramp alone uses
   `0.5 × 0.37 A × 3 Ω × t₁`: about 41 V·µs with a 100 µH inductor at
   50 V, 103 V·µs with 250 µH, and 411 V·µs with 1 mH (over budget). Each
   10 µs of freewheel at 37 A adds about 11 V·µs. **Use a 100–250 µH
   fixture inductor.** Between shots, allow at least 10 ms for the CT to
   reset (magnetizing 3.2 mH into about 3 Ω is τ ≈ 1.1 ms). These figures
   are estimates from the datasheet table; recompute them with the measured
   fixture inductance.
2. **The protection chain is live, so record it.** The tank-CT detector
   (static trip 50.6–60.0 A) shouldn't act below 37 A. The shunt OCP's
   worst-case static band is **38.4–85.6 A** (task 02 round 3), so it *may*
   assert BUS_FAULT inside this campaign. Capture BUS_FAULT (J4.10) and U6's
   output (`ocp_ok_hot`) on spare channels or a logic analyzer on the same
   trigger. A BUS_FAULT below 37 A is a finding, not a fixture fault: record
   the drain current at which it asserted. This measures the real shunt trip
   point, the evidence the held decision B needs.
3. **Measure the commutation-loop inductance from the ringing.** After each
   turn-off, fit the VDS ringing frequency `f` and its decay. With the
   device's datasheet Coss at the bus voltage plus the 1 nF snubber as `C`,
   `L_loop ≈ 1 / ((2πf)² C)`. To separate L from an unknown parasitic C, repeat
   one row (100 V, 20 A) with a second snubber value (for example 2.2 nF, after
   discharge) and solve the two frequencies for both. Report `L_loop` with its
   uncertainty. This is the quantity R5-D1 couldn't extract, and D2 can use
   it as a calibrated input.

## Raw record for every shot

Keep the native instrument waveform file **and** a lossless exported CSV, screenshot, scope setup file and hash manifest in an ignored per-shot `outputs/runs/` directory; publish reviewed summaries separately. A row is usable only if all mandatory channels cover the entire event without clipping. Suggested metadata:

```yaml
shot_id: null
timestamp_utc: null
operator_and_reviewer: null
source_commit: 91888bb29e318eef09c0a292245de88b9016d250
board_file_sha256: 16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162
assembly_id_and_part_lots: null
fixture_schematic_sha256: null
fixture_L_H_and_saturation_A: null
switch: Q3_or_Q2
bus_set_V: null
bus_local_before_at_peak_after_V: null
drain_current_peak_A: null
load_current_peak_A: null
pulse1_us: null
off_interval_us: null
pulse2_us: null
temperature_C: null
aux_15V_and_controller_rail_V: null
bootstrap_U1_16_to_14_V: null
permit_dis_fault_state: null
scope_model_serial_firmware_sample_rate_bandwidth: null
channels: {high_vds: null, low_vds: null, high_vgs: null, low_vgs: null, id: null, local_bus: null}
probe_models_serials_tip_adapters_ranges_cal_dates: null
probe_input_to_earth_and_differential_rating_check: null
current_sensor_calibration_and_polarity: null
deskew_ns_and_method: null
common_mode_null_and_second_tip_check: null
raw_files_sha256: null
peak_vds_high_low_V_and_uncertainty: null
off_vgs_high_low_max_min_V_and_uncertainty: null
scaled_screen_V_and_absolute_520V_result: null
abort_reason_or_pending_comparison: null
reviewer_disposition: null
```

No acceptance or release follows from filling this template. The current unresolved prerequisites are the inspected no-mains auxiliary/control/inhibit harness, a qualified leg-A inductor/current fixture and probe fit, safe assembled-board insulation/thermal review, physical R3/R4 and discharge verification, and R5-D1/D2 native-17 waveforms. Fabrication gates in `FAB-JLCPCB.md`/`DECISIONS.md` and D4's OCP/VGS conditions remain open.

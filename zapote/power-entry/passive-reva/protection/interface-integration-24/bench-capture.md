# Protected AUX and buck startup bench capture protocol

Status: executable test procedure; **not run**. This protocol is for the isolated low-voltage clamp prototype based on the Rev15/16 pin-level proposal and the Rev19 net graph. It does not establish a production design or convert Rev20–23 simulation fixtures into product limits. The latest full compiled power-entry candidate remains Rev11; first reconcile this fixture's exact component values and connectivity to the assembled article before energizing it.

## 1. Purpose and evidence boundary

Capture the actual cold and partially charged startup load of the selected 5 V buck and downstream consumers while observing the LT4363-1/FDB33N25 clamp. Separately characterize the source and apply documented, current-limited, low-voltage fault emulations. Determine whether the physical unit starts, folds back, times out, recovers, or latches off in each declared condition, and retain synchronized electrical/thermal evidence.

The Rev20–23 model screens use a synthetic 15 V source with 0.5 Ω series resistance, 130 Ω baseline load, 27 °C model temperature, and artificial extra-current shapes. In those fixtures the 35 V/50 ms event latched off; sustained +110 mA recovered while +120 mA latched off; and an added 150 mA pulse of 5 ms recovered while 20 ms latched off. These are **fixture sensitivities only**. They are not safe current limits, guaranteed surge thresholds, startup predictions, or pass/fail limits for hardware. The TPS54202 vendor model import failed in LTspice, so no converter waveform is available from that model attempt.

The source producer and its fault waveform are not yet selected or guaranteed. The bench worksheet's 24.6 V and 35 V fault levels and the simulation's 1 ms rise / 10–50 ms holds are provisional engineering stimuli until tied to a real source specification or measured source behavior. Do not call an emulated source event a manufacturer guarantee. A test that misses its commanded loaded waveform due to source current limit is invalid for that stimulus, not a pass.

## 2. Safety and fixture topology

Use a physically isolated, SELV-only fixture. Do not connect mains, a PFC bus, or an energized product power stage. The source at AUX_RAW shall be a floating, isolated, programmable DC source with enough voltage compliance to deliver the highest declared stimulus **at AUX_RAW under the test load and selected series impedance**, with a separately verified current limit. A 36 V terminal rating alone does not establish delivery of a 35 V board-level fault. Begin with the source set to 0 V and its output disabled. Use an isolated auxiliary supply for the HOT-side logic if the prototype requires one. Keep HOT_GND and any SELV_GND separate as drawn; make only the documented interface/isolation connections. Do not defeat protective earth on instruments.

```text
isolated programmable source (+) -- fuse -- source-current sensor -- selectable Rs/Ls -- AUX_RAW
isolated programmable source (-) ------------------------------------ HOT_GND (single fixture return)
AUX_PROTECTED/SNS --> actual buck VIN and selected downstream consumers
buck 5V --> electronic/resistive load; relay and PWM power stages remain physically inhibited
```

Put a keyed, shrouded disconnect and a discharge path on the isolated source/output. Choose fuse, current limit, wiring, discharge resistor and dummy-load power rating from the actual capacitor/load inventory before connection. Verify capacitor polarity and the clamp/FET pinout against the assembly netlist and manufacturer package drawings. Inspect for shorts with power off. Mount Q1 so its case can be measured; control and log ambient/case temperature. No flying leads on the gate, sense resistor, or timer node; use short Kelvin connections.

For forced overvoltage, short-circuit, or overload cases, use a characterized electronic source/transient fixture that can deliver the commanded waveform into the actual load without overshoot beyond the declared maximum. Start at the lowest energy condition. Use a separate dummy load to validate waveform and source current limit before attaching the prototype. Do not directly short a live rail with a hand switch. Insert an electronic load or a low-inductance, pulse-rated MOSFET load fixture with measured resistance/inductance and remote trigger. Keep any test energy within a separately reviewed component/fixture limit; stop if the FET trajectory approaches the approved SOA boundary or case-temperature limit.

All scope connections to HOT_GND/AUX nodes must use rated differential or isolated probes. Never put a grounded passive-probe clip on a floating rail or bridge HOT_GND to SELV_GND through an oscilloscope. Use differential probes for gate-to-source, sense, and source impedance measurements. Confirm probe common-mode and differential ratings at the maximum declared transient before use.

## 3. Article identity and preflight record

Before powering, fill a run sheet with:

- Assembly revision, serial number, schematic/netlist hash, board revision, modifications, exact LT4363-1, FDB33N25, sense resistor and diode markings.
- Exact C3 gate capacitor and C4/output bulk part numbers; measured or vendor-backed capacitance, ESR, tolerance, DC-bias, temperature and aging limits. Record total downstream capacitance including buck ceramics. Rev16 limits are C3 minimum effective 1.35 µF, C4 bulk meeting `Cbulk,min >= max(22 µF, 10 × maximum downstream ceramic capacitance)`, and total downstream capacitance no greater than 300 µF for that revision's startup screen. Do not assume the Rev20 simulation's 330 µF or the Rev16 220 µF target describes the built article.
- Exact buck IC/module, input/output capacitors, inductor, enable divider, UVLO, soft-start configuration and output load. Record all consumers on AUX and 5 V, firmware/config hash if present, and which loads are disconnected.
- Source model/serial, isolation rating, current limit, programmed waveform, added resistance/inductance and the independently measured loaded waveform. List electronic-load mode and settings.
- Ambient and Q1 case temperature, cooldown between fault tests, fixture wiring photographs, lead lengths, grounding diagram and operator.
- Instrument/probe make/model/serial, calibration due date, probe attenuation, bandwidth, sample rate, channel deskew, common-mode rating and uncertainty budget. Record zero/degauss and calibration checks before and after the campaign.

Confirm the service `/SHDN` input is in its normal state and can be pulled low only by the documented reset switch. Keep `/FLT` and `ENOUT` as unloaded observation points unless a separately justified probe/load is specified. Assert a hard external inhibit on relay and PWM power stages; additionally monitor the actual command/enable pins so the inhibit is evidenced, not assumed.

## 4. Instrumentation and simultaneous channels

Use one common-clock, at least 8-channel digitizer/scope or synchronized instruments with verified trigger/timebase alignment. All channels below are acquired simultaneously for every startup/fault record; add channels if available, do not replace required signals with sequential captures.

| Ch | Signal and exact reference | Sensor/probe | Purpose |
|---|---|---|---|
| 1 | `AUX_RAW` at clamp VCC pin 5 to HOT_GND at IC pins 7/9 | Differential voltage probe | Actual controller input and source waveform at the board |
| 2 | `AUX_PROTECTED` at the buck VIN/load-side of sense resistor to HOT_GND | Differential voltage probe | Consumer rail, startup, droop and overvoltage acceptance |
| 3 | `SNS` (Q1 source / sense resistor upstream Kelvin) minus `OUT` (protected-side Kelvin), measured directly across R_SENSE | Low-noise differential probe | Derive Q1/load path current as `Vsense/Rsense(actual, hot)`; verify polarity and bandwidth |
| 4 | Q1 gate to Q1 source (true `VGS`) | Differential probe, very short leads | Gate charge, regulation, turnoff and release |
| 5 | Q1 drain to Q1 source (true `VDS`) | Differential probe | Pass-FET electrical stress trajectory |
| 6 | LT4363 TMR pin 12 to local HOT_GND | High-impedance differential probe | Timer accumulation/reset/cooldown; probe capacitance documented |
| 7 | Buck VIN input current, in its dedicated AUX_PROTECTED branch | Calibrated wideband current probe or isolated shunt/differential probe | Actual converter input-current waveform; include sensor burden and bandwidth |
| 8 | Buck 5 V output at converter/load pins to its local return | Differential probe | Converter startup and output collapse/recovery |
| 9 | Buck EN pin to buck local ground | Differential probe | Enable threshold/state and relation to current transient |
| 10 | Current from source into AUX_RAW | Wideband isolated current probe or Kelvin shunt | Actual source current and delivered fault energy/impedance |
| 11 | Relay command/coil current or relay enable, whichever exists | Isolated logic probe/current probe | Prove relay remained disabled/enabled in each state |
| 12 | PWM enable/command and, if safe, representative gate-drive activity | Isolated logic probe | Prove PWM inhibit and identify any unintended switching |
| 13 | Existing driver VDD directly at driver supply pins to local driver ground | Differential probe | Directly check the driver rail requirement rather than infer it at the clamp |
| 14 | Q1 case temperature | Electrically isolated thermocouple/RTD logger; synchronized event marker | Thermal state and post-event temperature trajectory |

The direct driver-pin VDD must be captured even if nominally the same net as AUX_PROTECTED: routing drop and local return movement can matter. If channels are limited, use a second time-aligned digitizer for Ch14 and non-electrical auxiliaries, but preserve Channels 1–13 concurrently. Do not omit TMR, VGS, VDS, current, EN or driver-pin VDD from a fault capture.

**Bandwidth/sample settings:** For switching edges, source steps, current-limit entry and FET turnoff, use at least 20 MHz analog bandwidth (prefer 50 MHz when probes support it) and at least 100 MS/s per channel on the fast record. Acquire a pre-trigger interval of at least 10 ms and post-trigger at least 200 ms, extending until source and clamp settle or latch off. A separate simultaneous long record shall run from before stimulus through at least 6 s after the event (or until stable state plus 2 s), at at least 1 MS/s/channel with anti-alias filtering; if memory cannot cover it, use segmented/streaming acquisition with verified gap-free samples and a common timebase. For long cold ramps, also log a 10 s or longer record at ≥10 kS/s/channel while retaining the high-speed trigger capture around buck EN and any current-limit/TMR event. Log the exact analog bandwidth, decimation, record length and dead time. A 6 s LTspice run is not a product-required hold time; the long record is a diagnostic window derived from the modeled multi-second ramp and must be extended if the real assembly has not settled.

Trigger on source enable/edge, buck EN rising, sense voltage crossing a preselected diagnostic threshold, or TMR rise; use a common external event marker so all instruments align. Save the raw full-resolution samples, not screenshots alone. Do not use peak-detect display as the underlying record.

## 5. Source and fault-waveform characterization

1. With the prototype disconnected, measure the source open-circuit programmed waveform and source current limit using a calibrated differential probe and isolated current sensor. Record overshoot, slew, droop, recovery, output capacitance, control-loop response and any foldback.
2. Connect a pulse-rated dummy load approximating the expected minimum/maximum article load. Repeat each planned source waveform at the source connector and at the intended board input plane. Measure both source voltage and current simultaneously. Characterize at the normal endpoints 14.625, 15.00 and 15.75 V, plus the declared fault levels. Use low/high load conditions and the actual rise/fall durations.
3. Estimate quasi-static source resistance at each operating point from two stable load levels using `Rsource = ΔVboard/ΔIsource`; report the measurement interval and uncertainty. For fast edges, retain time-domain `Vboard(t)` and `Isource(t)`, and characterize dynamic impedance versus frequency with an appropriate isolated method if the real producer/cable network requires it. Do not reduce a nonlinear or current-limited source to a single resistor when reporting fast-fault behavior.
4. Where the actual source is known, reproduce its documented/measured source impedance, wiring inductance, current limit, rise/fall and duration. Where it is unknown, report the test as an emulated source case with its measured waveform; do not label it representative or guaranteed.
5. The historical model's 0.5 Ω, 1 ms-rise, 35 V event and 10/25/40/50 ms holds may be used as explicitly labeled diagnostic emulations only after checking fixture energy and FET SOA. The Rev15 worksheet also names 24.6 V and 35 V as provisional fault points. Capture the waveform actually delivered at AUX_RAW. These values do not define an accepted product envelope by themselves.
6. Before attaching the assembly, prove the programmable source can deliver the requested waveform under the expected load. If its current limit clips the waveform, lower the load or use a suitable source and repeat characterization; a clipped event cannot answer the intended stimulus question.

## 6. Startup and state matrix

Use the selected actual buck and intended downstream capacitors/load. Hold PWM and relay off by hardware during all initial power-up and through protected-output ramp. Record a baseline source-only capture before adding consumer branches. Start with the lowest source voltage/current-limit setting that can safely bring up the unit; increase only after current and polarity look correct.

For each listed state, capture normal endpoints 14.625 V, 15.00 V and 15.75 V, unless the declared source contract narrows the range. Record at least three repeats per state to expose startup variation; this is a repeatability sample, not a statistical reliability qualification.

| State | Initial condition and sequence | Capture/notes |
|---|---|---|
| Cold/discharged, consumers disabled | Discharge AUX_PROTECTED, buck VIN and 5 V capacitors through the designed resistor; independently verify initial rails are ≤0.1 V. This ≤0.1 V value is a bench reproducibility condition only; no product zero-charge requirement is established. Set relay/PWM disabled; source to 0, then ramp to target. | Capture AUX ramp, buck EN, inrush, sense current, TMR, VGS/VDS, driver VDD and 5 V output through full settling. |
| Cold/discharged, real buck enabled by intended sequence | Same discharge. Enable buck only at its intended actual threshold/control point; keep relay/PWM disabled until all rails are stable and RUN is low. | Capture threshold/hysteresis, actual VIN current, 5 V rise, AUX droop, repeated UV/EN cycling, foldback and timer state. |
| Partial AUX charge | With all consumers inhibited, precharge AUX_PROTECTED to 25%, 50% and 90% of its measured normal settled value using a separate isolated, current-limited precharge path. Disconnect the precharge path before normal startup; confirm it cannot backfeed the clamp/buck. Then apply the defined source ramp. | Record exact initial voltages on C3/C4 and 5 V caps; characterize restart/recharge, not just nominal cold-start behavior. If the topology cannot safely isolate precharge, use the circuit's natural measured partial-collapse state instead and document it. |
| Buck-output precharge | Separately prepare the 5 V output capacitor to the safe, defined partial level only if the actual design permits this condition without reverse-driving the buck; otherwise omit and record why. | Observe reverse current, EN behavior and AUX path current; do not force a state prohibited by the selected buck datasheet. |
| Relay only | After AUX and 5 V stabilize with PWM off and authorization low, enable relay using the actual driver/control path and actual relay coil/load. | Capture coil inrush, contact/load step, AUX/5 V droop and recovery. Keep power stage disabled. |
| PWM only | With relay off and safe dummy power-stage load, enable PWM under controlled low-energy conditions after rails are stable; ramp duty/load conservatively. | Capture switching startup/load steps, AUX/5 V ripple and current. Do not connect mains/PFC bus. |
| Simultaneous relay + PWM | Only after individual tests pass the existing limits and hardware inhibit/stop path is verified; start relay and PWM at the worst intended timing relationship under a current-limited dummy load. | Capture overlap peak, rail minimum, sense/TMR, driver VDD, current and command timing. |
| Maximum intended steady load / load step | Use measured/bounded loads for AUX and 5 V; exercise idle-to-maximum and maximum-to-idle steps, including the coincident relay/PWM state. | Record amplitude, duration, repetition, load slew, source droop and thermal rise. Replace historical allocations with measured values. |

For cold startup, report total load current while `AUX_PROTECTED < 3 V` separately. Rev15's 67.507 mA minimum-foldback calculation is a **conditional screen** derived from datasheet figures and a 0.22 Ω sense resistor; its applicability across this assembly's voltage, temperature and component corners must be confirmed. Keep relay and PWM off until the output has exited that region. Do not use Rev15's 129.700 mA operating-plus-ramp arithmetic as an accepted current limit below 3 V.

## 7. Fault and recovery matrix

First establish normal startup and load behavior. Then apply one fault at a time with relay/PWM inhibited, followed by only those combined states allowed by the approved low-energy fixture plan. Between events, wait for Q1 case temperature to return to the specified starting band and capture the entire cooldown. Do not infer permissible repetition rate from a single event.

| Case | Stimulus | Required observations |
|---|---|---|
| Slow/fast UV and recovery | Source collapse/ramp down and return at characterized slew rates, including repeated crossings of the actual UV threshold. | AUX_RAW/VCC, AUX_PROTECTED, VGS/VDS, sense current, TMR, driver VDD, buck EN and 5 V. Do not extrapolate controller guarantees below valid supply. No unintended relay/PWM/RUN on return. |
| Overvoltage, no load / normal load / maximum intended load | Use declared normal start at 15.75 V, then separate low-voltage fault emulations at 24.6 V and 35 V with measured source impedance and rise/fall. Include the actual producer waveform if available. Vary duration only within the reviewed fixture energy budget; the 10/25/40/50 ms sequence at 35 V is diagnostic model-matched emulation, not acceptance envelope. | Capture VCC/AUX_RAW, driver-pin VDD, protected rail peak, sense, TMR, VGS/VDS, Q1 current, source current, temperature and post-event latch/recovery. Start record before fault onset. |
| Overload/current-limit entry | Increase electronic-load demand in documented increments from idle to maximum intended load; include startup current waveform and controlled pulse tests. | Capture current, OUT/SNS, TMR, rail and VDS. Model-screen values +110/+120 mA sustained and +150 mA/5 or 20 ms are comparison markers only; do not use as acceptance limits. |
| Output short | Use a measured, pulse-rated electronic short fixture. Begin at lowest available source energy, then raise only within reviewed SOA limits. Record actual short resistance and inductance. | Capture from before short through removal and latch response. Do not use an arbitrary hard switch or step-sensitive SPICE peak as SOA evidence. |
| Persistent/repeated fault | Only after single-event waveform and thermal margin are accepted for the specific test article. Hold declared source event after off; also test repeats separated by recorded intervals and cooldown states. | Confirm LT4363-1 (-1) latches off under the declared condition; record TMR cooldown, gate, output and temperature. No automatic AUX retry is expected for -1; verify the exact article/model variant. |
| Service reset | After a documented latched fault and adequate thermal recovery, pull `/SHDN` low ≥120 ms, then release with measured slew ≥10 V/ms as specified in Rev15. Keep RUN, relay and PWM disabled. | Capture pin6 level, Q1 current cessation, VGS, rail discharge, timer and release ramp. Require a fresh valid authorization/session before any RUN. AUX restoration alone must not grant RUN. |
| Source interruption / brownout restart | Remove and restore the isolated source at slow and fast ramps; begin with full and partial stored charge. | Observe reset producers, driver rails, EN, latch states, relay/PWM outputs and absence of unintended RUN. Do not infer power-on reset from pulldowns alone. |

For each event that reaches current limit, record both the current-limit entry and the later load/output response. Timer voltage reaching the datasheet's threshold or the output collapsing is a functional observation, not by itself a safe FET result. Compute Q1 instantaneous `VDS × ID` and integrated electrical energy from calibrated traces, carry uncertainty, and compare the complete time trajectory and initial/case temperature with the applicable derated SOA and thermal limits. The vendor SPICE MOSFET model has no validated hot thermal/SOA behavior. Room-temperature model or graph agreement is not a hot-case pass.

## 8. Acceptance, disposition and uncertainty

Use three dispositions: **Pass against stated requirement**, **Fail against stated requirement**, or **Inconclusive / characterization only**. A waveform outside a provisional envelope is not a failure until that envelope is adopted as a requirement; an event within an emulated envelope is not a product pass unless it was the agreed requirement and the article/source/load corners represent it.

Existing numeric criteria that can be checked directly:

- At normal AUX_RAW values 14.625–15.75 V, the protected/driver rail must remain at least 14.25 V under the declared normal loads (Rev15/16 design screen). Record the minimum at the actual driver supply pins.
- During any adopted overvoltage fault, the driver VDD peak plus expanded measurement uncertainty must be **less than 18 V** (Rev15/16 limit). Report `Vpeak + U95`; a displayed trace below 18 V without uncertainty margin is not a pass.
- Normal operation must not cause LT4363 timer trip/latch-off. Cold startup with the actual converter and intended sequencing must complete without current-limit/timer latch-off, UV cycling or stalled startup; establish “complete” from stable rails, settled converter output/current and configured load, not a transient momentary threshold crossing.
- Maintain relay and PWM disabled until AUX/buck startup is complete and RUN remains low. In later integrated tests, faults must clear driver/PFC authorization and no return of input or AUX alone may re-enable RUN (Rev15/16 reset interface criteria).
- `/SHDN` service reset uses a measured low interval of at least 120 ms and release slew at least 10 V/ms, followed by a fresh protocol session. This is a reset-interface criterion, not a promise that the rail discharges fully within 120 ms.
- Component voltage/current/temperature trajectories must remain within applicable derated ratings/SOA using actual case temperature and uncertainty. No numerical shutdown-time, ride-through, pulse repetition, fault source impedance or universal startup-current requirement is presently established; these remain open acceptance inputs.

Before judging any limit, create an uncertainty budget including voltage probe gain/offset/noise, common-mode error, bandwidth/aliasing, probe loading, deskew, shunt tolerance/TCR/Kelvin error, current probe gain/offset/position, timebase/sample uncertainty and source calibration. State standard and expanded uncertainty, coverage factor, calibration traceability, probe bandwidth and the method used for extrema/energy. Deskew voltage/current channels and verify polarity on a known load before calculating peak power or energy. Use the worst-case uncertainty direction for limits; do not subtract measurement error from an unsafe peak.

If normal rail min or fault rail peak straddles its threshold after uncertainty, classify it inconclusive and improve the measurement or circuit margin. If the source missed the requested voltage, rise, duration or load due to current limiting, classify that stimulus invalid and repeat only after characterization. Do not round a failing/inconclusive trace into a pass.

## 9. Data package and closeout

For each run create a unique folder named `YYYYMMDD_<assembly>_<case>_<run#>` and retain:

- Unmodified binary waveform files from every synchronized instrument, plus an open CSV/TDMS/ASAM export with timestamp and one column per channel.
- Scope setup/state files, acquisition metadata and screenshots for orientation only.
- Channel-to-node map, source programmed and measured waveforms, current-limit settings, instrument/probe calibration and uncertainty spreadsheet, sample/bandwidth/timebase/trigger/deskew details.
- Fixture schematic, photos, measured Rs/Ls and shunt values, load settings, board/part/capacitor identity, initial capacitor voltages, relay/PWM state, ambient and case temperature, event sequence and operator notes.
- A derived analysis file for AUX minimum/maximum, driver-pin minimum/maximum, buck input-current peak and time integral, sense-derived clamp current, TMR maximum/crossing times, VGS/VDS, Q1 power/energy and uncertainty bounds. Preserve raw values and equations; do not make plots the sole data record.
- A per-run outcome table tying every pass/fail/inconclusive call to its existing requirement or explicitly marking the emulated stimulus as characterization only. Include event/cooldown history and any aborted/invalid tests.

Hash raw files and analysis outputs after acquisition, keep an untouched copy, and document any filtering/decimation as a derivative. Do not overwrite a failed run with a rerun. Update the system evidence only after a reviewer can reproduce plotted values from the raw capture and independently verify the acceptance comparison.

## 10. Hardware inputs still needed before the physical run

- The physical prototype/assembly and the exact clamp/buck/reset schematic or netlist; Rev11 full candidate is not the Rev19 clamp fixture.
- Chosen AUX producer/supply and documented output fault waveform, source impedance versus time/frequency, current limit, cable/wiring inductance and source recovery behavior; otherwise results are only named laboratory emulations.
- Exact selected buck and enable implementation, its input/output capacitors, actual 5 V and 15 V loads, supervisor/decoder/driver loads, and any measured current-vs-time envelope.
- Required fault envelope (including whether 24.6/35 V applies), acceptable AUX interruption/latch-off and recovery behavior, ride-through if any, repetition interval, ambient/case temperature range, and defined safe power-stage inhibit state.
- Exact C3/C4 and downstream capacitor population/effective values, FET mounting/thermal path, fuse and current-limit design, and accepted derated SOA criterion.
- Available isolated programmable source/electronic load, differential probes and synchronized channel count/bandwidth/sample memory; calibrated temperature instrumentation.

Until these are supplied, this protocol is ready for a characterized low-voltage prototype campaign, but it cannot issue a product-level source/fault acceptance verdict. No measurements were performed in preparing this document.

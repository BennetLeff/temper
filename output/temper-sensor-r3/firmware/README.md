# sensor-r3 C1 firmware and C-in-the-loop co-simulation

HANDOFF section C. The C1 algorithms are host-tested C in
`firmware/components/control/`. The same C runs closed-loop against the r3
Python truth plant here. Decisions and open items are in `DECISIONS.md`.

**Rerun everything:** `./run.sh`. It takes about 20 min and exits non-zero on any
failure. It includes both SIL configurations and their coverage gate. The
contact-change and contaminated-contact study is in `../robustness/`
(DECISIONS D-CSW, D-LPG; `../robustness/DECISIONS.md`).

**Evidence reference platform: the remote box (linux x86_64); the Mac checks
counts exactly and floats within tolerance** (`../evidence_compare.py`,
DECISIONS D-EVPLAT). Regenerate committed evidence on the box only:

    ssh bennet@100.121.239.87 'bash -lc "cd ~/WS-sensor/temper/output/temper-sensor-r3/firmware &&
      PATH=$HOME/WS-sensor/venv/bin:$PATH taskset -c 0-5,12-17 ./run.sh"'

A verification run anywhere ends `EVIDENCE MATCHES HEAD` before `ALL C1
FIRMWARE CHECKS PASS`.

The firmware build uses the C1 runtime when `TEMPER_PAN_CONTROL_C1` is
defined; `main/CMakeLists.txt` defines it for the ESP-IDF target (DECISIONS
D-MODE). `main/pan_control.{c,h}` connects the loop to the state machine, the
MAX31865 service, the rim NTC driver and the power stage.

## Firmware sources (`firmware/components/control/`)

| File | What it does |
|---|---|
| `pan_temp_estimator.{c,h}` | 4-state KF [T_pan, v, T_cap, T_el]. dt 0.1 s, 5 substeps. Float, with all constants in `pte_params_t`. |
| `contact_shift.{c,h}` | Contact-shift window (D-CSW): after an abrupt reading fall or rise that power does not explain, re-estimates the contact relative to the old model, or asks D1 for a probe. |
| `plant_gain.{c,h}` | Online a = η/C identification with RLS. Tags each power sample as measured or estimated. |
| `pan_rate_pid.{c,h}` | The r2 rate-domain PID, scheduled by a, with the latent-plateau guard (D-LPG). |
| `contact_check.{c,h}` | D1, as in screen.py, plus the firmware rules D-D1a–c. Fixed ring buffer, no heap. |
| `pan_sensor_guard.{c,h}` | Checks MAX31865 07h, SPI, stale data, range, rate, and the rim cross-check. Reports into the existing RTD fault sink. |
| `pan_temp_loop.{c,h}` | Composes the modules above and holds power authority: it never chases a cold reading. |
| `pan_supervisor.{c,h}` | Runaway supervision that replaces the legacy 15 K/s and target + 10 K latches in C1 builds: R1 sustained rise, and R2 stages 1/2a/2b (DECISIONS D-RUN). |
| `current_sense_check.{c,h}` | Bus-current sense plausibility: (a) ≥ 300 W commanded with no current, (b) the start-up pulse at PREHEAT entry, (c) input vs bus current when the input sense is fitted. Latches FAULT_CURRENT_SENSE (DECISIONS D-ISENSE). |
| `pan_leak_check.{c,h}` | Element-parallel Pt100 leakage: two chained cross-check suspect → probe-passed cycles latch FAULT_PROBE_LEAKAGE (DECISIONS D-LEAK). |
| `pan_rim_limit.{c,h}` | Setpoint-relative rim limit: a rim above the glass envelope of max(setpoint, t_hat) plus the rim's hot tolerance stack, not falling, for 5 s, latches FAULT_PROBE_LEAKAGE (DECISIONS D-RIMLIM). |
| `pan_cold_soak.{c,h}` | Cold-soak check at PREHEAT entry: coil off ≥ 30 min, 15 min of flat history with heatsink drift ≤ 0.02 K/min (D-SOAKTAU), the heatsink NTC VALID and ≤ 45 °C, the rim saturated; the heatsink over the Pt100 by > 19.4 K (16.9 K when the rail was measured through the window, D-RAIL) latches FAULT_PROBE_LEAKAGE before any power (DECISIONS D-SOAK). |
| `pan_soak_store.{c,h}` | The coil-off token in NVS: written once when a coil-off period reaches 15 min, revoked before the coil is energised, credited at boot as a lower bound (no clock survives mains loss); `main/soak_store_nvs.c` binds it to ESP-IDF NVS (DECISIONS D-SOAKNV). |

The C1 MAX31865 path is in `firmware/components/sensors/`:
- `rtd_convert.{c,h}` converts code → Ω → °C, with the CR-7 self-heating and
  optional loading correction, and classes a conversion beyond R(850 °C) or
  R(−200 °C), or with a 07h input bit, as a sensor failure (DECISIONS
  D-OPEN);
- `rtd_service.c` runs the C1 thresholds, the **manual** fault-detection
  cycle at power-up and before every probe-fault reset (5.5 ms steps, 11.5 ms
  restart, from the CR-1 network's τ_max 1.01 ms; D-FCYC), continuous
  conversion, the DRDY-stale check and the frozen-code check (DECISIONS
  D-CR7, D-STALE). DRDY is TCA9555 P07, polled over I2C each tick
  (`tca9555.c`, D-DRDY);
- `rail_adc.{c,h}` reads v3v3 from MCP3202 CH1 against the LM4040A25 on the
  same bus, from the RTD service's tick (one bus owner); the rim and heatsink
  drivers divide by it, or by 3.300 V when it is unknown (DECISIONS D-RAIL).

The rim NTC (Semitec 104GT-2 on GPIO9 / ADC1_CH8) is also in
`firmware/components/sensors/` (DECISIONS D-RIM):
- `rim_ntc.{c,h}` is the driver. It handles:
  - the CR-7 attenuation by node voltage, the trimmed mean and the
    v3v3 ratio;
  - the datasheet R-T table (`rim_ntc_table.h`, generated by `rim_ntc.py`);
  - the 1 s filter;
  - saturation, and the short, over-range, open and ADC faults.

  Hardware access goes through a HAL seam.
- `rim_ntc_board.c` binds that seam to `hal_adc`.

The heatsink NTC (Vishay NTCALUG01A104GA, 10 k pull-up, TLV9062 follower, then
the CR-8 divider 1.00 k / 5.90 k of zapote C45, on GPIO6 / ADC1_CH5) has the
same structure (DECISIONS D-HSNTC): `hs_ntc.{c,h}` (gain `HS_NTC_ADC_GAIN` =
0.855072), the Vishay material D table (`hs_ntc_table.h`, generated by
`hs_ntc.py`) and `hs_ntc_board.c`. `main/board_peripherals.c`
`read_heatsink_temperature()` reads it (+INF on a driver fault). With the
divider the channel is VALID from −40 °C, so it reads room temperature; a pin
above anything the intact divider can produce latches the DIVIDER fault.

**Cold-soak bench measurements** (DECISIONS D-SOAK, the full list): the
heatsink channel against a reference thermometer at the lug and in the room
after a 250 °C cook and through an overnight idle, which now runs **at
normal room temperature** (18–25 °C, and once at 10–15 °C) instead of a room
or box at ≥ 30 °C; the standby offset; τ_h and τ_g; the Pt100's off-pan
self-heating; the ADC1_CH5 offset at 2.5–2.75 V; and the ADC1_CH5 reading
at 2.9–3.3 V with R90 lifted (does the DIVIDER fault fire).

## Host tests (`firmware/test/`, registered in `CMakeLists.txt`)

| Test | Coverage |
|---|---|
| `test_pan_temp_estimator_only` | 6 tests. Golden vectors from `export_vectors.py`: worst max \|C − Py\| 0.00009 K, against a bar of 0.05 K. |
| `test_contact_check_only` | 11 tests. Replays loss on 4 pans, food on 3 and nominal runs, in screen mode and firmware mode, plus synthetic cases. |
| `test_pan_temp_loop_only` | 24 tests. Guard, plant gain (including the later-step updates), PID, the latent-plateau guard, the contact-shift window and power authority. |
| `test_pan_contact_sm_only` | 2 tests. EVENT_CONTACT_LOST in the state machine. |
| `test_c1_units_only` | 54 tests. Supervisor R1/R2, code-to-temperature conversion and the sensor-failure classes (D-OPEN), the current-sense checks (D-ISENSE), the leak check (D-LEAK), the rim limit (D-RIMLIM) and the cold-soak check (D-SOAK), its measured-rail threshold (D-RAIL), the coil-off credit and the token store (D-SOAKNV). |
| `test_c1_runtime_only` | 28 tests. The C1 state machine and `pan_control`: hot pan, h_c drop, lowered target, power stage disobeying, rising with power off, absolute 300 °C, intensity, C1 RTD window. Rim: cross-check on a low flat Pt100, no cross-check on a rising quench or a saturated rim, rim short/open/ADC failure → FAULT_PROBE_SHORT/OPEN. Current sense: dead while heating, failed start-up pulse, a low-power hold without a latch (D-ISENSE). Cold soak: a leak latches before any power and holds; agreement passes; a cold pan in the window, < 30 min, a saturated heatsink or a warm rim skip (D-SOAK); the coil-off token across a power cycle and a failing NVS erase (D-SOAKNV). |
| `test_c1_runtime_isense_only` | 31 tests. `test_c1_runtime_only` built with `TEMPER_INPUT_CURRENT_SENSE=1`, plus the input-vs-bus current cross-check (D-ISENSE (c)). |
| `test_c1_rtd_service_only` | 24 tests. The C1 MAX31865 sequence through the SPI mock and its analog model of the CR-1 input: thresholds (35544 / 12844), the manual cycle's order and waits, a too-fast or automatic cycle flagging a healthy element, open / shorted inputs at power-up and at a reset, a stuck cycle, conversion, fault flag, stale, the first-conversion allowance, frozen (D-FCYC, D-OPEN); the rail ADC's decode, device config, fallback states and 5 s of shared bus (D-RAIL); the expander DRDY path (D-DRDY). |
| `test_c1_rim_ntc_only` | 13 tests. The rim driver through a mock HAL. Datasheet points 25–250 °C, chain accuracy at 100–250 °C (worst 0.073 K) and the CR-7 attenuation, hysteresis and clip re-read. Saturation, rail fallback, short, glitch, over-range, open (600 s), ADC failure, filter τ, trimmed mean, and the board binding over the `hal_adc` mock. |
| `test_c1_hs_ntc_only` | 14 tests. The heatsink driver through a mock HAL on the CR-8 board: data-sheet points, chain accuracy at the trip points, room and cold temperatures VALID, SATURATED upper bounds, the divider's bottom open (DIVIDER latch) and top open (SHORT), no false divider fault at the intact extreme, short / over-range / ADC latches (+INF), the 1 s filter, the 100 ms poll, the CR-8 defaults, and the board binding (ADC1_CH5 only). |
| `test_sil_fault_injection` / `test_sil_fault_injection_c1` | The SIL fault-injection suite, built twice from one runner and `traces/manifest.json` (D-SIL). Legacy runs 31 scenarios. C1 runs 52: it uses the real MAX31865 service through a register-level converter model with the CR-1 input's analog model (no automatic cycle, fast step or early restart, asserted in every scenario), DRDY on the TCA9555 model, at the firmware's 10 ms cadence, and the bus current follows the command. |

## SIL fault injection in both configurations (D-SIL)

`python3 firmware/test/test_sil_coverage.py --gate` prints and gates
coverage. CI runs it as `scripts/check_sil_coverage.py`.

| Mode | Scenarios | (fault class, origin) pairs | C1 mechanism × origin |
|---|---|---|---|
| legacy | 31 | 20/20 | n/a |
| C1 | 52 | 28/28, a superset of legacy's (adds IDLE, INIT for FAULT_PROBE_OPEN, FAULT_CURRENT_SENSE and FAULT_PROBE_LEAKAGE) | 27/27 |

The C1 mechanisms are:
- R1 and the absolute 300 °C check;
- R2 stages 1, 2a and 2b;
- register 07h, DRDY stale and frozen code;
- the manual fault-detection cycle, at power-up (INIT) and on a reset request
  (IDLE) (D-FCYC);
- the current-sense checks (a) and (b) (D-ISENSE);
- the Pt100 leak check (D-LEAK);
- the setpoint-relative rim limit (D-RIMLIM), from HEATING and PREHEAT;
- the cold-soak check (D-SOAK) from PREHEAT: leak, pass and skip.

Four legacy scenarios are legacy-only, and each names its C1 replacement:
- **Thermal Runaway (target + 10 K latch).** Replaced by stage 1 (no latch,
  power 0 for 31 s at target + 15 K), stage 2a (stuck-on stage) and stage 2b
  (stuck-on stage with the current sense at 0 A).
- **The two COOLDOWN traces and the PAN_DET gap.** These depend on the legacy
  SIL's 100 ms update. Their replacements run in both modes.

C1 results (`sil_fault_tests_c1` output):
- **Stuck-on stage:** latches in 4 rows (0.4 s), against 120 (HEATING) and
  200 (PREHEAT) rows for legacy.
- **Double fault:** the legacy trace (the loop still commanding) is now
  caught by current-sense check (a) in 4 rows. With the loop not commanding
  (pan over target), stage 2b latches in 199 rows (bound 350, D-RUN).
- **Current sense dead:** (a) in 4 rows; dead from power-up, the start-up
  pulse in 11 rows (D-ISENSE).
- **Open Pt100:** held as FAULT_PROBE_OPEN (no longer RUNAWAY); a reset is
  accepted once the element is back. A flagged 380 °C reading still latches
  RUNAWAY (D-OPEN).
- **Pt100 leakage, the chain** (rim 105 °C over a reading sagging to 75 °C):
  FAULT_PROBE_LEAKAGE in 901 rows (bound 1250, D-LEAK).
- **Pt100 leakage, the rim limit** (rim 140 °C over a 100 °C reading;
  150 °C over 85 °C in PREHEAT): 166 and 267 rows (bounds 300 and 400,
  D-RIMLIM).
- **Pt100 leakage, the cold soak** (1 kΩ from power-up, 40 min idle in a
  25 °C room): FAULT_PROBE_LEAKAGE in the first PREHEAT period, 1 row (bound 2),
  before any power; an intact probe passes; a 10 min idle skips (D-SOAK).
- **20 K/s sensor rise:** R1 latches in 62 rows (6.2 s), before the reading
  passes 216 °C.
- **Frozen code:** 50 rows from the freeze onset in IDLE, PREHEAT and
  HEATING.

The C1 run found two defects, both fixed in `main/state_machine.c`:
- **D-LATCH.** A latched register-07h fault re-entered FAULT and logged to
  EEPROM on every conversion (251 entries rather than 1). A later sensor
  report overwrote the latched fault code.
- **D-RESET.** `fault_cleared()` used the legacy RTD window, and accepted a
  reset while the converter service had stopped.

## Harness (this folder)

| File | Role |
|---|---|
| `ref.py` | Python references: the KF (checked equal to r2 `KFNoPower`), the D1 replay, and the truth plant with a hot pan. |
| `export_vectors.py` | Writes `firmware/test/{pan_temp_estimator,contact_check}_vectors.h` and `vectors-summary.json`. Deterministic. |
| `cosim_shim.c`, `build_lib.sh` | The fifteen C sources (the seven loop modules, the supervisor, the current-sense and leak checks, the rim limit, the cold-soak check, the rim and heatsink NTC drivers, and the Pt100 conversion) and the ctypes shim, built as a host `.so` with plain `cc`. |
| `cosim.py` | Copy of screen.py `run()` with the C loop in it. Runs the cases below and writes `cosim-results.json`; gates the bars. The shadow is `../robustness/shift_kf.py` (KF plus window). |
| `../robustness/hc_cosim.py` | The 64 gated h_c steps and 100 oil / water / crud cases through the same C loop, before vs after. Writes `../robustness/hc-cosim.json`; gates R-HS / R-CT. |
| `b5_montecarlo.py` | D1 over 20 seeds and 3 rule sets. Writes `b5-montecarlo.json`; gates safety. |
| `d1_nuisance.py` | F1: 132 rim-limit stress benign cases at each of 250 and 230 °C through the unchanged C loop. Writes `d1-nuisance.json`; gates recorded D1 LOST ceilings of 2 and 1, with exact evidence verification via `--check`. |
| `sensitivity.py` | Tolerance to errors in a, and the loss-term variant. Writes `sensitivity.json`; reported only. |
| `runaway_checks.py` | Legacy vs C1 runaway rules on 50 Hz quantised readings: false trips (also with the stage in burst mode), fault detection times, the stage-2b sweep, and the current-sense checks against latent and simultaneous sense failures. Writes `runaway-checks.json`; gates the C1 rules (DECISIONS D-RUN, D-ISENSE, D-OPEN). |
| `sensor_fail_codes.py` | Recomputes the sensor-failure codes from IEC 60751 and shows 850 °C is out of the plant's reach. Writes `sensor-fail-codes.json`; gates `rtd_convert.h` (DECISIONS D-OPEN). |
| `fault_cycle.py` | The MAX31865 manual fault-detection timing on the CR-1 board (`pcb/checks.py`'s MNA network, 1536 corners): τ_max, the waits, the automatic cycle's false flags, the bits per wiring fault. Writes `fault-cycle.json` and `mock_max31865_afe.h`; gates `rtd_service.h` (DECISIONS D-FCYC). |
| `rail_adc.py` | The v3v3 reading's error budget (LM4040A25 SLOS456Q, MCP3202 DS21034F; `--verify-*-pdf`) against board temperature, the soak-band and full-range figures, the plausibility window, SPI mode and clock. Writes `rail-adc.json`; gates `rail_adc.h` (DECISIONS D-RAIL). |
| `rim_ntc.py` | The 104GT-2 R-T table, transcribed from the Semitec GT-2 datasheet (`--verify-pdf` re-extracts it). Writes `rim_ntc_table.h` and `rim-ntc.json`: interpolation error, K/mV, saturation and short temperatures, self-heating, and the rail error with the rail unknown and measured. Gates. |
| `cr7_thresholds.py` | Recomputes the MAX31865 C1 threshold words from the CR-7 inputs (R(−40 °C), R(360 °C)) using the firmware's derivation rule. Writes `cr7-thresholds.json`; gates `config.yaml` (DECISIONS D-THRESH). |
| `xcheck_cosim.py` | The rim NTC in the loop. The plant gets a glass node at T_c − Δ, and the NTC runs at its tolerance corners through the C driver. Covers benign runs and Pt100 leakage. Writes `xcheck-cosim.json`; gates benign runs (DECISIONS D-RIM). |
| `leak_checks.py` | The leak sweep (13 leaks 300 Ω–10 kΩ × 4 pans × Δ × bead corner) and 548 benign runs through the same glass and rim model, against the leak check and the rim limit. Writes `leak-checks.json`; gates 0 benign latches, the recorded status of the 300 °C bar and the recorded rim-limit coverage (DECISIONS D-LEAK, D-RIMLIM). |
| `rim_limit.py` | The rim limit's glass envelope (from `../cad/thermal-axisym.json` and study 08), its tolerance table, and the trade-off curve (margin × τ_dec × "not falling" × constant/table stack against coverage and false latches) over the sweep, the benign runs and worst-case stress sets; the CR-5 band study. Writes `rim-limit.json`; gates the firmware constants and the chosen variant's 0 false latches (DECISIONS D-RIMLIM). |
| `leak_alternatives.py` | Candidates B (energy plausibility) and C (cold soak, temperature-independent vs Arrhenius leaks, closed form at 35 °C against the `hs-ntc.json` threshold). Writes `leak-alternatives.json`; reported only (DECISIONS D-RIMLIM). |
| `hs_ntc.py` | The heatsink NTC's R-T table (Vishay doc 29049 material D column; `--verify-pdf`, `--verify-lug-pdf`, `--verify-esp-pdf` re-extract the sources; `--verify-board-ref controller-c1-crs` re-reads the zapote circuit, PCB and C45), the channel through the CR-8 divider (gain band, accuracy, VALID range, SAR sampling, divider faults, short, trip points, the pre-C45 row) and the cold-soak error budget (as a corner) and timing. Writes `hs_ntc_table.h` and `hs-ntc.json`; gates the table, `HS_NTC_ADC_GAIN` and the `pan_cold_soak.h` constants (DECISIONS D-HSNTC, D-SOAK). |
| `cold_soak_guards.py`, `F3-STUDY.md` | F3 comparison of eight guards through the C check, all baseline false-latch trajectories/readings, per-ambient/rail coverage and validation limits. CSV evidence goes to a caller-selected scratch directory. |
| `cold_soak.py` | The cold-soak check through the C (`hs_ntc.c`, `rtd_convert.c`, `pan_cold_soak.c` via `cosim_shim.c` `soak_run`) on the CR-8 board, rail unknown and rail measured (each with the threshold the firmware picks): threshold cross-checks, 954 benign cold-start trajectories per rail variant (318 × 3 corners, including τ_h 3600 s) (gated: 0 latches in both), sets outside the assumptions (reported), and the 277 hazardous leak runs (peak rule) at a cold start, temperature-independent and Arrhenius. Writes `cold-soak.json` (DECISIONS D-SOAK). |

The co-sim cases are:
- 16 design cases;
- 12 stress cases;
- 4 loss, 3 food and 4 nominal runs;
- 8 runs with a probe forced on intact contact (16 probes);
- 3 hot-pan placements;
- 4 h_c steps.

Each case runs in three gain modes:
- **true:** a fixed at the true value, as in screen.py;
- **id_measured:** a identified, with measured power;
- **id_estimated:** a identified from the commanded power, while the coil
  delivers P·(1.10 − 0.20·P/P_max).

## F1: D1 nuisance power cuts

`d1_nuisance.py` runs `rim_limit.stress_benign()` through the unchanged
`leak_checks.run_case`: 132 cases at each final-setpoint cap, 250 and 230 °C.
It preserves the cap study's factory ordering, down-step targets, seeds,
and glass/NTC corners. Production D1 is unchanged: the investigated correction
missed a real lift, so the gate retains the recorded ceilings of 2 LOST events
at 250 °C and 1 at 230 °C. Curvature fields describe that rejected counterfactual
candidate, never active detector behavior.

From this folder:

```sh
python3 d1_nuisance.py                 # write d1-nuisance.json beside the script
python3 d1_nuisance.py --check         # rerun and compare without rewriting it
```

`--out PATH` selects another evidence file; `--jobs N` changes concurrency.
Every invocation rebuilds the C library. `run.sh` step 4b invokes `--check`
without `--lib`, keeping the fresh build portable across host toolchains.
The comparison is exact for every count, float, and source-content hash; it
ignores only the six strings `python`, `numpy`, `scipy`, `matplotlib`, `machine`,
and `compiler` inside the `toolchain` object. Source provenance includes the
fixed task base and content changes from that base, independent of HEAD.

A transparent proxy reruns cases containing LOST and records every LOST event,
trigger source, complete 181-sample decision window, original C `d`, `d_exp`,
decay RMS and change, reconstructed significance, retry episode, and actual
zero-power interval. State restoration and continuous power-off time have
separate censoring flags. The read-only host shim `sim_cc_params` reports the
live C parameters after initialization; Python does not mirror C struct layouts.

T2 (`../leak-barrier/setpoint_cap.py --check`, step 5d) freezes its source inputs,
including this folder's Python files and `cosim_shim.c`. The new diagnostic and
parameter getter change those inputs and therefore cause its existing source
and evidence checks to fail. T2 and all existing gates remain unchanged; an F1
pass does not establish a full `run.sh` pass.

## Results (`cosim-results.json`)

| Bar | true | id_measured | id_estimated |
|---|---|---|---|
| B1 design ≥ 15/16 | 15/16 | 15/16 | 15/16 |
| B2 design 16/16 | 16/16 | 16/16 | 16/16 |
| B3 design 16/16 | 16/16 | 16/16 | 16/16 |
| B5 detected / worst suspect / worst confirm | 4/4, 2.7 s, 20.7 s | 4/4, 2.9 s, 20.9 s | 4/4, 2.8 s, 20.8 s |
| B5 T_c − SP (≤ 15 K) | 6.72 K | 6.89 K | 6.94 K |
| False latches: nominal, food, design, probe on intact contact | 0 | 0 | 0 |
| Identified a / a_true at end of first ramp (±30 %) | n/a | 0.88–1.115 | 0.881–1.087 |
| a / a_true after the later step (0.7–1.6, D-ID2) | n/a | 0.926–1.251 | 0.881–1.117 |
| Runaway supervisor latches / R1 trips | 0 / 0 | 0 / 0 | 0 / 0 |
| C vs Python shadow rms (≤ 0.05 K) | 8.8e-5 K | 1.3e-4 K | 1.3e-4 K |
| h_c steps, 64 cases (`../robustness/hc-cosim.json`): B2 / worst overshoot | 64/64, 4.95 K | 64/64, 5.00 K | 64/64, 4.72 K |
| Oil 28 + water 54 cases: T_c ≤ SP + 15 K, no D1 latch | 82/82 | 82/82 | 82/82 |

The one B1 miss is the same case in all three modes, the same as Python's
15/16: cast iron at h_c 12991, with a worst error of 3.07–3.09 K.

Identified a / a_true per pan, at the end of the first ramp:

| Pan | id_measured | id_estimated |
|---|---|---|
| carbon steel | 0.88–0.887 | 0.908–0.914 |
| cast iron | 1.082–1.115 | 1.025–1.087 |
| triply clad | 0.926–0.931 | 0.958–0.967 |
| water pot | 1.001–1.049 | 0.881–0.912 |

Reported, not gated:
- **Stress:** B1 7/12, 6/12, 7/12 (8/12 before D-CSW: one window without a
  contact change, DECISIONS D-CSW).
- **Hot pan:** 3/3 pass B1–B3, with no guard fault.
- **h_c steps (the original 4):** 1000 → 300 overshoot 1.93–4.21 K (was up
  to 13.09 K). 300 → 3000 still overshoots 5.65–7.08 K in the first ramp at
  h_c 300, before the step. The supervisor does not latch on them.
- **Crud:** a stuck post with pan bow over-heats T_c by up to 42.58 K, 8 of 15
  cases over SP + 15 K. This is not observable by the sensor
  (`../robustness/DECISIONS.md` R-B4).

Monte Carlo (`b5-montecarlo.json`): the firmware rule set passes with 80/80
losses detected, 0 false restores and 0 false latches in 300 non-loss runs.
DECISIONS D-D1 and D-B5 cover the other two rule sets.

Runaway checks (`runaway-checks.json`):
- Legacy false trips on 75 benign runs: the 15 K/s check trips 58, target
  + 10 K trips 21, the equal-reading check trips 24.
- C1 false trips: 0.
- Every hazardous fault is caught by C1 before T_c exceeds 301 °C. The one
  case later than legacy is the double fault (stuck-on stage with a failed
  current sense): ≤ 35.0 s, T_c ≤ 245.7 °C (DECISIONS D-RUN).
- Current sense (D-ISENSE): a sense that fails before the stage sticks is
  caught first (dead at power-up: the pulse, 1.0 s; dying at 100 s: 0.4 s
  later), 36/36 latent cases. A sense dying alone is caught in 0.4 s, 36/36.
  There are 0 false trips on the 75 benign runs and on the same 75 with the
  stage bursting below its 160 W floor.
- Open / short Pt100 (D-OPEN): `rtd_fail_code` at 0.00 s, no RUNAWAY.

## Rim NTC and threshold words

From `rim-ntc.json`, `cr7-thresholds.json` and `xcheck-cosim.json`
(DECISIONS D-RIM, D-THRESH):

| Item | Result |
|---|---|
| Table | 104GT-2, −50 to 300 °C, 38 points. Matches the datasheet PDF and pcb/checks.py. B25/85 4267 K. |
| Interpolation (leave-one-out, 20 K step) | 0.030 K worst (log-linear in T: 0.257 K) |
| Chain error, 100/150/200/250 °C (test) | ≤ 0.073 K at v3v3 3.242 V, ≤ 0.026 K at 3.300 V |
| Attenuation at 100/150/200/250 °C | ATTEN3 / ATTEN3 / ATTEN2 / ATTEN0 |
| Resolution, 100–250 °C | 0.143 K/mV worst (requirement ≤ 0.3 K) |
| Saturated (cold) below | 87.05–96.51 °C over v3v3 3.242–3.367 V |
| Short (0.25 V) | 297.5–300.4 °C |
| Not corrected | Self-heating ≤ 4.53 K (still air). The rail costs ≤ 4.37 K when unknown, ≤ 2.87 K measured (MCP3202, D-RAIL). |
| Fault policy | Latch through the RTD sink: short/over-range → FAULT_PROBE_SHORT, open/ADC → FAULT_PROBE_OPEN |
| Threshold words | 12844 / 35544. Recomputed from R(−40 °C) / R(360 °C), matching CR-7. The firmware was fixed from 35542. |
| Cross-check co-sim, benign (28 runs) | 0 D1 lost, 0 guard / rim / supervisor faults. 2 cross-check suspects (cast iron food). |
| Cross-check co-sim, Pt100 leakage (16 runs) | 1 kΩ: suspect in 5 of 8, 233–292 s after the leak, but the probe confirms contact and T_c reaches SP + 121.9 K; two meet the rim over-range fault first. 3 kΩ: no suspect, SP + 35.8 K. |
| Leak checks (`leak-checks.json`, 624 leak runs, 548 benign) | Hazardous (untripped T_c > 300 °C at any time, transient overshoot included, owner 2026-10-16; 250 °C setpoint): 300 Ω–2.32 kΩ, 277 runs (steady rule: 235, to 1.73 kΩ). With the rim limit (D-RIMLIM), latched before T_c passes 300 °C: 69 (59 of 235 steady rule; 7 with the D-LEAK chain alone). After: 204 (T_c ≤ 431.1 °C; was ≤ 474.2 °C). Never: 4 (2.32 kΩ, Δ 46 K, cold bead, peak 300.3–302.2 °C, settling at 299.3–299.5 °C; 0 under the steady rule, 9 before D-RIMLIM). The 300 °C bar is not met: at 250 °C the benign and leaking glass overlap by ~46 K. Insulation, a hot production test and seal qualification carry it (DECISIONS D-BARRIER, `../leak-barrier/SPEC.md`); no setpoint cap (≤ 15.6 % at the worst corner even at 200 °C, `../leak-barrier/setpoint-cap.json`) and CR-5 unchanged (a retuned band adds 0 over firmware at every cap, `../leak-barrier/cr5-band.json`). ≥ 4.16 kΩ is invisible. Benign: 0 latches. |
| Heatsink NTC (`hs-ntc.json`) | Vishay material D, −40–150 °C; polynomial 0.027 K, leave-one-out 0.029 K. CR-8 gain 0.855072 (band 0.854421–0.855722): VALID from −40 °C at every corner (pin ≤ 2.876 V). At 25 / 95 °C: ADC 4.7 / 0.46 K, tolerance 0.44 / 1.87 K, rail ≤ 5.3 / 1.1 K unknown, ≤ 3.4 / 0.71 K measured, SAR sampling 0.30 / 0.15 K (20 pF assumed). Divider fault at ≥ 2950 mV (intact worst 2937 mV). Cold-soak threshold 19.4 K (16.9 K rail measured). |
| Cold soak (D-SOAKTAU, `F3-STUDY.md`) | F3 rate guard: 0 latches on 954 gated trajectories per rail (corners included), including all 126 τ_h 3600 s trajectories. Original report-only false-latch counts fall from 23/24 to 23/23 (fallback/measured); frozen pots remain 22/36 and cold rooms 1/6 in each rail. Nominal independent-leak coverage at 5 / 15 / 25 / 30 / 35 / 40 °C stays 180 / 212 / 212 / 212 / 212 / 212 (fallback) and 212 / 212 / 212 / 248 / 248 / 248 (measured), of 277; all evaluated family/corner cells are preserved. Canonical JSON remains pre-F3 pending a Mac evidence refresh; the study records Linux results and T1/T2 provenance blockers. |
| Rim limit (`rim-limit.json`) | Limit 125.1 / 210.4 / 260.8 °C at a 100 / 200 / 250 °C reference. Trade-off (peak rule, of 277): margin −1 K → 76 but 28 false latches on 132 stress runs; 0 K → 70, 0 false, 4 never latched; +2.5 K → 64 and 22 never latched. At the leak envelope (warped pan, cool eye, cold stack) 3/137 before 300 °C. CR-5: lowering by 8 K (86.6 k → 76.8 k) adds 9/277, 7.8 K over the benign glass. |

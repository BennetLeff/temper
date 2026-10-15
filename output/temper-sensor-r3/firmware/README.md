# sensor-r3 C1 firmware and C-in-the-loop co-simulation

HANDOFF section C. The C1 algorithms are host-tested C in
`firmware/components/control/`. The same C runs closed-loop against the r3
Python truth plant here. Decisions and open items are in `DECISIONS.md`.

**Rerun everything:** `./run.sh`. It takes about 5 min and exits non-zero on any
failure. It includes both SIL configurations and their coverage gate.

The firmware build uses the C1 runtime when `TEMPER_PAN_CONTROL_C1` is
defined; `main/CMakeLists.txt` defines it for the ESP-IDF target (DECISIONS
D-MODE). `main/pan_control.{c,h}` connects the loop to the state machine, the
MAX31865 service and the power stage.

## Firmware sources (`firmware/components/control/`)

| File | What it does |
|---|---|
| `pan_temp_estimator.{c,h}` | 4-state KF [T_pan, v, T_cap, T_el]. dt 0.1 s, 5 substeps. Float, with all constants in `pte_params_t`. |
| `plant_gain.{c,h}` | Online a = η/C identification with RLS. Tags each power sample as measured or estimated. |
| `pan_rate_pid.{c,h}` | The r2 rate-domain PID, scheduled by a. |
| `contact_check.{c,h}` | D1, as in screen.py, plus the firmware rules D-D1a–c. Fixed ring buffer, no heap. |
| `pan_sensor_guard.{c,h}` | Checks MAX31865 07h, SPI, stale data, range, rate, and the rim cross-check. Reports into the existing RTD fault sink. |
| `pan_temp_loop.{c,h}` | Composes the modules above and holds power authority: it never chases a cold reading. |
| `pan_supervisor.{c,h}` | Runaway supervision that replaces the legacy 15 K/s and target + 10 K latches in C1 builds: R1 sustained rise, and R2 stages 1/2a/2b (DECISIONS D-RUN). |

The C1 MAX31865 path is in `firmware/components/sensors/`:
- `rtd_convert.{c,h}` converts code → Ω → °C, with the CR-7 self-heating and
  optional loading correction;
- `rtd_service.c` runs the C1 thresholds, the power-up fault cycle, continuous
  conversion, the DRDY-stale check and the frozen-code check (DECISIONS
  D-CR7, D-STALE).

## Host tests (`firmware/test/`, registered in `CMakeLists.txt`)

| Test | Coverage |
|---|---|
| `test_pan_temp_estimator_only` | 6 tests. Golden vectors from `export_vectors.py`: worst max \|C − Py\| 0.00009 K, against a bar of 0.05 K. |
| `test_contact_check_only` | 11 tests. Replays loss on 4 pans, food on 3 and nominal runs, in screen mode and firmware mode, plus synthetic cases. |
| `test_pan_temp_loop_only` | 19 tests. Guard, plant gain (including the later-step updates), PID and power authority. |
| `test_pan_contact_sm_only` | 2 tests. EVENT_CONTACT_LOST in the state machine. |
| `test_c1_units_only` | 17 tests. Supervisor R1/R2 and code-to-temperature conversion. |
| `test_c1_runtime_only` | 11 tests. The C1 state machine and `pan_control`: hot pan, h_c drop, lowered target, power stage disobeying, rising with power off, absolute 300 °C, intensity, C1 RTD window. |
| `test_c1_rtd_service_only` | 6 tests. The C1 MAX31865 sequence through the SPI mock: thresholds, fault cycle, conversion, fault flag, stale, frozen. |
| `test_sil_fault_injection` / `test_sil_fault_injection_c1` | The SIL fault-injection suite, built twice from one runner and `traces/manifest.json` (D-SIL). Legacy runs 31 scenarios. C1 runs 36: it uses the real MAX31865 service through a register-level converter model at the firmware's 10 ms cadence, and the bus current follows the command. |

## SIL fault injection in both configurations (D-SIL)

`python3 firmware/test/test_sil_coverage.py --gate` prints and gates
coverage. CI runs it as `scripts/check_sil_coverage.py`.

| Mode | Scenarios | (fault class, origin) pairs | C1 mechanism × origin |
|---|---|---|---|
| legacy | 31 | 20/20 | n/a |
| C1 | 36 | 23/23, a superset of legacy's (adds IDLE) | 16/16 |

The C1 mechanisms are:
- R1 and the absolute 300 °C check;
- R2 stages 1, 2a and 2b;
- register 07h, DRDY stale and frozen code.

Four legacy scenarios are legacy-only, and each names its C1 replacement:
- **Thermal Runaway (target + 10 K latch).** Replaced by stage 1 (no latch,
  power 0 for 31 s at target + 15 K), stage 2a (stuck-on stage) and stage 2b
  (stuck-on stage with the current sense at 0 A).
- **The two COOLDOWN traces and the PAN_DET gap.** These depend on the legacy
  SIL's 100 ms update. Their replacements run in both modes.

C1 results (`sil_fault_tests_c1` output):
- **Stuck-on stage:** latches in 4 rows (0.4 s), against 120 (HEATING) and
  200 (PREHEAT) rows for legacy.
- **Double fault:** 207 rows (20.7 s). The bound is 350 (D-RUN).
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
| `cosim_shim.c`, `build_lib.sh` | The seven C sources (the six loop modules and the supervisor) and the ctypes shim, built as a host `.so` with plain `cc`. |
| `cosim.py` | Copy of screen.py `run()` with the C loop in it. Runs the cases below and writes `cosim-results.json`; gates the bars. |
| `b5_montecarlo.py` | D1 over 20 seeds and 3 rule sets. Writes `b5-montecarlo.json`; gates safety. |
| `sensitivity.py` | Tolerance to errors in a, and the loss-term variant. Writes `sensitivity.json`; reported only. |
| `runaway_checks.py` | Legacy vs C1 runaway rules on 50 Hz quantised readings: false trips, fault detection times, and the stage-2b sweep. Writes `runaway-checks.json`; gates the C1 rules (DECISIONS D-RUN). |

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

## Results (`cosim-results.json`)

| Bar | true | id_measured | id_estimated |
|---|---|---|---|
| B1 design ≥ 15/16 | 15/16 | 15/16 | 15/16 |
| B2 design 16/16 | 16/16 | 16/16 | 16/16 |
| B3 design 16/16 | 16/16 | 16/16 | 16/16 |
| B5 detected / worst suspect / worst confirm | 4/4, 2.6 s, 20.6 s | 4/4, 2.5 s, 20.5 s | 4/4, 2.6 s, 20.6 s |
| B5 T_c − SP (≤ 15 K) | 12.04 K | 12.0 K | 11.65 K |
| False latches: nominal, food, design, probe on intact contact | 0 | 0 | 0 |
| Identified a / a_true at end of first ramp (±30 %) | n/a | 0.88–1.115 | 0.881–1.087 |
| a / a_true after the later step (0.7–1.6, D-ID2) | n/a | 0.926–1.251 | 0.881–1.117 |
| Runaway supervisor latches / R1 trips | 0 / 0 | 0 / 0 | 0 / 0 |
| C vs Python shadow KF rms (≤ 0.05 K) | 3.8e-5 K | 3.8e-5 K | 3.9e-5 K |

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
- **Stress:** B1 8/12, as in Python.
- **Hot pan:** 3/3 pass B1–B3, with no guard fault.
- **h_c steps:** B1 0/4, B2 0/4, overshoot up to 13.09 K (DECISIONS open
  item 9). The C1 supervisor does not latch on them.

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


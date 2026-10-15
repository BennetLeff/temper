# sensor-r3 C1 firmware and C-in-the-loop co-simulation

HANDOFF section C. The C1 algorithms are host-tested C in
`firmware/components/control/`. The same C runs closed-loop against the r3
Python truth plant here. Decisions and open items are in `DECISIONS.md`.

**Rerun everything:** `./run.sh`. It takes about 4 min and exits non-zero on any
failure.

## Firmware sources (`firmware/components/control/`)

| File | What it does |
|---|---|
| `pan_temp_estimator.{c,h}` | 4-state KF [T_pan, v, T_cap, T_el]. dt 0.1 s, 5 substeps. Float, with all constants in `pte_params_t`. |
| `plant_gain.{c,h}` | Online a = η/C identification with RLS. Tags each power sample as measured or estimated. |
| `pan_rate_pid.{c,h}` | The r2 rate-domain PID, scheduled by a. |
| `contact_check.{c,h}` | D1, as in screen.py, plus the firmware rules D-D1a–c. Fixed ring buffer, no heap. |
| `pan_sensor_guard.{c,h}` | Checks MAX31865 07h, SPI, stale data, range, rate, and the rim cross-check. Reports into the existing RTD fault sink. |
| `pan_temp_loop.{c,h}` | Composes the modules above and holds power authority: it never chases a cold reading. |

## Host tests (`firmware/test/`, registered in `CMakeLists.txt`)

| Test | Coverage |
|---|---|
| `test_pan_temp_estimator_only` | 6 tests. Golden vectors from `export_vectors.py`: worst max \|C − Py\| 0.00009 K, against a bar of 0.05 K. |
| `test_contact_check_only` | 11 tests. Replays loss on 4 pans, food on 3 and nominal runs, in screen mode and firmware mode, plus synthetic cases. |
| `test_pan_temp_loop_only` | 15 tests. Guard, plant gain, PID and power authority. |
| `test_pan_contact_sm_only` | 2 tests. EVENT_CONTACT_LOST in the state machine. |

## Harness (this folder)

| File | Role |
|---|---|
| `ref.py` | Python references: the KF (checked equal to r2 `KFNoPower`), the D1 replay, and the truth plant with a hot pan. |
| `export_vectors.py` | Writes `firmware/test/{pan_temp_estimator,contact_check}_vectors.h` and `vectors-summary.json`. Deterministic. |
| `cosim_shim.c`, `build_lib.sh` | The six C sources and the ctypes shim, built as a host `.so` with plain `cc`. |
| `cosim.py` | Copy of screen.py `run()` with the C loop in it. Runs the cases below and writes `cosim-results.json`; gates the bars. |
| `b5_montecarlo.py` | D1 over 20 seeds and 3 rule sets. Writes `b5-montecarlo.json`; gates safety. |
| `sensitivity.py` | Tolerance to errors in a, and the loss-term variant. Writes `sensitivity.json`; reported only. |

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
  item 3).

Monte Carlo (`b5-montecarlo.json`): the firmware rule set passes with 80/80
losses detected, 0 false restores and 0 false latches in 300 non-loss runs.
DECISIONS D-D1 and D-B5 cover the other two rule sets.

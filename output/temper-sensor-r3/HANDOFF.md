# sensor-r3 HANDOFF: the C1 pan sensor (CAD, PCB, firmware + in-the-box tests)

**Repo:** `/Users/bennet/Desktop/temper`. **Design folder:**
`output/temper-sensor-r3/`. Read `README.md`, `DECISIONS.md` and `PATENTS.md`
there first. Each section below is self-contained, so one agent can take one
section with no other context.

## Rules for every agent

- **Git and builds:**
  - Do not commit, push, `git stash`, or create worktrees. Leave new files
    untracked in your output folder.
  - Do not build the Rust workspace.
- **Read-only paths:**
  - `hardware/native21-*`, `elec/`
  - everything under `worktrees/` and `.worktrees/` (a power-stage session
    is live)
  - `firmware/components/owned_controls/`, `output/temper-owned-controls/`
    (Codex R44)
  - all `output/temper-manufacturing-r*` folders (frozen rounds). You may
    import their `src/*.py` for interface checks.
- **Evidence:** every numeric claim must come from a committed, rerunnable
  script in your folder. Check every part at its worst-case corner against
  its datasheet, on a UL basis, not IEC.
- **Patent design rules (P1, from `PATENTS.md`).** Do not introduce any of:
  - a flexible diaphragm or boot that receives the sensor;
  - a slot in the sensor with a flange engaged in it;
  - pins running in side slots as stops;
  - a plunger inner column and outer cap with the spring nested between them;
  - a compliant bumper under the sensor holder;
  - a sliding ramp clamp;
  - any heater or deliberate self-heating;
  - a second temperature sensor under the cap;
  - any plunger position sensor (optical or otherwise);
  - any actuator that moves the sensor;
  - a counterbore in the glass to seat the probe.

  If a requirement seems to need one of these, stop and record it in your
  DECISIONS.md instead.
- **Media:** never copy video frames into the repo.

## What C1 is (shared spec)

| Item | Value | Source |
|---|---|---|
| Contact disc | Si3N4, Ø8.0 × 0.32 mm, top lapped flat ≤ 1 µm, Ra ≤ 0.1 µm, 0.2 mm × 45° edge chamfer (contact Ø7.6) | `cartridge_budget.py` |
| Element | IST P0K1.202 Pt100 chip (1.8 × 2.0 × 0.65), 4-wire, bonded under the disc centre | R15/R16 |
| Bond | 0.10 ± 0.03 mm, k ≥ 1.5 W/m·K, **continuous rating ≥ 260 °C required** (EPO-TEK 930-4 publishes only "< 325 °C intermittent"; get a vendor statement or choose a rated alternative) | DECISIONS §3 |
| Thermal targets | C_cap ≤ 45 mJ/K; G_bond ≥ 0.05 W/K; cold-side leak ≤ 0.8 mW/K | `cartridge_budget.py` gates |
| Post | Polymer (polyimide, Vespel SP-1 class, preferred; PEEK only if its UL RTI covers the modelled post-top temperature). Thin neck ≥ 6 mm long, wall 0.25 mm, OD 8.0; alumina-silica fibre or aerogel plug in the cavity below the chip; leads potted at the post foot | budget |
| Seal | **Sliding wiper lip** on the neck OD, in the body's top collar inside the Ø18 glass bore. PTFE (FDA) if its modelled temperature is ≤ 250 °C, else FFKM (FDA grade). Friction ≤ 0.3 N. Static gasket between body rim and glass underside. | DECISIONS §3, P1 |
| Stroke | 0.60 ± 0.10 mm proud at rest, ≥ 1.2 mm stroke, down to flush or below before any hard stop. Up-stop: post shoulder against collar underside. | R16 |
| Spring | 1.2–1.8 N over the stroke, acting on the post foot through an on-axis spherical/conical seat so the post can rock | contact model |
| Tilt | Post free to rock ≥ ±5 mrad about a point within 1 mm of the disc face. Relative face-to-pan tilt ≤ 2 mrad under wiper friction. | `contact_model.py` |
| Rim NTC | Unchanged: Semitec 104GT-2 glass bead in the body rib pocket Ø1.8 × 3.5, bearing on the glass underside **outside the cap** (R36/R40) | US10278238B2 rule |
| Cable | 6 conductors: Pt 4-wire plus NTC 2-wire. The first 20 mm of Pt leads in low-k alloy (constantan class, Ø0.08), then high-temperature PTFE/FEP-insulated copper. | budget |
| Firmware model | KF with fixed contact h_nom 1300 W/m²K; detector D1; gain-scheduled PID | `screen.py` |

---

## A. CAD agent: the C1 cartridge in the R43 interfaces

**Goal.** A complete, checked CAD model of the C1 cartridge that drops into the
R43 sensor position without changing the glass, carrier or coil, plus fabrication
drawings and a quote list.

**Output:** `output/temper-sensor-r3/cad/`, containing:
- a generator in build123d (as R43 uses), `cartridge_r3.py`, exposing
  `r3_cartridge(travel_mm, tilt_mrad=0)` with part dicts in R43's
  `{name, shape}` style;
- `checks.py` → `checks.json`;
- STEP files, assembled and half-section;
- `render.png`, made with PyVista/VTK off-screen. Do not use matplotlib 3D:
  it has no z-buffer.
- `DRAWINGS.md` (critical dimensions and tolerances per custom part);
- `QUOTE-LIST.md`;
- `DECISIONS.md`.

**Interfaces.** Import these read-only from
`output/temper-manufacturing-r43/src`:

- Glass: `enclosure_r5.build()`, part `enclosure_glass_350x340x4_sensor_bore`.
  Glass top Z = 110.0, 4 mm thick, sensor axis at X 0, Y 261. The bore is Ø18
  (study 08). Confirm it from the shape.
- Carrier: `sensor_coil_r5.support()`, part `…routed_insulating_carrier`.
- R16 cartridge for reference: `sensor_coil_r5.r15_cartridge(travel)`.
- Keep R16's body principles:
  - the rigid rim registers on the glass underside (r12.2–13);
  - wave-spring float, A-286 gap-type spring, 3–15 N;
  - three-lug 60° bayonet into the carrier notches, with the Ø2 × 0.5 detent
    bump;
  - service from above with the cover lifted.
- Coil: the eye is clear to the coil spec (≥ Ø40); use the R43 coil part for
  clearance.
- Rim NTC pocket: as R40.

**Parts to model:**

- disc
- chip
- bond layer
- post: neck plus foot with the spherical seat
- fibre plug
- potting at the post foot
- wiper lip ring
- body with:
  - top collar in the bore
  - rim
  - static gasket groove
  - guide bushing
  - spring seat
  - bayonet lugs
  - NTC rib
  - lead exit
- spring
- wave spring
- static rim gasket
- retention for the post foot: a stop collar or circlip on the foot, never
  pin-in-slot
- cable strain relief

**Gates.** Every gate must PASS in `checks.json`; if one fails, record why.

1. **G1 collisions.** No collisions among moving and fixed parts, glass and
   carrier at travel 0 / 0.6 / 1.2 mm × tilt −5 / 0 / +5 mrad (two
   orthogonal axes). Follow the method in
   `output/temper-manufacturing-r43/evidence/sensor-r16/check_cartridge.py`.
2. **G2 protrusion.** 0.60 ± 0.10 mm, from the rim datum through the tolerance
   chain (worst-case stack listed). The disc is flush or below before any hard
   stop.
3. **G3 heat capacity.** Put the as-modelled dimensions into a copy of
   `../cartridge_budget.py` (`cad/budget_asbuilt.py`). C_cap ≤ 45 mJ/K.
4. **G4 cold leak.** ≤ 0.8 mW/K in the same script. Split the leak into the
   part going to the glass-bore collar (tracked by the rim NTC) and the part
   going to the body below the glass and to the cable (cold). Only the cold
   part is gated.
5. **G5 tilt follow.** A hand calculation of the righting moment (spring
   force × seat geometry) against the wiper friction moment (μ 0.3 × lip load
   × neck radius). This shows the residual relative tilt is ≤ 2 mrad for a
   5 mrad pan tilt.
6. **G6 disc strength.** Safety factor ≥ 2 at 20 N (bench T5 sliding load)
   over the as-drawn chip pocket (Roark simply-supported plate, as in the
   budget), plus 1 kg / 100 mm ball drop reasoning: the disc retracts, so the
   load path ends at the glass.
7. **G7 field.** No electrically conductive part inside Ø20 above the coil
   plane, except the open-helix spring. Re-screen that spring's eddy heating
   with `output/temper-manufacturing-r43/evidence/sensor-r16/thermal_screen.py`
   methods at B 5–20 mT.
8. **G8 temperatures and ratings.** Estimate the steady temperatures of the
   wiper, post top, bond and gasket under a 260 °C pan. Use the glass study
   inputs (`output/temper-r33-studies/08-undrilled-glass-sensor/`). Compare
   each to its datasheet continuous rating and UL RTI, and record the RTI
   source per material.
9. **G9 spill.** Model the path for liquid that passes the wiper: a sealed
   sump of ≥ 2 ml inside the body, or a drain away from the coil and live
   parts. Show no path to the coil, leads or carrier electronics.
10. **G10 assembly.** Drop the cartridge through the carrier notches and turn
    60° with the cover off; then the cover-on condition. Re-use
    `output/temper-manufacturing-r43/src/check_assembly_sequence.py` patterns.
11. **G11 insulation geometry.** Clearance and creepage from any coil winding
    or lead to any cartridge conductor, at least the values that section B
    sets.
12. **G12 P1 audit.** A table, part by part, against the patent design rules
    above.

**Done when:** all gates pass (or each failure has a recorded decision);
STEP files and drawings exist; and `QUOTE-LIST.md` names a supplier class for
each part:

- Si3N4 substrate laser-cut and lapped: Toshiba, Kyocera, Rogers-curamik
  distributors;
- PI or PEEK machined;
- PTFE or FFKM lip;
- spring.

---

## B. PCB agent: electronics for C1

**Conclusion of sensor-r3:** C1 needs **no new circuit type.** It uses the
existing 4-wire Pt100 front end (MAX31865 class) and the rim-NTC channel. Do
**not** lay out any heater or pulse driver.

**Your job:** make the existing channels meet C1's numbers, close the open
items below, and write a change request for the controller board.

**Read first:**
- `output/temper-manufacturing-r43/design/r31/CONTROLLER-ARCHITECTURE.md`
  (row 14 RTD; row 50–51 RTD fault and the open runaway decision; row 74, ADC1
  is exhausted) and `CONTROLLER-SPEC.md`.
- The R43 HANDOFF (`design/r43/HANDOFF.md`): the controller is captured in a
  separate session ("zapote/controller"). **Treat it as read-only.**
- The legacy RTD module `elec/src/modules.ato` `RTDSensing` (read-only):
  MAX31865, 430 Ω 0.1 % Rref, REF2025, `RTD_*` net names.

**Output:** `output/temper-sensor-r3/pcb/`, containing:
- `REQUIREMENTS.md`
- `checks.py` → `checks.json`
- `CHANGE-REQUEST.md`, with an ato snippet for the controller owner. Do not
  edit their sources.
- `DECISIONS.md`

**Requirements to meet and prove in `checks.py`:**

1. **Range and resolution.**
   - Pt100 range −20 to 320 °C (Rref ratio headroom at 320 °C).
   - Resolution ≤ 0.05 K.
   - Front-end error ≤ ±0.3 K at 40–250 °C after a single-point
     calibration, at worst-case Rref tolerance and tempco and REF drift over
     the board's temperature range.
   - Use datasheet worst-case values.
2. **Sample rate.** ≥ 16 Hz continuous (auto-conversion, 60 Hz notch for US).
   DRDY goes to the MCU as today (`rtd_service.c`).
3. **Self-heating.** Compute the bias current and the element power at the
   worst-case RTD. With C1's G_bond (0.061 W/K) and the lowest G_c
   (888 W/m²K × 45.4 mm²), the self-heating offset must be ≤ 0.1 K, or
   firmware must calibrate it as a constant. Keep the bias on continuously:
   no switching transients.
4. **Coil pickup.**
   - The cartridge sits in the coil eye at 20–100 kHz (native-21 runs
     ~40 kHz).
   - Specify differential and common-mode RC filtering at the MAX31865 inputs
     per the datasheet application circuit: values, tolerance, and the
     settling-time effect on the conversion.
   - Twisted pairs (F+/S+, F−/S−, NTC pair) in the cable, with the shield or
     drain at the controller SELV ground only.
   - Show that the filter attenuates a 1 V common-mode 40 kHz pickup to below
     1 LSB.
5. **Rim NTC (Semitec 104GT-2).**
   - It needs an ADC channel, and ADC1 is full.
   - Choose: an external I²C ADC (ADS1115 class) on REF2025, or another
     justified option.
   - Bias network sized for ≤ 0.3 K resolution at 100–250 °C.
   - Open/short detection.
6. **Connector and protection.**
   - The cartridge is user-replaceable, so its connector is user-touchable
     during service.
   - Low-capacitance TVS plus series R on all 6 lines. IEC 61000-4-2 level
     is the design target; UL 858 governs.
   - Show the protection doesn't spoil items 1 and 4.
7. **Insulation.** The cartridge and cable are SELV.
   - Get the coil/tank working voltage and frequency from the native-21 docs
     (`docs/hardware/power-section-120v/POWER-SECTION.md`, the R43 HANDOFF
     coil-NTC note citing IEC 60664-4 for f > 30 kHz).
   - Compute the reinforced clearance and creepage between coil (winding,
     leads) and cartridge conductors, including the derating above 30 kHz.
   - Hand the numbers to the CAD agent's G11 through your DECISIONS.md.
8. **Hardware runaway trip** (open in R31 row 51). If it is a comparator on
   the RTD channel, it is the **only** hardware trip fed by an under-cap
   sensor. A second hardware trip may use the rim NTC, which is not under the
   cap (Breville US10278238B2 rule). Specify thresholds and hysteresis
   against the max setpoint of 250 °C.
9. **Cable.**
   - Reconcile R31's "SAB TD 801 F 4 × AWG28" with R36's six conductors.
   - Pick a 6-core high-temperature cable (PTFE/FEP, ≥ 200 °C) with its
     rating source.
   - Specify the first-20 mm low-k Pt leads in the cartridge (CAD owns the
     geometry).

**Done when** `checks.py` passes all nine items with datasheet citations, and
the CHANGE-REQUEST lists:
- exact part numbers;
- net names (keep the `RTD_*` style);
- pinout of the 6-pin cartridge connector.

---

## C. Firmware + in-the-box testing agent: estimator, contact check, faults

**Goal.** Port sensor-r3's C1 algorithms into the ESP-IDF firmware as host-tested
C. Then rerun the screen with that **C code in the loop** against the Python
truth plant, and pass the same bars.

**Read first:**
- `output/temper-sensor-r3/screen.py`: `run()` is the reference behaviour;
  D1 is the `detector` block plus `probe_says_contact` and `free_decay_rms`.
- `output/temper-sensor-r2/estimator_study.py`: `KFNoPower` is the fixed
  contact model; the controller constants are there too.
- Both DECISIONS files.
- Firmware:
  - `firmware/components/sensors/` (`max31865.c`, `rtd_service.c`)
  - `firmware/components/control/` (`cascade_pid`, `pid_control`,
    `thermal_mass`, `pan_detect`, `profiles`)
  - `firmware/transition_table.yaml` and `firmware/test/gen_transition_table.py`
  - `firmware/test/CMakeLists.txt` (host tests)

**Do not touch:** `firmware/components/owned_controls/`.

**Implement** in new files under `firmware/components/control/`, with headers
in the component's include convention:

1. **`pan_temp_estimator.{c,h}`.**
   - A 4-state Kalman filter [T_pan, v, T_cap, T_el], dt 0.1 s, 5 Euler
     substeps.
   - Cartridge constants:
     - C_cap 40.4 mJ/K
     - C_el 8.175 mJ/K
     - G_bond 0.0612 W/K
     - G_leak 0.8 mW/K
     - contact area 45.4 mm²
     - h_nom 1300 W/m²K
   - Sink = rim-NTC reading.
   - Q = diag(0.02, 0.05, 1e-4, 1e-4)·dt; R = σ², with σ default 0.2 K.
   - Single-precision float (ESP32-S3 FPU). Prove the float version matches
     the Python double reference within 0.05 K on all screen vectors.
   - All constants live in one struct, so the bench can recalibrate C_cap,
     G_leak and h_nom.
2. **Plant-gain identification and scheduling.**
   - Extend `thermal_mass.c`, or add `plant_gain.{c,h}`, to estimate
     a = η/C_total online. Suggested method: regress T̂ rise on delivered
     input energy during the first heat-up, then update with a forgetting
     factor during ramps.
   - Feed it to a rate-domain PID:
     - KP 0.1/s, KI 0.002/s², KD 1.0
     - integrate only within 10 K
     - 1 K/s setpoint ramp
     - P = rate/a, clamped 0…1800 W
   - The screen gave the controller the true a; you must show the identified
     a is within ±30 % by the end of the first ramp on all 4 pans, and that
     B2/B3 still pass with it.
3. **`contact_check.{c,h}`.** D1 exactly as `screen.py` (constants in one
   struct):
   - Trigger: slope over 2 s < −0.8 K/s, held 1 s, mean P ≥ 40 %.
   - Probe: off 5 s, on 50 % for 8 s, off 5 s.
   - Regression on [1, t, t², E_lag(3 s)]; lost if the coefficient is < 25 %
     of a, **and** the free decay toward the rim NTC (τ_off = C_cap/G_leak,
     ±40 %, asymptote within 25 K) fits within 0.5 K rms.
   - On lost: P = 0, raise a state-machine event and a UI message ("pan must
     touch the sensor"), and retry every 20 s.
   - After a passing probe: 30 s hold-off.
   - Bounded memory: fixed 18 s ring buffers, no heap.
   - **Stretch, B5 timing:** a shorter probe that still never latches on the
     food-drop case. Document it in DECISIONS.
4. **Faults and plausibility**, mapped into `state_machine` via
   `transition_table.yaml` and regenerated with `gen_transition_table.py`:
   - MAX31865 fault register: open, short, RTDIN± over/under, REFIN.
   - Range: −20 to 320 °C.
   - Rate: |dT/dt| > 30 K/s is a sensor fault, not pan physics.
   - Pt100 vs rim-NTC cross-check: while heating, the Pt100 below rim − 15 K
     for 30 s means a suspect sensor, which triggers D1.
   - Stale DRDY.
   - **Never chase a cold reading:** while D1 is in probe or lost state, or
     in any RTD fault, power stays under the probe/zero rule, whatever the
     PID asks.

**In-the-box tests.**

- **Host unit tests** in `firmware/test/`, registered in `CMakeLists.txt`
  like the existing `test_*_only` targets:
  - **`test_pan_temp_estimator.c`:** golden vectors exported by a new script
    `output/temper-sensor-r3/firmware-sim/export_vectors.py` from the
    Python reference (step, ramp, h_c extremes, noise).
  - **`test_contact_check.c`:** loss on 4 pans, food drop on 3 pans, nominal
    runs with no trigger. These come from the same exporter.
  - **Updates** to the existing `test_*` for any state-machine change.
- **C-in-the-loop co-simulation** in
  `output/temper-sensor-r3/firmware-sim/`:
  1. Build the estimator, plant-gain, PID and contact_check C files as a
     host shared library: CMake or cc, not ESP-IDF.
  2. Drive them through ctypes from a copy of `screen.py`'s `run()`, with the
     Python truth plant unchanged.
  3. Rerun:
     - every C1 design case;
     - the 12 stress cases;
     - loss, food and nominal-detector runs;
     - plus a hot pan placed on the hob, and h_c steps (1000→300 and
       300→3000).
  4. Write `cosim-results.json` and a short README.
- **Acceptance** (the DECISIONS.md §1 bars, with C code in the loop):
  - B1 ≥ 15/16 design cases (match or beat the Python 15/16);
  - B2 16/16; B3 16/16;
  - B5: suspect ≤ 3 s, T_c ≤ SP + 15 K, confirm ≤ 21 s (≤ 15 s if the
    stretch lands);
  - zero false latches in nominal and food runs;
  - identified a within ±30 %;
  - C-vs-Python estimate difference ≤ 0.05 K rms.
- **Runner.** The existing `firmware/test/run_owned_controls.sh` belongs to
  another owner. Add your own `firmware-sim/run.sh` that runs the host tests
  and the co-sim and exits non-zero on any bar failure.

**Done when** `run.sh` exits 0, the results JSON is written, and DECISIONS
records any parameter you changed and why.

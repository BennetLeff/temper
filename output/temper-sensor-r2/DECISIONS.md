# temper-sensor-r2 decisions

## 0. Numbering (2026-10-14)

`output/temper-sensor-rN` is the sensing line. It is separate from the
enclosure line (`output/temper-manufacturing-rNN`), so sensing studies don't
take enclosure round numbers. R44 is reserved for Codex controls.

- **sensor-r1** is `output/temper-center-sensor-study/` (2 Oct 2026). It is
  the concept that picked a direct-contact, sprung Pt100 cartridge through
  the glass. It was not renamed.
- **The cartridge hardware** still lives in the enclosure rounds' evidence
  folders (`evidence/sensor-r15/`, `evidence/sensor-r16/`, carried into R43).
  Those folder names mean "manufacturing round 15/16". In prose, always write
  this line's full folder name (`temper-sensor-r2`) so the two don't get mixed
  up.
- **sensor-r2 (this folder)** asks a firmware-only question about the R16
  cartridge as built: can a model-based estimator that uses the commanded coil
  power remove most of the passive sensor's lag and contact-dependent error?
  This is "route 1" (coil-as-stimulus). It adds no heater and no position
  sensing to the cartridge, so it stays clear of the self-heated sensor in
  Impulse's US20240288175A1, which is allowed but not yet issued
  (`docs/evidence/2026-10-14-impulse-labs-teardown.md` §8).

## 1. What is held fixed

- **Cartridge:** R16 as built (identical to the R15 alumina design in
  `thermal_screen.py`).
  - 96 % alumina cap, Ø10, 0.6 mm roof and skirt
  - IST P0K1.202 Pt100 chip on a 0.2 mm bond
  - silicone boot, 1.11 mW/K leak
  - contact Ø9
- **Rim NTC:** the cartridge's backup rim NTC (R36, 6-conductor cable) gives
  the estimator a sink reading. The estimator is given that reading with an
  error, not the true sink temperature.
- **Power:** 1.8 kW input ceiling. The estimator sees measured input power
  (CT + AMC1311 bus sense in native-21) and does not know the coil-to-pan
  efficiency.
- **Coil:** heated annulus at r = 20–114 mm (coil eye ≥ Ø40 per
  TANK_COIL_SPECIFICATION row 14; OD 228).

## 2. What is being estimated

The **primary target is the pan base temperature at the contact point**
(T_c). It is the quantity the passive sensor converges to at steady state, and
a bench can measure it with a thermocouple welded beside the contact.

The **secondary quantity, reported but not gated, is the area-mean base
temperature over the heated annulus** (T_mean). It is closer to what food
sees. The coil eye is unheated, so the centre lags the annulus during a ramp.
That lag is a property of the pan, not of the sensor, and an active sensor at
the centre (Impulse's) has it too.

## 3. Acceptance bar (set before any result)

The bar applies to every scenario in §4, with Pt100 noise of 0.2 K rms and
h_c anywhere from 300 to 3000 W/m²K:

- **A1 (estimate):** |T̂ − T_c| ≤ 3 K from 10 s after start onward. This
  covers ramps, holds, and a mid-run contact change.
- **A2 (control):** with a PI loop closed on the estimate, the true T_c
  overshoots its setpoint by ≤ 5 K.

The baseline is the raw Pt100 reading in the same closed loop. If the
estimator fails A1 or A2, the next step is the active routes (2/3 in the
teardown note) and not a looser bar.

## 4. Truth model vs estimator model

The truth model is deliberately richer than the estimator model, so that
model mismatch is part of the test:

- **Truth:**
  - radial finite-difference pan base
  - wall mass on the rim ring
  - convective and radiative loss
  - optional water load that boils at 100 °C
  - cap, element and sink nodes from the R15 screen
  - sink temperature that rises during the run
- **Estimator:** one lumped pan node driven by a·P, plus the cap and element
  nodes. a = η/C_pan and G_c are unknown and are estimated online.

## 5. Controller frozen before any estimator was compared (2026-10-14)

**What happened.** The first exploratory run used a fixed PI. Even with
feedback on the true T_c, it overshot 7.9 K on clad and 32–40 K on carbon
steel (fixed-gain code not kept; figures not reproducible). Heat stored in
the annulus keeps flowing into the centre after the
centre reaches setpoint. That is pan physics plus controller, not sensing, so
A2 could not isolate the sensor.

**Decision.** Use a rate-domain PID, gain-scheduled by the pan's lumped
η/C_total, with a 1 K/s setpoint ramp. Gains were swept on perfect feedback
only (`controller_sweep.py`):

- KP 0.1/s, KI 0.002/s², KD 1.0, integrate within 10 K
- perfect-feedback worst overshoot 2.06 K, hold ≤ 1 K, reach ≤ 256 s

Every feedback variant gets the true η/C, so A2 compares sensing only. The
change came from the perfect-feedback result. The bar itself is unchanged.

## 6. Result: route 1 as specified fails (2026-10-14)

**Finding.** Online identification of h_c from coil power plus the Pt100
reading is not observable. The pan's centre lag and the contact lag are series
lags, and series lags commute (exact check in `results.json`). The route-1 EKF
passes A1 in 0 of 28 cases.

**Decision.** Do not pursue an adaptive coil-as-stimulus estimator for h_c.
Keep coil power for identifying η/C, which the controller needs (§5).

## 7. What passive sensing must achieve to pass

**Decision.** Firmware uses a fixed contact model: the KF with a nominal h_c.
That passes the bar only if every pan in use gives **h_c ≳ 2000 W/m²K (τ63
≲ 3 s with the R16 alumina cap)**, with the nominal set near 3000. For
h_c ≤ 500, nothing passive passes, even with h_c known exactly. The table is
in README.md.

## 8. Next (in order)

1. **Bench:** extend the R16 sensor tests to a cookware survey that measures
   τ63 per pan, dry, at the design spring force. This decides between §7 and
   item 3.
2. **Cartridge levers to screen:**
   - lower C_cap (roof thickness, cap size);
   - contact force and self-alignment, to raise and narrow h_c.

   Rerun `estimator_study.py` with the new C_cap.
3. **If the survey falls below the §7 line,** the fix is an in-situ contact
   measurement by heat injection, for example pulsed Pt100 self-heating. Read
   the allowed claims of US20240288175A1 before designing it.

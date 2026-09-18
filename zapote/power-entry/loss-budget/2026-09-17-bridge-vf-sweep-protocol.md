# GBJ2510-F forward-drop sweep — protocol (proposal)

Date: 2026-09-17
Status: **PROPOSAL — NOT AUTHORIZED.** The PFC experiment campaign authorizes no
powered bench operation. Nothing here may be executed until a qualified engineer,
under the site's electrical safety process, approves it. This supersedes nothing;
it derives its shape from the lower-risk companion measurement already scoped in
`zapote/power-entry/loss-budget/campaign/PHYSICAL-TEST-PLAN.md`.

Plan context: `docs/plans/2026-09-17-001-feat-pfc-bridge-loss-pinning-plan.md`.

## 1. Why

The bridge's ~28.30 W conduction term currently comes from one datasheet test
point (1.05 V max at 12.5 A, 25 °C) applied as a constant across a 60 Hz
waveform whose current spans zero to tens of amps. The retained datasheet also
carries a per-element typical forward-characteristics curve at 25 °C on a raster
plot, but a raster trace could not be made reliable (three tracer variants gave
0.833 V, 0.961 V and 1.100 V at 12.5 A; the third exceeds the datasheet's own
1.05 V maximum). A direct measurement anchors the curve instead.

Unlike the switching double-pulse test, this is a DC measurement: no fast
probes, no deskew, no wide-bandgap current transducer.

## 2. What the result decides

It replaces the temperature and part-spread uncertainty in the bridge term. The
comparison the result feeds is the ~1.5 W margin between the bridge term
(28.30 W) and the switching term (26.76 W), so a measurement uncertain by more
than a few tenths of a volt does not help.

## 3. Measurement

- **Device:** the exact retained `GBJ2510-F` bridge, or a single element of it.
- **Quantity:** forward voltage as a function of forward current, per element.
- **Current range:** from below the waveform's low-current decade up to the
  waveform peak. Cover at least 0.01 A, 0.1 A, 0.5 A, 1 A, 2 A, 5 A, 10 A,
  12.5 A, 15 A, 20 A, 25 A, 30 A. The low decade is where a log-axis reading and
  a constant-drop model diverge most, so it is the informative end.
- **Temperatures:** a cold case point near 25 °C and a hot case point
  representative of the installed condition. The GBJ thermal study reports
  whole-joint peaks up to 84 °C nominal and 118 °C weak-assembly, with a
  per-element 1.0 °C/W junction-to-case datum; pick the hot point from that
  study rather than inventing one.
- **Duty:** DC or a low-frequency pulse long enough to settle but short enough
  to limit self-heating. State the pulse width and duty. The datasheet's own
  reference point is a 300 µs pulse; a DC point at low current is acceptable and
  should be recorded as a different condition, not mixed with the pulsed points.
- **How temperature is established:** placed on the intended assembly or a
  controlled stage; record how the case temperature is set and verified, and
  record it, not ambient.
- **Case is not junction.** The datasheet's forward-voltage condition is junction
  temperature; the fixture controls and reports case temperature. Record the case
  temperature and state explicitly that the junction temperature is inferred, not
  measured.
- **One specimen.** This characterizes the bridge it is performed on. It does not
  bound part-to-part spread, which remains a separate uncertainty term rather than
  something a single measured curve can discharge.

## 4. What to record per point

Current, forward voltage, case temperature, duty/pulse width, instrument
identity and range, and the measurement's resolution at that current. Record a
repeat at one point per temperature to show repeatability.

## 5. Acceptance

- **Point check, not a curve bound.** At 12.5 A and a 25 °C junction, the measured
  forward voltage must not exceed the datasheet's 1.05 V maximum. That maximum is
  stated at one current and one junction temperature. It is not a curve-wide
  ceiling: above 12.5 A a correct measurement legitimately exceeds it, so a
  curve-wide inequality would reject valid points.
- The point set must span the waveform's full current range, or the integration
  will clamp over a range it should measure.
- Report the reading resolution so the uncertainty budget can carry it as a
  number.

## 6. Safety

Bench DC work at the currents involved still heats the device and the fixture.
Isolate and discharge before changing connections; use rated instrumentation and
termination; do not exceed the device's rated forward current. This document is
not a safety assessment — the authorizing engineer owns the hazard analysis.

## 7. What to retain

Raw instrument captures, fixture schematic, per-point readings with temperature
and duty, the repeatability check, and SHA-256 of every file. The receipt must
separate measured from modelled quantities.

## 8. Authorization

```text
authorizing engineer:
approval reference:
approved apparatus / facility:
hazard analysis reference:
approved current range and temperature points:
date:
```

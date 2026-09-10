# Behavioral model review criteria

Recorded by the host before accepting the new model or its simulation results.
The source is TI SLUSEF4A, revision November 2022. This is a model-development
review, not approval of unresolved Temper product requirements.

## Independent checks

- Bind the six subcircuit terminals explicitly to TI pins: GND 1, SW 2, VIN 3,
  FB 4, EN 5, CB 6. The Temper bench ties EN to VIN and places 100 nF from CB
  to SW; it must not short CB to SW with an ideal voltage source.
- Calculate the set point outside the model: 0.6 × (1 + 100/22.1) =
  3.314932 V. Independent resistor/reference corners are approximately
  3.2123–3.4203 V. Inspect measured steady-state response; never force the
  output node directly to its target or replace feedback with a prescribed
  waveform.
- At an explicit continuous-conduction operating point, measure switching
  edges against the declared 500 kHz oscillator. The datasheet permits
  450–560 kHz over its stated conditions; fixed nominal model parameters
  should produce nominal frequency. A light-load frequency below 500 kHz
  is expected for PFM and must not be mistaken for oscillator failure.
- Compare startup behavior with the 3.2/4.0/5.4 ms internal soft-start range.
  Distinguish reference-ramp duration from output 10–90% rise and settling;
  those are different measurements. Repeated enable/restart behavior must
  be tested if claimed supported.
- Check decreasing switching activity at light load, zero-current behavior,
  and the 0.48 A typical minimum peak current mechanism. A voltage-mode
  constant-frequency PWM model is not a faithful PFM/peak-current model.
- Inspect the actual switch and inductor-current waveforms, not only VOUT.
  Check steady-state inductor volt-second balance and finite input current.
  Supplied input energy must account for output energy and stored-energy
  changes. Physical losses omitted from the model must be listed.
- Run startup, input steps across 13.5–16.5 V, and a clearly exploratory
  0.05–0.5 A load step. Retain unsuccessful runs. These loads come from a
  source-backed 0.5 A design budget plus an assumed light-load probe;
  their slew, ripple and recovery limits are not approved product limits.
- Use a distinct datasheet-example bench to compare with published
  application waveforms. Identify any compensation parameters fitted to
  those curves; a fitted curve is calibration, not independent validation.
  Report differences and the limits of extracting numbers from plots.

## Claims that require more evidence

Internal compensation, PFM hysteresis, propagation delays, loss-versus-frequency
and temperature, bootstrap drive details, current-limit/hiccup timing, thermal
shutdown, and parasitic coupling may be incompletely specified. Omitted or
assumed behavior is unsupported, even if nominal regulation looks correct.
The model is datasheet-derived behavioral code, not a TI-supplied transistor
model. Passing these checks establishes a useful exploratory model; it does
not by itself authorize a trusted engineering qualification receipt.

Measured data must state model/deck/datasheet hashes, simulator version,
conditions, sample resolution, and whether values are assumptions, analytical
checks, model results, or published device observations. Board thermal and EMI
behavior remain outside schematic simulation.

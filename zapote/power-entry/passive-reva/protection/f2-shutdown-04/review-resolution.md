# Integration and review resolutions

Luna workers implemented separate circuit, fault-fixture and plant work units.
Independent Luna reviews checked the source and final test/model behavior; the
host compiled the circuit, checked physical pins, ran the independent vendor
and DC fixtures, and resolved integration failures. Worker handoffs alone were
not treated as passing evidence.

## Circuit and default-off interface

- Corrected SN74LVC1G17DBVR physical pins to1NC/2A/3GND/4Y/5VCC.
- Added a qualified enable AND so RUN and current clear_ok both authorize the
  disable transistor. ARM/PERMIT use powered-off tolerant input buffers.
- Moved the2.5V reference to logic5 and added the independent fast auxiliary
  comparator to asynchronous clear. Slow supervisor response alone cannot
  capture the tested1µs auxiliary interruption.
- Replaced the10kΩ IN− pullup with1kΩ after the unchanged TI driver model
  exposed a3.726V startup gate pulse. The final fast-ramp case peaks18.47mV.
  The1kΩ resistor is1210/.5W for0.324W at18V.
- Reduced the divider filter from100pF to47pF after the near-threshold mismatch
  test exceeded2µs in the filter alone. The old controller/trace is retained.
- Corrected reference-bias and logic-bleeder BOM/package fields; source-07 is
  the accepted export. All15 compiled circuit/regression checks pass.
- Partial-power logic behavior remains a model assumption. Ioff at zero
  supply was not promoted into a guaranteed analog brownout specification.

## Fault and supply test validity

- Replaced startup mismatch stimuli with independently driven VD/VB faults
  after verified gate activity. All four channels must assert individually.
- Corrected absent-supply cases to remain at0V; a delayed ramp is not absence.
- Made supervisor release retriggerable after dropout and required a positive
  fresh-edge rearm after valid rails return. Added startup with ARM/PWM held
  high and a1µs auxiliary-loss case.
- The extractor requires the complete expected case set and rejects malformed,
  missing, nonfinite, truncated or coarsely gapped traces. It checks the actual
  ARM threshold crossing and continuous retained shutdown up to that edge.
- Removed the dead LATE_FAULT parameter. The negative control is accurately
  named slow_detector_negative and changes the response time that is actually
  consumed. The bypass and slow cases fail ordinary assertions; their names
  do not manufacture failure.

## Power model and measurement

- Corrected a disconnected/shorted MOS channel hookup and placed a zero-volt
  probe in the source path. Inductor current is retained separately.
- Suppressed the level-1 MOS intrinsic body diode and retained one explicit
  body diode with its own current probe. The DC oracle checks suppression.
- Split the output-capacitance surrogate into344pF Cds and112pF Cgd, avoiding
  the previous parallel double count. ST456pF Coss(eq) is charging-time based;
  the constant-capacitance approximation is not an exact Eoss model.
- Removed SiC minority-carrier TT from the boost diodes, represented both
  parallel legs, and retained finite MOS channel conduction. DC I/V is checked
  in ngspice against source anchors, independently of the transient extractor.
- Separated controlled positive channel-current cessation from later passive
  reverse-current settling. The earlier apparent25µs shutdown was a measurement
  error. The raw reverse pulse and terminal-settling evidence are retained.
- Required the actual current at F2 opening and actual gate state near shutdown;
  initial-condition labels alone do not establish the exercised fault current.
- Fixed the consumed slow-driver parameter and retained a negative control.
- Scoped energy balance to the post-opening high-voltage/gate boundary, with
  source work, gate-boundary work, explicit stored energy and device terminal
  energy. The disconnected bulk bank is not counted as local absorption
  headroom. Full-interval numbers and omitted effects are diagnostic only.

See the retained review reports for the findings as originally raised. Final
summaries and the receipt identify the accepted runs; earlier failed attempts
remain diagnostic evidence and are not included as passing cases.

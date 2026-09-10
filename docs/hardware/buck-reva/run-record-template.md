# Buck Rev A — bench run record (template; fill per session)

## Identity

- Date / operator:
- Board revision + release manifest/hash (from `pcb/prototypes/buck-reva/verification/board-freeze.md`):
- Assembly identifier (new ID after any rework):
- Requirements revision: `temper-buck-requirements-2026-09-10-startup-compliance`
- This runbook revision (git SHA):

## Assembly inspection (pre-power)

- Populated MPNs vs assembly drawing:
- U3 orientation / solder bridges / L2 seating / connector polarity / TP1–TP4 silk:
- GND continuity and I/O-to-GND resistance (note time-varying capacitive behavior):
- Temperature sensor placement, emissivity, uncertainty; protective stop set (°C):

## Instrument settings

- Supply model / isolation / limits used (0.10/0.30/0.50 A stages + actual behavior):
- Load model / mode / programmed slew and plateau verification method:
- Scope model / probes / attenuation / bandwidth / sample rate / memory:
- DMMs, thermocouple/meter models, calibration and uncertainty notes:
- Wiring photo filename(s); raw-file hashes:

## Event log

| Time | Step / test ID | Observation / setting | Outcome |
|---|---|---|---|
| | | | |

## Failures and stop events

- (Record any stop-condition trip, current-limit event, rework, and affected test IDs.
  Rework creates a new assembly identity; list repeated tests.)

## Per-point results

- Attach filled `results-template.csv` (statuses PASS / FAIL / NOT RUN / INDETERMINATE;
  measured cells empty where not measured; instrument limits and near-uncertainty
  results visible).

## Conclusion (after real testing only)

- Demonstrated operating points:
- Failures and rework:
- Remaining tests (NOT RUN / INDETERMINATE with cause):
- Next-subsystem interface note: the 3.3 V/0.5 A budget may be cited as provisional
  immediately; it becomes demonstrated only for measured conditions. 1 A pulse headroom
  stays provisional until it passes. Do not release a sensitive downstream load onto a
  rail that failed the relevant test.

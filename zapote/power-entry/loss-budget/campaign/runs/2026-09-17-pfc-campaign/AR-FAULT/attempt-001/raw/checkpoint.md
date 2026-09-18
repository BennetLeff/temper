# AR-FAULT attempt-001 — Step 1 checkpoint

- Task question: what is the real device stress on a boost-switch-short fault,
  and does the AR-VERIFY ~586.7 V figure hold? Plus the boost-diode-short path,
  the V/I/E exposure from the actual bus capacitance, and how/whether the fault
  is interrupted.
- Changed design variable: **none**. Source-only assessment of the existing
  routed candidate; no board/source/model edit, no solver invocation.
- Frozen controls: board `zapote/power-entry/shunt-repair/candidate/`
  (schematic 49db3ee4, PCB 34e6fba9, manifest 136c94c3); contract
  `contract-C1.1.json` 0accd9bc; envelope bus 400 V, line 108/120/132 Vrms,
  15 A rms, claimed 586.7 V.
- Source/identity: HEAD `95d1d528` == dispatch `source_revision`. Output dir
  was unused except the delivered `dispatch.json`.
- Known delivered unknowns at start: the AC source/line impedance; the F1
  pre-arcing I²t; the state of the NTC bypass at the fault instant; the
  controller's post-fault switching behaviour; the C3D20065D surge ratings.

## Which outputs remain unknown at checkpoint time

- Peak switch-short fault current as a single number (needs line impedance).
- Fault duration / fuse clearing time (needs F1 I²t curve).
- Bus-cap discharge extent on a diode short (needs the controller response).
- No bench measurement; hardware qualification NOT_PERFORMED.

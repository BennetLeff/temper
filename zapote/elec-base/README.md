# Shared electrical base

- `src/` holds the atopile sources the units build from: the shared modules
  (`main.ato`, `modules.ato`, `components.ato`, ...) and each unit's entry
  (`rtd_unit.ato`, `current_sense_unit.ato`, `gate_drive_unit.ato`,
  `interlock_unit.ato`, `thermal_sense_unit.ato`; `voltage_sense_unit.ato` is
  archived but kept so builds see the tree they were made from). The unit
  tools (`<unit>/tools/build_source.py`, `rtd/unit/build_source.py`) copy this
  tree into a fresh workspace and build with atopile 0.2.69.
- `libs/` holds the footprint libraries, frozen from the old `pcb/libs`.

On 2026-10-10 `src/` was promoted from the units' latest source-build
snapshots (`current-sense/source-build-04`, `gate-drive/source-build-09`,
`interlock/source-build-02`, `thermal-sense/source-build-02`). Those snapshots
agree on every file they share. Before that, the unit sources existed only
inside the snapshots, and every unit build tool failed: the repo-root
`elec/src` they read had been removed. Rebuilding each unit from this tree
reproduces its snapshot's netlist and BOM exactly, once absolute build paths
are normalised, and rtd reproduces the 36 MPNs in its source manifest. The
snapshots stay as build outputs.

# Atopile 0.2.69 netlist library metadata limitation

Parent inspection of the installed compiler establishes the cause: in
`atopile/netlist.py:150–160`, `NetlistBuilder.build` groups all components by
footprint, calls `make_libpart(group_components[0])`, then passes that same
library record to every component in the group. `make_libpart` obtains the
representative component's MPN and pin descriptions. Individual component
footprints and net endpoints are emitted separately.

Consequently, `build/default.net` labels `isense_clamp` with the SOT-23
representative's LM4040 MPN, and the boost diode with the TO-247 representative's
MOSFET MPN. These are not the resolved source parts. The native per-instance
adapter record selects BAV23C-E3-08 and C3D20065D, respectively. The underlying
compiled source has not been changed to make a check pass.

The graph checker initially assumed `libsource.part` was a per-instance MPN
and rejected this export. That checker version is retained. The corrected
checker verifies selected endpoint connectivity only. Parent verification
separately binds the per-instance component attributes, source hashes and
netlist hash in `parent-review.json`.

This is an unresolved exporter limitation, not a passed part-selection test.
Do not use this netlist's library MPN/pin descriptions as manufacturing or
schematic-library authority. A future manufacturing export must preserve and
cross-check each instance's identity and pin map. Fixing the pinned compiler
or replacing that export path is outside this source-integration experiment.

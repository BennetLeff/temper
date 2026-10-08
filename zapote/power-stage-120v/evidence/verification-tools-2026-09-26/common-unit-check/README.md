# Shared-unit check, 2026-09-26

The required `make -C zapote check-units` ran against the five unchanged
maintained units after the shared route-receipt adapter changed. It exited 2
with **indeterminate** for all five units; this is not a passing suite.
The native/common checks have no failing status. Existing gaps include
unsupported open F.Fab body geometry, undeclared fabrication/assembly limits,
missing operating/timing contracts and device/hardware qualification. The
gate-drive power model also retains software coverage gaps; those are not
reclassified as physical qualification.

`status-summary.json` lists every section status and coverage gap. Full unit
reports are retained here; per-command outputs remain at the historical
local run path recorded in `summary.json`. This runner does not contain the
power-stage unit; its separate final-board gates are under
`native-06/verification/`. No shared unit was modified to clear these gaps.

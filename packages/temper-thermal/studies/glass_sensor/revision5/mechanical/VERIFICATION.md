# R5 mechanical verification

Final generation uses CadQuery2.6.1 in the prepared `temper-center-sensor-env` interpreter. R2 source SHA256 is checked before import. R5 source is dimensional geometry; no force or thermal solver is implemented in Python.

- D8 and D6 × rest, coupled-loaded, local-stop, full-stroke, upper-island-capture and cap-capture:12 nominal poses.
- Every modeled shape valid; all12 assemblies export and reimport STEP successfully.
- Zero rigid-part volume intersections above1e-5mm³ in every pose. Film/bond/cap contacts at shared surfaces are intentional.
- Zero full-wire versus rigid-part and wire-versus-wire intersections above1e-6mm³ in every pose.
- All48 pose/wire developed centerlines60mm within1e-7mm. Explicit minimum static circular radius0.5mm and dynamic service-loop radius2mm; these are proposed geometry, not supplier fatigue/forming limits.
- Every outer-wire solid volume agrees within1e-5mm³ with the exact composite outside volume π(0.116²×59.5+0.04²×0.5). Copper core volume and jacket volume are separate metadata. This checks the spline self-overlap failure encountered during design was removed.
- Each of four Cu/Ni bead process envelopes intersects its copper end and intended terminal with finite volume and has zero overlap with the opposite terminal. Results in `weld_connectivity.json`; no metallurgical or electrical performance is established.
- Both SVG section files parse as XML; Ruff checks pass.14STEP artifacts cover12poses and2standalone caps.

Main/local elastomer envelopes, optical witness rods and flags are excluded from the rigid interference census. Wire clearance to actual witness optics, final gland/vent/feedthrough hardware and final connector is not a certified assembly check; those items remain dry fixture or process interfaces. Moving flexure geometry is inherited and does not establish assembled force. R5 adds no firmware enablement.

All physical build, dimensional inspection, hot force, fatigue, weld quality, electrical insulation, spill leakage, induction and calibration outcomes remain NOT_RUN. All output paths and included geometry must be kept with the thermal scalar hash when another workstream imports this package.

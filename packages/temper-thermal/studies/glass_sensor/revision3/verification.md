# R3 verification — 2026-10-04

**Simulation and test preparation only; physical validation NOT_RUN.** Base commit `badce74c44a598da4096dffe2e1f7fe4f779bc5d`. Outputs were integrated in the isolated `codex/glass-sensor-simulation` worktree. Primary checkout and all previous evidence are unchanged.

| Check | Result |
|---|---|
| Rust model |28 tests pass:14 inherited kernel tests and14 R3 checks |
| Input identity |Runner checks full SHA-256 of inherited kernel, R2 CAD generator, mechanical-force CSV and R3 CAD scalar CSV |
| CAD |6 poses,34 valid parts each; no checked rigid intersections; exported STEP reimports valid |
| Replay |8 CSV outputs /765 rows identical between scratch execution and integrated execution |
| Static checks |rustfmt, rustc `-D warnings`, direct clippy-driver `-D warnings`, Ruff and whitespace checks pass |
| Historical preservation |146 PR1-manifest files and77 R2-manifest files retain full hashes |
| Artifact checks |CSV field counts, SVG XML and local report link existence verified |

See [thermal log](logs/thermal.log), [CAD log](logs/cad.log) and [artifact checks](logs/artifact-checks.txt). Source identities are in `source-provenance.json` and `thermal/inputs.sha256`.

The tests cover analytical network limits, not merely snapshots: prior R2 DC recovered when the new hook gap is disabled and hook temperature equalized; explicit hook path equals its DC series-resistor reduction; gas quadrature agrees with an exact flat film and refines; copper fin agrees with its prior record and no-ambient series-conduction limit; heat capacities/time integration refine; hot-anchor boundary checks and thermoelectric current-reversal algebra hold. The pinned kernel's existing radial-loop Clippy allowance remains scoped to that inherited module.

CadQuery2.6.1, rustc1.92.0 and Matplotlib3.10.8 were used. Python generates CAD and presentation; Rust owns physical arithmetic. The report chart was directly inspected as an image. Full HTML browser rendering was not performed because the existing local-file browser preview policy disallowed that route; no workaround was used.

Only R3 study files changed. Firmware/PCB and import boundaries are untouched. No ESP-IDF, hardware, energized induction, seal leakage, endurance or electrical-accuracy qualification is implied. The prior all-target host-build limitation remains documented in R2/PR1 evidence and was not re-tested for this study-only change.

Rigid checks omit previously labeled flexible/envelope routes. The four new short wire volumes define the anchor coupon only; full formed routing, weld regions, process/contact quality, jacket creep and cap retention strength remain unverified. A temperature source is prescribed; neither real induction heating nor closed-loop overshoot is solved.

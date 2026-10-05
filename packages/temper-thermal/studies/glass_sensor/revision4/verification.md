# R4 verification — 2026-10-04

Scope: numerical model, analysis and test preparation. No hardware measurement, CAD modification, seal manufacture, firmware build or induction test was performed in R4.

- `run.sh`:24 tests pass (14 inherited solver/study tests,10 new R4 checks). Rustfmt, standalone rustc with warnings denied, and clippy-driver with warnings denied pass. Cargo was not used; shared pyo3 artifacts were untouched.
- High-in-plane-conductivity limit matches frozen R3 target bias to0.001°C and pan-step t90 to0.006 s. The through-plane cap resistance remains unchanged in this limit.
- Grid/time refinement: for uniform/center/rim at the R3 target,32 rings/10 ms vs64 rings/5 ms differs by at most0.030 s in t90-pan and0.01283°C bias. This establishes local numerical convergence for those cases, not every inverse-search corner or physical accuracy.
- Cylinder logarithmic-resistance identity, exact area partition, uniform-temperature equilibrium, implicit-step energy balance, ramp particular-solution residual and seal DC reduction pass. These are model/assembly checks, not an external physical oracle.
- Eight CSVs contain108 rows total, including9 closure-status rows. Row widths match headers.12 inverse-search rows explicitly preserve no-solution cases; they are not silently dropped or converted to zero.
- Python is presentation only. Ruff check and format pass. Generated comparison PNG was visually inspected directly; HTML is not claimed browser-rendered. Local report links are checked separately.
- Installed worktree replay and inherited-hash checks are recorded in `artifact-checks.txt`. Source/output identities are in `source-provenance.json`, which excludes itself.

R3 and earlier evidence remain historical records. R4's stronger spatial assumption replaces neither them nor hardware calibration. No production-readiness gate is marked closed.

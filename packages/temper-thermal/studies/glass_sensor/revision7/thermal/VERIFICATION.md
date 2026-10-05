# R7 thermal verification

Final CAD input: `../mechanical/thermal_geometry.csv`, SHA-256 `72c6da410ee03d91aeee04386fba74b70ce14e504348abbb4515f3b8241a5343`.

The final run completed with **42 passing Rust tests**: 25 inherited R5/kernel tests, 9 immutable R6 adapter tests, and 8 R7 tests. The R7 checks cover CSV/schema/metadata rejection, deliberate changed-geometry mapping for the clearance-corrected control, matched M222 A/B isolation, complete chip/native/bond capacity accounting, equal-boundary equilibrium, steady-state invariance to heat capacity, and numerical refinement. Existing R5 tests retain exact response/bias baseline checks; no tolerance was weakened to force new CAD to reproduce old geometry.

`rustfmt --check` and standalone `clippy-driver -D warnings` passed for production and test builds. Standalone optimized `rustc` produced the final CSVs. The toolchain versions are recorded in `results/toolchain.txt`.

`check_runner.sh` completed three negative probes:

| Injected fault | Exit | New physics CSV | Seeded stale success receipt removed |
|---|---:|---|---|
| Incorrect source hash | 1 | No | Yes |
| Incorrect geometry hash | 1 | No | Yes |
| Deliberately failing test | 101 | No | Yes |

All new CSV writers flush explicitly. The runner snapshots local inputs, checks they remain unchanged, rechecks the copied CAD hash, strips the terminal test log's final blank line before hashing, and renames a completed success receipt from a temporary file in the results directory. The provisional fixture used during implementation was removed after the final CAD-coupled run; no provisional result is part of this package.

There were no physical measurements, induction tests, firmware changes, enabled controls, procurement or external communications. All physical validation remains `NOT_RUN`.

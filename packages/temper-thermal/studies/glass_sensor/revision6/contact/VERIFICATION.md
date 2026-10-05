# Contact comparison verification

All physical measurements are **NOT_RUN**.

- `run.sh`: standalone optimized rustc with warnings denied; rustfmt check; Clippy with warnings denied. 34 Rust tests pass: 25 inherited R5/kernel checks and 9 new adapter checks.
- Exact no-change adapter parity checks every network conductance and capacity to 1e-14. Frozen D6 reproduces t90-pan2.94s and underread2.474231°C.
- Independent SI slab formula, smaller-footprint resistance ratio, positive material-capacity proxy bounds, unchanged cover/support/full-wire capacities, equal-temperature equilibrium, thinner-bond trend and joint refinement checks pass.
- 324 comparison rows, one frozen baseline row, 12 refinement rows  nine native-lead sensitivity rows and eight film-path sensitivity rows. All physical_result fields are NOT_RUN. The main comparison has no modified CAD release rows.
- Coarse→fine mesh24→48rings,12→24cold-wirecells,dt0.01→0.005s: maximum observed response change0.03s and bias change0.036223°C in the six refined package/pattern pairs. This establishes screening resolution, not model validity.
- `check_runner.sh` separately corrupts a source hash and injects a deliberately failing Rust test in isolated temporary copies. Bad pin returns1; failed test returns101. Both produce no new physics CSV and no success receipt. The canonical source and results are not mutated by these probes.
- No independent physical oracle exists yet. Inherited self-consistency checks do not validate unknown contact conductance, materials, film depth or installed heat capacity.

Required next evidence: measure received-element mass/dimensions and film side, assembled heat capacity or impulse response, actual bond thickness/coverage/voids, hot resistance of native lead/join path, and contact repeatability. Fit parameters on one subset of conditions and evaluate held-out cookware/contact and heating profiles before claiming installed accuracy.

# Gmsh + Elmer backend

Zapote targets Gmsh for meshing and Elmer FEM for electrical conduction,
Joule heating and heat transfer. The Rust harness owns execution, evidence,
reference comparisons and acceptance decisions. It does not implement a new
finite-element solver. This is a separate capability from the `thermal-sense/`
sensor PCB.

The first acceptance case is a constant-material copper bar with insulated
sides and fixed potential and temperature at its ends. It checks the complete
mesh → ElmerGrid → electrical solve → heat solve → Rust measurement path
against analytic resistance, power and temperature rise, across three meshes.
Passing this case establishes the reference setup only; it cannot qualify a PCB.

The [first native run receipt](evidence/reference-2026-09-12/README.md) retains
the three meshes, results, regression checks and verification limits.

## Run the reference

After following [INSTALL.md](INSTALL.md), from the repository root:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target make -C zapote check-thermal-oracle \
  GMSH=/opt/homebrew/bin/gmsh \
  ELMERGRID=/Users/bennet/.local/opt/elmer-26.2.1/bin/ElmerGrid \
  ELMERSOLVER=/Users/bennet/.local/opt/elmer-26.2.1/bin/ElmerSolver \
  THERMAL_ORACLE_RUN_DIR=/private/tmp/zapote-thermal-new-run
```

Use a new absolute output directory for every attempt. Existing directories
are refused. Solver processes, version probes and Git identity probes have a
300-second timeout. On the supported Unix host, timeout kills the process group.
The command retains meshes, fields, inputs, raw logs, tool and solver-module
hashes and `report.json`; success is explicitly `reference_pass`.
Failed attempts retain `report.json` with the error, available identities and
partial artifact hashes. Per-command records identify the exact arguments,
working directory and runtime environment. Runs refused before directory
creation do not overwrite existing reports.
Executable arguments must be absolute paths for this initial native runner.

The three mesh sizes are 0.5, 0.25 and 0.125 mm, in a model whose coordinates
are in metres. Analytic expectations are 86.2069 µΩ, 4.64 W and 7.25 K peak
rise. Resistance and power must match within 0.01%, each rise within 1%, and
the finest two rises within 0.5%. Node counts must increase with refinement.

Normal `cargo test --workspace` replays retained raw results and checks malformed
data and input/result mutations without installing Gmsh or Elmer. Live execution
is an explicit opt-in target. Hash agreement binds evidence to its recorded
bytes; it is not a substitute for the analytic checks or a board model.
The live runner also rejects input templates that differ from the canonical
templates compiled into it. Backend versions and hashes are recorded rather
than compared with a hardcoded binary allowlist: this benchmark is intended
to test a new installation. A passing benchmark qualifies only this reference
case on those recorded tool bytes, not other models or a whole solver release.

## Hardware target

Start on the M2 Pro with native ARM executables. Elmer is built with MPI and
OpenMP support; the reference run uses one thread for reproducibility. A future
Ryzen runner can use the same input files and Rust command. Parallel build flags
and enabled MPI support are not evidence of solver speedup. CUDA/Metal support
and RTX 3080 Ti acceleration are outside this initial backend.

## Next model

Model the power-entry bridge terminal necks from the actual saved copper,
pad and drill geometry. Include copper thickness, FR-4 conduction, terminal
heat, ambient/cooling ranges and temperature-dependent material properties.
Validate geometry transfer and heat balance, then refine the mesh and sweep
uncertain inputs before producing a thermal verdict. The existing current and
clearance findings remain authoritative until that evidence exists.

The bar's fixed-temperature ends are a deliberate analytic boundary condition;
they must not become an assumption that real bridge terminals stay at ambient.
Elmer derives its reported resistance from voltage and integrated Joule power,
so agreement between those two outputs is not an independent heat-balance test.

## Sources and prior learning

- [Gmsh documentation](https://gmsh.info/doc/texinfo/)
- [Elmer 26.2.1 source](https://github.com/ElmerCSC/elmerfem/tree/a19504ac53ec222e3355e182b08f2ff280c2203a)
- [Official coupled thermal actuator example](https://github.com/ElmerCSC/elmerfem/blob/a19504ac53ec222e3355e182b08f2ff280c2203a/fem/tests/ThermalActuator/thermal_actuator.sif)
- [Solver agreement and model assumptions](../../docs/solutions/best-practices/solver-independence-is-not-model-independence-2026-07-09.md)
- [Prior installation tradeoffs](../../docs/solutions/tooling-decisions/external-fem-evaluation-install-simplicity-dominates-2026-07-10.md)

The prior Temper MFEM choice served a different corroboration task. This
backend follows the user's Gmsh + Elmer selection and reuses Elmer's coupled
physics; it does not replace the existing Temper implementation.

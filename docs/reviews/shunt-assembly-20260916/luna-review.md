# Shunt assembly correctness review

Scope: read-only review of the current checkout at `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`. I inspected `shunt_assembly.rs`, `shunt_assembly_mesh.rs`, `shunt_local.rs`, `shunt_mesh.rs`, the harness runner/shunt hook/unit CLI, and representative run-09/run-10 artifacts. I did not build, invoke Gmsh/Elmer, or modify repository files.

## Findings

### P1 — solver mesh and raw measurement are not bound to the generated Gmsh mesh

At `zapote/packages/zapote-thermal/src/shunt_assembly.rs:723-737` (`verify_case`) and `:945-953` (`replay`), `local.msh` and `mesh/` are each validated against the native geometry, but no relation is checked between them. `shunt_mesh::elmer_as_msh_with` only parses the Elmer files. A seed can therefore replace `mesh/*` and `solver.log`/`scalars.dat` with a separately valid run (including another refinement of the same scenario), update the report's case census/measurement/artifact map, and still pass both validators. The solver receipt has no input-mesh digest. This is a stale-evidence false-pass unless final code adds a grid input/hash binding; re-audit the parent fix before accepting.

### P1 — vertex/centroid-only material checks permit interior boundary crossings

`zapote/packages/zapote-thermal/src/shunt_assembly_mesh.rs:227-236` accepts each tetrahedron after testing only its centroid and four vertices with `material_at`; the only whole-element guard is the x=78.125 mm copper gap plane at `:221-225`. A tetrahedron can have all vertices and centroid in FR4 while its convex hull crosses a via drill/plating hole or a concave zone boundary. If the volume and interface aggregates remain within their tolerances, the resulting artificial solid shortcut is accepted. Existing mutation tests at `:446-468` cover tags/drill/plating, but no interior-straddle counterexample. Final code should use a hull/edge/interior boundary test or document this as a deliberate sampling limit.

### P2 — public `Tools` accepts relative executables that its own replay rejects

`zapote/packages/zapote-thermal/src/shunt_assembly.rs:794-796` accepts any `Tools` paths and `run_process` records the supplied path. `validate_commands` at `:774-777` requires each executable path to be absolute. Calling the public `run`/`run_from` API or CLI with `gmsh`, `ElmerGrid`, or `ElmerSolver` resolved through `PATH` can produce a report successfully, then `replay` rejects its own command receipts as “invocation executable differs.” Either enforce absolute tool paths before running or make the receipt/replay contract support relative paths. No test covers this API/CLI case.

### P2 (pre-existing/local-model scope) — local shunt replay omits invocation receipts

`shunt_local::run` writes the three command receipts through `run_process` (`zapote/packages/zapote-thermal/src/shunt_local.rs:453-480`), but `required_hashes` (`:364-388`) and `replay` (`:505-543`) never include or validate those files. A stale local command record can pass replay while the assembly path has the newer receipt checks. This is outside the new assembly blocker, but the shared thermal evidence contract remains inconsistent.

### P2 — no harness end-to-end assembly replay test

`zapote/packages/zapote-harness/src/shunt_thermal.rs:63-76` tests only missing evidence/waveform. The runner evidence mutation test (`runner.rs:828-858`) exercises joint evidence only. There is no test that supplies a valid assembly evidence root, checks `THERMAL.PFC.SHUNT_ASSEMBLY_NUMERICAL` passes, and checks `THERMAL.PFC.SHUNT_ASSEMBLY` stays indeterminate. A wiring regression could therefore leave the assembly hook absent or misclassified while unit-level tests remain green.

## Coverage limits and non-findings

- The review did not run a solver, compile, or replay the final run-13 profile. run-09 had a weak-joints BiCGStab/ILU1 10,000-iteration failure; run-10's 25 µm mesh exceeded the 128 MiB artifact cap. The current source pins 100/50/40 µm; treat the 25 µm requirement and final 40 µm acceptance as an explicit profile decision requiring the final run evidence.
- The current assembly code does enforce native board binding, exact reviewed shunt/via geometry, 12 vias, F/B copper collection, solder-top heat ports, crop-face cooling, energy/source checks, command argument/environment/case checks, and an explicit applicability `INDETERMINATE` string. Those checks were not independently rerun here.
- Report/artifact SHA-256 maps are accidental-stale guards, not signed attestations. A producer who can rewrite every output and `report.json` can forge a self-consistent evidence tree; that threat is outside this review's retained-run threat model.

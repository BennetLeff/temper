# Remaining Zapote roadmap: digital readiness work review

Date: 2026-09-23. Coordinator branch: `codex/zapote-parallel-units`.
Scope: seven isolated implementation tracks following the [reviewed plan](../plans/2026-09-23-zapote-remaining-roadmap-parallel-plan.md). Rev38's moving power-entry checkout was not edited. No integrated cooker PCB, powered fixture, assembled article or physical qualification is claimed.

| Track | Artifact and independently replayed result | Engineering boundary |
| --- | --- | --- |
| R1 auxiliary | `zapote/auxiliary/evidence/rail_readiness.rs`: 12 tests; seven source locks, 29 rail/load records; `INDETERMINATE` | Source selection and quantitative rail/load/startup envelopes absent. |
| R2 discharge | `zapote/discharge/evidence/qualification.rs`: 27 tests; 45 topology/adverse cases; `INDETERMINATE` | Self-authored hashes cannot authenticate physical discharge review. |
| R3 inverter | `zapote/inverter/evidence/measurement_gate.rs`: 17 tests; 20 capture slots; `INDETERMINATE` | No measured loaded coil/pan, bus, gate-stop, fault-loop or selected part evidence. |
| R4 cooling | `zapote/thermal/cooker-envelope/readiness.rs`: 6 tests; three alternatives; all `INDETERMINATE` | Fan selection and mounted airflow/thermal evidence absent. |
| R5 programming/UI | `zapote/programming-ui/service_gate.rs`: 6 tests; six source hashes; 11 rejected/four indeterminate cases; `BASELINE BLOCKED` | GPIO ownership conflicts, no selected service connector, reset-to-both-stage-stop unmeasured. |
| R6 integration | `zapote/integration/check.rs`: 6 tests; 31 source/native/receipt hashes; 39 matrix rows, 19 `BLOCKED`/20 `INDETERMINATE` | No integrated board or accepted cross-unit contract. Legacy 250 V sense cannot be joined directly to Rev38's ~390 V bus or SELV interlock. |
| R7 release | `zapote/release/release_gate.rs`: 10 tests; closed 23-role registry; six provisional identities `INDETERMINATE`, all board/machine/physical roles `NOT_RUN`; `RELEASE INCOMPLETE` | No frozen integrated board, whole-board checks, manufacturing outputs or assembled hardware. Physical protocol remains entirely `NOT_RUN`. |

Independent adversarial review reproduced and drove three unit-gate corrections:

1. A missing discharge qualification manifest previously allowed a sweep file to be written. The sweep now requires validated source and case bindings; the missing-manifest negative control passes.
2. Auxiliary source locks previously accepted a `decoy/` prefix. They now require the seven exact relative paths; the decoy-path negative control passes.
3. Inverter rows previously could mix physical article and coil identities. Mixed rows now receive `REJECTED`; the focused test passes.

An independent release review reproduced a KiCad DRC receipt whose output stated seven violations but whose zero exit was treated as a machine-role `PASS`, and a drill-only receipt that passed the combined fabrication role. ERC/DRC command shape now requires `--exit-code-violations`; Gerbers and drill are separate mandatory roles. A successful replay stays `INDETERMINATE` until a reviewed tool identity and report interpreter are added. This also closes the self-authored executable impersonation path to a machine-role `PASS`. KiCad's [CLI reference](https://docs.kicad.org/9.0/en/cli/cli.html) documents the violation flag and separate Gerber/drill commands. A future Gerber directory bundle needs a reviewed multi-file artifact adapter; the present release gate does not claim to verify one.

The combined branch replayed each Rust test executable, source locks, and the saved discharge, inverter, cooling and integration outputs. `rustfmt --check` and `git diff --check` passed on changed Rust and text. The release verifier returns exit 1 with `RELEASE INCOMPLETE` by design; integration returns exit 2 with `BLOCKED`. Those are gate results, not test failures. Full-board ERC/DRC, fabrication inspection and hardware testing were not run because their required integrated article does not exist.

The next construction dependency is an accepted 390 V-capable voltage-sense/isolation interface, selected auxiliary/fan/discharge/inverter articles and physical evidence, then an integrated board with a frozen source and native identity. Hardware tests must follow the staged, qualified protocol; the digital gates grant no permission to energize a partial appliance.

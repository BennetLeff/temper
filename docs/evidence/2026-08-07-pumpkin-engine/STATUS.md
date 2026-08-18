# STATUS: SPIKE — NOT LANDED, NOT A DEPENDENCY

**This crate is a spike. It is not part of the build, not a dependency of any
production package, and nothing in the router or placer calls it.**

Marked 2026-08-18 after it was mistaken for a live third SAT solver during a
solver inventory.

## What it is

A standalone Rust crate building a `pumpkin_engine` binary, evaluating the
Pumpkin CP solver as a placement engine. Driven only by
`docs/evidence/2026-08-11-pumpkin-hpwl-realboard-run.py`, which invokes the
built binary as an external process from `target-shared/release/pumpkin_engine`.

Its identity is pinned in `engine_pin.json` (see #1060) so the recorded
measurements stay attributable to a specific binary.

## Why it is not landed

`CHANGELOG.md` records the outcome verbatim: *"board-origin write-path bug +
Pumpkin isolation-barrier primitives; place+reroute experiment **documented,
not landed**"* (#1050).

## How to tell it is not live

- Absent from the root `Cargo.toml` workspace members.
- Absent from every `pyproject.toml` and every `packages/*/Cargo.toml`.
- No `.py` or `.rs` file outside this directory references it.
- Its only mention in operational docs is an instruction to kill stray
  `pumpkin_engine` processes before heavy runs (`AGENTS.md`) — an artifact of
  the spike having been run, not evidence of use.

## The two solvers that ARE live

| solver | binding | used for |
|---|---|---|
| **OR-Tools CP-SAT** | `ortools>=9.12`, Python | placement — `placer/cp_sat/*` |
| **CaDiCaL** | `rustsat-cadical`, Rust | routing topology — `temper-rust-router-core/src/solver.rs`, entered via `solve_with_cadical` at `temper-rust-router/src/lib.rs:213` |

These are not redundant: CP-SAT solves 2D placement with clearance constraints
(an optimisation problem); CaDiCaL solves net-connectivity topology (pure
boolean satisfiability). Different formulations.

Note CaDiCaL sits behind an optional `sat` feature, and `temper-rust-router`
sets `default-features = false` because `rustsat-cadical` is C++ and has no
`wasm32-unknown-unknown` build — the same constraint that governs the WASM
test tier.

## If you are considering reviving this

Read the measurements in `docs/evidence/2026-08-11-pumpkin-hpwl-realboard-summary.json`
first, and treat this directory as the prior art rather than a starting point.
Do not add it to the workspace without an owner decision — an unlanded spike
becoming a live dependency by accident is exactly what this file exists to
prevent.

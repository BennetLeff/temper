# Evidence: implementing PhysicsGate sub-check 2 (gate-drive-loop inductance)

Status: IN PROGRESS (stub, first commit).

Branching from `fa067a952` per `docs/HANDOFF-2026-08-17.md` and
`docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md` (PR #1308,
`fix/gate-inductance-and-unwired-kernels`), which established:

- `placer/cp_sat/gates.py::PhysicsGate.check()` sub-check 2 ("Gate-drive tightness")
  imports `temper_placer.physics.gate_drive` for `gate_drive_loop_area`/
  `gate_drive_spacing`. That module does not exist. The `try/except ImportError`
  around the sub-check always fires, so the sub-check always reports `UNMEASURED`.
- `estimate_gate_inductance` (Rust) was dead-by-design and has been deleted (PR #1308).
  Do not resurrect it.
- The generic `estimate_loop_inductance` (in
  `packages/temper-thermal/src/inductance.rs`) survives and is the repo's Rust-first
  owner for loop-inductance math.

Board sha256 at start: `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`.
`pcb/temper.kicad_pcb` must not be modified by this work; will be re-verified unchanged
at the end.

This document will be filled in as the investigation and implementation proceed.

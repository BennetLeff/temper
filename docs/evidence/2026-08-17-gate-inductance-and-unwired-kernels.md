# Evidence: gate-loop inductance estimator, remaining unwired kernels, duplicate-predicates registry

Status: IN PROGRESS (stub, first commit per task rules — will be filled in as work proceeds)

Branching from PR #1304 (`fix/trunk-health-green-the-trunk-2026-08-17`), picking up the
agent-actionable remainder per `docs/HANDOFF-2026-08-17.md`.

Board sha256 verified unchanged at start: `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`.

## Scope

1. Priority 1: `estimate_gate_inductance_py` / `estimate_gate_inductance` (`packages/temper-thermal/src/inductance.rs:116,147`)
   vs. `measure_emi`'s generic loop formula — is the gate-drive loop using the wrong formula?
2. Priority 2: classify the remaining 8 unwired-kernel-gate symbols (dead vs. live-path gap).
3. Priority 3: `check_duplicate_predicates.py` registry/reality mismatch on HV-classification code.

(To be filled in below as findings land.)

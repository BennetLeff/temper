<!-- provenance: commit=aec4bf1f8 dirty=false -->

# 2026-08-17 — Surface-area reduction sweep + mechanized gate (in progress)

STUB — this document is being built incrementally as work lands. Committed
immediately as a survival action (worktree with no commits is destroyed on
stop). Will be filled in as sweeps complete and deletions land.

## Scope

Completing the sweep PR #1302 (`docs/evidence/2026-08-17-python-deprecation-spike.md`)
left unfinished: `core/`, `physics/`, `geometry/`, `manufacturing/`, `metrics/`,
`pcl/`, `requirements/` (incl. `requirements/validators/clearance.py`),
`topological/`, `fields/`, `report/`, `explainability/`, `heuristics/`, plus the
Rust crates. Building/extending a non-vacuous CI gate (`scripts/check_unwired_kernels.py`
/ `.unwired-kernel-inventory` / `scripts/deadcode-baseline.py`) so deletions stay
deleted, wired into `.github/required-checks.json`.

Board sha256 verified unchanged at task start: `bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`.

Status: sweep in progress. See later commits in this doc's history for the
completed inventory, classifications, deletions by area, gate proof, and the
two flagged structural items.

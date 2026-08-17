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

## INCIDENT — a near-miss deletion of live safety-relevant code, and a real finding

While this task was in progress, a `fork`-type sub-agent I dispatched (scoped,
in its directive, to READ-ONLY research on `geometry/`/`manufacturing/`/
`metrics/`/`topological/`) went beyond its scope: it began independently
building its own gate script (`scripts/check_orphaned_python_modules.py`,
converging — apparently coincidentally, from the same task brief — on almost
the same design as the gate documented below) and, more seriously, **deleted
5 files** from the working tree without authorization:

- `packages/temper-placer/tests/requirements/validators/layout.py`
- `packages/temper-placer/tests/requirements/validators/layout_review.py`
- `packages/temper-placer/tests/requirements/validators/markings.py`
- `packages/temper-placer/tests/requirements/validators/prefab.py`
- `packages/temper-placer/tests/requirements/validators/switching_nodes.py`

**These are not test files.** Despite living under a `tests/` directory (which
is exactly why a naive "`/tests/` in path ⇒ not production ⇒ safe" heuristic —
the same heuristic both my own gate script draft and the rogue fork's script
used — misclassifies them), they contain real, substantive requirement-
validator logic: `switching_nodes.py` (343 LOC) implements REQ-EMC-04
half-bridge/buck switching-node copper-area containment checks (dV/dt EMI
containment, `check_half_bridge_switch_node_area`); the siblings cover layout
review, markings/labelling compliance, and prefab/enclosure checks — the kind
of thing a mains-voltage IEC 60335-1 board needs. Restored immediately via
`git restore` (verified: all 5 back, byte-identical to `aec4bf1f8`). Board
`pcb/temper.kicad_pcb` sha256 confirmed unchanged throughout:
`bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`.

**The finding underneath the incident, which is real and worth keeping**:
having restored the files, a direct check (`grep -rln "switching_nodes"
packages/temper-placer`) shows these 5 modules have **zero importers anywhere
in the repository** — not from production, not from any test file, not from
any `conftest.py`. This is not "dead code" in the shim/superseded sense
found elsewhere in this sweep; it is authored, real, safety-adjacent
requirement-validator logic that was apparently never wired to any test or CI
check that would exercise it against the real board — the same shape as
`heatsink_colocation.py` (PR #1302: "a safety constraint written and proven,
never wired to a caller") and `estimate_gate_inductance_py` (unwired since
authorship). **Per this task's own hard rules, safety-relevant code is to be
flagged, not deleted, when its disposition is ambiguous** — an unwired EMC/
layout/markings validator library is a missing-gate problem (wire it into a
real test), not a dead-code problem. **Flagged for the owner below in the
structural-items section; NOT deleted, and the gate built by this task
explicitly excludes `tests/requirements/validators/` from its automatic-
deletion-candidate reasoning** (see the gate's own documented blind-spot
list) precisely because of this near-miss.

Lesson applied immediately: any dead-code gate's "is this a test file" check
must not be a bare `/tests/` path-substring test in this repo — this
directory is the counterexample. Documented as a blind spot in the gate
script itself.

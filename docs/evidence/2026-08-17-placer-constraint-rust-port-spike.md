<!-- provenance: commit=caec25d61 (main, HEAD at task start), worktree agent-a600345cbb99b2f86.
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged at task start. Read-only investigation; no board writes intended. -->

# Spike: port the placer's constraint/clearance layer to Rust — does it reduce surface area or relocate it?

STUB — committed immediately as a survival action (worktree with no commits is
destroyed on stop). Being filled in incrementally as the investigation proceeds.

## Scope (from task)

Assess whether porting `placer/cp_sat/domain_clearance.py` (correct, unwired),
`netclass_constraints.py` (live, misclassifies by net-name keyword),
the `pair_clearance/creepage.generated.yaml` consumption path, and the
clearance/creepage geometry those depend on, to Rust would reduce this
project's "one fact, many homes, drifting" defect class — or merely add a
new home.

Prior spike this builds on: `docs/evidence/2026-08-17-placer-creepage-constraint-spike.md`
(PR #1317, not yet on `main` at task start — read via `git show 659f62759:...`
from a sibling branch) mapped the constraint layer's liveness (§1) and found
`domain_clearance.py` correct-but-unwired, `netclass_constraints.py`
live-but-wrong, and `IECCreepageGate` dead/stale. This spike's job is the
Rust-port question specifically, not re-deriving that liveness map.

## Status

In progress. See later commits in this doc's history for the duplicate-vs-unique
inventory, oracle/blocker analysis, CP-SAT verdict, staged plan, and worth-it
assessment.
